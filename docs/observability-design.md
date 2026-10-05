---
status: living
date: 2026-10-05
---

# Observability design

Dashpot records what it does as Runtime Events in a local Event Log, and
derives every count it shows from those events when they are read. This
document holds the whole design settled in
[#311](https://github.com/ned2/dashpot/issues/311), with the corrections its
review and backlog grooming made, the measurements behind it, and the fields
an event carries on disk. Two ADRs make its commitments binding:
[ADR 0058](adr/0058-record-runtime-events-locally-and-send-none.md) keeps
every Runtime Event on the machine, and
[ADR 0059](adr/0059-keep-an-append-only-event-log-in-each-checkout.md) sets
where the Event Log lives, its shape, levels, content and compatibility. The
terms are in the [domain language](domain-language.md#runtime).

## Why

Before this design Dashpot had no record of its own behaviour: no `logging`
import, no Textual `log`, no debug flag.

- A hook publisher that failed printed one line to the harness's stderr and
  exited 1. Asking "why did my session not bind?" left nothing to read.
- A failure off the event loop kept only its message, not its traceback.
- Cost was measured from outside: GitHub spend by sampling the dashboard's
  child processes ([#308](https://github.com/ned2/dashpot/issues/308)), local
  load by tracing a dashboard with `strace`.
- Nothing was kept over time, for a person troubleshooting or for a dashboard
  left running for weeks.

## Audiences and principles

- **Audiences, in order:** developing Dashpot; agents using Dashpot; people
  fixing their setup; watching long runs; bug reports. Output is therefore
  machine-readable, bounded, and holds no free text.
- **Dashpot's own data stays local.** Nothing is sent anywhere. `gh` has
  telemetry of its own, enabled by default in gh 2.100 (`gh send-telemetry`
  appears in a traced dashboard); Dashpot's `gh` children send it like any
  other `gh` run. Dashpot leaves that to the person's `gh` configuration and
  documents `GH_TELEMETRY=0` and `DO_NOT_TRACK=1`
  ([installation guide](installation.md#event-log)).
- **Events first, no counters.** Code records Runtime Events; every metric
  is an aggregation over recorded events, computed when read. Nothing keeps
  a running total, not even Runtime Stats, which aggregates an in-memory
  buffer of recent events.

## Runtime Events

- **Two kinds.** A *span* is a timed, nested unit of work — a refresh, then
  an observation or query, then a command or GitHub request — with an ID, a
  parent ID and a status. A *standalone event* is something that is not a
  unit of work: a process starting, a Diagnostic appearing or clearing, a
  level change, a hook arriving.
- **A span has an explicit start and end.** Dashboard work is asynchronous:
  `request_refresh` returns once it has scheduled work, and the page runner
  runs queued requests later from another message. So a refresh span starts
  when its timer (or `r`) fires and ends when the last key it scheduled
  lands; its owner holds it and names it as the parent of the work it
  schedules. A context-manager form times synchronous work, such as one
  command inside one observation.
- **What counts as failed.** A span fails when its work could not be done: a
  `CommandError` or `OSError` (the program could not start, timed out or was
  interrupted), a GitHub request failure, or a failure its caller classifies
  as one. A non-zero exit is an attribute, not a failure: `Git.maybe` and
  `Git.count` read one as an answer, and `merge-base` and `rev-parse` answer
  that way for every Branch on every refresh.
- **Process identity.** Every event carries an opaque, random run ID and the
  process kind (`dashboard`, `command:work-start`,
  `hook:claude-code:SessionStart`, …), and the Agent Session Identity,
  Project, Worktree and Issue whenever they are known. Work is followed
  across processes by those shared identifiers, not by propagating trace IDs.
- **`process.start`** records Dashpot's version; the install kind from PEP
  610 `direct_url.json` (`wheel` when absent, `editable`, `directory`,
  `archive` or `vcs`); the commit of Dashpot's own source — never the
  observed Repository's — as `vcs_info.commit_id` for a VCS install and
  otherwise read from the source checkout's Git files without starting a
  process (following a linked Worktree's `gitdir:` and `commondir`, then the
  loose ref or `packed-refs`, and `unknown` for anything else, reftable
  included); whether that source has uncommitted changes, from one
  `git status`, for a dashboard only; the PID, Python version, working
  directory, and the subcommand without its arguments.
- **`process.continued`** repeats `process.start`'s fields at the top of any
  file a writer opens after its first: the next UTC day's, or one an outside
  tool moved or deleted.
- **`process.end`** records the exit status and duration. A missing
  `process.end` means a crash or a kill; an orderly exit, Ctrl-C included,
  records its status. A dashboard whose own handler raised is the one crash
  that still ends in order: Textual prints the traceback and stops the app,
  and the process exits 1 and records that status, never 0.
- **Clocks.** Wall-clock UTC timestamps order events; a monotonic clock
  times durations.

### Content policy

- **Identifiers are kept:** paths, Repository names, Issue and Pull Request
  numbers and IDs, Branch names, Agent Session Identities, harnesses,
  GraphQL operation names, Diagnostic codes, exit statuses. Branch names and
  Worktree paths carry an Issue's title slug
  ([ADR 0011](adr/0011-prepare-issue-worktrees-by-convention.md)) and paths
  carry the home directory; they are what a person debugging needs, and the
  installation guide asks a person to read a log before attaching it to a
  bug report.
- **Measurements are kept:** durations, counts, costs, rate-limit readings,
  sizes.
- **No free text, ever:** tokens, environment variables, command output,
  Issue, Pull Request and comment titles and bodies, search text, prompts,
  raw hook payloads, and error messages. An error is its code or class — a
  Diagnostic code, a `DashpotError` subclass, an errno name — never its
  message: a `GitError`'s message carries the full argument list and
  stderr, and a GitHub failure carries `gh`'s stderr.
- **Commands are program and subcommand** (`gh api graphql`), never their
  arguments.
- **Enforced by the models.** Runtime Events are closed Pydantic models on
  `PublishedModel` with `extra="forbid"`. Every string field is constrained
  to the identifier it names, so no message fits; a test walks every event
  model and fails on a string field without a bound.

## On disk

Each event is one JSON object on its own line. The envelope and the process
identity are flattened beside the event's own fields, so a line reads the
way OpenTelemetry's log data model and semantic conventions name things;
where no convention exists the field is `dashpot.*`. The models override
Dashpot's camelCase aliases with these names explicitly. Every
`dashpot.duration_seconds` is written to the microsecond, and a reader takes
any precision, so lines written before #337 still read.

| Field | Carried by | Meaning |
|---|---|---|
| `schema` | every event | File-format version, `1` (the model field is `schema_version`) |
| `time` | every event | RFC 3339 UTC timestamp, microseconds |
| `dashpot.level` | every event | `standard` or `full`: the level the event belongs to |
| `event.name` | every event | `process.start`, `process.continued`, `process.end`, `level.changed`, `event_log.write_failed`, `hook.outcome`, `command.outcome`, `cleanup.subagents_acknowledged`, `agent_session.changed`, `diagnostic.changed`, `rate_limit_pause.changed`, `unattended_pause.changed`, `span` |
| `service.instance.id` | every event | The process's run ID, 32 hex digits |
| `dashpot.process.kind` | every event | `dashboard`, `command:<words>`, `hook:<harness>[:<event>]` |
| `dashpot.agent_session.harness`, `dashpot.agent_session.id` | when known | The Agent Session Identity |
| `dashpot.project.id`, `dashpot.worktree.path`, `dashpot.issue.id` | when known | What the process works for, or the subject of a dashboard's `agent_session.changed` or `diagnostic.changed`, or of a `cleanup.subagents_acknowledged` |
| `service.version` | `process.start`, `process.continued` | Dashpot's version |
| `dashpot.install.kind` | `process.start`, `process.continued` | `wheel`, `editable`, `directory`, `archive`, `vcs`, `unknown` |
| `vcs.ref.head.revision` | `process.start`, `process.continued` | Dashpot's own source commit, or `unknown` |
| `dashpot.source.dirty` | `process.start`, `process.continued` | Uncommitted source changes (dashboard only) |
| `process.pid`, `process.runtime.version`, `process.working_directory` | `process.start`, `process.continued` | PID, Python version, working directory |
| `dashpot.subcommand` | `process.start`, `process.continued`, `command.outcome` | `work start`, `observe`, … without arguments |
| `process.exit.code`, `dashpot.duration_seconds` | `process.end` | Exit status and how long the process ran |
| `dashpot.event_level.previous`, `dashpot.event_level.current` | `level.changed` | The change of level in force |
| `error.type` | `event_log.write_failed`, a failed `span`, `hook.outcome`, `command.outcome` | The error's code when a Dashpot error carries one (a Diagnostic code such as `github-authentication`, or `command-not-found`, `command-timed-out`, `command-interrupted`), else its errno name or class |
| `dashpot.outcome.result` | `hook.outcome`, `command.outcome` | `succeeded`; `refused`, a `DashpotError` or a plan's refusals; `failed` |
| `dashpot.hook.event`, `dashpot.agent_session.state` | `hook.outcome` | The harness's hook event name (for OpenCode, the last hook event its helper wrote, else its request kind, such as `register`), and the state the session's hook record was stored with, which can differ from the one the event maps to, as for a waiting session's compaction ([ADR 0100](adr/0100-keep-a-compacted-sessions-turn-state.md)) or a `Stop` while a sub-agent works ([ADR 0016](adr/0016-hold-a-session-running-while-its-sub-agents-work.md)); `ended` when the hook ended the session, or when a sub-agent's boundary changed or removed the ended record kept for it ([ADR 0095](adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)); absent when the store kept nothing of the event, such as a stale end or a sub-agent's event with no record to join |
| `dashpot.hook.reason` | `hook.outcome` | A reason word the hook kept: for OpenCode, its acknowledgment's reason, such as an interruption's `user` or a refusal's `session-deleted` |
| `dashpot.work_store.change` | `hook.outcome` | What the hook did to its session's Agent Run: `unchanged`, `continued`, `relocated`, `ended`, or `deferred` — a managed Codex daemon's `SessionEnd` handed to a settler, whose own `hook.outcome` then reports `ended` or `unchanged` ([ADR 0086](adr/0086-orphan-runs-of-a-stopped-or-restarted-managed-codex-daemon.md)) |
| `dashpot.outcome.action` | `command.outcome` | What the command did, such as `started`, `switched`, `relocation-prepared`, `stopped`, `no-work`, `created`, `planned`, `previewed`, `removed`, `deleted`, `installed`, `reported` |
| `dashpot.outcome.refusal_count`, `dashpot.outcome.dry_run` | `command.outcome` | How many refusals a plan or Cleanup stated, or how many harnesses an `integrate` across harnesses refused, never their text; whether it was a dry run |
| `dashpot.target.path`, `dashpot.target.branch`, `dashpot.target.harness` | `command.outcome` | The Worktree, Branch or harness the command acted on |
| `dashpot.duration_seconds` | `command.outcome` | How long the command's work took |
| `dashpot.agent_session.change` | `agent_session.changed` | `appeared`, `bound`, `switched`, `unbound`, `relocated`; `orphaned` when its Agent Run is an Orphaned Agent Run, including one already orphaned when the dashboard starts, and `continued` when its session takes the run back, whether a resume continues it or `work start` replaces it with a restarted run; `ended` |
| `dashpot.issue.previous_id`, `dashpot.worktree.previous_path` | `agent_session.changed` | The Issue a session was bound to before `switched` or `unbound`; the Worktree it left when `relocated` |
| `dashpot.diagnostic.change`, `dashpot.diagnostic.severity` | `diagnostic.changed` | `appeared` or `cleared`, and the Diagnostic's severity |
| `dashpot.diagnostic.source`, `dashpot.diagnostic.code` | `diagnostic.changed` | What identifies the Diagnostic, with its Project; `uncoded` for one without a code |
| `dashpot.sub_agent.ids`, `dashpot.cleanup.outcome` | `cleanup.subagents_acknowledged` | The sub-agent IDs a person acknowledged for one Agent Session, which the envelope names with the Worktree, in a Sub-agent Override ([ADR 0112](adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md)); and what became of the Worktree: `deleted`, `already-absent`, `refused` or `unknown` |
| `dashpot.rate_limit_pause.change`, `dashpot.rate_limit_pause.limit` | `rate_limit_pause.changed` | A Rate Limit Pause `started`, `lapsed` at its due time, or `lifted`: ended early by a manual refresh's attempt that succeeded; and the limit that refused: `primary` or `secondary` |
| `dashpot.rate_limit_pause.until` | `rate_limit_pause.changed` | When the pause was due to end; a `lifted` pause ended before it |
| `dashpot.unattended_pause.change`, `dashpot.unattended_pause.signal` | `unattended_pause.changed` | An Unattended Pause `started`, or `ended` when someone attended the dashboard; and the signal that started it, on its end as on its start: `detached` (no tmux client attached) or `idle` (no input for the idle period) |
| `dashpot.span.name`, `span_id`, `parent_span_id` | `span` | What the span timed, its ID and its parent's |
| `otel.status_code` | `span` | `OK` or `ERROR` |
| `attributes` | `span` | The span's own attributes, by the span's kind, below |

A span's `attributes` object holds the fields of its kind, each only when
known:

| `dashpot.span.name` | Attributes |
|---|---|
| `command` | `process.executable.name` (the program's base name), `dashpot.command.subcommand` (`worktree list`, `api graphql DashpotQueryPage`), `process.exit.code` |
| `github.request` | `dashpot.github.api` (`graphql` or `rest`), `graphql.operation.name`, and the response's own rate-limit reading: `dashpot.github.rate_limit.cost`, `.limit`, `.remaining`, `.reset_at` |
| `refresh` | `dashpot.refresh.trigger`: `initial`, `manual`, `local` (the local Refresh Period), `github` (the GitHub-query period), `fetch`, `cleanup` |
| `observation` | `dashpot.observation.kind`, `dashpot.project.id`, `dashpot.key.outcome` |
| `query` | `dashpot.query.key` (`issues`, `pull-requests`, `identities`), `dashpot.key.outcome` |

A key's outcome is `landed`; `superseded` when a newer request's answer
replaced it; `skipped` when a timer tick found the key still running; or
`dropped` when a newer request replaced it while it waited. A skipped or
dropped key is a span of no duration under the refresh that asked for it, so
Runtime Stats counts them by trigger.

A span is written once, when it ends, stamped with the time it started. A
hook records one `hook.outcome` and a management command one
`command.outcome` before its `process.end`, and each names the Agent
Session, Issue or Worktree it learned it works for on that event and every
later one. A management command also names the Project of the configured
checkout whose Event Log it writes to, and `init` the Project it declared;
a command writing to the machine-local fallback names none. A dashboard
records `agent_session.changed` and `diagnostic.changed` only when what it
observes changes, never for a refresh that changes nothing; each names its
subject — the session's harness, ID, Project, Worktree and Issue, or the
Diagnostic's Project — in the identity fields, beside the dashboard's own
run ID and kind, so `dashpot events --session` or `--project` finds it. The
Diagnostics box and the `diagnostic.changed` events read one list of
Diagnostics, so the log records every Diagnostic the box shows,
`event-log-large` included. A dashboard over one Project names that
Project on its own events once it is observed. A `rate_limit_pause.changed` is
recorded by the request that saw the change: the refused request records
`started`, the first request admitted after the pause's due time records
`lapsed`, and a manual refresh's attempt that succeeded before the due
time records `lifted`. An `unattended_pause.changed` is recorded by the
dashboard when a GitHub tick or tmux probe starts the pause, and when input,
focus or a reattached client ends it. A runtime value that does not
fit its field, such as a Branch name Git would refuse, is left out of the
event rather than failing the work. The reader is tolerant: it ignores fields a newer Dashpot added and skips a line
it cannot read, whose `schema` is newer, or whose `event.name` it does not
know. A change an older reader would misread, rather than skip, bumps
`schema`; a new value of an existing field does not, since an older reader
skips that line as one it cannot read. `dashpot events --json` is the published interface under
[ADR 0034](adr/0034-publish-an-alpha-with-patch-compatible-interfaces.md);
the file format is not. It prints JSON Lines, one event per line, and each
event keeps the field names above, with an absent field as `null`, rather
than the camelCase of the other `--json` documents, so an event reads the
same in a file and in the command's output.

## Levels

| Level | Written | Default |
|---|---|---|
| `off` | nothing; the dashboard's in-memory buffer still fills | |
| `standard` | `process.start` and `process.end`; hook and management-command outcomes; Agent Session and Agent Run changes; Diagnostics appearing and clearing; Rate Limit Pauses starting, lapsing and being lifted; Unattended Pauses starting and ending; level changes; every GitHub request span; every failed span | ✔ |
| `full` | plus every refresh, observation, query and command span | for development |

- **Each event carries its level**, so a reader can filter by it.
- **Counting rule.** Counting from the Event Log's files, count only what
  is always written at the level in force; Runtime Stats counts everything
  in the dashboard's buffer, which keeps every event whatever the level. At
  `standard`, failed local spans are debugging examples and are never
  counted; GitHub request spans are always written, so points and
  requests are always countable. `level.changed` marks where the level in
  force changed, and is written at whichever of the two levels records more.
- **Choosing the level.** The `event_level` setting in `config.toml`
  ([ADR 0052](adr/0052-read-machine-local-settings-as-toml.md)), overridden
  by `DASHPOT_EVENT_LEVEL`, and a toggle in the Runtime screen for a
  running dashboard that lasts for that run and never rewrites
  `config.toml`. There is no command-line flag. A settings file that fails
  to load leaves `standard`, silently in hooks and commands.
- **Volume.** A GitHub request span is about 680 bytes on disk, a command
  or observation span about 510, a query span 480 and a refresh span 420
  ([measurements](#measurements)). Most of a line is its envelope and its
  field names, about 300 bytes of envelope on a dashboard's span: the price
  of a self-describing wide event, which rounding durations trims by only 1
  to 2.5%. At `standard` a dashboard writes about 4 to 5.5 MB a day, almost
  all GitHub request spans, and stops with its GitHub requests while an
  Unattended Pause holds. Each hook run adds about 1.6 KB to the shared
  file, its `process.start`, `hook.outcome` and `process.end` together. At
  `full`, about 100 MB a day on Dashpot's own Repository with 16 Worktrees
  at the 15-second local period, four fifths of it command spans, growing
  with Worktrees and Branches.

## Where the Event Log lives

- **Per checkout** ([ADR 0003](adr/0003-prefer-project-local-dashpot-state.md)):
  a process writes to `.dashpot/state/events/` in the configured checkout —
  the Worktree whose root carries `.dashpot/config.json` — containing its
  working directory, found by walking up to the nearest plausible `.git`
  without starting Git: a directory holding `HEAD`, or a `gitdir:` file. The
  check is shallower than Git's, but the search follows Git's: an empty
  `.git` directory claims nothing
  ([#359](https://github.com/ned2/dashpot/issues/359)), a malformed or
  unreadable `.git` file ends the search, and the search stops below any
  directory that `GIT_CEILING_DIRECTORIES` names. It is the rule the hook
  publisher's `route_record_store` applies to hook records, and a hook
  routes its Event Log from the payload's working directory the same way. A
  one-shot command writes to the checkout it runs in; a dashboard to the
  checkout it was started in, including events about other Projects in its
  Workspace.
- **Fallback:** `$XDG_STATE_HOME/dashpot/events/` when that variable is an
  absolute path (a relative one is ignored, as the XDG specification
  requires), else `~/.local/state/dashpot/events/`, or
  `~/Library/Application Support/dashpot/events/` on macOS — beside the
  hook records' `runs/`. With no home directory either, there is nowhere to
  write: a hook or command outside every configured checkout records
  nothing, and a dashboard keeps only its recent events in memory. That
  includes `dashpot events remove` refusing for that very reason, since a
  command keeps no events in memory and its outcome is discarded.
  [#338](https://github.com/ned2/dashpot/issues/338) accepts the gap: by
  construction there is nowhere to keep the event, and the refusal's
  message on stderr says why.
- **The directory ignores itself.** `.dashpot/state/` is created through
  `ensure_state_directory`, which writes its `.gitignore` of `*`
  ([#312](https://github.com/ned2/dashpot/issues/312)); the fallback gets
  none.
- **Removing a Worktree removes its Event Log**, including the hook outcomes
  that explain its sessions. That is the cleanup the per-checkout location
  exists for.
- **Files split by UTC date.** Hooks and one-shot commands share
  `events-YYYY-MM-DD.jsonl`; each dashboard run writes
  `dashboard-<run>-YYYY-MM-DD.jsonl`.
- **One write per line.** Each event is one JSON line of at most 8 KiB,
  written with one `os.write` on an `O_APPEND` descriptor under a lock the
  writer's threads share. That keeps concurrent writers' lines whole on a
  local filesystem; it is not guaranteed on NFS. A longer event is dropped
  rather than split.
- **Never deleted by Dashpot on its own.** `dashpot events remove --before
  DATE` deletes this checkout's files dated before a day, never today's or
  later, and only on explicit invocation. An outside tool may move or delete
  past files — the [installation guide](installation.md#remove-old-event-log-files)
  gives `cron`, systemd-timer and `logrotate` examples — and a writer
  notices a moved or deleted current file by its inode and opens a new one.
  An `event-log-large` Diagnostic warns without acting when the dashboard's
  checkout's Event Log passes 200 MB; the dashboard measures it off the
  event loop when it starts and on each local or requested refresh. The
  threshold stays at 200 MB, and `full` keeps every span, by #337's
  decision. At `standard` one dashboard and 1,500 hook runs a day write 6.5
  to 8 MB, so a checkout reaches it in about four weeks, and sooner with
  several dashboards open, which is when old files are worth removing. A
  dashboard left at `full` reaches it in about two days, which suits `full`
  as a short-lived level for developing Dashpot: the warning is the intended
  prompt to remove old files or return to `standard`. A larger threshold
  would keep a week at `full` quiet but would rarely warn at `standard`, and
  writing fewer command spans at `full` would lose the per-command trail
  `full` exists to keep.
- **Writing never fails the work.** A failed write is dropped. The dashboard
  records the failure as an `event_log.write_failed` event in its in-memory
  buffer, where Runtime Stats counts it, and the first raises an
  `event-log-unavailable` Diagnostic. Hook and command processes stay silent.
- **Writing is a mutation observation now makes**, amending
  [ADR 0008](adr/0008-let-management-commands-mutate-on-explicit-invocation.md)'s
  list of observation's writes and ADR 0003's runtime-state consequence.

## Implementation

- **No logging library.** Events are closed Pydantic models rendered to one
  line, so a small appender in Dashpot's own code writes them: no new
  dependency, no process-global configuration, and no import cost in hooks
  (structlog alone imports in about 35 ms). One `EventLog` per process holds
  its destination, level and identity, so tests and several apps in one
  process never share one.
- **The span helper mirrors OpenTelemetry's API** — `start_span` returning a
  span its owner ends, and `start_as_current_span` for synchronous work — so
  a later exporter would change one module. The current span lives in a
  context variable.
- **Threads keep their own context.** Each executor thread adopts its
  command registry through a context variable set by the pool's initializer;
  that is how a dashboard's exit interrupts its commands
  ([ADR 0049](adr/0049-interrupt-observation-commands-at-dashboard-exit.md)).
  So `off_loop` sets only the current-span variable inside the thread's own
  context, and never runs the operation in a copy of the event loop's
  context.
- **Forwarding.** While `textual console` is attached, every recorded line
  also goes to Textual's `log`.
- **Explicit destinations.** `DashpotApp` takes an `EventLog`, and the
  command line and hook entry points an Event Log destination; the working
  directory only supplies the default. An autouse fixture sets
  `DASHPOT_EVENT_LEVEL=off` for every test, which reaches the processes a
  test starts too, and Event Log tests pass their own directory.
- **Instrumentation seams.** [#314](https://github.com/ned2/dashpot/issues/314)
  times these as spans. Commands: `run_command`, the direct `ps` and
  `sysctl` calls in `sessions/processes.py` that bypass it, and the
  Worktree opener's launch. A command exiting non-zero fails its span only
  when its caller raises an error for that exit: `Git.text`, `Git.records`
  and `merge-tree` (for any exit but a conflict's 1) declare one as a
  `GitError`, `worktree add` as a `WorktreeCreateError`, and the opener as
  a `WorktreeLaunchError`. A caller that reports the exit as an outcome
  instead — a Remote Fetch's failed remote, a Cleanup's refusal — leaves
  the span successful, with the exit status recorded. So does a `gh`
  command whose failure `GitHubGateway` reads from the response body rather
  than the exit: the failure is recorded on its `github.request` span, by
  code. GitHub requests: each `GitHubGateway` request,
  including each request of a `graphql_many` fan-out, with its own
  rate-limit reading, and its `gh` command a child span. Refreshes: the
  dashboard's first load, `r`, the two Refresh Period timers, a Remote Fetch
  and a Cleanup each start a refresh span, and every observation and query
  key it asks for is a child span that travels with the work — the ticket
  in flight, the pending rerun, the queued request, and a follow-up key a
  landed observation asks for. A query no refresh asked for — a page a
  person moved to, the Issues a selection resolves — is a root span, as is
  a command or GitHub request outside any span. Commands and hooks record
  the commands and GitHub requests they run into their own Event Log. A span
  still open when its process exits is never written.
  The standalone events come from the hook publisher and management
  commands, Agent Session and Agent Run changes, and Diagnostic
  transitions. A management command wraps its work in
  `record_command_outcome` and fills the note it is handed, as `dashpot
  events remove` does, so a new one records its outcome the same way.
- **Linux and macOS only**, as the package classifiers say.

## Reading

- **The Runtime screen**
  ([ADR 0098](adr/0098-show-runtime-events-and-stats-as-tabs-of-one-temporary-screen.md)),
  a full-screen temporary screen with two tabs, Events and Stats, opened from
  a Peer Screen by `e` or `s` or by the command palette's Runtime Events and
  Runtime Stats, and closed by `Escape` alone. Both tabs read the dashboard's
  in-memory buffer, which keeps the last hour's events at full detail
  whatever the level in force, and at most 10,000 of them. A shared header
  names the level, whose events these are, how far back the buffer reaches —
  saying so when it filled before the hour was up — and how many it holds.
  The screen redraws about once a second while open and sends no request of
  its own. `l` moves the level through `off`, `standard` and `full` for the
  rest of the run from either tab.
- **Runtime Events** ([#451](https://github.com/ned2/dashpot/issues/451)),
  the Events tab: the buffered events, newest last, by local time, level,
  kind (a span by its name), Project, outcome, duration and a one-line
  summary per kind, with every field of the selected event, its stored UTC
  time included, beside the table, or below it under 90 columns. Rows keep
  the buffer's order, so a span is listed where it ended but timed from
  when it started. Show (every buffered event, those the level in force
  records, or `standard` only), Kind and Errors only filters last until the
  dashboard exits. Errors only keeps failed spans and dropped writes; a
  non-zero exit the caller read as an answer shows its code but is no
  error. The table follows the newest event until a person moves back
  through it; `End` follows again.
- **Runtime Stats** ([#315](https://github.com/ned2/dashpot/issues/315)), the
  Stats tab, aggregating the buffer when it draws. Its sections:
  - **GitHub allowance:** `remaining`, `limit` and `resetAt` from the latest
    reading the Query Sources share, and the points the rest of the account
    spent: within each rate limit window, the change in points used between
    the requests' readings less the cost of this dashboard's own requests
    after the first. While a Rate Limit Pause holds GitHub queries, the
    section leads with when it ends and which limit refused
    ([ADR 0065](adr/0065-pause-github-queries-after-a-rate-limit-refusal.md)).
    While an Unattended Pause holds GitHub refreshes, it leads with when
    that started and what showed nobody attending, after any Rate Limit
    Pause
    ([ADR 0068](adr/0068-pause-github-queries-while-the-dashboard-is-unattended.md)).
  - **GitHub requests:** requests, points and failures by GraphQL operation
    (or by API for a request that names none), for the latest ended refresh
    that sent any and for the window.
  - **Refreshes:** by trigger, how many, their typical and worst duration,
    and the keys they skipped (busy) or dropped (replaced while waiting).
  - **Refresh keys:** each observation and query key's runs, typical and
    worst duration, skips, drops and failures, whether a refresh or a
    person asked for it.
  - **Commands:** by program, count, typical and worst duration, and
    failures.
  - **This process:** version, commit and uncommitted changes from
    `process.start`, uptime, memory, the Event Log's path, size, level and
    dropped writes. Memory is the current resident set
    size from `/proc/self/statm` on Linux; elsewhere it is the peak
    `getrusage` reports, labelled as the peak, so drawing the screen starts
    no process.
- **`dashpot events`** ([#316](https://github.com/ned2/dashpot/issues/316)):
  `--session`, `--issue`, `--project`, `--since` and `--level` filters and
  `--json`, merging every Worktree of the Repository and the machine-local
  fallback by time and leaving out the reader's own run. A filter matches
  its field wherever an event carries it, so a field a later event adds
  filters too. Reading is tolerant: an unreadable line or file is reported
  on standard error, with or without `--json`, and the rest is still
  printed. `--json` prints JSON Lines, one event per line
  ([ADR 0099](adr/0099-print-runtime-events-as-json-lines.md),
  [#450](https://github.com/ned2/dashpot/issues/450)). Only
  the Event Log's own `.jsonl` names are read, so a compressed or renamed
  file is invisible. `dashpot work show` lists its Agent Session's recent
  outcomes — at most 20 from the last 7 days, failures included — reading
  back one day at a time only as far as it needs.

## Measurements

- **Local observation load** (2026-09-26, `strace` of a dashboard on
  Dashpot's own Repository with two Worktrees): about 33 commands per
  15-second refresh, roughly 132 a minute
  ([#317](https://github.com/ned2/dashpot/issues/317) tracks the cost).
- **Span volume** (2026-09-27, #314, a headless dashboard on Dashpot's own
  Repository with ten Worktrees at `full` for 186 seconds, default periods):
  950 lines, 436 KB. 23 GitHub request spans averaged 619 bytes, 858
  command spans 456 (about 66 commands per local refresh), 39 observation
  spans 462, 12 query spans 423 and 16 refresh spans 363. That is about
  200 MB a day at `full`; at `standard` the GitHub request spans alone are
  about 14 KB in the same time — 23 requests, from the first load and three
  GitHub refreshes — or about 4.5 MB a day at 5 requests a minute.
  Superseded by the next measurement.
- **Span volume** (2026-10-04, #337, `scripts/experiments/event-volume-337.py`:
  the real dashboard, headless, on Dashpot's own Repository with 16
  Worktrees at `full` for 586 seconds, default periods, durations written to
  the microsecond, the Event Log in a temporary directory): 1,417 lines,
  730 KB. 1,150 command spans averaged 511 bytes (about 29 commands per
  local refresh after #317), 120 observation spans 520, 56 GitHub request
  spans 683, 49 refresh spans 421 and 33 query spans 480. Leaving out the
  first 90 seconds, that is about 97 MB a day at `full` and 5.2 MB a day at
  `standard`. Three of this machine's own dashboards, run for an hour or
  more each that day, wrote 155 to 232 KB of `standard` lines an hour, about
  3.7 to 5.6 MB a day, almost all GitHub request spans averaging 750 bytes:
  a GraphQL request's span carries four rate-limit fields and is about 750
  bytes, a REST request's about 440.
- **Duration rounding** (2026-10-04, #337, 2,781 lines written before it):
  writing `dashpot.duration_seconds` to the microsecond saves about 10
  bytes a line, 1.3% of a GitHub request span and 2.5% of a `process.end`.
- **GitHub spend** (2026-09-26, process sampling, recorded in #308): 14
  requests per 15 seconds then; about 5 per 60-second GitHub refresh after
  #303, #305 and #310.
- **Import costs** that shaped the implementation: `importlib.metadata`
  about 21 ms and structlog about 35 ms, so neither is imported by a hook.
- **Hook process cost** (2026-09-27, #313, Linux, Python 3.14): a Claude Code
  `Stop` hook in a configured checkout, 60 interleaved runs of each variant
  against the same interpreter running the base commit's source. The median
  hook process took 175.9 ms before and 187.4 ms with the Event Log at the
  default level, reading `config.toml` — 11.5 ms added, within the 30 ms
  budget. With `DASHPOT_EVENT_LEVEL=off` it added 12.3 ms, and at `full`
  14.3 ms; a second run of 40 after review fixes measured 14.7 ms added at
  every level. The cost is almost all import: building the Runtime Event
  models takes about 7 ms of it, and the Event Log modules with the settings
  loader about 12 ms cumulatively, part of which the hook already imported.
  Reading the version, install kind and source commit takes about 0.5 ms.
- **Standalone event volume** (2026-09-27, #314, real paths from this
  machine): a hook's `hook.outcome` is about 575 bytes beside its 728-byte
  `process.start` and 498-byte `process.end`, and takes about 0.07 ms to
  record (0.17 ms for the first). At 1,500 hook runs a day, a busy day of
  several sessions, that adds about 0.9 MB. A `command.outcome` is about
  840 bytes with a Worktree path and Branch, an `agent_session.changed`
  about 560 and a `diagnostic.changed` about 420; they follow commands a
  person runs and changes a dashboard observes, so they are a small part of
  a day's `standard` volume, which GitHub request spans dominate.
- **Hook volume** (2026-10-04, #337, this checkout's shared file over four
  and a half hours of several Claude Code sessions): 759 hook and command
  processes wrote 1.2 MB. A hook run's `process.start` averaged 615 bytes,
  its `hook.outcome` 533 and its `process.end` 438, about 1.6 KB a run
  together, so 1,500 hook runs a day add about 2.4 MB, of which the
  `hook.outcome` lines are 0.8 MB.

## Sources

- Canonical log lines and wide events:
  <https://stripe.com/blog/canonical-log-lines>,
  <https://www.honeycomb.io/blog/structured-events-basis-observability>
- Aggregating at read time:
  <https://charity.wtf/2024/08/07/is-it-time-to-version-observability-signs-point-to-yes/>
- Exemplars: <https://opentelemetry.io/docs/specs/otel/metrics/data-model/>
- OpenTelemetry semantic conventions and log data model:
  <https://opentelemetry.io/docs/specs/semconv/>,
  <https://opentelemetry.io/docs/specs/otel/logs/data-model/>
- PEP 610, recording the direct URL origin of installed distributions:
  <https://peps.python.org/pep-0610/>
