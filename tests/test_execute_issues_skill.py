"""The bundled ``dashpot-execute-issues`` skill: installed, self-contained, user-invoked.

The skill ships to users' own repositories, so beyond being installed like
every bundled skill it must carry nothing of Dashpot's own repository, and
must stay hidden from the model in each harness until a person invokes it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dashpot.core.model import Harness
from dashpot.sessions.integrate import (
    BUNDLED_SKILLS,
    OPENCODE_ACCEPTED_VERSION,
    install_integration,
    integration,
    integration_status,
    remove_integration,
    skill_directory,
)

HARNESSES: tuple[Harness, ...] = ("codex", "claude-code", "opencode")

SKILL = next(
    skill for skill in BUNDLED_SKILLS if skill.name == "dashpot-execute-issues"
)

# What would tie the shipped text to Dashpot's own repository rather than to
# the user's: its address, its decision records and their numbers, its
# Issues, its document layout, and the commands only its contributors run.
REPOSITORY_SPECIFIC = {
    "the repository's address": re.compile(r"ned2/dashpot|github\.com/ned2"),
    "an ADR reference": re.compile(r"\bADRs?\b"),
    "a decision-record path": re.compile(r"docs/adr"),
    "an Issue or PR number": re.compile(r"#\d"),
    "a Dashpot document path": re.compile(
        r"docs/(?:spikes|proposals|agents)|\bdocs/[\w-]+\.md"
    ),
    "Dashpot's source tree": re.compile(r"src/dashpot|tests/test_"),
    "a Dashpot script": re.compile(
        r"scripts/|review_coverage|maintain_docs|check_quality|check_distributions"
    ),
    "Dashpot's toolchain": re.compile(r"\buv (?:run|sync)\b|--locked|\.venv\b"),
    "a skill integrate does not install": re.compile(r"\bcode-review\b"),
}


def shipped(relative: str | Path) -> str:
    """One shipped file's text, by its path inside the skill."""
    return (SKILL.source / relative).read_text(encoding="utf-8")


def shipped_texts() -> dict[Path, str]:
    return {relative: shipped(relative) for relative in SKILL.files}


def section(text: str, heading: str) -> str:
    """The body of one ``## `` section, with its line wrapping collapsed."""
    body = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return " ".join(body.split())


def frontmatter(text: str) -> str:
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    body = match.group(1)
    assert isinstance(body, str)
    return body


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


def installed(harness: Harness, tmp_path: Path) -> tuple[Path, list[str]]:
    """Install ``harness``'s integration; return the skill's copy and messages."""
    spec = integration(harness)
    spec.default_home.mkdir(parents=True, exist_ok=True)
    command = tmp_path / "bin" / spec.command_name
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    messages = install_integration(
        harness,
        spec.default_home,
        command_path=command,
        version_probe=lambda: f"opencode v{OPENCODE_ACCEPTED_VERSION}",
    )
    return skill_directory(spec, spec.default_home, SKILL), messages


@pytest.mark.parametrize("harness", HARNESSES)
def test_integrate_installs_checks_and_removes_the_skill(
    tmp_path: Path, harness: Harness
) -> None:
    copy, messages = installed(harness, tmp_path)

    assert f"installed Dashpot Issue arc skill in {copy}" in messages
    for relative in SKILL.files:
        assert (copy / relative).read_bytes() == (SKILL.source / relative).read_bytes()
    assert {
        Path("SKILL.md"),
        Path("agents/openai.yaml"),
        Path("references/brief-template.md"),
        Path("references/harnesses.md"),
        Path("references/reviewer.md"),
        Path("references/run-records.md"),
        Path("references/strategies.md"),
    } == set(SKILL.files)
    spec = integration(harness)
    report = integration_status(
        harness,
        spec.default_home,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environ={},
        version_probe=lambda: f"opencode v{OPENCODE_ACCEPTED_VERSION}",
    )
    assert any(
        line.startswith(f"Issue arc skill installed in {copy}") for line in report
    )

    removed = remove_integration(harness, spec.default_home)

    assert f"removed the Dashpot Issue arc skill from {copy}" in removed
    assert not copy.exists()


def test_the_marker_follows_the_frontmatter() -> None:
    text = shipped("SKILL.md")
    assert SKILL.marker == "<!-- dashpot-managed-skill: dashpot-execute-issues -->"
    assert text.index("\n---\n") < text.index(SKILL.marker)


