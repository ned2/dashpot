# GitHub CLI feature delta relevant to Dashpot

Date: 2026-08-27

The machine has GitHub CLI `2.46.0`, released 2024-03-20. The latest upstream
release is `2.98.0`, released 2026-08-20.

Sources:

- [GitHub CLI 2.46.0 release](https://github.com/cli/cli/releases/tag/v2.46.0)
- [GitHub CLI 2.98.0 release](https://github.com/cli/cli/releases/tag/v2.98.0)

## Assessment

The installed CLI is old enough to materially impair Dashpot's manual GitHub
Issue workflow, but it does not currently impair Dashpot's read-only GitHub
adapter. The adapter calls `gh api graphql` and owns its GraphQL query,
normalization, and pagination. It does not call `gh issue list`, `view`,
`create`, or `edit`.

An upgrade is nevertheless recommended. `2.97.0` fixed several security issues,
including terminal escape-sequence injection affecting `gh api`, unsafe request
path construction, and partial token disclosure from `gh auth status`.

Source: [GitHub CLI 2.97.0 security release](https://github.com/cli/cli/releases/tag/v2.97.0)

## Relevant feature delta

| Area | Installed `2.46.0` | Upstream `2.98.0` | Dashpot consequence |
|---|---|---|---|
| Raw GraphQL transport | Supports the `gh api graphql -f` invocation Dashpot uses | Same core transport, plus later API conveniences and security hardening | No current functional blocker; upgrade for security rather than adapter semantics |
| Issue types | Not exposed by high-level `gh issue` commands | Create, edit, filter, view, and export `issueType` | Directly matches Dashpot's optional `issueType` field and improves dogfooding |
| Parent/sub-issues | No high-level flags or JSON fields | `--parent`, `--add-sub-issue`, `--remove-sub-issue`; `parent`, `subIssues`, and `subIssuesSummary` JSON | Removes the need for hand-written GraphQL during manual issue management |
| Dependencies | No high-level flags or JSON fields | Create/edit blocked-by and blocking relationships; export `blockedBy` and `blocking` | Directly matches Dashpot's relationship model and closeout workflow |
| Complete relationship reads | Only possible through raw API | High-level JSON exists, but returned relationship nodes are capped | Dashpot should retain its explicit GraphQL pagination rather than switch collectors |
| API pagination output | No `--slurp` | `gh api --paginate --slurp` wraps pages in an array | Not useful to the current adapter, which must also paginate nested connections independently |
| Pull request worktrees | `gh pr checkout` reuses the current checkout | `gh pr checkout --worktree PATH` | Useful contributor convenience and aligned with Workspace discovery, but not part of Dashpot's model or collector |
| Issue search | Conventional issue search | Semantic and hybrid search via `gh search issues --search-type` | Possible future server-side discovery mode; not relevant while Dashpot collects complete snapshots |
| GitHub Projects | Mostly ID-oriented project item operations | Project item query/filtering and name-based field/value addressing | Not currently relevant: a Dashpot Project is a repository, not a GitHub ProjectV2 |

GitHub CLI `2.94.0` is the pivotal release for Dashpot. It added high-level
support for issue types, parent/sub-issue hierarchy, and blocked-by/blocking
relationships to `gh issue create`, `edit`, `view`, and `list`.

Sources:

- [GitHub CLI 2.94.0 release](https://github.com/cli/cli/releases/tag/v2.94.0)
- [`gh issue create` manual](https://cli.github.com/manual/gh_issue_create)
- [`gh issue edit` manual](https://cli.github.com/manual/gh_issue_edit)
- [`gh issue view` manual](https://cli.github.com/manual/gh_issue_view)
- [`gh issue list` manual](https://cli.github.com/manual/gh_issue_list)
- [Official `gh` skill relationship and output-shape guidance](https://github.com/cli/cli/blob/trunk/skills/gh/SKILL.md)
- [`gh api` manual](https://cli.github.com/manual/gh_api)
- [`gh pr checkout` manual](https://cli.github.com/manual/gh_pr_checkout)

## Recommendation

1. Upgrade contributor and dogfooding environments to current upstream `gh`,
   presently `2.98.0`.
2. Do not rewrite `GitHubIssuesSource` around `gh issue list --json`. Its
   high-level relationship projections are convenient but capped, conflicting
   with Dashpot's complete-snapshot invariant.
3. Do not require `gh >= 2.94` for the existing read-only adapter merely because
   that version added high-level relationship commands. Specify and test the
   actual `gh api graphql` capability Dashpot needs.
4. Revisit `2.94` as a minimum only if a future mutation adapter deliberately
   uses `gh issue create/edit`. Direct GraphQL mutations may still provide a
   narrower and more deterministic adapter boundary.
