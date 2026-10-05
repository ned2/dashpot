---
status: research
date: 2026-10-05
---

# Prior art for Lead and Worker coordination

How other systems run a lead agent's workers, coordinate them, and show them
to a person, and what that suggests for the
[Lead and Worker design](lead-worker-design.md). It covers four kinds of
prior art:

- tools that run many coding agents in parallel;
- orchestration frameworks and protocols;
- practitioners' and labs' writing on parallel coding agents;
- dashboards and agent UIs that show grouped or parent and child rows.

It was made for [Issue #479](https://github.com/ned2/dashpot/issues/479) on
2026-10-05, from published documentation, source, issue trackers and
articles, each read on that date, and revised the same day after an audit
re-read every source. A point is _documented_ when a project's own
documentation or source states it, _reported_ when it comes from someone's
account of running a system, _research_ when it comes from a published study,
and _inference_ when it is this note's reading. A vendor's claim about its
own results is marked as such.

Lowercase lead, worker and sub-agent describe other systems in their own
general sense. Capitalised, Lead, Worker and Sub-agent are Dashpot's terms
from the [domain language](../domain-language.md).

## Summary

Prior art mostly supports the design's leading candidate, with three
qualifications.

- **For Workers that each work an Issue for hours and end in a PR, systems
  use independent sessions.** OpenAI's Symphony, Anthropic's Claude
  Projects, Warp, Agent Orchestrator and workmux all run one session per
  task. Vendors also ship sub-agents that write in parallel, several in their
  own Worktrees (Claude Code's `/batch`, Codex's `worker`, OpenCode's
  `general`, Cursor), but for bulk changes inside one session, and Codex
  warns against parallel write-heavy work. So the case for root sessions
  rests on lifetime and observability, not on write safety (inference).
- **Durable state is the truth, and messages are hints.** Orchestrators
  derive a worker's state from durable records, and the bugs recur where a
  message is pushed into a live conversation (inference). Protocols poll by
  default; MCP now lets a client rely on notifications a server supports,
  while A2A says messages are not a reliable channel for critical
  information.
- **The qualifications.** First, frameworks whose workers are sub-agents
  send a worker's permission prompts to its parent, and root-session Workers
  lose that. Claude Projects, whose workers are separate sessions, makes the
  same trade as the design: it keeps each ask in its worker, runs workers in
  auto mode, and surfaces a waiting worker in its Overview. Second, agent UIs
  organise by what needs a person, not by parent, so a grouped pane must
  never hide a Worker waiting for input. Third, mature orchestrators end
  child tasks with their parent by default, so letting a Worker outlive its
  Lead has to be a stated choice; Warp is the counter-example, leaving
  children running on purpose.

## Mechanism: sub-agents or independent sessions

- **Issue-scoped work that ends in a PR uses independent sessions.**
  - [Symphony](https://github.com/openai/symphony) (OpenAI, announced
    2026-04-27) runs one Codex agent and one workspace per tracker Issue
    (documented).
  - Claude Code's [Projects](https://code.claude.com/docs/en/claude-projects)
    (public beta on claude.ai/code and the desktop app, not the CLI) is the
    closest prior art. A coordinating conversation starts threads, each "a
    separate session with its own context window"; "A cloud thread works on
    its own branch and opens a pull request when the work calls for one"
    (documented).
  - Warp's [multi-agent runs](https://docs.warp.dev/platform/orchestration/multi-agent-runs)
    start child runs that coordinate with their parent through Warp's own
    durable messaging (documented).
  - [Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator)
    (2026-02) supervises workers across harnesses, each with "its own branch
    and worktree" (documented).
  - workmux's [coordinator skill](https://workmux.raine.dev/guide/skills)
    (2026-08) "writes prompt files, spawns worktree agents, monitors their
    status, sends follow-up instructions", and `workmux wait` blocks "until
    agents reach a target status" (documented). That is the design's loop of
    a launcher, a status read and a wait, with no parent link recorded.
  - Nicholas Carlini's
    [C compiler experiment](https://www.anthropic.com/engineering/building-c-compiler)
    (Anthropic, 2026-02-05) ran 16 parallel agents, each a loop of fresh
    Claude Code sessions in its own container, about 2,000 sessions in all,
    with no orchestrator, claiming tasks by lock files synced through git
    (reported).
  - [Gas Town](https://github.com/gastownhall/gastown) runs each worker
    (polecat) as a tmux session in its own Worktree (documented).
  - Claude Code's [agent view](https://code.claude.com/docs/en/agent-view)
    lists background sessions and does not list Sub-agents as rows
    (documented).
- **Sub-agents suit reading, review and bulk changes inside one session.**
  - Anthropic's
    [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
    (2025-06-13) uses sub-agents for parallel reading, and recommends that
    they store outputs externally and pass references back (reported).
  - Writing sub-agents ship widely (documented). Claude Code's
    [`/batch`](https://code.claude.com/docs/en/agents) splits "one large
    change into 5 to 30 worktree-isolated subagents". Codex's built-in
    [`worker`](https://learn.chatgpt.com/docs/agent-configuration/subagents)
    is an "execution-focused agent for implementation and fixes", though
    Codex adds "Be more careful with parallel write-heavy workflows".
    OpenCode's [`general`](https://opencode.ai/docs/agents/) "can make file
    changes" and is recommended "to run multiple units of work in parallel".
    Cursor's [sub-agents](https://cursor.com/docs/subagents) can run in a
    Worktree or as cloud sub-agents on their own branch.
  - [CAID](https://arxiv.org/abs/2603.21489) (Geng and Neubig, 2026-03,
    revised 2026-07): a manager delegating to engineers in git Worktrees,
    merging behind tests, beat a single agent by 25.6 points on PaperBench
    and 14.7 on Commit0 (research). Its delegates run inside one harness, so
    it is evidence for isolation, not for root sessions (inference).
  - Cognition's
    [Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents)
    (2025-06-12) argues that agents writing in parallel make conflicting
    implicit decisions (vendor claim). Its follow-up,
    [Multi-Agents: What's Actually Working](https://cognition.com/blog/multi-agents-working)
    (2026-04-22), reports that fresh-context review agents work, and that a
    sub-agent does not by default write back messages for its manager to
    pass to other agents (vendor claim).
  - LangChain's
    [How and when to build multi-agent systems](https://www.langchain.com/blog/how-and-when-to-build-multi-agent-systems)
    (2025-06-16) reconciles the two: reading parallelises more readily than
    writing.
  - What a root session adds is lifetime and observability. A Claude Code
    [dynamic workflow](https://code.claude.com/docs/en/workflows)'s
    sub-agents stop with their session unless it moves to the background
    (documented), while an Issue's Worker runs through CI and review.
  - So a Worker's reviewer stays a Sub-agent under this design.
- **A sub-agent makes its parent's "idle" wrong.**
  - In [Vibe Kanban #2783](https://github.com/BloopAI/vibe-kanban/issues/2783),
    Vibe Kanban's own commit-reminder `Stop` hook fired while the parent
    waited on Sub-agents, so the task was marked idle and a stray commit was
    made (reported; the maintainer reproduced it only by backgrounding and
    abandoning tasks).
  - [agent-deck #2473](https://github.com/asheshgoplani/agent-deck/issues/2473)
    is the same class (reported).
  - This is the gap [#472](https://github.com/ned2/dashpot/issues/472)
    records.
- **Not everyone uses Worktrees.**
  - Peter Steinberger's [Just talk to it](https://steipete.me/posts/just-talk-to-it)
    (2025-10-14) runs several agents in one folder, relying on atomic
    commits (reported).
  - Simon Willison's
    [parallel coding agent lifestyle](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)
    (2025-10-05) uses fresh checkouts (reported).
  - Conductor [recommends](https://conductor.build/docs/concepts/parallel-agents)
    several agents in one workspace when the work belongs on the same branch
    (documented).
  - These choices are about workspaces, and they leave the one Issue, one
    Worktree, one PR model untouched.

## Coordination: polling, doorbells and the hand-back

- **Protocols poll by default, and differ on notifications.**
  - [MCP Tasks](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks)
    (2025-11-25, experimental) said requestors "MUST NOT rely on" status
    notifications and SHOULD keep polling `tasks/get`. The current
    [Tasks extension](https://modelcontextprotocol.io/extensions/tasks/overview)
    (`io.modelcontextprotocol/tasks`) keeps polling as the default, but "If a
    server supports notifications, clients can rely on them instead of
    polling" (documented).
  - [A2A](https://a2a-protocol.org/latest/topics/streaming-and-async/)
    describes clients typically fetching the task after a push. Its
    [specification](https://a2a-protocol.org/latest/specification/) requires
    agents to "attempt delivery at least once", lets them stop after repeated
    failures, warns that "duplicate deliveries may occur" (§4.3.3), and says
    "Messages MUST NOT be considered a reliable delivery mechanism for
    critical information" (§3.7) (documented).
  - Symphony polls its tracker every 30 seconds by default and reconciles
    running work against it, without restoring scheduler state after a
    restart (documented).
  - Conductor's [API](https://www.conductor.build/docs/api) cookbook polls a
    session's status about every 15 seconds (documented).
- **Bugs recur where a message is pushed into a live conversation
  (inference).**
  - [agent-deck](https://github.com/asheshgoplani/agent-deck), the tool
    closest to this design, has explicit parents, a persistent conductor and
    nudges on state change. Its tracker records a heartbeat that answered a
    question on the user's behalf or overwrote their draft
    ([#1981](https://github.com/asheshgoplani/agent-deck/issues/1981)), one
    that re-read an 885,000-token context on every tick
    ([#2348](https://github.com/asheshgoplani/agent-deck/issues/2348)), a
    restart that re-sent a transition for every parked child
    ([#2240](https://github.com/asheshgoplani/agent-deck/issues/2240)),
    sub-agent completions flooding the parent
    ([#2469](https://github.com/asheshgoplani/agent-deck/issues/2469)), a
    child's death never delivered
    ([#2007](https://github.com/asheshgoplani/agent-deck/issues/2007)), and
    49% of turn-journal entries duplicated over a week
    ([#2481](https://github.com/asheshgoplani/agent-deck/issues/2481)), all
    closed within days (reported).
  - Agent Orchestrator removed its idle nudges because they "re-fire
    repeatedly", "Idle does not mean done", and each "burns an orchestrator
    turn" ([#3038](https://github.com/Untrivial-ai/agent-orchestrator/issues/3038),
    reported).
  - In [Gas Town #4607](https://github.com/gastownhall/gastown/issues/4607)
    (open, 2026-07-29), mail "arrives as a **new turn**, which cancels
    whatever tool call the recipient has in flight", while a nudge "is
    **appended to an existing turn** and cannot preempt anything" (reported).
  - Claude Code's agent teams deferred a lead's inbox messages until the end
    of its turn ([#50779](https://github.com/anthropics/claude-code/issues/50779),
    reported). Its
    [cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging)
    documents messages held, refused or dropped: a held message in a `-p`
    session expires after five minutes by default, at most 100 are held, and
    identical repeats are dropped (documented).
  - [Claude Squad #266](https://github.com/smtg-ai/claude-squad/issues/266)
    lost a prompt typed before the agent was ready (reported).

  The lessons, by inference:
  - never type into a Lead that is busy or waiting;
  - deliver at most one doorbell per transition;
  - make handling idempotent, so a lost doorbell costs only latency;
  - append a doorbell at a turn boundary and never start a turn that
    pre-empts work in flight. Claude Code's cross-session messages already
    arrive "between tool calls during an active turn, so a running tool is
    never interrupted" (documented).
- **A hand-back must be idempotent.**
  - OpenCode's own Sub-agent notice carries a stable id
    ([OpenCode evidence](lead-worker-opencode-evidence.md#affordances-beyond-the-existing-experiments)).
  - LangGraph re-runs a node on resume and advises that side effects before
    an [interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts)
    be idempotent (documented).
  - By inference, a Lead keys a hand-back on the Issue, PR, head commit and
    state.
- **Lost completions are found by inconsistency, not by waiting.**
  - Gas Town's
    [polecat lifecycle design](https://github.com/gastownhall/gastown/blob/main/docs/design/polecat-lifecycle-patrol.md)
    calls this "discover, don't track". Its monitors derive state from what
    they can observe, so a lost completion message heals itself (documented).
  - Agent Orchestrator's
    [architecture](https://github.com/Untrivial-ai/agent-orchestrator/blob/main/docs/architecture.md)
    never stores display status: "It is computed at read time from durable
    facts", and "Failed probes are NOT proof of death" (documented).
  - Dashpot's equivalents, by inference:
    - a PR open while the Worker's status still says working;
    - a session ended with no status;
    - a status of done with no PR.
- **Neither the end of a turn nor a process exiting means done.**
  - [Vibe Kanban #2495](https://github.com/BloopAI/vibe-kanban/issues/2495):
    Claude Code in stream-JSON mode never exits, so runs read running
    forever (reported).
  - Conductor's API notes that a session reads idle after a prompt is
    queued, until its turn starts (documented).
  - Claude Code's [agent teams](https://code.claude.com/docs/en/agent-teams)
    document that "task status can lag".
  - Completion belongs to durable state: the Worker's `work stop`, its status
    file, or its PR.
- **The PR is the usual completion surface.**
  - GitHub's
    [Copilot cloud agent](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent)
    (formerly coding agent) "can open exactly one pull request to address
    each task it is assigned" (documented).
  - Agent view's "Ready for review" group is sessions with an open PR, and
    Claude Projects' Overview groups threads the same way (documented).
- **Briefs and results travel as files.**
  - Anthropic's research system gives each delegate an objective, an output
    format, tools and boundaries, and recommends returning results as stored
    outputs referenced by path (reported).
  - Jesse Vincent's
    [September 2025 workflow](https://blog.fsck.com/2025/10/05/how-im-using-coding-agents-in-september-2025/)
    hands off through written plan files (reported).
  - Cognition's
    [follow-up](https://cognition.com/blog/multi-agents-working) warns that
    a manager that lacks deep knowledge of the code over-prescribes to its
    children (vendor claim).
- **No common protocol covers the harnesses.**
  - The [Agent Client Protocol](https://agentclientprotocol.com/overview/agents)
    is native in OpenCode and Gemini CLI. Claude reaches it only through
    Zed's `claude-agent-acp`, which drives the Agent SDK rather than the
    user's CLI session, and Codex through `codex-acp` (documented). Gemini
    CLI stopped serving its free, Pro and Ultra users on 2026-06-18
    ([Google](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/),
    documented).
  - Its model is one client driving one agent process, not peers
    coordinating (inference).
  - Vibe Kanban speaks each harness's own protocol: Claude Code's stream-JSON
    with a permission tool, Codex's app server, an OpenCode server per run,
    and ACP for Gemini, Qwen and Copilot (source).
  - This supports a harness-neutral core built on durable state rather than
    on any one protocol.

## The link between a Lead and its Workers

- **Mature systems record the parent at launch.**
  - Temporal records a
    [child workflow](https://docs.temporal.io/child-workflows) in its
    parent's history when it starts (documented).
  - Erlang/OTP links a child to its
    [supervisor](https://www.erlang.org/doc/system/sup_princ.html) with
    `start_link` (documented).
  - In Warp, "Setting `parent_run_id` is what links the child to its
    parent", and runs a script launches from the CLI "are independent runs"
    (documented).
  - A2A has grouping (`contextId`) and `referenceTaskIds` (specification
    §3.4) but no parent field, so no hierarchy (inference).
- **agent-deck links a child automatically through an environment variable.**
  A child started with `AGENT_DECK_SESSION_ID` set takes that session as its
  parent (documented, in its CLI reference). When a controller dropped the
  parent field for a remote host's sessions, those children showed flat
  ([#2450](https://github.com/asheshgoplani/agent-deck/issues/2450)).
- **Superset scopes globally installed hooks to its own sessions.** Its
  [hooks investigation](https://github.com/superset-sh/superset/blob/main/HOOKS_INVESTIGATION.md)
  found that hooks merged into the user's global configuration fired in every
  session on the machine. The fix was to require `SUPERSET_HOME_DIR`, which
  only Superset's own terminals set (documented).
- **Claude Code already has a parent flag.** Its agent-teams split-pane
  teammates are launched with a hidden `--parent-session-id` option, "Parent
  session ID for analytics correlation" (binary, 2.1.289;
  [Claude Code evidence](lead-worker-claude-code-evidence.md#capability-matrix)).
  Whether a `--bg` launch accepts it, and whether a hook sees it, is
  unmeasured.
- **For Dashpot**, by inference: a Lead could stamp its identity into a
  Worker's launch environment, so the Worker's `work start` can confirm the
  declared link rather than take it on trust. A Worker-side record matches
  where the link is stored elsewhere, but in prior art the launcher vouches
  for it, so a Lead-side confirmation is the norm rather than an extra. The
  Claude Code and Codex evidence notes record how each harness forwards a
  launching shell's environment, which decides whether the stamp survives.

## State vocabulary and attention

- **"Waiting on a person" is a state of its own.**
  - A2A's `input-required` and `auth-required`, MCP's `input_required`,
    agent view's "Needs input" and Claude Projects' "Waiting on you" each
    name it, and in each the worker reports it rather than it being guessed
    from silence (documented).
  - Agent view also keeps Idle apart from Completed, Failed and Stopped, and
    shows process liveness on a separate glyph (documented).
- **A permission system can stop a Worker.**
  - Claude Code's auto mode pauses and resumes prompting after the
    classifier blocks "3 times in a row or 20 times total"; a `-p` run with
    no prompt to fall back to skips the action "and Claude keeps working"
    ([permission modes](https://code.claude.com/docs/en/permission-modes),
    documented).
  - Codex's [auto-review](https://learn.chatgpt.com/docs/sandboxing/auto-review)
    "interrupts the turn after `3` consecutive denials or `10` denials within
    a rolling window of the last `50` reviews" (documented).
  - By inference, that is a needs-input state to show, not a crash.
- **Cancelled, rejected and failed differ.**
  - The ACP [prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn)
    must report `cancelled` apart from errors (documented).
  - A2A adds `rejected`, for an agent that declines the task
    ([life of a task](https://a2a-protocol.org/latest/topics/life-of-a-task/),
    documented).
  - A Worker that finds its Issue not actionable is not one that crashed.
- **A terminal state is permanent.**
  - In MCP's 2025-11-25 Tasks a cancelled task stayed cancelled even if it
    later finished. The current extension makes cancellation cooperative,
    so "the task may still reach a non-`cancelled` terminal status", but a
    terminal state still never changes (documented).
  - In A2A further work on a closed task is a new task in the same context
    (documented).
  - Dashpot already ends an Agent Run and starts another; follow-up work
    after a Worker's PR is a new run.
- **Calling a Worker stalled is risky.**
  - Gas Town's polecat lifecycle design records the "Deacon murder spree"
    bug, in which stuck detection killed agents that were working, and
    concludes that false positives "are worse than slow detection"
    (documented).
  - Symphony measures a stall from the last event and retries with backoff
    (documented).
  - By inference, a passive dashboard shows "quiet for N minutes" and leaves
    the verdict to a person or the Lead.

## Presentation

- **A tree inside a column, sorted among siblings, is the closest
  precedent.**
  - htop's tree view sorts each process's direct children only, and marks a
    collapsed subtree with `+` (htop(1) and its source).
  - btop's main branch adds an option, off by default and not yet released,
    to auto-collapse a parent with many children (source, 2026-05).
  - This supports drawing connectors in a frozen leading column (the
    design's placeholder ROLE).
- **Agent UIs group by attention, not by parent.**
  - Agent view's groups are Pinned, Ready for review, Needs input, Working
    and Completed, and rows move between them as state changes
    (documented).
  - Claude Projects' Overview groups threads as Ready for review, Waiting on
    you ("need your reply or approval, or that failed"), Working, Landing,
    Idle and Resolved, and its button "shows a dot when a thread is waiting
    on you" (documented).
  - Cursor's agents window can group by status into a "Needs Attention"
    section (vendor claim,
    [staff forum answer](https://forum.cursor.com/t/agents-approval-window/170388),
    2026-09-03).
  - VS Code's [application-icon badge](https://code.visualstudio.com/docs/agents/run/sessions/manage-sessions)
    (Preview, off by default in Stable) counts sessions waiting for input or
    with failing CI on an open PR (documented).
  - [ParallelPilot](https://arxiv.org/abs/2609.33113) (2026-09-27): with an
    ambient dashboard, participants raised ticket throughput 63% in short
    coding tasks and supervised one more concurrent agent at peak (research).
  - Grouping under a Lead can bury a waiting Worker, which argues for a
    pane-level attention signal alongside the grouping. Vendor lists that
    nest related rows, such as VS Code's peer chats beneath a main row and
    Warp's children under the parent's run, show the two can coexist
    (documented; the conclusion is inference).
- **Collapsing never hides urgency.**
  - When more than three teammates are idle, Claude Code's agent-teams panel
    keeps the first three idle rows and folds the rest into one "N idle
    agents" row; working and failed teammates, and the one being viewed,
    keep their own rows (documented).
  - [k9s](https://github.com/derailed/k9s)'s xray view adds a child count to
    each parent (source), and Temporal's UI can hide child workflows behind a
    count (documented, Temporal blog, 2024-04-23).
  - So a collapsed Lead would show its most urgent Worker's state, or refuse
    to fold a Worker that needs input (inference).
  - Grafana's nested tables start collapsed, but
    [grafana#123972](https://github.com/grafana/grafana/pull/123972) added
    an option to start expanded, requested for unattended displays
    (documented). Here Workers are the point, so groups would start expanded
    (inference).
- **A declared but missing reference gets a named state.** k9s marks a
  reference to a missing resource as `TOAST_REF`, beside its colour
  (source). This supports `⇢` and `not listed` as explicit states.
- **A child's state copied from its parent's record goes stale.** A user
  reported Temporal's relationships tab showing a completed child as running,
  for a child that had been abandoned by a parent that had closed
  ([community thread](https://community.temporal.io/t/13106), 2024-08,
  reported). A Worker row's state must come from observing that Worker,
  which root-session Workers allow.
- **Mature tables keep the hierarchy out of the main list.**
  - k9s's resource tables are flat, with a jump-to-owner key and a separate
    tree view that drops the columns (documented).
  - Lens shows a
    ["Controlled By"](https://docs.lenshq.io/k8slens/using-lens/workloads/pods/)
    column (documented).
  - These tools list hundreds of rows where Dashpot lists a handful, but a
    Lead column or a jump-to-Lead key is a fallback if grouping proves
    awkward.
- **Narrow screens fold settled rows first.**
  - Agent view folds completed rows that don't fit into an "N more" row,
    while failures and sessions with an open PR always stay visible
    (documented).
  - Buildkite shows parallel
    [groups](https://buildkite.com/docs/pipelines/group-step) ungrouped when
    a build's jobs are truncated (documented).
  - With two visible rows at 80×24, folding idle Workers comes before giving
    width to connectors.
- **Textual has no tree-table** to borrow; connectors drawn in a frozen cell
  are the realistic route (inference, from a search of Textual's issues and
  community widgets).
- **Keys.** tmux's `choose-tree` expands and collapses with `+` and `-`, a
  precedent for collapsible groups (documented, tmux(1)).

## Permissions for unattended Workers

- **Frameworks whose workers are sub-agents route asks to the parent.**
  - Claude Code's agent teams show teammates' permission prompts in the lead
    (documented).
  - Codex's approval overlay shows a sub-agent's request with "the source
    thread label" (documented).
  - The OpenAI Agents SDK surfaces a nested tool's
    [approval](https://openai.github.io/openai-agents-python/human_in_the_loop/)
    on the outer run (documented).
- **Claude Projects, whose workers are sessions, keeps each ask in its
  worker.** Threads run in auto mode, "so most tool calls run without asking
  you". When one needs approval, "the prompt is inside that thread and the
  thread waits until you answer it there. Telling Claude in the project
  conversation to go ahead doesn't reach it" (documented).
  - Claude Code's cross-session messaging agrees: "a message from another
    session never counts as your consent" (documented).
  - In [Agent Orchestrator #4660](https://github.com/Untrivial-ai/agent-orchestrator/issues/4660)
    (open, 2026-08-30), a worker paused on a permission decision could
    exchange no messages with its orchestrator until a person answered in
    its terminal (reported).
  - So a root-session Worker's parked ask is found through a view, and
    Dashpot's becomes the main one.
- **Vendors answer unattended asks with a posture, not by observing them.**
  - Claude Code's auto mode, in which a classifier reviews actions in place
    of the person, is the built-in starting mode for interactive terminal
    sessions from v2.1.283. Under it, "Pushing to any branch of the
    repository you're working in and creating a pull request that matches
    your request run without a prompt" (documented). Anthropic
    [reports](https://www.anthropic.com/engineering/claude-code-auto-mode)
    a 17% false-negative rate on real overeager actions, and says it "is not
    a drop-in replacement for careful human review on high-stakes
    infrastructure" (2026-03-25, vendor claim).
  - Claude Code's `dontAsk` mode, given an allowlist, denies anything that
    would prompt; and a `--bg` session is refused bypass mode until its
    dialog has been accepted in an interactive session (documented).
  - Codex's auto-review has a reviewer agent, rather than a person, decide
    escalations (documented).
  - Third-party tools press Enter on any detected prompt (Claude Squad's
    `--autoyes`, [uzi](https://github.com/devflowinc/uzi)'s `auto`; source),
    or have a model classify the ask
    ([ccmanager](https://github.com/kbwo/ccmanager), experimental;
    documented), or relay approvals over the harness's protocol (Vibe
    Kanban; source).
  - Copilot cloud agent and
    [container-use](https://github.com/dagger/container-use) run agents in
    isolated environments, which by inference reduces what needs asking.
- **Symphony's specification** says a run "MUST NOT stall indefinitely
  waiting for user input", and "A conforming implementation MAY fail the
  run, surface the request to an operator, satisfy it through an approved
  operator channel, or auto-resolve it according to its documented policy"
  (documented). The design's open decision on permission posture is the same
  choice: set a posture at launch, route asks through a harness API, or
  accept parked Workers that Dashpot makes visible.

## Lifecycle, ended leads and Cleanup

- **What happens to workers whose lead ends is explicit elsewhere.**
  - Temporal's
    [parent close policy](https://docs.temporal.io/parent-close-policy)
    defaults to terminating a child when its parent closes. Requesting
    cancellation, or abandoning the child so that it runs on, are the other
    options, and abandonment suits asynchronous children (documented).
  - Claude Projects' Pause "stops everything at once", and Archive stops
    every thread that was running or watching a pull request (documented).
  - Warp is the counter-example: "Cancelling the parent does **not**
    automatically cancel its children. This is intentional: in many
    orchestrations, you want children to finish even after the parent ends"
    (documented).
  - A Worker driving a PR fits abandonment, but Dashpot never ends a session
    itself. So the design would show a Worker whose Lead has ended as such,
    rather than hide it, and say so deliberately.
- **Root sessions survive restarts where in-process workers do not.**
  - Agent teams document that in-process teammates are not restored on
    resume (documented).
  - Agent view's supervisor restarts crashed sessions and leaves them
    resumable after a reboot (documented).
  - A Worker launched from the Lead's shell must be detached from it:
    [Claude Code #88071](https://github.com/anthropics/claude-code/issues/88071)
    (open, 2026-08-19) reports a `run_in_background` task, a `codex exec`
    among them, killed about six minutes after its session went idle
    (reported).
- **Workspaces are kept until the work is finished.**
  - Symphony cleans a workspace only when its Issue reaches a terminal state,
    and Gas Town's polecat lifecycle design keeps the sandbox until merge
    (documented).
  - The [Codex app](https://learn.chatgpt.com/docs/environments/git-worktrees)
    keeps the most recent fifteen Worktrees by default, protects running,
    pinned and permanent ones, and snapshots one before deleting it
    (documented).
  - agent-deck separates archiving from deletion, and gives deletion an undo
    window (documented).
  - [Vibe Kanban #1571](https://github.com/BloopAI/vibe-kanban/issues/1571)
    left a run reading running after its Worktree was removed (reported).
  - All of this matches Dashpot's confirmed, preview-first Cleanup
    ([ADR 0019](../adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)),
    which refuses while a session occupies the Worktree.

## Human limits and cost

- **About three to five active Workers per person is the reported comfort
  level.** The evidence:
  - OpenAI's
    [Symphony announcement](https://openai.com/index/open-source-codex-orchestration-symphony/)
    reports that most of its engineers "could comfortably manage three to
    five sessions at a time" before Symphony (reported).
  - Addy Osmani's [parallel agent limit](https://addyosmani.com/blog/cognitive-parallel-agents/)
    (2026-04-07) is three or four (reported).
  - Willison reports reviewing one significant change at a time.
  - Agent teams' documentation suggests starting with three to five.
  - Mitchell Hashimoto's
    [AI adoption journey](https://mitchellh.com/writing/my-ai-adoption-journey)
    (2026-02-05) runs one background agent, and advises turning off agent
    notifications because context switches are expensive (reported).
  - Armin Ronacher runs fewer in parallel than he did
    ([Pragmatic Engineer](https://blog.pragmaticengineer.com/new-trend-programming-by-kicking-off-parallel-ai-agents/),
    2025-10-30).
  - ParallelPilot's participants supervised one more concurrent agent at
    peak with an attention dashboard (research).
  - Gas Town's ten or more agents depend on automated merging and several
    subscriptions (heise,
    [Full Control – Gas Town Orchestrates Ten or More Coding Agents](https://www.heise.de/en/background/Full-Control-Gas-Town-Orchestrates-Ten-or-More-Coding-Agents-11178824.html),
    2026-02-21, reported).
- **Overlapping Issues defeat parallelism.** Carlini's agents collapsed into
  overwriting each other once they all hit the same bug (reported). A Lead
  that checks Issues for overlapping files before dispatch avoids this; a
  dashboard could flag Worker Branches that touch the same files
  (inference).
- **Cost scales with sessions.** Anthropic's research system reports
  multi-agent runs using about fifteen times a chat's tokens (reported).
  Root-session Workers on one subscription share its rate limits. Claude
  Code offers no usage-limit wait in background sessions and `-p` runs, and
  a dynamic workflow's agent there fails at the limit rather than pausing
  ([interactive mode](https://code.claude.com/docs/en/interactive-mode#wait-for-a-usage-limit-to-reset),
  [workflows](https://code.claude.com/docs/en/workflows#when-a-run-hits-your-usage-limit);
  documented). Claude Projects threads instead wait and continue when the
  limit resets (documented).
- **Many tools in this space have shut down or changed in 2026**, including
  Vibe Kanban's company ([shutdown](https://www.vibekanban.com/blog/shutdown)),
  Terragon, Crystal, and Gemini CLI for its consumer tiers. Their designs are
  evidence, not endorsements.

## Suggestions for the design

Suggestions 1 to 10 are reflected in the design rather than adopted:
suggestion 1 is part of its
[pilot shape](lead-worker-design.md#the-decision-and-the-pilot), suggestion 2
shapes its [communication core](lead-worker-design.md#communication), and
the rest appear among its
[open decisions](lead-worker-design.md#open-decisions). Suggestion 11 is new
in this revision. The design records each harness's measured doorbell
against it, and Claude Code's `SendMessage` does not wait for the end of a
busy session's turn: it arrives after the current tool call.

1. Keep Workers that run for an Issue's lifetime as root sessions and
   reviewers as Sub-agents. Argue it from lifetime and observability, since
   sub-agents that write in their own Worktrees are common.
2. Derive a Worker's state from durable evidence, and treat every harness
   message as a hint that costs only latency when lost or repeated.
3. Make the hand-back idempotent, keyed on Issue, PR, head commit and state.
4. Find lost completions by inconsistency between the Worker's status, its
   session and its PR.
5. Show "quiet for N minutes" rather than calling a Worker stalled.
6. Stamp the Lead's identity into a Worker's launch environment, so the
   declared link can be confirmed; in prior art the launcher vouches for the
   link. Measure Claude Code's `--parent-session-id` as a native route.
7. Treat needs-input as a first-class state, and keep it visible whatever the
   grouping: as a pane-level count or ordering, and never folded away, as
   Claude Projects' "Waiting on you" and its Overview dot do. Count a Worker
   stopped by its permission system as needing input.
8. Start groups expanded, and fold idle or finished Workers first when space
   runs out.
9. Decide explicitly what happens to a Worker whose Lead has ended, and
   show it. Both precedents exist: Temporal and Claude Projects end
   children by default, and Warp lets them run on.
10. Show the number of active Workers per Lead, since three to five per
    person is the reported comfort level.
11. (New.) Make a doorbell append at a turn boundary and never start a turn
    that pre-empts work in flight, and check each harness's doorbell against
    that in its experiment. The #479 experiment did: none interrupts a tool
    call, but Claude Code's `SendMessage` and OpenCode's `steer` arrive
    within the running turn.
