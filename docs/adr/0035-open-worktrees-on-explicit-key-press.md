---
status: accepted
date: 2026-09-12
---

# Open Worktrees on explicit key press

A person already looking at a Worktree should be able to open a terminal there
or copy its full path without reconstructing an abbreviated table cell.

Add Worktrees-only keyboard actions: `Enter` requests Open Worktree; `y` sends
Copy path through Textual's existing terminal clipboard transport. Mouse
selection alone never launches. Capture the selected row's complete observed
path on invocation and keep Issue/Session activation and input handling intact.

Extend machine-local TOML settings from
[ADR 0052](0052-read-machine-local-settings-as-toml.md) with
`worktree_open_command`. A custom argument array takes precedence over tmux;
replace only standalone `{path}` arguments and use the selected Worktree as cwd.
Otherwise, inside tmux, split below the originating pane and focus the new pane.
Escape tmux format expansion and its trailing-semicolon argument parsing.
Outside tmux, show configuration and Copy path guidance.

Load settings at startup. Invalid settings disable launching and produce a
Diagnostic without disabling observation or copying. Keep unknown-field warnings.
Run launch requests off the UI loop, with no interactive stdin and captured
output. Bound waiting for output EOF even after a request parent exits; reap only
the request process on timeout, preserving a terminal child. Wrappers must detach
persistent children and redirect their streams. Do not retry uncertain outcomes.

## Considered options

- Native support for every terminal would multiply configuration and platform
  policy. One literal argument-array contract admits wrappers instead.
- Generic row selection conflates Enter with mouse clicks; a Worktree table
  keyboard binding distinguishes the explicit launch.
- Copy path remains independently useful when launching is unavailable, so it
  has its own key and requires no live filesystem access.

## Consequences

These are explicit external actions alongside Remote Fetch and Cleanup.
Observation remains passive. Opening neither declares Issue work nor creates or
relocates an Agent Session; it does not alter Git metadata. Future session
handoff requires its own verified control mechanism.

A completed command is evidence of a launch request, not a ready shell. tmux or
shell startup may change the requested directory, including tmux's fallback when
it disappears after validation. Clipboard delivery is also terminal-dependent;
Dashpot reports that the path was sent, not that host clipboard state was verified.
See the [launcher and clipboard guide](../installation.md#open-worktrees-and-copy-paths).
