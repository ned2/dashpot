"""Publish one harness lifecycle hook event from standard input."""

from __future__ import annotations

import json
import re
import signal
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from .core.command_outcomes import outcome_error
from .core.errors import DashpotError
from .core.event_log import (
    EventLog,
    EventLogDestination,
    use_event_log,
    working_directory,
)
from .core.json_records import HookRecordError
from .core.model import Harness
from .core.runtime_events import HookOutcome, OutcomeResult, fitting
from .event_logs import open_event_log
from .sessions.deferred_end import SETTLE_COMMAND, DeferredEnd, settle_session_end
from .sessions.hook_publish import HookPublication, publish_hook_event
from .sessions.opencode_publish import (
    PluginRequest,
    parse_request,
    publish_opencode,
)
from .sessions.processes import ProcessLookup, host_process_lookup
from .sessions.work_store import ActiveWork

# A failed publish is reported but never blocks the session: Claude Code reads
# exit code 2 as "deny this action and feed stderr back to the model", which
# would let a full disk or an unwritable state directory erase a prompt or
# refuse a Stop. Observation must never get in the session's way.
NON_BLOCKING_FAILURE_EXIT_CODE = 1
# What fails a hook run, reported and recorded rather than shown as a
# traceback. ``ValueError`` is a store's refusal of an occupied destination,
# the base of a record's Pydantic validation failure and of unreadable JSON.
# ``RuntimeError`` stays for Python's own runtime faults, such as a symlink
# loop under ``Path.resolve``: a hook must never break its harness.
HOOK_FAILURES: tuple[type[Exception], ...] = (
    OSError,
    ValueError,
    RuntimeError,
    DashpotError,
)
# The Claude Code events whose hook output can add context for the model. Only
# a Claude Code run is ever continued (ADR 0053), so no other harness reaches
# this output.
CONTEXT_EVENTS = frozenset({"SessionStart", "UserPromptSubmit", "PostToolUse"})
# A hook event name as a process kind may carry it; anything else is left out.
HOOK_EVENT_NAME = re.compile(r"[A-Za-z]{1,64}")


def publish_from_stream(stream: TextIO, harness: Harness = "codex") -> str | None:
    """Publish one hook event; return the hook output the harness should read."""
    return publish_event(json.load(stream), harness)


def publish_event(event: object, harness: Harness = "codex") -> str | None:
    """Publish one parsed hook event; return the hook output the harness should read."""
    return _publish(event, harness)[1]


def _publish(event: object, harness: Harness) -> tuple[HookPublication, str | None]:
    if not isinstance(event, dict):
        raise HookRecordError("hook input must be a JSON object")
    publication = publish_hook_event(event, harness=harness)
    name = event.get("hook_event_name")
    if publication.continued is None or name not in CONTEXT_EVENTS:
        return publication, None
    return publication, json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": name,
                "additionalContext": continued_work_context(publication.continued),
            }
        }
    )


def continued_work_context(work: ActiveWork) -> str:
    """Tell a resumed session that its Issue work was carried over to it."""
    return (
        f"Dashpot: this Agent Session still holds Issue work on "
        f"{work.issue_reference}, started {work.started_at} at "
        f"{work.working_directory}; its Agent Run continued from the session's "
        f"previous process. Run 'dashpot work show' to confirm it. If this "
        f"conversation is no longer working on that Issue, run 'dashpot work stop'."
    )


def hook_event_log(
    harness: Harness,
    event: object,
    *,
    destination: EventLogDestination | None = None,
) -> EventLog:
    """Open the Event Log of one hook process, named for its harness and event.

    It is routed from the session's working directory, as its hook record
    is, and names the session when the payload does; a payload that says
    neither leaves the process's own working directory and no session.
    """
    payload: dict[str, Any] = event if isinstance(event, dict) else {}
    name = payload.get("hook_event_name")
    kind = f"hook:{harness}"
    if isinstance(name, str) and HOOK_EVENT_NAME.fullmatch(name):
        kind = f"{kind}:{name}"
    cwd = payload.get("cwd")
    directory = Path(cwd) if isinstance(cwd, str) and cwd else working_directory()
    session = payload.get("session_id")
    return open_event_log(
        kind,
        working_directory=directory,
        destination=destination,
        harness=harness,
        session_id=session if isinstance(session, str) else None,
    )


