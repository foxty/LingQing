"""Slack-specific identity source provisioning."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentIngressEndpoint, ExternalIdentity, IdentitySource
from apps.shared.external_identity.domain import (
    POLICY_REJECT,
    SOURCE_KIND_CHANNEL_WORKSPACE,
    is_slack_tenant_placeholder_source_key,
    slack_workspace_source_key,
)
from apps.shared.external_identity.identity_source_repository import IdentitySourceRepository


class SlackIdentitySourceRepository:
    """Slack workspace identity source lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._sources = IdentitySourceRepository(db)

    async def get_by_id(self, tenant_id: int, source_id: int) -> IdentitySource | None:
        return await self._sources.get_by_id(tenant_id, source_id)

    async def ensure_slack_workspace_source(
        self,
        *,
        tenant_id: int,
        team_id: str | None,
        display_name: str = "Slack",
        bind_policy: str | None = None,
    ) -> IdentitySource:
        if not team_id:
            team_sources = await self.get_slack_team_sources(tenant_id)
            if team_sources:
                return team_sources[0]
            raise ValueError("Slack team_id is required to create a workspace identity source")
        source_key = slack_workspace_source_key(team_id=team_id, tenant_id=tenant_id)
        existing = await self._sources.get_by_source_key(tenant_id, source_key)
        if existing:
            if display_name != "Slack" and existing.display_name != display_name:
                existing.display_name = display_name
                await self.db.flush()
            return existing
        row = IdentitySource(
            tenant_id=tenant_id,
            source_kind=SOURCE_KIND_CHANNEL_WORKSPACE,
            source_key=source_key,
            display_name=display_name,
            bind_policy=bind_policy or POLICY_REJECT,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_slack_team_sources(self, tenant_id: int) -> list[IdentitySource]:
        sources = await self._sources.list_for_tenant(tenant_id)
        return [
            source
            for source in sources
            if source.source_kind == SOURCE_KIND_CHANNEL_WORKSPACE
            and not is_slack_tenant_placeholder_source_key(source.source_key, tenant_id)
        ]

    async def consolidate_slack_tenant_placeholder(
        self,
        *,
        tenant_id: int,
        team_source: IdentitySource,
    ) -> None:
        """Move bindings off slack:tenant:{id} onto the real workspace source and drop the stub."""
        if is_slack_tenant_placeholder_source_key(team_source.source_key, tenant_id):
            return
        placeholder_key = slack_workspace_source_key(team_id=None, tenant_id=tenant_id)
        placeholder = await self._sources.get_by_source_key(tenant_id, placeholder_key)
        if not placeholder or placeholder.id == team_source.id:
            return

        await self.db.execute(
            update(AgentIngressEndpoint)
            .where(
                AgentIngressEndpoint.tenant_id == tenant_id,
                AgentIngressEndpoint.identity_source_id == placeholder.id,
            )
            .values(identity_source_id=team_source.id)
        )
        placeholder_identities = (
            await self.db.execute(
                select(ExternalIdentity).where(
                    ExternalIdentity.tenant_id == tenant_id,
                    ExternalIdentity.identity_source_id == placeholder.id,
                )
            )
        ).scalars().all()
        for identity in placeholder_identities:
            conflict = (
                await self.db.execute(
                    select(ExternalIdentity.id).where(
                        ExternalIdentity.tenant_id == tenant_id,
                        ExternalIdentity.identity_source_id == team_source.id,
                        ExternalIdentity.external_subject == identity.external_subject,
                    )
                )
            ).scalar_one_or_none()
            if conflict is not None:
                await self.db.delete(identity)
            else:
                identity.identity_source_id = team_source.id
        await self.db.flush()
        await self.db.delete(placeholder)
        await self.db.flush()
