---
status: proposal
date: 2026-09-13
---

# OpenCode integration design

Starting proposal based on the
[identity and lifecycle spike](opencode-identity-lifecycle-spike.md), committed
as `2f222d5`. This document separates recommended behavior from decisions still
to resolve. It does not change the accepted domain language, existing ADRs, or
production support.

## Recommended initial design

Keep one accepted plugin generation for each backend/location association,
with durable ordering and explicit retirement. Identify conversations by native
Agent Session Identity; use the backend process only as liveness evidence.
Restore observation after orderly plugin replacement in the same backend, but
require backend restart and explicit `work start` when lost disposal leaves
publisher ownership ambiguous. Defer a separate observation-recovery command.

For shell commands, clear inherited claims and inject a command-local
acknowledgment only after that invocation's bootstrap succeeds. Validate its
identity, backend, generation, location and parentage against current accepted
evidence. This satisfies the spike's failed-bootstrap requirement without a
persisted receipt, expiry policy or capacity limit for every command. A stronger
independent audit of each exact bootstrap would be an additional requirement.

These are reviewed recommendations. Only explicit Issue-work restart after
backend restart has been agreed; production implementation has not begun.

## Working scope

Design for local OpenCode conversations, including multiple conversations in
one backend and locally attached clients. Local TUI entry and exit still need
live verification before being advertised as supported. The tested legacy
plugin/shell path is the initial compatibility target; V2, remote backends,
same-session Worktree relocation and Pi remain separate work.

The first useful result should let two OpenCode Agent Sessions work on different
Issues in one Worktree without sharing bindings, activity or termination. The
dashboard remains passive, the Work Store remains the authority for Issue
Bindings, and opt-in still happens only through `work start`.

## Identity comes before process evidence

Use `(harness, native session ID)` as the semantic identity whenever the native
ID is available. A host process supplies Session Liveness, not an alternative
identity for a different named conversation. OpenCode must always supply its
native ID, even when its backend is visible in command ancestry.

One matching rule must govern command identification, Work Store lookup,
activity adoption, duplicate detection, location lookup and end reconciliation:

| Available evidence | Match behavior |
| --- | --- |
| Both records name native identities | Require equal harness and equal native ID; mismatches never fall back to process |
| OpenCode claim lacks native identity | Refuse Issue-work mutation; a PTY's backend ancestry is insufficient |
| OpenCode identity is named but corroboration is missing | Refuse mutation; report unknown activity instead of borrowing another conversation's evidence |
| Legacy record lacks native identity | Retain only the explicitly supported legacy process route, scoped to the harness; it cannot match a different named session |
| Conflicting native records or multiple eligible legacy candidates | Diagnose conflict; do not choose the freshest conversation to authorize a mutation |

New OpenCode Work Store record names must distinguish native identities sharing
one process. Encoding an opaque ID into a safe filename is a storage detail;
the full identity in the validated record remains authoritative. A digest must
not silently alias another identity. Do not migrate existing record names merely
by observing them: `ActiveWork.run_id` currently includes the record name, so a
rename can also change an Agent Run's identity.

Initially preserve existing Codex and Claude Code record formats and filenames.
Their normalized native identities should obey strict matching too. Migration
of identity-less records needs explicit compatibility tests and an opt-in path;
OpenCode support does not require a bulk rewrite of legacy Work Stores.

## Put evidence reconciliation behind one interface

Deepen the existing hook-record module into the place that owns validated
session evidence. Its callers should not each understand generations, ordering,
legacy formats or ambiguous matches. Keep its public responsibilities small:

1. **Accept a publication:** validate and atomically reconcile a harness event,
   returning acceptance, rejection or unavailable evidence.
2. **Confirm a command:** resolve its claim and corroboration to one Agent
   Session, Observation Location and Issue-work authority, or return a refusal.
3. **Observe sessions:** return normalized evidence for the current observation
   pass, with diagnostics and process liveness supplied through the existing
   fakeable process lookup.

