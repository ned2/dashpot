# AGENTS.md

Guidance for AI coding agents working in this repository.

## Orientation

Dashpot is a passive terminal view of declared Issues, repository state, and
active coding-agent runs. Observation never mutates; the named management
commands (`init`, `integrate`, `work start` / `stop`, `branch delete`,
`worktree remove`) and the dashboard's mutating keys (`f`, a Remote Fetch;
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
Codex relocation uses sequential `codex resume <session-id> -C <path>` with the
old client exited first; Claude Code uses `EnterWorktree`. Active Agent Run
continuity across a Codex exit and resume is not promised, so the resumed turn
runs `work start` and verifies `work show` again. Leave the Worktree in place
unless the user explicitly requests Cleanup.

## Vocabulary

Before changing code, tests, or documentation, read the shared
[domain language](docs/domain-language.md). Use its terms consistently —
Agent Session versus Agent Run, Work Store, Issue Binding, Issue Hint, Worktree
versus Repository Anchor — in code, tests, messages, documentation, and commit
messages, and follow every _Avoid_ note. Update the domain language in the same
change that introduces or clarifies a shared term; record a qualifying design
decision as a new ADR in `docs/adr/`.

## Quality and code conventions

The gate is `uv run pre-commit run --all-files` and `uv run pytest -q`, both
clean, before every commit; the pre-push hook then runs the full gate for the
pushed revision.

Under Codex on Linux, use the per-command sandbox-escalation mechanism for a
full gate only when its matching condition applies:

- `uv run pre-commit run --all-files`: the sandbox protects the tracked
  `.codex/config.toml`, while `end-of-file-fixer` opens every selected file for
  writing before deciding whether it needs a change.
- `uv run pytest -q` on Python 3.14: when the command runs under the
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
- Values at validating seams — untrusted input, persisted state, published
  wire shapes — are Pydantic models on the shared base in
  `src/dashpot/models.py`
  ([ADR 0013](docs/adr/0013-adopt-pydantic-models-by-seam.md)); trusted
  internal values stay frozen, slotted dataclasses
  (`@dataclass(frozen=True, slots=True)`) and `Literal` unions. Identity is
  opaque and never derived from labels or paths.
- A boolean toggle in the dashboard shows its state by the presence of its
  `X`, never by its colour: build it from `MarkedSelectionList` or
  `MarkedCheckbox` in `src/dashpot/marked_widgets.py`, not from Textual's
  stock `SelectionList` or `Checkbox`, whose `X` is always drawn and only
  recoloured, and give its button states one colour in `dashpot.tcss`.
- Docstrings are one imperative line in the voice of the shared domain language
  (`"""Identify the supported Agent Session enclosing this command."""`);
  comments explain why, not what.
- Tests drive public seams: `observe_agent_runs` with a fake process lookup
  rather than the process adapter, the `WorkStore` rather than its files,
  Textual screens through `App.run_test` / `pilot` and the `wait_until`
  helper in `tests/helpers.py`. Fakes stand in for GitHub; nothing in the
  suite talks to the network.
- Every document under `docs/` declares `status` and `date` in frontmatter,
  and every in-repo Markdown link resolves — path and heading anchor.
  `scripts/check_docs.py` fails the gate on either. When you move or rename a
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
