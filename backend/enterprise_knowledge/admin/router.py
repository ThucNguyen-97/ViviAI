from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import AdminViewer, require_dashboard_viewer
from admin import query_layer
from admin.schemas import (
    AdminOverviewResponse,
    AdminUserListResponse,
    ConversationLogDetailResponse,
    ConversationLogListResponse,
    LlmProvidersStatusResponse,
    RagStatsResponse,
)
from db.base import get_db

router = APIRouter(prefix="/admin/dashboard", tags=["Admin Dashboard"])


def pagination_limit(
    limit: int = Query(default=50, ge=1, le=200, description="Số bản ghi tối đa trả về."),
) -> int:
    return limit


def pagination_offset(
    offset: int = Query(default=0, ge=0, description="Vị trí bắt đầu phân trang."),
) -> int:
    return offset


@router.get("/overview", response_model=AdminOverviewResponse)
async def dashboard_overview(
    _: AdminViewer = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.get_overview(db)


@router.get("/users", response_model=AdminUserListResponse)
async def dashboard_users(
    search: Optional[str] = Query(default=None, description="Tìm theo email, tên hoặc user id."),
    role: Optional[str] = Query(default=None, description="Lọc role: admin, ceo, manager."),
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    viewer: AdminViewer = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.list_users(
        db,
        viewer,
        search=search,
        role=role,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations", response_model=ConversationLogListResponse)
async def dashboard_conversations(
    user_id: Optional[str] = Query(default=None, description="Lọc theo user id."),
    status: Optional[str] = Query(default=None, description="Lọc hội thoại có message thuộc status này."),
    search: Optional[str] = Query(default=None, description="Tìm theo tiêu đề hoặc tóm tắt hội thoại."),
    limit: int = Depends(pagination_limit),
    offset: int = Depends(pagination_offset),
    viewer: AdminViewer = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.list_conversations(
        db,
        viewer,
        user_id=user_id,
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationLogDetailResponse)
async def dashboard_conversation_detail(
    conversation_id: UUID,
    viewer: AdminViewer = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
):
    conversation = await query_layer.get_conversation_detail(db, viewer, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội thoại.")
    return conversation


@router.get("/rag", response_model=RagStatsResponse)
async def dashboard_rag(
    _: AdminViewer = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.get_rag_stats(db)


@router.get("/llm-providers", response_model=LlmProvidersStatusResponse)
async def dashboard_llm_providers(
    _: AdminViewer = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.get_llm_providers_status(db)
