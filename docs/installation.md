---
status: living
date: 2026-09-11
---

# Install and maintain Dashpot

The first release is being prepared. The PyPI commands below are the release
installation contract and work once `0.1.0` is published. Until then, use the
[development setup](../README.md#development-setup) or install a candidate wheel
with `uv tool install /absolute/path/to/dashpot-0.1.0-py3-none-any.whl`.

## Supported environments

| Component | Release target and evidence |
| --- | --- |
| Python | CPython 3.11–3.14. CI tests 3.11/3.14 on Linux and macOS, and 3.12/3.13 on Linux. Later Python versions remain unvalidated. |
| Linux | x86-64; Ubuntu CI plus a real-host checklist before publication. |
| macOS | Apple Silicon; macOS CI plus real-host acceptance on `omar` in [#5](https://github.com/ned2/dashpot/issues/5). Host acceptance is pending. |
| Git | 2.38 or newer. The minimum-version CI leg exercises the full suite with 2.38.0, including content-based Branch integration. |
| GitHub CLI | gh 2.100.0 or newer for GitHub-backed Projects. 2.100.0 passed live collection during release planning; older versions are outside the initial support promise. |
| Codex | Candidate baseline 0.154.0, subject to the per-host lifecycle checklist. |
| Claude Code | Candidate baseline 2.1.261, subject to the per-host lifecycle checklist. |

Windows, Intel macOS, other architectures, and older harnesses are not part of
the initial release target. A passing automated TUI test does not establish
real-host process identity or lifecycle-hook compatibility. Final evidence
belongs in [#5](https://github.com/ned2/dashpot/issues/5); complete the
[host checklist](releasing.md#host-acceptance) before publication.

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv tool install --python 3.14 dashpot
dashpot --version
dashpot --help
```

`--python 3.14` selects a supported interpreter; any supported version may be
used. uv can provision Python if necessary. Dashpot's exact Textual dependency
is isolated from other applications. If `dashpot` is not on PATH, run
`uv tool update-shell`, then open a new shell. Use `uv tool list` to inspect
the installation. Run `dashpot` directly in your Projects; `uv run dashpot` is
the contributor command for a Dashpot source checkout.

Verify external prerequisites with `git --version` and, for GitHub,
`gh --version`. Install Git and the [GitHub CLI](https://cli.github.com/) through
their supported installers or your operating system's package manager. Dashpot
does not install or upgrade those tools or the agent harnesses.

## Configure a Project

For a Git repository with a GitHub `origin`, authenticate `gh` and initialize:

```bash
gh auth login
gh auth status
cd /path/to/project
dashpot init
dashpot --json
dashpot
```

The authenticated account must be able to read the repository, its Issues, and
Pull Requests. Private repositories and organization SSO may require additional
authorization. No Dashpot-specific credential file is needed.

For a Project without GitHub:

```bash
cd /path/to/project
mkdir -p issues
dashpot init --markdown issues
dashpot
```

An existing empty directory is a valid empty Issue Source. Add Issues using the
[Local Issue Markdown grammar](../conformance/issue/local-markdown.md); Dashpot
does not create or edit them. This mode requires Git but does not require gh.

Track `.dashpot/config.json` in the Project. Add this rule to `.gitignore`:

```gitignore
.dashpot/state/
```

The ignored state contains the Project-local Work Store and session records.
Each linked Worktree owns its own state. The Work Store holds
declared Issue work and is not a user-edited file format. Machine-local Workspace
inventory and settings remain outside Project configuration. See
[Project configuration](../README.md#project-configuration) for full discovery
and ownership rules.

## Observe agent sessions

Install and run the selected harness once so its configuration directory
exists. Register the desired integration explicitly:

```bash
dashpot integrate codex
dashpot integrate codex --status
dashpot integrate claude-code
dashpot integrate claude-code --status
```

Register only the harnesses you use. Review any hook-trust prompt in the
harness, and start or resume a session in the configured Project. The
integration installs lifecycle hooks and the managed `dashpot-issue-work`
skill. It preserves unrelated settings; repeated installation refreshes its
own entries. An Agent Session declares Issue work with `dashpot work start`
from inside that session, as described in [Agent sessions](agent-sessions.md).

## Diagnose an installation

| Symptom | Check and next action |
| --- | --- |
| `dashpot` is not found | Run `uv tool list` and `uv tool update-shell`, then reopen the shell. |
| A different Dashpot version runs | Inspect `command -v dashpot` and `uv tool list`; select the intended tool installation before integrating. |
| Git is missing or an option is unsupported | Check `git --version`, install Git 2.38+, and ensure that version is on PATH. Content-based integration requires `merge-tree --write-tree`. |
| GitHub collection fails | Check `gh --version` and `gh auth status`, repository access, network connectivity, and the reported Diagnostic. Authentication failures remain distinct from an empty Issue collection. |
| The repository is unconfigured | Run `dashpot init`, or `dashpot init --markdown issues`, and ignore `.dashpot/state/`. |
| An Issue Source is unavailable | Inspect Diagnostics in the TUI or `dashpot --json`; a bad Markdown file fails the complete collection. |
| Sessions are missing or Issue opt-in is refused | Run `dashpot integrate <harness> --status` inside the session's Worktree; inspect hook trust, publisher path, skill version, and the confirmed Agent Session Identity. |
| Session liveness is unknown | Read the Diagnostic: an isolated process namespace can hide a live process. Unknown does not mean the Agent Session ended. |

## Upgrade and uninstall

Before upgrading, finish active Issue work and pending Relocation Intents, and
exit harness clients that would keep invoking the old publisher during the
upgrade. Review the [changelog](../CHANGELOG.md), then:

```bash
uv tool upgrade dashpot
dashpot --version
dashpot integrate codex
dashpot integrate claude-code
```

Rerun only installed integrations, then check their `--status` and restart the
harnesses. The hooks contain absolute publisher paths, and the managed skill
must match the installed version. `uv tool upgrade` respects the original
version constraint; an installation pinned to an exact release must be
reinstalled with the desired version. Within `0.1.x`, documented commands,
JSON, and user configuration remain compatible; a breaking change requires a
new minor release and release notes. Downgrades across changed Work Store
versions are not promised.

To uninstall, finish active Issue work, exit harness clients, and remove the
integrations while Dashpot is still available:

```bash
dashpot integrate codex --remove
dashpot integrate claude-code --remove
uv tool uninstall dashpot
```

Remove only integrations you installed. These commands preserve unrelated
harness settings. Uninstalling the tool does not delete Project configuration,
Local Issues, Worktrees, or Work Stores. Any later state removal is a separate
person-selected action; inspect active Agent Runs and pending Relocation
Intents first. Session records outside configured Projects use the documented
global fallback, which is not a global authority for Issue Bindings.
