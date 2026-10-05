"""Install, update, remove and report each harness's managed copy of a bundled skill.

A copy is a directory whose ``SKILL.md`` carries the skill's marker, and
whose manifest names every file Dashpot wrote there (ADR 0103).
"""

from __future__ import annotations

import contextlib
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from ...core.model import Harness
from ...core.pydantic import PersistedRecord, RepositoryRelativePath
from ...core.record_store import replace_atomically
from .registry import (
    BUNDLED_SKILL_VERSION,
    BundledSkill,
    HarnessIntegration,
    configuration_directory,
    user_skills_directory,
)
from .writes import IntegrationError, PendingWrite, Planned, file_mode

# Written beside the marker in every managed skill copy, it names each file
# Dashpot wrote there, so a later Dashpot can tell a file an earlier one
# shipped from one the user added (ADR 0103).
SKILL_MANIFEST = Path(".dashpot-manifest.json")
# The file that carries a skill, and in a managed copy its marker.
SKILL_FILE = Path("SKILL.md")


class SkillManifest(PersistedRecord):
    """The files Dashpot wrote into one managed skill copy, relative to it."""

    # A copy's files obey the Repository-relative rule: a POSIX path that
    # stays inside the directory it is relative to, here the copy itself.
    files: tuple[RepositoryRelativePath, ...]


# What a skill's destination holds, judged by its marker before any listing.
CopyState = Literal["vacant", "managed", "unmanaged", "not a directory"]


def skill_directory(
    spec: HarnessIntegration,
    home: Path,
    skill: BundledSkill,
    environ: Mapping[str, str],
) -> Path:
    """Locate this harness's user-wide copy of one bundled skill.

    A harness that reads skills outside its configuration directory, as
    Codex does, reads them from the home directory's when ``home`` is the
    directory ``environ`` names, and beside ``home`` otherwise.
    """
    if spec.skills_in_configuration:
        return home / spec.skills_home / skill.name
    if home == configuration_directory(spec, environ).path:
        return user_skills_directory(spec, environ) / skill.name
    return home.parent / spec.skills_home / skill.name


def skill_copies(
    spec: HarnessIntegration,
    home: Path,
    skills: tuple[BundledSkill, ...],
    environ: Mapping[str, str],
) -> list[tuple[BundledSkill, Path]]:
    """Each bundled skill, paired with where this harness keeps its copy."""
    return [(skill, skill_directory(spec, home, skill, environ)) for skill in skills]


def _skill_text(destination: Path) -> str:
    """An installed copy's ``SKILL.md``; raises ``OSError`` or ``ValueError``."""
    return (destination / SKILL_FILE).read_text(encoding="utf-8")


def is_managed(skill: BundledSkill, destination: Path) -> bool:
    """Whether a copy's ``SKILL.md`` is readable and carries this skill's marker."""
    try:
        return _copy_state(skill, destination) == "managed"
    except (OSError, ValueError):
        return False


def _copy_state(skill: BundledSkill, destination: Path) -> CopyState:
    """What holds a bundled skill's destination.

    ``SKILL.md`` is read before the directory is listed, so a copy that can
    be entered but not listed is still recognised by its marker; only a
    directory without one is listed, to tell an empty directory from
    someone else's. Raises ``OSError`` when the destination cannot be
    inspected, and ``ValueError`` when its ``SKILL.md`` is not text.
    """
    mode = file_mode(destination)
    if mode is None:
        return "vacant"
    if not stat.S_ISDIR(mode):
        return "not a directory"
    skill_mode = file_mode(destination / SKILL_FILE)
    if skill_mode is not None and stat.S_ISREG(skill_mode):
        return "managed" if skill.marker in _skill_text(destination) else "unmanaged"
    return "unmanaged" if any(destination.iterdir()) else "vacant"


def _recorded_files(destination: Path) -> frozenset[Path] | None:
    """The files a copy's manifest names, or ``None`` when it has no valid one."""
    try:
        manifest = SkillManifest.model_validate_json(
            (destination / SKILL_MANIFEST).read_bytes()
        )
    except (OSError, ValidationError):
        return None
    return frozenset(Path(relative) for relative in manifest.files)


def _written_files(skill: BundledSkill, destination: Path) -> frozenset[Path]:
    """Every file Dashpot wrote into a managed copy.

    A copy without a valid manifest was written by a revision from before
    Dashpot kept one, and every file those revisions shipped is still
    shipped, so the files this Dashpot ships stand in for its list
    (ADR 0103).
    """
    recorded = _recorded_files(destination)
    return frozenset(skill.files) if recorded is None else recorded


