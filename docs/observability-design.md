---
status: living
date: 2026-09-27
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
  a running total, not even the Runtime Stats screen, which aggregates an
  in-memory buffer of recent events.

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
  records its status.
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
Dashpot's camelCase aliases with these names explicitly.

| Field | Carried by | Meaning |
|---|---|---|
| `schema` | every event | File-format version, `1` (the model field is `schema_version`) |
| `time` | every event | RFC 3339 UTC timestamp, microseconds |
| `dashpot.level` | every event | `standard` or `full`: the level the event belongs to |
| `event.name` | every event | `process.start`, `process.continued`, `process.end`, `level.changed`, `event_log.write_failed`, `hook.outcome`, `command.outcome`, `agent_session.changed`, `diagnostic.changed`, `span` |
| `service.instance.id` | every event | The process's run ID, 32 hex digits |
| `dashpot.process.kind` | every event | `dashboard`, `command:<words>`, `hook:<harness>[:<event>]` |
| `dashpot.agent_session.harness`, `dashpot.agent_session.id` | when known | The Agent Session Identity |
| `dashpot.project.id`, `dashpot.worktree.path`, `dashpot.issue.id` | when known | What the process works for, or the subject of a dashboard's `agent_session.changed` or `diagnostic.changed` |
| `service.version` | `process.start`, `process.continued` | Dashpot's version |
| `dashpot.install.kind` | `process.start`, `process.continued` | `wheel`, `editable`, `directory`, `archive`, `vcs`, `unknown` |
| `vcs.ref.head.revision` | `process.start`, `process.continued` | Dashpot's own source commit, or `unknown` |
| `dashpot.source.dirty` | `process.start`, `process.continued` | Uncommitted source changes (dashboard only) |
| `process.pid`, `process.runtime.version`, `process.working_directory` | `process.start`, `process.continued` | PID, Python version, working directory |
| `dashpot.subcommand` | `process.start`, `process.continued`, `command.outcome` | `work start`, `observe`, … without arguments |
| `process.exit.code`, `dashpot.duration_seconds` | `process.end` | Exit status and how long the process ran |
| `dashpot.event_level.previous`, `dashpot.event_level.current` | `level.changed` | The change of level in force |
| `error.type` | `event_log.write_failed`, a failed `span`, `hook.outcome`, `command.outcome` | errno name or error class |
| `dashpot.outcome.result` | `hook.outcome`, `command.outcome` | `succeeded`; `refused`, a `DashpotError` or a plan's refusals; `failed` |
| `dashpot.hook.event`, `dashpot.agent_session.state` | `hook.outcome` | The harness's hook event name, and the state it wrote to the session's hook record |
| `dashpot.work_store.change` | `hook.outcome` | What the hook did to its session's Agent Run: `unchanged`, `continued`, `relocated`, `ended` |
| `dashpot.outcome.action` | `command.outcome` | What the command did, such as `started`, `switched`, `relocation-prepared`, `stopped`, `no-work`, `created`, `planned`, `previewed`, `removed`, `deleted`, `installed`, `reported` |
| `dashpot.outcome.refusal_count`, `dashpot.outcome.dry_run` | `command.outcome` | How many refusals a plan or Cleanup stated, never their text; whether it was a dry run |
| `dashpot.target.path`, `dashpot.target.branch`, `dashpot.target.harness` | `command.outcome` | The Worktree, Branch or harness the command acted on |
| `dashpot.duration_seconds` | `command.outcome` | How long the command's work took |
| `dashpot.agent_session.change` | `agent_session.changed` | `appeared`, `bound`, `switched`, `unbound`, `relocated`, `ended` |
| `dashpot.issue.previous_id`, `dashpot.worktree.previous_path` | `agent_session.changed` | The Issue a session was bound to before `switched` or `unbound`; the Worktree it left when `relocated` |
| `dashpot.diagnostic.change`, `dashpot.diagnostic.severity` | `diagnostic.changed` | `appeared` or `cleared`, and the Diagnostic's severity |
| `dashpot.diagnostic.source`, `dashpot.diagnostic.code` | `diagnostic.changed` | What identifies the Diagnostic, with its Project; `uncoded` for one without a code |
| `dashpot.span.name`, `span_id`, `parent_span_id` | `span` | What the span timed, its ID and its parent's |
| `otel.status_code` | `span` | `OK` or `ERROR` |
| `attributes` | `span` | The span's own attributes, such as `process.executable.name`, `dashpot.command.subcommand` and `process.exit.code` for a command |

