"""Async notification workflow: delivery, retry queue, final failure, isolation.

Time is passed explicitly (`now=`) so retry/backoff behaviour is deterministic.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import Attempt, AttemptStatus, Notification, NotificationStatus, Quiz, User
from app.seed import seed_quizzes
from app.services.email_service import MockEmailSender
from app.services.notification_service import (
    build_results_email,
    deliver_notification,
    process_due_notifications,
)
from tests.conftest import FailingEmailSender

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


class FlakySender:
    """Fails the first `failures` calls, then succeeds."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self.sent = []

    def send(self, message) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("provider timeout")
        self.sent.append(message)


@pytest.fixture
def notification_id(db) -> int:
    """A completed attempt (4/5) with a pending notification due at T0."""
    seed_quizzes(db)
    quiz = db.query(Quiz).first()
    user = User(name="Ada Lovelace", email="ada@example.com")
    attempt = Attempt(
        user=user,
        quiz=quiz,
        status=AttemptStatus.COMPLETED,
        started_at=T0 - timedelta(minutes=5),
        completed_at=T0,
        correct_count=4,
        total_questions=5,
        percentage=80.0,
    )
    attempt.notification = Notification(recipient_email=user.email, next_retry_at=T0)
    db.add(attempt)
    db.commit()
    return attempt.notification.id


def load(session_factory, notification_id) -> Notification:
    with session_factory() as s:
        return s.get(Notification, notification_id)


def test_successful_delivery_marks_sent(session_factory, notification_id):
    sender = MockEmailSender()

    status = deliver_notification(notification_id, session_factory, sender, now=T0)

    n = load(session_factory, notification_id)
    assert status == NotificationStatus.SENT
    assert n.status == NotificationStatus.SENT
    assert n.sent_at is not None and n.next_retry_at is None
    assert n.retry_count == 0
    assert len(sender.sent) == 1


def test_email_contains_required_fields(session_factory, notification_id):
    sender = MockEmailSender()
    deliver_notification(notification_id, session_factory, sender, now=T0)

    msg = sender.sent[0]
    assert msg.to == "ada@example.com"
    assert msg.data["user_name"] == "Ada Lovelace"
    assert msg.data["user_email"] == "ada@example.com"
    assert msg.data["quiz_title"]
    assert msg.data["score"] == "4/5"
    assert msg.data["percentage"] == 80.0
    assert msg.data["performance_message"].startswith("Great job")
    assert msg.data["completed_at"] == T0.isoformat()
    for text in ("Ada Lovelace", "ada@example.com", "4/5", "80.00%", "Great job", T0.isoformat()):
        assert text in msg.body


def test_failure_schedules_retry_with_backoff(session_factory, notification_id):
    status = deliver_notification(notification_id, session_factory, FailingEmailSender(), now=T0)

    n = load(session_factory, notification_id)
    assert status == NotificationStatus.PENDING
    assert n.retry_count == 1
    assert n.last_error == "ConnectionError: SMTP server down"
    assert n.next_retry_at == T0 + timedelta(seconds=settings.notification_retry_base_seconds)


def test_retry_not_attempted_before_due(session_factory, notification_id):
    sender = FailingEmailSender()
    deliver_notification(notification_id, session_factory, sender, now=T0)

    processed = process_due_notifications(session_factory, sender, now=T0 + timedelta(seconds=1))

    assert processed == 0
    assert sender.calls == 1


def test_retries_until_max_attempts_then_fails(session_factory, notification_id):
    sender = FailingEmailSender()
    now = T0
    deliver_notification(notification_id, session_factory, sender, now=now)
    for _ in range(10):  # more passes than needed: must stop at max attempts
        now += timedelta(hours=1)
        process_due_notifications(session_factory, sender, now=now)

    n = load(session_factory, notification_id)
    assert n.status == NotificationStatus.FAILED
    assert n.retry_count == settings.notification_max_attempts
    assert sender.calls == settings.notification_max_attempts
    assert n.next_retry_at is None


def test_backoff_is_exponential(session_factory, notification_id):
    sender = FailingEmailSender()
    base = settings.notification_retry_base_seconds
    deliver_notification(notification_id, session_factory, sender, now=T0)
    first_retry = T0 + timedelta(seconds=base)
    process_due_notifications(session_factory, sender, now=first_retry)

    n = load(session_factory, notification_id)
    assert n.retry_count == 2
    assert n.next_retry_at == first_retry + timedelta(seconds=base * 2)


def test_transient_failure_recovers_via_retry_queue(session_factory, notification_id):
    sender = FlakySender(failures=1)
    deliver_notification(notification_id, session_factory, sender, now=T0)

    process_due_notifications(session_factory, sender, now=T0 + timedelta(minutes=1))

    n = load(session_factory, notification_id)
    assert n.status == NotificationStatus.SENT
    assert n.retry_count == 1
    assert n.last_error == "TimeoutError: provider timeout"  # history of the failure is kept
    assert len(sender.sent) == 1


def test_claim_prevents_double_delivery(session_factory, notification_id):
    """Background task and worker racing for the same row: only one may send."""
    sender = FailingEmailSender()

    first = deliver_notification(notification_id, session_factory, sender, now=T0)
    second = deliver_notification(notification_id, session_factory, sender, now=T0)

    assert first == NotificationStatus.PENDING
    assert second is None  # not due any more (rescheduled), so not claimable
    assert sender.calls == 1


def test_sent_notification_is_never_resent(session_factory, notification_id):
    sender = MockEmailSender()
    deliver_notification(notification_id, session_factory, sender, now=T0)

    assert deliver_notification(notification_id, session_factory, sender, now=T0 + timedelta(days=1)) is None
    assert process_due_notifications(session_factory, sender, now=T0 + timedelta(days=1)) == 0
    assert len(sender.sent) == 1


def test_crashed_delivery_is_recovered_after_lease_expires(session_factory, notification_id):
    """Claimed but never finished (process died): the worker picks it up after the lease."""
    from app.services.notification_service import _claim

    with session_factory() as s:
        assert _claim(s, notification_id, T0)

    sender = MockEmailSender()
    assert process_due_notifications(session_factory, sender, now=T0 + timedelta(seconds=1)) == 0
    after_lease = T0 + timedelta(seconds=settings.notification_lease_seconds + 1)
    assert process_due_notifications(session_factory, sender, now=after_lease) == 1
    assert load(session_factory, notification_id).status == NotificationStatus.SENT


def test_delivery_never_raises_on_infrastructure_errors(notification_id):
    def broken_session_factory():
        raise RuntimeError("database unavailable")

    assert deliver_notification(notification_id, broken_session_factory, MockEmailSender(), now=T0) is None
    assert process_due_notifications(broken_session_factory, MockEmailSender(), now=T0) == 0


def test_unknown_notification_is_ignored(session_factory):
    assert deliver_notification(12345, session_factory, MockEmailSender(), now=T0) is None


def test_build_results_email_uses_stored_score(db, notification_id):
    attempt = db.get(Notification, notification_id).attempt
    msg = build_results_email(attempt)
    assert msg.subject == f"Your results: {attempt.quiz.title}"
