"""Normalize token usage by conversation

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
Create Date: 2026-07-18

Rebuild conversations, messages, agent_plans, and agent_tasks to keep logical
column order. Detail tables store only token counts; conversations stores
aggregate tokens and aggregate costs.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8d9e0f1a2b3c"
down_revision: Union[str, None] = "7c8d9e0f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS messages_refresh_conversation_usage_tokens ON messages")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_usage_tokens()")

    op.execute(
        """
        CREATE TABLE conversations_new (
            id UUID NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            input_token_cost NUMERIC(18, 2) NOT NULL DEFAULT 0,
            output_token_cost NUMERIC(18, 2) NOT NULL DEFAULT 0,
            total_cost NUMERIC(18, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO conversations_new (
            id,
            user_id,
            title,
            summary,
            input_tokens,
            output_tokens,
            total_tokens,
            input_token_cost,
            output_token_cost,
            total_cost,
            created_at,
            updated_at
        )
        SELECT
            id,
            user_id,
            title,
            summary,
            0,
            0,
            COALESCE(usage_tokens, 0),
            0,
            0,
            0,
            created_at,
            updated_at
        FROM conversations
        """
    )

    op.execute(
        """
        CREATE TABLE messages_new (
            id UUID NOT NULL,
            conversation_id UUID NOT NULL,
            role VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            status VARCHAR(50),
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            documents_source_url VARCHAR(1024),
            vouchers_source_url VARCHAR(1024),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO messages_new (
            id,
            conversation_id,
            role,
            content,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            documents_source_url,
            vouchers_source_url,
            created_at
        )
        SELECT
            id,
            conversation_id,
            role,
            content,
            status,
            COALESCE(input_tokens, 0),
            COALESCE(output_tokens, 0),
            COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0),
            documents_source_url,
            vouchers_source_url,
            created_at
        FROM messages
        """
    )

    op.execute(
        """
        CREATE TABLE agent_plans_new (
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
        INSERT INTO agent_plans_new (
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
            0,
            0,
            0,
            created_at
        FROM agent_plans
        """
    )

    op.execute(
        """
        CREATE TABLE agent_tasks_new (
            id UUID NOT NULL,
            agent_plans_id UUID NOT NULL,
            step_number INTEGER NOT NULL,
            label VARCHAR(255) NOT NULL,
            thought TEXT NOT NULL,
            action VARCHAR(255),
            action_input TEXT,
            action_output TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            ended_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )
    op.execute(
        """
        INSERT INTO agent_tasks_new (
            id,
            agent_plans_id,
            step_number,
            label,
            thought,
            action,
            action_input,
            action_output,
            status,
            input_tokens,
            output_tokens,
            total_tokens,
            error_message,
            started_at,
            ended_at
        )
        SELECT
            id,
            agent_plans_id,
            step_number,
            label,
            thought,
            action,
            action_input,
            action_output,
            status,
            0,
            COALESCE(usage_tokens, 0),
            COALESCE(usage_tokens, 0),
            error_message,
            started_at,
            ended_at
        FROM agent_tasks
        """
    )

    op.execute("DROP TABLE agent_tasks CASCADE")
    op.execute("DROP TABLE agent_plans CASCADE")
    op.execute("DROP TABLE messages CASCADE")
    op.execute("DROP TABLE conversations CASCADE")

    op.execute("ALTER TABLE conversations_new RENAME TO conversations")
    op.execute("ALTER TABLE messages_new RENAME TO messages")
    op.execute("ALTER TABLE agent_plans_new RENAME TO agent_plans")
    op.execute("ALTER TABLE agent_tasks_new RENAME TO agent_tasks")

    op.create_primary_key("conversations_pkey", "conversations", ["id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_primary_key("messages_pkey", "messages", ["id"])
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key("agent_plans_pkey", "agent_plans", ["id"])
    op.create_foreign_key(
        "agent_plans_message_id_fkey",
        "agent_plans",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key("agent_tasks_pkey", "agent_tasks", ["id"])
    op.create_foreign_key(
        "agent_tasks_agent_plans_id_fkey",
        "agent_tasks",
        "agent_plans",
        ["agent_plans_id"],
        ["id"],
        ondelete="CASCADE",
    )

    _create_token_triggers()


def downgrade() -> None:
    _drop_token_triggers()

    op.execute(
        """
        CREATE TABLE conversations_old (
            id UUID NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT,
            usage_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO conversations_old (
            id,
            user_id,
            title,
            summary,
            usage_tokens,
            created_at,
            updated_at
        )
        SELECT
            id,
            user_id,
            title,
            summary,
            COALESCE(total_tokens, 0),
            created_at,
            updated_at
        FROM conversations
        """
    )

    op.execute(
        """
        CREATE TABLE messages_old (
            id UUID NOT NULL,
            conversation_id UUID NOT NULL,
            role VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            status VARCHAR(50),
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            documents_source_url VARCHAR(1024),
            vouchers_source_url VARCHAR(1024),
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO messages_old (
            id,
            conversation_id,
            role,
            content,
            status,
            input_tokens,
            output_tokens,
            documents_source_url,
            vouchers_source_url,
            created_at
        )
        SELECT
            id,
            conversation_id,
            role,
            content,
            status,
            COALESCE(input_tokens, 0),
            COALESCE(output_tokens, 0),
            documents_source_url,
            vouchers_source_url,
            created_at
        FROM messages
        """
    )

    op.execute(
        """
        CREATE TABLE agent_plans_old (
            id UUID NOT NULL,
            message_id UUID NOT NULL,
            raw_plan JSONB NOT NULL,
            total_steps INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
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
            created_at
        )
        SELECT
            id,
            message_id,
            raw_plan,
            total_steps,
            status,
            created_at
        FROM agent_plans
        """
    )

    op.execute(
        """
        CREATE TABLE agent_tasks_old (
            id UUID NOT NULL,
            agent_plans_id UUID NOT NULL,
            step_number INTEGER NOT NULL,
            label VARCHAR(255) NOT NULL,
            thought TEXT NOT NULL,
            action VARCHAR(255),
            action_input TEXT,
            action_output TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            usage_tokens INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            ended_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )
    op.execute(
        """
        INSERT INTO agent_tasks_old (
            id,
            agent_plans_id,
            step_number,
            label,
            thought,
            action,
            action_input,
            action_output,
            status,
            usage_tokens,
            error_message,
            started_at,
            ended_at
        )
        SELECT
            id,
            agent_plans_id,
            step_number,
            label,
            thought,
            action,
            action_input,
            action_output,
            status,
            COALESCE(total_tokens, 0),
            error_message,
            started_at,
            ended_at
        FROM agent_tasks
        """
    )

    op.execute("DROP TABLE agent_tasks CASCADE")
    op.execute("DROP TABLE agent_plans CASCADE")
    op.execute("DROP TABLE messages CASCADE")
    op.execute("DROP TABLE conversations CASCADE")

    op.execute("ALTER TABLE conversations_old RENAME TO conversations")
    op.execute("ALTER TABLE messages_old RENAME TO messages")
    op.execute("ALTER TABLE agent_plans_old RENAME TO agent_plans")
    op.execute("ALTER TABLE agent_tasks_old RENAME TO agent_tasks")

    op.create_primary_key("conversations_pkey", "conversations", ["id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_primary_key("messages_pkey", "messages", ["id"])
    op.create_foreign_key(
        "messages_conversation_id_fkey",
        "messages",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key("agent_plans_pkey", "agent_plans", ["id"])
    op.create_foreign_key(
        "agent_plans_message_id_fkey",
        "agent_plans",
        "messages",
        ["message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_primary_key("agent_tasks_pkey", "agent_tasks", ["id"])
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
        CREATE OR REPLACE FUNCTION refresh_conversation_usage_tokens()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE conversations
                SET usage_tokens = COALESCE((
                    SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                    FROM messages
                    WHERE conversation_id = NEW.conversation_id
                ), 0)
                WHERE id = NEW.conversation_id;
                RETURN NEW;
            ELSIF TG_OP = 'UPDATE' THEN
                UPDATE conversations
                SET usage_tokens = COALESCE((
                    SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                    FROM messages
                    WHERE conversation_id = NEW.conversation_id
                ), 0)
                WHERE id = NEW.conversation_id;

                IF OLD.conversation_id IS DISTINCT FROM NEW.conversation_id THEN
                    UPDATE conversations
                    SET usage_tokens = COALESCE((
                        SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                        FROM messages
                        WHERE conversation_id = OLD.conversation_id
                    ), 0)
                    WHERE id = OLD.conversation_id;
                END IF;
                RETURN NEW;
            ELSE
                UPDATE conversations
                SET usage_tokens = COALESCE((
                    SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                    FROM messages
                    WHERE conversation_id = OLD.conversation_id
                ), 0)
                WHERE id = OLD.conversation_id;
                RETURN OLD;
            END IF;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER messages_refresh_conversation_usage_tokens
        AFTER INSERT OR UPDATE OR DELETE ON messages
        FOR EACH ROW
        EXECUTE FUNCTION refresh_conversation_usage_tokens()
        """
    )


def _create_token_triggers() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sync_detail_total_tokens()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.total_tokens = COALESCE(NEW.input_tokens, 0) + COALESCE(NEW.output_tokens, 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
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
                        SELECT COALESCE(SUM(COALESCE(agent_tasks.input_tokens, 0)), 0)
                        FROM agent_tasks
                        JOIN agent_plans ON agent_plans.id = agent_tasks.agent_plans_id
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
                        SELECT COALESCE(SUM(COALESCE(agent_tasks.output_tokens, 0)), 0)
                        FROM agent_tasks
                        JOIN agent_plans ON agent_plans.id = agent_tasks.agent_plans_id
                        JOIN messages ON messages.id = agent_plans.message_id
                        WHERE messages.conversation_id = p_conversation_id
                    ) AS output_tokens
            ) AS token_totals
            WHERE conversations.id = p_conversation_id;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_conversation_tokens_from_messages()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM refresh_conversation_token_totals(NEW.conversation_id);
                RETURN NEW;
            ELSIF TG_OP = 'UPDATE' THEN
                PERFORM refresh_conversation_token_totals(NEW.conversation_id);
                IF OLD.conversation_id IS DISTINCT FROM NEW.conversation_id THEN
                    PERFORM refresh_conversation_token_totals(OLD.conversation_id);
                END IF;
                RETURN NEW;
            ELSE
                PERFORM refresh_conversation_token_totals(OLD.conversation_id);
                RETURN OLD;
            END IF;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION refresh_conversation_tokens_from_agent_plans()
        RETURNS TRIGGER AS $$
        DECLARE
            new_conversation_id UUID;
            old_conversation_id UUID;
        BEGIN
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                SELECT conversation_id
                INTO new_conversation_id
                FROM messages
                WHERE id = NEW.message_id;

                PERFORM refresh_conversation_token_totals(new_conversation_id);
            END IF;

            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT conversation_id
                INTO old_conversation_id
                FROM messages
                WHERE id = OLD.message_id;

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
        CREATE OR REPLACE FUNCTION refresh_conversation_tokens_from_agent_tasks()
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
                WHERE agent_plans.id = NEW.agent_plans_id;

                PERFORM refresh_conversation_token_totals(new_conversation_id);
            END IF;

            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                SELECT messages.conversation_id
                INTO old_conversation_id
                FROM agent_plans
                JOIN messages ON messages.id = agent_plans.message_id
                WHERE agent_plans.id = OLD.agent_plans_id;

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

    for table_name in ("messages", "agent_plans", "agent_tasks"):
        op.execute(
            f"""
            CREATE TRIGGER {table_name}_sync_detail_total_tokens
            BEFORE INSERT OR UPDATE OF input_tokens, output_tokens ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION sync_detail_total_tokens()
            """
        )

    op.execute(
        """
        CREATE TRIGGER messages_refresh_conversation_token_totals
        AFTER INSERT OR UPDATE OR DELETE ON messages
        FOR EACH ROW
        EXECUTE FUNCTION refresh_conversation_tokens_from_messages()
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
    op.execute(
        """
        SELECT refresh_conversation_token_totals(id)
        FROM conversations
        """
    )


def _drop_token_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS agent_tasks_refresh_conversation_token_totals ON agent_tasks")
    op.execute("DROP TRIGGER IF EXISTS agent_plans_refresh_conversation_token_totals ON agent_plans")
    op.execute("DROP TRIGGER IF EXISTS messages_refresh_conversation_token_totals ON messages")
    op.execute("DROP TRIGGER IF EXISTS agent_tasks_sync_detail_total_tokens ON agent_tasks")
    op.execute("DROP TRIGGER IF EXISTS agent_plans_sync_detail_total_tokens ON agent_plans")
    op.execute("DROP TRIGGER IF EXISTS messages_sync_detail_total_tokens ON messages")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_tokens_from_agent_tasks()")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_tokens_from_agent_plans()")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_tokens_from_messages()")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_token_totals(UUID)")
    op.execute("DROP FUNCTION IF EXISTS sync_detail_total_tokens()")
