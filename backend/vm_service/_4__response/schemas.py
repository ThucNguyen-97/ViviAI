from typing import Optional
from pydantic import BaseModel, Field

from _1__ai_firewall.schemas import Intent


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
