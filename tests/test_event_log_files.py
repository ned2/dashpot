"""``dashpot events`` reads, and ``events remove`` removes, the files an Event Log keeps."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from unittest import mock

import pytest
from pydantic import Field

from dashpot import cli
from dashpot.core import runtime_events
from dashpot.core.event_log import (
    DASHBOARD_KIND,
    EVENTS_DIRECTORY,
    EventLog,
    EventLogDestination,
    event_log_file_day,
)
from dashpot.core.event_log_files import (
    LARGE_EVENT_LOG_BYTES,
    EventSelection,
    describe_runtime_event,
    event_log_large_diagnostic,
    event_log_size,
    read_event_logs,
    recent_events,
    remove_event_logs,
)
from dashpot.core.model import Harness
from dashpot.core.project_state import project_state_directory
from dashpot.core.runtime_events import (
    CommandAttributes,
    EventBody,
    EventLevel,
    LevelChanged,
    ProcessIdentity,
    ProcessStart,
)
from dashpot.core.state_paths import machine_state_directory
from dashpot.event_logs import LEVEL_VARIABLE
from factories import git, init_repository, write_project_config

RUN_A = "a" * 32
RUN_B = "b" * 32
RUN_C = "c" * 32
MIDDAY = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
SESSION = "01a05099-1563-79a3-8504-e30d50949ca6"
OTHER_SESSION = "01c7192b-2990-4f83-ad33-290ac22eb4d1"


class Clock:
    """A wall clock the test sets by hand."""

    def __init__(self, now: datetime = MIDDAY) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def facts() -> ProcessStart:
    return ProcessStart(
        version="0.1.0",
        install_kind="editable",
        revision="unknown",
        pid=42,
        python_version="3.14.0",
    )


def writer(
    directory: Path,
    clock: Clock,
    *,
    run: str = RUN_A,
    kind: str = "command:observe",
    level: EventLevel = "full",
    harness: Harness | None = None,
    session_id: str | None = None,
) -> EventLog:
    return EventLog(
        EventLogDestination(directory),
        identity=ProcessIdentity(
            run_id=run, kind=kind, harness=harness, session_id=session_id
        ),
        level=level,
        facts=facts,
        clock=clock,
    )


def events_directory(checkout: Path) -> Path:
    return project_state_directory(checkout) / EVENTS_DIRECTORY


def fallback_directory() -> Path:
    return machine_state_directory() / EVENTS_DIRECTORY


def repository_with_linked_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = init_repository(tmp_path / "repo")
    write_project_config(main)
    git(
        main,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "seed",
    )
    linked = tmp_path / "repo-linked"
    git(main, "worktree", "add", "-q", "-b", "linked", str(linked))
    write_project_config(linked)
    return main.resolve(), linked.resolve()


def read_json(
    capsys: pytest.CaptureFixture[str], *argv: str, own: Path | None = None
) -> dict[str, Any]:
    destination = None if own is None else EventLogDestination(own)
    assert cli.main(["events", *argv, "--json"], event_log=destination) == 0
    document: dict[str, Any] = json.loads(capsys.readouterr().out)
    return document


def names_and_runs(document: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (event["event.name"], event["service.instance.id"])
        for event in document["events"]
    ]


# --- File names --------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "day"),
    [
        ("events-2026-09-27.jsonl", date(2026, 9, 27)),
        (f"dashboard-{RUN_A}-2026-01-02.jsonl", date(2026, 1, 2)),
        ("events-2026-09-27.jsonl.gz", None),
        ("events-2026-13-01.jsonl", None),
        ("dashboard-short-2026-09-27.jsonl", None),
        ("notes-2026-09-27.jsonl", None),
        ("events-2026-09-27.jsonl.1", None),
    ],
)
def test_only_an_event_log_files_name_carries_its_day(
    name: str, day: date | None
) -> None:
    assert event_log_file_day(name) == day


# --- Reading -----------------------------------------------------------------


def test_events_merge_every_worktree_and_the_fallback_in_time_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, linked = repository_with_linked_worktree(tmp_path)
    clock = Clock()
    in_main = writer(events_directory(main), clock, run=RUN_A)
    in_linked = writer(events_directory(linked), clock, run=RUN_B, kind=DASHBOARD_KIND)
    in_fallback = writer(fallback_directory(), clock, run=RUN_C)
    in_linked.start()
    clock.now += timedelta(seconds=1)
    in_fallback.start()
    clock.now += timedelta(seconds=1)
    in_main.start()
    clock.now += timedelta(days=1)
    in_linked.end(0)
    monkeypatch.chdir(main)

    document = read_json(capsys)

    assert names_and_runs(document) == [
        ("process.start", RUN_B),
        ("process.start", RUN_C),
        ("process.start", RUN_A),
        ("process.continued", RUN_B),
        ("process.end", RUN_B),
    ]
    assert document["directories"] == [
        str(events_directory(main)),
        str(events_directory(linked)),
        str(fallback_directory()),
    ]
    assert document["unreadable"] == []


def test_events_outside_every_repository_read_the_fallback_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    writer(fallback_directory(), Clock()).start()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    document = read_json(capsys)

    assert names_and_runs(document) == [("process.start", RUN_A)]
    assert document["directories"] == [str(fallback_directory())]


def test_events_leave_out_the_reading_process_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, _linked = repository_with_linked_worktree(tmp_path)
    writer(events_directory(main), Clock(datetime.now(UTC))).start()
    monkeypatch.chdir(main)
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")

    first = read_json(capsys, own=events_directory(main))
    second = read_json(capsys, own=events_directory(main))

    assert names_and_runs(first) == [("process.start", RUN_A)]
    # The first reading's own start and end are there for the second to read.
    assert [name for name, _run in names_and_runs(second)] == [
        "process.start",
        "process.start",
        "process.end",
    ]


def test_events_filter_by_session_issue_project_and_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, linked = repository_with_linked_worktree(tmp_path)
    clock = Clock()
    hook = writer(
        events_directory(main),
        clock,
        run=RUN_A,
        kind="hook:codex:Stop",
        harness="codex",
        session_id=SESSION,
    )
    command = writer(
        events_directory(linked), clock, run=RUN_B, kind="command:work-start"
    )
    command.identify(project_id="project:test", issue_id="I_issue7")
    other = writer(
        events_directory(linked),
        clock,
        run=RUN_C,
        kind="hook:codex:Stop",
        harness="codex",
        session_id=OTHER_SESSION,
    )
    hook.start()
    command.start()
    other.start()
    with command.start_as_current_span(
        "command", attributes=CommandAttributes(program="git")
    ):
        pass
    monkeypatch.chdir(linked)

    by_session = read_json(capsys, "--session", SESSION)
    by_issue = read_json(capsys, "--issue", "I_issue7")
    by_project = read_json(capsys, "--project", "project:test")
    standard = read_json(capsys, "--level", "standard")
    full = read_json(capsys, "--level", "full")
    nothing = read_json(capsys, "--session", SESSION, "--issue", "I_issue7")

    assert names_and_runs(by_session) == [("process.start", RUN_A)]
    assert names_and_runs(by_issue) == [("process.start", RUN_B), ("span", RUN_B)]
    assert names_and_runs(by_project) == names_and_runs(by_issue)
    assert [run for _name, run in names_and_runs(standard)] == [RUN_A, RUN_B, RUN_C]
    assert len(full["events"]) == 4
    assert nothing["events"] == []


def test_events_since_a_day_or_an_instant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, _linked = repository_with_linked_worktree(tmp_path)
    clock = Clock(MIDDAY - timedelta(hours=1))
    log = writer(events_directory(main), clock)
    log.start()
    clock.now = MIDDAY
    log.record(LevelChanged(previous="standard", current="full"))
    clock.now = MIDDAY + timedelta(hours=1)
    log.end(0)
    monkeypatch.chdir(main)

    def since(value: str) -> list[str]:
        document = read_json(capsys, "--since", value)
        return [event["event.name"] for event in document["events"]]

    assert since("2026-09-27") == ["process.start", "level.changed", "process.end"]
    assert since("2026-09-27T12:00:00Z") == ["level.changed", "process.end"]
    assert since("2026-09-27T22:00:00+10:00") == ["level.changed", "process.end"]
    assert since("2026-09-28") == []


def test_an_unreadable_since_is_refused_as_usage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["events", "--since", "last tuesday"]) == 2

    assert "is not a day" in " ".join(capsys.readouterr().err.split())


def test_a_since_instant_without_an_offset_is_utc() -> None:
    assert cli.parse_since("2026-09-27T14:00:00") == datetime(
        2026, 9, 27, 14, tzinfo=UTC
    )
    assert cli.parse_since("2026-09-27") == datetime(2026, 9, 27, tzinfo=UTC)
    assert cli.parse_since("90m", MIDDAY) == MIDDAY - timedelta(minutes=90)
    assert cli.parse_since("7d", MIDDAY) == MIDDAY - timedelta(days=7)


def test_events_report_unreadable_lines_and_read_the_rest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, _linked = repository_with_linked_worktree(tmp_path)
    log = writer(events_directory(main), Clock())
    log.start()
    log.end(0)
    assert log.path is not None
    lines = log.path.read_bytes().splitlines()
    newer = json.loads(lines[1])
    newer["dashpot.added_later"] = "kept out"
    log.path.write_bytes(
        b"\n".join(
            [
                lines[0],
                b"not json",
                json.dumps({**newer, "schema": 2}).encode(),
                json.dumps(newer).encode(),
            ]
        )
        + b"\n"
    )
    # A compressed file is not one the Event Log names, so it is not read.
    (events_directory(main) / "events-2026-09-01.jsonl.gz").write_bytes(b"\x1f\x8b")
    monkeypatch.chdir(main)

    document = read_json(capsys)
    assert cli.main(["events"]) == 0
    text = capsys.readouterr()

    assert [event["event.name"] for event in document["events"]] == [
        "process.start",
        "process.end",
    ]
    assert "dashpot.added_later" not in document["events"][1]
    assert document["unreadable"] == [
        {"path": str(log.path), "lines": [2, 3], "error": None}
    ]
    assert text.out.splitlines()[0].startswith(
        "2026-09-27T12:00:00.000000Z standard command:observe process.start"
    )
    assert "process.exit.code=0" in text.out.splitlines()[1]
    assert text.err == f"dashpot: skipped 2 unreadable lines in {log.path}\n"


def test_events_say_so_when_none_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli.main(["events", "--session", SESSION]) == 0

    assert capsys.readouterr().out == "no matching Runtime Events\n"


def test_a_directory_that_cannot_be_listed_is_reported_not_fatal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    readable = tmp_path / "readable"
    writer(readable, Clock()).start()

    with mock.patch(
        "dashpot.core.event_log_files.os.scandir",
        side_effect=[PermissionError(13, "Permission denied"), os.scandir(readable)],
    ):
        reading = read_event_logs((tmp_path / "locked", readable), EventSelection())

    assert [event.body.name for event in reading.events] == ["process.start"]
    assert [(item.path, item.error) for item in reading.unreadable] == [
        (str(tmp_path / "locked"), "Permission denied")
    ]
    assert reading.directories == (str(readable),)


def test_a_file_removed_while_reading_is_skipped(tmp_path: Path) -> None:
    log = writer(tmp_path, Clock())
    log.start()
    assert log.path is not None
    path = log.path
    original = Path.open

    def vanish(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == path:
            raise FileNotFoundError(2, "gone")
        return original(self, *args, **kwargs)

    with mock.patch.object(Path, "open", vanish):
        reading = read_event_logs((tmp_path,), EventSelection())

    assert reading.events == ()
    assert reading.unreadable == ()


def test_a_file_that_cannot_be_read_is_reported_and_the_rest_printed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, linked = repository_with_linked_worktree(tmp_path)
    locked = writer(events_directory(main), Clock())
    locked.start()
    writer(events_directory(linked), Clock(), run=RUN_B).start()
    assert locked.path is not None
    path = locked.path
    original = Path.open

    def refuse(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == path:
            raise PermissionError(13, "Permission denied")
        return original(self, *args, **kwargs)

    monkeypatch.chdir(main)
    with mock.patch.object(Path, "open", refuse):
        assert cli.main(["events"]) == 0

    text = capsys.readouterr()
    assert len(text.out.splitlines()) == 1
    assert " process.start " in text.out
    assert text.err == f"dashpot: cannot read {path}: Permission denied\n"


def test_a_described_event_flattens_its_attributes_onto_one_line(
    tmp_path: Path,
) -> None:
    log = EventLog(
        EventLogDestination(tmp_path),
        identity=ProcessIdentity(run_id=RUN_A, kind=DASHBOARD_KIND),
        level="full",
        facts=lambda: facts().model_copy(update={"source_dirty": True}),
        clock=Clock(),
    )
    log.start()
    with log.start_as_current_span(
        "command", attributes=CommandAttributes(program="git", exit_code=1)
    ):
        pass

    start, span = read_event_logs((tmp_path,), EventSelection()).events

    assert "dashpot.source.dirty=true" in describe_runtime_event(start).split()
    words = describe_runtime_event(span).split()
    assert words[1:4] == ["full", "dashboard", "span"]
    assert {"process.executable.name=git", "process.exit.code=1"} <= set(words)
    assert any(word.startswith("dashpot.duration_seconds=") for word in words)


# --- work show's recent events ---------------------------------------------


class LaterOutcome(EventBody):
    """An outcome a later Dashpot records, standing in for #314's events."""

    name: Literal["hook.outcome"] = Field(default="hook.outcome", alias="event.name")


