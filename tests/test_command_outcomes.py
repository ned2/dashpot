"""Each management command records one ``command.outcome``: its target, result and duration."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Literal
from unittest import mock

import pytest

from dashpot import cli
from dashpot.core.command_outcomes import (
    OutcomeNote,
    outcome_error,
    record_command_outcome,
)
from dashpot.core.event_log import EventLogDestination
from dashpot.core.event_log_files import (
    EventLogError,
    EventLogFileRemoval,
    EventLogRemoval,
)
from dashpot.core.git import GitError
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.github.github import GitHubRequestError
from dashpot.repository.cleanup import TargetResult
from dashpot.sessions.integrate import HarnessReport
from factories import write_config_marker, write_project_config
from test_cli import PLAN, cleanup_preview, cleanup_report, cleanup_target

# What every command outcome holds beyond its envelope; any other field is
# one of the optional ones a test names.
REQUIRED = {"event.name", "dashpot.subcommand", "dashpot.outcome.result"}
DURATION = "dashpot.duration_seconds"
ENVELOPE = {
    "schema",
    "time",
    "dashpot.level",
    "service.instance.id",
    "dashpot.process.kind",
    "dashpot.agent_session.harness",
    "dashpot.agent_session.id",
    "dashpot.project.id",
    "dashpot.worktree.path",
    "dashpot.issue.id",
}


@pytest.fixture
def events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where the commands a test runs record, at the standard level."""
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    return tmp_path / "events"


def run(events: Path, *tokens: str) -> int:
    return cli.main(list(tokens), event_log=EventLogDestination(events))


def written_text(events: Path) -> str:
    return "".join(path.read_text() for path in sorted(events.glob("*.jsonl")))


def outcome(events: Path) -> dict[str, Any]:
    """The one ``command.outcome`` the command recorded, envelope included."""
    (found,) = [
        record
        for line in written_text(events).splitlines()
        if (record := json.loads(line))["event.name"] == "command.outcome"
    ]
    return found


def body(record: dict[str, Any]) -> dict[str, Any]:
    """The outcome's own fields, its duration aside."""
    assert record[DURATION] >= 0
    return {
        key: value
        for key, value in record.items()
        if key not in ENVELOPE and key != DURATION
    }


def test_a_refused_command_records_the_errors_class_never_its_message(
    events: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Outside any Repository Git refuses, and Git's words stay on stderr.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))

    assert run(events, "work", "start", "7") == 2

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "work start",
        "dashpot.outcome.result": "refused",
        "error.type": "GitError",
    }
    assert "not a git repository" not in written_text(events)
    assert str(tmp_path) not in outcome(events).get("error.type", "")


def test_a_git_failure_in_a_command_is_recorded_by_class_never_its_output(
    events: Path,
) -> None:
    failure = GitError(
        ("worktree", "add", "/w/secret"),
        Path("/w"),
        returncode=128,
        stderr="fatal: '/w/secret' already exists",
    )

    with mock.patch.object(cli, "create_issue_worktree", side_effect=failure):
        assert run(events, "worktree", "create", "35") == 2

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "worktree create",
        "dashpot.outcome.result": "refused",
        "error.type": "GitError",
        "dashpot.outcome.dry_run": False,
    }
    assert "secret" not in written_text(events)
    assert "already exists" not in written_text(events)


def test_a_github_failure_in_a_command_is_recorded_by_its_code_never_its_message(
    events: Path,
) -> None:
    failure = GitHubRequestError(
        "github-authentication", "gh: token for someone@example.com expired"
    )

    with mock.patch.object(cli, "start_issue_work", side_effect=failure):
        assert run(events, "work", "start", "7") == 2

    assert body(outcome(events))["error.type"] == "github-authentication"
    assert "someone@example.com" not in written_text(events)
    assert "expired" not in written_text(events)


def test_a_created_worktree_names_its_path_branch_and_issue(events: Path) -> None:
    with mock.patch.object(cli, "create_issue_worktree", return_value=PLAN):
        assert run(events, "worktree", "create", "35") == 0

    record = outcome(events)
    assert body(record) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "worktree create",
        "dashpot.outcome.result": "succeeded",
        "dashpot.outcome.action": "created",
        "dashpot.outcome.dry_run": False,
        "dashpot.target.path": "/w/dashpot.worktrees/35-worktree-protocol",
        "dashpot.target.branch": "35-worktree-protocol",
    }
    assert record["dashpot.issue.id"] == "I_35"


