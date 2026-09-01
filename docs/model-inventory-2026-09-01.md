# Structured-value inventory for the Pydantic adoption (2026-09-01)

The classification behind
[ADR 0013](adr/0013-adopt-pydantic-models-by-seam.md), prepared for
[#85](https://github.com/ned2/dashpot/issues/85). Every `@dataclass`,
`dict[str, Any]`-shaped record, manual JSON validator, and serializer in
`src/dashpot` is listed with the seam it sits at and the verdict the ADR
records for its family. Line numbers are as of commit `f72c155`.

Seam vocabulary (from #85): **untrusted input** (subprocess output, hook
payloads, files not owned by Dashpot), **persisted state** (files Dashpot
writes and reads back), **published value** (domain or observation value
handed across module boundaries and into read models), **command result**
(plan/report returned by a management command, including its `--json` form),
**read model** (derived, per-pane view of the store), **UI-only value**
(presentation data that never leaves the interface), and **mutable
implementation state** (locks, caches, accumulators).

## 1. Issue Profile family — Pydantic (first migration)

The profile is specified in four independent places today:
`issue_profile._ISSUE_KEYS` (issue_profile.py:11), the literal dict in
`normalize_github_issue` (github_issues.py:327), the front-matter key set and
literal dict in `local_markdown_issues.py:12,181`, and
`conformance/issue/issue.schema.json` (which nothing executes). One Pydantic
model collapses the first three and becomes the declared authority for the
fourth.

| Value | Where | Today | Seam |
| --- | --- | --- | --- |
| `Issue` | model.py:12 | `TypeAlias = dict[str, Any]`, camelCase keys | published value built from untrusted input |
| `conform_issue` + `_require_*`, `_canonical_string_set`, `_require_optional_timestamp` | issue_profile.py:40-167 | manual validator/canonicalizer; deepcopy on entry, sorted string sets, cross-field state invariants, closed key set | validation boundary |
| `origin` / `location` sub-shapes | issue_profile.py:169,183 | hand-validated `kind`-discriminated unions (`github`/`markdown`) | nested discriminated union |
| `relationships` sub-shape | issue_profile.py:32 | four-key dict, self-reference checks | nested value |
| `semantic_projection` / `semantically_equivalent` | issue_profile.py:105,114 | dict surgery + dict equality | canonical comparison |
| `normalize_github_issue` and its `_required*` helpers | github_issues.py:281,477-528 | gh GraphQL record → profile dict → `conform_issue` | untrusted input parser |
| `parse_local_markdown_issue` | local_markdown_issues.py:133 | JSON front matter → profile dict → `conform_issue` | untrusted input parser |
| `conformance/issue/issue.schema.json` | conformance/issue/ | hand-maintained, executed by nothing; missing the sorted-string-set and self-reference rules | documentation drift risk |

Adjacent but source-shaped, staying beside (not inside) the profile:
`IssueActivity` / `LinkedPullRequest` (model.py:26,33 — mutable today,
deep-copied at issue_sources.py:79,103 and github_issues.py:173) join the
observation family in §3. The lenient parsers `_label_colors` and
`_issue_activity` (github_issues.py:405,441) stay hand-written: leniency is
their contract.

## 2. Persisted records Dashpot owns — Pydantic

Each has a hand-written writer and a hand-written reader that restate the
same camelCase key set, plus a `version` gate with no unknown-field policy in
common.

- **hook record** (Agent Session record, `<sessionId>.json`):
  `build_hook_record` (agents.py:383), `HookRecordStore.write/read/_replace`
  (agents.py:450-593), strict reader `read_hook_record` (agents.py:1145,
  rejects `version != 2`), validator `classify_hook_record` (agents.py:1153)
  producing `HookRecordClassification`. The parsed model is incomplete, so
  `SessionLocation` (agents.py:714) carries the **raw dict alongside it** and
  `validate_session_claim`, `record_to_session`, and
  `locate_observation_target` re-read raw keys ad hoc. Unknown fields are
  silently retained today and `HookRecordStore.prune` (agents.py:513)
  compare-and-deletes on whole-dict equality — the model must round-trip
  unknown fields byte-stably or prune's optimistic-concurrency check changes
  meaning. The primitive validators `require_string` / `optional_string` /
  `validated_optional_issue_value` (agents.py:1348-1358) are the layer the
  model replaces; note `optional_string` silently coerces wrong types to
  `None` at ~15 sites.
- **Work Store record** (`.dashpot/state/work/<key>.json`): the dict literal
  in `WorkStore.start` (work_store.py:65-79) and its mirror `_parse`
  (work_store.py:145). Already writes explicit nulls and already ignores
  unknown fields, but pins `version == 1` exactly, and
  `isinstance(process.get("pid"), int)` accepts booleans. `SessionProcess`
  and `ActiveWork` (work_store.py:23,32, frozen/slots) become the model
  fields; `ActiveWork.run_id` stays a derived property.

## 3. Published observation values — Pydantic, frozen, with #68

`model.py` is the mutable core the deepcopy guards exist for. Frozen Pydantic
models with immutable collections deliver #68's outcome and give the
serialization seam (§5) typed input in one move; #68's aliasing tests land
first as the safety net either way.

| Value | Where | Today |
| --- | --- | --- |
| `Diagnostic`, `LinkedPullRequest`, `IssueActivity` | model.py:15,26,33 | mutable `slots=True`; `IssueActivity` mutated in place by its builder |
| `ObservationTarget`, `Branch`, `ObservationTargetInventory` | model.py:45,58,85 | mutable; `Branch`'s real invariants live in its docstring |
| `AgentRun` | model.py:98 | mutable, 13 fields, bare-`str` timestamps |
| `ProjectSnapshot`, `ProjectObservation`, `WorkspaceSnapshot` | model.py:118,170,184 | mutable; the shapes `--json` and every read model consume |
| `IssueSourceObservation`, `IssueSourceDiagnostic` | issue_sources.py:24,16 | mutable / frozen pair crossing the adapter boundary |
| `_SourceObservation`, `_AgentObservation` | collect.py:235,270 | mutable by design (`elapsed_ms` assigned post hoc) — supply at construction instead |
| `BranchObservation` | repository.py:374 | mutable command result |

Deepcopy pressure these mutabilities cause (deleted only behind aliasing
tests, per #68): ~15 sites in `observation_store.py` (copy-in 101, 114, 152,
185, 191; copy-out 212-296; checkpoint 362-365), `collect.py` 178, 534,
602-610, 629, and the source-boundary copies in `issue_sources.py` 76-103.
`_StoreState` (observation_store.py:58) is a frozen shell over mutable dicts
and follows the family. The frozen-shell-over-mutable-payload wrappers
`HookSessionObservation` (agents.py:666), `IssueContext`
(observation_store.py:45), and `WorkspaceResolution` (workspace.py:31) become
honest once their payloads freeze.

## 4. Persisted configuration — Pydantic, after characterization

Three closed-world parsers with three wordings of the same errors; #77 wants
the settings one opened. Migrate only after the current error text and
forward-compatibility behavior is characterized in tests (issue step 6).

- `ProjectConfig` + `GitHubIssueSourceConfig` / `LocalMarkdownIssueSourceConfig`
  (project_config.py) — `kind`-discriminated union, rejects unknown keys, and
  is also parsed from a Git blob by `_check_base_compatibility`
  (worktrees.py:368), where a parse failure must stay a refusal string.
- `Settings` (settings.py:30) — rejects unknown keys today; per #77 must
  instead ignore them with a Diagnostic. The one config holding a real
  `Path`, resolved against the settings file's directory.
- `load_workspaces` (workspace.py:50) — strictly closed key sets, aborts the
  whole file on first error.

## 5. Command results and the `--json` seam — Pydantic-serialized, contract pinned per #78

`to_jsonable` (model.py:194) drops every `None` dataclass field while the
embedded Issue dicts carry explicit nulls — two null conventions in one
document — and `issue show --json` (cli.py:302) bypasses it entirely.
`camel_case` (model.py:208) is the only alias rule for dataclasses; the Work
Store hand-writes its own; the profile is camelCase natively. Under #78 one
`serialization.py` owns command output, pins key sets and explicit nulls per
command, and `to_jsonable` is deleted last (issue step 9).

- `WorktreePlan`, `RemovalObstacle`, `WorktreeRemovability`
  (worktrees.py:61,86,104, frozen/slots) — the `--json` contracts; the
  post-creation `WorktreePlan` is restated field-by-field
  (worktrees.py:201-213), which a model `copy(update=...)` removes.
  `WorktreeRemovability.removable` is derived (`not obstacles`) and stays a
  computed property.
- `dashpot work start/stop/show` return bare `list[str]` (work.py:228,313,396)
  — no structured form exists yet; the gap is #78's, not this migration's,
  but any future `--json` there goes through the same module.
- `WorkspaceScopeError` (workspace.py:215) carries structured `projects` that
  today flatten to a stderr line — an error-contract question for #77/#73
  territory, noted, not solved here.

## 6. Retained as parsers into typed values — no model for the raw shape

Untrusted text formats whose parsing is already localized; the typed result
(§3) is the model, and modeling the raw shape would only restate Git.

- Worktree porcelain records `dict[str, str]` — `_parse_worktree_records`
  (repository.py:631), validated by `observe_observation_targets`
  (repository.py:133); flag keys carry presence-versus-value semantics
  (`"locked" in record` vs its reason string) that consumers test with `in`
  (worktrees.py:151,420,698).
- Branch ref records — positional NUL-separated `git for-each-ref` lines,
  `_parse_branch_record` (repository.py:449), `_parse_upstream_track`
  (repository.py:595).
- `observe_github_repository_identity` (repository.py:656) — three-check
  manual validation of one `gh api` payload; unknown fields ignored.
- gh GraphQL transport (`_graphql`, `_connection_page`,
  `_classify_github_error`, github_issues.py:235-629) — response-shape
  faults become `IssueSourceRefreshError` diagnostics; only the per-issue
  record crossing into the profile (§1) gets a model.

## 7. Retained dict surgery — foreign files Dashpot must not normalize

Harness hooks documents (`~/.claude/settings.json`, `~/.codex/hooks.json`,
integrate.py:406-509): Dashpot's contract is to preserve everything it did
not write — `_split_dashpot_handlers` (integrate.py:423) keeps unknown
groups and extra keys, and idempotence is a canonical-`json.dumps` equality
check (integrate.py:148). A validating model would normalize foreign state.
Only the handler Dashpot itself writes (integrate.py:154) has a fixed shape,
and `_is_dashpot_handler` (integrate.py:448) stays a matcher, not a
validator.

## 8. Retained frozen, slotted stdlib dataclasses

Trusted, internal, no runtime validation or serialization responsibility —
the deeper and simpler module without Pydantic. Categories, not one-off
exemptions:

- **Validated-outcome values built by their own validator functions**:
  `HookRecordClassification`, `StaleSessionRecord`, `SessionRecordSummary`,
  `ObservedActivity`, `ValidatedSessionIdentity` (agents.py:641-854),
  `AgentSessionIdentity` (work.py:38). The validation lives in
  `classify_hook_record` / `validate_session_claim`; the value is its result,
  never parsed from data. (`_session_identity`'s positional construction at
  work.py:209 deserves keyword arguments regardless.)
- **Scheduling and coordination tokens**: `ObservationKey`,
  `ObservationTicket`, `ObservationOutcome` (collect.py:56-80),
  `StoreChange` (observation_store.py:34 — already fully immutable via
  frozensets).
- **Static integration/config records**: `HarnessIntegration`
  (integrate.py:41), `ObservationOptions` (cli.py:43).
- **Read models**: `IssueListQuery/Row/Result` (issue_list.py:49-67),
  `SessionListRow/Result` (session_list.py:57,73), `BranchListRow/Result`
  (branch_list.py:83,105), `WorktreeListRow/Result` (worktree_list.py:47,66),
  `IssueContext`, `ObservedDiagnostic` (observation_store.py:45,52),
  `_ResolvedAnchor` (workspace.py:37), `ResolvedProject` (model.py:160 —
  already the frozen/tuple exemplar the mutable observation values lack).
- **UI-only values**: `ColumnSpec` (issue_table.py:244 — holds callables, so
  structurally not serializable), `SortTerm`, `IssueTableViewState`
  (issue_table.py:360,369 — its `__post_init__` validation is fine where it
  is), `ListColumn`, `ListRow` (list_pane.py:37,44), `AlertItem`, `Alert`
  (alerts.py:48,58), `DetailItem` (detail_fields.py:16 — gains `slots=True`
  for consistency), `Glyph`, `LegendSection`, the cell `str`/`Text`
  subclasses (issue_table.py:80-153), and Textual message payloads
  (app.py:100,117; list_pane.py:73).
- **Mutable implementation state**: `IssueSource`'s last-good cache
  (issue_sources.py:45), `ObservationCoordinator` / `SnapshotScheduler`
  internals (collect.py:277,665), `ObservedActivityIndex` (agents.py:936),
  `HookRecordStore` / `WorkStore` path holders, `_Preparation`
  (worktrees.py:117), widget state throughout the UI. Never models.

## Cross-cutting facts the migration must not break

- **Unknown-field policies today**: config/settings/workspaces reject;
  Work Store ignores; hook record retains and re-persists; hooks documents
  must preserve. The convention in ADR 0013 assigns one policy per seam
  instead of one global default.
- **Identity is opaque**: `run_id` formats (`work:{harness}:{key}:{started}`
  work_store.py:44; `{harness}-session:{id}` agents.py:659) and the
  unlabeled identity tuples (`ProcessKey`, `SessionIdentityKey`, the
  `(project_id, …)` index keys) are formats, not parsed data; typing them is
  optional polish, not part of this migration.
- **Change detection relies on `__eq__`**: `_changed_keys`
  (observation_store.py:473) diffs by equality, `HookRecordStore.prune` by
  raw-dict equality, `install_integration` by canonical `json.dumps`.
  Pydantic models compare by field values, so behavior is preserved only if
  serialization stays byte-stable.
- **Timestamps stay strings**: RFC-3339 `Z` strings ordered lexically
  (`now_iso` agents.py:104, `utc_now` issue_sources.py:129,
  `_require_optional_timestamp` issue_profile.py:157). Parsing them into
  `datetime` would change ordering semantics and the wire format; the models
  validate the format and keep `str`.
