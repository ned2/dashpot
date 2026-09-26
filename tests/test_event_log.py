"""An Event Log appends whole lines, splits by UTC date, and never fails the work it records."""

from __future__ import annotations

import errno
import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dashpot.core import event_log as event_log_module
from dashpot.core.event_log import (
    DASHBOARD_KIND,
    EVENT_TOO_LARGE,
    EventLog,
    EventLogDestination,
    carry_current_span,
    current_span,
    error_type,
    unrecorded_event_log,
    use_span,
)
from dashpot.core.project_state import STATE_GITIGNORE
from dashpot.core.runtime_events import (
    CommandAttributes,
    EventLevel,
    EventLogWriteFailed,
    ProcessIdentity,
    ProcessStart,
    SpanEnded,
    read_runtime_event,
)
from factories import completed, fake_git

RUN = "0123456789abcdef0123456789abcdef"
MIDDAY = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


class Clock:
    """A wall clock and a monotonic clock the test moves by hand."""

    def __init__(self, now: datetime = MIDDAY) -> None:
        self.now = now
        self.seconds = 100.0

    def wall(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.seconds += seconds


def facts() -> ProcessStart:
    return ProcessStart(
        version="0.1.0",
        install_kind="editable",
        revision="unknown",
        pid=42,
        python_version="3.14.0",
        working_directory="/work",
    )


def make_log(
    directory: Path | None,
    *,
    kind: str = "command:observe",
    level: EventLevel = "standard",
    clock: Clock | None = None,
    keep_recent: int = 0,
    checkout: Path | None = None,
    on_write_failure: Callable[[str], None] | None = None,
) -> EventLog:
    clock = clock or Clock()
    return EventLog(
        None if directory is None else EventLogDestination(directory, checkout),
        identity=ProcessIdentity(run_id=RUN, kind=kind),
        level=level,
        facts=facts,
        keep_recent=keep_recent,
        clock=clock.wall,
        monotonic=clock.monotonic,
        on_write_failure=on_write_failure,
    )


def lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def names(path: Path) -> list[str]:
    return [line["event.name"] for line in lines(path)]


def command_span() -> CommandAttributes:
    return CommandAttributes(program="git", subcommand="status")


# --- Files ------------------------------------------------------------------


def test_a_process_records_its_start_and_end_in_the_days_shared_file(
    tmp_path: Path,
) -> None:
    clock = Clock()
    log = make_log(tmp_path, clock=clock)

    log.start()
    clock.advance(1.5)
    log.end(3)
    log.close()

    path = tmp_path / "events-2026-09-27.jsonl"
    assert log.path == path
    assert names(path) == ["process.start", "process.end"]
    end = lines(path)[1]
    assert end["process.exit.code"] == 3
    assert end["dashpot.duration_seconds"] == pytest.approx(1.5)
    assert end["service.instance.id"] == RUN
    assert all(read_runtime_event(line) for line in path.read_bytes().splitlines())


def test_each_dashboard_run_writes_its_own_file(tmp_path: Path) -> None:
    log = make_log(tmp_path, kind=DASHBOARD_KIND)

    log.start()

    path = tmp_path / f"dashboard-{RUN}-2026-09-27.jsonl"
    assert log.path == path
    assert names(path) == ["process.start"]


def test_a_checkout_destination_creates_state_that_ignores_itself(
    tmp_path: Path,
) -> None:
    directory = tmp_path / ".dashpot" / "state" / "events"

    make_log(directory, checkout=tmp_path).start()

    assert (tmp_path / ".dashpot" / "state" / ".gitignore").read_text() == (
        STATE_GITIGNORE
    )
    assert names(directory / "events-2026-09-27.jsonl") == ["process.start"]


def test_the_fallback_destination_writes_no_gitignore(tmp_path: Path) -> None:
    directory = tmp_path / "state" / "dashpot" / "events"

    make_log(directory).start()

    assert not (tmp_path / "state" / "dashpot" / ".gitignore").exists()
    assert sorted(path.name for path in directory.iterdir()) == [
        "events-2026-09-27.jsonl"
    ]


def test_at_midnight_utc_the_next_days_file_opens_with_process_continued(
    tmp_path: Path,
) -> None:
    clock = Clock(datetime(2026, 9, 27, 23, 59, 59, tzinfo=UTC))
    log = make_log(tmp_path, clock=clock)
    log.start()

    clock.advance(2)
    log.end(0)

    assert names(tmp_path / "events-2026-09-27.jsonl") == ["process.start"]
    next_day = lines(tmp_path / "events-2026-09-28.jsonl")
    assert [line["event.name"] for line in next_day] == [
        "process.continued",
        "process.end",
    ]
    start = lines(tmp_path / "events-2026-09-27.jsonl")[0]
    repeated = {
        key: value for key, value in start.items() if key not in {"time", "event.name"}
    }
    assert repeated.items() <= next_day[0].items()


def test_the_date_is_utc_whatever_the_local_zone(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 9, 28, 8, 0, tzinfo=UTC).astimezone())
    log = make_log(tmp_path, clock=clock)

    log.start()

    path = tmp_path / "events-2026-09-28.jsonl"
    assert log.path == path
    assert lines(path)[0]["time"] == "2026-09-28T08:00:00.000000Z"


