// Independent verifier for a Claude Code 160 experiment trace.
// Checks the recorded hook, shell, listing and process evidence against the
// identity and lifecycle claims without importing the runner or publisher.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "2.1.276";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const hooks = of("hook");
const commands = of("command").filter((record) => record.phase === "start");
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `${expectedVersion} (Claude Code)`);
const scenarios = of("scenario").map((record) => record.name);
for (const name of ["headless-baseline", "headless-resume", "headless-fork", "headless-subagent", "background-workers", "background-worker-edit", "worker-abrupt-exit", "supervisor-replacement", "worker-stop-respawn", "supervisor-stop", "remote-control-eligibility"]) {
  assert(scenarios.includes(name), `scenario ${name} ran`);
}

// Every hook and every Bash command carries the same session claim and the
// pid of the process that executed it; ancestry corroborates that pid.
for (const hook of hooks) {
  assert.equal(hook.env.CLAUDE_CODE_SESSION_ID, hook.payload.session_id, `hook ${hook.event} claim matches payload`);
  assert(hook.ancestry.some((entry) => entry.pid === Number(hook.env.CLAUDE_PID)), `hook ${hook.event} descends from CLAUDE_PID`);
}
for (const command of commands) {
  assert(command.env.CLAUDE_CODE_SESSION_ID, `command ${command.label} claims a session`);
  assert(command.ancestry.some((entry) => entry.pid === Number(command.env.CLAUDE_PID)), `command ${command.label} descends from CLAUDE_PID`);
}

// Resume keeps the conversation identity across processes; fork does not.
const baseline = of("baseline.output")[0];
const resume = of("resume.output")[0];
const fork = of("fork.output")[0];
assert.equal(resume.sessionId, baseline.sessionId);
assert.notEqual(fork.sessionId, baseline.sessionId);
assert.equal(fork.source, "fork");
assert(!fork.startPayloadKeys.some((key) => /parent|origin|fork/i.test(key) && key !== "source"), "SessionStart names no parent for a fork");
const starts = hooks.filter((record) => record.event === "SessionStart");
assert.deepEqual(starts.filter((record) => record.payload.session_id === baseline.sessionId).map((record) => [record.payload.source, record.env.CLAUDE_PID !== starts[0].env.CLAUDE_PID]), [["startup", false], ["resume", true]]);

// A subagent shares its parent's session and process; hooks add agent_id.
const subagent = of("subagent.identity")[0];
assert.equal(subagent.childSessionId, subagent.sessionId);
assert.equal(subagent.childPid, subagent.parentPid);
assert.equal(subagent.startPayload.agent_id.length > 0, true);
assert.deepEqual(of("subagent.hooks")[0].events.map((event) => event[0]), ["SubagentStart", "PreToolUse", "PostToolUse", "SubagentStop"]);
assert(commands.every((command) => command.env.CLAUDE_CODE_CHILD_SESSION === "1"), "CLAUDE_CODE_CHILD_SESSION is set in every shell, not only a subagent's");
// A headless process ends its session with reason "other" at exit.
for (const output of [baseline, resume, fork]) {
  assert(hooks.some((record) => record.event === "SessionEnd" && record.payload.session_id === output.sessionId && record.payload.reason === "other"), "headless SessionEnd other");
}

