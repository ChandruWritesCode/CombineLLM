"""Settings, model registry, and application-recorded usage API."""

import asyncio
import csv
import io
import time
from contextlib import aclosing
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import SecretStr

from app.config import Settings
from app.connections import Connection, Preferences
from app.providers.base import ProviderError
from app.providers.compatible import APIProvider
from app.providers.gemini import GeminiProvider
from app.schemas import ChatRequest, Message
from app.storage import now

router = APIRouter(prefix="/api/v1", tags=["settings"])


class TrackedProvider:
    def __init__(self, provider, store, config, source):
        self.provider = provider
        self.store = store
        self.name = provider.name
        self.model = provider.model
        self.model_id = config.get("id")
        self.label = config.get("name", self.model)
        self.max_output_tokens = config.get("max_output_tokens", 2048)
        self.system_prompt = config.get("system_prompt", "")
        self.source = source

    async def stream(self, request):
        if request.system is None and self.system_prompt:
            request = request.model_copy(update={"system": self.system_prompt})
        event_id = str(uuid4())
        started = time.monotonic()
        usage = None
        status = "failed"
        error = None
        with self.store.connect() as db:
            db.execute(
                """INSERT INTO usage_events
                (id,model_id,label,provider,model,source,status,started_at)
                VALUES (?,?,?,?,?,?,'running',?)""",
                (event_id, self.model_id, self.label, self.name, self.model, self.source, now()),
            )
        try:
            async with aclosing(self.provider.stream(request)) as events:
                async for event in events:
                    if event.kind == "done":
                        usage = event.usage
                        status = "complete"
                    yield event
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except GeneratorExit:
            if status != "complete":
                status = "cancelled"
            raise
        except ProviderError as exc:
            error = exc.code
            raise
        finally:
            with self.store.connect() as db:
                db.execute(
                    """UPDATE usage_events SET status=?,duration_ms=?,input_tokens=?,
                    output_tokens=?,reasoning_tokens=?,total_tokens=?,error_code=? WHERE id=?""",
                    (
                        status,
                        round((time.monotonic() - started) * 1000),
                        usage.input_tokens if usage else None,
                        usage.output_tokens if usage else None,
                        usage.reasoning_tokens if usage else None,
                        usage.total_tokens if usage else None,
                        error,
                        event_id,
                    ),
                )


def build_provider(app, model_id=None, source="chat"):
    registry = app.state.connections
    prefs = registry.preferences()
    model_id = model_id or prefs.default_model_id
    if not model_id:
        raise ProviderError(
            "provider_not_configured", "Add a model and choose a default in Settings.", 503
        )
    config = registry.get(model_id)
    if not config["enabled"]:
        raise HTTPException(422, "Selected model is disabled. Choose another model explicitly.")
    key = registry.secret(model_id)
    if config["kind"] == "gemini":
        provider = GeminiProvider(
            Settings(
                _env_file=None,
                gemini_model=config["model"],
                gemini_api_key=SecretStr(key),
                provider_timeout_seconds=config["timeout_seconds"],
            )
        )
        provider.temperature = config["temperature"]
    else:
        provider = APIProvider(config, key)
    config["system_prompt"] = config["system_prompt"] or prefs.system_prompt
    return TrackedProvider(provider, app.state.store, config, source)


@router.get("/models")
async def list_models(request: Request):
    return request.app.state.connections.list()


@router.post("/models", status_code=201)
async def create_model(body: Connection, request: Request):
    return request.app.state.connections.save(body)


@router.put("/models/{model_id}")
async def edit_model(model_id: str, body: Connection, request: Request):
    return request.app.state.connections.save(body, model_id)


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(model_id: str, request: Request):
    request.app.state.connections.delete(model_id)
    return Response(status_code=204)


@router.post("/models/{model_id}/test")
async def test_model(model_id: str, request: Request):
    """Sends a small real prompt; may consume provider quota and is recorded as a test."""
    provider = build_provider(request.app, model_id, "connection_test")
    async with aclosing(
        provider.stream(
            ChatRequest(
                messages=[Message(role="user", content="Reply with a short greeting.")],
                max_output_tokens=256,
            )
        )
    ) as events:
        async for event in events:
            if event.kind == "done":
                return {
                    "ok": True,
                    "model": provider.model,
                    "usage": event.usage.model_dump() if event.usage else None,
                }
    raise ProviderError("incomplete_response", "Provider did not finish the test response.")


@router.get("/settings")
async def get_settings(request: Request):
    return request.app.state.connections.preferences()


@router.put("/settings")
async def save_settings(body: Preferences, request: Request):
    return request.app.state.connections.save_preferences(body)


def usage_rows(request, start, end, model_id):
    if start and end and start > end:
        raise HTTPException(422, "Start date must not be after end date")
    clauses, params = [], []
    for value, clause in [
        (start, "substr(started_at,1,10)>=?"),
        (end, "substr(started_at,1,10)<=?"),
        (model_id, "model_id=?"),
    ]:
        if value is not None:
            clauses.append(clause)
            params.append(str(value))
    query = "SELECT * FROM usage_events" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    with request.app.state.store.connect() as db:
        return [dict(r) for r in db.execute(query + " ORDER BY started_at DESC", params)]


@router.get("/usage")
async def get_usage(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    model_id: str | None = None,
):
    rows = usage_rows(request, start, end, model_id)
    groups = {}
    for row in rows:
        key = (row["model_id"], row["label"], row["provider"], row["model"])
        group = groups.setdefault(
            key,
            {
                "model_id": key[0],
                "label": key[1],
                "provider": key[2],
                "model": key[3],
                "requests": 0,
                "complete": 0,
                "failed": 0,
                "cancelled": 0,
                "interrupted": 0,
                "running": 0,
                "reported_tokens": 0,
                "unknown_usage": 0,
                "duration_ms": 0,
            },
        )
        group["requests"] += 1
        group[row["status"]] += 1
        group["reported_tokens"] += row["total_tokens"] or 0
        group["unknown_usage"] += row["total_tokens"] is None
        group["duration_ms"] += row["duration_ms"] or 0
    return {
        "requests": len(rows),
        "reported_tokens": sum(r["total_tokens"] or 0 for r in rows),
        "unknown_usage": sum(r["total_tokens"] is None for r in rows),
        "complete": sum(r["status"] == "complete" for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "models": list(groups.values()),
        "recent": rows[:100],
        "scope": "Requests through CombineLLM since Phase 4; not account-wide usage or billing.",
    }


@router.get("/usage/export")
async def export_usage(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    model_id: str | None = Query(default=None),
):
    rows = usage_rows(request, start, end, model_id)
    fields = [
        "started_at",
        "label",
        "provider",
        "model",
        "source",
        "status",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "duration_ms",
        "error_code",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(fields)
    for row in rows:
        values = [row.get(f) for f in fields]
        writer.writerow(
            [
                "'" + v
                if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                else v
                for v in values
            ]
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="combinellm-usage.csv"'},
    )