@dataclass(slots=True)
class HookRun:
    """What one hook process has learned about its run so far.

    It is filled while the run goes, so unlike the values it collects it is
    not frozen. ``event`` is the payload whose ``hook_event_name`` names the
    outcome, ``publication`` what the run did to its record and the Work
    Store, ``reason`` a reason word it kept, and ``error`` what failed it.
    """

    event: object = None
    publication: HookPublication | None = None
    reason: str | None = None
    error: Exception | None = None

    @property
    def exit_code(self) -> int:
        """The status the hook process exits with: a failure never blocks the session."""
        return 0 if self.error is None else NON_BLOCKING_FAILURE_EXIT_CODE


@contextmanager
def hook_process(log: EventLog, *, label: str | None = None) -> Iterator[HookRun]:
    """Run one hook process's work against its Event Log, which the block's spans go to.

    The process starts, and when the block ends its outcome is recorded from
    the :class:`HookRun` it filled, then the process ends with its exit
    status and the log is closed. A failure in :data:`HOOK_FAILURES` ends
    the block, is printed to standard error under ``label`` when one is
    given, and fails the run without blocking the session. Any other
    exception goes on, leaving no ``process.end``: a missing end is a crash.
    """
    log.start()
    run = HookRun()
    try:
        with use_event_log(log):
            yield run
    except HOOK_FAILURES as exc:
        if label is not None:
            print(f"dashpot {label} hook: {exc}", file=sys.stderr)
        run.error = exc
    record_hook_outcome(log, run.event, run.publication, run.error, run.reason)
    log.end(run.exit_code)
    log.close()


def _run(
    harness: Harness, label: str, *, event_log: EventLogDestination | None = None
) -> int:
    try:
        event: object = json.load(sys.stdin)
    except HOOK_FAILURES as exc:
        event = None
        failure: Exception | None = exc
    else:
        failure = None
    log = hook_event_log(harness, event, destination=event_log)
    with hook_process(log, label=label) as run:
        run.event = event
        if failure is not None:
            raise failure
        # Identifying the session runs ``ps``; its spans are the hook's.
        run.publication, output = _publish(event, harness)
        if output is not None:
            print(output)
    return run.exit_code


def record_hook_outcome(
    log: EventLog,
    event: object,
    publication: HookPublication | None,
    error: Exception | None,
    reason: str | None = None,
) -> None:
    """Record what one hook run did to its record and the Work Store, or its error class.

    The Issue of an Agent Run it changed names the process from here on.
    ``reason`` is a reason word the run kept, such as the harness's own.
    """
    payload: dict[str, Any] = event if isinstance(event, dict) else {}
    # A hook asks for nothing a person could be refused: any error failed it.
    result: OutcomeResult = "succeeded" if error is None else "failed"
    if publication is not None:
        log.identify(issue_id=publication.issue_id)
    log.record(
        fitting(
            HookOutcome,
            {"result": result},
            {
                "hook_event": payload.get("hook_event_name"),
                "record_state": None if publication is None else publication.state,
                "work": None if publication is None else publication.work,
                "hook_reason": reason,
                "error_type": None if error is None else outcome_error(error),
            },
        )
    )


# A helper whose plugin stopped waiting must not linger, holding a Publisher
# record lock: it gives up at the deadline the plugin passed, plus this.
OPENCODE_DEADLINE_GRACE_SECONDS = 0.5


def _expire(_signal: int, _frame: object) -> None:
    raise TimeoutError("the OpenCode plugin's publication deadline passed")


