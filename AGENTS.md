# AGENTS.md

Guidance for AI coding agents working in this repository.

## Orientation

Dashpot is a passive terminal view of declared Issues, repository state, and
active coding-agent runs. Observation never mutates; the named management
commands (`init`, `integrate`, `work start` / `work relocate` / `work stop` /
`work forget-subagents` / `work assign` / `work unassign`, `branch delete`,
`worktree remove`, `events remove`)
and the dashboard's
mutating keys (`f`, a Remote Fetch;
`x`, a Cleanup) mutate only what they name, on explicit invocation, and a
Cleanup — deleting a Branch or removing a Worktree — only what a person
selected from a preview and confirmed
([ADR 0008](docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md),
[ADR 0014](docs/adr/0014-fetch-remotes-on-explicit-key-press.md),
[ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md);
`events remove` removes only the Event Log files dated before the day it is
given, [ADR 0059](docs/adr/0059-keep-an-append-only-event-log-in-each-checkout.md)).
The shared context for humans and agents is the README:

- [Development setup](README.md#development-setup),
  [Quality gates](README.md#quality-gates), and
  [Continuous integration](README.md#continuous-integration)
- [Contributing](README.md#contributing) — the branch, push, and CI workflow
- [Domain language](docs/domain-language.md)
- [Project configuration](README.md#project-configuration)
- [Agent sessions](docs/agent-sessions.md) — how sessions are observed and
  [Issue work opt-in](docs/agent-sessions.md#issue-work-opt-in)
- [Design](docs/design.md) and the [Documentation map](README.md#documentation-map)

The Worktrees pane also supports explicit terminal/clipboard actions: `Enter`
opens the selected Worktree and `y` copies its path. These actions do not
establish Issue work or relocate an Agent Session
([launcher contract](docs/installation.md#open-worktrees-and-copy-paths)).

## Issue work lifecycle

Use the model-invoked `dashpot-issue-work` skill whenever work belongs to an
Issue. It owns the resolve, opt-in, Worktree dispatch, handoff, recovery, and
finish sequence while this file supplies this Repository's commands and gates.
`dashpot integrate <harness>` installs or updates the skill beside the
lifecycle hooks; if the skill is unavailable, ask the user to run
`uv run dashpot integrate codex` or `uv run dashpot integrate claude-code`.

For this Repository, invoke Dashpot through `uv run dashpot` in the Worktree
where work happens. Hold the Issue Binding through the whole engagement,
including every delegated task, final push, and CI run. A plain tool-call
`cd`, or a sub-agent's shell elsewhere, does not relocate an Agent Session.
Codex relocation uses sequential `codex resume <session-id> -C <path>`, and
the old client must exit to release the thread before the resumed client can
continue it; an active run declares its target with `work relocate`
before exit, and the resumed turn verifies the preserved run with `work show`
before using `work start`. Claude Code uses `EnterWorktree`, which carries an
active run along, so it too checks `work show` before using `work start`.
Leave the Worktree in place unless the user explicitly requests Cleanup.

The lifecycle hooks `dashpot integrate <harness>` installs observe a session in
this checkout as live automatically. Observation is not Issue opt-in: the
`work start` / `stop` lifecycle above still applies. Run `dashpot integrate
<harness>` only from the main checkout, never from an Issue Worktree: the hooks
bind the absolute path of the invoking environment's publisher, and a linked
Worktree's `.venv` is removed with the Worktree, which would break every hook
event on the machine. `integrate` refuses such a binding and `--status` warns
about one that already exists
([diagnosis](docs/installation.md#diagnose-an-installation)).

A sub-agent shares the session's Agent Run and needs no opt-in of its own. It
must leave `work start` / `stop` alone: running them from a sub-agent would
switch or end the whole session's Issue work, and a sub-agent's `work start`
in a Worktree other than the session's is refused as running where the
session is not
([ADR 0009](docs/adr/0009-hold-one-agent-run-per-session-across-worktrees.md)),
while `stop` is not refused, so the rule still matters. The `start` / `stop`
calls belong to the main session only, as do `work assign` / `work unassign`,
with which a Lead attributes each Worker to its own Issue
([ADR 0096](docs/adr/0096-attribute-a-leads-workers-to-their-issues-by-explicit-assignment.md)).

## Vocabulary

Before changing code, tests, or documentation, read the shared
[domain language](docs/domain-language.md). Use its terms consistently —
Agent Session versus Agent Run, Work Store, Issue Binding, Issue Hint, Worktree
versus Repository Anchor — in code, tests, messages, documentation, and commit
messages, and follow every _Avoid_ note. Update the domain language in the same
change that introduces or clarifies a shared term; record a qualifying design
decision as a new ADR in `docs/adr/`.

## Quality and code conventions

Before every commit, run the README's [local review gate](README.md#local-review-gate):
all-files pre-commit checks and the full suite with coverage, both clean.
Coverage replaces ordinary pytest for that gate. A change touching only the
Markdown that CI's [documentation lane](README.md#continuous-integration)
classifies skips the coverage run; confirm the classification with the
command the [local review gate](README.md#local-review-gate) gives rather
than by eye. Such a change still
runs the all-files pre-commit checks and gets independent review, and its PR's
validation section records that coverage was skipped because the change is
documentation only. Pre-push checks the pushed revision's lockfile, lint,
formatting, types, documentation, and distributions; it skips pytest. These
are Dashpot development rules, not rules for Projects observed by the
application.

### Independent review before integration

The agent implementing an Issue dispatches a review subagent using the
`code-review` skill before opening its integration PR. Supply the Issue and
acceptance criteria, a fixed base commit and the complete diff including new
files, applicable repository standards/domain language/ADRs, local validation
results, and verified coverage evidence from the local review gate unless the
change is documentation only. The skill
owns the review procedure and may delegate its Standards and Spec axes.
An unavailable skill is a reported blocker, not an implicit review exemption.

Review can start while checks run; its final decision waits for successful
validation and considers uncovered changed code, relevant failure paths, and
the tests' assertions. Line coverage measures execution, not assertion quality
or every branch outcome. Record review results, finding dispositions, and
source identity in the PR's validation section. An exception to independent
review requires explicit user direction and a recorded reason.

Address findings, refresh validation for changed sources, and request focused
follow-up review of the fixes. Changed tests, conflict resolutions, or
CI-driven fixes can invalidate approval too. Verify the coverage source digest
after hooks and before push, except for a documentation-only change, which has
no evidence, and a content-preserving rebase, below, whose evidence stays that
of the head it rebased; a commit that leaves the digest unchanged does not
invalidate review. Changes to the reviewed diff/base need appropriate follow-up review.
Green CI on unchanged reviewed code finishes verification without another
routine review. Follow the README's [integration sequence](README.md#contributing)
and keep the Issue Binding through all delegated work and green PR CI.

Pull requests integrate by squash merge on GitHub once the PR's own CI is
green ([ADR 0045](docs/adr/0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md)),
so the branch's own commits are not what lands on `main`; the PR title and
body are. The agent's work ends with the PR open, its validation section
recorded, and CI green; the operator reviews and merges. A PR does
not need to contain the current `main`, so `main` advancing past the branch's
base is not a reason to rebase. Nothing runs CI on `main` itself, so two PRs
that each passed on their own but conflict semantically surface on the first
run that contains both, which is the next PR branched from the new `main`;
the agent implementing that PR diagnoses the failure against `main` rather
than against its own change. When the branch conflicts with `main` textually,
this Repository authorizes the rebase: rebase the branch onto `origin/main`
and force-push the branch with an explicit lease on its previous head
(`--force-with-lease=refs/heads/<branch>:<old-head>`), without asking first.

A rebase is content-preserving when it applies without conflicts, or when its
only conflict is in the generated [ADR index](docs/adr/README.md) and is
resolved by running `uv run python scripts/maintain_docs.py --write-adr-index`.
Two branches that each add an ADR always conflict there, and the script
resolves it mechanically. Confirm it with
`git range-diff <old-base>..<old-head> <new-base>..<new-head>`: no commit's
added or removed lines change outside `docs/adr/README.md`. Context lines may
differ where `main` edited nearby. A content-preserving rebase needs no
further review: in place of the local review gate, rerun only
`uv run pre-commit run --all-files`, which checks the regenerated index, and
keep the coverage evidence of the head it rebased. The PR's CI on the rebased
head is the check for a semantic conflict with the new base. Any other rebase
resolves conflicts that change the reviewed diff: rerun the local review gate
against the new base and request focused follow-up review. Record the old and
new heads, the new base, and for a content-preserving rebase the range-diff
result, in the PR's validation section.

Under Codex on Linux, use the per-command sandbox-escalation mechanism for a
full gate only when its matching condition applies:

- `uv run pre-commit run --all-files`: the sandbox protects the tracked
  `.codex/config.toml`, while `end-of-file-fixer` opens every selected file for
  writing before deciding whether it needs a change.
- The local coverage command or `uv run pytest -q` on Python 3.14: when it runs under the
  restricted, network-disabled sandbox profile, its seccomp policy blocks the
  asyncio self-pipe wakeup
  ([openai/codex#15053](https://github.com/openai/codex/issues/15053)) and can
  make `asyncio.run()` wait five minutes while shutting down Textual's default
  executor. A network-enabled sandbox does not require escalation for this
  reason.

Scope each exception to the exact gate command and state its reason in the
escalation request. If per-command escalation is unavailable, ask the user to
run the gate. Keep the checkout's Python version unchanged and treat an
artificial timer or executor-shutdown patch as masking the environment fault
rather than fixing a test.

The conventions the tooling enforces or the code assumes:

- Full type annotations on everything in `src/` (Ruff `ANN`), and ty clean
  with no blanket `type: ignore` — an ignore names its rule and says why.
- Python 3.13 is the floor: a typing feature Python 3.13 provides
  (`TypeIs`, `deprecated`, a type parameter default) is imported from
  `typing` or `warnings`, never from `typing_extensions`, and Python
  3.14-only syntax is not written. A predicate is a `TypeIs` only when both
  answers are exact — a value that fails is never of the narrowed type — and
  stays a `TypeGuard` otherwise
  ([ADR 0105](docs/adr/0105-raise-the-python-floor-to-3-13.md)).
- Values at validating seams — untrusted input, persisted state, published
  wire shapes — are Pydantic models on the shared base in
  `src/dashpot/core/pydantic.py`
  ([ADR 0013](docs/adr/0013-adopt-pydantic-models-by-seam.md)). GitHub response
  models use `WireModel`; published query values use `ObservationModel` with
  their closed key contracts
  ([ADR 0041](docs/adr/0041-distinguish-github-wire-models-from-configuration.md)); trusted
  internal values stay frozen, slotted dataclasses
  (`@dataclass(frozen=True, slots=True)`) and `Literal` unions. Identity is
  opaque and never derived from labels or paths.
- A boolean toggle in the dashboard shows its state by the presence of its
  `X`, never by its colour: build it from `MarkedSelectionList` or
  `MarkedCheckbox` in `src/dashpot/ui/marked_widgets.py`, not from Textual's
  stock `SelectionList` or `Checkbox`, whose `X` is always drawn and only
  recoloured, and give its button states one colour in `dashpot.tcss`.
- Textual runs a message handler (`on_ready`, `on_observation_finished`, …)
  on every class of the MRO that defines it, subclass first, so an override
  never calls `super()` — that would run the base handler twice. Keep the
  handler thin and delegate to a plain method, as
  `DashpotApp.on_observation_finished` delegates to `_accept_observation`, so
  work that must follow the handler has a method to override.
- Every module has a docstring, a package's empty `__init__.py` aside. A
  docstring is written in the voice of the
  shared domain language and opens with one summary line: imperative for a
  function that acts (`"""Identify the supported Agent Session enclosing
  this command."""`), while a class, a property, or a function that only
  answers a question may instead name what it is or yields (`"""A
  management command refused before writing."""`, `"""Every record of
  ``git worktree list``, main working tree first."""`). A body may follow
  after a blank line when the summary cannot carry the contract alone.
  Comments explain why, not what.
- Tests drive public seams: `observe_agent_runs` with a fake process lookup
  rather than the process adapter, the `WorkStore` rather than its files,
  Textual screens through `App.run_test` / `pilot` and the waiting helpers
  in `tests/helpers.py`: `wait_until` for a change to begin, then `settled`
  for the geometry Textual lays out after it. A test of the shipped
  dashboard builds it with `dashboard_app` in `tests/app_harness.py`, whose
  `SnapshotQuerySource` serves the snapshot the collector observes, and
  waits on `first_load_landed` before reading a pane; `settle_screen`
  there settles every region on a screen, and `footer_showing` waits on
  the Footer, which recomposes rather than settles. Fakes stand in for
  GitHub; nothing in the suite talks to the network.
- Every document under `docs/` declares `status` and `date` in frontmatter,
  every in-repo Markdown link resolves — path, heading anchor, and `#L`
  line fragment — and every ADR carries a four-digit number no other ADR
  claims, so a bare "ADR NNNN" in prose or in a code comment still names one
  document.
  `scripts/maintain_docs.py` fails the gate on any of them. The
  [ADR index](docs/adr/README.md) is generated from the ADRs, so after adding
  or changing one run
  `uv run python scripts/maintain_docs.py --write-adr-index` and commit the
  result; the gate fails while the committed index is not what the script
  produces. When you move or rename a
  section, fix the pointers in the same change; when you finish work an ADR or
  a research note described as future, update that document's `status` rather
  than leaving a reader to discover it is stale. The vocabulary is in the
  README's [documentation map](README.md#documentation-map).
- Install with `uv sync --locked --group dev`.
- Within a task, relock with plain `uv lock` only to follow a `pyproject.toml`
  change the task makes: a dependency added, removed, or given a new version
  constraint, the Python floor (`requires-python`) moved, or the project
  version bumped. `uv lock` keeps every locked version still compatible, so
  each entry in the lockfile diff traces to that change. An upgrade
  (`--upgrade`, `--upgrade-package`, `--upgrade-group`) is its own task, as
  the README's [hook refresh](README.md#local-review-gate) is.

## Working in worktrees

Every checkout — the main worktree and each linked worktree — owns its own
`.venv`: run `uv sync --locked --group dev` inside the checkout you were
assigned before running anything there. Project state is per checkout too
(`.dashpot/state/` is ignored), which is why the Issue work lifecycle above is
run where the work happens. There is no tracked `.envrc`; an `.envrc` you find
in a checkout is local, ignored, and holds that user's `gh` credentials —
leave it alone and never commit one.

## Leading parallel Issue work

A Lead running the bundled `dashpot-execute-issues` skill fills each
Worker's brief from this file
([ADR 0092](docs/adr/0092-ship-a-user-invoked-execute-issues-skill-for-every-harness.md)).
In this Repository:

- A Lead merges only when the operator grants it merge authority for the
  arc; otherwise the operator merges, as
  [ADR 0089](docs/adr/0089-leave-the-pr-merge-to-the-operator.md) decides.
- Reserve ADR numbers per Issue, with a spare, before dispatch. Scan
  `origin/main`, open PRs, the Remote-Tracking Branches after a fetch,
  every local Worktree's Branch, and every open Arc's record Issue: the
  operator's own Worktrees take numbers too. ADR numbers may have gaps, so
  while another Arc is open, start your block ten above the highest number
  it holds, which leaves its later reservations clear of yours.
- Every checkout shares one `.git/hooks`, installed from the main checkout
  ([quality gates](README.md#quality-gates)). Never run `pre-commit install`
  from a linked Worktree, whose `.venv` is removed with it, and after
  removing a Worktree check the hooks still name the main checkout's
  Python.
- `scripts/maintain_docs.py` reads tracked files only: `git add -N` a new
  document before `--write-adr-index`, and regenerate the index after
  every rebase, since sibling Workers add ADRs too. A rebase whose only
  conflict is that index stays content-preserving
  ([independent review](#independent-review-before-integration)).
- Give each Worker a share of the cores with `review_coverage.py --workers
  N`; [development setup](README.md#development-setup) records sixteen
  pytest workers failing where eight passed. Live Arcs split the machine's
  cores evenly unless the operator sets other shares, and each Worker's
  `N` comes out of its Arc's share: with two Arcs on 32 cores, each runs
  two Workers at `--workers 8`, or four at `--workers 4`.
- CI checks out a PR's head alone, not its merge with `main`
  ([ADR 0045](docs/adr/0045-drop-the-up-to-date-rule-where-a-merge-queue-is-unavailable.md)),
  so a green run tested what will land only when the head contains
  `origin/main` (`git merge-base --is-ancestor origin/main <head>`). The
  `PR_BASE_SHA` in its `ci-revision-*` artifact
  (`gh run download <run> -p 'ci-revision-*'`) records only where `main`
  stood when the run began, not what the head contains.
- `code-review` reads the Issue itself
  ([issue tracker](docs/agents/issue-tracker.md)), so a brief gives it the
  Issue number, the review base and the evidence.
- A pinned harness experiment under `scripts/experiments/` runs in a
  disposable directory outside every Dashpot Project, with isolated
  configuration and every updater off (Codex
  `updater.autoUpdateEnabled=false`, Claude Code `DISABLE_AUTOUPDATER=1`).
  Its runner is detached with `setsid -f` and refuses to start under a
  harness process, whose ancestry would attach the fixture's hook records to
  the Lead's session. Run a retained release read-only, through a
  fixture-local `PATH` symlink: Codex's under
  `~/.codex/packages/standalone/releases/`, Claude Code's under
  `~/.local/share/claude/versions/`. Codex's `/tmp/codex-daemon-<uid>/` and
  Claude Code's `/tmp/cc-daemon-<uid>/` are shared with the user's own
  sessions, so never delete either wholesale. Read process arguments with
  `ps -ww`. Before merging a PR that commits a trace, check every hash it
  records against the PR head.

## Tracking and notes

**Do not create or rely on a private agent memory store.** Durable context
lives where humans read it: GitHub Issues (this Project's Issue Source) for
plans and follow-ups, the [README](README.md) and `docs/*.md` for shared project
context, and `docs/adr/` for decisions. If something is worth remembering,
record it there.

## Agent skills

Installed skills such as `code-review` look up this section by heading and
read `docs/agents/` by path.

### Issue tracker

The Issue Source named above, via `gh`. The fetch command and its pitfalls are
in [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md).

## Where rules live

Agent-facing rules and recurring gotchas belong in this file. Claude Code
loading notes belong in [CLAUDE.md](CLAUDE.md), which imports this file.
