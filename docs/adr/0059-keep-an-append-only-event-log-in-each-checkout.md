---
status: accepted
date: 2026-09-27
---

# Keep an append-only Event Log in each checkout

[ADR 0058](0058-record-runtime-events-locally-and-send-none.md) keeps every
Runtime Event on the machine that recorded it. This decision says where on
that machine, in what shape, for how long, and what a person may rely on when
reading it. The full design, with its measurements and sources, is in
[observability design](../observability-design.md).

## Decision

### Location and routing

- **Per checkout, following [ADR 0003](0003-prefer-project-local-dashpot-state.md).**
  A process writes to `.dashpot/state/events/` in the configured checkout
  containing its working directory: the Worktree whose root carries
  `.dashpot/config.json`. That is the rule `route_record_store` already
  applies to hook records, and the hook publisher uses it for its Event Log
  too. A one-shot command writes to the checkout it runs in; a dashboard
  writes to the checkout it was started in, including events about other
  Projects of its Workspace.
- **Fallback.** A process with no configured checkout writes to
  `$XDG_STATE_HOME/dashpot/events/`, else `~/.local/state/dashpot/events/`,
  or `~/Library/Application Support/dashpot/events/` on macOS — the hook
  records' fallback, beside their `runs/` directory.
- **The directory ignores itself.** `.dashpot/state/` is created through the
  one helper that writes its `.gitignore`
  ([#312](https://github.com/ned2/dashpot/issues/312)), so an Event Log is
  never picked up by Git whatever the Project's own `.gitignore` says.
- **An explicit destination.** The dashboard and the command line take their
  Event Log's destination as an argument; the working directory only
  supplies the default, so tests and several apps in one process never share
  one.

### Files

- **Split by UTC date.** Hooks and one-shot commands share
  `events-YYYY-MM-DD.jsonl`. Each dashboard run writes its own
  `dashboard-<run>-YYYY-MM-DD.jsonl`, where `<run>` is its opaque run ID.
- **Every file describes its writer.** A process's first event is
  `process.start`. When a writer opens a file after that — the next day's at
  midnight UTC, or a file an outside tool moved or deleted — it first writes
  `process.continued`, repeating `process.start`'s fields.
- **One line per event, appended whole.** Each event is one JSON line of at
  most 8 KiB, written with a single `os.write` on an `O_APPEND` descriptor,
  which keeps concurrent writers' lines whole on a local filesystem. That is
  not guaranteed on NFS, and the installation guide says so. A longer event is
  dropped rather than split.

### Retention

- **Dashpot never deletes, compresses or renames an Event Log on its own.**
  An outside tool may: the installation guide gives a `cron` example, which
  a systemd timer or `logrotate` can replace, and a writer notices a moved or
  deleted current file and opens a new one.
- **Removal is explicit.** `dashpot events remove`
  ([#316](https://github.com/ned2/dashpot/issues/316)) deletes Event Logs
  only when invoked; "prune" already names the Remote Fetch's removal of gone
  Remote-Tracking Branches. An `event-log-large` Diagnostic warns without
  acting when a directory passes 200 MB.
- **Removing a Worktree removes its Event Log**, including the hook outcomes
  that explain its sessions. That is the cleanup the per-checkout location
  exists for, and a Cleanup's `--delete-ignored` acknowledgement already
  covers `.dashpot/state/`.

### Levels and counting

- **Three levels.** `off` writes nothing; `standard`, the default, writes
  process starts and ends, hook and management-command outcomes, Agent
  Session and Agent Run changes, Diagnostics appearing and clearing, level
  changes, every GitHub request span and every failed span; `full` adds every
  local observation and command span.
- **Chosen per machine, per run.** The `event_level` setting in `config.toml`
  ([ADR 0052](0052-read-machine-local-settings-as-toml.md)) is overridden by
  the `DASHPOT_EVENT_LEVEL` environment variable. A running dashboard may
  change its level for the rest of that run; the change never rewrites
  `config.toml` and is recorded as `level.changed`. There is no command-line
  flag. A settings file that fails to load leaves the default level, silently
  in hooks and commands.
- **Each event carries its level** (`dashpot.level`: `standard` or `full`).
- **Counts are derived from events.** Every metric is an aggregation over
  recorded events, computed when read; nothing keeps a running total, not
  even the dashboard's own view, which aggregates an in-memory buffer of
  recent events. Only what is always written at the level in force is
  counted: at `standard`, failed local spans are examples, never a count.
  `level.changed` marks where the level in force changed.

### Content

- **Identifiers and measurements, never free text.** Paths, Repository names,
  Issue and Pull Request numbers and IDs, Branch names, Agent Session
  Identities, harnesses, GraphQL operation names, Diagnostic codes, exit
  statuses, durations, counts, costs and sizes are recorded. Tokens,
  environment variables, command output, titles and bodies, search text,
  prompts, raw hook payloads and error messages never are.
- **Branch names and paths are kept.** They carry Issue title slugs
  ([ADR 0011](0011-prepare-issue-worktrees-by-convention.md)) and the home
  directory, and they are what a person debugging needs. The installation
  guide asks a person to read a log before attaching it anywhere.
- **An error is its code or class.** A Diagnostic code, a `DashpotError`
  subclass, an errno name: never its message, which for a `GitError` carries
  the full argument list and stderr. A command is recorded as its program and
  subcommand, never its arguments.
- **Enforced by the models.** Runtime Events are closed Pydantic models; no
  field can hold a message, and every string field is constrained to the
  identifier it names.

### Compatibility

- **`dashpot events --json` is a published interface** under
  [ADR 0034](0034-publish-an-alpha-with-patch-compatible-interfaces.md).
- **The file format is internal and versioned.** Every event carries
  `schema`; a reader tolerates fields a newer Dashpot added, and a change a
  tolerant reader could not read bumps the version. Field names follow
  OpenTelemetry semantic conventions where one exists and are `dashpot.*`
  otherwise.

### Writing never fails the work

- **A failed write is dropped.** The work it described carries on. A hook or
  command process stays silent about it; a dashboard records the failure as
  a Runtime Event in its in-memory buffer and raises one
  `event-log-unavailable` Diagnostic on the first.

## Consequences

- Observation now writes: the dashboard, `dashpot --json` and every
  read-only command append Runtime Events, and create
  `.dashpot/state/.gitignore`. [ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)'s
  list of observation's writes and [ADR 0003](0003-prefer-project-local-dashpot-state.md)'s
  runtime-state consequence are amended to include them; both remain writes
  to Dashpot's own ignored state.
- Every hook and command reads `config.toml` for the level, where only the
  launcher, the Refresh Periods and `worktree create` read it before.
- Events about several Worktrees of one Repository are spread across their
  checkouts; `dashpot events` merges every Worktree of the Repository and the
  machine-local fallback to read them back.
- An Event Log grows without bound until a person or their tools act. A
  dashboard at `full` writes about 45 MB a day on this Repository; at
  `standard` its volume follows the GitHub request rate, about 2 MB a day at
  the 60-second GitHub Refresh Period.

## Considered options

- **One machine-wide Event Log.** Rejected: [ADR 0003](0003-prefer-project-local-dashpot-state.md)
  puts runtime state beside the checkout it belongs to, and a machine-wide
  file would outlive the Worktrees it describes and grow across every
  Project on the machine.
- **Rotate and delete on a schedule inside Dashpot.** Rejected: deleting a
  person's records is a mutation observation must not make on its own
  ([ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md));
  size is warned about, and removal is a named command.
- **A logging library such as `logging` or structlog.** Rejected: events are
  already closed models rendered to one line, a library adds process-wide
  configuration that several apps in one test process would share, and
  structlog alone costs about 35 ms to import in a hook.
- **Counters kept beside the log.** Rejected: a running total disagrees with
  the events once either is lost or edited, and cannot be re-cut by session,
  Issue or time after the fact.
