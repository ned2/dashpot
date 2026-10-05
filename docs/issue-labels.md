---
status: living
date: 2026-10-06
---

# Issue labels and triage

This Repository's GitHub Issues carry labels that say what kind of work an
Issue is, how urgent it is, and whether it waits on a person or on something
outside the Repository. Agents triage most Issues here, and people triage the
rest. This document lists the label set and the principles behind it, so that
both apply the labels the same way. The maintainer named here and in
`need/maintainer-input` is the person [AGENTS.md](../AGENTS.md) and the ADRs
call the operator.

These are conventions for developing Dashpot, in this Repository only. They
are not rules for the Projects Dashpot observes, and Dashpot the application
neither reads nor enforces them. One convention looks similar. Dashpot
recognises priority labels (`priority/p0` … `priority/p3`, or `critical`,
`high`, `medium`, `low`) in any observed Project and shows them in the Issue
table's `PRIORITY` column. That is product behaviour, described in the
README's [Usage](../README.md#usage) section. This Repository's `priority/*`
labels appear in that column only because Dashpot observes its own
Repository. The `need/*` and `status/*` labels mean nothing to the
application, and no change should make Dashpot apply them to an observed
Project.

## The principles

1. **`need/*` says who an Issue waits on. Blocked-by says which
   other Issues it waits on. `status/blocked` says what else holds it.** An
   Issue carries a `need/*` label only while someone must act on it:
   a triager, the reporter, or the maintainer. It carries
   `status/blocked` only while a capability or a third party holds it.
   Waiting on another Issue is recorded only as a native blocked-by
   relationship. Whether an Issue can be picked up is inferred from these,
   never labelled, so no label can go stale against a relationship. There
   are no ready-for-agent or ready-for-human labels: an Issue with no
   `need/*` label is free for either an agent or a person to pick up.
2. **`priority/*` measures urgency and nothing else.** Triage gives every
   Issue exactly one priority. A priority does not mark an Issue as triaged
   (removing `need/triage` does that) and is no condition on picking an
   Issue up: a `P3` Issue with no `need/*` label is as free to pick up as a
   `P0`.
3. **`need/maintainer-input` is applied by anyone and cleared only by the
   maintainer.** This asymmetry is what makes the label work. An agent that
   could clear it could decide its own way out of waiting. An agent may
   apply it whenever it reaches a question only the maintainer can settle.
   It removes it only on the maintainer's explicit direction, and it cites
   that direction on the Issue when it does.
