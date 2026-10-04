---
status: accepted
date: 2026-10-05
---

# Name a background command by its process, and show it on a waiting Claude Code session

A harness can leave a command running after the turn that started it ends:
a Claude Code `run_in_background` Bash command, a Codex background terminal
that `exec_command` yields, or an OpenCode shell command run with
`background: true`. Call it a Background Command.
[ADR 0104](0104-block-worktree-removal-while-a-process-runs-inside-it.md)
made Cleanup refuse a Worktree while any process the person can see works
inside it. That answered [#466](https://github.com/ned2/dashpot/issues/466)'s
Cleanup question for a Background Command while it runs, whatever its
session's state. Two questions were left open:

1. Does a Background Command whose owning session was deleted or ended need a
   blocker that names that session, beyond the generic `process` one?
2. Should observation show a waiting session that has a running Background
   Command differently?

The [background commands and Cleanup experiment](../spikes/background-commands-and-cleanup-spike.md)
measured Claude Code 2.1.289, Codex 0.160.0 and OpenCode 2.0.22 against the
`process` blocker. In every case where the command outlived its turn, its
session's move, a `/clear`, or its session's end or deletion, the blocker
named it in the Worktree it works in, by pid and command. In every case
where the harness ended the command, the Worktree became removable. Claude
Code's `/exit` with "Exit and stop tasks", a Codex terminal's `/exit`, the
Codex daemon unloading the thread, `claude -p` and `codex exec` each ended
it.

The command's own record of its owner does not hold up. Its environment
names the session that started it, and that session can be gone while the
command runs. After a Claude Code `/clear`, the command names the ended
session while its Host Process serves the next one. After "Move to
background and exit", it names the ended session while a forked session in
another Host Process takes its notice. The command's ancestry breaks too:
that exit reparents the command's shell to pid 1. OpenCode's
`GET /api/shell` still names a deleted session as the owner. A command's end
wakes its session in Claude Code and OpenCode, but in Codex it starts no
turn.

## Decision

**No session-named blocker.** A Background Command is named in Cleanup only
by the `process` blocker, by pid, command and working directory, whatever
became of the session that started it. ADR 0104 is unchanged.

- A deleted or ended session offers no step a person could take. Cleanup
  names a session so the person can move or end it. Here only the command
  is left, and the blocker already says how to deal with it: end it, or
  wait for it. `ps -ww -o pid=,args= -p <pids>` shows its full command line.
- No harness-neutral evidence names the owner.
  - The command's environment is stale after a Conversation Switch and
    after a Claude Code exit to the background.
  - Its ancestry breaks when the shell is reparented.
  - OpenCode's `GET /api/shell` names a deleted session, covers one
    harness, and is a query that ADR 0104 rejected.
  - Remembering which session started which pid would break ADR 0104's
    "computed on demand, nothing retained".
- When the session that runs the command is live in the same Worktree, its
  `agent-session` blocker already names it. That covers a Claude Code
  session after `/clear`, the fork after "Move to background and exit", and
  both Codex threads after `/clear`. When the session has moved away, as
  with Claude Code's `EnterWorktree` or an OpenCode move, the Worktree it
  left holds only the `process` blocker, and the person reads the command
  from the `ps` line.

**Show a running Background Command on a waiting Claude Code session.** A
waiting Claude Code session whose latest `Stop` reported a running
Background Command reads as waiting on that command, not as waiting on the
person. That `Stop` lists the command in its `background_tasks`, with
`type: "shell"` and `status: "running"`. The command's end wakes the
session by itself with a task notification, so a person who reads plain
"waiting" may answer a session that is about to carry on. The evidence is a
field of a hook Dashpot already receives, so showing it keeps observation
passive. The flag clears at the session's next `Stop`. When that `Stop`
follows the command's end, it reports no running command.

The implementation is deferred. It touches the hook record (#460's
`hook_records.py`) and the Sessions pane, whose Lead and Worker design #479
is settling. A follow-up Issue, blocked by #479, carries it. This decision
fixes what is shown and on which evidence. The follow-up chooses the form:
a state, a mark, or a column note, and whether `work show` carries it.

Codex and OpenCode sessions read as they do now:

- **Codex.** No hook reports a background terminal. Its end starts no turn,
  so a waiting Codex session really is waiting for the person.
- **OpenCode.** A command's end does wake the session. But the plugin's
  stored events carry no shell, and the service hosts many sessions, so only
  `GET /api/shell` could attribute the command. That query is the one ADR
  0104 rejected. By the 2.0.22 source, a shell publishes
  `Shell.Event.Created`, which is no session event and was not measured. A
  measurement of it can reopen this.

## Considered options

- **Name the session from the command's environment**
  (`CLAUDE_CODE_SESSION_ID`, `CODEX_THREAD_ID`, `OPENCODE_SESSION_ID`).
  Rejected. The measurements show the variable naming an ended session
  after a `/clear` and after an exit to the background. On macOS, `lsof`
  does not read environments at all.
- **Name the session through the command's Host Process ancestry and the
  hook records' Host Process.** Rejected. One Host Process can serve several
  sessions: a Codex terminal after `/clear`, or the OpenCode service. An exit
  to the background reparents the command away from every Host Process.
- **Query OpenCode's `GET /api/shell`.** Rejected again, for the reasons
  ADR 0104 gives. It also names a deleted session as the owner.
- **Leave a waiting Claude Code session's display unchanged.** Rejected. The
  evidence is in a hook Dashpot already receives, and "waiting" there
  misleads a person or Lead deciding whether to answer.
- **Show the command on every harness's waiting session.** Rejected for
  now. Codex reports nothing, and its "waiting" is accurate. OpenCode
  reports nothing Dashpot stores.

## Consequences

- Cleanup, `dashpot worktree check` and their JSON are unchanged. The
  measured cases are recorded as evidence for ADR 0104's `process` blocker.
- [Agent sessions](../agent-sessions.md#background-commands) describes
  each harness's Background Commands and what Cleanup names. It corrects the
  OpenCode passage that predates ADR 0104, which said Cleanup does not see
  the command.
- The follow-up keeps the latest `Stop`'s running shells on the session's
  hook record and shows them on a waiting session. A Claude Code `/clear`
  makes a new session whose first record is a `SessionStart`. That session
  carries no running command until its first `Stop`, even though the command
  will wake it. The follow-up says whether to carry the flag across a
  Conversation Switch, as ADR 0101 carries Sub-agents.
- A Claude Code session that moves leaves its Background Command behind. The
  Worktree it left reads as held by a process alone, so a person sees the
  command there only through Cleanup. The bundled skill asks only an
  OpenCode session to wait for its Background Commands before it moves.
  Whether a Claude Code session's `EnterWorktree` should wait too is left
  to the skill.
