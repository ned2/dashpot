"""Name the expected failures contained at observation boundaries."""

from pydantic import ValidationError

from .errors import DashpotError

# Keep collector containment limited to adapter failures, Dashpot's own
# refusals, and rejected published models. ``RuntimeError`` stays for an
# adapter's runtime fault — a symlink loop under ``Path.resolve``, say — so a
# dashboard keeps running and reports it as a Diagnostic; other programmer
# faults must still escape this boundary.
OBSERVATION_FAILURES = (OSError, RuntimeError, DashpotError, ValidationError)

# Query adapters also inspect raw payloads, whose shape errors use the built-in
# value, key, and type exceptions before a published model can be constructed.
QUERY_OBSERVATION_FAILURES = (*OBSERVATION_FAILURES, ValueError, KeyError, TypeError)
