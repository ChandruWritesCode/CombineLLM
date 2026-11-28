"""Simulated coordination flows; no provider credentials or network calls."""

import asyncio
import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderError, ProviderEvent
from app.schemas import Usage
from app.storage import Store


class FakeModel:
    requests = []
    invalid_plan = False
    slow_review = False
    fail_review = False

    def __init__(self, config, key):
        self.name = "compatible"
        self.model = config["model"]

    async def stream(self, request):
        prompt = request.messages[-1].content
        self.requests.append((self.model, prompt))
        if "Split the latest user request" in prompt:
            answer = "First task\nSecond task" if self.invalid_plan else "1. Research\n2. Compare"
        elif "Review the draft" in prompt:
            if self.slow_review:
                await asyncio.sleep(30)
            if self.fail_review:
                raise ProviderError("provider_unavailable", "Review model unavailable.")
            answer = "Clarify the conclusion."
        elif "Work only on subtask" in prompt:
            answer = f"Findings from {self.model}"
        elif "Synthesize one coherent final answer" in prompt:
            answer = "Synthesized answer"
        elif "Write the final answer" in prompt:
            answer = "Revised answer"
        else:
            answer = "Draft answer"
        yield ProviderEvent("delta", text=answer)
        yield ProviderEvent(
            "done",
            finish_reason="STOP",
            usage=Usage(input_tokens=10, output_tokens=2, total_tokens=12),
        )


def configured_client(monkeypatch):
    FakeModel.requests = []
    FakeModel.invalid_plan = False
    FakeModel.slow_review = False
    FakeModel.fail_review = False
    monkeypatch.setattr("app.model_api.APIProvider", FakeModel)
    return TestClient(create_app(Settings(_env_file=None, environment="test")))


def setup(client):
    ids = []
    for model in ("writer", "critic"):
        response = client.post(
            "/api/v1/models",
            json={
                "name": model,
                "kind": "compatible",
                "model": model,
                "base_url": "http://localhost:9999/v1",
                "input_price_per_million": "1",
                "output_price_per_million": "1",
            },
        )
        assert response.status_code == 201
        ids.append(response.json()["id"])
    cid = client.post("/api/v1/conversations", json={}).json()["id"]
    return cid, ids


def wait_for_answer(client, cid):
    deadline = time.monotonic() + 3
    path = f"/api/v1/conversations/{cid}"
    while time.monotonic() < deadline:
        message = client.get(path).json()["messages"][-1]
        if message["status"] != "streaming":
            return message
        time.sleep(0.01)
    raise AssertionError("Coordinated answer did not finish")


def test_review_tracks_stages_costs_and_rating(monkeypatch):
    with configured_client(monkeypatch) as client:
        cid, ids = setup(client)
        path = f"/api/v1/conversations/{cid}/messages"
        response = client.post(
            path,
            json={
                "content": "Explain the result",
                "model_id": ids[0],
                "coordination": {"mode": "review", "collaborator_model_id": ids[1]},
            },
        )
        assert response.status_code == 202
        answer = wait_for_answer(client, cid)
        assert answer["status"] == "complete"
        assert answer["content"] == "Revised answer"
        assert answer["model_id"] == ids[0]
        assert answer["coordination_mode"] == "review"
        assert [a["source"] for a in answer["attempts"]] == [
            "coordination_draft",
            "coordination_review",
            "coordination_revision",
        ]
        assert [a["status"] for a in answer["attempts"]] == ["complete"] * 3
        assert sum(float(a["estimated_cost_usd"]) for a in answer["attempts"]) > 0
        assert [model for model, _ in FakeModel.requests] == ["writer", "critic", "writer"]
        rated = client.put(path + f"/{answer['id']}/rating", json={"rating": 4})
        assert rated.status_code == 200
        assert rated.json()["rating"] == 4
        assert client.get(f"/api/v1/conversations/{cid}").json()["messages"][-1]["rating"] == 4
        quality = client.get("/api/v1/quality").json()
        assert quality["groups"] == [{"mode": "review", "rated": 1, "average_rating": 4.0}]
        assert client.put(path + f"/{answer['id']}/rating", json={"rating": 6}).status_code == 422


