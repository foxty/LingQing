"""Dashboard module for BI dashboard configurations."""

from apps.shared.dashboard.repository import DashboardRepository
from apps.shared.dashboard.schemas import (
    DashboardConfigDTO,
    DashboardCreate,
    DashboardFilterDTO,
    DashboardLayoutDTO,
    DashboardResponse,
    DashboardUpdate,
    DashboardWidgetDTO,
)
from apps.shared.dashboard.service import DashboardService

__all__ = [
    "DashboardCreate",
    "DashboardUpdate",
    "DashboardResponse",
    "DashboardConfigDTO",
    "DashboardLayoutDTO",
    "DashboardWidgetDTO",
    "DashboardFilterDTO",
    "DashboardQueryRequest",
    "DashboardRepository",
    "DashboardService",
]
