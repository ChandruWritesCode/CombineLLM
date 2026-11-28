"""Local request ceilings reserve before sending and use isolated SQLite files."""

import asyncio
from contextlib import aclosing

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_api import TrackedProvider
from app.providers.base import ProviderError, ProviderEvent
from app.schemas import ChatRequest, Message, Usage
from app.storage import Store


class Fake:
    calls = 0

    def __init__(self, config=None, key=""):
        self.name = "compatible"
        self.model = config["model"] if config else "test"

    async def stream(self, request):
        Fake.calls += 1
        await asyncio.sleep(0.02)
        yield ProviderEvent("delta", text="Hello")
        yield ProviderEvent("done", finish_reason="STOP", usage=Usage(total_tokens=12))


def test_concurrent_calls_reserve_one_model_slot(tmp_path):
    Fake.calls = 0
    store = Store(str(tmp_path / "limits.sqlite3"))
    providers = [
        TrackedProvider(
            Fake(),
            store,
            {
                "id": "one",
                "name": "One",
                "monthly_request_limit": 1,
            },
            "saved_chat",
        )
        for _ in range(2)
    ]
    request = ChatRequest(messages=[Message(role="user", content="Hi")])

    async def consume(provider):
        async with aclosing(provider.stream(request)) as events:
            return [event async for event in events]

    async def run():
        return await asyncio.gather(*(consume(p) for p in providers), return_exceptions=True)

    outcomes = asyncio.run(run())
    assert sum(isinstance(item, ProviderError) for item in outcomes) == 1
    assert Fake.calls == 1
    with store.connect() as db:
        rows = db.execute("SELECT status,error_code FROM usage_events ORDER BY status").fetchall()
    assert [(r["status"], r["error_code"]) for r in rows] == [
        ("complete", None),
        ("skipped", "local_request_limit"),
    ]


def test_workspace_ceiling_counts_tests_and_blocks_later_requests(monkeypatch):
    Fake.calls = 0
    monkeypatch.setattr("app.model_api.APIProvider", Fake)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        ids = []
        for name in ("one", "two"):
            result = client.post(
                "/api/v1/models",
                json={
                    "name": name,
                    "kind": "compatible",
                    "model": name,
                    "base_url": "http://localhost:9999/v1",
                    "monthly_request_limit": 1,
                },
            )
            assert result.status_code == 201
            ids.append(result.json()["id"])
        assert (
            client.put(
                "/api/v1/settings",
                json={
                    "monthly_request_limit": 2,
                },
            ).status_code
            == 200
        )
        assert client.post(f"/api/v1/models/{ids[0]}/test").status_code == 200
        body = {"messages": [{"role": "user", "content": "Hi"}], "model_id": ids[1]}
        assert client.post("/api/v1/chat", json=body).status_code == 200
        blocked = client.post("/api/v1/chat", json=body)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "local_request_limit"
        assert Fake.calls == 2
        limits = client.get("/api/v1/limits").json()
        assert limits["workspace"]["count"] == 2
        assert limits["workspace"]["reached"]
        assert [model["count"] for model in limits["models"]] == [1, 1]
        comparison = client.get("/api/v1/recommendations").json()
        assert comparison["suggested_model_id"] is None
        assert all(not model["eligible"] for model in comparison["models"])
        assert client.get("/api/v1/usage").json()["skipped"] == 1
        assert client.get("/api/v1/usage").json()["unknown_cost_requests"] == 2
        assert client.get("/api/v1/budgets").json()["workspace"]["unknown_cost_requests"] == 2
        assert (
            client.put(
                "/api/v1/settings",
                json={
                    "monthly_request_limit": 0,
                },
            ).status_code
            == 422
        )


def test_model_ceiling_does_not_block_another_model(monkeypatch):
    Fake.calls = 0
    monkeypatch.setattr("app.model_api.APIProvider", Fake)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        ids = []
        for name in ("one", "two"):
            ids.append(
                client.post(
                    "/api/v1/models",
                    json={
                        "name": name,
                        "kind": "compatible",
                        "model": name,
                        "base_url": "http://localhost:9999/v1",
                        "monthly_request_limit": 1,
                    },
                ).json()["id"]
            )
        body = {"messages": [{"role": "user", "content": "Hi"}]}
        assert client.post("/api/v1/chat", json={**body, "model_id": ids[0]}).status_code == 200
        assert client.post("/api/v1/chat", json={**body, "model_id": ids[0]}).status_code == 429
        assert client.post("/api/v1/chat", json={**body, "model_id": ids[1]}).status_code == 200
        assert Fake.calls == 2
