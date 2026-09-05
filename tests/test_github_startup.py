"""Pin startup's request dependencies and live-evidence publication barrier."""

from __future__ import annotations

import json
import threading

import pytest
from typing_extensions import override

from dashpot.commands import CommandResult
from dashpot.github import RefreshBudget
from dashpot.github_issue_snapshot import GitHubIssueSnapshotStore
from test_github_issues import (
    PROJECT_ID,
    REPOSITORY_ID,
    RoutedRunner,
    SequenceRunner,
    _linked_numbers,
    by_id,
    completed,
    graphql_failure,
    issue_page,
    issue_record,
    nodes_response,
    probe_response,
    pull_request_change,
    pull_request_changes_page,
    query_of,
    related,
    source,
    unrelated,
    with_linked_pull_requests,
)

MARK = "2026-08-26T09:00:00Z"
LATER = "2026-08-26T10:00:00Z"
FUTURE = "2099-01-01T00:00:00Z"


def seed_store(root, records, *, settled=None, candidate=None, high_water=MARK):
    store = GitHubIssueSnapshotStore(root)
    first = source(
        SequenceRunner([completed(issue_page(records))]), snapshot_store=store
    ).refresh()
    assert first.status == "fresh"
    seed = store.load(repository_id=REPOSITORY_ID, project_id=PROJECT_ID)
    assert seed is not None
    store.replace(
        seed.model_copy(
            update={
                "high_water": high_water,
                "pull_request_marks": seed.pull_request_marks.model_copy(
                    update={
                        "settled": settled,
                        "candidate": candidate,
                    }
                ),
            }
        )
    )
    return store


def record(number, **kwargs):
    return with_linked_pull_requests(
        unrelated(issue_record(number, updated_at=MARK, **kwargs))
    )


class FixedLatencyRunner(RoutedRunner):
    """Assign each serial request or concurrent identity wave a fixed latency."""

    def __init__(self, results, identities):
        super().__init__(results, identities, hold_until_active=4)
        self.stages = []
        self.stage_lock = threading.Lock()

    @override
    def __call__(self, args, cwd, timeout):
        operation = next(arg for arg in args if arg.startswith("query=")).split("(")[0]
        with self.stage_lock:
            # Only the identity wave is concurrent; every prefix/delta page
            # depends on the completed page or wave before it.
            if (
                not self.stages
                or operation != self.stages[-1]
                or "ById" not in operation
            ):
                self.stages.append(operation)
        return super().__call__(args, cwd, timeout)

    def clock(self):
        return len(self.stages) * 0.6


@pytest.mark.parametrize("pending", [False, True])
def test_fixed_latency_startup_graph(tmp_path, pending):
    records = [record(number) for number in range(1, 95)]
    store = seed_store(
        tmp_path,
        records,
        settled=None if pending else LATER,
        candidate=LATER if pending else None,
    )
    if pending:
        pages = [
            completed(
                pull_request_changes_page(
                    [pull_request_change(10, LATER, "I_issue_1")],
                    has_next_page=True,
                    end_cursor="prefix-1",
                    probe=probe_response(94, MARK),
                )
            ),
            completed(pull_request_changes_page([pull_request_change(9, MARK)])),
            completed(issue_page([records[-1]])),
        ]
    else:
        pages = [
            completed(
                issue_page(
                    [records[-1]],
                    probe=probe_response(94, MARK),
                    pull_request_updated_at=LATER,
                )
            )
        ]
    runner = FixedLatencyRunner(pages, {value["id"]: by_id(value) for value in records})
    observation = source(runner, snapshot_store=store, monotonic=runner.clock).refresh()

    assert observation.status == "fresh"
    assert len(observation.issues) == 94
    assert runner.max_active == 4
    assert sorted(map(len, runner.lookups())) == [22, 24, 24, 24]
    names = [value.removeprefix("query=query Dashpot") for value in runner.stages]
    assert names == (
        ["PullRequestStartup", "PullRequestChanges", "IssuesById", "IssuesSince"]
        if pending
        else ["IssuesById", "IssuesStartup"]
    )
    assert runner.clock() == pytest.approx(2.4 if pending else 1.2)
    assert len(runner.calls) == (7 if pending else 5)


