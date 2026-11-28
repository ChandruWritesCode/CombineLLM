"""Settings, model registry, and application-recorded usage API."""

import asyncio
import csv
import io
import time
from contextlib import aclosing
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import SecretStr

from app.config import Settings
from app.connections import Connection, Preferences
from app.costs import current_budgets, estimate, total_cost
from app.limits import current_limits, limit_reason
from app.policies import cool_down, remaining
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
        self.usage_group = config.get("usage_group", "")
        self.pool = (
            "group:" + self.usage_group if self.usage_group else "model:" + str(self.model_id)
        )
        self.attempt_group_id = str(uuid4())
        self.attempt_number = 1
        self.input_price = config.get("input_price_per_million")
        self.output_price = config.get("output_price_per_million")
        self.model_request_limit = config.get("monthly_request_limit")
        self.workspace_request_limit = config.get("workspace_request_limit")

    async def stream(self, request):
        if request.system is None and self.system_prompt:
            request = request.model_copy(update={"system": self.system_prompt})
        event_id = str(uuid4())
        started = time.monotonic()
        usage = None
        status = "failed"
        error = None
        started_at = now()
        limit_error = None
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            limit_error = limit_reason(
                db,
                started_at[:7],
                self.model_id,
                self.workspace_request_limit,
                self.model_request_limit,
            )
            db.execute(
                """INSERT INTO usage_events
                (id,model_id,label,provider,model,source,status,started_at,
                 input_price_per_million,output_price_per_million,attempt_group_id,attempt_number,usage_group)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    self.model_id,
                    self.label,
                    self.name,
                    self.model,
                    self.source,
                    "skipped" if limit_error else "running",
                    started_at,
                    self.input_price,
                    self.output_price,
                    self.attempt_group_id,
                    self.attempt_number,
                    self.usage_group,
                ),
            )
        try:
            if limit_error:
                status = "skipped"
                raise ProviderError("local_request_limit", limit_error, 429)
            wait = remaining(self.store, self.pool)
            if wait:
                status = "skipped"
                raise ProviderError(
                    "provider_cooldown",
                    f"Shared quota cooldown: try again in {int(wait) + 1} seconds.",
                    429,
                )
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
            if exc.code == "provider_rate_limited":
                cool_down(self.store, self.pool, exc.retry_after)
            raise
        finally:
            with self.store.connect() as db:
                db.execute(
                    """UPDATE usage_events SET status=?,duration_ms=?,input_tokens=?,
                    output_tokens=?,reasoning_tokens=?,total_tokens=?,error_code=?,
                    estimated_cost_usd=? WHERE id=?""",
                    (
                        status,
                        round((time.monotonic() - started) * 1000),
                        usage.input_tokens if usage else None,
                        usage.output_tokens if usage else None,
                        usage.reasoning_tokens if usage else None,
                        usage.total_tokens if usage else None,
                        error,
                        estimate(usage, self.input_price, self.output_price),
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
    config["workspace_request_limit"] = prefs.monthly_request_limit
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


@router.get("/budgets")
async def get_budgets(request: Request):
    return current_budgets(request.app.state.connections)


@router.get("/limits")
async def get_limits(request: Request):
    return current_limits(request.app.state.connections)


@router.get("/quality")
async def get_quality(request: Request):
    """Local, subjective answer ratings grouped by answer workflow."""
    with request.app.state.store.connect() as db:
        rows = db.execute(
            "SELECT COALESCE(coordination_mode,'single') AS mode, COUNT(*) AS rated, "
            "AVG(rating) AS average_rating FROM messages "
            "WHERE role='assistant' AND status='complete' AND rating IS NOT NULL "
            "GROUP BY COALESCE(coordination_mode,'single') ORDER BY mode"
        ).fetchall()
    return {"groups": [dict(row) for row in rows], "scope": "User ratings of saved answers."}


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
                "skipped": 0,
                "reported_tokens": 0,
                "unknown_usage": 0,
                "duration_ms": 0,
                "estimated_cost_usd": "0",
                "unknown_cost_requests": 0,
            },
        )
        group["estimated_cost_usd"] = str(
            Decimal(group["estimated_cost_usd"]) + Decimal(row["estimated_cost_usd"] or "0")
        )
        group["unknown_cost_requests"] += (
            row["status"] != "skipped" and row["estimated_cost_usd"] is None
        )
        group["requests"] += 1
        group[row["status"]] += 1
        group["reported_tokens"] += row["total_tokens"] or 0
        group["unknown_usage"] += row["status"] != "skipped" and row["total_tokens"] is None
        group["duration_ms"] += row["duration_ms"] or 0
    return {
        "estimated_cost_usd": str(total_cost(rows)),
        "unknown_cost_requests": sum(
            r["status"] != "skipped" and r["estimated_cost_usd"] is None for r in rows
        ),
        "requests": len(rows),
        "reported_tokens": sum(r["total_tokens"] or 0 for r in rows),
        "unknown_usage": sum(r["status"] != "skipped" and r["total_tokens"] is None for r in rows),
        "complete": sum(r["status"] == "complete" for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "skipped": sum(r["status"] == "skipped" for r in rows),
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
        "input_price_per_million",
        "output_price_per_million",
        "estimated_cost_usd",
        "attempt_group_id",
        "attempt_number",
        "usage_group",
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


@router.get("/usage-groups")
async def usage_groups(request: Request):
    registry = request.app.state.connections
    groups = {}
    for model in registry.list():
        label = model.get("usage_group", "")
        if label:
            groups.setdefault(label, {"requests": 0, "reported_tokens": 0})
    with registry.store.connect() as db:
        for row in db.execute(
            "SELECT usage_group,count(*) AS requests,coalesce(sum(total_tokens),0) AS tokens "
            "FROM usage_events WHERE usage_group != '' GROUP BY usage_group"
        ):
            groups[row["usage_group"]] = {
                "requests": row["requests"],
                "reported_tokens": row["tokens"],
            }
    return [
        {
            "name": name,
            **totals,
            "cooldown_seconds": int(remaining(registry.store, "group:" + name)),
        }
        for name, totals in groups.items()
    ]
