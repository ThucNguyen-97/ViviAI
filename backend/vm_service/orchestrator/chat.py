import json
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Form, Header, HTTPException, Request, UploadFile, status
from starlette.datastructures import UploadFile as StarletteUploadFile
from pydantic import BaseModel, Field

from ek_client import ek_client
from firewall.ai_firewall import check_message
from firewall.file_processor import FILE_REJECT_MESSAGE, process_uploads
from firewall.schemas import ExecutionPlan, ExecutionStep, FirewallDecision, Intent, ProcessedFile, UserContext

from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, LlmMessage, TokenUsage
from runtime.redis_gate import redis_concurrency_gate, set_runtime_state


REQUEST_REJECT_MESSAGE = "Yêu cầu của bạn không thể xử lý hoặc thông tin bạn yêu cầu không tồn tại"
FILE_CONTEXT_SOFT_ISSUES = {
    "unsupported_file_format_or_action",
    "unsupported_modality",
    "missing_file_context",
    "potential_unauthorized_file_access",
}
RAG_KNOWLEDGE_CATALOG = [
    {
        "source": "01_system_overview.md",
        "topics": [
            "AI VIVI / VietMAS system overview",
            "muc tieu he thong",
            "kien truc Enterprise Knowledge, VM Server, Frontend",
            "phan he cau hinh chung va tai chinh",
            "kha nang AI agent, RAG, tool, workflow, file editing",
        ],
    },
    {
        "source": "00_company_profile.md",
        "topics": [
            "cong ty Huong Vi Viet / Muoi Ot",
            "danh muc san pham muoi ot",
            "chinh sach ban si, chiet khau, dai ly",
            "giao hang, thanh toan, cong no, doi hang, bao quan",
            "thong tin lien he cong ty",
        ],
    },
]

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


async def classify_intent(message: str, user: UserContext, firewall: FirewallDecision, files: list[ProcessedFile]) -> Intent:
    if files:
        return "task_execution"

    file_summary = [
        {"file_name": file.original_file_name, "file_type": file.file_type, "flags": file.flags}
        for file in files
    ]
    prompt = f"""
Ban la intent classifier cho VietMAS. Hay phan loai yeu cau nguoi dung thanh dung mot intent.
Chi tra ve JSON hop le:
{{"intent": "general_chat", "reason": "short reason"}}

Intent hop le:
- rag_query: hoi dap dua tren tai lieu noi bo/RAG/chinh sach/quy trinh, gioi thieu VietMAS/AI VIVI/cong ty/san pham/he thong
- business_query: hoi du lieu nghiep vu trong database
- task_execution: yeu cau thao tac file, lap ke hoach tool/MCP, tao/sua/tong hop file
- general_chat: trao doi thong thuong khong can du lieu noi bo; gom ca cau hoi ve trang thai chatbot/API/demo neu khong yeu cau truy van du lieu nghiep vu

RAG knowledge catalog hien co:
{json.dumps(RAG_KNOWLEDGE_CATALOG, ensure_ascii=False, indent=2)}

Quy tac phan loai:
- Chon rag_query neu cau hoi co the tra loi tot hon bang tri thuc trong RAG knowledge catalog, ke ca khi nguoi dung noi mo ho nhu "he thong nay" hoac "cong ty".
- Chon business_query neu nguoi dung can so lieu/ban ghi nghiep vu dong trong database, vi du doanh thu, ton kho, chung tu, but toan, cong no, tong quan du lieu kinh doanh.
- Chon task_execution neu nguoi dung yeu cau thao tac file/tool/workflow/tao-sua-tong-hop file.
- Chon general_chat neu la hoi dap thong thuong, cau hoi ve trang thai API/demo/chatbot, hoac khong can tri thuc noi bo.

Vai tro: {user.role}
Firewall recommended_intent: {firewall.recommended_intent}
Files: {json.dumps(file_summary, ensure_ascii=False)}
Message: {message}
"""
    try:
        response = await llm_router.generate(
            LlmGenerateRequest(
                phase="default",
                max_output_tokens=128,
                temperature=0,
                messages=[LlmMessage(role="user", content=prompt)],
                metadata={"classifier": "intent", "user_id": user.user_id, "role": user.role},
            )
        )
        parsed = _json_object(response.content)
        intent = parsed.get("intent")
        if intent in {"rag_query", "business_query", "task_execution", "general_chat"}:
            return intent
    except Exception:
        pass
    if files:
        return "task_execution"
    return firewall.recommended_intent


