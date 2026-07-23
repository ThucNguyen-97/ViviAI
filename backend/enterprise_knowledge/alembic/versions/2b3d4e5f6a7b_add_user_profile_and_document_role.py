"""Add user profile fields and document access role

Revision ID: 2b3d4e5f6a7b
Revises: e76843c933a9
Create Date: 2026-07-17

Rebuild users and documents to keep column order aligned with the model,
while preserving existing rows and restoring foreign keys.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "2b3d4e5f6a7b"
down_revision: Union[str, None] = "e76843c933a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users_new (
            id VARCHAR(128) NOT NULL,
            email VARCHAR(255) NOT NULL,
            google_id VARCHAR(255),
            full_name VARCHAR(255),
            avatar_url VARCHAR(1024),
            role VARCHAR(50) NOT NULL DEFAULT 'manager',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_id VARCHAR(255),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO users_new (id, email, role, created_at)
        SELECT id, email, role, created_at
        FROM users
        """
    )

    op.execute(
        """
        CREATE TABLE documents_new (
            id UUID NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_path VARCHAR(1024) NOT NULL,
            file_size INTEGER NOT NULL,
            file_type VARCHAR(100) NOT NULL,
            source_url VARCHAR(1024),
            required_role VARCHAR(50),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_by VARCHAR(128),
            meta_info JSONB,
            PRIMARY KEY (id),
            CONSTRAINT documents_created_by_fkey
                FOREIGN KEY (created_by)
                REFERENCES users_new (id)
                ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO documents_new (
            id,
            file_name,
            file_path,
            file_size,
            file_type,
            source_url,
            created_at,
            updated_at,
            created_by,
            meta_info
        )
        SELECT
            id,
            file_name,
            file_path,
            file_size,
            file_type,
            source_url,
            created_at,
            updated_at,
            created_by,
            meta_info
        FROM documents
        """
    )

    op.execute("DROP TABLE documents CASCADE")
    op.execute("DROP TABLE users CASCADE")
    op.execute("ALTER TABLE users_new RENAME TO users")
    op.execute("ALTER TABLE documents_new RENAME TO documents")

    op.create_foreign_key(
        "vouchers_created_by_fkey",
        "vouchers",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE vouchers DROP CONSTRAINT IF EXISTS vouchers_created_by_fkey")

    op.execute(
        """
        CREATE TABLE users_old (
            id VARCHAR(128) NOT NULL,
            email VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'manager',
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        INSERT INTO users_old (id, email, role, created_at)
        SELECT id, email, role, created_at
        FROM users
        """
    )

    op.execute(
        """
        CREATE TABLE documents_old (
            id UUID NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_path VARCHAR(1024) NOT NULL,
            file_size INTEGER NOT NULL,
            file_type VARCHAR(100) NOT NULL,
            source_url VARCHAR(1024),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            created_by VARCHAR(128),
            meta_info JSONB,
            PRIMARY KEY (id),
            CONSTRAINT documents_created_by_fkey
                FOREIGN KEY (created_by)
                REFERENCES users_old (id)
                ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO documents_old (
            id,
            file_name,
            file_path,
            file_size,
            file_type,
            source_url,
            created_at,
            updated_at,
            created_by,
            meta_info
        )
        SELECT
            id,
            file_name,
            file_path,
            file_size,
            file_type,
            source_url,
            created_at,
            updated_at,
            created_by,
            meta_info
        FROM documents
        """
    )

    op.execute("DROP TABLE documents CASCADE")
    op.execute("DROP TABLE users CASCADE")
    op.execute("ALTER TABLE users_old RENAME TO users")
    op.execute("ALTER TABLE documents_old RENAME TO documents")

    op.create_foreign_key(
        "vouchers_created_by_fkey",
        "vouchers",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
