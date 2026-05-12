"""Shared result contract for internal system task handlers."""

from dataclasses import dataclass, field
from typing import Any, Literal

SystemTaskOutcome = Literal["success", "partial", "failed"]


@dataclass(frozen=True)
class SystemTaskHandlerResult:
    """Normalized handler result consumed by ScheduledTaskExecutionService."""

    outcome: SystemTaskOutcome
    data: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.outcome == "success"

    def to_payload(self) -> dict[str, Any]:
        payload = dict(self.data)
        payload["outcome"] = self.outcome
        if self.error_message is not None:
            payload["error_message"] = self.error_message
        return payload


def system_task_success(**data: Any) -> SystemTaskHandlerResult:
    return SystemTaskHandlerResult(outcome="success", data=data)


def system_task_partial(error_message: str, **data: Any) -> SystemTaskHandlerResult:
    return SystemTaskHandlerResult(outcome="partial", data=data, error_message=error_message)


def system_task_failed(error_message: str, **data: Any) -> SystemTaskHandlerResult:
    return SystemTaskHandlerResult(outcome="failed", data=data, error_message=error_message)
