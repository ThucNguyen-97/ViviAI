from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Intent = Literal["rag_query", "business_query", "task_execution", "general_chat"]
RiskLevel = Literal["low", "medium", "high"]


class UserContext(BaseModel):
    user_id: str
    email: Optional[str] = None
    role: Literal["admin", "ceo", "manager"] = "manager"


class FirewallDecision(BaseModel):
    allowed: bool = True
    risk_level: RiskLevel = "low"
    reason: str = ""
    detected_issues: list[str] = Field(default_factory=list)
    recommended_intent: Intent = "general_chat"
    raw: dict[str, Any] = Field(default_factory=dict)


class ProcessedFile(BaseModel):
    original_file_name: str
    file_type: str
    raw_path: str
    clean_path: str
    mime_type: Optional[str] = None
    sanitized: bool = False
    flags: list[str] = Field(default_factory=list)
    ek_file_id: Optional[str] = None
