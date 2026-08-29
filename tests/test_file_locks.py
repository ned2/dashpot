from __future__ import annotations

import threading
from pathlib import Path

from dashpot.file_locks import locked_path, prune_lock_file


def test_lock_file_is_created_and_kept_by_the_holder(tmp_path: Path) -> None:
    lock = tmp_path / ".session.lock"

    with locked_path(lock):
        assert lock.exists()

    assert lock.exists()


def test_prune_keeps_the_lock_while_its_record_exists(tmp_path: Path) -> None:
    lock = tmp_path / ".session.lock"
    record = tmp_path / "session.json"
    record.write_text("{}")

    assert prune_lock_file(lock, record) is False
    assert lock.exists()

    record.unlink()
    assert prune_lock_file(lock, record) is True
    assert not lock.exists()


def test_exclusion_survives_concurrent_pruning(tmp_path: Path) -> None:
    lock = tmp_path / ".session.lock"
    record = tmp_path / "session.json"
    started = threading.Barrier(9)
    stop_pruning = threading.Event()
    inside = threading.Lock()
    overlaps: list[str] = []
    failures: list[Exception] = []

    def worker(index: int) -> None:
        started.wait()
        try:
            for _turn in range(200):
                with locked_path(lock):
                    if not inside.acquire(blocking=False):
                        overlaps.append(f"worker {index}")
                        continue
                    try:
                        assert lock.exists()
                    finally:
                        inside.release()
        except Exception as exc:  # pragma: no cover - asserted below.
            failures.append(exc)

    def pruner() -> None:
        started.wait()
        try:
            while not stop_pruning.is_set():
                prune_lock_file(lock, record)
        except Exception as exc:  # pragma: no cover - asserted below.
            failures.append(exc)

    workers = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    sweeper = threading.Thread(target=pruner)
    for thread in [*workers, sweeper]:
        thread.start()
    for thread in workers:
        thread.join()
    stop_pruning.set()
    sweeper.join()

    assert failures == []
    assert overlaps == []
