"""Provider-neutral, text-only chat contract."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=50000)

    @field_validator("content")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must contain non-whitespace text")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["gemini"] = "gemini"
    messages: list[Message] = Field(min_length=1, max_length=100)
    system: str | None = Field(default=None, max_length=10000)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    stream: bool = False

    @model_validator(mode="after")
    def validate_history(self) -> "ChatRequest":
        if self.messages[0].role != "user" or self.messages[-1].role != "user":
            raise ValueError("History must start and end with a user message")
        if any(a.role == b.role for a, b in zip(self.messages, self.messages[1:])):
            raise ValueError("Messages must alternate between user and assistant")
        if sum(len(m.content) for m in self.messages) + len(self.system or "") > 100000:
            raise ValueError("Total input cannot exceed 100000 characters")
        return self


class Usage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    finish_reason: str
    usage: Usage


class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    model: str | None
