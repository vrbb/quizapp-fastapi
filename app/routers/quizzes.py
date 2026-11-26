"""Quiz endpoints. Thin layer: validate input, call the service, shape the response.

Every endpoint declares a *Public response_model, so the answer key
(is_correct, explanation) is filtered out even if the ORM object carries it.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.quiz import QuizCreate, QuizPublic, QuizSummary
from app.services import quiz_service

router = APIRouter(prefix="/quizzes", tags=["quizzes"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[QuizSummary])
def list_quizzes(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[QuizSummary]:
    return quiz_service.list_quizzes(db, limit=limit, offset=offset)


@router.get(
    "/{quiz_id}",
    response_model=QuizPublic,
    responses={404: {"description": "Quiz not found"}},
)
def get_quiz(quiz_id: int, db: DbSession):
    return quiz_service.get_quiz(db, quiz_id)


@router.post(
    "",
    response_model=QuizPublic,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "A quiz with this title already exists"}},
)
def create_quiz(payload: QuizCreate, db: DbSession):
    # The response intentionally uses the public schema: the answer key is
    # write-only through the API and only revealed in completed attempt results.
    return quiz_service.create_quiz(db, payload)
