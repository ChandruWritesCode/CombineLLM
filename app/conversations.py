"""Persistent chat API and generation lifecycle for a single backend process."""

import asyncio
import logging
from contextlib import aclosing

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.chat import get_provider, sse
from app.providers.base import ChatProvider, ProviderError
from app.storage import Store

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


class Title(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New conversation", min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=50000)
    max_output_tokens: int | None = Field(default=None, ge=1, le=8192)
    model_id: str | None = None


class Generations:
    def __init__(self, store: Store):
        self.store = store
        self.tasks: dict[str, asyncio.Task] = {}

    def start(self, message_id, request, provider):
        task = asyncio.create_task(self.run(message_id, request, provider))
        self.tasks[message_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(message_id, None))

    async def run(self, message_id, request, provider):
        content = ""
        try:
            async with aclosing(provider.stream(request)) as events:
                async for event in events:
                    if event.kind == "delta":
                        content += event.text
                        self.store.save_answer(message_id, content, "streaming")
                    else:
                        self.store.save_answer(
                            message_id,
                            content,
                            "complete",
                            finish=event.finish_reason,
                            usage=event.usage.model_dump() if event.usage else None,
                        )
                        return
            raise ProviderError("incomplete_response", "Provider stream ended before completion.")
        except asyncio.CancelledError:
            self.store.save_answer(message_id, content, "cancelled", error="Response stopped.")
            raise
        except ProviderError as exc:
            self.store.save_answer(message_id, content, "failed", error=exc.message)
        except Exception:
            # Do not log raw provider exception text or credentials.
            logger.error("Generation failed unexpectedly for message %s", message_id)
            self.store.save_answer(
                message_id,
                content,
                "failed",
                error="An internal error occurred while generating the response.",
            )

    async def cancel(self, message_id):
        task = self.tasks.get(message_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        # Covers cancellation before the coroutine starts executing.
        with self.store.connect() as db:
            db.execute(
                "UPDATE messages SET status='cancelled',error='Response stopped.' "
                "WHERE id=? AND status='streaming'",
                (message_id,),
            )

    async def close(self):
        for message_id in list(self.tasks):
            await self.cancel(message_id)


def store(request: Request) -> Store:
    return request.app.state.store


@router.get("")
async def list_conversations(db: Store = Depends(store)):
    return db.list()


@router.post("", status_code=201)
async def create_conversation(body: Title, db: Store = Depends(store)):
    return db.create(body.title)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, db: Store = Depends(store)):
    return db.get(conversation_id)


@router.patch("/{conversation_id}")
async def rename(conversation_id: str, body: Title, db: Store = Depends(store)):
    return db.rename(conversation_id, body.title)


@router.delete("/{conversation_id}", status_code=204)
async def delete(conversation_id: str, request: Request, db: Store = Depends(store)):
    conversation = db.get(conversation_id)
    for message in conversation["messages"]:
        if message["status"] == "streaming":
            await request.app.state.generations.cancel(message["id"])
    db.delete(conversation_id)
    return Response(status_code=204)


@router.post("/{conversation_id}/messages", status_code=202)
async def send(
    conversation_id: str,
    body: Turn,
    request: Request,
    db: Store = Depends(store),
    provider: ChatProvider = Depends(get_provider),
):
    try:
        message_id, chat_request = db.begin(
            conversation_id,
            body.content,
            body.max_output_tokens or getattr(provider, "max_output_tokens", 2048),
            provider,
        )
    except ValidationError as exc:
        raise HTTPException(
            422, "Input or conversation exceeds chat limits. Start a new chat."
        ) from exc
    request.app.state.generations.start(message_id, chat_request, provider)
    return {"message_id": message_id, "conversation_id": conversation_id}


@router.post("/{conversation_id}/messages/{message_id}/cancel")
async def cancel(
    conversation_id: str, message_id: str, request: Request, db: Store = Depends(store)
):
    message = db.message(conversation_id, message_id)
    if message["role"] != "assistant":
        raise HTTPException(422, "Only assistant responses can be cancelled")
    await request.app.state.generations.cancel(message_id)
    return db.message(conversation_id, message_id)


@router.get("/{conversation_id}/messages/{message_id}/events")
async def events(
    conversation_id: str, message_id: str, request: Request, db: Store = Depends(store)
):
    """Snapshots can be reattached after refresh. Closing the stream does not stop generation."""
    db.message(conversation_id, message_id)

    async def snapshots():
        previous = None
        while not await request.is_disconnected():
            try:
                message = db.message(conversation_id, message_id)
            except HTTPException:
                yield sse("removed", {})
                return
            if message != previous:
                yield sse("message", message)
                previous = message
            if message["status"] != "streaming":
                yield sse("done", {"status": message["status"]})
                return
            await asyncio.sleep(0.2)

    return StreamingResponse(
        snapshots(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
