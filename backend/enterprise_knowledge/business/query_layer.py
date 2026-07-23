from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from business.schemas import (
    AccountBalanceRead,
    AccountBalanceResponse,
    BusinessOverviewResponse,
    InventoryListResponse,
    InventoryRead,
    InventoryValuationResponse,
    JournalEntryListResponse,
    JournalEntryRead,
    JournalLineRead,
    PartnerListResponse,
    PartnerRead,
)
from db.models import GeneralJournal, GeneralJournalLine, Inventory, Partner


def _money(value) -> Decimal:
    return value if value is not None else Decimal("0")


def _apply_pagination(statement: Select, limit: int, offset: int) -> Select:
    return statement.limit(limit).offset(offset)


async def list_partners(
    db: AsyncSession,
    *,
    search: Optional[str] = None,
    partner_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> PartnerListResponse:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Partner.name.ilike(pattern),
                Partner.phone.ilike(pattern),
                Partner.email.ilike(pattern),
                Partner.address.ilike(pattern),
            )
        )
    if partner_type:
        filters.append(Partner.partner_type == partner_type)

    base = select(Partner).where(and_(*filters)).order_by(Partner.created_at.desc())
    count_statement = select(func.count()).select_from(Partner).where(and_(*filters))

    total = await db.scalar(count_statement)
    result = await db.execute(_apply_pagination(base, limit, offset))
    partners = result.scalars().all()

    return PartnerListResponse(
        total=total or 0,
        limit=limit,
        offset=offset,
        partners=[
            PartnerRead(
                id=str(partner.id),
                name=partner.name,
                partner_type=partner.partner_type,
                phone=partner.phone,
                email=partner.email,
                address=partner.address,
                created_at=partner.created_at,
            )
            for partner in partners
        ],
    )


async def list_inventory(
    db: AsyncSession,
    *,
    search: Optional[str] = None,
    low_stock_below: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> InventoryListResponse:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(Inventory.name.ilike(pattern), Inventory.description.ilike(pattern)))
    if low_stock_below is not None:
        filters.append(Inventory.quantity <= low_stock_below)

    base = select(Inventory).where(and_(*filters)).order_by(Inventory.created_at.desc())
    count_statement = select(func.count()).select_from(Inventory).where(and_(*filters))

    total = await db.scalar(count_statement)
    result = await db.execute(_apply_pagination(base, limit, offset))
    items = result.scalars().all()

    return InventoryListResponse(
        total=total or 0,
        limit=limit,
        offset=offset,
        items=[
            InventoryRead(
                id=str(item.id),
                name=item.name,
                quantity=item.quantity,
                unit=item.unit,
                purchase_price=_money(item.purchase_price),
                price=_money(item.price),
                description=item.description,
                created_at=item.created_at,
            )
            for item in items
        ],
    )


async def get_inventory_valuation(db: AsyncSession) -> InventoryValuationResponse:
    statement = select(
        func.count(Inventory.id),
        func.coalesce(func.sum(Inventory.quantity), 0),
        func.coalesce(func.sum(Inventory.quantity * Inventory.purchase_price), 0),
        func.coalesce(func.sum(Inventory.quantity * Inventory.price), 0),
    )
    total_items, total_quantity, purchase_value, sale_value = (await db.execute(statement)).one()

    return InventoryValuationResponse(
        total_items=total_items or 0,
        total_quantity=total_quantity or 0,
        total_purchase_value=_money(purchase_value),
        total_sale_value=_money(sale_value),
        potential_gross_profit=_money(sale_value) - _money(purchase_value),
    )


