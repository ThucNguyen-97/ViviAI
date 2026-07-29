from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Intent = Literal["rag_query", "business_query", "task_execution", "general_chat"]
RiskLevel = Literal["low", "medium", "high"]


class UserContext(BaseModel):
    user_id: str
    email: Optional[str] = None
    role: Literal["admin", "ceo", "manager"] = "manager"


class FirewallDecision(BaseModel):
    is_valid: bool = True
    allowed: bool = True
    risk_level: RiskLevel = "low"
    reason: str = ""
    detected_issues: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ExecutionStep(BaseModel):
    step_number: int
    action_input: dict[str, Any] = Field(default_factory=dict)
    step_name: str  # Tên bước (VD: "Đọc file Excel tải lên")
    action: str  # Loại action (VD: "mcp_tool", "rag_search", "sql_query", "llm_synthesize")
    thought: str  # Mô tả tư duy / nội dung công việc của bước


class ExecutionPlan(BaseModel):
    plan_name: str = Field(default="Kế hoạch thực thi tác vụ", description="Tên kế hoạch thực thi")
    total_steps: int = 0
    steps: list[ExecutionStep] = Field(default_factory=list)



class ProcessedFile(BaseModel):
    original_file_name: str
    file_type: str
    raw_path: str
    clean_path: str
    mime_type: Optional[str] = None
    sanitized: bool = False
    flags: list[str] = Field(default_factory=list)
    ek_file_id: Optional[str] = None
