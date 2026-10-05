"""Define the ``dashpot`` command line and state every refusal on one line.

Each command group is a module of its own: ``observe`` (the default
command), ``init``, ``work``, ``events``, ``sources`` (``issue`` and
``pr``), ``worktrees`` (``worktree`` and ``branch``) and ``integrate``.
``root`` gathers them on the root App and runs a command line; ``shared``
holds what the groups share.
"""

from .root import main as main
