from datetime import datetime

from pydantic import BaseModel


class QuizStats(BaseModel):
    quiz_id: int
    quiz_title: str
    completed_attempts: int
    best_percentage: float
    average_percentage: float
    last_completed_at: datetime


class UserStats(BaseModel):
    user_id: int
    total_attempts: int
    completed_attempts: int
    in_progress_attempts: int
    average_percentage: float | None  # over completed attempts; None if there are none
    best_percentage: float | None
    total_correct_answers: int
    total_questions_answered: int
    per_quiz: list[QuizStats]
