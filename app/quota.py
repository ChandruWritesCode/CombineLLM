"""Sanitized, advisory quota signals observed on provider HTTP responses."""

import json
import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["usage"])
_DURATION = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$")


def _count(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 1_000_000_000 else None


def _reset(value, observed):
    if value is None or len(value) > 40:
        return None
    match = _DURATION.fullmatch(value.strip())
    if not match or not any(part is not None for part in match.groups()):
        return None
    hours, minutes, seconds = match.groups()
    duration = int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0)
    if duration < 0 or duration > 86400 * 7:
        return None
    return (observed + timedelta(seconds=duration)).isoformat()


def parse_headers(headers):
    observed = datetime.now(UTC)
    result = {
        "observed_at": observed.isoformat(),
        "remaining_requests": _count(headers.get("x-ratelimit-remaining-requests")),
        "remaining_tokens": _count(headers.get("x-ratelimit-remaining-tokens")),
        "requests_reset_at": _reset(headers.get("x-ratelimit-reset-requests"), observed),
        "tokens_reset_at": _reset(headers.get("x-ratelimit-reset-tokens"), observed),
    }
    has_signal = any(value is not None for key, value in result.items() if key != "observed_at")
    return result if has_signal else None


def save(store, model_id, signal):
    if signal is None or not model_id:
        return
    with store.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO preferences (key,value) VALUES (?,?)",
            ("quota:" + model_id, json.dumps(signal)),
        )


def observed(registry):
    models = registry.list()
    with registry.store.connect() as db:
        rows = {
            row["key"][6:]: json.loads(row["value"])
            for row in db.execute("SELECT key,value FROM preferences WHERE key LIKE 'quota:%'")
        }
    return [
        {"model_id": model["id"], "name": model["name"], "signal": rows.get(model["id"])}
        for model in models
    ]


@router.get("/quota")
async def quota(request: Request):
    return {
        "advisory_only": True,
        "models": observed(request.app.state.connections),
        "scope": (
            "Last provider response headers observed by this app. Windows and account-wide "
            "balances may differ; absence means unknown."
        ),
    }
