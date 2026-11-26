"""Attempt endpoints.

The answer key is only ever returned by AttemptResult, which the service builds
exclusively for completed attempts. In-progress views use public question schemas.
"""
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db, get_session_factory
from app.schemas.attempt import (
    AttemptDetail,
    AttemptInProgress,
    AttemptResult,
    AttemptStart,
    AttemptSubmit,
)
from app.schemas.notification import NotificationOut
from app.services import attempt_service, notification_service
from app.services.email_service import EmailSender, get_email_sender

router = APIRouter(prefix="/attempts", tags=["attempts"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=AttemptInProgress,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "User or quiz not found"}},
)
def start_attempt(payload: AttemptStart, db: DbSession):
    """Start a new attempt. Retakes simply start another attempt; history is preserved."""
    return attempt_service.start_attempt(db, payload.user_id, payload.quiz_id)


@router.get(
    "/{attempt_id}",
    response_model=AttemptDetail,
    responses={404: {"description": "Attempt not found"}},
)
def get_attempt(attempt_id: int, db: DbSession):
    """In progress: questions only. Completed: full results with the answer key."""
    return attempt_service.get_attempt_detail(db, attempt_id)


@router.post(
    "/{attempt_id}/submit",
    response_model=AttemptResult,
    responses={
        404: {"description": "Attempt not found"},
        409: {"description": "Attempt already submitted"},
        422: {"description": "Invalid or incomplete answers"},
    },
)
def submit_attempt(
    attempt_id: int,
    payload: AttemptSubmit,
    background_tasks: BackgroundTasks,
    db: DbSession,
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
    email_sender: Annotated[EmailSender, Depends(get_email_sender)],
):
    """Score the attempt (exactly once) and queue the results email.

    The submission is committed before the email is attempted; email delivery
    runs after the response and can never fail this request.
    """
    result, notification_id = attempt_service.submit_attempt(db, attempt_id, payload)
    background_tasks.add_task(
        notification_service.deliver_notification, notification_id, session_factory, email_sender
    )
    return result


@router.get(
    "/{attempt_id}/notification",
    response_model=NotificationOut,
    responses={404: {"description": "Attempt or notification not found"}},
)
def get_attempt_notification(attempt_id: int, db: DbSession):
    attempt_service.get_attempt_detail(db, attempt_id)  # 404 if the attempt does not exist
    return notification_service.get_notification_for_attempt(db, attempt_id)
