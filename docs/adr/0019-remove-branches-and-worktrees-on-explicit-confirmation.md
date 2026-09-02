---
status: accepted
---

# Remove Branches and Worktrees on explicit confirmation

Dashpot reports whether a Branch is integrated
([ADR 0012](0012-observe-branch-integration-by-reachability.md),
[ADR 0017](0017-observe-branch-integration-by-content-when-commits-are-unreachable.md),
[ADR 0018](0018-assess-remote-tracking-branch-integration.md)) and whether a
Worktree could be removed (`dashpot worktree check`), but acting on either
means leaving Dashpot and re-deriving the same checks by hand.
[ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)
left Branch and Worktree removal for a separate product decision. This is
that decision.

Dashpot will delete a local Branch, delete a Branch at a remote, and remove a
linked Worktree when a person selects that concrete target from a preview and
confirms it. It is a named mutation under ADR 0008's boundary, invoked from
the dashboard's `x` key on a Branches or Worktrees row and from the
management commands `dashpot branch delete` and `dashpot worktree remove`,
and it mutates only the targets the person selected:

- **Preview, then confirm.** Every invocation first inspects, read-only, and
  presents each concrete target separately — the local ref, the Branch at
  each remote, the Worktree — with its own integration fact, blockers, and
  consequences. Every target starts unselected; nothing is deleted without a
  selection and a confirmation. Confirmation re-inspects, and when anything
  observed has changed since the preview it performs nothing and presents the
  revised preview instead.
- **Selection is the authority; integration is the gate.** A `⊆` or `≡` fact
  makes a Branch target eligible and explains it; it never chooses. A target
  that is `↑N`, `⊘`, checked out, held by an Agent Session or Agent Run,
  dirty, locked, or unavailable is shown as unavailable with the reason and
  the command a person could run. There is no force path.
- **Local Branch deletion is atomic.** The ref is deleted with
  `git update-ref -d refs/heads/NAME <oid>`, whose old-value check refuses a
  tip that moved after the preview, and the `branch.NAME.*` configuration is
  removed afterwards. `update-ref` does not refuse a Branch that is checked
  out in a Worktree — it deletes it and leaves that Worktree's HEAD dangling
  (verified on Git 2.53) — so the checked-out refusal is Dashpot's own, from
  `git worktree list` at inspection and again at confirmation. The
  Integration Branch is never a target.
- **Remote deletion is leased.** A Branch at a remote is deleted with
  `git push --force-with-lease=refs/heads/NAME:<oid> <remote>
  :refs/heads/NAME`, the lease being the Remote-Tracking Branch's tip as of
  the last Remote Fetch. A remote that advanced refuses the push
  (`[rejected] (delete) -> NAME (stale info)`); a remote ref already gone is
  reported as already absent, with the hint to press `f`. Only the canonical
  fetch mapping `+refs/heads/*:refs/remotes/<remote>/*` and a remote with
  exactly one effective push URL are supported, so the Remote-Tracking
  Branch whose fact is shown is the ref the push acts on, and Git itself
  drops that Remote-Tracking Branch on a successful delete push. Dashpot
  issues no separate tracking-ref deletion and never fetches; a tracking ref
  that survives an unknown outcome is left for `f`. The remote's Integration
  Branch is never a target. The push runs non-interactively under the Git
  timeout, with the person's pre-push hook honoured rather than bypassed.
- **Worktree removal is unforced.** `git worktree remove PATH` is run without
  `--force`, so Git refuses modified or untracked files, a lock, or
  submodules, and Dashpot refuses first: a Worktree with an Agent Session,
  an Agent Run, or an unreadable Work Store; the main Worktree; a configured
  Repository Anchor; and the working directory of the Dashpot process
  itself. Unforced removal still deletes ignored content — in this project
  every Worktree's `.venv` and `.dashpot/state`, including its hook store and
  Work Store — so ignored paths are inventoried and must be acknowledged
  explicitly. A detached Worktree is removable only when its HEAD is
  reachable from another local, Remote-Tracking, or tag ref; otherwise the
  preview shows the rescue-Branch command. Unintegrated commits on the
  attached Branch do not block removing the Worktree while the Branch is
  retained; deleting that Branch is a separate target with its own gate.
