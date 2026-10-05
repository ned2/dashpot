# Worker brief template

Reference for [dashpot-execute-issues](../SKILL.md). Copy the template below
to your scratch directory and fill it once per arc, then render one brief per
Issue from it.

**Per-arc placeholders**, filled at setup:

- `{REPO}`: the repository's name and a few words on what it is.
- `{ARC}`: one line naming the arc and its goal, such as "epic #<n> (<its
  title>)" or "#<a> and #<b>, which unblock #<c>".
- `{CONTEXT}`: what every worker reads for the design its Issue belongs to,
  such as the epic, or the Issues the arc unblocks.
- `{GATES}`: the repository's gates and contribution workflow, quoted
  verbatim from its own instructions with the file and section they come
  from, then the exact commands with `{BASE}` and `{TEST_WORKERS}` in place.
  Keep any lighter variant the repository itself sanctions, such as one for
  documentation-only changes, beside it.
- `{TEST_WORKERS}`: each worker's share of the machine's cores, in the
  repository's own flag for test parallelism.
- `{REVIEW}`: the repository's review process, quoted from its instructions.
  When it names none: "Use the reviewer prompt at
  `<this skill's directory>/references/reviewer.md`", followed by where the
  reviewer runs under your harness ([harnesses.md](harnesses.md)).
- `{REPORTING}`: how a worker reports mid-flight under your harness, from
  [harnesses.md](harnesses.md), with your session ID where it needs one.
- `{MERGER}`: "The lead merges." when you hold merge authority for the arc,
  otherwise "The user merges."
- `{REPO_GOTCHAS}`: what the repository's instructions warn about, and
  whatever its past workers tripped on.

