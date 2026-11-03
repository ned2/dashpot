// Independent verifier for the Codex 663 unload and resume trace. Checks the
// recorded daemon notifications, loaded-thread lists, Codex log lines,
// writer-lock probes, resume outcomes, turn contexts, hooks and Dashpot views
// against the claims the spike makes for the pinned release, without
// importing the runner or Dashpot. It prints each measured interval.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.166.0"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const hooks = of("hook");
const requests = of("model.request");
const ISSUE_A = "$ROOT/repository.worktrees/issue-a";
const ISSUE_B = "$ROOT/repository.worktrees/issue-b";
const ROOTS = ["$ROOT/repository.worktrees", "$ROOT/repository/.git"];
const checks = [];
const intervals = [];
const check = (claim, test) => { test(); checks.push(claim); };
const interval = (name, ms, low, high) => {
  assert(ms >= low && ms <= high, `${name}: ${ms} ms outside [${low}, ${high}]`);
  intervals.push(`${name} ${(ms / 1000).toFixed(1)} s`);
};

// The trace names the exact sources and release that produced it.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["run.mjs", "hook.mjs", "command.mjs", "mcp-blocked.mjs", "lock.py", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["hook.py", ...["hook_publish.py", "hook_records.py", "hook_scan.py", "deferred_end.py", "session_exits.py", "work.py", "work_store.py",
  "work_reconciliation.py", "liveness.py", "processes.py"].map((file) => `sessions/${file}`)].map((file) => `src/dashpot/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
assert.deepEqual(one("sources.after").sourceSHA256, environment.sourceSHA256, "no source changed during the run");
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.match(environment.binaryTarget, new RegExp(`/${expectedVersion.replaceAll(".", "\\.")}-x86_64-unknown-linux-musl/bin/codex$`));
if (expectedVersion === "0.166.0") assert.equal(environment.binarySHA256, "b8a11fedf24b2dfb59a70c9e52b030f9a508dcd49cd2dd0d41956f4c785156b8");
else assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "daemon-start", "ordinary", "relocate", "slow-release", "slow-timeout", "mcp-disconnect", "daemon-stop"]);

const daemon = one("daemon.ready").pid;
const outcome = (prefix) => one(`${prefix}.outcome`);
const view = (scenario, label) => one("dashpot.view", (record) => record.scenario === scenario && record.label === label);
const lock = (scenario, label) => one("lock", (record) => record.scenario === scenario && record.label === label).state;
const loadedAt = (scenario, label) => one("loaded.snapshot", (record) => record.scenario === scenario && record.label === label).ids;
const runsOf = (scenario, label) => view(scenario, label).agentRuns.map((run) => ({ issue: run.issueId ?? null, state: run.state, host: run.processOrSession,
  at: run.workingDirectory ?? run.observationTarget ?? null, startedAt: run.startedAt ?? null, orphaned: run.orphaned ?? null }));
// Codex's log database keeps a bounded number of rows, so the run snapshots
// each scenario's lines when it ends; the final snapshot adds the rest.
const log = [...new Map([...records.filter((record) => record.kind.endsWith(".outcome")).flatMap((record) => record.log ?? []), ...one("codex.log").entries]
  .map((entry) => [entry.id, entry])).values()].sort((a, b) => a.id - b.id);
const logFor = (thread, text) => log.filter((entry) => entry.message.includes(thread) && entry.message.includes(text));
// The start of the daemon's idle unload: its idle-shutdown log line, within
// 1 s of which it publishes the thread's SessionEnd. Codex writes its log in
// batches and can lose the last batch at daemon stop, so where the line was
// not kept the SessionEnd stands for it.
let loggedUnloads = 0;
const trigger = (thread) => {
  const end = hooks.find((record) => record.event === "SessionEnd" && record.payload.session_id === thread);
  assert(end, `SessionEnd for ${thread}`);
  assert.equal(end.ancestry[0].pid, daemon, "the daemon published it");
  const found = logFor(thread, "has no subscribers and is idle; shutting down");
  assert(found.length <= 1);
  if (found.length) {
    loggedUnloads += 1;
    assert.equal(found[0].pid, daemon, "the daemon unloaded it");
    assert(Math.abs(end.receiptTime - found[0].atMs) <= 1000, "SessionEnd within 1 s of the idle-shutdown line");
  }
  return found.length ? found[0].atMs : end.receiptTime;
};
const closedAt = (thread) => {
  const found = of("notification").filter((record) => record.method === "thread/closed" && record.thread === thread);
  assert(found.length >= 1, `thread/closed for ${thread}`);
  return found[0];
};
const sessionHooks = (session) => hooks.filter((record) => record.payload.session_id === session);
const hostOf = (record) => record.ancestry?.[0]?.pid ?? null;
const events = (scenario) => one("dashpot.events", (record) => record.scenario === scenario).events.filter((event) => event["event.name"] !== "process.end");
const outcomes = (scenario) => events(scenario).map((event) => [event["dashpot.process.kind"], event["dashpot.work_store.change"] ?? event["dashpot.outcome.action"] ?? null]);
const probe = (name) => one("model.request", (record) => record.probe?.label === name).probe;
const writes = (found) => Object.fromEntries(found.writes.map(([target, result]) => [
  target.includes("/issue-a/") ? "issue-a" : target.includes("/issue-b/") ? "issue-b" : target.includes("/outside/") ? "outside" : "main", result.ok ? "ok" : result.code]));
const lastTurn = (prefix) => outcome(prefix).turns.at(-1);

check("Every scenario finished, every wait was met, every hook reached Dashpot's real publisher and exited 0, no fixture process outlived the run, and the fixture daemon left nothing in the shared daemon directory", () => {
  assert(of("scenario.end").every((record) => record.ok));
  assert(of("wait").every((record) => record.met), "every wait met");
  assert(hooks.length > 0);
  for (const record of hooks) assert.equal(record.publisher.status, 0, `${record.event} publisher status`);
  assert.deepEqual(one("cleanup.remaining").pids, []);
  const shared = one("shared-daemon-dir");
  assert.equal(shared.ownBound, true);
  assert.equal(shared.ownBefore, 0);
  assert.equal(shared.ownLeft, 0);
  assert.equal(one("daemon.ready").sharedSocket, true, "the daemon's socket is in the shared directory");
});

const first = (prefix) => outcome(prefix).turns[0];
check("Every first turn ran in Issue Worktree A on the managed daemon with Codex's default sandbox: workspace-write, the network off, no extra writable root; its shell could write only in A and could not connect to loopback", () => {
  for (const prefix of ["or", "rl", "sr", "so"]) {
    const { session } = outcome(prefix);
    const start = sessionHooks(session).find((record) => record.event === "SessionStart");
    assert.equal(start.payload.source, "startup");
    assert.equal(hostOf(start), daemon, `${prefix} first session hosted by the daemon`);
    assert.equal(first(prefix).cwd, ISSUE_A);
    assert.equal(first(prefix).sandboxPolicy.type, "workspace-write");
    assert.equal(first(prefix).sandboxPolicy.network_access, false);
    assert.equal(first(prefix).sandboxPolicy.writable_roots, undefined);
    const found = probe(`${prefix}-first.0`);
    assert.equal(found.cwd, ISSUE_A);
    assert.deepEqual(writes(found), { main: "EROFS", "issue-a": "ok", "issue-b": "EROFS", outside: "EROFS" });
    assert.deepEqual(found.network, { ok: false, code: "EPERM" });
  }
});

check("Idle unload: for each session the daemon began the idle unload, logging it and publishing SessionEnd, 59 to 62 s after its last terminal exited, and the auxiliary ephemeral thread each turn starts closed 59 to 62 s after it started", () => {
  for (const prefix of ["or", "rl", "sr", "so"]) {
    const found = outcome(prefix);
    interval(`${prefix} idle unload after exit`, trigger(found.session) - found.exitedAt, 59000, 62000);
  }
  const ephemeral = of("notification").filter((record) => record.method === "thread/started" && record.ephemeral === true);
  assert(ephemeral.length >= 5, "an ephemeral thread per turn");
  for (const started of ephemeral) {
    const closed = of("notification").find((record) => record.method === "thread/closed" && record.thread === started.thread);
    if (!closed) continue;
    assert(closed.at - started.at >= 59000 && closed.at - started.at <= 62000, `ephemeral thread closed ${closed.at - started.at} ms after it started`);
    assert.equal(sessionHooks(started.thread).length, 0, "the ephemeral thread runs no hook");
  }
  assert(requests.filter((record) => ephemeral.some((started) => started.thread === record.thread)).every((record) => record.missing && record.step === 0),
    "an ephemeral thread's request was offered no exec_command");
});

check("A prompt-free unload: the daemon's SessionEnd and thread/closed follow the idle shutdown within 1 s, the thread leaves thread/loaded/list, and its writer lock file is gone at thread/closed", () => {
  for (const prefix of ["or", "rl"]) {
    const { session } = outcome(prefix);
    const at = trigger(session);
    const end = sessionHooks(session).find((record) => record.event === "SessionEnd");
    assert.equal(hostOf(end), daemon);
    assert.equal(end.payload.cwd, ISSUE_A);
    const closed = closedAt(session);
    interval(`${prefix} thread/closed after idle shutdown`, closed.at - at, 0, 1000);
    assert(end.receiptTime <= closed.receiptTime, "SessionEnd before thread/closed");
    assert.equal(closed.lock, "absent");
    assert.equal(lock(prefix, "before-exit"), "held");
    assert.equal(lock(prefix, "after-exit"), "held");
    assert(loadedAt(prefix, "after-exit").includes(session));
    assert(!loadedAt(prefix, "after-resume").includes(session), "the resumed thread is not the daemon's");
  }
});

// The resume command the execute-issues skill gives a Lead, with its options.
const resumed = (prefix) => one("resume.started", (record) => record.label === `${prefix}-resume`);
const resumeStart = (prefix) => sessionHooks(outcome(prefix).session).find((record) => record.event === "SessionStart" && record.payload.source === "resume");
check("Resume within the unload window: a `codex resume <id> -C <worktree>` with sandbox, writable-root and network options runs in its own process, which Codex refuses as long as the daemon holds the thread (`already has an active writer`), showing the read-only transcript; a retry after thread/closed resumes it, without sending the prompt from its command line", () => {
  for (const prefix of ["or", "rl"]) {
    const { session } = outcome(prefix);
    const started = resumed(prefix);
    assert.equal(started.met, true);
    assert(started.conflicts >= 1);
    const refusals = logFor(session, "already has an active writer");
    assert(refusals.length >= 2, `${prefix} refusals logged`);
    const resumer = refusals[0].pid;
    assert.notEqual(resumer, daemon);
    const closed = closedAt(session).at;
    assert(refusals.every((entry) => entry.pid === resumer && entry.atMs < closed + 1000), "every refusal came from the resuming client before the thread closed");
    const start = resumeStart(prefix);
    assert.equal(hostOf(start), resumer, "the resumed session runs in the resuming client");
    assert(start.receiptTime > closed);
    assert.equal(started.typed, true, "the retried client did not send its command-line prompt");
    interval(`${prefix} resumed SessionStart after thread/closed`, start.receiptTime - closed, 0, 15000);
  }
});

const granted = (turn, cwd) => {
  assert.equal(turn.cwd, cwd);
  assert.equal(turn.sandboxPolicy.type, "workspace-write");
  assert.deepEqual(turn.sandboxPolicy.writable_roots, ROOTS);
  assert.equal(turn.sandboxPolicy.network_access, true);
};
check("The resumed turn runs where `-C` names with the resume's grants: the Worktrees directory and the main checkout's `.git` writable, and the network on", () => {
  granted(lastTurn("or"), ISSUE_A);
  granted(lastTurn("rl"), ISSUE_B);
  for (const [name, cwd] of [["or-resume.0", ISSUE_A], ["rl-resume.0", ISSUE_B]]) {
    const found = probe(name);
    assert.equal(found.cwd, cwd);
    assert.deepEqual(writes(found), { main: "EROFS", "issue-a": "ok", "issue-b": "ok", outside: "EROFS" });
    assert.deepEqual(found.network, { ok: true });
  }
});

check("ordinary: the bound run does not survive an exit and immediate resume at the same Worktree. The daemon's SessionEnd defers the run's end, the resumed SessionStart leaves it under the daemon, and the settler ends it about 10 s after the SessionEnd, as the daemon is still live; the resumed session is then unbound", () => {
  const { session } = outcome("or");
  assert.equal(probe("or-first.0").work.status, 0);
  assert.deepEqual(runsOf("or", "after-start").map((run) => [run.issue, run.host]), [["I_fixture_1", `codex pid ${daemon}`]]);
  assert.deepEqual(runsOf("or", "after-unload").map((run) => [run.issue, run.state, run.host]), [["I_fixture_1", "unknown", `codex pid ${daemon}`]]);
  assert.deepEqual(outcomes("or").filter(([kind]) => kind.startsWith("hook:codex:Session")), [
    ["hook:codex:SessionStart", "unchanged"], ["hook:codex:SessionEnd", "deferred"], ["hook:codex:SessionStart", "unchanged"], ["hook:codex:SessionEnd", "ended"],
    ["hook:codex:SessionEnd", "unchanged"]]);
  const settled = events("or").find((event) => event["dashpot.hook.event"] === "SessionEnd" && event["dashpot.work_store.change"] === "ended");
  const deferred = events("or").find((event) => event["dashpot.work_store.change"] === "deferred");
  interval("or settler end after the daemon's SessionEnd", Date.parse(settled.time) - Date.parse(deferred.time), 9500, 12000);
  for (const label of ["after-resume-settle", "after-resumed-exit"]) assert(runsOf("or", label).every((run) => run.issue === null), `${label}: no bound run`);
  assert(runsOf("or", "after-resume-settle").some((run) => run.host === `${session} hook`));
});

check("relocate: with `work relocate` to Issue Worktree B declared before exit, the daemon's SessionEnd at A leaves the run pending, the resumed SessionStart at B relocates the same run (same Issue, same startedAt) to the resuming client, and `work show` there reports it; the run ends at that client's own SessionEnd", () => {
  const { session } = outcome("rl");
  assert.equal(probe("rl-declare.0").work.status, 0);
  assert.match(probe("rl-declare.0").work.stdout, /prepared this Agent Run to resume at \$ROOT\/repository\.worktrees\/issue-b/);
  assert.match(probe("rl-declare.1").work.stdout, /relocation pending to \$ROOT\/repository\.worktrees\/issue-b/);
  const before = runsOf("rl", "after-declare");
  assert.deepEqual(before.map((run) => [run.issue, run.host]), [["I_fixture_2", `codex pid ${daemon}`]]);
  assert(view("rl", "after-declare").diagnostics.some((found) => found.code === "work-relocation-pending"));
  assert(view("rl", "after-unload").diagnostics.some((found) => found.code === "work-relocation-pending"));
  const resumer = hostOf(resumeStart("rl"));
  for (const label of ["after-unload-settle", "after-resume", "after-resume-settle"]) {
    const runs = runsOf("rl", label);
    assert.deepEqual(runs.map((run) => [run.issue, run.host, run.at, run.startedAt]), [["I_fixture_2", `codex pid ${resumer}`, ISSUE_B, before[0].startedAt]], label);
    assert.equal(view("rl", label).diagnostics.length, 0);
  }
  assert.match(probe("rl-resume.0").work.stdout, new RegExp(`^codex pid ${resumer}: fixture-2 \\(I_fixture_2\\)`));
  assert.deepEqual(outcomes("rl").filter(([kind]) => kind.startsWith("hook:codex:Session") || kind.startsWith("command:")), [
    ["hook:codex:SessionStart", "unchanged"], ["command:work-start", "started"], ["command:work-relocate", "relocation-prepared"], ["hook:codex:SessionEnd", "unchanged"],
    ["hook:codex:SessionStart", "relocated"], ["hook:codex:SessionEnd", "ended"]]);
  assert.deepEqual(runsOf("rl", "after-resumed-exit"), []);
  const order = sessionHooks(session).map((record) => [record.event, record.payload.cwd === ISSUE_A ? "A" : record.payload.cwd === ISSUE_B ? "B" : record.payload.cwd, hostOf(record) === daemon ? "daemon" : "client"]);
  assert.deepEqual(order, [["SessionStart", "A", "daemon"], ["UserPromptSubmit", "A", "daemon"], ["Stop", "A", "daemon"], ["UserPromptSubmit", "A", "daemon"], ["Stop", "A", "daemon"],
    ["SessionEnd", "A", "daemon"], ["SessionStart", "B", "client"], ["UserPromptSubmit", "B", "client"], ["Stop", "B", "client"], ["SessionEnd", "B", "client"]]);
});

const holdOf = (prefix) => outcome(prefix);
check("Slow cleanup: with the writer coordination lock held by another process, the daemon still starts the idle unload on time and publishes SessionEnd at once, logs `thread_shutdown_slow` 10 s later, keeps the thread loaded with its writer lock held, and refuses a daemon `thread/resume` with `-32600` `is closing; retry thread/resume after the thread is closed`", () => {
  for (const prefix of ["sr", "so"]) {
    const found = holdOf(prefix);
    const at = trigger(found.session);
    assert(found.holdAcquiredAt < at, "the hold began before the unload");
    assert.equal(logFor(found.session, "has no subscribers and is idle").length, 1, "the idle-shutdown line was kept");
    const slow = logFor(found.session, "shutdown is taking longer than expected; continuing to wait");
    assert.equal(slow.length, 1);
    assert.match(slow[0].message, /codex\.app_server\.thread_shutdown_slow/);
    interval(`${prefix} slow-shutdown warning after idle shutdown`, slow[0].atMs - at, 9500, 11000);
    assert.equal(lock(prefix, "during-cleanup"), "held");
    assert.equal(lock(prefix, "during-cleanup-settle"), "held");
    assert(loadedAt(prefix, "during-cleanup").includes(found.session));
    const attempt = one("resume.attempt", (record) => record.scenario === prefix && record.phase === "during-cleanup");
    assert.equal(attempt.error.code, -32600);
    assert.equal(attempt.error.message, `thread ${found.session} is closing; retry thread/resume after the thread is closed`);
  }
});

check("slow-release: released 80 s after the exit, about 20 s into the cleanup, the daemon finishes it: thread/closed within 1 s of the release, the writer lock file removed, the thread gone from thread/loaded/list", () => {
  const found = holdOf("sr");
  const at = trigger(found.session);
  const closed = closedAt(found.session);
  interval("sr thread/closed after release", closed.at - found.holdReleasedAt, 0, 1000);
  interval("sr cleanup (idle shutdown to thread/closed)", closed.at - at, 15000, 25000);
  assert.equal(closed.lock, "absent");
  assert.equal(lock("sr", "after-release"), "absent");
  assert(!loadedAt("sr", "after-release").includes(found.session));
  assert.equal(logFor(found.session, "failed to coordinate thread writer lock cleanup").length, 0);
});

check("slow-timeout: held past Codex's 30 s wait for the coordination lock, the cleanup ends without it: the daemon logs `failed to coordinate thread writer lock cleanup`, sends thread/closed about 30 s after the idle shutdown while the hold continues, and leaves the thread's lock file in place, unlocked", () => {
  const found = holdOf("so");
  const at = trigger(found.session);
  const closed = closedAt(found.session);
  assert(closed.at < found.holdReleasedAt, "closed while the hold continued");
  interval("so thread/closed after idle shutdown", closed.at - at, 29000, 33000);
  // Codex's warning names no thread: the only one in this cleanup's window.
  const failed = log.filter((entry) => entry.message.includes("failed to coordinate thread writer lock cleanup") && entry.atMs >= at && entry.atMs <= closed.at + 1000);
  assert.equal(failed.length, 1);
  assert.equal(failed[0].pid, daemon);
  assert.equal(closed.lock, "free");
  assert.equal(lock("so", "closed-while-held"), "free");
  assert(!loadedAt("so", "closed-while-held").includes(found.session));
  assert.equal(lock("so", "after-release"), "free");
});

check("After either slow cleanup, `codex exec resume` with the grants resumes the same session in Worktree A, with the grants in force; Dashpot ended the bound run at the settler, about 10 s after the SessionEnd, while Codex still held the thread", () => {
  for (const [prefix, issue] of [["sr", "I_fixture_1"], ["so", "I_fixture_2"]]) {
    const found = holdOf(prefix);
    const attempt = one("resume.attempt", (record) => record.scenario === prefix && record.phase === "after-close");
    assert.equal(attempt.status, 0);
    const start = sessionHooks(found.session).filter((record) => record.event === "SessionStart");
    assert.deepEqual(start.map((record) => record.payload.source), ["startup", "resume"]);
    assert.notEqual(hostOf(start[1]), daemon);
    granted(lastTurn(prefix), ISSUE_A);
    assert.deepEqual(writes(probe(`${prefix}-exec.0`)), { main: "EROFS", "issue-a": "ok", "issue-b": "ok", outside: "EROFS" });
    assert.deepEqual(probe(`${prefix}-exec.0`).network, { ok: true });
    assert.deepEqual(runsOf(prefix, "after-unload").map((run) => [run.issue, run.state]), [[issue, "unknown"]]);
    assert.deepEqual(runsOf(prefix, "during-cleanup-settle"), [], "the run ended while the thread was still loaded");
    assert.match(probe(`${prefix}-exec.0`).work.stdout, /no active Issue work|not working on|no Agent Run/i);
    assert.deepEqual(outcomes(prefix).filter(([kind]) => kind.startsWith("hook:codex:Session")), [
      ["hook:codex:SessionStart", "unchanged"], ["hook:codex:SessionEnd", "deferred"], ["hook:codex:SessionEnd", "ended"], ["hook:codex:SessionStart", "unchanged"], ["hook:codex:SessionEnd", "unchanged"]]);
    const settled = events(prefix).find((event) => event["dashpot.work_store.change"] === "ended");
    const deferred = events(prefix).find((event) => event["dashpot.work_store.change"] === "deferred");
    interval(`${prefix} settler end after the daemon's SessionEnd`, Date.parse(settled.time) - Date.parse(deferred.time), 9500, 12000);
    assert(Date.parse(settled.time) < closedAt(found.session).at, "the run ended before Codex closed the thread");
  }
});

