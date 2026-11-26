# QuizApp API

A REST API for taking quizzes on AI development concepts. Users take quizzes, get scored results with per-question explanations, keep a full history of attempts and statistics, and receive a mock results email that is sent asynchronously and retried on failure.

Built with **FastAPI**, **SQLAlchemy 2**, **SQLite**, **Pydantic 2** and **pytest**.

---

## Quick start

Requires Python 3.12+ (developed on 3.15).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --reload
```

- API docs (Swagger UI): http://127.0.0.1:8000/docs
- Health check: `GET /`

On startup the app creates the tables in `quizapp.db` and seeds **2 quizzes with 5 questions each** ("Prompt Engineering Fundamentals" and "AI Agents and Tool Use"). Seeding is idempotent, so restarting never duplicates data. You can also run it manually with `python -m app.seed`.

### Run the tests

```bash
python -m pytest
```

There are 113 tests. Each one runs against a fresh in-memory SQLite database, so your local `quizapp.db` is never touched. Warnings are treated as errors (`pytest.ini`).

### Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `QUIZAPP_DATABASE_URL` | `sqlite:///./quizapp.db` | Database location |
| `QUIZAPP_EMAIL_FAILURE_RATE` | `0` | Probability (0–1) that the mock email fails, for exercising the retry flow |
| `QUIZAPP_NOTIFICATION_MAX_ATTEMPTS` | `3` | Delivery attempts before a notification becomes `failed` |
| `QUIZAPP_NOTIFICATION_RETRY_BASE_SECONDS` | `2` | Base delay for exponential backoff (2s, 4s, …) |
| `QUIZAPP_NOTIFICATION_LEASE_SECONDS` | `60` | How long a claimed notification stays invisible to other workers |
| `QUIZAPP_NOTIFICATION_WORKER_ENABLED` | `true` | Run the background retry worker |
| `QUIZAPP_NOTIFICATION_POLL_SECONDS` | `2` | Retry worker polling interval |
| `QUIZAPP_LOG_LEVEL` / `QUIZAPP_SQL_ECHO` | `INFO` / `false` | Logging |

To watch the email failure handling live:

```bash
# PowerShell: $env:QUIZAPP_EMAIL_FAILURE_RATE="1"; uvicorn main:app
QUIZAPP_EMAIL_FAILURE_RATE=1 uvicorn main:app
```

Submit an attempt, then poll `GET /attempts/{id}/notification`. The status goes `pending` (retries 1 → 2) → `failed`, while the attempt itself stays `completed`.

---

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/users` | Create a user. Email is validated and stored lower-cased; a duplicate returns `409`. |
| `GET` | `/users/{id}` | Get a user |
| `GET` | `/users/{id}/attempts` | Attempt history, newest first (`limit`, `offset`) |
| `GET` | `/users/{id}/stats` | Totals, average and best score, per-quiz breakdown |
| `GET` | `/quizzes` | List quizzes with question counts (`limit`, `offset`) |
| `GET` | `/quizzes/{id}` | Quiz with questions and options. **No answers or explanations.** |
| `POST` | `/quizzes` | Create a quiz with its answer key. The response is the public view. |
| `POST` | `/attempts` | Start an attempt (`user_id`, `quiz_id`). Each call creates a new attempt, so retakes are just new attempts. |
| `GET` | `/attempts/{id}` | In progress: questions only. Completed: full results. |
| `POST` | `/attempts/{id}/submit` | Submit answers for **every** question and get the results |
| `GET` | `/attempts/{id}/notification` | Email status: `pending` / `sent` / `failed`, retry count, last error |

### Example flow

```bash
# 1. Create a user
curl -X POST localhost:8000/users -H "Content-Type: application/json" \
     -d '{"name": "Ada Lovelace", "email": "ada@example.com"}'

# 2. Start an attempt. The response contains the questions and option ids, with no answers.
curl -X POST localhost:8000/attempts -H "Content-Type: application/json" \
     -d '{"user_id": 1, "quiz_id": 1}'

# 3. Submit one answer per question
curl -X POST localhost:8000/attempts/1/submit -H "Content-Type: application/json" \
     -d '{"answers": [{"question_id": 1, "option_id": 2}, {"question_id": 2, "option_id": 5},
                      {"question_id": 3, "option_id": 11}, {"question_id": 4, "option_id": 14},
                      {"question_id": 5, "option_id": 19}]}'