def test_split_synthesizes_two_bounded_subtasks(monkeypatch):
    with configured_client(monkeypatch) as client:
        cid, ids = setup(client)
        response = client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={
                "content": "Compare these options",
                "model_id": ids[0],
                "coordination": {"mode": "split", "collaborator_model_id": ids[1]},
            },
        )
        assert response.status_code == 202
        answer = wait_for_answer(client, cid)
        assert answer["content"] == "Synthesized answer"
        assert [a["source"] for a in answer["attempts"]] == [
            "coordination_plan",
            "coordination_subtask_1",
            "coordination_subtask_2",
            "coordination_synthesis",
        ]
        assert [model for model, _ in FakeModel.requests] == [
            "writer",
            "writer",
            "critic",
            "writer",
        ]
        assert "Research" in FakeModel.requests[1][1]
        assert "Compare" in FakeModel.requests[2][1]


def test_preflight_rejects_invalid_roles_without_usage(monkeypatch):
    with configured_client(monkeypatch) as client:
        cid, ids = setup(client)
        path = f"/api/v1/conversations/{cid}/messages"
        base = {"content": "Question", "model_id": ids[0]}
        assert (
            client.post(
                path,
                json={**base, "coordination": {"mode": "review", "collaborator_model_id": ids[0]}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                path,
                json={
                    **base,
                    "fallback": True,
                    "coordination": {"mode": "review", "collaborator_model_id": ids[1]},
                },
            ).status_code
            == 422
        )
        assert client.get("/api/v1/usage").json()["requests"] == 0
        assert client.get(f"/api/v1/conversations/{cid}").json()["messages"] == []


def test_invalid_plan_stops_before_workers(monkeypatch):
    with configured_client(monkeypatch) as client:
        cid, ids = setup(client)
        FakeModel.invalid_plan = True
        client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={
                "content": "Question",
                "model_id": ids[0],
                "coordination": {"mode": "split", "collaborator_model_id": ids[1]},
            },
        )
        answer = wait_for_answer(client, cid)
        assert answer["status"] == "failed"
        assert len(answer["attempts"]) == 1
        assert len(FakeModel.requests) == 1


def test_review_failure_does_not_publish_draft(monkeypatch):
    with configured_client(monkeypatch) as client:
        cid, ids = setup(client)
        FakeModel.fail_review = True
        client.post(
            f"/api/v1/conversations/{cid}/messages",
            json={
                "content": "Question",
                "model_id": ids[0],
                "coordination": {"mode": "review", "collaborator_model_id": ids[1]},
            },
        )
        answer = wait_for_answer(client, cid)
        assert answer["status"] == "failed"
        assert answer["content"] == ""
        assert [a["status"] for a in answer["attempts"]] == ["complete", "failed"]
        assert len(FakeModel.requests) == 2


def test_cancellation_stops_review_and_skips_revision(monkeypatch):
    with configured_client(monkeypatch) as client:
        cid, ids = setup(client)
        FakeModel.slow_review = True
        path = f"/api/v1/conversations/{cid}/messages"
        mid = client.post(
            path,
            json={
                "content": "Question",
                "model_id": ids[0],
                "coordination": {"mode": "review", "collaborator_model_id": ids[1]},
            },
        ).json()["message_id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            current = client.get(f"/api/v1/conversations/{cid}").json()["messages"][-1]
            if current["coordination_stage"] == "Reviewing draft":
                break
            time.sleep(0.01)
        assert current["coordination_stage"] == "Reviewing draft"
        stopped = client.post(path + f"/{mid}/cancel")
        assert stopped.json()["status"] == "cancelled"
        assert [a["status"] for a in stopped.json()["attempts"]] == ["complete", "cancelled"]
        assert len(FakeModel.requests) == 2


def test_schema_six_preserves_existing_messages(tmp_path):
    path = str(tmp_path / "migration.sqlite3")
    store = Store(path)
    cid = store.create("Existing")["id"]
    with store.connect() as db:
        db.execute("ALTER TABLE messages DROP COLUMN coordination_mode")
        db.execute("ALTER TABLE messages DROP COLUMN coordination_stage")
        db.execute("ALTER TABLE messages DROP COLUMN rating")
        db.execute("PRAGMA user_version=5")
    restored = Store(path)
    with restored.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 6
    assert restored.get(cid)["title"] == "Existing"
