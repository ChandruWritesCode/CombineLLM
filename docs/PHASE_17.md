# Phase 17: task-aware routing

In saved chat, enable **Choose a model automatically** and optionally choose a
task focus: General, Code, Writing, or Analysis. The comparison panel shows the
current suggestion and its reasons. A model you labeled for the task ranks ahead
of one without that label when higher-priority budget and reliability signals are
equal. A known context limit below the estimated input size makes the model
ineligible. Unknown limits remain eligible and are called out as unknown.

At send time, the backend counts the new prompt and completed conversation turns,
adds the chosen model's system instruction, and re-ranks. The comparison panel's
preview uses the current draft prompt and may omit saved history; the send-time
choice is authoritative. The answer records why that model was selected. There is
still exactly one provider call, no hidden tests or retries, and no combination
with fallback or coordinated mode. Local-only mode, cooldowns, and local request
ceilings remain enforced. Task labels and context limits are user-entered hints,
not live provider capability or quota measurements.

## Validation

Simulated-provider tests verify task preference, context exclusion, attribution,
one call, and invalid-input rejection. All 101 tests passed. Ruff lint and format,
JavaScript syntax, and Docker Compose configuration passed. The rebuilt container
became healthy, and browser review confirmed that task focus becomes available
when automatic choice is enabled. No live cloud call was made.
