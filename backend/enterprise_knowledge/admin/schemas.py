from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AdminApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json")
    def serialize_values(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value


class AdminUserRead(AdminApiModel):
    id: str
    email: Optional[str] = None
    email_hidden: bool = False
    full_name: Optional[str] = None
    role: str
    is_active: bool
    last_login_id: Optional[str] = None
    total_tokens: int = 0
    total_cost_usd: Decimal = Decimal("0")
    total_cost_vnd: Decimal = Decimal("0")
    created_at: datetime


class UsageStats(AdminApiModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_token_cost: Decimal = Decimal("0")
    output_token_cost: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")


class StatusCount(AdminApiModel):
    status: str
    total: int


class AdminOverviewResponse(AdminApiModel):
    total_users: int
    active_users: int
    total_conversations: int
    total_messages: int
    failed_messages: int
    total_agent_plans: int
    failed_agent_plans: int
    total_agent_steps: int
    failed_agent_steps: int
    rag_documents: int
    rag_chunks: int
    user_files: int
    vouchers: int
    usage: UsageStats
    message_statuses: list[StatusCount] = Field(default_factory=list)
    agent_step_statuses: list[StatusCount] = Field(default_factory=list)


class AdminUserListResponse(AdminApiModel):
    total: int
    limit: int
    offset: int
    cost_currency: str = "USD"
    display_currency: str = "VND"
    usd_to_vnd_rate: Decimal = Decimal("26200")
    users: list[AdminUserRead]


class ConversationLogItem(AdminApiModel):
    id: str
    user_id: str
    user: Optional[AdminUserRead] = None
    title: str
    summary: Optional[str] = None
    message_count: int
    usage: UsageStats
    created_at: datetime
    updated_at: datetime


class ConversationLogListResponse(AdminApiModel):
    total: int
    limit: int
    offset: int
    conversations: list[ConversationLogItem]


class AgentStepRead(AdminApiModel):
    id: str
    step_number: int
    step_name: str
    thought: str
    action: Optional[str] = None
    action_input: Optional[str] = None
    action_output: Optional[str] = None
    status: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    error_message: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None


class AgentPlanRead(AdminApiModel):
    id: str
    plan_name: Optional[str] = None
    raw_plan: dict[str, Any]
    mcp_tools: Optional[list[dict[str, Any]]] = None
    total_steps: int
    status: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    created_at: datetime
    steps: list[AgentStepRead] = Field(default_factory=list)



class MessageLogRead(AdminApiModel):
    id: str
    role: str
    content: str
    status: Optional[str] = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    documents_source_url: Optional[str] = None
    vouchers_source_url: Optional[str] = None
    created_at: datetime
    agent_plans: list[AgentPlanRead] = Field(default_factory=list)


class ConversationLogDetailResponse(ConversationLogItem):
    messages: list[MessageLogRead] = Field(default_factory=list)


class RagDocumentStats(AdminApiModel):
    id: str
    file_name: str
    file_type: str
    file_size: int
    storage_url: Optional[str] = None
    file_modified_at: Optional[datetime] = None
    created_at: datetime
    chunk_count: int


class RagStatsResponse(AdminApiModel):
    total_documents: int
    total_chunks: int
    documents: list[RagDocumentStats]


class LlmProviderStatus(AdminApiModel):
    provider: str
    display_name: str
    model: str
    configured: bool
    status: str
    routing_roles: list[str] = Field(default_factory=list)
    last_called_at: Optional[datetime] = None
    last_latency_ms: Optional[int] = None
    last_error_type: Optional[str] = None


class LlmProvidersStatusResponse(AdminApiModel):
    source: str
    note: str
    providers: list[LlmProviderStatus]
