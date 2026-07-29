"""add manager followed partners association

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manager_followed_partners",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("partner_id", sa.UUID(), nullable=False),
        sa.Column("partner_email", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "partner_id"),
    )


def downgrade() -> None:
    op.drop_table("manager_followed_partners")
