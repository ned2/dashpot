---
status: accepted
date: 2026-09-01
---

# Adopt Pydantic models at validating seams, keep dataclasses for trusted values

Dashpot represents structured values five different ways: mutable and frozen
stdlib dataclasses, the Issue Profile as `dict[str, Any]` plus a hand-written
validator, raw dictionaries at JSON and subprocess seams, hand-mirrored
writer/reader pairs for its persisted records, and a bespoke `to_jsonable`
serializer. [#85](https://github.com/ned2/dashpot/issues/85) asked for one
convention; the full survey is the
[structured-value inventory](../model-inventory-2026-09-01.md), and this ADR
records the convention and the classification so the migration is a series of
mechanical steps rather than eighty per-class decisions.

The deciding question for every value is its seam, not its shape: **a value
earns a Pydantic model when data crosses a trust or persistence boundary
through it — untrusted input, persisted state, or a published wire shape. A
value that is constructed, not parsed, stays a frozen, slotted stdlib
dataclass.** A model is earned by a seam, and a value that acquires one
later is promoted then; migration is never a mechanical decorator
replacement.

## The Dashpot model convention

All Pydantic models derive from one shared base (or an equivalent shared
`model_config`) in a new `src/dashpot/models.py`, with per-seam variants:

- **Strict by default, with two stated exceptions.** `strict=True` and
  `validate_default=True` (strict mode alone leaves defaults unvalidated):
  no silent coercion of strings, numbers, or booleans. The bool-is-int
  holes in today's hand validators (`work_store._parse` accepting
  `pid=True`) close for free; where a hand validator deliberately excludes
  bools, the model keeps that behavior. The exceptions:
  - *Sequences accept `list` input.* Strict Python-mode validation rejects
    a `list` for a `tuple[...]` field, and every producer — both Issue
    adapters, every snapshot builder, every test fixture — builds Python
    lists. Published sequence fields are declared `tuple[...]` with
    field-level lax sequence validation (a shared annotated type in
    `models.py`), so a `list` converts and anything else still fails.
  - *Hook-record leniency is per field, not per record.* See the
    unknown-fields policy below.
- **Frozen for published values.** Domain, observation, and command-result
  models are `frozen=True` with immutable collections: `tuple[...]` for
  sequences, and for mappings a shared frozen-mapping type in `models.py`
  (a `Mapping` field validated into an immutable view), because a bare
  `dict` field on a frozen model is still freely mutable in place and
  makes the model unhashable — exactly the fields (`label_colors`,
  `issue_activity`, `issue_runs`) the checkpoint deep-copies today.
  Mutable implementation state never becomes a model.
