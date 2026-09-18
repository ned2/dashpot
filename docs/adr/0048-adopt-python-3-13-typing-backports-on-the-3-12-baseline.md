---
status: accepted
date: 2026-09-18
---

# Adopt Python 3.13 typing backports on the 3.12 baseline

[ADR 0034](0034-publish-an-alpha-with-patch-compatible-interfaces.md) sets
CPython 3.12 as the floor, and [#222](https://github.com/ned2/dashpot/issues/222)
moved the code onto Python 3.12's own typing: PEP 695 type parameters and
`type` statements, `typing.override`. Python 3.13 adds a further set of
typing features — `TypeIs` (PEP 742), type parameter defaults (PEP 696),
`ReadOnly` for `TypedDict` (PEP 705), and `warnings.deprecated` (PEP 702) —
every one of which `typing_extensions` backports to 3.12, and one of which
(`TypeIs` on `is_harness`) the code already used.
[#223](https://github.com/ned2/dashpot/issues/223) asked which of the rest
earn a place in existing code, and where the line falls between a backport
that sharpens a contract and one adopted for its own sake.

## Decision

A Python 3.13 typing feature is imported from `typing_extensions`, never from
`typing`, so that every module parses and runs on 3.12; the direct
`typing-extensions>=4.15.0` dependency already covers each feature named
here. Python 3.13's own spellings — `typing.TypeIs`, `warnings.deprecated`,
`class C[T = Default]` — wait for a 3.13 floor. Adopted where a contract in
the code called for it:

- **`TypeIs` for an exact predicate.** `is_issue_sort_column` joins
  `is_harness` as a `TypeIs`: a column that passes is one of the sort
  columns and one that fails is none of them, so the rejected branch may be
  narrowed too. A predicate stays a `TypeGuard` when only its positive answer
  is exact. `_guards_type_checking` in `tests/test_module_boundaries.py` is
  the standing example: a node it rejects may still be an `ast.If`, just not
  a `TYPE_CHECKING` guard, and a `TypeIs` there would narrow the rejected
  node wrongly. The choice is made predicate by predicate, not by search
  and replace.
- **`deprecated` for the one retired field.**
  `GitHubIssueSourceConfig.reconciliation_seconds` was retired with
  Reconciliation ([ADR 0033](0033-query-pages-and-independent-issue-resolution.md))
  and stays parsed so a config written for an earlier alpha keeps loading
  (ADR 0034). The field is now declared
  `Field(deprecated=deprecated(...))`, which Pydantic turns into a
  `DeprecationWarning` on every read and a `deprecated: true` schema entry.
  Validating, comparing, and dumping the model stay silent, so the
  compatibility promise holds; reading the value is what the retirement
  forbids, and the suite's `filterwarnings = ["error"]` makes a new reader a
  failing test. Nothing else in the code is on a deprecation path: the
  "legacy" handling in `sessions/` is data-format compatibility for persisted
  records, not a Python API that callers should leave.

Evaluated and left alone, with the reason recorded so the question is not
reopened by default:

- **Type parameter defaults.** The one candidate is `ListResult[Row,
  Summary]`, where nine of nineteen annotations spell `Summary` as `None`.
  Giving `Summary` a `None` default on the 3.12 baseline means abandoning the
  PEP 695 declaration for a module-level
  `TypeVar("Summary", infer_variance=True, default=None)` and
  `Generic[Row, Summary]`, the form #222 just removed everywhere, to save
  `, None` at nine sites; it adds no precision. The tooling is not the
  obstacle — ty resolves the default and Ruff's `UP046` accepts the explicit
  form under the py312 target Ruff infers from `requires-python` — the
  declaration syntax is, so the trade is worth remaking only for a default
  that carries a contract rather than a shorthand. Once the floor is 3.13, `class ListResult[Row,
  Summary = None]` costs nothing and should be taken. `RetainingSource`,
  `FrozenDict`, and `MarkedSelectionList` have no parameter with a natural
  default.
- **`ReadOnly`.** There is no `TypedDict` in `src/`. Validating seams are
  Pydantic models and trusted values are frozen dataclasses
  ([ADR 0013](0013-adopt-pydantic-models-by-seam.md)); introducing a
  `TypedDict` to carry a `ReadOnly` field would trade a stronger contract for
  a weaker one.

## Consequences

`typing_extensions` is the import for `TypeIs` and `deprecated` throughout,
and the review asks a new `TypeGuard` whether it is really a `TypeIs`, and a
new `TypeIs` whether its rejected branch is exact. `tests/test_issue_list.py`
pins both narrowing directions of `is_issue_sort_column` with `assert_type`,
which ty checks as part of the gate, beside the runtime answers. A read of
`reconciliation_seconds` warns; the config tests that still read it do so
under `pytest.deprecated_call()`, and a future reader elsewhere fails the
suite rather than quietly reviving the setting. Raising the floor to 3.13
revisits this record: the `typing_extensions` imports move to `typing` and
`warnings`, and `ListResult` takes its default.
