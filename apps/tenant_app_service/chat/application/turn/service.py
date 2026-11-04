"""Session-scoped chat turn use case — composed from prepare / stream / complete mixins."""

from __future__ import annotations

from apps.tenant_app_service.chat.application.turn.base import ChatTurnBaseMixin
from apps.tenant_app_service.chat.application.turn.prepare_complete import ChatTurnPrepareCompleteMixin
from apps.tenant_app_service.chat.application.turn.runtime import ChatTurnRuntimeMixin
from apps.tenant_app_service.chat.application.turn.session import ChatTurnSessionMixin
from apps.tenant_app_service.chat.application.turn.stream import ChatTurnStreamMixin
from apps.tenant_app_service.chat.service_base import ChatServiceBase


class ChatTurnService(
    ChatTurnBaseMixin,
    ChatTurnRuntimeMixin,
    ChatTurnSessionMixin,
    ChatTurnStreamMixin,
    ChatTurnPrepareCompleteMixin,
    ChatServiceBase,
):
    """Prepare, invoke, and complete agent turns within one database session."""
