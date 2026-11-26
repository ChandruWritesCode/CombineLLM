# Changelog

## 0.3.0 — Phase 3

- Added a responsive local chat workspace at `/` with saved conversation navigation.
- Added SQLite persistence, schema version 1, crash recovery, and Docker storage.
- Added create/read/rename/delete APIs and persistent response snapshot streaming.
- Added explicit response cancellation and prompt reuse after provider failures.
- Retained partial failed answers and excluded failed turns from future model context.
- Moved service metadata from `/` to `/api/v1`; retained the stateless chat endpoint.
- Added backup utility, operations/architecture guides, and phase-based Git history.
- Known limits: single process, no authentication, no rich Markdown, no budget
  enforcement or fallback; current cloud availability is not guaranteed.

## 0.2.0 — Phase 2

- Added the official Gemini REST adapter and extensible provider interface.
- Added stateless text chat, optional SSE, request validation, and token metadata.
- Added sanitized errors, timeouts, cancellation cleanup, and simulated adapter tests.
- Live tests encountered retired-model and high-demand errors; listing a model alone
  was insufficient to confirm successful generation for the configured account.

## 0.1.0 — Phase 1

- Added FastAPI health/service endpoints, environment configuration, and API docs.
- Added Docker Compose, a non-root container, locked dependencies, and VS Code debugging.
- Added initial tests and the project roadmap.
