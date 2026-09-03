"""The GitHub gateway: how a failure is read, a cursor followed, a refresh bounded."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dashpot.commands import CommandResult
from dashpot.github import (
    CursorTrail,
    GitHubGateway,
    GitHubRequestError,
    RefreshBudget,
    classify_failure_text,
)

QUERY = "query { rateLimit { cost limit remaining resetAt } viewer { login } }"


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult([], returncode, stdout, stderr)


class RecordingRunner:
    def __init__(self, *results: CommandResult | Exception) -> None:
        self.results = iter(results)
        self.calls: list[tuple[list[str], Path, float]] = []

    def __call__(self, args, cwd, timeout):
        self.calls.append((list(args), cwd, timeout))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def gateway(*results: CommandResult | Exception) -> GitHubGateway:
    return GitHubGateway(Path("/repo"), timeout=7, runner=RecordingRunner(*results))


def graphql_failure(*, type: str, path: list[str | int], message: str) -> CommandResult:
    """The shape a real ``gh api graphql`` failure takes: body first, prose after."""
    body = json.dumps(
        {
            "data": {"node": None},
            "errors": [
                {"type": type, "path": path, "locations": [], "message": message}
            ],
        }
    )
    return completed(stdout=body, stderr=f"gh: {message}", returncode=1)


class ClassificationTests(unittest.TestCase):
    def test_graphql_error_type_is_read_before_any_prose(self) -> None:
        # The message alone would read as a repository fault; the type wins.
        result = graphql_failure(
            type="FORBIDDEN",
            path=["node"],
            message="Could not resolve to a Repository; bad credentials",
        )

        with self.assertRaises(GitHubRequestError) as caught:
            gateway(result).graphql(QUERY, {})

        self.assertEqual("github-permission", caught.exception.code)
        self.assertEqual(("node",), caught.exception.path)

    def test_a_missing_issue_is_not_found_at_its_path(self) -> None:
        result = graphql_failure(
            type="NOT_FOUND",
            path=["node", "issue"],
            message="Could not resolve to an Issue with the number of 999999.",
        )

        with self.assertRaises(GitHubRequestError) as caught:
            gateway(result).graphql(QUERY, {})

        self.assertEqual("github-not-found", caught.exception.code)
        self.assertEqual(("node", "issue"), caught.exception.path)
        self.assertIn("999999", str(caught.exception))

    def test_rest_failure_reads_the_status_after_the_message(self) -> None:
        body = json.dumps({"message": "Not Found", "status": "404"})
        result = completed(stdout=body, stderr="gh: Not Found (HTTP 404)", returncode=1)

        with self.assertRaises(GitHubRequestError) as caught:
            gateway(result).rest("repos/ned2/missing")

        self.assertEqual("github-not-found", caught.exception.code)
        self.assertEqual("Not Found (HTTP 404)", str(caught.exception))

    def test_prose_without_a_body_is_read_by_status_then_text(self) -> None:
        cases = [
            ("HTTP 401: Bad credentials", "github-authentication"),
            (
                "gh: Resource not accessible by integration (HTTP 403)",
                "github-permission",
            ),
            ("gh: API rate limit exceeded for user (HTTP 403)", "github-rate-limit"),
            ("gh: Not Found (HTTP 404)", "github-not-found"),
            (
                "gh: You have exceeded a secondary rate limit (HTTP 429)",
                "github-rate-limit",
            ),
            ("gh: Server Error (HTTP 502)", "github-unavailable"),
            ("error connecting to api.github.com", "github-network"),
            ("something unexpected", "github-request"),
        ]
        for stderr, expected in cases:
            with self.subTest(stderr=stderr):
                with self.assertRaises(GitHubRequestError) as caught:
                    gateway(completed(stderr=stderr, returncode=1)).graphql(QUERY, {})
                self.assertEqual(expected, caught.exception.code)
                self.assertEqual(stderr, str(caught.exception))

    def test_permission_prose_is_never_read_as_an_expired_login(self) -> None:
        # Both families of words in one message: the resource, not the login,
        # is what GitHub refused.
        text = "Resource not accessible by integration; check your authentication"

        self.assertEqual("github-permission", classify_failure_text(text))

    def test_runner_failures_keep_their_own_codes(self) -> None:
        cases = [
            (RuntimeError("command timed out after 7s: gh"), "github-timeout"),
            (RuntimeError("command not found: gh"), "github-cli-unavailable"),
            (OSError("[Errno 24] Too many open files"), "github-request"),
        ]
        for failure, expected in cases:
            with self.subTest(code=expected):
                with self.assertRaises(GitHubRequestError) as caught:
                    gateway(failure).graphql(QUERY, {})
                self.assertEqual(expected, caught.exception.code)

    def test_errors_beside_data_fail_the_request_even_on_exit_zero(self) -> None:
        body = json.dumps(
            {
                "data": {"viewer": {"login": "ned2"}},
                "errors": [{"message": "Resource not accessible by integration"}],
            }
        )

        with self.assertRaises(GitHubRequestError) as caught:
            gateway(completed(body)).graphql(QUERY, {})

        self.assertEqual("github-permission", caught.exception.code)
        self.assertEqual((), caught.exception.path)

    def test_malformed_answers_are_malformed_response(self) -> None:
        cases = [
            ("not-json", "GitHub returned malformed JSON"),
            ("[]", "GitHub response is not an object"),
            (json.dumps({"errors": "no"}), "malformed GraphQL errors value"),
            (json.dumps({"data": "no"}), "no data object"),
        ]
        for stdout, detail in cases:
            with self.subTest(stdout=stdout):
                with self.assertRaises(GitHubRequestError) as caught:
                    gateway(completed(stdout)).graphql(QUERY, {})
                self.assertEqual("github-malformed-response", caught.exception.code)
                self.assertIn(detail, str(caught.exception))


class RequestTests(unittest.TestCase):
    def test_variables_are_typed_by_their_python_type(self) -> None:
        runner = RecordingRunner(completed(json.dumps({"data": {}})))
        gate = GitHubGateway(Path("/repo"), timeout=7, runner=runner)

        gate.graphql(QUERY, {"id": "R_1", "number": 9})

        args, cwd, timeout = runner.calls[0]
        self.assertEqual(["gh", "api", "graphql", "-f", f"query={QUERY}"], args[:5])
        self.assertEqual(["-f", "id=R_1", "-F", "number=9"], args[5:])
        self.assertEqual((Path("/repo"), 7), (cwd, timeout))

    def test_a_list_variable_is_sent_one_item_per_flag(self) -> None:
        runner = RecordingRunner(completed(json.dumps({"data": {}})))
        gate = GitHubGateway(Path("/repo"), runner=runner)

        gate.graphql(QUERY, {"ids": ["I_1", "I_2"]})

        self.assertEqual(["-f", "ids[]=I_1", "-f", "ids[]=I_2"], runner.calls[0][0][5:])

    def test_a_tolerated_error_leaves_the_answer_usable(self) -> None:
        body = json.dumps(
            {
                "data": {"nodes": [{"id": "I_1"}, None]},
                "errors": [
                    {"type": "NOT_FOUND", "path": ["nodes", 1], "message": "gone"}
                ],
            }
        )
        # gh exits 1 whenever errors are present, whatever the data beside.
        answered = completed(stdout=body, stderr="gh: gone", returncode=1)

        data = gateway(answered).graphql(
            QUERY, {"ids": ["I_1", "I_2"]}, tolerated=frozenset({"NOT_FOUND"})
        )

        self.assertEqual([{"id": "I_1"}, None], data["nodes"])

    def test_an_error_outside_the_tolerated_types_still_fails(self) -> None:
        for errors in (
            [
                {"type": "NOT_FOUND", "path": ["nodes", 0], "message": "gone"},
                {"type": "FORBIDDEN", "path": ["nodes", 1], "message": "no"},
            ],
            [{"path": ["nodes", 0], "message": "untyped"}],
        ):
            with self.subTest(errors=errors):
                body = json.dumps({"data": {"nodes": [None, None]}, "errors": errors})
                answered = completed(stdout=body, stderr="gh: failed", returncode=1)
                with self.assertRaises(GitHubRequestError):
                    gateway(answered).graphql(
                        QUERY,
                        {"ids": ["I_1", "I_2"]},
                        tolerated=frozenset({"NOT_FOUND"}),
                    )

    def test_the_rate_limit_is_read_beside_every_answer(self) -> None:
        answered = json.dumps(
            {
                "data": {
                    "rateLimit": {
                        "cost": 6,
                        "limit": 5000,
                        "remaining": 400,
                        "resetAt": "2026-09-04T01:00:00Z",
                    },
                    "viewer": {"login": "ned2"},
                }
            }
        )
        gate = gateway(
            completed(answered),
            completed(json.dumps({"data": {"rateLimit": {"cost": "x"}}})),
        )

        data = gate.graphql(QUERY, {})
        self.assertEqual({"login": "ned2"}, data["viewer"])
        rate_limit = gate.rate_limit
        assert rate_limit is not None
        self.assertEqual(
            (6, 5000, 400, "2026-09-04T01:00:00Z"),
            (
                rate_limit.cost,
                rate_limit.limit,
                rate_limit.remaining,
                rate_limit.reset_at,
            ),
        )
        self.assertTrue(rate_limit.low)

        # A malformed block leaves the last well-formed reading in place.
        gate.graphql(QUERY, {})
        self.assertIs(rate_limit, gate.rate_limit)

    def test_rest_returns_the_object(self) -> None:
        gate = gateway(completed(json.dumps({"node_id": "R_1", "full_name": "a/b"})))

        self.assertEqual({"node_id": "R_1", "full_name": "a/b"}, gate.rest("repos/a/b"))


class CursorTrailTests(unittest.TestCase):
    def test_a_missing_or_repeated_cursor_is_a_pagination_fault(self) -> None:
        trail = CursorTrail("Issue collection")

        self.assertEqual("c1", trail.follow("c1"))
        self.assertEqual("c2", trail.follow("c2"))
        for bad in (None, "", "c1"):
            with self.subTest(cursor=bad):
                with self.assertRaises(GitHubRequestError) as caught:
                    trail.follow(bad)
                self.assertEqual("github-pagination", caught.exception.code)
                self.assertIn("Issue collection", str(caught.exception))


class RefreshBudgetTests(unittest.TestCase):
    def test_pages_are_spent_until_the_count_is_exhausted(self) -> None:
        meter = RefreshBudget(seconds=60, pages=2).start(lambda: 0.0)

        meter.next_page("0 Issues")
        meter.next_page("100 Issues")
        with self.assertRaises(GitHubRequestError) as caught:
            meter.next_page("200 Issues")

        self.assertEqual("github-refresh-budget", caught.exception.code)
        self.assertEqual(
            "GitHub refresh abandoned after 2 pages in 0.0s with 200 Issues; "
            "the budget is 2 pages or 60s",
            str(caught.exception),
        )

    def test_time_is_checked_before_each_page(self) -> None:
        clock = iter([0.0, 1.0, 61.5])
        meter = RefreshBudget(seconds=60, pages=25).start(lambda: next(clock))

        meter.next_page("0 Issues")
        with self.assertRaises(GitHubRequestError) as caught:
            meter.next_page("100 Issues")

        self.assertIn("after 1 pages in 61.5s with 100 Issues", str(caught.exception))
        self.assertEqual(1, meter.pages)


if __name__ == "__main__":
    unittest.main()