Publisher registration and retirement are publication variants. Private
implementation details can use the existing locked atomic record primitive.
The Work Store continues to own Agent Runs separately; accepting ordinary
activity or bootstrap evidence never creates, switches or relocates Issue work.
Explicit conversation-end handling may invoke the existing end-reconciliation
seam with an exact native identity.

The OpenCode adapter owns native hook interpretation, parentage and environment
injection. Shared code owns identity matching, storage validation and evidence
selection. The adapter also declares that process-only command identification
is unsupported and that plugin disposal is observation loss. Prefer these
concrete varying behaviors over another framework for third-party extensions.

## Track publisher lifetime without redefining Agent Session

The following protocol is a **recommendation**, not an accepted decision or
new shared terminology. A generation is one plugin instance, identified by an
opaque random value created before its first publication. Its scope includes
the exact backend process key (PID and start time) and canonical plugin
Worktree. It is neither an Agent Session Identity nor an Agent Run identity.
One generation can observe several native sessions.

### Small interface and retained facts

Keep three public operations, with registration, retirement and command
bootstrap represented as publication variants. Illustrative calls, not final
Python types or CLI spelling:

```python
view = evidence.observe(repository, lookup=process_lookup)
registered = evidence.publish(
    Register(generation, backend, location, expected_revision=view.revision)
)
ready = evidence.publish(
    CommandBootstrap(generation, session_metadata, sequence=18, command_id=nonce)
)
with evidence.confirm(ready.command_claim, worktree) as confirmed:
    work_store.start(explicit_run_for(confirmed, resolved_issue))
retired = evidence.publish(Retire(generation, backend, location))
```

`publish` returns `accepted`, `duplicate`, `conflict`, `retired` or `unavailable`,
plus a structured acknowledgment when appropriate. `confirm` yields normalized
identity, backend, Observation Location and parentage inside a bounded mutation
context, or returns an actionable refusal. That context holds the coordination
lock until the caller completes its local Work Store operation; it permits no
network work. It does not itself start work. `observe` returns normalized
evidence, conflicts and revision information without repairing state. The
Issue-work command must reconfirm under the coordination lock immediately before
its Work Store write;
a confirmation retained across Issue resolution is insufficient.

Persist in Project-local hook state, separately from the Work Store:

- Registration revision, active generation, accepted registration request, and
  retired-generation identifiers for each backend/plugin-location association.
- Native session metadata, backend association, generation, per-session sequence
  watermark, last accepted request digest, activity and normalized parentage.
- Any conflicting location/backend claims. Do not keep
  a persistent ledger of individual shell invocations in the initial design.
- A pending exact-run reconciliation only when an accepted conversation deletion
  needs to finish its Work Store effect after a crash.

Keep native metadata fetches, ordered queues, cancellation/deadline state and
whether an acknowledgment actually arrived in plugin memory. Neither the
short-lived helper's PID nor its memory is authoritative. Restarting that helper
loses no generation arbitration or accepted session evidence; restarting the plugin
creates a new generation; restarting the backend changes its process key.

For an initial storage implementation, use one versioned evidence document per
backend/plugin-location association, containing its generations and session
entries. Registration, retirement, bootstrap, and each activity
update then require one atomic replacement. This is a concrete way to reuse
[LockedRecordStore](../src/dashpot/record_store.py), not a requirement that all
future evidence remain in one JSON document. Measure the cost of rewriting it
before choosing release limits; split records only with an explicit crash
protocol, not an assumption that several renames form one transaction.

### Registration and replacement

1. At initialization, create the generation identifier and read the current
   registration revision before constructing the registration request. Retries
   preserve that request and its expected revision. Verify the backend's exact
   process key from the local host; a new registration requires positive live
   evidence. The publisher subprocess must never stand in for the backend.
2. Under the coordination lock, accept a previously unseen generation only if
   the revision still matches and the association has no active generation.
   A slot retired by its former owner is available; timestamps do not decide
   precedence. Two initializers that read the same revision cannot both win.
3. Repeating the identical successful registration returns its original
   acknowledgment only while that generation remains active. Changed payloads
   with a reused identifier are errors. A stale revision or an already-retired
   identifier cannot become a fresh registration through retry.
