"""Add llm_provider_calls

Revision ID: a1b2c3d4e5f6
Revises: 9e0f1a2b3c4d
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9e0f1a2b3c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_provider_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("phase", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_cost_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("output_cost_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("finish_reason", sa.String(100), nullable=True),
        sa.Column("provider_request_id", sa.String(255), nullable=True),
        sa.Column("fallback_from", sa.String(50), nullable=True),
        sa.Column("error_type", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("meta_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_provider_calls_conversation_id", "llm_provider_calls", ["conversation_id"])
    op.create_index("ix_llm_provider_calls_message_id", "llm_provider_calls", ["message_id"])
    op.create_index("ix_llm_provider_calls_provider", "llm_provider_calls", ["provider"])
    op.create_index("ix_llm_provider_calls_status", "llm_provider_calls", ["status"])
    op.create_index("ix_llm_provider_calls_created_at", "llm_provider_calls", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_provider_calls_created_at", table_name="llm_provider_calls")
    op.drop_index("ix_llm_provider_calls_status", table_name="llm_provider_calls")
    op.drop_index("ix_llm_provider_calls_provider", table_name="llm_provider_calls")
    op.drop_index("ix_llm_provider_calls_message_id", table_name="llm_provider_calls")
    op.drop_index("ix_llm_provider_calls_conversation_id", table_name="llm_provider_calls")
    op.drop_table("llm_provider_calls")