def _run_opencode(*, event_log: EventLogDestination | None = None) -> int:
    """Apply one OpenCode plugin publication and print its acknowledgment.

    The acknowledgment is the one line on standard output the plugin reads;
    a failure prints none, which the plugin reads as no acknowledgment.
    """
    request: PluginRequest | None
    failure: Exception | None
    try:
        request, failure = parse_request(sys.stdin.read()), None
    except HOOK_FAILURES as exc:
        request, failure = None, exc
    kind = "hook:opencode" if request is None else f"hook:opencode:{request.kind}"
    session = None if request is None else request.session
    location = (
        None
        if request is None
        else session.location
        if session is not None
        else request.location
    )
    log = open_event_log(
        kind,
        working_directory=working_directory() if location is None else Path(location),
        destination=event_log,
        harness="opencode",
        session_id=None if session is None else session.root,
    )
    with hook_process(log, label="OpenCode") as run:
        # The last shared event written stands in for a native hook event
        # name; a request that wrote none is named by its kind.
        run.event = {} if request is None else {"hook_event_name": request.kind}
        previous = signal.signal(signal.SIGALRM, _expire)
        try:
            if request is None:
                raise failure or ValueError("no OpenCode plugin request")
            signal.setitimer(
                signal.ITIMER_REAL,
                request.deadline_ms / 1000 + OPENCODE_DEADLINE_GRACE_SECONDS,
            )
            outcome = publish_opencode(request)
            if outcome.written:
                run.event = {"hook_event_name": outcome.written[-1]}
            if outcome.publications:
                run.publication = outcome.publications[-1]
            run.reason = outcome.acknowledgment.reason
            print(outcome.acknowledgment.wire())
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
    return run.exit_code


def main(*, event_log: EventLogDestination | None = None) -> int:
    """Publish one Codex hook event from standard input."""
    return _run("codex", "Codex", event_log=event_log)


def claude_code_main(*, event_log: EventLogDestination | None = None) -> int:
    """Publish one Claude Code hook event from standard input."""
    return _run("claude-code", "Claude Code", event_log=event_log)


def opencode_main(*, event_log: EventLogDestination | None = None) -> int:
    """Apply one OpenCode plugin publication from standard input."""
    return _run_opencode(event_log=event_log)


def settle_main(
    argv: Sequence[str],
    *,
    event_log: EventLogDestination | None = None,
    lookup: ProcessLookup = host_process_lookup,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Settle one deferred ``SessionEnd`` a managed Codex daemon published.

    It runs detached from the hook that started it, and records its own
    Event Log process as the ``SessionEnd`` hook it completes: ``ended`` when
    the daemon kept running and the runs ended, ``unchanged`` when they were
    left as Orphaned Agent Runs (ADR 0086).
    """
    deferred: DeferredEnd | None = None
    failure: Exception | None = None
    try:
        deferred = DeferredEnd.parse(argv[0]) if argv else None
    except HOOK_FAILURES as exc:
        failure = exc
    # Only the Codex adapter defers an end, so an unreadable one is Codex's.
    harness: Harness = "codex" if deferred is None else deferred.harness
    log = open_event_log(
        f"hook:{harness}:SessionEnd",
        working_directory=None if deferred is None else Path(deferred.cwd),
        destination=event_log,
        harness=harness,
        session_id=None if deferred is None else deferred.session_id,
    )
    # Detached from the hook that started it, the settler has no one to
    # print a failure to.
    with hook_process(log) as run:
        run.event = {"hook_event_name": "SessionEnd"}
        if deferred is None:
            raise failure or ValueError("no deferred SessionEnd to settle")
        ended = settle_session_end(deferred, lookup, clock=clock, sleep=sleep)
        # The settler writes no hook record; its outcome names the directory
        # the deferred end was published from.
        run.publication = HookPublication(
            Path(deferred.cwd),
            state="ended",
            work="ended" if ended else "unchanged",
            issue_id=ended[0][1].issue_id if ended else None,
        )
    return run.exit_code


def module_main(argv: Sequence[str]) -> int:
    """Run this module: settle a deferred ``SessionEnd``, else publish a Codex event."""
    if tuple(argv[:1]) == (SETTLE_COMMAND,):
        return settle_main(argv[1:])
    return main()


if __name__ == "__main__":
    raise SystemExit(module_main(sys.argv[1:]))
