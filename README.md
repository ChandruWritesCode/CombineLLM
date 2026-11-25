# CombineLLM — Phase 1

FastAPI foundation with Docker, configuration, health checks, and VS Code debugging.

## Run

```bash
cp -n .env.example .env
docker compose up --build -d --wait
```

Open http://localhost:8000/docs (use the port from `.env` if customized).
The health endpoint is `/api/v1/health`. Stop with `docker compose down`.

## Development

```bash
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
uv run pytest
uv run ruff check .
```

VS Code includes an F5 debugger configuration for port 8002. Keep the service
bound to localhost: authentication is not implemented. No providers or database
are connected in this phase. See [the roadmap](docs/ROADMAP.md).
