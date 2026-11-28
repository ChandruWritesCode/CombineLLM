# Phase 14: local request ceilings

Set **Monthly workspace request ceiling** or **Monthly model request ceiling** in
Settings. Leave either blank to keep that ceiling unset. The Usage page shows the
current UTC month's counts and remaining slots. `GET /api/v1/limits` exposes the
same local snapshot. Set a positive whole number from 1 to 1,000,000.

The app reserves a slot in SQLite before contacting a provider. Workspace and
model counts include running, complete, failed, cancelled and interrupted attempts.
Connection tests also count because they send provider requests. A skipped call
never reaches a provider and does not consume a slot. The reservation and count
check share one immediate transaction, so simultaneous requests cannot both take
the last slot. Limits reset at the next UTC month boundary.

When a ceiling is reached, the app records a skipped row with
`local_request_limit` and gives a clear error. Ordered fallback stops at that
point; it does not try another model as a way around the ceiling. Coordinated
workflows can use several slots and stop if a later stage reaches a ceiling.
Suggestions and automatic selection exclude capped models. Lowering a ceiling
below already recorded usage blocks new calls; raising or removing it allows new
calls again.

These are **local request counts**, not provider quota or a financial spending
cap. Other applications and provider websites can still use your account. A
provider may charge for a failed or cancelled call. The existing dollar budgets
remain advisory estimates based on entered rates and reported token counts.
Provider-side billing is the source of truth for actual charges. Unknown-cost
totals exclude skipped calls because those made no provider request.

No database migration is needed: caps live in existing settings JSON. The usage
ledger already stores the reservation status and error code. To inspect why a
request was skipped, open Usage → Recent requests and read its Error code column.

## Validation

The required checks passed: 95 tests, Ruff lint and format, JavaScript syntax,
and Docker Compose configuration. Simulated tests cover concurrent reservations,
workspace and model ceilings, connection tests, skipped accounting, recommendations
and invalid settings. The rebuilt Docker app became healthy. Browser review
confirmed the workspace and model controls plus the Usage summary. No live cloud
request was made in this phase.
