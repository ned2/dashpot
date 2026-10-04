---
status: research
date: 2026-10-05
---

# Conversation switch through the resume picker experiment

The experiment for [Issue #458](https://github.com/ned2/dashpot/issues/458)
measures the one Claude Code Conversation Switch
[#448](https://github.com/ned2/dashpot/issues/448) left unmeasured that can be
driven safely: `/resume` through the interactive picker, with no session id,
while a background Sub-agent works. It also records what Claude Code 2.1.289
means by `/fork`. [#448's experiment](session-start-on-a-live-session-spike.md#claude-code-21289)
measured `/clear`, `/resume <id>` and `/branch`.
[ADR 0101](../adr/0101-move-a-conversation-switchs-sub-agents-to-the-session-that-runs-them.md)
records the decision these measurements support.

The run used the same fixture as #448's:

- a disposable directory outside every Dashpot Project;
- a loopback Messages API fixture;
- an isolated `CLAUDE_CONFIG_DIR`, with `DISABLE_AUTOUPDATER=1`;
- the pinned binary, run read-only through a fixture-local `PATH` symlink;
- the runner launched with `setsid -f` outside every harness process, as the
  [agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires.

Every hook went to Dashpot's real publisher, run from the #458 working tree
with ADR 0101's rule, and the run recorded the hook records Dashpot stored
after every write. The trace is metadata only, with paths rewritten to
placeholders. [`verify.mjs`](../../scripts/experiments/claude-458/verify.mjs)
checks the claims below against it.

## Claude Code 2.1.289

Runner [`claude-458`](../../scripts/experiments/claude-458/), trace
[`issue-458-claude-trace.jsonl`](measurements/issue-458-claude-trace.jsonl)
(77 records, SHA-256
`81fd2904006cda9a9f16734fd1d053088dc76729af678b24caec388a52d80c36`). The
publisher ran the working tree over `d621fea`, with
`sessions/hook_records.py` at SHA-256 `3a204b72…e9ba`,
`sessions/hook_publish.py` at `a4e3721a…a1cd` and `sessions/hook_scan.py` at
`74079521…5af6`. Receipt numbers below are the trace's.

- **`resume-picker`, `/resume` through the picker (measured).**
  - **Setup.** A prior interactive session ran one turn and exited
    (#5–#15). The picker lists no `claude -p` session, which a probe run
    found, so the prior session is an interactive one. A second interactive
    lead started a background worker whose shell held on a gate (#21–#30).
  - **The picker.** `/resume` opened "Resume session", listing the prior
    session by its first prompt (#32). Typing the prior session's label
    searched the list, and Enter chose it (#33, #34).
  - **The switch.** The lead published `SessionEnd` with `reason` `resume`
    (#35), then `SessionStart` with `source` `resume` naming the prior
    session, from the same Host Process (#36). This is the same order
    `/resume <id>` published under #448.
  - **The worker.** It was still holding after the switch (#38). Once the
    gate opened, its next shell and model requests carried the prior
    session's id (#43), and its `SubagentStop` named that session (#47).
    Its completion reached the lead as a task notification in that session
    (#49).
  - **Dashpot's store (ADR 0101).** The `SessionEnd` kept the worker in an
    ended record with `reason` `resume` (#35). The `SessionStart` took it
    over: the prior session's record listed it and read `running`, and the
    ended record was gone (#36). After the worker's `SubagentStop` no record
    listed it (#47), and the notification turn's `Stop` read `waiting`
    (#51).
- **`fork-menu`, `/fork` described and not run.** In this release the
  command menu describes `/fork` as "Copy this conversation into a new
  background session and keep working here" (#70). Typing it without Enter
  published no hook. The runner cleared the line instead of running it,
  because a background session is hosted by the shared background daemon,
  whose state under `/tmp/cc-daemon-<uid>/` the user's own sessions share.

Not measured: `/fork` itself, which per its description leaves the current
session going on and runs the copy in another Host Process.

## Reproduce

From a checkout of the Worktree, outside every harness process. The run used
a private `TMPDIR` for the fixture root:

```sh
TMPDIR=<private dir> setsid -f node scripts/experiments/claude-458/run.mjs ~/.local/share/claude/versions/2.1.289 > claude-458.log 2>&1
node scripts/experiments/claude-458/verify.mjs docs/spikes/measurements/issue-458-claude-trace.jsonl --strict
```

The runner prints its fixture root, and its `trace.jsonl` is the trace.
`--strict` also fails once a Dashpot source the run hashed has changed since.
`SPIKE_PROBE=1` records the picker's screens and stops before choosing a
session.