// Two workers: distinct sessions and pids, each below the one supervisor.
const workers = of("workers.identity")[0];
assert.notEqual(workers.a.job.sessionId, workers.b.job.sessionId);
assert.notEqual(workers.a.job.pid, workers.b.job.pid);
assert.equal(workers.a.job.id, workers.a.job.sessionId.slice(0, 8));
for (const worker of [workers.a, workers.b]) {
  assert.equal(worker.env.CLAUDE_CODE_SESSION_ID, worker.job.sessionId);
  assert.equal(Number(worker.env.CLAUDE_PID), worker.job.pid);
  assert.equal(worker.commandCwd, worker.job.cwd);
  assert.equal(worker.hookCwd, worker.job.cwd);
  const pids = worker.ancestry.map((entry) => entry.pid);
  assert(pids.indexOf(worker.job.pid) < pids.indexOf(workers.supervisor.pid), "worker sits between command and supervisor");
  assert.equal(worker.ancestry.find((entry) => entry.pid === worker.job.pid).comm, workers.supervisor.comm, "worker and supervisor share the versioned executable name");
}
assert.notEqual(workers.supervisor.comm, "claude");
assert.equal(workers.supervisor.ppid, 1, "the transient supervisor is reparented to init");
assert(workers.supervisor.cmdline.includes("daemon run --origin transient"));
for (const worker of [workers.a, workers.b]) {
  const host = worker.ancestry.find((entry) => entry.pid === worker.ancestry.find((item) => item.pid === worker.job.pid).ppid);
  assert(host.cmdline.startsWith("claude bg-pty-host ") && host.ppid === workers.supervisor.pid, "a PTY host sits between worker and supervisor");
  assert.equal(worker.env.CLAUDE_JOB_DIR !== undefined, true, "worker shells carry CLAUDE_JOB_DIR");
}
assert(hooks.concat(commands).every((record) => record.env.CLAUDE_CODE_SESSION_KIND === undefined && record.env.CLAUDE_BG_BACKEND === undefined), "session-kind variables stay in the worker process");
assert(of("processes").some((record) => record.processes.some((entry) => entry.env.CLAUDE_CODE_SESSION_KIND === "bg")), "a worker process carries CLAUDE_CODE_SESSION_KIND=bg");
// The worker's argv is not a session carrier: a worker spawned directly names
// its session with --session-id, one claimed from a pre-warmed spare does not.
for (const worker of [workers.a, workers.b]) {
  const argv = worker.ancestry.find((entry) => entry.pid === worker.job.pid).cmdline;
  assert(argv.includes(`--session-id ${worker.job.sessionId}`) || argv.startsWith("claude bg-spare "), `worker argv is direct or a claimed spare: ${argv}`);
}
assert.equal(workers.b.ancestry.find((entry) => entry.pid === workers.b.job.pid).cmdline.startsWith("claude bg-spare "), true, "worker b came from a claimed spare");

// EnterWorktree relocates a worker: the listing, later hook cwds and the shell
// follow the linked Worktree while session, pid and CLAUDE_PROJECT_DIR stay.
const edit = of("worker.edit")[0];
const events = edit.hooks.map((event) => [event[0], event[2]]);
assert.deepEqual(events, [["SessionStart", null], ["UserPromptSubmit", null], ["PreToolUse", "EnterWorktree"], ["PostToolUse", "EnterWorktree"], ["PreToolUse", "Bash"], ["PostToolUse", "Bash"], ["Stop", null]]);
const projectDir = edit.hooks[0][1];
assert.notEqual(edit.d.cwd, projectDir);
assert(edit.worktrees.includes(edit.d.cwd), "the listing's cwd is a linked Worktree of the fixture");
assert.deepEqual(edit.hooks.map((event) => event[1] === projectDir), [true, true, true, false, false, false, false], "hook cwd follows the relocation from PostToolUse on");
assert(edit.hooks.slice(3).every((event) => event[1] === edit.d.cwd), "hooks after EnterWorktree report the linked Worktree");
assert(edit.hooks.every((event) => event[5] === projectDir), "CLAUDE_PROJECT_DIR stays at the dispatch directory");
assert(!hooks.some((record) => record.event === "CwdChanged"), "no CwdChanged hook was delivered for EnterWorktree");
assert.equal(edit.commandCwd, edit.d.cwd);
assert.equal(edit.commandSession, edit.d.sessionId);
assert.equal(edit.commandPid, edit.d.pid);

// An attached terminal dying leaves the worker running with no lifecycle hook.
const attach = of("attach")[0];
assert.equal(attach.workerAlive, true);
assert(!attach.newHooks.some((event) => event[0] === "SessionEnd"), "no SessionEnd when the attached terminal dies");

