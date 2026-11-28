# Phase 15: conversation portability

Open a saved chat and use **Export JSON** to download a portable archive. Use
**Export text** for a readable transcript. In the sidebar, **Import conversation**
accepts a CombineLLM JSON archive and creates a new saved chat. The original chat
remains in place. Check the selected model before sending a new message in the
imported chat.

The JSON archive uses `format: "combinellm-conversation"` and `version: 1`. It
contains the title and ordered message pairs with role, text, completion status,
provider/model labels and timestamps. Export and import support up to 400 messages and
1,000,000 total message characters. Messages must alternate user and assistant;
users must have nonblank completed text. Active streaming responses cannot be
exported. Stop or finish a response first. JSON imports reject unsupported
versions, extra fields and malformed transcripts before creating any records.

Archives exclude API keys, account logins, model connection IDs, routing settings,
usage ledger rows, cost estimates and attempt groups. Imports create fresh IDs and
do not count as provider requests. A new model connection must be selected for
future messages when the workspace has no default. Completed imported turns can
be used as conversation context; failed and stopped turns stay visible but are
excluded from future model context.

**The message text itself may contain private information that you or a model
entered.** Keep exported files private and review them before sharing. Text export
is for reading; JSON is the supported import format. Files are handled by the
local backend and browser without a third-party service.

API routes:

- `GET /api/v1/conversations/{id}/export?format=json` downloads JSON.
- `GET /api/v1/conversations/{id}/export?format=text` downloads plain text.
- `POST /api/v1/conversations/import` accepts the JSON archive and returns the
  newly created conversation.

No database migration is needed. Imported records use the existing conversation
and message tables, and the existing chat UI renders all text without HTML markup.

## Validation

Simulated local tests cover JSON/text export, import round trips, continued chat
context, invalid files, active-response rejection and credential/usage exclusion.
All 98 tests passed. Ruff lint and format, JavaScript syntax, and Docker Compose
configuration checks passed. The rebuilt container became healthy, and browser
review confirmed that Import conversation, Export JSON, and Export text are visible
at a narrow viewport. No live cloud request was made for this phase.
