"""End-to-end attempt flow: start, submit, results, history, retakes, stats, email."""
import pytest
from sqlalchemy import func, select

from app.models import Attempt, AttemptAnswer, Notification, NotificationStatus, Quiz
from app.services.email_service import get_email_sender
from tests.conftest import FailingEmailSender, collect_keys

ANSWER_KEY_FIELDS = {"is_correct", "explanation", "correct_option_id"}


# ---------- helpers ----------


@pytest.fixture
def user_id(client) -> int:
    return client.post("/users", json={"name": "Ada", "email": "ada@example.com"}).json()["id"]


@pytest.fixture
def quiz(seeded) -> Quiz:
    return seeded.scalar(select(Quiz).order_by(Quiz.id))


def start(client, user_id: int, quiz_id: int) -> dict:
    response = client.post("/attempts", json={"user_id": user_id, "quiz_id": quiz_id})
    assert response.status_code == 201, response.text
    return response.json()


def answers_for(quiz: Quiz, correct: int) -> list[dict]:
    """Answer the first `correct` questions correctly and the rest incorrectly."""
    result = []
    for i, q in enumerate(quiz.questions):
        right = next(o for o in q.options if o.is_correct)
        wrong = next(o for o in q.options if not o.is_correct)
        result.append({"question_id": q.id, "option_id": (right if i < correct else wrong).id})
    return result


def submit(client, attempt_id: int, answers: list[dict]):
    return client.post(f"/attempts/{attempt_id}/submit", json={"answers": answers})


# ---------- start ----------


def test_start_attempt_returns_questions_without_answer_key(client, user_id, quiz):
    body = start(client, user_id, quiz.id)

    assert body["status"] == "in_progress"
    assert body["quiz_title"] == quiz.title
    assert len(body["questions"]) == 5
    assert not ANSWER_KEY_FIELDS & collect_keys(body)


def test_get_in_progress_attempt_does_not_expose_answer_key(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]

    body = client.get(f"/attempts/{attempt_id}").json()

    assert body["status"] == "in_progress"
    assert not ANSWER_KEY_FIELDS & collect_keys(body)


def test_public_quiz_endpoints_never_expose_answer_key(client, seeded):
    for summary in client.get("/quizzes").json():
        assert not ANSWER_KEY_FIELDS & collect_keys(summary)
        assert not ANSWER_KEY_FIELDS & collect_keys(client.get(f"/quizzes/{summary['id']}").json())


@pytest.mark.parametrize(("user", "quiz_id"), [(999, 1), (None, 999)])
def test_start_attempt_unknown_user_or_quiz(client, user_id, seeded, user, quiz_id):
    response = client.post("/attempts", json={"user_id": user or user_id, "quiz_id": quiz_id})
    assert response.status_code == 404


def test_get_unknown_attempt(client):
    assert client.get("/attempts/999").status_code == 404
    assert submit(client, 999, [{"question_id": 1, "option_id": 1}]).status_code == 404


# ---------- submit & scoring ----------


def test_submit_scores_and_returns_full_breakdown(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]

    response = submit(client, attempt_id, answers_for(quiz, correct=4))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert (body["correct_count"], body["total_questions"], body["percentage"]) == (4, 5, 80.0)
    assert body["performance_message"].startswith("Great job")
    assert [q["is_correct"] for q in body["questions"]] == [True, True, True, True, False]
    for q_result, q in zip(body["questions"], quiz.questions):
        assert q_result["explanation"] == q.explanation
        assert q_result["correct_option_id"] == next(o.id for o in q.options if o.is_correct)
    assert body["completed_at"] is not None


@pytest.mark.parametrize(
    ("correct", "percentage", "message"),
    [(5, 100.0, "Perfect score"), (3, 60.0, "Good effort"), (0, 0.0, "Keep practicing")],
)
def test_submit_score_and_message_variants(client, user_id, quiz, correct, percentage, message):
    attempt_id = start(client, user_id, quiz.id)["id"]

    body = submit(client, attempt_id, answers_for(quiz, correct)).json()

    assert body["percentage"] == percentage
    assert body["correct_count"] == correct
    assert body["performance_message"].startswith(message)


def test_answer_order_does_not_matter(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]

    body = submit(client, attempt_id, list(reversed(answers_for(quiz, correct=5)))).json()

    assert body["correct_count"] == 5


def test_completed_attempt_detail_shows_results(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]
    submitted = submit(client, attempt_id, answers_for(quiz, correct=2)).json()

    detail = client.get(f"/attempts/{attempt_id}").json()

    assert detail["status"] == "completed"
    assert detail["percentage"] == 40.0
    assert detail["questions"] == submitted["questions"]