def test_recent_events_keep_the_sessions_outcomes_newest_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(runtime_events.EVENT_BODIES, "hook.outcome", LaterOutcome)
    now = datetime.now(UTC)
    clock = Clock(now - timedelta(days=8))
    hook = writer(
        tmp_path,
        clock,
        run=RUN_A,
        kind="hook:codex:Stop",
        harness="codex",
        session_id=SESSION,
    )
    other = writer(
        tmp_path,
        clock,
        run=RUN_B,
        kind="hook:codex:Stop",
        harness="codex",
        session_id=OTHER_SESSION,
    )
    hook.end(1)  # Too old to list.
    clock.now = now - timedelta(hours=1)
    hook.start()
    hook.record(LaterOutcome())
    hook.record(LevelChanged(previous="standard", current="full"))
    with (
        pytest.raises(OSError),
        hook.start_as_current_span(
            "command", attributes=CommandAttributes(program="ps")
        ),
    ):
        raise OSError(2, "No such file")
    with hook.start_as_current_span("command"):
        pass
    other.end(1)
    hook.end(0)
    clock.now = now - timedelta(minutes=1)
    hook.end(1)

    found = recent_events(
        (tmp_path,),
        EventSelection(
            session=SESSION,
            harness="codex",
            since=now - timedelta(days=7),
            outcomes_only=True,
        ),
        limit=20,
    )

    assert [
        (event.body.name, getattr(event.body, "status", None)) for event in found
    ] == [
        ("hook.outcome", None),
        ("span", "ERROR"),
        ("process.end", None),
    ]
    assert found[-1].time == (now - timedelta(minutes=1)).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def test_recent_events_read_back_only_as_far_as_they_need(tmp_path: Path) -> None:
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    clock = Clock(today)
    log = writer(tmp_path, clock)
    for second in range(3):
        clock.now = today + timedelta(seconds=second)
        log.end(second)
    # A line no writer could put there: yesterday's file holding an event
    # later than every one of today's, which shows whether it was read.
    yesterday = writer(tmp_path / "yesterday", Clock(today - timedelta(days=1)))
    yesterday.end(9)
    assert yesterday.path is not None
    late = json.loads(yesterday.path.read_bytes().splitlines()[-1])
    late["time"] = (today + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    (tmp_path / yesterday.path.name).write_text(json.dumps(late) + "\n")
    selection = EventSelection(since=today - timedelta(days=7))

    enough = recent_events((tmp_path,), selection, limit=2)
    # Today's file holds four: the writer's process.continued and three ends.
    more = recent_events((tmp_path,), selection, limit=5)

    assert [getattr(event.body, "exit_code", None) for event in enough] == [1, 2]
    assert [getattr(event.body, "exit_code", None) for event in more][-1] == 9
    assert recent_events((tmp_path,), selection, limit=0) == []


# --- Removing ----------------------------------------------------------------


def seed_days(directory: Path, *days: date) -> list[Path]:
    paths = []
    for day in days:
        log = writer(directory, Clock(datetime.combine(day, datetime.min.time(), UTC)))
        log.start()
        assert log.path is not None
        paths.append(log.path)
    return paths


def test_events_remove_deletes_this_checkouts_files_before_a_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, linked = repository_with_linked_worktree(tmp_path)
    today = datetime.now(UTC).date()
    old, older, recent = seed_days(
        events_directory(main),
        today - timedelta(days=40),
        today - timedelta(days=31),
        today - timedelta(days=2),
    )
    (sibling,) = seed_days(events_directory(linked), today - timedelta(days=40))
    stranger = events_directory(main) / "events-2020-01-01.jsonl.gz"
    stranger.write_bytes(b"compressed")
    monkeypatch.chdir(main)
    before = (today - timedelta(days=30)).isoformat()

    assert cli.main(["events", "remove", "--before", before]) == 0

    out = capsys.readouterr().out.splitlines()
    assert [line.split(" (")[0] for line in out] == [
        f"removed {old}",
        f"removed {older}",
    ]
    assert not old.exists()
    assert not older.exists()
    assert recent.exists()
    assert sibling.exists()
    assert stranger.exists()


def test_events_remove_dry_run_lists_without_removing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, _linked = repository_with_linked_worktree(tmp_path)
    today = datetime.now(UTC).date()
    (old,) = seed_days(events_directory(main), today - timedelta(days=3))
    monkeypatch.chdir(main)

    assert (
        cli.main(["events", "remove", "--before", today.isoformat(), "--dry-run"]) == 0
    )
    text = capsys.readouterr().out
    assert (
        cli.main(
            ["events", "remove", "--before", today.isoformat(), "--dry-run", "--json"]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)

    assert text == f"would remove {old} ({old.stat().st_size} bytes)\n"
    assert document == {
        "directory": str(events_directory(main)),
        "before": today.isoformat(),
        "today": today.isoformat(),
        "dryRun": True,
        "files": [
            {
                "path": str(old),
                "day": (today - timedelta(days=3)).isoformat(),
                "sizeBytes": old.stat().st_size,
                "outcome": "planned",
                "error": None,
            }
        ],
        "succeeded": True,
    }
    assert old.exists()


def test_events_remove_never_touches_today_or_later(tmp_path: Path) -> None:
    today = date(2026, 9, 27)
    yesterday, current, tomorrow = seed_days(
        tmp_path, today - timedelta(days=1), today, today + timedelta(days=1)
    )

    removal = remove_event_logs(
        EventLogDestination(tmp_path), date(2030, 1, 1), today=today
    )

    assert [(file.path, file.outcome) for file in removal.files] == [
        (str(yesterday), "removed")
    ]
    assert current.exists()
    assert tomorrow.exists()


def test_events_remove_outside_a_configured_checkout_acts_on_the_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    today = datetime.now(UTC).date()
    (old,) = seed_days(fallback_directory(), today - timedelta(days=10))
    unconfigured = init_repository(tmp_path / "plain")
    monkeypatch.chdir(unconfigured)

    assert cli.main(["events", "remove", "--before", today.isoformat(), "--json"]) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["directory"] == str(fallback_directory())
    assert [file["outcome"] for file in document["files"]] == ["removed"]
    assert not old.exists()


def test_events_remove_with_nothing_to_remove_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, _linked = repository_with_linked_worktree(tmp_path)
    monkeypatch.chdir(main)

    assert cli.main(["events", "remove", "--before", "2020-01-01"]) == 0

    assert capsys.readouterr().out == (
        f"no Event Log files dated before 2020-01-01 in {events_directory(main)}\n"
    )


def test_events_remove_reports_a_file_it_could_not_remove_and_goes_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, _linked = repository_with_linked_worktree(tmp_path)
    today = datetime.now(UTC).date()
    stuck, gone, removed = seed_days(
        events_directory(main),
        today - timedelta(days=3),
        today - timedelta(days=2),
        today - timedelta(days=1),
    )
    original = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self == stuck:
            raise PermissionError(13, "Permission denied")
        if self == gone:
            original(self)
        original(self, missing_ok)

    monkeypatch.chdir(main)
    with mock.patch.object(Path, "unlink", unlink):
        code = cli.main(["events", "remove", "--before", today.isoformat()])

    captured = capsys.readouterr()
    assert code == 2
    assert [line.split(" (")[0] for line in captured.out.splitlines()] == [
        f"could not remove {stuck}",
        f"already gone {gone}",
        f"removed {removed}",
    ]
    assert captured.err == (f"dashpot: could not remove {stuck}: Permission denied\n")
    assert stuck.exists()
    assert not removed.exists()


def test_events_remove_refuses_a_directory_it_cannot_list(tmp_path: Path) -> None:
    with (
        mock.patch(
            "dashpot.core.event_log_files.os.scandir",
            side_effect=PermissionError(13, "Permission denied"),
        ),
        pytest.raises(Exception, match="cannot list the Event Log"),
    ):
        remove_event_logs(EventLogDestination(tmp_path), date(2026, 9, 1))


def test_events_remove_refuses_without_anywhere_to_remove_from(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    with mock.patch.object(cli, "route_event_log", return_value=None):
        code = cli.main(["events", "remove", "--before", "2026-09-01"])

    assert code == 2
    assert capsys.readouterr().err.startswith("dashpot: no Event Log to remove from")


def test_events_remove_requires_a_day(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["events", "remove"]) == 2
    assert cli.main(["events", "remove", "--before", "soon"]) == 2

    err = " ".join(capsys.readouterr().err.split())
    assert "--before" in err
    assert "is not a day such as 2026-09-27" in err


# --- Size --------------------------------------------------------------------


def test_the_size_counts_only_event_log_files(tmp_path: Path) -> None:
    (tmp_path / "events-2026-09-01.jsonl").write_bytes(b"x" * 10)
    (tmp_path / f"dashboard-{RUN_A}-2026-09-01.jsonl").write_bytes(b"x" * 5)
    (tmp_path / "events-2026-08-01.jsonl.gz").write_bytes(b"x" * 1000)

    assert event_log_size(tmp_path) == 15
    assert event_log_size(tmp_path / "missing") == 0


def test_event_log_large_warns_past_its_size_and_acts_on_nothing(
    tmp_path: Path,
) -> None:
    checkout = EventLogDestination(tmp_path / "events", checkout=tmp_path)
    fallback = EventLogDestination(tmp_path / "fallback")

    assert event_log_large_diagnostic(checkout, LARGE_EVENT_LOG_BYTES) is None
    large = event_log_large_diagnostic(checkout, 250_000_000)
    elsewhere = event_log_large_diagnostic(fallback, LARGE_EVENT_LOG_BYTES + 1)

    assert large is not None
    assert large.code == "event-log-large"
    assert large.severity == "warning"
    assert large.message == (
        f"The Event Log in {tmp_path / 'events'} holds 250 MB, past 200 MB; "
        f"remove old files with 'dashpot events remove --before DATE' run in "
        f"{tmp_path}"
    )
    assert elsewhere is not None
    assert elsewhere.message.endswith("run outside every configured checkout")
