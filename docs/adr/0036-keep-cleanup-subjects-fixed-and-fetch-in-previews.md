---
status: amended
date: 2026-09-12
amended-by: 0054-finish-a-worktree-with-its-branch-by-default.md
---

# Keep Cleanup subjects fixed and fetch inside their previews

Amended by [ADR 0054](0054-finish-a-worktree-with-its-branch-by-default.md): a
Worktree's attached Branches start selected on a first preview, ignored content
is disclosed rather than acknowledged, and the retention rule below governs
every refresh but not a first preview's defaults.

A person pressing `x` has already selected a Worktree or Branch row. Requiring
another checkbox for that same concrete target adds no useful choice. Remote
facts can also become stale while a preview is open, forcing the person to
leave the dialog just to invoke Remote Fetch.

## Decision

The dashboard keeps a concrete primary target fixed through its preview and
ordinary confirmation. A Worktree has no redundant checkbox. Its attached local
Branch remains an unchecked, subordinate option and is retained unless selected.
A blocked Worktree offers Close and cannot authorize Branch-only deletion.
Ignored content still requires explicit acknowledgement; all existing occupancy,
protection, integration, and stale-preview checks remain enforced.

The Branch pane groups a local ref and Remote-Tracking Branches by name. Its
preview names the local Branch as primary when present, otherwise the single
remote Branch when unambiguous. When a remote-only row names several remotes,
or the local Branch is blocked while a remote target is available,
the person must explicitly select concrete targets; the dashboard never
arbitrarily promotes one remote to the destructive primary action. Additional
remote targets always start unchecked. A refreshed preview cannot substitute a
different target for a missing primary.

Both dialogs expose `f`, **Fetch & prune remotes**, including when deletion is
blocked. This explicitly invokes the existing non-interactive, timed Remote
Fetch contract from [ADR 0014](0014-fetch-remotes-on-explicit-key-press.md) at the
captured Repository Anchor supplying that Project's Branch facts. It does not
delete a local Branch or Worktree.

The open preview retains its Project reservation while permitting its own
Remote Fetch. Confirmation stays disabled through fetching, post-fetch Git
observation, and re-inspection of the same Cleanup request. Pre-fetch observations
already in flight cannot satisfy this barrier. Failed or stale observation and
failed inspection leave confirmation unavailable until a successful retry.
Remote failures and partial success remain visible and do not claim fresh
knowledge of failed remotes. Git’s repository-wide `FETCH_HEAD` timestamp is
labelled as such, with age where available, never as per-remote verification.
Failed remote targets explicitly retain last-known Remote-Tracking facts.
Guidance also covers detached Worktree reachability and local Branch integration.

Only unchanged optional target identities, expected tips, eligibility, and
disclosed consequences retain selection. New or changed targets start unchecked.
Ignored-content acknowledgement is conservatively reset after every refreshed
preview. The person still confirms the resulting evidence; fetching never
continues into deletion. Closing the dialog releases its Cleanup intent, while
an in-flight fetch retains mutation exclusion until it finishes. Completion may
update observation but cannot reopen the dialog or delete anything.

## Consequences

This amends the dashboard's redundant target-selection step and idle-preview
reservation in [ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md),
and adds a Remote Fetch invocation surface to ADR 0014. CLI target-selection
contracts and final execution safeguards stay in place.

Automatic session relocation from [Issue #148](https://github.com/ned2/dashpot/issues/148)
remains a separate, unverified part of that Issue. These changes do not grant
Dashpot control of live terminals or implement a session handoff. See the
[feasibility research](../cleanup-session-handoff-research.md). Occupying Agent
Sessions and active Agent Runs continue to block removal.
