// Independent verifier for a Codex 161 acceptance trace. Checks the recorded
// hosting, hook, shell, and protocol evidence, and Dashpot's own published
// view at each step, against the claims the docs make for the pinned
// release, without importing the runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.159.3"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const labelled = (kind, label) => one(kind, (record) => record.label === label);
const view = (label) => labelled("dashpot.view", label);
const hooks = of("hook");
const shell = (label, phase = "start") => one("command", (record) => record.label === label && record.phase === phase);
const hostOf = (record) => record.ancestry.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const scenario = (name) => one("scenario", (record) => record.name === name);
const nextScenario = (name) => of("scenario")[of("scenario").indexOf(scenario(name)) + 1] ?? records.at(-1);
const hooksIn = (name) => hooks.filter((record) => record.receipt > scenario(name).receipt && record.receipt < nextScenario(name).receipt);
const runFor = (snapshot, number) => snapshot.agentRuns.filter((run) => run.issueId === `I_fixture_${number}`);
const onlyRun = (snapshot, number) => { const runs = runFor(snapshot, number); assert.equal(runs.length, 1, `${snapshot.label}: one run for Issue ${number}`); return runs[0]; };
const unbound = (snapshot) => snapshot.agentRuns.filter((run) => run.issueId === null);
const hostedBy = (pid) => `codex pid ${pid}`;

// The trace names the exact sources that produced it, this file included.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "work.py", "work_reconciliation.py"].map((file) => `src/dashpot/sessions/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
const { main, other, third, fourth } = environment.worktrees;
assert.deepEqual([...environment.hookEvents].sort(), ["Interrupt", "SessionEnd", "SessionStart", "Stop", "SubagentStart", "SubagentStop", "UserPromptSubmit"]);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "exec-no-daemon", "remote-control", "standalone-terminal", "terminal-joined-input",
  "standalone-gone", "autostart-terminal", "autostart-disabled-beside-daemon", "standalone-exit", "daemon-roots", "attach-detach", "interrupt", "delegate", "fork",
  "live-relocation", "joined-input", "unload-while-running", "resume-after-unload", "daemon-gone", "daemon-recovery", "daemon-stop"]);
assert(of("hooks.list")[0].after.every(([, trust]) => trust === "trusted"), "fixture hooks trusted");
assert.deepEqual(labelled("processes", "after-trust").daemons, []);
// Dashpot's real publisher accepted every hook, and every hook names its thread.
for (const hook of hooks) {
  assert.equal(hook.publisher.status, 0, `publisher accepted ${hook.event}: ${hook.publisher.stderr}`);
  assert(hook.payload.session_id && hook.payload.cwd, `${hook.event} carries session_id and cwd`);
}
for (const record of of("dashpot.view")) assert.equal(record.status, 0, `dashpot view ${record.label}`);
assert.equal(of("server.error").length, 0, "the fixture servers saw no error");

// `codex exec` hosts its own thread, starts no daemon, and ends it.
const execShell = shell("exec");
assert.match(execShell.ancestry.find((entry) => entry.pid === hostOf(execShell)).cmdline, / exec /);
assert.deepEqual(hooksIn("exec-no-daemon").map((record) => [record.event, record.payload.source ?? record.payload.reason ?? null]),
  [["SessionStart", "startup"], ["UserPromptSubmit", null], ["Stop", null], ["SessionEnd", "other"]]);
assert.deepEqual(labelled("processes", "after-exec").daemons, []);

// `codex remote-control start` installs and starts the managed daemon even
// with no account; its stop leaves only the pid-update-loop companion.
const remote = labelled("codex.command", "remote-control-start");
assert.match(remote.stderr, /Installing daemon from CLI version .* into <root>\/codex-home\/packages\/app-server-daemon/);
assert.notEqual(remote.status, 0);
assert.equal(labelled("processes", "after-remote-control-start").daemons.length, 1);
const afterRemoteStop = labelled("processes", "after-remote-control-stop");
assert.deepEqual(afterRemoteStop.daemons, []);
assert(afterRemoteStop.processes.every(([, , , cmdline]) => / app-server daemon pid-/.test(cmdline)));

