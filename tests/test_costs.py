import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.connections import Connection, Connections, Preferences
from app.costs import budget_status, current_budgets, estimate
from app.main import create_app
from app.model_api import TrackedProvider
from app.providers.base import ProviderEvent
from app.schemas import ChatRequest, Message, Usage
from app.storage import Store


def test_exact_estimates_and_unknown_usage():
    assert Decimal(estimate(Usage(input_tokens=123, output_tokens=456), "0.1", "0.2")) == Decimal(
        "0.0001035"
    )
    assert estimate(Usage(total_tokens=100), "1", "2") is None
    assert estimate(Usage(input_tokens=1, output_tokens=2), None, "0") is None
    assert estimate(Usage(input_tokens=1, output_tokens=2), "0", "0") == "0"
    assert estimate(Usage(input_tokens=-1, output_tokens=2), "1", "1") is None


@pytest.mark.parametrize(
    "limit,status",
    [(None, "not_set"), ("10", "warning"), ("8", "exceeded"), ("20", "below"), ("0", "exceeded")],
)
def test_budget_boundaries_and_unknowns(limit, status):
    result = budget_status([{"estimated_cost_usd": "8"}, {"estimated_cost_usd": None}], limit, 80)
    assert result["status"] == status
    assert result["unknown_cost_requests"] == 1
    assert not result["complete_estimate"]


def test_price_snapshot_and_deleted_model_budget(tmp_path):
    store = Store(str(tmp_path / "cost.sqlite3"))
    registry = Connections(store)
    cfg = Connection(
        name="Simulated",
        kind="openai",
        model="test",
        input_price_per_million="2",
        output_price_per_million="4",
        monthly_budget_usd="0.01",
    )
    model = registry.save(cfg)
    registry.save_preferences(Preferences(monthly_budget_usd="0.005"))

    class Fake:
        name = "openai"
        model = "test"

        async def stream(self, request):
            registry.save(
                cfg.model_copy(update={"input_price_per_million": Decimal("999")}), model["id"]
            )
            yield ProviderEvent(
                "done", usage=Usage(input_tokens=1000, output_tokens=1000, total_tokens=2000)
            )

    async def run():
        tracker = TrackedProvider(Fake(), store, model, "chat")
        async for _ in tracker.stream(ChatRequest(messages=[Message(role="user", content="hi")])):
            pass

    asyncio.run(run())
    with store.connect() as db:
        row = db.execute("SELECT * FROM usage_events").fetchone()
        assert Decimal(row["estimated_cost_usd"]) == Decimal("0.006")
        assert row["input_price_per_million"] == "2"
        db.execute(
            "INSERT INTO usage_events (id,source,status,started_at,estimated_cost_usd) "
            "VALUES ('old','chat','complete','2000-01-01','100')"
        )
    budgets = current_budgets(registry)
    assert budgets["workspace"]["status"] == "exceeded"
    assert budgets["models"][0]["status"] == "below"
    registry.delete(model["id"])
    assert Decimal(current_budgets(registry)["workspace"]["estimated_cost_usd"]) == Decimal("0.006")
    assert (
        current_budgets(registry, datetime(2000, 2, 1, tzinfo=UTC))["workspace"][
            "estimated_cost_usd"
        ]
        == "0"
    )


def test_cost_api_validation_and_advisory_behavior():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        for bad in ["NaN", "Infinity", "-1", "1000001"]:
            assert (
                client.put("/api/v1/settings", json={"monthly_budget_usd": bad}).status_code == 422
            )
        assert client.put("/api/v1/settings", json={"monthly_budget_usd": "0"}).status_code == 200
        budgets = client.get("/api/v1/budgets").json()
        assert budgets["advisory_only"]
        assert budgets["workspace"]["status"] == "exceeded"
        assert client.get("/api/v1/usage").json()["estimated_cost_usd"] == "0"
        assert "estimated_cost_usd" in client.get("/api/v1/usage/export").text


def test_v2_migration_does_not_backfill_costs(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    store = Store(path)
    with store.connect() as db:
        db.execute(
            "INSERT INTO usage_events (id,source,status,started_at,total_tokens) "
            "VALUES ('old','chat','complete','2000-01-01',100)"
        )
        for column in ["input_price_per_million", "output_price_per_million", "estimated_cost_usd"]:
            db.execute(f"ALTER TABLE usage_events DROP COLUMN {column}")
        db.execute("PRAGMA user_version=2")
    store = Store(path)
    with store.connect() as db:
        row = db.execute("SELECT * FROM usage_events").fetchone()
        assert row["total_tokens"] == 100
        assert row["estimated_cost_usd"] is None
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3


def test_selected_models_history_costs_and_advisory_budget(monkeypatch):
    import time

    captured = []

    class Fake:
        def __init__(self, config, key):
            self.name = config["kind"]
            self.model = config["model"]

        async def stream(self, request):
            captured.append((self.model, request))
            yield ProviderEvent("delta", text="Simulated answer")
            yield ProviderEvent(
                "done",
                finish_reason="STOP",
                usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            )

    monkeypatch.setattr("app.model_api.APIProvider", Fake)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        client.put("/api/v1/settings", json={"monthly_budget_usd": "0"})
        ids = []
        for model in ["first", "second"]:
            response = client.post(
                "/api/v1/models",
                json={
                    "name": model,
                    "kind": "openai",
                    "model": model,
                    "input_price_per_million": "1",
                    "output_price_per_million": "2",
                },
            )
            assert response.status_code == 201
            ids.append(response.json()["id"])
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        path = f"/api/v1/conversations/{cid}"
        for mid in [ids[0], ids[1], None]:
            body = {"content": "Hello"}
            if mid:
                body["model_id"] = mid
            assert client.post(path + "/messages", json=body).status_code == 202
            for _ in range(200):
                chat = client.get(path).json()
                if chat["messages"][-1]["status"] != "streaming":
                    break
                time.sleep(0.01)
            assert chat["messages"][-1]["status"] == "complete"
        assert [m for m, _ in captured] == ["first", "second", "second"]
        assert len(captured[-1][1].messages) == 5
        assert chat["model_id"] == ids[1]
        usage = client.get("/api/v1/usage").json()
        assert usage["requests"] == 3
        assert Decimal(usage["estimated_cost_usd"]) == Decimal("0.00006")
        assert usage["unknown_cost_requests"] == 0
        assert client.delete(path).status_code == 204
        assert client.get("/api/v1/usage").json()["requests"] == 3
