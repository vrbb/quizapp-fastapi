"""User business logic."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import ConflictError, NotFoundError
from app.models import User
from app.schemas.user import UserCreate


class UserNotFoundError(NotFoundError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} not found")


class EmailAlreadyRegisteredError(ConflictError):
    def __init__(self) -> None:
        super().__init__("A user with this email already exists")


def create_user(db: Session, data: UserCreate) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise EmailAlreadyRegisteredError()
    user = User(name=data.name, email=data.email)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # concurrent registration with the same email
        raise EmailAlreadyRegisteredError() from None
    return user


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    return user