def test_pending_prefix_includes_new_targets_and_reobserves_removed_targets(tmp_path):
    old_target = with_linked_pull_requests(record(1), (10, "OPEN"))
    store = seed_store(tmp_path, [old_target], candidate=LATER)
    new_target = with_linked_pull_requests(record(2), (10, "MERGED"))
    related(new_target, "blocking", "I_issue_3")
    counterpart = related(record(3), "blockedBy", "I_issue_2")
    foreign = by_id(record(4))
    foreign["repository"] = {"id": "R_other", "nameWithOwner": "other/repo"}
    runner = RoutedRunner(
        [
            completed(
                pull_request_changes_page(
                    [
                        pull_request_change(
                            10, LATER, "I_issue_2", "I_issue_4", "I_deleted"
                        ),
                    ],
                    probe=probe_response(3, MARK),
                )
            ),
            completed(issue_page([])),
        ],
        {
            "I_issue_1": by_id(record(1)),
            "I_issue_2": by_id(new_target),
            "I_issue_3": by_id(counterpart),
            "I_issue_4": foreign,
            "I_deleted": None,
        },
    )

    result = source(runner, snapshot_store=store).refresh()

    assert result.status == "fresh"
    assert [issue.number for issue in result.issues] == [1, 2, 3]
    assert _linked_numbers(result, "I_issue_1") == set()
    assert _linked_numbers(result, "I_issue_2") == {10}
    assert runner.lookups() == [
        ["I_deleted", "I_issue_1", "I_issue_2", "I_issue_4"],
        ["I_issue_3"],
    ]


@pytest.mark.parametrize("pending", [False, True])
def test_later_startup_delta_wins_equal_timestamp(tmp_path, pending):
    store = seed_store(tmp_path, [record(1)], candidate=LATER if pending else None)
    prefix = (
        [
            completed(
                pull_request_changes_page(
                    [pull_request_change(10, LATER, "I_issue_1")],
                    probe=probe_response(1, MARK),
                )
            )
        ]
        if pending
        else []
    )
    runner = SequenceRunner(
        [
            *prefix,
            nodes_response([by_id(record(1, title="identity"))]),
            completed(
                issue_page(
                    [record(1, title="later delta")], probe=probe_response(1, MARK)
                )
            ),
        ]
    )
    result = source(runner, snapshot_store=store).refresh()
    assert result.status == "fresh"
    assert result.issues[0].title == "later delta"


def test_future_candidate_and_settled_marks_cannot_bound_prefix(tmp_path):
    store = seed_store(
        tmp_path, [record(1)], settled=FUTURE, candidate="2099-02-01T00:00:00Z"
    )
    runner = RoutedRunner(
        [
            completed(
                pull_request_changes_page(
                    [
                        pull_request_change(10, LATER),
                    ],
                    has_next_page=True,
                    end_cursor="next",
                    probe=probe_response(2, MARK),
                )
            ),
            completed(
                pull_request_changes_page([pull_request_change(9, MARK, "I_issue_2")])
            ),
            completed(issue_page([])),
        ],
        {"I_issue_1": by_id(record(1)), "I_issue_2": by_id(record(2))},
    )
    result = source(runner, snapshot_store=store).refresh()
    assert result.status == "fresh"
    assert [issue.number for issue in result.issues] == [1, 2]
    saved = store.load(repository_id=REPOSITORY_ID, project_id=PROJECT_ID)
    assert saved is not None
    assert saved.pull_request_marks.settled is None
    assert saved.pull_request_marks.candidate == LATER