- **Unknown fields are a per-seam policy, not a global default.**
  - *Forbid* (`extra="forbid"`) at validation seams whose contract is a
    closed key set: the Issue Profile and Project configuration.
  - *Ignore with a Diagnostic* where forward compatibility is required:
    machine-local settings ([#77](https://github.com/ned2/dashpot/issues/77))
    and the Workspace inventory.
  - *Retain* (`extra="allow"`) where Dashpot re-persists records a newer
    Dashpot may have written: the hook record and the Work Store record
    (which already ignores unknown fields on read). Two boundaries on the
    hook-record model. First, `prune`'s compare-and-delete stays defined on
    the record's **on-disk dict**, never on the model: `model_dump` cannot
    distinguish an absent declared field from an explicit `null`, so a
    model-level comparison would let a concurrent hook write compare equal
    and delete a live record. The raw dict is retained for that one
    comparison even after the model retires `SessionLocation.raw`'s field
    reads. Second, the record degrades **per field**: only `sessionId`,
    `version`, `state`, and `cwd` are record-fatal; a malformed optional
    field (a wrong-typed `branch`, an unparsable `sessionProcess`) falls
    back to `None` with a `Diagnostic`, because today's leniencies —
    `harness` defaulting to codex, `optional_string` coercing to `None`,
    a bad process identity degrading to liveness-unknown — are what keep a
    session visible-but-degraded in the pane rather than silently gone,
    and a strict whole-record rejection would turn degraded observation
    into lost observation. `build_hook_record`'s write path keeps copying
    unrecognized payload fields through unvalidated for the same reason: a
    surprising harness payload must not make the hook itself fail.
  - *No model at all* for foreign files Dashpot edits in place (harness
    hooks documents): preserving structure Dashpot does not understand is
    the contract, so the existing targeted dict surgery stays.
- **Python names, deliberate aliases.** Fields are snake_case with explicit
  camelCase aliases at wire seams (`alias_generator` producing today's
  `camel_case` output, `populate_by_name=True`). The Issue Profile keeps its
  native camelCase keys as aliases; the Work Store and hook record keep the
  exact key sets they persist today.
- **Timestamps stay `str`.** RFC-3339 `Z` strings order lexically and are
  the wire format; models validate the format and do not parse into
  `datetime`. Today's `_require_optional_timestamp` becomes a shared
  annotated type of pattern **plus** an `AfterValidator` that round-trips
  through `fromisoformat` (the regex alone accepts month 13) and raises
  today's message, "must be an RFC 3339 UTC timestamp ending in Z" —
  Pydantic's raw should-match-pattern text is not the stable, actionable
  message this convention promises.
- **Config models parse strings; a resolution step owns paths.**
  Configuration models declare `str` fields — strict mode rejects a JSON
  string for a `Path` field, and today's parsers strip whitespace and
  resolve `~` and relative paths against the config file's own directory,
  policy that belongs beside `resolve_worktree_root`, not inside
  validation. Whitespace-stripping is existing behavior to preserve
  explicitly.
- **Errors are translated at public seams.** A Pydantic `ValidationError`
  never reaches a user or a caller's `except` clause: adapters wrap it into
  the existing domain errors (`IssueProfileError`,
  `LocalMarkdownIssueError`, `GitHubIssueNormalizationError`, the
  `RuntimeError`-based CLI contract) or a `Diagnostic`, with stable,
  actionable messages. Migrations characterize the current error text first
  and preserve the actionable content, coordinating with
  [#73](https://github.com/ned2/dashpot/issues/73)'s error-contract work.
- **Serialization is owned, not defaulted.** Pydantic's `model_dump`
  defaults never define the headless JSON contract. One `serialization.py`
  module owns command output per
  [#78](https://github.com/ned2/dashpot/issues/78): it pins each command's
  key set, aliases, nullability (explicit `null`, not omission), and
  collection shapes, with tests per command. `to_jsonable` and its
  omit-`None` behavior are deleted only after every command output is
  covered (the last step, not a side effect) — but it cannot go untouched
  until then: it has no `BaseModel` branch, so the first model reaching a
  `--json` surface would hit the passthrough and make `json.dumps` raise.
  The step that first puts a model on a `--json` path adds an explicitly
  temporary `BaseModel` branch (dump by alias, preserving today's shapes)
  that step 8 deletes with the rest.
- **The checked-in schema is the authority; agreement is proven by
  fixtures.** `conformance/issue/issue.schema.json` stays hand-maintained
  and authoritative. Generating it from the model was considered and
  rejected: `model_json_schema` preserves the discriminated unions but
  loses `uniqueItems`, the `if`/`then` open-closed state rules, the
  `date-time`/`uri` formats, and — decisively — shrinks `required` to the
  fields without defaults, silently defeating #72's schema-agreement test.
  Instead, one shared corpus of valid and invalid fixtures runs through
  both the schema (via `jsonschema`, a dev dependency) and the model, so
  divergence — including today's drift, the sorted-string-set and
  self-reference rules missing from the schema — becomes a test failure.
  Corollary: **no Issue Profile field carries a default**, so an absent
  key is an error in both authorities rather than a silent fill-in.

## Classification

Recorded in full, value by value, in the
[inventory](../model-inventory-2026-09-01.md); the families:

**Pydantic:** the Issue Profile with its nested relationships, origin, and
location discriminated unions (§1); the persisted hook record and Work Store
record (§2); the published observation values — `Diagnostic` through
`WorkspaceSnapshot` — as frozen models (§3); Project configuration,
machine-local settings, and the Workspace inventory (§4); command
plans/reports at the `--json` seam (§5).

**Retained without models:** subprocess text formats parsed directly into
typed values — Git porcelain and for-each-ref records, the gh transport
(§6); foreign harness hooks documents (§7); and the frozen, slotted
dataclass categories (§8): validated-outcome values built by their own
validator functions, scheduling tokens, static integration records, read
models, UI-only values (including `ColumnSpec`, which holds callables and is
structurally unserializable), and mutable implementation state.

## Migration order

A PR series, observable behavior preserved at each step, per #85 — with
one recorded exception class: leniencies the convention deliberately
closes (bools accepted as ints, wrong-typed values silently coerced) are
listed in the migrating PR and covered by tests.

1. This ADR and the inventory.
2. The dependencies and lockfile update, alone: Pydantic v2 at runtime and
   `jsonschema` in the dev group (the fixture corpus in step 3 needs it,
   and a lockfile change is its own task, so it cannot ride along later).
3. The Issue Profile family, resolving
   [#72](https://github.com/ned2/dashpot/issues/72), in two changes:
   - *3a* — the model with its nested relationships, origin, and location
     unions, both adapters validating through it, `conform_issue` a thin
     adapter still returning the profile dict, and the shared fixture
     corpus proving schema agreement. No consumer changes; the wire is
     untouched.
   - *3b* — consumers move from the dict to the model: `Issue =
     dict[str, Any]` retired, the dead `IssueListRow.issue: Issue | None`
     optionality removed, fixtures rebuilt from the conformance fixture
     with overrides, `semantic_projection` /`semantically_equivalent`
     reworked as a model projection (`model_dump` excluding `origin` and
     `location`) rather than dict surgery, and the temporary `BaseModel`
     branch added to `to_jsonable` so both `--json` paths keep today's
     output. #72's misspelt-key-is-a-type-error outcome lands here, not
     in 3a.
4. The Work Store record. The persisted record is its own wire model, not
   `ActiveWork`: the record carries `version` (which `ActiveWork` does
   not) and omits `session_key` (the filename stem, supplied by the
   reader) — conflating them would invent a `sessionKey` key and change
   the persisted shape. `ActiveWork` is constructed from the validated
   record.
5. The hook record, retiring the ad-hoc raw-dict field reads beside
   `HookRecordClassification` (the `SessionLocation.raw` pattern), with
   the nested `sessionProcess` model, per-field degradation as the
   convention states, and `prune` kept on the on-disk dict. As landed,
   the nested model is `SessionProcessRecord`, the wire form beside
   `ProcessIdentity` rather than `ProcessIdentity` itself: the identity
   is a value the `ps` probe constructs (a retained category), and one
   record model converting to and from it mirrors the Work Store's
   record-versus-`ActiveWork` split. Liveness is probed by process key,
   not by raw dict, so `process_key_of` / `process_identity_of` are gone.
6. Configuration, settings, and the Workspace inventory, after their error
   and forward-compatibility behavior is characterized; delivers #77.
7. The observation values, frozen, in coordination with
   [#68](https://github.com/ned2/dashpot/issues/68): aliasing tests land
   first, and no `deepcopy` guard is deleted until the tests prove
   isolation **in both directions** — mutating the caller's input after
   publication, and mutating the published value's own collections.
   Validation-time copying makes the first direction pass almost for
   free; the second is what the frozen-mapping type exists for, and is
   where a bare `dict` field would silently reopen the aliasing hole.
8. Command plans/reports and `serialization.py` per #78; `to_jsonable`,
   including the temporary `BaseModel` branch, is deleted last.

## Considered options

- **One global model policy (everything strict-forbid-frozen):** rejected;
  the seams genuinely differ. Forbidding unknown fields in the settings file
  re-creates the #77 defect, freezing the hooks documents would normalize
  foreign state, and forbidding extras in the hook record would break
  re-persisting records written by a newer Dashpot.
- **Migrate every dataclass to Pydantic** (for one idiom and uniform
  tooling): rejected, for four concrete reasons.
  - *Per-keystroke construction cost.* A model validates every
    construction, and the retained read models are rebuilt wholesale on
    every search keystroke (`query_issue_list` and `build_rows`), where
    validating already-validated values buys nothing. This ground is
    deliberately narrow: it does **not** claim the migration slows the
    refresh path — step 7 puts validating models on that path and the
    Issue path gets faster (the model replaces `conform_issue`'s
    per-issue `deepcopy` plus hand validation) — it claims re-validation
    of trusted, derived values on interactive paths is waste.
    `model_construct()` avoids the cost only by giving up the guarantee.
  - *Structural carve-outs exist anyway.* `ColumnSpec` holds callables, the
    table cells subclass `str` and Rich `Text`, message payloads carry
    Textual objects — values Pydantic can neither validate nor serialize.
    Uniformity is unreachable; the only choice is where the line is drawn,
    and a seam is a principle where `arbitrary_types_allowed` is an accident.
  - *No parsing failure path.* A trusted value never fails on well-typed
    input — a shape error is a bug that Ruff `ANN` and ty catch at check
    time. (A retained value may still assert its own invariants and
    raise, as `IssueTableViewState.__post_init__` does; the claim is
    about parsing, not about invariants.) Making every construction a
    potential `ValidationError` threads a new runtime failure path
    through code bound by the one-line `dashpot:` error contract (#73).
  - *The split itself carries information.* `BaseModel` on a value signals
    that a trust or persistence seam is in play and its aliases and
    unknown-field policy matter; `@dataclass(frozen=True, slots=True)`
    signals plain trusted data. Uniform models erase that signal and put
    Pydantic's whole API surface in scope everywhere.

  The classification is therefore per-seam, not permanent: a retained value
  that later acquires a seam (say a structured `dashpot work --json`) is
  promoted to a model in a small mechanical change, not a re-litigation of
  this ADR. The accepted uniformity cost is two copy idioms,
  `dataclasses.replace` beside `model_copy`.
- **`TypedDict` for the Issue Profile** (the lighter option in #72):
  rejected here; it types keys but keeps `dict` mutability, does no runtime
  validation, and leaves `conform_issue`'s hand-rolled checks in place —
  the duplication #85 exists to remove. The frozen model direction was
  chosen with the #68 freeze in mind.
- **Freeze the dataclasses first (#68) and adopt Pydantic later:** rejected
  as doing the same migration twice; #68's aliasing tests are kept as the
  prerequisite, and the freeze happens by becoming frozen models (step 7).
- **Adopt `pydantic-settings` for configuration:** deferred; the three
  config parsers migrate to plain models first, and env-var layering
  (`DASHPOT_WORKTREE_ROOT`) stays in `resolve_worktree_root`, whose
  precedence logic is policy, not parsing.

## Consequences

- `src/dashpot/models.py` (shared base, the lax-sequence and
  frozen-mapping types, the timestamp type) and, at step 8,
  `src/dashpot/serialization.py` exist; Pydantic v2 joins the runtime
  dependencies and `jsonschema` the dev group (step 2, its own change).
- The Issue path sheds `conform_issue`'s per-issue `deepcopy`; the
  checkpoint's mapping deepcopies become deletable once the frozen-mapping
  type carries them.
- The Issue Profile becomes one typed, frozen, strictly validated model with
  one schema authority; `_ISSUE_KEYS`, the adapters' literal dicts, and the
  schema file stop being four independent statements of the same contract.
- Extra fields, coercion, aliases, and nested mutability get direct tests
  per family; validation failures keep the existing error and Diagnostic
  contracts.
- The deepcopy guards in `collect.py`, `observation_store.py`, and
  `issue_sources.py` become deletable behind aliasing tests (#68), and
  `checkpoint()` becomes cheap or unnecessary.
- `AGENTS.md`'s "domain values are frozen, slotted dataclasses" convention
  is superseded for the migrated families: the final wording (Pydantic at
  validating seams, dataclasses for trusted internal values) lands with the
  first migrating PR (step 3), not at the end.
- The [documentation map](../../README.md#documentation-map) gains the
  inventory as an audit document; the domain language is unchanged — no new
  shared term is introduced, and existing terms (Issue Profile, hook record,
  Work Store, Agent Run) keep their meanings.
