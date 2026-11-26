# Phase 5: manual budgets and cost estimates

Phase 5 keeps model selection manual. It adds user-entered prices and advisory
monthly budgets. **Budgets do not block requests and are not spending caps.**

## Configure

1. In **Settings → Edit model**, enter input and output prices in USD per million
   tokens, based on the rates applicable to your own account. Leave unknown rates
   blank. Enter zero only when you intend a zero-price estimate.
2. Optionally set a monthly budget for that connection.
3. Under **Workspace defaults**, set an overall monthly USD budget and the warning
   threshold (1–100%, default 80%). Blank disables a budget; zero immediately shows
   the target as reached. Saving does not change your provider account or billing.
4. Open **Usage** to see estimates and the current month's budget overview. Chat
   shows warnings for the workspace and selected connection when a threshold is
   reached, or when an active budget has unknown-cost requests.

## Calculation and limitations

For each completed request with reported input and output counts:

`estimated USD = (input tokens × input rate + output tokens × output rate) / 1,000,000`

Both rates and counts must be known. Missing values produce unknown cost; unknown
is not treated as a known zero. Totals sum only known estimates and separately
show the number of unknown-cost requests. Very small amounts display as less than
0.000001 USD; CSV retains the unrounded decimal estimate. Arithmetic uses Decimal.

Prices are snapshotted when an attempt starts. Changing rates applies to future
requests and never rewrites historical estimates. Old Phase 4 attempts remain
unknown-cost, even if prices are configured later. Tests from Settings count too.
Cancelled/failed attempts without final usage are unknown and might still be billed.

This is a simple input/output estimate, not a provider invoice. Special cache
rates, separate reasoning charges, search/tool charges, discounts, taxes, credits,
exchange rates and other applications' usage are not calculated. Provider token
categories differ; for example Gemini reasoning tokens are separate from answer
output in this adapter. Actual charges may therefore be higher or lower. No prices
are fetched automatically and no free-tier allowance is inferred.

Budgets use the **current UTC calendar month**, based on each request's start time.
They do not carry balances between months. The monthly overview is independent of
Usage date/model filters; the request tables and cost summary follow those filters.
Workspace totals include deleted connections; their historical usage remains.
Per-connection budgets are not shared provider/account quota pools. Warnings update
when opening a chat, changing models and completing requests; refresh to see
changes from another browser tab. They never reserve funds or prevent spending.

## API and storage

- Model configuration adds nullable decimal `input_price_per_million`,
  `output_price_per_million` and `monthly_budget_usd`.
- Workspace settings add nullable `monthly_budget_usd` and integer
  `budget_warning_percent`.
- `GET /api/v1/budgets` returns the UTC month, workspace and connection summaries,
  unknown counts, advisory status and estimated remaining budget. A remaining
  estimate is not a guaranteed available balance.
- `/api/v1/usage` includes estimated costs and unknown-cost counts; recent rows and
  CSV include the original prices and estimated USD. Decimal values are strings.
- SQLite schema 3 adds price snapshots and estimated costs without changing old
  messages or credentials. Back up the database and matching key before upgrading.

## Validation

Tests cover exact decimal arithmetic, unknown/zero/invalid values, warning
boundaries, monthly reset, immutable price snapshots, deleted-model retention,
v2 migration and an end-to-end simulated conversation switching two models. The
conversation continues with a zero advisory budget and retains its completed
history. Existing provider, backup and chat tests remain required. Live cloud
responses and live login are not verified by these tests.

Automatic fallback, hard spending enforcement, account-wide quota tracking and
multi-model task coordination remain future phases.

Release checks: 65 tests passed; Ruff lint/format, JavaScript syntax and Compose
configuration checks passed. Docker rebuilt and reported healthy after a pre-upgrade
backup. Browser checks used an isolated simulated provider server to verify model
switching, chat budget warnings, usage totals and settings persistence. No real
provider quota was consumed during these checks.