```

The submit response (abridged):

```json
{
  "status": "completed",
  "correct_count": 4,
  "total_questions": 5,
  "percentage": 80.0,
  "performance_message": "Great job! You have a strong understanding of this topic.",
  "notification_status": "pending",
  "questions": [
    {"question_id": 5, "selected_option_id": 19, "correct_option_id": 20,
     "is_correct": false, "explanation": "Prompt injection is when untrusted input ...", "...": "..."}
  ]
}
```

> **Testing in Swagger:** Swagger pre-fills the submit body with `question_id: 0, option_id: 0`, which is rejected with `422` because IDs must be greater than 0. Use the IDs returned by `POST /attempts`, and answer every question.

### Error responses

| Status | When |
|---|---|
| `404` | User, quiz, attempt or notification not found |
| `409` | Duplicate email or quiz title, or an attempt that was already submitted |
| `422` | Invalid input, or an invalid answer set: a missing or duplicate question, a question from another quiz, or an option that doesn't belong to its question |

---

## Architecture

```
app/
  main.py          App factory and lifespan (create tables, seed, start/stop the retry worker)
  config.py        Settings from environment variables (plain dataclass, no extra dependency)
  database.py      Engine, session factory, get_db / get_session_factory dependencies
  exceptions.py    Domain errors mapped to HTTP status codes in one place
  seed.py          Idempotent seed data
  models/          SQLAlchemy models: user, quiz (Quiz/Question/Option), attempt, notification
  schemas/         Pydantic request and response schemas (public vs. result separated)
  routers/         Thin HTTP layer: validate, call a service, return a response
  services/        Business logic: quiz, user, attempt, scoring, stats, notification, email (mock)
tests/             Unit and API tests (pytest + TestClient + in-memory SQLite)
```

The routers contain no business logic. Services raise domain errors (`NotFoundError`, `ConflictError`, `BusinessRuleError`) and never deal with HTTP; a single exception handler turns those errors into HTTP responses.

### Data model

```
User 1──* Attempt *──1 Quiz 1──* Question 1──* Option
            ├─1──* AttemptAnswer   (question_id, selected_option_id, is_correct)
            └─1──1 Notification    (also serves as the retry queue)
