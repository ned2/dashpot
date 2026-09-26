"""A dashboard records Agent Session and Diagnostic changes, and only changes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app_harness import SequenceCollector, dashboard_app, first_load_landed, issue
from app_harness import workspace_snapshot as harness_snapshot
from dashpot.core.event_log import DASHBOARD_KIND, EventLog, EventLogDestination
from dashpot.core.model import AgentRun, Diagnostic
from dashpot.core.runtime_events import ProcessIdentity, ProcessStart
from dashpot.observation.observation_store import ObservedDiagnostic
from dashpot.ui.change_events import (
    UNCODED,
    AgentSessionChanges,
    DiagnosticChanges,
)
from factories import agent_run
from helpers import wait_until
from test_app_event_log import unwritable

RUN = "0123456789abcdef0123456789abcdef"
ENVELOPE = {
    "schema",
    "time",
    "dashpot.level",
    "service.instance.id",
    "dashpot.process.kind",
}


def event_log(directory: Path) -> EventLog:
    return EventLog(
        EventLogDestination(directory),
        identity=ProcessIdentity(run_id=RUN, kind=DASHBOARD_KIND),
        level="standard",
        facts=lambda: ProcessStart(
            version="0.1.0",
            install_kind="editable",
            revision="unknown",
            pid=os.getpid(),
            python_version="3.14.0",
        ),
        keep_recent=100,
    )


def recorded(directory: Path, name: str) -> list[dict[str, Any]]:
    """Every written event of one name, without the fields every event has."""
    return [
        {key: value for key, value in event.items() if key not in ENVELOPE}
        for path in sorted(directory.glob("*.jsonl"))
        for line in path.read_text().splitlines()
        if (event := json.loads(line))["event.name"] == name
    ]


def session(
    issue_id: str | None = None,
    target: str = "/work/repo",
    *,
    run_id: str = "run-1",
    session_id: str | None = "s-1",
) -> AgentRun:
    run = agent_run(
        run_id,
        "project:test",
        harness="claude-code",
        issue_id=issue_id,
        target_path=target,
    )
    return run.model_copy(update={"session_id": session_id})


# --- Agent Sessions -----------------------------------------------------------


def test_each_agent_session_change_is_recorded_once(tmp_path: Path) -> None:
    changes = AgentSessionChanges(event_log(tmp_path))

    for observed in (
        [session()],
        [session()],
        [session("I_314")],
        [session("I_314")],
        [session("I_316")],
        [session("I_316", "/work/repo.worktrees/316")],
        [session(None, "/work/repo.worktrees/316")],
        [],
        [],
    ):
        changes.observe(observed)

    events = recorded(tmp_path, "agent_session.changed")
    subject = {
        "dashpot.agent_session.harness": "claude-code",
        "dashpot.agent_session.id": "s-1",
        "dashpot.project.id": "project:test",
    }
    assert events == [
        {
            **subject,
            "dashpot.worktree.path": "/work/repo",
            "event.name": "agent_session.changed",
            "dashpot.agent_session.change": "appeared",
        },
        {
            **subject,
            "dashpot.worktree.path": "/work/repo",
            "dashpot.issue.id": "I_314",
            "event.name": "agent_session.changed",
            "dashpot.agent_session.change": "bound",
        },
        {
            **subject,
            "dashpot.worktree.path": "/work/repo",
            "dashpot.issue.id": "I_316",
            "event.name": "agent_session.changed",
            "dashpot.agent_session.change": "switched",
            "dashpot.issue.previous_id": "I_314",
        },
        {
            **subject,
            "dashpot.worktree.path": "/work/repo.worktrees/316",
            "dashpot.issue.id": "I_316",
            "event.name": "agent_session.changed",
            "dashpot.agent_session.change": "relocated",
            "dashpot.worktree.previous_path": "/work/repo",
        },
        {
            **subject,
            "dashpot.worktree.path": "/work/repo.worktrees/316",
            "event.name": "agent_session.changed",
            "dashpot.agent_session.change": "unbound",
            "dashpot.issue.previous_id": "I_316",
        },
        {
            **subject,
            "dashpot.worktree.path": "/work/repo.worktrees/316",
            "event.name": "agent_session.changed",
            "dashpot.agent_session.change": "ended",
        },
    ]


def test_a_sessions_agent_run_stands_for_it_over_its_bare_hook_row(
    tmp_path: Path,
) -> None:
    changes = AgentSessionChanges(event_log(tmp_path))
    bare = session(run_id="hook-row")
    bound = session("I_314", run_id="work-row")

    changes.observe([bare, bound])
    changes.observe([bound, bare])

    (appeared,) = recorded(tmp_path, "agent_session.changed")
    assert appeared["dashpot.agent_session.change"] == "appeared"
    assert appeared["dashpot.issue.id"] == "I_314"


def test_a_session_without_a_native_id_is_followed_by_its_row(tmp_path: Path) -> None:
    changes = AgentSessionChanges(event_log(tmp_path))

    changes.observe([session(session_id=None, run_id="a"), session(run_id="b")])
    changes.observe([session(session_id=None, run_id="a")])

    events = recorded(tmp_path, "agent_session.changed")
    assert [event["dashpot.agent_session.change"] for event in events] == [
        "appeared",
        "appeared",
        "ended",
    ]
    assert "dashpot.agent_session.id" not in events[0]


# --- Diagnostics --------------------------------------------------------------


def shown(
    code: str | None,
    message: str = "anything",
    *,
    source: str = "settings:/home/someone/config.toml",
    project_id: str | None = None,
) -> ObservedDiagnostic:
    diagnostic = Diagnostic(
        source=source, severity="warning", message=message, code=code
    )
    return ObservedDiagnostic(diagnostic, "Some Project", project_id)


def test_a_diagnostic_is_recorded_when_it_appears_and_clears_never_its_message(
    tmp_path: Path,
) -> None:
    changes = DiagnosticChanges(event_log(tmp_path))

    changes.observe([shown("settings-invalid", "secret at /home/someone")])
    changes.observe([shown("settings-invalid", "a different secret")])
    changes.observe([])

    assert recorded(tmp_path, "diagnostic.changed") == [
        {
            "event.name": "diagnostic.changed",
            "dashpot.diagnostic.change": change,
            "dashpot.diagnostic.source": "settings:/home/someone/config.toml",
            "dashpot.diagnostic.code": "settings-invalid",
            "dashpot.diagnostic.severity": "warning",
        }
        for change in ("appeared", "cleared")
    ]
    assert "secret" not in "".join(p.read_text() for p in tmp_path.glob("*.jsonl"))


def test_the_same_diagnostic_in_two_projects_is_two_diagnostics(
    tmp_path: Path,
) -> None:
    changes = DiagnosticChanges(event_log(tmp_path))

    changes.observe(
        [
            shown("github-auth", source="github", project_id="project:a"),
            shown("github-auth", source="github", project_id="project:b"),
        ]
    )
    changes.observe([shown("github-auth", source="github", project_id="project:b")])

    events = recorded(tmp_path, "diagnostic.changed")
    assert [
        (event["dashpot.diagnostic.change"], event["dashpot.project.id"])
        for event in events
    ] == [
        ("appeared", "project:a"),
        ("appeared", "project:b"),
        ("cleared", "project:a"),
    ]


@pytest.mark.parametrize(
    "source",
    ["settings:the file at home is broken", "project:", "github\n", "a b"],
)
def test_a_source_that_is_no_identifier_or_path_is_left_out(
    tmp_path: Path, source: str
) -> None:
    changes = DiagnosticChanges(event_log(tmp_path))

    changes.observe([shown("settings-invalid", source=source)])

    (event,) = recorded(tmp_path, "diagnostic.changed")
    assert "dashpot.diagnostic.source" not in event
    assert event["dashpot.diagnostic.code"] == "settings-invalid"


@pytest.mark.parametrize(
    "source",
    [
        "github",
        "settings:/home/some one/config.toml",
        "refresh:workspace:*",
        "0123abcd",
    ],
)
def test_a_source_that_is_an_identifier_or_path_is_kept(
    tmp_path: Path, source: str
) -> None:
    changes = DiagnosticChanges(event_log(tmp_path))

    changes.observe([shown("settings-invalid", source=source)])

    (event,) = recorded(tmp_path, "diagnostic.changed")
    assert event["dashpot.diagnostic.source"] == source


@pytest.mark.parametrize("code", [None, "Not A Code: /home/someone"])
def test_a_diagnostic_without_a_code_is_recorded_as_uncoded(
    tmp_path: Path, code: str | None
) -> None:
    changes = DiagnosticChanges(event_log(tmp_path))

    changes.observe([shown(code, source="bad source\n")])

    (event,) = recorded(tmp_path, "diagnostic.changed")
    assert event["dashpot.diagnostic.code"] == UNCODED
    assert "dashpot.diagnostic.source" not in event
    assert "someone" not in json.dumps(event)


# --- The dashboard ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_dashboard_records_what_it_observes_change(tmp_path: Path) -> None:
    log = event_log(tmp_path / "events")
    first = harness_snapshot(
        issue("test/repo#1", "First"),
        runs=[session(target="/repo")],
        diagnostics=[
            Diagnostic(
                source="github",
                severity="warning",
                code="github-rate-limit-low",
                message="12 points left",
            )
        ],
    )
    app = dashboard_app(
        SequenceCollector(first, RuntimeError("gh: secret")), event_log=log
    )

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))
        await app.run_action("refresh")
        await wait_until(
            lambda: any(
                event["dashpot.diagnostic.code"] == "refresh-failed"
                for event in recorded(tmp_path / "events", "diagnostic.changed")
            )
        )

    sessions = recorded(tmp_path / "events", "agent_session.changed")
    assert [event["dashpot.agent_session.change"] for event in sessions] == ["appeared"]
    diagnostics = recorded(tmp_path / "events", "diagnostic.changed")
    assert {
        (
            event["dashpot.diagnostic.change"],
            event["dashpot.diagnostic.code"],
            event.get("dashpot.diagnostic.source"),
        )
        for event in diagnostics
    } == {
        ("appeared", "github-rate-limit-low", "github"),
        ("appeared", "refresh-failed", "refresh:workspace:*"),
    }
    written = "".join(p.read_text() for p in (tmp_path / "events").glob("*.jsonl"))
    assert "secret" not in written
    assert "12 points left" not in written


@pytest.mark.asyncio
async def test_a_dashboard_over_one_project_names_it_on_its_own_events(
    tmp_path: Path,
) -> None:
    log = event_log(tmp_path / "events")
    snapshot = harness_snapshot(issue("test/repo#1", "First"))
    app = dashboard_app(SequenceCollector(snapshot), event_log=log)

    async with app.run_test(size=(100, 30)):
        await wait_until(lambda: first_load_landed(app))

    assert log.identity.project_id == snapshot.projects[0].project_id


def test_a_dashboard_that_cannot_write_still_follows_changes(tmp_path: Path) -> None:
    log = event_log(unwritable(tmp_path))
    changes = AgentSessionChanges(log)

    changes.observe([session()])
    changes.observe([])

    assert [type(event.body).__name__ for event in log.recent][-4:] == [
        "AgentSessionChanged",
        "EventLogWriteFailed",
        "AgentSessionChanged",
        "EventLogWriteFailed",
    ]
