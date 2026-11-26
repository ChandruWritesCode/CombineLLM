import asyncio
import json
import sqlite3
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.connections import Connection, Connections
from app.main import create_app
from app.model_api import TrackedProvider
from app.providers.base import ProviderError, ProviderEvent
from app.providers.compatible import APIProvider
from app.schemas import ChatRequest, Message, Usage
from app.storage import Store


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        yield client


def config(**changes):
    return {"name": "Test", "kind": "openai", "model": "test-model", **changes}


def test_registry_credentials_and_destinations(client):
    body = config(api_key="test-private-credential")
    result = client.post("/api/v1/models", json=body)
    assert result.status_code == 201
    assert "test-private-credential" not in result.text
    mid = result.json()["id"]
    registry = client.app.state.connections
    assert registry.secret(mid) == body["api_key"]
    with registry.store.connect() as db:
        assert (
            body["api_key"]
            not in db.execute(
                "SELECT credential FROM model_connections WHERE id=?", (mid,)
            ).fetchone()[0]
        )
    assert client.put(f"/api/v1/models/{mid}", json=config()).status_code == 200
    assert registry.secret(mid) == body["api_key"]
    changed = config(kind="compatible", base_url="https://example.com/v1")
    assert client.put(f"/api/v1/models/{mid}", json=changed).status_code == 422
    assert (
        client.put(f"/api/v1/models/{mid}", json={**changed, "clear_key": True}).status_code == 200
    )
    assert registry.secret(mid) == ""
    for number in range(12):
        assert client.post("/api/v1/models", json=config(name=str(number))).status_code == 201
    assert len(client.get("/api/v1/models").json()) == 13
    assert client.delete(f"/api/v1/models/{mid}").status_code == 204
    assert client.get("/api/v1/models").headers["cache-control"] == "no-store"


def test_invalid_secrets_and_cross_origin(client):
    response = client.post("/api/v1/models", json=config(api_key="private\nsecret"))
    assert response.status_code == 422
    assert "private" not in response.text
    assert (
        client.post(
            "/api/v1/models", json=config(), headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/models", json=config(kind="compatible", base_url="http://example.com")
        ).status_code
        == 422
    )


def test_disabled_and_deleted_selection_never_falls_back(client):
    mid = client.post("/api/v1/models", json=config(enabled=False)).json()["id"]
    request = {"model_id": mid, "messages": [{"role": "user", "content": "hello"}]}
    assert client.post("/api/v1/chat", json=request).status_code == 422
    client.delete(f"/api/v1/models/{mid}")
    assert client.post("/api/v1/chat", json=request).status_code == 404


@pytest.mark.parametrize("failure", [False, True])
def test_tracked_usage_filters_and_retention(client, failure):
    class Fake:
        name = "openai"
        model = "simulated"

        async def stream(self, request):
            yield ProviderEvent("delta", text="hello")
            if failure:
                raise ProviderError("provider_unavailable", "Unavailable")
            yield ProviderEvent("done", usage=Usage(total_tokens=7))

    async def run():
        provider = TrackedProvider(
            Fake(), client.app.state.store, {"id": "one", "name": "=formula"}, "chat"
        )
        try:
            async for _ in provider.stream(
                ChatRequest(messages=[Message(role="user", content="hello")])
            ):
                pass
        except ProviderError:
            pass

    asyncio.run(run())
    result = client.get("/api/v1/usage").json()
    assert result["requests"] == 1
    assert result["failed"] == int(failure)
    assert result["unknown_usage"] == int(failure)
    assert result["reported_tokens"] == (0 if failure else 7)
    assert client.get("/api/v1/usage?model_id=other").json()["requests"] == 0
    assert client.get("/api/v1/usage?start=2100-01-01").json()["requests"] == 0
    assert client.get("/api/v1/usage?start=2100-01-01&end=2000-01-01").status_code == 422
    assert "'=formula" in client.get("/api/v1/usage/export").text


def test_pkce_exchange_and_replay(client, monkeypatch):
    mid = client.post("/api/v1/models", json=config(kind="openrouter")).json()["id"]
    url = client.post(f"/api/v1/oauth/openrouter/{mid}/start").json()["url"]
    query = parse_qs(urlsplit(url).query)
    assert query["code_challenge_method"] == ["S256"]
    callback = query["callback_url"][0]
    state = parse_qs(urlsplit(callback).query)["state"][0]
    original = httpx.AsyncClient

    def exchange(request):
        payload = json.loads(request.content)
        assert payload["code_verifier"] == client.app.state.oauth_pending.get(state, {}).get(
            "verifier", verifier
        )
        return httpx.Response(200, json={"key": "issued-private-key"})

    verifier = client.app.state.oauth_pending[state]["verifier"]
    monkeypatch.setattr(
        "app.oauth.httpx.AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(exchange), **kw),
    )
    path = f"/api/v1/oauth/openrouter/callback?state={state}&code=test"
    assert client.get(path.replace(state, "wrong"), follow_redirects=False).status_code == 400
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/settings?login=connected"
    assert client.app.state.connections.secret(mid) == "issued-private-key"
    assert "issued-private-key" not in client.get("/api/v1/models").text
    assert client.get(path, follow_redirects=False).status_code == 400


def test_migration_preserves_v1_chat(tmp_path):
    path = tmp_path / "v1.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE conversations (id TEXT PRIMARY KEY,title TEXT,created_at TEXT,updated_at TEXT);
        CREATE TABLE messages (seq INTEGER PRIMARY KEY,id TEXT,conversation_id TEXT,role TEXT,
          content TEXT,status TEXT,provider TEXT,model TEXT,finish_reason TEXT,
          usage TEXT,error TEXT,created_at TEXT);
        INSERT INTO conversations VALUES ('chat','Old chat','2020','2020');
        INSERT INTO messages VALUES
          (1,'msg','chat','user','Keep me','complete',NULL,NULL,NULL,NULL,NULL,'2020');
        PRAGMA user_version=1;
        """)
    store = Store(str(path))
    assert store.get("chat")["messages"][0]["content"] == "Keep me"
    assert store.get("chat")["model_id"] is None


def test_missing_encryption_key_fails_closed(tmp_path):
    store = Store(str(tmp_path / "db.sqlite3"))
    registry = Connections(store)
    registry.save(Connection(**config(api_key="private")))
    (tmp_path / "db.key").unlink()
    with pytest.raises(RuntimeError, match="key is missing"):
        Connections(store)


@pytest.mark.parametrize("kind", ["openai", "anthropic", "ollama"])
def test_adapter_streams_and_usage(kind):
    cfg = Connection(
        **config(kind=kind, base_url="http://localhost:11434/v1" if kind == "ollama" else "")
    ).model_dump()
    cfg["id"] = "model"
    if kind == "anthropic":
        events = [
            {"type": "message_start", "message": {"usage": {"input_tokens": 3}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 2},
            },
            {"type": "message_stop"},
        ]
    else:
        events = [
            {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            {
                "choices": [],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        ]
    content = "".join("data: " + json.dumps(e) + "\n\n" for e in events)
    if kind != "anthropic":
        content += "data: [DONE]\n\n"

    def respond(request):
        assert json.loads(request.content)["model"] == "test-model"
        return httpx.Response(200, text=content)

    async def run():
        provider = APIProvider(cfg, "test-key", httpx.MockTransport(respond))
        return [
            e
            async for e in provider.stream(
                ChatRequest(messages=[Message(role="user", content="Hi")])
            )
        ]

    result = asyncio.run(run())
    assert result[0].text == "Hello"
    assert result[-1].usage.total_tokens == 5