@pytest.mark.parametrize(
    "pending,failure_stage", [(False, 0), (False, 1), (True, 0), (True, 1), (True, 2)]
)
def test_startup_failures_never_publish_or_replace_seed(
    tmp_path, pending, failure_stage
):
    store = seed_store(tmp_path, [record(1)], candidate=LATER if pending else None)
    seed = store.load(repository_id=REPOSITORY_ID, project_id=PROJECT_ID)
    prefix = completed(
        pull_request_changes_page(
            [
                pull_request_change(10, LATER, "I_issue_1"),
            ],
            probe=probe_response(1, MARK),
        )
    )
    pages = ([prefix] if pending else []) + [
        nodes_response([by_id(record(1))]),
        completed(issue_page([], probe=probe_response(1, MARK))),
    ]
    pages[failure_stage] = graphql_failure("FORBIDDEN", ["node"], "Permission denied")
    result = source(SequenceRunner(pages), snapshot_store=store).refresh()
    assert result.status == "unavailable"
    assert result.issues == ()
    assert result.last_good_at is None
    assert result.diagnostics[0].code == "github-permission"
    assert store.load(repository_id=REPOSITORY_ID, project_id=PROJECT_ID) == seed


@pytest.mark.parametrize("pending", [False, True])
def test_every_combined_startup_request_spends_the_refresh_budget(tmp_path, pending):
    store = seed_store(tmp_path, [record(1)], candidate=LATER if pending else None)
    prefix = (
        [
            completed(
                pull_request_changes_page(
                    [
                        pull_request_change(10, LATER),
                    ],
                    probe=probe_response(1, MARK),
                )
            )
        ]
        if pending
        else []
    )
    runner = SequenceRunner([*prefix, nodes_response([by_id(record(1))])])
    result = source(
        runner,
        snapshot_store=store,
        budget=RefreshBudget(requests=2 if pending else 1),
    ).refresh()
    assert result.status == "unavailable"
    assert result.issues == ()
    assert result.diagnostics[0].code == "github-refresh-budget"
    assert len(runner.calls) == (2 if pending else 1)


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("fault", ["count", "identity", "timestamp", "pagination"])
def test_combined_startup_response_is_validated(tmp_path, pending, fault):
    store = seed_store(tmp_path, [record(1)], candidate=LATER if pending else None)
    response = (
        pull_request_changes_page(
            [
                pull_request_change(10, LATER, "I_issue_1"),
            ],
            probe=probe_response(1, MARK),
        )
        if pending
        else issue_page([], probe=probe_response(1, MARK))
    )
    payload = json.loads(response)
    repository = payload["data"]["node"]
    probe = repository["issues" if pending else "probeIssues"]
    if fault == "count":
        probe["totalCount"] = True
    elif fault == "identity":
        repository["id"] = "R_wrong"
    elif fault == "timestamp":
        probe["nodes"] = [{"updatedAt": 42}]
    else:
        repository["pullRequests" if pending else "issues"]["pageInfo"] = {
            "hasNextPage": True,
            "endCursor": None,
        }
    pages: list[CommandResult | Exception] = [completed(json.dumps(payload))]
    if not pending:
        pages.insert(0, nodes_response([by_id(record(1))]))
    result = source(SequenceRunner(pages), snapshot_store=store).refresh()
    assert result.status == "unavailable"
    assert result.issues == ()
    assert result.diagnostics[0].code == {
        "identity": "github-repository-identity",
        "pagination": "github-pagination",
    }.get(fault, "github-malformed-response")


def test_future_issue_cursor_corrects_delta_and_discovers_unknown_issue(tmp_path):
    store = seed_store(tmp_path, [record(1)], high_water=FUTURE)
    new = issue_record(2, updated_at=LATER)
    unrelated(new)
    runner = SequenceRunner(
        [
            nodes_response([by_id(record(1))]),
            completed(issue_page([], probe=probe_response(2, LATER))),
            completed(issue_page([new])),
        ]
    )
    result = source(runner, snapshot_store=store).refresh()
    assert result.status == "fresh"
    assert [issue.number for issue in result.issues] == [1, 2]
    assert f"since={FUTURE}" in runner.calls[1][0]
    assert f"since={LATER}" in runner.calls[2][0]
    assert "IssuesSince" in query_of(runner.calls[2])
