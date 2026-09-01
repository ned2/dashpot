from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

import pytest

from dashpot.record_store import LockedRecordStore

KEY = re.compile(r"^[A-Za-z0-9._-]+$")


def store_at(directory: Path) -> LockedRecordStore:
    return LockedRecordStore(
        directory, KEY, "record key contains unsupported characters"
    )


def write(store: LockedRecordStore, key: str, record: dict[str, object]) -> None:
    with store.locked(key):
        store.replace(key, record)


def test_a_replaced_record_survives_a_reread(tmp_path: Path) -> None:
    store = store_at(tmp_path)

    write(store, "one", {"value": 1})
    write(store, "one", {"value": 2})

    text = store.record_path("one").read_text()
    assert text.endswith("\n")
    assert json.loads(text) == {"value": 2}


def test_unsafe_keys_are_refused_before_any_write(tmp_path: Path) -> None:
    store = store_at(tmp_path)

    with pytest.raises(RuntimeError, match="record key"):
        store.record_path("../escape")

    assert not (tmp_path.parent / "escape.json").exists()


def test_concurrent_writers_never_partially_write_a_record(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    barrier = threading.Barrier(8)
    failures: list[Exception] = []
    observed: list[dict[str, object]] = []

    # Every writer hammers the one shared key, so the lock is contended and
    # each writer also proves every state it reads back is a complete record.
    def writer(index: int) -> None:
        barrier.wait()
        try:
            for turn in range(5):
                write(store, "shared", {"turn": turn, "index": index})
                observed.append(json.loads(store.record_path("shared").read_text()))
        except Exception as exc:  # pragma: no cover - asserted below.
            failures.append(exc)

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    assert len(observed) == 40
    assert all(set(record) == {"turn", "index"} for record in observed)
    final = json.loads(store.record_path("shared").read_text())
    assert final["turn"] == 4


def test_orphaned_lock_files_are_reclaimed_and_live_ones_kept(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    write(store, "kept", {"value": 1})
    (tmp_path / ".orphaned.lock").touch()
    (tmp_path / ".not a key.lock").touch()

    assert store.orphaned_locks() == ["orphaned"]
    assert store.prune_lock("orphaned") is True
    assert store.prune_lock("kept") is False

    assert not (tmp_path / ".orphaned.lock").exists()
    assert (tmp_path / ".kept.lock").exists()
    assert (tmp_path / ".not a key.lock").exists()


def test_sweep_removes_only_aged_crash_leftover_temporaries(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    write(store, "kept", {"value": 1})
    aged = time.time() - 7200
    crashed = tmp_path / ".kept.a1b2c3d4"
    crashed.touch()
    os.utime(crashed, (aged, aged))
    fresh = tmp_path / ".kept.e5f6a7b8"
    fresh.touch()
    foreign = tmp_path / ".gitignore"
    foreign.touch()
    os.utime(foreign, (aged, aged))
    os.utime(tmp_path / ".kept.lock", (aged, aged))

    assert store.sweep_temporaries() == 1

    assert not crashed.exists()
    assert fresh.exists()
    assert foreign.exists()
    assert (tmp_path / ".kept.lock").exists()
    assert (tmp_path / "kept.json").exists()


def test_sweeping_a_missing_directory_removes_nothing(tmp_path: Path) -> None:
    store = store_at(tmp_path / "absent")

    assert store.sweep_temporaries() == 0
