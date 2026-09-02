---
status: research
date: 2026-08-31
---

# Codebase review — 2026-08-31

A wholesale review of Dashpot at commit `f3a5eea` covering correctness, code
smells, modularity and abstraction, conciseness, test quality, and project /
engineering hygiene. Five parallel reviewers each took one slice
(agent-observation core; repository / worktrees / collection; Issue sources;
Textual UI; CLI and project hygiene), and a cross-cutting pass looked at the
module dependency graph. Every High finding and a sample of the rest were
re-verified against the source before being included; three UI bugs and two
parsing bugs were reproduced with throwaway tests.

Line numbers are as of `f3a5eea` and will drift.

## Health summary

The project is in good shape. All gates are green and nothing here is a
"rescue":

| Check                                      | Result                                          |
| ------------------------------------------ | ----------------------------------------------- |
| `uv run pytest -q`                         | 565 passed, 47 subtests, ~26 s; slowest 1.3 s   |
| `uv run ruff check` / `ruff format --check` | clean                                           |
| `uv run ty check`                          | clean                                           |
| `uv lock --check`                          | consistent                                      |
| Tracked artefacts                          | clean (no `dist/`, `scratch/`, caches, state)   |
| Wheel contents                             | includes `dashpot/dashpot.tcss`                 |
| Markdown links (31 files)                  | 6 broken (1 in README, 5 in one stale doc)      |
| Internal import cycles                     | none at runtime (`agents`↔`harnesses` is `TYPE_CHECKING` only) |

Strengths worth preserving: the liveness / observability distinction and
"never mistake *cannot observe* for *exited*" invariant in `agents.py`; the
lock-file relink dance in `file_locks.py`; pure read models feeding the UI; the
single-sourced Glyph vocabulary and the Legend test that scans for unexplained
glyphs (ADR 0010); the conformance fixtures used as expected output by both
Issue Sources; `test_worktrees.py` driving real Git through public functions;
the `GIT_*` scrubbing in `scripts/check_quality.py`; and AGENTS.md, whose
every command and flag claim checks out against the code.

The problems cluster in four places: a few genuinely wrong edge cases; three
god modules (`agents.py`, `app.py`, `test_app.py`) with clean-but-unused seams;
duplication that has started to diverge; and the gap between the documented
domain model (frozen values, typed Issue Profile) and what the code declares.

## Top priorities

Ranked by severity × blast radius ÷ effort. Each is expanded in the area
sections below.

