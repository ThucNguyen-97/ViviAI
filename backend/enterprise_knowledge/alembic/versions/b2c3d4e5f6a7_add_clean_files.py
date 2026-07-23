"""Add clean_files

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clean_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_file_name", sa.String(255), nullable=False),
        sa.Column("clean_file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="ready"),
        sa.Column("uploaded_by", sa.String(128), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="vm_firewall"),
        sa.Column("raw_vm_path", sa.String(1024), nullable=True),
        sa.Column("sanitized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("firewall_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("meta_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clean_files_file_type", "clean_files", ["file_type"])
    op.create_index("ix_clean_files_checksum_sha256", "clean_files", ["checksum_sha256"])
    op.create_index("ix_clean_files_status", "clean_files", ["status"])
    op.create_index("ix_clean_files_uploaded_by", "clean_files", ["uploaded_by"])
    op.create_index("ix_clean_files_created_at", "clean_files", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_clean_files_created_at", table_name="clean_files")
    op.drop_index("ix_clean_files_uploaded_by", table_name="clean_files")
    op.drop_index("ix_clean_files_status", table_name="clean_files")
    op.drop_index("ix_clean_files_checksum_sha256", table_name="clean_files")
    op.drop_index("ix_clean_files_file_type", table_name="clean_files")
    op.drop_table("clean_files")
