# Throughput strategies

Reference for planning a wave in [dashpot-execute-issues](../SKILL.md). Each
entry gives when it pays, how to run it, and its cost. The evidence comes
from the arcs this skill was refined on; in one, eight PRs landed in about
five hours, against six and a half or more one after another.

## Self-review by the worker

**When:** always.

**How:** the worker gets its own independent review, through the
repository's review process or the bundled [reviewer prompt](reviewer.md),
addresses the findings, and gets a focused follow-up review of its fixes.
The brief tells it to report back, not to skip review, if it cannot get the
reviewer.

**Evidence:** every PR of the first arc was reviewed this way, and the lead
never needed a reviewer of its own.

## Fast-track: start before the blocker merges

**When:** the gated slice is small, or the blocker is short compared with
the downstream Issue.

**How:**

- Brief the worker to build the ungated slice first, keeping the gated seam
  behind one function, so adopting the blocker is a one-line change.
- Set a **checkpoint** before the final gate: `git fetch`, then check
  whether the blocker has merged. If it has, rebase and use the new
  integration-branch tip as the review base. If it hasn't, report back with
  two offered exits: wait, or ship without the gated piece.
- When the blocker merges early, send the worker its API mid-flight so it
  never has to stop.

**Cost:** one rebase per upstream merge, each with a gate run and a focused
review.

**Evidence:** three Issues started early in one arc. One absorbed two
rebases with no idle time; one merged before its declared blocker, shipping
without one piece, which was re-homed to the blocker's worker.

## Split a large Issue

**When:** one Issue is about as large as the rest of the wave, and its work
divides cleanly.

**How:**

- **By ownership:** two Worktrees and two briefs, each owning its own part
  and its own section of any shared file.
- **By kind of work:** the core or adapter first, then the acceptance
  measurements and documents. The first half unblocks siblings sooner, and
  the second half's long measurements don't hold up the core.
- Both halves' commits reference the Issue without closing it, except the
  one that finishes it. The lead closes the Issue after both land, and
  whoever lands second rebases.

**Cost:** a rebase for the second to land. A closing keyword in prose (see
the brief's gotchas) can close the Issue early.

**Evidence:** an Issue split by ownership took about 76 minutes against
roughly 130 estimated for one worker. Splitting by kind worked twice in
another arc.

## Stack locally on an open blocker PR

**When:** the blocker's PR is open and its models are settled, but it hasn't
merged (red CI, or still in review).

**How:**

- The worker rebases onto the blocker's branch and builds on its real
  models.
- After the blocker's squash merge, it runs
  `git rebase --onto origin/<integration branch> <old base sha> HEAD`, then
  checks that the branch holds only its own commits.
- Stacks stay local. The PR is opened only once the branch is based on the
  integration branch.
- If the blocker is rebased before it merges, the stacked worker moves with
  `git rebase --onto <new blocker head> <old blocker head> HEAD`.

**Cost:** merge order matters. Merging a sibling first changes the blocker's
head, and the stack has to follow it.

**Evidence:** a stacked Issue had a conflict-free final rebase and landed
about 50 minutes after its blocker.

## Review while blocked

**When:** a worker is waiting at a checkpoint, or stacked and waiting.

**How:** run the full independent review on the worker's own diff (from the
stack base to its head) now. After the final rebase, only a focused review
of the conflict resolution and any model adjustments remains.

## Pay down a flaky check

**When:** a known flake or slow gate costs most PRs a rerun.

**How:** assign it a worker in the **first** wave, even if it sits outside
the arc. The brief asks for before-and-after stress evidence under load.

**Cost:** stress runs are slow. Started mid-arc, one landed after the rest
of the arc and saved nothing; started at the outset, it would have spared
most of the reruns.

## Pair a re-pin with its consumers' measurements

**When:** an Issue re-pins a tool release, and other Issues wait on how that
release behaves.

**How:** add the consumers' open questions to the re-pin's brief, and have
it report what it measures as soon as it has it. Post the measurement to
the consuming Issue at once.

**Evidence:** a re-pin measured a downstream Issue's signal mid-flight,
which turned that Issue from an open design question into a maintainer's
decision before its wave began.

## Verify and close

**When:** an Issue may already be delivered by work that merged since it
was written.

**How:** the brief allows "verified, nothing to change" as an outcome. The
worker maps each acceptance box to evidence on the integration branch, adds
a test where one is missing, and opens no PR if nothing needs changing. The
lead closes the Issue with the evidence map.

**Evidence:** one such Issue needed tests and documents only, no source
change.

## Regenerate recorded evidence once

**When:** two or more Issues in flight touch the sources a recorded
measurement depends on, and it takes long to regenerate.

**How:** at wave planning, assign the regeneration to whoever lands second,
along with any expectation the first lander's change invalidates. If the
planned order flips, move the regeneration with it: land the PR that is
ready, and have the worker still running regenerate once on the new base.
Evidence recorded at an older base stays valid as provenance at that base
when the merges since did not touch what it measures.

**Cost:** one extra full run for the second lander. Discovering the
collision mid-flight cost one Issue two discarded hour-long runs.
