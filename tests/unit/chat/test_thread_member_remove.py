"""Thread member removal service behavior."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.chat.membership_repository import ThreadMembershipRepository
from apps.tenant_app_service.chat.thread_kinds import MEMBER_ROLE_MEMBER, MEMBER_ROLE_OWNER
from apps.tenant_app_service.chat.thread_service import ThreadService


@pytest.mark.asyncio
async def test_remove_user_member_from_thread_rejects_owner(monkeypatch):
    db = AsyncMock()
    db_thread = MagicMock()
    db_thread.id = "thread-1"
    db_thread.user_id = 1
    db.get = AsyncMock(return_value=db_thread)

    membership = AsyncMock(spec=ThreadMembershipRepository)
    owner_row = MagicMock(role=MEMBER_ROLE_OWNER)
    membership.get_user_member = AsyncMock(return_value=owner_row)

    service = ThreadService(tenant_id=1, db=db)
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.thread_service.ThreadMembershipRepository",
        lambda _db: membership,
    )
    monkeypatch.setattr(service, "_is_thread_owner", AsyncMock(return_value=True))

    removed = await service.remove_user_member_from_thread(
        thread_id="thread-1",
        owner_user_id=1,
        user_id=1,
    )
    assert removed is False
    membership.remove_user_member.assert_not_called()


@pytest.mark.asyncio
async def test_remove_user_member_from_thread_deletes_member(monkeypatch):
    db = AsyncMock()
    db_thread = MagicMock()
    db_thread.id = "thread-1"
    db_thread.user_id = 1
    db.get = AsyncMock(return_value=db_thread)

    membership = AsyncMock(spec=ThreadMembershipRepository)
    member_row = MagicMock(role=MEMBER_ROLE_MEMBER)
    membership.get_user_member = AsyncMock(return_value=member_row)
    membership.remove_user_member = AsyncMock(return_value=True)
    membership.list_user_members = AsyncMock(return_value=[MagicMock(), MagicMock()])
    membership.list_agent_members = AsyncMock(return_value=[MagicMock()])

    service = ThreadService(tenant_id=1, db=db)
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.thread_service.ThreadMembershipRepository",
        lambda _db: membership,
    )
    monkeypatch.setattr(service, "_is_thread_owner", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "sync_thread_kind_from_roster", AsyncMock())

    removed = await service.remove_user_member_from_thread(
        thread_id="thread-1",
        owner_user_id=1,
        user_id=2,
    )
    assert removed is True
    membership.remove_user_member.assert_awaited_once_with("thread-1", 2)
