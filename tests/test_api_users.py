import pytest


def test_create_and_get_user(client):
    response = client.post("/users", json={"name": "  Ada  ", "email": "Ada@Example.com"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Ada"
    assert body["email"] == "ada@example.com"
    assert client.get(f"/users/{body['id']}").json() == body


def test_duplicate_email_is_rejected_case_insensitively(client):
    client.post("/users", json={"name": "Ada", "email": "ada@example.com"})

    response = client.post("/users", json={"name": "Other", "email": "ADA@example.com"})

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Ada", "email": "not-an-email"},
        {"name": "", "email": "ada@example.com"},
        {"name": "   ", "email": "ada@example.com"},
        {"name": "x" * 101, "email": "ada@example.com"},
        {"email": "ada@example.com"},
        {"name": "Ada"},
    ],
)
def test_create_user_validation(client, payload):
    assert client.post("/users", json=payload).status_code == 422


def test_get_unknown_user(client):
    assert client.get("/users/999").status_code == 404
    assert client.get("/users/999/attempts").status_code == 404
    assert client.get("/users/999/stats").status_code == 404


def test_stats_for_user_without_attempts(client):
    user_id = client.post("/users", json={"name": "Ada", "email": "ada@example.com"}).json()["id"]

    stats = client.get(f"/users/{user_id}/stats").json()

    assert stats == {
        "user_id": user_id,
        "total_attempts": 0,
        "completed_attempts": 0,
        "in_progress_attempts": 0,
        "average_percentage": None,
        "best_percentage": None,
        "total_correct_answers": 0,
        "total_questions_answered": 0,
        "per_quiz": [],
    }
