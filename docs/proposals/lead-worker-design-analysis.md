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

[ADR 0124](../adr/0124-keep-sub-agent-workers-and-qualify-root-session-workers-per-harness.md)
decided #479 on 2026-10-05: sub-agent Workers stay, and root-session Workers
are qualified one harness at a time, Claude Code first through a pilot. This
analysis stays as the comparison behind that decision.

This revision, made on 2026-10-05, reads the code and documents at `main`
c8069ac, which is both this branch's HEAD and its merge base with
`origin/main`, and the state of the Issues on that day. `origin/main` has
since reached 4110b53, which adds ADR 0107 (#460) and ADR 0109 (#459); those
are cited by number. It also reads upstream documentation, source and release
binaries. It corrects the facts the
[2026-10-05 review](../reviews/lead-worker-design-review-2026-10-05.md)
found stale or wrong, without changing a lean or recommendation. Nothing here
was run for this analysis. A statement marked _measured_ was observed by an
earlier Dashpot experiment, which the statement or its evidence note links;
_measured (#479)_ marks the
[root-session Workers experiment](../spikes/root-session-workers-spike.md),
whose Claude Code, Codex and OpenCode runs have all reported. One marked _inference_ is reasoning no source states directly.

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
  ([`agent_runs.py`](../../src/dashpot/sessions/agent_runs.py),
  [`hook_scan.py`](../../src/dashpot/sessions/hook_scan.py)), `work show`
  and Cleanup
  ([`obstacles.py`](../../src/dashpot/repository/cleanup/obstacles.py)) see
  them. And a Worker Assignment ends with its Lead's run, while an ended
  session's Sub-agents stay listed
  ([ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md))
  in a record no pane shows. So after a Codex Lead unloads, its Workers drop
  out of the Issues pane
  ([#492](https://github.com/ned2/dashpot/issues/492)), and they never appear
  in the Sessions pane, while Cleanup still refuses; since ADR 0112 the
  Cleanup dialog names each such session and its Sub-agent count.
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
| A working Worker blocks Cleanup of every Worktree in the Repository while it works ([ADR 0066](../adr/0066-block-worktree-removal-while-a-sub-agent-is-working.md); [#478](https://github.com/ned2/dashpot/issues/478)). Since [ADR 0112](../adr/0112-let-a-person-remove-a-worktree-despite-the-sub-agents-a-preview-lists.md) (#476) a person can lift those blockers with a Sub-agent Override; no agent gives it, so a Lead's own close-out still waits for every Worker | No hook places a Sub-agent, so occupancy blocks on any session with live Sub-agents | **Gone for Workers.** A Worker occupies only its own Worktree, as an ordinary Agent Session with an Agent Run. **Remains** while a Worker's own reviewer Sub-agent runs, when every Worktree shows the `sub-agent` blocker again (measured on Claude Code and OpenCode, #479); every Worker reviews |
| Issue attribution is declared, not observed ([ADR 0096](../adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)); `work assign` can race; a Codex v2 Worker must report its own thread id | A Sub-agent shares the Lead's Agent Session, so [ADR 0009](../adr/0009-hold-one-agent-run-per-session-across-worktrees.md) gives it no run of its own | **Gone.** The Worker's own `work start` gives it an Issue Binding at an observed location |
| Worker activity flickers ([#477](https://github.com/ned2/dashpot/issues/477), [#472](https://github.com/ned2/dashpot/issues/472)) | Activity comes from `SubagentStart` / `SubagentStop`, and an interim stop fires while background work runs | **Mostly gone.** The session's own turn state applies, and [ADR 0016](../adr/0016-hold-a-session-running-while-its-sub-agents-work.md) holds it running while its reviewers work. **Remains** in part: [ADR 0113](../adr/0113-name-a-background-command-by-its-process-and-show-it-on-a-waiting-claude-code-session.md) ([#466](https://github.com/ned2/dashpot/issues/466)) measured that a Claude Code or OpenCode session reads `waiting` while a Background Command runs, such as a Worker's `gh run watch`; the Claude Code display of it is [#517](https://github.com/ned2/dashpot/issues/517), blocked by #479. `codex exec` ends its Background Commands when it exits, so an `exec` Worker watches CI in the foreground |
| Listings that are never dropped ([#475](https://github.com/ned2/dashpot/issues/475), [#429](https://github.com/ned2/dashpot/issues/429), [#394](https://github.com/ned2/dashpot/issues/394), [ADR 0095](../adr/0095-keep-an-ended-sessions-sub-agents-listed-until-they-stop.md)) | Some Sub-agent stops are never published | **Gone for Workers.** A root session ends on positive evidence. **Remains** for reviewers |
| Listings that must follow the Lead across records and Host Processes ([ADR 0097](../adr/0097-carry-a-live-sessions-sub-agents-through-its-own-session-start.md), [ADR 0101](../adr/0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md), [ADR 0102](../adr/0102-clear-a-stopped-sub-agent-from-the-records-a-moved-session-left-behind.md), and ADR 0109 and ADR 0107 since, for [#459](https://github.com/ned2/dashpot/issues/459) and [#460](https://github.com/ned2/dashpot/issues/460); a Codex Lead's unload, [#492](https://github.com/ned2/dashpot/issues/492)) | The Workers' listing lives in the Lead's record | **Gone for Workers.** A Lead's moves, compactions, conversation switches and unloads no longer touch Worker records, and the skill's rules to stay where the Lead bound and to keep a client attached to a Codex Lead fall away. **Remains** for reviewers |
| The Sessions pane needs a separate Worker presentation ([#444](https://github.com/ned2/dashpot/issues/444)) | A Worker is not an Agent Session | **Mostly gone.** Workers are ordinary rows, and #444 reduces to grouping them by their Lead. **New**: more rows, and [#473](https://github.com/ned2/dashpot/issues/473) clutter from OpenCode Workers that stay live after they finish |
| Skill complexity: assignment upkeep, avoiding `TaskStop` and `interrupt_agent`, the Lead launching reviewers where nesting is limited, the choices at `/exit` | Sub-agent mechanics | **Mostly gone.** _Inference_: a root Worker launches its own reviewer, and a harness's limits on concurrent Sub-agents apply per Worker |

## What root-session Workers cost

- **N1. Completion notices are lost.** Claude Code's `<task-notification>`,
  Codex's final answer and OpenCode's `<subagent>` notice belong to
  Sub-agents. Codex never woke an idle Lead anyway.
- **N2. The hand-back needs its own transport.**
- **N3. A Lead message to a Worker needs a harness's own way in, and some
  carry hazards.** At 2.1.285, a `claude -p --resume <id>` against a running
  `--bg` session published a `SessionEnd` from another process, which only
  #326's record of the `--bg` session's Host Process guards against. At
  2.1.289 a `claude -p` that exits published no `SessionEnd` at all
  ([#518](https://github.com/ned2/dashpot/issues/518)), so what a `-p` route
  publishes now is open. Claude Code's `SendMessage` reaches a busy `--bg`
  Worker inside its running turn, after the current tool call (measured,
  #479). A Codex Lead cannot queue to a running `exec`
  Worker: the mail is consumed at the Worker's shutdown and lost (measured,
  #479). An OpenCode `SessionStart` from a second Host Process once dropped a
  session's Sub-agent listing while the child still worked
  ([#460](https://github.com/ned2/dashpot/issues/460)); ADR 0107, on `main`
  after this branch's base, fixed it.
- **N4. Permission asks in unattended sessions.** #162 measured
  `claude --bg` only with permission checks bypassed; auto, Claude Code's
  default permission mode since 2.1.283, and `dontAsk` also work with
  `--bg`, only bypass needs an interactive acceptance first, and auto falls
  back to prompting after 3 blocks in a row or 20 in total (documented).
  #479 ran manual, `dontAsk` and auto Workers too: a message between the
  bypass class and the prompting class is held, and a Worker blocked on an
  ask lists in `claude agents --json` as waiting for a permission prompt
  while Dashpot reads its run as `running` (measured, #479). OpenCode `run`
  rejects asks; a Lead answering through the API finds that `reject` cancels
  every pending ask in the session, and `always` saves a Project-wide rule
  (measured, #479). A Codex `exec` has no one to ask, and an `auto_review`
  approval is a model's, not a person's consent.
- **N5. Lifecycle hazards.** Claude Code retires an idle `--bg` session about
  61 minutes after its last `Stop` and publishes no hook, so its run is
  orphaned until someone attaches. A `--bg` Worker sent SIGTERM publishes
  `SessionEnd`, which ends its run, before its supervisor resumes the same
  session, so the resumed Worker must `work start` again (measured, #479). A Codex daemon thread with no subscriber
  unloads after 60 seconds and publishes `SessionEnd`; that applies to a
  daemon-hosted Lead, not to an `exec` Worker. A Codex `exec` Worker sent
  SIGTERM or SIGKILL publishes nothing and leaves an Orphaned Agent Run that
  blocks its Worktree (measured, #479). An OpenCode service stop orphans
  every Worker's run; the restarted service resumes the turns it cut off,
  unseen by Dashpot's plugin, so the run stays orphaned and the resumed
  turn's `work start` is refused as stale until a fresh prompt, and a pending
  ask is lost (measured, #479).
- **N6. Workers must be torn down before Cleanup.** A finished root session
  that is still live keeps its Worktree occupied. OpenCode Workers, and
  daemon-hosted Codex Workers, share their service or daemon Host Process
  ([ADR 0067](../adr/0067-observe-conversations-apart-from-the-runtimes-that-serve-them.md)),
  so that process's liveness never frees them. A Codex `exec` Worker is its
  own Host Process
  ([ADR 0072](../adr/0072-keep-every-codex-host-process-non-exclusive.md)),
  so its exit ends its run and frees its Worktree with no teardown
  (measured, #479). Deleting an OpenCode session discards its history.
- **N7. No harness links a root session to its Lead in a record Dashpot
  reads.** Claude Code's hidden `--parent-session-id`, "Parent session ID for
  analytics correlation", launches agent-teams split-pane teammates; whether
  a `--bg` launch accepts it or a hook sees it is unmeasured. Warp, outside
  Dashpot's harnesses, records `parent_run_id`
  ([prior art](lead-worker-prior-art.md#the-link-between-a-lead-and-its-workers)).
  Identity is never inferred
  ([ADR 0038](../adr/0038-isolate-native-agent-session-identities.md)), so the
  link has to be declared. Today's code would not keep a link stored on a
  Worker's run past its `work stop`; the design's
  [Lead link](lead-worker-design.md#the-lead-link) lists what it must handle.
- **N8. Workers would run `work start` and `work stop`.** ADR 0092 says a
  Worker runs no `work` command. In a mix of the two mechanisms, a Claude
  Code sub-agent Worker's `work stop` would still end its Lead's run, since it
  shares the Lead's session identity, so the two briefs must differ. A Codex
  Sub-agent's shell claims a delegate identity whenever its thread id differs
  from its session id
  ([`harnesses.py`](../../src/dashpot/sessions/harnesses.py), `_codex_claim`),
  which `work` refuses
  ([`session_identity.py`](../../src/dashpot/sessions/session_identity.py),
  `_refuse_delegate`), and
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
| D. The Lead polls Dashpot (`work show`, or a new `work wait`) from a background shell; the Worker's `work stop` or its session ending is completion, and its run becoming orphaned needs attention ([Orphaned Agent Run](../domain-language.md#observation)) | High for ending, which is an explicit act or positive evidence; silent stops don't matter | The poll interval; a finished background shell wakes a Claude Code or OpenCode Lead ([OpenCode, measured](../spikes/opencode-v2-background-permissions-spike.md)), though a `-p` or Agent SDK Claude Code Lead's background command is limited to 30 minutes by default and 2 hours at most (documented), while Codex must block inside its turn | Not addressed | Reads only | Low: only the waking differs |
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

Three caveats remain with root-session Workers:

- [ADR 0113](../adr/0113-name-a-background-command-by-its-process-and-show-it-on-a-waiting-claude-code-session.md)
  ([#466](https://github.com/ned2/dashpot/issues/466)) measured that a Claude
  Code or OpenCode session reads `waiting` while a Background Command runs,
  which covers a Worker's `gh run watch` and a Claude Code Lead's background
  `work wait`. The Claude Code display is
  [#517](https://github.com/ned2/dashpot/issues/517), blocked by #479; no
  OpenCode fix is decided. A Codex `exec` Worker cannot leave a command in
  the background at all.
- While a Worker's reviewer Sub-agent runs, every Worktree of the Repository
  shows the `sub-agent` blocker again (measured on Claude Code and OpenCode,
  #479).
- The domain language avoids "worker" for Claude Code's supervised worker
  process, and running Workers as `--bg` sessions would make that collision
  constant.

## The harnesses compared

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Best root-session mechanism | `claude --bg` started in the Issue Worktree | Detached `codex exec -C <worktree>`, launched from a full-access or escalated shell | A root session on the shared service, made with `opencode api POST /api/session` |
| Can a Sub-agent be given its own Worktree? | Only Claude Code's own `.claude/worktrees/` through `isolation: "worktree"`; the Agent tool's `cwd` is withheld from the model | No: a spawned agent always takes its parent's working directory | No: a child takes its parent's location |
| Waking the other party | Cross-session `SendMessage`, with `notify_when_idle`: a new turn for an idle session, delivery inside the running turn for a busy one, and an idle notice that quotes the Worker's final text (measured, #479) | `codex queue --thread <id>`, a durable queue that starts a turn on an idle thread, from Worker to Lead and from an unsandboxed shell only; mail to a running `exec` Worker is lost, so the Lead resumes it instead | A synthetic message to the Lead, the core operation OpenCode's own `<subagent>` notice uses, which wakes an idle Lead and steers a busy one |
| Unattended permission asks | A Worker parks in "Needs input" until a person attaches, and Dashpot reads it as `running` (measured, #479); auto, the default mode since 2.1.283, works with `--bg`; messages across the bypass and prompting classes are held (measured, #479) | No one to ask: full access, `--approve-for-me`, `-c approvals_reviewer=auto_review`, or fail; every resume restates the posture | Asks wait; the Lead can list and answer them through the API, where `reject` cancels every pending ask and `always` saves a Project-wide rule; a service stop loses them |
| Lifecycle hazard | An idle session retired after about 61 minutes with no hook; a SIGTERM respawn loses the Issue Binding; every Worker gets the environment of the shell that first started the supervisor, not the Lead's (measured, #479) | Each follow-up is a new process and a new run; SIGTERM or SIGKILL orphans the run | One idle timer per location; a service stop orphans every Worker's run, and a turn the restarted service resumes cannot bind again until a fresh prompt; a Worker gets the service's environment, not the Lead's |
| Strength of the evidence | Measured (#479) at 2.1.287 and 2.1.289: identity, environment, occupancy, messaging both ways, permission classes and asks, the commit instruction, `claude stop` and a SIGTERM respawn; hooks, process and idle eviction measured before (#162, #326) | Measured (#479): launch, identity, `codex queue` both ways, resume and its posture, signals, a daemon restart and a sandboxed Lead | Measured (#479): dispatch with metadata, the synthetic message, asks and replies, the finish, a service restart and a standalone Lead; root sessions made through the API measured before |

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
| Cleanup precision | Claude Code | Any working Worker blocks every Worktree in the Repository (measured, ADR 0066); a person can override it (ADR 0112) | Only its own Worktree, and the Repository while its reviewer runs (measured, #479; #162 had measured only the `--bg` lifecycle); a Worker still live after its `work stop` blocks its Worktree by session and process until `claude stop` (measured, #479) |
| | Codex | As Claude Code; after the Lead unloads, the blocker remains with nothing shown (measured, ADR 0095) | Only its own Worktree, freed when `exec` exits (measured, #479) |
| | OpenCode | As Claude Code (measured) | Only its own Worktree (measured, #379, #393 and #479), but a finished Worker blocks it until its finish step, and the Repository is blocked while its reviewer runs (measured, #479) |
| Activity fidelity | Claude Code | `SubagentStart` and `SubagentStop` only; an early stop flickers (#472); never `waiting` | Its own turn state, `waiting` included (measured), but a Worker blocked on a permission prompt reads `running` (measured, #479) |
| | Codex | As Claude Code; `interrupt_agent` publishes no stop | Its own turn state while `exec` runs; the run ends when `exec` exits (measured) |
| | OpenCode | Child events; never `waiting` | Its own turn state, but a pending ask reads `running` (measured), a Background Command reads `waiting` (ADR 0113), and a turn the restarted service resumes is not seen to start (measured, #479) |
| Lead notification | Claude Code | `<task-notification>` wakes the Lead (measured) | `SendMessage` or `notify_when_idle` (measured, #479), or a `work wait` background shell, which a `-p` or Agent SDK Lead's 30-minute default, 2-hour maximum background-command limit cuts short (documented) |
| | Codex | An idle Lead is never woken; a `wait_agent` loop (measured) | `codex queue` from an unsandboxed Worker shell (measured, #479): at once to an idle or busy daemon-hosted Lead, held until resume for an unloaded one, and held after an interrupt (source); or the Lead blocks in its turn |
| | OpenCode | The built-in `<subagent>` notice (measured) | A synthetic message (measured, #479), or polling the session's `outcome` and `time.idle` |
| Permission handling | Claude Code | Asks appear in the Lead (measured) | An ask parks until a person attaches; only bypass is gated, and auto, the default since 2.1.283, works with `--bg`; messages within the bypass or the prompting class deliver, and across them are held (measured, #479); a `--bg` session is instructed to ask before committing in a Worktree it did not enter itself, which the brief can override (documented; the instruction read in the 2.1.289 binary) and `worktree.bgIsolation: "none"` removes (measured, #479) |
| | Codex | Shown in the Lead's TUI (documented) | No one to ask: the posture decides (documented and source), and a bare resume drops it (measured, #479) |
| | OpenCode | Rejected under `run` (measured); otherwise in the TUI (unmeasured) | Asks wait; the Lead can list and answer them through the API (measured, #479), where `reject` cancels every pending ask and `always` saves a Project-wide rule; a service stop loses them |
| Sessions-pane story | Claude Code | A separate presentation: `⇢`, `not listed`, `+N` and a row kind for an ended session's retained Sub-agents | Ordinary rows grouped by a declared link |
| | Codex | As Claude Code, and Workers lost from view on unload | As Claude Code, with a new row for each follow-up run |
| | OpenCode | As Claude Code | As Claude Code, plus rows for finished Workers that stay live (#473) |
| Skill complexity | Claude Code | Assignment upkeep, avoiding `TaskStop`, `/exit` choices | Removes those; adds `--bg` launch, a shared permission class, messaging, `claude stop` and the link. _Inference_: about even |
| | Codex | Assignment upkeep, the v2 thread id report, a client kept attached, avoiding `interrupt_agent` | Removes those; adds the escalated `exec` launch, `codex queue` with a fallback for a sandboxed Worker, resume with the posture restated and binding again per follow-up, a posture, and stopping with SIGINT. _Inference_: larger |
| | OpenCode | Assignment upkeep, staying where the Lead bound, the depth limit on reviewers | Removes those; adds API dispatch, metadata, the synthetic notice, a finish step, the environment, an ask policy, and a fresh prompt to each Worker after a service restart. _Inference_: larger |
