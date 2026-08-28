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
- Codex lifecycle records published through an opt-in hook
- source freshness, failures, and last-good state
- durable Agent Run bindings through opaque Issue Identity

Each source remains independent in the read model. A failed Issue refresh, for
example, does not erase the last good Issue collection or hide repository facts.

## Development setup

Dashpot requires Python 3.11 or newer and uses
[uv](https://docs.astral.sh/uv/) for its locked development environment.

```bash
uv sync --group dev
uv run pytest -q
```

### Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on pull requests
targeting `main`, pushes to `main`, and manual dispatch. It tests the locked
environment on Ubuntu and macOS under Python 3.11 and 3.14, and builds the
package once per run. No credentials are provided and no live GitHub collection
happens in CI; the test suite exercises Issue collection against fakes.

Every CI verification step has an exact local equivalent:

```bash
# Verify uv.lock matches pyproject.toml
uv lock --check

# Install the locked development environment
uv sync --locked --group dev

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
different Workspace inventory. Use `r` to refresh, the arrow keys to move, and
`q` to quit. The default 15-second polling period can be changed with
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

## Codex observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` publisher.
[`examples/codex-hooks.json`](examples/codex-hooks.json) shows the opt-in Codex
hook configuration. No hook is installed automatically.

Start an Issue-bound Codex session by passing its opaque Issue Identity:

```bash
DASHPOT_ISSUE_ID=I_kwDOUEerrs8AAAABOSTptQ codex
```

An Issue Reference can be supplied as a one-time human-facing hint when the
identity is not convenient:

```bash
DASHPOT_ISSUE_REF=owner/repository#123 codex
```

Dashpot resolves explicit Reference hints, or an `issue/...` branch convention,
only when they identify exactly one Issue in the Agent Run's observed Project.
It then atomically persists the resulting Issue Identity. Ambiguous, stale, or
temporarily unverifiable hints remain unbound and produce diagnostics rather
than guesses. Once established, the binding survives repository renames, Issue
Reference edits, Local Issue moves, and transfers between configured Projects.
The ordinary TUI continues to show current References; raw identities remain in
headless output and diagnostics.

Hook records are stored under the platform's normal application-state location.
Set `DASHPOT_STATE_DIR` to override it. Dashpot reads and validates these records;
when a hint resolves unambiguously, collection atomically promotes it to a durable
Issue Identity binding before presenting the relationship.

## Design

`WorkspaceCollector.refresh()` still produces a complete serializable checkpoint,
but it is no longer the application's retained state. The Textual interface
accepts collector results into a process-local `WorkspaceObservationStore`, then
queries source-neutral Issue-list read models carrying a store revision. Headless
JSON is assembled through the same store's `checkpoint()` interface. Collection
happens off the UI thread, and the table is reconciled by stable row keys. See
[`docs/textual-implementation-notes.md`](docs/textual-implementation-notes.md) for
the framework research behind the current implementation.

## License

MIT