@pytest.mark.parametrize("outside_tool", ["move", "delete"])
def test_a_file_an_outside_tool_moved_or_deleted_is_opened_again(
    tmp_path: Path, outside_tool: str
) -> None:
    log = make_log(tmp_path)
    log.start()
    path = tmp_path / "events-2026-09-27.jsonl"
    if outside_tool == "move":
        path.rename(tmp_path / "rotated.jsonl")
    else:
        path.unlink()

    log.end(0)

    assert names(path) == ["process.continued", "process.end"]
    if outside_tool == "move":
        assert names(tmp_path / "rotated.jsonl") == ["process.start"]


def test_concurrent_writers_lines_stay_whole(tmp_path: Path) -> None:
    log = make_log(tmp_path, level="full")
    other = make_log(tmp_path, level="full")
    barrier = threading.Barrier(8)

    def write(writer: EventLog) -> None:
        barrier.wait()
        for _ in range(50):
            writer.start_span("command", attributes=command_span()).end()

    threads = [
        threading.Thread(target=write, args=(log if index % 2 else other,))
        for index in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    log.close()
    other.close()

    raw = (tmp_path / "events-2026-09-27.jsonl").read_bytes().splitlines()
    assert len(raw) == 8 * 50 + 2
    assert all(read_runtime_event(line) is not None for line in raw)


# --- Levels -----------------------------------------------------------------


def test_off_records_nothing_and_creates_nothing(tmp_path: Path) -> None:
    directory = tmp_path / "events"
    log = make_log(directory, level="off")

    log.start()
    log.start_span("command", level="standard").end()
    log.end(0)

    assert not directory.exists()


def test_standard_leaves_out_a_full_span(tmp_path: Path) -> None:
    log = make_log(tmp_path)

    log.start()
    log.start_span("command", attributes=command_span()).end()
    log.start_span("command", level="standard").end()

    assert names(tmp_path / "events-2026-09-27.jsonl") == ["process.start", "span"]
    assert lines(tmp_path / "events-2026-09-27.jsonl")[1]["dashpot.level"] == "standard"


def test_a_level_change_is_marked_in_the_log_it_leaves_or_enters(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path)
    log.start()

    log.set_level("off")
    log.start_span("command", level="standard").end()
    log.set_level("full")
    log.set_level("full")
    log.start_span("command").end()

    changes = [
        (
            line.get("dashpot.event_level.previous"),
            line.get("dashpot.event_level.current"),
        )
        for line in lines(tmp_path / "events-2026-09-27.jsonl")
        if line["event.name"] == "level.changed"
    ]
    assert changes == [("standard", "off"), ("off", "full")]
    assert names(tmp_path / "events-2026-09-27.jsonl") == [
        "process.start",
        "level.changed",
        "level.changed",
        "span",
    ]
    assert log.level == "full"


def test_a_log_switched_on_after_an_unrecorded_start_describes_its_process(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path, level="off", keep_recent=10)
    log.start()

    log.set_level("standard")

    assert names(tmp_path / "events-2026-09-27.jsonl") == [
        "process.continued",
        "level.changed",
    ]


def test_the_recent_buffer_keeps_every_event_whatever_the_level(tmp_path: Path) -> None:
    log = make_log(tmp_path, level="off", keep_recent=2)

    log.start()
    log.start_span("command").end()
    log.end(0)

    assert [event.body.name for event in log.recent] == ["span", "process.end"]
    assert not tmp_path.joinpath("events-2026-09-27.jsonl").exists()


# --- Failures ---------------------------------------------------------------


def test_an_event_longer_than_a_line_may_be_is_dropped_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failures: list[str] = []
    log = make_log(tmp_path, keep_recent=10, on_write_failure=failures.append)
    log.start()
    monkeypatch.setattr(event_log_module, "MAX_EVENT_BYTES", 64)

    log.end(0)

    monkeypatch.undo()
    assert failures == [EVENT_TOO_LARGE]
    assert log.write_failure == EVENT_TOO_LARGE
    assert isinstance(log.recent[-1].body, EventLogWriteFailed)
    # Nothing reached the file, so the next event follows on without a
    # ``process.continued``, as if the dropped one had never been.
    log.end(1)
    assert names(tmp_path / "events-2026-09-27.jsonl") == [
        "process.start",
        "process.end",
    ]


def test_a_failed_write_is_dropped_into_the_buffer_and_never_raised(
    tmp_path: Path,
) -> None:
    failures: list[str] = []
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    log = make_log(blocker / "events", keep_recent=10, on_write_failure=failures.append)

    log.start()
    log.end(0)

    assert failures == ["ENOTDIR", "ENOTDIR"]
    assert log.write_failure == "ENOTDIR"
    assert [event.body.name for event in log.recent] == [
        "process.start",
        "event_log.write_failed",
        "process.end",
        "event_log.write_failed",
    ]


@pytest.mark.parametrize(
    "write",
    [
        pytest.param(lambda fd, data: 1, id="short"),
        pytest.param(
            lambda fd, data: (_ for _ in ()).throw(OSError(errno.ENOSPC, "full")),
            id="raised",
        ),
    ],
)
def test_a_write_that_fails_closes_the_file_and_the_next_event_opens_it_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write: Callable[[int, bytes], int],
) -> None:
    failures: list[str] = []
    log = make_log(tmp_path, on_write_failure=failures.append)
    log.start()
    real_write = os.write
    monkeypatch.setattr(event_log_module.os, "write", write)

    log.start_span("command", level="standard").end()
    monkeypatch.setattr(event_log_module.os, "write", real_write)
    log.end(0)

    assert failures == ["ENOSPC"]
    # The file was closed and opened again, so the next event is whole on a
    # line of its own, after whatever the failed write left.
    path = tmp_path / "events-2026-09-27.jsonl"
    assert names(path)[0] == "process.start"
    last = read_runtime_event(path.read_bytes().splitlines()[-1])
    assert last is not None and last.body.name == "process.end"


