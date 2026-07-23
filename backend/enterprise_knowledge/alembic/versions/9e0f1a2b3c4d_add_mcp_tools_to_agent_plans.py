"""Add mcp_tools to agent_plans

Revision ID: 9e0f1a2b3c4d
Revises: 8d9e0f1a2b3c
Create Date: 2026-07-20

Keep the physical column order by rebuilding agent_plans with mcp_tools placed
right after raw_plan.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9e0f1a2b3c4d"
down_revision: Union[str, None] = "8d9e0f1a2b3c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    _drop_agent_plan_constraints_and_triggers()

    op.execute(
        """
        CREATE TABLE agent_plans_new (
            id UUID NOT NULL,
            message_id UUID NOT NULL,
            raw_plan JSONB NOT NULL,
            mcp_tools JSONB,
            total_steps INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO agent_plans_new (
            id,
            message_id,
            raw_plan,
            mcp_tools,
            total_steps,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            created_at
        )
        SELECT
            id,
            message_id,
            raw_plan,
            NULL,
            total_steps,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            created_at
        FROM agent_plans
        """
    )

    op.execute("DROP TABLE agent_plans")
    op.execute("ALTER TABLE agent_plans_new RENAME TO agent_plans")
    _create_agent_plan_constraints_and_triggers()


def downgrade() -> None:
    _drop_agent_plan_constraints_and_triggers()

    op.execute(
        """
        CREATE TABLE agent_plans_old (
            id UUID NOT NULL,
            message_id UUID NOT NULL,
            raw_plan JSONB NOT NULL,
            total_steps INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO agent_plans_old (
            id,
            message_id,
            raw_plan,
            total_steps,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            created_at
        )
        SELECT
            id,
            message_id,
            raw_plan,
            total_steps,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            created_at
        FROM agent_plans
        """
    )

    op.execute("DROP TABLE agent_plans")
    op.execute("ALTER TABLE agent_plans_old RENAME TO agent_plans")
    _create_agent_plan_constraints_and_triggers()


def _drop_agent_plan_constraints_and_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS agent_tasks_refresh_conversation_token_totals ON agent_tasks")
    op.execute("DROP TRIGGER IF EXISTS agent_plans_refresh_conversation_token_totals ON agent_plans")
    op.execute("DROP TRIGGER IF EXISTS agent_plans_sync_detail_total_tokens ON agent_plans")
    op.execute("ALTER TABLE agent_tasks DROP CONSTRAINT IF EXISTS agent_tasks_agent_plans_id_fkey")
    op.execute("ALTER TABLE agent_plans DROP CONSTRAINT IF EXISTS agent_plans_message_id_fkey")
    op.execute("ALTER TABLE agent_plans DROP CONSTRAINT IF EXISTS agent_plans_pkey")


def _create_agent_plan_constraints_and_triggers() -> None:
    op.create_primary_key("agent_plans_pkey", "agent_plans", ["id"])
    op.create_foreign_key(
        "agent_plans_message_id_fkey",
        "agent_plans",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "agent_tasks_agent_plans_id_fkey",
        "agent_tasks",
        "agent_plans",
        ["agent_plans_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        """
        CREATE TRIGGER agent_plans_sync_detail_total_tokens
        BEFORE INSERT OR UPDATE OF input_tokens, output_tokens ON agent_plans
        FOR EACH ROW
        EXECUTE FUNCTION sync_detail_total_tokens()
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_plans_refresh_conversation_token_totals
        AFTER INSERT OR UPDATE OR DELETE ON agent_plans
        FOR EACH ROW
        EXECUTE FUNCTION refresh_conversation_tokens_from_agent_plans()
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_tasks_refresh_conversation_token_totals
        AFTER INSERT OR UPDATE OR DELETE ON agent_tasks
        FOR EACH ROW
        EXECUTE FUNCTION refresh_conversation_tokens_from_agent_tasks()
        """
    )
