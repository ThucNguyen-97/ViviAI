import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from business import query_layer
from business.schemas import (
    AccountBalanceResponse,
    BusinessOverviewResponse,
    InventoryListResponse,
    InventoryValuationResponse,
    JournalEntryListResponse,
    JournalEntryRead,
    PartnerListResponse,
)
from core.config import settings
from db.base import get_db
from db.models import CleanFile, Conversation, LlmProviderCall, Message
from internal.auth import require_internal_api_key
from rag.retriever import DEFAULT_SCORE_THRESHOLD, DEFAULT_TOP_K, similarity_search
from rag.schemas import RagSearchRequest, RagSearchResponse

router = APIRouter(
    prefix="/internal/v1",
    tags=["Internal VM API"],
    dependencies=[Depends(require_internal_api_key)],
)


class LlmProviderCallCreate(BaseModel):
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    phase: str = Field(max_length=50)
    provider: str = Field(max_length=50)
    model: str = Field(max_length=255)
    status: str = Field(max_length=50)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost_usd: Decimal = Decimal("0")
    output_cost_usd: Decimal = Decimal("0")
    total_cost_usd: Decimal = Decimal("0")
    latency_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    provider_request_id: Optional[str] = None
    fallback_from: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    user_id: str = Field(max_length=128)
    title: str = Field(max_length=255)
    summary: Optional[str] = None


class ConversationCreateResponse(BaseModel):
    id: UUID


class MessageCreate(BaseModel):
    conversation_id: UUID
    role: str = Field(max_length=50)
    content: str
    status: Optional[str] = Field(default=None, max_length=50)
    input_tokens: int = 0
    output_tokens: int = 0
    documents_source_url: Optional[str] = None
    vouchers_source_url: Optional[str] = None


class MessageCreateResponse(BaseModel):
    id: UUID
    total_tokens: int


def _clean_file_root() -> Path:
    root = Path("/app/storage/clean_files")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _json_form(value: Optional[str]) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON form field.") from exc
    return parsed if isinstance(parsed, dict) else {}


def pagination_limit(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum records to return."),
) -> int:
    return limit


