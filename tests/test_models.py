"""Database-level constraints: these protect data integrity even if service code has a bug."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptStatus,
    Notification,
    NotificationStatus,
    Option,
    Question,
    Quiz,
    User,
)


def make_quiz(title: str = "Quiz") -> Quiz:
    return Quiz(
        title=title,
        questions=[
            Question(
                position=1,
                text="Q1",
                explanation="E1",
                options=[
                    Option(position=1, text="A", is_correct=True),
                    Option(position=2, text="B"),
                ],
            )
        ],
    )


def test_user_email_must_be_unique(db):
    db.add_all([User(name="A", email="a@example.com"), User(name="B", email="a@example.com")])
    with pytest.raises(IntegrityError):
        db.commit()


def test_quiz_title_must_be_unique(db):
    db.add_all([make_quiz("Same"), make_quiz("Same")])
    with pytest.raises(IntegrityError):
        db.commit()


def test_only_one_correct_option_per_question(db):
    quiz = make_quiz()
    quiz.questions[0].options[1].is_correct = True
    db.add(quiz)
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_are_enforced(db):
    db.add(Attempt(user_id=999, quiz_id=999))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_answer_per_question_per_attempt(db):
    quiz = make_quiz()
    user = User(name="U", email="u@example.com")
    attempt = Attempt(user=user, quiz=quiz)
    db.add(attempt)
    db.flush()
    q, opt = quiz.questions[0], quiz.questions[0].options[0]
    attempt.answers.extend(
        [
            AttemptAnswer(question_id=q.id, selected_option_id=opt.id, is_correct=True),
            AttemptAnswer(question_id=q.id, selected_option_id=opt.id, is_correct=True),
        ]
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_attempt_score_cannot_exceed_total(db):
    db.add(Attempt(user=User(name="U", email="u@example.com"), quiz=make_quiz(), correct_count=6, total_questions=5))
    with pytest.raises(IntegrityError):
        db.commit()


def test_retakes_create_separate_attempts(db):
    user, quiz = User(name="U", email="u@example.com"), make_quiz()
    db.add_all([Attempt(user=user, quiz=quiz), Attempt(user=user, quiz=quiz)])
    db.commit()
    assert len(db.scalars(select(Attempt).where(Attempt.user_id == user.id)).all()) == 2


def test_defaults_and_timezone_aware_timestamps(db):
    user, quiz = User(name="U", email="u@example.com"), make_quiz()
    attempt = Attempt(user=user, quiz=quiz)
    attempt.notification = Notification(recipient_email=user.email)
    db.add(attempt)
    db.commit()
    db.expire_all()

    loaded = db.get(Attempt, attempt.id)
    assert loaded.status == AttemptStatus.IN_PROGRESS
    assert loaded.started_at.tzinfo is timezone.utc
    assert loaded.notification.status == NotificationStatus.PENDING
    assert loaded.notification.retry_count == 0


def test_naive_datetimes_are_rejected(db):
    db.add(User(name="U", email="u@example.com", created_at=datetime(2026, 1, 1)))
    with pytest.raises(Exception, match="Naive datetimes"):
        db.commit()