// Abrupt worker death under a live supervisor: same session, new pid, resume.
const killed = of("worker.after-kill")[0];
assert.equal(killed.restartSource, "resume");
assert.equal(killed.a.sessionId, workers.a.job.sessionId);
assert.notEqual(killed.a.pid, workers.a.job.pid);
assert(killed.a.startedAt > workers.a.job.startedAt, "the restarted worker lists a later startedAt");
const startTimeOf = (pid) => hooks.flatMap((record) => record.ancestry).find((entry) => entry.pid === pid).startTime;
assert(startTimeOf(killed.a.pid) > startTimeOf(workers.a.job.pid), "the new worker pid has a later /proc start time");
assert(!killed.newHooks.some((event) => event[0] === "SessionEnd"), "no SessionEnd for a killed worker");

// Supervisor replacement: workers keep pid and session; no SessionEnd.
const replaced = of("workers.after-replacement")[0];
assert.notEqual(replaced.supervisor.pid, workers.supervisor.pid);
assert.equal(replaced.b.pid, workers.b.job.pid);
assert.equal(replaced.b.sessionId, workers.b.job.sessionId);
assert.equal(replaced.a.pid, killed.a.pid);
assert(!replaced.newHooks.some((event) => event[0] === "SessionEnd"), "no SessionEnd across supervisor replacement");
const without = of("workers.without-supervisor")[0];
assert.equal(without.supervisorRunning, false);
assert.equal(without.b.pid, workers.b.job.pid);
const stopB = hooks.find((record) => record.event === "Stop" && record.payload.session_id === workers.b.job.sessionId);
assert.equal(Number(stopB.env.CLAUDE_PID), workers.b.job.pid);
assert(stopB.receipt > replaced.receipt, "worker b's turn ended under the replacement supervisor");

// Explicit stop publishes SessionEnd; respawn resumes the same session anew.
const stopped = of("worker.after-stop")[0];
assert.deepEqual(stopped.newHooks.map((event) => event.slice(0, 3)), [["SessionEnd", workers.b.job.sessionId, "other"]]);
assert.equal(stopped.b.state, "stopped");
assert.equal(stopped.b.pid, undefined);
const respawned = of("worker.after-respawn")[0];
assert.equal(respawned.source, "resume");
assert.equal(respawned.b.sessionId, workers.b.job.sessionId);
assert.notEqual(respawned.b.pid, workers.b.job.pid);
assert(respawned.b.startedAt > workers.b.job.startedAt);

// Stopping the supervisor without --keep-workers ends every worker.
const shutdown = of("workers.after-supervisor-stop")[0];
const endedSessions = new Set(shutdown.newHooks.filter((event) => event[0] === "SessionEnd").map((event) => event[1]));
assert(endedSessions.has(workers.a.job.sessionId) && endedSessions.has(workers.b.job.sessionId), "supervisor stop ends the surviving workers");
const finalJobs = of("workers.final")[0].jobs;
assert(finalJobs.every((job) => job.state === "stopped" && job.pid === undefined));
assert(finalJobs.find((job) => job.id === workers.a.job.id).startedAt <= workers.a.job.startedAt, "a stopped job lists its dispatch time");
assert.equal(finalJobs.find((job) => job.id === edit.d.id).cwd, projectDir, "a stopped job lists its dispatch directory");
assert(!shutdown.processes.some((entry) => [killed.a.pid, respawned.b.pid, edit.d.pid].includes(entry[0])), "no worker outlives the supervisor stop");
assert(of("daemon.log")[0].lines.some((line) => line.includes("bg adopt: adopted=3")), "the replacement supervisor adopted the three survivors");

// Remote Control server mode refuses API-key credentials outright.
const remote = of("remote-control")[0];
assert.equal(remote.status, 1);
assert.match(remote.stderr, /must be logged in to use Remote Control/);

// The trace holds metadata only: no transcripts, tokens or prompts.
const text = readFileSync(tracePath, "utf8");
assert(!text.includes("CLAUDE_CODE_MESSAGING_TOKEN"), "messaging token not retained");
assert(!/"transcript_path":/.test(text) && !/last_assistant_message":/.test(text), "transcripts and messages not retained");
console.log(`Verified ${records.length} records: ${hooks.length} hooks, ${commands.length} commands, ${scenarios.length} scenarios.`);
