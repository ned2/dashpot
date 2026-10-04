// Independent verifier for a Codex 448 live-SessionStart trace. Checks every
// finding the run reports against the recorded hooks, shells, model requests
// and stored hook records, without importing the runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
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
const outcome = (name) => one(`${name}.outcome`);
const hooks = of("hook");
const hostOf = (record) => record.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const sessionHooks = (session, event) => hooks.filter((record) => record.payload.session_id === session && (!event || record.event === event));
const lastBefore = (list, receipt) => list.filter((record) => record.receipt < receipt).at(-1);
const subagentStop = (worker) => {
  const found = hooks.filter((record) => record.event === "SubagentStop" && record.payload.agent_id === worker);
  assert.equal(found.length, 1, `worker ${worker} stopped once`);
  return found[0];
};
const findings = [];
const finding = (text) => findings.push(text);

// The trace names the runner's exact sources.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "processes.py"].map((file) => `src/dashpot/sessions/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules were the same at the run's end as at its start.
assert.deepEqual(one("sources.after").sourceSHA256, environment.sourceSHA256, "no source changed during the run");
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "standalone", "daemon", "compact", "auto-compact", "daemon-terminal", "second-client-resume", "unload", "daemon-stop"]);
assert(!of("runner.error").length, "the runner completed");
assert(of("hooks.list")[0].after.every(([, trust]) => trust === "trusted"), "fixture hooks trusted");
assert(of("processes").every((record) => record.daemonSettings?.updater?.autoUpdateEnabled === false), "the daemon's updater stayed off");
assert.deepEqual(one("processes", (record) => record.label === "after-daemon-stop").processes, [], "no fixture Codex process outlived the daemon stop");
assert.deepEqual(one("shared-daemon-dir").removed, [], "nothing was removed from the shared daemon directory");
assert(hooks.filter((record) => environment.hookEvents.includes(record.event)).every((record) => record.publisher?.status === 0), "every subscribed hook reached Dashpot's publisher and succeeded");
assert(hooks.filter((record) => environment.recordedOnly.includes(record.event)).every((record) => record.publisher === null), "compaction hooks were recorded, not published");
// Every source a SessionStart carried in the run.
const sources = [...new Set(hooks.filter((record) => record.event === "SessionStart").map((record) => record.payload.source))].sort();
assert.deepEqual(sources, ["clear", "compact", "startup"], "the run saw startup, clear and compact, and never resume");
finding(`SessionStart sources seen: ${sources.join(", ")}`);
// Every SessionStart, by source, and whether its session had ended before it.
for (const start of hooks.filter((record) => record.event === "SessionStart")) {
  const earlier = sessionHooks(start.payload.session_id).filter((record) => record.receipt < start.receipt);
  if (start.payload.source === "startup" || start.payload.source === "clear") assert.equal(earlier.length, 0, `${start.payload.source} SessionStart ${start.receipt} opens a new session`);
  else assert(earlier.length > 0 && !earlier.some((record) => record.event === "SessionEnd"), `${start.payload.source} SessionStart ${start.receipt} follows a live record`);
}

