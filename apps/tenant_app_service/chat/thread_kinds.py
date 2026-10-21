"""Thread kind and message interaction constants."""

from typing import Final, Literal

THREAD_KIND_PERSONAL: Final = "personal"
THREAD_KIND_SHARED: Final = "shared"

ThreadKind = Literal["personal", "shared"]
DEFAULT_THREAD_KIND: ThreadKind = THREAD_KIND_PERSONAL

MEMBER_ROLE_OWNER: Final = "owner"
MEMBER_ROLE_MEMBER: Final = "member"
MEMBER_ROLE_VIEWER: Final = "viewer"

INTERACTION_ROOM_MESSAGE: Final = "room_message"
INTERACTION_AGENT_TURN: Final = "agent_turn"

SOURCE_WORKBENCH: Final = "workbench"
SOURCE_SLACK_PASSIVE: Final = "slack_passive"