def test_a_plans_refusals_are_counted_never_quoted(events: Path) -> None:
    refused = PLAN.model_copy(
        update={
            "dry_run": True,
            "created": False,
            "refusals": ("Branch '35-worktree-protocol' exists at /w/private/path",),
        }
    )

    with mock.patch.object(cli, "create_issue_worktree", return_value=refused):
        run(events, "worktree", "create", "35", "--dry-run")

    record = body(outcome(events))
    assert record["dashpot.outcome.result"] == "refused"
    assert record["dashpot.outcome.refusal_count"] == 1
    assert record["dashpot.outcome.dry_run"] is True
    assert "dashpot.outcome.action" not in record
    assert "/w/private/path" not in written_text(events)


def test_a_planned_worktree_is_recorded_as_planned(events: Path) -> None:
    planned = PLAN.model_copy(update={"dry_run": True, "created": False})

    with mock.patch.object(cli, "create_issue_worktree", return_value=planned):
        assert run(events, "worktree", "create", "35", "--dry-run") == 0

    assert body(outcome(events))["dashpot.outcome.action"] == "planned"


def deleted(target_kind: Literal["deleted", "refused"]) -> TargetResult:
    local = cleanup_target("local-branch")
    return TargetResult(
        identity=local.identity,
        kind="local-branch",
        label="Local Branch",
        expected=local.expected,
        outcome=target_kind,
        detail="deleted refs/heads/feat at e319d3c",
        recovery=f"git branch feat {local.expected}",
    )


@pytest.mark.parametrize(
    ("report_changes", "expected"),
    [
        (
            {"results": (deleted("deleted"),)},
            {
                "dashpot.outcome.result": "succeeded",
                "dashpot.outcome.action": "deleted",
            },
        ),
        (
            {"results": (deleted("refused"),)},
            {"dashpot.outcome.result": "failed"},
        ),
        (
            {"performed": False, "refusals": ("feat is checked out at /w/x",)},
            {"dashpot.outcome.result": "refused", "dashpot.outcome.refusal_count": 1},
        ),
        (
            {"dry_run": True, "performed": False},
            {
                "dashpot.outcome.result": "succeeded",
                "dashpot.outcome.action": "previewed",
            },
        ),
    ],
    ids=["deleted", "left-in-place", "refused", "previewed"],
)
def test_a_branch_deletion_records_how_it_came_out(
    events: Path, report_changes: dict[str, Any], expected: dict[str, Any]
) -> None:
    preview = cleanup_preview("branch", cleanup_target("local-branch"))
    report = cleanup_report(preview, **report_changes)

    with mock.patch.object(cli, "run_cleanup", return_value=report):
        run(events, "branch", "delete", "feat", "--local")

    record = body(outcome(events))
    assert record == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "branch delete",
        "dashpot.outcome.dry_run": False,
        "dashpot.target.branch": "feat",
        **expected,
    }
    assert "/w/x" not in written_text(events)


def test_a_branch_deletion_naming_no_ref_is_refused_by_class(events: Path) -> None:
    assert run(events, "branch", "delete", "feat") == 2

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "branch delete",
        "dashpot.outcome.result": "refused",
        "dashpot.outcome.dry_run": False,
        "dashpot.target.branch": "feat",
        "error.type": "CleanupError",
    }


def test_a_worktree_removal_names_the_worktree_it_removed(
    events: Path, tmp_path: Path
) -> None:
    worktree = cleanup_target("worktree")
    report = cleanup_report(
        cleanup_preview("worktree", worktree),
        results=(
            TargetResult(
                identity=worktree.identity,
                kind="worktree",
                label="Worktree",
                expected=worktree.expected,
                outcome="deleted",
                detail="removed /w/x",
                recovery=None,
            ),
        ),
    )

    with mock.patch.object(cli, "run_cleanup", return_value=report):
        assert run(events, "worktree", "remove", "../x") == 0

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "worktree remove",
        "dashpot.outcome.result": "succeeded",
        "dashpot.outcome.action": "removed",
        "dashpot.outcome.dry_run": False,
        "dashpot.target.path": str(tmp_path.resolve().parent / "x"),
    }