// A compaction's SessionStart: same session, same Host Process, no SessionEnd
// before it, the worker at work across it and stopping after it, and
// Dashpot's stored record after it still listing the worker.
const liveCompactStart = (name, lead, worker, compactAt, { trigger, lazy }) => {
  const startup = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === lead && record.payload.source === "startup");
  const pre = one("hook", (record) => record.event === "PreCompact" && record.payload.session_id === lead);
  const post = one("hook", (record) => record.event === "PostCompact" && record.payload.session_id === lead);
  const start = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === lead && record.payload.source === "compact");
  assert(pre.receipt > compactAt && pre.payload.trigger === trigger && post.payload.trigger === trigger, `${name}: ${trigger} PreCompact and PostCompact`);
  assert(pre.receipt < post.receipt && post.receipt < start.receipt, `${name}: SessionStart(compact) follows PostCompact`);
  assert(!sessionHooks(lead, "SessionEnd").some((record) => record.receipt < start.receipt), `${name}: no SessionEnd before SessionStart(compact)`);
  assert.equal(hostOf(start), hostOf(startup), `${name}: SessionStart(compact) from the startup's Host Process`);
  assert.equal(start.stored?.sessionProcess?.pid, hostOf(startup), `${name}: the stored record names that Host Process`);
  const between = sessionHooks(lead).filter((record) => record.receipt > post.receipt && record.receipt < start.receipt);
  if (lazy) {
    // Nothing until the next prompt: SessionStart(compact) opens that turn.
    assert.deepEqual(between.map((record) => record.event), [], `${name}: nothing published between PostCompact and SessionStart(compact)`);
    const prompt = sessionHooks(lead).find((record) => record.receipt > start.receipt);
    assert(prompt.event === "UserPromptSubmit" && prompt.payload.turn_id !== pre.payload.turn_id, `${name}: the next prompt's turn follows SessionStart(compact)`);
  } else {
    // Inside the compacting turn, with no prompt of its own.
    const stop = sessionHooks(lead, "Stop").find((record) => record.payload.turn_id === pre.payload.turn_id);
    assert(stop && stop.receipt > start.receipt, `${name}: SessionStart(compact) inside the compacting turn`);
    assert(!sessionHooks(lead, "UserPromptSubmit").some((record) => record.receipt > post.receipt && record.receipt < start.receipt), `${name}: no prompt before SessionStart(compact)`);
  }
  const stopped = subagentStop(worker);
  assert(stopped.receipt > start.receipt && stopped.payload.session_id === lead, `${name}: the worker's SubagentStop follows SessionStart(compact) on the same session`);
  const command = of("command").find((record) => record.phase === "start" && record.env.CODEX_THREAD_ID === worker);
  const ended = of("command").filter((record) => record.phase === "end" && record.env.CODEX_THREAD_ID === worker && record.label === command.label)[0];
  assert(command.receipt < start.receipt && ended.receipt > start.receipt, `${name}: the worker's first command spans SessionStart(compact)`);
  assert.equal(hostOf(command), hostOf(startup), `${name}: the worker runs in the same Host Process`);
  // Dashpot's stored record right after SessionStart(compact), under the
  // checkout's hook_records.py.
  assert(start.stored.liveSubagents.includes(worker) && start.stored.state === "running", `${name}: the stored record keeps the worker listed`);
  assert.deepEqual(stopped.stored.liveSubagents, [], `${name}: the worker's stop clears it`);
  finding(`${name}: ${trigger} compaction PreCompact ${pre.receipt}, PostCompact ${post.receipt}, SessionStart(compact) ${start.receipt} ${lazy ? "at the next prompt" : "inside the turn"}, host ${hostOf(start)}, SubagentStop ${stopped.receipt}`);
  return { start, post };
};

// Standalone terminal: `/compact`, then `/clear`, while worker S works.
const standalone = outcome("standalone");
liveCompactStart("standalone /compact", standalone.lead, standalone.worker, standalone.compactAt, { trigger: "manual", lazy: true });
assert.equal(standalone.nextSession, standalone.lead, "standalone: the next prompt stays in the lead's session");
assert(!standalone.compactWorking.stopped && standalone.compactWorking.commandsEnded === 0, "standalone: the worker works across /compact");
const clearStart = one("hook", (record) => record.event === "SessionStart" && record.payload.source === "clear" && record.payload.session_id === standalone.clearedSession);
assert.notEqual(standalone.clearedSession, standalone.lead, "standalone /clear: a new session");
assert.equal(hostOf(clearStart), hostOf(one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === standalone.lead && record.payload.source === "startup")), "standalone /clear: same Host Process");
assert(!standalone.clearWorking.stopped, "standalone: the worker works across /clear");
const standaloneStop = subagentStop(standalone.worker);
const standaloneEnd = one("hook", (record) => record.event === "SessionEnd" && record.payload.session_id === standalone.lead);
assert(standaloneStop.receipt > clearStart.receipt && standaloneStop.payload.session_id === standalone.lead, "standalone /clear: the old session's worker stops after the clear, on the old session");
assert(standaloneEnd.receipt > standaloneStop.receipt && standaloneEnd.receipt > one("terminal.type", (record) => record.name === "standalone" && record.text === "/exit").receipt,
  "standalone /clear: the old session ends only when the terminal exits");
finding(`standalone /clear: SessionStart(clear) ${clearStart.receipt} on new session, old session's SubagentStop ${standaloneStop.receipt}, old SessionEnd ${standaloneEnd.receipt} at exit`);

// Daemon: `thread/compact/start` while worker C works.
const compact = outcome("compact");
assert.deepEqual(one("compact.response").response, {}, "thread/compact/start answers {}");
liveCompactStart("daemon thread/compact/start", compact.lead, compact.worker, compact.compactAt, { trigger: "manual", lazy: true });
assert(!compact.compactWorking.stopped && compact.compactWorking.commandsEnded === 0 && !compact.nextWorking.stopped, "compact: the worker works across compaction and the next turn");
assert(compact.notifications.some(([method, , , item]) => method === "item/completed" && item === "contextCompaction"), "compact: the compaction is a turn with a contextCompaction item");

