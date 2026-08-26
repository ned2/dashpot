from __future__ import annotations

import unittest
from pathlib import Path

from dashpot.commands import CommandResult
from dashpot.correlation import correlate
from dashpot.model import AgentRun
from dashpot.sources import GitHubIssuesSource, LocalTasksSource


HERE = Path(__file__).parent


def fixture(name: str) -> str:
    return (HERE / "fixtures" / name).read_text()


class SequenceRunner:
    def __init__(self, results: list[CommandResult | Exception]) -> None:
        self.results = iter(results)
        self.calls: list[tuple[list[str], Path, float]] = []

    def __call__(self, args, cwd, timeout):
        self.calls.append((list(args), cwd, timeout))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult([], returncode, stdout, stderr)


class TaskSourceTests(unittest.TestCase):
    def test_local_normalizes_declared_states_and_stable_ids(self) -> None:
        source = LocalTasksSource(
            Path("/fixture"),
            runner=SequenceRunner([completed(fixture("tasks-list.json"))]),
        )

        result = source.refresh()

        self.assertEqual("fresh", result.status)
        self.assertEqual(3, len(result.tasks))
        self.assertFalse(result.tasks[0].declared_blocked)
        self.assertEqual("@agent-7", result.tasks[1].declared_claimant)
        self.assertTrue(result.tasks[2].declared_blocked)
        self.assertEqual("tasks-md:/fixture:TASKS.md:17", result.tasks[2].key)

    def test_failure_after_success_retains_last_good_data(self) -> None:
        source = LocalTasksSource(
            Path("/fixture"),
            runner=SequenceRunner(
                [completed(fixture("tasks-list.json")), completed("not-json")]
            ),
        )
        fresh = source.refresh()

        stale = source.refresh()

        self.assertEqual("stale", stale.status)
        self.assertEqual(fresh.tasks, stale.tasks)
        self.assertEqual(fresh.last_good_at, stale.last_good_at)
        self.assertIn("malformed JSON", stale.diagnostic.message if stale.diagnostic else "")

    def test_initial_failure_is_unavailable(self) -> None:
        source = LocalTasksSource(
            Path("/fixture"),
            runner=SequenceRunner([completed(stderr="boom", returncode=1)]),
        )

        result = source.refresh()

        self.assertEqual("unavailable", result.status)
        self.assertEqual([], result.tasks)
        self.assertIn("boom", result.diagnostic.message if result.diagnostic else "")

    def test_github_normalizes_labels_and_assignee(self) -> None:
        runner = SequenceRunner([completed(fixture("gh-issue-list.json"))])
        source = GitHubIssuesSource(Path("/fixture"), "example/project", runner=runner)

        result = source.refresh()

        task = result.tasks[0]
        self.assertEqual("github:example/project#17", task.key)
        self.assertEqual("P1", task.priority)
        self.assertEqual(["observability"], task.tags)
        self.assertEqual("ned2", task.declared_claimant)
        self.assertEqual("unknown", task.declared_blocked)
        self.assertEqual("tasks.md", runner.calls[0][0][6])


class CorrelationTests(unittest.TestCase):
    def test_only_explicit_branch_conventions_are_matched(self) -> None:
        tasks = GitHubIssuesSource(
            Path("/fixture"),
            "example/project",
            runner=SequenceRunner([completed(fixture("gh-issue-list.json"))]),
        ).refresh().tasks
        explicit = AgentRun(
            "process:1", "codex", "1", "running", "/fixture", "/fixture", "issue/17", None
        )
        fuzzy = AgentRun(
            "process:2",
            "codex",
            "2",
            "running",
            "/fixture",
            "/fixture",
            "show-stale-repository-snapshots-17",
            None,
        )

        correlate(tasks, [explicit, fuzzy])

        self.assertEqual("github:example/project#17", explicit.declared_work_key)
        self.assertIsNone(fuzzy.declared_work_key)
        self.assertEqual(["process:1"], tasks[0].observed_runs)


if __name__ == "__main__":
    unittest.main()
