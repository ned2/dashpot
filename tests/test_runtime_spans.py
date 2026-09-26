"""Commands and GitHub requests record themselves as spans, by code and never by message.

Each test reads the Event Log a test directory receives, so the assertions
cover the names and fields written to disk.
"""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from dashpot import cli, hook
from dashpot.core.commands import (
    CommandError,
    CommandResult,
    command_words,
    nonzero_exit_fails,
    run_command,
)
from dashpot.core.event_log import (
    EventLog,
    EventLogDestination,
    carry_current_span,
    current_event_log,
    error_type,
    recorded_span,
    use_event_log,
)
from dashpot.core.git import Git, GitError
from dashpot.core.runtime_events import EventLevel, ProcessIdentity, ProcessStart
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.github.github import GitHubGateway, GitHubRequestError
from dashpot.repository.worktree_launcher import (
    WorktreeLauncher,
    WorktreeLaunchError,
    run_launch_command,
)
from dashpot.sessions import processes
from factories import init_repository, write_project_config

RUN = "0123456789abcdef0123456789abcdef"
RESET_AT = "2026-09-27T13:00:00Z"
# Every field a command span writes, beside the envelope every event shares.
SPAN_FIELDS = {
    "schema",
    "time",
    "dashpot.level",
    "service.instance.id",
    "dashpot.process.kind",
    "event.name",
    "dashpot.span.name",
    "span_id",
    "dashpot.duration_seconds",
    "otel.status_code",
    "attributes",
}


def event_log(directory: Path, *, level: EventLevel = "full") -> EventLog:
    return EventLog(
        EventLogDestination(directory),
        identity=ProcessIdentity(run_id=RUN, kind="command:observe"),
        level=level,
        facts=lambda: ProcessStart(
            version="0.1.0",
            install_kind="editable",
            revision="unknown",
            pid=os.getpid(),
            python_version="3.14.0",
        ),
    )


def written(directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for path in sorted(directory.glob("*.jsonl"))
        for line in path.read_bytes().splitlines()
    ]


def spans(directory: Path, name: str) -> list[dict[str, Any]]:
    return [
        event for event in written(directory) if event.get("dashpot.span.name") == name
    ]


@pytest.fixture
def recording(tmp_path: Path) -> Iterator[Path]:
    """Record to an Event Log of ``tmp_path / "events"`` at ``full`` for the test."""
    directory = tmp_path / "events"
    with use_event_log(event_log(directory)):
        yield directory


