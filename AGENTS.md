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

- Run `start` as soon as you know which Issue the work belongs to. Run
  `stop` only when the **whole engagement** is finished: this session *and
  every agent it delegated* are done with the Issue, the last push has
  landed, and nothing you started is still running. Sub-agents share your
  session's Agent Run, so your `stop` ends theirs too — never stop while a
  background sub-agent or task of yours is still working.
- One engagement, one run. A PR series on one Issue is a single engagement:
  hold the binding across it rather than cycling `start`/`stop` per push.
  The invariant this protects: any agent working on an Issue shows that
  Issue's run in the pane, and a premature `stop` silently breaks it.
- When in doubt, leave the run open. An open run costs nothing while your
  session is alive, and a run still open when the session ends gracefully
  is ended for you
  ([ADR 0015](docs/adr/0015-reconcile-the-agent-run-at-session-end.md));
  only a session killed outright leaves an Orphaned Agent Run behind for a
  human to clean up. So run `stop` when the engagement truly ends, not
  defensively early.
- Only Issue work gets a `start`. Work without an Issue is observed as an
  unbound session, which is correct.
- Run the command **inside your own process tree** (from your shell tool, not
  a detached or backgrounded process): it identifies the enclosing harness by
  walking up from its own parent process.
- Run it **in the checkout where the work happens**. Each linked worktree has
  its own `.dashpot/state/` and its own `.venv`, so the record lands where the
  session is observed.
- A session holds **one active run across the Repository's worktrees**. If
  your session moves to another worktree (Claude Code `EnterWorktree`), run
  `start` again there: Dashpot verifies the move from your own hook records
  and moves the run. A `cd` inside a tool call, or a sub-agent's shell in
  another worktree, is not a move; `start` there is refused and writes
  nothing. `stop` ends your run wherever it is recorded.
- Run it **via `uv run`**: the `dashpot` console script lives in that
  checkout's `.venv`.
- It works from a sandboxed shell too: when the harness process cannot be
  seen, the session is identified by the Agent Session Identity its hooks
  published (see [Issue work opt-in](README.md#issue-work-opt-in)). If it is
  refused, run `uv run dashpot integrate <harness> --status` and read the
  `Agent Session identity claimed here` line; do not write a Work Store
  record by hand.

## Preparing a Worktree for an Issue

Interim instructions until the agent-facing skill
([#58](https://github.com/ned2/dashpot/issues/58)) exists. When work on an
Issue should happen in its own linked Worktree, let Dashpot apply the
conventions ([ADR 0011](docs/adr/0011-prepare-issue-worktrees-by-convention.md))
rather than running `git worktree add` yourself:

```bash
uv run dashpot issue show 35 --json          # 1. resolve: exactly one fresh Issue
uv run dashpot worktree create 35 --json     # 2. create: path, Branch, base reported
codex -C <path>                              # 3. launch there, or: cd <path> && claude
uv run dashpot work start 35                 # 4. inside that session, at that Worktree
```

- `create` refuses rather than guesses: an existing Worktree for the Issue is
  listed as a hint (pass `--branch NAME` for a second approach), and a base
  without the Project's configuration, a collision, or a partially created
  Worktree is reported with its recovery commands. `--dry-run` shows the
  same report without creating anything.
- The default Worktree Root is the sibling `<checkout>.worktrees/` of the
  checkout the command runs in and must lie outside every Worktree of the
  Project; from a Claude Code `.claude/worktrees/` checkout, name one with
  `--worktree-root` or `DASHPOT_WORKTREE_ROOT`.
- A running Claude Code session moves with `EnterWorktree path=<path>` (the
  path is in `git worktree list` after `create`) and then runs `work start`
  there; Codex cannot relocate, so it prepares the Worktree for a new
  session. Run `uv sync --locked --group dev` in the new Worktree first.
- Finished work leaves the Worktree in place until a person asks for its
  removal. `uv run dashpot worktree check <path>` reports whether it could be
  removed and the Git command for each reason it cannot (no path: every
  linked Worktree). `uv run dashpot worktree remove <path> --delete-ignored
  [--delete-branch]` and `uv run dashpot branch delete NAME --local
  [--remote REMOTE]` remove
  only what their flags name, unforced and only when integrated, and never
  the checkout they run from ([ADR 0019](docs/adr/0019-remove-branches-and-worktrees-on-explicit-confirmation.md));
  run them only when the user asks, and never on a Worktree with a live
  session.

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
