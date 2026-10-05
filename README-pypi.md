# Dashpot

_Useful damping for agent-assisted projects._

Dashpot is a terminal view of GitHub or Local Markdown Issues, Pull Requests,
Git Branches and Worktrees, and active Codex, Claude Code and OpenCode
sessions. It makes declared Issue work and repository state visible together.

Observation does not change Issues or Git refs. Fetch and Cleanup are explicit
actions; Cleanup previews concrete targets and requires confirmation.

## Install

Use [uv](https://docs.astral.sh/uv/getting-started/installation/) to install
Dashpot in its own environment:

```bash
uv tool install --python 3.14 dashpot
dashpot --version
```

The first release targets Linux and Apple Silicon macOS with CPython 3.13–3.14.
Git 2.39 or newer is required. GitHub-backed Projects also require authenticated
GitHub CLI (`gh`); the release baseline is gh 2.100.0. See the
[support and installation guide](https://github.com/ned2/dashpot/blob/main/docs/installation.md)
for host-validation status, harness versions, PATH setup, diagnosis, upgrades,
and uninstall instructions.

## Start with a Project

From a Git repository with a GitHub `origin`:

```bash
gh auth login
dashpot init
dashpot
```

Commit `.dashpot/config.json` as Project configuration. Local runtime state
lives in `.dashpot/state/`, which ignores itself in Git. For a Project without
GitHub, use `dashpot init --markdown issues` with an existing directory of
[Local Issue Markdown](https://github.com/ned2/dashpot/blob/main/conformance/issue/local-markdown.md).

Harness observation is opt-in. Integrate only the harnesses you use, naming
any of `claude-code`, `codex` or `opencode`, one or several in one command,
then check them:

```bash
dashpot integrate claude-code codex
dashpot integrate --status
```

Before upgrading Dashpot, finish active Issue work and exit harness clients.
Then refresh every harness already integrated, and no other, and restart the
clients:

```bash
uv tool upgrade dashpot
dashpot integrate --installed
dashpot integrate --status
```

See
[Upgrade and uninstall](https://github.com/ned2/dashpot/blob/main/docs/installation.md#upgrade-and-uninstall)
for the complete steps.

Dashpot 0.1.0 is alpha software. Documented command behavior, JSON, and user
configuration remain compatible within 0.1.x; breaking changes require a new
minor version and release notes. Python internals and exact terminal layout
are not extension interfaces.

[Documentation](https://github.com/ned2/dashpot#documentation-map) ·
[Issues](https://github.com/ned2/dashpot/issues) ·
[Release notes](https://github.com/ned2/dashpot/blob/main/CHANGELOG.md) ·
[Source and MIT license](https://github.com/ned2/dashpot)
