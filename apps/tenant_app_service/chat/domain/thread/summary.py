"""Thread summary aggregate (versioned compression)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.shared.domain.base_domain_model import BaseDomainModel


@dataclass
class ThreadSummaryDomain(BaseDomainModel):
    thread_id: str
    tenant_id: int
    version: int
    summary_content: str
    session_range: dict
    message_range: dict
    session_count: int
    token_count_before: int
    token_count_after: int
    created_at: datetime | None = None
    through_trigger_message_id: str | None = None

    @classmethod
    def create_cumulative(
        cls,
        *,
        thread_id: str,
        tenant_id: int,
        version: int,
        through_trigger_message_id: str,
        summary_content: str,
        session_range: dict,
        message_range: dict,
        session_count: int,
        token_count_before: int,
        token_count_after: int,
    ) -> ThreadSummaryDomain:
        return cls(
            thread_id=thread_id,
            tenant_id=tenant_id,
            version=version,
            summary_content=summary_content,
            session_range=session_range,
            message_range=message_range,
            session_count=session_count,
            token_count_before=token_count_before,
            token_count_after=token_count_after,
            through_trigger_message_id=through_trigger_message_id,
        )

    def get_token_savings(self) -> int:
        return self.token_count_before - self.token_count_after

    def get_compression_ratio(self) -> float:
        if self.token_count_before == 0:
            return 0.0
        return self.token_count_after / self.token_count_before

    def format_token_metrics(self) -> str:
        savings = self.get_token_savings()
        ratio_pct = self.get_compression_ratio() * 100
        if savings >= 0:
            return f"saved {savings} tokens ({ratio_pct:.1f}% of input)"
        return f"expanded by {-savings} tokens ({ratio_pct:.1f}% of input)"