4. Retirement is idempotent and names its exact generation. It records a
   tombstone even if that generation's registration has not arrived. If it is
   the current generation, retirement clears that ownership and advances the
   revision. A delayed retirement of another generation never clears the new
   owner. The plugin marks itself closed before sending retirement, stops queue
   admission and ignores any subsequently arriving initialization acknowledgment.
5. A replacement generation may register against the resulting retired revision
   in the same live backend and location. It restores each session's observation
   only after fresh metadata/bootstrap or a current native event. Without fresh
   status, report unknown activity rather than copying the disposed generation's
   busy/idle state. It must not
   list saved conversations and infer current activity from their existence.
   Existing command claims from the retired generation fail; the Agent Run's identity
   and `startedAt` remain unchanged.

A generation that never obtained ownership has no right to publish. An old init
whose original revision is stale must not reread and silently retry as a new
owner. Native creation order cannot be reconstructed from two unrelated requests
that were delayed before either read a revision; the supported contract is one
accepted owner and explicit conflicts, not proof of OpenCode's creation order.
If an unacknowledged registration committed and disposal was lost, it can block
its replacement. Recovery below handles that ambiguity without a timestamp rule.

Keep retirement identifiers and ordering watermarks for the lifetime of the
backend association. Reclaim them only in a publisher/explicit recovery path
when the exact backend process is proven gone, because new registration for a
gone process is refused and other publication variants cannot create a missing
association. Finish or retain any pending exact-run deletion effect before
reclaiming its containing document; process exit cannot discard an unfinished
Work Store reconciliation. Ordinary observation must not use the existing
hook-record stale-pruning path to delete these protocol records.
Unknown liveness is insufficient. No time-based tombstone expiry
or automatic dashboard repair is proposed. Retention for very long-lived or
permanently unobservable backends is a known storage cost.

### Atomicity, concurrency and lock ordering

The current [record store](../src/dashpot/record_store.py) durably replaces one
file: fsync the temporary, rename, then fsync its directory. Its separate keys
and separate Worktree stores are not a repository-wide transaction. The current
[file lock](../src/dashpot/file_locks.py) also waits without a deadline. Both
facts matter to this proposal.

Recommend one OpenCode coordination lock for each local Git Repository, shared
by its linked Worktrees. Place only the lock in the existing machine-local hook
state directory; use the canonical common Git directory as a machine-local lock
locator, never as Repository Identity, and do not write Git administration
metadata. Accepted evidence and Issue Bindings remain Project-local. Independent
clones coordinate independently. This extra lock location is a proposed storage
choice requiring review; it cannot be replaced by unrelated Worktree-local
locks and still exclude concurrent cross-Worktree claims.

Every OpenCode publication, command reconfirmation plus Work Store mutation,
and recovery action acquires that lock first. It then acquires any record locks
in canonical path order. Never enter this protocol holding a Work Store lock;
never run Issue Source requests, native metadata fetches or an external helper
while holding locks. Resolve the Issue first, acquire the coordination lock,
rescan all relevant Worktree evidence and work records, revalidate the command,
then write. Unreadable participating state or an incomplete Worktree inventory
refuses mutation. Observation takes a bounded consistent read through the same
module and reports unavailable evidence when it cannot obtain one.

This deliberately serializes small local writes across sessions. It avoids
exposing generation-lock/session-lock ordering to every caller. The initial
OpenCode scope refuses relocation and duplicate same-session records in other
Worktrees, so an ordinary opt-in replaces at most one Work Store record.
Automatic evidence replacement never edits that record. Existing Codex/Claude
paths keep their lifecycle behavior; shared matching fixes receive regression
coverage before reuse of the new locking path is considered.

For native conversation deletion, record a terminal tombstone and a pending effect
naming the exact observed Agent Run (identity, `startedAt` and backend), then
conditionally remove only that unchanged run and acknowledge completion. A crash
between files leaves a retryable pending effect. A helper retry or explicit
management command can finish it; observation cannot. New work first resolves
that pending effect under the lock. A delayed retry of that pending effect
cannot remove a later run or another session sharing the process. The tombstone
also invalidates pre-deletion command claims and rejects later status/bootstrap
publications for that native identity across generations of this backend,
even if delayed delivery assigns them higher sequence numbers. Native sequence
assignment alone cannot reconstruct an undelivered callback's original order.