4. **Each label records who may apply it and who may clear it.** Most
   labels are open to agents and people during triage. The exceptions are
   `need/maintainer-input`, `wontfix`, and the machine-applied `tasks.md`.
   The [Kubernetes `labels.yaml`](https://github.com/kubernetes/test-infra/blob/master/label_sync/labels.yaml)
   `addedBy` field is the precedent. It matters more here than there,
   because agents do most of the triage.
5. **A label exists because something consumes it.** The consumer can be
   triage, the dashboard's label search, an agent choosing work, or the
   closing of an Issue. A label nothing consumes is removed. This adapts the
   Kubernetes rule ("labels are here because they are intended to be
   produced or consumed by our automation"), and it decided the fate of
   GitHub's default labels [below](#removed-labels).
6. **Prefix namespaces group the axes.** `need/`, `status/`, `priority/`
   and `harness/` each name one axis, following the
   [IPFS label scheme](https://github.com/ipfs/community/blob/master/ISSUE_LABELS.md)
   this taxonomy was aligned with.

## Triage

A new Issue starts with `need/triage`, which `gh issue create --label
need/triage` applies ([issue tracker](agents/issue-tracker.md)). A reporter
who cannot apply labels opens an Issue with none, and triage adds
`need/triage` to it. Triaging an Issue means:

- removing `need/triage`;
- applying exactly one `priority/*` label;
- applying a category label when one fits, and every topic label that
  applies;
- recording each Issue whose work it waits on as a native blocked-by
  relationship;
- applying `need/info`, `need/maintainer-input` or `status/blocked` while
  the Issue waits on a person, a capability or a third party, and saying in
  the Issue what it waits for;
- or closing it with `duplicate` or `wontfix`.

Some label states contradict each other and should never occur on an open
Issue:

- `need/triage` together with a priority;
- neither `need/triage` nor a priority;
- more than one priority;
- `status/blocked` with no named hold;
- a hard ordering on another Issue ("after #N lands", "blocked by #N")
  written in prose and not recorded as blocked-by.

A soft ordering ("coordinate with", "prefer first", a sequence chosen to
avoid conflicts in shared files) is not a blocker and gets no relationship.

Some combinations are allowed. An Issue can carry `need/maintainer-input`
and `status/blocked` at once when the maintainer holds one part of it and a
third party holds another, such as an upstream report the maintainer is to
post and an upstream release the rest waits on.

## Free to pick up

An open Issue with no `need/*` label waits on no one, so it is free for an
agent or a person to pick up. Whether work can start now also depends on
its Open Blockers and on `status/blocked`.

Dashpot's own **Ready Issue**
([domain language](domain-language.md)) is a separate condition: an open
Issue with no Open Blocker, whatever its labels. The dashboard's Ready
lifecycle and `dashpot issue list --state ready` select Ready Issues, and
they read blocked-by relationships only, never labels. So the Ready
lifecycle alone does not exclude an Issue that carries a `need/*` label or
`status/blocked`. To list the open Issues that can be picked up now, choose
the Ready lifecycle and add the exclusions to the search:

```text
-label:need/triage -label:need/info -label:need/maintainer-input -label:status/blocked
```

An Issue whose work lives in its sub-issues can appear in that list. Its
sub-issues are the work.

## The labels

"Triage" in the tables means any agent or person triaging the Issue.

### `need/*`: who the Issue waits on

| Label | Meaning | Applied by | Cleared by |
| --- | --- | --- | --- |
| `need/triage` | Not yet evaluated. The default for a new Issue. | Whoever opens the Issue | Triage, when it finishes |
| `need/info` | Waiting on the reporter for specific information. The Issue says what is missing. It sits beside `need/triage` when triage itself waits on the answer. | Triage | Triage, once the reporter answers |
| `need/maintainer-input` | Cannot proceed without a decision, approval, or access only the maintainer can give. The Issue says what is needed. | Anyone | The maintainer only, or an agent on the maintainer's explicit direction ([principle 3](#the-principles)) |

### `status/blocked`: held by something that is not an Issue

| Label | Meaning | Applied by | Cleared by |
| --- | --- | --- | --- |
| `status/blocked` | Held by something other than another Issue: an unavailable capability (a host, a login, a platform feature) or a third party such as an upstream fix. The Issue names what holds it. Waiting on another Issue uses blocked-by instead, and a pending decision uses `need/maintainer-input`. | Triage | Triage, when the hold lifts |

### Blocked-by: native relationships, not labels

An Issue that waits on other Issues records each of them as a native GitHub
**blocked-by** relationship. Prose alone is not enough, and no label
repeats the relationship. Dashpot's `WAITING ON` column and Ready lifecycle
read these relationships, so they stay current as Open Blockers close. Triage
adds and removes them.

### `priority/*`: urgency

| Label | Meaning | Applied by | Cleared by |
| --- | --- | --- | --- |
| `priority/P0` | Critical | Triage | Triage, by replacing it with another priority |
| `priority/P1` | High | Triage | Triage, by replacing it with another priority |
| `priority/P2` | Normal | Triage | Triage, by replacing it with another priority |
| `priority/P3` | Low | Triage | Triage, by replacing it with another priority |

Consumers: the dashboard's `PRIORITY` column and ordering, and anyone
choosing what to work on next.

### Category: what kind of work

| Label | Meaning | Applied by | Cleared by |
| --- | --- | --- | --- |
| `bug` | Something isn't working. | Triage | Triage |
| `enhancement` | New feature or request. | Triage | Triage |
| `documentation` | Improvements or additions to documentation. | Triage | Triage |
| `refactor` | Code-quality uplift with no intended behaviour change. | Triage | Triage |
| `accessibility` | A barrier affecting people with disabilities. No Issue has carried it yet. | Triage | Triage |

An Issue carries a category when one fits. An Issue defined by its topic,
such as a harness measurement, may carry none. Consumers: the dashboard's
`LABELS` column and label search, and anyone choosing a kind of work.

### Topic: which area of work

| Label | Meaning | Applied by | Cleared by |
| --- | --- | --- | --- |
| `harness-server` | The shared conversation and runtime client-server model across agent harnesses. | Triage | Triage |
| `logging` | The Event Log of Runtime Events: Dashpot observing itself. | Triage | Triage |
| `harness/claude-code` | Specific to Claude Code's behaviour or integration. | Triage | Triage |
| `harness/codex` | Specific to Codex's behaviour or integration. | Triage | Triage |
| `harness/opencode` | Specific to OpenCode's behaviour or integration. | Triage | Triage |
| `tasks.md` | Tracked through `TASKS.md`. Historical: it marks the first Issues (#1, #6, #7, #8, #10, #11), all closed. | The tasks.md tool's GitHub backend, as its marker. Nobody applies it now. | Nobody |

`harness-server` and `logging` each gather one body of work. A `harness/*`
label goes on an Issue only when it concerns a single harness, so a
cross-harness Issue carries none. A `harness/*` label can sit beside
`harness-server`: `harness-server` names the body of work, and the
`harness/*` label names the harness. Consumer: the dashboard's label search,
used by a person or an agent picking up one body of work, such as one
harness's Issues before a re-pin or a harness acceptance run.

`tasks.md` was the marker label of the upstream tasks.md tool's GitHub
backend, which tracked this Repository's first Issues before
[ADR 0001](adr/0001-own-project-and-issue-model.md) replaced TASKS.md as a
backend. Nothing applies it now, and no one should apply it by hand. Its
consumer is the record: it shows which closed Issues were tracked through
TASKS.md, so it is kept while it marks closed Issues only.

### Closing

| Label | Meaning | Applied by | Cleared by |
| --- | --- | --- | --- |
| `duplicate` | This Issue or Pull Request already exists. Close it as a duplicate, naming the original. | Triage | Triage, if the Issue is reopened |
| `wontfix` | Declined: this will not be worked on. Close it as not planned. | The maintainer, or an agent recording the maintainer's decision | The maintainer |

Consumer: closing an Issue. Each label separates its closed Issues from
completed work. An agent that thinks an Issue should be declined applies
`need/maintainer-input` and does not apply `wontfix` itself.

### Removed labels

GitHub's defaults `invalid`, `question`, `good first issue` and `help wanted`
have no consumer under [principle 5](#the-principles), and no Issue
carries them. They are removed from this Repository and are not to be
recreated.

- `invalid` is covered by `duplicate`, `wontfix`, or closing as not planned.
- `question` is covered by `need/info` and `need/maintainer-input`.
- `good first issue` and `help wanted` have no contributor programme here to
  consume them.

The 2026-09-22 alignment with the IPFS scheme renamed `ready-for-human` to
`need/maintainer-input` and `needs-triage` to `need/triage`. On 2026-09-27
the maintainer removed `status/ready`, its replacement for
`ready-for-agent`, because whether an Issue can be picked up is inferred
from blocked-by relationships and `need/*` labels.
