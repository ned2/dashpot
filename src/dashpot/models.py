"""Share the Pydantic base and annotated types for Dashpot's validating seams."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, NoReturn, TypeVar

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict
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
