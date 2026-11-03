"""Exercise coverage evidence across source changes and failed validation."""

import subprocess
import sys
from pathlib import Path

import pytest

# Maintenance scripts are deliberately outside the installed package, and
# review_coverage imports CI's lane classifier beside it as a script does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import review_coverage

del sys.path[:2]


def commit_checkout(root, message):
    subprocess.run(["git", "-C", str(root), "commit", "-qm", message], check=True)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".review-coverage/\nignored/\n")
    (tmp_path / "module.py").write_text("value = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    commit_checkout(tmp_path, "Base")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    return tmp_path


def fake_pytest(monkeypatch, action):
    original = subprocess.run

    def run(command, *args, **kwargs):
        if command[1:3] == ["-m", "pytest"]:
            root = Path(kwargs["cwd"])
            action(root)
            return subprocess.CompletedProcess(command, 0)
        return original(command, *args, **kwargs)

    monkeypatch.setattr(review_coverage.subprocess, "run", run)


def report(root):
    (root / review_coverage.REPORT_DIRECTORY / "coverage.json").write_text(
        '{"totals": {}}\n'
    )


def test_evidence_survives_staging_and_committing_same_content(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    (checkout / "new.py").write_text("new = True\n")
    base = review_coverage.git(checkout, "rev-parse", "HEAD")
    evidence = review_coverage.collect(checkout, base)
    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
    commit_checkout(checkout, "Implementation")
    assert review_coverage.verify(checkout, base).evidence == evidence
    with pytest.raises(ValueError, match="Review base changed"):
        review_coverage.verify(checkout, "HEAD")


@pytest.mark.parametrize(
    "change", ["edit", "new", "delete", "mode", "symlink", "script"]
)
def test_source_changes_invalidate_evidence(checkout, monkeypatch, change):
    script = checkout / "scripts" / "tool.py"
    script.parent.mkdir()
    script.write_text('"""A maintenance script."""\n')
    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
    commit_checkout(checkout, "Script")
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    source = checkout / "module.py"
    if change == "edit":
        source.write_text("value = 2\n")
    elif change == "new":
        (checkout / "new.py").write_text("value = 3\n")
    elif change == "delete":
        source.unlink()
    elif change == "mode":
        source.chmod(0o755)
    elif change == "script":
        script.write_text('"""A changed maintenance script."""\n')
    else:
        source.unlink()
        source.symlink_to("missing.py")
    with pytest.raises(ValueError, match="Source files changed"):
        review_coverage.verify(checkout, "HEAD")


def test_ignored_files_do_not_invalidate_evidence(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    evidence = review_coverage.collect(checkout, "HEAD")
    (checkout / "ignored").mkdir()
    (checkout / "ignored" / "local.txt").write_text("local state")
    assert review_coverage.verify(checkout, "HEAD").evidence == evidence


def test_failed_rerun_removes_old_success_evidence(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")

    def fail(root):
        raise subprocess.CalledProcessError(1, ["pytest"])

    fake_pytest(monkeypatch, fail)
    with pytest.raises(subprocess.CalledProcessError):
        review_coverage.collect(checkout, "HEAD")
    with pytest.raises(FileNotFoundError):
        review_coverage.verify(checkout, "HEAD")


def test_changes_during_run_cannot_publish_success(checkout, monkeypatch):
    def changing_run(root):
        report(root)
        (root / "module.py").write_text("value = 2\n")

    fake_pytest(monkeypatch, changing_run)
    with pytest.raises(ValueError, match="changed during coverage"):
        review_coverage.collect(checkout, "HEAD")
    assert not (checkout / review_coverage.REPORT_DIRECTORY / "evidence.json").exists()


def test_replaced_report_is_rejected(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    (checkout / review_coverage.REPORT_DIRECTORY / "coverage.json").write_text("{}")
    with pytest.raises(ValueError, match="Coverage report changed"):
        review_coverage.verify(checkout, "HEAD")


def test_pytest_environment_cannot_silently_filter_full_suite(checkout, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k one_test")
    with pytest.raises(ValueError, match="Unset PYTEST_ADDOPTS"):
        review_coverage.collect(checkout, "HEAD")


def test_parallel_collection_records_the_exact_full_suite_command(
    checkout, monkeypatch
):
    fake_pytest(monkeypatch, report)
    evidence = review_coverage.collect(checkout, "HEAD", workers=2)
    assert evidence.command[-4:] == ["-n", "2", "--dist=load", "--max-worker-restart=0"]
    assert "--cov" in evidence.command
    assert review_coverage.verify(checkout, "HEAD").evidence == evidence


def test_default_collection_inherits_repository_worker_policy(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    evidence = review_coverage.collect(checkout, "HEAD")
    assert "-n" not in evidence.command
    assert "-o" not in evidence.command
    assert "--cov" in evidence.command


def test_serial_collection_explicitly_overrides_parallel_defaults(
    checkout, monkeypatch
):
    fake_pytest(monkeypatch, report)
    evidence = review_coverage.collect(checkout, "HEAD", workers=0)
    assert evidence.command[-4:] == ["-n", "0", "--dist=load", "--max-worker-restart=0"]
    assert review_coverage.verify(checkout, "HEAD").evidence == evidence


def test_invalid_worker_count_removes_old_evidence(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    with pytest.raises(ValueError, match="Workers"):
        review_coverage.collect(checkout, "HEAD", workers=-1)
    assert not (checkout / review_coverage.REPORT_DIRECTORY / "evidence.json").exists()


def test_documentation_changes_leave_evidence_standing_and_are_named(
    checkout, monkeypatch
):
    (checkout / "docs").mkdir()
    (checkout / "docs" / "guide.md").write_text("# Guide\n")
    (checkout / "docs" / "old.md").write_text("# Old\n")
    subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
    commit_checkout(checkout, "Documents")
    fake_pytest(monkeypatch, report)
    evidence = review_coverage.collect(checkout, "HEAD")
    (checkout / "docs" / "guide.md").write_text("# Guide, rewrapped\n")
    (checkout / "docs" / "old.md").unlink()
    (checkout / "AGENTS.md").write_text("# Agents\n")

    verified = review_coverage.verify(checkout, "HEAD")

    assert verified.evidence == evidence
    assert verified.documentation_delta == ("AGENTS.md", "docs/guide.md", "docs/old.md")
    assert review_coverage.source_digest(checkout) != evidence.source_digest


def test_unchanged_sources_accept_no_documentation_delta(checkout, monkeypatch):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    assert review_coverage.verify(checkout, "HEAD").documentation_delta == ()


@pytest.mark.parametrize(
    "name",
    [
        "src/dashpot/skills/example/SKILL.md",
        "scripts/experiments/example/run.mjs",
        "docs/spikes/measurements/issue-1-trace.jsonl",
        "CHANGELOG.md",
        "README-pypi.md",
    ],
)
def test_a_path_the_suite_or_build_reads_still_needs_a_rerun(
    checkout, monkeypatch, name
):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    (checkout / "docs").mkdir()
    (checkout / "docs" / "guide.md").write_text("# Guide\n")
    path = checkout / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed\n")
    with pytest.raises(ValueError, match="Source files changed") as refusal:
        review_coverage.verify(checkout, "HEAD")
    assert str(refusal.value).endswith(f"run it again: {name}")


def test_evidence_whose_sources_disagree_with_its_digest_is_rejected(
    checkout, monkeypatch
):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    manifest = checkout / review_coverage.REPORT_DIRECTORY / "evidence.json"
    evidence = review_coverage.Evidence.model_validate_json(manifest.read_text())
    edited = evidence.model_copy(update={"sources": {}})
    manifest.write_text(edited.model_dump_json())
    with pytest.raises(ValueError, match="do not match its digest"):
        review_coverage.verify(checkout, "HEAD")


def test_check_reports_the_documentation_it_accepted(checkout, monkeypatch, capsys):
    fake_pytest(monkeypatch, report)
    evidence = review_coverage.collect(checkout, "HEAD")
    (checkout / "NOTES.md").write_text("# Notes\n")
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(
        sys, "argv", ["review_coverage.py", "--base", "HEAD", "--check"]
    )

    assert review_coverage.main() == 0

    out = capsys.readouterr().out
    assert f"source SHA-256: {evidence.source_digest}" in out
    assert out.endswith("Accepted documentation changed since coverage:\n  NOTES.md\n")


def test_check_without_a_delta_names_no_accepted_documentation(
    checkout, monkeypatch, capsys
):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(
        sys, "argv", ["review_coverage.py", "--base", "HEAD", "--check"]
    )
    assert review_coverage.main() == 0
    assert "Accepted documentation" not in capsys.readouterr().out


def test_check_refuses_a_source_change_on_stderr(checkout, monkeypatch, capsys):
    fake_pytest(monkeypatch, report)
    review_coverage.collect(checkout, "HEAD")
    (checkout / "module.py").write_text("value = 2\n")
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(
        sys, "argv", ["review_coverage.py", "--base", "HEAD", "--check"]
    )
    assert review_coverage.main() == 1
    assert capsys.readouterr().err == (
        "Coverage evidence failed: Source files changed since coverage; "
        "run it again: module.py\n"
    )


def test_collection_prints_the_evidence_it_recorded(checkout, monkeypatch, capsys):
    fake_pytest(monkeypatch, report)
    monkeypatch.chdir(checkout)
    monkeypatch.setattr(sys, "argv", ["review_coverage.py", "--base", "HEAD"])
    assert review_coverage.main() == 0
    out = capsys.readouterr().out
    assert f"source SHA-256: {review_coverage.source_digest(checkout)}" in out
    assert "Accepted documentation" not in out
