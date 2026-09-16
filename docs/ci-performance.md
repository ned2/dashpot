---
status: living
date: 2026-09-17
---

# CI and test performance

CI keeps the supported Python/platform matrix and full suite. It reduces waiting
through documentation-only verification and process-parallel tests. The same
parallel execution is available locally without changing pytest's serial default.

## Documentation lane

[`ci_lane.py`](../scripts/ci_lane.py) classifies the complete PR diff, including
both paths of renames. Only Markdown at the root or under `docs/` and
`conformance/` qualifies. Other files, mixed changes, empty diffs, and an
unavailable comparison select full verification. Manual and reusable workflow
invocations always select full verification.

Quality checks, PR ancestry validation, and the revision artifact run in both
lanes. The aggregate gate accepts the expensive jobs' skipped results only after
successful documentation classification. Every failure, cancellation, missing
result, or unexpected skip fails the gate. The required check name and
integration artifact contract stay unchanged.

## Local parallel tests

Use the checkout's locked development environment:

```bash
uv sync --locked --group dev
uv run pytest -q -n 2 --dist=load --max-worker-restart=0
```

Each worker has its own Python process and runs its assigned tests sequentially.
Start with two workers; more processes may increase contention rather than speed.
Serial execution remains `uv run pytest -q`, or `-n 0` when overriding a parallel
command. Keep interactive debugging serial.

For the full local review gate, use the evidence helper rather than a separate
uninstrumented full-suite run:

```bash
review_base=$(git rev-parse origin/main)
uv run pre-commit run --all-files
uv run --locked python scripts/review_coverage.py --base "$review_base" --workers 2
uv run --locked python scripts/review_coverage.py --base "$review_base" --check
```

The helper combines worker coverage and records the command in the same source
and report evidence as serial execution. Omit `--workers` for serial coverage.
Worker crashes fail without automatic restarts. Keep one coverage run and one
writer per Worktree, as required by the [local review gate](../README.md#local-review-gate).
Worker coverage does not implicitly add application-spawned subprocess coverage.

## Repeatable measurements

The benchmark helper runs the full suite with zero, two, and four workers,
interleaved across three repetitions. It records elapsed process time, platform,
Python version, CPU count, Git revision, exact commands, JUnit results, and logs.
It rejects failures and changed test identities/outcomes across configurations.

```bash
uv run python scripts/benchmark_tests.py --output .review-coverage/benchmark
uv run python scripts/benchmark_tests.py --output .review-coverage/benchmark-cov --coverage
```

Use a fixed, clean revision and avoid concurrent test runs when comparing timings.
`--workers` and `--repeats` allow focused follow-up measurements. Compare coverage
executed/missing lines as well as counts; timing-dependent paths can vary, so
unexplained differences require investigation.

Manual CI dispatch accepts `test-workers` for ordinary full-matrix comparisons.
Its optional `benchmark` input runs the repeated comparison on macOS's minimum
Python, Ubuntu/Python 3.14 with coverage, and Debian minimum-Git. Remaining jobs
retain full verification. Benchmark logs, JUnit reports, and coverage reports are
uploaded as artifacts, including on failure. Python 3.14 coverage diagnostics
include process IDs so worker SysMonitor evidence remains attributable.

Measure whole-job and aggregate-gate time too: setup, runner scheduling, and the
slowest required job determine how long a person waits. The target for this
change is a 25% reduction in median full-gate time, with unchanged verification
and no new intermittent failures. It is an evaluation target, not a guarantee.

## UI profiling

Profile representative dashboard navigation and tooltip tests separately from
unprofiled timing runs:

```bash
uv run python -m cProfile -o /tmp/dashpot-ui.prof -m pytest -q tests/test_dashboard_interaction.py tests/test_header_tooltips.py
uv run python -m pstats /tmp/dashpot-ui.prof
```

The initial 26-test sample took 37.42 seconds unprofiled and 75.99 seconds under
cProfile on the development machine. Stylesheet application accounted for 32.10
cumulative seconds in the profile; event-loop polling accounted for 12.29 seconds
of self time. Cumulative async timings overlap and profiler overhead can change
Textual's CPU-idle detection, so these are diagnostic signals rather than
additive wall-time components.

The harness retains fresh application instances, production CSS, real Pilot
interactions, and condition-based readiness checks. Textual's `Pilot.pause()`
waits for message processing and idle state; removing it indiscriminately would
weaken synchronization. Tooltip tests already shorten the production tooltip
delay to 10 ms. Lowering timeout ceilings would not accelerate successful
condition-based waits. Replacing stylesheet processing or sharing mutable
applications across tests is not justified by this profile.


The dashboard harness disables optional animations through Textual's public
`animation_level` setting. These tests assert settled state and layout, rather
than intermediate animation frames; a test of motion can explicitly restore
`app.animation_level = "full"`. Three unprofiled runs of the 26-test sample had
baseline times of 37.42, 35.28, and 36.55 seconds (median 36.55); the harness
change yielded 34.67, 35.39, and 35.00 seconds (median 35.00, about 4% faster).
This modest gain is independent of parallel execution and does not justify
removing readiness or rendering synchronization.
