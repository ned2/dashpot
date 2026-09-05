from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from dashpot.work_store import ActiveWork, SessionProcess, WorkStore


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
    store.start(work(issue_id="I_two", started_at="2026-08-28T02:00:00Z"))

    active, _ = store.active()

    assert len(active) == 1
    assert active[0].issue_id == "I_two"
    assert active[0].started_at == "2026-08-28T02:00:00Z"


def test_stop_removes_only_that_sessions_work(tmp_path: Path) -> None:
    store = WorkStore(tmp_path)
    store.start(work(session_key="codex-1-aa"))
    store.start(work(session_key="codex-2-bb", issue_id="I_two"))

    assert store.stop("codex-1-aa") is True
    assert store.stop("codex-1-aa") is False

    active, _ = store.active()
    assert [item.session_key for item in active] == ["codex-2-bb"]
    assert not (store.directory / ".codex-1-aa.lock").exists()
    assert (store.directory / ".codex-2-bb.lock").exists()


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

    with pytest.raises(RuntimeError, match="session key"):
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
            for turn in range(5):
                store.start(
                    work(
                        session_key=f"codex-{index}-aa",
                        issue_id=f"I_{turn}",
                        started_at=f"2026-08-28T0{turn}:00:00Z",
                    )
                )
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
    ]
    assert document["sessionProcess"] == {
        "pid": 42,
        "startedAt": "Tue Aug 25 01:00:00 2026",
    }
    assert document["sessionId"] is None
    assert document["relocation"] is None


def _rewrite(store: WorkStore, **changes: object) -> None:
    path = store.directory / "codex-42-abcd1234.json"
    document = json.loads(path.read_text())
    document.update(changes)
    path.write_text(json.dumps(document))


def test_unknown_record_fields_are_retained_on_read(tmp_path: Path) -> None:
    # A newer Dashpot may persist more; this one reads what it knows.
    store = WorkStore(tmp_path)
    store.start(work())
    _rewrite(store, futureField={"nested": True})

    active, diagnostics = store.active()

    assert diagnostics == []
    assert active == [work()]


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
