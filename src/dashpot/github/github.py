"""Ask GitHub through one gateway: `gh` invocation, classification, budget.

Every module that asks GitHub a question goes through :class:`GitHubGateway`,
so the way a failure is read, the way a page cursor is followed, the rate
limit GitHub reports, and the bound on how much one refresh may fetch each
live in exactly one place.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Container, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from contextvars import Context, copy_context
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from ..core.commands import CommandError, CommandRunner, operation_name, run_command
from ..core.errors import DashpotError
from ..core.event_log import Span, current_event_log, recorded_span
from ..core.model import Diagnostic
from ..core.runtime_events import (
    GitHubRequestAttributes,
    RateLimitKind,
    RateLimitPauseChange,
    RateLimitPauseChanged,
    span_attributes,
)
from ..core.timestamps import observed_instant, utc_stamp

# Every GraphQL query Dashpot sends carries this selection beside its data,
# so the rate limit is observed on the way rather than asked for separately.
RATE_LIMIT_SELECTION = "rateLimit { cost limit remaining resetAt }"

# A GraphQL variable as gh sends it: a string, a typed Int, or a list of
# strings (an ``[ID!]!`` of nodes to look up).
GraphQLVariables = Mapping[str, str | int | Sequence[str]]

# How many requests one refresh may have in flight at once. GitHub asks
# clients to avoid concurrency and caps GraphQL at sixty seconds of CPU time
# a minute; four batches of a second or two each stay well inside that
# while a Source Enumeration of thousands of Issues finishes within its budget.
MAX_IN_FLIGHT = 4

MALFORMED_RESPONSE = "github-malformed-response"
NOT_FOUND = "github-not-found"
RATE_LIMIT = "github-rate-limit"
RATE_LIMIT_LOW = "github-rate-limit-low"
RATE_LIMIT_PAUSED = "github-rate-limit-paused"
REFRESH_BUDGET = "github-refresh-budget"

# How long GraphQL requests are held after a refusal that names no reset time
# Dashpot can use, doubling with each refusal in a row up to the limit. GitHub
# asks a client refused by a secondary limit to wait at least a minute and
# back off exponentially; an hour is the longest a primary window lasts.
PAUSE_BACKOFF = timedelta(minutes=1)
PAUSE_BACKOFF_LIMIT = timedelta(hours=1)

# GitHub's structured GraphQL error types, the first signal read.
_GRAPHQL_ERROR_TYPES = {
    "NOT_FOUND": NOT_FOUND,
    "FORBIDDEN": "github-permission",
    "INSUFFICIENT_SCOPES": "github-permission",
    "RATE_LIMITED": RATE_LIMIT,
    "UNAUTHORIZED": "github-authentication",
}
# ``gh`` names an HTTP failure as ``(HTTP 404)`` after a REST message and as
# ``HTTP 404:`` before one in its other commands; the status is read wherever
# it appears.
_HTTP_STATUS = re.compile(r"\bHTTP (\d{3})\b")
_RATE_LIMIT_TEXT = ("rate limit", "secondary limit", "abuse detection")
# What names a refusal as a secondary limit's rather than the hour's points.
_SECONDARY_LIMIT_TEXT = ("secondary", "abuse detection")


class GitHubRequestError(DashpotError, RuntimeError):
    """A GitHub request that could not answer, with its diagnostic code.

    ``path`` is the GraphQL error path when GitHub reported one, so a caller
    can tell a missing Issue (``("node", "issue")``) from a missing node.
    """

    def __init__(self, code: str, message: str, *, path: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass(frozen=True, slots=True)
class RateLimit:
    """The GraphQL rate limit as GitHub reported it beside one response."""

    cost: int
    limit: int
    remaining: int
    reset_at: str

    @property
    def low(self) -> bool:
        """Fewer than a tenth of the hour's points remain."""
        return self.remaining * 10 < self.limit


@dataclass(frozen=True, slots=True)
class RateLimitPause:
    """A stretch when GraphQL requests are held after GitHub refused one for its rate limit.

    ``until`` is when requests are due to be sent again; ``lifted`` is set
    while a manual refresh's one attempt waits to be sent.
    """

    limit: RateLimitKind
    until: datetime
    lifted: bool = False

    @property
    def until_text(self) -> str:
        """``until`` to the second, in UTC."""
        return f"{self.until.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}"

    @property
    def limit_text(self) -> str:
        """The limit that refused, as a person reads it."""
        return "secondary rate limit" if self.limit == "secondary" else "rate limit"


