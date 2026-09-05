---
status: research
date: 2026-09-05
---

# Sequencing GitHub observation data and state work

Initial research date: 2026-09-04. Outcomes captured when the investigation
closed on 2026-09-05.

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

The linear work followed the recommended order **#128, #127, #123, #126,
#125, #129 triage, then #124**. All seven are complete. #123 added a Pull
Request change signal inside the GitHub Issue Source without coupling it to the
independently scheduled Pull Requests pane; #126 and #125 settled their
configuration and state-machine choices; and #129 rejected the REST gate after
measurement. #124 then made the settled state machine durable across runs as a
strictly validated Snapshot Seed that is never published before a live
Reconciliation.

## Current architecture that constrains the order

The GitHub Issue observation now has four distinct layers of state:

1. A versioned Snapshot Seed beneath `.dashpot/state/github-issues/` may carry a
   previous process's internal state into a mandatory startup Reconciliation.
   It is untrusted persisted input, not an observation
   ([`github_issue_snapshot.py`](../src/dashpot/github_issue_snapshot.py),
   [ADR 0028](adr/0028-persist-github-issue-snapshots-as-untrusted-startup-seeds.md)).
2. Its private in-process `_Snapshot` owns the Issues by Issue Identity; separate Issue and
   Pull Request High-Water Marks; last successful Reconciliation time; any
   unexplained reported count; and whether a fallback sweep is due. The source
   replaces it only after the merged collection passes its invariants
   ([`github_issues.py`](../src/dashpot/github_issues.py)).
3. The general `IssueSource` retains the last successfully published complete
   Issue collection and returns it as stale after a refresh failure
   ([`issue_sources.py`](../src/dashpot/issue_sources.py),
   [ADR 0002](adr/0002-require-complete-issue-profile-snapshots.md)).
4. The `ObservationCoordinator` retains each independently scheduled source
   result and publishes it into the process-local
   `WorkspaceObservationStore`. Issues and Pull Requests are separate keys with
   separate last-good and failure state
   ([`collect.py`](../src/dashpot/collect.py),
   [`design.md`](design.md)).

