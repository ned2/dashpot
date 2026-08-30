@AGENTS.md

# Claude Code notes

The shared agent guidance is imported above from [AGENTS.md](AGENTS.md). Do not use Claude
Code memories or any other agent-private note store: never create or update files under a
`.claude/.../memory/` directory or a `MEMORY.md`. Follow the shared tracking policy in
[AGENTS.md](AGENTS.md) instead.

## Dashpot observes this session

The Dashpot hook publisher is installed user-wide for Claude Code (check with
`uv run dashpot integrate claude-code --status`), so a session in this checkout is observed
as live automatically. Observation is not Issue opt-in: the `dashpot work start` / `stop`
lifecycle in [AGENTS.md](AGENTS.md#issue-work-lifecycle) still applies.

## Sub-agents share the session's Agent Run

Verified against a real session: a Claude Code sub-agent's shell is a child of the same
`claude` process as the main session, so `identify_agent_session` resolves to the same
session key and `dashpot work show` from the sub-agent reports the main session's run. A
sub-agent therefore needs no opt-in of its own — and must leave `work start` / `stop` alone,
since running them from a sub-agent would switch or end the whole session's Issue work. The
`start` / `stop` calls belong to the main session only. With the hooks installed, a
sub-agent's `work start` in a worktree other than the main session's is refused as running
where the session is not ([ADR 0009](docs/adr/0009-hold-one-agent-run-per-session-across-worktrees.md));
`stop` is not, so the rule still matters.
