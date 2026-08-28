from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

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
        session_process=SessionProcess(42, "Tue Aug 25 01:00:00 2026"),
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
