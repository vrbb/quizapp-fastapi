"""Entry point kept at the project root so `uvicorn main:app` works."""
from app.main import app

__all__ = ["app"]
