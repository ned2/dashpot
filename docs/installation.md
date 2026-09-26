---
status: living
date: 2026-09-27
---

# Install and maintain Dashpot

The first release is being prepared. The PyPI commands below are the release
installation contract and work once `0.1.0` is published. Until then, use the
[development setup](../README.md#development-setup) or install a candidate wheel
with `uv tool install /absolute/path/to/dashpot-0.1.0-py3-none-any.whl`.

## Supported environments

| Component | Release target and evidence |
| --- | --- |
| Python | CPython 3.12–3.14. CI tests 3.12/3.14 on Linux and macOS, and 3.13 on Linux. Later Python versions remain unvalidated. |
| Linux | x86-64; Ubuntu CI plus a real-host checklist before publication. |
| macOS | Apple Silicon; macOS CI plus real-host acceptance on `omar` in [#5](https://github.com/ned2/dashpot/issues/5). Host acceptance is pending. |
| Git | 2.39 or newer, with current vendor patches. The minimum-version CI leg exercises the full suite with Debian 12’s packaged Git 2.39.x, including content-based Branch integration. |
| GitHub CLI | gh 2.100.0 or newer for GitHub-backed Projects. 2.100.0 passed live collection during release planning; older versions are outside the initial support promise. |
| Codex | Candidate baseline 0.154.0, subject to the per-host lifecycle checklist. |
| Claude Code | Candidate baseline 2.1.261, subject to the per-host lifecycle checklist. |

Windows, Intel macOS, other architectures, and older harnesses are not part of
the initial release target. A passing automated TUI test does not establish
real-host process identity or lifecycle-hook compatibility. Final evidence
belongs in [#5](https://github.com/ned2/dashpot/issues/5); complete the
[host checklist](releasing.md#host-acceptance) before publication.

The Git baseline is the maintained Debian 12 (Bookworm) package, rather than
unpatched upstream 2.39.0. CI installs current Bookworm updates and checks the
2.39.x series; ordinary Linux and macOS jobs exercise newer Git versions.
Git has [no guaranteed upstream long-term support policy](https://github.com/git/git/security/policy)
for older feature series. Vendor maintenance supplies the baseline's security
updates. Revisit this baseline by [Debian 12 LTS end, 30 June 2028](https://www.debian.org/releases/bookworm/),
or sooner if support for its Git package changes.

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
authorization. No Dashpot-specific credential file is needed. Dashpot's GitHub
queries count against that account's hourly allowance, which `gh` and agents
acting as the same user share; see [GitHub rate limits](github-rate-limits.md).

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

Track `.dashpot/config.json` in the Project. The `.dashpot/state/` directory
beside it ignores itself: Dashpot writes a `.gitignore` containing `*` into it
whenever it writes state there, so it needs no rule in the Project's own
`.gitignore`. A state directory an earlier Dashpot wrote gains the file the
next time Dashpot writes state there. The ignored state contains the
Project-local Work Store and session records. Each linked Worktree owns its own
state. The Work Store holds
declared Issue work and is not a user-edited file format. Machine-local Workspace
inventory and settings remain outside Project configuration. See
[Project configuration](../README.md#project-configuration) for full discovery
and ownership rules.

## Machine-local settings

Edit `$XDG_CONFIG_HOME/dashpot/config.toml`, or
`~/.config/dashpot/config.toml` when `XDG_CONFIG_HOME` is unset:

```toml
# Where newly prepared Issue Worktrees go.
worktree_root = '~/projects/.worktrees/dashpot'
```

An absent, empty, or comment-only file selects defaults. Omit an optional key
for its default; TOML has no null value. Unknown keys produce a warning and do
not override recognized keys. Use `worktree_root`, not `worktreeRoot`.
Invalid TOML, unreadable files, and invalid known values produce an error naming
the file. Worktree preparation reads settings before applying command-line or
environment overrides, so those overrides do not hide malformed configuration.

Use TOML 1.0 syntax: `#` begins a comment outside strings; single-quoted literal
strings preserve backslashes, while double-quoted strings interpret escapes
(for example, `"C:\\worktrees"`). TOML also supports multiline arrays. Configure a custom Worktree launcher with an argument array:

```toml
worktree_open_command = [
  '/absolute/path/to/my-launcher',
  '{path}',
]
```

Set how often the dashboard refreshes by itself, in seconds
([ADR 0056](adr/0056-refresh-github-queries-on-their-own-period.md)):

```toml
# Worktrees, Branches, Agent Sessions, and a Local Markdown Issue Source.
refresh_seconds = 15
# GitHub Issues, Pull Requests, Project Totals and bound Issues.
github_refresh_seconds = 60
```

Each is a finite number of seconds, zero or more; 0 switches that automatic
refresh off, and `r` still refreshes on demand. Omit a key for its default,
shown above. `--refresh-seconds` and `--github-refresh-seconds` override the
settings for one run. The dashboard still opens when the settings file cannot
be read: the periods keep their defaults, unless a flag sets one, and the
dashboard shows the settings error as a Diagnostic.

Parsing never performs shell or environment-variable expansion. For `worktree_root`, Dashpot
strips surrounding whitespace, expands `~`, and resolves relative paths against
the settings file's parent directory. Precedence remains `--worktree-root`,
then `DASHPOT_WORKTREE_ROOT`, then `worktree_root`, then the main working
tree's sibling default in [Issue Worktrees](../README.md#issue-worktrees).

For the one-time cutover, recreate an old setting such as
`{"worktreeRoot": "~/projects/.worktrees/dashpot"}` using the TOML example above.
Simply renaming the old JSON file is insufficient. Replace a previous null value
by omitting the key. Dashpot ignores `settings.json` entirely, even if malformed;
leaving only that file selects defaults and can change where new Worktrees go.
Remove the old file manually when convenient. Dashpot never rewrites or deletes
personal settings.

This file contains machine-local preferences only. Workspace inventory remains
`workspaces.json`, selected by `--config`; tracked Project configuration remains
`.dashpot/config.json`. Work Store records, public JSON output, and external
harness configuration retain their formats.

## Event Log

Every Dashpot process — the dashboard, each command, each lifecycle hook —
records what it does as Runtime Events in an Event Log on this machine.
Nothing is sent anywhere
([ADR 0058](adr/0058-record-runtime-events-locally-and-send-none.md),
[ADR 0059](adr/0059-keep-an-append-only-event-log-in-each-checkout.md)).

A process whose working directory is inside a configured checkout — one
whose Worktree root carries `.dashpot/config.json` — writes to that
checkout's `.dashpot/state/events/`, which is ignored with the rest of
`.dashpot/state/`. Any other process writes to
`$XDG_STATE_HOME/dashpot/events/`, else `~/.local/state/dashpot/events/`, or
`~/Library/Application Support/dashpot/events/` on macOS. Hooks and
commands share one file per UTC day, `events-YYYY-MM-DD.jsonl`; each
dashboard run writes its own, `dashboard-<run>-YYYY-MM-DD.jsonl`. Each line
is one JSON event. Removing a Worktree removes its Event Log with it.

Choose how much is recorded with the `event_level` setting:

```toml
# off, standard (the default), or full.
event_level = 'standard'
```

`off` records nothing. `standard` records process starts and ends, hook and
command outcomes, Agent Session and Agent Run changes, Diagnostics, every
GitHub request and every failure. `full` adds every local observation and
command, which is useful when developing Dashpot and writes about 45 MB a
day for a dashboard on a busy Repository. The `DASHPOT_EVENT_LEVEL`
environment variable overrides the setting for the processes that inherit
it, hooks included. A settings file that cannot be read leaves the level at
`standard`; hooks and commands say nothing about it, and the dashboard
shows the settings error as a Diagnostic.

A write that fails is dropped, and never fails the work it describes. The
dashboard reports the first one as an `event-log-unavailable` Diagnostic;
hooks and commands stay silent. Each event is appended whole with one write,
which keeps concurrent writers' lines intact on a local filesystem; on NFS a
line written by two processes at once may be interleaved.

Runtime Events hold identifiers, not messages: paths (which include your
home directory), Branch names (which carry Issue title slugs), Issue and
Pull Request numbers, Agent Session Identities and exit statuses, never
tokens, command output, titles, prompts or error messages. Read an Event
Log before attaching it to a bug report, and remove anything you would not
share.

`gh` has telemetry of its own: GitHub CLI 2.100 sends usage data by
default, and the `gh` processes Dashpot starts send it like any other `gh`
run. Dashpot leaves that to your `gh` configuration. To turn it off, set
`GH_TELEMETRY=0`, or `DO_NOT_TRACK=1` for every tool that honours it, in the
environment Dashpot runs in.

### Read the Event Log

`dashpot events` prints the Runtime Events recorded in this Repository, one
per line, oldest first:

```sh
dashpot events --since 12h
dashpot events --session <agent-session-id> --level standard
dashpot events --issue <issue-identity> --json
```

It merges the Event Log of every Worktree of the Repository, as
`git worktree list` names them, with the machine-local fallback, ordered by
time; outside a Repository it reads the fallback alone. It is the supported
route to a sibling Worktree's events for an agent whose sandbox cannot read
that Worktree directly. `--session` takes an Agent Session ID, `--issue` an
Issue Identity as `dashpot work show` prints it, and `--project` a Project
Identity, the `projectId` of `.dashpot/config.json`; each matches the field
wherever an event carries it. `--since` takes a UTC day (`2026-09-27`), an
instant (`2026-09-27T14:00:00Z`) or an age (`30m`, `12h`, `7d`); `--level
standard` keeps only the events the default level records. The command
leaves out its own events.

A dashboard records every event of its run in the checkout it was started
in, including its observations of the Workspace's other Projects, so read a
dashboard's events from the Repository it was started in; `--project` then
narrows them to one Project.

Reading is tolerant. A line that is not a Runtime Event this version knows —
a torn write, an event a newer Dashpot recorded, anything else — is skipped
and reported on standard error with its file, and a file that cannot be read
is reported the same way; the command still prints what it could read.
`--json` prints `directories`, `events` and `unreadable`; each event keeps
the field names it has in the Event Log. `dashpot events` reads only the
Event Log's own `.jsonl` files: a file that has been renamed or compressed,
by `logrotate` or anything else, is invisible to it.

`dashpot work show` ends with the current Agent Session's recent outcomes
from the same Event Log — at most 20 from the last 7 days, failures
included — reading back only as many days as it needs.

### Remove old Event Log files

Dashpot never deletes, compresses or renames an Event Log on its own, and the
dashboard shows an `event-log-large` Diagnostic when its checkout's Event Log
passes 200 MB. Remove old files explicitly:

```sh
dashpot events remove --before 2026-09-01 --dry-run
dashpot events remove --before 2026-09-01
```

`events remove` acts on the Event Log of the checkout it runs in, or on the
machine-local fallback when it runs outside every configured checkout. It
removes only files named as the Event Log names them whose UTC day is before
`--before`, never a file dated today or later, so a writer's current file is
always safe. It asks nothing, prints each file with its size, prints the
result as JSON with `--json`, and exits 2 when a file could not be removed.
Run it in each Worktree whose Event Log you want to trim; removing a
Worktree removes its Event Log with it.

Scheduled removal can run the same command, or `find`; a writer whose current
file was moved or deleted starts a new one. A daily `cron` entry keeping 30
days (GNU `date`; `cron` needs `%` escaped):

```sh
0 3 * * * cd /path/to/project && dashpot events remove --before "$(date -u -d '30 days ago' +\%F)"
```

A systemd user timer running `find`, as
`~/.config/systemd/user/dashpot-events.service`:

```ini
[Unit]
Description=Remove Dashpot Event Log files older than 30 days

[Service]
Type=oneshot
ExecStart=/usr/bin/find /path/to/project/.dashpot/state/events -name '*.jsonl' -mtime +30 -delete
```

and `~/.config/systemd/user/dashpot-events.timer`:

```ini
[Unit]
Description=Remove old Dashpot Event Log files daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable it with `systemctl --user enable --now dashpot-events.timer`. Where
`logrotate` already manages a machine's logs, a rule that removes each file
once it is 30 days old, and renames nothing, keeps the rest readable:

```text
/path/to/project/.dashpot/state/events/*.jsonl {
    daily
    minage 30
    rotate 0
    missingok
    nocreate
    nocompress
}
```

`missingok` and `nocreate` keep `logrotate` from complaining about a file
that is gone, or creating one a writer owns. Each file already holds one UTC
day, so a rule that keeps rotated copies — `rotate 7` with `maxage 30` — or
compresses them only leaves files `dashpot events` cannot read. Do not run
such a rule with `logrotate -f`, which ignores `minage` and removes today's
files too.

## Open Worktrees and copy paths

With the Worktrees table focused, `Enter` opens the selected Worktree and `y`
sends its full absolute path to the terminal clipboard. Mouse selection alone
does not open anything. The same actions apply to main and linked Worktrees.

A configured `worktree_open_command` takes precedence inside and outside tmux.
It must be a nonempty argument array with a nonblank executable first. Bare
executables use PATH; explicit executable paths must be absolute. Each standalone
`{path}` argument is replaced with the complete path; zero or repeated occurrences
are allowed. Other arguments are literal, including empty arguments. There is no
shell evaluation, environment expansion, or interpolation inside `--dir={path}`.
The selected Worktree is also the command's working directory. The command runs
on Dashpot's host with its normal environment; Dashpot does not load ignored
Worktree configuration or translate remote paths.

For example, an executable wrapper at `/absolute/path/to/open-terminal` can
request a persistent terminal and return promptly:

```sh
#!/bin/sh
# Install kitty separately, or substitute your terminal's command.
nohup kitty --directory "$PWD" </dev/null >/dev/null 2>&1 &
```

Configure `worktree_open_command = ['/absolute/path/to/open-terminal']`.
Redirect all three streams and detach persistent children: a background child
that retains captured pipes can keep the request pending after its parent exits.
A zero exit reports that the request completed, not that a shell is ready.
Requests use Dashpot's command timeout. A timeout may follow an already-opened
terminal; Dashpot does not retry or undo terminal actions automatically.

Omitting the setting uses automatic tmux behavior: when Dashpot runs inside
tmux, `Enter` splits its originating pane below, approximately in half, and
focuses the new pane with the selected directory requested through `-c`. tmux's
shell/default-command configuration still applies. Paths are passed literally,
including format-like `#{...}` or `#(...)` text and trailing semicolons. If the
directory disappears after validation, tmux can fall back to home or `/`; shell
startup can also change directory. Dashpot does not track or reuse panes.
Outside tmux, configure a launcher or press `y` to copy the path.

Settings are read at dashboard startup; restart Dashpot after editing them.
Read/validation failures disable Open Worktree and show a Diagnostic, while
observation and Copy path remain available. A failed custom launcher never falls
back to tmux. Unknown fields alone warn without disabling a valid launcher.

Copy path sends an OSC 52 clipboard request using the same transport as existing
text-selection copying. Terminal/tmux support determines delivery; Dashpot cannot
acknowledge host clipboard success. Inside tmux, applications need
`set -g set-clipboard on` and an outer terminal with clipboard support.
`set-clipboard external` ignores application requests. Enabling `on` permits
applications inside tmux to request clipboard writes; set it yourself if desired.
Text-selection copying uses this same transport and cannot bypass a blocked one.

## Observe agent sessions

Install and run the selected harness once so its configuration directory
exists. Register the desired integration explicitly:

```bash
dashpot integrate codex
dashpot integrate codex --status
dashpot integrate claude-code
dashpot integrate claude-code --status
```

Register only the harnesses you use, from the environment you mean to keep:
a tool installation or the Repository's main working tree, never a linked
Issue Worktree, whose `.venv` is removed with it. Review any hook-trust
prompt in the harness, and start or resume a session in the configured
Project. The
integration installs lifecycle hooks and the managed `dashpot-issue-work`
skill. It preserves unrelated settings; repeated installation refreshes its
own entries. An Agent Session declares Issue work with `dashpot work start`
from inside that session, as described in [Agent sessions](agent-sessions.md).

## Diagnose an installation

| Symptom | Check and next action |
| --- | --- |
| `dashpot` is not found | Run `uv tool list` and `uv tool update-shell`, then reopen the shell. |
| A different Dashpot version runs | Inspect `command -v dashpot` and `uv tool list`; select the intended tool installation before integrating. |
| Git is missing or an option is unsupported | Check `git --version`, install Git 2.39+, and ensure that version is on PATH. Content-based integration requires `merge-tree --write-tree`. |
| GitHub collection fails | Check `gh --version` and `gh auth status`, repository access, network connectivity, and the reported Diagnostic. Authentication failures remain distinct from an empty Issue collection. |
| GitHub observations go stale with a `github-rate-limit` Diagnostic | The account's hourly GraphQL allowance is spent. Close other dashboards or lengthen `github_refresh_seconds` (or `--github-refresh-seconds`), and wait for the reset; see [GitHub rate limits](github-rate-limits.md#staying-inside-the-limit). |
| GitHub Issues or Pull Requests lag a change by up to a minute | GitHub queries refresh on their own period, 60 seconds by default, while Worktrees and Agent Sessions refresh every 15. Press `r`, or lower `github_refresh_seconds`; see [Machine-local settings](#machine-local-settings). |
| The repository is unconfigured | Run `dashpot init`, or `dashpot init --markdown issues`, and commit `.dashpot/config.json`. |
| An Issue Source is unavailable | Inspect Diagnostics in the TUI or `dashpot --json`; a bad Markdown file fails the complete collection. |
| Sessions are missing or Issue opt-in is refused | Run `dashpot integrate <harness> --status` inside the session's Worktree; inspect hook trust, publisher path, skill version, and the confirmed Agent Session Identity. |
| Every hook event fails after a Worktree was removed, or `--status` warns that the publisher lives in a linked Worktree | The hooks were bound to a publisher in that Worktree's `.venv`, which the Cleanup removed. Rerun `dashpot integrate <harness>` from the Repository's main working tree or from an installed tool environment; `integrate` refuses to bind a linked Worktree's publisher in the first place. |
| The dashboard shows an `event-log-unavailable` Diagnostic | It could not write its [Event Log](#event-log); the work carries on and the events are dropped. Check that the checkout's `.dashpot/state/events/`, or the machine-local fallback, is writable and its disk is not full, or set `event_level = 'off'`. |
| The dashboard shows an `event-log-large` Diagnostic | Its checkout's Event Log holds more than 200 MB. Preview with `dashpot events remove --before DATE --dry-run` in the directory the Diagnostic names, then remove, or schedule removal; see [Remove old Event Log files](#remove-old-event-log-files). |
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
