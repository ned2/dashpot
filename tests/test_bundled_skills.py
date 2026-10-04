"""``dashpot integrate``: every bundled skill, installed, checked and removed.

Each harness's integration manages one copy of each skill Dashpot bundles,
and only a copy that carries that skill's own marker. A second bundled skill
is injected from a fixture directory, so behaviour across several skills is
exercised before Dashpot ships a second one.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from dashpot.core.model import Harness
from dashpot.sessions.integrate import (
    BUNDLED_SKILL_VERSION,
    BUNDLED_SKILLS,
    BUNDLED_SKILLS_ROOT,
    ISSUE_WORK_SKILL,
    OPENCODE_ACCEPTED_VERSION,
    BundledSkill,
    HarnessIntegration,
    IntegrationError,
    install_integration,
    integration,
    integration_status,
    remove_integration,
    skill_directory,
)

HARNESSES: tuple[Harness, ...] = ("codex", "claude-code", "opencode")


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep every harness's user directories inside the test's own directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    return home


@pytest.fixture
def second(tmp_path: Path) -> BundledSkill:
    """A second bundled skill, with a reference file two directories deep."""
    source = tmp_path / "bundled" / "fixture-second-skill"
    (source / "references" / "deep").mkdir(parents=True)
    skill = BundledSkill(
        name="fixture-second-skill", label="Second skill", source=source
    )
    (source / "SKILL.md").write_text(
        f"---\nname: {skill.name}\n---\n\n{skill.marker}\n\nThe second skill.\n"
    )
    (source / "references" / "deep" / "notes.md").write_text("Notes.\n")
    return skill


def config_home(harness: Harness) -> Path:
    """The harness's default configuration directory, created as its first run would."""
    spec = integration(harness)
    spec.default_home.mkdir(parents=True, exist_ok=True)
    return spec.default_home


def publisher(tmp_path: Path, spec: HarnessIntegration) -> Path:
    command = tmp_path / "bin" / spec.command_name
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


def accepted() -> str:
    return f"opencode v{OPENCODE_ACCEPTED_VERSION}"


def install(
    harness: Harness, tmp_path: Path, skills: tuple[BundledSkill, ...]
) -> list[str]:
    spec = integration(harness)
    return install_integration(
        harness,
        config_home(harness),
        command_path=publisher(tmp_path, spec),
        version_probe=accepted,
        skills=skills,
    )


def status(
    harness: Harness, tmp_path: Path, skills: tuple[BundledSkill, ...]
) -> list[str]:
    return integration_status(
        harness,
        config_home(harness),
        state_dir=tmp_path / "state",
        current=tmp_path,
        environ={},
        version_probe=accepted,
        skills=skills,
    )


def copy_of(harness: Harness, skill: BundledSkill) -> Path:
    return skill_directory(integration(harness), config_home(harness), skill)


def integration_file(harness: Harness) -> Path:
    spec = integration(harness)
    return spec.default_home / spec.hooks_file