@pytest.mark.parametrize(
    ("flags", "patched", "action"),
    [
        ((), "install_integration", "installed"),
        (("--remove",), "remove_integration", "removed"),
        (("--status",), "integration_status", "reported"),
    ],
)
def test_an_integration_records_its_harness_and_what_it_did(
    events: Path, flags: tuple[str, ...], patched: str, action: str
) -> None:
    with mock.patch.object(cli, patched, return_value=["done at /home/someone"]):
        assert run(events, "integrate", "claude-code", *flags) == 0

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "integrate",
        "dashpot.outcome.result": "succeeded",
        "dashpot.outcome.action": action,
        "dashpot.target.harness": "claude-code",
    }
    assert "/home/someone" not in written_text(events)


def test_an_integration_across_harnesses_counts_the_harnesses_refused(
    events: Path,
) -> None:
    reports = [
        HarnessReport("claude-code", "installed", ("done at /home/someone",)),
        HarnessReport("codex", "refused", note="refused", error="no /home/someone"),
        HarnessReport("opencode", "refused", note="refused", error="v1"),
    ]
    with mock.patch.object(cli, "refresh_integrations", return_value=reports):
        assert run(events, "integrate", "--installed") == 2

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "integrate",
        "dashpot.outcome.result": "refused",
        "dashpot.outcome.action": "installed",
        "dashpot.outcome.refusal_count": 2,
    }
    assert "/home/someone" not in written_text(events)


def test_an_integration_across_harnesses_left_incomplete_is_a_failure(
    events: Path,
) -> None:
    reports = [
        HarnessReport("codex", "incomplete", note="incomplete", error="disk full"),
        HarnessReport("opencode", "partial", ("left unchanged",), "partial"),
    ]
    with mock.patch.object(cli, "install_integrations", return_value=reports):
        assert run(events, "integrate", "codex", "opencode") == 2

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "integrate",
        "dashpot.outcome.result": "failed",
        "dashpot.outcome.action": "installed",
    }


def test_an_integration_that_changed_no_harness_records_no_action(
    events: Path,
) -> None:
    reports = [HarnessReport("codex", "not integrated", note="not integrated")]
    with mock.patch.object(cli, "refresh_integrations", return_value=reports):
        assert run(events, "integrate", "--installed") == 0

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "integrate",
        "dashpot.outcome.result": "succeeded",
    }


def test_init_names_the_checkout_it_initialized(events: Path, tmp_path: Path) -> None:
    with mock.patch.object(cli, "initialize_project", return_value=["wrote config"]):
        assert run(events, "init") == 0

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "init",
        "dashpot.outcome.result": "succeeded",
        "dashpot.outcome.action": "initialized",
        "dashpot.target.path": str(tmp_path.resolve()),
    }


