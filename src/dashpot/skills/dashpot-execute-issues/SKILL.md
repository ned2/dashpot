---
name: dashpot-execute-issues
description: Execute an arc of GitHub Issues, an epic's sub-issues or a list the user gives, by landing each through a background worker in its own Dashpot Issue Worktree while you map the arc, brief workers, sequence waves, merge when allowed, and clean up. Run it only when the user invokes it by name.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: false
---

<!-- dashpot-managed-skill: dashpot-execute-issues -->

# Execute an arc of Issues

**Run this skill only when the user asked for it by name.** Its settings
hide it from the model in Claude Code, Codex and OpenCode, but OpenCode can
still load it by name. If you loaded it without being asked, stop and ask
the user.

You are the **lead**. An **arc** is the set of Issues you are landing:
either an epic's sub-issues, or a list the user gives you, usually chosen to
unblock something downstream. Each **worker** is a background sub-agent of
your session that takes one Issue to an open PR with green CI, in its own
Issue Worktree. You own the sequencing, the briefs, integration between
siblings, merging when you are allowed to, cleanup, and follow-ups.

Spend your context on decisions. Workers read the code. You read their
**hand-backs** (final reports), PR status, and the few diff hunks the next
wave builds on.

You are not the only one changing the repository. The user lands their own
PRs, keeps their own Worktrees, and may merge yours. Re-check state before
you act on it, and leave alone what you did not create.

## What this skill needs

- `git`, and `gh` authenticated for the repository. The arc's Issues are
  GitHub Issues.
- Dashpot, with its integration for your harness installed
  (`<dashpot> integrate <harness> --status`), in a repository configured as
  a Dashpot Project with GitHub as its Issue Source. Use the Dashpot
  invocation the repository prescribes, otherwise `dashpot`. If
  `<dashpot> issue show <n>` finds no Project, ask the user whether to run
  `<dashpot> init`; do not run it unasked.
- The `dashpot-issue-work` skill, which `integrate` installs beside this
  one. It owns resolving an Issue and starting, checking and ending Issue
  work. Use it for those steps; this skill does not repeat them.
- Your harness's background workers. Read your harness's section of
  [harnesses.md](references/harnesses.md) before you set up. It names how to
  launch, message, wait for and resume a worker, and the fallback where a
  mechanism is missing.

Everything specific to the repository comes from the repository itself, in
step 2.

## Rules for the whole arc