@pytest.mark.parametrize("harness", HARNESSES)
def test_install_writes_every_bundled_skill_once(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    skills = (ISSUE_WORK_SKILL, second)

    messages = install(harness, tmp_path, skills)

    for skill in skills:
        copy = copy_of(harness, skill)
        assert f"installed Dashpot {skill.label} in {copy}" in messages
        for relative in skill.files:
            assert (copy / relative).read_bytes() == (
                skill.source / relative
            ).read_bytes()

    again = install(harness, tmp_path, skills)

    for skill in skills:
        assert (
            f"Dashpot {skill.label} already installed in {copy_of(harness, skill)}"
            in again
        )


def test_each_harness_installs_into_its_own_skill_directory(
    home: Path, second: BundledSkill
) -> None:
    assert copy_of("codex", second) == home / ".agents" / "skills" / second.name
    assert copy_of("claude-code", second) == home / ".claude" / "skills" / second.name
    assert copy_of("opencode", second) == (
        home / ".config" / "opencode" / "skills" / second.name
    )


@pytest.mark.parametrize("harness", HARNESSES)
def test_status_reports_each_skill_and_install_updates_only_the_stale_one(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    skills = (ISSUE_WORK_SKILL, second)
    install(harness, tmp_path, skills)
    first, other = copy_of(harness, ISSUE_WORK_SKILL), copy_of(harness, second)
    stale = other / "references" / "deep" / "notes.md"
    stale.write_text("Older notes.\n")

    report = status(harness, tmp_path, skills)

    assert (
        f"Issue work skill installed in {first} for Dashpot {BUNDLED_SKILL_VERSION}"
        in report
    )
    assert (
        f"Second skill update available at {other}; run "
        f"'dashpot integrate {harness}' to repair"
    ) in report

    messages = install(harness, tmp_path, skills)

    assert f"Dashpot Issue work skill already installed in {first}" in messages
    assert f"updated Dashpot Second skill in {other}" in messages
    assert stale.read_text() == "Notes.\n"
    assert f"Second skill installed in {other} for Dashpot " in "\n".join(
        status(harness, tmp_path, skills)
    )


@pytest.mark.parametrize("harness", HARNESSES)
def test_status_reports_a_missing_skill(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    install(harness, tmp_path, (ISSUE_WORK_SKILL,))

    report = status(harness, tmp_path, (ISSUE_WORK_SKILL, second))

    assert (
        f"Second skill not installed: no {copy_of(harness, second) / 'SKILL.md'}"
        in report
    )


@pytest.mark.parametrize("harness", HARNESSES)
def test_an_unmanaged_directory_of_a_bundled_skills_name_is_never_touched(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    skills = (ISSUE_WORK_SKILL, second)
    install(harness, tmp_path, (ISSUE_WORK_SKILL,))
    before = integration_file(harness).read_bytes()
    theirs = copy_of(harness, second)
    theirs.mkdir(parents=True)
    # Another bundled skill's marker does not make a copy this skill's.
    mine = f"---\nname: {second.name}\n---\n\n{ISSUE_WORK_SKILL.marker}\nMine.\n"
    (theirs / "SKILL.md").write_text(mine)

    with pytest.raises(IntegrationError) as refused:
        install(harness, tmp_path, skills)

    assert str(refused.value) == (
        f"cannot install the Dashpot Second skill at {theirs}: an existing skill "
        "is not managed by Dashpot; move it and retry"
    )
    assert integration_file(harness).read_bytes() == before
    assert (theirs / "SKILL.md").read_text() == mine
    assert not (theirs / "references").exists()
    assert f"Second skill conflict at {theirs}: not managed by Dashpot" in status(
        harness, tmp_path, skills
    )

    messages = remove_integration(harness, config_home(harness), skills=skills)

    assert f"left unmanaged Second skill unchanged at {theirs}" in messages
    assert (theirs / "SKILL.md").read_text() == mine
    assert not copy_of(harness, ISSUE_WORK_SKILL).exists()


def test_an_install_refusal_names_every_skill_it_cannot_manage(
    tmp_path: Path, second: BundledSkill
) -> None:
    first, other = copy_of("codex", ISSUE_WORK_SKILL), copy_of("codex", second)
    first.mkdir(parents=True)
    (first / "SKILL.md").write_text("Mine.\n")
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("a file, not a skill\n")

    with pytest.raises(IntegrationError) as refused:
        install("codex", tmp_path, (ISSUE_WORK_SKILL, second))

    assert str(refused.value) == (
        f"cannot install the Dashpot Issue work skill at {first}: an existing "
        "skill is not managed by Dashpot; move it and retry; "
        f"cannot install the Dashpot Second skill at {other}: the path is not a "
        "directory; move it and retry"
    )
    assert not integration_file("codex").exists()


@pytest.mark.parametrize("harness", HARNESSES)
@pytest.mark.parametrize("shape", ["directory without SKILL.md", "file"])
def test_a_path_that_is_no_dashpot_skill_is_a_conflict_left_in_place(
    harness: Harness, tmp_path: Path, second: BundledSkill, shape: str
) -> None:
    skills = (ISSUE_WORK_SKILL, second)
    install(harness, tmp_path, (ISSUE_WORK_SKILL,))
    theirs = copy_of(harness, second)
    if shape == "file":
        theirs.write_text("mine\n")
        kept = theirs
    else:
        theirs.mkdir()
        kept = theirs / "notes.md"
        kept.write_text("mine\n")

    with pytest.raises(IntegrationError):
        install(harness, tmp_path, skills)

    assert f"Second skill conflict at {theirs}: not managed by Dashpot" in status(
        harness, tmp_path, skills
    )
    messages = remove_integration(harness, config_home(harness), skills=skills)
    assert f"left unmanaged Second skill unchanged at {theirs}" in messages
    assert kept.read_text() == "mine\n"


@pytest.mark.parametrize("harness", HARNESSES)
def test_an_empty_directory_is_free_to_install_into(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    vacant = copy_of(harness, second)
    vacant.mkdir(parents=True)
    skills = (ISSUE_WORK_SKILL, second)

    assert f"Second skill not installed: no {vacant / 'SKILL.md'}" in status(
        harness, tmp_path, skills
    )
    assert (
        f"Dashpot Second skill is not installed: no {vacant / 'SKILL.md'}"
        in remove_integration(harness, config_home(harness), skills=skills)
    )
    install(harness, tmp_path, skills)
    assert (vacant / "SKILL.md").read_bytes() == (
        second.source / "SKILL.md"
    ).read_bytes()


@pytest.mark.parametrize("harness", HARNESSES)
def test_an_unreadable_skill_is_refused_reported_and_left_alone(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    skills = (ISSUE_WORK_SKILL, second)
    install(harness, tmp_path, (ISSUE_WORK_SKILL,))
    theirs = copy_of(harness, second)
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_bytes(b"\xff not a skill Dashpot wrote\n")

    with pytest.raises(IntegrationError, match="not managed by Dashpot"):
        install(harness, tmp_path, skills)

    assert any(
        message.startswith(f"Second skill unreadable at {theirs}: ")
        for message in status(harness, tmp_path, skills)
    )
    messages = remove_integration(harness, config_home(harness), skills=skills)
    assert any(
        message.startswith(f"could not inspect Dashpot Second skill at {theirs}: ")
        for message in messages
    )
    assert (theirs / "SKILL.md").read_bytes() == b"\xff not a skill Dashpot wrote\n"


@pytest.mark.parametrize("harness", HARNESSES)
def test_remove_takes_every_managed_skill_and_keeps_foreign_files(
    harness: Harness, tmp_path: Path, second: BundledSkill
) -> None:
    skills = (ISSUE_WORK_SKILL, second)
    install(harness, tmp_path, skills)
    other = copy_of(harness, second)
    foreign = other / "references" / "mine.md"
    foreign.write_text("keep me\n")

    messages = remove_integration(harness, config_home(harness), skills=skills)

    first = copy_of(harness, ISSUE_WORK_SKILL)
    assert f"removed the Dashpot Issue work skill from {first}" in messages
    assert f"removed the Dashpot Second skill from {other}" in messages
    assert not first.exists()
    assert foreign.read_text() == "keep me\n"
    assert not (other / "SKILL.md").exists()
    # The emptied nested directory goes; the one holding a foreign file stays.
    assert not (other / "references" / "deep").exists()

    again = remove_integration(harness, config_home(harness), skills=skills)

    assert (
        f"Dashpot Issue work skill is not installed: no {first / 'SKILL.md'}" in again
    )


@pytest.mark.parametrize("harness", HARNESSES)
def test_a_copy_installed_before_the_registry_is_recognised_and_updated(
    harness: Harness, tmp_path: Path
) -> None:
    # The marker every earlier Dashpot wrote into this skill; an installed
    # copy carrying it must stay Dashpot's to manage.
    assert ISSUE_WORK_SKILL.marker == (
        "<!-- dashpot-managed-skill: dashpot-issue-work -->"
    )
    earlier = copy_of(harness, ISSUE_WORK_SKILL)
    shutil.copytree(ISSUE_WORK_SKILL.source, earlier)
    (earlier / "SKILL.md").write_text(
        "---\nname: dashpot-issue-work\n---\n\n"
        "<!-- dashpot-managed-skill: dashpot-issue-work -->\n\n"
        "This skill is written for an earlier Dashpot.\n"
    )

    report = status(harness, tmp_path, (ISSUE_WORK_SKILL,))
    messages = install(harness, tmp_path, (ISSUE_WORK_SKILL,))

    assert (
        f"Issue work skill update available at {earlier}; run "
        f"'dashpot integrate {harness}' to repair"
    ) in report
    assert f"updated Dashpot Issue work skill in {earlier}" in messages
    assert (earlier / "SKILL.md").read_bytes() == (
        ISSUE_WORK_SKILL.source / "SKILL.md"
    ).read_bytes()


def test_opencode_reports_another_harness_copy_of_every_bundled_skill(
    tmp_path: Path, home: Path, second: BundledSkill
) -> None:
    skills = (ISSUE_WORK_SKILL, second)
    install("opencode", tmp_path, skills)
    install("claude-code", tmp_path, skills)
    install("codex", tmp_path, (ISSUE_WORK_SKILL,))
    claude_copy = home / ".claude" / "skills" / second.name
    (claude_copy / "references" / "deep" / "notes.md").write_text("Older notes.\n")
    codex_copy = home / ".agents" / "skills" / second.name
    codex_copy.mkdir(parents=True)
    (codex_copy / "SKILL.md").write_text(f"---\nname: {second.name}\n---\nMine.\n")

    warnings = [
        message
        for message in status("opencode", tmp_path, skills)
        if "also discovers" in message
    ]

    assert warnings == [
        f"warning: OpenCode also discovers the Second skill at {claude_copy}, "
        "which differs from this Dashpot's, and may use either; run 'dashpot "
        "integrate claude-code' or move it",
        f"warning: OpenCode also discovers the Second skill at {codex_copy}, "
        "which differs from this Dashpot's, and may use either; run 'dashpot "
        "integrate codex' or move it",
    ]


def test_opencode_install_reports_a_differing_copy_of_any_bundled_skill(
    tmp_path: Path, home: Path, second: BundledSkill
) -> None:
    claude_copy = home / ".claude" / "skills" / second.name
    claude_copy.mkdir(parents=True)
    (claude_copy / "SKILL.md").write_text(f"{second.marker}\n")

    messages = install("opencode", tmp_path, (ISSUE_WORK_SKILL, second))

    assert messages[-1] == (
        f"warning: OpenCode also discovers the Second skill at {claude_copy}, "
        "which differs from this Dashpot's, and may use either; run 'dashpot "
        "integrate claude-code' or move it"
    )


def test_every_bundled_skill_directory_is_registered_and_marked() -> None:
    names = [skill.name for skill in BUNDLED_SKILLS]
    assert len(set(names)) == len(names)
    assert sorted(names) == sorted(
        path.name for path in BUNDLED_SKILLS_ROOT.iterdir() if path.is_dir()
    )
    for skill in BUNDLED_SKILLS:
        assert skill.source == BUNDLED_SKILLS_ROOT / skill.name
        assert Path("SKILL.md") in skill.files
        text = (skill.source / "SKILL.md").read_text(encoding="utf-8")
        front = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
        assert front is not None, skill.name
        assert f"name: {skill.name}" in front.group(1).splitlines()
        assert skill.marker in text
