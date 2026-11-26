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
