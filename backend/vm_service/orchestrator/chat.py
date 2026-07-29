import json
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Form, Header, HTTPException, Request, UploadFile, status
from starlette.datastructures import UploadFile as StarletteUploadFile
from pydantic import BaseModel, Field

from ek_client import ek_client
from firewall.ai_firewall import check_message
from firewall.file_processor import FILE_REJECT_MESSAGE, process_uploads
from firewall.schemas import ExecutionPlan, ExecutionStep, Intent, ProcessedFile, UserContext

from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, LlmMessage, TokenUsage
from mcp_tools.mcp_catalog import render_for_planner
from mcp_tools.dispatcher import MCPDispatchError, dispatch_mcp_action
from runtime.redis_gate import redis_concurrency_gate, set_runtime_state
from runtime.rag_catalog import refresh_rag_catalog


REQUEST_REJECT_MESSAGE = "Yêu cầu của bạn không thể xử lý hoặc thông tin bạn yêu cầu không tồn tại"
FILE_CONTEXT_SOFT_ISSUES = {
    "unsupported_file_format_or_action",
    "unsupported_modality",
    "missing_file_context",
    "potential_unauthorized_file_access",
}
router = APIRouter(prefix="/v1", tags=["Chat Orchestrator"])


class ChatFirewallRead(BaseModel):
    allowed: bool
    risk_level: str
    reason: str
    detected_issues: list[str] = Field(default_factory=list)


class ChatFileRead(BaseModel):
    id: Optional[str] = None
    original_file_name: str
    file_type: str
    sanitized: bool
    flags: list[str] = Field(default_factory=list)


class ChatUsageRead(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    intent: Intent
    firewall: ChatFirewallRead
    status: str
    answer: str
    usage: ChatUsageRead
    files: list[ChatFileRead] = Field(default_factory=list)


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _title_from_message(message: str) -> str:
    normalized = " ".join(message.split())
    return (normalized[:80] or "Cuộc trò chuyện mới").strip()


def _normalize_conversation_id(conversation_id: Optional[str]) -> Optional[str]:
    value = (conversation_id or "").strip()
    if not value or value.lower() == "string":
        return None
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="conversation_id không hợp lệ") from exc


def _user_from_headers(
    x_user_id: Optional[str],
    x_user_email: Optional[str],
    x_user_role: Optional[str],
) -> UserContext:
    role = (x_user_role or "manager").strip().lower()
    if role not in {"admin", "ceo", "manager"}:
        role = "manager"
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=REQUEST_REJECT_MESSAGE)
    return UserContext(user_id=user_id, email=x_user_email, role=role)  # type: ignore[arg-type]


def _intent_from_plan(plan: ExecutionPlan) -> Intent:
    actions = {step.action for step in plan.steps if step.action}
    if any(action.startswith("mcp:") or action == "mcp_tool" for action in actions):
        return "task_execution"
    if "sql_query" in actions:
        return "business_query"
    if "rag_search" in actions:
        return "rag_query"
    return "general_chat"


def _merge_usage(total: TokenUsage, addition: TokenUsage) -> None:
    total.input_tokens += addition.input_tokens
    total.output_tokens += addition.output_tokens
    total.total_tokens += addition.total_tokens


async def _run_rag_search(message: str, action_input: dict[str, Any]) -> dict[str, Any]:
    query = str(action_input.get("query") or message)
    top_k = int(action_input.get("top_k") or 5)
    score_threshold = float(action_input.get("score_threshold") or 0.55)
    results = await ek_client.rag_search(query=query, top_k=top_k, score_threshold=score_threshold)
    context_blocks: list[str] = []
    for item in results.get("results", []):
        source = item.get("source") or {}
        if isinstance(source, dict):
            source_name = source.get("file_name") or source.get("document_id") or "unknown"
        else:
            source_name = str(source)
        context_blocks.append(f"Source: {source_name}\n{item.get('content', '')}")
    return {
        "query": query,
        "total": results.get("total", 0),
        "context_text": "\n\n".join(context_blocks),
    }


