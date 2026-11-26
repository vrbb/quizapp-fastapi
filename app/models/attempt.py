"""Attempt history: one row per quiz attempt, never updated after completion."""
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Enum, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.notification import Notification
    from app.models.quiz import Option, Question, Quiz
    from app.models.user import User


class AttemptStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint(
            "correct_count IS NULL OR (correct_count >= 0 AND correct_count <= total_questions)",
            name="ck_attempt_score_range",
        ),
        CheckConstraint(
            "percentage IS NULL OR (percentage >= 0 AND percentage <= 100)",
            name="ck_attempt_percentage_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        default=AttemptStatus.IN_PROGRESS,
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)
    # Filled in once, at submission time; stored so history/stats never recompute.
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    correct_count: Mapped[int | None]
    total_questions: Mapped[int | None]
    percentage: Mapped[float | None] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="attempts")
    quiz: Mapped["Quiz"] = relationship()
    answers: Mapped[list["AttemptAnswer"]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )
    notification: Mapped["Notification | None"] = relationship(back_populates="attempt")


class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_answer_attempt_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    selected_option_id: Mapped[int] = mapped_column(ForeignKey("options.id"))
    is_correct: Mapped[bool] = mapped_column(Boolean)

    attempt: Mapped[Attempt] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship()
    selected_option: Mapped["Option"] = relationship()
