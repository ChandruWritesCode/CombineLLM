# CombineLLM

A local, self-hosted chat workspace that will bring multiple LLM providers together.
**Current release: Phase 3 — saved conversations and a browser chat interface.**

The backend currently integrates Gemini. Provider availability depends on Google
and your account; a healthy backend does not guarantee a successful model response.

## Start in VS Code

Open this folder, then open **Terminal → New Terminal**:

```bash
cp -n .env.example .env
docker compose up --build -d --wait
```

This workspace uses port **8001** in `.env`:

- [Chat workspace](http://localhost:8001/)
- [Interactive API documentation](http://localhost:8001/docs)
- [Backend health](http://localhost:8001/api/v1/health)

Fresh installations default to port 8000; use the port set in your `.env`.
The container runs as a non-root user and listens on your machine only.

## Connect Gemini

Edit `.env` in VS Code:

```dotenv
COMBINELLM_GEMINI_API_KEY=your-key
COMBINELLM_GEMINI_MODEL=your-available-text-model-id
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey). Choose a text
model available to your account; listing a model does not prove your account can
successfully generate with it. Check account limits and billing before use.
Credentials stay on the backend. `.env` is plaintext, ignored by Git, and excluded
from the image. Never commit it or share it in chat.

Apply configuration changes:

```bash
docker compose up -d --wait
```

Use `--build` as well after changing source or dependencies. See
[the Gemini setup guide](docs/PHASE_2.md) for API examples and provider error codes.

## What works now

- Create, open, rename, and delete saved conversations.
- See incremental responses and stop an in-progress generation.
- Resume viewing a response after refreshing or switching conversations.
- Keep prompts and partial answers when a provider fails.
- Reuse a prompt and send it again explicitly; no automatic retries.
- View model attribution, completion status, and reported token totals.
- Preserve chats across Docker container rebuilds using a named SQLite volume.

Failed, cancelled, and interrupted turns remain visible but are excluded from
future model context. Successful turns are sent as history on subsequent messages.
Cloud prompts leave your machine; this is not offline inference. No account login,
paid-use cap, automatic fallback, or multi-user support exists yet.

## Develop without Docker

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

Open [the development workspace](http://localhost:8002/). Changes to Python reload
automatically; refresh the page after CSS or JavaScript changes. Restart after
changing `.env`. For breakpoints, install the recommended VS Code Python extensions,
select `.venv/bin/python`, and press **F5**. Stop any server using port 8002 first.

Native development stores chats in `data/combinellm.sqlite3`. Docker uses a separate
named volume. Each mode has its own history. Run exactly **one backend process**
per database: the current generation manager and restart recovery assume this.

## Checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
node --check app/static/app.js
docker compose config --quiet
```

Node is only needed for the optional JavaScript syntax check; the frontend has no
build step or package installation. Automated provider tests use simulated
responses and do not spend API credits. Tests use temporary databases.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `COMBINELLM_APP_NAME` | `CombineLLM` | Service name in API metadata |
| `COMBINELLM_ENVIRONMENT` | `development` | Validated environment label |
| `COMBINELLM_PORT` | `8000` | Docker host port |
| `COMBINELLM_GEMINI_API_KEY` | empty | Backend-only provider credential |
| `COMBINELLM_GEMINI_MODEL` | empty | Text model ID, without `models/` |
| `COMBINELLM_PROVIDER_TIMEOUT_SECONDS` | `60` | Provider timeout (1–300 seconds) |
| `COMBINELLM_DATABASE_PATH` | `data/combinellm.sqlite3` | Native database path; Compose fixes its own volume path |

Environment variables override `.env`. The container only receives the settings
listed in `compose.yaml`. `uv.lock` fixes Python dependencies for both run modes.

## Project documentation

- [Development roadmap](docs/ROADMAP.md) — scope and completion of each phase.
- [Phase 2: Gemini setup](docs/PHASE_2.md) — stateless API, errors, and streaming.
- [Phase 3: saved chat](docs/PHASE_3.md) — UI behavior and conversation API.
- [Architecture](docs/ARCHITECTURE.md) — storage, migrations, generation lifecycle.
- [Operations and troubleshooting](docs/OPERATIONS.md) — backups, recovery, provider outages.
- [Contributing and Git workflow](docs/CONTRIBUTING.md) — phase commits and validation.
- [Changelog](CHANGELOG.md) — user-facing changes and known limits.

## Source layout

```text
app/main.py             Application lifecycle, routes, static frontend
app/config.py           Environment settings
app/chat.py             Original stateless chat endpoint
app/conversations.py    Saved chat endpoints and generation tasks
app/storage.py          SQLite repository and versioned migrations
app/schemas.py          Provider-neutral chat messages
app/providers/          Gemini adapter and provider interface
app/static/             HTML, CSS, and JavaScript frontend
scripts/backup.py       Consistent SQLite backup utility
tests/                 API, storage, lifecycle, and adapter tests
```

To stop Docker without losing chats: `docker compose down`. Do not add `-v` unless
you intend to delete the saved-chat volume. See the operations guide before restoring
or relocating a database.
