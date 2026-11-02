// Independent verifier for the Codex 681 root-session departure trace.
// Checks the recorded model requests, sandboxed probes, hooks, controller
// replies and Dashpot's Cleanup checks against the claims the spike makes
// for the pinned release, without importing the runner or Dashpot.
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
const observation = (scenario, label) => one("observe", (record) => record.scenario === scenario && record.label === label);
const blockers = (scenario, label) => observation(scenario, label).checks.issue.blockers;
const probe = (name) => one("model.request", (record) => record.probe?.label === name).probe;
const MAIN = "$ROOT/repository";
const ISSUE = "$ROOT/repository.worktrees/issue";
const writable = (found) => Object.fromEntries(found.writes.map(([target, result]) => [target.includes("/repository.worktrees/issue/") ? "issue" : "main", result.ok ? "ok" : result.code]));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

// The trace names the exact sources that produced it.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["run.mjs", "hook.mjs", "probe.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["sessions/hook_publish.py", "sessions/hook_records.py", "sessions/hook_scan.py", "sessions/working_directories.py", "repository/cleanup/obstacles.py"]
  .map((file) => `src/dashpot/${file}`);
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
assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "cd-standalone", "daemon-start", "cd-daemon", "cd-inside", "settings-daemon", "daemon-stop"]);

const sessions = new Set(hooks.map((record) => record.payload.session_id));
const rootRequests = requests.filter((record) => sessions.has(record.thread));
const sideRequests = requests.filter((record) => !sessions.has(record.thread));

check("Every scenario finished, every wait was met, every hook reached Dashpot's real publisher and exited 0, no fixture process outlived the run, and the shared daemon directory was left as it was", () => {
  assert(of("scenario.end").every((record) => record.ok));
  assert(of("wait").every((record) => record.met), "every wait met");
  assert(hooks.length > 0);
  for (const record of hooks) assert.equal(record.publisher.status, 0, `${record.event} publisher status`);
  assert.deepEqual(one("cleanup.remaining").pids, []);
  const shared = one("shared-daemon-dir");
  assert.equal(shared.added, 0);
  assert.equal(shared.removed, 0);
});

const ROOT_TOOLS = ["apply_patch", "create_goal", "exec_command", "get_goal", "list_mcp_resource_templates", "list_mcp_resources", "read_mcp_resource",
  "request_user_input", "tool_search", "update_goal", "view_image", "web_search", "write_stdin"];
check("Every root session was offered the same thirteen tools, none of which moves the session; the planned exec_command was always offered to it", () => {
  const offered = rootRequests.filter((record) => record.tools);
  assert(offered.length >= 4, "the tools were recorded for each root session");
  for (const record of offered) assert.deepEqual(record.tools, ROOT_TOOLS);
  assert(rootRequests.every((record) => !record.missing));
});

check("Each user turn also made one auxiliary request on a thread with no hooks, offered apply_patch alone", () => {
  assert(sideRequests.length > 0);
  for (const record of sideRequests) {
    assert.equal(record.step, 0);
    if (record.tools) assert.deepEqual(record.tools, ["apply_patch"]);
  }
  const turns = rootRequests.filter((record) => record.step === 0).length;
  assert.equal(sideRequests.length, turns);
});

check("No sandboxed command could reach the app-server: the control socket was not visible and connect failed with EPERM, the shared daemon directory was not readable, and seccomp was in filter mode, in every scenario, daemon running or not", () => {
  const probes = requests.filter((record) => record.probe).map((record) => record.probe);
  assert.equal(probes.length, 11);
  for (const found of probes) {
    assert.deepEqual(found.controlSocket, { exists: false, connect: { ok: false, code: "EPERM" } }, found.label);
    assert.deepEqual(found.sharedDaemonDirectory, { read: { ok: false, code: "EACCES" } }, found.label);
    assert.equal(found.seccomp, "2");
  }
});

