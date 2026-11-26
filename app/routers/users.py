from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.attempt import AttemptSummary
from app.schemas.stats import UserStats
from app.schemas.user import UserCreate, UserOut
from app.services import attempt_service, stats_service, user_service

router = APIRouter(prefix="/users", tags=["users"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email already registered"}},
)
def create_user(payload: UserCreate, db: DbSession):
    return user_service.create_user(db, payload)


@router.get("/{user_id}", response_model=UserOut, responses={404: {"description": "User not found"}})
def get_user(user_id: int, db: DbSession):
    return user_service.get_user(db, user_id)


@router.get(
    "/{user_id}/attempts",
    response_model=list[AttemptSummary],
    responses={404: {"description": "User not found"}},
)
def list_user_attempts(
    user_id: int,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Attempt history, newest first. Every attempt (including retakes) is kept."""
    return attempt_service.list_user_attempts(db, user_id, limit=limit, offset=offset)


@router.get("/{user_id}/stats", response_model=UserStats, responses={404: {"description": "User not found"}})
def get_user_stats(user_id: int, db: DbSession):
    return stats_service.get_user_stats(db, user_id)
