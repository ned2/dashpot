"""Exercise CI lane selection across real diffs and aggregate job outcomes."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import ci_lane

sys.path.pop(0)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root):
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Change",
    )
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("Initial\n")
    base = commit(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path, base


@pytest.mark.parametrize(
    "name,expected",
    [
        ("README.md", "docs"),
        ("docs/deep/topic.md", "docs"),
        ("conformance/issue/spec.md", "docs"),
        ("src/README.md", "full"),
        ("src/a.py", "full"),
        ("tests/a.py", "full"),
        ("pyproject.toml", "full"),
        ("uv.lock", "full"),
        (".github/workflows/ci.yml", "full"),
        ("docs/example.py", "full"),
        ("docs/odd\nname.md", "docs"),
    ],
)
def test_complete_diff_classification(checkout, name, expected):
    root, base = checkout
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Changed\n")
    assert ci_lane.classify("pull_request", base, commit(root)) == expected


def test_earlier_code_change_is_not_hidden_by_latest_docs_commit(checkout):
    root, base = checkout
    (root / "code.py").write_text("x = 1\n")
    commit(root)
    (root / "README.md").write_text("Docs\n")
    assert ci_lane.classify("pull_request", base, commit(root)) == "full"


def test_rename_from_code_to_documentation_still_requires_full_ci(checkout):
    root, _ = checkout
    (root / "code.py").write_text("content\n")
    base = commit(root)
    (root / "code.py").rename(root / "example.md")
    assert ci_lane.classify("pull_request", base, commit(root)) == "full"


@pytest.mark.parametrize(
    "event", ["workflow_dispatch", "workflow_call", "push", "merge_group", ""]
)
def test_non_pr_invocations_always_run_full(checkout, event):
    root, base = checkout
    (root / "README.md").write_text("Docs\n")
    assert ci_lane.classify(event, base, commit(root)) == "full"


def test_empty_or_unavailable_diff_runs_full(checkout):
    _, base = checkout
    assert ci_lane.classify("pull_request", base, base) == "full"
    assert ci_lane.classify("pull_request", "", base) == "full"
    assert ci_lane.classify("pull_request", "missing", base) == "full"


def results(lane):
    return {
        "changes": {"result": "success", "outputs": {"lane": lane}},
        "quality": {"result": "success"},
        **{
            name: {"result": "skipped" if lane == "docs" else "success"}
            for name in ("test", "build", "install", "minimum-git")
        },
    }


@pytest.mark.parametrize("lane", ["docs", "full"])
def test_valid_lane_succeeds(lane):
    ci_lane.require_success(results(lane))


@pytest.mark.parametrize("lane", ["docs", "full"])
@pytest.mark.parametrize(
    "job", ["changes", "quality", "test", "build", "install", "minimum-git"]
)
@pytest.mark.parametrize("outcome", ["failure", "cancelled"])
def test_failure_or_cancellation_always_fails(lane, job, outcome):
    jobs = results(lane)
    jobs[job]["result"] = outcome
    with pytest.raises(ValueError):
        ci_lane.require_success(jobs)


@pytest.mark.parametrize(
    "job", ["changes", "quality", "test", "build", "install", "minimum-git"]
)
def test_unexpected_skip_fails(job):
    jobs = results("full")
    jobs[job]["result"] = "skipped"
    with pytest.raises(ValueError):
        ci_lane.require_success(jobs)


@pytest.mark.parametrize("invalid", ["missing-job", "missing-lane", "unknown-lane"])
def test_incomplete_or_unknown_results_fail(invalid):
    jobs = results("docs")
    if invalid == "missing-job":
        del jobs["test"]
    elif invalid == "missing-lane":
        jobs["changes"]["outputs"] = {}
    else:
        jobs["changes"]["outputs"] = {"lane": "unknown"}
    with pytest.raises(ValueError):
        ci_lane.require_success(jobs)


def test_reusable_pr_caller_forces_full_verification(checkout):
    root, base = checkout
    (root / "README.md").write_text("Docs\n")
    assert (
        ci_lane.classify("pull_request", base, commit(root), force_full=True) == "full"
    )


def test_workflow_commands_accept_docs_skips_but_reject_them_for_mixed_changes(
    checkout, monkeypatch
):
    root, base = checkout
    script = str(Path(ci_lane.__file__).resolve())
    output = root / "workflow-output"
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("PR_BASE_SHA", base)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("FORCE_FULL", "false")
    (root / "README.md").write_text("Documentation change\n")

    for lane in ("docs", "full"):
        if lane == "full":
            (root / "code.py").write_text("value = 1\n")
        monkeypatch.setenv("PR_HEAD_SHA", commit(root))
        subprocess.run([sys.executable, script, "classify"], check=True)
        name, emitted = output.read_text().strip().split("=")
        assert (name, emitted) == ("lane", lane)
        output.unlink()

        jobs = results("docs")
        jobs["changes"]["outputs"]["lane"] = emitted
        monkeypatch.setenv("RESULTS", json.dumps(jobs))
        aggregate = subprocess.run(
            [sys.executable, script, "require"], capture_output=True, text=True
        )
        if lane == "docs":
            assert aggregate.returncode == 0, aggregate.stderr
        else:
            assert aggregate.returncode != 0
            assert "must report success" in aggregate.stderr
