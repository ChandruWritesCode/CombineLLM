# Phase 10: coordinated models

Phase 10 adds two optional workflows to saved chat. Select the main model in the
chat bar, choose **How to answer**, and explicitly choose a different collaborator.
The main model writes the final answer. The two models receive conversation context.
Every call can consume provider quota, including failed calls, and appears in Usage.

## Workflows

| Mode | Calls | What happens |
| --- | ---: | --- |
| One model | 1 | The selected model answers normally. |
| Draft, review, revise | 3 | Main model drafts; collaborator critiques; main model writes the final answer. |
| Split and synthesize | 4 | Main model plans exactly two subtasks; main model handles one, collaborator handles the other; main model synthesizes. |

The planning step must return two numbered lines. If it cannot, the workflow stops
with an error rather than guessing subtasks. Intermediate drafts, reviews and
subtask findings are sent to the next relevant model. Since Phase 18, completed
intermediate results are stored separately from chat messages and can be inspected
under **Model attempts**. The final answer and a stage trail are stored. Coordinated mode and
ordered fallback cannot be enabled together. Local-only mode validates both
selected endpoints before a prompt is sent.

## Limits and failure behavior

- A workflow has a 180-second total deadline, no automatic retries, and at most
  three or four provider calls depending on the mode.
- Conversation input is limited to 30,000 characters in coordinated mode; each
  intermediate result is limited to 8,000 characters. Planning, draft, review and
  worker calls have smaller output token caps than the final answer.
- A failed intermediate step stops the workflow. Its draft is not shown as a final
  answer. Cancel stops the active call and skips remaining steps. A backend restart
  marks an active answer interrupted, as in ordinary chat.
- Each step has its own status, token report and price snapshot in Usage. The
  answer's **Model attempts** section sums known estimated costs and flags unknown
  costs. Estimates depend on user-entered prices and provider-reported token counts;
  they are not a provider bill or a quota guarantee.

Completed answers can be rated from 1 to 5 in the chat. The rating is saved in the
local database on that answer. Usage shows the count and average rating by workflow.
It is subjective feedback, not an automatic quality score. Providers do not receive
ratings.

## API and storage

`POST /api/v1/conversations/{id}/messages` accepts an optional `coordination` object:

```json
{
  "content": "Compare these options",
  "model_id": "main-model-connection-id",
  "coordination": {
    "mode": "review",
    "collaborator_model_id": "second-model-connection-id"
  }
}
```

Use `mode: "split"` for two-subtask synthesis. Set `local_only: true` to require
local endpoints. To save feedback, send `PUT /api/v1/conversations/{id}/messages/{message_id}/rating`
with `{"rating": 1}` through `{"rating": 5}`. Database schema 6 adds
`coordination_mode`, `coordination_stage`, and `rating` to messages while preserving
existing records. Back up the database before running an older release; schema 6
cannot be read by older versions.

## Validation

The required checks passed: 87 tests, Ruff lint and format, JavaScript syntax, and
Docker Compose configuration. Simulated provider tests cover both workflows, step
accounting, ratings, invalid roles and plans, review failure, cancellation, and
migration from schema 5. They use isolated SQLite databases and do not consume
provider credits. The rebuilt Docker app became healthy; chat controls were
inspected at desktop and phone widths. No live cloud response was tested in this
phase.
