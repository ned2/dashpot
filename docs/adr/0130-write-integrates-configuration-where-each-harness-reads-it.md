---
status: accepted
date: 2026-10-05
---

# Write integrate's configuration where each harness reads it, and finish `--remove` past a failed step

`dashpot integrate` writes into the user's own harness configuration: the
hooks file, `settings.json` for Claude Code and `hooks.json` for Codex,
beside a managed copy of each bundled skill. The holistic review of
2026-10-05 found five ways that went wrong
([#541](https://github.com/ned2/dashpot/issues/541)):

- **A linked hooks file was cut.** A dotfiles manager (stow, chezmoi,
  home-manager) leaves the hooks file as a symbolic link. `integrate`
  renamed a temporary over the link itself, so the link became a private
  0600 copy. The user's managed file never received the hooks, a later
  home-manager switch failed on a file in its way, and any text outside
  ASCII came back as `\uXXXX` escapes.
- **The configuration directory was always the home directory's.** Claude
  Code reads `$CLAUDE_CONFIG_DIR` and Codex `$CODEX_HOME` in place of
  `~/.claude` and `~/.codex`. `integrate` read neither, so with either set
  it wrote a file the harness never reads, and `--status` approved it.
- **A skill update wrote through a link inside a managed copy.** A user who
  linked a copy's `references/` elsewhere had the files there overwritten,
  while removal, which never follows such a link
  ([ADR 0103](0103-record-the-files-of-a-managed-skill-copy-in-a-manifest.md)),
  then left them stranded.
- **`--remove` ended in a traceback.** A directory it could not change
  stopped it part-way with a `PermissionError`, after removing some of the
  integration and reporting none of it.
  [ADR 0110](0110-check-every-integrate-destination-before-writing-and-carry-on-past-a-failed-write.md)
  had left `--remove` unchanged.
- **A hooks file that is not UTF-8 crashed** install, `--status`, `--remove`
  and every command across harnesses, where malformed JSON was refused.

## Decision

**Each harness's configuration directory, as the harness resolves it.**
One function resolves it: Claude Code's is `$CLAUDE_CONFIG_DIR`, else
`~/.claude`; Codex's is `$CODEX_HOME`, else `~/.codex`; OpenCode's stays
`$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode`. A variable set but
empty is read as unset. Claude Code reads its user skills inside its
configuration directory, so its skill copies follow `$CLAUDE_CONFIG_DIR`
too. Codex reads user skills from `~/.agents/skills` wherever `$CODEX_HOME`
points, so its copies stay there. When a harness's own variable chose the
directory, `--status` opens that harness's report with
`<harness> configuration directory: <path> (from <variable>)`, and the
refusal for a missing directory names the variable too.
`$XDG_CONFIG_HOME` is not named: it is the base of every application that
follows the XDG layout, not OpenCode's own choice, and `--status` already
names the directory under it. The check of the skill copies OpenCode also
discovers reads them where OpenCode does, `~/.claude/skills` and
`~/.agents/skills`, whatever `$CLAUDE_CONFIG_DIR` names; a differing copy
there that the owning harness's integration does not write is reported
with "move it" rather than a rerun that would not touch it.

**The user's hooks file is written where its link leads.** When the hooks
file is a symbolic link, `integrate` and `--remove` replace the file it
names, through every link, and the link stays. The check before writing
([ADR 0110](0110-check-every-integrate-destination-before-writing-and-carry-on-past-a-failed-write.md))
is of that file's directory, not the link's, and a refusal names both
("the Claude Code lifecycle hooks in …/settings.json, a link to …"), so a
link into a read-only directory, as home-manager's into the Nix store, is
refused before anything is written. A replaced hooks file keeps its mode,
and its JSON is written with text outside ASCII as itself. `--remove`
never unlinks a linked hooks file, even one left holding no hooks: it
rewrites the file the link names without Dashpot's hooks. Dashpot's own
files, the skill copies, the plugin and the agent, are unchanged by this:
a link at one of their paths is replaced, since the path is Dashpot's.

**A managed skill copy is never written through a link inside it.** Before
writing a copy, `integrate` refuses it when the directory of any file it
ships resolves outside the copy ("… resolves outside the copy through a
link; move it and retry"), so writing and removal agree on where a copy
ends. The refusal is one of the checks: it refuses the whole installation
of that harness, and nothing is written.

**`--remove` carries on past a failed step and names it.** Removal runs
its steps in order, the hooks or the plugin, then each skill copy, then
each agent. A step that fails, because a file cannot be read, rewritten or
unlinked, does not stop the others. When any failed, the command prints
what the others removed, then ends with one error naming every failure,
followed by "the rest of the integration is removed, and rerunning
'dashpot integrate <harness> --remove' once that is fixed finishes it",
and exits 2. The error is an `IncompleteRemovalError`, a subclass of
`IncompleteIntegrationError` that carries the printed lines, and the Event
Log records the command as refused with that error type, as ADR 0110 does
for an incomplete installation. An unreadable hooks file is now such a
step: it used to refuse the whole removal, and now the skill copies and
agents are removed regardless. A destination `--remove` cannot inspect, or
one that is not Dashpot's, is still reported and left in place, as ADR 0103
decided: it is not Dashpot's to remove, so leaving it is not a failure.

**A hooks file that is not UTF-8 cannot be read**, and is refused as
malformed JSON is, by `integrate`, `--status`, `--remove` and each harness
of a command across harnesses
([ADR 0111](0111-integrate-several-harnesses-and-every-integrated-one-in-one-command.md)).

## Considered options

- **Refuse a linked hooks file, naming the file to edit.** Rejected. Every
  dotfiles user would add the hooks by hand, and repeat it whenever a
  release subscribes a new event. Writing through the link puts the change
  where the manager sees it; the case that cannot be written, a read-only
  target, is still refused.
- **A `--config-dir` option on `integrate`.** Rejected. The harness reads
  its own variable, so the variable is what decides where it looks; an
  option could disagree with it and approve a file the harness never
  reads, the very fault fixed here.
- **Change the shared atomic write in `core/record_store.py` to keep a
  file's mode.** Not needed. The hooks file is the only file Dashpot
  replaces that is the user's; Dashpot's own records and copies keep the
  private mode they are created with.
- **Check every removal before removing anything, as `integrate` does.**
  Rejected. Every removal step is idempotent and its rerun finishes it, and
  a removal half done is already partial and reported so
  ([ADR 0111](0111-integrate-several-harnesses-and-every-integrated-one-in-one-command.md));
  naming each failure is what the user lacked.
- **Count a destination `--remove` cannot inspect as a failure.** Rejected.
  ADR 0103 leaves such a destination in place because Dashpot cannot tell
  it is its own; failing the command would ask the user to fix what
  Dashpot may have no claim to.

## Consequences

- A dotfiles-managed hooks file stays managed: the link survives
  `integrate` and `--remove`, the managed file carries the hooks, and its
  mode and non-ASCII text are unchanged.
- With `CLAUDE_CONFIG_DIR` or `CODEX_HOME` set, `integrate` must run with
  the same value the harness runs with; `--status` names the variable, so a
  shell without it is visible as the default directory.
- A Claude Code skill copy moves with `$CLAUDE_CONFIG_DIR`; one already
  installed in `~/.claude/skills` while the variable pointed elsewhere is
  left there, and OpenCode's `--status` reports it if it differs.
- `--remove` exits 2 when a step failed, where it used to end in a
  traceback or, for a skill copy it could not change, exit 0 with a
  message.
- ADR 0110's check of the hooks file's directory becomes the directory of
  the file a link names, and its list of a skill copy's checks gains the
  link rule; its "`--remove` and `--status` are unchanged" no longer holds
  for `--remove`. ADR 0103's rule that nothing outside a copy is removed
  now holds for writing too.
