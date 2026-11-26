"""Quiz aggregate: Quiz -> Questions -> Options.

Quizzes are immutable once created (no update/delete), so historical attempts
always reference the exact questions they were scored against.
"""
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import UTCDateTime, utc_now


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique title also makes seeding idempotent at the database level.
    title: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz",
        order_by="Question.position",
        cascade="all, delete-orphan",
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("quiz_id", "position", name="uq_question_quiz_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    position: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    options: Mapped[list["Option"]] = relationship(
        back_populates="question",
        order_by="Option.position",
        cascade="all, delete-orphan",
    )


class Option(Base):
    __tablename__ = "options"
    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_option_question_position"),
        # At most one correct option per question, enforced by the database.
        # "At least one" is enforced by input validation (QuizCreate schema).
        Index(
            "uq_option_one_correct_per_question",
            "question_id",
            unique=True,
            sqlite_where=text("is_correct = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    position: Mapped[int]
    text: Mapped[str] = mapped_column(String(500))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)

    question: Mapped[Question] = relationship(back_populates="options")
