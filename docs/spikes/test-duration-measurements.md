---
status: research
date: 2026-09-13
---

# Dashpot development test durations

[Issue #153](https://github.com/ned2/dashpot/issues/153) measures Dashpot's own
required gates. These findings do not change testing policy for observed Projects
or installed Issue-work guidance. Final full-suite and CI comparisons belong in
that Issue's integration PR, so recording their results does not itself invalidate
local coverage evidence.

## Baseline and method

The fixed base is `fed01bb43652018f13525f616c2366c5a91cbcaa`. The first required
local review gate ran on that base with only duration reporting added to
`scripts/review_coverage.py` and the CI test commands. Its source SHA-256 was
`2496c65e41b721f2d49767bfd24ac98bb00c07c7dfba3fb234a0b48ddb2a4b1a`.
No separate full benchmark suite was run. Both baseline and final validation use:

```bash
uv run pre-commit run --all-files
uv run --locked python scripts/review_coverage.py --base fed01bb43652018f13525f616c2366c5a91cbcaa
```

The helper invokes the checkout's Python with
`-m pytest -q --durations=0 --cov --cov-report=term-missing --cov-report=json:.review-coverage/coverage.json`.
All durations are reported locally so setup and teardown remain inspectable even
when test calls dominate. Pytest suppresses phases below 0.005 seconds and rounds
displayed values; their sum is not an exact total. CI reports its top 30 phases.
Coverage selection and required checks are unchanged.

Local environment: Ubuntu 26.04.1 LTS, Linux 7.0.0-30-generic, x86_64,
CPython 3.14.7, Git 2.53.0, coverage 7.16.0, Textual 8.2.8, locked checkout `.venv`.
The all-files gate passed. The suite passed **1,212 tests and 154 subtests in
127.01 seconds**, with 10,116 / 10,639 application statements covered (95.08%).
That is pytest's elapsed wall time, not the entire gate or CPU time. The local
host is shared; these sequential observations are not controlled benchmarks.

## Leading measured costs

| Baseline test call | Seconds |
| --- | ---: |
| Pane entry selects/reveals first row: mouse | 2.96 |
| Same: down | 2.91 |
| Same: shift+tab | 2.79 |
| Same: up | 2.69 |
| Same: tab | 2.60 |
| Paged Worktree launch keeps path across refresh/empty footer | 2.24 |
| Tab cycles focus through every list | 1.76 |
| Paged dashboard fetch waits for target observation | 1.75 |
| Early Cleanup confirmation explains missing selection | 1.68 |
| Arrows cross empty lists | 1.61 |

The five pane-entry variants total 13.95 seconds. Rounded reported phases sum to
25.32 seconds in `test_dashboard_interaction.py`, 21.08 in `test_cleanup_fetch.py`,
and 16.76 in `test_dashboard_cleanup.py`. These module totals include setup and
teardown performed *inside test calls*, such as Textual `run_test` contexts.
They do not establish that all of that time is UI waiting.

The largest reported fixture setup is 0.03 seconds for the coverage environment
rejection test, followed by 0.02 seconds for one source-digest test. Both create
and commit a small isolated Git checkout. Ten further setup phases round to
0.01 seconds; all teardown phases are below 0.005 seconds. Reported call phases
sum to 122.83 seconds and reported setup to 0.15 seconds, excluding suppressed
phases. This does not justify sharing mutable Git fixtures or changing fixture
scope.

## Bounded change and synchronization probes

The five leading variants visit every dashboard pane through tab, reverse tab,
up, down, and mouse entry. Each must establish a nonzero cursor, scroll away,
leave, re-enter, and prove row zero is selected and visible. Those actions and
all existing assertions remain.

Two setup `pilot.pause()` calls per pane now use `helpers.wait_until` to observe
focus, cursor visibility, and row zero. Focus alone is insufficient:
`FocusCursorTable.on_focus` shows the cursor and resets its row when it handles
the focus event. The checks wait for that observable state before sending input.
The helper's existing 1.5-second timeout is unchanged.

Inspection of the installed Textual 8.2.8 implementation explains the avoided
coordination cost: `Pilot.pause()` drains screen messages and polls process CPU
idleness in 20-millisecond intervals, potentially for a second. CPU idleness is
an indirect signal for these setup steps. `Pilot.press` also waits for idleness
and animations; replacing actual keyboard/mouse simulation or disabling
animations was not needed for this bounded improvement. Scroll completion still
uses the existing observable predicates.

Focused command, without coverage, before and after the wait change:

```bash
uv run pytest -q tests/test_dashboard_interaction.py::test_entering_each_pane_selects_and_reveals_its_first_row --durations=0
```

| Sequential focused observation | Tests | Pytest elapsed |
| --- | ---: | ---: |
| Before | 5 | 13.78 s |
| After | 5 | 10.68 s |
| After, focus handler delayed 80 ms on every invocation | 5 | 12.42 s |
| After, cursor reset removed; stop at first failure | 1 failed | 0.64 s |

The negative probe fails the unchanged final assertion with `cursor_row == 29`
instead of zero. The delay probe passes every entry variant. Both probes use a
process-local pytest plugin with an autouse `monkeypatch` fixture targeting
`FocusCursorTable.on_focus`; neither edits production files. The delayed async
handler awaits `asyncio.sleep(0.08)` before calling the original handler. The
negative handler preserves `show_cursor = True` and posting `FocusChanged()`,
but omits the row reset. Run the focused command through
`pytest.main([...], plugins=[Probe()])`, with `-x` for the negative probe. These
intentional probe delays are not proposed test optimizations.

[Issue #266](https://github.com/ned2/dashpot/issues/266) later removed the row
reset itself: each pane now keeps its cursor across focus changes, and the test
is `test_entering_each_pane_keeps_its_cursor_and_scroll`. The measurements above
describe the test as it was.

The observed focused decrease is 3.10 seconds, not a promised speedup. Even the
unchanged variants range from 2.37 to 3.06 seconds in the focused run versus
2.60 to 2.96 under baseline coverage. Coverage, scheduling, and rendering costs
make these observations informative but noisy.

## CI baseline after Issue 152

[Required CI run 34709799635](https://github.com/ned2/dashpot/actions/runs/34709799635)
validated the exact base above. It already includes
[#152](https://github.com/ned2/dashpot/issues/152), moving coverage to Python 3.14.
Its coverage log confirms `SysMonitor`, coverage 7.16.0, and Python 3.14.7.
The earlier #150 Python 3.11 coverage timing is historical context, not this
optimization's baseline.

| Baseline job | Test step | Whole job |
| --- | ---: | ---: |
| Ubuntu / Python 3.11 | 194 s | 204 s |
| Ubuntu / Python 3.12 | 194 s | 203 s |
| Ubuntu / Python 3.13 | 184 s | 194 s |
| Ubuntu / Python 3.14, coverage | 180 s | 192 s |
| macOS / Python 3.11 | 236 s | 246 s |
| macOS / Python 3.14 | 176 s | 185 s |
| Debian 12 / Git 2.39 | 191 s | 211 s |

The workflow took **258 seconds** (17:58:41–18:02:59 UTC on September 12).
macOS/Python 3.11 was the final test job; the required-check job completed after
it. Job and step times above are GitHub timestamps rounded to seconds, not CPU
usage, and must not be summed into workflow latency. Build took 13 seconds;
package-install jobs took 25–39 seconds and remained off the critical path.

The baseline commands were `uv run pytest -q`, or
`uv run pytest -q --cov --cov-report=term-missing` for coverage, followed by the
coverage diagnostics/summary commands. Linux runs passed 1,212 tests and 154
subtests; macOS passed 1,210 tests and 154 subtests with two existing skips.
The coverage pytest elapsed time was 176.94 seconds and macOS/Python 3.11 was
234.18 seconds; these exclude other work within the step.

The Ubuntu runner was 24.04.5, image `20260907.300.1`, with Git 2.55.0;
macOS was 26.6.2 arm64, image `20260907.0351.1`, Git 2.55.0, Python 3.11.9 for
the critical job. Hosted runner hardware, operating systems, Python versions,
and competing load differ from the local machine. Final CI must compare the
same matrix legs and report whether the critical path actually shortened.

## Remaining options

Keep measuring during required gates. The next candidates are the remaining
interaction costs and the Cleanup/Remote Fetch test calls, including context
startup, message processing, and shutdown. Fetch barrier tests deliberately hold
threading or asyncio events, assert confirmation remains disabled, and release
them explicitly; those timing/concurrency assertions must remain intact.
Measure those phases before changing their synchronization.

Partitioning is deferred. A separate proposal should first audit process-global
patches, event loops, background workers, temporary Git repositories, and resource
contention, then measure matrix critical paths under the proposed split. No
parallel execution, new dependency, lockfile change, fixture sharing, removed
assertion, new skip, matrix removal, or application behavior change is introduced.
