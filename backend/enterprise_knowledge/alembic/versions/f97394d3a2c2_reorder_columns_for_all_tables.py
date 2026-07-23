"""Reorder columns for all tables

Revision ID: f97394d3a2c2
Revises: 94175f7b93a6
Create Date: 2026-07-17

Drop and recreate all tables with correct column order.
Safe to run only when tables are empty (dev environment).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector


revision: str = 'f97394d3a2c2'
down_revision: Union[str, None] = '94175f7b93a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop all tables in reverse dependency order to avoid FK constraint errors
    op.execute("DROP TABLE IF EXISTS agent_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS general_journal_lines CASCADE")
    op.execute("DROP TABLE IF EXISTS general_journal CASCADE")
    op.execute("DROP TABLE IF EXISTS vouchers CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS inventory CASCADE")
    op.execute("DROP TABLE IF EXISTS partners CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    # ── users ──────────────────────────────────────────────────────────────
    op.create_table('users',
        sa.Column('id',         sa.String(128),  nullable=False),
        sa.Column('email',      sa.String(255),  nullable=False),
        sa.Column('role',       sa.String(50),   nullable=False, server_default='manager'),
        sa.Column('created_at', sa.DateTime(),   nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── rag_documents ───────────────────────────────────────────────────────
    op.create_table('rag_documents',
        sa.Column('id',          sa.Uuid(),       nullable=False),
        sa.Column('file_name',   sa.String(255),  nullable=False),
        sa.Column('file_path',   sa.String(1024), nullable=False),
        sa.Column('file_size',   sa.Integer(),    nullable=False),
        sa.Column('file_type',   sa.String(100),  nullable=False),
        sa.Column('storage_url', sa.String(1024), nullable=True),
        sa.Column('created_at',  sa.DateTime(),   nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── chunks ─────────────────────────────────────────────────────────────
    op.create_table('chunks',
        sa.Column('id',              sa.Uuid(),     nullable=False),
        sa.Column('rag_document_id', sa.Uuid(),     nullable=False),
        sa.Column('content',         sa.Text(),     nullable=False),
        sa.Column('embedding',       pgvector.sqlalchemy.Vector(768), nullable=False),
        sa.Column('chunk_index',     sa.Integer(),  nullable=False),
        sa.Column('meta_info',       postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['rag_document_id'], ['rag_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── documents ──────────────────────────────────────────────────────────
    op.create_table('documents',
        sa.Column('id',          sa.Uuid(),       nullable=False),
        sa.Column('file_name',   sa.String(255),  nullable=False),
        sa.Column('file_path',   sa.String(1024), nullable=False),
        sa.Column('file_size',   sa.Integer(),    nullable=False),
        sa.Column('file_type',   sa.String(100),  nullable=False),
        sa.Column('source_url',  sa.String(1024), nullable=True),
        sa.Column('created_at',  sa.DateTime(),   nullable=False),
        sa.Column('updated_at',  sa.DateTime(),   nullable=False),
        sa.Column('created_by',  sa.String(128),  nullable=True),
        sa.Column('meta_info',   postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── vouchers ───────────────────────────────────────────────────────────
    op.create_table('vouchers',
        sa.Column('id',          sa.Uuid(),       nullable=False),
        sa.Column('file_name',   sa.String(255),  nullable=False),
        sa.Column('file_path',   sa.String(1024), nullable=False),
        sa.Column('file_size',   sa.Integer(),    nullable=False),
        sa.Column('file_type',   sa.String(100),  nullable=False),
        sa.Column('storage_url', sa.String(1024), nullable=True),
        sa.Column('created_at',  sa.DateTime(),   nullable=False),
        sa.Column('created_by',  sa.String(128),  nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── general_journal ────────────────────────────────────────────────────
    op.create_table('general_journal',
        sa.Column('id',          sa.Uuid(),       nullable=False),
        sa.Column('vouchers_id', sa.Uuid(),       nullable=True),
        sa.Column('storage_url', sa.String(1024), nullable=True),
        sa.Column('date',        sa.DateTime(),   nullable=False),
        sa.Column('description', sa.Text(),       nullable=True),
        sa.Column('status',      sa.String(50),   nullable=False, server_default='pending'),
        sa.Column('approved_at', sa.DateTime(),   nullable=True),
        sa.Column('created_at',  sa.DateTime(),   nullable=False),
        sa.ForeignKeyConstraint(['vouchers_id'], ['vouchers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── general_journal_lines ──────────────────────────────────────────────
    op.create_table('general_journal_lines',
        sa.Column('id',                  sa.Uuid(),      nullable=False),
        sa.Column('general_journal_id',  sa.Uuid(),      nullable=False),
        sa.Column('account_code',        sa.String(50),  nullable=False),
        sa.Column('account_name',        sa.String(255), nullable=False),
        sa.Column('debit',               sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('credit',              sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['general_journal_id'], ['general_journal.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── inventory ──────────────────────────────────────────────────────────
    op.create_table('inventory',
        sa.Column('id',             sa.Uuid(),        nullable=False),
        sa.Column('name',           sa.String(255),   nullable=False),
        sa.Column('quantity',       sa.Integer(),     nullable=False, server_default='0'),
        sa.Column('unit',           sa.String(50),    nullable=True),
        sa.Column('purchase_price', sa.Numeric(10,2), nullable=False, server_default='0'),
        sa.Column('price',          sa.Numeric(10,2), nullable=False, server_default='0'),
        sa.Column('description',    sa.Text(),        nullable=True),
        sa.Column('created_at',     sa.DateTime(),    nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── partners ───────────────────────────────────────────────────────────
    op.create_table('partners',
        sa.Column('id',           sa.Uuid(),      nullable=False),
        sa.Column('name',         sa.String(255), nullable=False),
        sa.Column('partner_type', sa.String(50),  nullable=False, server_default='customer'),
        sa.Column('phone',        sa.String(50),  nullable=True),
        sa.Column('email',        sa.String(100), nullable=True),
        sa.Column('address',      sa.String(500), nullable=True),
        sa.Column('created_at',   sa.DateTime(),  nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── conversations ──────────────────────────────────────────────────────
    op.create_table('conversations',
        sa.Column('id',         sa.Uuid(),       nullable=False),
        sa.Column('user_id',    sa.String(128),  nullable=False),
        sa.Column('title',      sa.String(255),  nullable=False),
        sa.Column('summary',    sa.Text(),        nullable=True),
        sa.Column('created_at', sa.DateTime(),   nullable=False),
        sa.Column('updated_at', sa.DateTime(),   nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])

    # ── messages ───────────────────────────────────────────────────────────
    op.create_table('messages',
        sa.Column('id',                   sa.Uuid(),       nullable=False),
        sa.Column('conversation_id',      sa.Uuid(),       nullable=False),
        sa.Column('role',                 sa.String(50),   nullable=False),
        sa.Column('content',              sa.Text(),       nullable=False),
        sa.Column('status',               sa.String(50),   nullable=True),
        sa.Column('documents_source_url', sa.String(1024), nullable=True),
        sa.Column('vouchers_source_url',  sa.String(1024), nullable=True),
        sa.Column('created_at',           sa.DateTime(),   nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── agent_plans ────────────────────────────────────────────────────────
    op.create_table('agent_plans',
        sa.Column('id',          sa.Uuid(),     nullable=False),
        sa.Column('message_id',  sa.Uuid(),     nullable=False),
        sa.Column('raw_plan',    postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('total_steps', sa.Integer(),  nullable=False, server_default='0'),
        sa.Column('status',      sa.String(20), nullable=False, server_default='in_progress'),
        sa.Column('created_at',  sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── agent_tasks ────────────────────────────────────────────────────────
    op.create_table('agent_tasks',
        sa.Column('id',             sa.Uuid(),      nullable=False),
        sa.Column('agent_plans_id', sa.Uuid(),      nullable=False),
        sa.Column('step_number',    sa.Integer(),   nullable=False),
        sa.Column('label',          sa.String(255), nullable=False),
        sa.Column('thought',        sa.Text(),      nullable=False),
        sa.Column('action',         sa.String(255), nullable=True),
        sa.Column('action_input',   sa.Text(),      nullable=True),
        sa.Column('action_output',  sa.Text(),      nullable=True),
        sa.Column('status',         sa.String(20),  nullable=False, server_default='pending'),
        sa.Column('error_message',  sa.Text(),      nullable=True),
        sa.Column('started_at',     sa.DateTime(),  nullable=False),
        sa.Column('ended_at',       sa.DateTime(),  nullable=True),
        sa.ForeignKeyConstraint(['agent_plans_id'], ['agent_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS general_journal_lines CASCADE")
    op.execute("DROP TABLE IF EXISTS general_journal CASCADE")
    op.execute("DROP TABLE IF EXISTS vouchers CASCADE")
    op.execute("DROP TABLE IF EXISTS chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS inventory CASCADE")
    op.execute("DROP TABLE IF EXISTS partners CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
