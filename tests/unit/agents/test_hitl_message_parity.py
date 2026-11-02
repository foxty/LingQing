"""Keep agents/hitl_message helpers aligned with hitl/utils (harness must not import hitl)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage

from apps.tenant_app_service.agents import hitl_message as harness_hitl
from apps.tenant_app_service.hitl import utils as hitl_utils
from apps.tenant_app_service.hitl.domain import HITL_PAYLOAD_TYPE_APPROVAL_REQUEST


def test_approval_request_payload_constants_match_domain():
    assert harness_hitl.HITL_PAYLOAD_TYPE_APPROVAL_REQUEST == HITL_PAYLOAD_TYPE_APPROVAL_REQUEST


@pytest.mark.parametrize(
    ("payload", "proposal_id"),
    [
        (None, None),
        ({"type": "other"}, None),
        ({"type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST, "proposal_id": "p1"}, None),
        ({"type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST, "proposal_id": "p1"}, "p1"),
        ({"type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST, "proposal_id": "p1"}, "p2"),
    ],
)
def test_is_hitl_approval_request_matches_hitl_utils(payload, proposal_id):
    kwargs = {"hitl": payload} if payload is not None else {}
    message = ToolMessage(content="", tool_call_id=str(uuid4()), additional_kwargs=kwargs)
    assert harness_hitl.is_hitl_approval_request(message, proposal_id) == hitl_utils.is_hitl_approval_request(
        message, proposal_id
    )


def test_get_hitl_payload_matches_hitl_utils():
    payload = {"type": HITL_PAYLOAD_TYPE_APPROVAL_REQUEST, "proposal_id": "x"}
    message = ToolMessage(content="", tool_call_id=str(uuid4()), additional_kwargs={"hitl": payload})
    assert harness_hitl.get_hitl_payload(message) == hitl_utils.get_hitl_payload(message)
