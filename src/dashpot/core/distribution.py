"""Describe the running Dashpot: its version, how it was installed, and its commit.

Every hook process records these in ``process.start``, so they are read from
the installed distribution's own files and the source checkout's Git files,
without ``importlib.metadata`` (about 21 ms to import) or a ``git`` process.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from .commands import CommandError, run_command
from .runtime_events import InstallKind, ProcessStart

DISTRIBUTION = "dashpot"
UNKNOWN = "unknown"
_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True, slots=True)
class DistributionFacts:
    """What the running Dashpot is, and the source checkout it runs from, if any."""

    version: str = UNKNOWN
    install_kind: InstallKind = UNKNOWN
    revision: str = UNKNOWN
    source: Path | None = None


def installed_distribution(search: list[str] | None = None) -> Path | None:
    """The ``dist-info`` directory of the running Dashpot, as the import system finds it.

    The directory beside the imported package is tried first, which is where
    a wheel installs it; an editable install keeps it in site-packages while
    the package is imported from its source, so every ``sys.path`` entry is
    searched after that, in order, as ``importlib.metadata`` would.
    """
    package_parent = str(Path(__file__).resolve().parents[2])
    for entry in [package_parent, *(sys.path if search is None else search)]:
        try:
            candidates = sorted(Path(entry or ".").glob(f"{DISTRIBUTION}-*.dist-info"))
        except OSError:
            continue
        for candidate in candidates:
            if (candidate / "METADATA").is_file():
                return candidate
    return None


def describe_distribution(dist_info: Path | None) -> DistributionFacts:
    """Read the version, install kind and source commit of one installed Dashpot.

    The install kind follows PEP 610's ``direct_url.json``: none is a wheel
    from an index, ``dir_info`` is ``editable`` or a ``directory``, and
    ``archive_info`` and ``vcs_info`` name themselves. A VCS install records
    the commit it was built from; a directory install is read from its
    checkout's Git files; anything else has no commit to report.
    """
    if dist_info is None:
        return DistributionFacts()
    version = _metadata_version(dist_info / "METADATA")
    try:
        direct: object = json.loads((dist_info / "direct_url.json").read_text())
    except FileNotFoundError:
        return DistributionFacts(version=version, install_kind="wheel")
    except (OSError, ValueError):
        return DistributionFacts(version=version)
    if not isinstance(direct, dict):
        return DistributionFacts(version=version)
    if isinstance(vcs := direct.get("vcs_info"), dict):
        commit = vcs.get("commit_id")
        revision = (
            commit if isinstance(commit, str) and _OBJECT_ID.match(commit) else UNKNOWN
        )
        return DistributionFacts(version=version, install_kind="vcs", revision=revision)
    if isinstance(direct.get("archive_info"), dict):
        return DistributionFacts(version=version, install_kind="archive")
    if isinstance(info := direct.get("dir_info"), dict):
        kind: InstallKind = "editable" if info.get("editable") is True else "directory"
        source = _file_url_path(direct.get("url"))
        return DistributionFacts(
            version=version,
            install_kind=kind,
            revision=source_revision(source) if source is not None else UNKNOWN,
            source=source,
        )
    return DistributionFacts(version=version)


def running_distribution() -> DistributionFacts:
    """Describe the Dashpot this process is running."""
    return describe_distribution(installed_distribution())


def _metadata_version(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    break
                if line.startswith("Version:"):
                    return line.removeprefix("Version:").strip() or UNKNOWN
    except (OSError, UnicodeDecodeError):
        pass
    return UNKNOWN


def _file_url_path(url: object) -> Path | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def source_revision(checkout: Path) -> str:
    """The commit a source checkout's ``HEAD`` names, read from its Git files.

    A linked Worktree's ``.git`` file names its private directory, whose
    ``commondir`` names the shared one; ``HEAD`` is read there, then the
    loose ref it names, then ``packed-refs``. Anything else — a reftable
    Repository among them — is ``unknown`` rather than a started ``git``.
    """
    try:
        git_dir = _git_directory(checkout)
        if git_dir is None:
            return UNKNOWN
        common = git_dir
        commondir = git_dir / "commondir"
        if commondir.is_file():
            common = (git_dir / commondir.read_text().strip()).resolve()
        head = (git_dir / "HEAD").read_text().strip()
        if _OBJECT_ID.match(head):
            return head
        if not head.startswith("ref: "):
            return UNKNOWN
        ref = head.removeprefix("ref: ").strip()
        for directory in (git_dir, common):
            loose = directory / ref
            if loose.is_file():
                value = loose.read_text().strip()
                return value if _OBJECT_ID.match(value) else UNKNOWN
        return _packed_ref(common / "packed-refs", ref)
    except (OSError, UnicodeDecodeError):
        return UNKNOWN


def _git_directory(checkout: Path) -> Path | None:
    dot_git = checkout / ".git"
    if dot_git.is_dir():
        return dot_git
    if not dot_git.is_file():
        return None
    pointer = dot_git.read_text().strip()
    if not pointer.startswith("gitdir: "):
        return None
    return (checkout / pointer.removeprefix("gitdir: ").strip()).resolve()


def _packed_ref(path: Path, ref: str) -> str:
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        return UNKNOWN
    for line in lines:
        value, _, name = line.partition(" ")
        if name == ref and _OBJECT_ID.match(value):
            return value
    return UNKNOWN


def source_dirty(checkout: Path, *, timeout: float = 2.0) -> bool | None:
    """Whether a source checkout has uncommitted changes, from one ``git status``.

    Only a dashboard asks, once at its start; ``None`` when Git cannot say.
    """
    try:
        result = run_command(
            ["git", "status", "--porcelain"], checkout, timeout, interruptible=False
        )
    except (CommandError, OSError):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def process_start(
    working_directory: Path | None,
    *,
    subcommand: str | None = None,
    check_source: bool = False,
) -> ProcessStart:
    """Describe this process for ``process.start``.

    ``check_source`` adds whether Dashpot's own source has uncommitted
    changes, from one ``git status``; only a dashboard asks. Facts that do
    not fit their fields are recorded as unknown rather than failing the
    process.
    """
    distribution = running_distribution()
    dirty = (
        source_dirty(distribution.source)
        if check_source and distribution.source is not None
        else None
    )
    facts: dict[str, object] = {
        "version": distribution.version,
        "install_kind": distribution.install_kind,
        "revision": distribution.revision,
        "source_dirty": dirty,
        "pid": os.getpid(),
        "python_version": platform.python_version(),
        "working_directory": None
        if working_directory is None
        else str(working_directory),
        "subcommand": subcommand,
    }
    try:
        return ProcessStart.model_validate(facts)
    except ValidationError:
        return ProcessStart.model_validate(
            {
                **facts,
                "version": UNKNOWN,
                "python_version": UNKNOWN,
                "working_directory": None,
                "subcommand": None,
            }
        )