| #  | Finding                                                                                            | Sev  | Eff | Ref   |
| -- | -------------------------------------------------------------------------------------------------- | ---- | --- | ----- |
| 1  | Hook publisher exits **2** on failure — Claude Code treats that as a *blocking* error              | High | S   | O-C1  |
| 2  | A hook publisher path containing a space is never recognised by `integrate` (macOS-typical)        | High | S   | R-C1  |
| 3  | Detached HEAD discards the successful `repositoryRoot` lookup → record routed to the global store  | High | S   | O-C2  |
| 4  | Theme change repaints the Issue table but not the three list panes                                 | High | S   | U-C1  |
| 5  | Broken ADR 0003 link in README (ships as the PyPI long description)                                | High | S   | H-D1  |
| 6  | Packaging metadata has no license expression, classifiers, urls or authors (blocks Issue #5)       | High | S   | H-P1  |
| 7  | Removability reported as `true` on missing evidence (dropped Work Store diagnostics; swallowed base refusal) | Med | S | R-C2, R-S8 |
| 8  | Typing in the search box silently resets a chosen sort                                             | Med  | S   | U-C3  |
| 9  | `IssueSource.refresh` only converts `IssueSourceRefreshError`; other exceptions escape ADR 0002    | Med  | S   | I-C3  |
| 10 | `stop --session` can end a live sandboxed session's run (liveness guard skipped)                   | Med  | S   | O-C5  |
| 11 | One stale Issue Source anywhere hides real dangling bindings everywhere                            | Med  | S   | O-C6  |
| 12 | No `[tool.pytest.ini_options]` (no warnings-as-errors, asyncio mode by default, import mode implicit) | Med | S | H-T1  |
| 13 | Domain values are mutable, contradicting AGENTS.md and forcing six `deepcopy` calls on hot paths   | High | M   | R-A2  |
| 14 | No git adapter — three parallel ways to run git, tests patch module globals                        | High | M   | R-A1  |
| 15 | `agents.py` (1363 lines) is six modules; three duplicated scan loops; `HookRecordStore` ≡ `WorkStore` persistence | High | M | O-S1, O-A1, O-A2 |
| 16 | `DashpotApp` is a god object because there is no dashboard `Screen`; bindings leak to other screens | High | L  | U-S1, U-C2 |
| 17 | `Issue = dict[str, Any]` leaves a precisely specified 20-field record untyped across ~10 modules   | High | L   | I-A3  |

## Cross-cutting themes

### 1. The documented model is stricter than the declared one

AGENTS.md: "Domain values are frozen, slotted dataclasses." In `model.py` only
`RepositoryAnchor`, `Workspace` and `ResolvedProject` are frozen; `Diagnostic`,
`ObservationTarget`, `Branch`, `AgentRun`, `ProjectSnapshot`,
`ProjectObservation`, `WorkspaceSnapshot`, `IssueActivity`,
`IssueSourceObservation` and `IssueBindingResult` are all `@dataclass(slots=True)`.
The cost is paid in `collect.py` (six `deepcopy` calls, one of the whole
composed project map on every Agent Run observation), `observation_store.py`
(`detail_for` and `checkpoint` deep-copy on every cursor move and several times
per alert refresh), and in tests that mutate builder output after construction.
Freezing the values (and switching `list` fields to `tuple`) removes a whole
class of aliasing bugs the copies currently defend against — and nothing tests
that defence today (R-T15).

Likewise ADR 0002 defines a closed 20-field Issue Profile that
`issue_profile.conform_issue` enforces at runtime, but `Issue: TypeAlias =
dict[str, Any]` means the type checker knows nothing; consumers mix
`issue.get("assignees", [])` with `issue["state"]` and a typo is a runtime
`KeyError` in the render path. A `TypedDict` (or a frozen dataclass) returned
by `conform_issue` is the single largest gap between the domain language and
the code.

### 2. God modules with clean, unused seams

`agents.py` (1363), `app.py` (916), `issue_table.py` (715), `test_app.py`
(3421) and `test_collectors.py` (1779) each hold five or more concerns whose
boundaries are already visible in the code. In every case the split is
mechanical; the cost of not splitting is discoverability (there is no
`tests/test_agents.py` for the largest module in the package) and drift between
copies.

### 3. Duplication that has begun to diverge

- Three "scan hook stores → classify → keep freshest" loops in `agents.py`
  that already disagree on tie-breaking (`>` vs `>=`).
- `HookRecordStore` and `WorkStore` persistence layers are character-for-
  character identical except that one unlinks its lock inline and the other
  leaves it to the pruner.
- Two snapshot assemblers in `collect.py` (`ProjectCollector.refresh` and
  `ObservationCoordinator._compose`) with different diagnostic ordering and
  last-good rules; production only calls one.
- Two Issue Source factories (`configured_issue_source` and
  `create_project_collector`) with two wordings of one refusal and two default
  timeouts (10 vs 20).
- Four read models re-implement the same ~20-line snapshot-indexing prologue.
- Three copies of "restore the cursor by key, else nearest index".
- Two validator families in `github_issues.py` doing the same checks with
  different exceptions.
- Four rival temp-git-repository builders and five `issue()` builders across
  test modules; no `conftest.py`.

### 4. Layering: the read models' real seam is named private

`observation_store.py` imports `_query_indexed_{issue,session,branch,worktree}_list`
from four sibling modules. Those are the only production entry points; the
public `query_*_list(snapshot)` wrappers are used exclusively by tests. The
leading underscore is actively misleading about which function is the
contract. (`worktrees.py` importing `agents`, `harnesses` and `work_store` is
a heavier dependency than its name suggests, but is not a cycle.)

### 5. Errors that are swallowed rather than surfaced

A recurring pattern is a diagnostic being computed and then dropped:
`check_worktree` ignores Work Store read failures; `observe_branches` returns
`[]` for diagnostics once any anchor answers; `_branch_obstacles` passes a
throwaway `_Preparation()` to discard base-resolution refusals;
`work._session_work` throws away `store.active()` diagnostics; the app's
observation handler swallows every `NoMatches` from the whole reconcile;
`_observe_integration` returns the input unchanged on a git failure. Each is
individually defensible; together they contradict the project's own framing
that a failure "yields a diagnostic, never silence".

## Findings by area

Severity High / Medium / Low; effort S / M / L. IDs are prefixed by area
(O = observation core, R = repository & collection, I = Issue sources,
U = UI, H = CLI & hygiene). Full per-slice write-ups, with quoted snippets and
proposed code, are listed under *Source material* at the end.

### Observation core (`agents.py`, `hook.py`, `work.py`, `work_store.py`, `agent_bindings.py`, `observation_store.py`, …)

**Correctness**

- **O-C1 · High/S — Hook publisher returns exit code 2.** `hook.py:22`
  returns 2 on any publish failure. Claude Code's hook contract: exit 2 is a
  *blocking* error — stderr is fed back to Claude and the action is denied.
  Dashpot registers `UserPromptSubmit`, `Stop`, `SessionStart`, `SessionEnd`
  and `PostToolUse`, so a read-only `.dashpot`, a full disk or an unexpected
  event name erases the user's prompt or refuses to let Claude stop. A passive
  observer must never do that. Return 1; put the code on the harness spec if
  Codex needs something else; add a test pinning the value per harness
  (nothing does today).
- **O-C2 · High/S — Detached HEAD discards `repositoryRoot`.**
  `agents.py:406-411` wraps `rev-parse --show-toplevel` and `symbolic-ref`
  in one `try`; `symbolic-ref` exits 1 on a detached HEAD (bisect, `worktree
  add --detach`, a checkout by SHA) and `repository.git()` raises, throwing
  away the successful root. The record then routes to the **global** store,
  `locate_observation_target` falls back to a cwd prefix match, and the ADR
  0009 relocation check compares the wrong path. Guard the two calls
  independently (`work.py:268` already does this for branch alone).
- **O-C3 · Med/M — `ps -o comm=` with spaces misparses `lstart`.**
  `agents.py:196-206` assumes `comm` is one token; on macOS it is the full
  executable path. A space shifts the fields, `started_at` becomes garbage,
  and because liveness compares it as an exact string every later probe reads
  **gone** — manufacturing a false Orphaned Agent Run. Put free-form fields
  last or drop `comm`.
- **O-C4 · Med/S — Cross-worktree conflict missed across identity routes.**
  `agents.py:1023-1040` keys a run by *either* process or session id,
  preferring process; two records for one session written by different routes
  never collide, so the `work-session-conflict` diagnostic is not raised.
  `work._session_work` already matches on either key; reuse it.
- **O-C5 · Med/S — `stop --session` can end a live sandboxed run.**
  `work.py:357-364` skips the liveness guard when `session_process is None`,
  which is exactly the identity-route case the feature exists for. Fall back
  to `locate_agent_session` when only a session id is recorded.
- **O-C6 · Med/S — Binding validation deferred on *any* stale project.**
  `agent_bindings.py:64`: `any(status != "fresh" …)` over the whole Workspace,
  so one flaky GitHub source downgrades every genuine dangling binding to
  "deferred". Scope to the run's own project. The existing test name encodes
  the bug.
- **O-C7 · Low/S** — `ObservedActivityIndex._by_process` silently keeps one
  session per process key (`--resume` under the same PID).
- **O-C8 · Low/M** — `process_namespace_is_isolated()` returns False inside a
  Docker/Podman container, so every session reads `gone`; also re-reads
  `/proc/1/cmdline` per session per tick (memoize).
- **O-C9 · Low/M** — `build_hook_record` forks two `git` processes per hook
  event; combine into one call.
- **O-C10 · Low/S** — Freshness tie-breaking differs (`>` at `:795,:826`,
  `>=` at `:1119`).
- **O-C11 · Low/S** — `work_store.py:112` embeds an absolute path in a
  Diagnostic id, against "identity is never derived from labels or paths".
- **O-C12 · Low/S** — `_replace` in both stores has no `fsync` and orphans
  its temp file on a crash; nothing sweeps them.
- **O-C13 · Low/S** — `IssueBindingResult.agent_runs` is a pass-through of
  the input and the dataclass is not frozen.

**Structure & abstractions**

- **O-S1 · High/L — Split `agents.py`** into `processes.py` (probing,
  ancestry, namespace), `liveness.py`, `hook_records.py` (store, authoring,
  routing, reading, scanning), a slim `agents.py` (observation entry points)
  and `json_records.py` (validation helpers). The seams have almost no
  internal coupling.
- **O-A1 · High/M — One `scan_hook_stores()` seam** replacing the three
  copies (`locate_agent_session`, `sessions_at_worktree`,
  `observe_hook_sessions`) plus a fourth in `summarize_session_records`.
- **O-A2 · High/M — One `LockedJsonRecordStore`** under both
  `HookRecordStore` and `WorkStore` (identical `_locked`, `_lock_path`,
  `_replace`, `orphaned_locks`); the natural home for O-C12.
- **O-S2 · Med/M** — `observe_work_runs` is 85 lines, five deep; extract
  `_work_run`, `_orphan_diagnostic`, `_run_identity`, `_sweep_orphaned_locks`.
- **O-S3 · Med/M** — The `issueId` promotion machinery in
  `HookRecordStore.write` (~35 lines, plus `DASHPOT_ISSUE_ID`/`_REF`) keeps
  data that `record_to_session` now rejects with a warning. Delete or comment
  the removal condition.
- **O-S7 · Med/S** — `observation_store.py` imports four `_query_indexed_*`
  private functions (see cross-cutting §4).
- **O-A3 · Med/M** — Liveness is modelled twice (`SessionLiveness` and
  `HookRecordOutcome`); carry a `LivenessObservation` on the classification.
- **O-A4 · Med/S** — `locate_observation_target(raw, cwd, …)` re-parses
  untrusted JSON its caller already validated; pass the classification.
- **O-A5 · Med/S** — `work._session_work` discards `store.active()`
  diagnostics; a corrupt record for this session's key silently produces a
  second record.
- **O-N1 · Med/S** — `nearest_harness_process` re-implements the ancestry
  walk and silently `break`s on `ProcessUnobservable`, losing the
  sandboxed-vs-no-harness distinction.
- Low: `_stop_elsewhere(…, None)` name contradicts its use; two `X as X`
  re-exports nothing imports; `nearest_codex_process`/`nearest_agent_process`
  are test-only; `_metadata_updates` splats an untyped dict into `replace()`;
  "atomically" in `WorkspaceObservationStore` means exception-safe, not
  thread-safe; redundant `^…$` anchors on regexes used with `fullmatch`;
  `settings.py` hard-fails on unknown fields written by a newer Dashpot;
  five identical "index, raise on duplicate" functions in
  `observation_store.py`.

**Tests**

- **O-T1 · High/M** — No `tests/test_agents.py`; ~1000 of `test_collectors.py`'s
  1779 lines test `agents.py` and `work_store.py`. Split to mirror O-S1.
- **O-T3 · High/S** — Nothing pins the hook exit code.
- **O-T2 · Med/S** — Hook-record JSON literals hand-built in five modules;
  add a `hook_record(**overrides)` builder to `tests/helpers.py`.
- **O-T4 · Med/M** — Untested: detached HEAD, `stop --session` on an
  identity-route record, `sessions_at_worktree` directly, per-project
  freshness in bindings, spaced `comm`, two sessions sharing a process key,
  cross-harness session-id collision.

### Repository, worktrees, collection, configuration (`repository.py`, `worktrees.py`, `collect.py`, `workspace.py`, `model.py`, `integrate.py`, `init.py`)

**Correctness**

- **R-C1 · High/S — Hook path with a space is never recognised.**
  `integrate.py:455` does `command.split()[0]` on the unquoted command string,
  so `/Users/Jane Doe/…/dashpot-claude-code-hook` fails the name check.
  Verified. `install` appends a duplicate handler every run, `remove` leaves
  it behind, and `--status` says "not installed" — the exact line AGENTS.md
  tells agents to trust. Match the whole string, or write the command as a
  list. No test covers a spaced path.
- **R-C2 · Med/S — `check_worktree` drops Work Store diagnostics.**
  `worktrees.py:746` `active, _diagnostics = …`: a corrupt record for a live
  Agent Run yields `removable: true` with no obstacle.
- **R-S8 · Med/S — `_branch_obstacles` swallows base-resolution refusals**
  (`worktrees.py:798`, throwaway `_Preparation()`), so with no chosen base the
  `unmerged` obstacle silently never appears. Use `choose_integration_ref` and
  report the missing Integration Branch.
- **R-C3 · Med/S** — `observe_branches` returns `[]` for diagnostics once
  one anchor answers; failed anchors are invisible. The test asserting this is
  named as if the opposite were true (R-T4).
- **R-C12 · Med/M** — `to_jsonable` omits `None` fields, so `--json` key
  sets vary by outcome; `is_dataclass` is also true for classes.
- **R-C4 · Low/S** — `_observe_integration` / `_unintegrated_commit_count`
  swallow git failures; a failing `rev-list` looks like "no Integration
  Branch".
- **R-C5 · Low/S** — `for-each-ref` output split on newlines while the
  format includes `%(worktreepath)`; the worktree parser uses `-z` for this
  exact reason.
- **R-C6 · Low/S** — `_write_json` narrows an existing hook file to 0600.
- **R-C7 · Low/S** — `remove_integration` deletes a hooks file whose only
  remaining key is an unexplained magic `"description"`.
- **R-C8 · Low/S** — `integrate codex --status` reports the *other*
  harness's publisher as installed.
- **R-C9 · Low/S** — `init` threads a `runner` seam but `worktree_root` /
  `github_repo_from_remote` bypass it.
- **R-C10 · Low/S** — `assert plan.base_commit is not None` in production
  (`worktrees.py:504`), stripped under `-O`.
- **R-C11 · Low/S** — `_resolve_base` resolves the same ref twice.

**Structure & abstractions**

- **R-A1 · High/M — Introduce a `Git` adapter** (`root`, `timeout`,
  injectable `runner`; `run` / `text` / `maybe`). Today: `repository.git()`
  hard-codes `run_command`; `observe_*` thread a `CommandRunner`; `worktrees.py`
  has eleven raw `run_command(["git", …])` sites each re-doing returncode
  handling. Unblocks R-C9, R-S2, R-T5, R-T6, R-T7.
- **R-A2 · High/M — Freeze the observation values** (cross-cutting §1) and
  delete the six `deepcopy` calls in `collect.py`. `_SourceObservation.elapsed_ms`
  is the one genuine mutation and can be set at construction.
- **R-A3 · High/L — Type the Issue Profile** (cross-cutting §1; see I-A3).
- **R-S1 · High/M** — `observe_observation_targets` is 215 lines with six
  copies of one failure block; split discovery from per-record observation
  with an `_unavailable(...)` helper (~120 lines → ~40).
- **R-S3 · High/M** — `ProjectCollector.refresh()` is a second, drifting
  snapshot assembler that production never calls; `SnapshotScheduler` is in
  the same position. Delete or make it the single factory `_compose` uses.
- **R-S7 · Med/M** — Refusals accumulate via a mutable `_Preparation` bag
  passed as an out-parameter; pure `_check_*() -> list[str]` reads better.
- **R-S5 · Med/S** — Two different `ObservationKind` Literals with the same
  name in `collect.py` and `observation_store.py`.
- **R-A4 · Med/S** — `to_jsonable` / `camel_case` are a wire contract living
  in `model.py`; move to `serialization.py`.
- **R-A5 · Med/S** — `ObservationTargetInventory` tunnels Branches through a
  type named for targets.
- **R-A6 · Med/S** — `create_project_collector` has no seam for its own
  repository lookups; tests patch `dashpot.collect.worktree_root`.
- Low: `state_dir` is a dead parameter; `"refs/heads/"` spelled inline six
  times beside `LOCAL_REF_PREFIX`; `create_issue_worktree` rebuilds the plan
  field-by-field (`replace(plan, dry_run=False, created=True)`); legacy
  `*_codex_*` wrappers kept alive only by tests; `_utc_timestamp` returns its
  input on a parse failure; `workspace.py` hand-rolls key validation that
  `project_config._require_keys` already provides; serial `gh api` calls per
  anchor at startup; O(n²) untyped `_ordered_unique`.

**Tests**

- **R-T11 · High/M** — `test_collectors.py` god module (see O-T1); a stray
  mid-file `unittest.main()` at `:1614` would skip six classes outside pytest.
- **R-T13 · High/M** — Six process-wide `mock.patch.object(Path, "is_dir")`
  calls (one around threads) and `Path.stat` / `Path.read_bytes` patches;
  `test_coordinator.py` shows the right pattern (real `tmp_path` dirs).
- **R-T14 · High/M** — `test_overlapping_refreshes_are_serialized` passes
  whenever the threads merely fail to overlap; use an `Event` handshake.
- **R-T15 · High/S** — Snapshot aliasing is untested and
  `FakeProjectCollector` pre-deepcopies, so deleting every `deepcopy` in
  `collect.py` leaves the suite green. Prerequisite for R-A2.
- **R-T16 · High/M** — `create_project_collector` and its two user-facing
  config guards have no direct test.
- **R-T1 · Med/S** — `test_integrate.py` exercises the legacy wrappers, not
  `install_integration(harness, …)`; the `PostToolUse`+`EnterWorktree`
  matcher machinery ADR 0009 depends on is under-covered.
- **R-T21 · Med/S** — `resolve_hook_command` has zero tests; Codex array-form
  commands, malformed shapes, and group-drop rules on the matched
  subscription are unexercised.
- **R-T3 · Med/S** — Exact-argv assertions pin implementation (adding
  `--no-optional-locks` would break four tests).
- Med/Low: cross-module test imports (`from test_work import issue_document`);
  golden full-sentence assertions; `subTest` loops sharing state; an
  un-joined thread in `test_coordinator.py:485`; `_verify_worktree` branches
  unexercised; builder output mutated after construction (only possible
  because values are mutable).

### Issue sources (`github_issues.py`, `local_markdown_issues.py`, `issue_sources.py`, `issue_profile.py`, `issue_resolution.py`, `issue_list.py`)

**Correctness**

- **I-C3 · Med/S — `refresh()` only converts `IssueSourceRefreshError`.**
  `issue_sources.py:59-65`. A `TypeError`/`KeyError` from an unforeseen GraphQL
  shape or an `OSError` from `gh` (`_graphql` catches only `RuntimeError`;
  `run_command` maps only `FileNotFoundError`/timeout) bypasses the
  stale/last-good machinery and propagates out. `ProjectCollector.refresh`
  calls it outside its `try`; the async path guards it — an asymmetry. Add a
  final `except Exception` producing a `<source>-internal` diagnostic.
- **I-C1 · Med/S — Markdown discovery order violates its own contract.**
  `local_markdown_issues.py:75` `sorted(path.rglob("*.md"))` sorts by parts,
  not POSIX path; verified `a/b.md` sorts before `a-b.md`, the documented
  order is the reverse. Order is observable (issue list, JSON, duplicate
  diagnostics). One-line fix; the existing order test cannot distinguish.
- **I-C2 · Low/S** — Symlinked *directories* are silently skipped (`rglob`
  does not descend them), contrary to the conformance doc's "rejected".
- **I-C6 · Med/M** — Every refresh re-fetches every Issue body with a
  per-`gh`-call timeout only; a 2 000-issue repository is 20 sequential
  calls per tick with no overall budget and no conditional fetch.
- **I-C9 · Med/M** — Resolving one hint (`work start 35`) performs the full
  paginated collection; `IssueSource` has no `find(hint)` seam.
- **I-C10 · Med/S** — Duplicate-identity / duplicate-number invariants are
  re-implemented per adapter with different codes and messages; the
  conformance README states them as *profile* rules.
- **I-C4 · Low/S** — `_graphql` should catch `OSError` too.
- **I-C5 · Low/S** — Linked PRs truncated at 20 with no `pageInfo`; document.
- **I-C7 · Low/S** — Error classification substring-matches localisable
  stderr; prefer GraphQL `error.type` / `HTTP \d{3}` first. Ordering hazard:
  "resource not accessible" checked after "authentication".
- **I-C8 · Low/S** — Hint matching is exact, case-sensitive and unstripped;
  pasting the printed Issue URL back fails.

**Structure & abstractions**

- **I-A1 · Med/M — `IssueSource` hooks communicate through mutable instance
  state.** `refresh()` calls `_collect`, `_collect_label_colors`,
  `_collect_issue_activity` in a required order; the GitHub adapter stashes
  `self._label_colors` / `self._issue_activity` during `_collect` for the
  other two to return. Invisible to subclass authors, not thread-safe, and a
  failed `_collect` leaves last cycle's colours. Replace with one
  `_collect() -> CollectedIssues` and make the base a real ABC. Natural home
  for I-C10's shared invariants (I-A2) and `find(hint)` (I-C9).
- **I-A3 · High/M — `Issue = dict[str, Any]`** (cross-cutting §1). A
  `TypedDict` mirroring the schema, returned by `conform_issue`, costs nothing
  at runtime and would have caught the `.get`-vs-`[]` inconsistency.
- **I-A4 · Med/S — Two Issue Source factories** (`configured_issue_source`
  vs `create_project_collector`) with drifted wording, different default
  timeouts (10 vs 20), and only one applying `worktree_root()` normalisation.
- **I-S1 · Med/M** — Two parallel validator families in `github_issues.py`
  (~90 near-duplicate lines) differing only in the exception raised;
  `GitHubIssueNormalizationError` is only ever caught to be re-wrapped.
- **I-S6 · Med/S** — `IssueListRow.issue: Issue | None` and
  `RowKind = Literal["issue"]` are dead optionality that forces a
  `ValueError` in `issue_view.py:53` and the `issue_of()` test helper.
- Low: dead `"repository"` branch in `_response_object`; `_PAGE_SIZE` used
  by only half the queries; `IssueSourceObservation` not frozen; `row_key`
  lives in `issue_list.py` but serves every list; `IssueSearchField.values`
  is an eight-way `if self is …` ladder; `_collect` is one 60-line `try`;
  `parse_issue_search` runs two-to-three times per query across layers;
  redundant `isinstance` guards on typed parameters; `createdAt <= updatedAt`
  unconstrained (say so if intentional).

**Tests**

- **I-T1 · Med/S** — `test_issue_list.py` builds six-key "Issues" no adapter
  can produce; the `.get` defensiveness is load-bearing for tests only. Build
  from the conformance fixture with overrides.
- **I-T3 · Med/M** — `conformance/issue/issue.schema.json` is executed by
  nothing; at minimum assert its `required` list equals `_ISSUE_KEYS`. The
  shared conformance suite asserts only the observation lifecycle; adapter
  output conformance is re-implemented ad hoc per adapter.
- **I-T2 · Med/S** — Local Issue document builders duplicated across four
  modules; `test_issue_resolution.py` imports from `test_work.py`.
- **I-T4 · Med/S** — Markdown grammar edge cases untested (unclosed front
  matter, missing/empty title, `#Title`, `# Title #`, CRLF, blank lines
  before the title, `.MD`/`.markdown`).
- Low: ambiguous-hint branch untested (reachable — reference uniqueness is
  not enforced); GitHub branch of `configured_issue_source` untested;
  `Path.read_text` patched class-wide; argv indexed by position; no
  stale→fresh recovery test; nested pagination loop only ever entered once.

### Textual UI (`app.py`, `*_list.py`, `issue_table.py`, `list_pane.py`, `alerts.py`, `legend.py`, …)

**Correctness** (C1–C3 reproduced headlessly)

- **U-C1 · High/S — Theme change repaints only the Issue table.**
  `app.py:325` calls `reconcile_rows()` but not `reconcile_list_panes()`;
  pane cells carry raw hex colours chosen by `dark=`. After
  `theme = "textual-light"` the queue cell moves `#238636 → #1f883d` while the
  Sessions STATE glyph stays on `#3fb950`. One line plus a regression test.
- **U-C2 · Med/M — Dashboard bindings act on the hidden dashboard.**
  `/`, `c`, `o`, `s`, `shift+s` are App-level and unguarded; with the Issue
  view open, `/` focuses the inactive dashboard's search Input, `c` stacks the
  column editor over the Issue view. Root cause: no dashboard `Screen` (U-S1).
  Cheap fix: the `self.screen is not self.main_screen` guard that
  `cycle_list_focus` already uses.
- **U-C3 · Med/S — Search keystrokes discard the chosen sort.**
  `app.py:417-426` `sort=issue_search_sort_terms(...) or DEFAULT_SORT` on every
  keystroke; an `s`-selected `SortTerm('number')` reverts after one
  character. Override only when the parsed search names a sort, or on the
  transition where a `sort:` qualifier is removed.
- **U-C4 · Med/S** — Cold-load spinner sticks forever if the first accepted
  observation publishes no store change (`app.py:596-610` returns before
  clearing `loading`).
- **U-C5 · Med/S** — `show_row` leaves `selected_row_key` on the *previous*
  row when `detail_for` returns `None`, so `open_issue` opens the wrong
  Issue.
- **U-C6 · Med/S** — The observation handler wraps the entire reconcile in
  `except NoMatches: return`; a mistyped selector becomes a UI that silently
  stops updating. The shutdown race is already covered by the guard above it.
- **U-C7 · Med/S** — `detail_for` deep-copies a whole Project on every
  cursor move to read one `primary_anchor`.
- **U-C8 · Med/S** — `summarize_alerts` calls `store.checkpoint()` three
  times (each a full workspace deep copy) and `update_alert()` runs 2–3×
  per accepted observation — ~6 workspace copies per refresh.
- **U-C9 · Low/S** — `if self._closing or self._closed or not self.screen_stack`
  copied four times; Textual-private state is load-bearing. One `is_live`
  property with the comment attached.
- Low (U-C10): unreachable `RuntimeError` in `sort_rows` inside a message
  handler (enforce in `IssueTableViewState.__post_init__`); `_justify_cell`
  silently half-renders a wrong-arity row; `RowsChanged` posted on every
  `show_rows` so all panes refit every refresh; column editor has no keyboard
  Apply and never clears its error; Legend lists App bindings even from the
  Issue view; `highlight_issue` moves the cursor without focusing the table.

**Structure & abstractions**

- **U-S1 · High/L — Extract `DashboardScreen`.** `DashpotApp` (916 lines)
  holds composition, pane-height arithmetic, worker scheduling, observation
  acceptance, Issue-table reconciliation, view-state, diagnostics/alerts and
  focus cycling. `main_screen` / `screen_stack[0]` gymnastics, the four
  `_closing` guards and the binding leak (U-C2) all follow from the missing
  screen. Then split an `IssueTableView` controller out of it.
- **U-S2 · Med/M** — The three list panes are configured in four parallel
  places (`LIST_TABLE_IDS`, three `ListPane(...)`, three accessors, three
  branches in `reconcile_list_panes`) plus the ids in `dashpot.tcss`. One
  `PaneSpec` tuple.
- **U-S3 · Med/M** — Four read models duplicate the ~20-line
  snapshot-indexing prologue; one `SnapshotIndex`.
- **U-S4 · Med/S** — Promote `_query_indexed_*` to the public seam
  (cross-cutting §4).
- **U-S5 · Med/M** — `issue_table.py` mixes cell types, chip rendering, the
  column catalogue, the view-state machine and sorting; none depends on
  Textual, so the split is cheap.
- **U-A1 · Med/M** — One `KeyedTableView` (reconcile rows by key + restore
  cursor by key) for `ListPane.show_rows` and `reconcile_rows`; removes the
  third copy of the restore block (U-N1) and gives panes incremental updates.
- **U-A3 · Med/M** — Make `fit_list_panes` / `pane_wish` a pure
  `fit_panes(body_height, minimum, wishes) -> caps`, as `spread_widths`
  already is; ~160 lines of layout tests become unit tests.
- Low: `ListColumn` and `ColumnSpec` are the same idea at two ambition
  levels; `cells_match` is an `isinstance` ladder; dead `project_label`,
  `highlighted_row`, `empty_issue_message` (the last is a *missing feature* —
  the Issue table has no empty state); "queue" appears 29× but is not a
  domain term (pane title is ISSUES); `on_theme_changed` named like a Textual
  message handler; four identical 8-line `tcss` blocks; severity-class
  juggling written twice; inverse state-filter maps; `SpreadTable` lazy
  dicts.

**Tests**

- **U-T1 · Med/M** — `test_app.py` is a 3421-line, 90-test monolith covering
  ≥8 modules that have their own test files; split by subject.
- **U-T2 · Med/S** — Fixture builders re-implemented in five modules with
  differing defaults; `tests/helpers.py` exists for this.
- **U-T3 · Med/M** — Three tests prove negatives with wall-clock sleeps /
  polls and carry comments admitting slow-runner races; use
  `run_test(message_hook=…)` and an injected clock.
- **U-T5 · Med/S** — None of U-C1..C5 has coverage.
- Low: tests reach `_border_title`, `app._notifications`, the event loop's
  `_default_executor`; an 88-line kitchen-sink test asserts constants
  verbatim and `not hasattr(app, "snapshot")`.

### CLI (`cli.py`)

- **H-C1 · Med/S** — `main()` catches only `RuntimeError`; three domain
  errors subclass `ValueError` and ~12 sites raise bare `ValueError`.
  Containment today is incidental (via `IssueSource.refresh`), not
  contractual; the README's "one-line `dashpot:` diagnostic, exit 2" promise
  is untested per error family. Introduce a `DashpotError` base or widen the
  `except` with a comment naming the contract.
- **H-C2 · Med/S** — `cli.py:376-381` re-parses the `"refused: "` string
  prefix off rendered lines to split stdout from stderr while `plan.refusals`
  is already structured two lines later.
- **H-C3 · Low/S** — `Path.cwd().resolve()` repeated eight times; every CLI
  test must `monkeypatch.chdir`.
- **H-C4 · Low/S** — `--compact-json` is undocumented; the default command
  declares `--json` inline instead of via the shared `_JsonOutput` alias, so
  help strings differ; `issue show` prints a dict directly while the
  snapshot goes through `to_jsonable`.
- **H-C5 · Low/S** — `dashpot work` with no subcommand exits 0 (deliberate;
  README's blanket exit-2 rule does not mention the exception).
- **H-C6 · Low/S** — Unused `type_` converter parameter; `resolve()` inside
  an argument converter; `test_cli_module_no_longer_uses_argparse` is an
  obsolete migration guard.
- For balance: delegation is clean (every command ~5 lines), exit codes are
  consistent, negative-flag suppression is tested, and `test_cli.py` is
  thorough.

### Packaging, tooling, CI

- **H-P1 · High/S — Packaging metadata is empty where it matters.** A built
  wheel's METADATA has no `License-Expression`, no classifiers, no
  `[project.urls]`, no authors; PyPI would show the project as unlicensed
  despite the tracked MIT `LICENSE`. Blocks Issue #5.
- **H-P2 · Med/M** — No CHANGELOG, no git tags across 163 commits, no
  release workflow; CI's `build` job uploads an artifact nothing publishes.
  `--version` correctly reads installed metadata.
- **H-P3 · Low/S** — Stale gitignored `dist/` holds a pre-cyclopts 0.1.0
  wheel (`Requires-Dist: textual==8.2.8` only, old README) with the same
  version number as current code. `rm -rf dist/`.
- **H-P4 · Low/S** — `requires-python >=3.11`; CI tests 3.11 and 3.14 only.
  Record the endpoints-only decision or add 3.12/3.13 on one leg.
- **H-P5 · Low/S** — Pinning is mixed (`textual==8.2.8`, `cyclopts` ranged,
  `typing-extensions` unbounded) and the exact Textual pin — justified by the
  DataTable coupling — is unexplained in `pyproject.toml`; an `==` pin will
  conflict with any other Textual app in the same environment.
- **H-P6 · Low/S** — `.gitignore` is a 223-line template with two project
  lines; `scratch` lacks a trailing `/`; `.claude/` and `.agents/` are not
  ignored though `.claude/worktrees/` will hold checkouts.
- **H-P7 · Low/S** — `# ruff: ignore[module-import-not-at-top-of-file]` in
  `tests/test_check_quality.py:11` is preview-gated syntax (works because
  `preview = true`); stable equivalent is `# noqa: E402`. Add the *why*.
- **H-Q1 · Med/S** — README calls `scripts/check_quality.py` "the full gate"
  but it omits the pre-commit hygiene hooks CI runs, so a change can pass
  locally and fail CI on whitespace; conversely CI never runs
  `check_quality.py`, so its wheel/sdist assertion runs only at pre-push.
  AGENTS.md's two-command gate is the correct statement.
- **H-Q2 · Low/S** — Pre-push skips tests (deliberate, tested, documented in
  the hook name) but the README Contributing section says "a red gate stops
  the push" without the caveat.
- Good: frozen hook SHAs, pre-commit cache, concurrency group with its
  forward-looking comment, `GIT_*` scrubbing, `finally`-guarded worktree
  removal, null-ref check.

### Documentation

- **H-D1 · High/S** — `README.md:321` links
  `docs/adr/0003-prefer-project-local-configuration-and-work-state.md`; the
  file is `0003-prefer-project-local-dashpot-state.md`. It sits in the Work
  Store domain-language entry and ships as the PyPI description. Five more
  broken links in `docs/tasks-md-upstream-backend-audit.md` point at the
  deleted `src/dashpot/sources.py` / `tests/test_sources.py`. Add the link
  checker as a pre-commit local hook.
- **H-D2 · Med/M — Three stale docs.** `proposed-agent-worktree-protocol.md`
  (879 lines) is still `status: proposal` though ADR 0011 is accepted and
  `worktree create`/`check` ship — and the README says it "is under review";
  `cyclopts-cli-migration-research.md` describes a completed migration with
  no ADR recording the CLI framework choice; `tasks-md-upstream-backend-audit.md`
  references deleted modules. Cross-cutting fix: adopt frontmatter
  (`status: living | research | superseded`, `date:`) across `docs/` so
  staleness is self-declaring (this document does so).
- **H-D3 · Med/M** — README is 912 lines / 47 KB and doubles as the PyPI
  description; the 125-line "Design" section is maintenance prose that will
  drift silently. Move Design and Domain language to `docs/` with pointers
  (update AGENTS.md deep links in the same change).
- **H-D4 · Low/S** — ADRs 0001–0012 are consistent; nothing is ever
  `superseded` though 0003 refines 0001 and 0008 narrows 0005; ADR 0002 is 17
  lines against a 52–114 norm.

### Test-suite hygiene (cross-cutting)

- **H-T1 · Med/S — No `[tool.pytest.ini_options]`.** No `filterwarnings =
  error` (free today: the suite emits none, and warnings are the early signal
  for the Textual pin), `asyncio_mode` works by pytest-asyncio's default, no
  declared import mode (`tests/helpers.py` imports only because `prepend`
  puts `tests/` on `sys.path`). ~8 lines; highest value per line in the
  review.
- **H-T2 · Med/M — No `conftest.py`; four rival git-repository builders.**
  Three modules define a function literally named `repository` with three
  signatures; inline `git init` in four more; `.dashpot/config.json` literals
  hard-coded in six files. A `git_repository` fixture and a
  `dashpot_project(root, source=…)` builder.
- **H-T3 · Med/M** — No coverage measurement anywhere, though
  `# pragma: no cover` in the source implies it once was. Add `pytest-cov`
  (a lockfile change is its own task) with a non-gating report on one CI leg;
  resist a threshold.
- Shared-fixture sprawl is the same finding seen from every slice: hook
  records (O-T2), local Issue documents (I-T2), snapshot/run builders (U-T2,
  R-T17), git repos (H-T2). One `tests/factories.py` plus `conftest.py`, and
  lift `wait_until` out of `test_app.py` so AGENTS.md can point at a stable
  location.

## Suggested roadmap

Grouped so that each step is one reviewable change and later steps build on
earlier ones. Items with an Issue-sized scope are marked.

1. **Quick correctness fixes with tests** (one PR each, or a small batch):
   O-C1 hook exit code + test; R-C1 spaced hook path + test; O-C2 detached
   HEAD + test; U-C1 theme repaint + test; U-C3 search/sort + test; U-C4
   spinner; U-C5 selection key; I-C1 Markdown order + test; I-C3 total
   `refresh()`; O-C5, O-C6, R-C2, R-S8.
2. **Hygiene batch**: H-D1 README link + link-checker hook; H-P1 packaging
   metadata; H-T1 pytest config; `rm -rf dist/`; `.gitignore` trim; H-Q1
   README gate wording; H-D2 doc statuses; delete `test_cli_module_no_longer_uses_argparse`.
3. **Shared test infrastructure**: `conftest.py` + `factories.py`
   (git repo, project config, hook record, Issue document, snapshot
   builders); then R-T15 (aliasing test) as the safety net for step 5.
4. **Seams**: R-A1 `Git` adapter; O-A2 `LockedJsonRecordStore`; O-A1
   `scan_hook_stores`; I-A1 `CollectedIssues` + I-A2 shared invariants +
   I-A4 single source factory; U-S4 public `query_*` seam + U-S3
   `SnapshotIndex`.
5. **Model tightening** *(Issue-sized)*: R-A2 freeze the observation values
   and delete the `deepcopy`s (U-C7, U-C8 fall out); I-A3 typed Issue
   Profile.
6. **Splits** *(Issue-sized each)*: O-S1 `agents.py` with O-T1/R-T11 test
   split to match; U-S1 `DashboardScreen` + `IssueTableView` with U-C2, U-C9
   folded in; U-S5 `issue_table.py`; U-T1 `test_app.py` by subject; R-S1
   `observe_observation_targets`; R-S3 one snapshot factory.
7. **Later / when it hurts**: I-C6 / I-C9 GitHub fetch budget and
   `find(hint)`; O-C3 `ps` parsing (needs a macOS check); O-C8 container
   namespace detection; H-P2 release process (with Issue #5); H-D3 README
   restructure.

## Source material

The five per-slice reviews, with quoted snippets, proposed code and full
rationale for every finding above, were produced in this session's scratch
directory and are not tracked:

- `review-observation.md` — agent-observation core (44 findings)
- `review-repository.md` — repository / worktrees / collection (61 findings)
- `review-issues.md` — Issue sources (33 findings)
- `review-tui.md` — Textual UI (~30 findings)
- `review-hygiene.md` — CLI, packaging, CI, docs, tests (22 findings)

Two line references in the observation review were wrong and are corrected
here (`hook.py:22`, `agent_bindings.py:64`); every other cited location that
was spot-checked matched.
