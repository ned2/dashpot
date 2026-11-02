"""Run provisioning queries inside the operator's Codex sandbox.

This script uses only the standard library so an isolated Python can run it
without importing Dashpot or writing bytecode. Only boolean results leave
the sandbox; command output and environment values never do.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from types import FrameType
from typing import NoReturn
from urllib.parse import urlsplit


def _stop(process: subprocess.Popen[str]) -> None:
    """Stop a timed-out group while its unreaped leader still holds the group ID."""
    if process.returncode is not None:
        return
    try:
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        if os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
            break
        time.sleep(0.01)
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def _run(args: list[str], timeout: float, *, capture: bool = False) -> tuple[int, str]:
    """Run a bounded, non-interactive probe, discarding unneeded output."""
    try:
        with subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
            env={
                **os.environ,
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "SSH_ASKPASS_REQUIRE": "never",
            },
        ) as process:
            try:
                stdout, _stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                return -1, ""
            finally:
                _stop(process)
            code = process.returncode
            assert isinstance(code, int)
            return code, (stdout or "").strip() if capture else ""
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""


def _writable(path: str, timeout: float) -> bool:
    """Check a directory's effective sandbox grant without creating a file."""
    return Path(path).is_dir() and _run(["test", "-w", path], timeout)[0] == 0


def _cache(name: str, timeout: float) -> bool:
    """Whether the named cache variable selects an absolute, writable directory."""
    value = os.environ.get(name, "")
    return bool(value) and Path(value).is_absolute() and _writable(value, timeout)


def _ssh_destination(url: str) -> tuple[str, int | None] | None:
    """The SSH destination of a Git remote, or none for another transport."""
    if url.startswith(("ssh://", "git+ssh://")):
        parsed = urlsplit(url)
        if not parsed.hostname:
            raise ValueError("missing SSH host")
        user = f"{parsed.username}@" if parsed.username else ""
        return f"{user}{parsed.hostname}", parsed.port
    if "://" in url:
        return None
    scp = re.match(r"^(?!/)([^/:]+@[^/:]+|[^/:]+):.+", url)
    return (str(scp.group(1)), None) if scp else None


def _ssh(url: str, timeout: float) -> bool | None:
    """Check the profile's effective OpenSSH configuration for an SSH remote."""
    try:
        destination = _ssh_destination(url)
        if destination is None:
            return None
        command = os.environ.get("GIT_SSH_COMMAND")
        if not command:
            code, command = _run(
                ["git", "config", "--get", "core.sshCommand"], timeout, capture=True
            )
            if code not in {0, 1}:
                return False
        args = ["-G", "-o", "BatchMode=yes"]
        host, port = destination
        if port is not None:
            args += ["-p", str(port)]
        args.append(host)
        if command:
            # Git evaluates these operator-owned command strings with a shell.
            invocation = ["/bin/sh", "-c", command + ' "$@"', "ssh-preflight", *args]
        else:
            invocation = [os.environ.get("GIT_SSH", "ssh"), *args]
        return _run(invocation, timeout)[0] == 0
    except ValueError:
        return False


def probe(
    root: str, git_directory: str, remote: str, timeout: float
) -> dict[str, bool | None]:
    """Collect every applicable check without retaining command output."""
    code, url = _run(
        ["git", "remote", "get-url", "--push", remote], timeout, capture=True
    )
    remote_exists = code == 0 and bool(url)
    return {
        "worktreeRoot": _writable(root, timeout),
        "gitDirectory": _writable(git_directory, timeout),
        "uvCache": _cache("UV_CACHE_DIR", timeout),
        "preCommitCache": _cache("PRE_COMMIT_HOME", timeout),
        "remote": remote_exists,
        "ssh": _ssh(url, timeout) if remote_exists else None,
        "gitRemote": _run(["git", "ls-remote", "--", url], timeout)[0] == 0
        if remote_exists
        else None,
        "authentication": _run(["gh", "auth", "status"], timeout)[0] == 0,
    }


def _interrupt(signum: int, _frame: FrameType | None) -> NoReturn:
    """Unwind an active probe so its child group is stopped before exit."""
    raise SystemExit(128 + signum)


def main() -> None:
    """Print boolean observations for the parent preflight to validate."""
    signal.signal(signal.SIGTERM, _interrupt)
    signal.signal(signal.SIGINT, _interrupt)
    root, git_directory, remote, timeout = sys.argv[1:]
    print(json.dumps(probe(root, git_directory, remote, float(timeout))))


if __name__ == "__main__":
    main()
