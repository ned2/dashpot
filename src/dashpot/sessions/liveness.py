"""Derive Session Liveness from an Agent Session's recorded host process."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .processes import (
    ProcessKey,
    ProcessLiveness,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
    host_process_identities,
    host_process_lookup,
    process_liveness,
)

# A session is as live as its recorded host process.
SessionLiveness = ProcessLiveness


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
    if not isinstance(observed, ProcessPresent):
        return LivenessObservation(*process_liveness(observed))
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
        self._identities: dict[int, ProcessObservation] = {}

    def prepare(self, keys: Iterable[ProcessKey | None]) -> None:
        """Batch previously unobserved host PIDs; injected lookups stay unchanged."""
        if self._lookup is host_process_lookup:
            self._identities.update(
                host_process_identities(
                    key[0]
                    for key in keys
                    if key is not None and key[0] not in self._identities
                )
            )

    def _process(self, pid: int) -> ProcessObservation:
        """The pass's batched identity, or a lookup for a PID not prepared."""
        if pid in self._identities:
            return self._identities[pid]
        return self._lookup(pid)

    def observe(self, key: ProcessKey | None) -> LivenessObservation:
        if key is None:
            return session_liveness(key, self._lookup)
        observation = self._observed.get(key)
        if observation is None:
            observation = session_liveness(key, self._process)
            self._observed[key] = observation
        return observation
