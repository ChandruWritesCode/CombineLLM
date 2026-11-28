# Phase 12: usage-aware model suggestions

Open **Compare my models** in chat to see all configured connections. The panel
shows a suggested model and an explanation for each choice. Click **Choose** to
change the chat's selected model. That click sends no prompt. Refresh the panel
after changing model settings or when you want a new snapshot.

The comparison reads only local CombineLLM data:

- Enabled status and whether an endpoint is local when local-only mode is checked.
- Persistent cooldowns for the connection or its declared shared usage group.
- The current UTC month's advisory budget status and incomplete cost estimates.
- User-entered input/output prices, shown as an estimate for 1,000 input plus
  1,000 output tokens. Missing prices are shown as unknown.
- Up to 20 recent complete or failed chat attempts per model. Connection tests,
  skipped attempts and cancellations are excluded from that ratio.

The ranking first excludes disabled, local-only-incompatible and cooling models.
It then prefers a model below its advisory budget warning, avoids a poor recent
record when at least three outcomes exist, prefers known lower configured prices,
and uses recent completion rate and name as tie breakers. A budget warning does
not block manual use. The suggestion is not an answer-quality score and does not
know remaining provider quota or live availability. A successful past request
does not guarantee the next one will work.

`GET /api/v1/recommendations?local_only=true` returns the sorted explanations and
`suggested_model_id`. It does not contact any provider, read credentials, change
the selected model, or write to SQLite. Existing chat, fallback, and coordinated
answer behavior remain opt-in.

## Validation

The required checks passed: 89 tests, Ruff lint and format, JavaScript syntax,
and Docker Compose configuration. Isolated tests cover manual price ordering,
recent outcomes, local-only policy, shared cooldowns and budget warnings. The
rebuilt Docker app became healthy. Browser review confirmed the comparison panel
and local-only exclusion with a disabled Choose action. No live cloud request was
made in this phase.
