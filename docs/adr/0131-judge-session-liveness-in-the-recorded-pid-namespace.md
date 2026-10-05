---
status: accepted
date: 2026-10-05
---

# Judge Session Liveness in the recorded PID namespace

A PID names a process only within one PID namespace. Dashpot used to decide
whether it could observe a recorded Host Process by asking whether Dashpot
itself ran in an isolated namespace: inside a sandbox helper's namespace or
any Docker or Podman container, every recorded process was
`isolated-namespace`, so its Session Liveness was unknown. That kept a
sandboxed `work` command from mistaking a host PID for a gone one, but it
also made a harness running in the same container as Dashpot unobservable,
so a devcontainer could never see a session end or an Agent Run orphaned
([#542](https://github.com/ned2/dashpot/issues/542)). Where the observer runs
is the wrong question: what matters is whether the process was recorded in
the namespace the observer probes.

## Decision

**A recorded Host Process is probed only from the PID namespace it was
recorded in.** Every observation of a process carries the namespace it was
observed in, as Linux names it in `/proc/self/ns/pid`, and every record of a
Host Process keeps it as `pidNamespace`: the hook record's `sessionProcess`
and `subagentProcesses` entries, the Work Store record's `sessionProcess`,
and a deferred `SessionEnd`'s host.

- A process recorded in another namespace than the observer's has unknown
  liveness with the reason `isolated-namespace`. It is never gone, so its
  hook record is not pruned and its Agent Run is not orphaned.
- A process recorded in the observer's own namespace is probed, inside a
  container as anywhere else.
- A process recorded without a namespace, by a record written before it was
  kept or on a host without `/proc` such as macOS, keeps the earlier rule:
  unknown inside an isolated namespace, probed elsewhere.
- A command's ancestry walk never leaves its own namespace, so it probes
  every ancestor. A walk that ends without a harness inside an isolated
  namespace still reports `isolated-namespace`, since the harness may run
  outside it.

`pidNamespace` is optional and omitted when unknown, so a record stays
readable by an older Dashpot, which ignores it.

## Considered options

- **Decide by where the observer runs (the earlier rule).** It needs no
  new field, but it hides a harness in the observer's own container, and it
  would read a host's process as observable from a container whose
  detection misses it. Kept only for records that name no namespace.
- **Probe every recorded PID wherever the observer runs.** In another
  namespace the same PID may name an unrelated process, or none, so a live
  session would read gone and its Agent Run orphaned.
- **Detect a devcontainer and treat it as the host.** No marker separates
  a devcontainer from any other container reliably, and a session started
  outside it would still be probed by the wrong PID.

## Consequences

- A session in a devcontainer, observed by a Dashpot in the same container,
  is live, gone, or orphaned as on the host. Observed from the host, the
  same session reads unknown, as before.
- A sandboxed `work` command still reads the host's harness as unknown,
  since its hook recorded the host's namespace
  ([ADR 0007](0007-identify-sandboxed-sessions-by-agent-session-identity.md)).
- A test's fake process lookup stands for the probe alone: only a recorded
  namespace that differs from the observer's overrides it.
- The process scan Cleanup runs inside a Worktree
  ([ADR 0104](0104-block-worktree-removal-while-a-process-runs-inside-it.md))
  still reports an isolated namespace as a gap. It scans every process, and
  has no recorded namespace to decide by.