def test_every_harness_hides_the_skill_from_the_model() -> None:
    text = shipped("SKILL.md")
    front = frontmatter(text).splitlines()

    # Claude Code's flag, and OpenCode's metadata, which Codex's and Claude
    # Code's frontmatter parsers both accept beside it.
    assert "name: dashpot-execute-issues" in front
    assert "disable-model-invocation: true" in front
    assert front[front.index("metadata:") + 1] == "  opencode/autoinvoke: false"
    description = next(line for line in front if line.startswith("description: "))
    assert len(description) - len("description: ") <= 1024
    assert "only when the user invokes it by name" in description
    # Codex reads its invocation policy from this file beside SKILL.md.
    assert shipped("agents/openai.yaml") == (
        "policy:\n  allow_implicit_invocation: false\n"
    )
    assert "Run this skill only when the user asked for it by name" in text


@pytest.mark.parametrize("label", sorted(REPOSITORY_SPECIFIC))
def test_the_shipped_skill_carries_nothing_of_dashpots_own_repository(
    label: str,
) -> None:
    pattern = REPOSITORY_SPECIFIC[label]
    found = [
        f"{relative}:{text.count(chr(10), 0, match.start()) + 1}: {match.group()}"
        for relative, text in shipped_texts().items()
        for match in pattern.finditer(text)
    ]
    assert not found, f"{label} in the shipped skill: {found}"


def test_the_repository_specific_patterns_catch_what_they_name() -> None:
    samples = {
        "the repository's address": "see https://github.com/ned2/dashpot/issues",
        "an ADR reference": "as ADR 0066 decides",
        "a decision-record path": "docs/adr/0089-leave-the-pr-merge.md",
        "an Issue or PR number": "filed as #427",
        "a Dashpot document path": "docs/agent-sessions.md",
        "Dashpot's source tree": "src/dashpot/sessions/integrate.py",
        "a Dashpot script": "python scripts/review_coverage.py",
        "Dashpot's toolchain": "uv run pre-commit run --all-files",
        "a skill integrate does not install": "run the `code-review` skill",
    }
    assert samples.keys() == REPOSITORY_SPECIFIC.keys()
    for label, sample in samples.items():
        assert REPOSITORY_SPECIFIC[label].search(sample), label


def test_every_link_in_the_skill_stays_inside_it() -> None:
    # The documentation gate resolves each link and anchor; this only keeps
    # every target inside the copy a harness installs.
    for relative, text in shipped_texts().items():
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            assert "://" not in target, (relative, target)
            resolved = (SKILL.source / relative).parent / target.partition("#")[0]
            assert resolved.resolve().is_relative_to(SKILL.source.resolve()), (
                relative,
                target,
            )


def test_the_only_skills_it_names_are_bundled() -> None:
    bundled = {skill.name for skill in BUNDLED_SKILLS}
    for relative, text in shipped_texts().items():
        for name in re.findall(r"`(dashpot-[\w-]+)`", text):
            assert name in bundled | {"dashpot-worker"}, (relative, name)


def test_the_lead_binds_through_the_issue_work_skill_before_any_worktree() -> None:
    text = shipped("SKILL.md")
    setup = section(text, "2. Set up")
    assert '`dashpot-issue-work`\'s "Establish the workflow"' in setup
    assert "Its version check confirms the installed skills" in setup
    assert "Do not enter an Issue Worktree yourself" in setup
    flowed = " ".join(text.split())
    assert flowed.index("Establish the workflow") < flowed.index(
        "<dashpot> worktree create <n> --json"
    )
    close_out = section(text, "5. Close out")
    assert close_out.index("Once no worker is live, remove the Worktrees") < (
        close_out.index('"Finish the engagement"')
    )
    assert "--dry-run" in close_out
    rules = section(text, "Rules for the whole arc")
    assert "Never move your own session to another Worktree while a worker runs" in (
        rules
    )
    assert "Keep no private notes file" in rules


def test_the_lead_merges_only_with_granted_authority() -> None:
    text = shipped("SKILL.md")
    authority = section(text, "Merge authority")
    assert "the user granted merge authority for this arc" in authority
    assert "the repository's instructions do not reserve merging for a person" in (
        authority
    )
    assert "Never enable auto-merge" in authority
    merge = section(text, "4. Handle each hand-back")
    assert "Read CI from `statusCheckRollup`, never from the worker's report" in merge
    assert "--match-head-commit <full headRefOid>" in merge
    assert "Without authority, tell the user it is ready" in merge


