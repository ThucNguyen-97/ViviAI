from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Form, Header, HTTPException, Request, UploadFile, status
from starlette.datastructures import UploadFile as StarletteUploadFile

from _1__ai_firewall.ai_firewall import check_message
from _1__ai_firewall.file_processor import FILE_REJECT_MESSAGE, process_uploads
from _1__ai_firewall.schemas import UserContext
from _2__planner.planner import create_execution_plan, intent_from_plan
from _3__executor.executor import execute_plan
from _4__response.schemas import ChatFileRead, ChatFirewallRead, ChatResponse, ChatUsageRead
from _5__observer import observer
from runtime.redis_gate import redis_concurrency_gate, set_runtime_state


REQUEST_REJECT_MESSAGE = "Yêu cầu của bạn không thể xử lý hoặc thông tin bạn yêu cầu không tồn tại"
FILE_CONTEXT_SOFT_ISSUES = {
    "unsupported_file_format_or_action",
    "unsupported_modality",
    "missing_file_context",
    "potential_unauthorized_file_access",
}

router = APIRouter(prefix="/v1", tags=["Chat Orchestrator"])


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
                conversation_id = await observer.create_conversation(user_id=user.user_id, title=_title_from_message(message))
            user_message = await observer.record_user_message(conversation_id=conversation_id, content=message)
            assistant_message = await observer.record_assistant_message(
                conversation_id=conversation_id,
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
            conversation_id = await observer.create_conversation(user_id=user.user_id, title=_title_from_message(message))
        user_message = await observer.record_user_message(conversation_id=conversation_id, content=message)

        plan = await create_execution_plan(message, user, processed_files)
        llm_response, _execution_results = await execute_plan(message, user, processed_files, plan)
        intent = intent_from_plan(plan)

        assistant_message = await observer.record_assistant_message(
            conversation_id=conversation_id,
            content=llm_response.content,
            status="completed",
            input_tokens=llm_response.usage.input_tokens,
            output_tokens=llm_response.usage.output_tokens,
        )

        await observer.record_agent_plan(
            assistant_message_id=assistant_message["id"],
            plan=plan,
        )

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
