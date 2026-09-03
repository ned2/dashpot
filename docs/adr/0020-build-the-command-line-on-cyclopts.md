---
status: accepted
date: 2026-09-04
---

# Build the command line on Cyclopts, with per-command options

Dashpot's command line began as hand-rolled `argparse`: one parser per
management command, manual `add_argument` calls for every shared option, and
hand-written conversion from strings to the domain values the commands take —
`Workspace`, `RepositoryAnchor`, a timeout, a path. As `init`, `integrate`,
`work`, `issue show`, `worktree create` / `check` / `remove`, and
`branch delete` accumulated, the parser grew a second, untyped description of
each command's signature beside the function that implements it, and the two
drifted. The [Cyclopts research note](../cyclopts-cli-migration-research.md)
measured the alternative against the CLI as it stood.

Dashpot builds its command line on [Cyclopts](https://cyclopts.readthedocs.io/)
(`cyclopts>=4.23.3,<5`). A command is a plain annotated function registered on
an `App`; its signature is the parser, so the option set, the types, and the
help text have one definition. `Annotated[..., Parameter(...)]` carries the
converters and validators that turn tokens into domain values at the CLI seam,
which is the same seam-shaped validation
[ADR 0013](0013-adopt-pydantic-models-by-seam.md) applies to persisted and
published values.

Three details the research flagged are decided here, because each one is
visible in the CLI's contract:

- **Shared options are repeated on each command, not hoisted into a meta
  app.** `--timeout` and its siblings are declared per command as the shared
  `_Timeout` annotation. An option therefore belongs to the command it
  follows: `dashpot init --timeout 5`, never `dashpot --timeout 5 init`. The
  meta-app launcher would let a known option appear anywhere in the token
  stream, which reads as a global flag Dashpot does not have.
- **Dashpot owns its exit codes.** `main()` calls the app with
  `exit_on_error=False` and `result_action="return_int_as_exit_code_else_zero"`
  and translates `CycloptsError` itself, so every command failure — invalid
  input, a startup error, or a refused operation — stays one
  `dashpot: <message>` line on stderr and exit 2, with no traceback and no
  usage dump. Cyclopts' own default would exit 1 on a usage error and call
  `sys.exit` from inside the parse.
- **`cli.py` keeps `from __future__ import annotations`, and every CLI
  parameter type stays importable at module scope.** Cyclopts resolves
  signatures with `typing.get_type_hints`, so a `TYPE_CHECKING`-only import of
  a parameter type would fail at parse time rather than at type-check time.

## Considered options

- **Keep `argparse`:** rejected. It is in the standard library and needs no
  pin, but it duplicates every signature, converts nothing, and made the
  growing command tree the largest untyped surface in the package.
- **Typer or Click:** rejected. Both are mature and widely used, but Click's
  decorator options repeat the signature the way `argparse` does, and Typer
  resolves fewer annotation shapes than Cyclopts — `Literal` unions, the
  frozen domain values, and `list[T]` with a custom converter are exactly what
  Dashpot's parameters are made of.
- **Cyclopts 5.0:** rejected for now and pinned out with `<5`. Its beta moves
  usage errors to exit 2 (which Dashpot already does for itself) but also
  changes parameter scoping and token claiming, and removes fuzzy command
  matching. The upgrade is its own decision.
- **The meta-app launcher for shared options:** rejected, as above.

## Consequences

- `cyclopts>=4.23.3,<5` is a runtime dependency. Its own footprint on Python
  3.11+ is `attrs`, `rich`, `docstring-parser`, and `rich-rst`; `rich` already
  ships as a Textual dependency.
- Every command's options are documented by its own `--help`, and the
  option-placement rule is stated in the README's
  [Usage](../../README.md#usage) section.
- The [Cyclopts research note](../cyclopts-cli-migration-research.md) is
  superseded by this ADR: it describes the migration as prospective and its
  version findings are pinned to 2026-08-30.
- Raising the pin past `<5` requires re-checking the exit-code, scoping, and
  token-claiming changes against `main()` and the per-command options.
