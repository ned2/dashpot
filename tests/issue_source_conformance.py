from __future__ import annotations

import unittest
from typing import Any

from dashpot.issue_sources import IssueSourceObservation


def assert_fresh_observation(
    test: unittest.TestCase,
    observation: IssueSourceObservation,
    *,
    attempted_at: str,
    expected_issues: list[dict[str, Any]],
) -> None:
    test.assertEqual("fresh", observation.status)
    test.assertEqual(attempted_at, observation.attempted_at)
    test.assertEqual(attempted_at, observation.last_good_at)
    test.assertEqual(expected_issues, observation.issues)
    test.assertEqual([], observation.diagnostics)


def assert_unavailable_observation(
    test: unittest.TestCase,
    observation: IssueSourceObservation,
    *,
    attempted_at: str,
    source_name: str,
    diagnostic_code: str,
) -> None:
    test.assertEqual("unavailable", observation.status)
    test.assertEqual(attempted_at, observation.attempted_at)
    test.assertIsNone(observation.last_good_at)
    test.assertEqual([], observation.issues)
    test.assertEqual(1, len(observation.diagnostics))
    diagnostic = observation.diagnostics[0]
    test.assertEqual(source_name, diagnostic.source)
    test.assertEqual(diagnostic_code, diagnostic.code)
    test.assertEqual("error", diagnostic.severity)
    test.assertTrue(diagnostic.message)


def assert_stale_observation(
    test: unittest.TestCase,
    observation: IssueSourceObservation,
    *,
    attempted_at: str,
    last_good_at: str,
    source_name: str,
    diagnostic_code: str,
    expected_issues: list[dict[str, Any]],
) -> None:
    test.assertEqual("stale", observation.status)
    test.assertEqual(attempted_at, observation.attempted_at)
    test.assertEqual(last_good_at, observation.last_good_at)
    test.assertEqual(expected_issues, observation.issues)
    test.assertEqual(1, len(observation.diagnostics))
    diagnostic = observation.diagnostics[0]
    test.assertEqual(source_name, diagnostic.source)
    test.assertEqual(diagnostic_code, diagnostic.code)
    test.assertEqual("warning", diagnostic.severity)
    test.assertTrue(diagnostic.message)
