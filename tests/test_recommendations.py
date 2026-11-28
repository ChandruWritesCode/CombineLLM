"""Read-only suggestions use isolated local usage, never provider requests."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.policies import cool_down


def test_suggestions_explain_price_history_cooldown_and_local_policy():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        ids = {}
        for name, kind, url, rate in [
            ("Cheap cloud", "compatible", "https://example.com/v1", "0.1"),
            ("Local", "ollama", "http://localhost:11434/v1", "1"),
            ("Unknown price", "openai", "", None),
        ]:
            response = client.post(
                "/api/v1/models",
                json={
                    "name": name,
                    "kind": kind,
                    "model": name.lower().replace(" ", "-"),
                    "base_url": url,
                    "input_price_per_million": rate,
                    "output_price_per_million": rate,
                    "usage_group": "shared-local" if name == "Local" else "",
                },
            )
            assert response.status_code == 201
            ids[name] = response.json()["id"]

        initial = client.get("/api/v1/recommendations").json()
        assert initial["suggested_model_id"] == ids["Cheap cloud"]
        assert initial["models"][0]["cost_per_1k_each_usd"] == "0.0002"
        assert initial["models"][-1]["cost_per_1k_each_usd"] is None

        with client.app.state.store.connect() as db:
            for number, status in enumerate(("complete", "failed", "failed")):
                db.execute(
                    "INSERT INTO usage_events (id,model_id,source,status,started_at) "
                    "VALUES (?,?,?,?,?)",
                    (
                        f"event-{number}",
                        ids["Cheap cloud"],
                        "saved_chat",
                        status,
                        f"2026-11-28T00:00:0{number}+00:00",
                    ),
                )
            db.execute(
                "INSERT INTO usage_events (id,model_id,source,status,started_at) "
                "VALUES ('test',?,'connection_test','complete','2026-11-28T00:00:05+00:00')",
                (ids["Cheap cloud"],),
            )
        observed = client.get("/api/v1/recommendations").json()
        assert observed["suggested_model_id"] == ids["Local"]
        cloud = next(m for m in observed["models"] if m["model_id"] == ids["Cheap cloud"])
        assert (cloud["observed_requests"], cloud["completed"], cloud["failed"]) == (3, 1, 2)

        local = client.get("/api/v1/recommendations?local_only=true").json()
        assert local["suggested_model_id"] == ids["Local"]
        assert not next(m for m in local["models"] if m["model_id"] == ids["Cheap cloud"])[
            "eligible"
        ]
        cool_down(client.app.state.store, "group:shared-local", 60)
        cooled = client.get("/api/v1/recommendations?local_only=true").json()
        assert cooled["suggested_model_id"] is None
        assert (
            next(m for m in cooled["models"] if m["model_id"] == ids["Local"])["cooldown_seconds"]
            > 0
        )


def test_warning_budget_is_deprioritized():
    with TestClient(create_app(Settings(_env_file=None, environment="test"))) as client:
        ids = []
        for name, budget in (("Low budget", "0"), ("Available", None)):
            result = client.post(
                "/api/v1/models",
                json={
                    "name": name,
                    "kind": "ollama",
                    "model": name.lower().replace(" ", "-"),
                    "base_url": "http://localhost:11434/v1",
                    "input_price_per_million": "0",
                    "output_price_per_million": "0",
                    "monthly_budget_usd": budget,
                },
            )
            ids.append(result.json()["id"])
        result = client.get("/api/v1/recommendations").json()
        assert result["suggested_model_id"] == ids[1]
        assert (
            next(m for m in result["models"] if m["model_id"] == ids[0])["budget_status"]
            == "exceeded"
        )