class LatestRateLimit:
    """The account's rate limit as the gateways sharing it last saw it.

    The limit is the account's, not one gateway's, so every gateway behind
    one dashboard shares one of these: the reading it holds is the latest any
    of them received, whichever query's response carried it. Gateways record
    from the threads their requests run on, so a lock guards the reading, and
    answers to concurrent requests can arrive out of order: within one hour's
    window the points only fall, so a reading showing more points left than
    the one held for the same reset is older, and is not recorded.

    It also holds the Rate Limit Pause: once GitHub refuses one GraphQL
    request for its rate limit, no gateway sharing this one sends another
    until the pause lapses, or a manual refresh's one attempt is answered
    (ADR 0065).
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._lock = threading.Lock()
        self._clock = clock or _utc_now
        self._reading: RateLimit | None = None
        self._pause: RateLimitPause | None = None
        # Refusals in a row, which the first answer after them clears.
        self._refusals = 0
        # Advanced by every refusal that starts a pause, so a request sent
        # before it neither extends that pause nor ends it. While a pause is
        # in force, only its one attempt is sent under the current value.
        self._generation = 0

    @property
    def reading(self) -> RateLimit | None:
        """The last reading recorded, or None before any response carried one."""
        with self._lock:
            return self._reading

    @property
    def pause(self) -> RateLimitPause | None:
        """The Rate Limit Pause in force now, if any."""
        with self._lock:
            pause = self._pause
        if pause is None or self._clock() >= pause.until:
            return None
        return pause

    def record(self, reading: RateLimit) -> None:
        """Hold ``reading`` as the most recent, unless it is older than the one held."""
        with self._lock:
            held = self._reading
            if (
                held is not None
                and held.reset_at == reading.reset_at
                and held.remaining < reading.remaining
            ):
                return
            self._reading = reading

    def admit(self) -> int:
        """Admit one GraphQL request, or hold it while a pause is in force.

        Returns the ticket the request's outcome is reported under. A lifted
        pause admits exactly one request, its attempt, and holds every other
        until that attempt's answer ends the pause or its refusal restarts
        it. The first request admitted after a pause lapses records the lapse.
        """
        with self._lock:
            pause = self._pause
            ticket = self._generation
            if pause is not None and self._clock() < pause.until:
                if not pause.lifted:
                    raise GitHubRequestError(
                        RATE_LIMIT,
                        "GitHub query not sent: GitHub queries are paused until "
                        f"{pause.until_text} after a rate limit refusal",
                    )
                self._pause = replace(pause, lifted=False)
                return ticket
            self._pause = None
        # Recorded outside the lock, like every pause change, so a request
        # on another thread can record its own change first.
        if pause is not None:
            _record_pause("lapsed", pause)
        return ticket

    def answered(self, ticket: int) -> None:
        """Clear the refusals in a row once a request sent since the last one answers.

        A pause still in force was lifted, and this was its attempt: the
        answer ends it.
        """
        with self._lock:
            if ticket != self._generation:
                return
            self._refusals = 0
            pause = self._pause
            self._pause = None
        if pause is not None:
            _record_pause("lifted", pause)

    def refused(self, ticket: int, limit: RateLimitKind) -> None:
        """Pause every sharing gateway after GitHub refused a request for its rate limit.

        A primary refusal waits for the reset the latest reading names when
        that reading showed the hour's points running low and the reset is
        still ahead: the points are then plausibly spent. Any other refusal
        waits a backoff that doubles with each refusal in a row. A request
        sent before the pause started leaves it as it is.
        """
        with self._lock:
            if ticket != self._generation:
                return
            self._generation += 1
            self._refusals += 1
            now = self._clock()
            reading = self._reading
            reset = None if reading is None else observed_instant(reading.reset_at)
            if (
                limit == "primary"
                and reading is not None
                and reading.low
                and reset is not None
                and reset > now
            ):
                until = reset
            else:
                until = now + min(
                    PAUSE_BACKOFF * 2 ** (self._refusals - 1), PAUSE_BACKOFF_LIMIT
                )
            pause = RateLimitPause(limit, until)
            self._pause = pause
        _record_pause("started", pause)

    def lift(self) -> None:
        """Let exactly one request try GitHub before the pause is due to end.

        Its answer ends the pause; a refusal restarts it, keeping the count
        of refusals in a row, so a secondary limit's backoff keeps doubling.
        Failing for any other reason leaves the pause in force, no longer
        lifted.
        """
        with self._lock:
            if self._pause is not None:
                self._pause = replace(self._pause, lifted=True)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _record_pause(change: RateLimitPauseChange, pause: RateLimitPause) -> None:
    """Record a pause changing to the Event Log of the request that saw it."""
    log = current_event_log()
    if log is None:
        return
    log.record(
        RateLimitPauseChanged(
            change=change, limit=pause.limit, until=utc_stamp(pause.until)
        )
    )


def rate_limit_diagnostics(
    reading: RateLimit | None, source: str
) -> tuple[Diagnostic, ...]:
    """Warn while the hour's GraphQL points run low; never fail for it."""
    if reading is None or not reading.low:
        return ()
    return (
        Diagnostic(
            source=source,
            code=RATE_LIMIT_LOW,
            severity="warning",
            message=(
                f"GitHub GraphQL rate limit is low: {reading.remaining} of "
                f"{reading.limit} points remain until {reading.reset_at}; "
                f"the last request cost {reading.cost}"
            ),
        ),
    )


