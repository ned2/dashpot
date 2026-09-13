---
status: research
date: 2026-09-13
---

# In-loop friction: deep pass

Phase B deep pass on one feature idea from the cognitive-debt research: friction placed inside
the development loop — at task start and at every step — rather than at hand-off or merge. The
hand-off variant (quizzes, explain-it-back, merge gates) is covered separately in
[track-hand-off-checks.md](track-hand-off-checks.md). This note reads the primary sources
behind the tool modes that gate each step (plan approval, per-edit and per-command approval,
read-only and ask modes, learning styles that hand code back to the human), the interaction
research on step grain and turn-taking, generation-first and tutoring interfaces, and attempts
to carry solve.it's authorship inversion outside notebooks. It records what each mode withholds,
what the human must do before the agent proceeds, and whether it is the default. It is
documentary: no fit assessment, ranking, or recommendation. Phase A context is cited by relative
link rather than repeated. Status is as observed on 2026-09-13; tool documentation is quoted
from the live pages on that date.

## The idea

In-loop friction moves the moment of human engagement from the end of a task to its start and
to each step in between: the agent proposes a plan, an edit, a command, or a hunk and stops; the
human reads, edits, writes, or approves; the agent continues. The Phase A lineage: Litt's talk
argues that "doing it myself is how I develop understanding along the way" and imagines a
"command center" for a migration rather than a finished diff
([talk note, Proposal 3](understanding-bottleneck-talk.md#proposal-3-micro-worlds)); the
landscape sweep grouped Claude Code's Learning style, Cursor's Ask/Plan modes, quiz-blocking
skills, and AI-free days as friction and metacognitive checkpoints and observed that no seed item
"sits at task start" ([sweep, Cluster 7](landscape-sweep.md#cluster-7--friction-and-metacognitive-checkpoints));
the evidence note records that verification effort, not exposure, predicts comprehension, that
a step-by-step dialogue preserved learning where a one-shot answer did not, and that
"reading and approving" is the weakest engagement grain
([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026);
[evidence, reading and approving](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding));
solve.it's "Default Code" toggle, inert-until-promoted blocks, and absence of an automatic
follow-up prompt are the one worked example of inverting authorship inside the loop
([solveit, Product mechanics](solve-it-sweep.md#product-mechanics)); and Answer.AI's
"human in the loop at every step" claims give the philosophy behind it
([Answer.AI, Core claims](answer-ai-sweep.md#core-claims)).

## Existing modes and tools

Every mainstream agentic coding tool ships at least one step gate. What differs is the grain
(plan, file, hunk, command, token), what the gate withholds (edits, commands, code entirely),
what the human must do to release it (approve, edit, write), and whether it is on by default.
The table summarises; the entries below quote the sources.

| Tool | Mode | Withholds | Human action to proceed | Default? | Source |
| --- | --- | --- | --- | --- | --- |
| Claude Code | Manual (`default`) | writes, commands, MCP on first use | approve each prompt | on Enterprise, API-key, `-p`, cloud-provider setups; not on Pro/Max/Team (auto) | [permission modes][cc-modes] |
| Claude Code | Plan | all edits until plan approved | approve, edit (Ctrl+G), or keep planning | no | [permission modes][cc-modes] |
| Claude Code | Learning output style | 5–10 lines of code at `TODO(human)` | write the marked code | no | [output styles][cc-styles], [plugin][cc-plugin] |
| Cursor | Ask | all edits | switch to Agent | no (not stated) | [Ask mode][cur-ask] |
| Cursor | Plan | code until plan built | review/edit plan, click build | no | [Planning][cur-plan] |
| Copilot (VS Code) | Ask / Edit / Plan / Agent | edits (ask); per-file accept (edit); code until approved (plan); commands (agent, Manual) | accept per file / approve plan / approve command | Manual approval mode default | [Copilot Chat modes][gh-modes], [approvals][vsc-approvals] |
| Copilot CLI | per-tool prompt; plan mode | tool execution; code until plan | Yes / Yes for session / No + redirect | yes (prompt) | [Copilot CLI][gh-cli] |
| Codex | Ask for approval | actions outside workspace, network | approve each request | yes | [permission modes][cx-modes] |
| Codex | `/plan` | multi-step plan before code | answer plan-mode questions | no | [slash commands][cx-slash] |
| Aider | `ask` / `architect` | edits (ask); edits until architect proposal accepted | switch mode; accept (auto by default) | `code` default; `--auto-accept-architect` True | [modes][aider-modes], [options][aider-opts] |
| Cline | Plan | file changes, commands | switch to Act | no; approvals default on | [Plan & Act][cline-plan], [auto-approve][cline-auto] |
| Roo Code | Ask / Architect | edits (ask); non-markdown edits (architect) | switch mode; approve each action | Code default; all approvals manual by default | [modes][roo-modes], [auto-approve][roo-auto] |
| Kiro | Supervised | each turn with edits | accept/reject per hunk | no (Autopilot default) | [Autopilot][kiro-auto] |
| Kiro | Feature Spec | Design until Requirements approved, Tasks until Design approved | approve each phase | Feature vs Quick Spec chosen per spec | [Specs][kiro-specs], [Quick Spec][kiro-quick] |
| Devin/Cascade | Chat; Plan | edits (chat); implementation until approval (plan) | accept/insert; Implement button | no | [Cascade][dv-cascade], [changelog][dv-log] |
| JetBrains Junie | Ask; approval | edits (ask); sensitive actions | approve; per-file revert | approval on; Brave "not recommended" | [Junie plugin][jb-junie], [AI Assistant][jb-ai] |
| Zed | `confirm` tool permission; Review Changes | tool call; accept per hunk | Allow once / Always for tool | yes | [tool permissions][zed-perms], [agent panel][zed-panel] |
| Amp | `ask` action | matching tool call | confirm | built-in defaults; both modes "valid" | [permissions][amp-perms] |
| OpenCode | Plan agent | edits and bash set to `ask` | approve or Tab to Build | no (Build default) | [agents][oc-agents] |
| Continue | Chat / Plan; Ask First | tools (chat); writes (plan); each tool call | permission per tool | Ask First default | [how it works][cont-how] |
| Gemini CLI | Plan; default | edits until plan confirmed; each edit | confirm | default mode prompts | [plan mode][gem-plan] |
| Warp | Always Ask; Agent Decides | diffs and commands | review before apply | Agent Decides (not stated as default) | [agent permissions][warp-perms] |
| Antigravity | Request Review | proposed changes | explicit approval | yes | [artifact review][ag-review] |
| LangGraph | `interrupt()` | graph execution at a point | external input | library primitive | [interrupts][lg-int] |

### Claude Code

**Permission modes.** The permission-modes page tables six modes. Manual (`default`) runs
"Reads only" without prompting and is for "Reviewing every action yourself"; `acceptEdits`
auto-approves file edits so you "review changes in your editor or via git diff after the fact
rather than approving each edit inline"; `plan` reads and explores but "does not edit your
source"; `auto` runs "Everything, with background safety checks"; `dontAsk` and
`bypassPermissions` remove prompts entirely. "On Pro, Max, and Team plans, the built-in starting
permission mode is auto mode"; Enterprise, Console API key, Bedrock/Vertex/Foundry, and
`claude -p` sessions start in Manual ([permission modes][cc-modes]). The permissions page
describes Manual as "Prompts for permission on first use of each tool" ([permissions][cc-perms]).
Shift+Tab cycles default → acceptEdits → plan; `defaultMode: plan` in settings starts every
session in plan mode ([permission modes][cc-modes]).

**Plan mode as a task-start gate.** "Claude reads files, runs shell commands to explore, and
writes a plan, but does not edit your source ... edits stay blocked until you approve the plan."
The approval prompt offers three options: "Yes, and use auto mode" (or "Yes, auto-accept
edits"), "Yes, manually approve edits", and "No, keep planning". "Press Ctrl+G to open the
proposed plan in your default text editor and edit it directly" ([permission modes][cc-modes]).
The changelog records a `/plan` prefix shortcut, "Claude will now ask you questions more often in
plan mode", a dedicated Plan subagent, and the `AskUserQuestion` tool ([changelog][cc-log]).
The best-practices page recommends "Explore first, then plan, then code" and adds "Plan mode is
useful, but also adds overhead ... If you could describe the diff in one sentence, skip the
plan." It also describes Manual mode's cost: "After the tenth approval you're clicking through
rather than reviewing" ([best practices][cc-best]). (added 2026-09-13: the vendor's own
telemetry behind that sentence — 97% of prompts approved, 39% plan rejection versus 3%
per-permission rejection, blocking of dangerous commands falling from 17% to 5% after 50
prompts — is at <https://claude.com/blog/auto-mode-default-in-claude-code>; a secondary source
quotes the approval rate as 93%; see the
[literature addendum](literature-addendum.md#corrections-proposed).)

**Hooks as programmable gates.** A `PreToolUse` hook returns `permissionDecision` of `allow`,
`deny`, or `ask`; a `Stop` hook exiting 2 "Prevents Claude from stopping, continues the
conversation"; `UserPromptSubmit` can block a prompt ([hooks][cc-hooks]). The best-practices page
lists the Stop hook as "a deterministic gate" that "blocks the turn from ending until it
passes", with an override after eight consecutive blocks ([best practices][cc-best]).

**Output styles: Explanatory and Learning.** Explanatory "Provides educational 'Insights' in
between helping you complete software engineering tasks". Learning is a "Collaborative,
learn-by-doing mode where Claude will not only share 'Insights' while coding, but also ask you
to contribute small, strategic pieces of code yourself. Claude Code will add `TODO(human)`
markers". Set via `/config` (writes `.claude/settings.local.json`); `/output-style` was
deprecated in 2.1.73, removed in 2.1.91, and re-added as `/output-style [name]` in 2.1.269;
Proactive and Concise styles were added in 2.1.237 ([output styles][cc-styles];
[changelog][cc-log]). The changelog dates the styles to 1.0.81 ("new built-in educational output
styles 'Explanatory' and 'Learning'"), records deprecation in 2.0.30 and "Un-deprecate output
styles based on community feedback" in 2.0.32 ([changelog][cc-log]). Neither style is default.

The `learning-output-style` plugin in the Claude Code repository "combines the unshipped
Learning output style with explanatory functionality as a SessionStart hook". Its hook text is
the most explicit specification found of what a hand-back of authorship looks like: the model
should "identify opportunities where the user can write 5-10 lines of meaningful code that shapes
the solution", request contributions for business logic, error handling, algorithm choices, data
structures, UX decisions, and design patterns, and not for boilerplate, obvious code,
configuration, or CRUD; before requesting, "Create the file with surrounding context", "Add
function signature", and "Mark the location with TODO or clear placeholder"; insights are
formatted as "★ Insight ─────" blocks ([plugin][cc-plugin]).

### Cursor

Agent mode applies edits as it works: "Agent's edits are applied as it works. Review them in
the diff view and reject anything you don't want"; a "Restore Checkpoint" reverts to a snapshot
([Agent][cur-agent]), taken "before making significant changes" ([overview][cur-over]). Ask
mode "is a read-only mode for understanding your codebase. Agent answers questions and explores
code without making any edits"; "for questions that lead to code changes, switch back to Agent
mode" ([Ask mode][cur-ask]). Plan mode "Creates detailed implementation plans before writing any
code. Agent researches your codebase, asks clarifying questions, and generates a reviewable plan
you can edit before building"; "For quick changes ... jumping straight to Agent mode is fine"
([modes][cur-modes]). "You review and edit the plan through chat or markdown files"; "Click to
build the plan when ready" ([Planning][cur-plan]). The docs do not state which mode is default.

### GitHub Copilot

**Chat modes (VS Code and IDEs).** Ask mode answers without editing. Edit mode: "you choose
which files Copilot can make changes to ... and decide whether or not to accept the suggested
edits after each turn", with Accept/Discard per file. Agent mode: "Copilot determines which
files to make changes to, offers code changes and terminal commands to complete the task, and
iterates"; the user must "confirm whether or not Copilot can run" terminal commands. Plan mode
"does not make any code changes until the plan is reviewed and approved by you", after which
"Start Implementation" or "Open in Editor" ([Copilot Chat modes][gh-modes]).

**Approvals.** "common read-only commands run automatically, while risky commands such as `rm`
and `del` require approval"; `chat.tools.terminal.autoApprove` tunes this. Approval modes are
Manual (default), Assisted (experimental), and Allow all. Autopilot "Auto-approves all tools ...
Responds automatically to questions that would otherwise block progress"
([approvals][vsc-approvals]).

**Inline suggestions and token-level acceptance.** Tab accepts a whole suggestion; Ctrl+Right
"accept either the next word of a suggestion, or the next line"; suggestions can be snoozed or
disabled per language via `github.copilot.enable`; Next Edit Suggestions are a separate toggle
([inline suggestions][vsc-inline]).

**Copilot CLI.** Each tool call prompts "1. Yes / 2. Yes, and approve TOOL for the rest of the
running session / 3. No, and tell Copilot what to do differently (Esc)". Shift+Tab enters plan
mode, which "asks clarifying questions to understand scope and requirements, and builds a plan
before writing any code" ([Copilot CLI][gh-cli]). The earlier `gh copilot` extension (deprecated
2025-10-25) offered an "Execute command" option that asked "Are you sure you want to execute the
suggested command?" and noted that "Executed suggestions are added to your shell history"
([gh-copilot][gh-ghcop]).

**Coding agent (asynchronous).** The cloud coding agent works on issues and will "create pull
requests for you to review" — the gate is at hand-off, not in loop ([coding agent][gh-agent]).

**Learning-to-code guidance.** GitHub's guide for learners recommends custom instructions
that withhold code entirely: "I am learning to code. You are to act as a tutor; assume I am a
beginner coder. Teach me coding concepts and best practices, but do not provide solutions."
"Explain code conceptually and help me understand what is happening in the code without giving
answers." "Do not provide code snippets, even if I ask you for implementation advice." It also
recommends disabling completions with `{"github.copilot.enable": {"*": false}}` and reminds
learners to "Always check the correctness of AI-generated responses" ([learning to code][gh-learn]).
The March 2026 Copilot-for-students changelog promises "continued investment in AI-native learning
tools" without naming a feature ([students changelog][gh-students]).

### OpenAI Codex

Three permission modes. "Ask for approval" is the default: workspace-write sandbox with
`on-request` approvals, so Codex pauses before internet use or leaving the workspace. "Approve
for me" means "ChatGPT automatically reviews requests for additional access" (with the caveat
that it "can make mistakes"); "Full access" removes prompts. "changing who reviews a request
doesn't expand the sandbox" ([permission modes][cx-modes]). `approval_policy` values are
`on-request`, `never`, `on-failure`; the `untrusted` policy is retired; sandboxes are
`read-only`, `workspace-write`, `danger-full-access`, with non-VCS directories defaulting to
read-only ([approvals and security][cx-sec]). The CLI exposes `--ask-for-approval
on-request|never`, `--yolo`, and `/permissions` ("Set what Codex can do without asking first");
`--full-auto` is deprecated ([CLI reference][cx-cli]). Slash commands include `/plan` ("Toggle
plan mode for multi-step planning"), `/goal`, `/approve` ("Approve one retry of a recent
automatic-review denial"), and `/review` ([slash commands][cx-slash]). The changelog records
"clearer guidance for entering plan mode when you type plan" (app 26.210, 2026-02-10),
"notifications for plan mode questions so it's easier to notice when Codex needs input" (app
26.317, 2026-03-18), and, in CLI 0.154.0 (2026-09-09), "Use static instructions for the Default
collaboration mode", "Remove the Plan mode composer nudge", and "Retire the untrusted approval
policy" ([changelog][cx-log]).

The best-practices page frames step gates as a cost. It advises "If the task is complex,
ambiguous, or hard to describe well, ask Codex to plan before it starts coding" and "Keep
approval and sandboxing tight by default, then loosen permissions only for trusted repos", but
lists as a common mistake "Treating Codex like something you have to watch step by step instead
of using it in parallel with your own work" ([best practices][cx-best]).

### Aider

Four chat modes: `code` (default) makes edits; `ask` will "never make changes"; `architect`
uses one model to propose and another to edit; `help` answers about Aider itself
([modes][aider-modes]). `--auto-accept-architect` is "(default: True)", so the architect
proposal is applied without a confirmation step unless the flag is turned off; `--yes-always`
"Always say yes to every confirmation"; `--auto-commits` defaults to True ([options][aider-opts]).

### Cline and Roo Code

Cline's Plan mode "cannot modify any files or execute commands"; the docs say "planning first is
highly recommended"; the user switches to Act ([Plan & Act][cline-plan]). Auto-approve is a
per-category toggle (read/edit project files, read/edit all files, execute safe commands,
execute all commands, browser, MCP); commands such as `npm install <pkg>`, `rm -rf <path>`, and
`sed -i` require approval by default while `git status` and `npm test` do not; YOLO mode
"auto-approves everything: file changes, terminal commands, browser actions, MCP tools, and mode
transitions" and is documented as "dangerous" ([auto-approve][cline-auto]).

Roo Code ships Code (default), Ask (read and MCP only), Architect (edits markdown only), Debug,
and Orchestrator modes ([modes][roo-modes]). "By default, all actions require manual approval";
the auto-approve page opens with the warning that bypassing prompts "can result in data loss,
file corruption, or worse" ([auto-approve][roo-auto]).

### Kiro

"Autopilot mode (default)" applies changes without stopping. Supervised mode: "Kiro yields for
your approval after each turn that contains file edits", with per-hunk "Accept / Reject / Chat
inline" ([Autopilot][kiro-auto]). Specs run Requirements → Design → Tasks; "Tasks within a wave
execute concurrently ... Waves execute sequentially" ([Specs][kiro-specs]). Feature Spec puts an
approval gate between phases; "For well-understood features where you don't need approval gates
between phases, select Quick Spec" ([Feature specs][kiro-feature]), in which "Instead of
approving each phase before the next begins, you answer clarifying questions up front"
([Quick Spec][kiro-quick]). Best practices: "Your team benefits from explicit approval
checkpoints"; "The difference is whether you review each one before the next is generated"; a
"Run all Tasks" action removes the per-task gate ([Spec best practices][kiro-best]). Plan mode
writes no files, runs no commands, calls no MCP; "Once you approve the plan, execution begins
automatically" ([Plan][kiro-plan]).

### Windsurf Cascade and Devin desktop

Windsurf's Cascade documentation now redirects to Devin's desktop docs. Cascade has a Code mode
and a Chat mode in which "Cascade may propose new code to you that you can accept and insert"
([Cascade][dv-cascade]). The Devin desktop changelog records (v3.6.21, 2026-07-29) that "Plan
mode now works like Cascade's: the agent researches with read-only commands, keeps a persistent
Markdown plan file at `~/.devin/plans/plan-<session>.md`, and asks for approval before
implementing"; v3.8.20 (2026-08-21) adds an "explicit Implement button"; v3.9.19 (2026-09-08)
removes Cascade as a standalone product ([Devin changelog][dv-log]). Windsurf's earlier
"Planning Mode" and its command-execution settings were at first found only in secondary posts;
both were recovered from primary pages on 2026-09-13 (corrected; see Dead ends). Planning Mode
(Pro, Teams and Enterprise; on by default): Cascade "generates a local markdown file that it
refers back to throughout the project", persisted under `~/.codeium/windsurf/brain` "so it
won't be checked into version control"; "It will also try to look for approval before
implementing steps in the plan. After implementing steps, Cascade will update the plan and
summarize the changes for the user before proceeding to the next step(s)", while "a specialized
planning agent continuously refines the long-term plan" in the background
([Planning Mode, Wayback 2025-07-22][ws-plan]). Command execution has four "auto-execution
levels" — Disabled ("All commands require manual approval"), Allowlist Only, Auto ("Cascade
uses its judgment … Commands deemed potentially risky will still require your approval";
premium models only), and Turbo ("All commands are auto-executed immediately, except those in
your deny list") — plus allow and deny lists; the page now lives at Devin's desktop docs
([Terminal][dv-term]). Devin's cloud "Interactive Planning" (page since removed; Wayback
2025-06-30 and 2025-08-10) ran an "Initial Assessment" listing "Relevant files", "Key findings"
and "Implementation questions", then a "Detailed Plan" with "code citations and code snippets
that you can inspect before approving", gated by a "Wait for my approval" setting under
Settings > Customization ([Interactive Planning, Wayback][dv-plan]).

### JetBrains Junie

Ask mode runs in a "read-only capacity". Code mode "breaks the task into a multistep plan and
executes the proposed plan while reporting back"; sensitive actions "require explicit approval
from the user"; the user can "review and selectively revert the code changes file by file". Brave
mode is "not recommended. Opt for adding actions to the Action Allowlist" ([Junie plugin][jb-junie]).
The AI Assistant page lists Brave On/Off/Auto and an "Always allow" option per action
([AI Assistant][jb-ai]).

### Zed

Tool permissions fall back to `"confirm"` (the default); the legacy
`agent.always_allow_tool_actions` defaults to false. The prompt offers "Allow once / Deny once /
Always for <tool> / Always for <pattern>" ([tool permissions][zed-perms]). "Review Changes" opens
a multi-buffer where you "accept or reject each individual change hunk, or the whole set";
`agent.single_file_review` narrows it ([agent panel][zed-panel]). Profiles Write, Ask, and Minimal
scope tool sets ([profiles][zed-profiles]).

### Amp

Amp's permissions note argues that "agents work best when they can get feedback about the
changes they are making" and that "Taking tools away ... makes the agent look for an
alternative, like running a Bash command instead"; it presents autonomous and approval-based
operation as both valid. Rules map tool calls to `allow`, `reject`, `ask`, or `delegate`; when
nothing matches, "Amp checks the built-in permission list that contains sensible defaults"
([permissions][amp-perms]; [tool-level permissions][amp-tools]).

### OpenCode

Build is the "default primary agent with all tools enabled". Plan sets file edits and bash to
`ask`; Tab switches agents ([agents][oc-agents]).

### Continue

Chat has no tools, Plan is read-only, Agent has all tools. In the tool loop "The user gives
permission. This step is skipped if the policy for that tool is set to `Automatic`"; Ask First is
the default policy ([how it works][cont-how]).

### Gemini CLI

Plan mode is read-only and "will stop and wait for your confirmation" before implementation;
Shift+Tab cycles Default → Auto-Edit → Plan; approval modes are `default`, `auto_edit`, `yolo`,
`plan` ([plan mode][gem-plan]).

### Warp

"Agent will prompt you to review diffs before applying them"; profiles are Agent Decides,
Always Ask, and Always Allow; a denylist covers `rm`, `curl`, `wget`, `eval`; "Run until
completion" (Ctrl+Shift+I) bypasses prompts for a run ([agent permissions][warp-perms]).

### Google Antigravity

Request Review (default, recommended) "always halts and requests your explicit approval before
proceeding with proposed changes"; Always Proceed skips it ([artifact review][ag-review]).

### LangGraph `interrupt()`

The library primitive underneath several custom agents: `interrupt()` lets a graph "pause graph
execution at specific points and wait for external input", with documented patterns for
approval, review-and-edit of state, and tool-call review ([interrupts][lg-int]).

### What the vendors say about when to use the gates

Three vendor pages give explicit guidance on pacing, all framed around correctness and
throughput rather than the human's understanding. Claude Code: plan when "uncertain about the
approach, when the change modifies multiple files, or when you're unfamiliar with the code being
modified" ([best practices][cc-best]). Codex: plan when the task is "complex, ambiguous, or hard
to describe well"; do not "watch step by step" ([best practices][cx-best]). Kiro: Feature Spec
when "Your team benefits from explicit approval checkpoints" ([Spec best practices][kiro-best]).
Cursor: skip Plan "For quick changes" ([modes][cur-modes]). None of the pages fetched mentions
comprehension, learning, or ownership as a reason to choose a gated mode; the only vendor texts
that do are Claude Code's Learning style ([output styles][cc-styles]) and GitHub's
learning-to-code guide ([learning to code][gh-learn]).

## Step granularity and pacing

### Grains observed in tools

The catalogue above shows five grains at which a tool can stop and hand control back:

- **Task start (plan).** Claude Code, Cursor, Copilot, Codex, Cline, Kiro, Gemini CLI,
  Devin/Cascade, OpenCode. The human reads and (in Claude Code via Ctrl+G, Cursor via markdown
  files, Devin via the plan file) edits a plan before any code exists. Kiro's Feature Spec
  extends this to three gated phases ([Specs][kiro-specs]).
- **Per turn or per file.** Copilot edit mode (Accept/Discard per file, [Copilot Chat
  modes][gh-modes]); Junie's file-by-file revert ([Junie plugin][jb-junie]); Kiro Supervised
  "after each turn that contains file edits" ([Autopilot][kiro-auto]).
- **Per hunk.** Kiro Supervised's inline Accept/Reject/Chat ([Autopilot][kiro-auto]); Zed's
  Review Changes ([agent panel][zed-panel]); Cursor's diff view reject ([Agent][cur-agent]).
- **Per command or tool call.** Claude Code Manual, Copilot CLI, Codex on-request, Zed
  `confirm`, Continue Ask First, Warp Always Ask, Amp `ask`, Roo/Cline default approvals.
- **Per token or line.** Copilot inline suggestions with Ctrl+Right ([inline suggestions][vsc-inline]).

Every tool also documents the escape hatch — "Always for <tool>", "approve for the rest of the
running session", `--yes-always`, `yolo`, Autopilot, "Run until completion" — and several
document decay of attention under the fine grain: "After the tenth approval you're clicking
through rather than reviewing" ([best practices][cc-best]).

Undo rather than gate is the other pacing device: Cursor checkpoints ([overview][cur-over]) and
Claude Code's `/rewind`, which snapshots files "before each change" and is offered as an
alternative to "carefully planning every move" ([best practices][cc-best]).

### Interaction research on grain and turn-taking

**Acceleration versus exploration.** Barke, James, and Polikarpova's grounded-theory study of
20 programmers using Copilot distinguishes acceleration, where "the programmer knows what to do
next and uses Copilot to get there faster", from exploration, where the programmer is "unsure how
to proceed and uses Copilot to explore their options" ([Barke et al. 2023][barke]). The two
modes want different pacing; the paper does not measure comprehension.

**Where time goes: CUPS.** Mozannar et al. coded 21 programmers' sessions into 12 states plus
Accepted/Rejected. Of 1,024 suggestions, 34.0% were accepted; "'verifying suggestion' state
takes up the most time at 22.4%"; Copilot-specific states occupied 51.5% of session time, with
"34.3% on just double-checking and editing" ([Mozannar et al. 2024, CUPS][cups]). The companion
CDHF work learns when to withhold a suggestion, aiming to "reduce both latency and programmer
verification time" across 535 programmers, and warns that "using suggestion acceptance as a
reward signal ... can lead to suggestions of reduced quality" ([Mozannar et al. 2024, CDHF][cdhf]).

**Timing of proactive interventions.** Chen et al.'s CHI 2025 study of 65 students compared
three proactive-assistant designs. Timing rules: no suggestions while the user is interacting
or typing, a 5-second idle trigger, 20-second spacing. Test-case gains were 12.1%, 18%, and 11.6%
for Suggest-and-Preview, Suggest, and Persistent Suggest; preference was 90%, 80%, and 47%; the
persistent variant was called "distracting" and "annoying", while the gated variants "didn't
interrupt what I was doing" ([Chen et al. 2025][needhelp]). Kuo et al. instrumented 15 developers
over 229 interventions and 5,732 data points: "interventions at workflow boundaries (e.g.,
post-commit) achieved 52% engagement rates" whereas "mid-task interventions (e.g., on declined
edit) were dismissed 62% of the time"; interpreting an intervention took 45.4 s versus 101.4 s
depending on placement ([Kuo et al. 2026][kuo]).

**Agency allocation.** Feng, Yun, and Wang (CHI 2026, honorable mention) elicited senior
practice with five seniors (ACTA and Delphi), ran ten juniors through a task, and had five
seniors review. Seniors "delegated small units to AI (syntax, boilerplate, tests, formulas),
insisting on minimal, reviewable diffs"; juniors were told to be "absolutely sure of what's going
into your code before you approve it". The paper states "three non-negotiables ... (1)
interruptibility/override, (2) legible provenance ... (3) small, test-bounded diffs" and names
the practice "Preserving Individual Agency" through "incremental changes and interrupting and
verifying outputs" ([Feng et al. 2026][feng]). Cocoa lets "individual steps ... be assigned" to
user or agent in a shared plan and interleaves planning with execution (lab n=16, field n=7)
([Cocoa][cocoa]); Magentic-UI adds co-planning, co-tasking, and "action guards" that pause for
approval ([Magentic-UI][magentic]).

**Flow and trust.** Pimenova et al.'s interview corpus (~190,000 words) finds that "AI trust
regulates movement along a continuum from delegation to co-creation and supports the developer
experience by sustaining flow" ([Pimenova et al. 2025][pimenova]). Liang, Yang, and Myers' survey
of 410 developers found the main reasons for non-use were unsuitable output and that "developers
have trouble controlling the tool", recommending "minimal cognitive effort interactions ... to
reduce distractions" ([Liang et al. 2024][liang]). Sarkar et al. argue LLM-assisted programming
"ought to be viewed as a new way of programming with its own distinct properties" rather than
as pair programming ([Sarkar et al. 2022][sarkar-ppig]); Prather et al. observed CS1 students
with Copilot and report "cognitive and metacognitive difficulties" and new interaction patterns
([Prather et al. 2023][prather]).

**Interruption cost (pre-AI).** Mark, Gudith, and Klocke found that "people completed interrupted
tasks in less time with no difference in quality" but with "more stress, higher frustration, time
pressure and effort" ([Mark et al. 2008][mark]). Parnin and Rugaber, from 10,000 sessions of 86
programmers plus 414 survey responses, report that "only 10% of the sessions have programming
activity resume in less than 1 min" after an interruption and "only 7% ... involve no navigation
to other locations prior to editing" ([Parnin and Rugaber 2011][parnin]).

## Generation-first interactions

Generation-first interactions require the human to produce something — code, a prediction, an
explanation — before the tool supplies its version. Three families were found.

**Hand-back inside an agent loop.** Claude Code's Learning style is the only shipped agentic
mode found that stops mid-task and asks the human to write code: the model prepares the file,
adds the signature, marks `TODO(human)`, and waits ([output styles][cc-styles];
[plugin][cc-plugin]). The plugin's "5-10 lines of meaningful code" rule and its exclusion list
(boilerplate, configuration, CRUD) are the only published sizing heuristic. Cocoa's step
assignment is the research analogue: a plan step can be "assigned" to the user rather than the
agent ([Cocoa][cocoa]).

**Withholding solutions in tutoring tools.** CS50's duck (SIGCSE TS 2025) uses "pedagogical
guardrails to ensure responses provide constructive feedback and guidance rather than outright
solutions", reports "instruction dilution" as a failure mode, and measured leakage: 22% of 10M
responses contained code blocks, in 48% of 1.3M conversations, across 211,000 students
([Liu et al. 2025][cs50]). CodeAid (CHI 2024, 700 students) adopts a design goal to avoid direct
solutions ([CodeAid][codeaid]); CodeHelp (52 students, 12 weeks) similarly withholds full
answers ([CodeHelp][codehelp]). GitHub's learning-to-code instructions ("do not provide
solutions"; "Do not provide code snippets, even if I ask") are the same policy applied to a
general coding assistant via custom instructions ([learning to code][gh-learn]). Kazemitabaar's
step-by-step dialogue and Sankaranarayanan's explanation gate are recorded in Phase A
([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)).

**Provocateur rather than completer.** Sarkar's CACM essay proposes an AI that "does not
complete your report ... It does not write your code. Rather, it critiques your work", while
warning that "A constant barrage of criticism would frustrate users" and citing the finding that
"the more interactive the technology, the more it is perceived to contribute to critical
thinking" ([Sarkar 2024][sarkar-cacm]). The spreadsheet study operationalises this as
"provocations" and "critical shortlisting" ([Sarkar et al. 2024][sarkar-autopilot]).

**Anthropic's own usage taxonomy.** Anthropic's 2026 study of coding-skill outcomes names six
usage patterns and finds "Generation-then-Comprehension" — participants "first generated code
and then manually copied or pasted the code into their work ... then asked follow-up questions"
— among the high-comprehension patterns alongside Hybrid Code-Explanation and Conceptual
Inquiry, versus AI Delegation, Progressive AI Reliance, and Iterative AI Debugging on the low
side; it recommends "learning modes designed to foster understanding"
([Anthropic 2026][anth]). This is a within-tool pattern, not a mode, and the Phase A evidence
note gives the fuller reading ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)).

No editor or CLI feature was found that asks for a prediction before revealing output (the
predict-then-run pattern of the Phase A evidence note's generation-effect section,
[evidence, Generation effect](evidence-and-mechanisms.md#generation-effect)); Khanmigo and
OpenAI's study mode could not be reached from primary pages (see Dead ends).

## Inversion outside notebooks

The solve.it inversion has four mechanics: a "Default Code" toggle so the human authors unless
they opt in, no automatic follow-up prompt after a cell runs, inert fenced blocks that must be
promoted with a keystroke, and ghost text withheld until `⌥+.`
([solveit, Product mechanics](solve-it-sweep.md#product-mechanics)). Outside notebooks, only
fragments were found:

- **Authoring default off.** No editor or CLI documents a mode in which the agent is present but
  does not author by default. The nearest are Ask/Chat modes (Cursor, Copilot, Roo, Junie,
  Continue, Cascade), which withhold edits but still generate code in the transcript for the
  human to paste, and Claude Code's Learning style, which inverts authorship for 5–10 lines at a
  time ([output styles][cc-styles]).
- **Ghost text withheld.** Copilot's per-language disable and snooze are the closest to
  "withheld until asked" ([inline suggestions][vsc-inline]); GitHub's learning guide recommends
  disabling completions globally for learners ([learning to code][gh-learn]). No editor was found
  whose default is manual-trigger-only completions. (qualified 2026-09-13: no *editor*, but the
  most-used Neovim Copilot plugin, copilot.lua, defaults to `suggestion.auto_trigger = false`
  (<https://github.com/zbirenbaum/copilot.lua>); Zed's `subtle` mode and Visual Studio's
  manual-request option are opt-in; see the
  [discourse and tooling addendum](discourse-and-tooling-addendum.md#corrections-proposed).)
- **No automatic follow-up.** No tool documentation found describes suppressing the agent's
  next step after a command or edit; the gates above stop the agent before an action, not after
  one, and Claude Code's Stop hook works in the opposite direction (preventing a stop)
  ([hooks][cc-hooks]). (added 2026-09-13: the nearest change since is Claude Code 2.1.200, whose
  `AskUserQuestion` dialogs "no longer auto-continue by default"
  (<https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md>).)
- **Inert-until-promoted.** Copilot CLI's "Execute command" flow and `gh copilot`'s
  confirmation-then-history behaviour ([gh-copilot][gh-ghcop]) and Copilot CLI's three-option
  prompt ([Copilot CLI][gh-cli]) put a suggested shell command behind an explicit run; this is
  the terminal analogue of promoting a fenced block. ShellSage's design — suggest, human runs —
  is recorded in Phase A ([Answer.AI, Tools](answer-ai-sweep.md#tools-embodying-the-philosophy)).
- **REPL and literate workflows.** Cocoa "takes design inspiration from computational
  notebooks" for a non-notebook research agent, with assignable steps and interleaved planning
  and execution ([Cocoa][cocoa]). No CLI or editor was found that ports the notebook's
  one-cell-at-a-time cadence to agentic coding.

## Arguments and evidence

**Arguments for in-loop placement, as the sources make them.**

- Verification effort predicts comprehension; approving without verifying does not build it
  ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026);
  [evidence, reading and approving](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding)).
  In-loop gates are where verification effort is spent (CUPS: 22.4% of time verifying,
  [CUPS][cups]).
- Senior practitioners in Feng et al. prefer "small, test-bounded diffs" and "interrupting and
  verifying outputs" as the mechanism by which they stay in control ([Feng et al. 2026][feng]).
- Litt: "doing it myself is how I develop understanding along the way"
  ([Litt 2026][litt]).
- Anthropic's high-comprehension patterns are all interactive (follow-up questions, hybrid
  explanation, conceptual inquiry), and the paper recommends learning modes ([Anthropic 2026][anth]).
- Sarkar: interactivity is "perceived to contribute to critical thinking" ([Sarkar 2024][sarkar-cacm]).

**Arguments against, or costs, as the sources make them.**

- Attention decays under fine-grained approval: "After the tenth approval you're clicking
  through rather than reviewing" ([best practices][cc-best]); Codex names step-watching a
  mistake ([best practices][cx-best]).
- Mid-task interventions are dismissed 62% of the time versus 52% engagement at boundaries
  ([Kuo et al. 2026][kuo]); persistent prompting is rated "distracting" ([Chen et al. 2025][needhelp]).
- Interruption raises stress and effort even when task time does not suffer ([Mark et al. 2008][mark]);
  programmers rarely resume within a minute ([Parnin and Rugaber 2011][parnin]).
- Acceptance rate is what "drives developers' perception of productivity" ([Ziegler et al. 2022][ziegler]),
  and optimising for it "can lead to suggestions of reduced quality" ([CDHF][cdhf]).
- Restricting tools makes agents route around the restriction ([Amp permissions][amp-perms]).
- Guardrails leak: 22% of CS50 duck responses contained code despite the no-solutions policy
  ([Liu et al. 2025][cs50]).

**What has been measured.** Telemetry on where time goes (CUPS), on acceptance (Ziegler,
CUPS), and on engagement with proactive prompts by timing (Chen; Kuo); learning outcomes for
tutoring tools that withhold solutions (CS50, CodeAid, CodeHelp, and the Phase A
Kazemitabaar/Sankaranarayanan/Qiao items); usability of a co-planning agent (Cocoa). No source
found measures the comprehension effect of plan approval, per-hunk approval, or the
`TODO(human)` hand-back; the vendor pages report none.

## Open questions in the sources

- Chen et al. ask when a proactive assistant should intervene and note that the persistent
  variant, though rated poorly, still improved test performance ([Chen et al. 2025][needhelp]).
- Kuo et al. leave open whether boundary-timed interventions generalise beyond the 15
  developers and the specific intervention types studied ([Kuo et al. 2026][kuo]).
- Mozannar et al. (CDHF) flag the mismatch between acceptance as a reward signal and
  suggestion quality as unresolved ([CDHF][cdhf]).
- Feng et al. ask how junior developers acquire the senior's habit of small, verified
  delegation when the mentorship pipeline itself is being automated ("Evolving the Mentorship
  Pipeline") ([Feng et al. 2026][feng]).
- Sarkar asks how much provocation users will tolerate before frustration dominates
  ([Sarkar 2024][sarkar-cacm]).
- CS50 reports "instruction dilution" and 22% code leakage without a solution
  ([Liu et al. 2025][cs50]).
- Anthropic recommends "learning modes" but reports no evaluation of one ([Anthropic 2026][anth]);
  Claude Code's own Learning style shipped, was deprecated, and was restored "based on community
  feedback" with no published outcome data ([changelog][cc-log]).
- Amp presents autonomous and approval modes as both valid without a criterion for choosing
  ([Amp permissions][amp-perms]).

## Dead ends

- **Search tooling.** The WebSearch budget was exhausted mid-pass (200 calls, session-wide) and
  the subagent limit was reached, so discovery continued with curl against Seznam, OpenAlex,
  and Marginalia; DuckDuckGo, Bing, Brave, Yahoo, Startpage, Yandex, Google, and Baidu returned
  captchas, errors, or junk; arXiv API and Semantic Scholar rate-limited. WebFetch's summariser
  fabricated CUPS states, so exact numbers were taken with `pdftotext` from the PDFs.
- **Anthropic learning-modes announcement.** No announcement page located (anthropic.com/news
  URL 404); re-checked 2026-09-13 against the anthropic.com and claude.com sitemaps, the
  anthropic.com/news index, and Wayback's CDX index of `anthropic.com/news/*` and
  `claude.com/blog/*` — no page with "learning" in its slug exists or existed; the nearest
  posts are "Advancing Claude for Education" (2025-07-09) and "Anthropic's approach to teaching
  and learning AI", neither of which mentions the Claude Code styles. The styles are dated only
  by changelog 1.0.81 ([changelog][cc-log]), which the npm registry published on 2025-08-14.
- **Windsurf Planning Mode and Turbo/Auto/Off.** docs.windsurf.com redirects to docs.devin.ai
  and Devin's "interactive planning" page 404s. Resolved 2026-09-13: Wayback's raw mode
  (`web.archive.org/web/<ts>id_/`) returns the 2025-07-22 Planning Mode page and the
  2025-06-30 / 2025-08-10 Interactive Planning page (later captures are soft-404 shells), and
  the command-execution levels are on the live Devin desktop Terminal page that
  `docs.windsurf.com/windsurf/terminal` now redirects to ([Planning Mode][ws-plan],
  [Interactive Planning][dv-plan], [Terminal][dv-term]); the section above quotes them.
- **OpenAI study mode.** openai.com returned 403; not cited.
- **Khanmigo and Cursor education modes.** No primary page found for a Khanmigo coding mode or
  any Cursor learning mode; nothing cited.
- **Copilot for Students "AI-native learning tools".** Named but unspecified in the changelog
  ([students changelog][gh-students]).
- **Kiro spec approval prompt wording.** The approval prompt text between spec phases is not on
  the pages fetched; kiro.dev/docs/specs/concepts 404s. Re-checked 2026-09-13: the
  Requirements-First page ([Requirements-First][kiro-rf]) describes the gate only as "Confirm when requirements
  meet your needs" and "Once you confirm the requirements, Kiro generates a design.md" (the
  Design-First page 404s), Kiro's GitHub organisation (`kirodotdev`) contains no prompt text,
  and the verbatim line circulating as Kiro's ("Does the requirements document look good? If so,
  we can move on to the design") appears only in third-party system-prompt dumps (a GitHub code
  search finds it in ~660 repositories, none Kiro's). Still unverified against a Kiro source.
- **Amp manual.** The manual's permissions section lacks detail; the notes pages are cited instead.
- **dl.acm.org.** Returned 403 throughout; Vaithilingam et al. (CHI EA 2022, doi
  10.1145/3491101.3519665) and the Feng et al. DOI landing page were not readable, so
  Vaithilingam is not cited in the body and Feng is cited from the author PDF.
- **Jupyter AI magics page.** 404; no non-solve.it notebook evidence added.
- **Withheld ghost text by default.** No editor found with manual-trigger-only completions as
  default; only Copilot's disable/snooze and GitHub's learner guidance (qualified 2026-09-13:
  the copilot.lua plugin does; see [Inversion outside notebooks](#inversion-outside-notebooks)).
- **No automatic follow-up.** No non-notebook tool found that documents suppressing the next
  agent action after a step.
- **Comprehension effect of step gates.** No study found that measures understanding as a
  function of plan/hunk/command approval; the closest are CUPS verification time and the
  proactive-timing studies.

## References

[cc-modes]: https://code.claude.com/docs/en/permission-modes
[cc-perms]: https://code.claude.com/docs/en/permissions
[cc-hooks]: https://code.claude.com/docs/en/hooks
[cc-styles]: https://code.claude.com/docs/en/output-styles
[cc-plugin]: https://github.com/anthropics/claude-code/tree/main/plugins/learning-output-style
[cc-log]: https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
[cc-best]: https://code.claude.com/docs/en/best-practices
[cur-modes]: https://cursor.com/docs/agent/modes
[cur-plan]: https://cursor.com/docs/agent/planning
[cur-ask]: https://cursor.com/help/ai-features/ask-mode
[cur-agent]: https://cursor.com/help/ai-features/agent
[cur-over]: https://cursor.com/docs/agent/overview
[gh-modes]: https://docs.github.com/en/copilot/using-github-copilot/copilot-chat/asking-github-copilot-questions-in-your-ide
[vsc-approvals]: https://code.visualstudio.com/docs/agents/approvals
[vsc-inline]: https://code.visualstudio.com/docs/copilot/ai-powered-suggestions
[gh-cli]: https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli
[gh-ghcop]: https://github.com/github/gh-copilot
[gh-agent]: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent
[gh-learn]: https://docs.github.com/en/get-started/learning-to-code/setting-up-copilot-for-learning-to-code
[gh-students]: https://github.blog/changelog/2026-03-13-updates-to-github-copilot-for-students/
[cx-modes]: https://developers.openai.com/codex/permission-modes
[cx-sec]: https://developers.openai.com/codex/agent-approvals-security
[cx-cli]: https://developers.openai.com/codex/cli/reference
[cx-slash]: https://developers.openai.com/codex/reference/slash-commands
[cx-log]: https://developers.openai.com/codex/changelog
[cx-best]: https://developers.openai.com/codex/learn/best-practices
[aider-modes]: https://aider.chat/docs/usage/modes.html
[aider-opts]: https://aider.chat/docs/config/options.html
[cline-plan]: https://docs.cline.bot/features/plan-and-act
[cline-auto]: https://docs.cline.bot/features/auto-approve
[roo-modes]: https://roocodeinc.github.io/Roo-Code/basic-usage/using-modes
[roo-auto]: https://roocodeinc.github.io/Roo-Code/features/auto-approving-actions
[kiro-auto]: https://kiro.dev/docs/ide/chat/autopilot/
[kiro-specs]: https://kiro.dev/docs/specs/
[kiro-feature]: https://kiro.dev/docs/specs/feature-specs/
[kiro-quick]: https://kiro.dev/docs/specs/quick-spec/
[kiro-best]: https://kiro.dev/docs/specs/best-practices/
[kiro-plan]: https://kiro.dev/docs/specs/plan/
[dv-cascade]: https://docs.devin.ai/desktop/cascade
[dv-log]: https://docs.devin.ai/desktop/changelog
[dv-term]: https://docs.devin.ai/desktop/terminal
[dv-plan]: https://web.archive.org/web/20250810154151/https://docs.devin.ai/work-with-devin/interactive-planning
[ws-plan]: https://web.archive.org/web/20250722063053/https://docs.windsurf.com/windsurf/cascade/planning-mode
[kiro-rf]: https://kiro.dev/docs/specs/feature-specs/requirements-first/
[jb-junie]: https://junie.jetbrains.com/docs/junie-ide-plugin.html
[jb-ai]: https://www.jetbrains.com/help/ai-assistant/junie-agent.html
[zed-perms]: https://zed.dev/docs/ai/tool-permissions
[zed-panel]: https://zed.dev/docs/ai/agent-panel
[zed-profiles]: https://zed.dev/docs/ai/agent-profiles
[amp-perms]: https://ampcode.com/notes/permissions
[amp-tools]: https://ampcode.com/news/tool-level-permissions
[oc-agents]: https://opencode.ai/docs/agents/
[cont-how]: https://docs.continue.dev/ide-extensions/agent/how-it-works
[gem-plan]: https://geminicli.com/docs/cli/plan-mode/
[warp-perms]: https://docs.warp.dev/agent-platform/capabilities/agent-profiles-permissions/
[ag-review]: https://antigravity.google/docs/artifact-review/
[lg-int]: https://docs.langchain.com/oss/python/langgraph/interrupts
[anth]: https://www.anthropic.com/research/AI-assistance-coding-skills
[barke]: https://arxiv.org/abs/2206.15000
[cups]: https://arxiv.org/abs/2210.14306
[cdhf]: https://arxiv.org/abs/2306.04930
[needhelp]: https://arxiv.org/abs/2410.04596
[kuo]: https://arxiv.org/abs/2601.10253
[feng]: https://www.bhadayun.com/papers/fromjuniortosenior.pdf
[cocoa]: https://arxiv.org/abs/2412.10999
[magentic]: https://arxiv.org/abs/2507.22358
[pimenova]: https://arxiv.org/abs/2509.12491
[liang]: https://arxiv.org/abs/2303.17125
[sarkar-ppig]: https://arxiv.org/abs/2208.06213
[prather]: https://arxiv.org/abs/2304.02491
[sarkar-cacm]: https://www.microsoft.com/en-us/research/wp-content/uploads/2024/03/CACM_2024_AI_provocateur_MSFT_internal_preprint.pdf
[sarkar-autopilot]: https://arxiv.org/abs/2412.15030
[ziegler]: https://arxiv.org/abs/2205.06537
[cs50]: https://cs.harvard.edu/malan/publications/fp0627-liu.pdf
[codeaid]: https://arxiv.org/abs/2401.11314
[codehelp]: https://arxiv.org/abs/2308.06921
[mark]: https://ics.uci.edu/~gmark/chi08-mark.pdf
[parnin]: https://chrisparnin.me/pdf/parnin-sqj11.pdf
[litt]: https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck
