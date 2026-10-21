"""Roster agent resolution from message text."""

from types import SimpleNamespace

from apps.tenant_app_service.chat.roster_agent_resolve import resolve_agent_id_from_roster


def test_empty_roster_falls_back_to_endpoint_agent():
    assert (
        resolve_agent_id_from_roster(roster=[], endpoint_agent_id=42, message_text="hello") == 42
    )


def test_single_roster_entry_wins():
    roster = [SimpleNamespace(agent_id=7, display_alias=None)]
    assert (
        resolve_agent_id_from_roster(roster=roster, endpoint_agent_id=42, message_text="hi") == 7
    )


def test_multi_roster_requires_unique_alias_match():
    roster = [
        SimpleNamespace(agent_id=1, display_alias="Analyst"),
        SimpleNamespace(agent_id=2, display_alias="Writer"),
    ]
    assert (
        resolve_agent_id_from_roster(
            roster=roster, endpoint_agent_id=99, message_text="please ask Analyst to summarize"
        )
        == 1
    )
    assert (
        resolve_agent_id_from_roster(roster=roster, endpoint_agent_id=99, message_text="no tag here")
        is None
    )
