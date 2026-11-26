"""Aggregate user statistics, computed in SQL from stored attempt scores."""
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Attempt, AttemptStatus, Quiz
from app.schemas.stats import QuizStats, UserStats
from app.services import user_service


def get_user_stats(db: Session, user_id: int) -> UserStats:
    user_service.get_user(db, user_id)
    completed = Attempt.status == AttemptStatus.COMPLETED

    totals = db.execute(
        select(
            func.count(Attempt.id),
            func.count(case((completed, 1))),
            func.avg(case((completed, Attempt.percentage))),
            func.max(case((completed, Attempt.percentage))),
            func.coalesce(func.sum(case((completed, Attempt.correct_count))), 0),
            func.coalesce(func.sum(case((completed, Attempt.total_questions))), 0),
        ).where(Attempt.user_id == user_id)
    ).one()
    total, completed_count, avg_pct, best_pct, correct_sum, questions_sum = totals

    per_quiz_rows = db.execute(
        select(
            Attempt.quiz_id,
            Quiz.title,
            func.count(Attempt.id),
            func.max(Attempt.percentage),
            func.avg(Attempt.percentage),
            func.max(Attempt.completed_at),
        )
        .join(Quiz, Quiz.id == Attempt.quiz_id)
        .where(Attempt.user_id == user_id, completed)
        .group_by(Attempt.quiz_id, Quiz.title)
        .order_by(Attempt.quiz_id)
    ).all()

    return UserStats(
        user_id=user_id,
        total_attempts=total,
        completed_attempts=completed_count,
        in_progress_attempts=total - completed_count,
        average_percentage=round(avg_pct, 2) if avg_pct is not None else None,
        best_percentage=best_pct,
        total_correct_answers=correct_sum,
        total_questions_answered=questions_sum,
        per_quiz=[
            QuizStats(
                quiz_id=quiz_id,
                quiz_title=title,
                completed_attempts=count,
                best_percentage=best,
                average_percentage=round(avg, 2),
                last_completed_at=last,
            )
            for quiz_id, title, count, best, avg, last in per_quiz_rows
        ],
    )
