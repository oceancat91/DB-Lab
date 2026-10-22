"""Strict input contracts; server-owned fields are never accepted from clients."""
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Credentials(InputModel):
    username: str = Field(min_length=3, max_length=32, strict=True)
    password: str = Field(min_length=8, max_length=128, strict=True)

    @field_validator('username', mode='before')
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class Metadata(InputModel):
    title: str = Field(min_length=1, max_length=200, strict=True)
    description: str = Field(default='', max_length=5000, strict=True)
    allow_anonymous: StrictBool = True
    allow_repeat: StrictBool = False
    closes_at: datetime | None = None

    @field_validator('title', mode='before')
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('closes_at', mode='before')
    @classmethod
    def aware_date(cls, value):
        if value is not None:
            if not isinstance(value, str) or 'T' not in value:
                raise ValueError('截止时间必须为带时区的 ISO8601 文本')
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError as exc:
                raise ValueError('截止时间必须为带时区的 ISO8601 文本') from exc
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError('截止时间必须带时区')
            return value.astimezone(timezone.utc)
        return value


class DraftInput(Metadata):
    revision: StrictInt = Field(ge=0)
    questions: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    rules: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class PublishInput(InputModel):
    revision: StrictInt = Field(ge=0)


class DeadlineInput(InputModel):
    closes_at: datetime | None

    @field_validator('closes_at', mode='before')
    @classmethod
    def aware_date(cls, value):
        return Metadata.aware_date(value)


class NextInput(InputModel):
    version: StrictInt = Field(ge=1)
    answers: dict[str, Any] = Field(default_factory=dict, max_length=100)


class SubmitInput(NextInput):
    request_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$', strict=True)


class QuestionInput(InputModel):
    """Content of one stored question version; shape checks live in questions.check_definition."""
    type: str = Field(min_length=1, max_length=16, strict=True)
    title: str = Field(min_length=1, max_length=500, strict=True)
    required: StrictBool = False
    options: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    validation: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default='', max_length=500, strict=True)

    @field_validator('title', mode='before')
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class ShareInput(InputModel):
    username: str = Field(min_length=3, max_length=32, strict=True)


class BankInput(InputModel):
    name: str = Field(min_length=1, max_length=100, strict=True)
    description: str = Field(default='', max_length=500, strict=True)

    @field_validator('name', mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class BankPatch(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, strict=True)
    description: str | None = Field(default=None, max_length=500, strict=True)


class BankItemInput(InputModel):
    question_id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$', strict=True)
    version: StrictInt | None = Field(default=None, ge=1)


class BankVersionInput(InputModel):
    """Re-pin an existing bank item; the question id comes from the path."""
    version: StrictInt | None = Field(default=None, ge=1)


class ImportQuestionInput(InputModel):
    question_id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$', strict=True)
    version: StrictInt | None = Field(default=None, ge=1)
    bank_id: str | None = Field(default=None, min_length=1, max_length=64,
                                pattern=r'^[A-Za-z0-9_-]+$', strict=True)


class RevisionInput(InputModel):
    mode: str = Field(min_length=1, max_length=16, pattern=r'^(draft_only|new_version|fork)$', strict=True)
    question: QuestionInput
