"""User-entered USD estimates and advisory budgets; never provider billing."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

Money = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=16, decimal_places=8)]


def estimate(usage, input_price, output_price):
    if (
        usage is None
        or usage.input_tokens is None
        or usage.output_tokens is None
        or input_price is None
        or output_price is None
        or usage.input_tokens < 0
        or usage.output_tokens < 0
    ):
        return None
    return str(
        (
            Decimal(usage.input_tokens) * Decimal(str(input_price))
            + Decimal(usage.output_tokens) * Decimal(str(output_price))
        )
        / Decimal(1000000)
    )


def total_cost(rows):
    return sum(
        (Decimal(r["estimated_cost_usd"]) for r in rows if r["estimated_cost_usd"] is not None),
        Decimal(0),
    )


def budget_status(rows, limit, warning_percent):
    spent = total_cost(rows)
    budget = Decimal(str(limit)) if limit is not None else None
    state = "not_set"
    if budget is not None:
        state = (
            "exceeded"
            if spent >= budget
            else ("warning" if spent >= budget * Decimal(warning_percent) / 100 else "below")
        )
    unknown = sum(r["estimated_cost_usd"] is None for r in rows)
    return {
        "budget_usd": str(budget) if budget is not None else None,
        "estimated_cost_usd": str(spent),
        "unknown_cost_requests": unknown,
        "status": state,
        "remaining_estimate_usd": str(max(Decimal(0), budget - spent))
        if budget is not None
        else None,
        "complete_estimate": unknown == 0,
    }


def current_budgets(registry, clock=None):
    month = (clock or datetime.now(UTC)).strftime("%Y-%m")
    with registry.store.connect() as db:
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM usage_events WHERE substr(started_at,1,7)=?", (month,)
            )
        ]
    prefs = registry.preferences()
    return {
        "month_utc": month,
        "advisory_only": True,
        "workspace": budget_status(rows, prefs.monthly_budget_usd, prefs.budget_warning_percent),
        "models": [
            {
                "model_id": m["id"],
                "name": m["name"],
                **budget_status(
                    [r for r in rows if r["model_id"] == m["id"]],
                    m.get("monthly_budget_usd"),
                    prefs.budget_warning_percent,
                ),
            }
            for m in registry.list()
        ],
    }
