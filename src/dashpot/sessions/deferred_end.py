"""Settle a deferred ``SessionEnd`` by the fate of the Host Process that published it.

A managed Codex daemon publishes the same ``SessionEnd`` for a thread it
unloads as for every thread it holds when it is stopped or restarted, and it
waits for the hook before it exits, so the hook cannot see which it was. The
publisher therefore hands such an end to a detached settler, which watches the
daemon for a bounded window: a daemon that keeps running unloaded the thread,
and the run ends as any ``SessionEnd`` ends it; a daemon that exits leaves the
run an Orphaned Agent Run, recoverable with ``work start`` (ADR 0086).
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..core.json_records import optional_string, require_harness, require_string
from ..core.pydantic import NonEmptyString, PublishedModel
from .harnesses import HarnessName, HookSessionIdentity, adapter
from .liveness import session_liveness
from .processes import ProcessIdentity, ProcessLookup, host_process_lookup
from .work_store import (
    ActiveWork,
    SessionProcess,
    end_session_runs,
    session_runs_to_end,
)

# Measured at 0.160.0, the daemon exits within about 0.1 s of its last
# SessionEnd hook, and Codex kills a SessionEnd hook at about 3 s although its
# configuration names 30 s: a stop or restart ended the daemon well inside
# this window.
SETTLE_SECONDS = 10.0
POLL_SECONDS = 0.5
# The module whose ``settle`` entry a settler runs; the root hook module, so
# the settler records its Event Log as the hook it completes.
SETTLER_MODULE = "dashpot.hook"
SETTLE_COMMAND = "settle"


class DeferredEnd(PublishedModel):
    """A ``SessionEnd`` whose runs end only if its Host Process keeps running.

    It names the session, the Host Process the end came from, when it ended,
    and every Worktree of its Repository, so the settler can end the same runs
    the publisher would have ended.
    """

    harness: HarnessName
    session_id: HookSessionIdentity
    host: SessionProcess
    ended_at: str | None
    worktrees: tuple[NonEmptyString, ...]
    cwd: NonEmptyString

    def wire(self) -> str:
        """The settler's argument: this end as JSON."""
        return self.model_dump_json(by_alias=True)

    @classmethod
    def parse(cls, text: str) -> DeferredEnd:
        """Read a settler's argument, raising ``ValueError`` when it is not one."""
        return cls.model_validate_json(text)


# Starts the settler for one deferred end; the suite substitutes a recorder.
Settler = Callable[[DeferredEnd], None]


def defers_session_end(record: Mapping[str, Any], process: ProcessIdentity) -> bool:
    """Whether this ``SessionEnd``'s Host Process defers its runs' end.

    Only a Host Process its Harness Adapter names does; every other end is
    the session's own and ends its run at once (ADR 0015).
    """
    return adapter(require_harness(record.get("harness"))).defers_session_end(process)


def pending_session_end(
    record: Mapping[str, Any],
    process: ProcessIdentity,
    *,
    worktrees: Sequence[Path],
) -> tuple[DeferredEnd, list[tuple[Path, ActiveWork]]] | None:
    """The settler's end of the runs this ``SessionEnd`` would end, and those runs.

    Nothing is written: the runs stay as they are until the settler decides.
    A session with no run here, the common case, has none and needs no
    settler at all.
    """
    if not worktrees:
        return None
    harness = require_harness(record.get("harness"))
    session_id = require_string(record.get("sessionId"), "sessionId")
    ended_at = optional_string(record.get("lastActivityAt"))
    pending = session_runs_to_end(
        worktrees, harness, session_id, process.key, ended_at=ended_at
    )
    if not pending:
        return None
    deferred = DeferredEnd(
        harness=harness,
        session_id=session_id,
        host=SessionProcess(pid=process.pid, started_at=process.started_at),
        ended_at=ended_at,
        worktrees=tuple(str(worktree) for worktree in worktrees),
        cwd=require_string(record.get("cwd"), "cwd"),
    )
    return deferred, pending


def settle_session_end(
    deferred: DeferredEnd,
    lookup: ProcessLookup = host_process_lookup,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[tuple[Path, ActiveWork]]:
    """End the deferred runs only if their Host Process outlives the window.

    A host proved gone was stopped or restarted, so its runs are left as
    Orphaned Agent Runs. A host still live at the deadline unloaded the
    thread, and the runs end through the Work Store's compare-and-delete,
    so one a ``work start`` or ``work stop`` changed meanwhile is left as
    that command left it. A host that cannot be observed at the deadline
    ends nothing: unknown is never evidence of either.
    """
    key = deferred.host.key
    deadline = clock() + SETTLE_SECONDS
    while True:
        liveness = session_liveness(key, lookup).liveness
        if liveness == "gone":
            return []
        if clock() >= deadline:
            break
        sleep(POLL_SECONDS)
    if liveness != "live":
        return []
    return end_session_runs(
        [Path(worktree) for worktree in deferred.worktrees],
        deferred.harness,
        deferred.session_id,
        key,
        ended_at=deferred.ended_at,
    )


def settler_command(deferred: DeferredEnd) -> list[str]:
    """The command a detached settler runs: this interpreter and the hook module."""
    return [sys.executable, "-m", SETTLER_MODULE, SETTLE_COMMAND, deferred.wire()]


def spawn_settler(
    deferred: DeferredEnd,
    popen: Callable[..., object] = subprocess.Popen,
) -> None:
    """Start the settler in a session of its own, holding none of the hook's streams.

    Codex waits for its hook's output to close and kills the hook's process
    when it is slow, and the daemon then exits; the settler must outlive all
    three, so it shares no stream, process group or session with the hook.
    """
    popen(
        settler_command(deferred),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )
