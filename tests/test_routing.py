import asyncio
import time
from contextlib import aclosing

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_api import TrackedProvider
from app.providers.base import ProviderError, ProviderEvent
from app.routing import FallbackProvider
from app.schemas import ChatRequest, Message, Usage
from app.storage import Store


class Fake:
    name = "compatible"

    def __init__(self, model="good", key=""):
        self.model = model["model"] if isinstance(model, dict) else model
        self.requests = []
        self.closed = False

    async def stream(self, request):
        self.requests.append(request)
        try:
            if self.model == "partial":
                yield ProviderEvent("delta", text="Partial")
            if self.model == "slow":
                await asyncio.sleep(30)
            if self.model in {"busy", "partial"}:
                raise ProviderError("provider_unavailable", "Unavailable")
            if self.model in {"auth", "blocked"}:
                raise ProviderError(
                    "provider_auth_error" if self.model == "auth" else "content_blocked", "Rejected"
                )
            yield ProviderEvent("delta", text="Answer")
            yield ProviderEvent(
                "done",
                finish_reason="STOP",
                usage=Usage(input_tokens=10, output_tokens=2, total_tokens=12),
            )
        finally:
            self.closed = True


def chain(tmp_path, names):
    store = Store(str(tmp_path / "routing.sqlite3"))
    providers = [
        TrackedProvider(
            Fake(name), store, {"id": name, "name": name, "max_output_tokens": 100}, "chat"
        )
        for name in names
    ]
    return FallbackProvider(providers), store


def request():
    return ChatRequest(messages=[Message(role="user", content="Hi")])


def test_fallback_success_tracks_every_attempt(tmp_path):
    router, store = chain(tmp_path, ["busy", "good"])

    async def run():
        async with aclosing(router.stream(request())) as events:
            return [event async for event in events]

    result = asyncio.run(run())
    assert result[-1].kind == "done"
    assert router.model == "good"
    assert router.model_id == "busy"
    assert router.response_model_id == "good"
    with store.connect() as db:
        rows = db.execute("SELECT * FROM usage_events ORDER BY attempt_number").fetchall()
    assert [r["status"] for r in rows] == ["failed", "complete"]
    assert rows[0]["attempt_group_id"] == rows[1]["attempt_group_id"]
    assert [r["attempt_number"] for r in rows] == [1, 2]
    assert all(p.provider.closed for p in router.providers)
    assert router.providers[1].provider.requests[0].max_output_tokens == 100


@pytest.mark.parametrize("first", ["partial", "auth", "blocked"])
def test_no_fallback_after_text_or_nontransient_error(tmp_path, first):
    router, store = chain(tmp_path, [first, "good"])

    async def run():
        with pytest.raises(ProviderError):
            async for _ in router.stream(request()):
                pass

    asyncio.run(run())
    assert not router.providers[1].provider.requests
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM usage_events").fetchone()[0] == 1


def test_cancellation_never_falls_back(tmp_path):
    router, store = chain(tmp_path, ["slow", "good"])

    async def run():
        async def consume():
            async for _ in router.stream(request()):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert router.providers[0].provider.closed
    assert not router.providers[1].provider.requests
    with store.connect() as db:
        assert db.execute("SELECT status FROM usage_events").fetchone()[0] == "cancelled"


def test_overall_deadline_stops_chain(tmp_path, monkeypatch):
    router, _ = chain(tmp_path, ["slow", "good"])
    monkeypatch.setattr("app.routing.CHAIN_TIMEOUT_SECONDS", 0.01)

    async def run():
        with pytest.raises(ProviderError, match="Fallback time limit"):
            async for _ in router.stream(request()):
                pass

    asyncio.run(run())
    assert not router.providers[1].provider.requests
    assert router.providers[0].provider.closed


