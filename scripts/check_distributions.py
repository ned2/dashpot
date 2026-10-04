"""Validate release archives and emit their SHA-256 checksums."""

from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "dashpot"
# Every file of every bundled skill ships, so a new skill's directory needs
# no entry here.
ASSETS = (
    "dashpot.tcss",
    "plugins/opencode.js",
    "py.typed",
    *sorted(
        path.relative_to(PACKAGE).as_posix()
        for path in (PACKAGE / "skills").rglob("*")
        if path.is_file()
    ),
)


def validate(directory: Path) -> list[Path]:
    """Check both archives against the release source and runtime contract."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    wheel = directory / f"dashpot-{version}-py3-none-any.whl"
    sdist = directory / f"dashpot-{version}.tar.gz"
    archives = sorted(path for path in directory.iterdir() if path.name != ".gitignore")
    if archives != sorted([wheel, sdist]):
        raise ValueError("Expected only the versioned wheel and source distribution")
    with zipfile.ZipFile(wheel) as archive:
        wheel_files = {name: archive.read(name) for name in archive.namelist()}
    with tarfile.open(sdist) as archive:
        source_files: dict[str, bytes] = {}
        for member in archive.getmembers():
            if not member.isfile():
                raise ValueError(f"Unexpected source archive entry: {member.name}")
            if not member.name.startswith(f"dashpot-{version}/"):
                raise ValueError(f"Unexpected source archive root: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing archive content: {member.name}")
            name = member.name.split("/", 1)[1]
            if any(
                part in {"..", ".git", ".codex", ".dashpot", ".venv", ".envrc", ".env"}
                for part in Path(name).parts
            ):
                raise ValueError(
                    f"Repository-local file in source distribution: {name}"
                )
            source_files[name] = stream.read()
    metadata_dir = f"dashpot-{version}.dist-info"
    for payload in (
        wheel_files[f"{metadata_dir}/METADATA"],
        source_files["PKG-INFO"],
    ):
        metadata = BytesParser().parsebytes(payload)
        for key, expected in {
            "Name": "dashpot",
            "Version": version,
            "Requires-Python": project["requires-python"],
            "License-Expression": "MIT",
            "Description-Content-Type": "text/markdown",
        }.items():
            if metadata[key] != expected:
                raise ValueError(f"Incorrect {key}: {metadata[key]!r}")
        description = metadata.get_payload(decode=True)
        if not isinstance(description, bytes) or not description.strip():
            raise ValueError("Missing package description")
        for target in re.findall(rb"\]\(([^\s)]+)\)", description):
            if not target.startswith((b"https://", b"#")):
                raise ValueError(f"Relative package-description link: {target!r}")
    for name in ASSETS:
        wheel_asset = wheel_files.get(f"dashpot/{name}")
        source_asset = source_files.get(f"src/dashpot/{name}")
        if wheel_asset is None or source_asset is None:
            raise ValueError(f"Missing packaged asset: {name}")
        if wheel_asset != source_asset:
            raise ValueError(f"Wheel/source asset mismatch: {name}")
    skill = wheel_files["dashpot/skills/dashpot-issue-work/SKILL.md"].decode()
    if f"written for Dashpot {version}." not in skill or f"`{version}`" not in skill:
        raise ValueError("Bundled skill does not match the release version")
    for name, target in project["scripts"].items():
        if (
            f"{name} = {target}"
            not in wheel_files[f"{metadata_dir}/entry_points.txt"].decode()
        ):
            raise ValueError(f"Missing entry point: {name}")
    if (
        wheel_files[f"{metadata_dir}/licenses/LICENSE"]
        != (ROOT / "LICENSE").read_bytes()
    ):
        raise ValueError("Incorrect wheel license")
    return archives


def main() -> None:
    """Emit checksums only after every archive check succeeds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    options = parser.parse_args()
    for archive in validate(options.directory):
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        print(f"{digest}  dist/{archive.name}")


if __name__ == "__main__":
    main()