def test_a_span_failed_with_a_message_is_refused_where_it_fails(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path, level="full")

    with log.start_as_current_span("command") as span:
        with pytest.raises(ValidationError):
            span.fail("fatal: not a git repository (or any parent)")
        assert not span.failed

    assert (
        span_lines(tmp_path / "events-2026-09-27.jsonl")[0]["otel.status_code"] == "OK"
    )


def test_an_error_is_named_by_its_errno_or_class() -> None:
    assert error_type(OSError(errno.EACCES, "Permission denied: /secret")) == "EACCES"
    assert error_type(OSError("no errno")) == "OSError"
    assert error_type(ValueError("detail")) == "ValueError"


def test_a_log_with_no_destination_writes_nothing() -> None:
    log = unrecorded_event_log(keep_recent=5)

    log.set_level("full")
    log.start()
    log.end(0)

    assert log.path is None
    assert [event.body.name for event in log.recent] == [
        "level.changed",
        "process.start",
        "process.end",
    ]


# --- Spans ------------------------------------------------------------------


def span_lines(path: Path) -> list[dict[str, Any]]:
    return [line for line in lines(path) if line["event.name"] == "span"]


def test_a_span_takes_the_current_span_as_its_parent_unless_one_is_named(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path, level="full")

    with log.start_as_current_span("command") as outer:
        assert current_span() is outer
        log.start_span("command").end()
        log.start_span("command", parent=None).end()
    held = log.start_span("command")
    log.start_span("command", parent=held).end()
    held.end()
    held.end()

    assert current_span() is None
    parents = [
        line.get("parent_span_id")
        for line in span_lines(tmp_path / "events-2026-09-27.jsonl")
    ]
    assert parents == [outer.span_id, None, None, held.span_id, None]


