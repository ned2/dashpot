# Dashpot

_Useful damping for agent-driven projects._

Dashpot is a passive terminal view of declared work, repository state, and active
coding-agent runs. It makes the small but important project-management pause
visible before another prompt or agent adds more motion.

Like its [mechanical namesake](https://en.wikipedia.org/wiki/Dashpot), Dashpot is
intended to reduce oscillation without stopping progress. It observes; it does
not assign or edit Issues, mutate repositories, or control agent sessions.

> [!NOTE]
> Dashpot is an early implementation extracted from a successful research spike.
> Its interfaces and packaging are not yet stable.

## What it observes

- Projects with either GitHub Issues or Dashpot's Local Issue Markdown
- git branch, worktree, HEAD, and dirty state
- Codex and Claude Code lifecycle records published through opt-in hooks
- source freshness, failures, and last-good state
- durable Agent Run bindings through opaque Issue Identity

Each source remains independent in the read model. A failed Issue refresh, for
example, does not erase the last good Issue collection or hide repository facts.

## Development setup

Dashpot requires Python 3.11 or newer and uses
[uv](https://docs.astral.sh/uv/) for its locked development environment.

```bash
uv sync --group dev
uv run pre-commit install
uv run pytest -q
```

### Quality gates

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) is the shared quality
gate. `uv run pre-commit install` enables two sets of hooks for the checkout:

- **On commit**: repository hygiene checks (whitespace, line endings, YAML,
  TOML and JSON syntax, merge-conflict markers, stray debug statements, private
  keys, large files), then [Ruff](https://docs.astral.sh/ruff/) lint with safe
  fixes, then `ruff-format`, then [ty](https://docs.astral.sh/ty/) static type
  checking. Ruff's rule selection and ty's rule levels live in
  [`pyproject.toml`](pyproject.toml).
- **On push**: the full local gate in
  [`scripts/check_quality.py`](scripts/check_quality.py), which verifies the
  lockfile, Ruff lint and formatting, ty, the test suite, and the distribution
  build for the exact revision being pushed, in a temporary detached worktree.

Run the commit hooks across every tracked file:

```bash
uv run pre-commit run --all-files
```

Run the full gate directly against the working tree:

```bash
uv run python scripts/check_quality.py
```

Ruff fixes and formatting are idempotent: a second `--all-files` run after the
first has fixed something is clean. Hook revisions are pinned to frozen commit
SHAs; refresh them with

```bash
uv run pre-commit autoupdate --freeze
```

and bump the matching `ruff` and `ty` versions in `uv.lock` (`uv lock
--upgrade-package ruff --upgrade-package ty`) so the hooks and `uv run` agree.
First-time hook setup downloads the pinned hook environments, so it needs
network access.

### Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pull requests
targeting `main`, pushes to `main`, and manual dispatch. It runs the all-files
pre-commit quality gate once on Ubuntu, tests the locked environment on Ubuntu
and macOS under Python 3.11 and 3.14, and builds the package once per run. No
credentials are provided and no live GitHub collection happens in CI; the test
suite exercises Issue collection against fakes.

Every CI verification step has an exact local equivalent:

```bash
# Verify uv.lock matches pyproject.toml
uv lock --check

# Install the locked development environment
uv sync --locked --group dev

# Run the all-files quality gate
uv run pre-commit run --all-files

# Run the full test suite
uv run pytest -q

# Build the wheel and source distribution into dist/
uv build
```

Open the TUI for one or more projects:

```bash
cd /path/to/configured/project
uv run dashpot

uv run dashpot --workspace personal=/path/to/project
uv run dashpot --workspace personal=/path/first-clone \
  --workspace personal=/path/second-clone
```

Without arguments, Dashpot observes the current directory when it contains
`.dashpot/config.json`. Outside a configured Project it loads explicit Repository
Anchors from Dashpot's `~/.config/dashpot/workspaces.json`. Explicit
`--workspace` arguments each name one anchor and take precedence; repeat the
same Workspace name to include independent clones. Use `--config` to select a
different Workspace inventory. Use `r` to refresh the selected Project, `R` to
refresh every Project, `o` to flip the Work list between open, closed, and all
Issues, the arrow keys to move, `Enter` to read the selected Issue full-screen
(`Escape` returns to the table), and `q` to quit. The default
15-second polling period refreshes the selected Project and can be changed with
`--refresh-seconds`; zero disables polling.

A Workspace inventory stores named groupings and anchor paths, never discovered
or persisted worktree paths:

```json
{
  "workspaces": [
    {
      "name": "personal",
      "anchors": [
        "/home/me/projects/dashpot",
        "/home/me/independent-clones/dashpot"
      ]
    }
  ]
}
```

Relative anchor paths are resolved relative to the inventory file. Every anchor
is validated independently, and clones with the same Project Identity and
Repository Identity are presented as one Project. Anchor order is significant:
the first valid anchor for a Project supplies its display label and is the
authoritative checkout used for Issue collection.

On every refresh, Dashpot asks Git for the main and linked worktrees reachable
from every configured anchor. These runtime Observation Targets are deduplicated
by path and report branch or detached state, HEAD, dirty state, availability,
elapsed time, and target-specific diagnostics. Locked, prunable, missing, and
inaccessible targets remain visible without degrading the Project's Issue
Source. Target inventory is never persisted, and Project-level Issues are still
collected exactly once from the authoritative anchor.

The same collector has a headless JSON interface:

```bash
uv run dashpot --workspace my-project=/path/to/project --json
```

The TUI uses each Project's mutable display label. Headless snapshots also
include its durable `projectId` and `repositoryId`, along with Workspace names
and Repository Anchors, so automation and diagnostics do not depend on labels or
paths for identity.

## Project configuration

Configure a repository as a Dashpot Project with `dashpot init`, run from
anywhere inside its worktree. With a GitHub `origin` remote it asks nothing:
the Issue Source defaults to GitHub Issues and the durable repository identity
is resolved through the authenticated `gh` CLI. Without one, declare a Local
Issue Markdown source instead:

```bash
dashpot init
dashpot init --markdown issues
```

`dashpot init` never overwrites an existing configuration, and running
`dashpot` in an unconfigured repository never writes anything; it reports how
to proceed.

Every Repository Anchor has a tracked `.dashpot/config.json` containing stable
Project and Repository identities, a mutable display label, and the active
Issue Source. The `.dashpot/state/` directory holds ignored local runtime
state; add it to your repository's `.gitignore` so it never dirties the
worktree or gets committed:

```gitignore
.dashpot/state/
```

A GitHub-backed Project looks like this:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "displayLabel": "Dashpot",
  "repositoryId": "R_kgDOUEerrg",
  "issueSource": {
    "kind": "github"
  }
}
```

The Repository Anchor must have a GitHub `origin`; collection uses the
authenticated `gh` CLI. A Local Issue Markdown Project selects a repository-
relative file or directory:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "displayLabel": "Dashpot",
  "repositoryId": "repository:01947e42-4f18-74d1-b25f-329ef29b270c",
  "issueSource": {
    "kind": "markdown",
    "path": "issues"
  }
}
```

The owned file grammar is documented in
[`conformance/issue/local-markdown.md`](conformance/issue/local-markdown.md).
By default, both adapters collect the complete source inventory, including open
and closed Issues; source collection does not apply a lifecycle filter. The TUI
defaults its Work list to open Issues. Both adapters are currently read-only.

## Agent session observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` and
`dashpot-claude-code-hook` publishers. Nothing is installed into a harness
automatically; register the lifecycle hooks once per user with:

```bash
dashpot integrate codex                 # hooks in ~/.codex/hooks.json
dashpot integrate claude-code           # hooks in ~/.claude/settings.json
dashpot integrate <harness> --status    # diagnose config, publisher, records
dashpot integrate <harness> --remove    # remove exactly the Dashpot hooks
```

Installation performs a surgical merge of the harness's user-level hook file:
existing hooks and unrelated settings are preserved, the registered command is
the absolute path of this environment's publisher (so hook and observer
versions stay in lock-step), and rerunning `integrate` is idempotent and
repairs stale paths. Removal deletes only the Dashpot handlers. If Codex hooks
are also defined inline in `~/.codex/config.toml`, Dashpot leaves that file
alone and points out that Codex merges both layers.
[`examples/codex-hooks.json`](examples/codex-hooks.json) shows the equivalent
manual Codex configuration.

The hooks report session lifecycle only: which agent sessions are alive at a
worktree and whether they are running, waiting, or ended. A session that has
not declared an Issue is not listed as Work; it is counted in the Project's
`Agents` fact until it opts in with `dashpot work start`. Codex and Claude
Code sessions are observed side by side with distinct identities, and both may
work on the same Issue as separate Agent Runs. One user-level installation per
harness covers every configured repository, including linked worktrees: each
observation is routed to the checkout the session runs in, landing in that
worktree's ignored `.dashpot/state/sessions/`. Sessions outside any
Dashpot-configured checkout fall back to the platform's normal
application-state location; set `DASHPOT_STATE_DIR` to override that fallback.

## Issue work opt-in

An agent session declares which Issue it is working on from inside the
session, at the worktree where the work happens:

```bash
dashpot work start '#123'      # an Issue Number, or a full Issue Reference
dashpot work show              # list active Issue work at this worktree
dashpot work stop              # end this session's run; the session stays alive
```

`dashpot work start` resolves the Reference against the Project configured at
that worktree, requires it to identify exactly one currently observed Issue,
and atomically records the resulting durable Issue Identity in the Project-local
Work Store (`.dashpot/state/work/`). Running `start` again switches the session
to a new Issue. Once recorded, the binding survives repository renames, Issue
Reference edits, Local Issue moves, and transfers between configured Projects.
The ordinary TUI continues to show current References; raw identities remain in
headless output and diagnostics.

The Work Store is the sole authority for Issue association. Collection
correlates each recorded run with the hook's lifecycle observations by process
identity; a hook record that carries a global Issue binding (the retired
`DASHPOT_ISSUE_ID`/`DASHPOT_ISSUE_REF` environment convention) is rejected with
a diagnostic pointing at `dashpot work start`, never silently combined.

## Design

Observation is scheduled per key rather than as one refresh: each Project's
Issue Source and its worktree topology are observed independently, and Agent
Runs are observed once per Workspace whenever a Project has been published. An
[`ObservationCoordinator`](src/dashpot/collect.py) tracks a generation per key
so a superseded observation can never overwrite a newer one, retains the last
good result per key when a refresh fails, and composes each Project from its
latest accepted halves. The Textual interface publishes every accepted
observation into a process-local `WorkspaceObservationStore` as soon as it
lands, then re-queries source-neutral Issue-list read models carrying a store
revision; a slow GitHub call therefore never delays branch or dirty state.
`r` refreshes the selected row's Project (or all when nothing is selected) and
`R` fans out to the whole Workspace. Exceptional state is summarized in a
one-line alert above Diagnostics that takes no space while everything is
healthy: refresh failures and unavailable Projects are errors, unavailable or
stale worktrees and stale Issue Sources are warnings, and a refresh that has
been running longer than a moment is shown as information. The alert is
derived from current observations and clears itself on recovery; toasts are
reserved for manual-refresh failures and their recovery, and Diagnostics keeps
the durable detail. Headless JSON runs a coordinated barrier
over every key and serializes the store's `checkpoint()`, so it remains one
complete snapshot. Collection happens off the UI thread, and the table is
reconciled by stable row keys. See
[`docs/textual-implementation-notes.md`](docs/textual-implementation-notes.md) for
the framework research behind the current implementation.

## License

MIT
