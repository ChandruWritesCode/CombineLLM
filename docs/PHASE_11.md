# Phase 11: appearance themes

Open **Settings → Appearance** and choose a theme. The change applies immediately
to Chat, Settings, Find a model, and Usage. The available choices are:

| Choice | Appearance |
| --- | --- |
| Violet | Original vibrant dark palette; default for existing and new browsers. |
| Ocean | Cool dark teal palette. |
| Ember | Warm dark palette. |
| Daylight | Bright palette with dark text. |
| System | Daylight when the device requests light mode; Violet otherwise. |

The selected choice is saved in browser local storage under `combinellm-theme`.
It follows you between pages and across refreshes in that browser. It does not
sync between browsers or devices. If browser storage is unavailable, the choice
still applies in the current tab until it is closed. Theme scripts run before
styles load to avoid a flash of the wrong palette. The System option reacts when
the device preference changes. Existing reduced-motion and keyboard focus rules
continue to apply.

No database migration, provider call, account permission, or external asset is
needed. `theme.js` handles preference selection; `themes.css` contains the shared
palette overrides. The HTML pages load both assets from the local backend.

## Validation

The required repository checks passed. The theme picker was inspected in the
browser; Daylight remained active after navigating to Chat, and Ocean, Ember and
System resolved to their expected palettes. Violet was restored after review.
No live cloud model request was made for this phase.