// With autostart disabled and no daemon running, the terminal hosts its own
// thread; `work start` binds Issue 3 to that process.
const standalone = one("standalone.identity");
const tsHost = standalone.shell.host;
assert.deepEqual(standalone.daemons, []);
assert(standalone.hookHosts.every(([, host]) => host === tsHost));
assert.equal(standalone.shell.cwd, third);
assert.equal(standalone.shell.work.status, 0);
assert.match(shell("ts-start").ancestry.find((entry) => entry.pid === tsHost).cmdline, /--disable daemon_auto_start/);
const tsBound = onlyRun(view("standalone-bound"), 3);
assert.deepEqual([tsBound.processOrSession, tsBound.workingDirectory], [hostedBy(tsHost), third]);

// Input typed while the terminal's turn runs joins that turn: its
// UserPromptSubmit names the same turn and fires only once the running
// command has finished, at the turn's directory.
const joinedTerminal = one("terminal-joined.outcome");
const prompts = joinedTerminal.hooks.filter(([event]) => event === "UserPromptSubmit");
assert.equal(prompts.length, 2);
assert.equal(prompts[0][1], prompts[1][1], "one turn");
assert(prompts[1][3] >= joinedTerminal.holdEnded && prompts[1][3] > joinedTerminal.typedAt, "the joined input's hook fires when it is taken, after the command");
assert.equal(joinedTerminal.joined.cwd, third);

// SIGKILL of the standalone host: no hook; the run is orphaned.
assert.deepEqual(one("standalone-gone.hooks").newHooks, []);
const tsGone = onlyRun(view("standalone-gone"), 3);
assert.deepEqual([tsGone.orphaned, tsGone.state, tsGone.processOrSession], [true, "unknown", hostedBy(tsHost)]);

// The conversation resumed in a new standalone terminal is not continued
// (Codex declares no exclusive Host Process); `work start` recovers it.
const resumedFirst = one("standalone-resumed.first");
const ts2Host = resumedFirst.shell.host;
assert.notEqual(ts2Host, tsHost);
assert.deepEqual(resumedFirst.daemons, []);
assert.deepEqual(resumedFirst.newHooks[0].slice(0, 3), ["SessionStart", standalone.shell.thread, "resume"]);
assert(resumedFirst.hookHosts.every(([, host]) => host === ts2Host));
assert(resumedFirst.continuation.every(([, continued]) => continued === false), "no continuation notice");
const resumedView = view("standalone-resumed");
assert.deepEqual([onlyRun(resumedView, 3).orphaned, onlyRun(resumedView, 3).processOrSession], [true, hostedBy(tsHost)]);
assert.deepEqual(unbound(resumedView).map((run) => run.processOrSession), [`${standalone.shell.thread} hook`]);
assert.equal(one("standalone-resumed.recover").shell.work.status, 0);
const tsRecovered = onlyRun(view("standalone-recovered"), 3);
assert.deepEqual([tsRecovered.orphaned, tsRecovered.processOrSession], [false, hostedBy(ts2Host)]);
assert(tsRecovered.startedAt > tsBound.startedAt, "explicit recovery restarts the run");
assert.deepEqual(unbound(view("standalone-recovered")), []);

// A plain terminal autostarts the managed daemon from the CLI's own binary,
// as its child, and the daemon hosts every hook and shell of the terminal.
const autostart = one("autostart.identity");
const daemonPid = autostart.daemonPid;
assert(daemonPid, "a daemon was autostarted");
assert.match(autostart.daemonCmdline[3], /^<root>\/codex-home\/packages\/app-server-daemon\/releases\/.*\/codex app-server --remote-control --listen unix:\/\/ --managed-daemon/);
assert(autostart.installed.some((entry) => entry.startsWith("app-server-daemon")), "the daemon was installed into CODEX_HOME");
assert(!autostart.installed.some((entry) => entry.startsWith("standalone")), "no standalone release was linked");
assert(autostart.hookHosts.every(([, host, chain]) => host === daemonPid && chain[1][1] === "codex"), "the daemon, a child of the terminal, hosts its hooks");
assert.equal(autostart.shell.host, daemonPid);
const terminalPid = autostart.hookHosts[0][2][1][0];
assert.equal(labelled("processes", "autostart-running").processes.find(([pid]) => pid === daemonPid)[1], terminalPid);
assert.equal(onlyRun(view("autostart-bound"), 1).processOrSession, hostedBy(daemonPid));
// The standalone terminal keeps hosting its own thread beside the daemon; a
// terminal launched with autostart disabled while the daemon runs attaches
// to it, and its `/exit` runs no hook.
assert(one("standalone.second").hookHosts.every(([, host]) => host === ts2Host));
assert.equal(one("standalone.second").shell.host, ts2Host);
const disabled = one("autostart-disabled.identity");
assert(disabled.hookHosts.every(([, host]) => host === daemonPid));
assert.equal(disabled.shell.host, daemonPid);
assert.deepEqual(one("autostart-disabled.exit").newHooks, []);
// The standalone terminal's `/exit` ends its thread and Issue 3's run at once.
assert.deepEqual(one("standalone.exit").newHooks.map(([event, session, reason, , cwd]) => [event, session, reason, cwd]), [["SessionEnd", standalone.shell.thread, "other", third]]);
assert.deepEqual(runFor(view("standalone-exited"), 3), []);