check("mcp-disconnect: a controller's `thread/start` whose required MCP server blocks in initialize registers no thread while blocked; after the controller disconnects and the server answers, the thread starts with no subscriber, is unloaded 59 to 62 s later with SessionEnd and thread/closed, its MCP server is stopped as it shuts down, its writer lock removed, and a later `thread/resume` succeeds", () => {
  const found = outcome("md");
  const events_ = Object.fromEntries(found.mcp.map((entry) => [entry.event, entry]));
  assert(events_["initialize-received"].at < found.disconnectedAt);
  assert(found.disconnectedAt < events_["gate-open"].at);
  assert.deepEqual(loadedAt("md", "startup-blocked"), []);
  assert.deepEqual(loadedAt("md", "after-disconnect"), []);
  const started = one("notification", (record) => record.method === "thread/started" && record.thread === found.thread);
  assert(started.at >= found.openedAt);
  assert.equal(lock("md", "loaded"), "held");
  assert(loadedAt("md", "after-startup").includes(found.thread));
  const at = trigger(found.thread);
  interval("md idle unload after thread start", at - started.at, 59000, 62000);
  const closed = closedAt(found.thread);
  assert.equal(closed.lock, "absent");
  // Codex closes the server's stdin and stops it; which the server sees
  // first varies between runs.
  const ended = events_["stdin-end"] ?? events_.signal;
  assert(ended, "the MCP server was stopped");
  assert(ended.at >= at - 1000 && ended.at <= closed.at + 1000, "while the thread shut down");
  assert.equal(found.mcpAlive, false);
  const ends = sessionHooks(found.thread);
  assert.equal(ends[0].event, "SessionEnd");
  assert.equal(hostOf(ends[0]), daemon);
  assert(!ends.some((record) => record.event === "SessionStart"), "a thread with no turn has no SessionStart");
  const attempt = one("resume.attempt", (record) => record.scenario === "md");
  assert.equal(attempt.error, null);
  assert.equal(attempt.result.id, found.thread);
  assert.equal(attempt.result.cwd, ISSUE_A);
  assert.equal(attempt.result.turns, 0);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Intervals: ${intervals.join("; ")}; idle-shutdown log lines kept for ${loggedUnloads} of the unloads checked`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