async def _answer_general(message: str, user: UserContext) -> LlmGenerateResponse:
    return await llm_router.generate(
        LlmGenerateRequest(
            phase="default",
            max_output_tokens=768,
            temperature=0.2,
            messages=[LlmMessage(role="user", content=message)],
            metadata={"chat_route": "general_chat", "user_id": user.user_id, "role": user.role},
        )
    )


async def _answer_rag(message: str, user: UserContext) -> LlmGenerateResponse:
    results = await ek_client.rag_search(query=message, score_threshold=0.55)
    context_blocks: list[str] = []
    for item in results.get("results", []):
        source = item.get("source") or {}
        if isinstance(source, dict):
            source_name = source.get("file_name") or source.get("document_id") or "unknown"
        else:
            source_name = str(source)
        context_blocks.append(f"Source: {source_name}\n{item.get('content', '')}")
    context = "\n\n".join(context_blocks)
    prompt = f"""
Tra loi nguoi dung dua tren cac chunk RAG sau. Neu khong co thong tin phu hop, noi ngan gon rang thong tin khong ton tai.

Context:
{context}

Question:
{message}
"""
    return await llm_router.generate(
        LlmGenerateRequest(
            phase="default",
            max_output_tokens=1024,
            temperature=0.1,
            messages=[LlmMessage(role="user", content=prompt)],
            metadata={"chat_route": "rag_query", "user_id": user.user_id, "role": user.role, "rag_total": results.get("total", 0)},
        )
    )


async def _answer_business(message: str, user: UserContext) -> LlmGenerateResponse:
    if user.role == "manager":
        return LlmGenerateResponse(
            provider="google",
            model="policy",
            phase="default",
            content=REQUEST_REJECT_MESSAGE,
            usage=TokenUsage(),
            latency_ms=0,
        )
    overview = await ek_client.business_overview()
    prompt = f"""
Nguoi dung hoi ve du lieu nghiep vu. Hay tra loi ngan gon dua tren JSON overview sau.

Overview JSON:
{json.dumps(overview, ensure_ascii=False)}

Question:
{message}
"""
    return await llm_router.generate(
        LlmGenerateRequest(
            phase="default",
            max_output_tokens=1024,
            temperature=0.1,
            messages=[LlmMessage(role="user", content=prompt)],
            metadata={"chat_route": "business_query", "user_id": user.user_id, "role": user.role},
        )
    )


async def _answer_task_execution(message: str, user: UserContext, files: list[ProcessedFile]) -> LlmGenerateResponse:
    images_payload: list[dict] = []
    md_contexts: list[str] = []

    for file in files:
        clean_p = Path(file.clean_path)
        if not clean_p.exists():
            continue

        if file.file_type == "md":
            try:
                md_text = clean_p.read_text(encoding="utf-8", errors="replace")
                md_contexts.append(f"--- [Nội dung tệp Markdown: {file.original_file_name}] ---\n{md_text}\n--- [Kết thúc tệp] ---")
            except Exception:
                pass
        elif file.file_type == "png":
            try:
                raw_bytes = clean_p.read_bytes()
                images_payload.append({
                    "data": raw_bytes,
                    "mime_type": file.mime_type or "image/png",
                })
            except Exception:
                pass

    prompt_parts = []
    if md_contexts:
        prompt_parts.append("\n\n".join(md_contexts))

    prompt_parts.append(
        f"Yêu cầu của người dùng ({user.role}): {message}\n\n"
        "Hãy phân tích kỹ nội dung tệp tin đính kèm (hình ảnh/văn bản/markdown) và trả lời trực tiếp, đầy đủ, chính xác cho người dùng."
    )

    full_prompt = "\n\n".join(prompt_parts)

    return await llm_router.generate(
        LlmGenerateRequest(
            phase="default",
            max_output_tokens=1536,
            temperature=0.2,
            messages=[LlmMessage(role="user", content=full_prompt)],
            images=images_payload,
            metadata={"chat_route": "task_execution", "user_id": user.user_id, "role": user.role, "file_count": len(files)},
        )
    )



