"""Name scheduled observations and carry their tickets and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ScheduledObservationKind = Literal[
    "issues", "pull-requests", "targets", "agent-runs", "workspace"
]
WORKSPACE_SCOPE = "*"


@dataclass(frozen=True, slots=True)
class ObservationKey:
    """One independently scheduled observation: a kind for one Project."""

    kind: ScheduledObservationKind
    project_id: str = WORKSPACE_SCOPE

    @property
    def group(self) -> str:
        return f"{self.kind}:{self.project_id}"


AGENT_RUNS_KEY = ObservationKey("agent-runs")
WORKSPACE_KEY = ObservationKey("workspace")


@dataclass(frozen=True, slots=True)
class ObservationTicket:
    """A request for one observation; only the newest ticket per key is accepted."""

    key: ObservationKey
    generation: int


@dataclass(frozen=True, slots=True)
class ObservationOutcome:
    """What happened to a ticket after its observation ran.

    ``accepted`` is false when a newer ticket for the same key superseded it.
    An accepted observation is held by the scheduler until ``publish`` moves
    it into a store, so publishing can stay on the consumer's thread.
    """

    ticket: ObservationTicket
    accepted: bool
