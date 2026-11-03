"""Probe or hold a Codex writer-lock file for the Codex 663 unload and resume run.

Codex takes an advisory ``flock`` on ``<CODEX_HOME>/thread-writer-locks/<id>.lock``
while a runtime owns a thread, and on ``.coordination.lock`` beside it while it
creates or removes one. ``probe PATH`` prints ``absent`` when no file exists,
``held`` when another process holds the file's lock, and ``free`` when the file
exists unlocked; it never creates the file. ``hold PATH`` takes the lock,
waiting until it is free, prints ``acquired <ms>``, keeps it until its
standard input closes, then prints ``released <ms>``.
"""

from __future__ import annotations

import fcntl
import sys
import time


def now() -> int:
    """Milliseconds since the epoch, as the runner's clock reads them."""
    return time.time_ns() // 1_000_000


def probe(path: str) -> str:
    """Whether another process holds the lock on ``path``."""
    try:
        handle = open(path, "rb")  # ruff: ignore[open-file-with-context-handler] - closed below on every path
    except FileNotFoundError:
        return "absent"
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "held"
        fcntl.flock(handle, fcntl.LOCK_UN)
        return "free"


def hold(path: str) -> None:
    """Hold the lock on ``path`` until standard input closes."""
    with open(path, "a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        sys.stdout.write(f"acquired {now()}\n")
        sys.stdout.flush()
        sys.stdin.read()
        fcntl.flock(handle, fcntl.LOCK_UN)
        sys.stdout.write(f"released {now()}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    mode, target = sys.argv[1], sys.argv[2]
    if mode == "probe":
        sys.stdout.write(probe(target) + "\n")
    elif mode == "hold":
        hold(target)
    else:
        raise SystemExit(f"unknown mode {mode}")
