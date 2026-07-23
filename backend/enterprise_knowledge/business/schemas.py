from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json")
    def serialize_values(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value


class PaginatedResponse(ApiModel):
    total: int
    limit: int
    offset: int


class PartnerRead(ApiModel):
    id: str
    name: str
    partner_type: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime


class PartnerListResponse(PaginatedResponse):
    partners: list[PartnerRead]


class InventoryRead(ApiModel):
    id: str
    name: str
    quantity: int
    unit: Optional[str] = None
    purchase_price: Decimal
    price: Decimal
    description: Optional[str] = None
    created_at: datetime


class InventoryListResponse(PaginatedResponse):
    items: list[InventoryRead]


class InventoryValuationResponse(ApiModel):
    total_items: int
    total_quantity: int
    total_purchase_value: Decimal
    total_sale_value: Decimal
    potential_gross_profit: Decimal


class JournalLineRead(ApiModel):
    id: str
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal


class JournalEntryRead(ApiModel):
    id: str
    vouchers_id: Optional[str] = None
    storage_url: Optional[str] = None
    date: datetime
    description: Optional[str] = None
    status: str
    approved_at: Optional[datetime] = None
    created_at: datetime
    lines: list[JournalLineRead] = Field(default_factory=list)


class JournalEntryListResponse(PaginatedResponse):
    entries: list[JournalEntryRead]


class AccountBalanceRead(ApiModel):
    account_code: str
    account_name: str
    total_debit: Decimal
    total_credit: Decimal
    balance: Decimal


class AccountBalanceResponse(ApiModel):
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    status: Optional[str] = None
    accounts: list[AccountBalanceRead]


class BusinessOverviewResponse(ApiModel):
    total_partners: int
    total_inventory_items: int
    total_inventory_quantity: int
    inventory_purchase_value: Decimal
    inventory_sale_value: Decimal
    total_journal_entries: int
    pending_journal_entries: int
    approved_journal_entries: int
    total_debit: Decimal
    total_credit: Decimal
