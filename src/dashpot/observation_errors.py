"""Name the expected failures contained at observation boundaries."""

from pydantic import ValidationError

# Keep collector containment limited to adapter/runtime failures and rejected
# published models; other programmer faults must still escape this boundary.
OBSERVATION_FAILURES = (OSError, RuntimeError, ValidationError)

# Query adapters also inspect raw payloads, whose shape errors use the built-in
# value, key, and type exceptions before a published model can be constructed.
QUERY_OBSERVATION_FAILURES = (*OBSERVATION_FAILURES, ValueError, KeyError, TypeError)
