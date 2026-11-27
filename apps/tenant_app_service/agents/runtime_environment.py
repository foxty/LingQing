"""Ephemeral LLM context: current time and user locale for agent runs."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.tenant_app_service.agents.domain import AgentRuntimeContext

DEFAULT_TIMEZONE_IANA = "UTC"


def resolve_effective_timezone(timezone_iana: str | None) -> str:
    """Return a valid IANA zone name, falling back to UTC."""
    candidate = (timezone_iana or "").strip() or DEFAULT_TIMEZONE_IANA
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE_IANA
    return candidate


def build_runtime_environment_message(
    runtime: AgentRuntimeContext,
    *,
    now: datetime | None = None,
) -> str:
    """Build markdown system content with clock and user context for one LLM turn."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    else:
        instant = instant.astimezone(UTC)

    timezone_iana = resolve_effective_timezone(runtime.user.timezone_iana)
    local = instant.astimezone(ZoneInfo(timezone_iana))
    local_date = local.date().isoformat()

    user = runtime.user
    lines = [
        "## Runtime environment",
        f"- now_utc: {instant.isoformat()}",
        f"- timezone_iana: {timezone_iana}",
        f"- now_local: {local.isoformat()}",
        f"- local_calendar_date: {local_date}",
        f"- user: {user.username} (id={user.user_id}, role={user.role})",
        f"- tenant: {user.tenant_name} (id={user.tenant_id})",
        "- For relative dates (today, yesterday, this week), use local_calendar_date and now_local above.",
        "- Prefer this block over conversation memory or sandbox `date` when resolving the current time.",
        "- Interpret user-mentioned times in timezone_iana unless the user explicitly names another zone.",
        "- For cron scheduling, cron fields are local time in timezone_iana (do NOT convert cron fields to UTC manually).",
    ]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_TIMEZONE_IANA",
    "build_runtime_environment_message",
    "resolve_effective_timezone",
]