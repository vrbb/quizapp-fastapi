"""Application settings read from environment variables.

A plain frozen dataclass keeps us free of extra dependencies (e.g. pydantic-settings)
while still allowing overrides via env vars in tests or deployments.
"""
import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    app_name: str = "QuizApp"
    database_url: str = os.getenv("QUIZAPP_DATABASE_URL", "sqlite:///./quizapp.db")
    sql_echo: bool = _env_bool("QUIZAPP_SQL_ECHO", False)
    log_level: str = os.getenv("QUIZAPP_LOG_LEVEL", "INFO")

    # Mock email: probability (0..1) that a send fails, to exercise failure handling.
    email_failure_rate: float = float(os.getenv("QUIZAPP_EMAIL_FAILURE_RATE", "0"))

    # Notification retry queue
    notification_max_attempts: int = int(os.getenv("QUIZAPP_NOTIFICATION_MAX_ATTEMPTS", "3"))
    notification_retry_base_seconds: float = float(os.getenv("QUIZAPP_NOTIFICATION_RETRY_BASE_SECONDS", "2"))
    # A claimed notification is invisible to other workers for this long (crash recovery).
    notification_lease_seconds: float = float(os.getenv("QUIZAPP_NOTIFICATION_LEASE_SECONDS", "60"))
    notification_worker_enabled: bool = _env_bool("QUIZAPP_NOTIFICATION_WORKER_ENABLED", True)
    notification_poll_interval_seconds: float = float(os.getenv("QUIZAPP_NOTIFICATION_POLL_SECONDS", "2"))


settings = Settings()
