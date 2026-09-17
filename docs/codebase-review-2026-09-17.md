---
status: research
date: 2026-09-17
---

# Codebase review: refactor audit and current state (2026-09-17)

A point-in-time review of `src/dashpot/` at commit `fcd17ce`, after the
structural arc planned by the
[2026-09-13 review](codebase-review-2026-09-13.md) and recorded as complete in
[ADR 0042](adr/0042-group-leaf-and-domain-modules-into-subpackages.md). It has
two halves: an **audit** of whether that plan landed as intended, and a
**fresh review** of the code as it stands. Line numbers are as of `fcd17ce`
and will drift. Every claim marked **verified** was reproduced directly (by
script, a fresh-interpreter import, or reading the code) rather than taken
from a review agent's report.

Baseline at the reviewed commit: `uv run pre-commit run --all-files` clean;
the local review gate's coverage run passed 1596 tests with 96% line coverage
(source digest `b8648b6a…`).

## Method

Four review agents ran in parallel, each read-only: a structure audit (package
layout and import graph against the plan), a standards-findings audit (the
plan's twelve hard findings, dead surface, long functions, registries), and two
fresh reviews split at the `ui/` boundary. The import graph was recomputed
with `ast`, distinguishing runtime from `TYPE_CHECKING`-only edges. Claims
that contradicted the earlier review's erratum or looked like correctness
bugs were re-verified by hand; one agent finding (that `# ruff: ignore[…]` is
not Ruff syntax) was reproduced as false and dropped, confirming the erratum
in the earlier review.

## Audit: what landed

The structural arc landed as recorded. Verified:

- **Layout matches ADR 0042 exactly.** A programmatic diff of the ADR's
  ownership table against `find src/dashpot -name '*.py'` shows no missing,
  extra, or misplaced module. Every package initializer is empty except the
  documented Cleanup facade and the root `__init__.py`. No old-path re-export
  shims exist.
- **The headline inversion is gone.** `import dashpot.sessions.work`,
  `dashpot.observation.collect`, `dashpot.repository.cleanup`, and
  `dashpot.issues.issue_resolution` each leave `textual` and `dashpot.ui`
  unloaded in a fresh interpreter; `dashpot.hook` also leaves the GitHub
  gateway and the coordinator unloaded. `tests/test_module_boundaries.py`
  guards this.
- **All six inverted edges** from the plan's table are fixed at the named
  sites: `list_rows.py` holds the widget-free row shapes; `source_factories.py`
  holds the source builders; `LockHolder` lives in `processes`;
  `observation/keys.py` holds the scheduling keys; `composition.py` holds the
  composition roots and never imports `cli`.
- **`app.py` decomposition:** all seven planned extractions exist
  (`panes`, `messages`, `observation_runner`, `fetch_flow`, `cleanup_flow`,
  `issue_table_controller`, and the "delete it" branch for the Pull Request
  searcher), plus `page_runner`, `run_off_loop` as the single off-loop error
  boundary, `@on(..., "#id")` selectors, and a `PaneSpec` that carries
  `controls` / `related_columns`. The base/paged split is gone;
  `SnapshotScheduler` lives only in `tests/app_harness.py`.
- **Large files split as planned:** `cleanup` into four modules and a
  facade, `hook_records` into five, `worktrees` into four, GitHub identity out
  of `repository.py`, composition roots out of `cli.py`.
- **Hard findings closed:** Legend keys (`app.py:670-683`, with `g`
  replacing `home`), the Cleanup button doc/code drift with ADR 0019 marked
  amended by 0036, the `reconcile` thread, `BranchObservation` frozen, the
  Pydantic seam split (ADR 0041), `design.md` column lists, the `Anchor:`
  label, `ObservationTrigger` as a `Literal`, typed page messages, the
  `_meter` temporal coupling, the query-path blanket `except`s, and every
  item on the dead-surface list except `ListPane.show_rows(title_count=)`.
- **Consolidations:** one `ListResult[Row, Summary]`; `RetainingSource` for
  both collection sources; `github_wire.py` for the shared GraphQL shapes;
  `timestamps.py`; per-harness registries reduced from seven to `ADAPTERS`
  plus four edit points; ADR 0043 records the deliberate rejection of the
  query/collection merge.

## Audit: what did not land, or landed differently

| # | Finding | Status |
| --- | --- | --- |
| 1 | **Verified.** Five package-level runtime import cycles remain: `sessions <-> repository`, `issues <-> repository`, `project <-> repository`, `observation <-> queries`, `github <-> issues`. Three share one cause: the generic path helpers `same_path`, `is_within`, `worktree_root`, `worktree_records`, `main_worktree` live in the 770-line `repository/repository.py` (`:757-770`) and are imported by seven `sessions` modules, `issues/issue_resolution.py:9`, `project/init.py:14`, and `project/workspace.py:28`, while `repository` imports `sessions.processes`, `sessions.liveness`, `sessions.work_store`, and `project.settings`. The #186 helper consolidation widened the `sessions -> repository` edge the plan wanted removed. `observation <-> queries` is `queries/markdown_queries.py:18-25` importing sort and search helpers from `observation.issue_list` while `observation` imports `queries.source_queries`. The plan called `core` the fan-in floor; nothing in the test suite asserts package acyclicity. | Resolved by #238: the graph is acyclic, `tests/test_module_boundaries.py` asserts it, and ADR 0042 records the layering |
| 2 | **Verified.** `composition.py:33` imports `QUERY_SOURCE_KEYS` from `ui.page_runner`, so `import dashpot.composition` loads Textual. ADR 0042 places composition beside the headless entry points; the module-boundary test checks only that it leaves `cli` unloaded. | Resolved by #238 |
| 3 | **Verified.** `core/errors.py:9-11` still promises that every error reaching `cli.main` derives from `DashpotError`, but 93 bare `raise RuntimeError` sites remain (28 in `sessions/work.py`, 10 in `integrate.py`, 6 in `worktree_launcher.py`, …) and `cli.py:735-739` keeps a `RuntimeError` arm "while bare raise sites migrate". The sibling asymmetry (`PullRequestSourceRefreshError`) is fixed. `composition.py:88,131` catch `RuntimeError` by type to mean "not a repository", so a genuine runtime fault is misread. | Resolved by #239: every refusal site raises a seam's `DashpotError` subclass, `cli.main` catches `DashpotError` alone, and [ADR 0046](adr/0046-raise-every-refusal-as-a-dashpoterror-subclass.md) records the `RuntimeError` exemptions |
| 4 | **Verified.** Bare `str` where a `Literal` exists: harness is `str` in `core/model.py:154`, `sessions/work.py:52`, `work_store.py:140`, `harnesses.py:60,70`, `hook_scan.py:47-48`; `hook_records.py:72-73` validate `Harness` / `ActiveState` as annotated strings while `cli.py:63` defines a second, unrelated `Harness = Literal[...]`; `cast(RunState, …)` at `sessions/agents.py:429`; `PaneSpec.pane_id` / `table_id` (`ui/panes.py:95-96`). | Resolved by #239: `Harness`, `HARNESS_DISPLAY`, and `RunState` live in `core/model.py` and `ActiveState` in `hook_records.py`, each defined once; the `cast` and the second `Harness` alias are gone; `PaneSpec` ids are `Literal`s |
| 5 | Docstring rule: about 224 of 765 docstrings in `src/` open with a noun phrase or run to several lines (`ui` 77, `sessions` 48, `repository` 44). Most are class and property docstrings where a noun phrase is the natural form. The rule in AGENTS.md is unconditional and no amendment is recorded. | Resolved by #239: the rule admits a noun phrase for a class, a property, or a function that only answers a question, and every module has a docstring |
| 6 | **Verified.** `docs/domain-language.md:215` lists `github-reconciliation-overdue` as a live Diagnostic code; nothing in `src/` emits it. `docs/textual-implementation-notes.md:26-37` shows a `DashboardScreen` tree with `source-status` and a detail pane that `app.py:161-179` no longer composes; `:357` names a `SelectionList.SelectedChanged` handler the Cleanup screen no longer has. `docs/design.md:319` says the Issues `◈` column renders `▶` / `Ⅱ`, but `issue_cells.py:51` reuses the session glyphs `●` / `◐` / `○`. | Open (documentation currency) |
| 7 | **Verified.** `observation/paged_store.py:35` imports the private `_StoreState` from `observation_store` and the subclass overrides `_commit` and reads `self._state`; the private-reach test guards only the five read models. `DashboardScreen._update_widgets_mounted` is called from two other objects (`app.py:938`, `issue_table_controller.py:206`), the reach the plan flagged at the old `app.py:2063`. | Resolved by #238 for the store seam: `StoreState` is public and the private-reach test covers every module; the cross-object calls remain, through the public `surfaces_mounted` #248 renamed it to |
| 8 | **Verified.** ADR 0042's deferral of session-label formatting names `hook_records` as the second seam; after #227 it is `sessions/work_reconciliation.py:147-151`, with further wordings at `agents.py:436` and `hook_claims.py:60`. `ListPane.show_rows(title_count=)` (`list_pane.py:134,167`) is still dead. `observation/session_list.py:22` `HARNESS_LABELS` hand-copies `harnesses.HARNESS_DISPLAY` because observation may not import sessions; the duplication is unrecorded. | Minor; `HARNESS_LABELS` removed by #239, which moved `HARNESS_DISPLAY` to `core/model.py` |
| 9 | The 2026-09-13 review's source links were re-pathed to the new module locations but kept `b59032f` line fragments, so `app.py#L1267`, `#L1111` (the file is 971 lines), `repository.py#L350`, and about ten others point at the wrong lines. `scripts/check_docs.py` checks only the path half of a fragment. | Minor; pin them to the `b59032f` blob URL or drop the fragments |

Long functions were not shortened: `summarize_alerts` (187 lines),
`fetch_page` (133), `start_issue_work` (132), `_observe_target` (113),
`relocate_issue_work` (105), and `_resolve` (101) are unchanged, and five more
crossed 80 lines (`resolve_workspace_projects`, `normalize_github_issue`,
`markdown_queries.fetch_page`, `create_issue_worktree`, `issue_metadata_items`).
The plan listed these as judgement smells, and ADR 0042 leaves them advisory.

## Fresh review: hard findings

| # | Finding | Standard |
| --- | --- | --- |
| 1 | **Verified.** The hook publisher lets a `ValueError` escape as a traceback. `hook.py:26` catches `(OSError, JSONDecodeError, RuntimeError)`, but `HookRecordStore.write` raises `ValueError("hook destination is occupied by another Agent Session Identity")` at `sessions/hook_records.py:285`, and `HookRecord(...)` construction at `:152` can raise a Pydantic `ValidationError`, which is a `ValueError`. Nothing in `hook_publish.py` catches either. The exit code is still the non-blocking 1, but the harness sees a Python traceback instead of the one-line `dashpot … hook:` report. | `hook_records.py:140` contract: a hook must never break its harness |
| 2 | **Verified.** Three `_on_*` overrides call `super()`: `ui/focus_table.py:65` (`_on_mouse_move`), `:76` (`_on_leave`), `ui/spread_table.py:83` (`_on_resize`). Textual dispatches by name on every MRO class, and `DataTable` defines all three, so the base handler runs twice; a scratch reproduction printed `['sub', 'base', 'base']`. The duplicated bodies are idempotent today, but `focus_table.py` is the base of every dashboard table. | AGENTS.md handler rule |
| 3 | **Verified.** `serialization.py` promises one document shape per command, but `cli.py:364-371` builds the `issue list` / `pr list` JSON inline with `model_dump`, bypassing the module and the key-set pin in `tests/test_serialization.py`. `cli.py:355` also carries a function-local import of `QueryRequest` that the module already imports at top level. | `serialization.py:1-8` contract |
| 4 | **Verified.** `ui/detail_fields.py:16` is `@dataclass(frozen=True)` without `slots=True` and without a rationale; the eight `@dataclass(eq=False)` messages in `ui/messages.py:65-131` are the model for how such an exception should be recorded. | AGENTS.md dataclass rule |
| 5 | **Verified.** `issues/retaining_source.py:55` turns every `Exception` from an adapter's `_collect`, including `AssertionError` and `TypeError`, into an `-internal` Diagnostic, while `core/observation_errors.py:5-6` says programmer faults must escape and the query adapters honour that. ADR 0043 records the containment as deliberate history, so this is a recorded inconsistency between the two halves of one "shared implementation" rather than a defect. | `observation_errors.py` contract; ADR 0043 |

## Fresh review: judgement findings

Ordered by signal, not by package.

- **Cleanup vocabulary lives in `worktrees`.** `BlockerKind` / `CleanupBlocker`
  (`repository/worktrees/removability.py:31-49`) include kinds only
  `cleanup/preview.py` produces (`integration-branch`, `remote-mapping`,
  `push-url`, `protected`); `cleanup/targets.py:12` imports them back and the
  Cleanup facade re-exports a sibling package's class. Moving them to
  `cleanup/targets.py` creates no cycle. `repository/cleanup_selection.py`
  likewise sits outside the package whose policy it holds.
- **Three integration-ref choosers.** `repository.py:473-500`,
  `cleanup/preview.py:74-108` (`_RefIndex`), and `worktrees/base.py:24-71`
  (`resolve_base`) derive the same fact from `for-each-ref` or
  `symbolic-ref`; `removability.py:296-298` and the Cleanup preview of the
  same Worktree can disagree. `preview._integration_fact` and
  `removability.assess_branch_preservation` count the same `rev-list`.
- **Small helpers re-duplicated across the split halves:**
  `preview._branch_name` vs `records.short_branch`; `preview._checked_out_at`
  and `perform._registered` beside `records.registered_at`.
- **`CleanupHost` is wide.** `ui/cleanup_flow.py:47-69` needs ten members
  (`screen`, `screen_stack`, `push_screen`, `run_worker`, `off_loop`, plus
  `FlowHost` and `OffLoopHost`) against three for `ObservationHost`; the flow
  imports `get_current_worker` and writes `CleanupScreen` attributes directly
  (`:275,335,349`). Its two `except Exception` sites (`:328,362`) lack the
  boundary comment `app.py:773` carries, and `:363` reads an empty `str(exc)`
  as a timeout.
- **`IssueTableController` controls the whole dashboard.** It reaches through
  the screen to `dashpot.queries`, `.store`, `.submit_page` and back into
  screen widgets (`issue_table_controller.py:118-220`); its unit test covers
  only two pure functions. The Pull Request query trio on the screen
  (`app.py:325-360`) duplicates the Issue trio in the controller line for
  line, so query state has asymmetric ownership, and `panes.py:157-158`
  fabricates a zeroed `PullRequestListSummary` to reuse a row builder.
- **Four `build_*_rows` are eight-line near-copies** (`session_cells.py:68`,
  `branch_cells.py:177`, `worktree_cells.py:43`, `pull_request_cells.py:99`);
  a `build_list_rows(result, cells)` deletes them. Their `home=` parameter is
  test-only. Colour tuples are only partly centralised: `pull_request_cells.py:30,54`
  and `issue_cells.py:38-41` keep inline greys and reds that differ from
  `glyphs.MUTED_COLORS` / `BAD_COLORS` by one channel.
- **Hook records are validated then de-typed.** `hook_records.py:152-173`
  builds a `HookRecord`, dumps it, and every reader downstream
  (`hook_publish`, `work_reconciliation`, `:176-239`) works on
  `dict[str, Any]` with camelCase keys.
- **Query-driven coordinator reports `fresh` for never-observed halves.**
  `observation/collect.py:695-706` substitutes `unavailable` placeholders and
  `:740` then sets `status="fresh"` when `query_driven`.
- **Store duplicate-identity `ValueError` escapes `publish()` mid-loop**
  (`observation_store.py:557-632` under `collect.py:548-559`), leaving later
  pending Projects unpublished. Suspected only; sources already enforce
  uniqueness upstream.
- **`create_project_collector` residue:** `collect.py:190` accepts an unused
  `state_dir`; `:207-217` constructs fallback sources then assigns
  `collector.query_source` post-hoc (the redundant construction ADR 0043
  names); `:406` types the factory as `Callable[..., ProjectObserver]`.
- **Middle men and pass-throughs:** `hook_records.write_hook_record` (`:242`),
  `removability._count` (`:428`), four `result = …; return result` blocks in
  `observation_store.py:230-273`, the four pane accessors at `app.py:189-199`.
- **Two message idioms in one package:** five `Message` subclasses still
  hand-write `__init__` (`list_pane.py:44`, `cleanup_view.py:232`,
  `focus_table.py:131`, `worktree_table.py:25-33`) beside the dataclass
  messages whose module docstring says no message does.
- **Reactive candidates not adopted:** `FocusCursorTable.related_rows` /
  `related_columns` (`focus_table.py:29-30,88-94`) keep the hand-rolled cache
  clear while `WorktreeTable` and `CleanupScreen` adopted `reactive`.
- **Legend gaps:** `IssueScreen` `escape`, `CleanupScreen` `escape` / `f`,
  `IssueColumnEditor` `ctrl+up` / `ctrl+down`, and the `Tab` focus cycle
  (`app.py:646-657`, an override with no Binding) are absent, and no test
  asserts coverage of every shipped binding.
- **`DashboardScreen` still spans ten responsibilities** (`app.py:95-583`,
  composition through diagnostics and alert rendering); the diagnostics
  assembly at `:524-541` is a pure function waiting to be extracted. ADR 0042
  and Issue #234 already record this as deferred. Assessed by #234:
  [ADR 0047](adr/0047-keep-the-dashboard-screen-as-one-textual-adapter.md)
  keeps the screen as one Textual adapter and moves the diagnostics assembly
  to `ui/alerts.py` as `list_diagnostics`.
- **Widget-id pairing is untested:** `item_filter.py:70-84` composes
  `f"{item}-search"` while `app.py:316,325` and `dashpot.tcss:105,109` spell
  the ids literally. `dashpot.tcss:270-272` and `:546-549` repeat one rule.
- **`DashpotApp.worktree_path` (`app.py:786-793`) re-queries the store** on
  every `y` / `Enter` although `PaneRows.records` exists so a cursor action
  never queries the store.
- **Missing module docstrings** on 18 non-UI modules after the moves,
  including `observation/collect.py`, `observation_store.py`, `keys.py`,
  `cli.py`, `hook.py`, `sessions/work.py`, `repository/repository.py`.
- **Tests:** six files read Textual's private `app._notifications` and one
  reads `app._close_all`; a `toasts(app)` helper in `app_harness.py` would
  confine that. Three fixed `pilot.pause` calls remain
  (`test_dashboard_interaction.py:785`, `test_header_tooltips.py:66,88`).
  `tests/test_paged_app.py` is named for a deleted module and is the one file
  building `DashpotApp` directly, legitimately as an end-to-end variant.
  Sixteen `ui/` modules have no `test_<module>.py` and are covered indirectly.
  No sampled test reaches a private name of a flow, runner, store, or
  controller; direct file writes behind a store exist only for states the
  store cannot produce.

Correctness paths that came out clean: file-lock inode re-check
(`core/file_locks.py:22-34`), hook-then-Work-Store lock ordering, coordinator
generation re-check under `_state_lock`, and Cleanup perform's fingerprint
comparison before any mutation.

## Summary

- **Audit:** the plan landed. Layout, extractions, splits, and nine of the
  twelve hard findings are closed and verified; ADR 0042's ownership table is
  exact. What did not land is layering below the package names (five runtime
  cycles, `composition` loading Textual), the error-base contract, the
  `Literal` rule for harness and state, and the docstring rule.
- **Current state:** the suite is green at 96% coverage and the new seams
  (Cleanup facade, `worktrees/base` and `records`, `hook_scan`,
  `observation/keys`, `ListResult`, the runners) are genuinely deep. The two
  defects worth fixing first are the hook `ValueError` traceback and the
  `super()` calls in `_on_*` handlers. The remaining findings are placement
  and duplication left by the split, each Issue-sized.

## Suggested sequencing

Each group is tracked as a GitHub Issue, per the
[tracking policy](../AGENTS.md#tracking-and-notes).

1. **Defects** (#237): catch `ValueError` in `hook._run`; drop the `super()` calls
   in `focus_table.py` and `spread_table.py`; route `issue list` / `pr list`
   output through `serialization.py`.
2. **Finish the layering** (#238): move the path helpers to `core`, move
   `QUERY_SOURCE_KEYS` out of `ui`, give `queries` its own sort and search
   seam, make `_StoreState` public, then assert package acyclicity in
   `tests/test_module_boundaries.py`.
3. **Close the contracts** (#239): migrate the 93 `RuntimeError` sites onto
   `DashpotError` and drop the CLI's `RuntimeError` arm, or record why not;
   one `Harness` and `RunState` `Literal` in `sessions/harnesses.py`; amend
   the docstring rule. Landed, with the `Literal`s in `core/model.py` so
   that observation can share them
   ([ADR 0046](adr/0046-raise-every-refusal-as-a-dashpoterror-subclass.md)).
4. **Documentation currency** (#240): the three stale passages in finding 6, the
   old review's line fragments, and ADR 0042's `hook records` wording.
5. **Cleanup placement and duplication** (#241): `CleanupBlocker` into
   `cleanup/targets`, one integration-ref chooser, the record helpers.
6. **UI consolidation** (#242): generic `build_list_rows`, the colour constants,
   one message idiom, the Pull Request query trio into the controller,
   Legend coverage test. Issue #234 owns the further screen extraction.
