"""Versioned, text-only conversation archives without credentials or usage events."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortableMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=50000)
    status: Literal["complete", "failed", "cancelled", "interrupted"]
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    created_at: datetime

    @model_validator(mode="after")
    def require_timezone(self):
        if self.created_at.tzinfo is None:
            raise ValueError("Message timestamps must include a timezone")
        return self


class ConversationArchive(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    format: Literal["combinellm-conversation"]
    version: Literal[1]
    title: str = Field(min_length=1, max_length=100)
    messages: list[PortableMessage] = Field(max_length=400)

    @model_validator(mode="after")
    def validate_transcript(self):
        if len(self.messages) % 2:
            raise ValueError("A transcript must contain complete user/assistant pairs")
        if sum(len(message.content) for message in self.messages) > 1_000_000:
            raise ValueError("A transcript cannot exceed 1,000,000 characters")
        for index, message in enumerate(self.messages):
            role = "user" if index % 2 == 0 else "assistant"
            if message.role != role:
                raise ValueError("Messages must alternate between user and assistant")
            if role == "user" and (message.status != "complete" or not message.content.strip()):
                raise ValueError("User messages must contain completed text")
        return self


def plain_text(archive):
    lines = [f"CombineLLM conversation: {archive.title}", ""]
    for message in archive.messages:
        label = "You" if message.role == "user" else "Assistant"
        if message.role == "assistant" and message.model:
            label += f" ({message.model})"
        lines.extend(
            [
                f"{label} · {message.status} · {message.created_at.isoformat()}",
                message.content,
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)
