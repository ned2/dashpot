"""The bundled ``dashpot-execute-issues`` skill: installed, self-contained, user-invoked.

The skill ships to users' own repositories, so beyond being installed like
every bundled skill it must carry nothing of Dashpot's own repository, and
must stay hidden from the model in each harness until a person invokes it.
"""

from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

import pytest

from dashpot.core.model import Harness
from dashpot.sessions.harnesses import OPENCODE_ACCEPTED_VERSION
from dashpot.sessions.integrate import (
    BUNDLED_SKILLS,
    IntegrationEnvironment,
    configuration_directory,
    install_integration,
    integration,
    integration_status,
    remove_integration,
    skill_directory,
)

HARNESSES: tuple[Harness, ...] = ("codex", "claude-code", "opencode")
ACCEPTED = IntegrationEnvironment(
    version_probe=lambda: f"opencode v{OPENCODE_ACCEPTED_VERSION}"
)

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
    home = configuration_directory(spec, os.environ).path
    home.mkdir(parents=True, exist_ok=True)
    command = tmp_path / "bin" / spec.command_name
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    messages = install_integration(
        harness, home, command_path=command, environment=ACCEPTED
    )
    return skill_directory(spec, home, SKILL, os.environ), messages


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
    home = configuration_directory(integration(harness), os.environ).path
    report = integration_status(
        harness,
        home,
        state_dir=tmp_path / "state",
        current=tmp_path,
        environment=dataclasses.replace(ACCEPTED, environ={}),
    )
    assert any(
        line.startswith(f"Issue arc skill installed in {copy}") for line in report
    )

    removed = remove_integration(harness, home)

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
        "<dashpot> worktree create <n> --base"
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
    # The sub-agent override is the user's assertion alone (ADR 0112).
    override = " ".join(rules.split())
    assert "**Leave the sub-agent override to the user.**" in override
    assert "offers `--despite-subagents` with your workers' IDs" in override
    assert "Never pass it yourself, and never brief a worker to." in override


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


def test_a_maintainers_instruction_is_checked_before_it_is_briefed() -> None:
    mapping = section(shipped("SKILL.md"), "1. Map the arc")
    assert (
        "Before you restate one in a brief, check it against both. Where they "
        "conflict, brief the intent and the conflict, and record on the Issue "
        "which one you chose."
    ) in mapping


def test_the_lead_finds_every_other_open_arc_by_its_opening_line() -> None:
    mapping = section(shipped("SKILL.md"), "1. Map the arc")
    search = re.search(
        r"`gh issue list --state open --search '\"(.+?)\" in:body'`", mapping
    )
    assert search is not None
    records = shipped("references/run-records.md")
    opening = re.search(r"```markdown\n(Tracking Issue for a .+?)\n```", records)
    assert opening is not None
    # GitHub's search ignores the backticks the opening line carries.
    assert opening.group(1).replace("`", "").startswith(search.group(1))
    flowed_records = " ".join(records.split())
    assert "For an epic, add it at the top of the epic's body" in flowed_records
    assert "The record Issue's body opens with this line" in flowed_records
    assert (
        "note the files its collision plan owns, the numbers it reserved, "
        "and its share of the machine's cores"
    ) in mapping
    assert (
        "settle its ownership with the other arc's lead through the user, or sequence"
        in mapping
    )
    dispatch = section(shipped("SKILL.md"), "3. Dispatch a wave")
    assert "A file another open arc owns stays with it" in dispatch


def test_reservations_and_cores_are_shared_with_every_live_arc() -> None:
    setup = section(shipped("SKILL.md"), "2. Set up")
    assert "and the reservations of every other open arc" in setup
    assert (
        "A clash found before dispatch: the arc whose arc map posted later "
        "takes the next free numbers. A clash found after dispatch: the arc "
        "that dispatched the number later renumbers, and its lead broadcasts "
        "the new number to its workers."
    ) in setup
    assert "Divide the machine's cores between every live arc, yours included" in setup
    assert "record yours in the arc map" in setup
    assert "who asks the other lead to shrink its share" in setup
    assert "create the first Worktree: until it is posted" in setup
    dispatch = section(shipped("SKILL.md"), "3. Dispatch a wave")
    assert "re-split the cores between the live arcs" in dispatch
    arc_map = section(shipped("references/run-records.md"), "The arc map")
    assert "Posted once, at setup, before you create the first Worktree:" in arc_map
    assert "your share of the machine's cores" in arc_map
    wave = " ".join(
        shipped("references/brief-template.md").split("## The wave block", 1)[1].split()
    )
    assert "Other arcs hold <numbers, by record Issue>: never take them." in wave
    assert "- Another arc, record Issue #<t>: <files>." in wave


