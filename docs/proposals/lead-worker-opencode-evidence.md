---
status: research
date: 2026-10-05
---

# OpenCode evidence for Lead and Worker mechanisms

Whether a Lead's Workers can run as root sessions on OpenCode's shared
service rather than as child Sub-agents, and what that costs. This is
evidence for the [Lead and Worker design](lead-worker-design.md) and its
[analysis](lead-worker-design-analysis.md), made for
[Issue #479](https://github.com/ned2/dashpot/issues/479). Its sibling notes
cover [Claude Code](lead-worker-claude-code-evidence.md) and
[Codex](lead-worker-codex-evidence.md).

Each claim carries its evidence:

- **measured**: by a Dashpot experiment at 2.0.22, linked; **measured
  (#479)** names [the #479 experiment](#the-479-experiment);
- **documented**: in OpenCode's documentation or a Dashpot experiment that
  cites the source;
- **source**: read in the [`v2.0.22`](https://github.com/anomalyco/opencode/tree/v2.0.22)
  source (commit `527f0b93`) only, with paths relative to that tag;
- **inference**: reasoning that no source states.

A second read of the source checked every source claim here. The #479
experiment then ran the dispatch, the notices, a Worker's asks, the finish,
interrupt, deletion, a Lead's move, Option B, a service restart and a
standalone Lead against a pinned 2.0.22 service
([runner](../../scripts/experiments/opencode-479/),
[trace](../spikes/measurements/issue-479-opencode-trace.jsonl)). The
[root-session Workers spike](../spikes/root-session-workers-spike.md)
reports it beside the other harnesses.

## Conclusion

Root-session Workers are viable on the shared service, and for Dashpot they
are better than child Workers. Each Worker becomes an ordinary observed root
Agent Session, with its own location, events, `work start` and Issue
Binding (measured (#479)). Dashpot's plugin needs no change to observe them:
it already treats any session without a `parentID` as a root
([`opencode.js`](../../src/dashpot/plugins/opencode.js)).

The cost is coordination. OpenCode's built-in completion notice, its durable
job recovery and its parent-only resume all belong to child sessions, so the
skill has to supply a notice, a declaration of the Lead, and a finish step.
What a root session keeps is its recorded outcome, which a Lead can read.

Three gaps were measured (#479):

- **Restart recovery.** A restarted service resumes the turns it cut off,
  but Dashpot's plugin never sees those turns start, so each Worker's Agent
  Run stays orphaned and its `work start` from the resumed turn is refused.
  Only a fresh prompt rebinds it.
- **Asks at a stop.** A pending ask is cancelled when the service stops, and
  the resumed turn goes on without asking again.
- **Reviewers.** While a Worker's reviewer Sub-agent runs, ADR 0066's
  Repository-wide `sub-agent` blocker comes back.

## Affordances beyond the existing experiments

- **`opencode api`.** Source (`packages/cli/src/commands/handlers/api.ts`):
  a CLI command that calls a service by `METHOD /path` or operationId, with
  `-d` and `-H`, and `--param` with an operationId only. The model never
  reads the registration or the password. Dashpot's documents and code don't
  mention it yet. Which server it reaches is decided in
  `packages/cli/src/services/server-connection.ts` (source):
  - `--server <url>` calls that URL, authenticating with `OPENCODE_PASSWORD`;
  - `--standalone` always starts a new private server, never the Lead's;
  - if the service configuration disables the service, it silently starts a
    private server instead, which exits with the command. A session it
    dispatched is not destroyed, since standalone servers share the session
    database: its execution is interrupted with the claim kept, and it runs
    only when a shared service next starts;
  - otherwise it uses the registered shared service, whatever its version,
    and **starts one if none is running**. The service it starts carries the
    calling shell's whole environment and runs in `$HOME`. Measured (#479):
    with no registration, `opencode api GET /api/info` started the service
    in 166 ms;
  - a registered service that answers 404 on `/api/info`, the earlier v2
    health protocol, is replaced: `opencode api` stops it and starts a new
    one.

  Measured (#479): every call from the Lead's and the Workers' shells
  reached the fixture's service through its `XDG_STATE_HOME`. `--server` was
  not exercised. From a standalone Lead's shell, `opencode api` reached the
  shared service, never the Lead's private server.
- **`POST /api/session`.** Source (`packages/protocol/src/groups/session.ts`,
  `packages/server/src/handlers/session.ts`): every field is optional:
  `id`, `parentID`, `title`, `agent`, `model`, `location: {directory}`,
  `metadata` and `permissions`.
  - With a `parentID`, the session is a child at its parent's location, and a
    given `location` is silently dropped. A child inherits `permissions` as
    well as `metadata`.
  - With neither, the root is placed at the **service's** working directory,
    which the [v2 experiment](../spikes/opencode-v2-spike.md) found to be
    `$HOME`. A Worker must always be given its `location`.
  - An `id` must start with `ses`. Creating with an existing id returns that
    session unchanged, whatever `location` is given.
  - Measured (#479): a root made with `location` and `metadata` has a null
    `parentID`, sits at that location and returns its metadata from `GET`.
    Creation took 54 ms. Until its first prompt it reads waiting
    ([ADR 0106](../adr/0106-record-a-session-waiting-after-a-session-start-that-begins-no-turn.md)).
- **Session `metadata`.** Source (`packages/schema/src/session-metadata.ts`,
  `session-event.ts`): "host-supplied session annotations, durable and
  opaque to core", carried in `session.created`, with a
  `session.metadata.updated` event. Measured (#479): a plugin receives it in
  `session.created`. Three caveats for a Lead link:
  - children inherit their parent's metadata unless their creator supplies
    its own. Measured (#479): a Worker's reviewer carries the Worker's
    `dashpot.lead` and `dashpot.issue`;
  - **a fork is a root with copied metadata.** Measured (#479):
    `POST /api/session/:id/fork` gives a session with a null `parentID`, a
    `fork: {sessionID, boundary}` field, the source's location and agent,
    and a copy of its metadata. Dashpot's plugin treats a fork as a root. A
    reader of a Lead link must check that both `parentID` and `fork` are
    absent;
  - any client can change it with `PATCH /api/session/:id`, so it is a
    declaration, not proof of who made the session. A `PATCH` replaces the
    whole metadata object (source, `packages/core/src/session/projector.ts`),
    so a writer of another key erases `dashpot.lead`.
- **`POST /api/session/:id/synthetic`.** Source: "durably admit synthetic
  session input and schedule execution unless resume is false", with
  `{id?, text, description?, metadata?, delivery?: "steer" | "queue", resume?}`.
  `delivery` defaults to `steer`. OpenCode's own `<subagent>` notice uses
  the same core operation in process
  (`packages/core/src/session/subagent-completion.ts`), and passes a stable
  `id` so a retry is not delivered twice. The `id` is a message id, so it
  must start with `msg_`. Unlike `opencode run --session`, it attaches no
  client that rejects asks. Measured (#479):
  - to an idle Lead it starts a new execution at once, with the notice as a
    fresh `user` message;
  - to a busy Lead, `steer` is delivered at the next step and `queue` after
    the turn's last planned step, both within the same execution;
  - the Lead's own pending ask stays pending; the notice waits in the inbox
    until the ask is answered;
  - a repeated `id` answers 200 with the first message, and the model never
    sees the duplicate, but it **starts an empty execution** of the Lead,
    which makes no model request. By source, a repeat with a different type
    or delivery answers 409.
- **`POST /api/session/:id/prompt`.** Source: accepts `id`, `skills`,
  `files`, `agents`, `delivery` and `resume`. `skills` is a list of objects,
  `[{"id": "dashpot-issue-work"}]` (`packages/schema/src/prompt-input.ts`).
  Measured (#479): admission took 133 ms, and a prompt from any process
  steers a Worker, not only from a parent.
- **Waiting and interrupting.** Source: `POST
  /api/experimental/session/:id/wait` waits until the agent loop is idle,
  and returns at once if it is already idle. Measured (#479): through
  `opencode api` a wait held for 330 s and returned once the awaited ask was
  answered; there is no five-minute cut. `POST …/interrupt` targets one
  session, and stops only an execution "owned by this OpenCode process",
  so it cannot reach a session executing in a standalone server.
  `GET /api/session/active` lists only the foreground executions the
  service owns, which makes it a weak completion check.
- **Events.** Measured (#479): `opencode api GET /api/event` printed nothing
  for 390 s, because `opencode api` buffers the whole body. A Lead cannot
  stream events through it. By the same buffering, the per-session log at
  `GET /api/experimental/session/:id/log?follow=true` would not stream
  through it either (inference).
- **Permission asks.** Source (`packages/protocol/src/groups/permission.ts`):
  `GET /api/permission/request` lists pending asks for one location, chosen
  by a `location[directory]` query or an `x-opencode-directory` header.
  `GET /api/session/:id/permission` lists one session's. `POST
  /api/session/:id/permission/:req/reply` answers with
  `{"decision": …, "message"?: …}`, the decision one of `once`, `always`
  or `reject`. Measured (#479):
  - both listings work. Without a location, `GET /api/permission/request`
    lists the service's directory and returns nothing, even from a shell
    whose working directory is the Worker's Worktree;
  - `once` lets the Worker go on;
  - **`reject` cancels every pending ask in the session and ends the
    turn.** With two asks pending, one `reject` answered both, and no further
    model request followed;
  - **`reject` with a `message`** hands the tool the message and the turn
    goes on to its next step;
  - **`always` saves a Project-wide rule** in the database, listed by
    `GET /api/permission/saved?projectID=<p>` and by nothing without the
    `projectID`. It also answered **the Lead's** next ask at the main
    Worktree, and it survived a service restart. `DELETE
    /api/permission/saved/<id>` removes it.
- **Question forms.** Source: an unattended Worker's `question` tool waits
  like an ask, listed at `GET /api/session/:id/form` and answered at
  `…/form/:id/reply`, which the permission API does not cover. `opencode
  run` cancels forms for its session family. Not measured.
- **Deletion.** Source: `DELETE /api/session/:id` deletes a session and its
  children; `opencode session delete` does the same.
- **Sub-agent depth.** Source (`packages/core/src/tool/plugin/subagent.ts`):
  depth counts along the `parentID` chain against
  `experimental.subagent_depth`, which defaults to 1. A root Worker can
  therefore launch its own reviewer, which a child Worker cannot; measured
  (#479). Resume is still parent-only.
- **`opencode run`.** Source (`packages/cli/src/run/`):
  - it creates its session at `$PWD`, and `--session <id>` creates a session
    with that id if none exists;
  - on the managed service only, it copies the caller's whole environment
    into the session, except the password, and does so for an existing
    session too, so `opencode run --session <worker>` overwrites that
    Worker's environment with the caller's;
  - it answers asks for its session and every descendant with `reject`, or
    `once` under `--auto`, and cancels their question forms;
  - it returns when its session's execution succeeds, fails or is
    interrupted.
- **Agent selection.** Measured (#479): a root session made with
  `agent: "dashpot-worker"`, a `mode: subagent` agent, is accepted and runs
  with that agent, and the agent's `*session_move` denial holds: its move
  attempt got `Unknown tool 'opencode.session_move'`. The v2 documentation
  says a `subagent` agent runs only in a child session; the source
  (`packages/core/src/agent.ts`) and the measurement disagree with it.
- **Plugin sessions.** Source: v2 plugins can add tools
  (`ctx.tool.transform`). Measured (#479): a plugin's `ctx.session` offers
  `create`, `prompt`, `synthetic`, `wait`, `interrupt`, `move`, `remove` and
  more, and `ctx.permission` exists. Only the method names were recorded;
  none was called. Plugins load lazily, once per location instance, not at
  service boot.
- **Outcome.** Source (`packages/schema/src/session.ts`,
  `packages/core/src/session/projector.ts`): when a session goes idle it
  records `time.idle` and an `outcome` of `succeeded`, `failed` or
  `interrupted`, which `GET /api/session/:id` returns. An idle eviction
  records `interrupted`. An interrupt at service shutdown records nothing and
  keeps the execution claim. Measured (#479):
  - an interrupt records `interrupted` with `time.idle`;
  - a turn resumed after a restart records `succeeded` and a new
    `time.idle` when it ends, so a poller then sees `succeeded` for a turn
    the model only half redid;
  - a turn ended by `reject` showed no `outcome` or `time.idle` right after
    its `wait` returned. Why is unknown.
- **No creator.** Source (`packages/schema/src/session.ts`): a session
  records no creator, only `fork.sessionID` for a fork.

## A service restart

Measured (#479). Before `opencode service stop`, Workers and the Lead were
mid-shell, one Worker waited on an ask, one had been interrupted and one was
idle and bound.

- **The stop orphans every run.** Every bound run reads `unknown`, orphaned,
  with an `agent-run` blocker on its Worktree. Dashpot's plugin publishes
  `Stop` for the sessions that were running.
- **The restarted service resumes the turns it cut off.** It appends a
  `user` message, "The server restarted while you were working. Continue
  from where you left off without repeating completed work.", turns the
  cut-off tool's result into `Command cancelled`, and the model continues at
  the next step without rerunning the cut-off shell. By source
  (`packages/core/src/session/execution/restart.ts`), it tries a turn up to
  ten times before recording `failed`. Interrupted and idle sessions are
  left alone.
- **A pending ask is lost.** It is aborted with "Interaction cancelled
  because the location shut down". After the restart nothing is pending, and
  the resumed turn went on without asking again.
- **Dashpot never sees a resumed turn start.** Neither a client subscribed
  159 ms after the restart nor a plugin loaded at about 295 ms saw
  `session.execution.started` for a resumed session, only its `succeeded`.
  The resumed Worker's run stays orphaned while it works.
- **`work start` from the resumed turn is refused.** It exits 2: the
  lifecycle hook record for the session "is stale (whose process is gone)".
  `work show` from that turn reports the old, orphaned run.
- **Only a fresh prompt rebinds.** After a new `/prompt`, `work start`
  bound a new run ("run restarted"), which reads `waiting`, not orphaned. A
  Worker that was idle stays orphaned until prompted.
- **A replaced environment is lost.** The resumed shell lacks what
  `PUT /api/session/:id/environment` set.

## Capability matrix

| Mechanism | Own identity and placement | Own Agent Run | Dispatch | Progress and completion | Permission asks | Cancel | Eviction and restart | Standalone Lead | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A. Child `subagent`** (today) | No: resolved to the Lead through `parentID`, at the Lead's directory | No: its `work start` is refused as a delegated session; attributed with `work assign` | `subagent` with `background: true` | Built-in `<subagent>` notice (`completed`, `error`, `cancelled`), durable job recovery, resume by the parent only | Rejected under `run`; otherwise shown in the TUI (unmeasured) | Interrupting the Lead leaves Workers running; deleting it deletes them | Shares the Lead's location and idle timer; a stop ends everything | Leads none ([ADR 0108](../adr/0108-keep-opencode-self-move-and-leading-workers-on-the-shared-service.md)); children would die with the Lead's private server (inference) | Measured ([Worker mechanics experiment](../spikes/opencode-v2-worker-mechanics-spike.md)), except the standalone cell |
| B. Root through the Lead's background shell, `cd <worktree> && opencode run --agent … "<brief>"` | Yes, with no metadata | Yes | A blocking client in a background shell | The shell ends when the Worker's **first** execution ends, and its notice wakes the Lead with the Worker's final text; later executions have no client | Rejected while `run` is attached (approved under `--auto`); afterwards they wait and the Worker reads running | Interrupt through the API, or Ctrl-C in the client | The Lead's shell may die if the Lead's location is evicted ([#467](https://github.com/ned2/dashpot/issues/467)) | Workers must stay on the shared service | Dispatch, binding, the Lead's environment in the Worker and the notice measured (#479); eviction inference |
| **C. Root through `opencode api POST /api/session` and `/prompt`** | Yes, from `location`; `metadata` can carry the Lead | Yes | Non-blocking: creation 54 ms, prompt admission 133 ms (#479); reads waiting until prompted (ADR 0106) | Needs a protocol: the Worker's synthetic message, which wakes an idle Lead and steers a busy one, with a status file and the Lead's polling or `wait` as backstops | The Lead lists and answers them; `reject` ends the turn and `always` is Project-wide; `permissions` at creation is unmeasured | `interrupt`, or deletion; background shells survive deletion (measured) | One idle timer per location (source). A stop orphans every run; the restarted service resumes cut-off turns, unseen by Dashpot, and only a fresh prompt rebinds | Leads none (ADR 0108). Its `opencode api` reaches the shared service, and a notice runs its session there while its private server is mid-turn | Measured (#479), and roots made through the API in [#379](https://github.com/ned2/dashpot/issues/379), [#393](https://github.com/ned2/dashpot/issues/393) and [#421](https://github.com/ned2/dashpot/issues/421); eviction and asks set at creation source |
| D. A person's TUI, `opencode <worktree> --prompt` | Yes | Yes | Manual | None | In the TUI | The person | As C | Shared service only | Measured ([#163](https://github.com/ned2/dashpot/issues/163)) |
| E. A plugin tool or Dashpot helper wrapping C | Yes | Yes | One tool call | Could post the notice reliably on execution events | Could relay asks | Yes | As C | Leads none (ADR 0108) | `ctx.session` and `ctx.permission` exist (method names measured (#479), none called); would need building, and an ADR, since observation stays passive ([ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)) |
| F. `opencode run --standalone` Workers | Yes, in a private server | Yes | Blocking | — | — | — | Die with their client, background commands included (measured) | — | Not viable |

Option C is the recommendation. B is a cheap prototype, but its notice comes
too early for a Worker that waits on CI. E is the most robust end state, and
the plugin API offers its parts, but it needs an ADR.

## What Dashpot gets and what it must build

Gets, as it stands, all measured (#479):

- Cleanup blocks only a Worker's own Worktree: its `agent-session`, its
  `agent-run` and a `process` blocker for a shell it holds. ADR 0066's
  Repository-wide blocker is gone for Workers, except while a Worker's
  reviewer Sub-agent runs: then every Worktree, including one no session
  uses, shows a `sub-agent` blocker naming the Worker, until the reviewer
  ends.
- The [#427](https://github.com/ned2/dashpot/issues/427),
  [#459](https://github.com/ned2/dashpot/issues/459) and
  [#460](https://github.com/ned2/dashpot/issues/460) stranding classes
  cannot arise from Workers, since the Lead has no child Workers to strand.
  ADR 0107 has since fixed #460 for Sub-agents, which a Worker's reviewer
  still is.
- Deleting or moving the Lead strands nothing. A deleted Lead's Workers keep
  running and bound; a moved Lead's run moves with it, and a Worker's notice
  reaches it at its new location.
- No `work assign`.
- Workers are ordinary rows in the Sessions pane.
- A person can watch or answer a Worker with `opencode <worktree> --session
  <id>`; resuming from another directory leaves the session where it was
  ([agent sessions](../agent-sessions.md#opencode-hosting-modes)).
- Reviewers run at the default depth, as children whose `work start` is
  refused as a delegated session.

Must build:

1. **A completion and progress notice.** The built-in `<subagent>` notice,
   its `error` and `cancelled` states, job recovery and cascading delete are
   all for children. A root Worker's recorded `outcome` tells a Lead that
   polls `GET /api/session/:id` whether its last execution failed, but
   nothing pushes it to the Lead. A notice to a deleted Lead fails with 404
   and the Worker carries on.
2. **A declaration of the Lead**, which `metadata` can carry; Dashpot does
   not read it today. A reader must skip forks and children, which carry the
   same declaration, and a `PATCH` by anyone else replaces it. Deriving it
   from the title would derive identity from a label, which AGENTS.md
   forbids.
3. **A policy for asks** in an unattended Worker, whose asks wait while it
   reads running
   ([measured](../spikes/opencode-v2-background-permissions-spike.md#opencode-run-under-default-permissions)).
   The replies are blunt: `reject` ends the turn, `always` widens the
   Lead's permissions too, and question forms need their own route.
4. **A finish step.** A finished Worker stays live at its Worktree, blocking
   Cleanup there and adding to [#473](https://github.com/ned2/dashpot/issues/473)'s
   clutter. It needs `work stop` and then a move back to the main Worktree
   ([ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)),
   which makes the Worktree removable (measured (#479), by a Worker on
   another agent). The `dashpot-worker` agent's move denial
   ([ADR 0093](../adr/0093-install-an-opencode-worker-agent-that-cannot-move-sessions.md))
   forbids that move today, or the Lead deletes the Worker. One session
   moving or deleting another is a new authority.
5. **Recovery after a service stop.** The restarted service resumes the
   Workers it cut off, but their runs stay orphaned and their own
   `work start` is refused; idle Workers are not resumed at all. A fresh
   prompt to each Worker is what rebinds a run in place of its Orphaned
   Agent Run ([agent sessions](../agent-sessions.md#opencode-hosting-modes)).
   A Worker that was waiting on an ask has lost it. Only Claude Code
   continues an orphaned run itself.
6. **The Worker's environment.** A session made through the API gets the
   service's environment, from whichever client started the service, not the
   Lead's `PATH` or `gh` credentials: `GH_TOKEN` exported in the Lead's shell
   was absent from the Worker's (measured (#479)). `PUT
   /api/session/:id/environment` replaces it wholesale, and the service keeps
   it in memory only, so a service restart loses it (measured (#479)). By
   source, the Worker's reviewer child gets the service's environment, not
   the Worker's, and `opencode service set env` is the durable, service-wide
   alternative. A model's shell still carries the right
   `OPENCODE_SESSION_ID`, so `work start` identity holds (measured (#479)).

## A Lead and Worker exchange

All through `opencode api`, so no one handles the password:

```text
# Dispatch: a root session at the Worktree, then its first prompt
opencode api POST /api/session -d '{"location":{"directory":"/abs/worktree"},"agent":"dashpot-worker","title":"#123","metadata":{"dashpot.lead":"ses_L","dashpot.issue":"123"}}'
opencode api POST /api/session/ses_W/prompt -d '{"text":"Read your brief at …","skills":[{"id":"dashpot-issue-work"}]}'

# Worker to Lead, with a stable id so a retry is not delivered twice
opencode api POST /api/session/ses_L/synthetic -d '{"id":"msg_…","text":"<worker session=\"ses_W\" issue=\"123\" state=\"completed\">…</worker>"}'
```

- **The notice's id:** one per notice, reused only to retry a POST that
  failed. A repeat is not shown to the Lead, but it starts an empty
  execution of the Lead (measured (#479)).
- **Steer or resume a Worker:** `POST /api/session/ses_W/prompt`, from any
  process, not only a parent.
- **Asks:** `GET /api/session/ses_W/permission`, or `GET
  /api/permission/request` with the Worktree's `location[directory]`, then
  `…/permission/<id>/reply` with `once`, or `reject` with a `message` so the
  Worker goes on.
- **Cancel:** `POST …/interrupt`, or `opencode session delete`.
- **Backstop:** the status file, and the Lead's polling of
  `GET /api/session/ses_W`, or a blocking `…/wait`. `GET /api/event` does
  not stream through `opencode api`.

## Risks and unknowns

- **Restart-resumed turns.** A resumed Worker works with an orphaned run
  that its own `work start` cannot rebind, and its finished turn records
  `succeeded`. Whether a real model, told it was restarted, repeats side
  effects such as a push or a PR comment is unknown.
- **Reaching the right service.** From a model's shell, `opencode api` finds
  the service through `XDG_STATE_HOME`, and may start one; the #479 fixture's
  calls all reached its own service. At 2.0.22 it also replaces a registered
  service that speaks the earlier health protocol (source).
- **Completion depends on the Worker sending it.** A crash, an execution that
  errors and an idle eviction send nothing, so the Lead must also poll. A
  poll can tell a failed execution from the session's `outcome`, but a
  shutdown leaves the previous `outcome` in place until a resumed turn
  overwrites it, so the poll must check that `time.idle` is newer than its
  prompt.
- **A repeated notice id** starts an empty execution of the Lead, which can
  flicker its state; its effect on Dashpot's hook state was not isolated.
- **`always`** saves a rule that answers every session in the Project, the
  Lead and the operator's own included, and outlives a restart.
- **`work show` from a session with no run.** After Worker A's `work stop`
  and its move back to the main Worktree, where the Lead holds a run, its
  `work show` reported the Lead's run (measured (#479)). Root sessions of one
  service at one Worktree are not told apart there.
- **Forks.** A fork of a Worker is a second root at the same Worktree
  declaring the same Lead and Issue.
- **Eviction.** The idle timer is per location, so it is one per Worker only
  while each Worker is alone at its Worktree. A Lead's background waiter may
  die if the Lead's location is evicted (#467). Not measured.
- **Standalone Leads.** ADR 0108 lets a standalone Lead lead no Workers.
  The #479 experiment measured why: a Worker's notice ran the standalone
  Lead's session on the shared service while its private server was still
  mid-turn, two Host Processes executing one session
  ([#454](https://github.com/ned2/dashpot/issues/454)).
- **Session moves can't be limited to oneself:** a Worker can move or
  delete any session through the API, as today (measured,
  [#421](https://github.com/ned2/dashpot/issues/421)).
- **Cost and concurrency** (inference). Each Worker is a full session with
  its own instructions and skills. No cap on root sessions was found in the
  source, and `experimental.subagent_depth` limits only children. Every
  Worker runs in the one service process, so that process, the provider's
  rate limits and the Lead's skill are what bound them.
- **Upstream changes.** The unreleased upstream `v2` branch, ahead of
  2.0.22, changes some of this; recheck before repinning:
  - anomalyco/opencode#50825: `opencode api` fails rather than replacing a
    service of the earlier protocol;
  - anomalyco/opencode#52668: a session whose location directory is missing,
    such as a removed Worktree, answers 404 on `/permission`, `/prompt` and
    others, which a Lead polling after Cleanup meets;
  - anomalyco/opencode#52747: skills honour `disable-model-invocation`;
  - anomalyco/opencode#52573: a PTY handoff can no longer block a restart.

## The #479 experiment

[`scripts/experiments/opencode-479/`](../../scripts/experiments/opencode-479/),
cloned from `opencode-421/`, ran the pinned 2.0.22 binary in a `TMPDIR`
fixture outside every Project, with isolated `HOME` and XDG directories, a
private service port, autoupdate off, a loopback model and a loopback-only
proxy, detached with `setsid -f`. A guard checked every `opencode api` call
reached the fixture's service; the operator's service was never touched.
Its `verify.mjs` checks 35 claims against the retained
[trace](../spikes/measurements/issue-479-opencode-trace.jsonl). It covered
dispatch, notices to an idle and a busy Lead, a Worker's asks and the reply
semantics, a fork, a reviewer, the finish, interrupt, deleting and moving
the Lead, Option B, a service restart, a standalone Lead and a 330 s wait.

Still unknown:

- whether a real model repeats side effects after a restart; the fixture's
  model only advances steps;
- whether a plugin's `ctx.session` calls work from a tool and respect
  permissions; calling them would need an ADR;
- the one-hour idle eviction, which stays with #467;
- asks answered by `permissions` set at creation, question forms, and a
  restart with more than one turn queued;
- cost and concurrency at scale.

## Sources

- Upstream, at [`v2.0.22`](https://github.com/anomalyco/opencode/tree/v2.0.22):
  `packages/cli/src/commands/handlers/api.ts`,
  `packages/cli/src/services/server-connection.ts`, `packages/cli/src/run/`,
  `packages/protocol/src/groups/session.ts` and `permission.ts`,
  `packages/server/src/handlers/session.ts`,
  `packages/core/src/session/subagent-completion.ts`,
  `packages/core/src/session/execution/restart.ts`,
  `packages/core/src/session/projector.ts`,
  `packages/schema/src/session-event.ts` and `session-metadata.ts`.
- Dashpot: the [#479 experiment](../../scripts/experiments/opencode-479/) and
  its [trace](../spikes/measurements/issue-479-opencode-trace.jsonl), the
  [Worker mechanics experiment](../spikes/opencode-v2-worker-mechanics-spike.md),
  the [background permissions experiment](../spikes/opencode-v2-background-permissions-spike.md),
  the [v2 experiment](../spikes/opencode-v2-spike.md),
  [OpenCode v2 research](../research/opencode-v2-research.md),
  [agent sessions](../agent-sessions.md#opencode-hosting-modes), the
  [`dashpot-worker` agent](../../src/dashpot/agents/dashpot-worker.md) and
  the execute-issues [harness references](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md).
