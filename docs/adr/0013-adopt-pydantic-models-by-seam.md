---
status: accepted
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
dataclass.** Migration is never a mechanical decorator replacement.

## The Dashpot model convention

All Pydantic models derive from one shared base (or an equivalent shared
`model_config`) in a new `src/dashpot/models.py`, with per-seam variants:

- **Strict by default.** `strict=True`: no silent coercion of strings,
  numbers, or booleans. The bool-is-int holes in today's hand validators
  (`work_store._parse` accepting `pid=True`) close for free; where a hand
  validator deliberately excludes bools, the model keeps that behavior.
- **Frozen for published values.** Domain, observation, and command-result
  models are `frozen=True`, and their collections are immutable at the type
  level: `tuple[...]` for sequences, and mappings published only where
  aliasing is proven harmless (see the #68 coordination below). Mutable
  implementation state never becomes a model.
- **Unknown fields are a per-seam policy, not a global default.**
  - *Forbid* (`extra="forbid"`) at validation seams whose contract is a
    closed key set: the Issue Profile and Project configuration.
  - *Ignore with a Diagnostic* where forward compatibility is required:
    machine-local settings ([#77](https://github.com/ned2/dashpot/issues/77))
    and the Workspace inventory.
  - *Retain and round-trip* (`extra="allow"` plus stable re-serialization)
    where Dashpot re-persists records a newer Dashpot may have written: the
    hook record, whose `prune` compare-and-delete depends on reading back
    exactly what was observed, and the Work Store record, which already
    ignores unknown fields on read.
  - *No model at all* for foreign files Dashpot edits in place (harness
    hooks documents): preserving structure Dashpot does not understand is
    the contract, so the existing targeted dict surgery stays.
- **Python names, deliberate aliases.** Fields are snake_case with explicit
  camelCase aliases at wire seams (`alias_generator` producing today's
  `camel_case` output, `populate_by_name=True`). The Issue Profile keeps its
  native camelCase keys as aliases; the Work Store and hook record keep the
  exact key sets they persist today.
- **Timestamps stay `str`.** RFC-3339 `Z` strings order lexically and are
  the wire format; models validate the format (today's
  `_require_optional_timestamp` becomes a shared annotated type) and do not
  parse into `datetime`.
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
  covered (the last step, not a side effect).
- **Schema authority is declared.** `conformance/issue/issue.schema.json`
  becomes generated from the Issue Profile model, or a conformance test
  asserts exact semantic agreement; either way one authority is declared and
  drift (today: the sorted-string-set and self-reference rules missing from
  the schema) becomes a test failure.

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

A PR series, observable behavior preserved at each step, per #85:

1. This ADR and the inventory.
2. The Pydantic dependency and lockfile update, alone.
3. The Issue Profile family — the representative model, resolving
   [#72](https://github.com/ned2/dashpot/issues/72) and the schema-authority
   decision. `conform_issue` becomes a thin adapter over the model so both
   adapters keep one validation interface.
4. The Work Store record, replacing the hand-mirrored writer/reader pair.
5. The hook record, retiring the raw-dict re-reads beside
   `HookRecordClassification` (the `SessionLocation.raw` pattern) behind
   round-trip tests that pin `prune`'s equality semantics.
6. Configuration, settings, and the Workspace inventory, after their error
   and forward-compatibility behavior is characterized; delivers #77.
7. The observation values, frozen, in coordination with
   [#68](https://github.com/ned2/dashpot/issues/68): aliasing tests land
   first, and no `deepcopy` guard is deleted until a test proves the
   published value is isolated from caller mutation.
8. Command plans/reports and `serialization.py` per #78; `to_jsonable` is
   deleted last.

## Considered options

- **One global model policy (everything strict-forbid-frozen):** rejected;
  the seams genuinely differ. Forbidding unknown fields in the settings file
  re-creates the #77 defect, freezing the hooks documents would normalize
  foreign state, and forbidding extras in the hook record would break
  re-persisting records written by a newer Dashpot.
- **Migrate every dataclass to Pydantic:** rejected; for trusted internal
  values validation is dead weight at import and construction time, and a
  frozen, slotted dataclass is the deeper module — nothing to configure,
  nothing to serialize. `ColumnSpec` cannot migrate at all (callable
  fields).
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

- `src/dashpot/models.py` (shared base and annotated types) and, at step 8,
  `src/dashpot/serialization.py` exist; Pydantic v2 joins the runtime
  dependencies (step 2, its own change).
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
