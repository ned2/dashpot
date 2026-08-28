"""Typed conveniences shared by the test modules.

Observation results are honestly optional in the read model; a test that has
arranged for a value to exist says so through these helpers instead of
dereferencing an ``Optional``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from dashpot.agents import (
    ProcessAbsent,
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
    ProcessUnobservable,
)
from dashpot.issue_list import IssueListRow
from dashpot.model import Issue, ProjectObservation, ProjectSnapshot, to_jsonable
from dashpot.observation_store import IssueContext

T = TypeVar("T")


def required(value: T | None) -> T:
    """Fail the test rather than dereference an absent value."""
    assert value is not None
    return value


def snapshot_of(project: ProjectObservation | None) -> ProjectSnapshot:
    """A Project's observed snapshot, which the test expects to exist."""
    return required(required(project).snapshot)


def issue_of(row: IssueListRow | IssueContext | None) -> Issue:
    """The Issue behind a row or context, which the test expects to exist."""
    return required(required(row).issue)


def jsonable(value: object) -> dict[str, Any]:
    """The JSON object form of a dataclass snapshot."""
    payload = to_jsonable(value)
    assert isinstance(payload, dict)
    return payload


def present(identity: ProcessIdentity) -> ProcessLookup:
    """A process lookup that finds ``identity`` running at every PID."""
    return lambda _pid: ProcessPresent(identity)


def absent() -> ProcessLookup:
    """A process lookup whose host authoritatively reports every PID absent."""
    return lambda pid: ProcessAbsent(pid)


def unobservable(reason: str) -> ProcessLookup:
    """A process lookup that cannot observe any PID, for the given reason."""
    return lambda pid: ProcessUnobservable(pid, reason)


def table_lookup(processes: Mapping[int, ProcessIdentity]) -> ProcessLookup:
    """A process lookup over a fixed process table; other PIDs are absent."""

    def lookup(pid: int) -> ProcessObservation:
        identity = processes.get(pid)
        if identity is None:
            return ProcessAbsent(pid)
        return ProcessPresent(identity)

    return lookup