# ---------- invalid submissions ----------


def test_missing_answers_rejected(client, user_id, quiz, db):
    attempt_id = start(client, user_id, quiz.id)["id"]

    response = submit(client, attempt_id, answers_for(quiz, 5)[:4])

    assert response.status_code == 422
    assert "missing" in response.json()["detail"]
    assert client.get(f"/attempts/{attempt_id}").json()["status"] == "in_progress"


def test_duplicate_question_rejected(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]
    answers = answers_for(quiz, 5)
    answers[1] = dict(answers[0])

    assert submit(client, attempt_id, answers).status_code == 422


def test_option_from_another_question_rejected(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]
    answers = answers_for(quiz, 5)
    answers[0]["option_id"] = quiz.questions[1].options[0].id

    response = submit(client, attempt_id, answers)

    assert response.status_code == 422
    assert "does not belong" in response.json()["detail"]


def test_question_from_another_quiz_rejected(client, user_id, quiz, seeded):
    other = seeded.scalar(select(Quiz).where(Quiz.id != quiz.id))
    attempt_id = start(client, user_id, quiz.id)["id"]
    answers = answers_for(quiz, 5) + [answers_for(other, 1)[0]]

    assert submit(client, attempt_id, answers).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [{}, {"answers": []}, {"answers": [{"question_id": "x", "option_id": 1}]}, {"answers": [{"question_id": 0, "option_id": 1}]}],
)
def test_malformed_submission_rejected(client, user_id, quiz, payload):
    attempt_id = start(client, user_id, quiz.id)["id"]
    assert client.post(f"/attempts/{attempt_id}/submit", json=payload).status_code == 422


def test_invalid_submission_errors_do_not_leak_correctness(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]
    answers = answers_for(quiz, 5)
    answers[0]["option_id"] = 999999

    detail = submit(client, attempt_id, answers).json()["detail"]

    assert "correct" not in detail.lower()


# ---------- duplicate submission ----------


def test_duplicate_submission_is_rejected_and_score_preserved(client, user_id, quiz, db, email_sender):
    attempt_id = start(client, user_id, quiz.id)["id"]
    first = submit(client, attempt_id, answers_for(quiz, correct=2))

    second = submit(client, attempt_id, answers_for(quiz, correct=5))

    assert first.status_code == 200
    assert second.status_code == 409
    assert client.get(f"/attempts/{attempt_id}").json()["correct_count"] == 2
    assert db.scalar(select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt_id)) == 5
    assert db.scalar(select(func.count(Notification.id)).where(Notification.attempt_id == attempt_id)) == 1
    assert len(email_sender.sent) == 1


def test_conditional_update_blocks_concurrent_double_submit(client, user_id, quiz, session_factory):
    """Simulate a race: the attempt is completed by another request after our
    status check but before our update. The guarded UPDATE must reject it."""
    from app.schemas.attempt import AttemptSubmit
    from app.services import attempt_service
    from app.services.attempt_service import AttemptAlreadySubmittedError

    attempt_id = start(client, user_id, quiz.id)["id"]
    payload = AttemptSubmit(answers=answers_for(quiz, 5))

    with session_factory() as racer, session_factory() as loser:
        attempt_service._load_attempt(loser, attempt_id)  # loser sees in_progress
        attempt_service.submit_attempt(racer, attempt_id, payload)

        original_load = attempt_service._load_attempt
        stale = {"done": False}

        def stale_load(db, aid):
            # First load returns the stale in-progress snapshot (as if read before the racer committed)
            attempt = original_load(db, aid)
            if not stale["done"]:
                stale["done"] = True
                from app.models import AttemptStatus

                attempt.status = AttemptStatus.IN_PROGRESS
            return attempt

        attempt_service._load_attempt = stale_load
        try:
            with pytest.raises(AttemptAlreadySubmittedError):
                attempt_service.submit_attempt(loser, attempt_id, payload)
        finally:
            attempt_service._load_attempt = original_load

    with session_factory() as s:
        assert s.scalar(select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt_id)) == 5


# ---------- history & retakes ----------


