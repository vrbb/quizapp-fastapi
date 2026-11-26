"""Domain errors raised by services and translated to HTTP responses in one place.

Services stay HTTP-agnostic; routers stay free of try/except boilerplate.
"""
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT


class BusinessRuleError(DomainError):
    """Well-formed request that violates a business rule (e.g. invalid answer set)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