// Two root threads in the main Worktree and the terminal's thread in
// `other`, each with its own run, all on one daemon process.
const roots = one("daemon-roots.identity");
assert.deepEqual([roots.r1.host, roots.r2.host, roots.r1.cwd, roots.r2.cwd], [daemonPid, daemonPid, main, main]);
const rootsView = view("daemon-roots");
for (const [number, at] of [[2, main], [4, main], [1, other]]) {
  const run = onlyRun(rootsView, number);
  assert.deepEqual([run.processOrSession, run.workingDirectory, run.orphaned], [hostedBy(daemonPid), at, false]);
}
const r1 = roots.r1Thread;
const r2 = roots.r2Thread;
const ta = autostart.shell.thread;
const runIds = Object.fromEntries([1, 2, 4].map((number) => [number, onlyRun(rootsView, number).id]));

// Attach and detach while a turn continues: no hook, no change to the run.
assert.deepEqual(one("attach.outcome").newHooks, []);
assert.equal(onlyRun(view("attach-turn-running"), 2).state, "running");
const detach = one("detach.outcome");
assert.deepEqual([detach.commandEnded, detach.status], [true, "completed"]);
assert(!detach.newHooks.some(([event]) => ["Interrupt", "SessionEnd"].includes(event)));
assert.deepEqual([onlyRun(view("after-detach"), 2).id, onlyRun(view("after-detach"), 2).state], [runIds[2], "waiting"]);

// Interrupt: the turn settles interrupted, and the run stays.
const interrupt = one("interrupt.outcome");
assert.equal(interrupt.status, "interrupted");
assert(interrupt.newHooks.some(([event, session]) => event === "Interrupt" && session === r2));
assert.equal(onlyRun(view("interrupt-running"), 4).state, "running");
assert.deepEqual([onlyRun(view("after-interrupt"), 4).id, onlyRun(view("after-interrupt"), 4).state], [runIds[4], "waiting"]);

// A delegated thread: its shell carries its own thread id under its root's
// session id, its hooks are child-scoped, and its parent stays running and
// bound while it works.
const delegate = one("delegate.outcome");
assert.notEqual(delegate.childThread, r1);
assert.deepEqual([delegate.child.thread, delegate.child.session, delegate.child.host], [delegate.childThread, r1, daemonPid]);
const childScoped = delegate.newHooks.filter(([, , , agent]) => agent === delegate.childThread);
assert(childScoped.every(([, session]) => session === r1), "the child's hooks name the root session and the child agent");
assert(childScoped.some(([event]) => event === "SubagentStart") && childScoped.some(([event]) => event === "SubagentStop"));
assert.equal(delegate.child.work.status, 0);
assert.equal(onlyRun(view("delegate-running"), 2).state, "running");
const delegateCheck = labelled("dashpot.worktree-check", "delegate-running").result;
assert.equal(delegateCheck.removable, false);
assert(delegateCheck.obstacles.some((obstacle) => obstacle.kind === "agent-run" && /fixture-2/.test(obstacle.detail)));
const fourthWhileDelegating = labelled("dashpot.worktree-check", "delegate-running-fourth").result;
assert.equal(fourthWhileDelegating.removable, false);
assert.deepEqual(fourthWhileDelegating.obstacles.map((obstacle) => obstacle.kind), ["sub-agent"]);
assert(fourthWhileDelegating.obstacles[0].detail.includes(delegate.childThread), "the blocker names the sub-agent");
assert.equal(onlyRun(view("after-delegate"), 2).id, runIds[2]);

