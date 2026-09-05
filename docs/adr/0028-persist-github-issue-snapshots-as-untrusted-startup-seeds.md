---
status: amended
date: 2026-09-05
amended-by: 0030-combine-startup-evidence-with-mandatory-reads.md
---

# Persist GitHub Issue snapshots as untrusted startup seeds

A GitHub Issue Source will persist the complete internal snapshot from its last
successful refresh beneath the Worktree's ignored state directory. A later
process may use that record only as a Snapshot Seed for a mandatory live
Reconciliation by Issue Identity; it is never an observation or retained
last-good state by itself. This avoids repeating the cursor sweep at every
process start without letting local persisted data become observation.

The record lives at
`.dashpot/state/github-issues/<repository-identity-sha256>.json`. Its strict
Pydantic wire model carries one version, the Repository and Project identities,
the complete observed Issue entries, the Issue High-Water Mark, and both the
settled and candidate Pull Request High-Water Marks. The version covers the
whole wire shape, including the embedded Issue Profile: any incompatible
change to either increments it. A corrupt record, unsupported version,
identity mismatch, invalid Issue Profile, repeated Issue Identity or Number,
or missing Issue High-Water Mark is ignored and startup uses the cursor sweep.

A Snapshot Seed has no maximum age and stores no wall-clock freshness value.
Age cannot make its identities unsafe because GitHub re-observes every one and
the delta after its inclusive High-Water Mark before anything is published;
discarding it after an arbitrary interval would only remove the restart
benefit. The process-local monotonic Reconciliation time is reset to the live
startup attempt. An unexplained reported count and a due fallback sweep are not
persisted: the mandatory Reconciliation re-establishes either condition from
current GitHub evidence. Persisted Issue and Pull Request marks are untrusted
startup cursors, not publishable facts: the live probe bounds any cursor beyond
GitHub's newest update, and the identity Reconciliation and delta derive the
Issue mark that replaces it. Both Pull Request marks are persisted so an
ordinary restart avoids an unnecessary full all-state prefix and does not lose
a pending second confirmation; the live probe discards either mark when it lies
beyond current evidence.

If the mandatory startup Reconciliation fails, the source is unavailable under
ADR 0002. The Snapshot Seed remains private for another attempt; it cannot make
that first failure stale because this process has not yet produced a good
observation. Once a live Reconciliation succeeds, the resulting complete
snapshot becomes both publishable and persistable through the normal source
path.

Writes use a per-Repository lock, a same-directory temporary file, `fsync`, and
atomic replacement. Concurrent Dashpot processes do not merge private source
state: whichever successful refresh completes its locked replacement last owns
the file. This is safe because every valid record is only a seed that the next
process must Reconcile, not an authority whose recency Dashpot trusts.

## Considered options

- **Publish a valid record immediately as stale:** rejected. Retained last-good
  state belongs to observations this process completed, and local bytes are not
  evidence that GitHub still has the same collection.
- **Discard records after a fixed age:** rejected. Repository identity, schema
  version, strict validation, and mandatory Reconciliation establish trust
  without an arbitrary cutoff.
- **Persist Reconciliation scheduling and fallback state:** rejected. Monotonic
  clocks cannot cross processes, while the startup Reconciliation supplies the
  current count evidence and resets the schedule.
- **Merge concurrent writers:** rejected. Merging observations from different
  times could manufacture a collection no refresh observed; last-completer-wins
  atomic replacement preserves one complete snapshot.

## Consequences

- [ADR 0030](0030-combine-startup-evidence-with-mandatory-reads.md) collects the
  live startup probe beside a mandatory read: the later Issue delta for a settled
  seed, or the first Pull Request prefix page for a pending candidate. A future
  Issue cursor requires a corrected inclusive delta; pending closing targets
  join the following identity Reconciliation. This changes request ordering,
  not the Snapshot Seed wire version or its trust boundary.
- A non-empty repository with a valid Snapshot Seed starts with the bounded
  identity Reconciliation and delta instead of the cursor sweep. A first run,
  invalid seed, or empty seed without an Issue High-Water Mark still sweeps.
- A syntactically valid future mark cannot suppress current GitHub evidence.
  Startup may move a mark backwards because the seed supplied only a cursor;
  the published mark comes from the live probe, identities, delta, and any
  required Pull Request prefix scan.
- The ignored file may be old or may be replaced by a slower concurrent
  process. Correctness is unchanged because no saved value is published before
  current GitHub evidence reconciles it.
- Every change to the persisted model or embedded Issue Profile must consciously
  keep or increment the snapshot version.
