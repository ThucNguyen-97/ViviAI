from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
from db.base import get_db

router = APIRouter(prefix="/business", tags=["Business Queries"])


def pagination_limit(
    limit: int = Query(default=50, ge=1, le=200, description="Số bản ghi tối đa trả về."),
) -> int:
    return limit


def pagination_offset(
    offset: int = Query(default=0, ge=0, description="Vị trí bắt đầu phân trang."),
) -> int:
    return offset


@router.get("/overview", response_model=BusinessOverviewResponse)
async def business_overview(db: AsyncSession = Depends(get_db)):
    return await query_layer.get_business_overview(db)


@router.get("/partners", response_model=PartnerListResponse)
async def partners(
    search: Optional[str] = Query(default=None, description="Tìm theo tên, SĐT, email hoặc địa chỉ."),
    partner_type: Optional[str] = Query(default=None, description="Lọc theo loại đối tác."),
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


@router.get("/inventory", response_model=InventoryListResponse)
async def inventory(
    search: Optional[str] = Query(default=None, description="Tìm theo tên hoặc mô tả hàng hóa."),
    low_stock_below: Optional[int] = Query(default=None, ge=0, description="Lọc hàng tồn kho <= ngưỡng."),
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


@router.get("/inventory/valuation", response_model=InventoryValuationResponse)
async def inventory_valuation(db: AsyncSession = Depends(get_db)):
    return await query_layer.get_inventory_valuation(db)


@router.get("/journals", response_model=JournalEntryListResponse)
async def journal_entries(
    date_from: Optional[datetime] = Query(default=None, description="Lọc bút toán từ ngày/giờ này."),
    date_to: Optional[datetime] = Query(default=None, description="Lọc bút toán đến ngày/giờ này."),
    status: Optional[str] = Query(default=None, description="Lọc theo trạng thái bút toán."),
    account_code: Optional[str] = Query(default=None, description="Lọc các bút toán có tài khoản này."),
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


@router.get("/journals/{entry_id}", response_model=JournalEntryRead)
async def journal_entry(entry_id: UUID, db: AsyncSession = Depends(get_db)):
    entry = await query_layer.get_journal_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Không tìm thấy bút toán.")
    return entry


@router.get("/accounts/balances", response_model=AccountBalanceResponse)
async def account_balances(
    date_from: Optional[datetime] = Query(default=None, description="Tổng hợp từ ngày/giờ này."),
    date_to: Optional[datetime] = Query(default=None, description="Tổng hợp đến ngày/giờ này."),
    status: Optional[str] = Query(default=None, description="Chỉ tổng hợp bút toán theo trạng thái."),
    db: AsyncSession = Depends(get_db),
):
    return await query_layer.get_account_balances(
        db,
        date_from=date_from,
        date_to=date_to,
        status=status,
    )
