import asyncio
import base64
import time
from dataclasses import dataclass

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, AsyncAnthropic
from google import genai
from google.genai import types

from llm.schemas import LlmGenerateRequest, LlmGenerateResponse, LlmMessage, LlmProvider, TokenUsage


class LlmProviderError(Exception):
    def __init__(
        self,
        provider: LlmProvider,
        message: str,
        *,
        error_type: str = "provider_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.error_type = error_type
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderPricing:
    input_usd_per_mtok: float = 0.0
    output_usd_per_mtok: float = 0.0


def calculate_cost(usage: TokenUsage, pricing: ProviderPricing) -> tuple[float, float, float]:
    input_cost = usage.input_tokens * pricing.input_usd_per_mtok / 1_000_000
    output_cost = usage.output_tokens * pricing.output_usd_per_mtok / 1_000_000
    return input_cost, output_cost, input_cost + output_cost


def _combined_text(messages: list[LlmMessage]) -> str:
    return "\n\n".join(f"{message.role.upper()}:\n{message.content}" for message in messages)


def _usage_from_google(response) -> TokenUsage:
    metadata = getattr(response, "usage_metadata", None)
    input_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(metadata, "candidates_token_count", 0) or 0)
    total_tokens = int(getattr(metadata, "total_token_count", 0) or input_tokens + output_tokens)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _usage_from_anthropic(message) -> TokenUsage:
    usage = getattr(message, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _anthropic_messages(messages: list[LlmMessage], images: list[dict] = None) -> list[dict]:
    result: list[dict] = []
    user_msgs = [m for m in messages if m.role == "user"]
    last_user_msg = user_msgs[-1] if user_msgs else None

    for message in messages:
        if message.role == "system":
            continue
        if message is last_user_msg and images:
            content_blocks: list[dict] = []
            for img in images:
                raw_data = img.get("data")
                mime_type = img.get("mime_type", "image/png")
                if raw_data:
                    b64_str = base64.b64encode(raw_data).decode("utf-8")
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64_str,
                        },
                    })
            content_blocks.append({"type": "text", "text": message.content})
            result.append({"role": message.role, "content": content_blocks})
        else:
            result.append({"role": message.role, "content": message.content})
    return result


def _text_from_anthropic(message) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "\n".join(part for part in parts if part).strip()


class GoogleAdapter:
    provider: LlmProvider = "google"
    display_name = "Google Gemini"

    def __init__(self, *, api_key: str, model: str, pricing: ProviderPricing) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.pricing = pricing

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def generate(self, request: LlmGenerateRequest, *, timeout_seconds: float) -> LlmGenerateResponse:
        if not self.configured:
            raise LlmProviderError(self.provider, "GOOGLE_API_KEY is not configured.", error_type="missing_api_key")

        started = time.perf_counter()
        try:
            client = genai.Client(api_key=self.api_key).aio
            config = types.GenerateContentConfig(
                max_output_tokens=request.max_output_tokens,
                temperature=request.temperature,
                system_instruction=request.system,
            )

            contents: list = []
            if request.images:
                for img in request.images:
                    raw_data = img.get("data")
                    mime_type = img.get("mime_type", "image/png")
                    if raw_data:
                        contents.append(types.Part.from_bytes(data=raw_data, mime_type=mime_type))
            contents.append(_combined_text(request.messages))

            response = await asyncio.wait_for(
                client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise LlmProviderError(self.provider, "Google request timed out.", error_type="timeout", retryable=True) from exc
        except Exception as exc:
            raise LlmProviderError(
                self.provider,
                str(exc),
                error_type=exc.__class__.__name__,
                retryable=True,
            ) from exc

        usage = _usage_from_google(response)
        input_cost, output_cost, total_cost = calculate_cost(usage, self.pricing)
        return LlmGenerateResponse(
            provider=self.provider,
            model=self.model,
            phase=request.phase,
            content=(getattr(response, "text", None) or "").strip(),
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total_cost,
            finish_reason=str(getattr(response, "finish_reason", "") or "") or None,
            provider_request_id=str(getattr(response, "response_id", "") or "") or None,
        )


class AnthropicAdapter:
    provider: LlmProvider = "anthropic"
    display_name = "Anthropic Claude"

    def __init__(self, *, api_key: str, model: str, pricing: ProviderPricing) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.pricing = pricing

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def generate(self, request: LlmGenerateRequest, *, timeout_seconds: float) -> LlmGenerateResponse:
        if not self.configured:
            raise LlmProviderError(self.provider, "ANTHROPIC_API_KEY is not configured.", error_type="missing_api_key")

        started = time.perf_counter()
        client = AsyncAnthropic(api_key=self.api_key, timeout=timeout_seconds)
        system_parts = [message.content for message in request.messages if message.role == "system"]
        system = request.system or ("\n\n".join(system_parts) if system_parts else None)

        try:
            params = {
                "model": self.model,
                "max_tokens": request.max_output_tokens or 2048,
                "messages": _anthropic_messages(request.messages, request.images),
            }
            if system:
                params["system"] = system
            message = await client.messages.create(**params)
        except (APIConnectionError, APITimeoutError) as exc:
            raise LlmProviderError(self.provider, str(exc), error_type=exc.__class__.__name__, retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code in {408, 409, 429, 500, 502, 503, 504}
            raise LlmProviderError(self.provider, str(exc), error_type=f"http_{exc.status_code}", retryable=retryable) from exc
        except Exception as exc:
            raise LlmProviderError(self.provider, str(exc), error_type=exc.__class__.__name__, retryable=True) from exc

        usage = _usage_from_anthropic(message)
        input_cost, output_cost, total_cost = calculate_cost(usage, self.pricing)
        return LlmGenerateResponse(
            provider=self.provider,
            model=getattr(message, "model", None) or self.model,
            phase=request.phase,
            content=_text_from_anthropic(message),
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            total_cost_usd=total_cost,
            finish_reason=getattr(message, "stop_reason", None),
            provider_request_id=getattr(message, "id", None),
        )
