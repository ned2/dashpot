"""A person's acknowledgement of the sub-agents a Worktree preview lists (ADR 0112).

A live sub-agent blocks every Worktree of its Repository because no hook says
where it works (ADR 0066). The acknowledgement lifts exactly those blockers,
for exactly the set the preview names, while the processes inside the
Worktree were all checked and none was found (ADR 0104); nothing else.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dashpot import cli
from dashpot.core.event_log import (
    DASHBOARD_KIND,
    EventLog,
    EventLogDestination,
    use_event_log,
)
from dashpot.core.runtime_events import (
    ProcessIdentity,
    ProcessStart,
    SubagentsAcknowledged,
    read_runtime_event,
)
from dashpot.event_logs import LEVEL_VARIABLE
from dashpot.repository.cleanup import (
    CHANGED_SINCE_PREVIEW,
    NO_ACKNOWLEDGEMENT,
    Acknowledgement,
    BranchCleanupRequest,
    CleanupConfirmation,
    CleanupError,
    CleanupPreview,
    CleanupReport,
    ListedSubagents,
    WorktreeCleanupRequest,
    describe_cleanup_preview,
    describe_cleanup_report,
    inspect_cleanup,
    lifted,
    listed_in,
    override_offer,
    parse_despite_subagents,
    perform_cleanup,
)
from dashpot.serialization import cleanup_preview_document
from dashpot.sessions import processes
from dashpot.sessions.hook_records import session_directory
from dashpot.sessions.processes import ProcessIdentity as SessionProcessIdentity
from dashpot.sessions.processes import ProcessLookup
from dashpot.sessions.work_store import ActiveWork, SessionProcess, WorkStore
from dashpot.sessions.working_directories import (
    ProcessDirectory,
    ProcessScan,
    WorkingDirectories,
)
from factories import git
from helpers import scan_of, table_lookup
from test_cleanup import (
    PARENT,
    PARENT_SESSION,
    publish_subagent,
    serve,
    sub_agent_worktrees,
)

OTHER_SESSION = "9c1e0b7a-2f4d-4e8a-b6c3-0d5e7f8a9b1c"
LOOKUP = table_lookup({PARENT.pid: PARENT})
BOTH = frozenset({ListedSubagents(PARENT_SESSION, frozenset({"a3932", "a686b12"}))})


def two_subagents(
    tmp_path: Path, process: SessionProcessIdentity = PARENT
) -> tuple[Path, Path]:
    """A Repository whose parent session at the main Worktree lists two sub-agents."""
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    store = session_directory(root)
    publish_subagent(store, root, "SubagentStart", "a686b12", process=process)
    publish_subagent(store, root, "SubagentStart", "a3932", minute=42, process=process)
    return root, target


def shown(root: Path, target: Path, scan: ProcessScan | None = None) -> CleanupPreview:
    return inspect_cleanup(
        WorktreeCleanupRequest(root, target),
        lookup=LOOKUP,
        scan=scan_of() if scan is None else scan,
    )


def removing(
    preview: CleanupPreview, root: Path, target: Path, acknowledged: Acknowledgement
) -> CleanupConfirmation:
    """Confirm the Worktree and its local Branch, despite ``acknowledged``."""
    return CleanupConfirmation(
        WorktreeCleanupRequest(root, target),
        preview.fingerprint,
        tuple(
            one.identity
            for one in preview.targets
            if one.kind in {"worktree", "local-branch"}
        ),
        despite_subagents=acknowledged,
        listed=listed_in(preview) if acknowledged else None,
    )


def memory_log() -> EventLog:
    return EventLog(
        None,
        identity=ProcessIdentity(run_id="0" * 32, kind=DASHBOARD_KIND),
        level="standard",
        facts=lambda: ProcessStart(
            version="0.1.0",
            install_kind="editable",
            revision="unknown",
            pid=os.getpid(),
            python_version="3.14.0",
        ),
        keep_recent=50,
    )


def acknowledgements(log: EventLog) -> list[SubagentsAcknowledged]:
    return [
        event.body
        for event in log.recent_events()
        if isinstance(event.body, SubagentsAcknowledged)
    ]


def perform(
    confirmation: CleanupConfirmation,
    *,
    scan: ProcessScan | None = None,
    lookup: ProcessLookup = LOOKUP,
    log: EventLog | None = None,
    dry_run: bool = False,
) -> CleanupReport:
    with use_event_log(log):
        return perform_cleanup(
            confirmation,
            lookup=lookup,
            scan=scan_of() if scan is None else scan,
            dry_run=dry_run,
        )


def test_the_flag_reads_one_exact_set_per_session() -> None:
    assert parse_despite_subagents(()) == NO_ACKNOWLEDGEMENT
    assert parse_despite_subagents(
        [f"{PARENT_SESSION}:a686b12,a3932", f"{OTHER_SESSION}:b1"]
    ) == frozenset(
        {
            ListedSubagents(PARENT_SESSION, frozenset({"a3932", "a686b12"})),
            ListedSubagents(OTHER_SESSION, frozenset({"b1"})),
        }
    )
    (listed,) = parse_despite_subagents([f"{PARENT_SESSION}:a686b12,a3932"])
    assert listed.argument == f"{PARENT_SESSION}:a3932,a686b12"


@pytest.mark.parametrize(
    "value", ["a686b12", ":a686b12", f"{PARENT_SESSION}:", f"{PARENT_SESSION}:a,,b"]
)
def test_a_malformed_value_is_a_usage_mistake(value: str) -> None:
    with pytest.raises(CleanupError, match="takes SESSION:AGENT"):
        parse_despite_subagents([value])


def test_a_session_named_twice_is_refused() -> None:
    with pytest.raises(CleanupError, match="more than once"):
        parse_despite_subagents([f"{PARENT_SESSION}:a1", f"{PARENT_SESSION}:a2"])


def test_the_exact_set_removes_the_worktree_and_its_branch_and_is_recorded(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    tree = next(one for one in preview.targets if one.kind == "worktree")
    held = next(one for one in preview.targets if one.kind == "local-branch")
    assert not tree.available
    assert override_offer(preview) == BOTH
    assert lifted(preview, BOTH) == {tree.identity, held.identity}
    log = memory_log()

    report = perform(removing(preview, root, target, BOTH), log=log)

    assert report.succeeded is True
    assert [result.outcome for result in report.results] == ["deleted", "deleted"]
    assert not target.exists()
    assert git(root, "branch", "--list", "feat") == ""
    (event,) = [
        event
        for event in log.recent_events()
        if isinstance(event.body, SubagentsAcknowledged)
    ]
    assert event.body == SubagentsAcknowledged(
        agents=("a3932", "a686b12"), outcome="deleted"
    )
    assert event.process.session_id == PARENT_SESSION
    assert event.process.harness == "claude-code"
    assert event.process.worktree == str(target.resolve())


def test_without_the_acknowledgement_the_sub_agents_still_block(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    log = memory_log()

    report = perform(removing(preview, root, target, NO_ACKNOWLEDGEMENT), log=log)

    assert report.performed is False
    assert report.refusals[0].startswith("Worktree is unavailable: Claude Code session")
    assert target.exists()
    assert acknowledgements(log) == []
    # The refusal says how a person may go on, with the exact value.
    lines = describe_cleanup_report(report)
    assert lines[-1] == (
        f"                    --despite-subagents {PARENT_SESSION}:a3932,a686b12"
    )


@pytest.mark.parametrize(
    "acknowledged",
    [
        pytest.param({PARENT_SESSION: {"a686b12"}}, id="fewer"),
        pytest.param({PARENT_SESSION: {"a3932", "a686b12", "a777"}}, id="more"),
        pytest.param({OTHER_SESSION: {"a3932", "a686b12"}}, id="another-session"),
        pytest.param(
            {PARENT_SESSION: {"a3932", "a686b12"}, OTHER_SESSION: {"b1"}},
            id="an-extra-session",
        ),
    ],
)
def test_a_set_other_than_the_one_listed_is_refused_as_a_mistake(
    tmp_path: Path, acknowledged: dict[str, set[str]]
) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    given = frozenset(
        ListedSubagents(session, frozenset(agents))
        for session, agents in acknowledged.items()
    )
    assert lifted(preview, given) == frozenset()

    report = perform(removing(preview, root, target, given))

    assert report.performed is False
    # The preview is unchanged, so the set was mistyped rather than changed.
    assert report.changed is False
    (refusal,) = report.refusals
    assert refusal.startswith(
        f"the sub-agents listed as working are {PARENT_SESSION}:a3932,a686b12, not the "
    )
    assert refusal.endswith(
        " acknowledged; nothing was removed: check them again against this preview"
    )
    lines = describe_cleanup_report(report)
    assert lines[2].startswith("Refused         the sub-")
    assert lines[-1].endswith(f"--despite-subagents {PARENT_SESSION}:a3932,a686b12")
    assert target.exists()


def test_a_sub_agent_that_starts_after_the_preview_refuses_the_removal(
    tmp_path: Path,
) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a686b12")
    preview = shown(root, target)
    acknowledged = override_offer(preview)
    publish_subagent(session_directory(root), root, "SubagentStart", "a3932", minute=42)

    report = perform(removing(preview, root, target, acknowledged))

    assert report.performed is False
    assert report.changed is True
    (refusal,) = report.refusals
    assert refusal.startswith(
        f"the sub-agents listed as working are {PARENT_SESSION}:a3932,a686b12, "
        f"not the {PARENT_SESSION}:a686b12 acknowledged"
    )
    assert describe_cleanup_report(report)[2].startswith("Changed         the sub-")
    assert target.exists()


def test_a_process_inside_the_worktree_is_never_acknowledged(tmp_path: Path) -> None:
    root, target = two_subagents(tmp_path)
    shell = ProcessDirectory(4242, 1, "bash", target.resolve())
    preview = shown(root, target, scan_of(shell))
    assert override_offer(preview) == NO_ACKNOWLEDGEMENT
    assert "--despite-subagents" not in "\n".join(describe_cleanup_preview(preview))

    report = perform(removing(preview, root, target, BOTH), scan=scan_of(shell))

    assert report.performed is False
    assert report.refusals[0].startswith("Worktree is unavailable: ")
    assert "A process is running inside this Worktree" in report.refusals[0]
    assert target.exists()


def test_a_process_that_arrives_after_the_preview_refuses_the_removal(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    shell = ProcessDirectory(4242, 1, "bash", target.resolve())

    report = perform(removing(preview, root, target, BOTH), scan=scan_of(shell))

    assert report.refusals == (CHANGED_SINCE_PREVIEW,)
    assert target.exists()


def test_an_incomplete_process_check_cannot_carry_an_acknowledgement(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    gap = scan_of(incomplete="isolated-namespace")
    preview = shown(root, target, gap)
    assert override_offer(preview) == NO_ACKNOWLEDGEMENT

    report = perform(removing(preview, root, target, BOTH), scan=gap)

    assert report.performed is False
    assert report.changed is False
    (refusal,) = report.refusals
    assert refusal.startswith(
        "sub-agents cannot be acknowledged while the processes inside the "
        "Worktree were not all checked: "
    )
    assert target.exists()


def dirty(root: Path, target: Path) -> None:
    (target / "scratch.txt").write_text("work in progress\n")


def another_session_here(root: Path, target: Path) -> None:
    publish_subagent(
        session_directory(target), target, "SubagentStart", "b1", session=OTHER_SESSION
    )


def an_agent_run_here(root: Path, target: Path) -> None:
    WorkStore(target).start(
        ActiveWork(
            session_key=f"claude-code-{OTHER_SESSION}",
            harness="claude-code",
            session_label=f"Claude Code session {OTHER_SESSION}",
            session_process=SessionProcess(
                pid=PARENT.pid, started_at=PARENT.started_at
            ),
            issue_id="I_10",
            issue_reference="issue-10",
            binding_provenance="explicit-reference",
            started_at="2026-09-30T03:35:00.000000Z",
            working_directory=str(target),
            branch="feat",
            session_id=OTHER_SESSION,
        )
    )


@pytest.mark.parametrize(
    ("occupy", "kind"),
    [
        pytest.param(dirty, "dirty", id="dirty"),
        pytest.param(another_session_here, "agent-session", id="agent-session"),
        pytest.param(an_agent_run_here, "agent-run", id="agent-run"),
    ],
)
def test_no_other_blocker_is_lifted(
    tmp_path: Path, occupy: Callable[[Path, Path], None], kind: str
) -> None:
    root, target = two_subagents(tmp_path)
    occupy(root, target)
    preview = shown(root, target)
    tree = next(one for one in preview.targets if one.kind == "worktree")
    assert kind in {blocker.kind for blocker in tree.blockers}
    assert "sub-agent" in {blocker.kind for blocker in tree.blockers}
    assert override_offer(preview) == NO_ACKNOWLEDGEMENT
    assert lifted(preview, BOTH) == frozenset()
    assert "--despite-subagents" not in "\n".join(describe_cleanup_preview(preview))

    report = perform(removing(preview, root, target, BOTH))

    assert report.performed is False
    assert report.refusals[0].startswith("Worktree is unavailable: ")
    assert target.exists()
    # A mistyped set is a mistake here too, though nothing was offered.
    fewer = frozenset({ListedSubagents(PARENT_SESSION, frozenset({"a686b12"}))})
    mistyped = perform(removing(preview, root, target, fewer))
    assert mistyped.performed is False
    assert mistyped.changed is False
    assert mistyped.refusals[0].startswith("the sub-agents listed as working are ")
    assert target.exists()


def test_an_agent_id_the_flag_cannot_spell_is_left_to_the_dialog(
    tmp_path: Path,
) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a1,a2")
    preview = shown(root, target)
    (listed,) = override_offer(preview)
    assert listed.spelled is False

    lines = describe_cleanup_preview(preview)

    assert not any(line.strip().startswith("--despite-subagents") for line in lines)
    assert any(
        line.endswith(
            "from the dashboard's Cleanup dialog: --despite-subagents spells "
            "only IDs that are identifiers without :"
        )
        for line in lines
    )
    # The spelling the flag would need reads back as another set.
    assert parse_despite_subagents([listed.argument]) != frozenset({listed})


def test_an_agent_id_a_shell_would_split_is_left_to_the_dialog(
    tmp_path: Path,
) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    publish_subagent(session_directory(root), root, "SubagentStart", "a1 $(a2)")
    preview = shown(root, target)
    (listed,) = override_offer(preview)
    assert listed.spelled is False

    lines = describe_cleanup_preview(preview)

    assert not any(line.strip().startswith("--despite-subagents") for line in lines)
    assert any(
        line.endswith(
            "from the dashboard's Cleanup dialog: --despite-subagents spells only IDs that are identifiers without :"
        )
        for line in lines
    )


def test_an_agent_id_that_is_no_identifier_is_left_out_of_the_event(
    tmp_path: Path,
) -> None:
    root, target, _sibling = sub_agent_worktrees(tmp_path)
    store = session_directory(root)
    publish_subagent(store, root, "SubagentStart", "a686b12")
    publish_subagent(store, root, "SubagentStart", "not an id", minute=42)
    preview = shown(root, target)
    log = memory_log()

    report = perform(removing(preview, root, target, override_offer(preview)), log=log)

    assert report.succeeded is True
    assert acknowledgements(log) == [
        SubagentsAcknowledged(agents=("a686b12",), outcome="deleted")
    ]


def test_a_branch_cleanup_takes_no_acknowledgement(tmp_path: Path) -> None:
    root, _target = two_subagents(tmp_path)
    request = BranchCleanupRequest(root, "other")
    preview = inspect_cleanup(request, lookup=LOOKUP, scan=scan_of())

    report = perform(
        CleanupConfirmation(request, preview.fingerprint, (), despite_subagents=BOTH)
    )

    assert report.refusals == (
        "--despite-subagents acknowledges sub-agents only for removing a Worktree",
    )


class ScanTurns:
    """A scan that finds nothing until its ``after``-th call, then ``then`` from it on."""

    def __init__(self, after: int, then: WorkingDirectories) -> None:
        self.after = after
        self.then = then
        self.calls = 0

    def __call__(self) -> WorkingDirectories:
        self.calls += 1
        return WorkingDirectories() if self.calls < self.after else self.then


def scans_per_inspection(root: Path, target: Path) -> int:
    counting = ScanTurns(10_000, WorkingDirectories())
    shown(root, target, counting)
    return counting.calls


def test_each_step_is_checked_again_just_before_it_runs(tmp_path: Path) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    # The process arrives after the confirmation's re-inspection, in time
    # for the check taken just before the Worktree is removed.
    shell = ProcessDirectory(4242, 1, "bash", target.resolve())
    arrives = ScanTurns(
        scans_per_inspection(root, target) + 1, WorkingDirectories((shell,))
    )
    log = memory_log()

    report = perform(removing(preview, root, target, BOTH), scan=arrives, log=log)

    assert report.performed is True
    tree, branch = report.results
    assert tree.outcome == "refused"
    assert tree.detail.startswith(
        "not attempted: process: A process is running inside this Worktree"
    )
    assert branch.outcome == "refused"
    assert branch.detail == "not attempted: Worktree was refused"
    assert target.exists()
    assert acknowledgements(log) == [
        SubagentsAcknowledged(agents=("a3932", "a686b12"), outcome="refused")
    ]


def test_the_check_before_deleting_at_the_remote_comes_first(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    bare = serve(tmp_path, root, "feat")
    preview = shown(root, target)
    remote = next(one for one in preview.targets if one.kind == "remote-branch")
    assert remote.identity in lifted(preview, BOTH)
    shell = ProcessDirectory(4242, 1, "bash", target.resolve())
    arrives = ScanTurns(
        scans_per_inspection(root, target) + 1, WorkingDirectories((shell,))
    )
    confirmation = CleanupConfirmation(
        WorktreeCleanupRequest(root, target),
        preview.fingerprint,
        tuple(one.identity for one in preview.targets),
        despite_subagents=BOTH,
        listed=BOTH,
    )

    report = perform(confirmation, scan=arrives)

    first, *rest = report.results
    assert first.kind == "remote-branch"
    assert first.outcome == "refused"
    assert first.detail.startswith("not attempted: process: ")
    assert all(one.outcome == "refused" for one in rest)
    assert git(bare, "for-each-ref", "refs/heads/feat") != ""
    assert target.exists()


def test_a_scan_that_falls_short_before_a_step_refuses_it(tmp_path: Path) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    falls_short = ScanTurns(
        scans_per_inspection(root, target) + 1,
        WorkingDirectories(incomplete="lsof-timeout"),
    )

    report = perform(removing(preview, root, target, BOTH), scan=falls_short)

    tree, _branch = report.results
    assert tree.outcome == "refused"
    assert tree.detail == (
        "not attempted: Processes running inside this Worktree were not all "
        "checked: lsof did not answer in time."
    )
    assert target.exists()


def test_a_sub_agent_set_that_changes_before_a_step_refuses_it(
    tmp_path: Path,
) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    inspections = scans_per_inspection(root, target)

    calls: list[int] = []

    def stop_one() -> WorkingDirectories:
        calls.append(1)
        if len(calls) == inspections:
            # The last scan of the re-inspection: the hook reports the stop
            # just after, so the step's check sees one sub-agent fewer.
            publish_subagent(
                session_directory(root), root, "SubagentStop", "a3932", minute=43
            )
        return WorkingDirectories()

    report = perform(removing(preview, root, target, BOTH), scan=stop_one)

    tree, _branch = report.results
    assert tree.outcome == "refused"
    assert tree.detail == (
        "not attempted: the sub-agents listed as working changed to "
        f"{PARENT_SESSION}:a686b12 from the {PARENT_SESSION}:a3932,a686b12 "
        "acknowledged"
    )
    assert target.exists()


def test_a_dry_run_plans_the_removal_and_records_nothing(tmp_path: Path) -> None:
    root, target = two_subagents(tmp_path)
    preview = shown(root, target)
    log = memory_log()

    report = perform(removing(preview, root, target, BOTH), log=log, dry_run=True)

    assert report.performed is False
    assert len(report.planned) == 2
    assert acknowledgements(log) == []
    assert target.exists()


def test_the_blocker_publishes_its_session_and_agents(tmp_path: Path) -> None:
    root, target = two_subagents(tmp_path)

    document = cleanup_preview_document(shown(root, target))

    worktree = next(one for one in document["targets"] if one["kind"] == "worktree")
    (blocker,) = worktree["blockers"]
    assert blocker["kind"] == "sub-agent"
    assert blocker["sessionId"] == PARENT_SESSION
    assert blocker["harness"] == "claude-code"
    assert blocker["agents"] == ["a3932", "a686b12"]


def written(directory: Path, name: str) -> list[dict[str, Any]]:
    return [
        event
        for path in sorted(directory.glob("*.jsonl"))
        for line in path.read_text().splitlines()
        if (event := json.loads(line))["event.name"] == name
    ]


def remove(target: Path, *flags: str, events: Path) -> int:
    return cli.main(
        ["worktree", "remove", str(target), *flags],
        event_log=EventLogDestination(events),
    )


def test_the_command_line_removes_despite_the_named_sub_agents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The command line looks processes up on the host, so the parent
    # session is this test's own process, live for the whole test.
    monkeypatch.setattr(processes, "process_namespace_is_isolated", lambda: False)
    live = processes.host_process_lookup(os.getpid())
    assert isinstance(live, processes.ProcessPresent)
    root, target = two_subagents(tmp_path, live.identity)
    monkeypatch.chdir(root)
    monkeypatch.setenv(LEVEL_VARIABLE, "standard")
    events = tmp_path / "events"

    assert remove(target, "--delete-branch", events=events) != 0
    refused = capsys.readouterr().out
    flag = f"--despite-subagents {PARENT_SESSION}:a3932,a686b12"
    assert flag in refused
    assert target.exists()

    assert remove(target, "--despite-subagents", f"{PARENT_SESSION}:x", events=events)
    assert "not the " in capsys.readouterr().out
    assert target.exists()

    assert remove(target, *flag.split(), "--delete-branch", events=events) == 0
    assert "deleted" in capsys.readouterr().out
    assert not target.exists()
    assert git(root, "branch", "--list", "feat") == ""
    (recorded,) = written(events, "cleanup.subagents_acknowledged")
    assert recorded["dashpot.sub_agent.ids"] == ["a3932", "a686b12"]
    assert recorded["dashpot.cleanup.outcome"] == "deleted"
    assert recorded["dashpot.agent_session.id"] == PARENT_SESSION
    assert recorded["dashpot.agent_session.harness"] == "claude-code"
    assert recorded["dashpot.worktree.path"] == str(target)
    read = read_runtime_event(json.dumps(recorded))
    assert read is not None
    assert read.body == SubagentsAcknowledged(
        agents=("a3932", "a686b12"), outcome="deleted"
    )


def test_a_malformed_flag_removes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, target = two_subagents(tmp_path)
    monkeypatch.chdir(root)

    assert remove(target, "--despite-subagents", "a686b12", events=tmp_path) == 2
    assert "takes SESSION:AGENT" in " ".join(capsys.readouterr().err.split())
    assert target.exists()
