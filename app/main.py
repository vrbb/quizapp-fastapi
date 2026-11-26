"""FastAPI application factory and lifespan."""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import SessionLocal, init_db
from app.exceptions import register_exception_handlers
from app.routers import quizzes
from app.seed import seed_quizzes

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    logger.info("Database initialised at %s", settings.database_url)
    with SessionLocal() as db:
        seed_quizzes(db)
    # The notification retry worker is added in a later step.
    yield


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    @application.get("/", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "message": f"{settings.app_name} is running"}

    register_exception_handlers(application)
    application.include_router(quizzes.router)
    # Users and attempts routers are registered in later steps.
    return application


app = create_app()