// A fork is a new conversation: its own SessionStart, no inherited run.
const fork = one("fork.outcome");
assert.notEqual(fork.fork.id, r1);
assert.equal(fork.fork.forkedFromId, r1);
assert.deepEqual(fork.newHooks[0].slice(0, 3), ["SessionStart", fork.fork.id, "fork"]);
assert.deepEqual(unbound(view("after-fork")).filter((run) => run.workingDirectory === main).map((run) => run.processOrSession), [`${fork.fork.id} hook`]);
assert.deepEqual(view("after-fork").agentRuns.filter((run) => run.issueId).map((run) => run.id).sort(), Object.values(runIds).sort());

// Live Relocation: a controller's `turn/start` with a `cwd` override on the
// terminal's thread carries Issue 1's run to `fourth` with its identity,
// and the terminal's own next turn runs there too.
const beforeMove = onlyRun(view("before-relocation"), 1);
const move = one("relocation.move");
assert.deepEqual([move.shell.cwd, move.shell.thread, move.shell.host], [fourth, ta, daemonPid]);
assert(move.newHooks.some(([event, session, , , cwd]) => event === "UserPromptSubmit" && session === ta && cwd === fourth));
const afterMove = onlyRun(view("after-relocation"), 1);
assert.deepEqual([afterMove.id, afterMove.startedAt, afterMove.workingDirectory, afterMove.processOrSession], [beforeMove.id, beforeMove.startedAt, fourth, hostedBy(daemonPid)]);
assert.equal(labelled("dashpot.worktree-check", "after-relocation-other").result.removable, true);
const fourthCheck = labelled("dashpot.worktree-check", "after-relocation-fourth").result;
assert(fourthCheck.obstacles.some((obstacle) => obstacle.kind === "agent-run" && /fixture-1/.test(obstacle.detail)));
// The run left `other`; the session's older record stays there until its
// SessionEnd, read as no occupant since the freshest record is at `fourth`.
assert(!view("after-relocation").stateFiles.other.some((name) => name.startsWith("work/")));
assert.equal(one("relocation.terminal").shell.cwd, fourth);
assert.equal(onlyRun(view("after-relocation-terminal"), 1).id, beforeMove.id);

// Input joined to a running controller turn with a `cwd` override: the
// override applies after that turn, so the joined input's hook and shell
// stay at the old directory and the run moves only on the next turn's
// UserPromptSubmit.
const joinedRequest = one("joined.request");
assert.deepEqual([joinedRequest.sameTurn, joinedRequest.status], [true, "inProgress"]);
const joined = one("joined.outcome");
const joinedPrompts = joined.turns.filter(([event, session]) => event === "UserPromptSubmit" && session === r1);
assert.equal(joinedPrompts.length, 2);
assert(joinedPrompts.every(([, , , cwd]) => cwd === main));
assert(joinedPrompts[1][4] >= joined.holdEnded, "the joined input's hook fires when it is taken");
assert.equal(joined.joined.cwd, main);
assert.equal(joined.thread.cwd, third);
assert.equal(onlyRun(view("joined-while-running"), 2).workingDirectory, main);
assert.equal(onlyRun(view("after-joined"), 2).workingDirectory, main);
assert.equal(shell("r1-span").cwd, third);

// One thread unloads, and the terminal exits and its thread unloads, while
// another thread's turn runs: each SessionEnd ends exactly its own run, the
// moved thread's records are gone from every Worktree, and nothing ended
// stays listed, though the daemon was reparented when its terminal exited.
const unload = one("unload.outcome");
assert.equal(unload.spanRunning, true);
const endedAfter = Object.fromEntries(unload.endedAfterMs);
for (const thread of [r2, ta, fork.fork.id]) assert(endedAfter[thread] > 50000 && endedAfter[thread] < 75000, `${thread} unloaded after the delay`);
assert(!(r1 in endedAfter));
assert(unload.newHooks.some(([event, session, reason, , cwd]) => event === "SessionEnd" && session === ta && reason === "other" && cwd === fourth));
const afterUnload = view("after-unload");
assert.deepEqual(afterUnload.agentRuns.map((run) => [run.issueId, run.id, run.workingDirectory]), [["I_fixture_2", runIds[2], third]]);
assert.deepEqual([afterUnload.stateFiles.other, afterUnload.stateFiles.fourth], [[], []]);

