from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


LlmPhase = Literal["default", "agent_plans", "agent_tasks", "rag_answer", "tool_result"]
LlmRole = Literal["system", "user", "assistant"]
LlmProvider = Literal["google", "anthropic"]


class LlmMessage(BaseModel):
    role: LlmRole
    content: str


class LlmGenerateRequest(BaseModel):
    phase: LlmPhase = "default"
    messages: list[LlmMessage] = Field(min_length=1)
    system: Optional[str] = None
    max_output_tokens: Optional[int] = Field(default=None, ge=1, le=8192)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class LlmError(BaseModel):
    provider: LlmProvider
    error_type: str
    message: str
    retryable: bool = False


class LlmGenerateResponse(BaseModel):
    provider: LlmProvider
    model: str
    phase: LlmPhase
    content: str
    usage: TokenUsage
    latency_ms: int
    input_cost_usd: float = 0.0
    output_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    finish_reason: Optional[str] = None
    provider_request_id: Optional[str] = None
    attempts: int = 1
    fallback_from: Optional[LlmProvider] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ProviderStatus(BaseModel):
    provider: LlmProvider
    display_name: str
    model: str
    configured: bool
    routing_roles: list[str] = Field(default_factory=list)


class RouterStatusResponse(BaseModel):
    status: str
    providers: list[ProviderStatus]
