import logging
from typing import Optional

import httpx

from core.config import settings
from llm.adapters import LlmProviderError
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, LlmProvider, TokenUsage

logger = logging.getLogger(__name__)


async def send_provider_call_log(
    request: LlmGenerateRequest,
    *,
    provider: LlmProvider,
    model: str,
    status: str,
    usage: Optional[TokenUsage] = None,
    latency_ms: Optional[int] = None,
    response: Optional[LlmGenerateResponse] = None,
    error: Optional[LlmProviderError] = None,
    fallback_from: Optional[LlmProvider] = None,
) -> None:
    if not settings.EK_SERVICE_URL.strip() or not settings.EK_INTERNAL_API_KEY.strip():
        return

    usage = usage or TokenUsage()
    payload = {
        "conversation_id": request.conversation_id,
        "message_id": request.message_id,
        "phase": request.phase,
        "provider": provider,
        "model": model,
        "status": status,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "input_cost_usd": response.input_cost_usd if response else 0,
        "output_cost_usd": response.output_cost_usd if response else 0,
        "total_cost_usd": response.total_cost_usd if response else 0,
        "latency_ms": latency_ms if latency_ms is not None else (response.latency_ms if response else None),
        "finish_reason": response.finish_reason if response else None,
        "provider_request_id": response.provider_request_id if response else None,
        "fallback_from": fallback_from,
        "error_type": error.error_type if error else None,
        "error_message": str(error) if error else None,
        "metadata": request.metadata,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.EK_SERVICE_URL.rstrip('/')}/internal/v1/llm/provider-calls",
                headers={"X-Internal-Api-Key": settings.EK_INTERNAL_API_KEY},
                json=payload,
            )
    except Exception as exc:
        logger.warning("Failed to send LLM provider call log to EK: %s", exc)
