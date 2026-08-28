# GitHub and Dashpot work-sequencing capabilities

Research date: 2026-08-28

## Executive conclusion

Dashpot cannot currently present or choose a work sequence. It already collects
GitHub's native parent/sub-issue and `blocked by`/`blocking` relationships, but
does not expose them in the Issue table, Issue pane, search grammar, or a
"next Issue" operation. Its default last-action sort, optional priority column,
and arbitrary table sorting are presentation order, not workflow order
([GitHub collection](../src/dashpot/github_issues.py),
[Issue profile](../src/dashpot/issue_profile.py),
[table state](../src/dashpot/issue_table.py),
[Issue pane](../src/dashpot/app.py)).

GitHub Issues can represent **partial work order** directly with native Issue
dependencies: Issue B can be marked as blocked by Issue A. GitHub shows blocked
Issues on repository Issue lists and Project boards, and exposes these
relationships through GitHub CLI and APIs
([creating Issue dependencies](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies),
[REST dependency endpoints](https://docs.github.com/en/rest/issues/issue-dependencies)).

GitHub does not expose a first-class, strictly enforced execution sequence.
This is an inference from its documented primitives: dependencies express
blocking relationships, while manually positioned rows, milestone order,
custom priority fields, and iterations are described as prioritization or
planning tools. Projects is deliberately methodology-neutral
([About Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)).
A total order can be *communicated* with those tools, or modelled as a chain of
dependencies, but GitHub does not turn that order into an exclusive queue or
prevent work from starting out of order.

For Dashpot's current Issues, the cleanest representation is therefore:

- encode only real prerequisites as native `blocked by` relationships;
- use a GitHub Project's manual row position as the preferred pickup order
  among Issues that are currently unblocked; and
- retain priority for urgency, rather than overloading it as sequence.

For example, `#18 -> #19 -> #3` is a genuine prerequisite chain. `#2` can be
ranked first without declaring that `#18` is technically blocked by it, unless
the team explicitly adopts "CI must land before feature work" as a policy.

The current repository does **not** yet use native dependency relationships.
On 2026-08-28, `gh issue view NUMBER --json blockedBy,blocking` returned empty
relationships for every open Issue (#2, #3, #4, #5, #12, #17, #18, #19, and
#20). The dependency statements recently added to Issue bodies are therefore
human-readable prose, not GitHub's structured relationship data
([open Issues](https://github.com/ned2/dashpot/issues)).

## What each GitHub primitive means

| Primitive | What it represents | Does it represent sequence? |
|---|---|---|
| Issue dependencies | An Issue is `blocked by` or `blocking` another Issue. GitHub marks blocked work in Issue lists and Projects. | **Yes: prerequisites / partial order.** This is the strongest native fit. It does not by itself define an order among independent Issues. |
| Sub-issues | Decomposition and hierarchy. GitHub supports up to 100 children per parent and eight nesting levels; Projects can show parent and completion progress. | **No.** Siblings are work breakdown, not prerequisite steps, unless separate dependency edges are added. |
| Markdown task list | Ordered, draggable checkboxes; linked Issues auto-check when closed. GitHub has retired tasklist *blocks* and recommends sub-issues as their replacement, although ordinary Markdown task lists remain. | **Visual order only.** Useful for a small checklist, but weaker than dependency metadata. |
| Milestone | A repository-scoped target grouping with due date and completion progress. Open items inside a milestone can be manually prioritized. | **Priority within a target, not enforced sequence.** |
| Project manual position | Rows/cards can be manually reordered. The GraphQL mutation calls item position its "priority." | **Preferred pickup order, not a dependency.** Sorting a view can replace the visible manual order. |
| Project priority field | Usually a single-select custom field such as High/Medium/Low, with filtering, grouping, and sorting. | **Urgency class, not exact sequence.** Multiple Issues can share a value. |
| Project iteration | A repeating timebox which can be filtered, grouped, sorted, and rolled forward. | **Scheduling bucket, not order within the bucket.** |
| Project date/roadmap fields | Start and target dates place work on a timeline. | **Planned timing, not dependency enforcement.** |

Sources:

- [Creating Issue dependencies](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies)
- [Adding sub-issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues)
- [Parent Issue and sub-Issue progress in Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-parent-issue-and-sub-issue-progress-fields)
- [About task lists](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/about-tasklists)
- [About milestones](https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/about-milestones)
- [Customizing the Project table layout](https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/customizing-the-table-layout)
- [Project item-position GraphQL mutation](https://docs.github.com/en/graphql/reference/projects#updateprojectv2itemposition)
- [About single-select fields](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-single-select-fields)
- [About iteration fields](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-iteration-fields)
- [Customizing the roadmap layout](https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/customizing-the-roadmap-layout)

## Dashpot's latent capability and missing product surface

The GitHub collector requests `parent`, `subIssues`, `blockedBy`, `blocking`,
and `milestone` for every Issue. The source-neutral profile requires and
validates those relationships. This means basic dependency display does **not**
require a new underlying Issue data model
([GitHub collection](../src/dashpot/github_issues.py),
[Issue validation](../src/dashpot/issue_profile.py)).

What is missing is projection and interaction:

- no Blocked/Ready column or indicator;
- no `blocked-by`, `blocking`, parent, milestone, rank, or iteration field in
  the single-Issue pane;
- no dependency-aware filter or sort;
- no distinction between urgency and preferred pickup order; and
- no GitHub Project metadata ingestion, including Project item position,
  custom priority, or iteration values.

Dashpot could first expose native Issue dependencies without integrating
GitHub Projects. A minimal useful surface would show `Blocked by` and `Blocking`
in the single-Issue pane, mark blocked rows, and offer a view of open Issues
whose blocker set is empty. A later Project integration would be needed if
Dashpot should reproduce GitHub's manually curated pickup order or iteration
plan.

## Recommendation for the current plan

1. Record the real dependency graph in GitHub Issue relationships, rather than
   relying only on `Depends on` prose in Issue bodies.
2. Do not create a full dependency chain merely to preserve one conversation's
   suggested order. It would falsely prevent safe parallel work such as CI and
   configuration migration.
3. If a persistent linear backlog is wanted now, create one GitHub Project and
   use manual item position for unblocked work. Add `Status` and retain the
   existing P0-P3 labels or introduce a Project priority field only if the
   distinction is useful.
4. Create a focused Dashpot Issue to expose the native dependency data it
   already owns. Treat GitHub Project ordering as a separate integration
   decision because it introduces a new source and ownership boundary.

This provides two independent answers to "what next?": dependencies determine
what is **eligible**, while Project position determines what is **preferred**.
