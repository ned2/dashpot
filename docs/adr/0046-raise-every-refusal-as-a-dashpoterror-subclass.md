---
status: accepted
date: 2026-09-18
---

# Raise every refusal as a DashpotError subclass

The README and [ADR 0024](0024-build-the-command-line-on-cyclopts.md)
promise that a refusal is one `dashpot: <message>` line on stderr and exit
status 2, and `core/errors.py` promised that every error reaching `cli.main`
derives from `DashpotError`. The code kept the second promise unevenly:
`core/errors.py` stated it, while 93 `raise RuntimeError` sites — 28 in
`sessions/work.py` alone — relied on a second `RuntimeError` arm in
`cli.main` that had been left "while bare raise sites migrate". The
[2026-09-17 review](../codebase-review-2026-09-17.md) found the same gap in
the `Literal` contracts: harness names were bare `str` on most models,
`cli.py` defined a second `Harness` alias, and `observation/session_list.py`
hand-copied the display names, because observation may not import
`sessions`.

## Decision

A refusal is a `DashpotError`. Each seam that refuses raises its own subclass
— `IssueWorkError`, `IntegrationError`, `WorktreeCreateError`,
`ProjectConfigError`, `CommandError`, and so on — so that a caller catches
the refusal of the seam it called (`composition.py` catches `GitError` and
`WorkspaceConfigError`, never a bare `Exception`), and `cli.main` catches
`DashpotError` alone. The seam classes carry no state of their own; the
subclass is the seam's name, and the message stays the one the site already
stated.

Two kinds of `RuntimeError` remain, recorded in `core/errors.py`:

- A programmer fault is not a refusal. An exhaustive-match guard such as
  `unsupported observation kind`, a worktree plan without a base commit, or
  an Issue Source factory called for the wrong Issue Source kind stays a bare
  `RuntimeError` and escapes `cli.main` with its traceback, since stating it
  as `dashpot: …` would present a bug as a decision. `tests/test_cli.py`
  pins that `cli.main` lets it through.
- The observation boundary keeps `RuntimeError` beside `DashpotError` in
  `OBSERVATION_FAILURES`: a Project's observation turns any failure of its
  own sources into a Diagnostic, and a bug in a source is still a Diagnostic
  rather than a crashed dashboard. The same goes for the `except` clauses
  around `Path.resolve`, which raises `RuntimeError` for a symlink loop:
  that is Python's fault to report, not a refusal Dashpot raises.

Public classes that already derived from both `DashpotError` and a standard
base (`GitError(DashpotError, RuntimeError)`,
`IssueProfileError(DashpotError, ValueError)`, …) keep the second base, so
that a caller's existing `except` clause still matches. New seam classes,
and a module-private class whose only catcher is beside it, derive from
`DashpotError` alone.

The `Literal` half of the same gap closes in `core/model.py`, which is the
one package every layer may import: `Harness`, `HARNESS_DISPLAY`, and the
`is_harness` guard live there, and `AgentRun.harness` and every session
model are typed with it. Persisted records keep validating with the same
messages through `HarnessName` and `ActiveStateName`, a `BeforeValidator`
over the `Literal`. `RunState` and `ActiveState` are each defined once;
`sessions/agents.py` derives the run state without a `cast`. The AGENTS.md
docstring rule now says what the code does: a function that acts opens with
an imperative line, while a class, a property, or a function that only
answers a question may name what it is or yields.

## Consequences

`cli.main` has one refusal arm. A new refusal site derives from the seam's
class, or adds one beside the seam; a new `raise RuntimeError` is a claim
that the condition is a bug, and the review asks for that claim. Callers
narrow their `except` clauses to the seam they call, so a fault in an
unrelated layer no longer reads as that seam's refusal. `HARNESS_LABELS` is
gone; adding a harness means extending `Harness` and `HARNESS_DISPLAY`
together, and the type checker names every site that must follow.