async def _run_sql_query(message: str, user: UserContext) -> dict[str, Any]:
    if user.role == "manager":
        return {"denied": True, "content": REQUEST_REJECT_MESSAGE}
    overview = await ek_client.business_overview()
    return {"denied": False, "overview": overview, "question": message}


def _file_payloads(files: list[ProcessedFile]) -> tuple[list[dict], list[str]]:
    images_payload: list[dict] = []
    md_contexts: list[str] = []
    for file in files:
        clean_p = Path(file.clean_path)
        if not clean_p.exists():
            continue
        if file.file_type == "md":
            try:
                md_text = clean_p.read_text(encoding="utf-8", errors="replace")
                md_contexts.append(
                    f"--- [Nội dung tệp Markdown: {file.original_file_name}] ---\n{md_text}\n--- [Kết thúc tệp] ---"
                )
            except Exception:
                pass
        elif file.file_type == "png":
            try:
                raw_bytes = clean_p.read_bytes()
                images_payload.append(
                    {
                        "data": raw_bytes,
                        "mime_type": file.mime_type or "image/png",
                    }
                )
            except Exception:
                pass
    return images_payload, md_contexts


async def _synthesize_answer(
    message: str,
    user: UserContext,
    files: list[ProcessedFile],
    context: dict[str, Any],
    step: Optional[ExecutionStep],
) -> LlmGenerateResponse:
    if (context.get("business") or {}).get("denied"):
        return LlmGenerateResponse(
            provider="google",
            model="policy",
            phase="default",
            content=REQUEST_REJECT_MESSAGE,
            usage=TokenUsage(),
            latency_ms=0,
        )

    prompt_parts: list[str] = []
    rag_context = (context.get("rag") or {}).get("context_text", "")
    if rag_context:
        prompt_parts.append(f"Tri thuc RAG:\n{rag_context}")

    business = context.get("business") or {}
    if business.get("overview") is not None:
        prompt_parts.append(f"Du lieu nghiep vu:\n{json.dumps(business['overview'], ensure_ascii=False)}")

    mcp_blocks: list[str] = []
    for item in context.get("mcp", []):
        if item.get("status") == "success":
            mcp_blocks.append(
                f"Ket qua tu {item.get('action')}: {json.dumps(item.get('result'), ensure_ascii=False)}"
            )
    if mcp_blocks:
        prompt_parts.append("Ket qua MCP tool:\n" + "\n".join(mcp_blocks))

    images_payload, md_contexts = _file_payloads(files)
    if md_contexts:
        prompt_parts.append("\n\n".join(md_contexts))

    step_hint = step.thought if step else "Tong hop cac buoc truoc do va tra loi nguoi dung."
    prompt_parts.append(
        f"Yeu cau nguoi dung ({user.role}): {message}\n\n"
        f"Huong dan buoc hien tai: {step_hint}\n\n"
        "Hay tra loi truc tiep, day du va chinh xac cho nguoi dung."
    )
    full_prompt = "\n\n".join(part for part in prompt_parts if part)

    return await llm_router.generate(
        LlmGenerateRequest(
            phase="default",
            max_output_tokens=1536,
            temperature=0.2,
            messages=[LlmMessage(role="user", content=full_prompt)],
            images=images_payload,
            metadata={
                "chat_route": "plan_execute",
                "user_id": user.user_id,
                "role": user.role,
                "file_count": len(files),
            },
        )
    )


