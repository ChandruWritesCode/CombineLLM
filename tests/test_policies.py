import asyncio
from contextlib import aclosing

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.model_api import TrackedProvider
from app.policies import cool_down, is_local, remaining, retry_delay
from app.providers.base import ProviderError
from app.providers.gemini import GeminiProvider
from app.schemas import ChatRequest, Message
from app.storage import Store


def test_retry_header_and_diagnostics():
    assert retry_delay("120") == 120
    assert retry_delay("invalid") == 60
    assert retry_delay("999999") == 86400
    with pytest.raises(ProviderError) as error:
        GeminiProvider._check_status(429, "90")
    assert error.value.retry_after == 90


def test_shared_cooldown_persists_and_skips_network(tmp_path):
    store = Store(str(tmp_path / "test.sqlite3"))
    calls = []

    class Limited:
        name = "openai"
        model = "test"

        async def stream(self, request):
            calls.append(1)
            raise ProviderError("provider_rate_limited", "Rate limited", 429, retry_after=30)
            yield

    async def run():
        for mid, code in [("one", "provider_rate_limited"), ("two", "provider_cooldown")]:
            provider = TrackedProvider(
                Limited(), store, {"id": mid, "usage_group": "shared"}, "test"
            )
            with pytest.raises(ProviderError) as error:
                async with aclosing(
                    provider.stream(ChatRequest(messages=[Message(role="user", content="hi")]))
                ) as stream:
                    async for _ in stream:
                        pass
            assert error.value.code == code

    asyncio.run(run())
    assert len(calls) == 1
    assert remaining(Store(store.path), "group:shared") > 0
    assert remaining(store, "model:unrelated") == 0
    with store.connect() as db:
        assert [
            r[0] for r in db.execute("SELECT status FROM usage_events ORDER BY started_at")
        ] == ["failed", "skipped"]


def test_local_policy_and_fallback_permission():
    assert is_local({"kind": "ollama", "base_url": "http://localhost:11434/v1"})
    assert not is_local({"kind": "compatible", "base_url": "https://api.groq.com/openai/v1"})
    with TestClient(create_app(Settings(_env_file=None))) as client:
        ids = []
        for name in ["a", "b"]:
            ids.append(
                client.post(
                    "/api/v1/models",
                    json={"name": name, "kind": "openai", "model": name, "allow_fallback": False},
                ).json()["id"]
            )
        client.put(
            "/api/v1/settings", json={"default_model_id": ids[0], "fallback_model_ids": [ids[1]]}
        )
        body = {"messages": [{"role": "user", "content": "hi"}]}
        assert client.post("/api/v1/chat", json={**body, "local_only": True}).status_code == 422
        assert client.post("/api/v1/chat", json={**body, "fallback": True}).status_code == 422
        assert client.get("/api/v1/usage").json()["requests"] == 0
        cool_down(client.app.state.store, "group:demo", 60)


def test_chat_attempt_details_and_group_summary(monkeypatch):
    import time

    from app.providers.base import ProviderEvent
    from app.schemas import Usage

    class Provider:
        def __init__(self, config, key):
            self.name = config["kind"]
            self.model = config["model"]

        async def stream(self, request):
            yield ProviderEvent("delta", text="Policy test answer")
            yield ProviderEvent("done", finish_reason="STOP", usage=Usage(total_tokens=12))

    monkeypatch.setattr("app.model_api.APIProvider", Provider)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        mid = client.post(
            "/api/v1/models",
            json={
                "name": "Local test",
                "kind": "compatible",
                "model": "test",
                "base_url": "http://localhost:9999/v1",
                "usage_group": "account",
            },
        ).json()["id"]
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        path = "/api/v1/conversations/" + cid
        assert (
            client.post(
                path + "/messages", json={"content": "hello", "model_id": mid, "local_only": True}
            ).status_code
            == 202
        )
        for _ in range(100):
            chat = client.get(path).json()
            if chat["messages"][-1]["status"] != "streaming":
                break
            time.sleep(0.01)
        answer = chat["messages"][-1]
        assert answer["attempts"][0]["label"] == "Local test"
        assert answer["attempts"][0]["status"] == "complete"
        groups = client.get("/api/v1/usage-groups").json()
        assert groups[0]["name"] == "account"
        assert groups[0]["reported_tokens"] == 12
        assert client.get("/api/v1/usage").json()["skipped"] == 0
