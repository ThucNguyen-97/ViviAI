"""Rename agent_tasks to agent_steps, add plan_name, rename label to step_name

Revision ID: c3d4e5f6a7b8
Revises: 8d9e0f1a2b3c
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"

branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add plan_name column to agent_plans
    op.add_column("agent_plans", sa.Column("plan_name", sa.String(255), nullable=True))
    op.execute("UPDATE agent_plans SET plan_name = 'Kế hoạch thực thi tác vụ' WHERE plan_name IS NULL")

    # 2. Drop old triggers & functions on agent_tasks
    op.execute("DROP TRIGGER IF EXISTS agent_tasks_refresh_conversation_token_totals ON agent_tasks")
    op.execute("DROP TRIGGER IF EXISTS agent_tasks_sync_detail_total_tokens ON agent_tasks")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_tokens_from_agent_tasks() CASCADE")


    # 3. Rename table agent_tasks -> agent_steps
    op.rename_table("agent_tasks", "agent_steps")

    # 4. Rename column agent_plans_id -> agent_plan_id
    op.alter_column("agent_steps", "agent_plans_id", new_column_name="agent_plan_id")

    # 5. Rename column label -> step_name
    op.alter_column("agent_steps", "label", new_column_name="step_name")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_conversation_token_totals(p_conversation_id UUID)
        RETURNS VOID AS $$
        BEGIN
            UPDATE conversations
            SET
                input_tokens = token_totals.input_tokens,
                output_tokens = token_totals.output_tokens,
                total_tokens = token_totals.input_tokens + token_totals.output_tokens
            FROM (
                SELECT
                    (
                        SELECT COALESCE(SUM(COALESCE(input_tokens, 0)), 0)
                        FROM messages
                        WHERE conversation_id = p_conversation_id
                    ) + (
                        SELECT COALESCE(SUM(COALESCE(agent_plans.input_tokens, 0)), 0)
                        FROM agent_plans
                        JOIN messages ON messages.id = agent_plans.message_id
                        WHERE messages.conversation_id = p_conversation_id
                    ) + (
                        SELECT COALESCE(SUM(COALESCE(agent_steps.input_tokens, 0)), 0)
                        FROM agent_steps
                        JOIN agent_plans ON agent_plans.id = agent_steps.agent_plan_id
                        JOIN messages ON messages.id = agent_plans.message_id
                        WHERE messages.conversation_id = p_conversation_id
                    ) AS input_tokens,
                    (
                        SELECT COALESCE(SUM(COALESCE(output_tokens, 0)), 0)
                        FROM messages
                        WHERE conversation_id = p_conversation_id
                    ) + (
                        SELECT COALESCE(SUM(COALESCE(agent_plans.output_tokens, 0)), 0)
                        FROM agent_plans
                        JOIN messages ON messages.id = agent_plans.message_id
                        WHERE messages.conversation_id = p_conversation_id
                    ) + (
                        SELECT COALESCE(SUM(COALESCE(agent_steps.output_tokens, 0)), 0)
                        FROM agent_steps
                        JOIN agent_plans ON agent_plans.id = agent_steps.agent_plan_id
                        JOIN messages ON messages.id = agent_plans.message_id
                        WHERE messages.conversation_id = p_conversation_id
                    ) AS output_tokens
            ) AS token_totals
            WHERE conversations.id = p_conversation_id;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_steps_sync_detail_total_tokens
        BEFORE INSERT OR UPDATE OF input_tokens, output_tokens ON agent_steps
        FOR EACH ROW
        EXECUTE FUNCTION sync_detail_total_tokens()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_conversation_tokens_from_agent_steps()
        RETURNS TRIGGER AS $$
        DECLARE
            new_conversation_id UUID;
            old_conversation_id UUID;
        BEGIN
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                SELECT messages.conversation_id
                INTO new_conversation_id
                FROM agent_plans
                JOIN messages ON messages.id = agent_plans.message_id
                WHERE agent_plans.id = NEW.agent_plan_id;

                PERFORM refresh_conversation_token_totals(new_conversation_id);
            END IF;

            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT messages.conversation_id
                INTO old_conversation_id
                FROM agent_plans
                JOIN messages ON messages.id = agent_plans.message_id
                WHERE agent_plans.id = OLD.agent_plan_id;

                IF TG_OP = 'DELETE' OR old_conversation_id IS DISTINCT FROM new_conversation_id THEN
                    PERFORM refresh_conversation_token_totals(old_conversation_id);
                END IF;
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER agent_steps_refresh_conversation_token_totals
        AFTER INSERT OR UPDATE OR DELETE ON agent_steps
        FOR EACH ROW
        EXECUTE FUNCTION refresh_conversation_tokens_from_agent_steps()
        """
    )



def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS agent_steps_refresh_conversation_token_totals ON agent_steps")
    op.execute("DROP TRIGGER IF EXISTS agent_steps_sync_detail_total_tokens ON agent_steps")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_tokens_from_agent_steps()")

    op.alter_column("agent_steps", "step_name", new_column_name="label")
    op.alter_column("agent_steps", "agent_plan_id", new_column_name="agent_plans_id")
    op.rename_table("agent_steps", "agent_tasks")

    op.execute(
        """
        CREATE TRIGGER agent_tasks_sync_detail_total_tokens
        BEFORE INSERT OR UPDATE OF input_tokens, output_tokens ON agent_tasks
        FOR EACH ROW
        EXECUTE FUNCTION sync_detail_total_tokens()
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
    op.drop_column("agent_plans", "plan_name")
