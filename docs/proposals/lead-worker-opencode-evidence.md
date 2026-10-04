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

- **measured**: by a Dashpot experiment at 2.0.22, linked;
- **documented**: in OpenCode's documentation or a Dashpot experiment that
  cites the source;
- **source**: read in the [`v2.0.22`](https://github.com/anomalyco/opencode/tree/v2.0.22)
  source (commit `527f0b93`) only, with paths relative to that tag;
- **inference**: reasoning that no source states.

A second read of the source checked every source claim here; nothing was run
against an OpenCode service.

## Conclusion

Root-session Workers are viable on the shared service, and for Dashpot they
are better than child Workers. Each Worker becomes an ordinary observed root
Agent Session, with its own location, events, `work start` and Issue
Binding. Dashpot's plugin needs no change: it already treats any session
without a `parentID` as a root
([`opencode.js`](../../src/dashpot/plugins/opencode.js)).

The cost is coordination. OpenCode's built-in completion notice, its durable
job recovery and its parent-only resume all belong to child sessions, so the
skill has to supply a notice, a declaration of the Lead, and a finish step.
What a root session keeps is its recorded outcome, which a Lead can read.

## Affordances beyond the existing experiments

- **`opencode api`.** Source (`packages/cli/src/commands/handlers/api.ts`):
  a CLI command that calls the shared service by `METHOD /path` or
  operationId, with `-d` and `-H`, and `--param` with an operationId only,
  and authenticates from the
  service registration itself. The model never reads the registration or the
  password. Dashpot's documents and code don't mention it yet. Three caveats:
  - it **starts the shared service if none is running**, and accepts a
    running service of another version;
  - if the service configuration disables the service, it silently starts a
    private server instead, which exits with the command and takes any
    dispatched session with it;
  - `--standalone` always starts a new private server, never the Lead's.
- **`POST /api/session`.** Source (`packages/protocol/src/groups/session.ts`,
  `packages/server/src/handlers/session.ts`): every field is optional:
  `id`, `parentID`, `title`, `agent`, `model`, `location: {directory}`,
  `metadata` and `permissions`.
  - With a `parentID`, the session is a child at its parent's location, and a
    given `location` is silently dropped.
  - With neither, the root is placed at the **service's** working directory,
    which the [v2 experiment](../spikes/opencode-v2-spike.md) found to be
    `$HOME`. A Worker must always be given its `location`.
- **Session `metadata`.** Source (`packages/schema/src/session-metadata.ts`,
  `session-event.ts`): "host-supplied session annotations, durable and
  opaque to core", carried in `session.created`, with a
  `session.metadata.updated` event. Two caveats for a Lead link:
  - children and forks **inherit** their parent's metadata unless their
    creator supplies its own, so a Worker's reviewer would usually carry the
    same `dashpot.lead`, and a reader must also check that `parentID` is
    absent;
  - any client can change it with `PATCH /api/session/:id`, so it is a
    declaration, not proof of who made the session.
- **`POST /api/session/:id/synthetic`.** Source: "durably admit synthetic
  session input and schedule execution unless resume is false", with
  `{id?, text, description?, metadata?, delivery?: "steer" | "queue", resume?}`.
  OpenCode's own `<subagent>` notice uses the same core operation in process
  (`packages/core/src/session/subagent-completion.ts`), and passes a stable
  `id` so a retry is not delivered twice; a Worker's notice should too. The
  `id` is a message id, so it must start with `msg_`.
  Unlike `opencode run --session`, it attaches no client that rejects asks.
- **`POST /api/session/:id/prompt`.** Source: accepts `skills`, `delivery`
  and `resume`. `skills` is a list of objects, `[{"id": "dashpot-issue-work"}]`
  (`packages/schema/src/prompt-input.ts`).
- **Waiting and interrupting.** Source: `POST
  /api/experimental/session/:id/wait` waits until the agent loop is idle.
  `POST …/interrupt` stops an execution "owned by this OpenCode process",
  which on the shared service is the service itself, so it reaches every
  session the service runs. `GET /api/session/active` lists only the
  foreground executions the service owns, which makes it a weak completion
  check.
- **Permission asks.** Source (`packages/protocol/src/groups/permission.ts`):
  `GET /api/permission/request` lists pending asks for one location, chosen
  by a `location[directory]` query or an `x-opencode-directory` header, and
  falls back to the service's directory. `GET /api/session/:id/permission`
  lists one session's. `POST /api/session/:id/permission/:req/reply` answers
  with a body of `{"decision": …}`, one of `once`, `always` or `reject`.
- **Deletion.** Source: `DELETE /api/session/:id` deletes a session and its
  children; `opencode session delete` does the same.
- **Sub-agent depth.** Source (`packages/core/src/tool/plugin/subagent.ts`):
  depth counts along the `parentID` chain against
  `experimental.subagent_depth`, which defaults to 1. A root Worker can
  therefore launch its own reviewer, which a child Worker cannot. Resume is
  still parent-only.
- **`opencode run`.** Source (`packages/cli/src/run/`):
  - it creates its session at `$PWD`, and `--session <id>` creates a session
    with that id if none exists;
  - on the managed service only, it copies the caller's whole environment
    into the session, except the password, and does so for an existing
    session too;
  - it answers asks for its session and every descendant with `reject`, or
    `once` under `--auto`;
  - it returns when its session's execution succeeds or is interrupted.
- **Agent selection.** Source (`packages/core/src/agent.ts`): the filter that
  keeps `mode: subagent` agents out applies only to default selection, so
  the `dashpot-worker` agent could probably be chosen explicitly for a root
  session. Not measured.
- **Plugin tools.** Source: v2 plugins can add tools (`ctx.tool.transform`);
  whether a plugin may create or prompt sessions is unverified.
- **Outcome.** Source (`packages/schema/src/session.ts`,
  `packages/core/src/session/projector.ts`): when a session goes idle it
  records `time.idle` and an `outcome` of `succeeded`, `failed` or
  `interrupted`, which `GET /api/session/:id` returns. An interrupt at
  service shutdown records nothing: the previous execution's `outcome` and
  `time.idle` are left in place, so a poller compares `time.idle` with the
  time of its last prompt before trusting the `outcome`.
- **No creator.** Source (`packages/schema/src/session.ts`): a session
  records no creator.

## Capability matrix

| Mechanism | Own identity and placement | Own Agent Run | Dispatch | Progress and completion | Permission asks | Cancel | Eviction and restart | Standalone Lead | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **A. Child `subagent`** (today) | No: resolved to the Lead through `parentID`, at the Lead's directory | No: its `work start` is refused as a delegated session; attributed with `work assign` | `subagent` with `background: true` | Built-in `<subagent>` notice (`completed`, `error`, `cancelled`), durable job recovery, resume by the parent only | Rejected under `run`; otherwise shown in the TUI (unmeasured) | Interrupting the Lead leaves Workers running; deleting it deletes them | Shares the Lead's idle timer; a stop ends everything | Children die with the Lead's private server | Measured ([Worker mechanics experiment](../spikes/opencode-v2-worker-mechanics-spike.md)) |
| B. Root through the Lead's background shell, `cd <worktree> && opencode run --agent … "<brief>"` | Yes | Yes | A blocking client in a background shell | The shell ends when the Worker's **first** execution ends, and its notice carries the Worker's output; later executions have no client | Rejected while `run` is attached (approved under `--auto`); afterwards they wait and the Worker reads running | Interrupt through the API, or Ctrl-C in the client | The Lead's shell may die if the Lead's location is evicted ([#467](https://github.com/ned2/dashpot/issues/467)) | Workers must stay on the shared service | Parts measured; the combination inference |
| **C. Root through `opencode api POST /api/session` and `/prompt`** | Yes, from `location`; `metadata` can carry the Lead | Yes | Non-blocking; prompt admission measured at 22 ms ([#421](https://github.com/ned2/dashpot/issues/421)) | Needs a protocol: the Worker's synthetic message, with a status file and the Lead's polling as backstops | The Lead lists and answers them, or sets `permissions` when making the session | `interrupt`, or deletion; background shells survive deletion (measured) | One idle timer per Worker; a service restart orphans every Worker's run and nothing resumes them | The Lead can dispatch to the shared service, but a notice back into a standalone Lead is the two-Host-Process case ([#454](https://github.com/ned2/dashpot/issues/454)) | Roots made through the API measured as observed, placed and bound ([#379](https://github.com/ned2/dashpot/issues/379), [#393](https://github.com/ned2/dashpot/issues/393)); the rest source |
| D. A person's TUI, `opencode <worktree> --prompt` | Yes | Yes | Manual | None | In the TUI | The person | As C | Shared service only | Measured ([#163](https://github.com/ned2/dashpot/issues/163)) |
| E. A plugin tool or Dashpot helper wrapping C | Yes | Yes | One tool call | Could post the notice reliably on execution events | Could relay asks | Yes | As C | Must refuse a standalone Lead | Would need building, and an ADR, since observation stays passive ([ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)) |
| F. `opencode run --standalone` Workers | Yes, in a private server | Yes | Blocking | — | — | — | Die with their client, background commands included (measured) | — | Not viable |

Option C is the recommendation. B is a cheap prototype, but its notice comes
too early for a Worker that waits on CI. E is the most robust end state but
needs an ADR.

## What Dashpot gets and what it must build

Gets, as it stands:

- Cleanup blocks only a Worker's own Worktree; ADR 0066's Repository-wide
  blocker is gone for Workers.
- The [#427](https://github.com/ned2/dashpot/issues/427),
  [#459](https://github.com/ned2/dashpot/issues/459) and
  [#460](https://github.com/ned2/dashpot/issues/460) stranding classes
  disappear, since the Lead has no child Workers to strand.
- No `work assign`.
- Workers are ordinary rows in the Sessions pane.
- A person can watch or answer a Worker with `opencode <worktree> --session
  <id>`; resuming from another directory leaves the session where it was
  ([agent sessions](../agent-sessions.md#opencode-hosting-modes)).
- Reviewers run at the default depth.

Must build:

1. **A completion and progress notice.** The built-in `<subagent>` notice,
   its `error` and `cancelled` states, job recovery and cascading delete are
   all for children. A root Worker's recorded `outcome` tells a Lead that
   polls `GET /api/session/:id` whether its last execution failed, but
   nothing pushes it to the Lead.
2. **A declaration of the Lead**, which `metadata` can carry; Dashpot does
   not read it today. Deriving it from the title would derive identity from a
   label, which AGENTS.md forbids.
3. **A policy for asks** in an unattended Worker, whose asks wait while it
   reads running
   ([measured](../spikes/opencode-v2-background-permissions-spike.md#opencode-run-under-default-permissions)).
4. **A finish step.** A finished Worker stays live at its Worktree, blocking
   Cleanup there and adding to [#473](https://github.com/ned2/dashpot/issues/473)'s
   clutter. It needs `work stop` and then a move back to the main Worktree
   ([ADR 0094](../adr/0094-let-a-root-opencode-session-move-itself-for-issue-work.md)),
   which the `dashpot-worker` agent's move denial forbids today, or the Lead
   deletes it. One session moving or deleting another is a new authority.
5. **Recovery after a service stop.** The Lead prompts each Worker again,
   and each runs `work start` again, which binds a new run in place of its
   Orphaned Agent Run
   ([agent sessions](../agent-sessions.md#opencode-hosting-modes)). Only
   Claude Code continues an orphaned run itself.
6. **The Worker's environment.** A session made through the API gets the
   service's environment, from whichever client started the service, not the
   Lead's `PATH` or `gh` credentials. `PUT /api/session/:id/environment`
   replaces it wholesale, and the service keeps it in memory only, so a
   service restart loses it. A model's shell still carries the right
   `OPENCODE_SESSION_ID`, so `work start` identity holds
   ([measured](../spikes/opencode-v2-spike.md#shell-identity)).

## A Lead and Worker exchange

All through `opencode api`, so no one handles the password:

```text
# Dispatch: a root session at the Worktree, then its first prompt
opencode api POST /api/session -d '{"location":{"directory":"/abs/worktree"},"agent":"dashpot-worker","title":"#123","metadata":{"dashpot.lead":"ses_L","dashpot.issue":"123"}}'
opencode api POST /api/session/ses_W/prompt -d '{"text":"Read your brief at …","skills":[{"id":"dashpot-issue-work"}]}'

# Worker to Lead, with a stable id so a retry is not delivered twice
opencode api POST /api/session/ses_L/synthetic -d '{"id":"msg_…","text":"<worker session=\"ses_W\" issue=\"123\" state=\"completed\">…</worker>"}'
```

- **Steer or resume a Worker:** `POST /api/session/ses_W/prompt`, from any
  process, not only a parent.
- **Asks:** `GET /api/session/ses_W/permission`, then
  `…/permission/<id>/reply`.
- **Cancel:** `POST …/interrupt`, or `opencode session delete`.
- **Backstop:** the status file, and the Lead's polling. Long-lived waiting
  shells in the Lead are best avoided.

## Risks and unknowns

- **Reaching the right service.** From a model's shell, `opencode api` finds
  the service through `XDG_STATE_HOME`, and may start one. A fixture must
  point it at its own registration, or it reaches, or starts, the operator's
  real service. Unmeasured.
- **The synthetic message is unmeasured.** Does it wake an idle root Lead,
  steer a busy one, and leave the Lead's own asks to its TUI rather than
  rejecting them?
- **Completion depends on the Worker sending it.** A crash, an execution that
  errors and an idle eviction send nothing, so the Lead must also poll. A
  poll can tell a failed execution from the session's `outcome`, but a
  shutdown interrupt leaves the previous `outcome`, possibly `succeeded`, in
  place, so the poll must check that `time.idle` is newer than its prompt.
- **Eviction per Worker.** Each Worker has its own one-hour idle timer. A
  Lead's background waiter may die if the Lead's location is evicted (#467).
- **Standalone Leads.** A notice back into a standalone Lead is unsafe
  (#454), so that case polls only or is refused.
- **Session moves can't be limited to oneself** (inference): a Worker can
  move or delete any session through the API, as today.
- **Cost and concurrency** (inference). Each Worker is a full session with
  its own instructions and skills. No cap on root sessions was found in the
  source, and `experimental.subagent_depth` limits only children. Every
  Worker runs in the one service process, so that process, the provider's
  rate limits and the Lead's skill are what bound them.

## Proposed experiment

A new `scripts/experiments/opencode-479/run.mjs`, cloned from
`opencode-421/`: the pinned 2.0.22 binary copied into the fixture, a
`TMPDIR` fixture outside every Project, isolated `HOME` and XDG directories,
a private service port, autoupdate off, a loopback model and a loopback-only
proxy. It refuses to start under a harness and runs under `setsid -f`. The
fixture's `PATH` resolves `opencode` to the pinned copy, and the shell
environment points at the fixture's service registration. A `verify.mjs`
checks a retained metadata-only trace.

1. The Lead's shell makes and prompts Worker A at worktree A with metadata.
   Check that it is a root with no `parentID`, that the plugin sees the
   metadata, that the Worker's `work start` binds at A, that worktree B is
   free, and that A has only the Worker's Agent Session blocker.
2. A synthetic notice to an idle Lead and to a busy one. Check that the
   Lead's own ask stays pending.
3. A Worker asks for permission: Dashpot shows it running; the Lead lists and
   answers the ask.
4. Interrupt and delete Worker A; delete the Lead while Workers run; move the
   Lead while Workers run. No stranded records.
5. A Worker's reviewer Sub-agent at the default depth, and its inherited
   metadata.
6. The Worker finishes with `work stop` and moves back to the main Worktree;
   A becomes removable.
7. Option B: a background `opencode run` dispatch and its notice.
8. `opencode service stop` and `start` mid-turn: runs orphaned, then
   recovered.
9. A standalone Lead dispatching through `opencode api`.

The one-hour idle eviction stays with #467.

## Sources

- Upstream, at [`v2.0.22`](https://github.com/anomalyco/opencode/tree/v2.0.22):
  `packages/cli/src/commands/handlers/api.ts`, `packages/cli/src/run/`,
  `packages/protocol/src/groups/session.ts` and `permission.ts`,
  `packages/server/src/handlers/session.ts`,
  `packages/core/src/session/subagent-completion.ts`,
  `packages/schema/src/session-event.ts` and `session-metadata.ts`.
- Dashpot: the [Worker mechanics experiment](../spikes/opencode-v2-worker-mechanics-spike.md),
  the [background permissions experiment](../spikes/opencode-v2-background-permissions-spike.md),
  the [v2 experiment](../spikes/opencode-v2-spike.md),
  [OpenCode v2 research](../research/opencode-v2-research.md),
  [agent sessions](../agent-sessions.md#opencode-hosting-modes), the
  [`dashpot-worker` agent](../../src/dashpot/agents/dashpot-worker.md) and
  the execute-issues [harness references](../../src/dashpot/skills/dashpot-execute-issues/references/harnesses.md).
