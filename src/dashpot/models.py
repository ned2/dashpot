"""Share the Pydantic base and annotated types for Dashpot's validating seams."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Annotated, NoReturn, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    ValidationError,
)
from pydantic.alias_generators import to_camel
from typing_extensions import TypeAliasType


class DashpotModel(BaseModel):
    """Validate strictly at a Dashpot seam, with camelCase wire aliases."""

    model_config = ConfigDict(
        strict=True,
        validate_default=True,
        populate_by_name=True,
        alias_generator=to_camel,
    )


class PublishedModel(DashpotModel):
    """Freeze a validated value published across module boundaries."""

    model_config = ConfigDict(frozen=True)


class PersistedRecord(PublishedModel):
    """Read a record Dashpot persists, retaining fields a newer Dashpot wrote."""

    model_config = ConfigDict(extra="allow")


class ConfigModel(PublishedModel):
    """Validate a configuration file whose key set is a closed contract."""

    model_config = ConfigDict(extra="forbid")


# A required wire string is never empty: the hand validators these models
# replace all read "non-empty" as part of the field's contract.
NonEmptyString = Annotated[str, StringConstraints(min_length=1)]


def _strip_non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must be a non-empty string")
    return stripped


# Configuration strings are stripped, and blank is absent: the behavior of
# the hand parsers this type replaces, preserved explicitly (ADR 0013).
NonBlankString = Annotated[str, AfterValidator(_strip_non_blank)]


def describe_validation_error(error: ValidationError) -> str:
    """Summarize every failure by its wire path, for a Diagnostic or domain error."""

    return "; ".join(_describe_detail(detail) for detail in error.errors())


def translate_validation_error(
    error: ValidationError,
    *,
    root: str,
    field_order: Sequence[str] = (),
    union_tags: frozenset[str] = frozenset(),
    union_message: str = "",
    describe_path: Callable[[Sequence[str]], str] = ".".join,
) -> str:
    """State one failure in the wording the hand validators used at this seam.

    The hand validators raised at their first failed check; a
    ``ValidationError`` carries every failure, so the details are ranked by
    ``field_order`` (the old check order) to keep the reported message stable
    for callers pinning error text. Missing and unexpected fields are grouped
    by their parent — ``root`` names the top level — and a discriminated
    union's tag segments (``union_tags``) are dropped from the wire path, with
    ``union_message`` naming the discriminator's accepted values.
    """

    def rank(segments: Sequence[str]) -> int:
        if not segments:
            return len(field_order) + 1
        try:
            return field_order.index(segments[0])
        except ValueError:
            return len(field_order)

    missing: dict[str, list[str]] = {}
    unexpected: dict[str, list[str]] = {}
    candidates: list[tuple[tuple[int, int], str]] = []
    for detail in error.errors():
        segments = [
            str(segment) for segment in detail["loc"] if str(segment) not in union_tags
        ]
        kind = detail["type"]
        if kind in {"missing", "extra_forbidden"}:
            grouped = missing if kind == "missing" else unexpected
            parent = describe_path(segments[:-1]) or root
            grouped.setdefault(parent, []).append(segments[-1])
            continue
        path = describe_path(segments)
        if kind in {"model_type", "model_attributes_type", "dict_type"}:
            message = f"{path} must be an object"
        elif kind in {"union_tag_invalid", "union_tag_not_found"}:
            if isinstance(detail.get("input"), Mapping):
                message = f"{path}{'.' if path else ''}{union_message}"
            else:
                message = f"{path} must be an object"
        elif kind == "string_type":
            message = f"{path} must be a string"
        elif kind in {"list_type", "tuple_type"} or (
            kind == "is_instance_of" and "Sequence" in detail["msg"]
        ):
            message = f"{path} must be an array"
        else:
            tail = detail["msg"].removeprefix("Value error, ")
            message = f"{path} {tail}" if path else tail
        candidates.append(((rank(segments), 2), message))
    for grouped, position, verb in (
        (missing, 0, "is missing fields"),
        (unexpected, 1, "has unexpected fields"),
    ):
        for parent, fields in grouped.items():
            parent_rank = -1 if parent == root else rank(parent.split("."))
            candidates.append(
                (
                    (parent_rank, position),
                    f"{parent} {verb}: {', '.join(sorted(fields))}",
                )
            )
    candidates.sort(key=lambda candidate: candidate[0])
    return candidates[0][1]


def _describe_detail(detail: Mapping[str, object]) -> str:
    loc = detail["loc"]
    assert isinstance(loc, tuple)
    path = ".".join(str(segment) for segment in loc)
    message = str(detail["msg"]).removeprefix("Value error, ")
    return f"{path} {message}" if path else message


_M = TypeVar("_M", bound=BaseModel)


def validate_degrading(
    model: type[_M], raw: Mapping[str, object], *, fatal: frozenset[str]
) -> tuple[_M, tuple[str, ...]]:
    """Validate a record, dropping malformed non-fatal fields to their defaults.

    A record that keeps observing something is worth more than one that is
    lost: only a failure in a ``fatal`` wire field (or one with no default to
    fall back to) raises. Every other failing field is removed from the input
    so its default applies, and is described in the returned messages.
    """

    data = dict(raw)
    degraded: list[str] = []
    while True:
        try:
            return model.model_validate(data), tuple(degraded)
        except ValidationError as exc:
            details = exc.errors()
            fields = [
                str(detail["loc"][0]) if detail["loc"] else "" for detail in details
            ]
            if any(field in fatal or field not in data for field in fields):
                raise
            for field, detail in zip(fields, details, strict=True):
                if field in data:
                    degraded.append(_describe_detail(detail))
                    del data[field]


def _tuple_from_list(value: object) -> object:
    # Strict mode rejects a `list` for a tuple field, but every producer builds
    # lists; convert exactly that one shape and let anything else fail.
    if isinstance(value, list):
        return tuple(value)
    return value


_T = TypeVar("_T")

# ``Sequence`` is the declared seam so producers may pass lists or tuples;
# the validator makes every stored value a tuple.
LaxSequence = TypeAliasType(
    "LaxSequence",
    Annotated[Sequence[_T], BeforeValidator(_tuple_from_list)],
    type_params=(_T,),
)

_K = TypeVar("_K")
_V = TypeVar("_V")


class FrozenDict(dict[_K, _V]):
    """Reject in-place mutation of a published model's mapping field.

    A ``dict`` subclass so serialization and strict validation treat it as a
    plain mapping; every mutator is closed because ``frozen=True`` on a model
    does not reach into its collections.
    """

    def _reject(self, *args: object, **kwargs: object) -> NoReturn:
        raise TypeError(f"{type(self).__name__} does not support mutation")

    __setitem__ = _reject
    __delitem__ = _reject
    __ior__ = _reject
    clear = _reject
    pop = _reject
    popitem = _reject
    setdefault = _reject
    update = _reject


def _frozen_mapping(value: Mapping[_K, _V]) -> FrozenDict[_K, _V]:
    return FrozenDict(value)


# ``Mapping`` is the declared seam so producers may pass any mapping and
# readers get a read-only view; the validator makes every stored value a
# ``FrozenDict``.
FrozenMapping = TypeAliasType(
    "FrozenMapping",
    Annotated[Mapping[_K, _V], AfterValidator(_frozen_mapping)],
    type_params=(_K, _V),
)

# The hour range is in the pattern because RFC 3339 forbids ISO 8601's
# end-of-day 24:00:00, which `fromisoformat` accepts on some Python versions.
_RFC_3339_UTC = re.compile(
    r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):\d{2}:\d{2}(?:\.\d+)?Z"
)


def validate_rfc3339_timestamp(value: str) -> str:
    """Require an RFC 3339 UTC timestamp string ending in Z."""

    if not _RFC_3339_UTC.fullmatch(value):
        raise ValueError("must be an RFC 3339 UTC timestamp ending in Z")
    try:
        # The pattern alone accepts impossible dates such as month 13.
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("must be a valid RFC 3339 timestamp") from exc
    return value


Rfc3339Timestamp = Annotated[str, AfterValidator(validate_rfc3339_timestamp)]
