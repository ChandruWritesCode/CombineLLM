# CombineLLM

A local, self-hosted chat workspace that will bring multiple LLM providers together.
**Current release: Phase 18 — collaboration clarity.**

Connect Gemini, OpenAI, Anthropic, OpenRouter, Ollama, or compatible text APIs.
Provider availability depends on the service and your account; backend health does
not guarantee a successful model response.

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

## Connect models

Open **Find a model** in the sidebar for provider walkthroughs and prefilled setup,
or use **Settings** to add custom connections, credentials and model IDs.
Choose a model in chat. OpenRouter also supports account connection through PKCE.
See [Phase 4 setup and options](docs/PHASE_4.md). Use **Usage** for per-model request
and token statistics, estimated costs and monthly budget warnings. Enter your own
prices and budgets in Settings. Budgets are advisory: requests remain enabled.
Manual selection remains the default. Configure an optional fallback order in
Settings, then explicitly enable it in chat. See [Phase 6](docs/PHASE_6.md).
For coordinated answers, choose **Draft, review, revise** or **Split and synthesize**
in chat, then choose a different collaborator model. The selected model writes the
final answer. See [Phase 10](docs/PHASE_10.md) for the number of calls, limits and
privacy behavior.
Choose a color theme in **Settings → Appearance**. The preference applies across
pages in the same browser. See [Phase 11](docs/PHASE_11.md).
Open **Compare my models** in chat to inspect a read-only suggestion based on
configured prices, recent local request outcomes, advisory budgets, and cooldowns.
Click **Choose** to use one; no prompt is sent until you submit it. See
[Phase 12](docs/PHASE_12.md).
For one saved-chat message, enable **Choose a model automatically for my next
message**. The app checks the ranking when you send and makes one provider request.
It records the selected model on the answer and turns the option off after that
message. See [Phase 13](docs/PHASE_13.md).
Set optional monthly **request ceilings** for the workspace or a model in Settings.
These stop new calls through CombineLLM after its local count is reached. They do
not control provider-side billing. See [Phase 14](docs/PHASE_14.md).
Export a saved conversation as JSON for reimport or as a readable text transcript.
Use **Import conversation** in the sidebar to create a new chat from a JSON archive.
Exports include conversation text, so keep downloaded files private. See
[Phase 15](docs/PHASE_15.md).
In Settings, add your own context-size and task-strength hints to each model. They
are labels for future routing, not provider-verified capabilities. See
[Phase 16](docs/PHASE_16.md).
For automatic choice, you can optionally choose a task focus. The app prefers
models you tagged for that task and excludes models whose entered context limit
is below the estimated input size. It still makes one provider call per message;
see [Phase 17](docs/PHASE_17.md).
Coordinated answers now retain their intermediate draft, review, planning, or
subtask results locally. Expand **Model attempts** on the answer to inspect each
step alongside token counts and estimated costs. See [Phase 18](docs/PHASE_18.md).

### Import Gemini from the environment

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

Environment credentials are imported once into each database. Afterwards, edit
the model in Settings. For initial import or server configuration changes:

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
- Review each coordinated step's usage and estimated cost; rate completed answers.
- Preserve chats across Docker container rebuilds using a named SQLite volume.

Failed, cancelled, and interrupted turns remain visible but are excluded from
future model context. Successful turns are sent as history on subsequent messages.
Cloud prompts leave your machine; select a local endpoint for local inference.
OpenRouter login is supported; other connections use API keys. Paid-use caps and
multi-user support are not included. Ordered fallback and coordination are separate
opt-in modes; budgets remain advisory.

## Develop without Docker

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8002 --no-access-log
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
| `COMBINELLM_PUBLIC_BASE_URL` | `http://localhost:8001` | Browser origin for login; Compose derives it from host port |
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
- [Phase 4: connections and usage](docs/PHASE_4.md) — settings, credentials, login and statistics.
- [Phase 5: budgets and estimates](docs/PHASE_5.md) — manual rates, warnings and limitations.
- [Phase 6: ordered fallback](docs/PHASE_6.md) — opt-in routing, attempt limits and policy.
- [Phase 7: routing controls](docs/PHASE_7.md) — shared cooldowns, local-only policy and attempt history.
- [Phase 8: guided setup](docs/PHASE_8.md) — free offers, trials, official links and setup walkthroughs.
- [Phase 9: interface refresh](docs/PHASE_9.md) — colors, responsive layout and accessibility.
- [Phase 10: coordinated models](docs/PHASE_10.md) — review, subtask synthesis, ratings and costs.
- [Phase 11: appearance themes](docs/PHASE_11.md) — color presets and system preference.
- [Phase 12: model suggestions](docs/PHASE_12.md) — explainable, read-only comparison.
- [Phase 13: automatic selection](docs/PHASE_13.md) — opt-in one-call choice and attribution.
- [Phase 14: request ceilings](docs/PHASE_14.md) — local monthly call limits and accounting.
- [Phase 15: conversation portability](docs/PHASE_15.md) — transcript export and import.
- [Phase 16: model capability hints](docs/PHASE_16.md) — manual context and task labels.
- [Phase 17: task-aware routing](docs/PHASE_17.md) — one-call choice using your hints.
- [Phase 18: collaboration clarity](docs/PHASE_18.md) — saved step results and usage.
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
app/connections.py      Model registry and encrypted credentials
app/model_api.py        Settings and application usage ledger
app/costs.py            Decimal cost estimates and advisory budgets
app/limits.py           Transactional local request ceilings
app/portability.py      Versioned text-only conversation archive contract
app/routing.py          Bounded opt-in ordered fallback
app/coordination.py     Bounded draft/review and split/synthesis workflows
app/recommendations.py  Read-only model comparisons from local data
app/oauth.py            OpenRouter PKCE account connection
app/providers/          Gemini, Anthropic and compatible text adapters
app/static/             HTML, CSS, and JavaScript frontend
scripts/backup.py       Consistent SQLite backup utility
tests/                 API, storage, lifecycle, and adapter tests
```

To stop Docker without losing chats: `docker compose down`. Do not add `-v` unless
you intend to delete the saved-chat volume. See the operations guide before restoring
or relocating a database.
