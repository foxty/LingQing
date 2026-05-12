"""DTO schemas for notification APIs."""

from datetime import datetime

from pydantic import BaseModel, Field

from apps.shared.notification.domain import NotificationChannelType


class NotificationResponse(BaseModel):
    id: str
    event_type: str
    title: str
    payload: dict
    is_read: bool
    created_at: datetime


class NotificationPreferenceItem(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    channels: list[NotificationChannelType] = Field(default_factory=list)


class NotificationPreferenceUpdateRequest(BaseModel):
    preferences: list[NotificationPreferenceItem]


class NotificationPreferenceResponse(BaseModel):
    event_type: str
    channels: list[NotificationChannelType]
    updated_at: datetime