// A thread resumed after its unload: the same id, a new incarnation, unbound.
const resumed = one("resume.outcome");
assert.equal(resumed.thread.id, r2);
assert.deepEqual(resumed.newHooks[0].slice(0, 3), ["SessionStart", r2, "resume"]);
assert.deepEqual(runFor(view("after-resume"), 4), []);
assert.deepEqual(unbound(view("after-resume")).map((run) => run.processOrSession), [`${r2} hook`]);

// SIGKILL of the daemon: no hook; the bound run is orphaned and unbound
// sessions leave the view.
assert.deepEqual(one("daemon-gone.hooks").newHooks, []);
assert.deepEqual(view("daemon-gone").agentRuns.map((run) => [run.issueId, run.orphaned, run.state, run.processOrSession]), [["I_fixture_2", true, "unknown", hostedBy(daemonPid)]]);

// A new daemon resumes R1 at its persisted directory: not continued, listed
// beside its orphaned run, and recovered by an explicit `work start`.
const restarted = labelled("processes", "daemon-restarted");
assert.equal(restarted.daemons.length, 1);
const newDaemon = restarted.daemons[0];
assert.notEqual(newDaemon, daemonPid);
const cold = one("cold-resume.outcome");
assert.deepEqual(cold.newHooks[0].slice(0, 3), ["SessionStart", r1, "resume"]);
assert.deepEqual([cold.shell.cwd, cold.shell.host], [third, newDaemon]);
assert(cold.continuation.every(([, continued]) => continued === false));
const coldView = view("cold-resumed");
assert.deepEqual([onlyRun(coldView, 2).orphaned, onlyRun(coldView, 2).processOrSession], [true, hostedBy(daemonPid)]);
assert.deepEqual(unbound(coldView).map((run) => run.processOrSession), [`${r1} hook`]);
assert.equal(one("recover.outcome").shell.work.status, 0);
const recoveredRun = onlyRun(view("recovered"), 2);
assert.deepEqual([recoveredRun.orphaned, recoveredRun.processOrSession, recoveredRun.workingDirectory], [false, hostedBy(newDaemon), third]);
assert.deepEqual(unbound(view("recovered")), []);

// `daemon stop` publishes SessionEnd for the loaded thread, which ends its run.
assert.deepEqual(one("daemon-stop.outcome").newHooks.map(([event, session, reason]) => [event, session, reason]), [["SessionEnd", r1, "other"]]);
assert.deepEqual(view("after-daemon-stop").agentRuns, []);
assert.deepEqual(labelled("processes", "after-daemon-stop").daemons, []);

// Dashpot's Event Log reports each carry as `relocated`, each ending once,
// and no continuation.
const events = one("dashpot.events");
assert.equal(events.status, 0);
const outcomes = events.events.filter((event) => event["event.name"] === "hook.outcome");
assert(outcomes.some((event) => event["dashpot.agent_session.id"] === ta && event["dashpot.hook.event"] === "UserPromptSubmit" && event["dashpot.work_store.change"] === "relocated" && event["dashpot.worktree.path"] === fourth));
assert(outcomes.some((event) => event["dashpot.agent_session.id"] === r1 && event["dashpot.work_store.change"] === "relocated" && event["dashpot.worktree.path"] === third));
assert.deepEqual(outcomes.filter((event) => event["dashpot.work_store.change"] === "ended").map((event) => event["dashpot.issue.id"]).sort(),
  ["I_fixture_1", "I_fixture_2", "I_fixture_3", "I_fixture_4"]);
assert(!outcomes.some((event) => event["dashpot.work_store.change"] === "continued"), "Codex never continues an orphaned run");
assert(outcomes.every((event) => event["dashpot.outcome.result"] === "succeeded"));

console.log(`Verified ${records.length} records from codex-cli ${expectedVersion}`);
console.log(drifted.length ? `Dashpot modules changed since the run: ${drifted.join(", ")}` : `Dashpot modules match the run's (${environment.dashpot.head})`);
