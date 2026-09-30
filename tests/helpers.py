"""Typed conveniences shared by the test modules.

Observation results are honestly optional in the read model; a test that has
arranged for a value to exist says so through these helpers instead of
dereferencing an ``Optional``.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from dashpot.core.issue_profile import IssueProfile, conform_issue
from dashpot.core.model import ProjectObservation, ProjectSnapshot
from dashpot.sessions.processes import (
    ProcessAbsent,
    ProcessIdentity,
    ProcessLookup,
    ProcessObservation,
    ProcessPresent,
    ProcessUnobservable,
)

_CONFORMANCE_FIXTURES = Path(__file__).parents[1] / "conformance" / "issue" / "fixtures"
_GITHUB_FIXTURE: dict[str, Any] = json.loads(
    (_CONFORMANCE_FIXTURES / "github.json").read_text()
)


async def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Poll inside the running event loop until ``predicate`` holds.

    The deadline bounds a predicate that never holds; it is not a budget a
    passing test spends, since polling returns as soon as the predicate
    holds, and no test waits it out on purpose. It was 1.5 s until #341:
    with the suite's workers oversubscribing two cores eightfold, a single
    ``pilot.pause()`` took 1.7 s, so a correct app could miss the deadline
    by a frame. At 5 s the touched layout tests ran 700 times there without
    a timeout, and a failing wait still reports within seconds.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition was not met before timeout")
        await asyncio.sleep(0.01)


class FrameDriver(Protocol):
    """A driver that advances a running Textual app by a frame, as ``Pilot`` does."""

    async def pause(self) -> None: ...


async def settled[T](
    pilot: FrameDriver, read: Callable[[], T], what: str, *, frames: int = 20
) -> T:
    """Drive the app frame by frame until ``read`` holds, and return the reading.

    A proxy such as a breakpoint class, a pane's cap or a landed observation
    becomes true a frame or more before the layout it stands for, so geometry
    read the moment a ``wait_until`` on the proxy returns may not be laid out
    yet. This drives the app one frame at a time with ``pilot.pause()``, which
    lays out whatever is pending, and returns the reading once it has held
    for two frames in a row: under load, a widget's idle work, such as a
    table measuring its columns, can miss a frame. Wait on the proxy first,
    so that the change has begun, since an untouched reading holds at once.
    ``frames`` bounds the wait, so layout that never converges fails naming
    ``what`` rather than hanging a worker.

    Settle geometry, which converges on its layout. A widget that recomposes,
    such as the Footer, passes through an empty interim state that can last
    as long; wait on what it should show instead.
    """
    previous, held = read(), 0
    for _ in range(frames):
        await pilot.pause()
        current = read()
        held = held + 1 if current == previous else 0
        if held == 2:
            return current
        previous = current
    raise AssertionError(
        f"{what} did not settle within {frames} frames; last read {previous!r}"
    )


def required[T](value: T | None) -> T:
    """Fail the test rather than dereference an absent value."""
    assert value is not None
    return value


def snapshot_of(project: ProjectObservation | None) -> ProjectSnapshot:
    """A Project's observed snapshot, which the test expects to exist."""
    return required(required(project).snapshot)


def semantic_projection(issue: IssueProfile) -> dict[str, Any]:
    """Project the source-neutral facts the conformance contract compares."""
    return issue.model_dump(mode="json", by_alias=True, exclude={"origin", "location"})


def semantically_equivalent(left: IssueProfile, right: IssueProfile) -> bool:
    """Compare complete Issues after excluding provenance and location."""
    return semantic_projection(left) == semantic_projection(right)


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


def jsonable(value: BaseModel) -> dict[str, Any]:
    """The wire document of a published model, exactly as ``--json`` prints it."""
    return value.model_dump(mode="json", by_alias=True)


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
