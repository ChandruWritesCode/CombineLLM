# CombineLLM

A self-hosted workspace for multiple LLM providers. **Phase 2: first model connection.**
The backend supports Gemini text chat, optional streaming, provider configuration
status, and per-response token usage. Conversation storage and a chat UI come next.

See [the Phase 2 setup and examples](docs/PHASE_2.md) to configure a Gemini key and
model, then send your first message. Without credentials the backend still starts,
but chat returns a clear configuration error.

## Run with Docker in VS Code

Open this folder in VS Code, then choose **Terminal → New Terminal**.
Docker Engine must be running, with Docker Compose installed.

```bash
cp -n .env.example .env
docker compose up --build -d --wait
```

Open [API docs](http://localhost:8000/docs) or
[health](http://localhost:8000/api/v1/health). The health response is `{"status":"ok"}`.
In the docs, expand the health endpoint, choose **Try it out**, then **Execute**.

```bash
docker compose ps
docker compose logs -f backend
docker compose down
```

The container runs as a non-root user and the published port is restricted to your
own machine. This phase has no authentication; keep that local binding.
If port 8000 is occupied, change `COMBINELLM_PORT` in `.env` and run Compose again.
Use the new port in your browser. Rebuild after source changes.

For this workspace, `.env` currently selects port **8001** because 8000 was already
occupied. Open <http://localhost:8001/docs>. The copy command above preserves an
existing `.env`.

## Develop locally in VS Code

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed.
uv uses `.python-version` to select Python 3.12 and can download it automatically.
Run from the project root:

```bash
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

Open <http://localhost:8002/docs>. Stop with Ctrl+C. Native development uses port
8002 so it can run alongside the Docker instance.
Local development automatically reloads after code changes.

For breakpoints, install the recommended Python extensions, select `.venv/bin/python`
with **Python: Select Interpreter**, then press **F5** and choose
**CombineLLM: debug backend**. Stop any existing server first. The debugger runs
without auto-reload to keep breakpoint behavior predictable.

## Validate changes

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
docker compose config --quiet
```

`uv.lock` locks dependencies for local and Docker installs. After intentionally
changing dependencies, run `uv lock`, then `uv sync` and the checks above.

## Configuration

Copy `.env.example` to `.env` for optional overrides. Environment variables take
precedence over `.env` for native runs. Compose passes the listed settings into the
container; `.env` is not copied into the image.

| Variable | Default | Meaning |
| --- | --- | --- |
| `COMBINELLM_APP_NAME` | `CombineLLM` | API title and service name |
| `COMBINELLM_ENVIRONMENT` | `development` | `development`, `test`, or `production`; currently metadata only |
| `COMBINELLM_PORT` | `8000` | Compose host port; native port is set in the run command |
| `COMBINELLM_GEMINI_API_KEY` | empty | Backend-only Gemini API key |
| `COMBINELLM_GEMINI_MODEL` | empty | Text model ID available to your account, without `models/` |
| `COMBINELLM_PROVIDER_TIMEOUT_SECONDS` | `60` | Provider timeout, from 1 to 300 seconds |

## Layout

```text
app/config.py       Validated settings
app/main.py         FastAPI app and service/health endpoints
app/chat.py         Chat and provider status routes
app/schemas.py      Provider-neutral request and response formats
app/providers/     Adapter interface and Gemini REST implementation
tests/              API and configuration checks
.vscode/            Editor and debugger configuration
Dockerfile          Container build and health check
compose.yaml        Local Docker setup
docs/ROADMAP.md     Six development phases
```

The health endpoint checks process liveness, not provider or database availability.
The provider status endpoint checks configuration presence, not key validity or quota.
See [the roadmap](docs/ROADMAP.md) for the next phases.

Container setup follows the [FastAPI Docker guidance](https://fastapi.tiangolo.com/deployment/docker/)
and [uv Docker integration guidance](https://docs.astral.sh/uv/guides/integration/docker/).
