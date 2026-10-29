#!/usr/bin/env python3
"""Post-upgrade check: legacy chat_messages sessions are represented on main/run stores.

Exit code 0 when every distinct (thread_id, session_id) in chat_messages has a
matching agent_runs row. Exit code 1 and a sample list otherwise.

    uv run --env-file .env.local scripts/verify_chat_messages_backfill.py
"""

# ruff: noqa: T201

from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.config import EnvConfig
from apps.shared.db.url import build_postgres_psycopg2_url
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

_SAMPLE_LIMIT = 25


def find_unbackfilled_sessions(connection) -> list[tuple[str, str]]:
    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT cm.thread_id, cm.session_id
            FROM chat_messages cm
            WHERE cm.session_id IS NOT NULL AND cm.session_id != ''
              AND NOT EXISTS (
                SELECT 1 FROM agent_runs ar WHERE ar.session_id = cm.session_id
              )
            ORDER BY cm.thread_id, cm.session_id
            LIMIT :limit
            """
        ),
        {"limit": _SAMPLE_LIMIT},
    ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def count_unbackfilled_sessions(connection) -> int:
    return int(
        connection.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT cm.thread_id, cm.session_id
                  FROM chat_messages cm
                  WHERE cm.session_id IS NOT NULL AND cm.session_id != ''
                    AND NOT EXISTS (
                      SELECT 1 FROM agent_runs ar WHERE ar.session_id = cm.session_id
                    )
                ) AS missing
                """
            )
        ).scalar()
        or 0
    )


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
        total = count_unbackfilled_sessions(connection)
        if total == 0:
            print("OK: all chat_messages sessions have agent_runs rows.")
            return

        sample = find_unbackfilled_sessions(connection)
        print(f"FAIL: {total} session(s) in chat_messages without agent_runs (showing up to {_SAMPLE_LIMIT}):")
        for thread_id, session_id in sample:
            print(f"  thread_id={thread_id} session_id={session_id}")
        logger.error("Backfill incomplete: %s sessions missing agent_runs", total)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
