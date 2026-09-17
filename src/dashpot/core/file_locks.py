"""Per-record lock files that a pruner may delete without breaking exclusion."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def locked_path(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive ``flock`` on ``lock_path``, creating it when absent.

    The lock file may be unlinked by ``prune_lock_file`` while another
    process is still waiting on the same inode. A waiter that then acquires
    an unlinked inode would be exclusive against nobody, so after every
    acquisition the holder confirms the inode it holds is still the one
    linked at ``lock_path`` and otherwise starts over on the fresh file.
    """
    while True:
        lock = lock_path.open("a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if not _still_linked(lock.fileno(), lock_path):
                continue
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return
        finally:
            lock.close()


def prune_lock_file(lock_path: Path, guarded: Path) -> bool:
    """Delete ``lock_path`` unless the record it guards exists.

    The check and the unlink happen while holding the lock, so a writer that
    is mid-way through creating ``guarded`` is waited for rather than raced,
    and a writer queued behind this pruner re-acquires on the replacement
    file. Returns whether the lock file was removed.
    """
    with locked_path(lock_path):
        if guarded.exists():
            return False
        lock_path.unlink(missing_ok=True)
        return True


def _still_linked(descriptor: int, lock_path: Path) -> bool:
    held = os.fstat(descriptor)
    try:
        linked = lock_path.stat()
    except FileNotFoundError:
        return False
    return (held.st_dev, held.st_ino) == (linked.st_dev, linked.st_ino)
