# Architecture

## Request paths

```text
Browser → FastAPI → SQLite (save user + pending assistant)
                  → background generation task → provider adapter → Gemini
Browser ← SSE snapshots ← SQLite ← incremental results / terminal status
```

The browser is served by the same FastAPI origin. No CORS setup, frontend framework,
CDN, or separate frontend server is required. Secrets remain in backend settings.
The existing stateless chat endpoint calls the same adapter without saving history.

## Backend components

- `main.py`: application factory, startup migration/recovery, shutdown cancellation,
  static frontend, and API routing.
- `storage.py`: short SQLite transactions, conversation/message persistence, context
  reconstruction, and schema version checks.
- `conversations.py`: REST endpoints and the in-process generation task registry.
- `chat.py`: stateless chat, SSE serialization, and provider dependency resolution.
- `providers/base.py`: provider protocol and normalized delta/done/error objects.
- `providers/gemini.py`: fixed official REST endpoint, request mapping, timeouts,
  sanitized failures, and reported usage mapping.

## Database and migrations

Python's built-in `sqlite3` is sufficient for the single-user foundation and avoids
an additional service. Short synchronous database operations run between network
awaits. This is intentionally not a high-throughput deployment design.

Database schema version 1 is installed transactionally when `PRAGMA user_version`
is 0. On later starts it is not recreated. A newer schema version is rejected so
an old application cannot silently modify a newer database. Future schema changes
must add ordered migrations, preserving earlier migrations and existing data.
Take a backup before applying schema changes. There is no downgrade migration yet.

`conversations`: UUID, title, created/updated timestamps.
`messages`: ordered sequence, UUID, conversation foreign key, role, text, status,
provider/model, finish reason, JSON usage, error, and creation time.

Foreign keys are enabled on each connection. Deleting a conversation cascades to
messages. WAL mode supports reads while response snapshots are saved. Use the
backup API utility, not a live copy of just the main database file: committed
updates can reside in the WAL sidecar.

## Generation lifecycle

A write transaction validates stored history, rejects concurrent turns in the
same chat, and inserts a user/assistant pair atomically. No provider request runs
inside that transaction. A strong reference to each background task is held until
completion. Incremental text is persisted before it is displayed through SSE.

Completion persists finish metadata and usage. Failures retain partial text and
sanitized errors. Cancellation closes the adapter stream and records a terminal
status, including the case where a task has not started yet. Shutdown cancels active
tasks. Startup marks any leftover streaming rows interrupted after a crash.

Run exactly one backend process per database. Multiple workers would have separate
task registries and could incorrectly mark another worker's responses interrupted.
A future multi-user deployment requires shared job ownership, worker coordination,
authentication, pagination, and more scalable storage access.

## Privacy and boundaries

Only localhost is exposed by default. No authentication exists; do not expose this
server to a LAN or the internet without an authentication design. `.env` and SQLite
are plaintext on the local disk. The Docker image and Git history exclude both.
API keys are sent in headers to Google's fixed endpoint, not supplied by the browser.
Cloud prompts and completed conversation context are sent to the provider.

The frontend renders model/user text with `textContent`, never raw HTML. Only the
selected conversation ID is placed in localStorage; chat content remains in SQLite.
Provider settings presence is shown separately from actual availability.

## Phase 4 additions

SQLite schema 2 adds model connections, workspace preferences and a usage ledger,
and model connection IDs on conversations/messages. Migration preserves schema 1
history. Connections encrypt credentials with a Fernet key adjacent to the database.
Provider selection resolves an explicit ID, saved chat ID, then workspace default;
missing/disabled selections fail without fallback. Adapter streams are wrapped by
a tracker that records terminal outcome and reported usage for each attempt.
Settings and usage use separate HTML pages with plain JavaScript. OpenRouter PKCE
state is short-lived and process-local, bound to an HttpOnly browser cookie.
See [Phase 4](PHASE_4.md) for capabilities, API routes and limitations.

## Phase 5 additions

Schema 3 adds two nullable price snapshots and a nullable estimated USD amount to
each usage event. Connection/default JSON stores manual rates and budget targets.
The tracker captures rates before streaming and calculates Decimal costs from final
input/output counts. No retroactive repricing occurs. `app/costs.py` calculates
current UTC-month advisory budgets including unknown-cost counts. No generation
path blocks or routes requests based on budgets. See [Phase 5](PHASE_5.md).

## Phase 6 additions