def is_current(skill: BundledSkill, destination: Path) -> bool:
    """Whether a copy holds every file this Dashpot ships, unchanged, and no other of Dashpot's.

    Its manifest must name exactly the shipped files: a file it names beyond
    them is one an earlier Dashpot shipped and an update removes. Files the
    user added are not Dashpot's, and leave the copy current.
    """
    try:
        return _recorded_files(destination) == frozenset(skill.files) and all(
            (destination / relative).is_file()
            and (destination / relative).read_bytes()
            == (skill.source / relative).read_bytes()
            for relative in skill.files
        )
    except OSError:
        return False


def skill_has_update(skill: BundledSkill, destination: Path) -> bool:
    """Whether refreshing would write a copy: one behind, or one this release adds.

    A copy held by what Dashpot does not manage does not count, since
    refreshing refuses it.
    """
    try:
        state = _copy_state(skill, destination)
    except (OSError, ValueError):
        return False
    return state in ("vacant", "managed") and not is_current(skill, destination)


def skill_refusal(skill: BundledSkill, destination: Path) -> str | None:
    """Why a copy's destination holds what Dashpot does not manage; ``None`` when free.

    An empty or absent skill directory is free to install into; any other
    directory must already carry that skill's own marker, and one that
    cannot be inspected is refused.
    """
    refused = f"cannot install the Dashpot {skill.label} at {destination}: "
    try:
        state = _copy_state(skill, destination)
    except OSError as exc:
        return f"{refused}could not inspect it: {exc}; move it and retry"
    except ValueError:
        state = "unmanaged"
    if state == "not a directory":
        return f"{refused}the path is not a directory; move it and retry"
    if state == "unmanaged":
        return (
            f"{refused}an existing skill is not managed by Dashpot; move it and retry"
        )
    return None


def _write_manifest(destination: Path, files: frozenset[Path]) -> None:
    """Record which files Dashpot wrote into a managed copy.

    The manifest is rewritten whole: anything a newer Dashpot recorded in it
    described the copy this one has just rewritten.
    """
    manifest = SkillManifest(files=tuple(path.as_posix() for path in sorted(files)))
    replace_atomically(
        destination / SKILL_MANIFEST,
        manifest.model_dump_json(by_alias=True, indent=2) + "\n",
        temporary_prefix=f".{SKILL_MANIFEST.name}.",
    )


def _remove_files(destination: Path, files: Sequence[Path]) -> None:
    """Unlink each named file of a copy, in order, then the directories they emptied.

    Only the directories holding a named file are pruned, deepest first, and
    only once empty: anything else in them is the user's. A name whose
    directory resolves outside the copy, through a symbolic link the user
    put there, is never followed.
    """
    root = destination.resolve()
    for relative in files:
        path = destination / relative
        if _resolves_inside(path, root) and path.is_file():
            path.unlink()
    nested = {
        ancestor
        for relative in files
        for ancestor in relative.parents
        if ancestor != Path(".")
    }
    for relative in sorted(nested, key=lambda path: len(path.parts), reverse=True):
        # Removing rather than listing first keeps a directory that cannot be
        # listed prunable; one still holding the user's files refuses.
        directory = destination / relative
        if _resolves_inside(directory, root):
            with contextlib.suppress(OSError):
                directory.rmdir()


def plan_skill(skill: BundledSkill, destination: Path) -> Planned:
    """The pending write of one skill's copy, unless it is current."""
    if is_current(skill, destination):
        return f"Dashpot {skill.label} already installed in {destination}"
    # An empty directory, as a first installation cut short leaves, is
    # installed into, not updated.
    existed = is_managed(skill, destination)

    def write() -> str:
        try:
            _write_skill(skill, destination, managed=existed)
        except OSError as exc:
            action = "update" if existed else "install"
            raise IntegrationError(
                f"could not {action} the Dashpot {skill.label} in {destination}: {exc}"
            ) from exc
        verb = "updated" if existed else "installed"
        return f"{verb} Dashpot {skill.label} in {destination}"

    return PendingWrite(
        subject=f"the Dashpot {skill.label} at {destination}",
        directories=_skill_write_directories(skill, destination, managed=existed),
        perform=write,
        blocked=_skill_write_outside(skill, destination),
    )


def _skill_write_directories(
    skill: BundledSkill, destination: Path, *, managed: bool
) -> tuple[Path, ...]:
    """Every directory an update of a copy writes a file in or removes one from.

    The copy itself holds its manifest. A file an earlier Dashpot wrote that
    this one no longer ships is removed only where its directory resolves
    inside the copy, so only there is its directory checked.
    """
    shipped = frozenset(skill.files)
    directories = {destination, *((destination / path).parent for path in shipped)}
    if managed:
        root = destination.resolve()
        for relative in _written_files(skill, destination) - shipped:
            if _resolves_inside(destination / relative, root):
                directories.add((destination / relative).parent)
    return tuple(sorted(directories))


