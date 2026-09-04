---
status: superseded
date: 2026-08-30
superseded-by: adr/0024-build-the-command-line-on-cyclopts.md
---

# Cyclopts for the Dashpot CLI

> **Superseded.** The migration this note prepared is done: `src/dashpot/cli.py`
> is a Cyclopts app, and the decisions it raised are recorded in
> [ADR 0024](adr/0024-build-the-command-line-on-cyclopts.md). Read this
> document as the version-pinned evidence behind that ADR — every finding below
> describes Cyclopts 4.23.3 as of 2026-08-30 and the argparse CLI as it stood
> then, not the CLI as it is now.

Research date: 2026-08-30.

Reference for migrating `src/dashpot/cli.py` (argparse) to Cyclopts. Every
claim below is checked against the Cyclopts documentation for the latest
release, the tagged source, PyPI metadata, or the GitHub release notes; items
marked **unconfirmed** could not be verified from those sources. No package was
installed and no experiment was run: the session's shell was unavailable, so the
tagged source was read from a throwaway clone instead.

Note that the upstream repository is `BrianPugh/cyclopts`, not `BrandonSmith`;
PyPI lists `https://github.com/BrianPugh/cyclopts` as the project homepage.
[PyPI project page](https://pypi.org/project/cyclopts/)

## Conclusion

Cyclopts 4.23.3 covers every feature the argparse CLI uses, with three
decisions that need care:

1. **Shared `--timeout` and other root options.** The documented mechanism is
   the meta app (`@app.meta.default` launcher that forwards `*tokens` to
   `app(tokens)`). It composes help correctly and lets the launcher pass values
   into commands through `Parameter(parse=False)` injection, but it changes
   where options may appear: known keyword options are consumed anywhere in
   the token stream, not only before the subcommand. The lighter alternative is
   repeating the shared parameters on each command (optionally as one flattened
   dataclass via `Parameter(name="*")`), which forces options *after* the
   subcommand. See [Shared options](#shared-options-across-commands).
2. **Exit codes.** Cyclopts exits 1 on usage errors, not 2, and its default
   `result_action` calls `sys.exit` itself. Keeping today's "exit 2 with
   `dashpot: <msg>` on stderr" contract means calling
   `app(argv, exit_on_error=False, result_action="return_value")` from
   `main()` and translating `CycloptsError` and `RuntimeError` there. Cyclopts
   5.0 (currently beta) moves usage errors to exit 2. See
   [Exit codes](#exit-codes-and-error-handling).
3. **`from __future__ import annotations`.** Cyclopts documents only partial
   support for stringified annotations. Function signatures are resolved with
   `typing.get_type_hints`, so `cli.py` must keep every annotation name
   importable at module scope (no `TYPE_CHECKING`-only imports for CLI
   parameter types), or drop the future import in that module. See
   [Version and compatibility](#version-and-compatibility).

Pin `cyclopts>=4.23.3,<5` until the 5.0 breaking changes are evaluated.

## Version and compatibility

| Item | Finding | Source |
| --- | --- | --- |
| Latest release | 4.23.3; the `v4.23.3` tag commit is dated 2026-08-26 and PyPI shows the same date. | [GitHub release v4.23.3](https://github.com/BrianPugh/cyclopts/releases/tag/v4.23.3), [PyPI](https://pypi.org/project/cyclopts/) |
| Pre-release | 5.0.0b1 (2026-08-06) with breaking changes: usage errors exit 2, `parse_mode` hierarchical parameter scoping, subcommands claim tokens placed after them, fuzzy command matching removed. | [GitHub release v5.0.0b1](https://github.com/BrianPugh/cyclopts/releases/tag/v5.0.0b1) |
| Python | `requires-python = ">=3.10"`; classifiers list 3.10 through 3.14. | [pyproject.toml at v4.23.3](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/pyproject.toml) |
| Runtime dependencies | `attrs>=23.1.0`, `rich>=13.6.0`, `docstring-parser>=0.15,<4.0`, `rich-rst>=1.3.1,<3.0.0`; `typing-extensions>=4.8.0` and `tomli>=2.0.0` only for Python `<3.11`. Extras `toml`, `trio`, `yaml` are optional. Dashpot targets `>=3.11`, so the footprint is attrs, rich, docstring-parser, rich-rst (rich is already a Textual dependency). | [pyproject.toml at v4.23.3](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/pyproject.toml) |
| License | Apache-2.0. | [pyproject.toml at v4.23.3](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/pyproject.toml) |
| `py.typed` | Present: `cyclopts/py.typed` (and a `cyclopts/__init__.pyi`) ship in the package directory at the tag. | [cyclopts/ tree at v4.23.3](https://github.com/BrianPugh/cyclopts/tree/v4.23.3/cyclopts) |
| String annotations | The Known Issues page says Cyclopts "can only support some scenarios" of PEP 563 and lists CPython `get_type_hints` bugs (mainly around dataclasses) and PEP 649/749 deprecation as reasons it will not chase full support. In the source, command signatures are read via `typing.get_type_hints(func, include_extras=True)` and dataclass fields via `get_type_hints(hint, include_extras=True)`, i.e. stringified hints *are* resolved, provided every name resolves in the defining module's globals. **Unconfirmed** for Dashpot's exact modules; keep `Annotated`, `Parameter`, `Path`, `Literal`, and the domain types imported at module level in `cli.py`. | [Known Issues](https://cyclopts.readthedocs.io/en/latest/known_issues.html), [field_info.py `signature_parameters`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/field_info.py) |

## Command hierarchy

- `App()` is the root. `@app.default` registers the action for "no command"
  (a sub-App cannot be a default; with no default, Cyclopts prints help).
  `@app.command` registers a function *or another `App`* as a command.
  [Commands](https://cyclopts.readthedocs.io/en/latest/commands.html)
- Nested group: `work = app.command(App(name="work", help="..."))`, then
  `@work.command def start(...)`, `@work.command def stop(...)`,
  `@work.command def show()`. Sub-apps are addressable as `app["work"]` and
  "Cyclopts's command structure is fully recursive". A sub-app with no
  `default` and no tokens prints its help, which matches today's
  `required=True` sub-parser behaviour closely enough.
  [Commands — Registering a SubCommand](https://cyclopts.readthedocs.io/en/latest/commands.html#registering-a-subcommand)
- Help resolution for a command: `help=` on the `@app.command` decorator,
  then `App.help` for sub-apps, then the registered function's docstring short
  description. Passing `help=` when registering an `App` raises `ValueError`.
  [Help — resolution order](https://cyclopts.readthedocs.io/en/latest/help.html)
- The root help page lists commands in a "Commands" panel with their short
  descriptions, plus `--help,-h` and `--version` rows; `dashpot work --help`
  shows the `work` sub-app's own panel.
  [Help](https://cyclopts.readthedocs.io/en/latest/help.html),
  [Meta App help example](https://cyclopts.readthedocs.io/en/latest/meta_app.html)
- Names: `default_name_transform` converts PascalCase to snake_case, lowercases,
  replaces `_` with `-`, and strips leading/trailing `-`. So `refresh_seconds`
  becomes `--refresh-seconds`, `state_dir` becomes `--state-dir`,
  `compact_json` becomes `--compact-json`. Override per app with
  `App(name_transform=...)`, per parameter with `Parameter(name="--x")` (manual
  names bypass the transform), or app-wide with
  `App(default_parameter=Parameter(name_transform=...))`.
  [utils.py `default_name_transform`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/utils.py),
  [Parameters — Naming](https://cyclopts.readthedocs.io/en/latest/parameters.html#naming),
  [Commands — Changing Command Name](https://cyclopts.readthedocs.io/en/latest/commands.html#changing-command-name)
- `claude-code` is a positional *value*, not a name; spell it in the `Literal`
  (see [Positional arguments and choices](#positional-arguments-and-choices)).
- `App(name="dashpot")` is optional: the name falls back to the default
  function's name, the package name for `__main__`, then `sys.argv[0]`.
  Set it explicitly so the usage line is stable under pytest.
  [API — App.name](https://cyclopts.readthedocs.io/en/latest/api.html)

## Shared options across commands

Cyclopts has no argparse "parent parser" concept. The cookbook lists exactly
two ways to share parameters: a meta app ("powerful ... a bit heavy-handed and
clunky") or a common dataclass passed to each command.
[Cookbook — Sharing Parameters](https://cyclopts.readthedocs.io/en/latest/cookbook/sharing_parameters.html)

### Option A: meta app (documented canonical example)

```python
from cyclopts import App, Group, Parameter
from typing import Annotated

app = App()
app.meta.group_parameters = Group("Session Parameters", sort_key=0)


@app.command
def foo(loops: int):
    for i in range(loops):
        print(f"Looping! {i}")


@app.meta.default
def my_app_launcher(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)], user: str
):
    print(f"Hello {user}")
    app(tokens)


app.meta()
```

`$ my-script --user=Bob foo 3` prints `Hello Bob` then the loop.
[Meta App](https://cyclopts.readthedocs.io/en/latest/meta_app.html)

What the docs and source establish:

- `*tokens` "will aggregate all remaining tokens, including those starting
  with a hyphen"; `show=False` hides it from help. The meta app "inherits many
  configuration values from its parent app and is additionally scanned when
  generating help screens", so the root `--help` shows the meta's parameters
  panel plus the parent's commands.
  [Meta App](https://cyclopts.readthedocs.io/en/latest/meta_app.html)
- Entry point becomes `app.meta()` (or `app.meta(argv, ...)`), not `app()`.
- **Where options may appear.** The doc example places `--user` before the
  subcommand. The coercion rules state that when a `*args`-style positional
  has `allow_leading_hyphen=True`, "Known keyword arguments are parsed first",
  and the example shows `--some-flag` being claimed from the *end* of the
  token list. Applied to the launcher, that means `--timeout 5` is claimed by
  the meta app wherever it appears (`dashpot init --timeout 5` as well as
  `dashpot --timeout 5 init`), and a `--timeout` after `--` is left in
  `tokens`. **Unconfirmed by experiment.** Cyclopts 5.0 changes this
  ("Subcommand Token Priority": a parameter placed after a subcommand that both
  levels recognise goes to the child; `parse_mode="strict"` rejects parent
  parameters after the subcommand).
  [Coercion Rules — List, positional](https://cyclopts.readthedocs.io/en/latest/rules.html#list),
  [GitHub release v5.0.0b1](https://github.com/BrianPugh/cyclopts/releases/tag/v5.0.0b1)
- **Getting `--timeout` into `init` / `work start`.** Two documented paths:
  1. Declare a keyword-only `Annotated[float, Parameter(parse=False)]`
     parameter on the command. It is excluded from parsing and help and is
     reported in the `ignored` dict returned by `app.parse_args(tokens)`; the
     launcher then calls `command(*bound.args, **bound.kwargs, timeout=...)`.
     The parameter "**must** be a keyword-only parameter" (or have a
     default). An app-wide regex `Parameter(parse="^(?!_)")` skips every
     `_`-prefixed keyword-only parameter the same way.
     [Meta App — Custom Command Invocation](https://cyclopts.readthedocs.io/en/latest/meta_app.html#custom-command-invocation),
     [Default Parameter — Skipping Private Parameters](https://cyclopts.readthedocs.io/en/latest/default_parameter.html#skipping-private-parameters)
  2. Simply call `app(tokens)` and have commands read the launcher's values
     from shared state (module variable, context object). Not documented as a
     pattern; it works because "Cyclopts does not modify the decorated
     function in any way".
     [Commands — Decorated Function Details](https://cyclopts.readthedocs.io/en/latest/commands.html#decorated-function-details)
- **`--help` and `--version` inside a meta app.** In `_parse_known_args` the
  help flag is looked for anywhere in the tokens (before a `--` delimiter),
  all help/version flags are stripped, and the command is replaced by the
  outermost meta parent's `help_print`. The launcher body is therefore *not*
  executed for `dashpot --help` or `dashpot work start --help`, and required
  launcher parameters do not block help. Meta commands registered with
  `@app.meta.command` bypass the launcher entirely.
  [core.py `_parse_known_args`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py),
  [Meta App — Meta Commands](https://cyclopts.readthedocs.io/en/latest/meta_app.html#meta-commands)
- **Nested-call result handling.** `App.__call__` detects a nested call
  (meta pattern) and defaults `result_action` to `"return_value"`, so the
  inner `app(tokens)` returns the command's return value to the launcher
  instead of calling `sys.exit`. The *outer* `app.meta()` still applies the
  default exit behaviour.
  [core.py `App.__call__`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py)
- Meta-app docstring is the last fallback for the root help text.
  [Help — resolution order](https://cyclopts.readthedocs.io/en/latest/help.html)

### Option B: repeat parameters on each command, optionally as one dataclass

Each command declares its own `timeout: Annotated[float, ...] = 10.0`. To
avoid duplication, put shared fields on a dataclass decorated with
`@Parameter(name="*")` (namespace flattening) and take
`common: Common | None = None` as a keyword-only parameter on every command;
the help page then shows `--url`, `--port`, `--verbose` under the command.
Options are only accepted *after* the subcommand (they belong to that
command), which is the reverse of the argparse layout today.
[Cookbook — Sharing Parameters](https://cyclopts.readthedocs.io/en/latest/cookbook/sharing_parameters.html),
[Coercion Rules — Namespace Flattening](https://cyclopts.readthedocs.io/en/latest/rules.html#namespace-flattening)

For Dashpot, only `--timeout` is genuinely shared (root default command,
`init`, `work start`); the other root options belong to the default command
alone. Option B (a plain `timeout` parameter on the three commands, with a
shared `Annotated` alias such as `Timeout = Annotated[float,
Parameter(validator=validators.Number(gt=0))]`) is the simplest and keeps
`dashpot init --timeout 5` working; it stops accepting
`dashpot --timeout 5 init`. Option A preserves the "global options first"
shape but adds the token-placement ambiguity above.

## Repeatable options with custom conversion

- `list[T]` keyword options are repeatable by default: "The keyword can be
  specified multiple times." Each occurrence consumes one element's worth of
  tokens unless `consume_multiple=True`, which consumes until the stream ends
  or an option-like token appears. `allow_repeating=False` rejects repeats.
  [Coercion Rules — List, keyword](https://cyclopts.readthedocs.io/en/latest/rules.html#keyword),
  [API — Parameter.consume_multiple](https://cyclopts.readthedocs.io/en/latest/api.html)
- **Converter signature**: `def converter(type_, tokens) -> Any` where
  `type_` is the parameter's type hint and `tokens` is "a `list[cyclopts.Token]`
  of CLI tokens" (a `dict` of tokens when dotted keys are used). Bound
  classmethods receive `(cls, tokens)`. "Typically, the converter function will
  receive a single token, but it may receive multiple tokens if the annotated
  type is iterable (e.g. list, set)", and `Parameter(n_tokens=...)` overrides
  the inferred count.
  [API — Parameter.converter](https://cyclopts.readthedocs.io/en/latest/api.html),
  [Coercion Rules — intro](https://cyclopts.readthedocs.io/en/latest/rules.html),
  [Parameters — Converters](https://cyclopts.readthedocs.io/en/latest/parameters.html#converters)
- `Token` is a frozen attrs class with `keyword: str | None` (`None` when
  positional), `value: str`, `source: str` (`"cli"` for CLI tokens),
  `index: int`, `keys: tuple[str, ...]`, `implicit_value`.
  [API — Token](https://cyclopts.readthedocs.io/en/latest/api.html),
  [token.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/token.py)
- Whether a converter on a `list[Workspace]` parameter is invoked once with
  all tokens across repeated `--workspace` occurrences, or once per element,
  is **unconfirmed** from the docs. Two shapes avoid the question: declare
  `workspace: list[str] | None = None` and convert in the command body (a
  `RuntimeError` there still lands in the `dashpot: <msg>` path), or decorate
  a converter with `@Parameter(n_tokens=1, accepts_keys=False)` and use it as
  the element converter. The doc shows `@Parameter(converter=parse_point)`
  applied to a *class*; decorating `Workspace` (a domain value) with CLI
  metadata is undesirable, so prefer the string-list shape or a small
  `Annotated` element alias, and verify with a test.
  [Parameters — Controlling Token Count](https://cyclopts.readthedocs.io/en/latest/parameters.html#controlling-token-count)
- **Raising errors from a converter.** The docs describe error promotion only
  for *validators*: "Any of `AssertionError`, `TypeError` or `ValidationError`
  will be promoted to a `cyclopts.ValidationError`" (the Parameters page says
  `ValueError`, `TypeError`, `AssertionError`). What a converter's `ValueError`
  renders as is **unconfirmed**; `CoercionError(msg=...)` exists for a custom
  message and is prefixed with `Invalid value for --workspace: ` when raised
  for a keyword token. A validator is the documented place for
  "workspace must be PATH or NAME=PATH".
  [Parameter Validators](https://cyclopts.readthedocs.io/en/latest/parameter_validators.html),
  [Parameters — Validating Input](https://cyclopts.readthedocs.io/en/latest/parameters.html#validating-input),
  [exceptions.py `CoercionError`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/exceptions.py)
- **Metavar**: there is no `Parameter` field for a display value name; the
  full attribute list (`name`, `alias`, `short_alias`, `converter`,
  `validator`, `group`, `negative*`, `allow_leading_hyphen`, `requires_equals`,
  `parse`, `required`, `show`, `show_default`, `show_choices`, `help`,
  `show_env_var`, `env_var`, `env_var_split`, `name_transform`,
  `accepts_keys`, `consume_multiple`, `json_dict`, `json_list`, `count`,
  `allow_repeating`, `n_tokens`) contains nothing like argparse `metavar`.
  Keyword-only parameters render as just `--workspace`; positional-capable
  ones render as `NAME --name`. Put `[NAME=]PATH` in the help text.
  [API — Parameter](https://cyclopts.readthedocs.io/en/latest/api.html),
  [Parameters — Manual Naming example](https://cyclopts.readthedocs.io/en/latest/parameters.html#manual-naming)
- **Defaults for list parameters.** The docs recommend `list | None = None`
  and building the real list in the body (mutable-default warning). Every
  iterable parameter also gets an auto-generated `--empty-<name>` negative
  flag; disable it with `Parameter(negative="")` or app-wide
  `App(default_parameter=Parameter(negative=()))`.
  [Coercion Rules — Empty List](https://cyclopts.readthedocs.io/en/latest/rules.html#empty-list),
  [API — Parameter.negative](https://cyclopts.readthedocs.io/en/latest/api.html)

## Validators

- Signature `def validator(type_, value: Any) -> None`; runs after conversion;
  `ValueError` / `TypeError` / `AssertionError` are re-rendered as
  `ValidationError`. Multiple validators may be given as a list.
  [Parameter Validators](https://cyclopts.readthedocs.io/en/latest/parameter_validators.html)
- Built-ins: `cyclopts.validators.Number(lt=, lte=, gt=, gte=, modulo=)`,
  `validators.Path(exists=...)`, `validators.Slice`, and pre-annotated types
  such as `cyclopts.types.PositiveFloat`, `NonNegativeFloat`.
  [API — Validators and Types](https://cyclopts.readthedocs.io/en/latest/api.html#validators)
- Messages: `Number(gte=0)` raises `ValueError("Must be >= 0.")`, `gt=0`
  raises `"Must be > 0."`; the rendered error is
  `Invalid value "-1" for "AGE". Must be >= 0.` for a positional token, and
  uses the keyword (e.g. `--timeout`) when supplied by keyword.
  [validators/_number.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/validators/_number.py),
  [exceptions.py `ValidationError`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/exceptions.py)
- Multiple `Parameter` annotations stack; attributes resolve right-to-left, so
  `Annotated[PositiveFloat, Parameter(help="...")]` works.
  [Parameters — Parameter Resolution](https://cyclopts.readthedocs.io/en/latest/parameters.html#parameter-resolution)

## Boolean flags

- A keyword `bool` is a flag; the default false-like flag is `--no-<name>`.
  `--flag=true|false` is also accepted.
  [Coercion Rules — Bool](https://cyclopts.readthedocs.io/en/latest/rules.html#bool)
- Suppress the negative form per parameter with `Parameter(negative="")`
  (an empty list or string disables it), or app-wide with
  `App(default_parameter=Parameter(negative=()))`; help then shows only
  `--json`. A group-level `Group(default_parameter=Parameter(negative=""))`
  does the same for its members.
  [API — Parameter.negative](https://cyclopts.readthedocs.io/en/latest/api.html),
  [Default Parameter](https://cyclopts.readthedocs.io/en/latest/default_parameter.html),
  [Group Validators — LimitedChoice example](https://cyclopts.readthedocs.io/en/latest/group_validators.html#limitedchoice)
- Flags show `[default: False]` in help unless `show_default=False`.
  [Group Validators — LimitedChoice example](https://cyclopts.readthedocs.io/en/latest/group_validators.html#limitedchoice)

## Mutually exclusive options

```python
action = Group(
    "Action",
    default_parameter=Parameter(negative=""),
    validator=validators.MutuallyExclusive(),  # alias for LimitedChoice()
)


@app.command
def integrate(
    harness: Literal["codex", "claude-code"],
    *,
    status: Annotated[bool, Parameter(group=action)] = False,
    remove: Annotated[bool, Parameter(group=action)] = False,
): ...
```

- `Group(name="", help="", *, show=None, sort_key=None, validator=None,
  default_parameter=None, help_formatter=None)`; a group validator has the
  signature `validator(argument_collection: ArgumentCollection)` and is
  "always invoked, regardless if any argument within the collection has
  token(s)". A group without a name is not shown as a panel.
  [group.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/group.py),
  [API — Group](https://cyclopts.readthedocs.io/en/latest/api.html)
- `LimitedChoice(min=0, max=None, allow_none=False)`; `max` defaults to 1 when
  `min == 0`. `MutuallyExclusive()` is `LimitedChoice()` with no arguments,
  and `validators.mutually_exclusive` is a pre-built instance.
  [validators/_group.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/validators/_group.py)
- Error text: `Invalid values for group "Vehicle (choose one)". Mutually
  exclusive arguments: {--car, --truck}`; with other bounds:
  `Received N arguments: {...}. Only [min, max] choices may be specified.`
  [Group Validators — LimitedChoice](https://cyclopts.readthedocs.io/en/latest/group_validators.html#limitedchoice)
- A parameter may belong to several groups:
  `Parameter(group=(app.group_parameters, action))`.
  [Groups](https://cyclopts.readthedocs.io/en/latest/groups.html)

## Positional arguments and choices

- `Literal["codex", "claude-code"]` is "the recommended way of providing the
  user a set of choices"; options are tried left-to-right, coercing the token
  into each option's type. Help shows `[choices: codex, claude-code]`
  (`show_choices=True` by default). The error for an unknown token is
  `Invalid value "fizz" for VALUE. Choose from: "foo", "bar", 3.` and the
  source appends ` Did you mean "..."?` when a close match exists.
  [Coercion Rules — Literal](https://cyclopts.readthedocs.io/en/latest/rules.html#literal),
  [exceptions.py `CoercionError`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/exceptions.py)
- A plain `reference: str` positional-or-keyword parameter renders as
  `REFERENCE --reference` and accepts either form; make it positional-only
  with `/` to show only `REFERENCE` (positional-only parameters land in the
  "Arguments" panel, others in "Parameters").
  [Coercion Rules — Positional Only With Subsequent Parameters](https://cyclopts.readthedocs.io/en/latest/rules.html#positional-only-with-subsequent-parameters),
  [API — App.group_arguments](https://cyclopts.readthedocs.io/en/latest/api.html)
- Tokens such as `#7` and `ned2/dashpot#7` are not option-like (only tokens
  starting with `-` are, excluding negative numbers and slices), so they parse
  positionally without `allow_leading_hyphen`.
  [utils.py `is_option_like`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/utils.py)

## Help text

- Docstrings are parsed with `docstring_parser.parse` (no explicit style, so
  the library's auto-detection applies; the documented examples use NumPy
  `Parameters\n----------` sections). Cyclopts first joins the summary block
  into one line; a long description "**must** also have a short description".
  Parameter help comes from the docstring entry keyed by the *Python* name, or
  from `Parameter(help=...)`, which wins.
  [help/help.py `docstring_parse`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/help/help.py),
  [Help — Markup Format](https://cyclopts.readthedocs.io/en/latest/help.html#markup-format),
  [Parameters — Help](https://cyclopts.readthedocs.io/en/latest/parameters.html#help)
- `App(help=...)` sets the app description; `help_format` is
  `"markdown"` (default), `"plaintext"`, `"rich"`, or `"restructuredtext"`/
  `"rst"`, inherited by sub-apps; `help_prologue` / `help_epilogue` add text
  around the panels; `App(usage=...)` replaces the `Usage:` line (empty string
  removes it); `help_flags` changes or disables `--help`/`-h`.
  [Help](https://cyclopts.readthedocs.io/en/latest/help.html),
  [API — App](https://cyclopts.readthedocs.io/en/latest/api.html)
- Output is Rich panels (rounded boxes titled "Commands", "Parameters",
  "Arguments", or the group name). `help_formatter="plain"` selects a
  no-frills `PlainFormatter`.
  [API — App.help_formatter](https://cyclopts.readthedocs.io/en/latest/api.html)
- Help goes to `App.console`, which "defaults to stdout"; errors go to
  `App.error_console`, which "defaults to stderr" and, when not set, is a
  copy of the main console with `stderr=True` and the same width/colour
  settings. Both can be passed per call (`app(tokens, console=...,
  error_console=...)`).
  [App Calling — Exception Handling](https://cyclopts.readthedocs.io/en/latest/app_calling.html#exception-handling-and-exiting),
  [utils.py `create_error_console_from_console`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/utils.py)
- Exit code after `--help`: `help_print` returns `None`; under the default
  `result_action` a `None` result becomes `sys.exit(0)`. With
  `result_action="return_value"` the call simply returns `None`.
  [core.py `help_print`, `_handle_result_action`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py),
  [_result_action.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/_result_action.py)
- Deterministic width/colour for tests: construct
  `rich.console.Console(file=..., width=80, force_terminal=False,
  color_system=None)` and pass it as `App(console=...)` or `app(tokens,
  console=...)`; the derived error console copies `width`, `no_color`, and
  `color_system`. Rich's own `NO_COLOR`/`TERM` handling also applies but is a
  Rich detail, not documented by Cyclopts.
  [API — App.console](https://cyclopts.readthedocs.io/en/latest/api.html)

## `--version`

- Cyclopts adds `--version` by default. Resolution: explicit `App(version=str
  | callable)`; else `importlib.metadata.version()` of the package that
  instantiated the `App` (derived from the calling module); else that
  package's `__version__`; else `"0.0.0"`. For an installed `dashpot`
  distribution this prints the project version with no extra code.
  [Version](https://cyclopts.readthedocs.io/en/latest/version.html),
  [core.py `_get_fallback_version_string`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py)
- Disable with `App(version_flags="")` or `App(version_flags=[])`; rename
  with `version_flags=["--version", "-v"]`. Sub-apps inherit `version`.
  [Version](https://cyclopts.readthedocs.io/en/latest/version.html)

## Exit codes and error handling

- Exception family (all `CycloptsError` subclasses, attrs classes):
  `ValidationError`, `CoercionError`, `UnknownOptionError`,
  `UnknownCommandError`, `UnusedCliTokensError`, `MissingArgumentError`,
  `ConsumeMultipleError`, `RequiresEqualsError`, `RepeatArgumentError`,
  `MixedArgumentError`, `CombinedShortOptionError`. `CommandCollisionError`
  and `DocstringError` are developer errors and do not derive from
  `CycloptsError`. There is no per-exception `exit_code` attribute in 4.23.3.
  [exceptions.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/exceptions.py)
- Default behaviour on a parse/validation error: print a red `Error` panel
  (`CycloptsPanel`) on the error console (stderr), then `sys.exit(1)`.
  `exit_on_error=False` re-raises the exception instead (the panel is still
  printed unless `print_error=False`); `help_on_error=True` prints the help
  page first; `error_formatter` replaces the panel with any Rich renderable,
  e.g. `lambda e: f"dashpot: {e}"`. All of these are `App` attributes and
  per-call overrides, inherited by sub-apps.
  [App Calling — Exception Handling](https://cyclopts.readthedocs.io/en/latest/app_calling.html#exception-handling-and-exiting),
  [core.py `parse_args`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py)
- Exit code 2 for usage errors is **not** available in 4.x; it is a 5.0
  breaking change ("parse errors now exit with code 2, matching
  argparse/Click"). To keep exit 2 today, catch `CycloptsError` in `main()`.
  [GitHub release v5.0.0b1](https://github.com/BrianPugh/cyclopts/releases/tag/v5.0.0b1)
- Application exceptions raised *inside* a command are untouched: "Cyclopts is
  hands-off when it comes to handling exceptions and exiting the application"
  except for its own runtime errors. `KeyboardInterrupt` is swallowed into
  `sys.exit(130)` unless `suppress_keyboard_interrupt=False`. So the
  `RuntimeError` -> `dashpot: <msg>` + exit 2 translation stays in `main()`.
  [App Calling — Exception Handling](https://cyclopts.readthedocs.io/en/latest/app_calling.html#exception-handling-and-exiting),
  [API — App.suppress_keyboard_interrupt](https://cyclopts.readthedocs.io/en/latest/api.html)
- Return values: `App.__call__` "returns the command's value per
  `result_action`". The default `"print_non_int_sys_exit"` prints non-int
  results and calls `sys.exit` (bool -> 0/1, int -> that code, else 0), which
  is chosen so `app()` behaves the same as a script and as a console entry
  point. For a `main() -> int` entry point (`dashpot = "dashpot.cli:main"`)
  use `result_action="return_int_as_exit_code_else_zero"` (never prints;
  int/bool become the code, anything else 0) or `"return_value"`, and let
  the console script's `sys.exit(main())` apply it.
  [App Calling — Return Value](https://cyclopts.readthedocs.io/en/latest/app_calling.html#return-value),
  [API — App.result_action](https://cyclopts.readthedocs.io/en/latest/api.html)

Resulting `main()` shape (Option B command layout):

```python
def main(argv: Sequence[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    try:
        app(
            tokens,
            exit_on_error=False,
            result_action="return_int_as_exit_code_else_zero",
        )
    except CycloptsError:
        return 2  # usage error; panel already printed on stderr
    except RuntimeError as exc:
        print(f"dashpot: {exc}", file=sys.stderr)
        return 2
    return 0
```

Passing an explicit token list also avoids the pytest warning described under
[Testing patterns](#testing-patterns). With `error_formatter=lambda e:
f"dashpot: {e}"` the usage-error output loses the panel and matches the
application-error line format; `str(e)` "for just the message text" is
documented.
[App Calling — Custom Error Formatting](https://cyclopts.readthedocs.io/en/latest/app_calling.html#custom-error-formatting)

## Testing patterns

- Call the app with explicit tokens: `app(["work", "start", "#7"])` or the
  string form `app("work start #7")` (split with `shlex.split`). Use
  `result_action="return_value"` (or the entry-point-friendly action above) so
  the call does not `sys.exit`.
  [App Calling — Input Command](https://cyclopts.readthedocs.io/en/latest/app_calling.html#input-command)
- Signatures in 4.23.3:
  - `App.parse_args(tokens=None, *, console=None, error_console=None,
    print_error=None, exit_on_error=None, help_on_error=None, verbose=None,
    end_of_options_delimiter=None, error_formatter=None) ->
    tuple[Callable, inspect.BoundArguments, dict[str, Any]]`; the dict is
    `ignored` (`parse=False` parameters). Raises `UnusedCliTokensError` when
    tokens remain.
  - `App.parse_known_args(tokens=None, *, console=None, error_console=None,
    end_of_options_delimiter=None) -> (command, bound, unused_tokens,
    ignored)`.
  - `App.__call__(tokens=None, *, console, error_console, print_error,
    exit_on_error, help_on_error, verbose, end_of_options_delimiter, backend,
    result_action, error_formatter) -> Any`.
  [core.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py)
- `parse_args` is the seam for asserting bound values without executing the
  command: `command, bound, _ = app.parse_args(["--timeout", "5", "--json"])`
  then inspect `bound.arguments`. Note it still prints and exits on error
  unless `exit_on_error=False` / `print_error=False` are passed.
  [core.py `parse_args`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py)
- Capturing output: pass a `Console(file=io.StringIO(), width=...)` via
  `console=` for help, and `error_console=` for errors, or rely on pytest
  `capsys` (the default consoles write to `sys.stdout`/`sys.stderr`). The
  docs' own examples use `capsys` with `exit_on_error=False` for error cases.
  [App Calling — Exception Handling](https://cyclopts.readthedocs.io/en/latest/app_calling.html#exception-handling-and-exiting)
- Guard rail: when `tokens is None` under pytest (`PYTEST_VERSION` set),
  Cyclopts emits `UserWarning: Cyclopts application invoked without tokens
  under unit-test framework "pytest". Did you mean "app([])"?`. Always pass a
  list in tests (and in `main()` when `argv` is supplied).
  [core.py `_log_framework_warning`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py)
- Exit codes are observable as `SystemExit` from `app(...)` when
  `exit_on_error` is left on; `pytest.raises(SystemExit)` and `.value.code`
  work as usual (standard Python behaviour, not Cyclopts-specific).

## Path and float conversion

- `pathlib.Path` parameters are converted automatically (the docs use
  `Path` positionals throughout, and `validators.Path` / `cyclopts.types.
  ExistingPath` add existence checks). No `expanduser()` is applied; keep the
  explicit `.expanduser()` calls.
  [Parameter Validators — Path](https://cyclopts.readthedocs.io/en/latest/parameter_validators.html#path),
  [API — Annotated Path Types](https://cyclopts.readthedocs.io/en/latest/api.html)
- `float` is `float(token)`. A bad token renders as
  `Invalid value for --timeout: unable to convert "abc" into float.`
  (positional form: `Invalid value for TIMEOUT: unable to convert ...`).
  [Coercion Rules — Float](https://cyclopts.readthedocs.io/en/latest/rules.html#float),
  [exceptions.py `CoercionError`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/exceptions.py)
- Negative numbers are not treated as options, so `--refresh-seconds -1`
  reaches the validator rather than raising `UnknownOptionError`.
  [utils.py `is_option_like`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/utils.py)

## Config and environment sources

Not needed now. `App(config=...)` accepts callables that inject values before
conversion; built-ins are `cyclopts.config.Toml`, `Yaml`, `Json`, `Dict`, and
`Env(prefix)` (derives `PREFIX_COMMAND_PARAM` names). A single parameter can
also declare `Parameter(env_var="DASHPOT_TIMEOUT")`, shown in help unless
`show_env_var=False`. CLI beats env beats config beats Python default.
[Config Files](https://cyclopts.readthedocs.io/en/latest/config_file.html),
[API — Config, Parameter.env_var](https://cyclopts.readthedocs.io/en/latest/api.html)

## Other things a migrator should know

- **`Optional` / unions**: union members are tried left-to-right; `None` is
  ignored, so `Path | None = None` behaves as `Path` with a `None` default.
  `show_default` hides a `None` default automatically.
  [Coercion Rules — Union](https://cyclopts.readthedocs.io/en/latest/rules.html#union),
  [API — Parameter.show_default](https://cyclopts.readthedocs.io/en/latest/api.html)
- **`Annotated` placement**: `Annotated[T, Parameter(...)]` on the parameter;
  stacked annotations resolve right-to-left; app-wide defaults come from
  `App(default_parameter=Parameter(...))`, then `Group.default_parameter`,
  then the annotation (highest priority). Any field set to `None` reverts to
  the Cyclopts default.
  [Default Parameter — Resolution Order](https://cyclopts.readthedocs.io/en/latest/default_parameter.html#resolution-order)
- **Keyword-only parameters** (`*,`) are how to make an option keyword-only in
  the CLI; otherwise every parameter is also positional and shows as
  `NAME --name`. Use `*` for all of the root options.
  [Parameters — Manual Naming example](https://cyclopts.readthedocs.io/en/latest/parameters.html#manual-naming)
- **`*args`**: consumed as a list; with `allow_leading_hyphen=True` it also
  swallows option-like tokens (the meta-app forwarding trick). Tokens after
  `--` are always positional; `App(end_of_options_delimiter="")` disables the
  delimiter.
  [Coercion Rules — List, positional](https://cyclopts.readthedocs.io/en/latest/rules.html#positional),
  [API — App.end_of_options_delimiter](https://cyclopts.readthedocs.io/en/latest/api.html)
- **Repeated scalar options** raise `RepeatArgumentError` by default
  (`Parameter --x specified multiple times.`); argparse's last-wins needs
  `Parameter(allow_repeating=True)`.
  [API — Parameter.allow_repeating](https://cyclopts.readthedocs.io/en/latest/api.html)
- **`App(help_on_error=True)`** prints the help page before every usage
  error; leave it off to keep stderr short.
  [API — App.help_on_error](https://cyclopts.readthedocs.io/en/latest/api.html)
- **`App(help_flags=...)` / `App(version_flags=...)`** accept a string, a
  list, or empty to disable.
  [Help — Help Flags](https://cyclopts.readthedocs.io/en/latest/help.html#help-flags),
  [Version](https://cyclopts.readthedocs.io/en/latest/version.html)
- **Sub-app inheritance**: `exit_on_error`, `print_error`, `help_format`,
  `version`, group defaults, and `name_transform` flow from parent to child
  unless overridden.
  [Commands — SubCommand Configuration](https://cyclopts.readthedocs.io/en/latest/commands.html#subcommand-configuration),
  [API — App.name_transform](https://cyclopts.readthedocs.io/en/latest/api.html)
- **Meta help composition**: `app.meta.group_parameters = Group("Session
  Parameters", sort_key=0)` renames and orders the meta panel; default groups
  (`Commands`, `Arguments`, `Parameters`) sort first unless given `sort_key`.
  [Meta App](https://cyclopts.readthedocs.io/en/latest/meta_app.html),
  [API — Group.sort_key](https://cyclopts.readthedocs.io/en/latest/api.html)
- **Fuzzy command matching**: 4.x tolerates `foo_bar` for `foo-bar` as a
  compatibility shim; 5.0 removes it. Do not rely on it in tests.
  [core.py `_normalize_for_matching`](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/core.py),
  [GitHub release v5.0.0b1](https://github.com/BrianPugh/cyclopts/releases/tag/v5.0.0b1)
- **Docstring voice**: parameter docs must use the Python name even when the
  CLI name differs; a docstring with a long description without a short one
  fails the assertion in `docstring_parse`.
  [Help](https://cyclopts.readthedocs.io/en/latest/help.html),
  [help/help.py](https://github.com/BrianPugh/cyclopts/blob/v4.23.3/cyclopts/help/help.py)

## Prototype verification (2026-08-30)

A throwaway script modelling the proposed command layout was run against
Cyclopts 4.23.3 (`uv run --no-project --with cyclopts==4.23.3`, outside the
project environment, so `uv.lock` was untouched). It resolves the items marked
unconfirmed above:

- **`from __future__ import annotations`** works for a module whose parameter
  types (`Annotated`, `Parameter`, `Path`, `Literal`, the domain dataclass) are
  imported at module scope.
- **List converters receive every token at once.** With
  `Annotated[list[Workspace] | None, Parameter(converter=f, n_tokens=1,
  accepts_keys=False)]`, `--workspace a=/tmp --workspace /tmp/b` calls `f`
  exactly once with both tokens, and `f` must return the whole list. Without
  `n_tokens=1, accepts_keys=False` Cyclopts inspects the dataclass and demands
  one token per field (`Parameter --workspace requires 2 positional
  arguments. Only got 1.`). A `ValueError("workspace must be PATH or
  NAME=PATH")` raised inside the converter renders as
  `Invalid value for --workspace: workspace must be PATH or NAME=PATH`,
  the same text as raising `CoercionError(msg=...)` explicitly.
- **Option placement under Option B.** `dashpot init --timeout 5` and
  `dashpot work start ned2/dashpot#7 --timeout 3` bind `timeout`; the argparse
  layout `dashpot --timeout 5 init` fails with `Unused Tokens: ['init'].`
- **Validation rendering** with `error_formatter=lambda e: f"dashpot: {e}"`:
  `dashpot: Invalid value "0.0" for --timeout. Must be > 0.`,
  `dashpot: Invalid value for --timeout: unable to convert "abc" into float.`,
  `dashpot: Invalid value "-1.0" for --refresh-seconds. Must be >= 0.`,
  `dashpot: Invalid values for group Action. Mutually exclusive arguments:
  {--status, --remove}`, `dashpot: Invalid value "emacs" for HARNESS. Choose
  from: "codex", "claude-code".`, `dashpot: Unknown command "bogus".
  Available commands: start, stop, show.`, `dashpot: Unknown option: --bogus.`
- **Negative flags.** `App(default_parameter=Parameter(negative=()))` removes
  both `--no-json` and `--empty-workspace` (`Unknown option: --no-json. Did you
  mean --json?`). `show_default=False` on the same default parameter drops the
  `[default: False]` suffix from flags (and from every other parameter).
- **Exit codes.** `app(argv, exit_on_error=False,
  result_action="return_int_as_exit_code_else_zero")` returns the command's
  int; `CycloptsError` propagates after the formatted line is printed, and a
  `RuntimeError` raised by a command propagates untouched, so `main()` can map
  both to exit 2. `dashpot work` with no subcommand prints the `work` help
  page and returns 0, where argparse's `required=True` sub-parser exited 2.
- **`--version`** prints `0.0.0` from a bare script; installed as the
  `dashpot` distribution it would print the project version.
- **`app.parse_args(argv, exit_on_error=False, print_error=False)`** returns
  `(command, BoundArguments, ignored)` and is a workable test seam for bound
  values without executing the command.
- **Help pages** render `Usage: dashpot COMMAND [OPTIONS]`, a Commands panel
  (`init`, `integrate`, `work`, `--help (-h)`, `--version`) and a Parameters
  panel; positional-only parameters land in an Arguments panel with a
  `[required]` marker and `[choices: codex, claude-code]` for the `Literal`.
  A `Console(file=io.StringIO(), width=80, force_terminal=False,
  color_system=None)` passed as `console=` makes the output deterministic.
