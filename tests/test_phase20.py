"""Phase 20 routing and quota behavior with simulated providers and isolated storage."""

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.quota import parse_headers
from tests.test_coordination import FakeModel, wait_for_answer


def test_quota_headers_are_sanitized_and_last_observation_is_saved(monkeypatch):
    signal = parse_headers(
        {
            "x-ratelimit-remaining-requests": "0",
            "x-ratelimit-reset-requests": "2m59.56s",
            "x-ratelimit-remaining-tokens": "1400",
            "Authorization": "secret",
        }
    )
    assert signal["remaining_requests"] == 0
    assert signal["requests_reset_at"]
    assert "secret" not in str(signal)
    assert parse_headers({"x-ratelimit-remaining-requests": "unlimited"}) is None

    def respond(_):
        return httpx.Response(
            200,
            headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "1m"},
            text=(
                'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n"
            ),
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        "app.providers.compatible.httpx.AsyncClient",
        lambda **kw: original(**{**kw, "transport": httpx.MockTransport(respond)}),
    )
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        model = client.post(
            "/api/v1/models",
            json={
                "name": "quota",
                "kind": "compatible",
                "model": "quota",
                "base_url": "http://localhost:9999/v1",
            },
        ).json()
        tested = client.post("/api/v1/models/%s/test" % model["id"])
        assert tested.status_code == 200, tested.json()
        observed = client.get("/api/v1/quota").json()["models"][0]["signal"]
        assert observed["remaining_requests"] == 0
        assert client.get("/api/v1/recommendations").json()["models"][0]["quota_warning"]


def test_profile_preview_and_split_calls(monkeypatch):
    FakeModel.requests = []
    monkeypatch.setattr("app.model_api.APIProvider", FakeModel)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        for name in ("alpha", "beta"):
            response = client.post(
                "/api/v1/models",
                json={
                    "name": name,
                    "kind": "compatible",
                    "model": name,
                    "base_url": "http://localhost:9999/v1",
                    "input_price_per_million": "1",
                    "output_price_per_million": "1",
                },
            )
            assert response.status_code == 201
        saved = client.put(
            "/api/v1/settings",
            json={
                "routing_profiles": [
                    {
                        "name": "research",
                        "mode": "split",
                        "priority": "balanced",
                        "max_calls": 4,
                        "max_estimated_cost_usd": "1",
                    }
                ]
            },
        )
        assert saved.status_code == 200
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        preview = client.get(
            "/api/v1/routing/preview",
            params={"profile": "research", "conversation_id": cid, "input_chars": 10},
        ).json()
        assert preview["calls"] == 4
        assert preview["collaborator_model_id"]
        assert not FakeModel.requests
        sent = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={
                "content": "Compare two options",
                "auto_select": True,
                "routing_profile": "research",
            },
        )
        assert sent.status_code == 202
        answer = wait_for_answer(client, cid)
        assert answer["status"] == "complete"
        assert answer["coordination_mode"] == "split"
        assert answer["selection_mode"] == "automatic"
        assert len(FakeModel.requests) == 4
        assert client.get("/api/v1/usage").json()["requests"] == 4


def test_profile_cost_preflight_blocks_calls(monkeypatch):
    FakeModel.requests = []
    monkeypatch.setattr("app.model_api.APIProvider", FakeModel)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        client.post(
            "/api/v1/models",
            json={
                "name": "priced",
                "kind": "compatible",
                "model": "priced",
                "base_url": "http://localhost:9999/v1",
                "input_price_per_million": "100",
                "output_price_per_million": "100",
            },
        )
        assert (
            client.put(
                "/api/v1/settings",
                json={
                    "routing_profiles": [
                        {"name": "capped", "max_calls": 1, "max_estimated_cost_usd": "0"}
                    ]
                },
            ).status_code
            == 200
        )
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "Hello", "auto_select": True, "routing_profile": "capped"},
        )
        assert response.status_code == 422
        override = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={
                "content": "Hello",
                "auto_select": True,
                "routing_profile": "capped",
                "max_output_tokens": 8192,
            },
        )
        assert override.status_code == 422
        assert not FakeModel.requests
        assert client.get("/api/v1/usage").json()["requests"] == 0
