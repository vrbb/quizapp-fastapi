from sqlalchemy import func, select

from app.models import Option, Question, Quiz
from app.seed import SEED_QUIZZES, seed_quizzes


def test_seed_creates_at_least_two_quizzes_with_five_questions(db):
    created = seed_quizzes(db)

    quizzes = db.scalars(select(Quiz)).all()
    assert created == len(SEED_QUIZZES)
    assert len(quizzes) >= 2
    for quiz in quizzes:
        assert len(quiz.questions) >= 5
        for question in quiz.questions:
            assert len(question.options) >= 2
            assert sum(o.is_correct for o in question.options) == 1
            assert question.explanation


def test_seed_is_idempotent(db):
    seed_quizzes(db)
    counts_before = (
        db.scalar(select(func.count(Quiz.id))),
        db.scalar(select(func.count(Question.id))),
        db.scalar(select(func.count(Option.id))),
    )

    created_again = seed_quizzes(db)
    seed_quizzes(db)

    counts_after = (
        db.scalar(select(func.count(Quiz.id))),
        db.scalar(select(func.count(Question.id))),
        db.scalar(select(func.count(Option.id))),
    )
    assert created_again == 0
    assert counts_after == counts_before


def test_seed_only_adds_missing_quizzes(db):
    seed_quizzes(db)
    db.delete(db.scalar(select(Quiz).where(Quiz.title == SEED_QUIZZES[0].title)))
    db.commit()

    assert seed_quizzes(db) == 1
    assert db.scalar(select(func.count(Quiz.id))) == len(SEED_QUIZZES)


def test_seed_question_and_option_positions_are_ordered(db):
    seed_quizzes(db)
    for quiz in db.scalars(select(Quiz)).all():
        assert [q.position for q in quiz.questions] == list(range(1, len(quiz.questions) + 1))
        for q in quiz.questions:
            assert [o.position for o in q.options] == list(range(1, len(q.options) + 1))