`app/routing.py` composes separately tracked providers only when a chat request
explicitly enables fallback. Preflight validates the saved order; generation uses
a bounded transient-error policy and propagates cancellation. Each tracked attempt
shares a group ID with its chain. Schema 4 adds group/number columns without changing
past costs. Saved messages receive actual provider attribution while the conversation
retains the primary model. See [Phase 6](PHASE_6.md) for exact transition rules.

## Phase 7 routing controls

Schema 5 persists shared cooldowns and links saved answers to attempt groups.
See [Phase 7](PHASE_7.md) for configuration, endpoint restrictions and limits.
Groq live generation was reported working by the user before this phase.

## Phase 10 coordination

`app/coordination.py` composes tracked providers for saved conversations. The
selected model owns drafting/planning and the final answer; a distinct selected
collaborator reviews or works on one subtask. All steps share an attempt group and
are recorded in `usage_events` with distinct sources. Only final-answer text is
saved as assistant content; the user sees the current stage while generation runs.
Schema 6 stores the chosen mode, current stage and a 1–5 user rating on messages.
The existing cancellation and restart recovery paths apply to the whole workflow.
See [Phase 10](PHASE_10.md) for bounds and failure behavior.

## Phase 11 appearance

`theme.js` reads a browser-local theme choice before CSS loads. `themes.css` applies
palette overrides across the existing pages. The System option follows the device
light/dark preference and reacts to changes. Themes make no backend request and
do not change model settings, stored chats, or the SQLite schema. See
[Phase 11](PHASE_11.md).

## Phase 12 suggestions

`app/recommendations.py` reads saved model settings, usage events, advisory budgets
and cooldowns. The endpoint performs no provider calls and stores no new data.
Chat shows the explanation in a collapsible panel and changes the selected model
only after the user clicks Choose. See [Phase 12](PHASE_12.md) for ranking rules and
limits.

## Phase 13 automatic selection

The saved-chat provider dependency uses the Phase 12 comparison to choose one
eligible model when `auto_select` is explicitly true. It resolves immediately
before the turn is saved and sends through the normal tracked provider path. There
is no fallback or coordination in that request. Schema 7 stores selection mode and
a short explanation on the answer. The usage ledger records the single actual
provider attempt. See [Phase 13](PHASE_13.md).

## Phase 14 request ceilings

`app/limits.py` counts current UTC-month usage events excluding skipped rows. The
tracked provider starts an immediate SQLite transaction, checks workspace and
model ceilings, and inserts a running reservation before contacting a provider.
Concurrent requests therefore cannot both claim the last local slot. A blocked
attempt is saved as skipped with `local_request_limit`; it never contacts the
provider. Caps are stored in the existing connection/preferences JSON, so no
schema migration is needed. See [Phase 14](PHASE_14.md).

## Phase 15 portability

`app/portability.py` defines the versioned JSON transcript. Export reads a
consistent SQLite snapshot and rejects a chat with an active response. Import
validates the entire archive, then writes a new conversation and message IDs in
one transaction. It keeps text, statuses, model labels and timestamps, while
leaving model connection IDs, credentials, usage ledger rows and attempt groups
behind. Readable text export uses the same validated snapshot. See
[Phase 15](PHASE_15.md).

## Phase 16 capability hints

Connections may store a user-entered character limit and task-strength tags in
their existing JSON configuration. No schema migration or provider discovery is
involved. Blank context limits remain unknown. See [Phase 16](PHASE_16.md).

## Phase 17 task-aware routing

The comparison endpoint accepts an optional task label and estimated input size.
Matching user labels improve ranking, while a known context limit below the input
size makes a connection ineligible. The automatic saved-chat path recomputes input
size from completed context plus the new prompt and applies the same comparison
before selecting its one provider. See [Phase 17](PHASE_17.md).

## Phase 18 collaboration steps

Schema 8 adds `coordination_steps`, keyed by answer ID and step number, with a
foreign key that removes steps when the answer is deleted. Completed bounded
intermediate outputs are saved as separate records and returned with saved chat
messages; the final answer remains the only assistant text used in future model
context. The existing attempt group supplies per-step status, tokens and cost
estimates. Portable JSON exports exclude these internal results. See
[Phase 18](PHASE_18.md).

## Phase 19 diagnostics and recovery

`GET /api/v1/diagnostics` reads SQLite quick-check status, schema version, local
record counts, key-file presence and active-generation count. It returns no paths,
credentials, provider secrets or cloud-health claims. `scripts.restore` validates
SQLite integrity and decryptability of saved credentials using the adjacent key,
then copies a verified backup to a new path with exclusive creation. It never
overwrites a live database. See [Phase 19](PHASE_19.md).
