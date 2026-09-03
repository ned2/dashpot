"""Ask GitHub through one gateway: `gh` invocation, classification, budget.

Every module that asks GitHub a question goes through :class:`GitHubGateway`,
so the way a failure is read, the way a page cursor is followed, the rate
limit GitHub reports, and the bound on how much one refresh may fetch each
live in exactly one place.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Container, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import CommandRunner, run_command
from .errors import DashpotError

# Every GraphQL query Dashpot sends carries this selection beside its data,
# so the rate limit is observed on the way rather than asked for separately.
RATE_LIMIT_SELECTION = "rateLimit { cost limit remaining resetAt }"

# A GraphQL variable as gh sends it: a string, a typed Int, or a list of
# strings (an ``[ID!]!`` of nodes to look up).
GraphQLVariables = Mapping[str, str | int | Sequence[str]]

# How many requests one refresh may have in flight at once. GitHub asks
# clients to avoid concurrency and caps GraphQL at sixty seconds of CPU time
# a minute; four batches of a second or two each stay well inside that
# while a Reconciliation of thousands of Issues finishes within its budget.
MAX_IN_FLIGHT = 4

MALFORMED_RESPONSE = "github-malformed-response"
NOT_FOUND = "github-not-found"
REFRESH_BUDGET = "github-refresh-budget"

# GitHub's structured GraphQL error types, the first signal read.
_GRAPHQL_ERROR_TYPES = {
    "NOT_FOUND": NOT_FOUND,
    "FORBIDDEN": "github-permission",
    "INSUFFICIENT_SCOPES": "github-permission",
    "RATE_LIMITED": "github-rate-limit",
    "UNAUTHORIZED": "github-authentication",
}
# ``gh`` names an HTTP failure as ``(HTTP 404)`` after a REST message and as
# ``HTTP 404:`` before one in its other commands; the status is read wherever
# it appears.
_HTTP_STATUS = re.compile(r"\bHTTP (\d{3})\b")
_RATE_LIMIT_TEXT = ("rate limit", "secondary limit", "abuse detection")


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
class RefreshBudget:
    """How much one refresh may fetch before it is abandoned as too costly.

    Both bounds are checked before each request, so a refresh overruns by at
    most the requests in flight plus the command timeout. The default covers
    a Reconciliation of about two and a half thousand Issues in batches of
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
    ) -> None:
        self.root = root
        self.timeout = timeout
        self.runner = runner
        # The rate limit GitHub reported beside the latest GraphQL answer.
        self.rate_limit: RateLimit | None = None

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
        payload = self._run(args, tolerated=tolerated)
        errors = payload.get("errors")
        if errors is not None and not isinstance(errors, list):
            raise GitHubRequestError(
                MALFORMED_RESPONSE,
                "GitHub response has a malformed GraphQL errors value",
            )
        if errors and not _all_tolerated(errors, tolerated):
            raise _graphql_failure(errors)
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise GitHubRequestError(
                MALFORMED_RESPONSE, "GitHub response has no data object"
            )
        rate_limit = _rate_limit(data.get("rateLimit"))
        if rate_limit is not None:
            self.rate_limit = rate_limit
        return data

    def graphql_many(
        self,
        query: str,
        variables: Sequence[GraphQLVariables],
        *,
        tolerated: Container[str] = (),
    ) -> list[Mapping[str, Any]]:
        """Run one query for each set of variables, at most MAX_IN_FLIGHT at once.

        Answers come back in the order asked. The first failure is raised
        once the requests already running have finished, and the ones not
        yet started are never sent.
        """
        if len(variables) <= 1:
            return [
                self.graphql(query, each, tolerated=tolerated) for each in variables
            ]
        with ThreadPoolExecutor(
            max_workers=min(MAX_IN_FLIGHT, len(variables)), thread_name_prefix="gh"
        ) as executor:
            futures = [
                executor.submit(self.graphql, query, each, tolerated=tolerated)
                for each in variables
            ]
            try:
                return [future.result() for future in futures]
            except BaseException:
                executor.shutdown(wait=True, cancel_futures=True)
                raise

    def rest(self, path: str) -> Mapping[str, Any]:
        """Run one REST request and return its JSON object."""
        return self._run(["gh", "api", path])

    def _run(
        self, args: list[str], *, tolerated: Container[str] = ()
    ) -> Mapping[str, Any]:
        try:
            result = self.runner(args, self.root, self.timeout)
        except (OSError, RuntimeError) as exc:
            # The runner maps a missing gh and a timeout to RuntimeError; any
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
                    if _all_tolerated(errors, tolerated):
                        return payload
                    raise _graphql_failure(errors)
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
        return "github-rate-limit"
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


def _status_code(status: str, normalized: str) -> str | None:
    if status == "401":
        return "github-authentication"
    if status == "403":
        if any(text in normalized for text in _RATE_LIMIT_TEXT):
            return "github-rate-limit"
        return "github-permission"
    if status == "404":
        return NOT_FOUND
    if status == "429":
        return "github-rate-limit"
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


def _graphql_failure(errors: Sequence[object]) -> GitHubRequestError:
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
