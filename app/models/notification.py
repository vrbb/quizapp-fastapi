"""Completion notifications. The table doubles as a durable retry queue."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.attempt import Attempt


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"  # queued or waiting for a retry
    SENT = "sent"
    FAILED = "failed"  # final: retries exhausted


class Notification(Base):
    __tablename__ = "notifications"
    # The retry worker looks up due items by (status, next_retry_at).
    __table_args__ = (Index("ix_notification_due", "status", "next_retry_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), unique=True)
    recipient_email: Mapped[str] = mapped_column(String(254))
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        default=NotificationStatus.PENDING,
    )
    retry_count: Mapped[int] = mapped_column(default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=utc_now)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    attempt: Mapped["Attempt"] = relationship(back_populates="notification")
