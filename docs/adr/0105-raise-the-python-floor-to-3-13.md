---
status: accepted
date: 2026-10-05
---

# Raise the Python floor to 3.13

[ADR 0034](0034-publish-an-alpha-with-patch-compatible-interfaces.md) set
CPython 3.12 as the floor of the first release's 3.12–3.14 target, and
[ADR 0048](0048-adopt-python-3-13-typing-backports-on-the-3-12-baseline.md)
imported the Python 3.13 typing features the code adopted, `TypeIs` and
`deprecated`, from `typing_extensions` so that every module still ran on 3.12.
ADR 0048 also listed what would change once the floor reached 3.13.
[#463](https://github.com/ned2/dashpot/issues/463) asked whether to make that
change before the first publication, and the maintainer decided to.

Little code depends on the 3.12 floor: three backport imports, one type
parameter written without its natural default, and a worker-count fallback
in the test setup. What it costs is a CI matrix of five test and five install
legs where four of each would cover both endpoints, and an agent rule that
forbids Python 3.13 spellings. Nothing is published yet, so no installed user
loses support by the change.

## Decision

**The floor is CPython 3.13, and the target is 3.13–3.14.**
`requires-python` is `>=3.13`, the 3.12 classifier is gone, ty checks
against Python 3.13, and Ruff infers its 3.13 target from `requires-python`.
No CI or release job runs 3.12: the test and install matrices are 3.13 and
3.14 on Ubuntu and macOS, and every job pinned to the floor (the quality gate,
the distribution build, the Debian Git 2.39 compatibility job, and the release
validation) runs 3.13. The other platform, Git and gh targets in ADR 0034
stand.

**Python 3.13's own spellings replace the backports.** `TypeIs` comes from
`typing` and `deprecated` from `warnings`, and Dashpot no longer declares
`typing-extensions` as a direct dependency. Pydantic, pydantic-core and
Textual still require it, so an installation is no smaller; the lockfile
changes only by that dependency, its 3.12-only markers, and the 3.12-only
wheel entries a 3.13 floor cannot install. `ListResult` declares its summary's
default, `class ListResult[Row, Summary = None]`, and an annotation of a list
without a summary no longer writes `None`. The test setup counts the CPUs the
process may use with `os.process_cpu_count()`, which Python 3.13 provides on
every platform, in place of the `sched_getaffinity` probe and its `cpu_count`
fallback.

**ADR 0048's choices that do not depend on the floor carry forward.**
A predicate is a `TypeIs` only when both of its answers are exact, and stays a
`TypeGuard` otherwise; `_guards_type_checking` in
`tests/test_module_boundaries.py` remains the standing example.
`GitHubIssueSourceConfig.reconciliation_seconds` stays declared
`Field(deprecated=deprecated(...))`, so reading it warns while validating,
comparing and dumping a config stay silent. `ReadOnly` stays unadopted, since
there is no `TypedDict` in `src/` to carry it. This ADR supersedes ADR 0048 and
amends ADR 0034's Python target.

**3.14 is not the floor yet.** A 3.14 floor would let PEP 649 and PEP 749
deferred annotations replace `from __future__ import annotations` in every
module that imports it. That is a separate change with its own churn, and
the maintainer deferred it to a later Issue.

## Consequences

The CI matrix runs four test legs and four install legs, both Python
endpoints on both platforms, with no intermediate version left to add on
Linux. The Ubuntu/Python 3.14 leg still collects coverage. The optional
benchmark keeps measuring macOS at its minimum Python, now 3.13, so it still
differs from the Ubuntu/Python 3.14 coverage leg.

Anyone who would have installed Dashpot with a system Python 3.12, the default
on Ubuntu 24.04 LTS and supported upstream until October 2028, needs another
interpreter. `uv tool install --python 3.14 dashpot`, the recommended install,
already selects one, as does `pipx install --python`.

A symlink loop under `Path.resolve` raises `RuntimeError` only on Python 3.12;
the handlers that catch it for that release are now unreachable, and removing
them is left to a later change.