async def create_execution_plan(
    message: str,
    user: UserContext,
    files: list[ProcessedFile],
) -> ExecutionPlan:
    rag_knowledge_catalog = await refresh_rag_catalog()
    file_summary = [
        {"file_name": file.original_file_name, "file_type": file.file_type, "flags": file.flags}
        for file in files
    ]
    prompt = f"""
Ban la AI Planner cho VietMAS. Hay phan tich yeu cau nguoi dung va sinh ra Ke hoach thuc thi (Execution Plan) gom chuoi cac buoc (steps) can thuc hien.
Chi tra ve JSON hop le theo cau truc:
{{
  "plan_name": "Kế hoạch xử lý yêu cầu",
  "total_steps": 2,
  "steps": [
    {{
      "step_number": 1,
      "step_name": "Tra cứu trí thức RAG",
      "action": "rag_search",
      "action_input": {{}},
      "thought": "Tìm kiếm chính sách bán hàng liên quan trong RAG"
    }},
    {{
      "step_number": 2,
      "step_name": "Tổng hợp câu trả lời",
      "action": "llm_synthesize",
      "thought": "Tổng hợp thông tin RAG để trả lời người dùng"
    }}
  ]
}}

Cac loai action hop le:
- rag_search: truy van tri thuc RAG
- sql_query: truy van du lieu CSDL nghiep vu
- mcp_tool: danh dau buoc thao tac tool/file khi can phan tich file dinh kem
- llm_synthesize: tong hop ket qua tu cac buoc va sinh phan hoi cuoi cung
- mcp:<mcp_name>.<tool_name>: goi dung MCP tool trong danh muc

RAG knowledge catalog hien co:
{json.dumps(rag_knowledge_catalog, ensure_ascii=False, indent=2)}

Files dinh kem:
{json.dumps(file_summary, ensure_ascii=False)}

Quy tac lap ke hoach:
- Neu co file dinh kem, uu tien buoc phan tich file (llm_synthesize) va/hoac MCP tool phu hop.
- Neu cau hoi ve tri thuc noi bo/chinh sach/cong ty/he thong, dung rag_search roi llm_synthesize.
- Neu can so lieu nghiep vu dong tu CSDL, dung sql_query roi llm_synthesize.
- Neu can thao tac email/tool, dung mcp:<mcp_name>.<tool_name>; co the ket hop llm_synthesize sau do.
- Ket thuc bang llm_synthesize de tra loi nguoi dung, tru khi chi gui email bang send_email.

Message: {message}
Role: {user.role}

DANH MUC MCP TOOL DUOC PHEP LUA CHON:
{render_for_planner()}

Neu dung MCP, action phai dung dinh dang `mcp:<mcp_name>.<tool_name>` va phai
chon dung mot tool co trong danh muc. Khong tu sang tao ten MCP/tool.
"""
    try:
        response = await llm_router.generate(
            LlmGenerateRequest(
                phase="default",
                max_output_tokens=384,
                temperature=0,
                messages=[LlmMessage(role="user", content=prompt)],
                metadata={"planner": "execution_plan", "user_id": user.user_id},
            )
        )
        parsed = _json_object(response.content)
        return ExecutionPlan.model_validate(parsed)
    except Exception:
        if files:
            return ExecutionPlan(
                plan_name="Phân tích file đính kèm",
                total_steps=1,
                steps=[
                    ExecutionStep(
                        step_number=1,
                        step_name="Phân tích nội dung file",
                        action="llm_synthesize",
                        thought="Phân tích file đính kèm và trả lời người dùng",
                    )
                ],
            )
        return ExecutionPlan(
            plan_name="Trả lời yêu cầu",
            total_steps=1,
            steps=[
                ExecutionStep(
                    step_number=1,
                    step_name="Tổng hợp câu trả lời",
                    action="llm_synthesize",
                    thought="Trả lời trực tiếp yêu cầu của người dùng",
                )
            ],
        )


