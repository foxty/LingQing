"""Thread access rules for personal vs shared threads."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.thread_access import (
    can_read_thread,
    can_write_thread,
    require_read_thread,
)
from apps.tenant_app_service.chat.thread_kinds import (
    MEMBER_ROLE_MEMBER,
    MEMBER_ROLE_OWNER,
    MEMBER_ROLE_VIEWER,
    THREAD_KIND_PERSONAL,
    THREAD_KIND_SHARED,
)


def _user(user_id: int = 1, tenant_id: int = 10) -> UserDTO:
    return UserDTO(
        id=user_id,
        username="u",
        email="u@example.com",
        role="member",
        tenant_id=tenant_id,
        tenant_name="t",
    )


@pytest.mark.asyncio
async def test_personal_read_write_owner_only(monkeypatch):
    thread = SimpleNamespace(tenant_id=10, user_id=1, thread_kind=THREAD_KIND_PERSONAL, id="t1")
    db = MagicMock()
    owner = SimpleNamespace(role=MEMBER_ROLE_OWNER)

    repo = MagicMock()
    repo.get_user_member = AsyncMock(side_effect=lambda _tid, uid: owner if uid == 1 else None)
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.thread_access.ThreadMembershipRepository",
        lambda _db: repo,
    )

    assert await can_read_thread(db, thread=thread, user=_user(1))
    assert await can_write_thread(db, thread=thread, user=_user(1))
    assert not await can_read_thread(db, thread=thread, user=_user(2))
    assert not await can_write_thread(db, thread=thread, user=_user(2))


@pytest.mark.asyncio
async def test_shared_write_requires_member_not_viewer(monkeypatch):
    thread = SimpleNamespace(tenant_id=10, user_id=1, thread_kind=THREAD_KIND_SHARED, id="s1")
    db = MagicMock()

    member = SimpleNamespace(role=MEMBER_ROLE_MEMBER)
    viewer = SimpleNamespace(role=MEMBER_ROLE_VIEWER)

    repo = MagicMock()
    repo.get_user_member = AsyncMock(side_effect=lambda _tid, uid: member if uid == 2 else viewer)
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.thread_access.ThreadMembershipRepository",
        lambda _db: repo,
    )

    assert await can_read_thread(db, thread=thread, user=_user(2))
    assert await can_write_thread(db, thread=thread, user=_user(2))
    assert await can_read_thread(db, thread=thread, user=_user(3))
    assert not await can_write_thread(db, thread=thread, user=_user(3))


@pytest.mark.asyncio
async def test_require_read_thread_raises_when_missing(monkeypatch):
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(AuthorizationError):
        await require_read_thread(db, thread_id="missing", user=_user())