The distinction remains deliberate. Persisting private source state to resume
an Incremental Refresh does not persist a dashboard checkpoint, and a Snapshot
Seed does not make the base `IssueSource` regard a failed first refresh as stale
rather than unavailable.

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
| [#128 Verify which Issue changes bump `updatedAt`](https://github.com/ned2/dashpot/issues/128) | Live experiments for assignment, parent/sub-Issue, milestone, and Issue type changes; then make ADR 0022 and the README's blind-spot list exact. This is correctness evidence, not an optimization. | Informed which facts require Reconciliation and the design of #123. | **Completed.** Reproducible evidence and the verified blind spots are in the API research note and ADR 0022. |
| [#127 Reuse the already-fetched delta](https://github.com/ned2/dashpot/issues/127) | Remove a duplicated delta when an ordinary tick discovers a count disagreement and enters Reconciliation; merge duplicate observations by `updatedAt`, with the identity observation winning a tie. | Changed the same `_refresh_incrementally` to `_reconcile` handoff that #125 later restructured. | **Completed.** The handoff reuses one delta with timestamp-ordered merge semantics. |
| [#123 Observe Linked Pull Requests incrementally](https://github.com/ned2/dashpot/issues/123) | Close the most visible Reconciliation blind spot for a Linked Pull Request opening, merging, closing, linking, or unlinking. | Live research found no Pull Request `since` filter and observed derived closing-reference indexing lag. ADR 0025 therefore uses a newest-first prefix and two confirming ticks inside the Issue Source while preserving the independent Pull Request source. | **Completed.** Pull Request changes re-observe current and previous Issue targets by identity. |
| [#126 Configure the Reconciliation period](https://github.com/ned2/dashpot/issues/126) | Put the five-minute period in each Project's configuration and retain the current default. | Validation needs the Project setting, and a recurring TUI run also needs its polling period. | **Completed.** `issueSource.reconciliationSeconds` requires a positive finite value and is compared only with a recurring TUI polling schedule. |
| [#125 Give the fallback sweep its own Refresh Budget](https://github.com/ned2/dashpot/issues/125) | Prevent an identity Reconciliation plus delta plus fallback sweep from repeatedly exceeding one sixty-second budget on a large repository. | Followed #127's count-disagreement handoff and established state #124 must persist consciously. | **Completed.** ADR 0026 defers the marked sweep to the next refresh under its own Refresh Budget. |
| [#129 Add a REST conditional probe](https://github.com/ned2/dashpot/issues/129) | Evaluate whether a quiet repository can spend zero GraphQL points per tick by using a REST `304` as a gate before the authoritative GraphQL probe. | #123 added its Pull Request update signal to the existing one-point GraphQL query. Research found that a REST ETag validates only one paginated representation and supplies no exact Issue count, so it cannot safely replace the probe's repository-wide evidence. | **Completed triage; rejected.** ADR 0027 keeps the combined GraphQL probe authoritative rather than adding an undocumented deletion/transfer blind spot. |
| [#124 Persist the GitHub Issue snapshot](https://github.com/ned2/dashpot/issues/124) | Avoid the full cursor sweep on every process start by loading the previous `_Snapshot`, validating it, and reconciling it before publication. This is the durable-state change in the cluster. | Followed the settled Pull Request marks and fallback-sweep state added by #123 and #125. ADR 0028 excludes process-local scheduling, count, and sweep-due state while preserving both Pull Request cursors. | **Completed.** A strict, identity-bound Snapshot Seed starts a mandatory live Reconciliation; its marks are untrusted cursors and never enter retained last-good state by themselves. |

## Sequence plan and outcomes

### 1. Establish the missing evidence with #128

The controlled GitHub experiments updated the API research note, ADR 0022, and
domain language together. They prevented the later designs from accidentally
optimizing around an incomplete list of facts that `updatedAt` does not date
([ADR 0022](adr/0022-refresh-github-issues-incrementally-between-reconciliations.md),
[`github-api-batching-research.md`](github-api-batching-research.md)). The
verified relationship blind spots remain Reconciliation-only facts.

### 2. Simplify the existing handoff with #127

The delta-reuse change landed before #125. Besides saving a request, it gave
#125 one canonical payload to carry from the ordinary tick into a
Reconciliation and kept the handoff directly represented by its request-sequence
test
([ADR 0023](adr/0023-reconcile-github-issues-by-identity-in-bounded-parallel-batches.md)).

### 3. Re-scope and implement #123 alongside the Pull Request source

ADR 0025 answered the open design questions before code:

- the Issue Source owns its own bounded Pull Request prefix observation rather
  than changing the independently scheduled Pull Request source;
- changed Pull Requests cause current and previous closing-Issue targets to be
  re-observed by identity without coupling the sources' last-good state;
- the all-state prefix still observes merge and close transitions after a Pull
  Request leaves the independent active-only collection, while a two-tick
  confirmation window accommodates delayed closing-reference indexing; and
- live API evidence records the absence of a Pull Request `since` filter and
  the lag in derived closing-reference indexing.

The coordinator's separate observation keys remain a boundary: the additional
Pull Request signal shares the Issue Source's one-point probe but not the Pull
Request source's schedule or failure state
([ADR 0025](adr/0025-observe-linked-pull-requests-from-pull-request-changes.md)).

### 4. Correct and implement #126

The per-Project `issueSource.reconciliationSeconds` setting now rejects a
non-positive or non-finite value in `GitHubIssueSourceConfig`; the application
composition seam compares it with the effective polling interval only after a
recurring TUI schedule exists. Polling disabled with zero and headless one-shot
collection have no recurring polling interval to compare.

### 5. Decide and implement #125

ADR 0026 records the two-stage fallback: an identity-based Reconciliation may
publish its complete best-known collection with the existing
`github-issue-count` warning, then the next refresh performs only the cursor
sweep under a fresh Refresh Budget. The source clears the due marker before
sending the sweep, so a failure is retried on the Reconciliation period rather
than every tick. A person's `r` requests a Reconciliation, not an unbounded
chain of follow-up requests
([ADR 0026](adr/0026-run-fallback-sweeps-under-their-own-refresh-budget.md)).

### 6. Triage #129: keep the GraphQL probe authoritative

After #123, the combined Issue and Pull Request probe still cost one GraphQL
point. Live and documented REST evidence showed that `304` validates only the
requested page, which has no exact Issue count; it cannot safely suppress the
repository-wide evidence of the GraphQL probe. ADR 0027 therefore rejects the
REST gate. This closes #129 as triaged rather than implementing its requested
zero-point optimization
([ADR 0027](adr/0027-keep-the-graphql-change-probe-authoritative.md)).

### 7. Persist only the settled state with #124

ADR 0028 preceded the file format and settled the open choices. The strict
Pydantic record lives at a SHA-256 Repository-Identity key beneath
`.dashpot/state/github-issues/`; one version covers both its wire shape and the
embedded Issue Profile. Atomic, locked last-completer-wins replacement keeps
one complete seed under concurrent processes without merging observations.

No maximum age or wall-clock freshness field is stored: the mandatory live
Reconciliation establishes freshness, then resets the process-local monotonic
schedule. A failure leaves the first observation unavailable and keeps the seed
private for another attempt. Issue and Pull Request High-Water Marks, including
the pending Pull Request candidate, persist only as startup cursors; live probe,
identity, delta, and prefix evidence derive their publishable replacements.
Reported count and fallback-sweep state reset because startup current-count
evidence re-establishes them.
Corruption, identity mismatch, an unsupported version, or an incompatible Issue
Profile falls back to the bootstrap sweep. This keeps persisted state a
validating seam under
[ADR 0013](adr/0013-adopt-pydantic-models-by-seam.md) and retains ADR 0002's
complete-observation guarantee
([ADR 0028](adr/0028-persist-github-issue-snapshots-as-untrusted-startup-seeds.md)).

## Resulting dependency graph

The work did not require serializing all seven changes. The points at which
sequencing mattered were:

- **#128 before the final #123 design**, because it settled which Issue-side
  changes require Reconciliation;
- **#127 before #125**, because both own the count-disagreement handoff;
- **#123 before the #129 decision**, because it changed both the number of
  probes and the usefulness of Pull Request activity moving the REST ETag; and
- **#125 and #126 before #124**, with #123 also settled, because persistence
  should encode a stable source state machine once rather than become a
  migration burden immediately.
