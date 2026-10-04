// Independent verifier for a Codex 460 second-terminal resume trace. Checks
// every finding the run reports against the recorded hooks, shells, terminal
// notices, stored hook records and Cleanup checks, without importing the
// runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.160.0"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const hooks = of("hook");
const hostOf = (record) => record.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const sessionHooks = (session) => hooks.filter((record) => record.payload.session_id === session);
const within = (kind, from, to) => of(kind).filter((record) => record.receipt > from && record.receipt < to);
const findings = [];
const finding = (text) => findings.push(text);
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

// The trace names the runner's exact sources and each publisher's.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs"];
assert.deepEqual(Object.keys(environment.scriptSHA256).sort(), [...scripts].sort());
for (const file of scripts) assert.equal(sha256(readFileSync(path.join(here, file))), environment.scriptSHA256[file], `${file} matches the hash the run recorded`);
const after = one("sources.after");
assert.deepEqual(after.scriptSHA256, environment.scriptSHA256, "no script changed during the run");
assert.deepEqual(after.publishers, environment.publishers.map(({ name, sourceSHA256 }) => ({ name, sourceSHA256 })), "no installed publisher changed during the run");
const checkout = path.resolve(here, "..", "..", "..");
const drifted = [];
for (const publisher of environment.publishers) {
  assert.deepEqual(publisher.dirtySource, [], `${publisher.name}: built from a clean source`);
  for (const [file, digest] of Object.entries(publisher.sourceSHA256)) {
    const source = `src/dashpot/${file}`;
    let current = null;
    if (publisher.source === "worktree") {
      current = existsSync(path.join(checkout, source)) ? sha256(readFileSync(path.join(checkout, source))) : null;
    } else {
      try { current = sha256(execFileSync("git", ["-C", checkout, "show", `${publisher.revision}:${source}`])); } catch { current = null; }
    }
    if (current !== digest) drifted.push(`${publisher.name}:${file}`);
  }
}
assert(!(strict && drifted.length), `publisher sources differ from the run's: ${drifted.join(", ")}`);

const variants = ["attached", "no-daemon"];
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "daemon",
  ...environment.publishers.flatMap(() => variants.map(() => "second-terminal-resume")), "daemon-stop", "control-resume"]);
assert(!of("runner.error").length, "the runner completed");
assert(of("hooks.list")[0].after.every(([, trust]) => trust === "trusted"), "fixture hooks trusted");
assert(of("processes").every((record) => record.daemonSettings?.updater?.autoUpdateEnabled === false), "the daemon's updater stayed off");
assert.deepEqual(one("processes", (record) => record.label === "after-daemon-stop").processes, [], "no fixture Codex process outlived the daemon stop");
assert.deepEqual(one("shared-daemon-dir").removed, [], "nothing was removed from the shared daemon directory");
assert(!of("cleanup.kill").length, "the runner killed no leftover Codex process");
assert(hooks.filter((record) => environment.hookEvents.includes(record.event)).every((record) => record.publisher?.status === 0), "every subscribed hook reached Dashpot's publisher and succeeded");
const daemonPid = one("processes", (record) => record.label === "daemon-started").daemons[0];

