"""Define the ``dashpot`` command line, one module per command group.

Each command group is a module of its own: ``observe`` (the default
command), ``init``, ``work``, ``events``, ``sources`` (``issue`` and
``pr``), ``worktrees`` (``worktree`` and ``branch``) and ``integrate``.
``root`` gathers them on the root App and runs a command line; ``shared``
holds what the groups share.
"""

from .root import main as main