// Daemon: automatic compaction mid-turn while worker A works.
const auto = outcome("auto-compact");
const autoRun = liveCompactStart("daemon auto-compaction", auto.lead, auto.worker, 0, { trigger: "auto", lazy: false });
assert(!auto.turnWorking.stopped && auto.turnWorking.commandsEnded === 0, "auto-compact: the worker works across compaction");
assert(auto.requests.some(([, label, , compaction]) => label === "ac-spawn" && compaction), "auto-compact: Codex sent a compaction request");
assert(auto.requests.filter(([, label, , compaction, , action]) => label === "ac-spawn" && !compaction && action === "exec_command").length === 2, "auto-compact: the turn carried on after compaction");
assert(!sessionHooks(auto.lead, "SessionStart").some((record) => record.receipt > autoRun.start.receipt), "auto-compact: the next turn publishes no SessionStart");

// Daemon terminal: `/new`, then the new thread's `/clear`.
const terminal = outcome("daemon-terminal");
const daemonPid = compact.daemonPid;
const newStart = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === terminal.newSession);
const clearedStart = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === terminal.clearedSession);
assert.equal(newStart.payload.source, "startup", "/new opens a new session with source startup");
assert.equal(clearedStart.payload.source, "clear", "/clear opens a new session with source clear");
assert(new Set([terminal.lead, terminal.newSession, terminal.clearedSession]).size === 3, "each of /new and /clear made a new thread");
for (const record of [newStart, clearedStart]) assert.equal(hostOf(record), daemonPid, "the daemon hosts the new thread");
// The terminal leaves the old thread at once; the daemon unloads it, with
// SessionEnd, about 60 s later, as for any thread with no client.
for (const [lead, worker, opened, typed] of [[terminal.lead, terminal.worker, newStart, "/new"], [terminal.newSession, terminal.secondWorker, clearedStart, "/clear"]]) {
  const keystroke = one("terminal.type", (record) => record.name === "daemon" && record.text === typed);
  const stopped = subagentStop(worker);
  const ended = one("hook", (record) => record.event === "SessionEnd" && record.payload.session_id === lead);
  assert(stopped.receipt > opened.receipt && stopped.payload.session_id === lead, "the old thread's worker stops after the new thread opens, on the old session");
  const unloadMs = ended.receiptTime - keystroke.receiptTime;
  assert(unloadMs > 55000 && unloadMs < 70000, `the old thread unloads about 60 s after ${typed}`);
  assert(!sessionHooks(lead, "SessionStart").some((record) => record.payload.source !== "startup"), "the old thread publishes no further SessionStart");
  finding(`daemon terminal ${typed}: SessionStart(${opened.payload.source}) on new ${opened.payload.session_id.slice(-6)} at ${opened.receipt}; old ${lead.slice(-6)} worker SubagentStop ${stopped.receipt} (+${stopped.receiptTime - opened.receiptTime} ms), old SessionEnd ${ended.receipt} ${unloadMs} ms after ${typed}`);
}
assert(!terminal.newWorking.stopped && !terminal.clearWorking.stopped, "the workers work across /new and /clear");

// Daemon: a second client and a terminal resume a loaded lead while worker R works.
const resume = outcome("second-client-resume");
assert.equal(one("resume.response").thread.id, resume.lead, "thread/resume answered the loaded lead");
const resumeStarts = sessionHooks(resume.lead, "SessionStart");
assert.deepEqual(resumeStarts.map((record) => record.payload.source), ["startup"], "no SessionStart(resume) for a loaded thread");
const resumePrompts = sessionHooks(resume.lead, "UserPromptSubmit").filter((record) => record.receipt > resume.resumeAt);
assert.equal(resumePrompts.length, 2, "the second client's and the terminal's prompts both ran on the lead");
assert(resumePrompts.every((record) => hostOf(record) === daemonPid), "the resumed lead stays in the daemon");
assert(!resume.resumeWorking.stopped && !resume.tuiWorking.stopped, "the worker works across both resumes");
const resumeStop = subagentStop(resume.worker);
assert(resumeStop.receipt > resumePrompts.at(-1).receipt, "the worker stops after both resumes");
assert(resumePrompts.every((record) => record.stored.liveSubagents.includes(resume.worker)), "the stored record keeps the worker listed across both resumes");
finding(`second-client resume: thread/resume ${resume.resumeAt}, prompts ${resumePrompts.map((record) => record.receipt).join(", ")}, no SessionStart after startup ${resumeStarts[0].receipt}, SubagentStop ${resumeStop.receipt}`);

console.log(findings.join("\n"));
console.log(`Verified ${records.length} records${drifted.length ? `; Dashpot modules drifted since the run: ${drifted.join(", ")}` : ""}.`);
