import asyncio
from typing import Sequence

from core.config import settings
from llm.adapters import AnthropicAdapter, GoogleAdapter, LlmProviderError, ProviderPricing
from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, LlmProvider, ProviderStatus, RouterStatusResponse
from llm.telemetry import send_provider_call_log


ROUTING_ROLES = {
    "google": ["primary"],
    "anthropic": ["fallback"],
}


class LlmRouter:
    def __init__(self) -> None:
        self.google = GoogleAdapter(
            api_key=settings.GOOGLE_API_KEY,
            model=settings.GOOGLE_LLM_MODEL,
            pricing=ProviderPricing(
                input_usd_per_mtok=settings.GOOGLE_INPUT_USD_PER_MTOK,
                output_usd_per_mtok=settings.GOOGLE_OUTPUT_USD_PER_MTOK,
            ),
        )
        self.anthropic = AnthropicAdapter(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_LLM_MODEL,
            pricing=ProviderPricing(
                input_usd_per_mtok=settings.ANTHROPIC_INPUT_USD_PER_MTOK,
                output_usd_per_mtok=settings.ANTHROPIC_OUTPUT_USD_PER_MTOK,
            ),
        )

    def status(self) -> RouterStatusResponse:
        providers = [
            ProviderStatus(
                provider="google",
                display_name=self.google.display_name,
                model=self.google.model,
                configured=self.google.configured,
                routing_roles=ROUTING_ROLES["google"],
            ),
            ProviderStatus(
                provider="anthropic",
                display_name=self.anthropic.display_name,
                model=self.anthropic.model,
                configured=self.anthropic.configured,
                routing_roles=ROUTING_ROLES["anthropic"],
            ),
        ]
        configured = [provider for provider in providers if provider.configured]
        return RouterStatusResponse(
            status="ready" if configured else "missing_api_keys",
            providers=providers,
        )

    def _provider_order(self, phase: str) -> Sequence[LlmProvider]:
        primary: list[LlmProvider] = ["google", "anthropic"]
        if settings.LLM_ENABLE_CROSS_PROVIDER_FALLBACK:
            return primary
        return primary[:1]

    async def generate(self, request: LlmGenerateRequest) -> LlmGenerateResponse:
        normalized = request.model_copy(
            update={
                "max_output_tokens": request.max_output_tokens or settings.LLM_DEFAULT_MAX_OUTPUT_TOKENS,
                "temperature": request.temperature if request.temperature is not None else settings.LLM_DEFAULT_TEMPERATURE,
            }
        )
        errors: list[LlmProviderError] = []
        fallback_from: LlmProvider | None = None

        for attempt, provider in enumerate(self._provider_order(normalized.phase), start=1):
            adapter = self.google if provider == "google" else self.anthropic
            try:
                response = await self._generate_with_retries(adapter, normalized)
                response.attempts = attempt
                response.fallback_from = fallback_from
                await send_provider_call_log(
                    normalized,
                    provider=provider,
                    model=adapter.model,
                    status="success",
                    usage=response.usage,
                    response=response,
                    fallback_from=fallback_from,
                )
                return response
            except LlmProviderError as exc:
                errors.append(exc)
                fallback_from = fallback_from or provider
                await send_provider_call_log(
                    normalized,
                    provider=provider,
                    model=adapter.model,
                    status="failed",
                    error=exc,
                    fallback_from=None,
                )
                continue

        message = "; ".join(f"{error.provider}: {error.error_type}: {error}" for error in errors)
        raise LlmProviderError("google", message or "No LLM provider was available.", error_type="router_exhausted")

    async def _generate_with_retries(self, adapter, request: LlmGenerateRequest) -> LlmGenerateResponse:
        last_error: LlmProviderError | None = None
        for retry_index in range(settings.LLM_MAX_RETRIES + 1):
            try:
                return await adapter.generate(
                    request,
                    timeout_seconds=settings.LLM_REQUEST_TIMEOUT_SECONDS,
                )
            except LlmProviderError as exc:
                last_error = exc
                if not exc.retryable or retry_index >= settings.LLM_MAX_RETRIES:
                    raise
                await asyncio.sleep(0.3 * (retry_index + 1))
        raise last_error or LlmProviderError("google", "Unknown router error.")


llm_router = LlmRouter()
