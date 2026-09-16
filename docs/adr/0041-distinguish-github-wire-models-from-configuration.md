---
status: accepted
date: 2026-09-17
---

# Distinguish GitHub wire models from configuration

[#185](https://github.com/ned2/dashpot/issues/185) exposes two existing GitHub
response-validation styles and published query values inheriting a configuration
base. This amends [ADR 0013](0013-adopt-pydantic-models-by-seam.md): selected
GraphQL response models derive from `WireModel` in `models.py`, a frozen, strict,
camelCase-aliased base with `extra="forbid"`. It preserves the existing response
models' closed field contract while giving their seam an accurate name.
`ConfigModel` remains the configuration-file base. Published query requests,
contexts, continuations, and observations derive from `ObservationModel` and
explicitly retain their existing `extra="forbid"` policy.

`github_wire.py` owns shared identity, Repository, page-info, and search-connection
models, Issue and Pull Request field selections, and Pull Request state mapping.
The transport's existing `github.MALFORMED_RESPONSE` remains the single malformed
response code. Consumers use public adapter operations for completing required
Issue connections and auxiliary Linked Pull Requests, and public functions for
normalizing activity and label colours. Query text and response semantics stay
unchanged.

The Issue adapter does **not** converge wholesale on `WireModel` in this change.
Its hand parser accepts extra fields, permits an absent `endCursor` until forward
pagination needs it, and degrades malformed auxiliary facts independently of the
required Issue Profile. Replacing it with the strict shared `PageInfo` would
change those contracts; a permissive global wire base would instead weaken the
existing Pull Request and query validators. Keep those targeted checks and their
path-specific errors until a separate migration characterizes each leniency.
The hand parser does not introduce parallel Pydantic response classes.

[#183](https://github.com/ned2/dashpot/issues/183) shares complete-collection
retention in `RetainingSource` and uses the published `Diagnostic` at both source
seams. Collection-specific uniqueness checks and mapping snapshots stay in the
source modules. Query caching remains separate because its retention depends on
request scope and continuation identity. The collector keeps its existing `OBSERVATION_FAILURES` boundary. Query adapters
extend it with malformed payload value, key, and type errors in the named
`QUERY_OBSERVATION_FAILURES` tuple;
unexpected programmer failures escape the query boundary. Complete-collection
adapters retain their established broad fault containment and Diagnostic behavior.
