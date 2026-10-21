"""Room message dedupe by external key."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat import room_message_service as svc


def _author() -> UserDTO:
    return UserDTO(
        id=3,
        username="alice",
        email="a@example.com",
        role="member",
        tenant_id=1,
        tenant_name="t",
    )


@pytest.mark.asyncio
async def test_persist_room_message_returns_existing_on_dedupe_key(monkeypatch):
    db = MagicMock()
    thread = MagicMock(tenant_id=1, thread_kind="shared", agent_id=9, id="1_shared_x")
    existing = MagicMock(message_id="slack_passive_123.456")

    monkeypatch.setattr(svc, "require_write_thread", AsyncMock(return_value=thread))

    scalar = MagicMock()
    scalar.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=scalar)

    row = await svc.persist_room_message(
        db,
        tenant_id=1,
        thread_id="1_shared_x",
        author=_author(),
        content="hello",
        external_dedupe_key="slack_passive_123.456",
    )
    assert row is existing
