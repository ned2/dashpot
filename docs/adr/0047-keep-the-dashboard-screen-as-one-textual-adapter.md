---
status: accepted
date: 2026-09-18
---

# Keep the dashboard screen as one Textual adapter

[Issue #234](https://github.com/ned2/dashpot/issues/234) assesses whether
`DashboardScreen` in [`ui/app.py`](../../src/dashpot/ui/app.py) should lose
another responsibility after the pane, layout, Issue-table-controller,
runner, Remote Fetch and Cleanup extractions
[ADR 0042](0042-group-leaf-and-domain-modules-into-subpackages.md) deferred
this question from. No further structural seam is made: what remains on the
screen is the adapter between Textual — its widgets, focus, messages and
lifecycle — and the plain objects that already hold every decision, and each
candidate seam would move a handler's few lines behind a protocol or callback
the screen must still satisfy. One derivation is moved: the Diagnostics
readout, the last content the screen assembled itself, now comes from
`summarize_diagnostics` beside `summarize_alerts` in
[`alerts.py`](../../src/dashpot/ui/alerts.py), and the two readouts are
painted by one method.

## What the screen holds now

`DashboardScreen` is 460 lines and 52 methods; no method is longer than 24
lines. Grouped by what each group depends on, with the module that already
owns the group's decision:

| Responsibility | Methods | Depends on | Decision already elsewhere |
| --- | --- | --- | --- |
| Composition and widget accessors | `__init__`, `compose`, `queue_table`, `list_pane`, the four pane accessors, `pane_controls`, `filter_kind`, `list_panes`, `focus_tables`, `surfaces_mounted` | `query_one`, `LIST_PANE_SPECS` | What each pane is: [`panes.py`](../../src/dashpot/ui/panes.py) |
| Focus and navigation | `action_focus_search`, `cycle_list_focus`, `on_focus_cursor_table_row_boundary_reached`, `on_mount`, `page_kind`, the three page actions | `self.focused`, `Widget.focus()`, the page runner | Page navigation: [`page_runner.py`](../../src/dashpot/ui/page_runner.py) |
| Layout | `on_body_resized`, `on_list_pane_rows_changed`, `fit_list_panes` | the body's size, the Issue pane's stylesheet minimum, each pane's count | The arithmetic: [`pane_layout.py`](../../src/dashpot/ui/pane_layout.py) |
| Pane reconciliation | `reconcile_list_panes`, `update_issue_inventory`, `on_theme_changed` | the store, the navigation, the theme, `ListPane.show_rows` | Each pane's read model: `PaneSpec.rows` |
| Query submission | `submit_column_ordering`, `order_issues_by`, `submit_search`, `change_lifecycle`, `action_cycle_issue_state`, `action_columns` | `Input`, `Select`, `DataTable.HeaderSelected`, the page runner | The submitted queries: [`list_queries.py`](../../src/dashpot/ui/list_queries.py); the Issue table's state: [`issue_table_controller.py`](../../src/dashpot/ui/issue_table_controller.py) |
| Cursor and relationship events | `follow_cursor`, `select_highlighted_issue`, `on_focus_cursor_table_focus_changed`, `on_screen_suspend`, `on_screen_resume` | `DataTable.RowHighlighted`, screen suspend and resume | Which rows relate: [`related_rows.py`](../../src/dashpot/observation/related_rows.py) via the controller |
| Opening Issues and Worktrees | `open_selected_issue`, `open_session_issue`, `open_bound_issue`, `action_open_issue`, `open_issue`, the two Worktree-table handlers | `push_screen`, `notify`, the store, `DashpotApp.request_identities` | Identity resolution: the page runner |
| Explicit mutations | `action_fetch`, `action_cleanup`, `cleanup_selection` | `self.focused`, the highlighted row | The flows: [`fetch_flow.py`](../../src/dashpot/ui/fetch_flow.py), [`cleanup_flow.py`](../../src/dashpot/ui/cleanup_flow.py) |
| Readouts | `update_diagnostics`, `update_alert`, `paint_readout` | the runners' errors, the launcher Diagnostics, the store's Diagnostics, two `Static` widgets | Both readouts: [`alerts.py`](../../src/dashpot/ui/alerts.py) |

The right-hand column is the finding. Each group's decision — what a pane
shows, how much height it gets, which rows relate to the cursor, which query
a filter bar has submitted, what either readout says — lives in a module
that tests exercise without a running App. The screen's methods gather
widget facts, call that module and paint the result, or forward a Textual
event to the collaborator that owns the reaction. The `dashpot` property
narrows `self.app` once so the screen reaches Dashpot-owned state (the
store, the runners, the flows) by name rather than through the Textual API.

The `pull-requests-pane` special cases the
[2026-09-13 review](../codebase-review-2026-09-13.md#apppy-decomposition)
counted are gone: `PaneSpec` carries `query_kind`, `controls`,
`controls_height`, `related` and `related_columns`, so the screen composes,
refits and re-lists every pane from its spec, and `filter_bars` maps each
paged kind to the one filter bar composed for it. The four named pane
accessors are the only literal pane ids left, and each names the pane a
handler must read: the highlighted Branch or Worktree for a Cleanup, the
Agent Session row for its bound Issue, and the pane `page_kind` finds focus
within. The Issue pane's `queue-pane` container is not a list pane and takes
no spec.

## Candidates assessed

Each candidate is weighed by what its caller would have to know, whether the
moved code coheres with its new home, what becomes testable, and the
protocol or callback surface it adds.

| Candidate | Benefit | Cost and decision |
| --- | --- | --- |
| A layout coordinator owning `fit_list_panes` and the two resize handlers | A class whose refit could be unit-tested. | `pane_layout.fit_panes` is that unit, tested in [`test_pane_layout.py`](../../tests/test_pane_layout.py). The 22 lines left read the body's height, the Issue pane's stylesheet minimum and each pane's count from widgets, then call `fit_rows` on each pane; a coordinator would take those as a protocol and still need the screen to call it from `on_body_resized`. Rejected. |
| A focus cycle object owning `focus_tables`, `cycle_list_focus` and the boundary handler | A place for the Tab and arrow-boundary rules. | The rule is one line: the next table in composed order, wrapping. It needs `self.focused` and `Widget.focus()`, which only a screen has, and `DashpotApp.action_focus_next` must still ask the visible screen. [`test_dashboard_interaction.py`](../../tests/test_dashboard_interaction.py) pins Tab, arrow boundaries and empty panes through the pilot. Rejected. |
| A query-submission controller for the search, lifecycle and ordering handlers | Fewer `@on` handlers on the screen. | `ListQueries` already owns what a filter bar submits, for both paged kinds; each handler left is a decorated Textual dispatch target that reads one control and calls it. Moving them to a plain object leaves the same handlers forwarding to it, or a mixin that reintroduces the MRO hazard below. `order_issues_by` is the only logic left (17 lines), and its tests drive the header through the pilot. Rejected. |
| An Issue-opening flow holding `selected_identity` and `open_when_resolved` with `open_issue`, `open_bound_issue` and `open_resolved_issue` | The wait for an off-page bound Issue becomes a plain state machine with a host protocol, as the mutating flows are. | That state lives on `DashpotApp`, not the screen, and `request_identities` also serves every refresh's bound-Issue resolution, so the flow would either own refresh identities too or split the state again. The wait is two fields and one predicate; `test_enter_resolves_a_bound_issue_off_the_page_before_opening_it` in [`test_dashboard_panes.py`](../../tests/test_dashboard_panes.py) pins it. Not warranted at this size; the first candidate to revisit if the wait grows (queued opens, a timeout, more than one pending identity). |
| A Worktree launch flow for `request_worktree_open` and `open_worktree` | Symmetry with the Remote Fetch and Cleanup flows. | Twenty-eight lines on the app with one field of state, the table's `opening` flag, which the table owns. The refusals are already pinned through the dashboard in [`test_app_worktree_launcher.py`](../../tests/test_app_worktree_launcher.py). A flow would add a host protocol for `notify`, `off_loop` and the table. Rejected. |
| A pure Diagnostics readout beside `summarize_alerts` | The four-source gathering, the Project prefix and the severity rank become testable without an App, in the module that owns the severity vocabulary; the screen stops repeating two rules that module already expresses as values (`Alert.severity`, `AlertItem.display`); and the two readout methods take one shape, painted by one method. | The screen still reads the observation runner, the launcher configuration, the fetch flow and the store to call it, as it does for the alert. No protocol or callback is added; the function returns the same `Alert` the alert does. Both codebase reviews named this assembly as the pure function left on the screen. **Chosen.** |
| Leave the screen whole | The dashboard's Textual surface is one class, its handlers thin, its decisions elsewhere. | Chosen for everything but the readout. |

## Why the screen stays cohesive

Textual runs a message handler on every class in the MRO that defines it,
subclass first, so a handler extracted to a mixin or base would either run
twice or force the `super()` call
[AGENTS.md](../../AGENTS.md#quality-and-code-conventions) forbids. The
handlers must stay on the one screen class; the convention the repository
already follows — a thin handler that delegates to a plain method or
collaborator, as `on_observation_finished` delegates to
`_accept_observation` — is what the screen does throughout. An extraction can
only take the delegate, and every delegate with a decision in it has now
gone.

Observation stays independent of the UI:
[`test_module_boundaries.py`](../../tests/test_module_boundaries.py) requires
the headless modules to load without Textual, and `summarize_diagnostics`
imports only what `summarize_alerts` already did.

Revisit when a screen method grows a decision of its own that the pilot
cannot reach cheaply, when a second screen needs the same handler, or when a
flow's host protocol would let a wait or a refusal be tested without a
running App, as the Cleanup flow's does. Line or method counts alone do not
reopen this.

## Verification evidence

The moved derivation is pinned twice: `test_healthy_state_has_no_diagnostics`,
`test_diagnostics_list_the_apps_own_failures_before_every_observed_line` and
`test_diagnostics_carry_the_severity_they_were_observed_with` in
[`test_alerts.py`](../../tests/test_alerts.py) assert the order, the Project
prefix and the severity without an App, and the Diagnostics box keeps its
existing tests through the widget —
`test_diagnostics_carry_the_severity_they_were_observed_with`,
`test_target_diagnostic_is_visible_without_hiding_project`,
`test_workspace_identity_conflict_is_visible_as_a_diagnostic` and
`test_failed_refresh_keeps_last_good_rows_and_shows_diagnostic` in
[`test_app.py`](../../tests/test_app.py) — so its content, severity class and
zero height when empty are unchanged.

The behaviours the Issue names are pinned through the public seams
[AGENTS.md](../../AGENTS.md#quality-and-code-conventions) requires — the
shipped dashboard built by `dashboard_app`, `App.run_test` and the pilot:

- Layout and pane fitting: `test_dashboard_stacks_the_panes_above_the_issues`,
  `test_pane_grows_with_its_records_to_the_cap_then_scrolls`,
  `test_panes_yield_height_before_the_issue_table_loses_its_minimum` and the
  breakpoint tests in
  [`test_dashboard_layout.py`](../../tests/test_dashboard_layout.py).
- Focus and cursor: `test_tab_cycles_focus_through_every_list`,
  `test_arrows_move_between_lists_only_at_row_boundaries`,
  `test_arrows_cross_empty_lists_in_composed_order`,
  `test_only_focused_dashboard_table_shows_its_row_cursor` and
  `test_slash_focuses_the_pull_request_search_from_its_table` in
  [`test_dashboard_interaction.py`](../../tests/test_dashboard_interaction.py).
- Related-row emphasis and theme repaint:
  `test_related_rows_have_background_and_bold_without_losing_glyph_colors` in
  [`test_app_activity.py`](../../tests/test_app_activity.py) and
  `test_a_theme_change_repaints_the_list_panes` in
  [`test_dashboard_panes.py`](../../tests/test_dashboard_panes.py).
- Search, lifecycle, ordering and page controls: the header, qualifier,
  lifecycle and count tests in `test_dashboard_interaction.py`.
- The alert and shutdown: `test_alert_is_hidden_and_takes_no_space_when_healthy`,
  `test_late_observation_is_dropped_after_dashboard_children_unmount` and
  `test_queued_refresh_indicator_is_harmless_during_shutdown` in `test_app.py`.
- Modal suspend and resume:
  `test_keyboard_mouse_focus_and_modal_emphasis_leave_other_panes_unchanged`
  in `test_app_activity.py` clears the emphasis while the Legend is up and
  restores it on Escape;
  `test_enter_opens_the_issue_view_and_escape_restores_the_table` and
  `test_refresh_while_the_issue_view_is_open_reaches_both_screens` in
  [`test_issue_screen.py`](../../tests/test_issue_screen.py) restore the
  selection, cursor and focus.
- Explicit user-action authority: the Remote Fetch and Cleanup keys are
  driven in [`test_dashboard_fetch.py`](../../tests/test_dashboard_fetch.py)
  and [`test_dashboard_cleanup.py`](../../tests/test_dashboard_cleanup.py).

No dependency, lockfile, UI or source/session change accompanies this
decision.
