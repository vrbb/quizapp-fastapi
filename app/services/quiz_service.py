"""Quiz business logic."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.exceptions import ConflictError, NotFoundError
from app.models import Option, Question, Quiz
from app.schemas.quiz import QuizCreate, QuizSummary


class QuizNotFoundError(NotFoundError):
    def __init__(self, quiz_id: int) -> None:
        super().__init__(f"Quiz {quiz_id} not found")


class QuizAlreadyExistsError(ConflictError):
    def __init__(self, title: str) -> None:
        super().__init__(f"A quiz titled '{title}' already exists")


def get_quiz_by_title(db: Session, title: str) -> Quiz | None:
    return db.scalar(select(Quiz).where(Quiz.title == title))


def list_quizzes(db: Session, limit: int, offset: int) -> list[QuizSummary]:
    question_count = (
        select(func.count(Question.id)).where(Question.quiz_id == Quiz.id).scalar_subquery()
    )
    rows = db.execute(
        select(Quiz, question_count).order_by(Quiz.id).limit(limit).offset(offset)
    ).all()
    return [
        QuizSummary(
            id=quiz.id,
            title=quiz.title,
            description=quiz.description,
            question_count=count,
            created_at=quiz.created_at,
        )
        for quiz, count in rows
    ]


def get_quiz(db: Session, quiz_id: int) -> Quiz:
    """Load a quiz with its questions and options (eagerly, to avoid N+1 queries)."""
    quiz = db.scalar(
        select(Quiz)
        .where(Quiz.id == quiz_id)
        .options(selectinload(Quiz.questions).selectinload(Question.options))
    )
    if quiz is None:
        raise QuizNotFoundError(quiz_id)
    return quiz


def build_quiz(data: QuizCreate) -> Quiz:
    """Map validated input to ORM objects (positions are 1-based, in input order)."""
    return Quiz(
        title=data.title,
        description=data.description,
        questions=[
            Question(
                position=q_pos,
                text=q.text,
                explanation=q.explanation,
                options=[
                    Option(position=o_pos, text=o.text, is_correct=o.is_correct)
                    for o_pos, o in enumerate(q.options, start=1)
                ],
            )
            for q_pos, q in enumerate(data.questions, start=1)
        ],
    )


def create_quiz(db: Session, data: QuizCreate) -> Quiz:
    if get_quiz_by_title(db, data.title) is not None:
        raise QuizAlreadyExistsError(data.title)
    quiz = build_quiz(data)
    db.add(quiz)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request inserted the same title between our check and commit.
        db.rollback()
        raise QuizAlreadyExistsError(data.title) from None
    return get_quiz(db, quiz.id)
