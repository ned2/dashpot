"""Exercise the trace drift report across a PR's own changes and main's."""

import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Maintenance scripts are deliberately outside the installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import trace_drift

sys.path.pop(0)

EXPERIMENT = "scripts/experiments/codex-1"
TRACE = "docs/spikes/measurements/issue-1-codex-trace.jsonl"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A run at one commit, main moving on, and a PR branched from the new main."""
    root = tmp_path / "repository"
    git(tmp_path, "init", "-q", "-b", "main", str(root))
    write(root, "src/dashpot/ours.py", "ours = 1\n")
    write(root, "src/dashpot/theirs.py", "theirs = 1\n")
    write(root, "src/dashpot/settled.py", "settled = 1\n")
    write(root, f"{EXPERIMENT}/run.mjs", "// runner\n")
    write(root, f"{EXPERIMENT}/verify.mjs", "// verifier\n")
    run_head = commit(root, "Run here")
    write(root, "src/dashpot/theirs.py", "theirs = 2\n")
    commit(root, "Main moves on")
    git(root, "switch", "-qc", "measurement")
    write(root, "src/dashpot/ours.py", "ours = 2\n")
    commit(root, "The PR's review fix")
    monkeypatch.chdir(root)
    return SimpleNamespace(root=root, run_head=run_head)


def environment(**extra):
    return {
        "kind": "environment",
        "sourceSHA256": {
            "run.mjs": sha("// runner\n"),
            "src/dashpot/ours.py": sha("ours = 1\n"),
            "src/dashpot/theirs.py": sha("theirs = 1\n"),
            "src/dashpot/settled.py": sha("settled = 1\n"),
        },
        **extra,
    }


def record_trace(root, first, *, name=TRACE):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(first) + "\n" + json.dumps({"kind": "scenario"}) + "\n"
    if name.endswith(".gz"):
        path.write_bytes(gzip.compress(text.encode()))
    else:
        path.write_text(text)
    return path


def fake_node(monkeypatch, *, strict, lenient, stdout="ok - claim\n"):
    """Stand in for Node: each run reports the exit status the test names."""
    original = subprocess.run
    calls = []

    def run(command, *args, **kwargs):
        if command[0] != "node":
            return original(command, *args, **kwargs)
        calls.append(command)
        failed = strict if command[-1] == "--strict" else lenient
        stderr = (
            "node:internal/modules/run_main:123\n    triggerUncaughtException(\n"
            f"AssertionError [ERR_ASSERTION]: {failed}\n    at file:///verify.mjs:1:1\n"
            if failed
            else ""
        )
        return subprocess.CompletedProcess(command, 1 if failed else 0, stdout, stderr)

    monkeypatch.setattr(trace_drift.subprocess, "run", run)
    return calls


def check(*arguments):
    return trace_drift.main(
        ["--main", "main", f"{EXPERIMENT}/verify.mjs", TRACE, *arguments]
    )


def test_a_passing_strict_check_prints_the_verifiers_output(
    checkout, monkeypatch, capsys
):
    record_trace(checkout.root, environment(dashpot={"head": checkout.run_head}))
    calls = fake_node(monkeypatch, strict=None, lenient=None)

    assert check("0.166.0") == 0

    assert capsys.readouterr().out == "ok - claim\n"
    assert calls == [["node", f"{EXPERIMENT}/verify.mjs", TRACE, "0.166.0", "--strict"]]


def test_drift_is_attributed_to_the_pr_or_to_main_since_the_recorded_run(
    checkout, monkeypatch, capsys
):
    record_trace(checkout.root, environment(dashpot={"head": checkout.run_head}))
    fake_node(monkeypatch, strict="Dashpot modules differ", lenient=None)

    assert check() == 1

    out = capsys.readouterr().out
    assert out == (
        f"{TRACE}: {EXPERIMENT}/verify.mjs --strict failed: Dashpot modules differ\n"
        "Without --strict it passes, so the failure is source drift alone.\n"
        f"The run's base: {checkout.run_head}, as the trace records it.\n"
        "Drifted sources:\n"
        "  changed by this PR: src/dashpot/ours.py\n"
        "  changed by main since the run's base: src/dashpot/theirs.py\n"
    )
    assert "Traceback" not in out and "at file://" not in out


@pytest.mark.parametrize(
    "recorded",
    [
        {},
        {"dashpotHead": "0" * 40},
        {"head": "not a commit"},
    ],
    ids=["unrecorded", "unknown-commit", "malformed"],
)
def test_without_a_run_base_the_merge_base_stands_in_and_says_so(
    checkout, monkeypatch, capsys, recorded
):
    record_trace(checkout.root, environment(**recorded))
    fake_node(monkeypatch, strict="sources changed under --strict", lenient=None)
    merge_base = git(checkout.root, "merge-base", "main", "HEAD")

    assert check() == 1

    out = capsys.readouterr().out
    assert (
        "The trace records no run base this checkout has, so the run's base is "
        f"taken as the merge-base of HEAD and main: {merge_base}.\n"
    ) in out
    assert out.endswith(
        "  changed by this PR: src/dashpot/ours.py\n"
        "  changed by neither this PR nor main since the run's base: "
        "src/dashpot/theirs.py\n"
    )


def test_each_recorded_head_key_names_the_run_base(checkout, monkeypatch, capsys):
    for recorded in (
        {"dashpotHead": checkout.run_head},
        {"head": checkout.run_head},
    ):
        record_trace(checkout.root, environment(**recorded))
        fake_node(monkeypatch, strict="drift", lenient=None)
        assert check() == 1
        assert f"The run's base: {checkout.run_head}," in capsys.readouterr().out


def test_uncommitted_and_untracked_changes_are_the_prs_own(
    checkout, monkeypatch, capsys
):
    first = environment(dashpot={"head": checkout.run_head})
    first["sourceSHA256"]["src/dashpot/new.py"] = sha("new = 0\n")
    record_trace(checkout.root, first)
    write(checkout.root, "src/dashpot/settled.py", "settled = 2\n")
    write(checkout.root, "src/dashpot/new.py", "new = 1\n")
    fake_node(monkeypatch, strict="drift", lenient=None)

    assert check() == 1

    out = capsys.readouterr().out
    assert "  changed by this PR: src/dashpot/new.py\n" in out
    assert "  changed by this PR: src/dashpot/settled.py\n" in out


def test_a_source_gone_from_the_checkout_is_named_with_its_origin(
    checkout, monkeypatch, capsys
):
    first = environment(dashpot={"head": checkout.run_head})
    first["experimentSHA256"] = {"helper.mjs": sha("// helper\n")}
    record_trace(checkout.root, first)
    (checkout.root / "src/dashpot/settled.py").unlink()
    fake_node(monkeypatch, strict="drift", lenient=None)

    assert check() == 1

    out = capsys.readouterr().out
    assert (
        "  changed by this PR: src/dashpot/settled.py (no longer in the checkout)\n"
    ) in out
    assert out.endswith("  not found in the checkout: helper.mjs\n")


def test_a_failure_with_no_drift_is_not_reported_as_drift(
    checkout, monkeypatch, capsys
):
    first = environment(dashpot={"head": checkout.run_head})
    first["sourceSHA256"] = {"run.mjs": sha("// runner\n")}
    record_trace(checkout.root, first)
    fake_node(monkeypatch, strict="exactly one hook record", lenient="exactly one")

    assert check() == 1

    out = capsys.readouterr().out
    assert "Without --strict it fails too: exactly one\n" in out
    assert out.endswith(
        "No hashed source differs from the run's, so the failure is not drift.\n"
    )


def test_a_gzipped_trace_is_read_as_kept(checkout, monkeypatch, capsys):
    gzipped = TRACE + ".gz"
    record_trace(
        checkout.root, environment(dashpot={"head": checkout.run_head}), name=gzipped
    )
    fake_node(monkeypatch, strict="drift", lenient=None)

    assert (
        trace_drift.main(["--main", "main", f"{EXPERIMENT}/verify.mjs", gzipped]) == 1
    )

    assert "changed by this PR: src/dashpot/ours.py" in capsys.readouterr().out


def test_only_working_tree_hash_maps_are_compared():
    digest = "a" * 64
    first = {
        "kind": "environment",
        "headSourceSHA256": {"src/head.py": digest},
        "worktreeSourceSHA256": {"src/worktree.py": digest},
        "binarySHA256": digest,
        "publishers": [
            {"name": "installed", "revision": "abc", "sourceSHA256": {"x.py": digest}},
            {"name": "worktree", "sourceSHA256": {"y.py": digest}},
        ],
        "notesSHA256": {"label": "not a digest"},
    }
    assert sorted(trace_drift.hashed_sources(first)) == [
        ("src/worktree.py", digest),
        ("y.py", digest),
    ]


def test_an_unknown_integration_branch_is_refused(checkout, capsys):
    record_trace(checkout.root, environment())
    assert (
        trace_drift.main(
            ["--main", "no-such-branch", f"{EXPERIMENT}/verify.mjs", TRACE]
        )
        == 1
    )
    assert capsys.readouterr().err == (
        "Trace check failed: no-such-branch names no commit in this checkout\n"
    )


def test_a_trace_that_does_not_open_with_an_object_is_refused(
    checkout, monkeypatch, capsys
):
    (checkout.root / TRACE).parent.mkdir(parents=True)
    (checkout.root / TRACE).write_text("[]\n")
    fake_node(monkeypatch, strict="drift", lenient=None)
    assert check() == 1
    assert capsys.readouterr().err == (
        f"Trace check failed: {TRACE} does not open with a JSON object\n"
    )


def test_a_failure_without_an_error_line_names_the_exit_status():
    result = subprocess.CompletedProcess(["node"], 3, "", "Killed\n")
    assert trace_drift.failure(result) == "it exited with status 3"
