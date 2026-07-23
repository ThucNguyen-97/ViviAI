"""Add token usage columns

Revision ID: 7c8d9e0f1a2b
Revises: 2b3d4e5f6a7b
Create Date: 2026-07-18

Rebuild conversations, messages, and agent_tasks to keep logical column order.
Conversation usage is maintained from message token usage by a database trigger.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "7c8d9e0f1a2b"
down_revision: Union[str, None] = "2b3d4e5f6a7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations_new (
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
        INSERT INTO conversations_new (
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
            0,
            0,
            documents_source_url,
            vouchers_source_url,
            created_at
        FROM messages
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
            usage_tokens INTEGER NOT NULL DEFAULT 0,
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
            0,
            error_message,
            started_at,
            ended_at
        FROM agent_tasks
        """
    )

    op.execute("DROP TABLE agent_tasks CASCADE")
    op.execute("DROP TABLE messages CASCADE")
    op.execute("DROP TABLE conversations CASCADE")

    op.execute("ALTER TABLE conversations_new RENAME TO conversations")
    op.execute("ALTER TABLE messages_new RENAME TO messages")
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
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                UPDATE conversations
                SET usage_tokens = COALESCE((
                    SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                    FROM messages
                    WHERE conversation_id = NEW.conversation_id
                ), 0)
                WHERE id = NEW.conversation_id;
            END IF;

            IF TG_OP IN ('UPDATE', 'DELETE') THEN
                UPDATE conversations
                SET usage_tokens = COALESCE((
                    SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0))
                    FROM messages
                    WHERE conversation_id = OLD.conversation_id
                ), 0)
                WHERE id = OLD.conversation_id
                  AND (TG_OP = 'DELETE' OR OLD.conversation_id IS DISTINCT FROM NEW.conversation_id);
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
        CREATE TRIGGER messages_refresh_conversation_usage_tokens
        AFTER INSERT OR UPDATE OR DELETE ON messages
        FOR EACH ROW
        EXECUTE FUNCTION refresh_conversation_usage_tokens()
        """
    )
    op.execute(
        """
        UPDATE conversations
        SET usage_tokens = COALESCE(usage_totals.total_tokens, 0)
        FROM (
            SELECT
                conversation_id,
                SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) AS total_tokens
            FROM messages
            GROUP BY conversation_id
        ) AS usage_totals
        WHERE conversations.id = usage_totals.conversation_id
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS messages_refresh_conversation_usage_tokens ON messages")
    op.execute("DROP FUNCTION IF EXISTS refresh_conversation_usage_tokens()")

    op.execute(
        """
        CREATE TABLE conversations_old (
            id UUID NOT NULL,
            user_id VARCHAR(128) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT,
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
            created_at,
            updated_at
        )
        SELECT
            id,
            user_id,
            title,
            summary,
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
            documents_source_url,
            vouchers_source_url,
            created_at
        FROM messages
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
            error_message,
            started_at,
            ended_at
        FROM agent_tasks
        """
    )

    op.execute("DROP TABLE agent_tasks CASCADE")
    op.execute("DROP TABLE messages CASCADE")
    op.execute("DROP TABLE conversations CASCADE")

    op.execute("ALTER TABLE conversations_old RENAME TO conversations")
    op.execute("ALTER TABLE messages_old RENAME TO messages")
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
