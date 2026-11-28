from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from app.schemas import ChatRequest, Usage


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retry_after: float = 60):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after

    def payload(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass
class ProviderEvent:
    kind: Literal["delta", "done", "stage", "intermediate"]
    text: str = ""
    finish_reason: str = ""
    usage: Usage | None = None


class ChatProvider(Protocol):
    name: str
    model: str

    def stream(self, request: ChatRequest) -> AsyncIterator[ProviderEvent]: ...