The conditional removal must durably unlink the Work Store record before the
pending effect is durably cleared. An already-absent record also needs its
directory persistence barrier before acknowledging reconciliation. Existing
`WorkStore.stop(key)` neither compares the exact current run nor fsyncs the
directory after unlink, so it is insufficient for this protocol. Whether conversation
deletion should end Issue work remains a recommended policy, unlike the agreed
backend restart policy.

## Corroborate the command that is actually executing

Prefer a short-lived installed Dashpot publisher accepting metadata on stdin,
with no listening daemon. The plugin invokes it directly; the spike's receiver
remains experimental. All metadata reads, queue admission, lock acquisition,
helper execution and acknowledgment parsing share one finite shell-hook budget.
A full queue refuses immediately; it cannot create unbounded work behind a
nominal per-request timeout. Select the budget and capacity after measuring the
installed helper. The spike's 250 ms timeout is not a release requirement.

### Command-local acknowledgment

After every successful bootstrap, the helper returns a normalized command claim:
exact harness/native identity, backend process key, accepted generation, canonical
session Worktree and known parentage. It also echoes the current request's opaque
command identifier so the plugin can reject mismatched responses. These values
are injected only into the shell invocation whose acknowledgment arrived in time.
They are claims corroborated by accepted session evidence, not persisted receipts
for individual commands. Their encoding and variable names remain adapter details.

At the start of **every** shell hook, overwrite inherited OpenCode identity and
acknowledgment variables with explicit empty values in that command's environment.
Deleting keys from an augmentation map would leave inherited backend values intact.
On missing ID, metadata failure, budget exhaustion or failed publication, keep
those values empty. Native identity alone cannot authorize Issue-work mutation.
On success, inject the matching acknowledged values. Never mutate the backend's
process-global environment to identify concurrent conversations.

Retain a command-local OpenCode context indicator even on failure. It names the
executing harness, not an Agent Session Identity. For that context, missing or
failed corroboration must refuse mutation without falling back to another
harness's inherited native variables or enclosing process. Otherwise a failed
OpenCode bootstrap launched from Codex could accidentally bind the outer Codex
session. The precise environment contract needs a nested-harness regression.

Normalize parentage from a complete, successfully validated native session
response into `root` or `child(parent_id)`. A valid response with no optional
`parentID` identifies a root; failed or incomplete metadata is `unknown`, not a
root. This is an internal validating representation, not a new shared domain
term. Both the acknowledged claim and current accepted evidence must carry
matching known parentage. Child identity is valid observation evidence, but
cannot authorize independent Issue-work reassignment.

Confirmation requires all acknowledged facts to match current accepted evidence,
an active generation, no session-deletion tombstone and no competing association.
Proven backend exit refuses it. An unobservable backend may use previously
accepted host evidence, as existing sandbox identity does; unknown liveness
cannot establish a fresh backend registration or displace another runtime.
Metadata changes to the acknowledged identity/location/parentage refuse the old
claim rather than reinterpreting its authority. Confirmation is repeated inside
the final Work Store mutation context.

Two concurrent commands C1 and C2 in session A can both remain valid across
ordinary activity. Confirmation does not require equality with the latest
bootstrap or activity sequence. Issue-work writes still serialize under the
coordination lock, so the later accepted operation determines A's one active
Agent Run. A shell can invoke multiple Dashpot commands. Retirement, deletion,
conflicting associations or proven backend exit invalidates its claim; an
accepted replacement generation requires a fresh shell invocation.

This design uses the existing local hook trust model: the installed plugin
truthfully clears inherited state and injects values only after an acknowledgment.
It does not independently prove to the command validator which exact bootstrap
produced those values, nor defend against a hostile process owned by the same
user. That stronger requirement would justify a different protocol. The initial
requirement is that a failed current shell hook cannot reuse ambient old evidence.
A shell successfully prepared before silent plugin loss can continue using its
accepted generation until contradictory evidence appears; no detection deadline
or implicit claim expiry is promised.

