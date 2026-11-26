"""Quiz schemas.

Two families, kept deliberately separate:
- *Create schemas: admin input, contains the answer key (is_correct, explanation).
- *Public schemas: what clients see before submission. They do NOT declare
  is_correct or explanation, so FastAPI's response_model filtering strips them
  even if an ORM object carrying them is returned.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------- Input (contains the answer key) ----------

class OptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    is_correct: bool = False

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class QuestionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    explanation: str = Field(min_length=1, max_length=2000)
    options: list[OptionCreate] = Field(min_length=2, max_length=10)

    @field_validator("text", "explanation")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @model_validator(mode="after")
    def check_options(self) -> "QuestionCreate":
        correct = sum(o.is_correct for o in self.options)
        if correct != 1:
            raise ValueError(f"each question must have exactly one correct option (got {correct})")
        texts = [o.text.casefold() for o in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError("options within a question must be unique")
        return self


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    questions: list[QuestionCreate] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


# ---------- Public output (NO answer key) ----------


class OptionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str


class QuestionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    options: list[OptionPublic]


class QuizSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    question_count: int
    created_at: datetime


class QuizPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    created_at: datetime
    questions: list[QuestionPublic]
