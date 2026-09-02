"""Derive Session Liveness from an Agent Session's recorded host process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .processes import (
    ProcessAbsent,
    ProcessKey,
    ProcessLookup,
    ProcessUnobservable,
    host_process_lookup,
)

SessionLiveness = Literal["live", "gone", "unknown"]


@dataclass(frozen=True, slots=True)
class LivenessObservation:
    """Whether an Agent Session's recorded host process is live, gone, or unknown.

    Unknown means the process could not be observed; it is never evidence that
    the session ended.
    """

    liveness: SessionLiveness
    reason: str | None = None


def session_liveness(
    key: ProcessKey | None, lookup: ProcessLookup = host_process_lookup
) -> LivenessObservation:
    """Derive Session Liveness from a recorded process key (PID and start time).

    A PID that is absent or reused by a process with a different start time is
    gone; an unobservable process is unknown, with the adapter's reason.
    """
    if key is None:
        return LivenessObservation("unknown", "no recorded process identity")
    pid, started_at = key
    observed = lookup(pid)
    if isinstance(observed, ProcessAbsent):
        return LivenessObservation("gone")
    if isinstance(observed, ProcessUnobservable):
        return LivenessObservation("unknown", observed.reason)
    if observed.identity.started_at != started_at:
        return LivenessObservation("gone")
    return LivenessObservation("live")


class LivenessProbe:
    """Memoize Session Liveness per process identity for one observation pass.

    The hook Agent Session pass and the Work Store pass then probe each
    recorded process once and always agree about it.
    """

    def __init__(self, lookup: ProcessLookup) -> None:
        self._lookup = lookup
        self._observed: dict[ProcessKey, LivenessObservation] = {}

    def observe(self, key: ProcessKey | None) -> LivenessObservation:
        if key is None:
            return session_liveness(key, self._lookup)
        observation = self._observed.get(key)
        if observation is None:
            observation = session_liveness(key, self._lookup)
            self._observed[key] = observation
        return observation
