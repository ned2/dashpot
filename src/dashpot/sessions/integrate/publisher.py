"""Report the hook publisher ``integrate`` binds, and the linked Worktree it may live in.

A publisher in a linked Worktree's ``.venv`` is removed with that Worktree,
and every hook event fails from then on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ...core.git import GitError
from ...core.model import Harness
from ...core.worktree_paths import main_worktree, worktree_records, worktree_root


@dataclass(frozen=True, slots=True)
class LinkedWorktreeBinding:
    """A hook publisher that a linked Worktree's lifetime would take away."""

    worktree: Path
    # None when the Repository is bare: every checkout is then a linked
    # Worktree and there is no main working tree to run the command from.
    main_worktree: Path | None


def linked_worktree_binding(command: Path) -> LinkedWorktreeBinding | None:
    """Name the linked Worktree holding a hook publisher, if one does.

    A publisher inside a linked Worktree — its ``.venv`` — is removed with
    that Worktree when its Issue is finished, and every hook event fails
    from then on. One in the main working tree, or outside any Git working
    tree such as a tool installation, has no such lifetime.
    """
    # When Git cannot answer — no Repository holds the publisher, or Git
    # itself is unavailable — the binding is not refused: the refusal names
    # the one lifetime it can see, and ordinary installation does not wait
    # on Git to prove a negative.
    try:
        root = worktree_root(command.parent)
        records = worktree_records(root)
    except GitError:
        return None
    main = main_worktree(records)
    if root == main:
        return None
    return LinkedWorktreeBinding(
        worktree=root, main_worktree=None if "bare" in records[0] else main
    )


def linked_worktree_consequence(
    arguments: str,
    binding: LinkedWorktreeBinding,
    *,
    publisher: str = "that publisher lives",
) -> str:
    """Say what binding a linked Worktree's publisher would do, and how to rerun.

    ``arguments`` are the ones the rerun names, such as ``codex`` or
    ``--installed``.
    """
    rerun = f"run 'dashpot integrate {arguments}' from "
    if binding.main_worktree is not None:
        rerun += f"the main working tree {binding.main_worktree} or from "
    return (
        f"{publisher} in the linked Worktree {binding.worktree}, which "
        "is removed when its Issue is finished, and every hook event would fail "
        f"from then on; {rerun}an installed tool environment"
    )


def publisher_status(harness: Harness, shown: str, executable: Path) -> list[str]:
    """Report the hook publisher an installed integration runs, shown as it is bound."""
    if not executable.is_file():
        return [
            f"hook publisher missing at {shown}; run "
            f"'dashpot integrate {harness}' to repair"
        ]
    if not os.access(executable, os.X_OK):
        return [f"hook publisher at {shown} is not executable"]
    messages = [f"hook publisher: {shown}"]
    # While the file still exists the binding only looks healthy; say now
    # what removing its Worktree will do.
    binding = linked_worktree_binding(executable)
    if binding is not None:
        messages.append(f"warning: {linked_worktree_consequence(harness, binding)}")
    return messages
