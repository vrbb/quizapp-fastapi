"""Attempt lifecycle: start -> submit (exactly once) -> results.

Answer-key exposure rule: build_attempt_result() is the only function that reads
is_correct/explanation for clients, and it refuses attempts that are not completed.
"""
from collections import Counter

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models import (
    Attempt,
    AttemptAnswer,
    AttemptStatus,
    Notification,
    Question,
    Quiz,
)
from app.models.common import utc_now
from app.schemas.attempt import (
    AttemptInProgress,
    AttemptResult,
    AttemptSubmit,
    AttemptSummary,
    OptionResult,
    QuestionResult,
)
from app.schemas.quiz import QuestionPublic
from app.services import quiz_service, user_service
from app.services.scoring import performance_message, score_answers


class AttemptNotFoundError(NotFoundError):
    def __init__(self, attempt_id: int) -> None:
        super().__init__(f"Attempt {attempt_id} not found")


class AttemptAlreadySubmittedError(ConflictError):
    def __init__(self, attempt_id: int) -> None:
        super().__init__(f"Attempt {attempt_id} has already been submitted")


class InvalidSubmissionError(BusinessRuleError):
    pass


# ---------- Loading ----------


def _load_attempt(db: Session, attempt_id: int) -> Attempt:
    attempt = db.scalar(
        select(Attempt)
        .where(Attempt.id == attempt_id)
        .options(
            selectinload(Attempt.quiz).selectinload(Quiz.questions).selectinload(Question.options),
            selectinload(Attempt.answers),
            selectinload(Attempt.notification),
            selectinload(Attempt.user),
        )
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise AttemptNotFoundError(attempt_id)
    return attempt


# ---------- Views ----------


def build_in_progress_view(attempt: Attempt) -> AttemptInProgress:
    return AttemptInProgress(
        id=attempt.id,
        user_id=attempt.user_id,
        quiz_id=attempt.quiz_id,
        quiz_title=attempt.quiz.title,
        started_at=attempt.started_at,
        questions=[QuestionPublic.model_validate(q) for q in attempt.quiz.questions],
    )


def build_attempt_result(attempt: Attempt) -> AttemptResult:
    if attempt.status != AttemptStatus.COMPLETED:
        # Defensive: never reveal the answer key for an unfinished attempt.
        raise ConflictError(f"Attempt {attempt.id} is not completed")

    answers = {a.question_id: a for a in attempt.answers}
    questions = []
    for q in attempt.quiz.questions:
        answer = answers[q.id]
        correct_option = next(o for o in q.options if o.is_correct)
        questions.append(
            QuestionResult(
                question_id=q.id,
                position=q.position,
                text=q.text,
                options=[OptionResult(id=o.id, text=o.text, is_correct=o.is_correct) for o in q.options],
                selected_option_id=answer.selected_option_id,
                correct_option_id=correct_option.id,
                is_correct=answer.is_correct,
                explanation=q.explanation,
            )
        )
    return AttemptResult(
        id=attempt.id,
        user_id=attempt.user_id,
        quiz_id=attempt.quiz_id,
        quiz_title=attempt.quiz.title,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        correct_count=attempt.correct_count,
        total_questions=attempt.total_questions,
        percentage=attempt.percentage,
        performance_message=performance_message(attempt.percentage),
        notification_status=attempt.notification.status if attempt.notification else None,
        questions=questions,
    )


def get_attempt_detail(db: Session, attempt_id: int) -> AttemptInProgress | AttemptResult:
    attempt = _load_attempt(db, attempt_id)
    if attempt.status == AttemptStatus.COMPLETED:
        return build_attempt_result(attempt)
    return build_in_progress_view(attempt)


# ---------- Commands ----------


def start_attempt(db: Session, user_id: int, quiz_id: int) -> AttemptInProgress:
    """Always creates a NEW attempt, so retakes never touch earlier attempts."""
    user_service.get_user(db, user_id)
    quiz_service.get_quiz(db, quiz_id)
    attempt = Attempt(user_id=user_id, quiz_id=quiz_id, status=AttemptStatus.IN_PROGRESS)
    db.add(attempt)
    db.commit()
    return build_in_progress_view(_load_attempt(db, attempt.id))


def _validate_submission(quiz: Quiz, submission: AttemptSubmit) -> dict[int, int]:
    """Return question_id -> option_id, or raise InvalidSubmissionError.

    Messages only reference IDs and membership, never correctness.
    """
    counts = Counter(a.question_id for a in submission.answers)
    duplicates = sorted(qid for qid, n in counts.items() if n > 1)
    if duplicates:
        raise InvalidSubmissionError(f"Duplicate answers for question(s): {duplicates}")

    options_by_question = {q.id: {o.id for o in q.options} for q in quiz.questions}
    selected = {a.question_id: a.option_id for a in submission.answers}

    unknown = sorted(set(selected) - set(options_by_question))
    if unknown:
        raise InvalidSubmissionError(f"Question(s) {unknown} do not belong to this quiz")
    missing = sorted(set(options_by_question) - set(selected))
    if missing:
        raise InvalidSubmissionError(f"All questions must be answered; missing question(s): {missing}")
    invalid = sorted(qid for qid, oid in selected.items() if oid not in options_by_question[qid])
    if invalid:
        raise InvalidSubmissionError(f"Selected option does not belong to question(s): {invalid}")
    return selected


def submit_attempt(db: Session, attempt_id: int, submission: AttemptSubmit) -> tuple[AttemptResult, int]:
    """Score and complete an attempt exactly once.

    Returns the result and the id of the queued notification. The answers, score,
    status change and notification row are committed in ONE transaction, so the
    submission is durable before any email work starts.
    """
    attempt = _load_attempt(db, attempt_id)
    if attempt.status == AttemptStatus.COMPLETED:
        raise AttemptAlreadySubmittedError(attempt_id)

    selected = _validate_submission(attempt.quiz, submission)
    answer_key = {q.id: next(o.id for o in q.options if o.is_correct) for q in attempt.quiz.questions}
    score = score_answers(answer_key, selected)

    # Conditional update = optimistic guard against concurrent double submission:
    # only one request can move the attempt out of IN_PROGRESS.
    result = db.execute(
        update(Attempt)
        .where(Attempt.id == attempt_id, Attempt.status == AttemptStatus.IN_PROGRESS)
        .values(
            status=AttemptStatus.COMPLETED,
            completed_at=utc_now(),
            correct_count=score.correct_count,
            total_questions=score.total_questions,
            percentage=score.percentage,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise AttemptAlreadySubmittedError(attempt_id)

    db.add_all(
        AttemptAnswer(
            attempt_id=attempt_id,
            question_id=qid,
            selected_option_id=oid,
            is_correct=score.correctness[qid],
        )
        for qid, oid in selected.items()
    )
    notification = Notification(attempt_id=attempt_id, recipient_email=attempt.user.email)
    db.add(notification)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AttemptAlreadySubmittedError(attempt_id) from None

    return build_attempt_result(_load_attempt(db, attempt_id)), notification.id


# ---------- History ----------


def list_user_attempts(db: Session, user_id: int, limit: int, offset: int) -> list[AttemptSummary]:
    user_service.get_user(db, user_id)
    rows = db.execute(
        select(Attempt, Quiz.title)
        .join(Quiz, Quiz.id == Attempt.quiz_id)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.started_at.desc(), Attempt.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        AttemptSummary(
            id=a.id,
            quiz_id=a.quiz_id,
            quiz_title=title,
            status=a.status.value,
            started_at=a.started_at,
            completed_at=a.completed_at,
            correct_count=a.correct_count,
            total_questions=a.total_questions,
            percentage=a.percentage,
        )
        for a, title in rows
    ]