def test_all_models_fail_once(tmp_path):
    router, store = chain(tmp_path, ["busy", "busy"])

    async def run():
        with pytest.raises(ProviderError, match="Unavailable"):
            async for _ in router.stream(request()):
                pass

    asyncio.run(run())
    assert all(len(p.provider.requests) == 1 for p in router.providers)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM usage_events").fetchone()[0] == 2


def test_saved_chat_opt_in_attribution_and_preflight(monkeypatch):
    monkeypatch.setattr("app.model_api.APIProvider", Fake)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        ids = []
        for model in ["busy", "good"]:
            r = client.post(
                "/api/v1/models",
                json={
                    "name": model,
                    "kind": "compatible",
                    "model": model,
                    "base_url": "http://localhost:9999/v1",
                },
            )
            ids.append(r.json()["id"])
        assert (
            client.put(
                "/api/v1/settings",
                json={"default_model_id": ids[0], "fallback_model_ids": [ids[1]]},
            ).status_code
            == 200
        )
        body = {"messages": [{"role": "user", "content": "Hi"}]}
        assert client.post("/api/v1/chat", json=body).status_code == 502
        assert client.get("/api/v1/usage").json()["requests"] == 1
        response = client.post("/api/v1/chat", json={**body, "fallback": True})
        assert response.status_code == 200
        assert response.json()["model"] == "good"
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        path = f"/api/v1/conversations/{cid}"
        assert (
            client.post(path + "/messages", json={"content": "Hi", "fallback": True}).status_code
            == 202
        )
        for _ in range(100):
            saved = client.get(path).json()
            if saved["messages"][-1]["status"] != "streaming":
                break
            time.sleep(0.01)
        assert saved["model_id"] == ids[0]
        assert saved["messages"][-1]["model_id"] == ids[1]
        assert saved["messages"][-1]["model"] == "good"
        assert saved["messages"][-1]["status"] == "complete"
        assert (
            client.put("/api/v1/settings", json={"fallback_model_ids": [ids[1]] * 2}).status_code
            == 422
        )
        assert (
            client.put("/api/v1/settings", json={"fallback_model_ids": [ids[1]] * 4}).status_code
            == 422
        )
        # A disabled fallback rejects the whole chain before spending on the primary.
        config = client.get("/api/v1/models").json()[1]
        for key in ["id", "has_key", "auth_method", "created_at"]:
            config.pop(key)
        config["enabled"] = False
        client.put(f"/api/v1/models/{ids[1]}", json=config)
        count = client.get("/api/v1/usage").json()["requests"]
        assert client.post("/api/v1/chat", json={**body, "fallback": True}).status_code == 422
        assert client.get("/api/v1/usage").json()["requests"] == count
        assert client.delete(f"/api/v1/models/{ids[1]}").status_code == 204
        assert client.get("/api/v1/settings").json()["fallback_model_ids"] == []


def test_v3_migration_preserves_legacy_usage(tmp_path):
    path = str(tmp_path / "migration.sqlite3")
    store = Store(path)
    with store.connect() as db:
        db.execute(
            "INSERT INTO usage_events (id,source,status,started_at,estimated_cost_usd) "
            "VALUES ('old','chat','complete','2026-01-01','0.1')"
        )
        db.execute("ALTER TABLE usage_events DROP COLUMN attempt_group_id")
        db.execute("ALTER TABLE usage_events DROP COLUMN attempt_number")
        db.execute("DROP TABLE cooldowns")
        db.execute("ALTER TABLE messages DROP COLUMN attempt_group_id")
        for column in [
            "coordination_mode",
            "coordination_stage",
            "rating",
            "selection_mode",
            "selection_reason",
        ]:
            db.execute(f"ALTER TABLE messages DROP COLUMN {column}")
        db.execute("ALTER TABLE usage_events DROP COLUMN usage_group")
        db.execute("PRAGMA user_version=3")
    store = Store(path)
    with store.connect() as db:
        row = db.execute("SELECT * FROM usage_events").fetchone()
        assert row["estimated_cost_usd"] == "0.1"
        assert row["attempt_group_id"] is None
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