### Failure and acknowledgment loss

Assign a per-session sequence, scoped to `(generation, native identity)`, when
the plugin admits an event; callbacks pass through a finite ordered queue.
An exact duplicate of the most recent accepted request can return its original
acknowledgment without refreshing activity. A reused sequence with different
content or an older sequence is rejected. Retries must preserve the original
request, not obtain a newer sequence to override intervening evidence. If a
bootstrap retry is now older than accepted activity, refuse it; a later fresh
shell invocation can publish new corroboration. Correctness does not depend on
recovering every lost acknowledgment.

A duplicate acknowledgment requires a durability barrier too. After a helper
crashes between rename and directory fsync, visible JSON alone does not establish
that the update is durable. Under the lock, re-establish durable accepted state
before reporting duplicate success. Generation registration follows the same
rule. Duplicate native idle signals may advance the watermark, but must not
reset the activity clock when they report the same transition.

On deadline, stop waiting, cancel metadata/queued work where possible and
terminate the exact helper process. Use deadline-aware lock acquisition rather
than assuming a blocking `flock` is bounded. Termination cannot promise rollback:
the helper might have renamed or fsynced the new evidence already. It also
cannot guarantee immediate reap if the operating system stalls in I/O; the
shell hook's return must not wait indefinitely for reap. Bound outstanding
helpers and refuse admission while a timed-out helper remains unresolved.

If the durable write succeeds but its acknowledgment is lost or late, the current
shell receives **no command claim**, even if the record is visible. An older
valid session record or unrelated activity cannot repair its empty environment.
Within the original budget only, an idempotent retry may recover an acknowledgment.
After returning the environment, there is no background injection or retroactive
authorization. A later fresh invocation can publish its own bootstrap.

Publication failure does not itself prove a session idle, ended or orphaned.
Report a bounded diagnostic to the caller with a stderr fallback. If the store
cannot accept a failure indication, the dashboard cannot know callbacks were
lost: its last accepted observation remains last known, not a promise of current
publisher health. Known retirement makes activity unavailable immediately; silent
observation loss while the backend stays alive has no detection deadline under
this protocol. No heartbeat or lease is proposed.

### Alternatives and what they add

| Alternative | Tradeoff |
| --- | --- |
| Native ID plus a hook record, without clearing failed-shell claims | Old-good-record/current-bootstrap-failed case remains unsafe |
| Command-local acknowledgment checked against accepted evidence | Recommended initially; trusts the installed plugin's environment handling and avoids per-command persistent state |
| Independently persisted immutable receipt for every command | Adds independently checkable exact-bootstrap provenance, but needs storage limits, reclamation, retry semantics and a policy for long-running shells; not required by the current trust model |
| Latest bootstrap sequence as command proof | C2 invalidates C1 before C1 reaches `work start`; unsuitable for overlapping commands |
| Consume a receipt on first mutation | Breaks multiple operations within one shell and complicates retry after successful writes |
| Persistent broker or heartbeat/lease protocol | Adds another process lifetime and scheduling contract; not needed to make failed bootstrap refuse mutation |

## Recovery and scenario outcomes

For the initial release, recommend refusing automatic takeover when a plugin
replacement finds an active predecessor in the same live backend. Missing
clients, helper exit, silence and newer timestamps do not prove retirement.
If the old generation cannot publish its own retirement, the recovery path is
an operator-initiated backend restart, followed by explicit `work start` for
each conversation whose Issue work should resume. This disrupts other clients
of that backend, so observation must describe the conflict rather than perform
the restart. Positive proof that the old backend is gone is still required to
replace its run association; a restart instruction does not make unknown
process evidence sufficient.

