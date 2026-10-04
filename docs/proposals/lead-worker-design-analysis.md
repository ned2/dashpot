---
status: research
date: 2026-10-05
---

# Lead and Worker design analysis

The analysis behind the [Lead and Worker design](lead-worker-design.md), made
for [Issue #479](https://github.com/ned2/dashpot/issues/479). It asks how a
Lead's Workers should appear in the Sessions pane, and whether the mechanism
that runs them should change to make that answer simpler and more truthful.
It weighs the Workers the
[execute-issues skill](../adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)
runs today, which are Sub-agents of the Lead, against Workers run as their own
root Agent Sessions in their Issue Worktrees. The harness findings it draws on
are in three evidence notes:
[Claude Code](lead-worker-claude-code-evidence.md),
[Codex](lead-worker-codex-evidence.md) and
[OpenCode](lead-worker-opencode-evidence.md).

The [domain language](../domain-language.md#observation) defines a Worker as
a background Sub-agent of a Lead. To compare the two mechanisms, this document
calls today's Workers **sub-agent Workers** and the alternative **root-session
Workers**. Adopting the alternative would change that definition, which is one
of the design's open decisions.

This is a read of the code, documents and Issues at `main` 928e264, and of
upstream documentation, source and release binaries. Nothing here was run
for this analysis. A statement marked _measured_ was observed by an earlier
Dashpot experiment, which the statement or its evidence note links; one
marked _inference_ is reasoning no source states directly.

## Today's Sessions pane and read model

- **What the pane lists.** One row per active Agent Run, ordered by turn state
  and then by latest activity
  ([`session_list.py`](../../src/dashpot/observation/session_list.py)). The
  columns are `◈ HARNESS [TARGET] BRANCH ISSUE DIRECTORY ACTIVITY`, and only
  `◈` is frozen
  ([`session_cells.py`](../../src/dashpot/ui/session_cells.py)). The pane is
  a `FocusCursorTable`
  ([`session_table.py`](../../src/dashpot/ui/session_table.py)). Every refresh
  rebuilds the rows and restores the cursor by row key, or by index when that
  row has gone ([`list_pane.py`](../../src/dashpot/ui/list_pane.py),
  [`keyed_table.py`](../../src/dashpot/ui/keyed_table.py)).
- **No Workers.** `AgentRun.workers`
  ([`model.py`](../../src/dashpot/core/model.py)) is read only by the Issues
  pane ([`issue_list.py`](../../src/dashpot/observation/issue_list.py)) and the
  store's change tracking. A Worker carries an opaque Sub-agent identity, its
  Issue, a _declared_ Worktree, when it was assigned, and a state of
  `running`, `unknown` or none. It is never `waiting`, and it has no activity
  time, observed location or parentage
  ([ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md);
  [#477](https://github.com/ned2/dashpot/issues/477),
  [#478](https://github.com/ned2/dashpot/issues/478)).
- **What the read model lacks.** No `AgentRun` field counts the live
  Sub-agents that hold no Worker Assignment. Only the hook observations
  ([`agents.py`](../../src/dashpot/sessions/agents.py),
  [`hook_scan.py`](../../src/dashpot/sessions/hook_scan.py)), `work show`
  and Cleanup
  ([`obstacles.py`](../../src/dashpot/repository/cleanup/obstacles.py)) see
  them. And a Worker Assignment ends with its Lead's run, while an ended
  session's Sub-agents stay listed
  ([ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md))
  in a record no pane shows. So after a Codex Lead unloads, its Workers drop
  out of the Issues pane, and they never appear in the Sessions pane, while
  Cleanup still refuses.
- **Space.** Each pane spends four lines on chrome
  ([`pane_layout.py`](../../src/dashpot/ui/pane_layout.py)), and three panes,
  the status bar and the Footer share the screen. Below 100 columns the
  screen is compact and the status bar takes two lines, so at 80×24 with
  every pane full each pane gets three content lines. One of them is the
  horizontal scrollbar when the table scrolls, which leaves the Sessions
  pane **two** visible rows. Columns size to their content: without TARGET a
  full row can need about 120 to 145 cells, and TARGET, shown whenever
  sessions span more than one Observation Target, adds about 30. A short row
  is about 86 cells, so the pane scrolls sideways at 80 columns and often at
  100. A marker inside a frozen leading column survives that scroll; a new
  column does not.
- **Textual 8.2.8.** `DataTable` has keyed rows and frozen leading columns,
  which the list panes already use. `Tree` has one label column, with no
  headers, header tooltips or frozen columns. There is no tree-table widget.

## What sub-agent Workers cost

Each row is a problem the current mechanism causes, with what happens to it
when Workers are root sessions instead.

| Problem | Cause | With root-session Workers |
| --- | --- | --- |
| A working Worker blocks Cleanup of every Worktree in the Repository for the whole Arc ([ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md); [#476](https://github.com/ned2/dashpot/issues/476), [#478](https://github.com/ned2/dashpot/issues/478)) | No hook places a Sub-agent, so occupancy blocks on any session with live Sub-agents | **Gone for Workers.** A Worker occupies only its own Worktree, as an ordinary Agent Session with an Agent Run. **Remains** while a Worker's own reviewer Sub-agent runs |
| Issue attribution is declared, not observed ([ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)); `work assign` can race; a Codex v2 Worker must report its own thread id | A Sub-agent shares the Lead's Agent Session, so [ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md) gives it no run of its own | **Gone.** The Worker's own `work start` gives it an Issue Binding at an observed location |
| Worker activity flickers ([#477](https://github.com/ned2/dashpot/issues/477), [#472](https://github.com/ned2/dashpot/issues/472)) | Activity comes from `SubagentStart` / `SubagentStop`, and an interim stop fires while background work runs | **Mostly gone.** The session's own turn state applies, and [ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md) holds it running while its reviewers work. **Remains** as [#466](https://github.com/ned2/dashpot/issues/466): a session reads `waiting` while a background command runs, measured on OpenCode with a generic command and possible on the others; a Worker's background `gh run watch` would be such a command |
| Listings that are never dropped ([#475](https://github.com/ned2/dashpot/issues/475), [#429](https://github.com/ned2/dashpot/issues/429), [#394](https://github.com/ned2/dashpot/issues/394), [ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)) | Some Sub-agent stops are never published | **Gone for Workers.** A root session ends on positive evidence. **Remains** for reviewers |
| Listings that must follow the Lead across records and Host Processes ([ADR 0097](../adr/0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md), [ADR 0101](../adr/0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md), [ADR 0102](../adr/0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md), [#459](https://github.com/ned2/dashpot/issues/459), [#460](https://github.com/ned2/dashpot/issues/460), a Codex Lead's unload) | The Workers' listing lives in the Lead's record | **Gone for Workers.** A Lead's moves, compactions, conversation switches and unloads no longer touch Worker records, and the skill's rules to stay where the Lead bound and to keep a client attached to a Codex Lead fall away. **Remains** for reviewers |
| The Sessions pane needs a separate Worker presentation ([#444](https://github.com/ned2/dashpot/issues/444)) | A Worker is not an Agent Session | **Mostly gone.** Workers are ordinary rows, and #444 reduces to grouping them by their Lead. **New**: more rows, and [#473](https://github.com/ned2/dashpot/issues/473) clutter from OpenCode Workers that stay live after they finish |
| Skill complexity: assignment upkeep, avoiding `TaskStop` and `interrupt_agent`, the Lead launching reviewers where nesting is limited, the choices at `/exit` | Sub-agent mechanics | **Mostly gone.** _Inference_: a root Worker launches its own reviewer, and a harness's limits on concurrent Sub-agents apply per Worker |

## What root-session Workers cost

- **N1. Completion notices are lost.** Claude Code's `<task-notification>`,
  Codex's final answer and OpenCode's `<subagent>` notice belong to
  Sub-agents. Codex never woke an idle Lead anyway.
- **N2. The hand-back needs its own transport.**
- **N3. A Lead message to a Worker needs a harness's own way in, and some
  carry hazards.** A `claude -p --resume <id>` against a running `--bg`
  session publishes a `SessionEnd` from another process, which only #326's
  record of the `--bg` session's Host Process guards against. An OpenCode `SessionStart`
  from a second Host Process drops a session's Sub-agent listing while the
  child still works, so Cleanup wrongly reads its Worktrees as removable
  ([#460](https://github.com/ned2/dashpot/issues/460)).
- **N4. Permission asks in unattended sessions.** Dashpot measured
  `claude --bg` only with permission checks bypassed. OpenCode `run` rejects
  asks. A Codex `exec` has no one to ask.
- **N5. Lifecycle hazards.** Claude Code retires an idle `--bg` session about
  61 minutes after its last `Stop` and publishes no hook, so its run is
  orphaned until someone attaches. A Codex daemon thread with no subscriber
  unloads after 60 seconds and publishes `SessionEnd`.
- **N6. Workers must be torn down before Cleanup.** A finished root session
  that is still live keeps its Worktree occupied. OpenCode and Codex Workers
  share their service or daemon Host Process
  ([ADR 0067](../adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md),
  [ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)), so
  that process's liveness never frees them. Deleting an OpenCode session
  discards its history.
- **N7. No harness links a root session to its Lead.** Identity is never
  inferred
  ([ADR 0038](../adr/0038-isolate-native-agent-session-identities.md)), so the
  link has to be declared.
- **N8. Workers would run `work start` and `work stop`.** ADR 0092 says a
  Worker runs no `work` command. In a mix of the two mechanisms, a Claude
  Code sub-agent Worker's `work stop` would still end its Lead's run, since it
  shares the Lead's session identity, so the two briefs must differ. A Codex
  Sub-agent's shell claims a delegate identity whenever its thread id differs
  from its session id
  ([`harnesses.py`](../../src/dashpot/sessions/harnesses.py), `_codex_claim`),
  which `work` refuses
  ([`work.py`](../../src/dashpot/sessions/work.py), `_refuse_delegate`), and
  an OpenCode child's claim is refused
  ([`hook_claims.py`](../../src/dashpot/sessions/hook_claims.py),
  `_refuse_opencode_claim`).
- **N9. Cost.** Each root session loads the full instructions and skills, and
  _inference_: no harness Sub-agent cap bounds how many run at once.

## How a Lead and its Workers communicate

| Option | Completion reliability | Latency | Unattended asks | Keeps observation passive ([ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)) | Differs per harness |
| --- | --- | --- | --- | --- | --- |
| A. The harness's Sub-agent channels (today) | High: the notice carries the result, though some stops are silent ([#429](https://github.com/ned2/dashpot/issues/429), [#394](https://github.com/ned2/dashpot/issues/394)) | Immediate | Shown in the Lead | Not affected | High |
| B. A Dashpot mailbox (`work report` / `work message`) | Only as good as the Worker remembering to send | Needs something to wake the Lead | Not addressed | Allowed as an explicit command, but moves Dashpot into coordination | Low |
| C. Status and lead files in the Worktree's git directory, which the skill already uses as a fallback | Medium: nothing wakes the Lead | The poll interval | Not addressed | Not Dashpot's | Low |
| D. The Lead polls Dashpot (`work show`, or a new `work wait`) from a background shell; the Worker's `work stop`, its session ending, or its run becoming orphaned, is completion | High for ending, which is an explicit act or positive evidence; silent stops don't matter | The poll interval; a finished background shell wakes a Claude Code or OpenCode Lead ([OpenCode, measured](../spikes/opencode-v2-background-permissions-spike.md)), while Codex must block inside its turn | Not addressed | Reads only | Low: only the waking differs |
| E. Each harness's own channels between root sessions (detail in the evidence notes) | High where measured | Low | Varies, with N3 and N4's hazards | The Lead's side only | Highest |
| F. Git and PR state: the PR open and its checks green | High for "ready"; silent about blockers or a dead Worker | Minutes | Not addressed | Reads only | None |
| G. Issue comments | High and durable, but public | The poll interval | Not addressed | Not affected | None |

The analysis favours a mix (_inference_):

- **D** for liveness and completion;
- **C** for the hand-back and the Lead's broadcasts, since it already ships;
- **F** as the authoritative "ready" signal;
- **E** only to wake a party sooner.

A lost wake-up then only delays the Lead, and no result is lost.

## How Workers could appear in the Sessions pane

| Option | Fit | Accessibility | At 80 columns | Refresh stability | Textual effort |
| --- | --- | --- | --- | --- | --- |
| A. Flat rows with ROLE and LEAD columns | Weak: the global sort scatters an Arc | Text labels work | Two more columns, scrolled away | Good | Low |
| **B. Grouped, indented rows in the DataTable** | Good | Tree connectors plus the word "worker" | The marker sits in a frozen second column | Good, with a fallback that knows the group | Low: the query emits rows in group order |
| C. Textual `Tree` | Poor: loses the columns | Fine | Labels truncate | Its own node ids need re-plumbing | High: a new Legend, emphasis and tests |
| D. B with collapsible Lead groups | Good once an Arc overflows the two visible rows | A `▸` / `▾` Glyph plus a count | Best | Needs the set of expanded Leads | Medium: the query filters |
| E. A separate Arc pane or screen | Splits one question across two places | Fine | About four more lines of chrome, or a screen change | Good | Medium to high |
| F. Master and detail | Hides Workers until a Lead is selected | Fine | The detail starves the rows | Good | Medium, as Runtime Events does |

Option B, with D as a later increment, is the recommendation:

1. **Group, don't flatten.** A Lead's row is followed by its Workers' rows,
   and the group sorts as one unit by its liveliest member, since a Lead may
   wait while its Workers run. Inside a group the order is stable (when
   assigned, then Issue number), so a Worker's state changing moves no
   sibling.
2. **Mark the role in a frozen second column.** HARNESS would be renamed
   and frozen beside `◈`. The mockups below call it ROLE; an earlier draft called
   it AGENT, which the domain language avoids for a harness, so the label
   needs a vocabulary ruling. A Lead row shows its harness; a Worker row shows
   `├ worker` or `└ worker`, a word rather than a colour, with the connectors
   as Glyphs the Legend explains.
3. **Lead each Worker row with its Issue.** The harness identity goes to a
   tooltip and `--json`.
4. **Count the Sub-agents that hold no Worker Assignment; never list them.**
   A `+N` suffix in the role cell, and a Worker total in the pane title,
   such as `SESSIONS · 3 · 4 Workers`, give
   [#478](https://github.com/ned2/dashpot/issues/478)'s Cleanup refusal
   something visible to point at.
5. **Show only what the evidence supports for a sub-agent Worker.** A Worker
   no longer reported working shows a blank `◈` and `not listed`, never
   `done`. TARGET shows the declared Worktree behind a `⇢` "declared, not
   observed" Glyph, DIRECTORY shows `-`, and ACTIVITY shows `working` or
   `unknown` with no duration, since none is observed. Such a row emphasises
   no Worktree or Branch, and the resume key is not offered on it.
6. **Fall back within the group.** When a Worker's row disappears, the cursor
   moves to its next sibling, then to its Lead, rather than to whatever row
   now holds its index.
7. **Decide visibility per group.** A group shows if any member is visible,
   so a Lead with no client attached never hides working Workers
   ([#473](https://github.com/ned2/dashpot/issues/473)).

At about 100 columns, with sub-agent Workers, the grouped pane might read as
follows. ROLE is a placeholder label for the frozen column. The mockup also
moves ISSUE, which today comes after BRANCH, ahead of TARGET, and the first
Worker's `+2` assumes #477 has landed:

```text
╭ SESSIONS · 2 · 4 Workers ──────────────────────────────────────────────────────────────────────────╮
│◈ ROLE           ISSUE                             TARGET           BRANCH    DIRECTORY   ACTIVITY  │
│● Claude Code +1 #464 Arc: worker safety           ~/p/dashpot      main      ~/p/dashpot running 2h│
│●  ├ worker +2   #436 Keep blockers after a move   ⇢ ~/wt/issue-436 issue-436 -           working   │
│●  ├ worker      #458 Carry the listing on /clear  ⇢ ~/wt/issue-458 issue-458 -           working   │
│○  ├ worker      #427 Stale blockers after moving  ⇢ ~/wt/issue-427 issue-427 -           unknown   │
│   └ worker      #461 Keep waiting across /compact ⇢ ~/wt/issue-461 issue-461 -           not listed│
│◐ Codex          no active Issue work              ~/p/other        main      ~/p/other   idle 14m  │
╰────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

At 80 columns `◈` and ROLE stay pinned and the rest scrolls. Collapsed, as
in option D, an Arc takes one row, with `▸`, its Worker count and its `+N`:

```text
╭ SESSIONS · 2 · 4 Workers ────────────────────────────────────────────────────╮
│◈ ROLE               ISSUE                   TARGET      BRANCH DIRECTORY   A…│
│● Claude Code ▸ 4 +1 #464 Arc: worker safety ~/p/dashpot main   ~/p/dashpot r…│
│◐ Codex              no active Issue work    ~/p/other   main   ~/p/other   i…│
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Which mechanism gives the more truthful pane

Root-session Workers do. Each Worker row is an ordinary session row:

- its own turn state, including `waiting`, so a Worker stuck on a permission
  ask shows, which a sub-agent Worker never can;
- an observed TARGET, BRANCH and DIRECTORY, with no `⇢` caveat;
- a real duration in ACTIVITY and a real Issue Binding in ISSUE;
- resume on an Orphaned Agent Run;
- correct Worktrees-pane session counts and related-row emphasis with no
  extra work;
- a `+N` from the Worker's own Sub-agents, so #477's parentage is not needed
  for display;
- rows that stay when the Lead ends, under a group header that can say so,
  and a pane that falls back to today's flat table if the link is missing.

For sub-agent Workers to be shown honestly, the pane needs four things:

- the `⇢` marking;
- a "not listed" state;
- a read-model field for the unassigned Sub-agent count;
- a row kind for an ended session's retained Sub-agents.

Without the last, the pane says nothing while Cleanup refuses.

What root-session Workers add instead is the link to their Lead, as its own
evidence. Claude Code's supervisor starts `--bg` sessions, so they are not
children of the Lead's process, and process ancestry won't connect them
(_inference_ from the
[harness reference](../agent-harness-server-client-reference.md#clients-and-supervised-workers-through-dashpot-at-21286)).
Both mechanisms can share one layout, with TARGET showing which applies: `⇢`
for a declared location, a plain path for an observed one.

Two caveats remain with root-session Workers:

- [#466](https://github.com/ned2/dashpot/issues/466) may still apply: an
  OpenCode session reads `waiting` while a background command runs, which
  was measured with a generic command and would cover a Worker's
  `gh run watch`, and Claude Code and Codex may share the gap.
- The domain language avoids "worker" for Claude Code's supervised worker
  process, and running Workers as `--bg` sessions would make that collision
  constant.

## The harnesses compared

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Best root-session mechanism | `claude --bg` started in the Issue Worktree | Detached `codex exec -C <worktree>` | A root session on the shared service, made with `opencode api POST /api/session` |
| Can a Sub-agent be given its own Worktree? | Only Claude Code's own `.claude/worktrees/` through `isolation: "worktree"`; the Agent tool's `cwd` is withheld from the model | No: a spawned agent always takes its parent's working directory | No: a child takes its parent's location |
| Waking the other party | Cross-session `SendMessage`, with `notify_when_idle` | `codex queue --thread <id>`, a durable queue that starts a turn on an idle thread | A synthetic message to the Lead, the core operation OpenCode's own `<subagent>` notice uses |
| Unattended permission asks | A Worker parks in "Needs input" until a person attaches | No one to ask: bypass, `auto_review`, or fail | Asks wait; the Lead can list and answer them through the API |
| Lifecycle hazard | An idle session retired after about 61 minutes with no hook | Each follow-up is a new process and a new run | One idle timer per Worker; a service stop orphans every Worker's run; a Worker gets the service's environment, not the Lead's |
| Strength of the evidence | Hooks, process and stop measured; messaging documented only | Hooks measured; `exec` launch from a Lead and `codex queue` read in the source only | Root sessions made through the API measured; `opencode api`, metadata and the synthetic message read in the source only |

The evidence notes give each harness's capability matrix, risks and the
pinned experiment that would settle its unknowns.

### Against #479's criteria

#479 asks for each mechanism to be compared on each harness. Each cell names
its evidence; the evidence notes carry the detail
([Claude Code](lead-worker-claude-code-evidence.md),
[Codex](lead-worker-codex-evidence.md),
[OpenCode](lead-worker-opencode-evidence.md)), which also define their
labels: _documented_, _source_, _unmeasured_ and the rest.

| Criterion | Harness | Sub-agent Workers (today) | Root-session Workers |
| --- | --- | --- | --- |
| Cleanup precision | Claude Code | Any working Worker blocks every Worktree in the Repository (measured, ADR 0066) | Only its own Worktree (measured, #162), and, _inference_ from ADR 0066, the Repository while its reviewer runs |
| | Codex | As Claude Code; after the Lead unloads, the blocker remains with nothing shown (measured, ADR 0095) | Only its own Worktree (inference from the measured `exec` lifecycle) |
| | OpenCode | As Claude Code (measured) | Only its own Worktree (measured, #379 and #393), but a finished Worker blocks it until its finish step |
| Activity fidelity | Claude Code | `SubagentStart` and `SubagentStop` only; an early stop flickers (#472); never `waiting` | Its own turn state, `waiting` included (measured) |
| | Codex | As Claude Code; `interrupt_agent` publishes no stop | Its own turn state while `exec` runs; the run ends when `exec` exits (measured) |
| | OpenCode | Child events; never `waiting` | Its own turn state, but a pending ask reads `running` (measured), and #466 |
| Lead notification | Claude Code | `<task-notification>` wakes the Lead (measured) | `SendMessage` or `notify_when_idle` (documented, unmeasured), or a `work wait` background shell |
| | Codex | An idle Lead is never woken; a `wait_agent` loop (measured) | `codex queue` (source), held after an interrupt; or the Lead blocks in its turn |
| | OpenCode | The built-in `<subagent>` notice (measured) | A synthetic message (source), or polling the session's `outcome` and `time.idle` |
| Permission handling | Claude Code | Asks appear in the Lead (measured) | An ask parks until a person attaches; unattended postures are gated, and the commit prompt (documented) |
| | Codex | Shown in the Lead's TUI (documented) | No one to ask: the posture decides (documented and source) |
| | OpenCode | Rejected under `run` (measured); otherwise in the TUI (unmeasured) | Asks wait; the Lead can list and answer them through the API (source) |
| Sessions-pane story | Claude Code | A separate presentation: `⇢`, `not listed`, `+N` and a row kind for an ended session's retained Sub-agents | Ordinary rows grouped by a declared link |
| | Codex | As Claude Code, and Workers lost from view on unload | As Claude Code, with a new row for each follow-up run |
| | OpenCode | As Claude Code | As Claude Code, plus rows for finished Workers that stay live (#473) |
| Skill complexity | Claude Code | Assignment upkeep, avoiding `TaskStop`, `/exit` choices | Removes those; adds `--bg` launch, a shared permission class, messaging, `claude stop` and the link. _Inference_: about even |
| | Codex | Assignment upkeep, the v2 thread id report, a client kept attached, avoiding `interrupt_agent` | Removes those; adds the `exec` launch, `codex queue`, resume and binding again per follow-up, a posture and sandbox escalation. _Inference_: larger |
| | OpenCode | Assignment upkeep, staying where the Lead bound, the depth limit on reviewers | Removes those; adds API dispatch, metadata, the synthetic notice, a finish step, the environment and an ask policy. _Inference_: larger |
