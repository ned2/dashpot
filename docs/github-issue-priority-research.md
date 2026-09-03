---
status: research
date: 2026-08-29
---

# GitHub Issue priority support and established conventions

Research date: 2026-08-29

## Executive conclusion

GitHub now has first-class, Issue-level priority. **Issue fields** became
generally available on 2026-07-02 for every GitHub organization on Free, Team,
Enterprise, and GitHub Enterprise Cloud with data residency. Each organization
receives a default `Priority` single-select field with `Urgent`, `High`,
`Medium`, and `Low` options
([GA announcement](https://github.blog/changelog/2026-07-02-issue-fields-are-now-generally-available/),
[Issue field administration](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#default-fields)).

That support does **not** apply to Dashpot's present GitHub Issue Source.
Issue fields are defined for an organization and apply across repositories
owned by that organization. `ned2/dashpot` is owned by a personal account—the
GitHub API reports `ned2` as `type: User`—so it cannot receive the native Issue
`Priority` field unless the repository moves to an organization or GitHub
extends the feature to user-owned repositories
([organization scope](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization),
[repository Issue API field rules](https://docs.github.com/en/rest/issues/issues#list-repository-issues),
[`ned2` account API](https://api.github.com/users/ned2)).

Dashpot should therefore retain its label-derived priority now. It should not
replace that convention with a personal Project field: a Project field belongs
to one Project item, so the same GitHub Issue can have different priorities in
different Projects. If Dashpot later supports native Issue fields, the clean
precedence is an explicitly configured organization Issue field, followed by
the existing label convention. Project priority should be a separate,
explicitly configured source because its scope and meaning differ
([GitHub's Issue-field migration guidance](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#migrating-from-project-fields-to-issue-fields)).

## Three different things called priority

| Representation | Owner and value scope | First-class semantics | Fit for Dashpot |
| --- | --- | --- | --- |
| Organization Issue field `Priority` | One organization defines the field; one value lives on each Issue and is consistent in every Project containing it | **Yes.** GitHub creates it by default as a single-select Issue field | Best future GitHub source, but unavailable to the current user-owned repository |
| Project custom field named `Priority` | One user or organization Project defines it; one value lives on that Project item | No special type: it is an ordinary custom single-select convention | Useful for one curated Project, but ambiguous for an Issue Source unless a Project is explicitly selected |
| Repository labels such as `priority/P1` | One repository owns the labels; an Issue may carry zero, one, or several | No built-in exclusivity, option order, or priority type | Portable to user-owned repositories and already supported by Dashpot, but convention must be validated locally |

There are also two unrelated uses of the word in GitHub's API: Project item
position and sibling sub-Issue position. Those are manual ordering, not an
Issue urgency field. They should not be interpreted as a GitHub Issue's
priority
([Project item position mutation](https://docs.github.com/en/graphql/reference/projects#updateprojectv2itemposition),
[sub-Issue position mutation](https://docs.github.com/en/graphql/reference/issues#reprioritizesubissue)).

## Native organization Issue fields

### Data and ownership semantics

The default `Priority` is structured Issue metadata, but it is not a fixed
`Issue.priority` enum. It is an automatically created organization Issue field
whose type is single-select. Organization owners can rename or delete the
field, rename/reorder/recolor its options, or add options. An integration must
therefore discover or configure the field and option identities; assuming the
English name `Priority` and four fixed spellings is not a durable contract
([default field customization](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#default-fields),
[GraphQL Issue field types](https://docs.github.com/en/graphql/reference/issues#issuefields)).

Issue fields are organization-wide rather than repository-wide. The same field
is available to Issues in every repository in the organization, and its value
stays with the Issue across all Projects which contain it. This solves the
cross-repository schema drift inherent in labels and the per-Project divergence
of custom Project fields
([Issue fields in Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-issue-fields),
[migration semantics](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#migrating-from-project-fields-to-issue-fields)).

Issue fields currently apply only to Issues, not pull requests. In a Project,
their cells are empty for pull requests, draft Issues, and Issues owned by
another organization. A Project custom field remains the broader option when
one value must cover all Project item kinds
([Issue field limitations](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-issue-fields#adding-an-issue-field-to-a-project),
[setting Issue fields](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-and-managing-issue-fields)).

Organization owners manage field definitions; people with triage access or
greater can edit values. New fields default to `Organization only` visibility.
For a public repository, a field must be made `Public` before unaffiliated
readers can see it through the UI, API, timeline, search suggestions, or a
public Project. This is material to a passive observer: an absent value and an
invisible value cannot safely be treated as the same fact
([field permissions](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-and-managing-issue-fields),
[visibility rules](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#setting-field-visibility)).

Current limits are 25 Issue fields per organization, 100 options per
single-select field, 10 pinned fields per Issue type, and 50 total fields in a
Project. These limits are ample for one priority scale but reinforce that Issue
fields are a managed organization schema
([Issue field limits](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#limits)).

### User interface, search, and ordering

Issue field values appear in the Issue sidebar and, since general
availability, on the repository Issue list. They can be pinned to particular
Issue types so the relevant fields appear during creation and viewing. Pinning
controls presentation; it does not make priority a property of the Issue type
([GA announcement](https://github.blog/changelog/2026-07-02-issue-fields-are-now-generally-available/),
[pinned fields](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#pinning-fields-to-issue-types)).

Repository Issue lists and the Issues dashboard support typed field filters,
including:

```text
field.priority:high
field.priority:high,medium
field.story-points:>5
field."target date":>=2026-03-01
```

The documented repository Issue-list sorts remain created time, update time,
comment count, and reactions; the Issue-list documentation does not currently
define a sort by Issue field option order. Once an Issue field is added to a
Project, Project views can group, filter, sort, use it as a board column, and
chart it
([Issue field search](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#filtering-by-issue-fields),
[Issue-list sorting](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests#sorting-issues-and-pull-requests),
[Issue fields in Project views](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-issue-fields#grouping-filtering-and-sorting)).

### API and automation surface

The feature has full REST and GraphQL support:

- REST API version `2026-03-10` exposes organization field definitions at
  `/orgs/{org}/issue-fields` and per-Issue values at
  `/repos/{owner}/{repo}/issues/{number}/issue-field-values`. The value
  endpoint can list, add, replace, or delete values; single-select writes must
  name an existing option
  ([organization field REST API](https://docs.github.com/en/rest/orgs/issue-fields),
  [Issue value REST API](https://docs.github.com/en/rest/issues/issue-field-values)).
- GraphQL exposes `Issue.issueFieldValues`, typed field and value unions,
  `IssueFilters.issueFieldValues`, creation inputs, and create/update/set/delete
  mutations. Dashpot's existing GraphQL collector could therefore acquire the
  field with the Issue rather than make one REST request per Issue
  ([GraphQL Issues schema](https://docs.github.com/en/graphql/reference/issues)).
- Field changes emit `issues` webhook/Actions activity types `field_added`
  (including updates) and `field_removed`, with the current and previous value
  in the payload
  ([Issue field Actions events](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-and-managing-issue-fields#automating-with-github-actions)).

The current high-level GitHub CLI Issue commands lag this API surface.
`gh issue list --search 'field.priority:high'` can forward the advanced search
syntax, but `gh issue list` and `gh issue view` do not list Issue field values
among their JSON fields, and `gh issue create` has no Issue-field flag. Reading
or writing values from the CLI therefore requires `gh api` (or another API
client) today
([`gh issue list`](https://cli.github.com/manual/gh_issue_list),
[`gh issue view`](https://cli.github.com/manual/gh_issue_view),
[`gh issue create`](https://cli.github.com/manual/gh_issue_create)).

Issue fields also cannot currently be pre-filled by URL parameters or assigned
by an Issue template. Values can instead be set in the sidebar or a Project,
through REST/GraphQL, or by an Action. A bot or Action can classify new Issues,
but it owns policy that GitHub does not infer by itself
([creation limitation](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-and-managing-issue-fields#setting-a-field-value)).

## Older and alternative approaches

### Project custom fields

Before Issue fields, GitHub's own Projects quickstart instructed users to
create an ordinary custom single-select named `Priority` with `High`, `Medium`,
and `Low` options. GitHub still recommends this pattern for Project items. It
works in personal and organization Projects and can cover Issues, pull
requests, and draft Issues
([Projects quickstart](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/quickstart-for-projects#creating-a-priority-field),
[Projects best practices](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/best-practices-for-projects#use-different-field-types-to-add-metadata-to-your-project-items)).

Project views can filter, group, sort, and assign a default option when a new
item is added. Project fields have GraphQL and REST APIs, and `gh project
item-edit` can edit a selected Project item's value
([single-select Project fields](https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-single-select-fields),
[Project field REST API](https://docs.github.com/en/rest/projects/fields),
[`gh project item-edit`](https://cli.github.com/manual/gh_project_item-edit)).

The cost is scope. An Issue outside the Project has no value, one Issue in two
Projects may have two values, and a copied field is a different schema. GitHub
now explicitly calls the Issue field the source of truth and warns that keeping
both Issue and Project fields named `Priority` can confuse users
([GitHub's migration guidance](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#migrating-from-project-fields-to-issue-fields)).

Project automation has additional operational cost. Built-in workflows cover
item addition, status transitions, and archiving; custom priority policy needs
Actions or API calls. A repository `GITHUB_TOKEN` cannot access Projects, so a
Project-writing workflow needs a suitably permissioned GitHub App or personal
access token
([built-in Project automation](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations),
[Project automation with Actions](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/automating-projects-using-actions)).

### Priority labels

Labels remain the most portable convention. They work in personal or
organization repositories, are visible in normal Issue lists and APIs, compose
with other filters, and need no Project membership. Their weaknesses are the
ones Issue fields were designed to address: labels are repository-scoped,
untyped, and do not enforce exactly one option. GitHub creates no default
priority label
([label scope and defaults](https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/managing-labels),
[Issue fields GA rationale](https://github.blog/changelog/2026-07-02-issue-fields-are-now-generally-available/)).

Established label vocabularies include:

- **A shared prefix plus descriptive ordered values.** Kubernetes maintains
  `priority/critical-urgent`, `priority/important-soon`,
  `priority/important-longterm`, `priority/backlog`, and
  `priority/awaiting-more-evidence`, with prose definitions for each. The
  namespace makes the dimension obvious, while the prose avoids implying that
  urgency is only a number
  ([Kubernetes label catalogue](https://github.com/kubernetes/test-infra/blob/master/label_sync/labels.md)).
- **Compact P-levels.** Flutter uses `P0` through `P3` as progressively lower
  priorities, documents P2 as the default, reserves P0/P1 for active escalation,
  and connects the levels to review cadence. Traefik uses the namespaced form
  `priority/P0` through `priority/P3`, very close to Dashpot's existing
  convention
  ([Flutter Issue hygiene](https://github.com/flutter/flutter/wiki/Issue-hygiene),
  [Traefik triage guide](https://github.com/traefik/contributors-guide/blob/master/issue_triage.md#define-priority)).
- **Priority plus a separate demand signal.** Flutter treats thumbs-up reactions
  as popularity input while retaining the maintainer-assigned P-level as
  priority. This avoids letting votes silently become an urgency or severity
  decision
  ([Flutter reactions policy](https://github.com/flutter/flutter/wiki/Issue-hygiene#thumbs-up-reactions)).

The essential discipline is to define one mutually exclusive dimension, say
who may change it, document the default/unprioritized state, and diagnose
multiple recognized labels. Dashpot currently chooses the highest recognized
priority and defaults an unlabelled Issue to P2; that is deterministic but
hides malformed multi-priority labelling and conflates `unset` with `P2`
([Dashpot priority interpretation](../src/dashpot/issue_table.py)).

### Numeric scores

Both organization Issue fields and Project custom fields offer a number type,
so a team can store a rank, impact score, cost-of-delay value, or an externally
calculated prioritization score. Project views can sort by number and show
field sums. GitHub documents number storage and aggregation, but not a formula
field that calculates a score from other fields; a composite score therefore
needs a person, bot, Action, or external integration to calculate and refresh
it
([Issue field types](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-fields-in-your-organization#about-issue-field-types),
[Project number-field sums](https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/customizing-the-table-layout#showing-the-sum-of-a-number-field)).

Scores provide finer ordering than P0-P3, but they add false-precision and
staleness risks unless their formula, inputs, recalculation event, and tie
handling are explicit. A score is also not necessarily the priority users mean:
impact, urgency, severity, confidence, and effort are useful separate inputs.

### Templates, bots, Actions, and forms

An Issue template or form can automatically add a fixed priority label for a
particular intake path. A form can also ask a dropdown question, but form
answers are rendered into the Issue body; they do not become labels or Issue
fields automatically. Dynamic translation from a form answer or other Issue
facts into a priority label/field requires a bot or Action
([Issue form syntax](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)).

Automation is useful for defaults, validation, escalation, or mirroring during
migration. It should not run two bidirectional authorities indefinitely: label
and field edits can race or loop, and users cannot know which one wins. GitHub
publishes a first-party Copilot skill specifically for mapping label families
such as `p0`–`p3` into an Issue field, illustrating a bounded migration rather
than permanent dual ownership
([GitHub Issue-field migration skill](https://github.com/github/awesome-copilot/blob/main/skills/issue-fields-migration/SKILL.md)).

### Milestones, manual order, Issue types, and sub-Issues

These features can complement priority but do not replace it:

- A **milestone** groups repository Issues and pull requests around a goal,
  optionally with a due date and progress. Items can be manually ordered within
  a milestone, but that order is target-specific and is disabled above 500 open
  items
  ([milestones](https://docs.github.com/en/issues/using-labels-and-milestones-to-track-work/about-milestones)).
- **Manual Project position** communicates a preferred pickup sequence. It is a
  total presentation order inside one Project, not an urgency class and not an
  Issue fact
  ([Project table ordering](https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/customizing-the-table-layout#reordering-rows)).
- An **Issue type** classifies kind of work; GitHub's defaults are Task, Bug,
  and Feature. Priority can be pinned to selected types, but `Bug` is not itself
  a priority
  ([Issue types](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/managing-issue-types-in-an-organization)).
- **Sub-Issues** express decomposition and hierarchy, while Issue dependencies
  express eligibility. Neither says which independent Issue is most urgent
  ([sub-Issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues),
  [Issue dependencies](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies)).

The last distinction aligns with the separate
[work-sequencing research](github-work-sequencing-research.md): priority is an
urgency class, not a dependency or exact execution order.

## Recommendation for Dashpot

1. **Keep labels authoritative for the current repository.** The present
   `priority/P0`–`priority/P3` representation is close to established public
   practice and, unlike Issue fields, works in `ned2/dashpot` today. Do not add
   a personal Project merely to relocate the same value.
2. **Tighten the convention before expanding it.** Document P0-P3 meanings and
   whether P2 is a real default or an `unset` presentation fallback. Consider
   surfacing conflicting recognized labels rather than silently taking the
   highest priority. The broad aliases `critical`, `high`, `medium`, and `low`
   are convenient but more collision-prone than the namespaced labels.
3. **Preserve priority as a derived interpretation.** ADR 0001 remains correct:
   GitHub's native Priority is a customizable organization field, Local Issues
   need source-neutral semantics, and user-owned GitHub repositories have no
   Issue field. The model should record which observed evidence produced the
   interpretation rather than assume one universal GitHub scalar
   ([ADR 0001](adr/0001-own-project-and-issue-model.md)).
4. **Add native Issue fields as a future source capability, not a global
   replacement.** Configure by opaque field/option identity or an explicit
   option mapping; do not hard-code the display name. Native Issue field should
   outrank labels when configured. If both are present and disagree, report a
   conflict during migration instead of silently merging them.
5. **Treat Project priority as separate integration scope.** Support it only
   when a Project is explicitly selected and preserve its Project provenance.
   Never infer one Issue priority from an arbitrary Project membership.
6. **If the repository moves to an organization, perform a bounded cutover.**
   Customize the native field to the chosen P0-P3 scale or define an explicit
   mapping from `Urgent`/`High`/`Medium`/`Low`; make it Public if anonymous
   observation matters; bulk-copy label values; audit conflicts and unset
   values; switch the authority; then remove the old priority labels. Do not
   leave two editable sources of truth.

This keeps Dashpot compatible with GitHub's new first-class model without
making an organization-only feature a false invariant of the source-neutral
Issue Profile.