An optional later observation-recovery command could preserve a running backend
by explicitly retiring one named generation and admitting another. It would need
a bounded candidate-request lifecycle: admission, retained request identity,
acknowledgment retrieval, cancellation on plugin disposal, and reclamation.
The saved draft did not define those facts for rejected registrations. Before
adding such a command, specify how it confirms that a candidate has not itself
been disposed, revalidates a concrete preview under the coordination lock, and
prevents delayed requests from regaining ownership. Ordinary `integrate`,
`work start`, startup and observation must not silently perform this takeover.
This extension is deferred, not part of the initial protocol.

Different backend processes claiming the same native session, or conflicting
native/plugin directories across linked Worktrees, are unsupported concurrency.
Under the repository lock retain the conflicting claim as diagnostic evidence;
refuse confirmation for *both* associations instead of selecting a winner by
freshness. Retirement/withdrawal of the conflicting publisher, or proof its
backend is gone, permits reconciliation by a subsequent publisher action. An
operator must correct the native location or stop the unwanted instance;
observation recovery cannot override location, authorize relocation or merge two
backends. No session record is moved merely because a shell supplied another cwd.

A new backend can register its plugin independently. Bootstrap for a native
session formerly associated with a gone backend can establish new observation,
but joins to Agent Runs require both native identity and the recorded backend
association for OpenCode. The old Agent Run remains orphaned. Explicit
`work start <issue>` may replace its same-Worktree record only after confirming
the old backend is gone; it produces a new `startedAt` and Agent Run identity.
If the old backend is live or unknown, refuse the restart until that conflict
is resolved. Refuse a surviving record in another Worktree while relocation
remains outside scope. An explicit stop can reconcile a specifically selected
Orphaned Agent Run under the existing management authority; for OpenCode it must
require positive gone evidence. The current external-stop helper tests only
whether a recorded process is live, so its unknown case needs explicit attention
rather than being assumed safe. Observation cannot perform this recovery.

| Scenario | Expected outcome |
| --- | --- |
| Two different native sessions in one backend | Independent command claims, activity and Agent Runs; no process-based identity collision |
| Two commands in one native session | Both acknowledged claims stay valid across ordinary activity; Issue-work writes serialize |
| Valid old claim/record, current metadata or bootstrap failure | Current shell receives neither inherited proof nor new proof; mutation refuses |
| Durable bootstrap, acknowledgment timeout | Record may exist; current shell still refuses, later fresh shell can recover |
| Duplicate init, activity or disposal | Idempotent exact duplicate; no repeated transition or new Issue Binding |
| Delayed old init/activity/disposal after replacement | Old generation cannot take ownership, overwrite activity or retire the new owner |
| Two publishers race to register | One comparison succeeds; the other reports conflict without a retry that steals ownership |
| Helper restarts after writing evidence | Durable revision and watermarks govern the retry; helper PID is irrelevant |
| Orderly plugin replacement in same backend/location | Fresh corroboration restores observation; preserve existing Agent Run |
| Disposal lost, old backend live | No automatic takeover; operator backend restart and explicit Issue-work start |
| Plugin silently disappears, backend live | No guaranteed detection; no inferred end; a fresh command without proof cannot mutate |
| Backend PID absent or reused with different start time | Proven gone; old bound work is orphaned; explicit start under the new backend creates a new run |
| Backend inaccessible or missing process identity | Unknown; do not infer retirement, transfer work or reclaim ordering evidence |
| Session metadata and plugin directory disagree | Diagnostic and refusal; tool cwd does not repair the mismatch |
| Same native identity simultaneously claims linked Worktrees/backends | Conflict for both; no freshest-record winner and no implicit relocation |
| Native child executes Issue-work command | Valid child observation, refused independent reassignment; parent activity still aggregates children |
| Pending conversation-deletion effect retries after another run began | Exact-run conditional reconciliation leaves the newer run untouched |

## Activity, lifetime and authority

