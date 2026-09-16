"""State the Dashpot CLI error contract in one place."""

from __future__ import annotations


class DashpotError(Exception):
    """A refusal Dashpot states to a person: one ``dashpot: ...`` line, exit 2.

    Every domain error that may reach ``cli.main`` derives from this base, so
    the contract the README promises — a one-line ``dashpot: <message>``
    diagnostic on stderr and exit code 2, with no traceback — is stated and
    caught once. Existing classes keep their second base (``RuntimeError`` or
    ``ValueError``) so the ``except`` sites that translate them keep working.
    """
