---
status: accepted
date: 2026-10-05
---

# Block Worktree removal while a process runs inside it

Cleanup refuses to remove a Worktree occupied by an Agent Session, an Agent
Run, or a Work Store it cannot read
([ADR 0019](0019-remove-branches-and-worktrees-on-explicit-confirmation.md)),
and, while any session in the Repository lists a live sub-agent, every
Worktree of the Repository
([ADR 0066](0066-block-worktree-removal-while-a-sub-agent-is-working.md)).
Each of these blockers comes from what hooks report. None of them sees a
process that is actually running in the Worktree: a sub-agent's command,
which no hook places; a background command that outlived its session
([#466](https://github.com/ned2/dashpot/issues/466)); a person's shell, a
dev server, or an editor's terminal. A clean Worktree with such a process in
it was removable, and its process lost the directory it worked in.

The process table answers that directly. A process whose working directory
is inside the Worktree is positive evidence that something is there, and
it does not depend on any harness
([#476](https://github.com/ned2/dashpot/issues/476), Part 1).

## Decision

Removing a Worktree is refused while any process the person can see has its
working directory inside it.

- **One `process` blocker per Worktree.** It names each process, up to five,
  by pid, command, and working directory, and counts the rest. It gives
  `ps -ww -o pid=,args= -p <pids>` as the command that shows them, and says
  to end them or move them out of the Worktree. Because there is a single
  blocker whatever the count, a process starting or ending beside another
  does not change the preview's fingerprint.
- **Computed on demand, nothing retained.** The check runs each time a
  linked Worktree is assessed: in the Cleanup preview, in
  `dashpot worktree check`, and in the re-inspection when a Cleanup is
  confirmed, which already refuses a preview that changed. It only reads the
  host's process table and records nothing, so observation stays passive
  ([ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)).
  The main Worktree is not checked. It is never removable, and its tree can
  hold linked Worktrees whose processes are not its own.
- **Positive only.** Finding no process clears no other blocker. An idle
  sub-agent between commands has no process in the Worktree, so the
  `sub-agent` blocker stands as ADR 0066 decides.
- **Working directories, not open files.** A process counts when its
  working directory is the Worktree or a directory below it. Open files do
  not count. Listing every open file of every process is far costlier,
  especially through `lsof` on macOS, and it mostly finds indexers and
  watchers rather than occupants. An edit an editor has not saved is not
  guarded by this check. What guards it is the dirty-Worktree refusal and the
  unforced `git worktree remove`.
- **Only the processes the person can read.** On Linux, Dashpot reads each
  process's `/proc/<pid>/cwd` link and its parent from `/proc/<pid>/stat`.
  Linux refuses that link for another user's process, and for one that made
  itself undumpable, such as `ssh-agent`. Such a process is skipped, as is
  one that exits during the scan or whose working directory was removed. It
  gives no evidence either way. Counting it would block every Cleanup on a
  host where one runs, which is every host. Run as root, Dashpot reads every
  process.
- **macOS, through `lsof`.** A host without `/proc` is asked with
  `lsof -w -d cwd -F pRcfn`, which lists each readable process's working
  directory and parent and leaves out the processes it may not read. `lsof`
  ships with macOS, which keeps a native `libproc` binding out of Dashpot.
- **A scan that falls short says so.** Sometimes the scan cannot cover
  every process the person can see. The host may have no `/proc` and no
  `lsof` that runs, `lsof` may fail or time out, `/proc` may be unreadable,
  or Dashpot may run inside a sandbox's PID namespace, where the host's
  processes are hidden. The Worktree is then not called free without a
  qualification. The preview and the `worktree check` report carry a
  sentence saying which processes were not all checked and why, as
  `uncheckedProcesses` in their JSON. The dashboard and the text reports
  state it beneath a removable Worktree, beside the sub-agent scope ADR 0066
  states, and a blocked Worktree claims nothing to qualify. A performed
  `worktree remove` states it beneath the removed Worktree's result. Whether
  the scan was complete is part of the preview's fingerprint, so a change
  in it at confirmation, either way, refuses the removal as changed: a scan
  that falls short only at confirmation is refused, and the revised preview
  states the gap. It is a
  statement, not a blocker, because the check is a positive safety net: an
  unsupported host gets the Cleanup it had before this decision, and is
  told so. A sandboxed scan still blocks on every process it does see.
- **The inspecting Dashpot process is no occupant; its ancestors are.**
  The Dashpot process asking, and every process it started, are left out.
  These are its own Git and `ps` probes, and a dashboard's observation may
  run Git inside the Worktree at the moment the Cleanup inspects it. A
  launched terminal is not among them, since the Worktree launcher requires
  its wrappers to detach. The shell that runs `dashpot worktree remove`
  from inside the Worktree is an ancestor and is counted: removal would
  take its working directory away. A person or agent runs the removal from
  outside the Worktree.

`processes_inside(path, scan)` in `src/dashpot/sessions/working_directories.py`
is the one query: every visible process inside a path, without the
inspecting process and its descendants, together with the scan's gap if it
had one. The scan is injectable, so tests drive it with a fake table.

## Considered options

- **Count open files too:** rejected for cost and noise, as above. A
  process with a file open in the Worktree and its working directory
  elsewhere is the narrow case left uncovered.
- **Block when the scan falls short:** rejected. It would refuse every
  Cleanup on a host without a reader, and every Cleanup run from inside a
  sandbox, to guard against a gap that existed before this check. A stated
  gap keeps the decision with the person.
- **Count unreadable processes as possible occupants:** rejected. Every
  host runs processes of other users and undumpable ones, so the block
  would never lift.
- **Exclude the invoking shell and the harness above it:** rejected. A
  shell sitting in the Worktree is exactly the occupant this check exists
  to find, whoever started Dashpot from it.
- **Query OpenCode's `GET /api/shell` for its background commands:**
  rejected here. It covers one harness, and it is an HTTP query observation
  does not make. The process table covers every harness's commands while
  they run.

## Consequences

- A `process` blocker joins the occupancy blockers in
  `dashpot worktree check`, the Cleanup preview, `dashpot worktree remove`,
  and the re-inspection on confirmation. A process that appears between
  preview and confirmation changes the preview, so the confirmed removal
  performs nothing.
- Part 2 of #476, a person's override of `sub-agent` blockers scoped to the
  preview, will call `processes_inside` again before each destructive step.
  It refuses when any process is inside the target, so the override can
  never remove a Worktree a sub-agent's command is running in.
- #466's Cleanup question is answered for a background command while it
  runs, whatever its session's state. A command whose session was deleted
  is named by its pid and command, not by that session.
- A short-lived command that starts and ends between two inspections is not
  seen. This is the same race that ADR 0066 bounds with the dirty check and
  unforced removal.
- A dashboard observing the Repository from another process can run a Git
  probe inside the Worktree just as a Cleanup inspects it. That probe is
  briefly an occupant, and the preview or confirmation is refused until the
  next inspection.