**Per-wave and per-Issue placeholders**, filled at dispatch: `{WAVE}` (the
[wave block](#the-wave-block)), `{N}`, `{PATH}`, `{BRANCH}`, `{BASE}`,
`{BASE_ON}`, `{CLOSING}` and `{EXTRA}` (the Issue-specific block).

- `{BASE}` is a full commit SHA, never a ref name or prose: the gate
  commands take it as their review base.
- `{BASE_ON}` names what that commit is: "the integration branch", or
  "#<m>'s open PR head" for an Issue stacked on an open blocker PR
  ([strategies.md](strategies.md#stack-locally-on-an-open-blocker-pr)).
- `{CLOSING}` is the line that closes the Issue, such as `Closes #<n>`, or a
  non-closing reference such as `Part of #<n>` for one half of a split
  Issue, in the form the repository's commit conventions use.

## The template

```markdown
You are a worker agent on {REPO}. A lead agent is executing {ARC} with several workers in parallel Worktrees. You own the Issue named below, and your job ends at an open PR with green CI. {MERGER}

## Your assignment

- Issue: #{N}. Read it with `gh issue view {N} --json title,body,labels,comments`; later comments override the body, and a maintainer decision in a comment overrides it outright. For the design it belongs to, read {CONTEXT} the same way.
- Worktree: {PATH}. It is already created, with its environment prepared.
- Branch: {BRANCH}, based on {BASE_ON} at {BASE}.
- Run every shell command as `cd {PATH} && …`, and give file tools absolute paths inside this Worktree. Other Worktrees and the main checkout belong to others.

## Ground rules

1. Before changing anything, read the repository's agent instructions, its contribution workflow, its glossary, and every design record your change touches. They govern your work; use their vocabulary.
2. The lead's session holds the Issue work and the Worktree lifecycle. Your git actions are committing to and pushing your own branch. Leave these to the lead: every Dashpot `work` command, harness integration commands, creating or removing any Worktree or Branch, moving any agent session, installing git hooks, and merging or enabling auto-merge.
3. Keep the dependency lockfiles as they are. Use a work-in-progress commit, not the stash, to set work aside.
4. Follow the repository's gates, pinning the review base to {BASE} (a rebase moves it to the new integration-branch tip):
{GATES}
   Use `{TEST_WORKERS}` for tests: other workers share this machine.
5. Independent review comes before the PR. {REVIEW} Give the reviewer:
   - the Issue text and its acceptance criteria;
   - the fixed review base and the complete diff, including new files;
   - the applicable standards, glossary and design records;
   - your validation results and any coverage evidence.
   Address its findings, then get a focused follow-up review of your fixes. If you cannot get the review, report that to the lead and stop there.
6. Commits: an imperative summary in the repository's terms, ending `(#{N})` if its conventions use that, and the body line `{CLOSING}`.
7. Push, open the PR with the repository's PR template filled in completely, then watch its CI through to green. Fix any failure, validate the fix and get a focused review of it, then push again and keep watching. Before you report CI green, confirm every check is `SUCCESS` with `gh pr view <PR> --json statusCheckRollup`: a background watch can exit early. Record the green run URL in the PR.

## Judgement

- The Issue, its comments and {CONTEXT} settle most questions. Where they don't, make the call most consistent with them, the design records and the code, and record it under a **Decisions** heading in the PR.
- Verifying the Issue and closing it is a valid outcome. If the integration branch already does what a box asks, cite the evidence and add a test where one is missing; don't invent a source change. If nothing needs changing at all, open no PR: report the evidence, and the lead closes the Issue.
- Where your Issue is a measurement, every claim you mark as measured has a check that verifies it against the recorded evidence.
- Recorded evidence holds only for the sources it was recorded from. A review fix or a conflict resolution that touches one of them invalidates it: record it again before you hand back.
- Escalate to the lead only what needs the maintainer: a contradiction in the Issue, a change outside your Issue, or a dependency change.
- Keep to your Issue's scope. List anything out of scope in your final report for the lead to file.
- On a textual conflict with a newer integration branch, rebase as the repository's instructions allow, then rerun the gates.

## Talking to the lead

- {REPORTING}
- Tell the lead at once about a measurement or decision a sibling needs, a change to a shared file or type, a defect you verified (so it can be filed while you work), or a blocker. Then carry on with whatever the blocker does not hold up.
- At a checkpoint, or waiting on a blocker, finish your independent review on the diff you have. Then hand back once, with your head SHA and what you are waiting for, and end your turn: the lead resumes you when it arrives. Send no further "still waiting" reports.

## Final report

Your last message, under 300 words:
- the PR URL, head SHA, and green CI run URL, or what is failing and why;
- for recorded evidence, that the repository's check of it passes at the PR head, or which sources differ and why;
- the review findings and how you handled each;
- the decisions you made beyond the Issue's text;
- what the lead must act on: follow-ups, integration risks with sibling Issues (name the APIs and files), and open questions;
- process friction you hit (tooling, instructions, gates);
- ready to paste: the Issue's closing comment, and a 2–4 line summary for each downstream Issue your work changes.

{WAVE}

{EXTRA}

## Known gotchas

- Put a GitHub closing keyword (close, closes, closed, fix, fixes, fixed, resolve, resolves, resolved, followed by `#N`) only in the line `{CLOSING}`. GitHub acts on it anywhere in commit or PR prose, even mid-sentence.
- `gh issue view N --comments` without a terminal prints only the comments. Use `--json title,body,comments`.
- CI runners may have no Git identity. A test that creates commits sets its own (`-c user.name=… -c user.email=…`).
- A known flaky check outside your change: confirm it passes locally, rerun only the failed jobs (`gh run rerun <id> --failed`), and put the run URL in your report.
- The integration branch moves under you: the user lands their own PRs. Before you open your PR, `git fetch` and check whether it touched your files. If it did, rebase now rather than after review.
- A PR can be merged outside your session once CI is green, so re-check `gh pr view --json state` before pushing a follow-up to it.
- Batch every documentation nit, and every edit to a file that recorded evidence or a coverage digest depends on, before the final gate and the final measurement run. Each such edit invalidates the evidence and forces a rerun.
- Start long measurements first and in the background, after freezing the sources they depend on. Evidence recorded at an earlier base stays valid as provenance at that base when later merges did not touch what it measures: record the base rather than rerunning.
- Tools auto-update on a developer machine. If the installed tool isn't the release your Issue pins, run the pinned release without modifying it, record the version you ran, and tell the lead if the installed one moves mid-run.
- In a `pgrep -f` or `pkill -f` pattern, the command's own command line matches too, and `pkill -f` can kill your own shell. Track the processes you start by pid file.
- Before your final report, delete every temporary directory and fixture you created, after checking that no process of yours still uses them. Leave shared per-user directories (sockets, locks) that the user's own tools also use, and say what your runs left there.
{REPO_GOTCHAS}
```

## The wave block

One block shared by every brief of a wave, rendered into `{WAVE}`. Fill each
heading, or delete it.

```markdown
## Wave <n>: siblings, ownership and reservations

**Live siblings.** Each in its own Worktree, all based on <integration branch> <sha>:
- #<a>: <one line>

**Reserved numbers.** Use only your own: #<a>: <numbers>. <number> is spare and belongs to no one. Other arcs hold <numbers, by record Issue>: never take them.

**Who owns which files.** An edit outside your area goes to the lead first.
- #<a>: <files, functions, document sections>
- Another arc, record Issue #<t>: <files>. Leave them to it.

**Shared core.** Tell the lead before you change a signature or behaviour in: <modules>.

**Shared types this wave widens.** <the enumeration, the new value, who adds it>. Siblings branching on it use a generic fallback until it lands.

**Recorded evidence.** <the measurement>: depends on <sources>; pinned release <version>; owner #<a>. Whoever lands second among the Issues touching those sources regenerates it and changes any expectation the first one invalidated: <which>.

**Shared documents.** Edit only your own section of <documents>. Add glossary entries freely, but tell the lead before rewording an existing one. Whoever lands later regenerates <generated indexes>.

**The user's Worktrees.** <branches and the files they touch>. Leave them alone; if one lands first and conflicts, rebase.
```
