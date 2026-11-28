# Phase 13: guarded automatic selection

In saved chat, check **Choose a model automatically for my next message**. The
current suggestion appears beside the checkbox and in **Compare my models**. At
send time, the backend recomputes that suggestion from current local data. It
chooses one enabled model that is allowed by local-only mode and is not cooling
down, then makes exactly one provider request. The checkbox turns off after a
successful send. The answer names its actual model and records that it was chosen
automatically.

This mode is separate from manual selection, ordered fallback and coordinated
answers. Those modes cannot be combined in one request. A request with no eligible
model fails before inserting messages or contacting a provider. If availability
changes after the comparison, the normal provider error is saved; there is no
automatic retry or second model. Advisory budgets influence the ranking but do
not block requests or guarantee a cost cap. The app cannot see provider quota or
live availability before a real call.

`POST /api/v1/conversations/{id}/messages` accepts `"auto_select": true` with no
`model_id`, `fallback`, or `coordination`. The `local_only` flag can also be set.
Schema 7 adds `selection_mode` and `selection_reason` to saved messages. Manual
messages remain supported, and existing conversations are preserved by migration.
The selected connection remains visible as the conversation's model after the
turn. The Usage page records the one actual attempt.

## Validation

The required checks passed: 92 tests, Ruff lint and format, JavaScript syntax,
and Docker Compose configuration. Simulated tests cover one-call selection,
attribution, rejected mode conflicts, local-only exclusions, cooldowns, and
migration from schema 6. The database and key were backed up before the local
upgrade; the rebuilt Docker app became healthy. Browser review confirmed the
checkbox, current suggestion, and disabled Send action when local-only mode left
no eligible model. No live cloud request was made in this phase.
