---
status: living
date: 2026-09-30
---

# Issue tracker: GitHub

Dashpot's Issue Source is GitHub Issues on `ned2/dashpot`, read and written
with the `gh` CLI from inside a checkout. This file answers the Issue Source
questions that skills such as `code-review` look up at this path. The rest of
working on an Issue lives elsewhere: the Issue work lifecycle and independent
review in [AGENTS.md](../../AGENTS.md), the integration sequence in the
README's [Contributing](../../README.md#contributing) section.

## Fetch an Issue

```bash
gh issue view <number> --json number,title,state,body,labels,comments
```

This returns the body and the comments together; the comments often correct
the body, so read both. `gh issue view <number> --comments` on its own prints
only the comments when no terminal is attached, so a review would miss the
Issue's text. A bare `#N` can also name a Pull Request, which the same command
resolves; `gh pr view <number>` gives the Pull Request's own fields.

## Create an Issue

Run `gh issue create --label need/triage` so the new Issue enters triage.
