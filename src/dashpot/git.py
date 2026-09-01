"""Run Git for one Repository Anchor through a single adapter.

Every module that asks Git a question goes through :class:`Git`, so the
return-code and stderr handling, the ``%00`` field discipline for
``for-each-ref``, and the rule that a failure is never reported as an
absence each live in exactly one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandResult, CommandRunner, run_command


class GitError(RuntimeError):
    """A Git command that could not answer: non-zero exit, missing binary, or timeout."""

    def __init__(
        self,
        argv: Sequence[str],
        cwd: Path,
        *,
        returncode: int | None = None,
        stderr: str = "",
        detail: str | None = None,
    ) -> None:
        self.argv = tuple(argv)
        self.cwd = cwd
        self.returncode = returncode
        self.stderr = stderr
        # ``detail`` is the one-line reason callers put into Diagnostics and
        # refusal messages; the full message keeps the argv for a person.
        self.detail = (
            detail if detail is not None else (stderr.strip() or f"exit {returncode}")
        )
        super().__init__(f"git {' '.join(self.argv)} failed: {self.detail}")


@dataclass(frozen=True, slots=True)
class Git:
    """Run ``git`` at one Worktree with one timeout and an injectable runner."""

    root: Path
    timeout: float = 5
    runner: CommandRunner = run_command

    def at(self, root: Path, *, timeout: float | None = None) -> Git:
        """Retarget this adapter at another Worktree, keeping its runner."""
        return Git(root, self.timeout if timeout is None else timeout, self.runner)

    def run(self, *args: str) -> CommandResult:
        """Run git and return the result; a non-zero exit is the caller's to read.

        A runner failure — the binary missing, a timeout — is a
        :class:`GitError`; it can never be mistaken for Git answering.
        """
        try:
            return self.runner(["git", *args], self.root, self.timeout)
        except (OSError, RuntimeError) as exc:
            raise GitError(args, self.root, detail=str(exc)) from exc

    def text(self, *args: str) -> str:
        """Stripped stdout of a git command that must succeed."""
        result = self._succeeding(args)
        return result.stdout.strip()

    def maybe(self, *args: str) -> str | None:
        """Stripped stdout, or None only when Git itself answered non-zero.

        This is the "failure is not absence" rule: a missing binary or a
        timeout still raises :class:`GitError` rather than reading as "no".
        """
        result = self.run(*args)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def count(self, *args: str) -> int | None:
        """``maybe`` for a command whose answer is a count, such as rev-list.

        None means Git answered non-zero or with something that is not an
        integer; a runner failure still raises :class:`GitError`.
        """
        answer = self.maybe(*args)
        if answer is None:
            return None
        try:
            return int(answer)
        except ValueError:
            return None

    def records(self, *args: str, fields: Sequence[str]) -> list[tuple[str, ...]]:
        """List refs with ``for-each-ref``, one fixed-arity tuple per ref.

        Fields are ``%00``-separated and each record ends with ``%00`` so a
        value containing a newline — ``%(worktreepath)`` — can never split or
        merge records. The first field must be a refname-shaped one, which
        Git guarantees is newline-free; the record separator is stripped from
        it by arity, never by guessing at the content.
        """
        format_argument = "--format=" + "%00".join(fields) + "%00"
        result = self._succeeding(("for-each-ref", format_argument, *args))
        parts = result.stdout.split("\0")
        width = len(fields)
        listed: list[tuple[str, ...]] = []
        # After every record's closing NUL Git prints its newline separator,
        # which lands at the front of the next record's first field.
        for start in range(0, len(parts) - 1, width):
            record = parts[start : start + width]
            if len(record) < width:
                break
            if start:
                record[0] = record[0].removeprefix("\n")
            listed.append(tuple(record))
        return listed

    def worktree_records(self) -> list[dict[str, str]]:
        """Every record of ``git worktree list``, main working tree first.

        A record maps Git's porcelain keys to their values: ``worktree`` (the
        path), ``HEAD``, ``branch`` (a full refname), and, when present, the
        flag keys ``bare``, ``detached``, ``locked``, and ``prunable`` with
        their reason or an empty string.
        """
        raw = self.text("worktree", "list", "--porcelain", "-z")
        return _parse_worktree_records(raw)

    def _succeeding(self, args: Sequence[str]) -> CommandResult:
        result = self.run(*args)
        if result.returncode != 0:
            raise GitError(
                args, self.root, returncode=result.returncode, stderr=result.stderr
            )
        return result


def _parse_worktree_records(raw: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for field in raw.split("\0"):
        if not field:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = field.partition(" ")
        current[key] = value if separator else ""
    if current:
        records.append(current)
    return records