def _skill_write_outside(skill: BundledSkill, destination: Path) -> str | None:
    """Why writing a copy would leave it, through a link the user put inside it.

    A shipped file whose directory resolves outside the copy would be
    written wherever the link leads, which removal never follows, so the
    write is refused as removal is (ADR 0130); ``None`` when every shipped
    file's directory resolves inside the copy.
    """
    root = destination.resolve()
    outside = sorted(
        {
            (destination / relative).parent
            for relative in skill.files
            if not _resolves_inside(destination / relative, root)
        }
    )
    if not outside:
        return None
    return (
        f"{', '.join(map(str, outside))} resolves outside the copy through a "
        "link; move it and retry"
    )


def _resolves_inside(path: Path, root: Path) -> bool:
    """Whether the directory holding ``path`` resolves inside the resolved ``root``."""
    # A link loop is never followed: Python 3.12 raises ``RuntimeError``
    # for one where later releases leave the path unresolved.
    try:
        return path.parent.resolve().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _write_skill(skill: BundledSkill, destination: Path, *, managed: bool) -> None:
    """Leave a managed copy holding exactly the shipped files, beside the user's own.

    ``SKILL.md`` is written first, so a first installation cut short before
    it leaves a directory free to install into again. An update cut short
    leaves every file Dashpot wrote named by the manifest, for the next
    update or ``--remove`` to finish.
    """
    shipped = frozenset(skill.files)
    recorded = _recorded_files(destination) if managed else None
    earlier = frozenset[Path]()
    if managed:
        earlier = shipped if recorded is None else recorded
    destination.mkdir(parents=True, exist_ok=True)
    # Without a manifest the shipped files already stand in for one, so only
    # a manifest that names fewer files than will be written is widened first.
    if recorded is not None and recorded != earlier | shipped:
        _write_manifest(destination, earlier | shipped)
    for relative in sorted(skill.files, key=lambda path: path != SKILL_FILE):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_atomically(
            target,
            (skill.source / relative).read_text(encoding="utf-8"),
            temporary_prefix=f".{target.name}.",
        )
    _remove_files(destination, sorted(earlier - shipped))
    _write_manifest(destination, shipped)


def remove_skill(skill: BundledSkill, destination: Path) -> str:
    """Remove a managed copy's files, leaving the user's own and any copy not Dashpot's.

    Raises ``IntegrationError`` when a file of Dashpot's cannot be removed.
    """
    try:
        state = _copy_state(skill, destination)
    except (OSError, ValueError) as exc:
        return f"could not inspect Dashpot {skill.label} at {destination}: {exc}"
    if state == "vacant":
        return f"Dashpot {skill.label} is not installed: no {destination / SKILL_FILE}"
    if state != "managed":
        return f"left unmanaged {skill.label} unchanged at {destination}"
    # SKILL.md, which carries the marker, goes last, after the manifest, so
    # a removal cut short leaves a copy the next ``--remove`` still
    # recognises and finishes.
    written = sorted(_written_files(skill, destination) - {SKILL_FILE, SKILL_MANIFEST})
    try:
        _remove_files(destination, [*written, SKILL_MANIFEST, SKILL_FILE])
    except OSError as exc:
        raise IntegrationError(
            f"could not remove Dashpot {skill.label} from {destination}: {exc}"
        ) from exc
    # The copy stays while it still holds the user's files.
    with contextlib.suppress(OSError):
        destination.rmdir()
    return f"removed the Dashpot {skill.label} from {destination}"


def skill_status(skill: BundledSkill, destination: Path, *, harness: Harness) -> str:
    """Report whether a copy is installed, current, or held by what is not Dashpot's."""
    try:
        state = _copy_state(skill, destination)
    except (OSError, ValueError) as exc:
        return f"{skill.label} unreadable at {destination}: {exc}"
    if state == "vacant":
        return f"{skill.label} not installed: no {destination / SKILL_FILE}"
    if state != "managed":
        return f"{skill.label} conflict at {destination}: not managed by Dashpot"
    if not is_current(skill, destination):
        return (
            f"{skill.label} update available at {destination}; run "
            f"'dashpot integrate {harness}' to repair"
        )
    return (
        f"{skill.label} installed in {destination} for Dashpot {BUNDLED_SKILL_VERSION}"
    )
