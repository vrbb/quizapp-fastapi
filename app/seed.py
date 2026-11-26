"""Idempotent seed data: quizzes on AI development concepts.

Each quiz is identified by its (unique) title. Running the seed again only inserts
quizzes that are missing, so it is safe to call on every startup.

Run manually with: python -m app.seed
"""
import logging

from sqlalchemy.orm import Session

from app.schemas.quiz import OptionCreate as O
from app.schemas.quiz import QuestionCreate as Q
from app.schemas.quiz import QuizCreate
from app.services.quiz_service import build_quiz, get_quiz_by_title

logger = logging.getLogger(__name__)

SEED_QUIZZES: list[QuizCreate] = [
    QuizCreate(
        title="Prompt Engineering Fundamentals",
        description="Core techniques for getting reliable output from large language models.",
        questions=[
            Q(
                text="What is 'few-shot prompting'?",
                explanation="Few-shot prompting includes a small number of worked examples in the prompt so the model can infer the expected pattern.",
                options=[
                    O(text="Fine-tuning a model on a small dataset"),
                    O(text="Including a few input/output examples in the prompt", is_correct=True),
                    O(text="Limiting the response to a few tokens"),
                    O(text="Sending the same prompt a few times and voting"),
                ],
            ),
            Q(
                text="Which technique asks the model to reason step by step before answering?",
                explanation="Chain-of-thought prompting elicits intermediate reasoning steps, which tends to improve accuracy on multi-step problems.",
                options=[
                    O(text="Chain-of-thought prompting", is_correct=True),
                    O(text="Temperature scaling"),
                    O(text="Retrieval-augmented generation"),
                    O(text="Tokenization"),
                ],
            ),
            Q(
                text="What does lowering the sampling temperature generally do?",
                explanation="Lower temperature sharpens the probability distribution, making outputs more deterministic and less varied.",
                options=[
                    O(text="Makes outputs more random and creative"),
                    O(text="Increases the context window"),
                    O(text="Makes outputs more deterministic and focused", is_correct=True),
                    O(text="Reduces the cost per token"),
                ],
            ),
            Q(
                text="What is the main purpose of a system prompt?",
                explanation="The system prompt sets persistent instructions, role and constraints that frame the whole conversation.",
                options=[
                    O(text="To store the user's chat history"),
                    O(text="To set the model's role, rules and behaviour for the conversation", is_correct=True),
                    O(text="To configure the model's hardware"),
                    O(text="To translate the user's input"),
                ],
            ),
            Q(
                text="What is 'prompt injection'?",
                explanation="Prompt injection is when untrusted input contains instructions that try to override the developer's intended instructions.",
                options=[
                    O(text="Adding more examples to a prompt"),
                    O(text="Compressing a prompt to save tokens"),
                    O(text="Caching prompts to reduce latency"),
                    O(text="Untrusted input that tries to override the intended instructions", is_correct=True),
                ],
            ),
        ],
    ),
    QuizCreate(
        title="AI Agents and Tool Use",
        description="How LLM-based agents plan, call tools and stay safe in real workflows.",
        questions=[
            Q(
                text="In an LLM agent, what is a 'tool'?",
                explanation="A tool is an external function or API the model can request to call, such as search, code execution or a database query.",
                options=[
                    O(text="A function or API the model can call to act or fetch information", is_correct=True),
                    O(text="A plugin that increases model size"),
                    O(text="A type of training dataset"),
                    O(text="A GPU optimisation library"),
                ],
            ),
            Q(
                text="What does RAG (Retrieval-Augmented Generation) do?",
                explanation="RAG retrieves relevant documents at query time and adds them to the prompt so answers are grounded in that content.",
                options=[
                    O(text="Randomly augments training data"),
                    O(text="Retrieves relevant documents and adds them to the prompt as context", is_correct=True),
                    O(text="Re-generates answers until they pass a test"),
                    O(text="Reduces the model's parameter count"),
                ],
            ),
            Q(
                text="What is a typical 'agent loop'?",
                explanation="Agents repeatedly decide on an action, execute it (often via a tool), observe the result and continue until the goal is met.",
                options=[
                    O(text="Training the model in a loop until loss is zero"),
                    O(text="Sending the same request until it succeeds"),
                    O(text="Plan an action, execute it, observe the result, repeat until done", is_correct=True),
                    O(text="Looping through all tokens in the vocabulary"),
                ],
            ),
            Q(
                text="Why should AI-generated code be reviewed before merging?",
                explanation="Generated code can be plausible but wrong or insecure; human review and tests catch bugs, security issues and misunderstood requirements.",
                options=[
                    O(text="Because AI code cannot be executed"),
                    O(text="Because it may contain subtle bugs or security issues", is_correct=True),
                    O(text="Because reviews make the code run faster"),
                    O(text="Because licences forbid unreviewed code"),
                ],
            ),
            Q(
                text="What is the main benefit of giving an agent narrowly scoped permissions?",
                explanation="Least privilege limits the damage a mistaken or manipulated agent can do.",
                options=[
                    O(text="It makes the model smarter"),
                    O(text="It reduces token usage"),
                    O(text="It removes the need for tests"),
                    O(text="It limits the impact of mistakes or malicious instructions", is_correct=True),
                ],
            ),
        ],
    ),
]


def seed_quizzes(db: Session) -> int:
    """Insert any missing seed quizzes. Returns how many were created."""
    created = 0
    for data in SEED_QUIZZES:
        if get_quiz_by_title(db, data.title) is None:
            db.add(build_quiz(data))
            created += 1
    db.commit()
    logger.info("Seed complete: %d quiz(zes) created, %d already present", created, len(SEED_QUIZZES) - created)
    return created


if __name__ == "__main__":
    from app.database import SessionLocal, init_db

    logging.basicConfig(level=logging.INFO)
    init_db()
    with SessionLocal() as session:
        seed_quizzes(session)
