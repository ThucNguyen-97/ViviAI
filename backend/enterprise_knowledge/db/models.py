import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import ForeignKey, String, Integer, DateTime, Text, Numeric, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from db.base import Base

# Gemini Embedding 2 is stored at 768 dimensions to keep pgvector compact.
EMBEDDING_DIM = 768


class User(Base):
    """Báº£ng lÆ°u thĂ´ng tin ngÆ°á»i dĂ¹ng há»‡ thá»‘ng (Ä‘á»“ng bá»™ tá»« Firebase)."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # Firebase UID
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    google_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="manager")  # admin, ceo, manager
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )

    # Relationships
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="creator")
    vouchers: Mapped[List["Voucher"]] = relationship("Voucher", back_populates="creator")


class RagDocument(Base):
    """Báº£ng lÆ°u thĂ´ng tin cĂ¡c tĂ i liá»‡u tri thá»©c phá»¥c vá»¥ RAG (chá»‰ Admin má»›i táº£i lĂªn)."""
    __tablename__ = "rag_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )

    # Relationships
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk", back_populates="rag_document", cascade="all, delete-orphan"
    )


class Document(Base):
    """Báº£ng lÆ°u thĂ´ng tin cĂ¡c tĂ i liá»‡u cá»§a ngÆ°á»i dĂ¹ng hoáº·c do AI chá»‰nh sá»­a/táº¡o sinh."""
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    required_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow()
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Metadata bá»• sung lÆ°u trá»¯ dÆ°á»›i dáº¡ng JSONB
    meta_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    creator: Mapped[Optional["User"]] = relationship("User", back_populates="documents")


class Chunk(Base):
    """Báº£ng lÆ°u cĂ¡c Ä‘oáº¡n text ngáº¯n Ä‘Æ°á»£c chia nhá» tá»« tĂ i liá»‡u RAG vĂ  embedding vector tÆ°Æ¡ng á»©ng."""
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    rag_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # pgvector embedding column
    embedding: Mapped[Vector] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    
    meta_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    rag_document: Mapped["RagDocument"] = relationship("RagDocument", back_populates="chunks")


class Voucher(Base):
    """Báº£ng lÆ°u trá»¯ thĂ´ng tin hĂ³a Ä‘Æ¡n chá»©ng tá»« (vouchers)."""
    __tablename__ = "vouchers"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    creator: Mapped[Optional["User"]] = relationship("User", back_populates="vouchers")
    general_journals: Mapped[List["GeneralJournal"]] = relationship("GeneralJournal", back_populates="voucher")


class Conversation(Base):
    """Báº£ng lÆ°u trá»¯ phiĂªn chat há»™i thoáº¡i."""
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_token_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    output_token_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow()
    )

    # Relationships
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """Báº£ng lÆ°u chi tiáº¿t cĂ¡c tin nháº¯n trong má»™t cuá»™c há»™i thoáº¡i."""
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # pending, generating, completed, failed
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Cá»™t lÆ°u giĂ¡ trá»‹ source_url tá»« báº£ng documents & vouchers tÆ°Æ¡ng á»©ng
    documents_source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    vouchers_source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    agent_plans: Mapped[List["AgentPlan"]] = relationship("AgentPlan", back_populates="message", cascade="all, delete-orphan")


class AgentPlan(Base):
    """Bảng lưu trữ kế hoạch tổng thể suy luận của AI (agent_plans)."""
    __tablename__ = "agent_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    plan_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
    mcp_tools: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress") # in_progress, success, failed
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="agent_plans")
    steps: Mapped[List["AgentStep"]] = relationship(
        "AgentStep", back_populates="plan", cascade="all, delete-orphan"
    )


class AgentStep(Base):
    """Bảng lưu trữ chi tiết từng bước thực thi trong kế hoạch của AI (agent_steps)."""
    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    agent_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_plans.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(255), nullable=False)
    thought: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending") # pending, running, success, failed
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    plan: Mapped["AgentPlan"] = relationship("AgentPlan", back_populates="steps")



class LlmProviderCall(Base):
    """Provider call metadata recorded by the VM LLM router."""
    __tablename__ = "llm_provider_calls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    output_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fallback_from: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), index=True
    )


class CleanFile(Base):
    """Metadata for files that passed VM firewall/sanitization and are stored by EK."""
    __tablename__ = "clean_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    clean_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ready", index=True)
    uploaded_by: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="vm_firewall")
    raw_vm_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    sanitized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    firewall_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    meta_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), index=True
    )


class Partner(Base):
    """Báº£ng lÆ°u thĂ´ng tin Ä‘á»‘i tĂ¡c (KhĂ¡ch hĂ ng / NhĂ  cung cáº¥p)."""
    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Kiá»ƒu Ä‘á»‘i tĂ¡c: customer, vendor, partner, ...
    partner_type: Mapped[str] = mapped_column(String(50), nullable=False, default="customer")
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )


class ManagerFollowedPartner(Base):
    """Partners followed by an individual manager for email monitoring."""

    __tablename__ = "manager_followed_partners"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), primary_key=True
    )
    partner_email: Mapped[str] = mapped_column(String(255), nullable=False)


class Inventory(Base):
    """Báº£ng lÆ°u thĂ´ng tin kho hĂ ng / sáº£n pháº©m nghiá»‡p vá»¥."""
    __tablename__ = "inventory"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # ÄÆ¡n vá»‹ tĂ­nh (thĂªm má»›i)
    purchase_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.0)  # GiĂ¡ mua
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.0)  # GiĂ¡ bĂ¡n
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )


class GeneralJournal(Base):
    """Báº£ng lÆ°u nháº­t kĂ½ chung."""
    __tablename__ = "general_journal"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    
    # Cá»™t liĂªn káº¿t vouchers_id sau cá»™t id
    vouchers_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("vouchers.id", ondelete="SET NULL"), nullable=True
    )
    storage_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # pending, approved, draft...
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow()
    )

    # Relationships
    voucher: Mapped[Optional["Voucher"]] = relationship("Voucher", back_populates="general_journals")
    lines: Mapped[List["GeneralJournalLine"]] = relationship(
        "GeneralJournalLine", back_populates="general_journal", cascade="all, delete-orphan"
    )


class GeneralJournalLine(Base):
    """Báº£ng lÆ°u chi tiáº¿t bĂºt toĂ¡n ghi sá»• (Ä‘á»‘i á»©ng ná»£/cĂ³)."""
    __tablename__ = "general_journal_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    # general_journal_id Ä‘á»©ng sau id
    general_journal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("general_journal.id", ondelete="CASCADE"), nullable=False
    )
    
    account_code: Mapped[str] = mapped_column(String(50), nullable=False)  # VĂ­ dá»¥: 1111, 1121, 331, 131
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)  # TĂªn tĂ i khoáº£n tÆ°Æ¡ng á»©ng
    
    debit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    credit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)

    # Relationships
    general_journal: Mapped["GeneralJournal"] = relationship("GeneralJournal", back_populates="lines")

