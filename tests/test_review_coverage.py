"""Exercise coverage evidence across source changes and failed validation."""

import subprocess
import sys
from pathlib import Path

import pytest

# Maintenance scripts are deliberately outside the installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import review_coverage

sys.path.pop(0)


def commit_checkout(root, message):
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            message,
        ],
        check=True,
    )


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
    assert review_coverage.verify(checkout, base) == evidence
    with pytest.raises(ValueError, match="Review base changed"):
        review_coverage.verify(checkout, "HEAD")


@pytest.mark.parametrize("change", ["edit", "new", "delete", "mode", "symlink"])
def test_source_changes_invalidate_evidence(checkout, monkeypatch, change):
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
    assert review_coverage.verify(checkout, "HEAD") == evidence


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
