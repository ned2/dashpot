---
status: superseded
superseded-by: adr/0034-read-machine-local-settings-as-toml.md
date: 2026-09-12
---

# Migrate machine-local settings to config.toml

The settings migration is implemented by [ADR 0034](adr/0034-read-machine-local-settings-as-toml.md).
The launcher remains separately scoped in #146. The historical investigation
below describes the pre-migration code and proposal. It assesses
replacing Dashpot's machine-local `settings.json` with `config.toml`, including
the proposed launcher setting in [Issue #146](https://github.com/ned2/dashpot/issues/146).
No application behavior, personal configuration, or Issue specification was
changed for this investigation.

## Assessment

The parser change is small and needs no new dependency. The remaining work is
updating the file and key conventions, tests, and documentation. Dashpot already
separates file validation from resolved settings, so the existing Pydantic seam
can remain.

The user confirmed that there are no other current consumers and backwards
compatibility is unnecessary. Recommend a clean TOML-only cutover to
`~/.config/dashpot/config.toml`, respecting `XDG_CONFIG_HOME`, for machine-local
preferences only. Use flat snake_case setting names, with a settings-local
model override, and manually recreate the one existing preference. No legacy
reader, merge policy, compatibility aliases, or automatic conversion is needed.

## Current repository facts

The settings boundary is [settings.py](../src/dashpot/settings.py). Its file
model currently has one known setting, `worktreeRoot`; its resolved value is
`Settings.worktree_root`. An absent file gives defaults. Invalid JSON, unreadable
files, and invalid known values cause a `RuntimeError`. Unknown fields produce
a `settings-unknown-field` Diagnostic while valid known fields remain usable.

The shared model in [models.py](../src/dashpot/models.py) uses strict validation,
camelCase aliases, and `populate_by_name=True`. Consequently, the loader also
accepts the Python spelling `worktree_root`. Unknown fields are retained in the
intermediate file model and reported, not rewritten to disk. `worktreeRoot`
strings are stripped, `~` expands, and relative roots resolve against the
settings file's parent directory.

Only [Worktree preparation](../src/dashpot/worktrees.py) currently calls
`load_settings`; the dashboard does not load this file. The current precedence
is `--worktree-root`, then `DASHPOT_WORKTREE_ROOT`, then the machine setting,
then the sibling default described in [Issue Worktrees](../README.md#issue-worktrees).
Changing the format need not change that precedence or its validation behavior.

The files with similar names have separate contracts:

| File | Owner and role | Migration scope |
| --- | --- | --- |
| `~/.config/dashpot/settings.json` | Machine-local preferences | Replace with `config.toml` |
| `~/.config/dashpot/workspaces.json` | Workspace inventory | Keep JSON |
| `.dashpot/config.json` | Tracked Project configuration and identity | Keep JSON |
| `.dashpot/state/` records and other persisted JSON | Observation or Work Store data | Keep their existing formats |
| Claude Code `settings.json` handled by integration | External harness configuration | Keep the harness's format |

The public `--config` option selects the Workspace inventory file; it does not
select machine-local settings. Naming the new file `config.toml` must not
silently repurpose that option. Relevant boundaries are
[workspace.py](../src/dashpot/workspace.py),
[project_config.py](../src/dashpot/project_config.py),
[cli.py](../src/dashpot/cli.py), and [integrate.py](../src/dashpot/integrate.py).

## Parser, validation, and dependencies

[pyproject.toml](../pyproject.toml) requires Python 3.11 or newer. Python 3.11
already includes `tomllib`: `load()` reads a binary file into a dictionary and
raises `TOMLDecodeError` for invalid TOML. Its output fits the existing
`SettingsFile.model_validate(raw)` seam directly.
[Python 3.11 tomllib documentation](https://docs.python.org/3.11/library/tomllib.html)

Use binary reading with `tomllib.load()`, retain Pydantic validation and error
translation, then resolve paths as today. Normalize read errors, decoding
errors, and parse errors to the existing settings error boundary, including
the selected filename. The TOML parser always produces a dictionary, so the
JSON-only top-level-object check can be removed.
Binary reading avoids newline translation and uses the format's encoding
directly. [PEP 680](https://peps.python.org/pep-0680/)

Python 3.14 still documents TOML 1.0 support; its new structured error attributes
such as `lineno` were added in 3.14, so do not require those attributes on the
3.11 floor. Using the exception's readable message is sufficient initially.
[Python 3.14 tomllib documentation](https://docs.python.org/3.14/library/tomllib.html)

Python 3.15 adds TOML 1.1 support. Recommend documenting TOML 1.0-compatible
configuration and testing examples on Python 3.11. This promises a portable
baseline without implementing a separate parser to reject newer syntax on
newer interpreters. Requiring uniform TOML 1.1 support would be a separate
dependency or Python-floor decision, with no benefit for the two settings
currently under discussion.
[Python 3.15 tomllib documentation](https://docs.python.org/3.15/library/tomllib.html)

Continue validating the parsed Python dictionary, not a JSON reserialization.
Pydantic distinguishes Python validation from JSON validation, including some
strict-mode behavior. Its existing configuration-level strictness can remain;
no `pydantic-settings` adoption or configuration framework is required.
[Pydantic model validation](https://docs.pydantic.dev/latest/concepts/models/),
[Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)

No writer is needed for a manually edited file and a read-only migration.
`tomllib` does not write TOML. If a later explicit command generates new files,
a writer such as Tomli-W is a separate choice; editing existing comments and
formatting calls for a style-preserving library such as TOML Kit. Avoid building
an ad hoc serializer or adding either library now. A future dependency change
also needs the repository's separately scoped lockfile work.
[Python tomllib writer guidance](https://docs.python.org/3.14/library/tomllib.html),
[PEP 680 write API rationale](https://peps.python.org/pep-0680/#including-an-api-for-writing-toml)

## Proposed file shape and syntax

The following is proposed syntax, not supported by the current application:

```toml
# Machine-local Worktree creation preference.
worktree_root = '~/projects/.worktrees'

# Optional; omit to use automatic tmux behavior once Issue #146 is implemented.
worktree_open_command = [
  '/home/example/bin/open-worktree',
  '{path}',
]
```

TOML supports comments, multiline arrays, and literal single-quoted strings;
camelCase and snake_case are both legal keys. It has no null value. Duplicate
definitions of the same TOML key are invalid. A relative path is still just a
string: Dashpot, rather than the parser, decides how to resolve it. Literal
strings preserve backslashes; double-quoted strings interpret escapes, so
document quoting for paths and command arguments.
[TOML 1.0 specification](https://toml.io/en/v1.0.0)

An existing JSON `"worktreeRoot": null` becomes an omitted key, not
`worktree_root = null`, `"null"`, or an empty string. Apply the same rule to
Issue #146's optional launcher. An empty or comment-only TOML file intentionally
selects all defaults and must not re-enable settings from a legacy file.

Recommend snake_case names `worktree_root` and `worktree_open_command` in
TOML. This matches Python field names and makes the new human-edited format's
contract explicit. Keeping camelCase is technically valid, but avoiding a
compatibility break is no longer a reason to retain it. The naming recommendation
still needs acceptance; the user requested the filename and removed the need
for backwards compatibility, rather than prescribing key spelling.

The existing shared model accepts either spelling. A local in-memory probe
confirmed that supplying both makes camelCase win while snake_case is retained
as an unknown extra. That ambiguous alias behavior need not carry into the new
format. A second probe confirmed that declaring `alias_generator=None` on
`SettingsFile` itself keeps snake_case fields working without active camelCase
aliases. Old camelCase keys then receive the existing unknown-field warning
rather than silently taking effect. Keep the shared model's alias contract and
public JSON result fields such as `worktreeRoot` and `worktreeRootSource`
unchanged.

A new `[worktree]` table could eventually group preferences, but adds no useful
structure for two fields. Keep the schema flat until real grouping needs emerge.

## Clean cutover

Read only `config.toml`. An absent file gives defaults; an empty or comment-only
file intentionally selects all defaults. A malformed or unreadable file produces
a settings error. Remove the JSON parser from the settings boundary and update
`default_settings_path()` and its documentation. An explicit `load_settings(path)`
reads that path as TOML without discovering siblings or guessing formats from
contents. Preserve its existing absent-file behavior.

The person can recreate their current setting as `worktree_root = '...'` in the
new file and then remove the old file when convenient. Simply renaming JSON does
not convert its syntax. No private configuration was read or written for this
research, and Dashpot should not automatically rewrite or delete it during
observation. `settings.json` is no longer an input after cutover; an existing old
file alone therefore leaves the new application at defaults. Document that
one-time setup requirement clearly, especially because the Worktree Root default
can select a different destination.

No deprecation window, second parser, legacy fallback, converter, or new
configuration management command is necessary. This also removes conflict and
merge behavior from the design rather than creating policies with no consumers.

## Interaction with Issue #146

The current [Issue #146 specification](https://github.com/ned2/dashpot/issues/146)
names `settings.json` and shows JSON examples. Before implementing the launcher,
update it to name `config.toml`, use TOML examples with `worktree_open_command`,
and describe omission rather than null for defaults. Update every field-specific
diagnostic and acceptance criterion consistently if snake_case is accepted. The
launcher field's argument-list validation, custom command precedence, and literal
`{path}` replacement do not need a format-driven redesign.

Preserve the important difference between missing settings and failed settings.
The proposed dashboard behavior shows a Diagnostic and disables Open Worktree
when loading fails; observation and Copy path remain usable. An invalid custom
command must never be treated as absence and launch tmux instead. Unknown-field
warnings alone must not disable a valid launcher.

Current Worktree management raises on settings load failure. Preserve that
behavior while the dashboard handles the error at its own boundary. Do not
silently turn all loader errors into default `Settings`, because that could
change Worktree creation destinations and violate the launcher's failure
contract. With syntactically invalid TOML, field recovery is unavailable; the
dashboard's ability to continue does not imply that the file was partly loaded.

The file-format migration can land first, independently of the larger launcher
implementation. Dashboard loading, startup error presentation, and restart-to-
reload behavior belong to Issue #146; they are not existing capabilities to
preserve. A configuration editor, get/set commands, live reload, and a keymap
are unnecessary for either change.

## Implementation and verification inventory

| Area | Required follow-up when implementing |
| --- | --- |
| [settings.py](../src/dashpot/settings.py) | Filename, TOML parser, normalized errors, diagnostics, settings-local alias policy |
| [test_settings.py](../tests/test_settings.py) | TOML fixtures and format behavior |
| [test_worktrees.py](../tests/test_worktrees.py) | Settings diagnostic source fixture and unchanged root precedence |
| [cli.py](../src/dashpot/cli.py) | Keep Workspace `--config` meaning; adjust help only if setting names change |
| [README](../README.md#issue-worktrees), [installation guide](installation.md), [domain language](domain-language.md#observation) | Canonical path, setting names, example, file responsibilities, one-time recreation guidance |
| [ADR 0011](adr/0011-prepare-issue-worktrees-by-convention.md) | Record a new accepted migration decision and amend the filename convention when implemented |
| [Issue #146](https://github.com/ned2/dashpot/issues/146) | Update proposed settings syntax and missing/error semantics before implementation |

Retain tests for absent settings, absolute/relative roots, whitespace policy,
`~`, XDG resolution, strict known-field validation, unknown-field warnings, and
unchanged Worktree Root precedence. Add behavioral coverage for empty/commented
TOML, Unicode and quoted paths, malformed TOML, invalid UTF-8, duplicate keys,
snake_case fields, old camelCase names treated as unknown, wrong types including
TOML dates/tables, and errors naming the actual source file. Parser error assertions should check useful
context rather than entire interpreter-specific wording.

Verify that loading does not change files and ignores the old JSON file even
when it exists. Validate examples with the Python 3.11 floor as well as the
normal supported-version CI matrix. These are proposed implementation tests;
no runtime configuration migration was performed for this research. The parent
investigation ran small in-memory parser/model probes: null and duplicate keys
raise `TOMLDecodeError`; an unquoted date supplied as a root fails Pydantic
validation; the unimplemented launcher setting is currently an unknown extra.
The implementation still needs the repository's normal quality gates.

## Decisions and boundaries

The user has settled compatibility: perform a clean cutover with no backwards
compatibility requirement. Remaining design choices are the public spelling
(recommended: snake_case) and confirmation that machine-local settings are the
intended scope. Migrating tracked Project configuration would involve
initialization, Git revision reads, conformance fixtures, and published contracts,
substantially broadening this work.

Preserve existing root resolution and error timing: the current Worktree command
loads settings before choosing CLI/environment overrides, so a malformed file
already fails even when an override would win. Likewise, do not bundle changes
to relative `XDG_CONFIG_HOME` handling with a format migration. No new setting
precedence, path-expansion rules, configuration framework, or serialization
contract is required.

The technical direction is ready for a focused implementation Issue. This
research does not accept an ADR or modify #146.
