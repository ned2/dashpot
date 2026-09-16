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

Pre-integration tests run both commands against real documentation-only and
mixed Git diffs, pass the emitted `GITHUB_OUTPUT` lane into the aggregate, and
check accepted and rejected skips. Workflow inspection confirms quality and
revision-artifact publication remain unconditional for PRs. A live docs-only PR
can confirm GitHub's orchestration after this workflow lands on `main`; this
implementation PR necessarily selects the full lane.

## Local parallel tests

Use the checkout's locked development environment:

```bash
uv sync --locked --group dev
uv run pytest -q -n 2 --dist=load --max-worker-restart=0
```

Each worker has its own Python process and runs its assigned tests sequentially.
Start with two workers; more processes may increase contention rather than speed.
Four workers failed a layout-readiness assertion on the measured Debian runner,
so CI uses two; higher local counts require validation on that machine.
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
Its optional `benchmark` input compares serial execution with `test-workers`
(two by default), three times each, on macOS's minimum
Python, Ubuntu/Python 3.14 with coverage, and Debian minimum-Git. Remaining jobs
retain full verification. Benchmark logs, JUnit reports, and coverage reports are
uploaded as artifacts, including on failure. Python 3.14 coverage diagnostics
include process IDs so worker SysMonitor evidence remains attributable.

The local helper defaults to evaluating all three counts. Hosted benchmarking
uses the selected count so an unsuitable candidate need not interrupt repeated
validation of the chosen configuration. Selecting zero measures serial only.

Measure whole-job and aggregate-gate time too: setup, runner scheduling, and the
slowest required job determine how long a person waits. The target for this
change is a 25% reduction in median full-gate time, with unchanged verification
and no new intermittent failures. It is an evaluation target, not a guarantee.

## Measured results

At revision `f75abdc344497ee9afc5c6598a93e4cb3bdd3ead`, local Python 3.14.7 coverage
runs on an Intel Core i9-13900K (32 logical CPUs, Linux) produced:

| Workers | Three full-suite times (seconds) | Median | Reduction from serial |
| --- | --- | --- | --- |
| 0 | 201.02, 203.30, 206.67 | 203.30 | — |
| 2 | 116.40, 114.98, 116.72 | 116.40 | 42.7% |
| 4 | 80.63, 83.03, 80.89 | 80.89 | 60.2% |

Each run passed 1,532 tests and 159 subtests. These are elapsed process times,
including coverage, rather than pytest's slightly shorter internal duration.

The [hosted candidate comparison](https://github.com/ned2/dashpot/actions/runs/35120362971)
rejected four workers on Debian and macOS: Debian's serial and two-worker runs
passed in 330.42 and 213.13 seconds; four workers failed the refresh indicator's
layout-readiness assertion. macOS passed its first four-worker run, then failed
the same assertion on the second. Explicitly holding the fake source until
release removes its separate two-second lifetime race, but did not resolve this
four-worker rendering failure.
The test retains its assertions and 1.5-second readiness deadline. Deeper
four-worker rendering diagnosis is deferred; two workers are the CI candidate,
and local four-worker success does not establish hosted reliability.

The completed Ubuntu 3.14 coverage repetitions in that run had serial times of
261.35, 236.29, and 248.87 seconds (median 248.87), versus 160.57, 154.34, and
141.27 seconds with two workers (median 154.34, 38.0% faster). All six passed.
The unfinished final four-worker repetition was cancelled after the other
platforms rejected that count; it is not counted as a successful run.

All local serial and two-worker runs covered the same 10,193 of 10,607
production statements, with identical executed lines. Ubuntu's coverage varied
between 10,192 and 10,194 statements in both serial and parallel runs. The
executed-line unions across three repetitions were identical: variation was
limited to the existing unmatched-Agent-Session returns in `agents.py` and
alternative concurrent-Worktree-creation diagnostics in `worktrees.py`.
No production source changed. Worker debug logs identify SysMonitor cores by
process ID; the controller's initial `-none-` entry is not the worker core.

The [ordinary serial full-matrix run](https://github.com/ned2/dashpot/actions/runs/35120780797)
passed all jobs at the same test-source revision. Gate execution took 372 seconds,
measured from the first job start to completion of `CI required`, excluding the
deliberate benchmark queue. Whole test-job times ranged from 259 to 353 seconds;
Debian took 346 seconds including setup. These single-run timings provide context
for the repeated suite measurements, not a controlled median gate comparison.

The [selected-configuration benchmark](https://github.com/ned2/dashpot/actions/runs/35123084668)
at `94093cafc6119dafb9130ac36d523b5db14d928f` passed all 18 representative
full-suite runs, with identical JUnit test identities and outcomes. Its test
sources match the earlier revision; only benchmark controls and documentation
changed. Hosted runner medians confirm the two-worker choice:

| Environment | Serial runs (seconds) | Two-worker runs (seconds) | Median reduction |
| --- | --- | --- | --- |
| Ubuntu, Python 3.14 coverage, 4 CPUs | 305.69, 293.53, 307.77 | 189.12, 189.33, 194.34 | 38.1% (305.69 → 189.33) |
| Debian 12, Python 3.11, Git 2.39, 4 CPUs | 335.47, 301.03, 310.73 | 194.29, 187.61, 202.04 | 37.5% (310.73 → 194.29) |
| macOS ARM64, Python 3.11, 3 CPUs | 400.89, 309.57, 286.71 | 204.86, 177.61, 164.46 | 42.6% (309.57 → 177.61) |

Each run passed 1,532 tests and 159 subtests without retries or worker restarts.
Ubuntu's production coverage again varied only at the existing paths described
above. This batch's parallel union omitted `worktrees.py:563`, the alternative
diagnostic when a competing Worktree creator has already finished; it executed
the initializing-creator diagnostic instead. The earlier two-worker batch covered
both paths. The concurrent-creation test still asserts one successful creation,
one refusal, and preservation of the winning Worktree and Branch. No unexplained
coverage loss was observed. The other supported CI legs also passed with two
workers in this run.

The [ordinary two-worker full-matrix run](https://github.com/ned2/dashpot/actions/runs/35123764103)
passed with a 261-second gate, versus the serial run's 372 seconds: 29.8% less
execution time in this pair. Whole test jobs took 126–238 seconds, with Debian
at 187 seconds. This meets the 25% target for this pair; it is not evidence of a
controlled 25% median gate reduction. Final PR validation records subsequent
ordinary gate runs separately from the deliberately longer benchmark workflow.

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
The isolated 4% figure applies only to this representative sample. No isolated
whole-suite percentage is attributed to the harness change; the full-suite
measurements above validate the combined changes.
