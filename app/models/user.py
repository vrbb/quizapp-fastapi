from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.common import UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.attempt import Attempt


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now)

    attempts: Mapped[list["Attempt"]] = relationship(back_populates="user")
