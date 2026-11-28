# Phase 16: model capability hints

Edit a model in Settings to record a known context limit in characters and choose
task labels: General, Code, Writing, or Analysis. The model card shows these hints.
Leave the limit blank when unknown. The backend validates the limit and accepts
only distinct known labels. Existing models default to unknown context and no
labels; no database migration is needed.

These are **your descriptions**, not capabilities verified by a provider. They do
not change a provider request or guarantee that a prompt will fit. Model settings
continue to exclude API keys from responses. Phase 17 will use the hints for
opt-in automatic routing.

## Validation

The isolated test checks saving, editing, validation, and credential exclusion.
All 99 tests, Ruff lint and format, JavaScript syntax, and Docker Compose
configuration checks passed. The rebuilt container became healthy, and browser
review showed the fields in the model editor without changing the saved model.
No live provider call was made.
