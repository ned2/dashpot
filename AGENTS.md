# AGENTS.md

Guidance for AI coding agents working in this repository.

## Orientation

Dashpot is a passive terminal view of declared Issues, repository state, and
active coding-agent runs; it observes and never controls. The shared context
for humans and agents is the README:

- [Development setup](README.md#development-setup),
  [Quality gates](README.md#quality-gates), and
  [Continuous integration](README.md#continuous-integration)
- [Contributing](README.md#contributing) — the branch, push, and CI workflow
- [Domain language](README.md#domain-language)
- [Project configuration](README.md#project-configuration)
- [Agent session observation](README.md#agent-session-observation) and
  [Issue work opt-in](README.md#issue-work-opt-in)
- [Design](README.md#design) and the [Documentation map](README.md#documentation-map)

## Issue work lifecycle

Dashpot observes this session automatically once the harness hooks are
installed, but it never infers which Issue you are working on: the Work Store
is the sole authority for Issue association, and only an explicit opt-in from
inside the session writes to it. Declare your work:

```bash
uv run dashpot work start 35      # when you begin work on Issue #35
uv run dashpot work start 36      # again, whenever you switch to another Issue
uv run dashpot work stop          # when the work is finished
```

The Issue may be a bare Issue Number (`35`), a `#`-prefixed one (`'#35'`,
quoted for the shell), or a full Issue Reference such as `ned2/dashpot#35` or a
Local Issue slug. `stop` takes no argument. Check what is recorded with
`uv run dashpot work show`.

- Run `start` as soon as you know which Issue the work belongs to, and `stop`
  after the final push, before reporting done. Ending a session with a run
  still open leaves an Orphaned Agent Run behind for a human to clean up.
- Only Issue work gets a `start`. Work without an Issue is observed as an
  unbound session, which is correct.
- Run the command **inside your own process tree** (from your shell tool, not
  a detached or backgrounded process): it identifies the enclosing harness by
  walking up from its own parent process.
- Run it **in the checkout where the work happens**. Each linked worktree has
  its own `.dashpot/state/` and its own `.venv`, so the record lands where the
  session is observed.
- Run it **via `uv run`**: the `dashpot` console script lives in that
  checkout's `.venv`.

## Vocabulary

Before changing code, tests, or documentation, read the shared
[domain language](README.md#domain-language). Use its terms consistently —
Agent Session versus Agent Run, Work Store, Issue Binding, Issue Hint, Worktree
versus Repository Anchor — in code, tests, messages, documentation, and commit
messages, and follow every _Avoid_ note. Update the domain language in the same
change that introduces or clarifies a shared term; record a qualifying design
decision as a new ADR in `docs/adr/`.

## Quality and code conventions

The gate is `uv run pre-commit run --all-files` and `uv run pytest -q`, both
clean, before every commit; the pre-push hook then runs the full gate for the
pushed revision. The conventions the tooling enforces or the code assumes:

- Full type annotations on everything in `src/` (Ruff `ANN`), and ty clean
  with no blanket `type: ignore` — an ignore names its rule and says why.
- Domain values are frozen, slotted dataclasses
  (`@dataclass(frozen=True, slots=True)`) and `Literal` unions; identity is
  opaque and never derived from labels or paths.
- Docstrings are one imperative line in the voice of the shared domain language
  (`"""Identify the supported Agent Session enclosing this command."""`);
  comments explain why, not what.
- Tests drive public seams: `observe_agent_runs` with a fake process lookup
  rather than the process adapter, the `WorkStore` rather than its files,
  Textual screens through `App.run_test` / `pilot` and the `wait_until`
  helper in `tests/test_app.py`. Fakes stand in for GitHub; nothing in the
  suite talks to the network.
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
