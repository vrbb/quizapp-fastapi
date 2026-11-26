"""Attempt schemas.

AttemptInProgress only ever contains public question data. The answer key
(is_correct, correct_option_id, explanation) exists only on AttemptResult, which
the service builds exclusively for completed attempts.
"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import NotificationStatus
from app.schemas.quiz import QuestionPublic

# ---------- Input ----------


class AttemptStart(BaseModel):
    user_id: int = Field(gt=0)
    quiz_id: int = Field(gt=0)


class AnswerIn(BaseModel):
    question_id: int = Field(gt=0)
    option_id: int = Field(gt=0)


class AttemptSubmit(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=100)


# ---------- Output ----------


class AttemptInProgress(BaseModel):
    id: int
    user_id: int
    quiz_id: int
    quiz_title: str
    status: Literal["in_progress"] = "in_progress"
    started_at: datetime
    questions: list[QuestionPublic]


class OptionResult(BaseModel):
    id: int
    text: str
    is_correct: bool


class QuestionResult(BaseModel):
    question_id: int
    position: int
    text: str
    options: list[OptionResult]
    selected_option_id: int
    correct_option_id: int
    is_correct: bool
    explanation: str


class AttemptResult(BaseModel):
    id: int
    user_id: int
    quiz_id: int
    quiz_title: str
    status: Literal["completed"] = "completed"
    started_at: datetime
    completed_at: datetime
    correct_count: int
    total_questions: int
    percentage: float
    performance_message: str
    notification_status: NotificationStatus | None
    questions: list[QuestionResult]


AttemptDetail = Annotated[AttemptInProgress | AttemptResult, Field(discriminator="status")]


class AttemptSummary(BaseModel):
    """History row: score only, no per-question data."""

    id: int
    quiz_id: int
    quiz_title: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    correct_count: int | None
    total_questions: int | None
    percentage: float | None
