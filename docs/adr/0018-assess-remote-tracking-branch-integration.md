---
status: accepted
---

# Assess Remote-Tracking Branch integration

The Branches pane joins local and Remote-Tracking Branches by name, but its
`INTEGRATED` fact was assessed only for local refs. Deleting an integrated
local Branch therefore turned a useful `⊆` or `≡` into `-` while the same tip
remained under `refs/remotes`. A remote-only row could report presence and
freshness but not the Git fact needed to decide whether its work had landed.

Dashpot will assess every concrete local and Remote-Tracking Branch ref
against the Integration Branch. It uses ADR 0012's exact reachability first
and ADR 0017's content integration for retained commits. Results for refs at
the same commit are reused within an observation, so synchronized local and
Remote-Tracking Branches do not repeat the Git work.

The Branches pane keeps its local-first meaning. When a local ref exists,
`INTEGRATED` renders that ref's result. A remote-only row renders the result
when all its Remote-Tracking Branches name the same commit and carry the same
integration facts. Divergent remotes report `⊘`; one cell must not silently
choose a remote or imply that every observed tip is safe to remove.

The result is an observation of local Git state. Dashpot never fetches while
observing, so integration reported for a Remote-Tracking Branch is qualified
by the same last-fetch age as its presence. It neither queries a forge nor
claims that deleting a Branch is appropriate under a hosting workflow.

## Considered options

- **Keep remote-only integration unavailable:** rejected because the concrete
  ref required for the existing comparison is already present, and discarding
  a known result makes cleanup harder immediately after local cleanup.
- **Choose `origin` or the first remote:** rejected because Branch identity
  joins every remote of the same name and another remote may retain different
  work.
- **Treat a merged pull request as integration:** rejected because Branch
  observation remains Git- and Issue-Source-independent, and Local Markdown
  Projects have no forge fact.
- **Fetch before comparing:** rejected under the passive observation rule.
  The pane already exposes the Remote-Tracking facts' age and provides the
  explicit `f` Remote Fetch.

## Consequences

- Remote-Tracking Branch records now populate `unintegratedCommits` and
  `contentIntegrated` in the headless JSON; the wire shape is unchanged.
- A sole remote tip can render `⊆`, `≡`, or `↑N`. `-` remains the UPSTREAM
  fact that a remote-only row has no local ref; `⊘` is the INTEGRATED fact
  when comparison is unavailable or remote tips disagree.
- Integration observation may do more Git work for remote-only tips with
  retained commits. Facts are cached by commit within one observation, and
  no network or Repository mutation is introduced. Measured on 2026-09-03
  under [#100](https://github.com/ned2/dashpot/issues/100) through
  `observe_branches` on disposable repositories: Remote-Tracking refs the
  Integration Branch reaches cost nothing beyond the one `--merged` listing
  (1000 such refs, 3 Git commands, 0.04 s), while each ref with retained
  commits costs three Git commands, about 13 ms (100 such refs 1.4 s, 300
  refs 4 s), the same per-ref cost a local Branch with retained commits
  already paid under ADR 0017. A Repository with hundreds of unmerged remote
  Branches therefore spends seconds per observation, off the event loop;
  batching the content check is the follow-up if that is ever felt.
- This decision extends ADR 0012 and ADR 0017 where they scoped integration
  fields and assessment to local Branches.