async def create_execution_plan(
    message: str,
    user: UserContext,
    firewall: FirewallDecision,
    files: list[ProcessedFile],
    intent: Intent,
) -> ExecutionPlan:
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
- mcp_tool: thao tac file hoac tool
- llm_synthesize: tong hop ket qua tu cac buoc va sinh phan hoi

Message: {message}
Intent khoi tao: {intent}
Role: {user.role}
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
        step_action = "llm_synthesize"
        if intent == "rag_query":
            step_action = "rag_search"
        elif intent == "business_query":
            step_action = "sql_query"
        elif intent == "task_execution":
            step_action = "mcp_tool"
        return ExecutionPlan(
            plan_name=f"Kế hoạch thực thi {intent}",
            total_steps=1,
            steps=[
                ExecutionStep(
                    step_number=1,
                    step_name=f"Xử lý {intent}",
                    action=step_action,
                    thought=f"Thực thi tác vụ theo ý định {intent}",
                )
            ],
        )



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
    # Parse files từ raw form data - lọc bỏ empty string do Swagger gửi (-F 'files=')
    # Dùng StarletteUploadFile thay fastapi.UploadFile vì Starlette tạo parent class instance,
    # isinstance(v, fastapi.UploadFile) sẽ False với starlette.UploadFile object
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
                intent=firewall.recommended_intent,
                firewall=ChatFirewallRead(**firewall.model_dump(exclude={"raw", "recommended_intent", "details", "is_valid"})),
                status="rejected",
                answer=REQUEST_REJECT_MESSAGE,
                usage=ChatUsageRead(),
                files=[],
            )

        intent = await classify_intent(message, user, firewall, processed_files)
        if not conversation_id:
            conversation_id = await ek_client.create_conversation(user_id=user.user_id, title=_title_from_message(message))
        user_message = await ek_client.create_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            status="completed",
        )

        if intent == "rag_query":
            llm_response = await _answer_rag(message, user)
        elif intent == "business_query":
            llm_response = await _answer_business(message, user)
        elif intent == "task_execution":
            llm_response = await _answer_task_execution(message, user, processed_files)
        else:
            llm_response = await _answer_general(message, user)

        assistant_message = await ek_client.create_message(
            conversation_id=conversation_id,
            role="assistant",
            content=llm_response.content,
            status="completed",
            input_tokens=llm_response.usage.input_tokens,
            output_tokens=llm_response.usage.output_tokens,
        )

        # 2. Sinh Execution Plan đa bước và lưu vào agent_plans / agent_steps CSDL Enterprise Knowledge
        plan = await create_execution_plan(message, user, firewall, processed_files, intent)
        step_payloads = [
            {
                "step_number": step.step_number,
                "step_name": step.step_name,
                "action": step.action,
                "thought": step.thought,
                "status": "completed",
            }
            for step in plan.steps
        ]
        try:
            await ek_client.create_agent_plan(
                message_id=assistant_message["id"],
                plan_name=plan.plan_name,
                raw_plan=plan.model_dump(),
                steps=step_payloads,
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
            firewall=ChatFirewallRead(**firewall.model_dump(exclude={"raw", "recommended_intent", "details", "is_valid"})),
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