| Observation | Proposed behavior |
| --- | --- |
| Busy or automatic retry | Agent Session activity is running |
| Parent idle with a running child | Parent's Agent Run remains running |
| Parent and all observed children idle | Agent Run is waiting; native duplicate idle events do not reset its clock |
| Child status unavailable | Do not manufacture child completion; preserve uncertainty in the aggregate |
| Native child invokes `work start`, `stop` or relocation | Refuse independent reassignment; child identity is valid observation evidence, not parent Issue-work authority |
| Fork appears | New unbound Agent Session; no copied binding or inferred parent authority |
| Attached client exits | No change to the backend's other clients or the conversation's Issue Binding |
| Plugin generation is disposed | Activity evidence becomes unavailable; retain the Issue Binding |
| Backend is proven gone | Report affected bound work as orphaned; do not turn absence into graceful session-end reconciliation |
| Backend cannot be observed | Liveness stays unknown; do not end work |
| Native conversation is deleted | Reconcile only that native session's Agent Run; parent/child deletion races need explicit tests |

**Agreed initial resume policy (2026-09-13): require explicit restart of Issue
work after a backend restart.** A new OpenCode backend can resume the same
Agent Session Identity, but its startup, session bootstrap and activity events
must not transfer the previous Agent Run to the new process association. The
agent must invoke `work start <issue>` again, with the normal corroboration and
conflict checks, to begin a new Agent Run. Any surviving previous Work Store
record remains associated with the old process until explicitly reconciled;
new-runtime activity must not make that old run look active again.

This policy distinguishes continuation of a saved conversation from continuation
of declared Issue work. Automatic Agent Run preservation across backend restart
is deferred beyond the initial integration. It does not imply a lease,
heartbeat, timeout-based end, or permission to treat unknown liveness as gone.

For plugin replacement within the same backend and location, the proposal
remains to restore observation of the existing Agent Run after validating the
replacement generation. Closing and reconnecting an attached client is not a
backend restart.

Cross-Worktree continuation is deferred. A tool requested in another Worktree
cannot move the session, and two concurrent runtime/location associations for
one native identity must produce a diagnostic and mutation refusal until an
explicit relocation contract is designed.

## Concrete code changes to plan

| Existing seam | Why it needs attention |
| --- | --- |
| [work.py](../src/dashpot/work.py): `identify_agent_session`, `_session_identity` | Host ancestry is currently primary; even a confirmed native identity becomes a process-keyed record when a process is known |
| [work.py](../src/dashpot/work.py): `_session_work`, `start_issue_work`, `stop_issue_work` | Exclude process fallback after native mismatch; revalidate acknowledged command facts inside the final mutation context; require gone evidence before replacing an old backend association or externally stopping its run |
| [agents.py](../src/dashpot/agents.py): `ObservedActivityIndex.adopt` | A missing named session currently falls through to another session on the same process; OpenCode also requires the recorded backend association when joining new observation to old work |
| [agents.py](../src/dashpot/agents.py): `run_identities` | Shared process identity can mark distinct native sessions as conflicting Agent Runs |
| [hook_records.py](../src/dashpot/hook_records.py): `locate_agent_session`, `HookRecordStore` | Lookup admits process matches; record naming is native-ID-only and writes have no generation ordering contract |
| [work_store.py](../src/dashpot/work_store.py): `end_session_runs`, `replace_current`, `stop` | Native identity OR process matching can end another conversation's work; add exact-current conditional stop for retryable end reconciliation |
| [record_store.py](../src/dashpot/record_store.py): `LockedRecordStore.replace`, `locked` | One-file durable replacement is reusable; repository coordination and deadline-aware acquisition are additional requirements |
| [liveness.py](../src/dashpot/liveness.py): `session_liveness`, `LivenessProbe` | Reuse PID/start-time proof and per-pass memoization; unknown never authorizes takeover or orphan recovery |
| [harnesses.py](../src/dashpot/harnesses.py) | Express native-identity requirements without treating backend recognition as session identification |
| [integrate.py](../src/dashpot/integrate.py) | Add managed OpenCode plugin installation/status/removal without assuming every harness uses hook JSON |

Use Pydantic models on the shared base for new publication and persisted shapes;
normalize to frozen, slotted dataclasses internally. Decide versioning and
backward-compatible readers only after the identity, generation and acknowledgment
contracts are settled. Leave existing record formats readable throughout.

## Implementation sequence and decisions to resolve

