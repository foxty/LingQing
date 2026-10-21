"""Thread kind inference from roster counts."""

from apps.tenant_app_service.chat.thread_roster_rules import (
    distinct_user_count,
    is_shared_roster,
)


def test_personal_roster_one_user_one_agent():
    assert is_shared_roster(agent_count=1, distinct_user_count=1) is False


def test_shared_roster_multiple_agents():
    assert is_shared_roster(agent_count=2, distinct_user_count=1) is True


def test_shared_roster_multiple_users():
    assert is_shared_roster(agent_count=1, distinct_user_count=2) is True


def test_distinct_user_count_includes_owner():
    assert distinct_user_count(owner_user_id=10, member_user_ids=[10, 20]) == 2
