# Changelog

## Phase 13 — guarded automatic selection

- Added an opt-in one-message automatic model choice in saved chat.
- Rechecked the Phase 12 ranking at send time and recorded the chosen model and reason.
- Rejected conflicting fallback/coordination choices and unavailable candidates before sending.
- Made exactly one provider request per automatic turn; no automatic retries or hidden fallback.

## Phase 12 — usage-aware model suggestions

- Added a read-only Compare my models panel in chat with an explicit Choose action.
- Explained manual price estimates, recent observed outcomes, advisory budgets,
  cooldowns, and local-only exclusions for each configured model.
- Kept provider quota and live availability unknown unless a real request proves an outcome.

## Phase 11 — appearance themes

- Added Violet, Ocean, Ember, Daylight, and System theme choices in Settings.
- Saved the choice in this browser and applied it across all four pages before styles load.
- Kept the original vibrant theme as the default, with readable light and dark palettes.

## Phase 10 — coordinated model workflows

- Added opt-in draft/review/revision and two-subtask synthesis in saved chat.
- Recorded each step in the existing usage ledger, with per-answer cost estimates.
- Added progress stages, answer ratings with a Usage summary, bounded calls, and cancellation handling.
- Kept manual model selection and ordered fallback as separate options.

## Phase 9 — interface and usability refresh

- Added a vibrant violet, aqua, and coral palette across chat and management pages.
- Improved navigation, responsive cards and forms, focus visibility, and skip links.
- Added subtle motion with reduced-motion support and a Copy response action.
- Moved coordinated models to Phase 10; theme choices remain future work.

## Phase 8 — provider discovery and guided setup

- Added Find a model with nine dated provider guides and prefilled connection forms.
- Distinguished recurring offers, evaluations, trials, conditional access and local inference.
- Added official signup/source links, explicit optional testing and outdated-offer exclusions.
- Kept keys in the encrypted registry and preserved defaults/fallback settings.
- Moved coordinated models to Phase 9. No guarantee of exhaustive coverage or free eligibility.


## Phase 7 — shared cooldowns and routing controls

- Added persistent Retry-After cooldowns shared by user-defined usage groups.
- Added fallback permission and local-endpoint-only request restrictions.
- Added attempt details in saved chats, group usage totals and skipped attempt counts.
- Improved sanitized diagnostics; schema 5 preserves earlier history and costs.
- Budgets remain advisory; no quota inference or automatic task coordination.


## Phase 6 — opt-in ordered fallback

- Added a saved order of up to three fallback connections and an explicit chat toggle.
- Limited fallback to transient failures before answer text, with four total attempts
  and a 120-second overall deadline; cancellation never starts another attempt.
- Preserved the selected primary while attributing answers to the actual model.
- Added attempt group/number tracking in usage and CSV; schema 4 preserves prior data.
- Retained manual defaults and advisory budgets. Cloud availability remains unverified.


## Phase 5 — manual budgets and cost estimates

- Added optional user-entered USD input/output rates and per-request price snapshots.
- Added workspace and per-model monthly UTC budgets with configurable warning thresholds.
- Showed costs, unknown-cost counts and budget status in Usage, CSV and chat warnings.
- Kept historical costs unchanged when prices change; schema 3 preserves old usage
  as unknown-cost instead of inventing historical rates.
- Budgets are advisory only; no requests are blocked and no models are switched.
- Tested with simulated providers; these estimates are not verified provider bills.


## Phase 4 — model connections, settings and usage

- Added multiple named model connections and explicit selection per chat.
- Added Gemini, OpenAI-compatible, Anthropic, OpenRouter and Ollama text adapters.
- Added Settings and Usage pages, UTC filters and CSV export.
- Encrypted saved credentials and added official OpenRouter PKCE account connection.
- Migrated SQLite to schema 2 while preserving chats; backups now include the key file.
- Imported existing environment Gemini credentials once; future changes use Settings.
- No automatic routing or fallback. Provider tests are simulated; live cloud generation
  and live OpenRouter login have not been verified for this release.


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
