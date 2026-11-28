"""Read-only local storage diagnostics without secret values or provider calls."""

import json
from pathlib import Path

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["diagnostics"])


@router.get("/diagnostics")
async def diagnostics(request: Request):
    store = request.app.state.store
    with store.connect() as db:
        integrity = db.execute("PRAGMA quick_check(1)").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        conversations = db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        models = db.execute("SELECT config FROM model_connections").fetchall()

    return {
        "storage": "ready" if integrity == "ok" else "needs_attention",
        "schema_version": version,
        "conversations": conversations,
        "model_connections": len(models),
        "enabled_models": sum(
            bool(json.loads(row["config"]).get("enabled", True)) for row in models
        ),
        "credential_key_present": Path(store.path).with_suffix(".key").is_file(),
        "active_generations": len(request.app.state.generations.tasks),
        "cloud_availability": "not_checked",
    }