def test_each_known_dashpot_gap_is_named_for_removal() -> None:
    text = shipped("SKILL.md")
    gaps = section(text, "Known Dashpot gaps")
    # One entry per open Dashpot Issue, mapped in the skill's ADR; drop an
    # entry here and there when the installed Dashpot fixes its gap.
    assert re.findall(r"- \*\*(.+?)\*\*", gaps) == [
        "A relocated lead keeps a finished worker listed.",
        "A Codex worker's shell names no session.",
        "A stopped Claude Code worker's wording.",
        "An unloaded Codex lead drops its workers' blocker.",
    ]


def test_each_harness_has_its_mechanics_and_fallbacks() -> None:
    text = shipped("references/harnesses.md")
    headings = re.findall(r"^## (.+)$", text, re.M)
    assert headings == ["Claude Code", "Codex", "OpenCode"]

    claude = section(text, "Claude Code")
    assert "`run_in_background: true`" in claude
    assert "address the worker by that ID" in claude
    assert "`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`" in claude
    assert 'SendMessage with `to: "main"`' in claude
    assert "Avoid `TaskStop`" in claude
    assert '"Exit and stop tasks", or "Stay"' in claude

    codex = section(text, "Codex")
    assert "Run the lead on a multi-agent v2 model." in codex
    assert "Codex never starts a turn for an idle lead" in codex
    assert "Keep a client attached." in codex
    assert "3 open workers by default" in codex
    assert "`[agents] max_threads`" in codex
    assert "`wait_agent`" in codex and "`list_agents`" in codex
    assert "`followup_task`" in codex
    assert "**Fallback: v1.**" in codex
    assert "6 workers by default" in codex
    # Mail to a running worker is unmeasured, so broadcasts also go by file.
    assert "**Messaging a worker (v2).**" in codex
    assert codex.count("`execute-issues-lead`") == 4
    assert "allow_implicit_invocation: false" in codex

    opencode = section(text, "OpenCode")
    assert '`agent: "dashpot-worker"`' in opencode
    assert "`background: true`" in opencode
    assert (
        "If the agent is missing, ask the user to run `<dashpot> integrate opencode`"
        in (opencode)
    )
    assert "It does not stop a determined process" in opencode
    assert 'opencode run --session <lead-session-id> "<message>"' in opencode
    assert "A foreground shell times out after 2 minutes" in opencode
    flowed = " ".join(opencode.split())
    assert "rejects every permission ask the turn raises" in flowed
    assert "waits for its background shells before handing back" in flowed
    assert "an ask any worker raises is rejected too" in flowed
    assert "what that hour does to a background shell is unmeasured" in flowed
    assert "nesting depth defaults to 1" in opencode
    assert "`opencode/autoinvoke: false`" in opencode


def test_every_brief_placeholder_is_explained() -> None:
    text = shipped("references/brief-template.md")
    explained, template = text.split("## The template\n", 1)
    used = set(re.findall(r"\{([A-Z_]+)\}", template.split("## The wave block")[0]))
    assert used == set(re.findall(r"`\{([A-Z_]+)\}`", explained))
    assert {"GATES", "REVIEW", "REPORTING", "MERGER", "WAVE", "EXTRA"} <= used
    harnesses = shipped("references/harnesses.md")
    assert harnesses.count("`{REPORTING}`:") == 4


def test_the_bundled_reviewer_runs_without_the_repositorys_own_process() -> None:
    text = shipped("references/reviewer.md")
    flowed = " ".join(text.split())
    assert "only when the repository's instructions name no review process" in flowed
    assert "The reviewer must not be the agent that wrote the change" in flowed
    assert "**Spec.**" in text and "**Standards.**" in text
    assert "Read only." in text
    skill = shipped("SKILL.md")
    assert "[reviewer prompt](references/reviewer.md)" in skill


def test_run_records_go_to_github_comments() -> None:
    text = shipped("references/run-records.md")
    headings = re.findall(r"^## (.+)$", text, re.M)
    assert headings == [
        "The arc map",
        "A wave",
        "A merge",
        "A decision",
        "The close-out",
    ]
    flowed = " ".join(text.split())
    assert "not in a private notes file" in flowed
    assert "`gh issue comment <record-issue> --body-file <file>`" in flowed
    assert "Keep out of it local paths" in flowed