def python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def executable(directory: Path, name: str, code: str) -> Path:
    """A program called ``name`` on a fresh ``PATH`` entry, running Python ``code``."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!{sys.executable}\n{code}\n")
    path.chmod(0o755)
    return path


# --- Commands --------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "program", "subcommand"),
    [
        (["git", "rev-parse", "--verify", "main"], "git", "rev-parse"),
        (["git", "worktree", "add", "-b", "314-x", "/tmp/x"], "git", "worktree add"),
        (["git", "for-each-ref", "--format=%(refname)%00"], "git", "for-each-ref"),
        (["/usr/bin/git", "-C", "/repo", "status"], "git", None),
        (
            ["gh", "api", "graphql", "-f", "query=query DashpotQueryPage($a: ID!) {}"],
            "gh",
            "api graphql DashpotQueryPage",
        ),
        (
            ["gh", "api", "graphql", "-f", "query={ viewer { login } }"],
            "gh",
            "api graphql",
        ),
        (["gh", "api", "repos/ned2/dashpot"], "gh", "api"),
        (["gh", "api", "graphql", "-F", "first=10"], "gh", "api graphql"),
        (["tmux", "split-window", "-v", "-c", "/repo"], "tmux", "split-window"),
        (["ps", "-p", "42", "-o", "pid="], "ps", None),
        (["/home/someone/bin/open-term", "/repo"], "open-term", None),
    ],
)
def test_a_command_is_named_by_program_and_subcommand_never_its_arguments(
    args: list[str], program: str, subcommand: str | None
) -> None:
    assert command_words(args) == (program, subcommand)


def test_a_command_records_its_program_subcommand_and_exit_status(
    recording: Path,
) -> None:
    result = run_command([*python("import sys; sys.exit(3)")], Path.cwd(), 10)

    assert result.returncode == 3
    (span,) = spans(recording, "command")
    assert set(span) == SPAN_FIELDS
    assert span["dashpot.level"] == "full"
    # A non-zero exit is an answer the caller reads, not a failure.
    assert span["otel.status_code"] == "OK"
    assert span["attributes"] == {
        "process.executable.name": Path(sys.executable).name,
        "process.exit.code": 3,
    }


def test_a_command_that_cannot_start_fails_by_its_code(
    recording: Path, tmp_path: Path
) -> None:
    with pytest.raises(CommandError):
        run_command([str(tmp_path / "missing"), "status"], Path.cwd(), 10)
    with pytest.raises(CommandError):
        run_command(python("import time; time.sleep(5)"), Path.cwd(), 0.2)

    missing, slow = spans(recording, "command")
    assert (missing["otel.status_code"], missing["error.type"]) == (
        "ERROR",
        "command-not-found",
    )
    assert missing["attributes"] == {"process.executable.name": "missing"}
    assert slow["error.type"] == "command-timed-out"
    # A failed command is written at ``standard``, as every failed span is.
    assert missing["dashpot.level"] == slow["dashpot.level"] == "standard"


def test_a_caller_that_reads_a_non_zero_exit_as_failure_fails_the_span_by_class(
    recording: Path,
) -> None:
    with nonzero_exit_fails(GitError):
        run_command(python("import sys; sys.exit(1)"), Path.cwd(), 10)
        run_command(python("pass"), Path.cwd(), 10)

    # ``merge-tree`` answers a conflict with exit 1, and fails with any other.
    with nonzero_exit_fails(GitError, answers=(1,)):
        run_command(python("import sys; sys.exit(1)"), Path.cwd(), 10)
        run_command(python("import sys; sys.exit(128)"), Path.cwd(), 10)

    failed, succeeded, conflict, broken = spans(recording, "command")
    assert (failed["otel.status_code"], failed["error.type"]) == ("ERROR", "GitError")
    assert succeeded["otel.status_code"] == "OK"
    assert conflict["otel.status_code"] == "OK"
    assert conflict["attributes"]["process.exit.code"] == 1
    assert (broken["error.type"], broken["attributes"]["process.exit.code"]) == (
        "GitError",
        128,
    )


def test_a_git_failure_is_recorded_by_class_and_never_its_message(
    recording: Path, git_repository: Path
) -> None:
    git = Git(git_repository)

    with pytest.raises(GitError) as raised:
        git.text("rev-parse", "--verify", "refs/heads/no-such-branch")
    assert git.maybe("rev-parse", "--verify", "refs/heads/no-such-branch") is None

    failed, answered = spans(recording, "command")
    assert set(failed) == SPAN_FIELDS | {"error.type"}
    assert failed["error.type"] == "GitError"
    assert failed["attributes"] == {
        "process.executable.name": "git",
        "dashpot.command.subcommand": "rev-parse",
        "process.exit.code": 128,
    }
    # ``Git.maybe`` reads the same exit as an answer: "no such ref".
    assert answered["otel.status_code"] == "OK"
    line = json.dumps(failed)
    assert raised.value.stderr.strip() and raised.value.stderr.strip() not in line
    assert "no-such-branch" not in line and "--verify" not in line


def test_git_commands_nest_under_the_span_they_run_in(
    recording: Path, git_repository: Path
) -> None:
    log = current_event_log()
    assert log is not None
    with log.start_as_current_span("observation") as parent:
        Git(git_repository).maybe("rev-parse", "HEAD")

    (command,) = spans(recording, "command")
    assert command["parent_span_id"] == parent.span_id


def test_code_without_an_event_log_records_nothing(tmp_path: Path) -> None:
    assert current_event_log() is None
    with recorded_span("command") as span:
        assert span is None
    assert run_command(python("pass"), Path.cwd(), 10).returncode == 0
    with pytest.raises(WorktreeLaunchError):
        run_launch_command([str(tmp_path / "missing")], tmp_path, 5)


def test_a_span_carried_to_another_thread_takes_its_event_log(tmp_path: Path) -> None:
    log = event_log(tmp_path)
    with use_event_log(log):
        carried = carry_current_span(current_event_log)

    assert current_event_log() is None
    assert carried() is log


def test_an_error_is_named_by_its_code_before_its_errno_or_class() -> None:
    assert error_type(GitHubRequestError("github-rate-limit", "API rate limit")) == (
        "github-rate-limit"
    )
    assert error_type(CommandError("timed out", code="command-timed-out")) == (
        "command-timed-out"
    )
    # A code that is not a code is never recorded.
    assert error_type(GitHubRequestError("rate limit exceeded", "x")) == (
        "GitHubRequestError"
    )
    assert error_type(CommandError("timed out")) == "CommandError"
    assert error_type(FileNotFoundError(2, "gone")) == "ENOENT"
    # Only a Dashpot error's code is an identifier; another may be free text.
    assert error_type(SystemExit("usage")) == "SystemExit"


def test_process_probes_record_their_commands(
    recording: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processes, "process_namespace_is_isolated", lambda: False)
    probed = processes.host_process_lookup(os.getpid())
    assert isinstance(probed, processes.ProcessPresent)
    ran = spans(recording, "command")
    assert ran and {span["attributes"]["process.executable.name"] for span in ran} == {
        "ps"
    }
    assert all(
        span["otel.status_code"] == "OK"
        and "dashpot.command.subcommand" not in span["attributes"]
        for span in ran
    )

    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    unavailable = processes.host_process_lookup(os.getpid())
    assert processes.boot_time(tmp_path / "no-stat") is None

    assert isinstance(unavailable, processes.ProcessUnobservable)
    ps, sysctl = spans(recording, "command")[len(ran) :]
    assert (ps["attributes"]["process.executable.name"], ps["error.type"]) == (
        "ps",
        "command-not-found",
    )
    assert (sysctl["attributes"]["process.executable.name"], sysctl["error.type"]) == (
        "sysctl",
        "command-not-found",
    )


def test_a_worktree_launch_records_its_command(recording: Path, tmp_path: Path) -> None:
    launcher = WorktreeLauncher(
        (sys.executable, "-c", "import sys; sys.exit(4)"),
        None,
        False,
        tmp_path / "config.toml",
        runner=run_launch_command,
    )

    with pytest.raises(WorktreeLaunchError):
        launcher(tmp_path)
    with pytest.raises(WorktreeLaunchError):
        run_launch_command([str(tmp_path / "missing")], tmp_path, 5)

    exited, missing = spans(recording, "command")
    # The launcher reads its non-zero exit as a failure to open the Worktree.
    assert exited["error.type"] == "WorktreeLaunchError"
    assert exited["attributes"]["process.exit.code"] == 4
    assert missing["error.type"] == "command-not-found"


def test_a_worktree_launch_that_cannot_finish_fails_by_its_code(
    recording: Path, tmp_path: Path
) -> None:
    unrunnable = tmp_path / "not-executable"
    unrunnable.write_text("")

    with pytest.raises(WorktreeLaunchError):
        run_launch_command(
            [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 0.2
        )
    with pytest.raises(WorktreeLaunchError):
        run_launch_command([str(unrunnable)], tmp_path, 5)

    timed_out, refused = spans(recording, "command")
    assert timed_out["error.type"] == "command-timed-out"
    assert refused["error.type"] == "EACCES"


# --- GitHub requests -------------------------------------------------------


def fake_gh(
    monkeypatch: pytest.MonkeyPatch,
    directory: Path,
    response: dict[str, Any],
    *,
    exit_code: int = 0,
) -> None:
    """Put a ``gh`` that answers ``response``, and says a secret, first on ``PATH``."""
    executable(
        directory,
        "gh",
        "import sys\n"
        f"sys.stdout.write({json.dumps(json.dumps(response))})\n"
        "sys.stderr.write('gh: secret stderr text')\n"
        f"sys.exit({exit_code})",
    )
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")


def reading(remaining: int, cost: int = 1) -> dict[str, Any]:
    return {
        "rateLimit": {
            "cost": cost,
            "limit": 5000,
            "remaining": remaining,
            "resetAt": RESET_AT,
        }
    }


QUERY = "query DashpotQueryPage($id: ID!) { rateLimit { cost } node(id: $id) { id } }"


def test_a_github_request_records_its_operation_and_its_own_reading(
    recording: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gh(
        monkeypatch, tmp_path / "bin", {"data": {**reading(4990, cost=3), "node": None}}
    )

    GitHubGateway(tmp_path).graphql(QUERY, {"id": "I_secret-variable"})

    (request,) = spans(recording, "github.request")
    (command,) = spans(recording, "command")
    # Every request is written at ``standard``, so requests and points are
    # always countable; the command beneath it at ``full``.
    assert request["dashpot.level"] == "standard"
    assert set(request) == SPAN_FIELDS
    assert request["attributes"] == {
        "dashpot.github.api": "graphql",
        "graphql.operation.name": "DashpotQueryPage",
        "dashpot.github.rate_limit.cost": 3,
        "dashpot.github.rate_limit.limit": 5000,
        "dashpot.github.rate_limit.remaining": 4990,
        "dashpot.github.rate_limit.reset_at": RESET_AT,
    }
    assert command["parent_span_id"] == request["span_id"]
    assert command["attributes"] == {
        "process.executable.name": "gh",
        "dashpot.command.subcommand": "api graphql DashpotQueryPage",
        "process.exit.code": 0,
    }
    assert "secret" not in json.dumps(written(recording))


def test_a_failed_github_request_is_recorded_by_its_code_never_gh_text(
    recording: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gh(
        monkeypatch,
        tmp_path / "bin",
        {
            "data": None,
            "errors": [{"type": "RATE_LIMITED", "message": "secret GitHub message"}],
        },
        exit_code=1,
    )

    with pytest.raises(GitHubRequestError):
        GitHubGateway(tmp_path).graphql_result(QUERY, {"id": "I_1"})

    (request,) = spans(recording, "github.request")
    assert request["dashpot.level"] == "standard"
    assert (request["otel.status_code"], request["error.type"]) == (
        "ERROR",
        "github-rate-limit",
    )
    assert request["attributes"] == {
        "dashpot.github.api": "graphql",
        "graphql.operation.name": "DashpotQueryPage",
    }
    assert "secret" not in json.dumps(written(recording))


@pytest.mark.parametrize(
    "response", [{"data": {}, "errors": "secret"}, {"data": "secret"}]
)
def test_a_malformed_github_response_is_recorded_by_its_code(
    recording: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> None:
    fake_gh(monkeypatch, tmp_path / "bin", response)

    with pytest.raises(GitHubRequestError):
        GitHubGateway(tmp_path).graphql_result(QUERY, {"id": "I_1"})

    (request,) = spans(recording, "github.request")
    assert request["error.type"] == "github-malformed-response"
    assert "secret" not in json.dumps(written(recording))


def test_each_request_of_a_fan_out_records_its_own_reading(
    recording: Path, tmp_path: Path
) -> None:
    answers = iter([4990, 4980, 4970])

    def runner(args: object, cwd: Path, timeout: float) -> CommandResult:
        body = {"data": {**reading(next(answers)), "node": None}}
        return CommandResult([], 0, json.dumps(body), "")

    gateway = GitHubGateway(tmp_path, runner=runner)
    log = current_event_log()
    assert log is not None
    with log.start_as_current_span("query") as parent:
        gateway.graphql_many(QUERY, [{"id": "a"}, {"id": "b"}, {"id": "c"}])

    requests = spans(recording, "github.request")
    assert len(requests) == 3
    assert {request["parent_span_id"] for request in requests} == {parent.span_id}
    assert sorted(
        request["attributes"]["dashpot.github.rate_limit.remaining"]
        for request in requests
    ) == [4970, 4980, 4990]


def test_a_rest_request_is_a_span_of_its_own(recording: Path, tmp_path: Path) -> None:
    gateway = GitHubGateway(
        tmp_path,
        runner=lambda args, cwd, timeout: CommandResult([], 0, '{"id": 1}', ""),
    )

    gateway.rest("repos/ned2/dashpot")

    (request,) = spans(recording, "github.request")
    assert request["attributes"] == {"dashpot.github.api": "rest"}
    assert "ned2" not in json.dumps(request)


# --- Processes -------------------------------------------------------------


def test_a_one_shot_command_records_its_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "full")
    checkout = init_repository(tmp_path / "checkout")
    write_project_config(checkout)
    monkeypatch.chdir(checkout)
    events = tmp_path / "events"

    cli.main(["worktree", "check", "--json"], event_log=EventLogDestination(events))

    kinds = {event["dashpot.process.kind"] for event in written(events)}
    assert kinds == {"command:worktree-check"}
    commands = spans(events, "command")
    assert commands and {
        command["attributes"]["process.executable.name"] for command in commands
    } == {"git"}


def test_a_hook_records_the_commands_that_identify_its_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(LEVEL_VARIABLE, "full")
    monkeypatch.setattr(processes, "process_namespace_is_isolated", lambda: False)
    checkout = init_repository(tmp_path / "checkout")
    write_project_config(checkout)

    def publish(event: object, harness: object) -> None:
        processes.host_process_lookup(os.getpid())

    monkeypatch.setattr(hook, "publish_event", publish)
    event = {"session_id": "s-1", "hook_event_name": "Stop", "cwd": str(checkout)}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert hook.claude_code_main() == 0

    commands = spans(checkout / ".dashpot" / "state" / "events", "command")
    assert commands and all(
        command["attributes"]["process.executable.name"] == "ps"
        and command["dashpot.process.kind"] == "hook:claude-code:Stop"
        for command in commands
    )
