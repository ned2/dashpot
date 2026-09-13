---
status: research
date: 2026-09-13
---

# Codebase review: clean-code uplifts and module boundaries (2026-09-13)

A point-in-time review of `src/dashpot/` at commit `b59032f` looking for
clean-code uplifts and, above all, for the logical boundaries along which the
flat package of 78 modules (about 24k lines) could become subpackages, and for
the seams along which its largest files — `app.py` first — could be decomposed.
Line numbers are as of `b59032f` and will drift; the findings are grounded in
the code as it stood, and every claim marked **verified** was reproduced
directly rather than taken from a review agent's report.

## Method

The `code-review` skill reviews a diff along two axes — Standards and Spec —
in parallel sub-agents. A whole-codebase review has neither a diff nor an
originating spec, so the skill was adapted:

- **Standards** kept its brief: conformance with the documented standards
  ([AGENTS.md](../AGENTS.md#quality-and-code-conventions),
  [domain language](domain-language.md), [design](design.md),
  [ADR 0013](adr/0013-adopt-pydantic-models-by-seam.md),
  [Textual implementation notes](textual-implementation-notes.md)) plus the
  fixed Fowler smell baseline the skill carries. It ran as two sub-agents so
  each could read its share: one over the domain, observation, and management
  modules; one over the presentation modules. A documented standard is
  reported as **hard**; a baseline smell is always a **judgement** call.
- **Spec** was replaced by a **Structure** axis: package boundaries derived
  from the intra-package import graph and the domain-language sections, and
  decomposition plans for the oversized files.

The import graph was computed with `ast` over every module. Fan-in leaders:
`model` 33, `issue_profile` 18, `models` 15, `repository` 12, `issue_list` 12,
`processes` 11, `commands` 11, `project_config` 11, `source_queries` 10,
`errors` 10, `git` 9. Fan-out leaders: `app` 30, `cli` 18, `collect` 16,
`paged_app` 15, `worktrees` 12.

## Structure

### Presentation leaks into the headless and CLI path (verified)

[Textual implementation notes](textual-implementation-notes.md) require the
headless `ObservationCoordinator` and its snapshots to stay independent of
Textual. At the import level they are not:

- Each of the five pane read models (`session_list.py`, `branch_list.py`,
  `worktree_list.py`, `pull_request_list.py`, `issue_list.py`) fuses a pure
  query (`query_session_list`, `SessionListRow`, `SessionListResult`) with
  Rich/Textual rendering (`build_session_rows`, `session_state_cell -> Text`)
  and imports `ListCell`, `ListColumn`, `ListRow`, and `truncate_end` from
  [`list_pane.py`](../src/dashpot/list_pane.py#L33-L64), a widget module.
- [`observation_store.py`](../src/dashpot/observation_store.py#L7-L32) and
  [`paged_store.py`](../src/dashpot/paged_store.py#L18) import the **private**
  `_query_indexed_*` functions from all five;
  [`collect.py`](../src/dashpot/collect.py#L40) imports the store;
  [`issue_resolution.py`](../src/dashpot/issue_resolution.py#L7) imports
  `collect.build_issue_source`; `work.py` and `worktrees.py` import
  `issue_resolution`.
- Consequently `import dashpot.work`, `import dashpot.worktrees`, and
  `import dashpot.collect` each load `textual` (checked in the checkout's
  `.venv`). `dashpot work start` — the hook-lifecycle path — pays for
  Textual. `hook_records` is still clean.

Other private cross-module reaches, each a missing public seam:
[`github_queries.py`](../src/dashpot/github_queries.py#L21-L28) imports
`_ISSUE_NODE_FIELDS`, `_issue_activity`, `_label_colors`, and
`_validate_grouping` from siblings and calls
`self.profiles._complete_nested_connections` (`:503`);
[`markdown_queries.py`](../src/dashpot/markdown_queries.py#L15-L20) imports
`_matches_search` and `issue_table.build_rows` (Rich output) only to sort a
Query Page; `paged_app.py:295,412,471` call `paged_store._row`;
`app.py:2063` calls `self.dashboard._update_widgets_mounted()`.

### `model.py`, `models.py`, and `issue_profile.py` (verified)

The split is principled but the names are not. `models.py` is Pydantic
infrastructure (the `DashpotModel` / `PublishedModel` / `PersistedRecord` /
`ConfigModel` bases, `LaxSequence`, `FrozenMapping`, `validate_degrading`);
`model.py` is the published observation domain (`ProjectSnapshot`,
`AgentRun`, `WorkspaceSnapshot`, …) plus three trusted dataclasses —
`RepositoryAnchor`, `Workspace`, `ResolvedProject`
([`model.py:193-211`](../src/dashpot/model.py#L193-L211)) — that belong
beside `workspace.py`; `issue_profile.py` is the Issue Profile seam. The two
Pydantic modules are the first and third most-imported in the package and
differ by one letter. Renaming `models.py` to something like `core/pydantic.py`
(or `seams.py`) removes the confusion.

### Proposed subpackage layout

Derived from the import graph and the domain-language sections (Declared
work, Observation, Presentation, Source queries):

```text
dashpot/
  core/          errors, commands, git, file_locks, json_records, record_store,
                 pydantic (= models), issue_profile, model (observation models only)
  project/       project_config, settings, workspace (+ the three dataclasses
                 from model.py), init
  github/        github (gateway), github_issues, github_pull_requests,
                 github_pull_request_search, + the GitHub identity functions
                 from repository.py:748-782
  issues/        issue_sources, pull_request_sources, local_markdown_issues,
                 issue_resolution, search, pull_request_search,
                 + build_issue_source / build_pull_request_source from collect.py:302-357
  queries/       source_queries, query_source, github_queries, markdown_queries,
                 page_navigation
  sessions/      harnesses, processes, liveness, session_matching, work_store,
                 hook_records, hook, agents, agent_bindings, work, integrate
  repository/    repository (Git observation), fetch, worktrees, cleanup,
                 cleanup_selection, worktree_launcher
  observation/   collect (the coordinator), observation_store, paged_store,
                 the query halves of the *_list.py modules, related_rows
  ui/            app (split, below), paged_app, list_pane, focus_table, keyed_table,
                 spread_table, worktree_table, pane_layout, marked_widgets,
                 item_filter, detail_fields, glyphs, issue_cells, issue_table,
                 column_editor, issue_view, cleanup_view, legend, alerts,
                 the rendering halves of the *_list.py modules, dashpot.tcss
  cli.py, serialization.py   stay top-level as the CLI wire seam
```

`core` is the fan-in floor. `sessions` is the domain-language Agent Session /
Agent Run / Work Store cluster, whose internal graph
(`work -> hook_records -> work_store -> record_store`) is already closed
except for `repository.repository_worktrees` and `issue_resolution`.
`repository/` is the Git-observing-and-mutating code that shares `Git`;
`cleanup.py` importing `repository` and `worktrees` is legitimate there.
`queries/` is a genuine mutual cluster (`configured_query_source` lazily
imports both adapters) and matches its domain-language section.

Edges the layout inverts, each marking misplaced code:

| Inverted edge | Fix |
| --- | --- |
| `observation -> ui`: the store imports `_query_indexed_*`; read models import `list_pane` | Move `ListColumn` / `ListRow` / `ListCell` / `truncate_*` to a widget-free module; split each `*_list.py` into a query module and a cells module (the split `issue_list.py` / `issue_cells.py` already has); make the index queries public. `relative_age` (`issue_cells.py:319`) is pure and moves to `core`. |
| `queries -> ui`: `markdown_queries.py:20` | Expose a sort key from the read model instead of `build_rows`. |
| `issues -> observation`: `issue_resolution.py:7` | Move `build_issue_source` and `build_pull_request_source` out of `collect.py`. |
| `sessions -> repository`: `processes.py:17` imports the `LockHolder` `Literal` | Define it in `processes`. `harnesses.py:22` already needs `TYPE_CHECKING` to dodge a cycle with `processes`. |
| `ui.alerts -> observation.collect` for `ObservationKey`, a ten-line dataclass | An `observation/keys.py` holding `ObservationKey`, `ObservationTicket`, `ObservationOutcome` (`collect.py:78-117`). |
| `cli.create_collector` (`cli.py:784-837`) and `cleanup_protection` (`:593-641`) are composition roots | Move them out so `cli.py` is parsing and printing. |

Modules that do not fit cleanly: `serialization.py` (a CLI wire seam over
`cleanup`, `worktrees`, and `model`; keep it beside `cli.py`),
`repository.py` (straddles Git observation and GitHub identity),
`worktree_launcher.py` (an adapter used by both the CLI and the app).

### `app.py` decomposition

**The base/paged split is unsound (verified).**
[`cli.py:35`](../src/dashpot/cli.py#L35) reads
`from .paged_app import PagedDashpotApp as DashpotApp`: production only ever
runs the paged app. `PagedDashboardScreen` overrides fifteen methods,
neutering `on_input_changed`
([`paged_app.py:128-131`](../src/dashpot/paged_app.py#L128-L131)) and
`sort_rows` (`:203-206`) to no-ops, dropping `sort` from `set_issue_query`,
and re-implementing `update_alert` verbatim plus one keyword (`:265-280`
against `app.py:1064-1079`). The base `DashpotApp` is constructed about 137
times across the test suite against four tests for the paged app, so the
suite exercises base-only behaviour production never runs: header-click
local sort (`app.py:620-646, 751-767`), incremental text filtering
(`:649-676`), and the whole `pull_request_searcher` path (`:1364-1443`;
`GitHubPullRequestSearcher` is never constructed in `src/`).
`SnapshotScheduler` (`collect.py:947`) and the
`SnapshotCollector | ObservationScheduler` union in `DashpotApp.__init__`
exist only for that fixture. `highlight_issue` (`app.py:913`) moves a cursor
in the base and pushes a screen in the paged app, so the name now misleads.

The recommendation is one app: fold the paged behaviour in, delete the dead
base-only paths and `SnapshotScheduler`, and re-point the tests at the shipped
class, injecting a store for in-memory snapshots rather than a different app
class. Highest value, highest risk.

Then extract, as plain objects unless noted:

1. `ui/panes.py` — `PaneRows`, `PaneRowsSource`, `PaneSpec`, the four
   `*_pane_rows` functions, `LIST_PANE_SPECS` (`app.py:130-251`). Pure.
2. `ui/messages.py` — the six `Message` classes (`:254-340`),
   `DashboardBody`, `CleanupSelection`.
3. `ui/observation_runner.py` — a coordinator owning `scheduler`,
   `in_flight`, `pending_rerun`, `observation_errors`, the refresh executor
   and indicator timer, with `schedule_observations` (`:1956`),
   `_finish_in_flight`, `_schedule_pending_rerun`, `observe`,
   `_accept_observation` (`:2075`), and `show_refreshing`. It needs
   `run_worker`, `set_timer`, and `post_message`, so it takes the app as a
   narrow protocol; the coalescing logic (`COALESCED_TRIGGERS`, `:119-127`,
   [ADR 0020](adr/0020-coalesce-requests-onto-the-observation-in-flight.md))
   becomes testable without Textual.
4. `ui/fetch_flow.py` — `request_fetch` through `record_fetch_result`
   (`:1445-1553`) and the `fetching` / `fetch_errors` state.
5. `ui/cleanup_flow.py` — `request_cleanup` through `reobserve_after_cleanup`
   (`:1555-1950`), the module helpers `cleanup_subject`,
   `cleanup_result_line`, `cleanup_summary` (`:1082-1103`), and the
   `cleaning` / `cleanup_previews` / `_cleanup_refresh_waiters` state.
   `fetch_cleanup_preview` (`:1738-1801`) is the one piece that genuinely
   needs screen access; `finish_cleanup_observation` (`:1833`) is the hook the
   observation runner calls back into.
6. `ui/pull_request_search_flow.py` — `:1356-1443` plus the nine
   `pull_request_search_*` attributes (`:1130-1138`), exposing
   `result(query) -> PaneRows` so `DashboardScreen._pull_request_pane_rows`
   (`:494-532`) stops reading app internals. Or delete it, per the finding
   above.
7. `ui/issue_table_controller.py` — `DashboardScreen`'s query state
   (`issue_view`, `rows_by_key`, `rendered_cells`, `selected_row_key`) with
   `reconcile_rows` (`:836-899`), `sort_rows`, `apply_issue_sort`, and
   `show_table_columns`. This is the screen's cohesion problem: it does
   composition (`:418`), pane fitting (`:792`), diagnostics rendering
   (`:1013-1062`), and is the Issue-table state machine. The controller
   drives a `DataTable`, so it is Textual-touching, but it is not a Screen.

After this, `DashpotApp` keeps bindings, `on_ready`, worktree opening
(`:1297-1336`), and delegation; `DashboardScreen` keeps composition, focus
cycling, and pane fitting; `app.py` drops to roughly 700 lines.

Cross-cutting inside `app.py`:

- Six worker coroutines share one `get_current_worker` / `run_in_executor` /
  `post_message(...Finished(error=...))` shape
  (`:1398, 1497, 1638, 1738, 1875, 2044`); one `run_off_loop(...)` helper
  removes about 120 lines and gives them one error boundary.
- Widget-id string cascades (`"queue"`, `"sessions"`, `"issue-search"`,
  `"pull-request-search"`, `"issue-state"`, `"pull-request-state"`) across
  `:649-718`, `:905-963`, and `paged_app.py:133-144`; Textual's
  `@on(Input.Submitted, "#issue-search")` removes them.
- `spec.pane_id == "pull-requests-pane"` is special-cased at `:373`,
  `:434-441`, and `:820`, undermining `PaneSpec`'s promise (`:155-160`) that
  adding a pane is adding a spec. `PaneSpec` could carry `controls`,
  `controls_height`, `count_widget`, and `related_columns`.

### Other large files

- **`cleanup.py`** (1173 lines): a cohesive domain with two phases and two
  vocabularies — preview (`inspect_cleanup` `:195` through
  `describe_cleanup_preview` `:656`) and perform (`Outcome` `:692` through
  `describe_cleanup_report` `:1091`) — plus `CleanupAdapter` (`:1133`). Split
  into `preview`, `perform`, and `adapter` modules over a shared `targets`
  module (`:57-192`).
- **`collect.py`** (1044): source factories (`:268-357`, to `issues/`),
  `ProjectCollector` and snapshot composition (`:156-266`, `:360-523`),
  `ObservationCoordinator` (`:532-941`), and the test-only
  `SnapshotScheduler` (`:943-999`, delete). `create_project_collector`
  (`:298`) always sets `query_source`, so the `self.source.refresh()` branch
  at `:183` is dead in production.
- **`hook_records.py`** (1042): its own docstring lists five jobs. Seams:
  record model and store (`:88-393`), publish and relocation (`:395-627`;
  `complete_session_work_relocation` reads every Work Store twice, before
  and inside the lock), classification and scanning (`:629-967`), claim
  validation (`:969` onward). `end_session_work` and
  `complete_session_work_relocation` belong beside `work_store.py`.
- **`worktrees.py`** (1025): two commands — create
  (`create_issue_worktree` `:124` through `describe_worktree_plan` `:614`)
  and removability (`check_worktree` `:652` onward); `cleanup.py:47-55`
  imports only the latter. Split accordingly.
- **`cli.py`** (863): the cyclopts commands are fine; extract the
  composition roots above and the `_cleanup` orchestration (`:554-590`).
- **`repository.py`** (789): target observation (`:120-350`), branch and
  integration observation (`:351-720`), GitHub identity (`:748-782`, which
  drags the `github` gateway into every hook run). Move the GitHub part; the
  rest is cohesive.
- **`github_issues.py`** (775): cohesive; at most extract the normaliser
  (`:497-763`) for reuse by `github_queries`.

## Standards

### Hard findings

| # | Finding | Standard |
| --- | --- | --- |
| 1 | **Verified.** [`repository.py:350`](../src/dashpot/repository.py#L350) `@dataclass(slots=True) class BranchObservation` is the only non-frozen dataclass in `src/`. | AGENTS.md: trusted internal values are frozen, slotted dataclasses. |
| 2 | **Verified.** The headless coordinator transitively imports Textual (see Structure). | Textual implementation notes. |
| 3 | **Verified.** The Legend omits shipped keys. [`app.py:1267`](../src/dashpot/app.py#L1267) builds it from `DashboardScreen.BINDINGS`, but production runs `PagedDashboardScreen` (`n`, `p`, `home` at `paged_app.py:94-105`) and `WorktreeTable` binds `enter` and `y` (`worktree_table.py:18`). | Domain language: the Legend lists the keys; `design.md`. |
| 4 | **Verified.** [`design.md`](design.md) and [`textual-implementation-notes.md`](textual-implementation-notes.md) say the Cleanup confirm button "is never disabled", while [`cleanup_view.py:488`](../src/dashpot/cleanup_view.py#L488) sets `button.disabled = self.busy or not self.preview_valid`. The code follows [ADR 0036](adr/0036-keep-cleanup-subjects-fixed-and-fetch-in-previews.md) ("Confirmation stays disabled through fetching"), which post-dates the rejected alternative in [ADR 0019](adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md); the premature-press case is still handled without disabling. The two documents are stale and ADR 0019 wants `amended-by` 0036. | `design.md`; AGENTS.md documentation-currency rule. |
| 5 | **Withdrawn** (see the erratum below). Two lint directives, [`github_issues.py:710`](../src/dashpot/github_issues.py#L710) `# ruff: ignore[any-type]` and [`app.py:1111`](../src/dashpot/app.py#L1111) `# ruff: ignore[mutable-class-default]`, were reported as not Ruff syntax and therefore inert. | AGENTS.md: an ignore names its rule. |
| 6 | **Verified.** Retired vocabulary is still threaded. The domain language retires *Reconciliation* ([ADR 0033](adr/0033-query-pages-and-independent-issue-resolution.md)), yet `reconcile=` is set at `app.py:1983`, carried through `ObservationTicket.reconcile` (`collect.py:103`), `ObservationScheduler.request`, `ProjectCollector.observe_issues`, and `IssueSource.refresh(reconcile=)` into `_reconcile_requested` (`issue_sources.py:140-165`), which nothing outside that class reads. `GitHubIssuesSource.reconcile_seconds` (`github_issues.py:218`) is stored and never read. | Domain language; AGENTS.md vocabulary rule. |
| 7 | Wrong Pydantic base for the seam. `ConfigModel` (`models.py:202`, "a configuration file whose key set is a closed contract") carries published observations in `source_queries.py:29-173` and GraphQL wire shapes in `github_queries.py:73-95`, `github_pull_request_search.py:62-83`, `github_pull_requests.py:100-136`. GitHub responses are hand-validated in `github_issues.py:690-760` (the idiom ADR 0013 records as retained) but Pydantic-validated in the three newer modules — two idioms for one seam with no recorded decision. | [ADR 0013](adr/0013-adopt-pydantic-models-by-seam.md) per-seam variants. |
| 8 | **Verified.** [`errors.py:9-13`](../src/dashpot/errors.py#L9-L13) states that every error reaching `cli.main` derives from `DashpotError`; `src/` has 93 bare `raise RuntimeError` sites against 17 `DashpotError` ones, and `PullRequestSourceRefreshError(RuntimeError)` (`pull_request_sources.py:42`) is off the base while its sibling `IssueSourceRefreshError` is on it. | `errors.py` contract. |
| 9 | Docstrings "one imperative line": about 109 noun-phrase first lines in the domain modules (`git.py:70`, `processes.py:273`, `cleanup.py:93`, …) and about 95 multi-line or noun-phrase docstrings in the presentation modules (`app.py:131,155,792,1445`, …). Pervasive enough that either the rule or the code wants adjusting. | AGENTS.md. |
| 10 | Domain-language *Avoid* notes: `cleanup_view.py:284` labels a checkout path "Repository:"; `spread_table.py:32` says "icon". | Domain language. |
| 11 | `design.md` pane column lists are stale: Sessions (first column is now `◈`), Worktrees ("five", now six), Branches ("seven", now eight). | AGENTS.md documentation-currency rule. |
| 12 | Trusted enumerations as bare `str`: the observation `trigger` (`app.py:113-122` frozensets), `PaneSpec.pane_id` / `table_id`, `paged_app.py:329-339` sources keyed by `"totals:issues"` strings, `QueryFinished.value: object` re-typed by `isinstance` / `cast` at `:430-448`; harness is `str` everywhere with ad-hoc validators (`hook_records._supported_harness`, `harnesses.adapter`); session state is `str` plus `cast(RunState, …)` at `agents.py:460`. | AGENTS.md: `Literal` unions. |

**Erratum (2026-09-13, #174).** Finding 5's premise was wrong for the pinned
toolchain. Ruff 0.16 with this repository's `preview = true` recognises
`# ruff: ignore[<rule>]` as its native suppression syntax, accepting the rule
name (`any-type`) as well as the code (`ANN401`): removing either comment makes
`any-type` and `mutable-class-default` fire, and the preview rule
`noqa-comments` flags a legacy `# noqa: ANN401` and auto-fixes it *to*
`# ruff: ignore[ANN401]`. Both directives are correct as written and were kept.

### Judgement findings

The highest-signal baseline smells; each is a heuristic, not a violation.

- **Dead or test-only surface.** `processes.nearest_codex_process`,
  `nearest_agent_process`, `nearest_harness_process` (`:188,243,250`);
  `issue_profile.semantic_projection`, `semantically_equivalent`
  (`:240,246`); `HookRecordStore.read` (`hook_records.py:372`);
  `AgentSessionIdentity.route` (`work.py:58`, written at `:163,181`, never
  read); `build_hook_record`'s `environ` parameter (`hook_records.py:170`;
  the comment at `:183-186` admits it is unused); `work.py:283`
  `if location is not None:` is always true after the raise at `:202`;
  `RowKind = Literal["issue"]` (`issue_list.py:16`) makes
  `observation_store.py:302` unfalsifiable; `PaneRows.title_count` is never
  set by any source; `ui_error` (`app.py:1225`), `project_label`
  (`app.py:2133`), `ListPane.highlighted_row` (`list_pane.py:239`) are
  test-only; `dashpot.tcss:253-258` targets a `SelectionList` that no longer
  lives under `#cleanup-targets`. The `integrate.install_codex_integration`,
  `remove_codex_integration`, and `codex_integration_status` wrappers
  (`integrate.py:321-349`) are test-only conveniences over `INTEGRATIONS`,
  not dead (**verified**, correcting the sub-agent).
- **Long functions.** `alerts.summarize_alerts` 187 lines (`:76-262`);
  `work.start_issue_work` 133 (`:185-317`); `github_queries.fetch_page` 134
  (`:179-312`); `repository._observe_target` 115 (`:201-315`);
  `hook_records.complete_session_work_relocation` 110 (`:471-580`);
  `work.relocate_issue_work` 105; `github_queries._resolve` 101;
  `CleanupScreen.compose` 89 (`cleanup_view.py:271-359`);
  `DashpotApp.__init__` 86.
- **Too many parameters.** `worktrees.create_issue_worktree` (11),
  `GitHubIssuesSource.__init__` (10), `cleanup.perform_cleanup` (7),
  `cleanup._inspect_worktree` (6), `hook_records.publish_hook_event` (6).
- **Data clumps.** `(record, role, branch, detached, diagnostics)` passed to
  `_unavailable` seven times (`repository.py:221-303`);
  `(branches, fetched_at, integration_ref, branch_anchor)` carried by
  `BranchObservation`, `RepositoryStateInventory` (`model.py:129-132`),
  `_SourceObservation` (`collect.py:377-380`), and `ProjectSnapshot`
  (`model.py:187-190`) — shotgun surgery for any new Branch fact;
  `cleanup_previews: dict[str, tuple[CleanupScreen, Path | None]]` indexed
  `[0]` / `[1]` (`app.py:1694-1795`); the nine `pull_request_search_*`
  attributes; positional eight-argument `PullRequestListResult(…, 0, 0)`
  (`paged_app.py:243-256`) and ten-positional `IssueListRow(…)`
  (`paged_store.py:60-71`).
- **Feature envy.** `SessionEvidence(work.harness, work.session_id, …)` is
  hand-built from `ActiveWork` at `work.py:672`, `work_store.py:330`,
  `hook_records.py:531`, and `agents.py:93`, and from
  `HookRecordClassification` at `hook_records.py:531,605,761,877` — both
  want an `.evidence` property; `Path(record.repository_root or record.cwd)`
  at `hook_records.py:610,707` and `agents.py:246`;
  `agents.work_process_key` (`:196`) duplicates `SessionProcess.key`, which
  `agents.py:145` already uses directly; the app writes screen state
  (`self.dashboard.pull_request_search_diagnostics = …` at
  `app.py:1367,1379,1436,1439`); `app.py:976-1005` re-runs three store
  queries on every cursor move to recover a run id the pane row could carry.
- **Repeated switches.** `ProcessAbsent -> gone`,
  `ProcessUnobservable -> unknown`, else `live` in `processes.py:106-113`
  and `liveness.py:357-367`; `issue_state_filter_value` and
  `pull_request_status_filter_value` are byte-identical (`app.py:2137-2150`)
  and their map recurs inline in `on_select_changed` (`:697-718`);
  `key.kind in ("targets", "workspace")` three times (`app.py:1549,1808,1947`);
  seven per-harness registries to edit when adding a harness
  (`harnesses.ADAPTERS`, `HARNESS_DISPLAY`, `processes.HARNESS_HOSTS`,
  `integrate.INTEGRATIONS`, `hook.main`, `cli.Harness`,
  `hook_records._supported_harness`) — pertinent to the
  [proposed OpenCode integration](opencode-integration-design.md).
- **Mysterious names.** `AgentRun.process_or_session` (`model.py:138`) holds
  `work.session_label` or `f"{session_id} hook"`;
  `ObservationCoordinator(local_only=recurring)` (`cli.py:836`) passes
  TUI-ness as "local only"; two different `Harness` names (`cli.py:67` a
  `Literal`, `hook_records.py:115` a validated `str`).
- **Hidden temporal coupling.** `GitHubQuerySource._meter` is assigned in
  `observe_context` (`github_queries.py:164`) and read in `fetch_page`
  (`:209`) and `fetch_totals` (`:325`), undeclared in `__init__`.
- **Blanket `except Exception`** at `query_source.py:274,321,357` and
  `github_queries.py:382,424,560`, against the named `OBSERVATION_FAILURES`
  tuple in `collect.py:143`.
- **Message boilerplate.** Twelve `Message` subclasses with hand-written
  `__init__` (`app.py:238-340`, `paged_app.py:56-60`, `list_pane.py:70-79`,
  `focus_table.py:75-89`, `worktree_table.py:25-33`,
  `cleanup_view.py:226-231`), about 80 lines; `paged_app.py:436,462-465`
  write `paged_store.totals` / `pages` directly with no revision bump, so
  `IssueListResult.revision` is meaningless in paged mode and nothing in
  `app.py` or `paged_app.py` reads it.
- **Reactive candidates.** `DashpotApp.refreshing_visible` with seven manual
  `update_alert()` calls; `CleanupScreen.busy`, `fetch_status`,
  `preview_valid` each followed by `refresh_state()`
  (`cleanup_view.py:499-541`); `FocusCursorTable.related_rows` /
  `related_columns` class-level attributes with a hand-rolled cache clear
  (`focus_table.py:22-34`). `WorktreeTable` (`worktree_table.py:22-23`)
  already shows the idiom.
- **Middle man.** `hook_records.write_hook_record` (`:290`, a one-line
  delegate with one caller); `sessions_pane()` through `pull_requests_pane()`
  (`app.py:454-464`) are four one-liners over `list_pane`.

### Cross-module duplication

The consolidation opportunities, in descending value:

1. **Two parallel "retain last-good" hierarchies.** `IssueSource`
   (`issue_sources.py:131-282`) and `PullRequestSource`
   (`pull_request_sources.py:50-128`) follow the same
   `refresh` / `_failed` / `_check_collection_invariants` / `_collect`
   template with parallel `*Diagnostic`, `*Observation`, `Collected*`,
   `*RefreshError`, `Clock`, and `IssueSourceStatus ≡ SourceStatus`
   (`model.py:17`). A generic `RetainingSource[T]` removes about 150 lines.
2. **Three Diagnostic shapes** with the same four fields, converted
   field-by-field fifteen times (`collect.py:198-206,218-226,423-431,1019-1026`;
   `github_queries.py:591-611`). `model.Diagnostic` alone suffices.
3. **Five near-identical pane read models.** Each `*_list.py` has an
   `XListRow` (key, project, record, sessions), an `XListResult(rows,
   revision)` with `count`, a `query_x_list(snapshot)` that rebuilds the
   snapshot index and is called only by tests, `_query_indexed_x_list`,
   `build_x_rows(result, dark, now)`, and `x_cells(row)`. A generic
   `ListResult[Row]` and one shared snapshot indexer (the store already owns
   `_issues_by_project` and friends at `observation_store.py:546-633`)
   delete the five builders; tests then query through
   `WorkspaceObservationStore(snapshot)`, the seam AGENTS.md prefers.
4. **Two query-source families over the same adapters.** `CachedQuerySource`
   wraps `GitHubIssuesSource` / `GitHubPullRequestsSource`
   (`github_queries.py:135-149`) and `LocalMarkdownIssuesSource`
   (`markdown_queries.py:51`) solely for `enumerate_source` / `find`, and
   `ProjectCollector.observe_issues` (`collect.py:181-207`) reconverts the
   enumeration back into an `IssueSourceObservation`.
5. **GraphQL wire models and constants.** `_PageInfo` three times,
   `_Repository` twice, `_Identity ≡ _RepositoryIdentity`,
   `_Search ≡ _SearchConnection`; Pull Request field selections in
   `github_queries.py:59`, `github_pull_request_search.py:48-52`,
   `github_pull_requests.py:84-88`; `_STATES ≡ _PULL_REQUEST_STATES`;
   `_RESPONSE_CODE` twice, shadowing `github.MALFORMED_RESPONSE` (`:37`).
6. **Small helpers, many copies.** Path equality
   (`hook_records._resolves_to:619`, `work._same_worktree:634`, inline
   `.resolve() ==` at `work_store.py:264`, `agents.py:514`,
   `cleanup.py:1067`, `worktrees.py:468`); "worktree records to resolved
   non-bare paths" four times (`repository.py:56-60`,
   `worktrees.py:153-157,646-650,745-749`); timestamp helpers
   (`hook_records.now_iso`, `issue_sources.utc_now`, `observed_instant`,
   `repository._utc_timestamp`, a bare `fromisoformat` at
   `work_store.py:341`); atomic write (`record_store.replace:147-169`,
   `integrate._write_json:667`, `_write_text:682`); last-stderr-line
   (`fetch._failure_detail:117`, `cleanup._last_line:1086`);
   repository-relative check (`project_config._repository_relative:17`,
   `issue_profile._repository_relative_path:97`, `init.py:41-43`);
   `NonEmptyString` (`models.py:210`) and `issue_profile._NonEmptyString`
   (`:105`); `HookSessionIdentity` defined twice (`hook_records.py:114`,
   `work_store.py:41`); `RemovalObstacle` (`worktrees.py:84`) ≡
   `CleanupBlocker` (`cleanup.py:92`); store sweeping
   (`agents.sweep_work_store:182-193` against `agents.py:410-414`, wanting
   `LockedRecordStore.sweep()`); session-label formatting
   (`work.py:160,174-178`, `hook_records.py:567-571`); hook-store list
   building three times (`hook_records.reachable_hook_stores:714`,
   `agents.py:227-229`, `agents.py:356-378`).
7. **Colour tuples** `("#9a6700", "#d29922")` re-declared in `glyphs.py:55`,
   `worktree_list.py:35,37`, `pull_request_list.py:22`.

## Summary

- **Structure**: six layout inversions and one unsound inheritance split.
  The worst is the base/paged app split — production runs code the suite
  barely tests, and the suite tests code production never runs.
- **Standards**: twelve hard findings, three of them user-visible (Legend
  keys, the Cleanup button against its design, `dashpot work` importing
  Textual); about twenty judgement smells; seven consolidation clusters. The
  worst is the Textual import leak into the hook-lifecycle path.

The axes are deliberately not ranked against each other.

## Suggested sequencing

Ordered by value over risk. Each of 2–7 is an Issue-sized task and, per the
[tracking policy](../AGENTS.md#tracking-and-notes), belongs in a GitHub Issue
rather than in this document; nothing below has been filed or started.

1. **Quick wins with no design decision**: Legend bindings (`app.py:1267`),
   freeze `BranchObservation`,
   delete the dead `reconcile` thread and the listed dead code, refresh the
   `design.md` column lists, and resolve the Cleanup-button doc/code drift.
2. **Break `observation -> ui`**: move `ListRow` / `ListColumn` / `ListCell`
   out of `list_pane.py`, split rendering out of the five `*_list.py`
   modules, make the index queries public. Mechanical; restores the
   documented layering and takes Textual out of `dashpot work`.
3. **Break `issues -> observation`**: move `build_issue_source` and
   `build_pull_request_source` out of `collect.py`.
4. **One app**: fold `PagedDashpotApp` into `DashpotApp`, delete
   `SnapshotScheduler` and the dead base-only paths, re-point the tests.
   The biggest payoff; needs a session of its own.
5. **Extract the four flows and the observation runner from `DashpotApp`**,
   the table controller from `DashboardScreen`, and the `run_off_loop`
   helper.
6. **Consolidations**: `RetainingSource[T]`, one `Diagnostic`, a generic
   `ListResult`, shared GraphQL wire models, the small-helper dedupes.
7. **Subpackages with re-export shims**, following the layout above. Low
   risk once 2 and 3 are done; it also resolves the
   `processes -> repository.LockHolder` and `harnesses <-> processes` cycles.
