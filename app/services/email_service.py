"""Mock email delivery. No real email is sent; messages are logged and recorded."""
import logging
import random
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """Raised when the (mock) email provider fails to deliver a message."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)  # structured payload, handy for tests/logs


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Deliver the message or raise an exception."""


class MockEmailSender:
    """Logs emails instead of sending them; can simulate provider failures.

    failure_rate: probability in [0, 1] that a send raises EmailDeliveryError.
    """

    def __init__(self, failure_rate: float = 0.0, rng: random.Random | None = None) -> None:
        if not 0 <= failure_rate <= 1:
            raise ValueError("failure_rate must be between 0 and 1")
        self.failure_rate = failure_rate
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        # Bounded so a long-running server does not grow memory without limit.
        self.sent: deque[EmailMessage] = deque(maxlen=1000)

    def send(self, message: EmailMessage) -> None:
        if self._rng.random() < self.failure_rate:
            raise EmailDeliveryError("Mock email provider unavailable")
        with self._lock:
            self.sent.append(message)
        logger.info("[MOCK EMAIL] to=%s subject=%r", message.to, message.subject)


_default_sender = MockEmailSender(failure_rate=settings.email_failure_rate)


def get_email_sender() -> EmailSender:
    """FastAPI dependency; overridden in tests to inject failing/recording senders."""
    return _default_sender
