# Dashpot

Useful damping for agent-driven projects.

Dashpot is a passive terminal view of declared work, repository state, and active
coding-agent runs. It makes the small but important project-management pause
visible before another prompt or agent adds more motion.

Like its mechanical namesake, Dashpot is intended to reduce oscillation without
stopping progress. It observes; it does not assign or edit Issues, mutate
repositories, or control agent sessions.

> [!NOTE]
> Dashpot is an early implementation extracted from a successful research spike.
> Its interfaces and packaging are not yet stable.

## What it observes

- Projects with either GitHub Issues or Dashpot's Local Issue Markdown
- git branch, worktree, HEAD, and dirty state
- Codex lifecycle records published through an opt-in hook
- source freshness, failures, and last-good state
- explicit Issue-to-agent correlation through Issue References

Each source remains independent in the read model. A failed Issue refresh, for
example, does not erase the last good Issue collection or hide repository facts.

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
`.dashpot.json`. Outside a configured Project it discovers Projects from
Dashpot's `~/.config/dashpot/workspaces.json`. Explicit `--workspace`
arguments take precedence; use `--config` to select a different workspace
inventory. Use `r` to refresh, the arrow keys to move, and `q` to quit. The
default 15-second polling period can be changed with `--refresh-seconds`; zero
disables polling.

The same collector has a headless JSON interface:

```bash
uv run dashpot --workspace my-project=/path/to/project --json
```

## Project configuration

Every Repository Anchor has a tracked `.dashpot.json` containing its stable
Project Identity and active Issue Source. A GitHub-backed Project looks like
this:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "issueSource": {
    "kind": "github",
    "repositoryId": "R_kgDOUEerrg"
  }
}
```

The Repository Anchor must have a GitHub `origin`; collection uses the
authenticated `gh` CLI. A Local Issue Markdown Project selects a repository-
relative file or directory:

```json
{
  "projectId": "project:01947e42-3f67-7c38-a41c-218df18a169b",
  "issueSource": {
    "kind": "markdown",
    "path": "issues"
  }
}
```

The owned file grammar is documented in
[`conformance/issue/local-markdown.md`](conformance/issue/local-markdown.md).
Both adapters are currently read-only.

## Codex observation

Installing Dashpot provides the no-stdout `dashpot-codex-hook` publisher.
[`examples/codex-hooks.json`](examples/codex-hooks.json) shows the opt-in Codex
hook configuration. No hook is installed automatically.

Start an Issue-bound Codex session by passing its current Issue Reference:

```bash
DASHPOT_ISSUE_REF=owner/repository#123 codex
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
