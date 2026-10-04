---
status: accepted
date: 2026-10-05
---

# Check every integrate destination before writing, and carry on past a failed write

`dashpot integrate <harness>` writes several destinations: the hooks file
(Codex, Claude Code) or the managed plugin (OpenCode), one managed copy of
each bundled skill, and, for OpenCode, the bundled agent definition. Before
writing, it already refused a destination that holds what Dashpot does not
manage, or that it could not inspect, so such a refusal left everything as
it was.

[ADR 0103](0103-record-the-files-of-a-managed-skill-copy-in-a-manifest.md)
left one case outside that check: a managed skill copy Dashpot can read but
not change. `integrate` met it only when writing, and stopped there with
"could not update". The hooks or plugin, and every skill before that copy,
were already written; the skills and agents after it were not attempted.
`--status` then reported some copies current and others with an update
available until someone fixed the permissions and reran `integrate`
([#491](https://github.com/ned2/dashpot/issues/491)).

Two remedies were open: check every destination before writing anything,
or carry on past the unwritable copy and report every failure together.
Neither alone keeps an install whole. A check reads permissions, and the
write can still fail after it passes: the destination can change in
between, the write can be refused for a reason permissions do not show (a
full disk, an immutable file, a sticky directory holding another user's
file), or the process can be killed. Carrying on alone writes every other destination
and so guarantees the mixed install for the very case the Issue names.

## Decision

**Check first.** `integrate` works out every destination it would change
before writing any of them, and checks each: a destination already current
is not checked, since nothing is written there. A destination is writable
when every directory in which its write creates, replaces or removes a file
is a directory this process may write and search; a directory not there yet
is created in its nearest existing ancestor, which is checked instead. For a
skill copy those are the copy itself, which holds `SKILL.md` and the
manifest, the directory of each shipped file, and the directory of each
file an earlier Dashpot wrote that this one no longer ships, where that
directory resolves inside the copy. For the hooks file, the plugin and an
agent, it is the directory holding the file; anything but a file at the
hooks path is refused too, as the plugin's and an agent's paths already
were, since it would read as absent and fail only at the write. One that fails the check
refuses the whole installation, with a line per refused destination
("cannot install the Dashpot Issue work skill at …: … is not writable; make
it writable and retry"), all of them in one error, and nothing is written.
The refusals for unmanaged or uninspectable destinations, which come first,
are unchanged. An unwritable managed
copy therefore leaves the hooks, the plugin and every other copy at the
release they were, and `--status` reports the install as it was before the
attempt.

**Then carry on.** When a write fails after every check passed, `integrate`
writes the remaining destinations regardless, then ends with an error
naming every destination that failed ("could not install …", "could not
update …"), followed by "the rest of the integration is written, and
rerunning 'dashpot integrate <harness>' once that is fixed finishes it".
The command prints what it did write first, then the error, and exits 2 as
any refusal does. The error is an `IncompleteIntegrationError`, a subclass
of the refusal `IntegrationError` that also carries those printed lines, as
`GitError` carries its command beside the
[ADR 0046](0046-raise-every-refusal-as-a-dashpoterror-subclass.md) contract.
The Event Log records the command as refused, and its error type,
`IncompleteIntegrationError`, tells an incomplete installation from one that
wrote nothing. A
skill copy cut short is left as ADR 0103 describes: its manifest still
names every file Dashpot wrote, so the rerun or `--remove` finishes it.
This residual case does leave a mixed install, but only the destinations
that failed are behind, each is named, and nothing a check could have
caught gets this far.

**Across harnesses.** The rule applies per harness. When one command
integrates several harnesses, as
[#480](https://github.com/ned2/dashpot/issues/480) proposes, each harness
stands alone: its destinations are checked together before any of them is
written, a harness refused by its check is left as it was, and neither a
refused harness nor one whose writes failed stops the others. The command
reports each harness's outcome and exits non-zero when any harness was
refused or incomplete. A refusal that concerns the command rather than one
harness, such as the publisher living in a linked Worktree, is still made
before any harness changes. Harnesses are separate installs whose `--status`
is reported per harness, so one harness's unwritable directory is no reason
to leave another harness at an older release.

`--remove` and `--status` are unchanged.

## Considered options

- **Carry on past an unwritable copy alone, and report every failure
  together.** Rejected as the first line. It writes the hooks and the other
  copies and so leaves exactly the mixed install the check prevents; it
  remains the answer for a write that fails after the check.
- **Check first, and stop at the first write that still fails.** Rejected.
  It is what ADR 0103 already did once the check passed: the destinations
  after the failure stay behind for no reason of their own, and only the
  first failure is named.
- **Stage every write and commit them together.** Rejected. The
  destinations sit in different directories, some on other filesystems,
  so no single rename can commit them, and a rollback can itself fail
  part-way. The check covers the common cause, and the manifest already
  makes a cut-short copy recoverable.
- **Write the hooks or plugin last.** Rejected. It changes which
  destinations are behind after a failure, not whether some are.

## Consequences

- A managed copy, skill directory, agent directory or configuration
  directory Dashpot cannot write refuses `integrate` before it writes
  anything, where it used to stop part-way.
- The check asks the operating system whether the process may write and
  search each directory, so it cannot foresee a full disk, an immutable
  file or a sticky directory; those fail at the write and are reported
  together.
- A failed write of the hooks file, the plugin or an agent is reported as
  `integrate`'s error, where it used to end in a traceback.
- `--status` reports a mixed install only after a write that failed past the
  check, and the error that ended that `integrate` named each destination
  behind.
- [#480](https://github.com/ned2/dashpot/issues/480) applies the per-harness
  rule above when it integrates several harnesses in one command.
