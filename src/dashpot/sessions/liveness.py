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
    local_process_lookup,
    process_liveness,
    recorded_process_lookup,
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
    key: ProcessKey | None,
    lookup: ProcessLookup = host_process_lookup,
    *,
    namespace: str | None,
) -> LivenessObservation:
    """Derive Session Liveness from a recorded process key (PID and start time).

    A PID that is absent or reused by a process with a different start time is
    gone; an unobservable process is unknown, with the adapter's reason.
    ``namespace`` is the PID namespace the process was recorded in, which
    decides whether it can be observed from here (``recorded_process_lookup``);
    every caller names it, ``None`` for a record that keeps none.
    """
    if key is None:
        return LivenessObservation("unknown", "no recorded process identity")
    pid, started_at = key
    observed = recorded_process_lookup(lookup, namespace)(pid)
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
        self._observed: dict[tuple[ProcessKey, str | None], LivenessObservation] = {}
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

    def _local_process(self, pid: int) -> ProcessObservation:
        """The pass's batched identity, or a lookup for a PID not prepared."""
        if pid in self._identities:
            return self._identities[pid]
        return local_process_lookup(pid)

    def observe(
        self, key: ProcessKey | None, *, namespace: str | None
    ) -> LivenessObservation:
        """The Session Liveness of a process recorded in PID namespace ``namespace``."""
        if key is None:
            return session_liveness(key, self._lookup, namespace=namespace)
        observation = self._observed.get((key, namespace))
        if observation is None:
            lookup = recorded_process_lookup(self._lookup, namespace)
            # The batch probed this namespace's own processes, so it answers
            # only where a recorded process is observed as one of them.
            if lookup is local_process_lookup:
                lookup = self._local_process
            # The lookup already decided the namespace, so none is left to.
            observation = session_liveness(key, lookup, namespace=None)
            self._observed[key, namespace] = observation
        return observation