def test_retake_creates_new_attempt_and_preserves_previous(client, user_id, quiz):
    first_id = start(client, user_id, quiz.id)["id"]
    submit(client, first_id, answers_for(quiz, correct=1))
    second_id = start(client, user_id, quiz.id)["id"]
    submit(client, second_id, answers_for(quiz, correct=5))

    assert first_id != second_id
    assert client.get(f"/attempts/{first_id}").json()["correct_count"] == 1
    assert client.get(f"/attempts/{second_id}").json()["correct_count"] == 5

    history = client.get(f"/users/{user_id}/attempts").json()
    assert [h["id"] for h in history] == [second_id, first_id]  # newest first
    assert [h["percentage"] for h in history] == [100.0, 20.0]
    assert not ANSWER_KEY_FIELDS & collect_keys(history)


def test_history_includes_in_progress_attempts(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]

    history = client.get(f"/users/{user_id}/attempts").json()

    assert history[0]["id"] == attempt_id
    assert history[0]["status"] == "in_progress"
    assert history[0]["percentage"] is None


def test_user_stats(client, user_id, quiz, seeded):
    other = seeded.scalar(select(Quiz).where(Quiz.id != quiz.id))
    for correct in (2, 4):
        submit(client, start(client, user_id, quiz.id)["id"], answers_for(quiz, correct))
    submit(client, start(client, user_id, other.id)["id"], answers_for(other, 5))
    start(client, user_id, other.id)  # in progress: excluded from averages

    stats = client.get(f"/users/{user_id}/stats").json()

    assert stats["total_attempts"] == 4
    assert stats["completed_attempts"] == 3
    assert stats["in_progress_attempts"] == 1
    assert stats["average_percentage"] == round((40 + 80 + 100) / 3, 2)
    assert stats["best_percentage"] == 100.0
    assert stats["total_correct_answers"] == 11
    assert stats["total_questions_answered"] == 15
    per_quiz = {q["quiz_id"]: q for q in stats["per_quiz"]}
    assert per_quiz[quiz.id]["completed_attempts"] == 2
    assert per_quiz[quiz.id]["average_percentage"] == 60.0
    assert per_quiz[quiz.id]["best_percentage"] == 80.0
    assert per_quiz[other.id]["completed_attempts"] == 1


# ---------- notifications through the API ----------


def test_successful_submission_sends_email_in_background(client, user_id, quiz, email_sender):
    attempt_id = start(client, user_id, quiz.id)["id"]

    body = submit(client, attempt_id, answers_for(quiz, 4)).json()

    # Response is produced before the background task runs.
    assert body["notification_status"] == "pending"
    notification = client.get(f"/attempts/{attempt_id}/notification").json()
    assert notification["status"] == "sent"
    assert email_sender.sent[0].data["score"] == "4/5"
    assert email_sender.sent[0].data["user_name"] == "Ada"


def test_email_failure_does_not_break_submission(client, user_id, quiz, db):
    from app.main import app

    failing = FailingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: failing
    attempt_id = start(client, user_id, quiz.id)["id"]

    response = submit(client, attempt_id, answers_for(quiz, 3))

    assert response.status_code == 200
    assert response.json()["correct_count"] == 3
    assert failing.calls == 1
    attempt = client.get(f"/attempts/{attempt_id}").json()
    assert attempt["status"] == "completed"
    assert attempt["correct_count"] == 3
    notification = client.get(f"/attempts/{attempt_id}/notification").json()
    assert notification["status"] == "pending"  # queued for retry
    assert notification["retry_count"] == 1
    assert notification["last_error"] == "ConnectionError: SMTP server down"
    assert db.get(Attempt, attempt_id).answers  # answers persisted


def test_notification_eventually_marked_failed(client, user_id, quiz, session_factory):
    from datetime import timedelta

    from app.config import settings
    from app.main import app
    from app.models.common import utc_now
    from app.services.notification_service import process_due_notifications

    failing = FailingEmailSender()
    app.dependency_overrides[get_email_sender] = lambda: failing
    attempt_id = start(client, user_id, quiz.id)["id"]
    submit(client, attempt_id, answers_for(quiz, 3))

    now = utc_now()
    for _ in range(settings.notification_max_attempts):
        now += timedelta(hours=1)
        process_due_notifications(session_factory, failing, now=now)

    notification = client.get(f"/attempts/{attempt_id}/notification").json()
    assert notification["status"] == NotificationStatus.FAILED.value
    assert notification["retry_count"] == settings.notification_max_attempts
    assert client.get(f"/attempts/{attempt_id}").json()["status"] == "completed"


def test_notification_404_for_in_progress_attempt(client, user_id, quiz):
    attempt_id = start(client, user_id, quiz.id)["id"]
    assert client.get(f"/attempts/{attempt_id}/notification").status_code == 404
    assert client.get("/attempts/999/notification").status_code == 404
