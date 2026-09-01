"""One locked, atomic JSON record store beneath the hook and Work stores."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .file_locks import locked_path, prune_lock_file

# A writer's temporary file lives for milliseconds between creation and
# rename; one this old was left behind by a crash and will never be renamed
# into place.
TEMPORARY_MAX_AGE_SECONDS = 3600.0


class LockedRecordStore:
    """Keep keyed JSON records in one directory, replaced atomically under a lock.

    Each key owns a ``<key>.json`` record and a ``.<key>.lock`` file; writers
    replace records durably via a same-directory temporary file, and sweeps
    reclaim locks that guard no record and temporaries a crash left behind.
    """

    def __init__(
        self, directory: Path, key_pattern: re.Pattern[str], key_error: str
    ) -> None:
        self.directory = directory
        self._key_pattern = key_pattern
        self._key_error = key_error

    def record_path(self, key: str) -> Path:
        """The key's record path, refusing keys that could escape the store."""
        if not self._key_pattern.fullmatch(key):
            raise RuntimeError(self._key_error)
        return self.directory / f"{key}.json"

    def lock_path(self, key: str) -> Path:
        """The lock file that serializes writers of the key's record."""
        return self.directory / f".{key}.lock"

    @contextmanager
    def locked(self, key: str) -> Iterator[None]:
        """Hold the key's lock, creating the store directory when absent."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with locked_path(self.lock_path(key)):
            yield

    def replace(self, key: str, record: dict[str, Any]) -> None:
        """Replace the key's record atomically and durably."""
        destination = self.record_path(key)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{key}.", dir=self.directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(record, stream, indent=2)
                stream.write("\n")
                # Flush to disk before the rename, so a crash never leaves the
                # destination pointing at a partially persisted record.
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            # The rename itself must also survive a crash, which takes an
            # fsync of the directory entry, not just the file's contents.
            directory_descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if temporary.exists():
                temporary.unlink()

    def prune_lock(self, key: str) -> bool:
        """Delete the key's lock file once no record remains behind it."""
        return prune_lock_file(self.lock_path(key), self.record_path(key))

    def orphaned_locks(self) -> list[str]:
        """Keys of lock files in this store that guard no record."""
        if not self.directory.is_dir():
            return []
        orphaned: list[str] = []
        for path in sorted(self.directory.glob(".*.lock")):
            key = path.name[1 : -len(".lock")]
            if not self._key_pattern.fullmatch(key):
                continue
            if not self.record_path(key).exists():
                orphaned.append(key)
        return orphaned

    def sweep_temporaries(self, max_age: float = TEMPORARY_MAX_AGE_SECONDS) -> int:
        """Remove crash-leftover temporaries no writer will rename into place.

        A live writer's temporary is younger than ``max_age``; a lock file, a
        record, or a name no key of this store could have produced is not a
        temporary and is left alone. Returns how many files were removed.
        """
        if not self.directory.is_dir():
            return 0
        removed = 0
        now = time.time()
        for path in sorted(self.directory.glob(".*")):
            # A record's ``.json`` suffix can never be a mkstemp suffix, so a
            # record for a leading-dot key is never mistaken for a temporary.
            if (
                path.name.endswith(".lock")
                or path.name.endswith(".json")
                or not path.is_file()
            ):
                continue
            # ``mkstemp(prefix=f".{key}.")`` names are ``.<key>.<random>``.
            key, separator, _suffix = path.name[1:].rpartition(".")
            if not separator or not self._key_pattern.fullmatch(key):
                continue
            with contextlib.suppress(OSError):
                if now - path.stat().st_mtime >= max_age:
                    path.unlink()
                    removed += 1
        return removed
