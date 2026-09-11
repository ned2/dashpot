"""Validate a release tag and extract its reviewed changelog entry."""

from __future__ import annotations

import argparse
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_notes(tag: str, version: str, changelog: str) -> str:
    """Refuse tags without a matching package version and release entry."""
    if not re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag):
        raise ValueError("Release tag must be vMAJOR.MINOR.PATCH")
    if tag != f"v{version}":
        raise ValueError(f"Tag {tag} does not match package version {version}")
    match = re.search(
        rf"^## {re.escape(version)}(?: — [^\n]+)?\n(.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if match is None or not match[1].strip():
        raise ValueError(f"Missing changelog entry for {version}")
    entry = match.group(1)
    assert isinstance(entry, str)
    return entry.strip() + "\n"


def main() -> None:
    """Validate the checked-out revision without fetching or changing refs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--notes", type=Path, required=True)
    options = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    notes = release_notes(options.tag, version, (ROOT / "CHANGELOG.md").read_text())
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", options.main_ref],
        cwd=ROOT,
        check=True,
    )
    options.notes.write_text(notes)
    print(f"Validated {options.tag} on {options.main_ref}")


if __name__ == "__main__":
    main()
