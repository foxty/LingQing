"""Chat turn application mixins — composed by ``ChatTurnService``."""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.adapters import db_artifact_to_domain
from apps.tenant_app_service.chat.thread_summary_manager import ThreadSummaryManager


class ChatTurnSessionMixin:
    async def _handle_session_end_async(
        self,
        session_id: str,
        thread_id: str,
        *,
        run_id: str | None = None,
    ) -> None:
        """Handle session end asynchronously.

        Creates session summary and checks if thread summary is needed.
        Works for both streaming and non-streaming modes.
        Statistics (tokens, duration, etc.) are tracked separately by Metrics V3.

        Args:
            session_id: Session ID
            thread_id: Thread ID
            run_id: When set, skip summarization until the agent run is terminal
                (e.g. defer while ``awaiting_hitl`` until approve/reject completes).

        Note:
            Creates its own database session to avoid conflicts with router-level
            session lifecycle. The router session is closed immediately after the
            response is sent, but this background task may still be running.
        """
        try:
            from apps.shared.db.session import app_db_session
            from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
            from apps.tenant_app_service.chat.domain import run_status_allows_thread_rollup

            # Background tasks must use their own session: the router-level session
            # is closed as soon as the response is sent, which may happen before
            # this task finishes.  app_db_session() commits on clean exit and rolls
            # back on any exception.
            async with app_db_session() as db:
                if run_id:
                    run = await ThreadRunService(db, self.tenant_id).get_run(run_id)
                    if run and not run_status_allows_thread_rollup(run.status):
                        self.logger.info(
                            "Deferred thread roll-up for session %s (run %s status=%s)",
                            session_id,
                            run_id,
                            run.status,
                        )
                        return
                # Cumulative thread summary. The manager commits on success.
                # Pairs still inside the reserved main-line tail are not folded in.
                thread_summary_manager = ThreadSummaryManager(db, self.tenant_id)
                thread_summary = await thread_summary_manager.check_and_create_if_needed(thread_id)

                if thread_summary:
                    self.logger.info(f"Created thread summary v{thread_summary.version} for thread {thread_id}")

        except Exception as e:
            self.logger.error(
                f"Failed to handle session end for session {session_id}: {e}",
                exc_info=True,
            )

    async def _inject_message_attachments(
        self,
        lc_messages: list,
        *,
        selected_artifact_ids: list[int] | None = None,
        selected_artifact_id: int | None = None,
        current_user: UserDTO | None = None,
    ) -> list:
        """Inject @mention artifact context for the agent."""
        ids: list[int] = []
        if selected_artifact_ids:
            ids.extend(selected_artifact_ids)
        elif selected_artifact_id is not None:
            ids.append(selected_artifact_id)
        if not ids:
            return lc_messages
        return await self._inject_selected_artifacts(
            lc_messages,
            ids,
            current_user=current_user,
        )

    async def _inject_selected_artifacts(
        self,
        lc_messages: list,
        artifact_ids: list[int],
        *,
        current_user: UserDTO | None,
    ) -> list:
        """Inject artifact continuity context from artifact record ids (not thread-scoped)."""
        if not artifact_ids or current_user is None:
            return lc_messages

        from apps.shared.artifact.access import require_artifact_record_read

        context_lines = [
            "[Context] The user attached the following artifacts to continue working on:",
        ]
        metadata: list[dict] = []

        for artifact_id in artifact_ids:
            try:
                record = await require_artifact_record_read(
                    db=self.db,
                    tenant_id=self.tenant_id,
                    user_id=current_user.id,
                    user_role=current_user.role,
                    artifact_id=artifact_id,
                )
                artifact = db_artifact_to_domain(record)
                context_lines.append(
                    f"- Type: {artifact.artifact_type}, Title: {artifact.title}, "
                    f"Artifact id: {artifact.id}, Resource id: {artifact.resource_id}, "
                    f"URL: {artifact.url or 'n/a'}"
                )
                metadata.append(
                    {
                        "artifact_id": artifact.id,
                        "artifact_type": artifact.artifact_type,
                        "title": artifact.title or "Untitled",
                        "resource_id": artifact.resource_id,
                    }
                )
            except Exception as exc:
                self.logger.warning(
                    "Skipping inaccessible artifact %s for user %s: %s",
                    artifact_id,
                    current_user.id,
                    exc,
                )
                context_lines.append(f"- artifact id={artifact_id}: not accessible")
                metadata.append(
                    {
                        "artifact_id": artifact_id,
                        "artifact_type": "unknown",
                        "title": f"Artifact #{artifact_id}",
                        "inaccessible": True,
                    }
                )

        context_lines.append(
            "Use the tools appropriate to each artifact type to inspect or update the underlying resource."
        )
        lc_messages.insert(0, SystemMessage(content="\n".join(context_lines)))
        self._stamp_attached_artifacts(lc_messages, metadata)
        return lc_messages

    @staticmethod
    def _stamp_attached_artifacts(lc_messages: list, items: list[dict]) -> None:
        if not items:
            return
        chip_payload = [
            {
                "artifact_id": item["artifact_id"],
                "artifact_type": item.get("artifact_type", "unknown"),
                "title": item.get("title", "Untitled"),
                "resource_type": item.get("artifact_type", "unknown"),
                "resource_id": item["artifact_id"],
            }
            for item in items
        ]
        for msg in reversed(lc_messages):
            if isinstance(msg, HumanMessage):
                kwargs = dict(msg.additional_kwargs or {})
                kwargs["attached_artifacts"] = chip_payload
                msg.additional_kwargs = kwargs
                return

    def schedule_session_end(
        self,
        session_id: str,
        thread_id: str | None,
        *,
        run_id: str | None = None,
    ) -> None:
        """Schedule cumulative thread roll-up after a turn completes."""
        if not thread_id:
            return
        asyncio.create_task(
            self._handle_session_end_async(
                session_id=session_id,
                thread_id=thread_id,
                run_id=run_id,
            )
        )
