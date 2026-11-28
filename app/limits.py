"""Local monthly request ceilings; counts are reservations, not provider quotas."""

from datetime import UTC, datetime


def _count(db, month, model_id=None):
    query = "SELECT COUNT(*) FROM usage_events WHERE substr(started_at,1,7)=? AND status!='skipped'"
    params = [month]
    if model_id is not None:
        query += " AND model_id=?"
        params.append(model_id)
    return db.execute(query, params).fetchone()[0]


def limit_reason(db, month, model_id, workspace_limit, model_limit):
    """Call inside the same immediate transaction as a running usage-row insert."""
    if workspace_limit is not None and _count(db, month) >= workspace_limit:
        return "Workspace monthly request ceiling reached."
    if model_limit is not None and _count(db, month, model_id) >= model_limit:
        return "Model monthly request ceiling reached."
    return None


def current_limits(registry, clock=None):
    month = (clock or datetime.now(UTC)).strftime("%Y-%m")
    prefs = registry.preferences()
    with registry.store.connect() as db:
        workspace_count = _count(db, month)
        models = [
            {
                "model_id": model["id"],
                "name": model["name"],
                "count": _count(db, month, model["id"]),
                "limit": model.get("monthly_request_limit"),
            }
            for model in registry.list()
        ]
    for model in models:
        model["remaining"] = (
            max(0, model["limit"] - model["count"]) if model["limit"] is not None else None
        )
        model["reached"] = model["remaining"] == 0
    workspace_limit = prefs.monthly_request_limit
    return {
        "month_utc": month,
        "workspace": {
            "count": workspace_count,
            "limit": workspace_limit,
            "remaining": max(0, workspace_limit - workspace_count)
            if workspace_limit is not None
            else None,
            "reached": workspace_limit is not None and workspace_count >= workspace_limit,
        },
        "models": models,
        "scope": (
            "Local requests sent through CombineLLM in this UTC month. "
            "Connection tests and failed provider calls count. Skipped calls do not. "
            "This is not a provider quota or spending cap."
        ),
    }
