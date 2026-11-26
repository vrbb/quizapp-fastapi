import pytest

from app.seed import SEED_QUIZZES
from tests.conftest import collect_keys

ANSWER_KEY_FIELDS = {"is_correct", "explanation"}


def new_quiz_payload(title: str = "Python Basics", questions: int = 2) -> dict:
    return {
        "title": title,
        "description": "desc",
        "questions": [
            {
                "text": f"Question {i}?",
                "explanation": f"Because {i}.",
                "options": [
                    {"text": "Right", "is_correct": True},
                    {"text": "Wrong"},
                    {"text": "Also wrong"},
                ],
            }
            for i in range(1, questions + 1)
        ],
    }


# ---------- GET /quizzes ----------


def test_list_quizzes_returns_seeded_quizzes_with_question_counts(client, seeded):
    response = client.get("/quizzes")

    assert response.status_code == 200
    body = response.json()
    assert [q["title"] for q in body] == [q.title for q in SEED_QUIZZES]
    assert all(q["question_count"] == 5 for q in body)
    assert set(body[0]) == {"id", "title", "description", "question_count", "created_at"}


def test_list_quizzes_empty_database(client):
    assert client.get("/quizzes").json() == []


def test_list_quizzes_pagination(client, seeded):
    first = client.get("/quizzes", params={"limit": 1}).json()
    second = client.get("/quizzes", params={"limit": 1, "offset": 1}).json()

    assert len(first) == len(second) == 1
    assert first[0]["id"] != second[0]["id"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"limit": "abc"}])
def test_list_quizzes_rejects_invalid_pagination(client, params):
    assert client.get("/quizzes", params=params).status_code == 422


# ---------- GET /quizzes/{id} ----------


def test_get_quiz_returns_questions_and_options_in_order(client, seeded):
    quiz_id = client.get("/quizzes").json()[0]["id"]

    body = client.get(f"/quizzes/{quiz_id}").json()

    assert body["title"] == SEED_QUIZZES[0].title
    assert [q["position"] for q in body["questions"]] == [1, 2, 3, 4, 5]
    expected_options = [o.text for o in SEED_QUIZZES[0].questions[0].options]
    assert [o["text"] for o in body["questions"][0]["options"]] == expected_options


def test_get_quiz_never_exposes_answer_key(client, seeded):
    for summary in client.get("/quizzes").json():
        body = client.get(f"/quizzes/{summary['id']}").json()
        assert not ANSWER_KEY_FIELDS & collect_keys(body)


def test_get_quiz_not_found(client):
    response = client.get("/quizzes/9999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Quiz 9999 not found"}


def test_get_quiz_invalid_id(client):
    assert client.get("/quizzes/not-a-number").status_code == 422


# ---------- POST /quizzes ----------


def test_create_quiz_returns_public_view_without_answer_key(client):
    response = client.post("/quizzes", json=new_quiz_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Python Basics"
    assert len(body["questions"]) == 2
    assert not ANSWER_KEY_FIELDS & collect_keys(body)


def test_created_quiz_is_persisted_and_listed(client):
    created = client.post("/quizzes", json=new_quiz_payload(questions=3)).json()

    listed = client.get("/quizzes").json()
    fetched = client.get(f"/quizzes/{created['id']}").json()

    assert listed == [
        {
            "id": created["id"],
            "title": "Python Basics",
            "description": "desc",
            "question_count": 3,
            "created_at": created["created_at"],
        }
    ]
    assert fetched == created


def test_create_quiz_persists_answer_key_internally(client, db):
    from app.models import Quiz

    quiz_id = client.post("/quizzes", json=new_quiz_payload()).json()["id"]

    quiz = db.get(Quiz, quiz_id)
    assert [o.is_correct for o in quiz.questions[0].options] == [True, False, False]
    assert quiz.questions[0].explanation == "Because 1."


def test_create_quiz_duplicate_title_conflict(client, seeded):
    response = client.post("/quizzes", json=new_quiz_payload(title=SEED_QUIZZES[0].title))

    assert response.status_code == 409
    assert len(client.get("/quizzes").json()) == len(SEED_QUIZZES)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(title=""),
        lambda p: p.update(questions=[]),
        lambda p: p["questions"][0]["options"][1].update(is_correct=True),  # two correct
        lambda p: p["questions"][0]["options"][0].update(is_correct=False),  # none correct
        lambda p: p["questions"][0].update(options=p["questions"][0]["options"][:1]),  # one option
        lambda p: p["questions"][0].pop("explanation"),
        lambda p: p["questions"][0]["options"][0].update(is_correct="maybe"),
    ],
    ids=["blank-title", "no-questions", "two-correct", "no-correct", "one-option", "no-explanation", "bad-bool"],
)
def test_create_quiz_validation_errors(client, mutate):
    payload = new_quiz_payload()
    mutate(payload)

    response = client.post("/quizzes", json=payload)

    assert response.status_code == 422
    assert client.get("/quizzes").json() == []
