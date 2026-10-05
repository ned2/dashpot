"""Tell an Orphaned Agent Run by the one rule observation, ``work`` and Cleanup share."""

from __future__ import annotations

from collections.abc import Callable

from .liveness import LivenessObservation
from .work_store import ActiveWork, SessionProcess

# Session Liveness of one recorded Host Process, as the caller probes it.
ProcessObserver = Callable[[SessionProcess], LivenessObservation]


def orphaned_process(
    work: ActiveWork, observe: ProcessObserver
) -> SessionProcess | None:
    """The gone Host Process of an Orphaned Agent Run, or None for any other run.

    A run is orphaned when its recorded Host Process is gone. A run whose
    relocation is pending is not: its old client exits before the session
    resumes at the target, so its process is expected to be gone until the
    resume carries the run there. A run that records no process cannot be
    shown gone.
    """
    process = work.session_process
    if work.relocation is not None or process is None:
        return None
    return process if observe(process).liveness == "gone" else None
