---
status: research
date: 2026-10-05
---

# Idle SessionStart and /fork experiment

The experiment for [Issue #488](https://github.com/ned2/dashpot/issues/488)
measures what Claude Code publishes after a `SessionStart` that nobody follows
with a prompt. It covers a session that is opened, resumed at launch, started
headless, or `/clear`ed with no worker. The same fixture measures `/fork` with
a working background Sub-agent for
[#490](https://github.com/ned2/dashpot/issues/490). The
[conversation-switch experiment](conversation-switch-picker-spike.md) only
described `/fork` from the command menu.
[ADR 0106](../adr/0106-record-a-session-waiting-after-a-session-start-that-begins-no-turn.md)
records the decision these measurements support.

The run used the same fixture as #448's and #458's:

- a disposable directory outside every Dashpot Project;
- a loopback Messages API fixture;
- an isolated `CLAUDE_CONFIG_DIR`, with `DISABLE_AUTOUPDATER=1`;
- the pinned binary, run read-only through a fixture-local `PATH` symlink;
- the runner launched with `setsid -f` outside every harness process, as the
  [agent guidance](../../AGENTS.md#leading-parallel-issue-work) requires.

`/fork` starts its copy under a background daemon. With the isolated
configuration, the fixture got a daemon of its own: a new entry under
`/tmp/cc-daemon-<uid>/` beside the user's. The runner stopped it with
`claude daemon stop --any` in the fixture's environment, and the entry was
gone afterwards. The trace records only which entries appeared and went, and
that the entry already there before the run stayed.

Every hook went to Dashpot's real publisher, run from the #488 working tree
with ADR 0106's rule, and the run recorded the hook records Dashpot stored
after every write. The trace is metadata only, with paths rewritten to
placeholders. [`verify.mjs`](../../scripts/experiments/claude-488/verify.mjs)
checks the claims below against it, 17 checks in all.

## Claude Code 2.1.289

Runner [`claude-488`](../../scripts/experiments/claude-488/), trace
[`issue-488-claude-trace.jsonl`](measurements/issue-488-claude-trace.jsonl)
(144 records, SHA-256
`eb8158c09445786341a796b77b8cc049a1ad9abf8c920585e45322c1cc3bcefd`). The
publisher ran the working tree over `8598b2d`, with #488's
`sessions/hook_records.py` at SHA-256 `0c232451…91ff`. Receipt numbers below are the
trace's. Each idle wait lasted 20 s, with nothing typed or sent.

- **`idle-startup`, an interactive session opened with no prompt.**
  `SessionStart` `startup` (#5), then no hook at all while idle (#7, #8).
  Dashpot stored the session `waiting` with no turn clock. Its first prompt
  recorded `running`, with the turn clock starting at the prompt (#11), and
  the turn's `Stop` recorded `waiting` (#16).
- **`idle-resume`, `claude --resume <id>` of that session.** `SessionStart`
  `resume` for the same session id, from a new Host Process (#25), then no
  hook while idle (#27, #28). Stored `waiting`.
- **`idle-headless`, a stream-json `claude -p` sent no input.** `SessionStart`
  `startup` arrived during the idle wait, before any user message was sent
  (#40). Nothing else arrived until the first user message, which published
  `UserPromptSubmit` (#44). Stored `waiting`, then `running`.
- **`clear-idle`, `/clear` with no worker.** `SessionEnd` `clear` (#70),
  which removed the session's record, then `SessionStart` `clear` for a new
  session id from the same Host Process (#71), then no hook while idle (#73,
  #74). The new session was stored `waiting` with no turn clock.
- **`fork-worker`, `/fork` while a background worker works.**
  - **Setup.** An interactive lead started a background worker whose shell
    held on a gate (#86–#93). Its record read `running`, listing the worker,
    with no turn clock (#92). The command menu describes `/fork` as "Copy
    this conversation into a new background session and keep working here"
    (#95).
  - **The fork.** `/fork` and Enter (#96) published no `SessionEnd` for the
    lead. They published one `SessionStart` with `source` `fork` and a new
    session id (#98). It came from another Host Process: a background
    session under a transient daemon that the lead's process had started,
    with a new entry under `/tmp/cc-daemon-<uid>/` (#101). `claude agents`
    listed the lead as interactive and the fork as background, each with its
    own pid (#103).
  - **The fork begins no turn.** No hook came while the fork was left idle
    (#104–#106). The fork published nothing more until the daemon stopped,
    and then ended with `reason` `other` (#132, #133).
  - **The worker.** It was still holding after the fork (#108). Once the
    gate opened, its shells carried the lead's session id and Host Process,
    and its model requests the lead's id (#111–#115). Its `SubagentStop`
    named the lead's session and Host Process (#117), and its completion
    reached the lead as a task notification (#119).
  - **Dashpot's store.** The fork's `SessionStart` was stored `waiting`
    with no sub-agents. The lead's record still read `running` with the
    worker listed, because the fork took nothing over (#98). After the
    worker's `SubagentStop`, no record listed it and the lead read `waiting`
    (#117).
  - **Cleanup.** `claude daemon stop --any` stopped the fixture's daemon and
    removed its entry (#135). No fixture process outlived the run (#143).

`/fork` therefore leaves the forking session and its worker where they are.
Its copy is a separate session of another Host Process that begins no turn
until someone attaches to it and prompts it.

Not measured: attaching to the fork and prompting it, `/fork` with no
worker, and a Codex session that starts and is never prompted. Codex and
OpenCode were not run again. ADR 0106 cites the orders their #448 traces
already show.

## Reproduce

From a checkout of the Worktree, outside every harness process. The run used
a private `TMPDIR` for the fixture root:

```sh
TMPDIR=<private dir> setsid -f node scripts/experiments/claude-488/run.mjs ~/.local/share/claude/versions/2.1.289 > claude-488.log 2>&1
node scripts/experiments/claude-488/verify.mjs docs/spikes/measurements/issue-488-claude-trace.jsonl --strict
```

The runner prints its fixture root, and its `trace.jsonl` is the trace.
`--strict` also fails once a Dashpot source the run hashed has changed since.
`SPIKE_SCENARIOS` runs a subset, and `SPIKE_PROBE=1` records the `/fork`
menu and stops before running it.
