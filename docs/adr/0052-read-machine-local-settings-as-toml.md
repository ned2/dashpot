---
status: accepted
date: 2026-09-12
---

# Read machine-local settings as TOML

Machine-local settings need comments and readable command arrays for the
planned Worktree launcher. Dashpot has one current consumer, so supporting two
file formats or active aliases would add ambiguity without a compatibility need.

Read only `$XDG_CONFIG_HOME/dashpot/config.toml`, falling back to
`~/.config/dashpot/config.toml`, with flat snake_case keys. `worktree_root` is the
current setting; the launcher field belongs to
[#146](https://github.com/ned2/dashpot/issues/146). Use standard-library `tomllib`
and the existing shared Pydantic base, disabling alias generation only on the
settings file model. Unknown fields retain their existing warning behavior.

An absent, empty, or comment-only file selects defaults. Invalid syntax, encoding,
read failures, and invalid known values report a settings error naming the file.
Preserve Worktree Root precedence, path resolution, and loading before override
selection. Explicit loader paths are TOML regardless of filename. Reading never
rewrites settings or discovers the old JSON file.

## Considered options

- A legacy JSON reader or automatic converter would create an unnecessary
  second input contract. Recreate the single user's preference manually.
- Keeping camelCase aliases would retain competing spellings. Settings use
  snake_case while existing published JSON retains its own aliases.
- A TOML writer or configuration framework has no role in a read-only boundary.
  No dependency or Python-version change is needed.

## Consequences

- This amends the settings filename and key in
  [ADR 0011](0011-prepare-issue-worktrees-by-convention.md); all its other
  Worktree preparation conventions remain in force.
- The old `settings.json` is ignored. Leaving only that file selects defaults;
  the [settings guide](../installation.md#machine-local-settings) documents
  recreating the preference rather than renaming JSON contents.
- Workspace `--config`, tracked Project configuration, Work Store records,
  public JSON, and external harness configuration retain their contracts.
- The [migration investigation](../toml-settings-migration-research.md) is
  superseded for the settings migration. Dashboard loading and launcher
  behavior are defined separately in
  [ADR 0035](0035-open-worktrees-on-explicit-key-press.md).
