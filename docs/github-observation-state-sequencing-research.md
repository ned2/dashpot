---
status: research
date: 2026-09-04
---

# Sequencing GitHub observation data and state work

Research date: 2026-09-04.

## Scope

A live `gh issue list` found ten open Issues. Seven belong to the GitHub
observation follow-up cluster created when
[#79](https://github.com/ned2/dashpot/issues/79) was completed:
[#123](https://github.com/ned2/dashpot/issues/123),
[#124](https://github.com/ned2/dashpot/issues/124),
[#125](https://github.com/ned2/dashpot/issues/125),
[#126](https://github.com/ned2/dashpot/issues/126),
[#127](https://github.com/ned2/dashpot/issues/127),
[#128](https://github.com/ned2/dashpot/issues/128), and
[#129](https://github.com/ned2/dashpot/issues/129). They are the scope of this
note: fetching and retaining GitHub Issue and Linked Pull Request facts,
Reconciliation scheduling, and persistence of the GitHub Issue Source's
snapshot.

The other open Issues are not part of this sequence. #58 concerns distribution
of the agent-facing Issue-work skill and the Work Store; #4 is real-host macOS
validation; #5 is release preparation. They touch runtime state or `gh` only at
the product boundary, not the GitHub observation state machine reviewed here
([#58](https://github.com/ned2/dashpot/issues/58),
[#4](https://github.com/ned2/dashpot/issues/4),
[#5](https://github.com/ned2/dashpot/issues/5)).

The seven in-scope Issues have no comments, native `blocked by`/`blocking`
relationships, parent, or sub-Issues at the research date. Their dependencies
are prose references and implementation dependencies rather than a recorded
GitHub dependency graph.

## Executive conclusion

Treat the work as three tracks which converge before persistence:

```text
evidence and Linked Pull Request freshness:  #128 -> #123 -> #129 decision
count-mismatch and fallback efficiency:       #127 -> #125
configuration:                                #126 (after its seam is corrected)

all settled in-memory state -------------------------------> #124
```

For one person working linearly, the recommended order is **#128, #127, #123,
#126, #125, #129 triage, then #124**. #128 and #127 are the two cleanly ready
starting points. #123 is the highest-priority user-visible gap, but its proposed
shape predates the now-complete Pull Requests pane and must be revised before
implementation. #126, #125, and #124 each contain a design choice or seam
contradiction despite carrying `ready-for-agent`. #129 already carries
`needs-triage` and should be implemented only if measurement after #123 justifies
it. #124 should be last because it makes the state machine and its compatibility
contract durable across runs.

## Current architecture that constrains the order

The GitHub Issue Source currently has three distinct layers of in-process state:

1. Its private `_Snapshot` owns the Issues by Issue Identity, High-Water Mark,
   last successful Reconciliation time, and any unexplained reported count.
   The source replaces it only after the merged collection passes its invariants
   ([`github_issues.py`](../src/dashpot/github_issues.py)).
2. The general `IssueSource` retains the last successfully published complete
   Issue collection and returns it as stale after a refresh failure
   ([`issue_sources.py`](../src/dashpot/issue_sources.py),
   [ADR 0002](adr/0002-require-complete-issue-profile-snapshots.md)).
3. The `ObservationCoordinator` retains each independently scheduled source
   result and publishes it into the process-local
   `WorkspaceObservationStore`. Issues and Pull Requests are separate keys with
   separate last-good and failure state
   ([`collect.py`](../src/dashpot/collect.py),
   [`design.md`](design.md)).

This distinction matters most to #123 and #124. Persisting a dashboard
checkpoint is not the same as persisting enough private source state to resume
an Incremental Refresh, and a persisted `_Snapshot` does not by itself make the
base `IssueSource` regard a failed first refresh as stale rather than
unavailable.

The recently completed
[#83](https://github.com/ned2/dashpot/issues/83) also changes #123's premise.
`GitHubPullRequestsSource` now independently sweeps every open Pull Request on
each of its observations, with its own Refresh Budget and last-good state
([`github_pull_requests.py`](../src/dashpot/github_pull_requests.py)). A second
Pull Request observation inside the Issue Source would duplicate work and blur
the deliberately separate failure states.

## Issue-by-Issue assessment

| Issue | Present scope and value | Dependency or overlap | Readiness |
| --- | --- | --- | --- |
| [#128 Verify which Issue changes bump `updatedAt`](https://github.com/ned2/dashpot/issues/128) | Live experiments for assignment, parent/sub-Issue, milestone, and Issue type changes; then make ADR 0022 and the README's blind-spot list exact. This is correctness evidence, not an optimization. | Informs which facts require Reconciliation and the design of #123. No code dependency. | **Ready first.** It requires authorized scratch-Issue mutations, but its experiment and documentation outcome are fully stated. |
| [#127 Reuse the already-fetched delta](https://github.com/ned2/dashpot/issues/127) | Remove a duplicated delta when an ordinary tick discovers a count disagreement and enters Reconciliation; merge duplicate observations by `updatedAt`, with the identity observation winning a tie. | Changes the same `_refresh_incrementally` to `_reconcile` handoff that #125 will restructure. | **Ready first.** Small, pinned by an existing request-sequence test, and should precede #125. |
| [#123 Observe Linked Pull Requests incrementally](https://github.com/ned2/dashpot/issues/123) | Close the most visible five-minute blind spot: a Linked Pull Request opening, merging, closing, linking, or unlinking should update its Issue on the next tick. It is the only P2 in the cluster. | The issue's sketch assumes a new Pull Request probe, but #83 has since supplied an independent full Pull Request source. It also leaves two API facts for live verification: whether closing-reference edits bump the Pull Request's `updatedAt`, and whether a usable Pull Request `since` delta exists. | **Re-triage, then design first.** Revise the Issue/ADR around one Pull Request observation rather than duplicate collection, while preserving independent Issue and Pull Request failure state. |
| [#126 Configure the Reconciliation period](https://github.com/ned2/dashpot/issues/126) | Put the five-minute period in each Project's configuration and retain the current default. This is useful tuning for repositories with different sizes and shared-token pressure. | The requested validation compares the configured period with the polling interval, but `ProjectConfig` sees only `.dashpot/config.json`; polling is the runtime `--refresh-seconds` CLI option and is passed directly to the app, not the Project collector ([`project_config.py`](../src/dashpot/project_config.py), [`cli.py`](../src/dashpot/cli.py)). | **Specification correction required.** Validate positivity in the Project config model, and validate the period-versus-polling relationship at run construction after both values are known. Clarify the rule for zero polling and headless single-shot runs. |
| [#125 Give the fallback sweep its own Refresh Budget](https://github.com/ned2/dashpot/issues/125) | Prevent an identity Reconciliation plus delta plus fallback sweep from repeatedly exceeding one sixty-second budget on a large repository. | Overlaps #127's count-disagreement path. Its notes leave two materially different designs open: defer a marked sweep to a later tick, or grant Reconciliation a larger budget. A deferred `sweep_due` marker would become part of the state #124 persists. | **Decide the ADR shape after #127.** Prefer the separate later sweep: it preserves the ordinary Refresh Budget and avoids making a person's `r` unexpectedly much longer, while still publishing no partial sweep. |
| [#129 Add a REST conditional probe](https://github.com/ned2/dashpot/issues/129) | Let a quiet repository spend zero GraphQL points per tick by using a REST `304` only as a gate before the authoritative GraphQL probe. | Its economics explicitly improve after #123. Its premise also predates #83: the REST Issues-list ETag moving on Pull Request activity may be a useful shared hint now, but Issues and Pull Requests are independently scheduled keys. Sharing it could couple sources; using it separately could duplicate REST calls. | **Triage after #123.** Measure real primary-limit pressure and settle whether one safe shared gate can serve both sources. Close or defer it if the complexity exceeds the saved points. |
| [#124 Persist the GitHub Issue snapshot](https://github.com/ned2/dashpot/issues/124) | Avoid the full cursor sweep on every process start by loading the previous `_Snapshot`, validating it, and reconciling it before publication. This is the durable-state change in the cluster. | It freezes the shape produced by #125 and the configured period from #126. If #123 introduces shared Pull Request high-water or relationship state, persistence must consciously include or exclude it. | **Last, after a dedicated ADR.** The Issue already leaves trust age and first-run last-good behavior undecided, and the current monotonic `reconciled_at` cannot be meaningfully restored in another process. |

## Recommended sequence and gates

### 1. Establish the missing evidence with #128

Run the controlled GitHub experiments and update the research note, ADR 0022,
and README together. This prevents the later designs from accidentally
optimizing around an incomplete list of facts that `updatedAt` does not date
([ADR 0022](adr/0022-refresh-github-issues-incrementally-between-reconciliations.md),
[`github-api-batching-research.md`](github-api-batching-research.md)). If an
experiment shows that neither end of a relationship changes its timestamp,
record that as a Reconciliation-only fact before changing the state machine.

### 2. Simplify the existing handoff with #127

Land the small delta-reuse change while the current request sequence is still
directly represented by the existing test. Besides saving a request, it gives
#125 one canonical payload to carry from the ordinary tick into a
Reconciliation. Doing #125 first would force #127 to rediscover that handoff in
a newly split sweep state machine
([ADR 0023](adr/0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md)).

### 3. Re-scope and implement #123 against the Pull Request source

Before code, update #123's accepted design to answer:

- whether the existing Pull Request source becomes incremental and exposes
  closing-Issue relationship changes, or whether a separate internal observer
  supplies that signal;
- how a Pull Request observation asks the Issue Source to re-observe the
  affected Issue identities without coupling their last-good/failure states;
- how a merge or close is positive evidence when the active-only Pull Request
  collection no longer lists that Pull Request; and
- the two live API questions already named in #123.

The coordinator's separate observation keys are a useful boundary to preserve,
not an obstacle to bypass. This work should precede #129 because it determines
whether Dashpot has one or two GraphQL change probes per tick and whether the
REST ETag can safely gate either of them.

### 4. Correct and implement #126

Keep the per-Project setting on `GitHubIssueSourceConfig`, but split validation:
the model can reject a non-positive value and the CLI/application composition
seam can compare it with the effective polling interval. With polling disabled
or a headless one-shot collection, there is no recurring polling interval to
compare. The Issue should say this explicitly before code so configuration
parsing does not acquire a hidden dependency on CLI state.

### 5. Decide and implement #125

After #127, record the two-stage fallback in an ADR: an identity-based
Reconciliation may publish its complete best-known collection with the existing
`github-issue-count` warning, then a later refresh performs only the cursor
sweep under a fresh Refresh Budget. Mark the sweep attempted before sending it
so a failure is retried on the Reconciliation period rather than every tick,
matching the existing retry discipline. Keep a person's `r` semantics explicit:
it requests a Reconciliation, not an unbounded chain of follow-up requests.

### 6. Re-evaluate #129 rather than assuming it should ship

After #123, measure the resulting GraphQL probe cost and update #129 for the
actual Pull Request architecture. The REST gate remains non-authoritative: only
`304` may suppress GraphQL; any other response continues to the existing
probe. Implement it only if it can preserve independently scheduled source
state without a shared-cache lifecycle more complex than the points it saves.
Its current `needs-triage` label is accurate.

### 7. Persist only the settled state with #124

Write the ADR before the file format. It should decide at least:

- the exact Repository-Identity-keyed path under `.dashpot/state/`, atomic
  replacement, and behavior with concurrent Dashpot processes;
- a version covering both the persisted wire model and the Issue Profile shape;
- whether a maximum age rejects a snapshot, and which wall-clock timestamp
  replaces or accompanies the current process-local monotonic
  `reconciled_at`;
- whether failure of the mandatory startup Reconciliation leaves the source
  unavailable or may publish the persisted collection as stale; and
- whether pending fallback-sweep state from #125 and any Pull Request
  High-Water Mark from #123 are persisted, reset, or deliberately outside this
  file.

Load and validate the file, but publish nothing from it until GitHub has
successfully reconciled it, as #124 requires. Corruption, identity mismatch, an
unsupported version, or an explicitly over-age snapshot should fall back to
the existing bootstrap sweep rather than contaminate the live source's
last-good state. This keeps persisted state a validating seam under
[ADR 0013](adr/0013-adopt-pydantic-models-by-seam.md) and retains ADR 0002's
complete-observation guarantee.

## Resulting dependency graph

There is no reason to serialize all seven changes. After #128, #123 can proceed
independently of the #127 to #125 chain, and #126 can proceed as soon as its
specification is corrected. The points at which sequencing matters are:

- **#128 before the final #123 design**, because it settles which Issue-side
  changes require Reconciliation;
- **#127 before #125**, because both own the count-disagreement handoff;
- **#123 before the #129 decision**, because it changes both the number of
  probes and the usefulness of Pull Request activity moving the REST ETag; and
- **#125 and #126 before #124**, with #123 also settled, because persistence
  should encode a stable source state machine once rather than become a
  migration burden immediately.

The GitHub dependency metadata should be updated to express those real
prerequisites once the Issue bodies' open design choices have been resolved.
