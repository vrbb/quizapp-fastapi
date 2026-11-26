"""Importing this package registers every model on Base.metadata."""
from app.models.attempt import Attempt, AttemptAnswer, AttemptStatus
from app.models.notification import Notification, NotificationStatus
from app.models.quiz import Option, Question, Quiz
from app.models.user import User

__all__ = [
    "Attempt",
    "AttemptAnswer",
    "AttemptStatus",
    "Notification",
    "NotificationStatus",
    "Option",
    "Question",
    "Quiz",
    "User",
]
