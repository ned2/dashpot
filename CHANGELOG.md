# Changelog

## 0.1.0 — First release (not yet published)

Dashpot's first alpha release provides a terminal view of declared Issue work,
Git Repository state, Pull Requests, and active coding-agent sessions.

- Observe GitHub Issues or Local Issue Markdown, with complete profiles,
  freshness, and actionable Diagnostics.
- Inspect Worktrees, local and Remote-Tracking Branches, integration state,
  and GitHub Pull Requests. Fetch explicitly; preview and confirm Cleanup.
- Observe Codex and Claude Code through opt-in hooks, and declare Issue work
  through a Project-local Work Store and the bundled Issue-work skill.
- Install as an isolated Python application with `uv tool install dashpot`.
  Hook publishers work when their installation path contains spaces or shell
  metacharacters.

This release establishes the first compatibility baseline. Documented commands,
JSON key sets and semantics, Local Issue Markdown, and `.dashpot/config.json`
remain compatible within 0.1.x. Breaking changes require a new minor version and
release notes. Python internals and exact terminal layout are not extension
interfaces.

The release targets Linux x86-64 and Apple Silicon macOS, CPython 3.11–3.14,
Git 2.38+, and gh 2.100.0+ for GitHub-backed Projects. See
[installation and support](docs/installation.md) for the required host/harness
acceptance and [the release checklist](docs/releasing.md) for publication gates.