1. Establish strict native matching through `identify_agent_session`, the
   Issue-work commands, `WorkStore` and `observe_agent_runs` using fake process
   lookup. Cover missing A evidence with busy B on the same process, two named
   runs sharing a backend, cross-harness native-ID collisions, and ending A
   without affecting B. Existing tests cover named-A preference when A exists,
   and end isolation across different processes; neither proves these cases.
   Preserve legacy identity-less freshest-process observation with its diagnostic
   where currently supported; that observation rule does not authorize ambiguous
   Issue-work mutation.
2. Implement the publication module with temporary Project-local stores, an
   injected process lookup and controllable clock. Exercise registration races,
   retirement-before-init, exact duplicates, altered duplicate payloads, stale
   sequences, delayed old disposal, helper restart and rejection of ambiguous
   generation takeover through `publish`, `confirm` and `observe`. Include simultaneous conflicting
   claims at linked Worktrees. Assert outcomes and retained accepted facts,
   not JSON filename layout.
3. Test command corroboration through `start_issue_work`/`stop_issue_work` and
   public `WorkStore` reads: C1/C2 overlap; old proof with failed fresh bootstrap;
   unchanged command claims across activity; retirement between Issue resolution
   and mutation; inherited variable clearing and refusal of outer-harness
   fallback; complete root metadata versus failed metadata; unknown versus gone
   backend; and a backend restart that never adopts the prior run
   until explicit start. Use a controlled publisher subprocess fixture to
   distinguish write-before-ack-timeout, wait-on-lock timeout and helper crash
   around rename. Exercise the new exact-current stop with a newer run inserted
   before pending deletion reconciliation retries. Check deletion invalidates
   existing shell claims, later status cannot reopen a deleted conversation,
   duplicate acknowledgment re-establishes durability, and pruning retains
   unfinished deletion effects.
4. Add the OpenCode adapter and explicit managed installation once the supported
   legacy/local scope is accepted. Verify that installed short-lived helpers
   expose the backend's host process key and impose the complete hook budget.
   Test native child authority and running-child aggregation through
   `observe_agent_runs` and Issue-work commands. Re-run Codex declared relocation,
   sandbox identity and Claude Code SessionEnd regressions. The normal repository
   gates remain required before implementation commits.
5. Record accepted tradeoffs in a new ADR and update shared vocabulary when
   agreed; split implementation Issues at these testable seams. This proposal
   does not amend
   [ADR 0007](adr/0007-identify-sandboxed-sessions-by-agent-session-identity.md),
   [ADR 0015](adr/0015-reconcile-the-agent-run-at-session-end.md),
   [ADR 0016](adr/0016-hold-a-session-running-while-its-sub-agents-work.md), or
   [ADR 0029](adr/0029-preserve-agent-runs-through-declared-codex-relocation.md).

The **agreed decision** is explicit Issue-work restart after backend restart.
The following remain recommendations for review:

- Defer a separate observation-recovery command initially and use operator
  backend restart for lost disposal. This is simpler, but interrupts other
  conversations sharing that backend.
- Use the trusted command-local acknowledgment checked against accepted evidence.
  Independently auditing each exact bootstrap would be a stronger requirement
  and would need a separate persisted-receipt design.
- Accept the repository coordination lock and grouped Project-local evidence
  storage. Coarse serialization is easier to reason about but needs latency
  measurement and a writable shared lock location.
- Accept native conversation deletion as exact-run termination, and the initial
  local legacy-plugin/client scope. Neither follows automatically from the agreed
  backend restart policy.

Later isolated experiments must verify local TUI startup/exit, actual installed
helper ancestry and startup/lock latency, queue saturation, and disposal/reload
while shell invocations overlap. The retained trace does not prove those
contracts, durable receiver restart, crash persistence, or generation arbitration.
Verify cross-directory metadata and simultaneous clients explicitly before
supporting any relocation. V2 and remote backends remain outside this proposal's
verified scope. If independently persisted command receipts are later required,
verify which completion callbacks cover every `shell.env` invocation before
relying on them for reclamation.
