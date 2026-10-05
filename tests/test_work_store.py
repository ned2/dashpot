from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from dashpot.core.record_store import RecordKeyError
from dashpot.sessions.work_store import (
    ActiveWork,
    RelocationIntent,
    SessionProcess,
    WorkerAssignment,
    WorkStore,
)

LATER = "2026-08-28T02:00:00Z"
ASSIGNED = WorkerAssignment(
    worker_id="agent-1",
    issue_id="I_first",
    issue_reference="first",
    worktree="/repo-first",
    assigned_at="2026-10-04T00:00:00Z",
)


def work(
    session_key: str = "codex-42-abcd1234",
    issue_id: str = "I_one",
    started_at: str = "2026-08-28T01:00:00Z",
) -> ActiveWork:
    return ActiveWork(
        session_key=session_key,
        harness="codex",
        session_label="codex pid 42",
        session_process=SessionProcess(pid=42, started_at="Tue Aug 25 01:00:00 2026"),
        issue_id=issue_id,
        issue_reference="example/project#7",
        binding_provenance="explicit-reference",
        started_at=started_at,
        working_directory="/repo",
        branch="main",
    )


def test_started_work_survives_a_reread(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work())

    active, diagnostics = WorkStore(tmp_path).active()

    assert diagnostics == []
    assert active == [work()]
    assert active[0].run_id == "work:codex:codex-42-abcd1234:2026-08-28T01:00:00Z"


def test_switching_replaces_the_sessions_active_run(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work(issue_id="I_one", started_at="2026-08-28T01:00:00Z"))
    (previous,) = store.active()[0]
    assert store.replace_current(
        previous, work(issue_id="I_two", started_at="2026-08-28T02:00:00Z")
    )

    active, _ = store.active()

    assert len(active) == 1
    assert active[0].issue_id == "I_two"
    assert active[0].started_at == "2026-08-28T02:00:00Z"


