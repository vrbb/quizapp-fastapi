"""Completion-email delivery over a durable, DB-backed retry queue.

Flow
1. submit_attempt() commits a Notification(status=pending, next_retry_at=now)
   in the same transaction as the score, then the router schedules
   deliver_notification() as a FastAPI background task (first try, right after
   the response is sent).
2. On failure, retry_count is incremented and next_retry_at is pushed back with
   exponential backoff; after `notification_max_attempts` failures the status
   becomes FAILED (final).
3. A lightweight worker (started in the app lifespan) calls
   process_due_notifications() periodically to pick up due retries and anything
   left pending by a crash.

Every delivery first *claims* the row with a conditional UPDATE that pushes
next_retry_at forward by a lease, so the background task and the worker can never
send the same notification twice concurrently.

Nothing in this module ever raises to its caller: notification problems must
never affect a quiz submission.
"""
import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.exceptions import NotFoundError
from app.models import Attempt, Notification, NotificationStatus
from app.models.common import utc_now
from app.services.email_service import EmailMessage, EmailSender
from app.services.scoring import performance_message

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class NotificationNotFoundError(NotFoundError):
    def __init__(self, attempt_id: int) -> None:
        super().__init__(f"No notification found for attempt {attempt_id}")


def build_results_email(attempt: Attempt) -> EmailMessage:
    user, quiz = attempt.user, attempt.quiz
    message = performance_message(attempt.percentage)
    completed_at = attempt.completed_at.isoformat()
    data = {
        "user_name": user.name,
        "user_email": user.email,
        "quiz_title": quiz.title,
        "correct_count": attempt.correct_count,
        "total_questions": attempt.total_questions,
        "score": f"{attempt.correct_count}/{attempt.total_questions}",
        "percentage": attempt.percentage,
        "performance_message": message,
        "completed_at": completed_at,
    }
    body = (
        f"Hi {user.name} ({user.email}),\n\n"
        f"You completed the quiz \"{quiz.title}\".\n"
        f"Score: {data['score']} ({attempt.percentage:.2f}%)\n"
        f"{message}\n\n"
        f"Completed at: {completed_at}\n"
    )
    return EmailMessage(to=user.email, subject=f"Your results: {quiz.title}", body=body, data=data)


def retry_delay(failed_attempts: int) -> timedelta:
    """Exponential backoff: base, 2*base, 4*base, ..."""
    return timedelta(seconds=settings.notification_retry_base_seconds * 2 ** (failed_attempts - 1))


def _claim(db: Session, notification_id: int, now: datetime) -> bool:
    result = db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == NotificationStatus.PENDING,
            Notification.next_retry_at <= now,
        )
        .values(next_retry_at=now + timedelta(seconds=settings.notification_lease_seconds))
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount == 1


def deliver_notification(
    notification_id: int,
    session_factory: SessionFactory,
    sender: EmailSender,
    now: datetime | None = None,
) -> NotificationStatus | None:
    """Try to deliver one notification. Returns the new status, or None if it was
    not claimable (already sent/failed, not yet due, or claimed by another worker).
    Never raises."""
    now = now or utc_now()
    try:
        with session_factory() as db:
            if not _claim(db, notification_id, now):
                return None
            notification = db.get(Notification, notification_id, populate_existing=True)
            try:
                sender.send(build_results_email(notification.attempt))
            except Exception as exc:  # any provider error is a delivery failure
                notification.retry_count += 1
                notification.last_error = f"{type(exc).__name__}: {exc}"[:500]
                if notification.retry_count >= settings.notification_max_attempts:
                    notification.status = NotificationStatus.FAILED
                    notification.next_retry_at = None
                    logger.error(
                        "Notification %s failed permanently after %s attempts: %s",
                        notification_id, notification.retry_count, notification.last_error,
                    )
                else:
                    notification.next_retry_at = now + retry_delay(notification.retry_count)
                    logger.warning(
                        "Notification %s failed (attempt %s), retry at %s: %s",
                        notification_id, notification.retry_count,
                        notification.next_retry_at.isoformat(), notification.last_error,
                    )
            else:
                notification.status = NotificationStatus.SENT
                notification.sent_at = utc_now()
                notification.next_retry_at = None
                logger.info("Notification %s sent to %s", notification_id, notification.recipient_email)
            db.commit()
            return notification.status
    except Exception:
        # Infrastructure error (e.g. DB unavailable). The row stays pending and the
        # lease expires, so the worker retries it later.
        logger.exception("Unexpected error while delivering notification %s", notification_id)
        return None


def process_due_notifications(
    session_factory: SessionFactory,
    sender: EmailSender,
    now: datetime | None = None,
    batch_size: int = 50,
) -> int:
    """Deliver every pending notification whose retry time has come. Returns how many
    were attempted. Never raises."""
    now = now or utc_now()
    try:
        with session_factory() as db:
            due_ids = db.scalars(
                select(Notification.id)
                .where(
                    Notification.status == NotificationStatus.PENDING,
                    Notification.next_retry_at <= now,
                )
                .order_by(Notification.next_retry_at)
                .limit(batch_size)
            ).all()
    except Exception:
        logger.exception("Could not query due notifications")
        return 0
    attempted = 0
    for notification_id in due_ids:
        if deliver_notification(notification_id, session_factory, sender, now=now) is not None:
            attempted += 1
    return attempted


async def run_retry_worker(
    session_factory: SessionFactory,
    sender: EmailSender,
    stop: asyncio.Event,
    interval_seconds: float,
) -> None:
    """Background loop started in the app lifespan. Runs DB work in a thread."""
    logger.info("Notification retry worker started (every %ss)", interval_seconds)
    while not stop.is_set():
        await asyncio.to_thread(process_due_notifications, session_factory, sender)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    logger.info("Notification retry worker stopped")


def get_notification_for_attempt(db: Session, attempt_id: int) -> Notification:
    notification = db.scalar(select(Notification).where(Notification.attempt_id == attempt_id))
    if notification is None:
        raise NotificationNotFoundError(attempt_id)
    return notification
