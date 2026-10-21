"""Rules for when a thread is personal vs shared from roster size."""

from __future__ import annotations


def is_shared_roster(*, agent_count: int, distinct_user_count: int) -> bool:
    """Shared when more than one agent or more than one human participant."""
    return agent_count > 1 or distinct_user_count > 1


def distinct_user_count(*, owner_user_id: int, member_user_ids: list[int] | None) -> int:
    users = {owner_user_id}
    for uid in member_user_ids or []:
        users.add(uid)
    return len(users)