def pause_diagnostics(
    pause: RateLimitPause | None, source: str
) -> tuple[Diagnostic, ...]:
    """Say that GitHub queries are paused, and until when, while a pause is in force."""
    if pause is None:
        return ()
    return (
        Diagnostic(
            source=source,
            code=RATE_LIMIT_PAUSED,
            severity="warning",
            message=(
                f"GitHub queries paused until {pause.until_text} after GitHub "
                f"refused one for its {pause.limit_text}; a manual refresh "
                "tries once"
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class GraphQLResponse:
    """One GraphQL answer: its data, the errors beside it, and its rate limit.

    ``rate_limit`` is the reading this response carried, not the latest the
    gateway holds, so each request can be accounted for by its own.
    """

    data: Mapping[str, Any]
    errors: Sequence[Mapping[str, Any]]
    rate_limit: RateLimit | None


@dataclass(frozen=True, slots=True)
class RefreshBudget:
    """How much one refresh may fetch before it is abandoned as too costly.

    Both bounds are checked before each request, so a refresh overruns by at
    most the requests in flight plus the command timeout. The default covers
    a Source Enumeration of about two and a half thousand Issues in batches of
    twenty-four beside the probe, the delta and the nested pages.
    """

    seconds: float = 60.0
    requests: int = 120

    def start(self, monotonic: Callable[[], float] = time.monotonic) -> RefreshMeter:
        return RefreshMeter(self, monotonic)


DEFAULT_REFRESH_BUDGET = RefreshBudget()


class RefreshMeter:
    """One refresh's spend against its budget."""

    def __init__(self, budget: RefreshBudget, monotonic: Callable[[], float]) -> None:
        self.budget = budget
        self._monotonic = monotonic
        # The monotonic moment the refresh started, which is also the
        # refresh's one reading of "now" for anything it schedules by.
        self.started = monotonic()
        self.requests = 0

    @property
    def elapsed(self) -> float:
        return self._monotonic() - self.started

    def next_request(self, fetched: str) -> None:
        """Spend one request, refusing when the budget is already exhausted.

        ``fetched`` names what the refresh has so far, so the diagnostic says
        what was fetched before the refresh was abandoned.
        """
        elapsed = self.elapsed
        budget = self.budget
        if self.requests >= budget.requests or elapsed > budget.seconds:
            raise GitHubRequestError(
                REFRESH_BUDGET,
                f"GitHub refresh abandoned after {self.requests} requests in "
                f"{elapsed:.1f}s with {fetched}; the budget is "
                f"{budget.requests} requests or {budget.seconds:g}s",
            )
        self.requests += 1


class GitHubGateway:
    """Run `gh` for one Repository and read GitHub's answer."""

    def __init__(
        self,
        root: Path,
        *,
        timeout: float = 10,
        runner: CommandRunner = run_command,
        latest_rate_limit: LatestRateLimit | None = None,
    ) -> None:
        self.root = root
        self.timeout = timeout
        self.runner = runner
        self.latest_rate_limit = latest_rate_limit or LatestRateLimit()

    @property
    def rate_limit(self) -> RateLimit | None:
        """The rate limit beside the latest GraphQL answer to any sharing gateway."""
        return self.latest_rate_limit.reading

    def graphql(
        self,
        query: str,
        variables: GraphQLVariables,
        *,
        tolerated: Container[str] = (),
    ) -> Mapping[str, Any]:
        """Run one GraphQL query and return its ``data`` object.

        ``tolerated`` names the GraphQL error types that leave the data
        usable — a ``NOT_FOUND`` beside a ``nodes(ids:)`` lookup marks one
        position null while its siblings answer — so a response whose every
        error is tolerated is returned rather than raised.
        """
        with (
            self._unless_paused(),
            _request_span("graphql", operation_name(query)) as span,
        ):
            payload = self._graphql_payload(query, variables, tolerated=tolerated)
            errors = payload.get("errors")
            if errors is not None and not isinstance(errors, list):
                raise GitHubRequestError(
                    MALFORMED_RESPONSE,
                    "GitHub response has a malformed GraphQL errors value",
                )
            if errors and not _all_tolerated(errors, tolerated):
                raise graphql_failure(errors)
            data = payload.get("data")
            if not isinstance(data, Mapping):
                raise GitHubRequestError(
                    MALFORMED_RESPONSE, "GitHub response has no data object"
                )
            _record_reading(span, self._read_rate_limit(data))
            return data

    def graphql_result(
        self, query: str, variables: GraphQLVariables
    ) -> GraphQLResponse:
        """Expose attributable GraphQL errors beside the data they leave usable."""
        with (
            self._unless_paused(),
            _request_span("graphql", operation_name(query)) as span,
        ):
            payload = self._graphql_payload(query, variables, partial=True)
            errors = payload.get("errors", [])
            if not isinstance(errors, list) or not all(
                isinstance(error, Mapping) for error in errors
            ):
                raise GitHubRequestError(
                    MALFORMED_RESPONSE, "GitHub errors are malformed"
                )
            data = payload.get("data")
            if not isinstance(data, Mapping):
                if errors:
                    raise graphql_failure(errors)
                raise GitHubRequestError(
                    MALFORMED_RESPONSE, "GitHub response has no data object"
                )
            reading = self._read_rate_limit(data)
            _record_reading(span, reading)
            return GraphQLResponse(data, errors, reading)

    @contextmanager
    def _unless_paused(self) -> Iterator[None]:
        """Send one GraphQL request only outside a pause, and report how it went.

        A held request raises before it is sent, so it is no request span
        and spends nothing; a rate limit refusal pauses every gateway that
        shares this one's rate limit.
        """
        latest = self.latest_rate_limit
        ticket = latest.admit()
        try:
            yield
        except GitHubRequestError as exc:
            if exc.code == RATE_LIMIT:
                latest.refused(ticket, rate_limit_kind(str(exc)))
            raise
        latest.answered(ticket)

    def _read_rate_limit(self, data: Mapping[str, Any]) -> RateLimit | None:
        """Read the rate limit a response's data carries and record it as the latest."""
        reading = _rate_limit(data.get("rateLimit"))
        if reading is not None:
            self.latest_rate_limit.record(reading)
        return reading

    def _graphql_payload(
        self,
        query: str,
        variables: GraphQLVariables,
        *,
        tolerated: Container[str] = (),
        partial: bool = False,
    ) -> Mapping[str, Any]:
        args = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            if isinstance(value, str):
                args.extend(["-f", f"{key}={value}"])
            elif isinstance(value, int):
                # -F sends an integer as a typed GraphQL Int variable; -f
                # would send it as a String and fail the variable declaration.
                args.extend(["-F", f"{key}={value}"])
            else:
                # gh's key[]=value form appends to a list variable.
                args.extend(
                    part for item in value for part in ("-f", f"{key}[]={item}")
                )
        return self._run(args, tolerated=tolerated, partial=partial)

    def graphql_many(
        self,
        query: str,
        variables: Sequence[GraphQLVariables],
        *,
        tolerated: Container[str] = (),
    ) -> list[Mapping[str, Any]]:
        """Run one query for each set of variables, at most MAX_IN_FLIGHT at once.

        Answers come back in the order asked; the first failure is raised
        once the requests already running have finished. Each request is a
        span of its own under the caller's, with its own rate limit reading.
        """
        if len(variables) <= 1:
            return [
                self.graphql(query, each, tolerated=tolerated) for each in variables
            ]
        with ThreadPoolExecutor(
            max_workers=min(MAX_IN_FLIGHT, len(variables)), thread_name_prefix="gh"
        ) as executor:
            # Each request runs in its own copy of this thread's context, so
            # the registry an exit interrupts reaches the fanned-out commands,
            # and each request's span is a child of the span current here.
            def request(context: Context, each: GraphQLVariables) -> Mapping[str, Any]:
                return context.run(self.graphql, query, each, tolerated=tolerated)

            futures = [
                executor.submit(request, copy_context(), each) for each in variables
            ]
            try:
                return [future.result() for future in futures]
            except BaseException:
                executor.shutdown(wait=True, cancel_futures=True)
                raise

    def rest(self, path: str) -> Mapping[str, Any]:
        """Run one REST request and return its JSON object."""
        with _request_span("rest"):
            return self._run(["gh", "api", path])

    def _run(
        self, args: list[str], *, tolerated: Container[str] = (), partial: bool = False
    ) -> Mapping[str, Any]:
        try:
            result = self.runner(args, self.root, self.timeout)
        except (OSError, CommandError) as exc:
            # The runner maps a missing gh and a timeout to CommandError; any
            # other failure to run it (a permission error, an exhausted
            # process table) is the same refusal to reach GitHub.
            raise GitHubRequestError(classify_failure_text(str(exc)), str(exc)) from exc
        payload = _json_object(result.stdout)
        if result.returncode != 0:
            # gh echoes GitHub's JSON body before its own one-line stderr, so
            # the structured error is read first and the text only without it.
            if isinstance(payload, Mapping):
                errors = payload.get("errors")
                if isinstance(errors, list) and errors:
                    # gh exits non-zero whenever errors are present, even
                    # beside data every tolerated error leaves usable.
                    if partial or _all_tolerated(errors, tolerated):
                        return payload
                    raise graphql_failure(errors)
                message = payload.get("message")
                status = payload.get("status")
                if isinstance(message, str) and message:
                    text = message
                    if isinstance(status, str):
                        text = f"{message} (HTTP {status})"
                    raise GitHubRequestError(classify_failure_text(text), text)
            message = (
                result.stderr.strip()
                or f"{' '.join(args[:3])} exited {result.returncode}"
            )
            raise GitHubRequestError(classify_failure_text(message), message)
        if payload is None:
            raise GitHubRequestError(
                MALFORMED_RESPONSE, "GitHub returned malformed JSON"
            )
        if not isinstance(payload, Mapping):
            raise GitHubRequestError(
                MALFORMED_RESPONSE, "GitHub response is not an object"
            )
        return payload


def _request_span(
    api: Literal["graphql", "rest"], operation: str | None = None
) -> AbstractContextManager[Span | None]:
    """Time one GitHub request as a span written at ``standard``.

    Every request is written, so the points and requests a dashboard spends
    are always countable. A failed request names its Diagnostic code, never
    GitHub's or ``gh``'s text.
    """
    return recorded_span(
        "github.request",
        attributes=span_attributes(
            GitHubRequestAttributes, api=api, operation=operation
        ),
        level="standard",
    )


def _record_reading(span: Span | None, reading: RateLimit | None) -> None:
    """Record the rate limit reading beside one request's response on its span."""
    if span is None or reading is None or span.attributes is None:
        return
    attributes = span_attributes(
        GitHubRequestAttributes,
        **{
            **span.attributes.model_dump(),
            "cost": reading.cost,
            "limit": reading.limit,
            "remaining": reading.remaining,
            "reset_at": reading.reset_at,
        },
    )
    if attributes is not None:
        span.set_attributes(attributes)


def classify_failure_text(message: str) -> str:
    """Name the diagnostic code of a failure GitHub or gh described in prose.

    The structured signals — a GraphQL error type, an HTTP status — are read
    by the gateway before this is consulted; the substrings are the last
    resort for text gh localises or GitHub rewords, with permission checked
    before authentication so a forbidden resource is never an expired login.
    """
    normalized = message.casefold()
    status_match = _HTTP_STATUS.search(message)
    if status_match:
        code = _status_code(status_match.group(1), normalized)
        if code is not None:
            return code
    if "command not found" in normalized:
        return "github-cli-unavailable"
    if "timed out" in normalized or "timeout" in normalized:
        return "github-timeout"
    if any(text in normalized for text in _RATE_LIMIT_TEXT):
        return RATE_LIMIT
    if any(
        text in normalized
        for text in (
            "forbidden",
            "permission",
            "resource not accessible",
            "insufficient scope",
            "saml enforcement",
        )
    ):
        return "github-permission"
    if any(
        text in normalized
        for text in ("bad credentials", "not logged", "authentication", "unauthorized")
    ):
        return "github-authentication"
    if any(
        text in normalized
        for text in ("could not resolve to a repository", "repository not found")
    ):
        return "github-repository"
    if "could not resolve to a" in normalized or "not found" in normalized:
        return NOT_FOUND
    if any(
        text in normalized
        for text in (
            "network",
            "connection",
            "could not resolve host",
            "error connecting",
        )
    ):
        return "github-network"
    return "github-request"


def rate_limit_kind(message: str) -> RateLimitKind:
    """Name the limit a rate limit refusal describes: secondary only when it says so.

    GitHub names a secondary limit, or its older abuse detection, in the
    refusal's text; a refusal that names neither is read as the primary
    limit on the hour's points.
    """
    normalized = message.casefold()
    if any(text in normalized for text in _SECONDARY_LIMIT_TEXT):
        return "secondary"
    return "primary"


def _status_code(status: str, normalized: str) -> str | None:
    if status == "401":
        return "github-authentication"
    if status == "403":
        if any(text in normalized for text in _RATE_LIMIT_TEXT):
            return RATE_LIMIT
        return "github-permission"
    if status == "404":
        return NOT_FOUND
    if status == "429":
        return RATE_LIMIT
    if status.startswith("5"):
        return "github-unavailable"
    return None


def _all_tolerated(errors: Sequence[object], tolerated: Container[str]) -> bool:
    for error in errors:
        if not isinstance(error, Mapping):
            return False
        error_type = error.get("type")
        if not isinstance(error_type, str) or error_type not in tolerated:
            return False
    return True


def graphql_failure(errors: Sequence[object]) -> GitHubRequestError:
    """Read a GraphQL ``errors`` list: its first typed error names the code."""
    messages: list[str] = []
    code: str | None = None
    path: tuple[str, ...] = ()
    for error in errors:
        if not isinstance(error, Mapping):
            continue
        message = error.get("message")
        if isinstance(message, str):
            messages.append(message)
        if code is None:
            error_type = error.get("type")
            if isinstance(error_type, str) and error_type in _GRAPHQL_ERROR_TYPES:
                code = _GRAPHQL_ERROR_TYPES[error_type]
                raw_path = error.get("path")
                if isinstance(raw_path, list):
                    path = tuple(str(part) for part in raw_path)
    message = "; ".join(messages) or "GitHub GraphQL request failed"
    return GitHubRequestError(
        code or classify_failure_text(message), message, path=path
    )


def _rate_limit(value: object) -> RateLimit | None:
    """Read the rate limit beside a response; a malformed one is left unread."""
    if not isinstance(value, Mapping):
        return None
    numbers: dict[str, int] = {}
    for field in ("cost", "limit", "remaining"):
        number = value.get(field)
        if not isinstance(number, int) or isinstance(number, bool) or number < 0:
            return None
        numbers[field] = number
    reset_at = value.get("resetAt")
    if not isinstance(reset_at, str) or not reset_at:
        return None
    return RateLimit(reset_at=reset_at, **numbers)


def _json_object(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class CursorTrail:
    """The cursors one connection has been followed through.

    A missing or repeated cursor is a pagination fault, so a source can never
    loop on a cursor GitHub keeps returning.
    """

    def __init__(self, subject: str) -> None:
        self.subject = subject
        self._seen: set[str] = set()

    def follow(self, end_cursor: object) -> str:
        if not isinstance(end_cursor, str) or not end_cursor:
            raise GitHubRequestError(
                "github-pagination",
                f"{self.subject} has another page but no end cursor",
            )
        if end_cursor in self._seen:
            raise GitHubRequestError(
                "github-pagination",
                f"{self.subject} repeated pagination cursor {end_cursor}",
            )
        self._seen.add(end_cursor)
        return end_cursor