def test_each_worktree_is_cut_from_a_freshly_fetched_tip() -> None:
    dispatch = section(shipped("SKILL.md"), "3. Dispatch a wave")
    assert (
        "Run `git fetch`, then at once "
        "`<dashpot> worktree create <n> --base origin/<integration-branch> --json`"
    ) in dispatch
    assert (
        "Check that the `baseCommit` it reports is "
        "`git rev-parse origin/<integration-branch>`"
    ) in dispatch
    assert "`git -C <path> merge --ff-only origin/<integration-branch>`" in dispatch
    assert "including each one a merge unblocks" in dispatch


def test_a_merge_lands_only_what_ci_tested() -> None:
    merge = section(shipped("SKILL.md"), "4. Handle each hand-back")
    assert "several merges behind" not in merge
    check = merge.index("**Check that CI tested what will land.**")
    assert check < merge.index("--match-head-commit")
    assert (
        "`git merge-base --is-ancestor origin/<integration-branch> <headRefOid>` "
        "succeeds: the head already contains the integration branch's tip."
    ) in merge
    assert "it also did when the run's **tested base** is that tip" in merge
    assert "Where CI checks out the head alone, only the first test applies." in merge
    assert (
        "Merge directly only when one test holds. Otherwise, whoever moved the "
        "branch, do one of these:"
    ) in merge
    assert "Re-running the old run tests the old revision again." in merge
    assert (
        "`git log --oneline <last-broadcast>..origin/<integration-branch>`"
    ) in merge
    assert "names every merge in that range, whoever made it" in merge
    assert "Record the merge with the SHA you broadcast, at once" in merge
    record = section(shipped("references/run-records.md"), "A merge")
    assert (
        "the merge SHA and the SHA you broadcast are posted at once: the next "
        "broadcast starts from the SHA you broadcast."
    ) in record
    assert "how you checked that CI tested what lands" in record


def test_close_out_waits_for_another_sessions_sub_agents() -> None:
    close_out = section(shipped("SKILL.md"), "5. Close out")
    assert "**A removal refused for another session's sub-agents** waits" in close_out
    assert "tell the user which sessions the blockers name" in close_out
    assert "wait for their sub-agents to finish, and retry the dry run" in close_out
    assert (
        "A blocker that says its session ended never clears by waiting: give the "
        "user the command it names, and leave running it to them"
    ) in close_out
    assert (
        "Offer the user the override only when they explicitly ask for it"
        in " ".join(close_out.split())
    )
    for check in (
        "`git -C <path> status --porcelain` prints nothing",
        "its PR shows `MERGED`",
        "no process has its working directory inside it",
        "the dry run lists no blocker but those sessions' `sub-agent` ones",
    ):
        assert check in close_out, check
    # One sentence names the bypass: the user's own override (ADR 0112).
    flowed = " ".join(close_out.split())
    assert close_out.count("The bypass is the user's own Dashpot override:") == 1
    assert "give them each `--despite-subagents` flag the refused dry run prints" in (
        flowed
    )
    # The user runs the step-2 removal, whose flags differ for a check Worktree.
    assert (
        "for them to run the Worktree's step-2 removal themselves with those "
        "flags added"
    ) in flowed
    assert "git worktree remove" not in close_out
    assert (
        "Record that you handed the user the override, their instruction and "
        "each check's result"
    ) in flowed
    record = section(shipped("references/run-records.md"), "The close-out")
    assert "each Worktree the user removed despite listed sub-agents" in record


def test_each_known_dashpot_gap_is_named_for_removal() -> None:
    text = shipped("SKILL.md")
    gaps = section(text, "Known Dashpot gaps")
    # One entry per Dashpot gap a lead works around; drop an entry here and
    # there when the installed Dashpot fixes its gap.
    assert re.findall(r"- \*\*(.+?)\*\*", gaps) == [
        "An unloaded Codex lead ends its workers' Issue work.",
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
    # A lead off the shared service stops before any worker launches.
    assert "**Lead only on the shared service.**" in opencode
    assert (
        "read the `OpenCode Host Process mode` line of "
        "`<dashpot> integrate opencode --status`. Lead only when it reads "
        "`shared-service`. On `unknown`, run it once more first, since a busy "
        "machine can leave the server unread. On `standalone` or `unknown`, stop "
        "before binding or launching any worker"
    ) in flowed
    assert "start the lead again with a plain `opencode`, without `--standalone`" in (
        flowed
    )
    assert opencode.index("**Lead only on the shared service.**") < (
        opencode.index("**Launch.**")
    )
    assert "for OpenCode, the hosting mode a lead needs" in " ".join(
        shipped("SKILL.md").split()
    )
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
