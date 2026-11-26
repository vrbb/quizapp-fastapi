
# CLAUDE.md

## Project Context
This project is a Python FastAPI backend coding challenge for a Quiz Application.

## Development Guidelines

- Use Python with type hints.
- Use FastAPI for REST endpoints.
- Use SQLAlchemy for database persistence.
- Use Pydantic for request and response validation.
- Use pytest for automated tests.
- Follow clean code and separation of concerns.
- Keep business logic inside service modules, not API routers.
- Handle errors explicitly.
- Prefer simple, maintainable solutions over unnecessary complexity.

## Important Business Rules

- Never expose correct answers before quiz submission.
- Preserve all historical quiz attempts.
- Ensure scoring calculations are accurate.
- Notification failures must never break quiz submission.
- Persist notification status.
- Validate all incoming data.

## AI Development Workflow

- Analyze requirements before implementation.
- Explain architectural decisions and trade-offs.
- Implement incrementally.
- Review generated code critically.
- Run tests after important changes.
- Never assume generated code is correct.
