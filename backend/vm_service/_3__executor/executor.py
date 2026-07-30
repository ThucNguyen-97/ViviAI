from typing import Any, Optional

from ek_client import ek_client
from _1__ai_firewall.schemas import ExecutionPlan, ExecutionStep, ProcessedFile, UserContext
from _3__executor.mcp_tools.dispatcher import MCPDispatchError, dispatch_mcp_action
from llm.schemas import LlmGenerateResponse, TokenUsage
from _4__response.response import synthesize_answer

REQUEST_REJECT_MESSAGE = "Yêu cầu của bạn không thể xử lý hoặc thông tin bạn yêu cầu không tồn tại"


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
            step_response = await synthesize_answer(message, user, files, context, step)
            _merge_usage(usage_total, step_response.usage)
            llm_response = step_response

    if llm_response is None:
        fallback = await synthesize_answer(message, user, files, context, None)
        _merge_usage(usage_total, fallback.usage)
        llm_response = fallback

    if usage_total.total_tokens:
        llm_response.usage = usage_total

    return llm_response, execution_results
