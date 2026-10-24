"""Unit tests for ops backfill script (not runtime app code)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.backfill_agent_runs_from_chat_messages import backfill_chat_messages_to_agent_runs


def test_backfill_skips_when_agent_run_session_exists():
    connection = MagicMock()
    connection.execute.side_effect = [
        MagicMock(fetchall=lambda: [("thread-1", "sess-1")]),
        MagicMock(scalar=lambda: 1),
    ]

    stats = backfill_chat_messages_to_agent_runs(connection)

    assert stats["sessions_seen"] == 1
    assert stats["sessions_skipped_existing"] == 1
    assert stats["sessions_backfilled"] == 0
