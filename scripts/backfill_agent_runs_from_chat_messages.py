#!/usr/bin/env python3
"""Mandatory upgrade step: copy chat_messages sessions into main timeline + agent runs.

The runtime app reads/writes thread_main_messages and agent_run_messages only;
chat_messages is source data for this script (and may remain until a later drop).

Run after migration 079:

    uv run --env-file .env.local scripts/backfill_agent_runs_from_chat_messages.py

Then verify:

    uv run --env-file .env.local scripts/verify_chat_messages_backfill.py

Idempotent per session_id (skips when agent_runs.session_id already exists).
"""

# ruff: noqa: T201

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.config import EnvConfig
from apps.shared.db.url import build_postgres_psycopg2_url
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_BACKFILL_META = {"legacy_backfill": True}


def backfill_chat_messages_to_agent_runs(connection: Connection, *, batch_log_every: int = 500) -> dict[str, int]:
    stats = {"sessions_seen": 0, "sessions_skipped_existing": 0, "sessions_backfilled": 0, "run_messages_copied": 0}

    session_rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT thread_id, session_id
            FROM chat_messages
            WHERE session_id IS NOT NULL AND session_id != ''
            ORDER BY thread_id, session_id
            """
        )
    ).fetchall()

    for thread_id, session_id in session_rows:
        stats["sessions_seen"] += 1
        if stats["sessions_seen"] % batch_log_every == 0:
            logger.info("Backfill progress: %s sessions processed", stats["sessions_seen"])

        existing = connection.execute(
            sa.text("SELECT 1 FROM agent_runs WHERE session_id = :session_id LIMIT 1"),
            {"session_id": session_id},
        ).scalar()
        if existing:
            stats["sessions_skipped_existing"] += 1
            continue

        thread_row = connection.execute(
            sa.text("SELECT tenant_id FROM chat_threads WHERE id = :thread_id"),
            {"thread_id": thread_id},
        ).fetchone()
        if not thread_row:
            continue
        tenant_id = int(thread_row[0])

        msgs = connection.execute(
            sa.text(
                """
                SELECT id, message_id, type, content, agent_id, timestamp, tool_calls,
                       additional_kwargs, message_metadata, created_at, is_summarized
                FROM chat_messages
                WHERE thread_id = :thread_id AND session_id = :session_id
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"thread_id": thread_id, "session_id": session_id},
        ).fetchall()

        human = next((m for m in msgs if m.type == "human"), None)
        if human is None:
            continue

        ai_messages = [m for m in msgs if m.type == "ai"]
        final_ai = ai_messages[-1] if ai_messages else None

        agent_id = human.agent_id or (final_ai.agent_id if final_ai else None)
        if agent_id is None:
            agent_id = connection.execute(
                sa.text("SELECT agent_id FROM chat_threads WHERE id = :thread_id"),
                {"thread_id": thread_id},
            ).scalar()
        if agent_id is None:
            continue

        run_id = str(uuid.uuid4())
        trigger_message_id = human.message_id or f"backfill-human-{human.id}"
        now = datetime.now(UTC)

        human_meta = _merge_json(human.message_metadata, _BACKFILL_META)
        connection.execute(
            sa.text(
                """
                INSERT INTO agent_runs (
                    id, tenant_id, thread_id, agent_id, trigger_message_id, invoke_index,
                    status, session_id, created_at, updated_at, completed_at
                ) VALUES (
                    :id, :tenant_id, :thread_id, :agent_id, :trigger_message_id, 0,
                    'completed', :session_id, :created_at, :updated_at, :completed_at
                )
                """
            ),
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "thread_id": thread_id,
                "agent_id": agent_id,
                "trigger_message_id": trigger_message_id,
                "session_id": session_id,
                "created_at": human.created_at or human.timestamp or now,
                "updated_at": now,
                "completed_at": (final_ai.created_at or final_ai.timestamp) if final_ai else now,
            },
        )

        connection.execute(
            sa.text(
                """
                INSERT INTO thread_main_messages (
                    message_id, thread_id, type, content, agent_id, trigger_message_id,
                    agent_run_id, invoke_index, session_id, timestamp, additional_kwargs,
                    message_metadata, created_at
                ) VALUES (
                    :message_id, :thread_id, 'human', :content, NULL, NULL,
                    NULL, NULL, NULL, :timestamp, CAST(:additional_kwargs AS JSON),
                    CAST(:message_metadata AS JSON), :created_at
                )
                ON CONFLICT (message_id) DO NOTHING
                """
            ),
            {
                "message_id": trigger_message_id,
                "thread_id": thread_id,
                "content": human.content,
                "timestamp": human.timestamp or human.created_at or now,
                "additional_kwargs": _json_or_null(human.additional_kwargs),
                "message_metadata": _json_or_null(human_meta),
                "created_at": human.created_at or human.timestamp or now,
            },
        )

        if final_ai:
            ai_message_id = final_ai.message_id or f"backfill-ai-{final_ai.id}"
            ai_meta = _merge_json(final_ai.message_metadata, _BACKFILL_META)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO thread_main_messages (
                        message_id, thread_id, type, content, agent_id, trigger_message_id,
                        agent_run_id, invoke_index, session_id, timestamp, additional_kwargs,
                        message_metadata, created_at
                    ) VALUES (
                        :message_id, :thread_id, 'ai', :content, :agent_id, :trigger_message_id,
                        :agent_run_id, 0, :session_id, :timestamp, CAST(:additional_kwargs AS JSON),
                        CAST(:message_metadata AS JSON), :created_at
                    )
                    ON CONFLICT (message_id) DO NOTHING
                    """
                ),
                {
                    "message_id": ai_message_id,
                    "thread_id": thread_id,
                    "content": final_ai.content,
                    "agent_id": agent_id,
                    "trigger_message_id": trigger_message_id,
                    "agent_run_id": run_id,
                    "session_id": session_id,
                    "timestamp": final_ai.timestamp or final_ai.created_at or now,
                    "additional_kwargs": _json_or_null(final_ai.additional_kwargs),
                    "message_metadata": _json_or_null(ai_meta),
                    "created_at": final_ai.created_at or final_ai.timestamp or now,
                },
            )

        for msg in msgs:
            if msg.type == "human":
                continue
            run_message_id = msg.message_id or f"backfill-run-{msg.id}"
            connection.execute(
                sa.text(
                    """
                    INSERT INTO agent_run_messages (
                        message_id, run_id, thread_id, type, content, is_summarized,
                        tool_calls, additional_kwargs, session_id, agent_id, timestamp,
                        message_metadata, created_at
                    ) VALUES (
                        :message_id, :run_id, :thread_id, :type, :content, :is_summarized,
                        CAST(:tool_calls AS JSON), CAST(:additional_kwargs AS JSON),
                        :session_id, :agent_id, :timestamp,
                        CAST(:message_metadata AS JSON), :created_at
                    )
                    """
                ),
                {
                    "message_id": run_message_id,
                    "run_id": run_id,
                    "thread_id": thread_id,
                    "type": msg.type,
                    "content": msg.content,
                    "is_summarized": bool(msg.is_summarized),
                    "tool_calls": _json_or_null(msg.tool_calls),
                    "additional_kwargs": _json_or_null(msg.additional_kwargs),
                    "session_id": session_id,
                    "agent_id": msg.agent_id or agent_id,
                    "timestamp": msg.timestamp or msg.created_at or now,
                    "message_metadata": _json_or_null(msg.message_metadata),
                    "created_at": msg.created_at or msg.timestamp or now,
                },
            )
            stats["run_messages_copied"] += 1

        stats["sessions_backfilled"] += 1

    return stats


def _json_or_null(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _merge_json(existing: Any, extra: dict) -> dict:
    base = dict(existing) if isinstance(existing, dict) else {}
    return {**base, **extra}


def main() -> None:
    sync_url = build_postgres_psycopg2_url(
        user=EnvConfig.TENANT_APP_DB_USER,
        password=EnvConfig.TENANT_APP_DB_PASSWORD,
        host=EnvConfig.TENANT_APP_DB_HOST,
        port=EnvConfig.TENANT_APP_DB_PORT,
        db_name=EnvConfig.TENANT_APP_DB_NAME,
        ssl_mode=EnvConfig.TENANT_APP_DB_SSL_MODE or None,
    )
    engine = create_engine(sync_url)
    with engine.connect() as connection:
        with connection.begin():
            stats = backfill_chat_messages_to_agent_runs(connection)
    print(stats)
    logger.info("Backfill stats: %s", stats)


if __name__ == "__main__":
    main()
