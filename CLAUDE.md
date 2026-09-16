@AGENTS.md

# Claude Code notes

The shared agent guidance is imported above from [AGENTS.md](AGENTS.md); this file holds
only what is specific to the Claude Code harness.

- Claude Code's memory feature is the private note store [AGENTS.md](AGENTS.md#tracking-and-notes)
  forbids: never create or update files under a `.claude/.../memory/` directory or a
  `MEMORY.md`.
- The hook publisher is installed with `dashpot integrate claude-code`; check it with
  `uv run dashpot integrate claude-code --status`.
- A Claude Code sub-agent's shell is a child of the same `claude` process as the main
  session (verified against a real session), so `identify_agent_session` resolves to the
  same session key and `dashpot work show` from the sub-agent reports the main session's
  run. That is the mechanism behind the sub-agent rule in
  [AGENTS.md](AGENTS.md#issue-work-lifecycle).
