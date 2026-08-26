# Dashpot

_Useful damping for agent-driven projects._

Dashpot is a passive terminal view of declared work, repository state, and active
coding-agent runs. It makes the small but important project-management pause
visible before another prompt or agent adds more motion.

Like its [mechanical namesake](https://en.wikipedia.org/wiki/Dashpot), Dashpot is intended to reduce oscillation without
stopping progress.

> [!NOTE]
> Dashpot is an early implementation extracted from a successful research spike.
> Its interfaces and packaging are not yet stable.

## What it observes

- TASKS.md projects using either local Markdown or GitHub Issues
- git branch, worktree, HEAD, and dirty state
- Codex lifecycle records published through an opt-in hook
- source freshness, failures, and last-good state
- explicit task-to-agent correlation through qualified work keys

Each source remains independent in the read model. A failed issue refresh, for
example, does not erase the last good task list or hide repository facts.

## Development setup

Dashpot requires Python 3.11 or newer and uses
[uv](https://docs.astral.sh/uv/) for its locked development environment.

```bash
uv sync --group dev
uv run pytest -q
```

Open the TUI for one or more projects:

```bash
cd /path/to/configured/project
uv run dashpot

uv run dashpot --workspace my-project=/path/to/project
uv run dashpot --workspace first=/path/one --workspace second=/path/two
```

Without arguments, Dashpot observes the current directory when it contains
`TASKS.md` or `.tasksmd.json`. Outside a configured project it discovers projects
from TASKS.md's `~/.config/tasks-md/workspaces.json`. Explicit `--workspace`
arguments take precedence; use `--config` to select a different workspace
inventory. Use `r` to refresh, the arrow keys to move, and `q` to quit. The
default 15-second polling period can be changed with `--refresh-seconds`; zero
disables polling.

The same collector has a headless JSON interface:

```bash
uv run dashpot --workspace my-project=/path/to/project --json
```

## Task sources

A project's `.tasksmd.json` selects its source. A GitHub Issues project looks
like this:

```json
{
  "backend": "github-issues",
  "repo": "owner/repository",
  "label": "tasks.md"
}
```

GitHub collection uses the authenticated `gh` CLI. Local Markdown collection
uses the `tasks` executable and its JSON output.

## Codex observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` publisher.
[`examples/codex-hooks.json`](examples/codex-hooks.json) shows the opt-in Codex
hook configuration. No hook is installed automatically.

Start a task-bound Codex session by passing its qualified work key:

```bash
DASHPOT_TASK_REF=github:owner/repository#123 codex
```

Hook records are stored under the platform's normal application-state location.
Set `DASHPOT_STATE_DIR` to override it. The TUI only reads and validates these
records.

## Design

The Textual interface sits on a headless `WorkspaceCollector.refresh()` contract.
Collection happens off the UI thread, project sources refresh independently, and
the table is reconciled by stable row keys. See
[`docs/textual-implementation-notes.md`](docs/textual-implementation-notes.md) for
the framework research behind the current implementation.

## License

MIT