- **Only you bind, unbind, assign, create, remove and merge.** Workers share
  your Agent Session: Dashpot attributes their hooks and shells to it. A
  worker's `work start` or `work stop` would switch or end your Issue work,
  so the brief forbids every `work` command, Worktree creation and removal,
  and merging. Your one Issue Binding covers the arc. You tell Dashpot which
  Issue each worker works on with `work assign`
  ([Assign each worker](#assign-each-worker)).
- **Stay where you bound.** Never move your own session to another
  Worktree while a worker runs; [harnesses.md](references/harnesses.md)
  says what can move a session in each harness. Workers work in their
  Worktrees by giving every command its own `cd <path> && …`.
- **Remove Worktrees only when no worker is live.** Dashpot refuses to
  remove any Worktree of the repository while a session's sub-agents are
  running, and your workers are your session's sub-agents. Stop a worker
  the way [harnesses.md](references/harnesses.md) says for your harness: a
  stop Dashpot never hears of keeps that refusal up until your session
  ends.
- **Merge only with authority.** See [Merge authority](#merge-authority).
- **Keep the record on GitHub.** The arc's record goes in comments on the
  epic, or on a tracking Issue you open for a list, in the shape
  [run-records.md](references/run-records.md) defines. Keep no private
  notes file. Your scratch directory holds only working files, such as the
  filled brief template, and everything needed to resume the arc after a
  lost scratch directory is in those comments.

## 1. Map the arc

- Read every Issue in the arc with
  `gh issue view <n> --json title,body,labels,comments`. Later comments
  often override the body and move edges, and a maintainer's decision in a
  comment overrides it outright.
  - **Epic:** read the epic too, and take its sub-issues as the arc.
  - **List:** also read the Issues the list exists to unblock. They are the
    arc's **goal**, and their text says what each Issue must deliver for
    them.
- Build the graph from GitHub's own relationships: `gh api graphql` with
  each Issue's `subIssues`, `blockedBy` and `blocking`. Pull in any outside
  blocker on the critical path. For a list, check whether its Issues block
  each other; an ad-hoc list often mixes a critical-path root with
  independent work.
- Name each Issue's **float**: how far it can slip without delaying the
  goal. An Issue with float can wait for a later wave or fill spare
  capacity.
- For each blocked-by edge, name the **gated slice**: the part of the
  downstream Issue the blocker really gates. It is usually a slice, not the
  whole Issue.
- List the Worktrees that already exist (`git worktree list`). Those you
  did not create are the user's: note the files they touch, and never
  remove them. If your session already sits in a Worktree, check whether
  its work has merged (`gh pr list --state all --head <branch>`).

Done when you know the arc's Issues, its goal, the graph, the critical
path, each Issue's float, each edge's gated slice, and the user's
Worktrees.

## 2. Set up

1. **Read the repository's own instructions**: `AGENTS.md`, `CLAUDE.md`,
   the README, `CONTRIBUTING`, the PR template, and what they point at.
   Collect:
   - how a new Worktree is prepared (its dependency or bootstrap command);
   - the gates before a commit and a push, quoted verbatim, and any lighter
     variant the repository itself sanctions;
   - its review process, if it names one;
   - commit and PR conventions, including how a commit closes an Issue;
   - its merge method, and whether an agent may merge;
   - anything its checks require to be unique, such as decision-record or
     migration numbers;
   - recurring gotchas, and anything addressed to leads or parallel
     workers.
2. **Bind your session** to one Issue for the whole arc: the epic, or for a
   list its critical-path root. Follow `dashpot-issue-work`'s "Establish
   the workflow" here, in the checkout you are in now, which is the
   Worktree it asks about. Its version check confirms the installed skills
   match the installed Dashpot. Do not enter an Issue Worktree yourself.
   When it asks for a repair that must run from a checkout the user told
   you to leave alone, such as `integrate` from their main checkout, give
   the user the command rather than running it.
3. **Settle merge authority** now: see [Merge authority](#merge-authority).
4. **Reserve** anything the repository's checks require to be unique, one
   set per Issue, plus a spare, before any dispatch. Scan the integration
   branch, open PRs, the Remote-Tracking Branches after a `git fetch`, and
   every local Worktree's Branch: the user's own Worktrees take numbers too.
5. **Size the waves.** Find your harness's worker limit in
   [harnesses.md](references/harnesses.md), and split the machine's cores
   between the workers' test runs. A documentation-only Issue runs no
   suite and costs almost nothing alongside the others.
6. **Fill the brief template.** Copy
   [brief-template.md](references/brief-template.md) to your scratch
   directory and fill its per-arc placeholders, which that file lists.
   Render briefs with a script or a quoted heredoc (`<<'EOF'`): an unquoted
   heredoc runs backtick spans as commands.
7. **Post the arc map** comment ([run-records.md](references/run-records.md)).

Done when the session is bound, the reservations and the arc map are
posted, and the filled template exists.

## 3. Dispatch a wave

A **wave** is every Issue whose ungated work can start now. Read
[strategies.md](references/strategies.md) while planning each wave. It
covers starting before a blocker merges, splitting a large Issue, stacking
on an open PR, pairing a measurement with its consumers, and paying down a
flaky check.

Before dispatching, look for collisions between the wave's Issues:

- **Shared files and functions.** Give every file, function and document
  section one owner. A change to a shared core goes through you first.
- **Shared types.** A sibling that widens an enumeration others branch on
  must say so at once; the others use a generic fallback until it lands.
- **Recorded evidence.** For each recorded measurement, list the sources it
  depends on against each Issue's touched files. Where two Issues touch one
  measurement's sources, decide up front who regenerates it (whoever lands
  second) and who changes which expectation.

Write all of this into the wave block every brief of the wave shares
([brief-template.md](references/brief-template.md#the-wave-block)).

For each Issue in the wave:

1. Run `<dashpot> worktree create <n> --json` from the integration branch's
   tip, adding `--branch <name>` for the second half of a split Issue. Use
   the path, Branch and base it reports. Prepare the Worktree with the
   repository's own setup command. Do not install git hooks from a
   Worktree when every checkout shares the repository's hooks directory:
   that repoints every checkout at an environment removed with the
   Worktree.
2. Render its brief from the template, with the wave block and an
   Issue-specific block. The Issue-specific block says which gate variant
   applies, what the worker owns and reserves, what has merged and the API
   it exposes, what a sibling needs from it and when, any checkpoint, any
   pinned tool release it measures, whether verifying and closing the Issue
   is an allowed outcome, and how its commits reference the Issue.
3. Launch every worker of the wave at once, in the background, each with a
   short prompt that points at its brief. Record each worker's handle (its
   ID or task name) beside its Issue.
4. Assign each worker to its Issue, as
   [Assign each worker](#assign-each-worker) says.

Post the wave comment. Done when every startable Issue has a live, assigned
worker.

### Assign each worker

Your Issue Binding names only the arc's Issue, so on its own Dashpot shows
the arc running and the Issues your workers implement idle. An assignment
tells Dashpot which Issue a worker works on. Run it from your own checkout,
never from a worker:

```bash
<dashpot> work assign <n> --worker <worker-id> --worktree <path>
```

- **The worker's ID** is the one its launch returned, or for a Codex v2
  worker the thread ID it reports first. Your harness's section of
  [harnesses.md](references/harnesses.md) says which.
- **`--worktree`** is the Issue Worktree from step 1.
- **A refusal that lists no such sub-agent as working** means Dashpot has
  not yet recorded the worker's start, or the worker already finished. Run
  the same command again shortly, and assign each worker right after its
  launch. Never assign an ID you did not get from the launch or the worker.

The Issue then reads `running` in Dashpot's Issues pane while your hooks
report the worker working, and goes quiet when its stop is recorded. The
assignment changes nothing else: not your binding, your location, or
Cleanup's `sub-agent` blocker. `<dashpot> work show` lists every assignment
and whether its worker is still listed as working. Assignments end with
your Issue work. Maintain them as workers come and go:

- **A resumed worker** keeps its ID and its assignment.
- **A relaunched worker** has a new ID. Assign it, then
  `<dashpot> work unassign <old-id>`.
- **A worker you stopped** without its stop being recorded (see your
  harness's "Stopping") keeps its Issue reading `running`. Run
  `<dashpot> work unassign <worker-id>`.
- **A reviewer you launch as a separate worker** may be assigned to the
  Issue it reviews, the same way.
- **After you bind again**, as after a fork or an unloaded Codex lead,
  assign every live worker again. Any `work start` ends your assignments,
  even one on the arc's own Issue.

## 4. Handle each hand-back

A hand-back is a PR ready to merge, a checkpoint reached, or a blocker. A
notice that a worker stopped while it still has background work running is
not a hand-back: wait for its report. A worker that ended without a report
(stopped, killed, failed, cancelled or errored, or silent after an
interruption) is a blocker: check its Worktree and PR, then resume it or
launch a fresh worker on the same brief, assigned in the old one's place.

**PR ready.** Run the merge routine:

1. `gh pr view <pr> --json state,headRefOid,mergeStateStatus,statusCheckRollup`.
   If the user already merged it, skip to step 5. Otherwise every check
   must be `SUCCESS` and the state clean. Read CI from
   `statusCheckRollup`, never from the worker's report.
2. Read what the next wave builds on: the new public API, every changed
   decision record (a changed decision needs a new record, not an edit),
   any model that enforces a content or security rule, and for recorded
   evidence, that what it records matches the PR head.
   Tests and docs ride on the worker's independent review.
3. When the branch is several merges behind and siblings touched the same
   files, check its merge with today's integration branch in a detached
   check Worktree (`git worktree add --detach <path> <integration-branch>`,
   prepared like any other), running the touched tests and then the full
   suite. CI tests the PR head, not that merge. Keep the check Worktree for
   later checks, moving it with `git -C <path> checkout --detach <sha>`:
   Dashpot refuses to remove it while a worker is live, so it goes at
   close-out with the others.
4. With authority, merge with the repository's merge method, pinned to the
   head you checked, for example
   `gh pr merge <pr> --squash --match-head-commit <full headRefOid>`. Paste
   the full SHA. Confirm the PR shows `MERGED` and that every Issue it
   references is in the state you intended. Without authority, tell the
   user it is ready and continue from step 5 once it shows `MERGED`.
5. **Broadcast** to every live worker: the new integration-branch SHA,
   including merges the user made; what changed that touches them (renamed
   or moved names, widened types, new modules, numbers taken, recorded
   evidence whose sources changed); and whether they must rebase now, with
   any regeneration that now falls to them. This curbs merge skew: siblings
   building on a stale base, and changes that pass alone but break
   together.
6. Record the merge ([run-records.md](references/run-records.md)), and
   dispatch whatever the merge unblocked (step 3).

Merge in order of readiness, not of plan. When the PR planned to land
second is ready first, land it and move the follow-on work to the worker
still running.

**Checkpoint.** Resume the worker with one of: the merged blocker's SHA and
API; a stack instruction ([strategies.md](references/strategies.md)); or
permission to ship without the gated piece, re-homing that piece to the
blocker's worker in the same round. A worker that must wait anyway runs its
independent review on the diff it already has.

**Blocker.** Decide sequencing and ownership questions yourself. Take to
the user what needs the maintainer: a contradiction in an Issue, a
dependency or lockfile change, or a change of scope. Before you explain an
Issue's options to the user, check its terms against the repository's
glossary: an Issue's own framing can be wrong.

On every hand-back and mid-flight message:

- Verify each defect it reports with one command or one search, then file
  it at once with the repository's triage labels, so the worker's PR can
  link a durable Issue.
- Route a finding to the sibling that owns the file and the acceptance
  box, not to whoever found it.
- Approve an edit outside a worker's area explicitly, with its conditions.
- Add each new friction item to the template's gotchas, and broadcast the
  workaround to live workers at once.
- Close off optional extras a worker offers: the Issue's text sets its
  scope.
- Forward anything a sibling needs, such as a measurement or a decision,
  to that sibling at once, and post a measurement that settles a
  downstream decision to that Issue.

Anything you post publicly restates evidence. Check it against the primary
source, not against a worker's summary or your own earlier comment.

## 5. Close out

Close out each wave once all its workers have handed back, and the arc once
every Issue has merged:

1. Check every Issue's final state, and reopen any that closed early.
2. Once no worker is live, remove the Worktrees you created: `git fetch
   --prune`, then for each one
   `<dashpot> worktree remove <path> --delete-branch --delete-remote-branch --delete-ignored --dry-run`,
   then the same without `--dry-run`. A detached check Worktree has no
   Branch: check out the integration branch's tip in it first
   (`git -C <path> checkout --detach <integration-branch>`), since Dashpot
   refuses to drop a trial merge no ref reaches, then remove it with
   `--delete-ignored` alone. Confirm afterwards that the shared git hooks
   still point where they did.
3. Post each Issue's closing comment (workers draft them), including on
   Issues their PRs closed automatically.
4. File follow-ups batched from the hand-backs, each claim verified, with
   the repository's triage labels. Comment on any Issue outside the arc that
   inherits deferred scope.
5. Record the arc on its goal: for an epic, close it with a comment mapping
   each Issue to its PR; for a list, comment on each Issue the arc unblocked
   with what landed and what it now needs.
6. Post the close-out record ([run-records.md](references/run-records.md)).
   File the repository-specific lessons as Issues against its agent
   instructions, and list the lessons about this skill for the user.
7. Once every worker you launched has finished, end your Issue work as
   `dashpot-issue-work`'s "Finish the engagement" says.
8. Leave the user's main checkout as it is. Check its reflog for what moved
   it during the arc, and tell the user whether it needs updating and what
   that changes.

Done when no PR you opened is unaccounted for, no Worktree you created
remains, and the goal carries the record.

## Merge authority

You merge only when both hold:

- the user granted merge authority for this arc, in the request or when you
  asked once before the first merge; and
- the repository's instructions do not reserve merging for a person.

Otherwise each worker's job, and yours for its PR, ends with the PR open,
its validation recorded and CI green, and the user merges. Never enable
auto-merge, and never bypass a required check or protection rule.

## Reviews

Each worker gets an independent review before it opens its PR. When the
repository names a review process, the brief quotes it. Otherwise the brief
uses the bundled [reviewer prompt](references/reviewer.md), dispatched as a
sub-agent of the worker where the harness lets a worker launch one, or by
you as a separate worker where it does not
([harnesses.md](references/harnesses.md)).

## Known Dashpot gaps

Each gap is named so its workaround can be dropped once the installed
Dashpot fixes it.

- **An unloaded Codex lead ends its workers' Issue work.** A daemon-hosted
  Codex lead with no client attached is unloaded about 60 s later. Dashpot
  then ends its Issue work while its workers keep running. Their
  assignments end with it, so their Issues stop reading `running`. Keep a
  client attached to the lead until every worker has finished.
