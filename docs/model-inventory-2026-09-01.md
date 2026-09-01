# Structured-value inventory for the Pydantic adoption (2026-09-01)

The classification behind
[ADR 0013](adr/0013-adopt-pydantic-models-by-seam.md), prepared for
[#85](https://github.com/ned2/dashpot/issues/85). Every `@dataclass`,
`dict[str, Any]`-shaped record, manual JSON validator, and serializer in
`src/dashpot` is listed with the seam it sits at and the verdict the ADR
records for its family; §8 additionally lists the retained values by
category. Line numbers are as of commit `f72c155`.

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

Two facts that shape the migration here. `semantic_projection` works by
`del` on a mutable dict and `semantically_equivalent` by dict equality —
on a frozen model this becomes a `model_dump` projection excluding
`origin` and `location`, decided up front rather than mid-PR. And the
schema stays the authority: generating it from the model would lose
`uniqueItems`, the `if`/`then` state rules, the formats, and most of
`required` (fields with defaults drop out), so agreement is proven by a
shared valid/invalid fixture corpus run through both `jsonschema` and the
model, and no profile field carries a default. The model also removes
`conform_issue`'s per-issue `deepcopy` — the profile path gets cheaper,
not dearer.

Adjacent but source-shaped, staying beside (not inside) the profile:
`IssueActivity` / `LinkedPullRequest` (model.py — frozen with #68, their
deep copies deleted) joined the observation family in §3. The lenient parsers `_label_colors` and
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
  silently retained today, and `HookRecordStore.prune` (agents.py:513)
  compare-and-deletes on whole-dict equality — both sides of that compare
  are already raw `json.loads` dicts, and they stay that way: `model_dump`
  cannot tell an absent declared field from an explicit `null`, so prune
  is defined on the on-disk dict and the raw dict is retained for that one
  comparison. The model replaces the ad-hoc *field* reads, per field:
  today `classify_hook_record` defaults a missing `harness` to codex,
  `optional_string` (agents.py:1354) coerces wrong types to `None` at ~15
  sites, and `process_identity_of` (agents.py:303) degrades a malformed
  `sessionProcess` to liveness-unknown — leniencies that keep a session
  visible-but-degraded rather than gone, which the model preserves as
  per-field fallback with a Diagnostic (only `sessionId`, `version`,
  `state`, `cwd` are record-fatal). `require_string` /
  `validated_optional_issue_value` (agents.py:1348,1358) are the strict
  half the model absorbs directly.
- **`ProcessIdentity`** (agents.py:40) — the nested `sessionProcess`
  sub-record, with its own hand-mirrored pair (`as_record`,
  agents.py:47, and `process_identity_of`, agents.py:303) and a **third
  null convention**: `arguments` is omitted when falsy rather than
  written as `null`. It becomes the hook record's nested model.
  `SessionProcess.as_record` (work_store.py:27) writes `{pid, startedAt}`
  for the same concept the hook record writes as
  `{pid, parentPid, command, startedAt, arguments?}` — two shapes for one
  concept across the two stores, kept distinct (each store's model owns
  its shape) rather than unified, which would change a persisted format.
- **Work Store record** (`.dashpot/state/work/<key>.json`): the dict literal
  in `WorkStore.start` (work_store.py:65-79) and its mirror `_parse`
  (work_store.py:145). Already writes explicit nulls and already ignores
  unknown fields, but pins `version == 1` exactly, and
  `isinstance(process.get("pid"), int)` accepts booleans. The persisted
  record is its own wire model, **not** `ActiveWork`: the record carries
  `version` (no domain meaning) and omits `session_key`, which is the
  filename stem supplied by the reader (work_store.py:151) — conflating
  the two would invent a `sessionKey` key and change the persisted shape.
  `SessionProcess` (work_store.py:23) becomes the record's nested model;
  `ActiveWork` (work_store.py:32) is constructed from the validated
  record and keeps `run_id` as a derived property.

## 3. Published observation values — Pydantic, frozen, with #68

`model.py` is the mutable core the deepcopy guards exist for. Frozen Pydantic
models with immutable collections deliver #68's outcome and give the
serialization seam (§5) typed input in one move; #68's aliasing tests land
first as the safety net either way.

Done with #68. The family froze as planned:

| Value | Where | Now |
| --- | --- | --- |
| `Diagnostic`, `LinkedPullRequest`, `IssueActivity` | model.py | frozen `ObservationModel`; `IssueActivity` built in one construction |
| `ObservationTarget`, `Branch`, `ObservationTargetInventory` | model.py | frozen `ObservationModel` |
| `AgentRun` | model.py | frozen `ObservationModel` (timestamps still bare `str`) |
| `ProjectSnapshot`, `ProjectObservation`, `WorkspaceSnapshot` | model.py | frozen `ObservationModel`; `to_jsonable` keeps the `--json` shape byte-identical (None fields omitted) |
| `IssueSourceObservation`, `IssueSourceDiagnostic` | issue_sources.py | frozen `slots=True` pair — constructed from validated profiles, never parsed, so it stays a dataclass per ADR 0013 |
| `_SourceObservation`, `_AgentObservation` | collect.py | frozen `slots=True`; `elapsed_ms` supplied via `dataclasses.replace` at the timing seam |
| `BranchObservation` | repository.py | mutable command result (unchanged; adapter-internal, §6 family) |
| `IssueBindingResult` | agent_bindings.py | frozen `slots=True`; the pass-through `agent_runs` field was dropped |

The deepcopy guards those mutabilities forced are gone from
`observation_store.py`, `collect.py`, and `issue_sources.py`, deleted behind
the aliasing tests in `tests/test_observation_aliasing.py`; last-good
retention keeps fresh containers (`tuple`, `FrozenDict`), never deep copies.
`_StoreState` keeps one deliberately mutable dict (`issue_runs`, restored in
place) with the reason recorded at the site. The frozen-shell wrappers
`HookSessionObservation` (agents.py), `IssueContext` (observation_store.py),
and `WorkspaceResolution` (workspace.py) are now honest.

Two cautions this family honoured. A `frozen=True` model with a bare `dict`
field is unhashable and its dict is still freely mutable in place — so the
mapping fields (`label_colors`, `issue_activity`, `issue_runs`) take the
shared `FrozenMapping` type from models.py, not `dict`. And Pydantic copies
collections during validation, which makes the
publish-then-mutate-the-caller's-input test pass almost for free — the
aliasing tests therefore also mutate the *published* value's collections,
so a bare `dict` field cannot pass the suite while reopening the hole.

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
  whole file on first error. Its output values `Workspace` and
  `RepositoryAnchor` (model.py:154,149, already frozen/slots with tuples)
  stay dataclasses constructed by the parser: the file gets the model, the
  domain values stay values.

Per the convention, these models declare `str` fields — strict mode
rejects a JSON string for a `Path` field, and today's `.strip()`,
`.expanduser()`, and resolve-against-the-config-file's-directory behavior
(settings.py:56, workspace.py:83, project_config.py's stripping
`_non_empty_string`) is resolution policy that runs after validation and
must be preserved, stripping included.

## 5. Command results and the `--json` seam — Pydantic-serialized, contract pinned per #78

`to_jsonable` (model.py:194) drops every `None` dataclass field while the
embedded Issue dicts carry explicit nulls — two null conventions in one
document (three across the codebase: `ProcessIdentity.as_record` omits
`arguments` when falsy) — and `issue show --json` (cli.py:302) bypasses it
entirely. `to_jsonable` also has no `BaseModel` branch, so the first model
reaching a `--json` surface needs the temporary shim ADR 0013 records.
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
  `AgentSessionIdentity` (work.py:38), and the liveness/ancestry values
  `ProcessPresent` / `ProcessAbsent` / `ProcessUnobservable`,
  `LivenessObservation`, `AgentAncestry` (agents.py:60-224). The validation
  lives in `classify_hook_record` / `validate_session_claim`; the value is
  its result, never parsed from data. (`_session_identity`'s positional
  construction at work.py:209 deserves keyword arguments regardless.)
- **Subprocess and parse results**: `CommandResult` (commands.py:9) — the
  raw subprocess seam §6's parsers consume — and `ParsedIssueSearch` /
  `IssueSearchSort` (issue_search.py:10,16), parsed from the user's own
  search box with diagnostics carried in the value.
- **Harness adapter declarations**: `SessionIdentityClaim`,
  `HarnessAdapter` (harnesses.py:32,47).
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
  `_ResolvedAnchor` (workspace.py:37), `ResolvedProject` (model.py —
  the frozen/tuple exemplar the observation values now match).
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