- **Ordering favours the revisable path.** A Worktree is removed before its
  Branch is deleted. A Branch at a remote is deleted before the local ref: a
  lease refusal is the strongest sign that someone is still working there,
  and a revised preview can only be offered while the local ref exists, so a
  refused or unknown remote outcome stops the local deletion. Operations are
  not transactional and a successful mutation is never rolled back.
- **Every target reports its own outcome.** `deleted`, `already-absent`,
  `refused`, or `unknown` — the last for a timeout or an interrupted remote
  operation that may have succeeded, which Dashpot never retries. A deleted
  target reports its tip OID and the command that recreates it, so the `≡`
  case, whose original commits lose their last named ref, stays recoverable
  until Git prunes them.
- **One mutation per Project at a time.** Cleanup runs off the Textual event
  loop and excludes another cleanup and a Remote Fetch of the same Project,
  since a fetch with prune rewrites `refs/remotes` under a leased push.
  Afterwards the Project's Git state is re-observed the passive way; nothing
  is inferred from the mutation.
- **Which checkout runs Git.** A Branch target mutates at the Repository
  Anchor whose refs supplied the Branch observation, as Remote Fetch does; a
  Worktree target mutates at the Repository its path belongs to.

## Considered options

- **Keep reporting removability and never remove:** rejected because the
  report already computes every gate, and the person then re-derives the
  atomic deletion, the lease, and the checked-out and session checks in a
  shell, where `update-ref -d` and `branch -D` each lack one of them.
- **Delete on the key press, with an undo:** rejected because a remote
  deletion and a removed Worktree's ignored content cannot be undone by
  Dashpot; the preview and confirmation are the undo.
- **`git branch -D` for the local deletion:** it refuses a checked-out Branch
  and removes the Branch configuration, but has no old-value check, so a
  tip that moved between preview and confirmation would be deleted.
  `update-ref -d` with the expected OID is atomic; Dashpot supplies the
  checked-out check and the configuration removal it lacks.
- **Deleting the local ref before the remote:** rejected because a lease
  refusal after the local ref is gone cannot be revised, only reported.
- **Removing the Remote-Tracking Branch after a successful delete push:**
  rejected as redundant; under the canonical mapping Git already removes it,
  and issuing a second deletion would mask a non-canonical mapping.
- **Bulk or automatic deletion of every integrated Branch:** rejected; a
  fact as of the last fetch, without a forge check, is a gate, not an
  authority, and the person selects each target.
- **Forced removal of dirty or locked Worktrees, or stopping an Agent
  Session or Agent Run to free one:** rejected; the reason is shown with the
  command a person could run, and Dashpot runs none of them.
- **Live remote observation before deletion** (`git ls-remote`): rejected
  under [ADR 0005](0005-observe-branches-without-fetching.md); the lease
  answers the same question at the moment it matters.

## Consequences

- ADR 0008's exclusion of Worktree and Branch removal is lifted for this
  decision; its boundary is unchanged. The README's product statement and the
  AGENTS.md orientation name the mutating keys and commands together rather
  than calling `f` the dashboard's one mutation.
- The domain language gains **Remote Branch**, the branch at the remote as
  distinct from its Remote-Tracking Branch, and **Cleanup**, the confirmed
  removal of selected targets.
- Delivery is a PR series on one Issue
  ([#101](https://github.com/ned2/dashpot/issues/101)): read-only inspection
  with the removability assessments split out of `check_worktree`; the local
  management commands with `--dry-run` and JSON; remote deletion on its own;
  the `x` key and its modal; then documentation, the Legend, and fixtures.
  `dashpot worktree check` keeps its report, composed from the split
  assessments.
- The cleanup module calls the Git adapter with structured arguments and
  never executes the command strings `worktree check` renders for people;
  the dashboard injects it the way it injects the fetcher, so a construction
  without one refuses `x`.
- Non-goals: bulk deletion, custom remote-ref mappings, several push
  destinations, forge or open-PR checks, automatic fetching, and atomic
  rollback across filesystem, refs, and network. Each needs its own decision.