async def execute_plan(
    message: str,
    user: UserContext,
    files: list[ProcessedFile],
    plan: ExecutionPlan,
) -> tuple[LlmGenerateResponse, list[dict]]:
    context: dict[str, Any] = {"rag": None, "business": None, "mcp": []}
    execution_results: list[dict] = []
    llm_response: Optional[LlmGenerateResponse] = None
    usage_total = TokenUsage()

    for step in plan.steps:
        action = (step.action or "").strip()
        if action == "rag_search":
            context["rag"] = await _run_rag_search(message, step.action_input)
            continue

        if action == "sql_query":
            context["business"] = await _run_sql_query(message, user)
            continue

        if action.startswith("mcp:"):
            try:
                action_arguments = dict(step.action_input)
                if action.startswith("mcp:email_mcp."):
                    action_arguments["user_id"] = user.user_id
                result = await dispatch_mcp_action(action, action_arguments)
                execution_results.append(
                    {
                        "step_number": step.step_number,
                        "action": action,
                        "status": "success",
                        "result": result,
                    }
                )
                context["mcp"].append({"action": action, "status": "success", "result": result})
                if action == "mcp:email_mcp.send_email":
                    llm_response = LlmGenerateResponse(
                        provider="google",
                        model="mcp",
                        phase="default",
                        content="Đã gửi email thành công.",
                        usage=TokenUsage(),
                        latency_ms=0,
                    )
            except MCPDispatchError as exc:
                execution_results.append(
                    {
                        "step_number": step.step_number,
                        "action": action,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                context["mcp"].append({"action": action, "status": "failed", "error": str(exc)})
            continue

        if action in {"llm_synthesize", "mcp_tool"}:
            step_response = await _synthesize_answer(message, user, files, context, step)
            _merge_usage(usage_total, step_response.usage)
            llm_response = step_response

    if llm_response is None:
        fallback = await _synthesize_answer(message, user, files, context, None)
        _merge_usage(usage_total, fallback.usage)
        llm_response = fallback

    if usage_total.total_tokens:
        llm_response.usage = usage_total

    mcp_results_summary: list[str] = []
    sent_email = any(
        execution.get("status") == "success" and execution.get("action") == "mcp:email_mcp.send_email"
        for execution in execution_results
    )
    for execution in execution_results:
        if execution.get("status") != "success":
            continue
        action = execution.get("action", "")
        result_data = execution.get("result")
        if action in ("mcp:email_mcp.check_email", "mcp:email_mcp.search_email"):
            mcp_results_summary.append(f"Kết quả từ {action}: {json.dumps(result_data, ensure_ascii=False)}")

    # The planner should normally include an explicit llm_synthesize step.
    # Do not synthesize MCP results a second time after that step (or after
    # the fallback synthesis above); this preserves one Planner -> Execution
    # -> Response path.
    if mcp_results_summary and not sent_email and llm_response is None:
        synthesis_prompt = f"""
Ban la AI Assistant cua VietMAS. Hay tong hop ket qua tu MCP tool thanh cau tra loi tu nhien, than thien va day du thong tin cho nguoi dung.

Yeu cau nguoi dung: {message}

Ket qua thuc thi MCP tool:
{chr(10).join(mcp_results_summary)}
"""
        try:
            synth_response = await llm_router.generate(
                LlmGenerateRequest(
                    phase="default",
                    max_output_tokens=1024,
                    temperature=0.2,
                    messages=[LlmMessage(role="user", content=synthesis_prompt)],
                    metadata={"chat_route": "mcp_synthesis", "user_id": user.user_id},
                )
            )
            _merge_usage(usage_total, synth_response.usage)
            llm_response.content = synth_response.content
            llm_response.usage = usage_total
        except Exception:
            pass

    return llm_response, execution_results


@router.post(
    "/chat",
    response_model=ChatResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["message"],
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "Nội dung tin nhắn gửi đến AI",
                            },
                            "conversation_id": {
                                "type": "string",
                                "nullable": True,
                                "description": "UUID hội thoại (để trống để tạo mới)",
                            },
                            "files": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "nullable": True,
                                "description": (
                                    "File đính kèm (tối đa 2 file/request). "
                                    "Định dạng cho phép: .png (≤10MB), .md (≤2MB). "
                                    "File sẽ được kiểm duyệt qua AI Firewall Lớp 2 trước khi xử lý."
                                ),
                            },
                        },
                    }
                }
            },
        }
    },
)
async def chat(
    request: Request,
    message: str = Form(...),
    conversation_id: Optional[str] = Form(default=None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    x_user_email: Optional[str] = Header(default=None, alias="X-User-Email"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
):
    user = _user_from_headers(x_user_id, x_user_email, x_user_role)
    conversation_id = _normalize_conversation_id(conversation_id)
    try:
        form = await request.form()
        upload_files: list[UploadFile] = [
            v for v in form.getlist("files")
            if isinstance(v, StarletteUploadFile) and v.filename
        ]
    except Exception:
        upload_files = []

    async with redis_concurrency_gate():
        await set_runtime_state(f"chat:{user.user_id}:last_status", "running")

        try:
            processed_files = await process_uploads(upload_files, user) if upload_files else []
        except HTTPException as exc:
            if exc.detail == FILE_REJECT_MESSAGE:
                raise
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE) from exc

        firewall = await check_message(message, user)
        is_firewall_allowed = firewall.is_valid and firewall.allowed
        if processed_files and not is_firewall_allowed:
            issues = set(firewall.detected_issues)
            if issues and issues.issubset(FILE_CONTEXT_SOFT_ISSUES):
                firewall.is_valid = True
                firewall.allowed = True
                firewall.risk_level = "low"
                firewall.reason = "File đã qua kiểm duyệt hardcode/AI trước bước xử lý yêu cầu."
                is_firewall_allowed = True

        if not is_firewall_allowed:
            if not conversation_id:
                conversation_id = await ek_client.create_conversation(user_id=user.user_id, title=_title_from_message(message))
            user_message = await ek_client.create_message(
                conversation_id=conversation_id,
                role="user",
                content=message,
                status="completed",
            )
            assistant_message = await ek_client.create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=REQUEST_REJECT_MESSAGE,
                status="failed",
            )
            return ChatResponse(
                conversation_id=conversation_id,
                user_message_id=user_message["id"],
                assistant_message_id=assistant_message["id"],
                intent="general_chat",
                firewall=ChatFirewallRead(**firewall.model_dump(exclude={"raw", "details", "is_valid"})),
                status="rejected",
                answer=REQUEST_REJECT_MESSAGE,
                usage=ChatUsageRead(),
                files=[],
            )

        if not conversation_id:
            conversation_id = await ek_client.create_conversation(user_id=user.user_id, title=_title_from_message(message))
        user_message = await ek_client.create_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            status="completed",
        )

        plan = await create_execution_plan(message, user, processed_files)
        llm_response, _execution_results = await execute_plan(message, user, processed_files, plan)
        intent = _intent_from_plan(plan)

        assistant_message = await ek_client.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=llm_response.content,
            status="completed",
            input_tokens=llm_response.usage.input_tokens,
            output_tokens=llm_response.usage.output_tokens,
        )
        step_payloads = [
            {
                "step_number": step.step_number,
                "step_name": step.step_name,
                "action": step.action,
                "thought": step.thought,
                "action_input": json.dumps(step.action_input, ensure_ascii=False),
                "status": "completed",
            }
            for step in plan.steps
        ]
        selected_mcp_tools = []
        for step in plan.steps:
            if not step.action or not step.action.startswith("mcp:"):
                continue
            qualified_name = step.action.removeprefix("mcp:").strip()
            if "." not in qualified_name:
                continue
            mcp_name, tool_name = qualified_name.split(".", 1)
            selected_mcp_tools.append(
                {
                    "mcp_name": mcp_name,
                    "tool_name": tool_name,
                    "qualified_name": qualified_name,
                    "step_number": step.step_number,
                }
            )
        try:
            await ek_client.create_agent_plan(
                message_id=assistant_message["id"],
                plan_name=plan.plan_name,
                raw_plan=plan.model_dump(),
                steps=step_payloads,
                mcp_tools=selected_mcp_tools,
                total_steps=plan.total_steps,
                status="success",
            )
        except Exception:
            pass

        await set_runtime_state(f"chat:{user.user_id}:last_status", "completed")

        return ChatResponse(
            conversation_id=conversation_id,
            user_message_id=user_message["id"],
            assistant_message_id=assistant_message["id"],
            intent=intent,
            firewall=ChatFirewallRead(**firewall.model_dump(exclude={"raw", "details", "is_valid"})),
            status="completed",
            answer=llm_response.content,
            usage=ChatUsageRead(**llm_response.usage.model_dump()),
            files=[
                ChatFileRead(
                    id=file.ek_file_id,
                    original_file_name=file.original_file_name,
                    file_type=file.file_type,
                    sanitized=file.sanitized,
                    flags=file.flags,
                )
                for file in processed_files
            ],
        )
