import pytest
from pydantic import ValidationError

from app.schemas.quiz import (
    OptionPublic,
    QuestionCreate,
    QuestionPublic,
    QuizCreate,
    QuizPublic,
)
from app.seed import SEED_QUIZZES, seed_quizzes
from sqlalchemy import select
from app.models import Quiz

ANSWER_KEY_FIELDS = {"is_correct", "explanation"}


def option(text: str, correct: bool = False) -> dict:
    return {"text": text, "is_correct": correct}


def test_public_schemas_do_not_declare_answer_key_fields():
    for schema in (OptionPublic, QuestionPublic, QuizPublic):
        assert not ANSWER_KEY_FIELDS & set(schema.model_fields), schema.__name__


def test_public_quiz_serialisation_contains_no_answer_key(db):
    seed_quizzes(db)
    quiz = db.scalar(select(Quiz).where(Quiz.title == SEED_QUIZZES[0].title))

    payload = QuizPublic.model_validate(quiz).model_dump_json()

    assert "is_correct" not in payload
    assert "explanation" not in payload
    assert quiz.questions[0].options[0].text in payload


@pytest.mark.parametrize(
    "options",
    [
        [option("A"), option("B")],  # no correct option
        [option("A", True), option("B", True)],  # two correct options
        [option("A", True)],  # fewer than two options
        [option("A", True), option("a")],  # duplicate option (case-insensitive)
        [option("A", True), option("   ")],  # blank option text
    ],
)
def test_question_create_rejects_invalid_options(options):
    with pytest.raises(ValidationError):
        QuestionCreate(text="Q", explanation="E", options=options)


def test_quiz_create_requires_questions_and_title():
    with pytest.raises(ValidationError):
        QuizCreate(title="T", questions=[])
    with pytest.raises(ValidationError):
        QuizCreate(
            title="   ",
            questions=[{"text": "Q", "explanation": "E", "options": [option("A", True), option("B")]}],
        )


def test_quiz_create_strips_whitespace():
    quiz = QuizCreate(
        title="  Title  ",
        questions=[{"text": " Q ", "explanation": " E ", "options": [option(" A ", True), option("B")]}],
    )
    assert quiz.title == "Title"
    assert quiz.questions[0].text == "Q"
    assert quiz.questions[0].options[0].text == "A"
