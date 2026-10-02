---
status: accepted
date: 2026-10-02
---

# Install OpenCode as one managed plugin, and keep it unsupported until acceptance

Codex and Claude Code read hook definitions from a JSON file, and
`dashpot integrate` merges Dashpot's handlers into it. OpenCode has no
command hooks. It loads every JavaScript module in its global configuration
directory's `plugins/`, and finds skills in its own `skills/` and also in
Claude Code's and the shared `.agents` skill directories. The
[OpenCode design](../proposals/opencode-integration-design.md#installation-and-shared-skill-ownership)
left those installation questions open. Each supported harness release is
pinned by an acceptance run
([README](../../README.md#harness-acceptance-runs)). The OpenCode acceptance
run is the second half of [#163](https://github.com/ned2/dashpot/issues/163),
and has not yet passed.

## Decision

**The plugin.** `dashpot integrate opencode` writes one managed plugin,
`plugins/dashpot.js`, to OpenCode's global configuration directory. That
directory is `$XDG_CONFIG_HOME/opencode`, or `~/.config/opencode`. The
plugin is rendered from the asset shipped with Dashpot, bound to the
absolute path of this environment's `dashpot-opencode-hook` helper.

- **Ownership.** The plugin's first line is a marker. A file without the
  marker at that path is the user's own plugin: `integrate` refuses to
  overwrite it, and `--remove` leaves it in place.
- **Repair.** Rerunning `integrate` rewrites a plugin that differs from the
  rendered one, and leaves an identical one untouched.
- **Linked Worktrees.** A helper inside a linked Worktree is refused, as
  for the other harnesses.

**The skill.** OpenCode's integration installs and removes the Issue work
skill in `<config>/opencode/skills/` only. A copy in Claude Code's or the
`.agents` directory belongs to that harness's integration, and is never
touched by OpenCode's. `--status` warns about any such copy that differs
from the one this Dashpot ships, since OpenCode may use either. The fix it
names is that harness's own `integrate`.

**Status.** `dashpot integrate opencode --status` reports:

- whether the plugin is installed, current, and bound to an executable
  helper;
- the `opencode` release on PATH, against the measured 1.18.30;
- a warning when `OPENCODE_PURE` is set, since then OpenCode loads no
  plugin.

**Unsupported until acceptance.** `integrate` and `--status` both state that
OpenCode stays unsupported until the OpenCode acceptance run passes, and the
documentation says the same. The integration observes sessions and accepts
corroborated opt-in. No OpenCode release is accepted for Issue work before
that run.

## Considered options

- **A project-level plugin in `.opencode/plugins/`.** Rejected. It would
  have to be installed in every checkout and every Worktree. The user-level
  installation covers all of them, as for the other harnesses.
- **Register through `opencode.json`'s `plugin` list.** Rejected. That
  would edit a configuration file the user owns, where a dedicated file can
  be owned and removed whole.
- **Install the skill once, to a directory every harness reads.**
  Rejected. Removing one harness's integration would remove a skill another
  harness still uses, and no marker can say which integrations depend on
  it.

## Consequences

- Upgrading Dashpot requires rerunning `dashpot integrate opencode`.
  `--status` reports a stale plugin as an available update.
- An OpenCode started with `--pure`, or with `OPENCODE_PURE`, publishes
  nothing, and its commands cannot opt in.
- The second half of #163 measures the local TUI and accepts a release.
  Until then, no document claims OpenCode support.