def test_stop_removes_only_that_sessions_work(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    first = work(session_key="codex-1-aa")
    store.start(first)
    store.start(work(session_key="codex-2-bb", issue_id="I_two"))

    assert store.stop_current(first) is True
    assert store.stop_current(first) is False

    active, _ = store.active()
    assert [item.session_key for item in active] == ["codex-2-bb"]


def test_two_sessions_on_one_issue_are_independent_records(
    tmp_path: Path,
) -> None:
    store = WorkStore(tmp_path)
    store.start(work(session_key="codex-1-aa"))
    store.start(work(session_key="codex-2-bb"))

    active, _ = store.active()

    assert len(active) == 2
    assert len({item.run_id for item in active}) == 2


def test_malformed_and_unversioned_records_become_diagnostics(
    tmp_path: Path,
) -> None:
    store = WorkStore(tmp_path)
    store.start(work())
    (store.directory / "broken.json").write_text("{not json")
    (store.directory / "future.json").write_text(json.dumps({"version": 99}))

    active, diagnostics = store.active()

    assert len(active) == 1
    codes = {diagnostic.code for diagnostic in diagnostics}
    assert codes == {"work-store-malformed"}
    assert len(diagnostics) == 2


def test_unsafe_session_key_is_rejected(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)

    with pytest.raises(RecordKeyError, match="session key"):
        store.start(
            ActiveWork(
                session_key="../escape",
                harness="codex",
                session_label="codex pid 42",
                session_process=None,
                issue_id="I_one",
                issue_reference="example/project#7",
                binding_provenance="explicit-reference",
                started_at="2026-08-28T01:00:00Z",
                working_directory="/repo",
                branch=None,
            )
        )

    assert not (tmp_path / ".dashpot" / "escape.json").exists()


def test_concurrent_writers_never_partially_write_state(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    barrier = threading.Barrier(8)
    failures: list[Exception] = []

    def writer(index: int) -> None:
        barrier.wait()
        try:
            previous = None
            for turn in range(5):
                replacement = work(
                    session_key=f"codex-{index}-aa",
                    issue_id=f"I_{turn}",
                    started_at=f"2026-08-28T0{turn}:00:00Z",
                )
                if previous is None:
                    store.start(replacement)
                else:
                    assert store.replace_current(previous, replacement)
                previous = replacement
        except Exception as exc:  # pragma: no cover - asserted below.
            failures.append(exc)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    active, diagnostics = store.active()
    assert failures == []
    assert diagnostics == []
    assert len(active) == 8
    assert all(item.issue_id == "I_4" for item in active)


def test_orphaned_lock_files_are_reclaimed_and_live_ones_kept(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work(session_key="codex-1-aa"))
    (store.directory / ".codex-9-zz.lock").touch()
    (store.directory / ".not a key.lock").touch()

    assert store.orphaned_locks() == ["codex-9-zz"]
    assert store.prune_lock("codex-9-zz") is True
    assert store.prune_lock("codex-1-aa") is False

    assert not (store.directory / ".codex-9-zz.lock").exists()
    assert (store.directory / ".codex-1-aa.lock").exists()
    assert (store.directory / ".not a key.lock").exists()


def test_session_identity_round_trips_and_legacy_records_carry_none(
    tmp_path: Path,
) -> None:
    store = WorkStore(tmp_path)
    recorded = ActiveWork(
        session_key="codex-session-0123abcd4567",
        harness="codex",
        session_label="codex session 01a05099",
        session_process=None,
        issue_id="I_one",
        issue_reference="example/project#7",
        binding_provenance="explicit-reference",
        started_at="2026-08-28T01:00:00Z",
        working_directory="/repo",
        branch="main",
        session_id="01a05099",
    )
    store.start(recorded)
    store.start(work())
    path = store.directory / "codex-42-abcd1234.json"
    document = json.loads(path.read_text())
    del document["sessionId"]
    path.write_text(json.dumps(document))

    active, diagnostics = store.active()

    assert diagnostics == []
    by_key = {item.session_key: item for item in active}
    assert by_key["codex-session-0123abcd4567"] == recorded
    assert by_key["codex-42-abcd1234"].session_id is None


def test_malformed_session_identity_is_diagnosed(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work())
    path = store.directory / "codex-42-abcd1234.json"
    document = json.loads(path.read_text())
    document["sessionId"] = "not valid!"
    path.write_text(json.dumps(document))

    active, diagnostics = store.active()

    assert active == []
    assert [diagnostic.code for diagnostic in diagnostics] == ["work-store-malformed"]


def test_the_persisted_record_keeps_its_wire_key_set(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work(session_key="codex-42-abcd1234"))

    document = json.loads((store.directory / "codex-42-abcd1234.json").read_text())

    # The record's keys are the persisted contract: camelCase, explicit nulls,
    # no session key (that is the filename), in the order they were written.
    assert list(document) == [
        "version",
        "harness",
        "sessionLabel",
        "sessionProcess",
        "issueId",
        "issueReference",
        "bindingProvenance",
        "startedAt",
        "workingDirectory",
        "branch",
        "sessionId",
        "relocation",
        "workers",
    ]
    assert document["sessionProcess"] == {
        "pid": 42,
        "startedAt": "Tue Aug 25 01:00:00 2026",
    }
    assert document["sessionId"] is None
    assert document["relocation"] is None
    assert document["workers"] == []


def test_worker_assignments_round_trip_under_their_wire_keys(
    tmp_path: Path,
) -> None:
    store = WorkStore(tmp_path)
    assigned = WorkerAssignment(
        worker_id="agent-1",
        issue_id="I_first",
        issue_reference="first",
        worktree="/repo-first",
        assigned_at="2026-10-04T00:00:00Z",
    )
    store.start(replace(work(), workers=(assigned,)))

    document = json.loads((store.directory / "codex-42-abcd1234.json").read_text())

    assert document["workers"] == [
        {
            "workerId": "agent-1",
            "issueId": "I_first",
            "issueReference": "first",
            "worktree": "/repo-first",
            "assignedAt": "2026-10-04T00:00:00Z",
        }
    ]
    (read,) = store.active()[0]
    assert read.workers == (assigned,)


def test_a_record_written_before_assignments_reads_with_none(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work(session_key="codex-42-abcd1234"))
    path = store.directory / "codex-42-abcd1234.json"
    document = json.loads(path.read_text())
    del document["workers"]
    path.write_text(json.dumps(document))

    (read,) = store.active()[0]

    assert read.workers == ()


def _rewrite(store: WorkStore, **changes: object) -> None:
    path = store.directory / "codex-42-abcd1234.json"
    document = json.loads(path.read_text())
    document.update(changes)
    path.write_text(json.dumps(document))


def test_fields_a_newer_dashpot_wrote_are_read_and_compared(tmp_path: Path) -> None:
    # A newer Dashpot may persist more; this one reads what it knows.
    store = WorkStore(tmp_path)
    store.start(work())
    _rewrite(store, futureField={"nested": True})

    (read,), diagnostics = store.active()

    assert diagnostics == []
    assert read.retained == {"futureField": {"nested": True}}
    assert replace(read, retained={}) == work()
    # The compare-and-swap sees them, so a run read before they were written
    # is no longer current.
    assert not store.replace_current(work(), replace(work(), branch="other"))


def _with_newer_fields(store: WorkStore) -> ActiveWork:
    """Start a run whose every object carries a field a newer Dashpot wrote."""
    intent = RelocationIntent(target_worktree="/target", requested_at=LATER)
    store.start(replace(work(), relocation=intent, workers=(ASSIGNED,)))
    path = store.record_path(work().session_key)
    document = json.loads(path.read_text())
    document["futureField"] = {"nested": True}
    document["sessionProcess"]["futureProcessField"] = 1
    document["relocation"]["futureIntentField"] = 2
    document["workers"][0]["futureWorkerField"] = 3
    path.write_text(json.dumps(document))
    (read,) = store.active()[0]
    return read


@pytest.mark.parametrize("rewrite", ["replace_current", "complete_relocation"])
def test_a_rewrite_carries_the_fields_a_newer_dashpot_wrote(
    tmp_path: Path, rewrite: str
) -> None:
    source = WorkStore(tmp_path / "a")
    read = _with_newer_fields(source)
    changed = replace(read, branch="other")
    destination = source if rewrite == "replace_current" else WorkStore(tmp_path / "b")

    if rewrite == "replace_current":
        assert source.replace_current(read, changed)
    else:
        assert source.complete_relocation(read, destination, changed)

    document = json.loads(destination.record_path(read.session_key).read_text())
    assert document["branch"] == "other"
    assert document["futureField"] == {"nested": True}
    assert document["sessionProcess"]["futureProcessField"] == 1
    assert document["relocation"]["futureIntentField"] == 2
    assert document["workers"][0]["futureWorkerField"] == 3
    assert destination.active()[0] == [changed]


def test_a_new_run_or_rebuilt_object_starts_without_newer_fields(
    tmp_path: Path,
) -> None:
    store = WorkStore(tmp_path)
    read = _with_newer_fields(store)
    rebuilt = replace(
        read,
        session_process=SessionProcess(pid=43, started_at="Tue Aug 25 02:00:00 2026"),
        relocation=None,
        workers=(ASSIGNED,),
    )

    assert store.replace_current(read, rebuilt)
    document = json.loads(store.record_path(read.session_key).read_text())
    assert document["futureField"] == {"nested": True}
    assert "futureProcessField" not in document["sessionProcess"]
    assert document["relocation"] is None
    assert "futureWorkerField" not in document["workers"][0]

    (current,) = store.active()[0]
    assert store.replace_current(current, work(started_at=LATER))
    document = json.loads(store.record_path(read.session_key).read_text())
    assert "futureField" not in document


def _interrupted_move(
    tmp_path: Path,
) -> tuple[WorkStore, WorkStore, ActiveWork, ActiveWork]:
    """Start a pending run at A and leave at B the copy a crash would leave."""
    source, destination = WorkStore(tmp_path / "a"), WorkStore(tmp_path / "b")
    intent = RelocationIntent(target_worktree=str(tmp_path / "b"), requested_at=LATER)
    pending = replace(work(), relocation=intent)
    source.start(pending)
    copy = replace(pending, working_directory=str(tmp_path / "b"), relocation=None)
    destination.start(copy)
    return source, destination, pending, copy


def test_a_retry_replaces_the_copy_an_interrupted_relocation_left(
    tmp_path: Path,
) -> None:
    source, destination, pending, copy = _interrupted_move(tmp_path)
    relocated = replace(
        copy,
        session_process=SessionProcess(pid=43, started_at="Tue Aug 25 02:00:00 2026"),
    )

    assert source.complete_relocation(pending, destination, relocated, repairing=copy)
    assert source.active()[0] == []
    assert destination.active()[0] == [relocated]


def test_a_retry_refuses_once_the_interrupted_copy_is_gone(
    tmp_path: Path,
) -> None:
    source, destination, pending, copy = _interrupted_move(tmp_path)
    assert destination.stop_current(copy)
    relocated = replace(copy, branch="other")

    assert not source.complete_relocation(
        pending, destination, relocated, repairing=copy
    )
    assert source.active()[0] == [pending]
    assert destination.active()[0] == []


def test_a_repaired_copy_must_be_the_relocating_run(tmp_path: Path) -> None:
    source, destination, pending, copy = _interrupted_move(tmp_path)

    with pytest.raises(ValueError, match="relocating Agent Run"):
        source.complete_relocation(
            pending,
            destination,
            copy,
            repairing=replace(copy, started_at=LATER),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sessionProcess": {"pid": True, "startedAt": "x"}}, "sessionProcess.pid"),
        ({"sessionProcess": {"pid": "42", "startedAt": "x"}}, "sessionProcess.pid"),
        ({"branch": 3}, "branch"),
        ({"issueId": ""}, "issueId"),
        ({"bindingProvenance": "inferred"}, "bindingProvenance"),
        ({"sessionId": "not valid!"}, "sessionId must be a hook session identity"),
    ],
)
def test_coerced_or_wrong_typed_fields_are_diagnosed_by_wire_path(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    store = WorkStore(tmp_path)
    store.start(work())
    _rewrite(store, **changes)

    active, diagnostics = store.active()

    assert active == []
    (diagnostic,) = diagnostics
    assert diagnostic.code == "work-store-malformed"
    assert message in diagnostic.message


def test_a_session_process_is_frozen() -> None:
    process = SessionProcess(pid=42, started_at="Tue Aug 25 01:00:00 2026")

    with pytest.raises(ValidationError):
        process.pid = 43  # ty: ignore[invalid-assignment]
