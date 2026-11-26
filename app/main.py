"""FastAPI application factory and lifespan."""
import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import SessionLocal, init_db
from app.exceptions import register_exception_handlers
from app.routers import attempts, quizzes, users
from app.seed import seed_quizzes
from app.services.email_service import get_email_sender
from app.services.notification_service import run_retry_worker

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

    stop = asyncio.Event()
    worker: asyncio.Task | None = None
    if settings.notification_worker_enabled:
        worker = asyncio.create_task(
            run_retry_worker(
                SessionLocal, get_email_sender(), stop, settings.notification_poll_interval_seconds
            )
        )
    try:
        yield
    finally:
        stop.set()
        if worker is not None:
            await worker


def create_app() -> FastAPI:
    application = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    @application.get("/", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "message": f"{settings.app_name} is running"}

    register_exception_handlers(application)
    application.include_router(users.router)
    application.include_router(quizzes.router)
    application.include_router(attempts.router)
    return application


app = create_app()