const blockers = (record) => record.obstacles.filter((obstacle) => obstacle.kind === "sub-agent");
// Per publisher and variant: the daemon's lead has a working worker when a
// second terminal resumes the lead.
const scenarios = of("scenario").filter((record) => record.name === "second-terminal-resume");
for (const scenario of scenarios) {
  const label = `r${scenario.index}${scenario.variant === "attached" ? "a" : "n"}`;
  const outcome = one("second-terminal-resume.outcome", (record) => record.variant === scenario.variant && record.publisher === scenario.publisher);
  const name = `${scenario.publisher} ${scenario.variant}`;
  const { lead, worker, resumeAt, workerStopAt, exitAt } = outcome;
  assert.equal(outcome.daemonPid, daemonPid);
  const startup = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === lead && record.receipt < resumeAt);
  assert(startup.payload.source === "startup" && hostOf(startup) === daemonPid, `${name}: the daemon started the lead`);
  const workerStart = one("hook", (record) => record.event === "SubagentStart" && record.payload.agent_id === worker);
  const workerStop = one("hook", (record) => record.event === "SubagentStop" && record.payload.agent_id === worker);
  assert(workerStart.receipt < resumeAt && workerStop.receipt > resumeAt, `${name}: the worker started before the resume and stopped after it`);
  assert.equal(workerStop.receipt, workerStopAt, `${name}: the run waited for the worker's stop`);
  const commands = of("command").filter((record) => record.env?.CODEX_THREAD_ID === worker);
  assert(commands.length > 0 && commands.every((record) => hostOf(record) === daemonPid), `${name}: the worker's commands ran in the daemon`);
  assert(!outcome.resumeWorking.stopped && outcome.resumeWorking.commandsStarted > outcome.resumeWorking.commandsEnded, `${name}: the worker was mid-command when the terminal's minute ran out`);
  const terminal = one("terminal.start", (record) => record.name === `${label}-${scenario.variant}`);
  assert(terminal.receipt > resumeAt && terminal.receipt < workerStop.receipt, `${name}: the terminal started while the worker worked`);
  assert.equal(terminal.args.includes("--no-daemon"), scenario.variant === "no-daemon");
  const typed = one("terminal.type", (record) => record.name === terminal.name && record.text === "/exit");
  assert(typed.receipt > workerStop.receipt, `${name}: the terminal stayed open past the worker's stop`);
  const exited = one("terminal.exit", (record) => record.name === terminal.name);
  assert.equal(exited.status, 0, `${name}: the terminal exited cleanly`);
  // The terminal's own process was there throughout.
  const states = of("standalone.state").filter((record) => record.label === `${label}-resumed` || record.label === `${label}-after-worker`);
  assert.equal(states.length, 2);
  for (const state of states) assert.equal(state.processes.length, 1, `${name}: one terminal Codex process at ${state.label}`);
  const terminalPid = states[0].processes[0].pid;
  assert.equal(states[1].processes[0].pid, terminalPid);
  // Every hook of the lead from the resume to the exit came from the daemon.
  const resumed = sessionHooks(lead).filter((record) => record.receipt > resumeAt && record.receipt < exited.receipt);
  assert(resumed.every((record) => hostOf(record) === daemonPid), `${name}: the daemon published every hook of the lead`);
  assert(!resumed.some((record) => record.event === "SessionStart" || hostOf(record) === terminalPid), `${name}: the terminal published no SessionStart and no hook`);
  const prompts = resumed.filter((record) => record.event === "UserPromptSubmit");
  if (scenario.variant === "attached") {
    assert(prompts.length === 1 && prompts[0].receipt < workerStop.receipt, `${name}: the attached terminal's turn ran in the daemon while the worker worked`);
    assert(exited.notices.some((notice) => notice.startsWith("Disconnected from this task")), `${name}: the attached terminal disconnected from the daemon's task`);
  } else {
    assert.deepEqual(prompts, [], `${name}: the --no-daemon terminal ran no turn`);
    assert(states.every((state) => state.processes[0].state.startsWith("S")), `${name}: the --no-daemon terminal sat waiting`);
  }
  // Cleanup kept the worker's blocker until its stop, and only then let go.
  const checks = within("cleanup", scenario.receipt, outcome.receipt);
  assert(checks.every((record) => record.publisher === scenario.publisher));
  assert.deepEqual(checks.map((record) => record.label), ["before", "resumed-turn", "worker-stopped", "terminal-exited"]);
  assert(checks[0].receipt <= resumeAt && checks[2].receipt > workerStop.receipt && checks[3].receipt > exitAt, `${name}: the checks fall around the resume, the stop and the exit`);
  for (const check of checks) {
    assert.equal(check.status, 0);
    const blocking = check.receipt < workerStop.receipt;
    assert.equal(blockers(check).length, blocking ? 1 : 0, `${name} ${check.label}: the sub-agent blocker ${blocking ? "holds" : "is gone"}`);
    if (blocking) assert(blockers(check)[0].detail.includes(worker), `${name} ${check.label}: the blocker names the worker`);
  }
  finding(`${name}: resume ${resumeAt}, lead hooks ${resumed.map((record) => `${record.event}@${record.receipt}`).join(", ")} all from daemon ${daemonPid}, terminal pid ${terminalPid} published none; blocker held until SubagentStop ${workerStop.receipt}`);
}

// Control: with the daemon stopped, a --no-daemon resume is its own Host
// Process and publishes the resumed session's turn.
const control = one("control-resume.outcome");
const daemonStopped = one("processes", (record) => record.label === "after-daemon-stop");
const controlHooks = control.hooks.map((receipt) => hooks.find((record) => record.receipt === receipt));
assert.deepEqual(controlHooks.map((record) => record.event), ["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"], "control: the resumed session's start, turn and end");
assert(controlHooks.every((record) => record.receipt > daemonStopped.receipt && record.payload.session_id === control.lead), "control: after the daemon stopped, on the lead");
assert.equal(controlHooks[0].payload.source, "resume", "control: SessionStart(resume)");
assert.equal(control.hosts.length, 1);
assert(control.hosts[0] !== daemonPid && controlHooks.every((record) => hostOf(record) === control.hosts[0]), "control: one Host Process of its own");
finding(`control: --no-daemon resume after the daemon stopped published SessionStart(resume) ${controlHooks[0].receipt} and its turn from its own pid ${control.hosts[0]}`);

console.log(findings.join("\n"));
console.log(`Verified ${records.length} records${drifted.length ? `; publisher sources drifted since the run: ${drifted.join(", ")}` : ""}.`);
