import json
from pathlib import Path
from typing import Any, Optional

from _1__ai_firewall.schemas import ExecutionStep, ProcessedFile, UserContext
from llm.router import llm_router
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, LlmMessage, TokenUsage

REQUEST_REJECT_MESSAGE = "Yêu cầu của bạn không thể xử lý hoặc thông tin bạn yêu cầu không tồn tại"


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


async def synthesize_answer(
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
