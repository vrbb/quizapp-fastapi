"""Pure scoring logic: no database, no I/O, so it is trivially unit-testable."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreResult:
    correct_count: int
    total_questions: int
    percentage: float
    correctness: dict[int, bool]  # question_id -> answered correctly


def score_answers(answer_key: dict[int, int], selected: dict[int, int]) -> ScoreResult:
    """Score a submission.

    answer_key: question_id -> correct option_id (defines the full question set).
    selected:   question_id -> chosen option_id.
    The score is always out of ALL questions in the answer key; a question with no
    selection counts as incorrect (the API layer additionally requires all answers).
    """
    if not answer_key:
        raise ValueError("answer_key must contain at least one question")

    correctness = {qid: selected.get(qid) == correct for qid, correct in answer_key.items()}
    correct_count = sum(correctness.values())
    total = len(answer_key)
    return ScoreResult(
        correct_count=correct_count,
        total_questions=total,
        percentage=round(correct_count * 100 / total, 2),
        correctness=correctness,
    )


def performance_message(percentage: float) -> str:
    if not 0 <= percentage <= 100:
        raise ValueError("percentage must be between 0 and 100")
    if percentage == 100:
        return "Perfect score! You've mastered this topic."
    if percentage >= 80:
        return "Great job! You have a strong understanding of this topic."
    if percentage >= 50:
        return "Good effort! Review the explanations to strengthen your knowledge."
    return "Keep practicing! Review the material and try again."