def pagination_offset(
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> int:
    return offset


@router.get("/health")
async def internal_health():
    return {"status": "ok", "service": "ek-service", "api": "internal-v1"}


@router.post("/llm/provider-calls")
async def internal_create_llm_provider_call(
    request: LlmProviderCallCreate,
    db: AsyncSession = Depends(get_db),
):
    provider_call = LlmProviderCall(
        conversation_id=request.conversation_id,
        message_id=request.message_id,
        phase=request.phase,
        provider=request.provider,
        model=request.model,
        status=request.status,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        total_tokens=request.total_tokens,
        input_cost_usd=request.input_cost_usd,
        output_cost_usd=request.output_cost_usd,
        total_cost_usd=request.total_cost_usd,
        latency_ms=request.latency_ms,
        finish_reason=request.finish_reason,
        provider_request_id=request.provider_request_id,
        fallback_from=request.fallback_from,
        error_type=request.error_type,
        error_message=request.error_message,
        meta_info=request.metadata,
    )
    db.add(provider_call)
    await db.commit()
    await db.refresh(provider_call)
    return {"id": str(provider_call.id), "status": "recorded"}


@router.post("/conversations", response_model=ConversationCreateResponse)
async def internal_create_conversation(
    request: ConversationCreate,
    db: AsyncSession = Depends(get_db),
):
    conversation = Conversation(
        user_id=request.user_id,
        title=request.title,
        summary=request.summary,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationCreateResponse(id=conversation.id)


@router.post("/messages", response_model=MessageCreateResponse)
async def internal_create_message(
    request: MessageCreate,
    db: AsyncSession = Depends(get_db),
):
    conversation = await db.get(Conversation, request.conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    message = Message(
        conversation_id=request.conversation_id,
        role=request.role,
        content=request.content,
        status=request.status,
        input_tokens=request.input_tokens,
        output_tokens=request.output_tokens,
        documents_source_url=request.documents_source_url,
        vouchers_source_url=request.vouchers_source_url,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return MessageCreateResponse(id=message.id, total_tokens=message.total_tokens)


@router.post("/clean-files")
async def internal_create_clean_file(
    file: UploadFile = File(...),
    original_file_name: str = Form(...),
    uploaded_by: str = Form(...),
    file_type: str = Form(...),
    status: str = Form(default="ready"),
    mime_type: Optional[str] = Form(default=None),
    raw_vm_path: Optional[str] = Form(default=None),
    sanitized: bool = Form(default=False),
    firewall_result: Optional[str] = Form(default=None),
    metadata: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    extension = Path(file.filename or original_file_name).suffix.lower()
    clean_name = f"{uuid.uuid4()}{extension}"
    target_path = _clean_file_root() / clean_name

    data = await file.read()
    target_path.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()

    clean_file = CleanFile(
        original_file_name=original_file_name,
        clean_file_name=clean_name,
        file_path=str(target_path),
        file_size=len(data),
        file_type=file_type,
        mime_type=mime_type,
        checksum_sha256=checksum,
        status=status,
        uploaded_by=uploaded_by,
        raw_vm_path=raw_vm_path,
        sanitized=sanitized,
        firewall_result=_json_form(firewall_result),
        meta_info=_json_form(metadata),
    )
    db.add(clean_file)
    await db.commit()
    await db.refresh(clean_file)
    return {
        "id": str(clean_file.id),
        "file_path": clean_file.file_path,
        "file_size": clean_file.file_size,
        "checksum_sha256": clean_file.checksum_sha256,
        "status": clean_file.status,
    }


@router.get("/clean-files")
async def internal_list_clean_files(
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    db: AsyncSession = Depends(get_db),
):
    """Liệt kê tất cả các tệp sạch đã qua kiểm duyệt và lưu trữ trên EK."""
    from sqlalchemy import select
    result = await db.execute(
        select(CleanFile)
        .order_by(CleanFile.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    files = result.scalars().all()
    return {
        "total": len(files),
        "clean_files": [
            {
                "id": str(f.id),
                "original_file_name": f.original_file_name,
                "clean_file_name": f.clean_file_name,
                "file_path": f.file_path,
                "file_size": f.file_size,
                "file_type": f.file_type,
                "sanitized": f.sanitized,
                "uploaded_by": f.uploaded_by,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in files
        ],
    }



@router.post("/rag/search", response_model=RagSearchResponse)
async def internal_rag_search(
    request: RagSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    top_k = request.top_k or DEFAULT_TOP_K
    score_threshold = (
        request.score_threshold
        if request.score_threshold is not None
        else DEFAULT_SCORE_THRESHOLD
    )
    gemini_key = settings.GEMINI_API_KEY

    results = await similarity_search(
        db,
        query=request.query,
        top_k=top_k,
        score_threshold=score_threshold,
        gemini_api_key=gemini_key,
    )

    return RagSearchResponse(
        query=request.query,
        top_k=top_k,
        score_threshold=score_threshold,
        total=len(results),
        results=results,
    )


@router.get("/business/overview", response_model=BusinessOverviewResponse)
async def internal_business_overview(db: AsyncSession = Depends(get_db)):
    return await query_layer.get_business_overview(db)


@router.get("/business/partners", response_model=PartnerListResponse)
async def internal_partners(
    search: Optional[str] = Query(default=None, description="Search by name, phone, email, or address."),
    partner_type: Optional[str] = Query(default=None, description="Filter by partner type."),
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.list_partners(
        db,
        search=search,
        partner_type=partner_type,
        limit=limit,
        offset=offset,
    )


@router.get("/business/inventory", response_model=InventoryListResponse)
async def internal_inventory(
    search: Optional[str] = Query(default=None, description="Search by item name or description."),
    low_stock_below: Optional[int] = Query(default=None, ge=0, description="Filter inventory quantity <= threshold."),
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.list_inventory(
        db,
        search=search,
        low_stock_below=low_stock_below,
        limit=limit,
        offset=offset,
    )


@router.get("/business/inventory/valuation", response_model=InventoryValuationResponse)
async def internal_inventory_valuation(db: AsyncSession = Depends(get_db)):
    return await query_layer.get_inventory_valuation(db)


@router.get("/business/journals", response_model=JournalEntryListResponse)
async def internal_journal_entries(
    date_from: Optional[datetime] = Query(default=None, description="Include entries from this datetime."),
    date_to: Optional[datetime] = Query(default=None, description="Include entries through this datetime."),
    status: Optional[str] = Query(default=None, description="Filter by journal status."),
    account_code: Optional[str] = Query(default=None, description="Filter entries containing this account code."),
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.list_journal_entries(
        db,
        date_from=date_from,
        date_to=date_to,
        status=status,
        account_code=account_code,
        limit=limit,
        offset=offset,
    )


@router.get("/business/journals/{entry_id}", response_model=JournalEntryRead)
async def internal_journal_entry(entry_id: UUID, db: AsyncSession = Depends(get_db)):
    entry = await query_layer.get_journal_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found.")
    return entry


@router.get("/business/accounts/balances", response_model=AccountBalanceResponse)
async def internal_account_balances(
    date_from: Optional[datetime] = Query(default=None, description="Aggregate from this datetime."),
    date_to: Optional[datetime] = Query(default=None, description="Aggregate through this datetime."),
    status: Optional[str] = Query(default=None, description="Aggregate only journals with this status."),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.get_account_balances(
        db,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )


class AgentStepCreate(BaseModel):
    step_number: int
    step_name: str
    action: Optional[str] = None
    thought: str
    action_input: Optional[str] = None
    action_output: Optional[str] = None
    status: str = "completed"


class AgentPlanCreate(BaseModel):
    message_id: UUID
    plan_name: Optional[str] = "Kế hoạch thực thi tác vụ"
    raw_plan: dict[str, Any]
    mcp_tools: Optional[list] = None
    total_steps: int = 0
    status: str = "success"
    steps: list[AgentStepCreate] = Field(default_factory=list)


@router.post("/agent-plans")
async def internal_create_agent_plan(
    request: AgentPlanCreate,
    db: AsyncSession = Depends(get_db),
):
    from db.models import AgentPlan, AgentStep

    message = await db.get(Message, request.message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found.")

    plan = AgentPlan(
        message_id=request.message_id,
        plan_name=request.plan_name,
        raw_plan=request.raw_plan,
        mcp_tools=request.mcp_tools or [],
        total_steps=request.total_steps or len(request.steps),
        status=request.status,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    for step_data in request.steps:
        step = AgentStep(
            agent_plan_id=plan.id,
            step_number=step_data.step_number,
            step_name=step_data.step_name,
            action=step_data.action,
            thought=step_data.thought,
            action_input=step_data.action_input,
            action_output=step_data.action_output,
            status=step_data.status,
        )
        db.add(step)

    await db.commit()
    return {"id": str(plan.id), "plan_name": plan.plan_name, "total_steps": plan.total_steps, "status": plan.status}


@router.get("/agent-plans")
async def internal_list_agent_plans(
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    db: AsyncSession = Depends(get_db),
):
    """Liệt kê tất cả kế hoạch thực thi AgentPlan và AgentStep chi tiết."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from db.models import AgentPlan

    result = await db.execute(
        select(AgentPlan)
        .options(selectinload(AgentPlan.steps))
        .order_by(AgentPlan.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    plans = result.scalars().all()
    return {
        "total": len(plans),
        "plans": [
            {
                "id": str(p.id),
                "message_id": str(p.message_id),
                "plan_name": p.plan_name,
                "total_steps": p.total_steps,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "steps": [
                    {
                        "id": str(s.id),
                        "step_number": s.step_number,
                        "step_name": s.step_name,
                        "action": s.action,
                        "thought": s.thought,
                        "status": s.status,
                    }
                    for s in p.steps
                ],
            }
            for p in plans
        ],
    }



