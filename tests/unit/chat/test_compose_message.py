"""Compose message invoke resolution."""

from types import SimpleNamespace

from apps.tenant_app_service.chat.compose_message import resolve_invoke_agent_ids
from apps.tenant_app_service.chat.thread_kinds import THREAD_KIND_PERSONAL, THREAD_KIND_SHARED


def test_shared_no_agent_mentions_room_only():
    thread = SimpleNamespace(thread_kind=THREAD_KIND_SHARED, agent_id=1)
    assert resolve_invoke_agent_ids(thread=thread, mention_agent_ids=[], roster_agent_ids={1, 2}) == []


def test_shared_two_agent_mentions():
    thread = SimpleNamespace(thread_kind=THREAD_KIND_SHARED, agent_id=1)
    assert resolve_invoke_agent_ids(
        thread=thread, mention_agent_ids=[2, 1, 2], roster_agent_ids={1, 2}
    ) == [2, 1]


def test_personal_defaults_primary():
    thread = SimpleNamespace(thread_kind=THREAD_KIND_PERSONAL, agent_id=5)
    assert resolve_invoke_agent_ids(thread=thread, mention_agent_ids=[], roster_agent_ids={5}) == [5]
