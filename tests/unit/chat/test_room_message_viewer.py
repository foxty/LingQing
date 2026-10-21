"""Room messages require write access (viewers cannot post)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat import room_message_service as svc


def _author() -> UserDTO:
    return UserDTO(
        id=9,
        username="viewer",
        email="v@example.com",
        role="member",
        tenant_id=1,
        tenant_name="t",
    )


@pytest.mark.asyncio
async def test_viewer_cannot_persist_room_message(monkeypatch):
    db = MagicMock()
    thread = MagicMock(tenant_id=1, thread_kind="shared", id="1_shared_x")

    async def _deny_write(*_args, **_kwargs):
        raise AuthorizationError("Access denied")

    monkeypatch.setattr(svc, "require_write_thread", _deny_write)

    with pytest.raises(AuthorizationError):
        await svc.persist_room_message(
            db,
            tenant_id=1,
            thread_id="1_shared_x",
            author=_author(),
            content="hello",
        )