for (const [p, scenario, inside] of [["cs", "cd-standalone", false], ["cd", "cd-daemon", false], ["ci", "cd-inside", true]]) {
  const outcome = one(`${p}.outcome`);
  const cdAt = one("terminal.type", (record) => record.text === `/cd ${MAIN}` && record.receipt > one("scenario", (found) => found.name === scenario).receipt
    && record.receipt < one("scenario.end", (found) => found.name === scenario).receipt);
  const oldEnd = one("hook", (record) => record.event === "SessionEnd" && record.payload.session_id === outcome.session);
  check(`${scenario}: /cd forks to a new session at the destination, carrying the history, and moves the writable root with it`, () => {
    assert.notEqual(outcome.forked, null);
    assert.notEqual(outcome.forked, outcome.session);
    const start = one("hook", (record) => record.event === "SessionStart" && record.payload.session_id === outcome.forked);
    assert.equal(start.payload.source, "fork");
    assert.equal(start.payload.cwd, MAIN);
    assert.deepEqual(outcome.afterLabels, [`${p}-first`, `${p}-after`]);
    assert.equal(probe(`${p}-first.0`).thread, outcome.session);
    assert.equal(probe(`${p}-first.0`).cwd, ISSUE);
    assert.deepEqual(writable(probe(`${p}-first.0`)), { main: "EROFS", issue: "ok" });
    assert.equal(probe(`${p}-after.0`).thread, outcome.forked);
    assert.equal(probe(`${p}-after.0`).cwd, MAIN);
    assert.deepEqual(writable(probe(`${p}-after.0`)), { main: "ok", issue: "EROFS" });
  });
  check(`${scenario}: the old session stays live in the Issue Worktree after /cd and ends with SessionEnd (reason other) about a minute later`, () => {
    assert.equal(oldEnd.payload.reason, "other");
    assert.equal(oldEnd.payload.cwd, ISSUE);
    const seconds = (oldEnd.receiptTime - cdAt.receiptTime) / 1000;
    assert(seconds > 45 && seconds < 90, `old SessionEnd ${seconds}s after /cd`);
    const before = blockers(p, "after-cd-turn").filter((found) => found.kind === "agent-session");
    assert.deepEqual(before.map((found) => [found.session, found.live]), [[outcome.session, true]]);
    assert.deepEqual(blockers(p, "after-old-end").filter((found) => found.kind === "agent-session"), []);
  });
  if (!inside) {
    check(`${scenario}: started outside the Worktree, the client leaves it removable once the old session ends`, () => {
      assert.equal(one("terminal.start", (record) => record.name === p).cwd, "$ROOT");
      assert.equal(observation(p, "after-old-end").checks.issue.removable, true);
      assert.deepEqual(blockers(p, "after-old-end"), []);
    });
  } else {
    check(`${scenario}: started inside the Worktree, the terminal and the Codex client keep a process blocker after /cd and after the old session ends, until the client exits`, () => {
      assert.equal(one("terminal.start", (record) => record.name === p).cwd, ISSUE);
      for (const label of ["before-cd", "after-cd-turn", "after-old-end"]) {
        const process = blockers(p, label).filter((found) => found.kind === "process");
        assert.equal(process.length, 1, label);
        assert(process[0].processes.includes("codex"), `${label} names the Codex client`);
      }
      assert.equal(observation(p, "after-old-end").checks.issue.removable, false);
      assert.equal(observation(p, "after-exit").checks.issue.removable, true);
    });
  }
}

check("A daemon-hosted fork ends about a minute after its client exits; a standalone one ends with its client", () => {
  for (const [p, low, high] of [["cs", 0, 10], ["cd", 45, 90], ["ci", 45, 90]]) {
    const outcome = one(`${p}.outcome`);
    const exited = one("terminal.exit", (record) => record.name === p);
    const end = one("hook", (record) => record.event === "SessionEnd" && record.payload.session_id === outcome.forked);
    const seconds = (end.receiptTime - exited.receiptTime) / 1000;
    assert(seconds >= low - 2 && seconds < high, `${p} fork SessionEnd ${seconds}s after exit`);
  }
});

const st = one("st.outcome");
const updates = of("settings.update");
check("settings-daemon: a controller's thread/settings/update cwd on the idle thread is accepted, keeps the thread id, and moves the next turn, its sandbox and its writable root to the new directory", () => {
  const idle = updates.find((record) => record.phase === "idle");
  assert.equal(idle.error, null);
  assert.deepEqual(idle.result, {});
  assert.equal(idle.before.cwd, ISSUE);
  assert.deepEqual([idle.after.id, idle.after.cwd, idle.after.forkedFrom], [st.session, MAIN, null]);
  assert.equal(st.afterSession, st.session);
  assert.deepEqual(writable(probe("st-after.0")), { main: "ok", issue: "EROFS" });
  assert.equal(probe("st-after.0").cwd, MAIN);
  assert.equal(probe("st-after.0").thread, st.session);
  const starts = hooks.filter((record) => record.event === "SessionStart" && record.payload.session_id === st.session);
  assert.equal(starts.length, 1, "no second SessionStart");
  const prompts = hooks.filter((record) => record.event === "UserPromptSubmit" && record.payload.session_id === st.session).map((record) => record.payload.cwd);
  assert.deepEqual(prompts, [ISSUE, MAIN, MAIN, ISSUE]);
});

check("settings-daemon: the update alone leaves the Worktree occupied; after the next turn ends at the new directory, Dashpot reads the Issue Worktree removable", () => {
  assert.deepEqual(blockers("st", "after-update").map((found) => [found.kind, found.session]), [["agent-session", st.session]]);
  assert.equal(observation("st", "after-update-turn").checks.issue.removable, true);
});

check("settings-daemon: sent while a command of a turn runs, the update is accepted, but the rest of that turn keeps the old directory and permissions; it applies from the next turn", () => {
  const running = updates.find((record) => record.phase === "running");
  assert.equal(running.error, null);
  assert.deepEqual(running.result, {});
  assert.equal(running.during.status, "active");
  for (const name of ["st-mid.0", "st-mid.1"]) {
    assert.equal(probe(name).cwd, MAIN, name);
    assert.deepEqual(writable(probe(name)), { main: "ok", issue: "EROFS" }, name);
  }
  assert.equal(probe("st-next.0").cwd, ISSUE);
  assert.deepEqual(writable(probe("st-next.0")), { main: "EROFS", issue: "ok" });
  assert.equal(st.nextSession, st.session);
  assert.deepEqual(blockers("st", "after-next-turn").map((found) => [found.kind, found.session]), [["agent-session", st.session]]);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
