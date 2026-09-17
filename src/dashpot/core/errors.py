"""State the Dashpot CLI error contract in one place."""

from __future__ import annotations


class DashpotError(Exception):
    """A refusal Dashpot states to a person: one ``dashpot: ...`` line, exit 2.

    Every domain error that may reach ``cli.main`` derives from this base, so
    the contract the README promises — a one-line ``dashpot: <message>``
    diagnostic on stderr and exit code 2, with no traceback — is stated and
    caught once. Each seam raises its own subclass (``GitError``,
    ``IssueWorkError``, ``ProjectConfigError``, …) so a caller that must tell
    one refusal from another catches that class, never a built-in type.

    Two kinds of ``RuntimeError`` deliberately stay outside the contract:

    - A programmer fault — an exhaustive guard over a closed union, a plan
      missing the value its own builder must have set — is a bug to fix, not
      a refusal to state, and ``cli.main`` lets it traceback.
    - The observation boundary (``core.observation_errors``) still contains
      ``RuntimeError`` beside this base: a dashboard keeps running on an
      adapter's runtime fault, such as a symlink loop under ``Path.resolve``,
      and reports it as a Diagnostic.

    Public classes that predate the contract keep their second base
    (``RuntimeError`` or ``ValueError``) for callers outside the package that
    still catch the built-in type; new subclasses, and a module-private class
    caught beside its raise, derive from this base alone (ADR 0046).
    """
