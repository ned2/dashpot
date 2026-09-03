---
status: accepted
---

# Coalesce requests onto the observation in flight

Observation is scheduled per key, and the `ObservationCoordinator` guards each
key with a generation so a late result can never overwrite a newer one
([#17](https://github.com/ned2/dashpot/issues/17)). The dashboard treated every
request the same way: each automatic tick minted a new generation for every
key and cancelled the worker of the one still running. The cancelled worker's
thread could not be stopped — a started executor future runs to completion —
so it finished its `gh` calls and had its result discarded as superseded,
while the new ticket waited on the coordinator's per-key lock until it did.
Once one Issue refresh outlasted the polling period, every observation of that
key was discarded on landing and the Issues pane silently kept its first
collection with no diagnostic; on this connection that is roughly 700 GitHub
Issues at the default 15-second period
([#79](https://github.com/ned2/dashpot/issues/79)). The queued tickets also
held executor threads the Git and Agent Run observations needed.

Superseding a running observation of a key never yields a fresher result
sooner, because observations of one key are serialised: the newer ticket
cannot start until the running one finishes. It only discards finished work.
Dashpot therefore observes a key at most once at a time:

- A request for a key whose observation is in flight coalesces onto it. The
  running observation is left to land and publish; no worker is cancelled by
  a later request, so every started observation ends by posting its outcome
  and the in-flight gate always reopens.
- An automatic tick queues nothing further: the next tick is its rerun.
- Every other trigger — a key press, a Remote Fetch or Cleanup that changed
  the Repository while it was being observed, a follow-up of a publish —
  queues one more observation of the key for when the running one lands,
  under the latest such trigger. What a mutation changed, or what a publish
  made observable, is therefore always observed after it happened.
- A coalesced key press shows the refreshing alert at once rather than after
  the indicator threshold, so the press is never silent.
- Automatic ticks carry their own trigger, so their failures and recoveries
  change the alert and Diagnostics without the toast a manual refresh earns.

The coordinator's generations stay as they are: they remain the guard that
keeps a late result out of the store, they serve the headless JSON barrier
that requests every key at once, and they are exercised by the coordinator's
own tests. Coalescing is a scheduling rule of the dashboard, which is the
one place a rerun can be started.

## Considered options

- **Refuse the generation bump inside the coordinator's `request`:** rejected;
  the headless barrier needs a ticket for every key, and the rerun needs a
  worker only the dashboard can start.
- **Let a manual refresh keep superseding:** rejected; it cannot deliver a
  fresher observation any sooner and would keep discarding the running work
  the person is waiting for.
- **Bound the refresh instead:** necessary but not sufficient, and a separate
  decision; a bounded refresh that still outlasts the period would be
  discarded all the same.

## Consequences

- A slow refresh now lands late rather than never. The bound on how late,
  and the diagnostic that names what a refresh fetched before giving up,
  belong to the GitHub refresh budget that follows this decision.
- At most one observation per key runs at a time, so the refresh executor is
  sized to the keys and a slow Issue Source never starves another key.
- `--refresh-seconds 0` with a manual refresh behaves as before: the press
  observes, and a second press while it runs reruns once.
