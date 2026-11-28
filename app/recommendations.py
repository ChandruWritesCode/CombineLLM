"""Read-only model suggestions from local observations and user-entered rates."""

from decimal import Decimal
from math import ceil

from fastapi import APIRouter, Request

from app.costs import current_budgets
from app.policies import is_local, remaining

router = APIRouter(prefix="/api/v1", tags=["recommendations"])


def _observations(store, model_id):
    with store.connect() as db:
        rows = db.execute(
            "SELECT status FROM usage_events WHERE model_id=? "
            "AND source!='connection_test' AND status IN ('complete','failed') "
            "ORDER BY started_at DESC LIMIT 20",
            (model_id,),
        ).fetchall()
    completed = sum(row["status"] == "complete" for row in rows)
    return {"observed_requests": len(rows), "completed": completed, "failed": len(rows) - completed}


def _price(config):
    input_rate = config.get("input_price_per_million")
    output_rate = config.get("output_price_per_million")
    if input_rate is None or output_rate is None:
        return None
    # One thousand input plus one thousand output tokens, using manual rates.
    return (Decimal(str(input_rate)) + Decimal(str(output_rate))) / Decimal(1000)


def compare_models(app, local_only=False):
    registry = app.state.connections
    budgets = current_budgets(registry)
    budget_by_id = {item["model_id"]: item for item in budgets["models"]}
    items = []
    for config in registry.list():
        model_id = config["id"]
        local = is_local(config)
        pool = (
            "group:" + config["usage_group"] if config.get("usage_group") else "model:" + model_id
        )
        cooldown = ceil(remaining(registry.store, pool))
        budget = budget_by_id[model_id]
        observed = _observations(registry.store, model_id)
        price = _price(config)
        reasons = []
        if not config["enabled"]:
            reasons.append("Disabled in Settings")
        if local_only and not local:
            reasons.append("Excluded by local-only mode")
        if cooldown:
            reasons.append(f"Shared cooldown: about {cooldown}s remaining")
        if budget["status"] in {"warning", "exceeded"}:
            reasons.append(f"Manual budget {budget['status']}")
        if budget["unknown_cost_requests"]:
            reasons.append("Monthly cost estimate is incomplete")
        if price is None:
            reasons.append("Configured price is unknown")
        if not observed["observed_requests"]:
            reasons.append("No recent chat outcomes recorded")
        eligible = config["enabled"] and (not local_only or local) and cooldown == 0
        items.append(
            {
                "model_id": model_id,
                "name": config["name"],
                "model": config["model"],
                "local": local,
                "eligible": eligible,
                "cooldown_seconds": cooldown,
                "budget_status": budget["status"],
                "cost_per_1k_each_usd": str(price) if price is not None else None,
                **observed,
                "reasons": reasons,
            }
        )

    def ranking(item):
        observed = item["observed_requests"]
        completion_rate = item["completed"] / observed if observed else 0
        poor_history = observed >= 3 and completion_rate < 0.5
        budget_rank = {"exceeded": 2, "warning": 1}.get(item["budget_status"], 0)
        price = item["cost_per_1k_each_usd"]
        return (
            not item["eligible"],
            budget_rank,
            poor_history,
            price is None,
            Decimal(price) if price is not None else Decimal(0),
            -completion_rate,
            item["name"].casefold(),
        )

    items.sort(key=ranking)
    suggestion = next((item["model_id"] for item in items if item["eligible"]), None)
    return {
        "suggested_model_id": suggestion,
        "models": items,
        "scope": (
            "Read-only suggestion from configured prices, local request outcomes, "
            "manual budgets, and cooldowns. It does not know provider quota, "
            "live availability, or answer quality. Selection remains manual."
        ),
    }


@router.get("/recommendations")
async def recommendations(request: Request, local_only: bool = False):
    return compare_models(request.app, local_only)