@pytest.mark.parametrize("where", [".", "src/deep"], ids=["root", "subdirectory"])
def test_init_names_the_project_it_declared(
    events: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, where: str
) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    (repository / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (repository / where).mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(repository / where)

    def declare(current: Path, **options: object) -> list[str]:
        # As init does, the configuration goes at the Worktree's root.
        write_project_config(repository, project_id="project:declared")
        return ["wrote config"]

    with mock.patch.object(cli, "initialize_project", side_effect=declare):
        assert run(events, "init") == 0

    lines = [json.loads(line) for line in written_text(events).splitlines()]
    record, end = lines[-2:]
    assert record["event.name"] == "command.outcome"
    for each in (record, end):
        assert each["dashpot.project.id"] == "project:declared"


@pytest.mark.parametrize("configured", [True, False], ids=["configured", "fallback"])
def test_a_command_names_the_project_of_the_checkout_it_records_in(
    events: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    write_project_config(tmp_path, project_id="project:checkout")
    # Refused before it learns anything else, the command still names it.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    destination = EventLogDestination(events, checkout=tmp_path if configured else None)

    assert cli.main(["work", "start", "7"], event_log=destination) == 2

    record = outcome(events)
    assert record["dashpot.outcome.result"] == "refused"
    assert record.get("dashpot.project.id") == (
        "project:checkout" if configured else None
    )


def test_a_checkout_whose_configuration_cannot_be_read_names_no_project(
    events: Path, tmp_path: Path
) -> None:
    write_config_marker(tmp_path)
    destination = EventLogDestination(events, checkout=tmp_path)

    with mock.patch.object(cli, "install_integration", return_value=["done"]):
        assert cli.main(["integrate", "claude-code"], event_log=destination) == 0

    record = outcome(events)
    assert record["dashpot.outcome.result"] == "succeeded"
    assert "dashpot.project.id" not in record


def test_a_command_that_crashes_records_a_failure_by_class(events: Path) -> None:
    with (
        mock.patch.object(cli, "initialize_project", side_effect=KeyError("secret")),
        pytest.raises(KeyError),
    ):
        run(events, "init")

    record = body(outcome(events))
    assert record["dashpot.outcome.result"] == "failed"
    assert record["error.type"] == "KeyError"
    assert "secret" not in written_text(events)


def test_the_outcome_names_the_session_and_issue_the_command_worked_for(
    events: Path,
) -> None:
    def start(*args: object, outcome: OutcomeNote, **options: object) -> list[str]:
        outcome.identify(harness="codex", session_id="s-1", issue_id="I_7")
        outcome.identify(harness=None, project_id="project:test")
        outcome.action = "started"
        return ["started work on #7"]

    with mock.patch.object(cli, "start_issue_work", side_effect=start):
        assert run(events, "work", "start", "7") == 0

    lines = [json.loads(line) for line in written_text(events).splitlines()]
    record, end = lines[-2:]
    assert body(record)["dashpot.outcome.action"] == "started"
    for each in (record, end):
        assert each["dashpot.agent_session.harness"] == "codex"
        assert each["dashpot.agent_session.id"] == "s-1"
        assert each["dashpot.issue.id"] == "I_7"
        assert each["dashpot.project.id"] == "project:test"


def test_without_an_event_log_the_note_is_filled_and_nothing_recorded() -> None:
    with record_command_outcome(None, "events remove") as note:
        note.action = "removed"

    assert note.result() == "succeeded"
    note.refusals = 2
    assert note.result() == "refused"
    note.refusals, note.incomplete = 0, True
    assert note.result() == "failed"


@pytest.mark.parametrize(
    ("flags", "action"), [((), "removed"), (("--dry-run",), "previewed")]
)
def test_an_event_log_removal_names_the_directory_it_acted_on(
    events: Path, flags: tuple[str, ...], action: str
) -> None:
    target = EventLogDestination(events.parent / "removed-from")
    removal = EventLogRemoval(
        directory=str(target.directory),
        before=date(2026, 9, 1),
        today=date(2026, 9, 27),
        dry_run=bool(flags),
    )

    with (
        mock.patch.object(cli, "owned_event_log", return_value=target),
        mock.patch.object(cli, "remove_event_logs", return_value=removal),
    ):
        assert run(events, "events", "remove", "--before", "2026-09-01", *flags) == 0

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "events remove",
        "dashpot.outcome.result": "succeeded",
        "dashpot.outcome.action": action,
        "dashpot.outcome.dry_run": bool(flags),
        "dashpot.target.path": str(target.directory),
    }


def test_an_event_log_removal_that_left_a_file_is_recorded_as_failed(
    events: Path,
) -> None:
    target = EventLogDestination(events.parent / "removed-from")
    removal = EventLogRemoval(
        directory=str(target.directory),
        before=date(2026, 9, 1),
        today=date(2026, 9, 27),
        dry_run=False,
        files=(
            EventLogFileRemoval(
                path=str(target.directory / "events-2026-08-01.jsonl"),
                day=date(2026, 8, 1),
                size_bytes=10,
                outcome="failed",
                error="Permission denied: /secret",
            ),
        ),
    )

    with (
        mock.patch.object(cli, "owned_event_log", return_value=target),
        mock.patch.object(cli, "remove_event_logs", return_value=removal),
    ):
        assert run(events, "events", "remove", "--before", "2026-09-01") == 2

    record = body(outcome(events))
    assert record["dashpot.outcome.result"] == "failed"
    assert "dashpot.outcome.action" not in record
    assert "/secret" not in written_text(events)


def test_an_event_log_removal_with_nowhere_to_remove_from_is_refused(
    events: Path,
) -> None:
    nowhere = EventLogError("no Event Log for this directory")
    with mock.patch.object(cli, "owned_event_log", side_effect=nowhere):
        assert run(events, "events", "remove", "--before", "2026-09-01") == 2

    assert body(outcome(events)) == {
        "event.name": "command.outcome",
        "dashpot.subcommand": "events remove",
        "dashpot.outcome.result": "refused",
        "dashpot.outcome.dry_run": False,
        "error.type": "EventLogError",
    }


def test_an_error_whose_code_is_no_code_is_named_by_its_class() -> None:
    assert outcome_error(GitHubRequestError("not a code: /home/x", "m")) == (
        "GitHubRequestError"
    )
    assert outcome_error(PermissionError(13, "denied")) == "EACCES"
