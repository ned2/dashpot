---
name: dashpot-issue-work
description: Manage declared Dashpot Issue work, including starting, switching, finishing, handing off, recovering, and preparing or reusing Issue Worktrees. Use whenever repository work belongs to an Issue observed by Dashpot.
---

<!-- dashpot-managed-skill: dashpot-issue-work -->

# Work on a Dashpot Issue

This skill is written for Dashpot 0.1.0.

## Establish the workflow

1. Read the repository's agent instructions, contribution workflow, and domain
   language before changing anything. Use the Dashpot invocation they prescribe;
   otherwise use `dashpot`.
2. Run `<dashpot> --version`. If it is not `0.1.0`, stop and ask the user to
   rerun `<dashpot> integrate <harness>` before continuing. Do not guess at a
   newer or older command contract.
3. Run `<dashpot> issue show <reference> --json`. Continue only when exactly one
   fresh Issue resolves from the configured Issue Source and Profile.
4. Run `<dashpot> integrate <harness> --status` from the intended Worktree,
   using `codex` for Codex or `claude-code` for Claude Code, and require its
   `Agent Session identity claimed here` line to be confirmed. If a Worktree
   must be selected, prepared, or entered, read
   [dispatch](references/dispatch.md) and complete that branch first.
5. Run `<dashpot> work show` from that Worktree. When it already reports this
   Agent Session working on the intended Issue, retain that Agent Run. Otherwise
   run `<dashpot> work start <reference>`, then `work show`. Continue only when
   `show` reports the intended Issue at the intended Worktree.
6. Follow the repository's implementation, test, commit, push, review, and CI
   workflow. Keep the Issue Binding active across the entire engagement.

Never infer an Issue Binding from a Branch, Worktree, conversation, or Issue
lookup. Only `work start` declares it; `work relocate` can preserve that
existing binding but cannot create one. Observation commands and dashboards
stay passive; run a management command only for the action the user requested.

## Finish the engagement

Wait until this Agent Session and every agent or process it started are done,
the final push has landed, and required CI is green. Then run `<dashpot> work
stop` and `<dashpot> work show`. Completion means `show` reports no active Issue
work for this Agent Session.

Leave the Issue Worktree in place unless the user explicitly requests cleanup.
Cleanup remains a separate preview-and-confirm workflow.

## Recover a refusal

Read [recovery](references/recovery.md) only when a command is refused, the
session is observed at the wrong location, resume is unavailable, or existing
state prevents the ordinary workflow. Preserve the refusal's safety boundary;
do not repair Dashpot state by hand.