async def list_journal_entries(
    db: AsyncSession,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    status: Optional[str] = None,
    account_code: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> JournalEntryListResponse:
    filters = []
    if date_from:
        filters.append(GeneralJournal.date >= date_from)
    if date_to:
        filters.append(GeneralJournal.date <= date_to)
    if status:
        filters.append(GeneralJournal.status == status)
    if account_code:
        filters.append(GeneralJournal.lines.any(GeneralJournalLine.account_code == account_code))

    base = (
        select(GeneralJournal)
        .options(selectinload(GeneralJournal.lines))
        .where(and_(*filters))
        .order_by(GeneralJournal.date.desc(), GeneralJournal.created_at.desc())
    )
    count_statement = select(func.count()).select_from(GeneralJournal).where(and_(*filters))

    total = await db.scalar(count_statement)
    result = await db.execute(_apply_pagination(base, limit, offset))
    entries = result.scalars().all()

    return JournalEntryListResponse(
        total=total or 0,
        limit=limit,
        offset=offset,
        entries=[
            JournalEntryRead(
                id=str(entry.id),
                vouchers_id=str(entry.vouchers_id) if entry.vouchers_id else None,
                storage_url=entry.storage_url,
                date=entry.date,
                description=entry.description,
                status=entry.status,
                approved_at=entry.approved_at,
                created_at=entry.created_at,
                lines=[
                    JournalLineRead(
                        id=str(line.id),
                        account_code=line.account_code,
                        account_name=line.account_name,
                        debit=_money(line.debit),
                        credit=_money(line.credit),
                    )
                    for line in sorted(entry.lines, key=lambda line: line.account_code)
                ],
            )
            for entry in entries
        ],
    )


async def get_journal_entry(db: AsyncSession, entry_id: UUID) -> Optional[JournalEntryRead]:
    result = await db.execute(
        select(GeneralJournal)
        .options(selectinload(GeneralJournal.lines))
        .where(GeneralJournal.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return None

    return JournalEntryRead(
        id=str(entry.id),
        vouchers_id=str(entry.vouchers_id) if entry.vouchers_id else None,
        storage_url=entry.storage_url,
        date=entry.date,
        description=entry.description,
        status=entry.status,
        approved_at=entry.approved_at,
        created_at=entry.created_at,
        lines=[
            JournalLineRead(
                id=str(line.id),
                account_code=line.account_code,
                account_name=line.account_name,
                debit=_money(line.debit),
                credit=_money(line.credit),
            )
            for line in sorted(entry.lines, key=lambda line: line.account_code)
        ],
    )


async def get_account_balances(
    db: AsyncSession,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    status: Optional[str] = None,
) -> AccountBalanceResponse:
    filters = []
    if date_from:
        filters.append(GeneralJournal.date >= date_from)
    if date_to:
        filters.append(GeneralJournal.date <= date_to)
    if status:
        filters.append(GeneralJournal.status == status)

    statement = (
        select(
            GeneralJournalLine.account_code,
            GeneralJournalLine.account_name,
            func.coalesce(func.sum(GeneralJournalLine.debit), 0).label("total_debit"),
            func.coalesce(func.sum(GeneralJournalLine.credit), 0).label("total_credit"),
        )
        .join(GeneralJournal, GeneralJournal.id == GeneralJournalLine.general_journal_id)
        .where(and_(*filters))
        .group_by(GeneralJournalLine.account_code, GeneralJournalLine.account_name)
        .order_by(GeneralJournalLine.account_code)
    )
    rows = (await db.execute(statement)).all()

    accounts = [
        AccountBalanceRead(
            account_code=row.account_code,
            account_name=row.account_name,
            total_debit=_money(row.total_debit),
            total_credit=_money(row.total_credit),
            balance=_money(row.total_debit) - _money(row.total_credit),
        )
        for row in rows
    ]

    return AccountBalanceResponse(
        date_from=date_from,
        date_to=date_to,
        status=status,
        accounts=accounts,
    )


async def get_business_overview(db: AsyncSession) -> BusinessOverviewResponse:
    partner_count = await db.scalar(select(func.count()).select_from(Partner))
    inventory_count = await db.scalar(select(func.count()).select_from(Inventory))

    inventory_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Inventory.quantity), 0),
                func.coalesce(func.sum(Inventory.quantity * Inventory.purchase_price), 0),
                func.coalesce(func.sum(Inventory.quantity * Inventory.price), 0),
            )
        )
    ).one()

    journal_row = (
        await db.execute(
            select(
                func.count(GeneralJournal.id),
                func.count().filter(GeneralJournal.status == "pending"),
                func.count().filter(GeneralJournal.status == "approved"),
            )
        )
    ).one()

    ledger_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(GeneralJournalLine.debit), 0),
                func.coalesce(func.sum(GeneralJournalLine.credit), 0),
            )
        )
    ).one()

    return BusinessOverviewResponse(
        total_partners=partner_count or 0,
        total_inventory_items=inventory_count or 0,
        total_inventory_quantity=inventory_row[0] or 0,
        inventory_purchase_value=_money(inventory_row[1]),
        inventory_sale_value=_money(inventory_row[2]),
        total_journal_entries=journal_row[0] or 0,
        pending_journal_entries=journal_row[1] or 0,
        approved_journal_entries=journal_row[2] or 0,
        total_debit=_money(ledger_row[0]),
        total_credit=_money(ledger_row[1]),
    )
