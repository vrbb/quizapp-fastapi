from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import NotificationStatus


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_id: int
    recipient_email: str
    status: NotificationStatus
    retry_count: int  # number of failed delivery attempts so far
    next_retry_at: datetime | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