```

Key constraints, enforced by the database and not only in code:
- At most one correct option per question (a partial unique index on `options(question_id) WHERE is_correct = 1`). "At least one" is checked by input validation.
- One answer per question per attempt, and one notification per attempt.
- Score ranges are checked: `0 ≤ correct_count ≤ total_questions` and `0 ≤ percentage ≤ 100`.
- Unique user email and unique quiz title. The unique title also guarantees the seed can't insert a quiz twice.
- SQLite foreign-key enforcement is switched on for every connection (SQLite has it off by default).
- All timestamps are timezone-aware UTC. A custom column type restores the timezone, which SQLite drops.

---

## Key design decisions

### 1. The answer key is never exposed before submission
- **Separate schemas.** `OptionPublic` and `QuestionPublic` don't declare `is_correct` or `explanation` at all. Those fields exist only on `AttemptResult`.
- **Every endpoint declares a `response_model`.** FastAPI then filters out undeclared fields even if a database object carrying them is returned by mistake.
- **One gatekeeper.** `build_attempt_result()` is the only code path that reads the answer key for clients, and it refuses attempts that aren't completed.
- **Explanations are hidden too**, because they usually give the answer away.
- **Error messages mention only IDs**, never which answer is correct.
- **Tests guard it.** They walk every key of the JSON returned by each endpoint used before submission. Mutation check: exposing `explanation` makes 7 tests fail.

### 2. Accurate, auditable scoring
- Scoring is a pure function (`services/scoring.py`) with no I/O, unit-tested in isolation, including the performance-message boundaries (100 / 80 / 50).
- The score is always out of **all** questions in the quiz. Every question must be answered, otherwise the API returns `422` and nothing is saved.
- The score and each answer's correctness are **stored at submission time**, so history and stats never recalculate them.
- Quizzes are immutable (no update or delete), so old attempts always point to the questions they were scored against.

### 3. Each attempt is submitted exactly once, and history is preserved
- A retake is a new `Attempt` row; earlier attempts are never modified.
- Duplicate submissions are blocked by four independent layers:
  1. a status check;
  2. an update that only succeeds while the attempt is still `in_progress`, so of two simultaneous submits only one can win;
  3. a unique constraint on (attempt, question) for answers;
  4. a unique constraint on the attempt's notification.

  The second submit gets `409`, and the original score is kept.

### 4. Asynchronous email that can't break a submission
**Approach:** FastAPI `BackgroundTasks` for the first send, plus a retry queue stored in the database.

1. Submission saves the answers, the score, the `completed` status and a `Notification(status=pending)` in **one transaction**. The submission is durable before any email work starts.
2. After the response is sent, a background task tries the first send, using its own database session.
3. A failure increments `retry_count`, stores `last_error` and schedules a retry with exponential backoff. After `MAX_ATTEMPTS` failures the status becomes `failed` (final).
4. A small background worker, started with the app, polls for due retries. It also recovers anything left `pending` after a crash.
5. Before sending, a worker claims the notification for a short time (60 seconds by default), so the background task and the retry worker can never send the same email twice. If a send crashes midway, the claim expires and the retry is automatic.
6. Nothing in the notification path raises an error to its caller.

**Why not Celery or RQ?** They need a broker (Redis or RabbitMQ) and a separate worker process, which is a lot of infrastructure for a mock email. The database-backed queue survives restarts, makes every status visible through the API, and is easy to test: tests pass in explicit timestamps, so retry timing is checked without any sleeps.

The email (mocked and logged) contains the user's name and email, quiz title, score (correct/total), percentage, performance message and completion timestamp.

### 5. Other practices I prioritized
- **Input validation everywhere:** types, lengths, ID > 0, trimmed non-blank strings, email format, and pagination bounds.
- **Race-safe creates:** a duplicate email or title is caught both by a check before inserting and by the database's unique constraint, so two simultaneous requests get `409` instead of `500`.
- **No N+1 queries:** quizzes and attempts are loaded together with their questions and options, and stats are computed with SQL aggregates.
- **Dependency injection for testability:** the database session factory and the email sender are FastAPI dependencies, so tests swap in an in-memory database and failing or recording email senders.
- **Logging** of every notification state change. Only the recipient and subject are logged; the email body is not.

---

## Testing strategy

| File | Covers |
|---|---|
| `test_scoring.py` | Scoring (all, none, partial, rounding) and performance-message boundaries |
| `test_notifications.py` | Async workflow: success, email content, backoff, final failure, recovery after a temporary failure, no double sends, recovery after a crashed send, never raising |
| `test_api_attempts.py` | Full flow, answer-leak checks, invalid submissions, duplicate submits (including a simulated race), retakes, history, stats, email failure not breaking submission |
| `test_api_quizzes.py` | List, get and create; validation; duplicate titles; no answer key in responses |
| `test_api_users.py` | Create and get, email validation and normalization, empty stats |
| `test_models.py` | Database constraints (foreign keys, uniqueness, one correct option, score ranges, UTC) |
| `test_seed.py` / `test_quiz_schemas.py` | Seed requirements and idempotency; schema validation |

The critical tests were **mutation-checked**: I broke the code on purpose and confirmed that the relevant tests fail, for answer leaks, email-error handling and duplicate-submit protection.

---

## What I deliberately left out (and what I'd add next)

| Left out | Why / next step |
|---|---|
| Authentication and authorization | Out of scope for the challenge. Today anyone who knows an ID can read any user's attempts. Next: JWT or OAuth2, plus ownership checks on `/users/{id}/*` and `/attempts/{id}`. |
| Database migrations | `create_all` on startup is enough for SQLite in a challenge. Next: Alembic. |
| Message broker | A single process with a database queue is enough here. With multiple instances: Celery or RQ, or `SELECT … FOR UPDATE SKIP LOCKED` on Postgres. |
| Quiz editing and versioning | Quizzes are immutable to keep history consistent. Editing would need quiz versions. |
| Multiple-answer questions | Single choice keeps scoring unambiguous. |
| Rate limiting, metrics, Docker | A reasonable next step for production readiness. |

---

## AI-assisted development

This project was developed with Claude Code as the main implementation agent, under the author's technical direction: analysis and a plan first, then implementation in reviewed steps, with tests and manual checks after each one. The full interaction log is part of the challenge submission and is not published in this repository.
