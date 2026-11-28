# Phase 18: collaboration clarity

Choose either **Draft, review, revise** or **Split and synthesize** in saved chat,
then choose a different collaborator model. These remain explicit three-call and
four-call workflows. Expand **Model attempts** on a coordinated answer to see the
status, reported token total, estimated cost, and completed intermediate result
for each step. The final answer is shown above that section. A failed or cancelled
workflow keeps results from steps that already completed, without presenting them
as the final answer. Only the final answer joins future model conversation context.

Schema 8 adds a local `coordination_steps` table. It preserves existing chats and
deletes step results when their answer is deleted. Each intermediate output is
bounded to 8,000 characters by the existing workflow. Results can contain private
prompt information and are included in database backups. The Phase 15 portable
JSON export keeps its text-only final-answer format and excludes step results.
No new provider calls, retries, or external services were added.

## Validation

Simulated-provider tests cover review and split outputs, failed and cancelled
workflows, export exclusion, and migration from schema 7. All 102 tests passed.
Ruff lint and format, JavaScript syntax, and Docker Compose configuration passed.
After a local database and matching-key backup, the rebuilt container became
healthy and browser review confirmed the saved chat remained accessible. No live
cloud request was made.