def test_a_span_records_when_it_started_and_how_long_it_took(tmp_path: Path) -> None:
    clock = Clock()
    log = make_log(tmp_path, level="full", clock=clock)

    span = log.start_span("command", attributes=command_span())
    clock.advance(0.25)
    span.set_attributes(
        CommandAttributes(program="git", subcommand="status", exit_code=0)
    )
    span.end()

    (line,) = span_lines(tmp_path / "events-2026-09-27.jsonl")
    assert line["time"] == "2026-09-27T12:00:00.000000Z"
    assert line["dashpot.duration_seconds"] == pytest.approx(0.25)
    assert line["otel.status_code"] == "OK"
    assert line["attributes"] == {
        "process.executable.name": "git",
        "dashpot.command.subcommand": "status",
        "process.exit.code": 0,
    }


def test_an_exception_leaving_a_span_fails_it_by_class_at_standard(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path)

    with pytest.raises(TimeoutError), log.start_as_current_span("command"):
        raise TimeoutError("git status timed out after 5s in /secret/path")
    with log.start_as_current_span("command") as span:
        span.fail("CommandError")

    failed = span_lines(tmp_path / "events-2026-09-27.jsonl")
    assert [(line["otel.status_code"], line["error.type"]) for line in failed] == [
        ("ERROR", "TimeoutError"),
        ("ERROR", "CommandError"),
    ]
    assert {line["dashpot.level"] for line in failed} == {"standard"}
    assert "/secret/path" not in (tmp_path / "events-2026-09-27.jsonl").read_text()


def test_a_non_zero_git_exit_read_as_an_answer_is_no_failed_span(
    tmp_path: Path,
) -> None:
    git = fake_git(completed(stderr="fatal: Needed a single revision", returncode=1))
    log = make_log(tmp_path, level="full")

    with log.start_as_current_span(
        "command", attributes=CommandAttributes(program="git", subcommand="rev-parse")
    ) as span:
        answer = git.maybe("rev-parse", "--verify", "--quiet", "no-such-ref")
        span.set_attributes(
            CommandAttributes(program="git", subcommand="rev-parse", exit_code=1)
        )

    assert answer is None
    (line,) = span_lines(tmp_path / "events-2026-09-27.jsonl")
    assert line["otel.status_code"] == "OK"
    assert "error.type" not in line
    assert line["attributes"]["process.exit.code"] == 1
    assert "fatal" not in (tmp_path / "events-2026-09-27.jsonl").read_text()


def test_the_current_span_is_carried_into_an_executor_thread(tmp_path: Path) -> None:
    log = make_log(tmp_path, level="full")
    seen: list[object] = []

    with ThreadPoolExecutor(1) as executor:
        # The thread's own context persists across its tasks: set a marker
        # there first, and the carried span must leave it in place.
        executor.submit(lambda: use_span(None).__enter__()).result()
        with log.start_as_current_span("command") as span:
            carried = carry_current_span(lambda: seen.append(current_span()))
        executor.submit(carried).result()
        executor.submit(lambda: seen.append(current_span())).result()

    assert seen == [span, None]


# --- Identity and forwarding -----------------------------------------------


def test_later_events_name_what_the_process_learned_it_works_for(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path)
    log.start()

    log.identify(project_id="project-1", worktree="/work/tree", issue_id="313")
    log.end(0)

    start, end = lines(tmp_path / "events-2026-09-27.jsonl")
    assert "dashpot.project.id" not in start
    assert (
        end["dashpot.project.id"],
        end["dashpot.worktree.path"],
        end["dashpot.issue.id"],
    ) == ("project-1", "/work/tree", "313")


def test_every_recorded_line_is_forwarded_while_a_console_listens(
    tmp_path: Path,
) -> None:
    forwarded: list[str] = []
    log = make_log(tmp_path)
    log.forward = forwarded.append

    log.start()
    log.start_span("command").end()

    assert [json.loads(line)["event.name"] for line in forwarded] == ["process.start"]
    assert forwarded[0] + "\n" == (tmp_path / "events-2026-09-27.jsonl").read_text()


def test_a_log_whose_first_event_is_no_start_opens_with_process_continued(
    tmp_path: Path,
) -> None:
    log = make_log(tmp_path, level="full")

    log.start_span("command").end()

    written = (tmp_path / "events-2026-09-27.jsonl").read_bytes().splitlines()
    assert names(tmp_path / "events-2026-09-27.jsonl") == ["process.continued", "span"]
    event = read_runtime_event(written[-1])
    assert event is not None and isinstance(event.body, SpanEnded)
