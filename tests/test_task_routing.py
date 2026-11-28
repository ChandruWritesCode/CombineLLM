"""Task-aware automatic routing uses user hints without hidden provider calls."""

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderEvent
from app.schemas import Usage


class FakeModel:
    calls = []

    def __init__(self, config, key):
        self.name = "compatible"
        self.model = config["model"]

    async def stream(self, request):
        self.calls.append(self.model)
        yield ProviderEvent("delta", text=self.model)
        yield ProviderEvent("done", finish_reason="STOP", usage=Usage(total_tokens=2))


def wait_for_answer(client, conversation_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        answer = client.get(f"/api/v1/conversations/{conversation_id}").json()["messages"][-1]
        if answer["status"] != "streaming":
            return answer
        time.sleep(0.01)
    raise AssertionError("Answer did not finish")


def test_task_hint_and_context_limit_change_one_call_choice(monkeypatch):
    FakeModel.calls = []
    monkeypatch.setattr("app.model_api.APIProvider", FakeModel)
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        ids = {}
        for model, price, tags, limit in (
            ("code", "10", ["code"], 1000),
            ("cheap", "1", ["writing"], 5000),
        ):
            result = client.post(
                "/api/v1/models",
                json={
                    "name": model,
                    "kind": "compatible",
                    "model": model,
                    "base_url": "http://localhost:9999/v1",
                    "input_price_per_million": price,
                    "output_price_per_million": price,
                    "task_tags": tags,
                    "context_limit_chars": limit,
                },
            )
            assert result.status_code == 201
            ids[model] = result.json()["id"]

        ranked = client.get("/api/v1/recommendations?task_hint=code&input_chars=100").json()
        assert ranked["suggested_model_id"] == ids["code"]
        too_long = client.get("/api/v1/recommendations?task_hint=code&input_chars=1100").json()
        assert too_long["suggested_model_id"] == ids["cheap"]
        code = next(item for item in too_long["models"] if item["model_id"] == ids["code"])
        assert not code["eligible"]
        assert any("context limit" in reason for reason in code["reasons"])

        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        sent = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "Write a function", "auto_select": True, "task_hint": "code"},
        )
        assert sent.status_code == 202
        answer = wait_for_answer(client, cid)
        assert answer["model_id"] == ids["code"]
        assert "code" in answer["selection_reason"]
        assert FakeModel.calls == ["code"]
        assert client.get("/api/v1/usage").json()["requests"] == 1

        follow_up = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "x" * 990, "auto_select": True, "task_hint": "code"},
        )
        assert follow_up.status_code == 202
        answer = wait_for_answer(client, cid)
        assert answer["model_id"] == ids["cheap"]
        assert FakeModel.calls == ["code", "cheap"]
        assert client.get("/api/v1/usage").json()["requests"] == 2


def test_invalid_task_hint_rejected_before_generation():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        cid = client.post("/api/v1/conversations", json={}).json()["id"]
        result = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={"content": "Question", "auto_select": True, "task_hint": "magic"},
        )
        assert result.status_code == 422
        assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []
