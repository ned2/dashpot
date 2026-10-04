---
status: accepted
date: 2026-10-05
---

# Integrate several harnesses, and every integrated one, in one command

`dashpot integrate` took exactly one harness. Refreshing the hooks, skills
and agents after an upgrade took one command per integrated harness, and
the order a person ran them in produced warnings of its own: OpenCode also
discovers Claude Code's and Codex's skill copies, so `dashpot integrate
opencode` run first warned about copies the next two commands were about to
refresh ([#480](https://github.com/ned2/dashpot/issues/480)).

Integration is opt-in: nothing is installed into a harness without
`dashpot integrate` naming it
([ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)).
A command that refreshes "every harness" must keep that, so it needs a
definition of an integrated harness that a person can only reach by having
integrated it.

## Decision

**Several harnesses.** `dashpot integrate` takes any number of harnesses:
`dashpot integrate claude-code codex opencode`. A harness named twice runs
once. One named harness behaves exactly as before, output and refusals
included.

**`--installed`.** `dashpot integrate --installed` refreshes every harness
that is already integrated, and no other. It takes no harness argument.

- **Integrated** means `--status` would find every one of Dashpot's
  lifecycle hooks registered for the harness: every subscription in its
  hooks file for Codex and Claude Code, and the managed plugin, which
  registers all of OpenCode's events at once, for OpenCode.
- **Stale is integrated.** A harness whose hooks are all registered but
  whose skill, agent or plugin is behind, or missing because this release
  adds it, is integrated. Refreshing it is what `--installed` is for, so a
  release that adds a bundled skill installs it everywhere the person opted
  in. Hooks bound to a publisher that has since gone are integrated too,
  and the refresh rebinds them.
- **Partial is not integrated.** Some of Dashpot's hooks without the
  others, or a managed skill copy or agent left with no hook, means the
  person's opt-in is incomplete or half removed. `--installed` cannot tell
  which, so it leaves the harness unchanged and reports it, naming
  `dashpot integrate <harness>` to complete it and `dashpot integrate
  <harness> --remove` to clear it. A partial harness alone does not make
  the exit status non-zero: nothing failed.
- **Not integrated** — no configuration directory, or no Dashpot hook and
  nothing Dashpot manages — gets one line and is never installed into, even
  when the harness is on `PATH`. With no harness integrated, `--installed`
  changes nothing and exits 0.
- A hooks file or plugin `--installed` cannot read to tell refuses that
  harness: integration cannot be decided, and the refusal names the file.

**Order.** The harnesses run in a fixed order, Claude Code, Codex, then
OpenCode, whatever order they are named in. OpenCode's check of the copies
it also discovers then reads copies this same command has refreshed, and
warns only about one that genuinely differs: a harness refused, partial or
not integrated, or a skill directory Dashpot does not manage.

**Each harness stands alone**, as
[ADR 0110](0110-check-every-integrate-destination-before-writing-and-carry-on-past-a-failed-write.md)
decided for a command across harnesses. Each harness's destinations are
checked together before that harness is written; a harness refused by its
checks, or left incomplete by a write that failed after them, does not stop
the others. A harness whose publisher cannot be located is refused alone.

**One refusal concerns the command.** The hooks bind the absolute path of
the invoking environment's publisher, so a publisher in a linked Worktree
refuses the whole command before any harness changes, naming each harness
it would have bound and the arguments to rerun from the main working tree
or an installed tool environment.

**Output and exit status.** Each harness's lines are printed under its
name: `Codex:` and then its messages indented, or one line such as
`OpenCode: refused` or `Codex: not integrated (…)`. A refused or incomplete
harness's error follows on standard error as `dashpot: <harness>: <error>`.
The command exits 2 when any harness was refused or left incomplete, and 0
otherwise. Its `command.outcome` names no target harness, counts the
harnesses refused as its refusal count, and is `refused` when any harness
was refused, `failed` when one was left incomplete and none refused, and
`succeeded` otherwise; its action is `installed` when any harness was
written.

**`--status` across harnesses.** `dashpot integrate --status`, with no
harness or with `--installed`, reports every harness: an integrated one in
full, a partial one in full led by how to complete or clear it, and one
not integrated in one line. Harnesses named with `--status` are each
reported in full. The session record stores, which every harness shares,
are reported once, after the harnesses. When two or more integrated
harnesses have an update available, a last line names the one command that
updates them together: `dashpot integrate --installed`, or the stale
harnesses when they were named. Each skill, agent and plugin line still
names its own harness's `dashpot integrate <harness>`, which is the repair
for that one.

**`--remove` still names one harness.** Removal is the destructive
direction, so it is never offered across harnesses: `--remove` with no
harness, several, or `--installed` is refused.

## Considered options

- **Count any trace of Dashpot as integrated.** Rejected by the maintainer.
  A managed skill left after a hooks file was deleted by hand, or the hooks
  of one event, would be "refreshed" into a full installation the person
  may have been removing.
- **Count only a fully current harness as integrated.** Rejected. A release
  that adds a bundled skill would leave every existing installation
  skipped, the very case the command is for.
- **Make a skipped partial harness fail the command.** Rejected. Nothing was
  attempted and nothing failed, and a refresh run after every upgrade would
  fail until the person resolved a state they may have chosen.
- **Offer `--remove --installed`.** Rejected. Removing every integration at
  once is easy to run by mistake and saves little: there are three
  harnesses.
- **Run the harnesses in the order named.** Rejected. The order changes only
  which warnings appear, and the fixed order makes them appear only for a
  genuine conflict.

## Consequences

- Upgrading Dashpot needs one command, `dashpot integrate --installed`, run
  from the environment the hooks should bind, unless the release subscribes
  a new hook event, below.
- `--installed` never widens an opt-in: it installs a new bundled skill or
  agent only into a harness whose every hook is registered.
- A person finishing or undoing a half-done integration is told which; the
  refresh never decides for them.
- An installation from before a release subscribed a new hook event, as
  Codex's `SubagentStart` and `SubagentStop` were, or Claude Code's
  `PostToolUse(ExitWorktree)`, is partial: `--installed` leaves it as it is
  and names `dashpot integrate <harness>`, which adds the missing hooks. A
  release that subscribes another event leaves every earlier installation
  of that harness for its own `integrate` the same way.
- [ADR 0110](0110-check-every-integrate-destination-before-writing-and-carry-on-past-a-failed-write.md)'s
  single-harness behaviour and its per-harness rule are unchanged, so it is
  not amended; neither is
  [ADR 0079](0079-install-opencode-as-one-managed-plugin-and-keep-it-unsupported-until-acceptance.md),
  whose warning still names the harness that owns a differing copy.
