import pytest

from app.services.scoring import performance_message, score_answers

KEY = {1: 10, 2: 20, 3: 30, 4: 40, 5: 50}


def test_all_correct():
    result = score_answers(KEY, dict(KEY))
    assert (result.correct_count, result.total_questions, result.percentage) == (5, 5, 100.0)
    assert all(result.correctness.values())


def test_none_correct():
    result = score_answers(KEY, {qid: oid + 1 for qid, oid in KEY.items()})
    assert (result.correct_count, result.percentage) == (0, 0.0)
    assert not any(result.correctness.values())


def test_partial_score_example_from_spec():
    selected = dict(KEY) | {5: 99}  # 4 of 5 correct
    result = score_answers(KEY, selected)
    assert (result.correct_count, result.total_questions, result.percentage) == (4, 5, 80.0)
    assert result.correctness == {1: True, 2: True, 3: True, 4: True, 5: False}


def test_unanswered_question_counts_as_incorrect_and_total_is_all_questions():
    result = score_answers(KEY, {1: 10, 2: 20})
    assert (result.correct_count, result.total_questions, result.percentage) == (2, 5, 40.0)


def test_extra_selections_are_ignored():
    result = score_answers({1: 10}, {1: 10, 999: 1})
    assert (result.correct_count, result.total_questions) == (1, 1)


def test_percentage_is_rounded_to_two_decimals():
    key = {1: 1, 2: 2, 3: 3}
    assert score_answers(key, {1: 1}).percentage == 33.33
    assert score_answers(key, {1: 1, 2: 2}).percentage == 66.67


def test_empty_answer_key_is_rejected():
    with pytest.raises(ValueError):
        score_answers({}, {})


@pytest.mark.parametrize(
    ("percentage", "expected_start"),
    [
        (100, "Perfect score"),
        (99.99, "Great job"),
        (80, "Great job"),
        (79.99, "Good effort"),
        (50, "Good effort"),
        (49.99, "Keep practicing"),
        (0, "Keep practicing"),
    ],
)
def test_performance_message_boundaries(percentage, expected_start):
    assert performance_message(percentage).startswith(expected_start)


@pytest.mark.parametrize("percentage", [-0.01, 100.01])
def test_performance_message_rejects_out_of_range(percentage):
    with pytest.raises(ValueError):
        performance_message(percentage)