A span is written once, when it ends, stamped with the time it started. A
hook records one `hook.outcome` and a management command one
`command.outcome` before its `process.end`, and each names the Agent
Session, Issue or Worktree it learned it works for on that event and every
later one. A dashboard records `agent_session.changed` and
`diagnostic.changed` only when what it observes changes, never for a refresh
that changes nothing; each names its subject — the session's harness, ID,
Project, Worktree and Issue, or the Diagnostic's Project — in the identity
fields, beside the dashboard's own run ID and kind, so `dashpot events
--session` or `--project` finds it. A dashboard over one Project names that
Project on its own events once it is observed. A runtime value that does not
fit its field, such as a Branch name Git would refuse, is left out of the
event rather than failing the work. The reader is tolerant: it ignores fields a newer Dashpot added and skips a line
it cannot read, whose `schema` is newer, or whose `event.name` it does not
know. A change a tolerant reader could not read bumps `schema`. `dashpot
events --json` ([#316](https://github.com/ned2/dashpot/issues/316)) is the
published interface under
[ADR 0034](adr/0034-publish-an-alpha-with-patch-compatible-interfaces.md);
the file format is not.

## Levels

| Level | Written | Default |
|---|---|---|
| `off` | nothing; the dashboard's in-memory buffer still fills | |
| `standard` | `process.start` and `process.end`; hook and management-command outcomes; Agent Session and Agent Run changes; Diagnostics appearing and clearing; level changes; every GitHub request span; every failed span | ✔ |
| `full` | plus every local observation and command span | for development |

- **Each event carries its level**, so a reader can filter by it.
- **Counting rule.** Count only what is always written at the level in
  force. At `standard`, failed local spans are debugging examples and are
  never counted; GitHub request spans are always written, so points and
  requests are always countable. `level.changed` marks where the level in
  force changed, and is written at whichever of the two levels records more.
- **Choosing the level.** The `event_level` setting in `config.toml`
  ([ADR 0052](adr/0052-read-machine-local-settings-as-toml.md)), overridden
  by `DASHPOT_EVENT_LEVEL`, and a toggle in the Runtime Stats screen for a
  running dashboard that lasts for that run and never rewrites
  `config.toml`. There is no command-line flag. A settings file that fails
  to load leaves `standard`, silently in hooks and commands.
- **Volume.** An event is about 240 bytes. At `full`, about 45 MB a day on
  Dashpot's own Repository at the 15-second local period, growing with
  Branches. At `standard` the bulk is GitHub request spans: about 20 MB a day
  at #308's measured 14 requests per 15 seconds, and about 2 MB a day at the
  roughly 5 requests per 60-second GitHub refresh the dashboard sends since
  #303, #305 and #310 landed.

## Where the Event Log lives

- **Per checkout** ([ADR 0003](adr/0003-prefer-project-local-dashpot-state.md)):
  a process writes to `.dashpot/state/events/` in the configured checkout —
  the Worktree whose root carries `.dashpot/config.json` — containing its
  working directory, found by walking up to the nearest `.git` entry without
  starting Git. It is the rule the hook publisher's `route_record_store`
  applies to hook records, and a hook routes its Event Log from the
  payload's working directory the same way. A one-shot command writes to the
  checkout it runs in; a dashboard to the checkout it was started in,
  including events about other Projects in its Workspace.
- **Fallback:** `$XDG_STATE_HOME/dashpot/events/`, else
  `~/.local/state/dashpot/events/`, or
  `~/Library/Application Support/dashpot/events/` on macOS — beside the
  hook records' `runs/`.
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
- **Never deleted by Dashpot.** An outside tool may move or delete past
  files — the installation guide gives a `cron` example — and a writer
  notices a moved or deleted current file by its inode and opens a new one.
  An `event-log-large` Diagnostic warns without acting past 200 MB, and
  `dashpot events remove` deletes only on explicit invocation.
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
- **Instrumentation seams**, for
  [#314](https://github.com/ned2/dashpot/issues/314): `run_command`, plus the
  direct `ps` and `sysctl` calls in `sessions/processes.py` that bypass it;
  `GitHubGateway`; the observation and query runners, with the 15-second
  local and the GitHub-query refresh timers told apart; the hook publisher
  and management commands; Agent Session and Agent Run changes; Diagnostic
  transitions. A management command wraps its work in
  `record_command_outcome` and fills the note it is handed, so a new one
  (such as `dashpot events remove`) records its outcome the same way.
- **Linux and macOS only**, as the package classifiers say.

## Reading

- **Runtime Stats** ([#315](https://github.com/ned2/dashpot/issues/315)), a
  screen on `s` laid out like the Legend screen: GitHub allowance (points
  and requests by operation for the last refresh and the last hour,
  `remaining` and `resetAt`, spend by the rest of the account, pause state);
  refresh health (durations, and refreshes skipped or dropped, by timer);
  commands (by program: count, typical and worst time, failures); and this
  process (version, commit, uncommitted changes, uptime, memory, the Event
  Log's path, size, level and write errors, and the level toggle).
- **`dashpot events`** ([#316](https://github.com/ned2/dashpot/issues/316)):
  `--session`, `--issue`, `--project`, `--since` and `--level` filters and
  `--json`, merging every Worktree of the Repository and the machine-local
  fallback. `dashpot work show` lists its session's recent events, bounded in
  count and age.

## Measurements

- **Local observation load** (2026-09-26, `strace` of a dashboard on
  Dashpot's own Repository with two Worktrees): about 33 commands per
  15-second refresh, roughly 132 a minute
  ([#317](https://github.com/ned2/dashpot/issues/317) tracks the cost).
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
