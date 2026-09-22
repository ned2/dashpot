# AGENTS.md

Guidance for AI coding agents working in this repository.

## Orientation

Dashpot is a passive terminal view of declared Issues, repository state, and
active coding-agent runs. Observation never mutates; the named management
commands (`init`, `integrate`, `work start` / `work relocate` / `work stop`,
`branch delete`, `worktree remove`) and the dashboard's mutating keys (`f`, a
Remote Fetch;
`x`, a Cleanup) mutate only what they name, on explicit invocation, and a
Cleanup — deleting a Branch or removing a Worktree — only what a person
selected from a preview and confirmed
([ADR 0008](docs/adr/0008-let-management-commands-mutate-on-explicit-invocation.md),
[ADR 0014](docs/adr/0014-fetch-remotes-on-explicit-key-press.md),
[ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md)).
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
before using `work start`. Claude Code uses `EnterWorktree`. Leave the Worktree
in place unless the user explicitly requests Cleanup.

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
calls belong to the main session only.

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
Coverage replaces ordinary pytest for that gate. Pre-push checks the pushed
revision's lockfile, lint, formatting, types, documentation, and distributions;
it skips pytest. These are Dashpot development rules, not rules for Projects
observed by the application.

### Independent review before integration

The agent implementing an Issue dispatches a review subagent using the
`code-review` skill before opening its integration PR. Supply the Issue and
acceptance criteria, a fixed base commit and the complete diff including new
files, applicable repository standards/domain language/ADRs, local validation
results, and verified coverage evidence from the local review gate. The skill
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
after hooks and before push; a content-preserving commit does not invalidate
review. Changes to the reviewed diff/base need appropriate follow-up review.
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
this Repository authorizes the rebase: rebase the branch onto `origin/main`,
rerun the local review gate against the new base, and force-push the branch
with an explicit lease on its previous head
(`--force-with-lease=refs/heads/<branch>:<old-head>`), without asking first. A
conflict-free rebase whose diff against the old head is exactly what landed on
`main` is content-preserving and needs no further review; a rebase that
resolves conflicts changes the reviewed diff and needs focused follow-up
review. Record the old and new heads and the new base in the PR's validation
section.

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
- Python 3.12 is the floor: a Python 3.13 typing feature (`TypeIs`,
  `deprecated`, a `TypeVar` default) is imported from `typing_extensions`,
  never from `typing` or `warnings`, and Python 3.13-only syntax is not
  written. A predicate is a `TypeIs` only when both answers are exact — a
  value that fails is never of the narrowed type — and stays a `TypeGuard`
  otherwise
  ([ADR 0048](docs/adr/0048-adopt-python-3-13-typing-backports-on-the-3-12-baseline.md)).
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
  Textual screens through `App.run_test` / `pilot` and the `wait_until`
  helper in `tests/helpers.py`. A test of the shipped dashboard builds it with
  `dashboard_app` in `tests/app_harness.py`, whose `SnapshotQuerySource`
  serves the snapshot the collector observes, and waits on
  `first_load_landed` before reading a pane. Fakes stand in for GitHub;
  nothing in the suite talks to the network.
- Every document under `docs/` declares `status` and `date` in frontmatter,
  every in-repo Markdown link resolves — path, heading anchor, and `#L`
  line fragment — and every ADR carries a four-digit number no other ADR
  claims, so a bare "ADR NNNN" in prose or in a code comment still names one
  document. The [ADR index](docs/adr/README.md) is generated from the ADRs, so
  after adding or changing one run
  `uv run python scripts/maintain_docs.py --write-adr-index` and commit the
  result; the gate fails while the committed index is not what the script
  produces.
  `scripts/maintain_docs.py` fails the gate on any of them. When you move or rename a
  section, fix the pointers in the same change; when you finish work an ADR or
  a research note described as future, update that document's `status` rather
  than leaving a reader to discover it is stale. The vocabulary is in the
  README's [documentation map](README.md#documentation-map).
- A lockfile change is its own task. Install with `uv sync --locked --group
  dev`; never relock or upgrade a dependency as a side effect of other work.

## Working in worktrees

Every checkout — the main worktree and each linked worktree — owns its own
`.venv`: run `uv sync --locked --group dev` inside the checkout you were
assigned before running anything there. Project state is per checkout too
(`.dashpot/state/` is ignored), which is why the Issue work lifecycle above is
run where the work happens. There is no tracked `.envrc`; an `.envrc` you find
in a checkout is local, ignored, and holds that user's `gh` credentials —
leave it alone and never commit one.

## Tracking and notes

**Do not create or rely on a private agent memory store.** Durable context
lives where humans read it: GitHub Issues (this Project's Issue Source) for
plans and follow-ups, the [README](README.md) and `docs/*.md` for shared project
context, and `docs/adr/` for decisions. If something is worth remembering,
record it there.

## Where rules live

Agent-facing rules and recurring gotchas belong in this file. Claude Code
loading notes belong in [CLAUDE.md](CLAUDE.md), which imports this file.
