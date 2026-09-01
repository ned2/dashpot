"""Typed conveniences shared by the test modules.

Observation results are honestly optional in the read model; a test that has
arranged for a value to exist says so through these helpers instead of
dereferencing an ``Optional``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

from dashpot.agents import (
    ProcessAbsent,
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
    ProcessUnobservable,
)
from dashpot.issue_profile import IssueProfile, conform_issue
from dashpot.model import ProjectObservation, ProjectSnapshot, to_jsonable

T = TypeVar("T")

_CONFORMANCE_FIXTURES = Path(__file__).parents[1] / "conformance" / "issue" / "fixtures"
_GITHUB_FIXTURE: dict[str, Any] = json.loads(
    (_CONFORMANCE_FIXTURES / "github.json").read_text()
)


def required(value: T | None) -> T:
    """Fail the test rather than dereference an absent value."""
    assert value is not None
    return value


def snapshot_of(project: ProjectObservation | None) -> ProjectSnapshot:
    """A Project's observed snapshot, which the test expects to exist."""
    return required(required(project).snapshot)


def issue_payload(**overrides: object) -> dict[str, Any]:
    """Build a complete Issue wire payload from the conformance fixture."""
    payload = copy.deepcopy(_GITHUB_FIXTURE)
    payload.update(overrides)
    return payload


def make_issue(**overrides: object) -> IssueProfile:
    """Build a complete Issue Profile from the conformance fixture with overrides.

    Overrides use the wire's camelCase keys, exactly as a fixture document
    would spell them; the result is validated like any adapter's output.
    """
    return conform_issue(issue_payload(**overrides))


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
