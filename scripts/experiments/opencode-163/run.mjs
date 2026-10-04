// Real-harness acceptance run for OpenCode v2, re-pinned to 2.0.22 by Issue
// #407 (ADR 0090), first written for 1.18.30 by Issue #163. It drives a pinned
// OpenCode release against a loopback OpenAI-compatible model fixture, in
// disposable configuration and state, with the background service on a
// private port, so the operator's own OpenCode service is never contacted.
// Dashpot is built from this checkout and installed into a fixture
// environment, and `dashpot integrate opencode` from that installation writes
// the plugin and skill the run exercises, so the plugin and helper are
// exactly what an installation runs. The sessions' shells run that
// installation's `dashpot work` commands, as the Issue-work skill does.
// Between steps the runner records what `dashpot --json` and
// `dashpot worktree check` observe, the hook and Publisher Records, and
// OpenCode's own session events. The trace is metadata only; the runner
// asserts only what it needs to keep going, and the independent verifier
// checks the trace against the documented claims.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <opencode 2.0.22> <opencode 2.0.21> <opencode 1.18.30> > log 2>&1
// Each binary is an absolute path. It is done when it prints "All scenarios
// completed". SPIKE_REMOVE_FIXTURE=1 deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import {
  appendFileSync, chmodSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, renameSync,
  rmSync, symlinkSync, writeFileSync,
} from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, inFixture } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
// A harness above the runner would be an ancestor of every client the run
// starts, and the Host Process Dashpot finds for a process it does not
// recognise, so the runner refuses to start below one; `setsid -f` detaches it.
const above = [];
for (let pid = process.ppid; pid > 1 && above.length < 64;) { try { const entry = describe(pid); above.push(entry); pid = entry.ppid; } catch { break; } }
const host = above.find((entry) => /^(claude|codex|opencode|opencode2|opencode\.exe)$/.test(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const [binary, olderBinary, v1Binary] = process.argv.slice(2);
for (const [given, what] of [[binary, "OpenCode 2.0.22"], [olderBinary, "an older OpenCode 2.0.x"], [v1Binary, "OpenCode 1.18.30"]]) {
  assert(given && path.isAbsolute(given), `Pass the absolute path to the ${what} binary`);
}
const uv = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-407-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree and three linked Worktrees; a second
// Project's Repository; and a directory in no Repository at all.
const fixture = path.join(root, "repository");
const treeA = path.join(root, "repository.worktrees", "a");
const treeB = path.join(root, "repository.worktrees", "b");
const treeC = path.join(root, "repository.worktrees", "c");
const other = path.join(root, "other");
const plain = path.join(root, "plain");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, the binaries'
// directories, this directory, the checkout, and the operator's home by
// placeholder.
const retained = (text) => text.replaceAll(path.dirname(binary), "$BINARY_DIR").replaceAll(path.dirname(olderBinary), "$OLDER_BINARY_DIR")
  .replaceAll(path.dirname(v1Binary), "$V1_BINARY_DIR").replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR")
  .replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const sha256 = (file) => !existsSync(file) ? null : createHash("sha256").update(readFileSync(file)).digest("hex");

// Dashpot, built from this checkout and installed outside every Worktree, as
// a person's installation is; its helper is what the plugin is bound to.
const venv = path.join(root, "venv");
execFileSync(uv, ["build", "-q", "--wheel", "-o", path.join(root, "dist"), checkout], { stdio: "pipe" });
const [wheel] = readdirSync(path.join(root, "dist")).filter((name) => name.endsWith(".whl"));
execFileSync(uv, ["venv", "-q", "--python", path.join(checkout, ".venv", "bin", "python"), venv], { stdio: "pipe" });
execFileSync(uv, ["pip", "install", "-q", "--offline", "--python", path.join(venv, "bin", "python"), path.join(root, "dist", wheel)], { stdio: "pipe" });
const dashpot = path.join(venv, "bin", "dashpot");
const helper = path.join(venv, "bin", "dashpot-opencode-hook");
const installed = execFileSync(path.join(venv, "bin", "python"), ["-c", "import dashpot, os; print(os.path.dirname(dashpot.__file__))"], { encoding: "utf8" }).trim();
// The Dashpot sources the run exercises; the installed copies must be them.
const exercised = ["plugins/opencode.js", "sessions/opencode_publish.py", "sessions/opencode_publishers.py", "sessions/hook_claims.py",
  "sessions/hook_scan.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/harnesses.py", "sessions/work.py",
  "sessions/integrate.py", "sessions/session_exits.py", "repository/cleanup/obstacles.py", "hook.py"];

const env = {
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  SHELL: "/bin/bash",
  LANG: "C.UTF-8",
  OPENCODE_DISABLE_AUTOUPDATE: "1",
  OPENCODE_DISABLE_MODELS_FETCH: "1",
  OPENCODE_DISABLE_PROJECT_CONFIG: "1",
  // Nothing but loopback is reachable: a model OpenCode chose over the
  // fixture's would otherwise be a hosted one.
  HTTP_PROXY: "http://127.0.0.1:9", HTTPS_PROXY: "http://127.0.0.1:9", http_proxy: "http://127.0.0.1:9", https_proxy: "http://127.0.0.1:9",
  NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
  // Sessions outside a configured checkout would publish here.
  DASHPOT_STATE_DIR: path.join(root, "dashpot-state"),
  // Ancestry walks from shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_HELPER: helper,
};
// OpenCode installed as its curl installer does, at ~/.opencode/bin/opencode;
// the older 2.0.x and 1.18.30 releases in directories of their own; and the
// npm package's layout, the binary linked to `bin/opencode.exe` in the
// package, with npm's `opencode` link to it.
const curlBin = path.join(env.HOME, ".opencode", "bin");
const olderBin = path.join(root, "older", "bin");
const v1Bin = path.join(root, "v1", "bin");
const npmPackageBin = path.join(root, "npm", "lib", "node_modules", "@opencode", "cli", "bin");
const npmBin = path.join(root, "npm", "bin");
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
for (const dir of [fixture, other, plain, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, curlBin, olderBin, v1Bin,
  npmPackageBin, npmBin, configHome]) mkdirSync(dir, { recursive: true });
const place = (source, target) => { try { linkSync(source, target); } catch { execFileSync("cp", [source, target]); } chmodSync(target, 0o755); };
place(binary, path.join(curlBin, "opencode"));
place(olderBinary, path.join(olderBin, "opencode"));
place(v1Binary, path.join(v1Bin, "opencode"));
place(binary, path.join(npmPackageBin, "opencode.exe"));
symlinkSync("../lib/node_modules/@opencode/cli/bin/opencode.exe", path.join(npmBin, "opencode"));
const basePath = `${path.dirname(process.execPath)}:/usr/bin:/bin`;
env.PATH = `${curlBin}:${basePath}`;
const versionOf = (bin) => execFileSync(path.join(bin, "opencode"), ["--version"], { env: { ...env, PATH: `${bin}:${basePath}` }, encoding: "utf8" }).trim();
const version = versionOf(curlBin);
assert.equal(version, "opencode v2.0.22", `unexpected OpenCode version: ${version}`);
const olderVersion = versionOf(olderBin);
assert.match(olderVersion, /^opencode v2\.0\.\d+$/);
assert.notEqual(olderVersion, version, "the older binary must be another release");
const v1Version = versionOf(v1Bin);
assert.equal(v1Version, "1.18.30", `unexpected OpenCode v1 version: ${v1Version}`);

// Two Dashpot Projects with markdown Issue Sources: the fixture Repository,
// with one Issue per binding, and another Repository a session moves to.
const project = (directory, name, issues) => {
  mkdirSync(path.join(directory, ".dashpot"), { recursive: true });
  mkdirSync(path.join(directory, "issues"), { recursive: true });
  writeFileSync(path.join(directory, ".dashpot", "config.json"), JSON.stringify({ projectId: `project:${name}`, displayLabel: name,
    repositoryId: `repository:${name}`, issueSource: { kind: "markdown", path: "issues" } }));
  for (let number = 1; number <= issues; number++) {
    const front = { id: `I_${name}_${number}`, number, reference: `issue-${number}`, state: "open", stateReason: null, labels: [], assignees: [],
      author: "fixture", relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
      createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
    writeFileSync(path.join(directory, "issues", `issue-${number}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
  }
  const git = (...args) => execFileSync("git", ["-C", directory, ...args], { env, stdio: "pipe" });
  git("init", "--initial-branch=main");
  git("add", ".");
  git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
  return git;
};
const git = project(fixture, "fixture", 20);
for (const [name, tree] of [["a", treeA], ["b", treeB], ["c", treeC]]) git("worktree", "add", "-b", name, tree);
project(other, "other", 1);
writeFileSync(path.join(plain, "README.md"), "In no Repository.\n");
const worktrees = [fixture, treeA, treeB, treeC, other];

const listen = async (handler) => {
  const server = http.createServer(async (req, res) => {
    try { await handler(req, res); } catch (error) {
      trace("server.error", { path: req.url, error: retained(String(error?.stack ?? error)).slice(0, 1000) });
      if (!res.headersSent) res.writeHead(500);
      res.end();
    }
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return { server, url: `http://127.0.0.1:${server.address().port}` };
};
const body = async (req) => {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
};
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  trace(url.pathname === "/replay" ? "replay" : "command", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `PROBE:<label>` text in the latest user turn selects a
// tool sequence, built when the model is asked so it can name sessions the
// runner learns later, and the turn ends once every step has a tool result.
// A label with no sequence runs one shell command of that name.
const commandScript = path.join(here, "command.mjs");
const replayScript = path.join(here, "replay.mjs");
const known = {};
const shell = (command) => ({ name: "shell", arguments: { command } });
const report = (label, hold = 0) => shell(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => shell(`node ${commandScript} ${label} 0 -- work ${args.join(" ")}`);
const bind = (prefix, issue) => [work(`${prefix}-start`, "start", issue), work(`${prefix}-show`, "show")];
const delegate = (child, background = false) => ({ name: "subagent", arguments: { agent: "general", description: `Fixture ${child}`, prompt: `PROBE:${child}`,
  ...(background ? { background: true } : {}) } });
const moveTo = (directory) => ({ name: "execute", arguments: { code: `return await tools.opencode.session_move({ directory: ${JSON.stringify(directory)} })` } });
const sequences = {
  "tui-bind": () => bind("tui", "issue-1"),
  "a1-bind": () => bind("a1", "issue-2"),
  "a2-bind": () => bind("a2", "issue-3"),
  "b1-bind": () => bind("b1", "issue-4"),
  "a1-hold": () => [report("a1-hold", 6000)],
  "a2-refusals": () => [
    shell(`cd ${treeA} && node ${commandScript} a2-cd-tree-a 0 -- work start issue-5`),
    shell(`env -u OPENCODE_SESSION_ID -u OPENCODE DASHPOT_AGENT_SESSION=opencode:${known.a2} node ${commandScript} a2-explicit 0 -- work start issue-5`),
  ],
  "run-bind": () => bind("run", "issue-6"),
  "a1-switch": () => [work("a1-switch", "start", "issue-7"), work("a1-switched-show", "show")],
  "a2-stop": () => [work("a2-stop", "stop"), work("a2-stopped-show", "show")],
  "tui-resumed-elsewhere": () => [work("tui-resumed-elsewhere-show", "show")],
  "p-bind": () => bind("p", "issue-8"),
  "p-delegate": () => [delegate("child-hold")],
  "child-hold": () => [report("child-hold", 5000), work("child-start", "start", "issue-9")],
  "q-bind": () => bind("q", "issue-10"),
  "q-delegate-background": () => [delegate("bg-child", true)],
  "bg-child": () => [report("bg-child", 8000), work("bg-child-start", "start", "issue-9")],
  "fork-bind": () => [work("fork-unbound-show", "show"), work("fork-start", "start", "issue-11"), work("fork-show", "show")],
  "m-bind": () => bind("m", "issue-12"),
  "m-moved-by-tool": () => [moveTo(treeA), work("m-moved-by-tool-show", "show")],
  "m-moved-by-api": () => [work("m-moved-by-api-show", "show")],
  "m-busy-hold": () => [report("m-busy-hold", 5000), work("m-moved-while-busy-show", "show")],
  "m-back": () => [work("m-back-show", "show")],
  "q-reload-hold": () => [report("q-reload-hold", 8000)],
  "a1-missing-helper": () => [work("a1-missing-helper-show", "show")],
  "a1-stalled-helper": () => [work("a1-stalled-helper-show", "show")],
  "a1-helper-back": () => [work("a1-helper-back-show", "show")],
  "a1-unplugged": () => [work("a1-unplugged-start", "start", "issue-13")],
  "a1-replugged": () => [work("a1-replugged-show", "show")],
  "a1-replay": () => [shell(`node ${replayScript} ${known.a1} ${known.b1} ${treeA} ${plain}`)],
  "a1-on-older": () => [work("a1-on-older-show", "show"), work("a1-on-older-start", "start", "issue-7"), work("a1-on-older-bound-show", "show")],
  "q-resumed": () => [work("q-resumed-show", "show"), work("q-resumed-start", "start", "issue-10")],
  "k-bind": () => bind("k", "issue-14"),
  "sa-run-bind": () => [work("sa-run-start", "start", "issue-15"), report("sa-run-hold", 3000)],
  "sa-tui-bind": () => bind("sa-tui", "issue-16"),
  "npm-bind": () => bind("npm", "issue-17"),
};
const modelRequests = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const lastUser = messages.findLastIndex((message) => message.role === "user");
  const content = JSON.stringify(messages[lastUser]?.content ?? "");
  const label = content.match(/PROBE:([a-z0-9-]+)/)?.[1] ?? null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const titled = /title generator/i.test(system) || !tools.length;
  const step = messages.slice(lastUser + 1).filter((message) => message.role === "tool").length;
  const count = titled ? 0 : (modelRequests.get(label) ?? 0) + 1;
  if (!titled) modelRequests.set(label, count);
  const sequence = (label && (sequences[label]?.() ?? [report(label)])) || [];
  const tool = titled ? undefined : sequence[step];
  trace("model.request", { label, step, tool: tool?.name ?? null, count, titled,
    sessionID: req.headers["x-opencode-session-id"] ?? null, tools: count === 1 ? tools : undefined });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (tool) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${label}_${step}_${count}`, type: "function", function: { name: tool.name, arguments: JSON.stringify(tool.arguments) } }] });
  else chunk({ role: "assistant", content: titled ? "Fixture title" : "Fixture complete." });
  chunk({}, tool ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed, the
// background service on a private port with a known password.
const freePort = async () => {
  const server = net.createServer().listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  server.close();
  return port;
};
const servicePort = await freePort();
const password = "fixture-password";
writeFileSync(path.join(configHome, "service.json"), JSON.stringify({ hostname: "127.0.0.1", port: servicePort, password }));
const opencodeConfig = JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  permissions: [{ action: "*", resource: "*", effect: "allow" }],
}, null, 2);

// --- Observation -------------------------------------------------------------

const run = (command, args, { cwd = fixture, extra = {} } = {}) => {
  const result = spawnSync(command, args, { cwd, env: { ...env, ...extra }, encoding: "utf8", timeout: 60000 });
  return { status: result.status, stdout: retained(result.stdout ?? ""), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const integrate = (label, args, options = {}) => trace("integrate", { label, args, ...run(dashpot, ["integrate", ...args], options) });
// What a person's dashboard reads: the headless snapshot of a Project.
const observe = (label, cwd = fixture) => {
  const result = run(dashpot, ["--json"], { cwd });
  let snapshot = null;
  try { snapshot = JSON.parse(result.stdout); } catch {}
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((item) => item.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: String(message).slice(0, 400) }));
  return trace("observation", { label, error: snapshot ? null : result.stderr, runs, diagnostics });
};
// What Cleanup says about one linked Worktree.
const check = (label, worktree) => {
  const result = run(dashpot, ["worktree", "check", worktree, "--json"]);
  let report = null;
  try { report = JSON.parse(result.stdout); } catch {}
  return trace("cleanup", { label, worktree, status: result.status, report: report ?? result.stdout.slice(0, 2000), stderr: report ? undefined : result.stderr });
};
const storeOf = (worktree) => path.join(worktree, ".dashpot", "state", "sessions");
const readJson = (file) => { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return null; } };
const hookRecord = (worktree, id) => readJson(path.join(storeOf(worktree), `${id}.json`));
// Every hook record and Publisher Record in the fixture's stores, by file.
const stateFiles = (label) => {
  const files = {};
  for (const worktree of worktrees) {
    for (const directory of [storeOf(worktree), path.join(storeOf(worktree), "opencode")]) {
      let names = [];
      try { names = readdirSync(directory).filter((name) => name.endsWith(".json")); } catch { continue; }
      for (const name of names) files[path.join(directory, name)] = readJson(path.join(directory, name));
    }
  }
  let outside = [];
  try { outside = readdirSync(env.DASHPOT_STATE_DIR, { recursive: true }).map(String); } catch {}
  return trace("state", { label, files, outside });
};
// Every Runtime Event the fixture's Dashpot processes recorded, flattened.
const eventLog = () => {
  const events = [];
  const directories = [...worktrees.map((worktree) => path.join(worktree, ".dashpot", "state", "events")), path.join(env.XDG_STATE_HOME, "dashpot", "events"),
    path.join(env.DASHPOT_STATE_DIR, "events")];
  for (const directory of directories) {
    let names = [];
    try { names = readdirSync(directory); } catch { continue; }
    for (const name of names) {
      for (const line of readFileSync(path.join(directory, name), "utf8").split("\n")) {
        if (!line) continue;
        const flat = {};
        const merge = (value) => { for (const [key, item] of Object.entries(value)) { if (item && typeof item === "object" && !Array.isArray(item)) merge(item); else flat[key] = item; } };
        try { merge(JSON.parse(line)); } catch { continue; }
        events.push(flat);
      }
    }
  }
  return events;
};
// How many plugin instances have registered, and how many last-instance
// cleanups have marked their sessions, by the helper runs the Event Log holds.
const helperRuns = (kindName) => eventLog().filter((event) => event["event.name"] === "process.end" && event["dashpot.process.kind"] === kindName).length;
const instances = (label) => trace("instances", { label, registered: helperRuns("hook:opencode:register"), unobserved: helperRuns("hook:opencode:unobserved") });
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
const settle = (ms = 1500) => delay(ms);
// Every process whose environment names the fixture configuration, so the
// operator's own processes are never observed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    if (!inFixture(name, env.XDG_CONFIG_HOME)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const processes = (label) => trace("processes", { label, processes: fixtureProcesses()
  .filter((entry) => !entry.cmdline.includes("command.mjs") && entry.pid !== process.pid)
  .map(({ pid, ppid, comm, cmdline, exe }) => ({ pid, ppid, comm, cmdline, exe })) });
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
// The TCP ports a process listens on, from its socket descriptors.
const listening = (pid) => {
  const inodes = new Set();
  try {
    for (const fd of readdirSync(`/proc/${pid}/fd`)) {
      try { const inode = readlinkSync(`/proc/${pid}/fd/${fd}`).match(/^socket:\[(\d+)\]$/)?.[1]; if (inode) inodes.add(inode); } catch {}
    }
  } catch { return null; }
  const found = [];
  for (const table of ["tcp", "tcp6"]) {
    let lines = [];
    try { lines = readFileSync(`/proc/net/${table}`, "utf8").trim().split("\n").slice(1); } catch { continue; }
    for (const line of lines) {
      const fields = line.trim().split(/\s+/);
      if (fields[3] !== "0A" || !inodes.has(fields[9])) continue;
      const [address, port] = fields[1].split(":");
      found.push({ table, address, port: parseInt(port, 16) });
    }
  }
  return found;
};
// Helper processes, sampled while the run lasts: their parent is the process
// that loaded the plugin.
const helpers = new Map();
const sampler = setInterval(() => {
  for (const entry of fixtureProcesses()) {
    if (helpers.has(entry.pid)) continue;
    // The recorded command line keeps eight arguments; read them all.
    let full = "";
    try { full = readFileSync(`/proc/${entry.pid}/cmdline`, "utf8"); } catch { continue; }
    if (!full.includes("dashpot-opencode-hook")) continue;
    let parent = null;
    try { parent = describe(entry.ppid); } catch {}
    helpers.set(entry.pid, { pid: entry.pid, ppid: entry.ppid, parentComm: parent?.comm ?? null, parentCmdline: parent?.cmdline ?? null, seenAt: Date.now() });
  }
}, 25);

// --- The background service and its clients -----------------------------------

const registration = () => readJson(path.join(env.XDG_STATE_HOME, "opencode", "service.json"));
const service = { url: `http://127.0.0.1:${servicePort}`, pid: null, events: null };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
// One API request: its status and parsed body.
const request = async (method, route, data, { directory } = {}) => {
  const headers = { "content-type": "application/json", authorization };
  if (directory) headers["x-opencode-directory"] = encodeURIComponent(directory);
  const response = await fetch(service.url + route, { method, headers, body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = raw.slice(0, 500); }
  return { status: response.status, body: parsed?.data ?? parsed };
};
// One API request that must succeed: its parsed body.
const api = async (method, route, data, options) => {
  const answer = await request(method, route, data, options);
  assert(answer.status >= 200 && answer.status < 300, `${method} ${route}: ${answer.status} ${JSON.stringify(answer.body).slice(0, 700)}`);
  return answer.body;
};
// OpenCode's server event stream: every location's session events, as a
// client sees them.
const subscribe = (name) => {
  const controller = new AbortController();
  (async () => {
    try {
      const response = await fetch(service.url + "/api/event", { headers: { authorization }, signal: controller.signal });
      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of response.body) {
        buffer += decoder.decode(chunk, { stream: true });
        let at;
        while ((at = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, at);
          buffer = buffer.slice(at + 2);
          let event;
          try { event = JSON.parse(block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5)).join("")); } catch { continue; }
          if (!/^session\.(created|forked|deleted|moved|execution\.)/.test(event.type ?? "")) continue;
          const data = event.data ?? {};
          trace("server.event", { name, type: event.type, location: event.location?.directory ?? null, sessionID: data.sessionID ?? null,
            parentID: data.parentID ?? null, reason: data.reason ?? null, to: event.type === "session.moved" ? data.location?.directory ?? null : undefined,
            sequence: event.durable?.seq ?? null });
        }
      }
    } catch {}
  })();
  return controller;
};
// The running service, once its registration answers.
const awaitService = async (label, previousPid = null) => {
  let info = null;
  await waitFor(() => (info = registration()) && info.pid !== previousPid && alive(info.pid), `${label}: service registered`, 60000);
  let ready = false;
  for (let attempt = 0; attempt < 200 && !ready; attempt++) {
    ready = (await request("GET", "/api/info").catch(() => null))?.status === 200;
    if (!ready) await delay(100);
  }
  assert(ready, `${label}: service never ready`);
  service.pid = info.pid;
  service.events?.abort();
  service.events = subscribe(label);
  trace("service", { label, pid: info.pid, version: info.version ?? null, process: describe(info.pid), listening: listening(info.pid) });
  return info;
};
const session = async (title, directory) => {
  const made = await api("POST", "/api/session", { title, location: { directory }, model: { id: "fixture", providerID: "loop" } });
  trace("session", { title, sessionID: made.id, directory: made.location?.directory ?? null, parentID: made.parentID ?? null });
  return made.id;
};
const prompt = async (id, label) => {
  const started = Date.now();
  await api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}` });
  const waited = await request("POST", `/api/experimental/session/${id}/wait`, {});
  assert(waited.status >= 200 && waited.status < 300, `${label}: wait ${waited.status}`);
  trace("turn", { sessionID: id, label, ms: Date.now() - started, wait: waited.status });
};
const info = async (id) => {
  const answer = await request("GET", `/api/session/${id}`);
  return answer.status === 200 ? { location: answer.body?.location?.directory ?? null, parentID: answer.body?.parentID ?? null } : { missing: answer.status };
};
const move = async (id, directory, label) => {
  const answer = await request("POST", `/api/session/${id}/move`, { directory });
  await settle();
  trace("move", { label, sessionID: id, to: directory, status: answer.status, after: await info(id) });
};
const active = async () => (await request("GET", "/api/session/active")).body ?? {};
// A client process, a CLI command or a TUI on a pseudo-terminal, and a CLI
// command run to completion, each in an environment of the installation it
// names.
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const clientEnv = (name, { cwd, bin, extra }) => ({ ...env, PATH: `${bin}:${basePath}`, PWD: cwd, SPIKE_CLIENT: name, ...extra });
const clients = [];
const client = (name, args, { terminal = false, cwd = fixture, extra = {}, bin = curlBin } = {}) => {
  const clientEnvironment = clientEnv(name, { cwd, bin, extra });
  const quoted = args.map((arg) => /^[\w./:=@-]+$/.test(arg) ? arg : `'${arg.replaceAll("'", "'\\''")}'`);
  const child = terminal
    ? spawn("script", ["-qfec", ["opencode", ...quoted].join(" "), "/dev/null"], { cwd, env: { ...clientEnvironment, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] })
    : spawn("opencode", args, { cwd, env: clientEnvironment, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.stderr.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() }; trace("client.exit", { name, code, signal, tail: terminal ? null : retained(state.output.slice(-600)) }); });
  clients.push(state);
  trace("client.spawn", { name, args, cwd, terminal, bin, pid: child.pid, inherited: Object.keys(extra) });
  return state;
};
const cli = (args, { cwd = fixture, bin = curlBin } = {}) => {
  const result = spawnSync("opencode", args, { cwd, env: clientEnv(`cli-${args[0]}`, { cwd, bin, extra: {} }), encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const finished = async (state, timeout = 60000) => { await waitFor(() => state.exited, `${state.name} exit`, timeout); return state.exited; };
const quit = async (state, label) => {
  const started = Date.now();
  for (let attempt = 0; attempt < 4 && !state.exited; attempt++) {
    state.child.stdin.write("\u0003");
    try { await waitFor(() => state.exited, `${state.name} quit`, 3000); } catch {}
  }
  if (!state.exited) {
    state.child.stdin.write("/exit\r");
    try { await waitFor(() => state.exited, `${state.name} /exit`, 5000); } catch {}
  }
  assert(state.exited, `${state.name} did not quit: ${state.output.slice(-800)}`);
  trace("tui.quit", { label, client: state.name, ms: state.exited.at - started });
};
const stopService = async (label, how) => {
  const pid = service.pid;
  if (how === "cli") trace("service.stop", { label, ...cli(["service", "stop"]) });
  else process.kill(pid, how);
  await waitFor(() => !alive(pid), `${label}: service ${pid} exit`, 15000);
  await settle(500);
  service.events?.abort();
  service.events = null;
  service.pid = null;
  trace("service.stopped", { label, how, pid, registration: registration() ? "kept" : "removed" });
};
const startService = async (label, options) => {
  trace("service.start", { label, ...cli(["service", "start"], options) });
  return awaitService(label);
};
// End each orphaned Agent Run the way Cleanup says to.
const stopOrphans = (label, worktree) => {
  const obstacles = check(`${label}-before-stop`, worktree).report?.obstacles?.filter((item) => item.kind === "agent-run") ?? [];
  assert(obstacles.length, `${label}: Cleanup names no orphaned Agent Run to stop`);
  for (const obstacle of obstacles) {
    const key = obstacle.command?.match(/--session (\S+)/)?.[1];
    assert(key, `${label}: ${obstacle.detail}`);
    trace("work-stop", { label, ...run(dashpot, ["work", "stop", "--session", key], { cwd: worktree }) });
  }
  return check(`${label}-stopped`, worktree);
};
// Wait until more plugin instances have registered than had before.
const reregistered = async (label, before) => {
  await waitFor(() => helperRuns("hook:opencode:register") > before, `${label}: instances registered again`, 30000);
  await settle(1500);
  return instances(label);
};

const pluginFile = path.join(configHome, "plugins", "dashpot.js");
try {
  trace("environment", { version, olderVersion, v1Version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), olderBinary, olderBinarySHA256: sha256(olderBinary), v1Binary, v1BinarySHA256: sha256(v1Binary),
    servicePort, fixture, treeA, treeB, treeC, other, plain, wheel,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(checkout, "src", "dashpot", file))),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "verify.mjs", "command.mjs", "replay.mjs", "ancestry.mjs"].map((file) => [file, path.join(here, file)]),
      ...exercised.map((file) => [`src/dashpot/${file}`, path.join(checkout, "src", "dashpot", file)]),
    ].map(([name, file]) => [name, sha256(file)])) });

  // Scenario 1: the installer, beside unrelated configuration and plugins:
  // refused under OpenCode v1, installed, reinstalled, removed and installed
  // again, a plugin of the same name that is the user's own kept, and the
  // status of each release on PATH.
  trace("scenario", { name: "installer" });
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig);
  mkdirSync(path.join(configHome, "plugins"), { recursive: true });
  const unrelatedPlugin = path.join(configHome, "plugins", "unrelated.js");
  writeFileSync(unrelatedPlugin, "// Not Dashpot's.\nexport default { id: \"unrelated\", async setup() { return async () => {}; } };\n");
  const files = (label) => trace("files", { label, plugin: sha256(pluginFile), skill: existsSync(path.join(configHome, "skills", "dashpot-issue-work", "SKILL.md")),
    unrelated: Object.fromEntries([path.join(configHome, "opencode.json"), path.join(configHome, "service.json"), unrelatedPlugin].map((file) => [file, sha256(file)])) });
  files("before");
  integrate("v1-on-path", ["opencode"], { extra: { PATH: `${v1Bin}:${basePath}` } });
  files("after-v1");
  integrate("install", ["opencode"]);
  integrate("status", ["opencode", "--status"]);
  files("installed");
  integrate("reinstall", ["opencode"]);
  files("reinstalled");
  integrate("remove", ["opencode", "--remove"]);
  files("removed");
  writeFileSync(pluginFile, "// The user's own plugin.\nexport default { id: \"mine\", async setup() { return async () => {}; } };\n");
  integrate("foreign-plugin", ["opencode"]);
  trace("foreign", { kept: readFileSync(pluginFile, "utf8").startsWith("// The user's own plugin.") });
  rmSync(pluginFile);
  integrate("install-again", ["opencode"]);
  assert(readFileSync(pluginFile, "utf8").includes(JSON.stringify(helper)), "the plugin names the installed helper");
  integrate("status-older-on-path", ["opencode", "--status"], { extra: { PATH: `${olderBin}:${basePath}` } });
  integrate("status-v1-on-path", ["opencode", "--status"], { extra: { PATH: `${v1Bin}:${basePath}` } });
  files("final");

  // Scenario 2: the shared service. A TUI started as the Issue-work skill
  // dispatches one, `opencode <worktree> --prompt`, from outside the
  // Repository, with another harness's claims and a leaked OpenCode session
  // in its environment, starts the service; sessions in the main Worktree
  // and a linked one, and a CLI run in another, each start, switch or stop
  // their own Issue work, and the shells that cannot opt in are refused.
  trace("scenario", { name: "shared" });
  const leaked = { OPENCODE_SESSION_ID: "ses_leakedfromanothersession00", OPENCODE: "1", DASHPOT_AGENT_SESSION: "codex:inherited",
    CODEX_THREAD_ID: "inherited-codex-thread", CLAUDE_CODE_SESSION_ID: "inherited-claude-session", CLAUDE_PID: "1" };
  const tui = client("tui", [treeC, "--prompt", "PROBE:tui-bind"], { terminal: true, cwd: root, extra: leaked });
  await waitFor(() => command("tui-show"), "TUI bound", 90000);
  await awaitService("shared");
  processes("tui-running");
  known.tui = command("tui-start", "start").env.OPENCODE_SESSION_ID;
  integrate("status-service", ["opencode", "--status"]);
  known.a1 = await session("A1", fixture);
  known.a2 = await session("A2", fixture);
  known.b1 = await session("B1", treeA);
  await prompt(known.a1, "a1-bind");
  await prompt(known.a2, "a2-bind");
  await prompt(known.b1, "b1-bind");
  await settle();
  stateFiles("three-bound");
  observe("three-bound");
  check("tree-a-bound", treeA);
  const holding = prompt(known.a1, "a1-hold");
  await waitFor(() => command("a1-hold", "start"), "a1 hold started");
  await settle();
  observe("a1-holding");
  await holding;
  await prompt(known.a2, "a2-refusals");
  // A shell the user runs in the session, as the TUI's `!` does, and a
  // terminal the server opens.
  await api("POST", `/api/session/${known.a2}/shell`, { command: `node ${commandScript} user-shell 0 -- work start issue-5` });
  await waitFor(() => command("user-shell"), "user shell");
  const pty = await request("POST", "/api/pty", { command: process.execPath, args: [commandScript, "pty", "0", "--", "work", "start", "issue-5"], cwd: fixture }, { directory: fixture });
  trace("pty", { status: pty.status, id: pty.body?.id ?? null });
  await waitFor(() => command("pty"), "PTY command", 15000);
  // A CLI run in a third Worktree, which exits once its turn ends.
  const cliRun = client("run", ["run", "--title", "R", "-m", "loop/fixture", "--auto", "PROBE:run-bind"], { cwd: treeB });
  await finished(cliRun, 90000);
  known.run = command("run-start", "start").env.OPENCODE_SESSION_ID;
  await prompt(known.a1, "a1-switch");
  await prompt(known.a2, "a2-stop");
  await settle();
  observe("switched-and-stopped");
  check("tree-b-run-exited", treeB);
  await quit(tui, "ctrl-c");
  await settle(2500);
  trace("service.after-tui", { pid: service.pid, alive: alive(service.pid) });
  observe("tui-quit");
  check("tree-c-tui-quit", treeC);
  // The TUI's session resumed from another directory, as `opencode <dir>
  // --session <id>` does.
  const elsewhere = client("tui-resumed-elsewhere", [fixture, "--session", known.tui, "--prompt", "PROBE:tui-resumed-elsewhere"], { terminal: true, cwd: root });
  await waitFor(() => command("tui-resumed-elsewhere-show"), "resumed TUI shell", 90000);
  await settle();
  trace("session.info", { label: "tui-resumed-elsewhere", sessionID: known.tui, ...(await info(known.tui)) });
  await quit(elsewhere, "resumed-ctrl-c");
  await settle();
  stateFiles("tui-resumed-elsewhere");
  observe("tui-resumed-elsewhere");

  // Scenario 3: Sub-agents. A child working in the foreground holds its root
  // running; a background child holds it running after the root's own
  // execution has ended; neither child's command can opt in.
  trace("scenario", { name: "subagents" });
  known.p = await session("P", fixture);
  await prompt(known.p, "p-bind");
  const delegating = prompt(known.p, "p-delegate");
  await waitFor(() => command("child-hold", "start"), "child hold started");
  await settle();
  stateFiles("child-working");
  observe("child-working");
  await delegating;
  await settle();
  observe("child-finished");
  known.q = await session("Q", treeA);
  await prompt(known.q, "q-bind");
  await prompt(known.q, "q-delegate-background");
  trace("parent.settled", { sessionID: known.q, childStarted: Boolean(command("bg-child", "start")), childEnded: Boolean(command("bg-child")) });
  await waitFor(() => command("bg-child", "start"), "background child started", 30000);
  await settle();
  trace("active", { label: "background-working", sessions: await active() });
  stateFiles("background-working");
  observe("background-working");
  check("tree-b-background-working", treeB);
  await waitFor(() => command("bg-child-start"), "background child ended", 30000);
  await settle(3000);
  observe("background-finished");
  check("tree-b-background-finished", treeB);

  // Scenario 4: a fork of a bound session is a root of its own.
  trace("scenario", { name: "fork" });
  const forked = await api("POST", `/api/session/${known.a1}/fork`, {}, { directory: fixture });
  known.fork = forked.id;
  trace("fork", { source: known.a1, sessionID: forked.id, parentID: forked.parentID ?? null, location: forked.location?.directory ?? null });
  await settle();
  await prompt(known.fork, "fork-bind");
  await settle();
  observe("forked");

  // Scenario 5: a bound session moved by the model's tool and by the API,
  // idle and while a shell runs, within the Repository; then to another
  // Repository, outside every Project, and back.
  trace("scenario", { name: "moves" });
  known.m = await session("M", fixture);
  await prompt(known.m, "m-bind");
  await prompt(known.m, "m-moved-by-tool");
  await settle();
  trace("session.info", { label: "m-moved-by-tool", sessionID: known.m, ...(await info(known.m)) });
  observe("m-moved-by-tool");
  await move(known.m, treeB, "m-moved-by-api");
  await prompt(known.m, "m-moved-by-api");
  observe("m-moved-by-api");
  const busy = prompt(known.m, "m-busy-hold");
  await waitFor(() => command("m-busy-hold", "start"), "m busy hold started");
  await move(known.m, fixture, "m-moved-while-busy");
  await busy;
  await settle();
  trace("session.info", { label: "m-moved-while-busy", sessionID: known.m, ...(await info(known.m)) });
  observe("m-moved-while-busy");
  await move(known.m, other, "m-to-other");
  await prompt(known.m, "m-in-other");
  await settle();
  stateFiles("m-in-other");
  observe("m-in-other");
  observe("m-in-other-project", other);
  await move(known.m, plain, "m-to-plain");
  await prompt(known.m, "m-in-plain");
  await settle();
  stateFiles("m-in-plain");
  observe("m-in-plain");
  await move(known.m, fixture, "m-back");
  await prompt(known.m, "m-back");
  await settle();
  stateFiles("m-back");
  observe("m-back");

  // Scenario 6: plugin instance churn. A plugin file edit and its repair
  // each set every instance up again; `opencode reload` cleans every
  // instance up before setting any up, while a bound session's shell runs.
  trace("scenario", { name: "churn" });
  let before = instances("before-edit").registered;
  writeFileSync(pluginFile, readFileSync(pluginFile, "utf8") + "\n// Edited.\n");
  await reregistered("edited", before);
  await prompt(known.a1, "a1-after-edit");
  integrate("status-edited", ["opencode", "--status"]);
  before = instances("before-repair").registered;
  integrate("repair", ["opencode"]);
  await reregistered("repaired", before);
  const reloadHolding = prompt(known.q, "q-reload-hold");
  await waitFor(() => command("q-reload-hold", "start"), "q reload hold started");
  before = instances("before-reload").registered;
  trace("reload", cli(["reload"]));
  await reregistered("reloaded", before);
  stateFiles("reload-holding");
  observe("reload-holding");
  check("tree-a-reload-holding", treeA);
  await reloadHolding;
  await settle(2000);
  stateFiles("reload-hold-ended");
  observe("reload-hold-ended");
  check("tree-a-reload-hold-ended", treeA);

  // Scenario 7: the helper missing, then stalled, then back. A turn never
  // waits on a publication longer than the plugin's deadline, and a shell no
  // longer than its wait.
  trace("scenario", { name: "unavailable-helper" });
  const parked = `${helper}.parked`;
  renameSync(helper, parked);
  integrate("status-missing-helper", ["opencode", "--status"]);
  await prompt(known.a1, "a1-missing-helper");
  writeFileSync(helper, "#!/bin/sh\nexec sleep 30\n");
  chmodSync(helper, 0o755);
  await prompt(known.a1, "a1-stalled-helper");
  rmSync(helper);
  renameSync(parked, helper);
  await prompt(known.a1, "a1-helper-back");
  await settle();
  stateFiles("helper-back");
  observe("helper-back");

  // Scenario 8: deletion. Through the API, and with `opencode session
  // delete` from another Worktree; then a deletion no plugin instance
  // received, recovered when an instance registers; then late, deleted,
  // forged and misplaced publications replayed through the helper.
  trace("scenario", { name: "deletion" });
  trace("delete", { sessionID: known.b1, ...(await request("DELETE", `/api/session/${known.b1}`)) });
  await settle(2500);
  stateFiles("b1-deleted");
  observe("b1-deleted");
  const deleting = client("cli-delete", ["session", "delete", known.run], { cwd: fixture });
  await finished(deleting, 30000);
  await settle(2500);
  stateFiles("run-deleted-by-cli");
  observe("run-deleted-by-cli");
  check("tree-b-run-deleted", treeB);
  instances("before-remove");
  integrate("remove-live", ["opencode", "--remove"]);
  trace("reload", cli(["reload"]));
  await settle(4000);
  instances("removed");
  trace("delete", { sessionID: known.fork, unplugged: true, ...(await request("DELETE", `/api/session/${known.fork}`)) });
  await settle(2000);
  await prompt(known.a1, "a1-unplugged");
  stateFiles("fork-deleted-unplugged");
  observe("fork-deleted-unplugged");
  before = instances("before-restore").registered;
  integrate("restore", ["opencode"]);
  await prompt(known.a1, "a1-replugged");
  await reregistered("restored", before);
  await waitFor(() => !hookRecord(fixture, known.fork), "the fork's deletion recovered", 20000).catch((error) => trace("recovery.missing", { error: String(error) }));
  await settle();
  stateFiles("fork-recovered");
  observe("fork-recovered");
  await prompt(known.a1, "a1-replay");
  await settle();
  observe("replayed");

  // Scenario 9: the service replaced and stopped. A TUI of an older 2.0.x
  // release replaces it, and a session resumed there continues its Issue
  // work only through `work start`; a 2.0.22 TUI resuming another session
  // as the skill says to replaces it again; `opencode service stop` leaves
  // every bound run orphaned, and a killed service leaves its registration.
  trace("scenario", { name: "replacement" });
  let previous = service.pid;
  const olderTui = client("older-tui", ["--prompt", "PROBE:older-tui"], { terminal: true, bin: olderBin });
  await awaitService("older", previous);
  await waitFor(() => command("older-tui"), "older TUI shell", 90000);
  await quit(olderTui, "older-ctrl-c");
  await settle();
  integrate("status-older-service", ["opencode", "--status"]);
  observe("older-service");
  await prompt(known.a1, "a1-on-older");
  await settle();
  observe("a1-on-older");
  previous = service.pid;
  const resumed = client("q-resumed", [treeA, "--session", known.q, "--prompt", "PROBE:q-resumed"], { terminal: true, cwd: root });
  await awaitService("newer", previous);
  await waitFor(() => command("q-resumed-start"), "resumed TUI bound", 90000);
  await quit(resumed, "resumed-ctrl-c");
  await settle();
  observe("q-resumed");
  await stopService("service-stop", "cli");
  stateFiles("service-stopped");
  observe("service-stopped");
  check("tree-a-service-stopped", treeA);
  stopOrphans("tree-a-orphans", treeA);
  await startService("restarted");
  known.k = await session("K", treeC);
  await prompt(known.k, "k-bind");
  // Let the turn's last helper finish: one still running when the service
  // dies is reparented to pid 1, and the kill is about the registration.
  await settle();
  await stopService("service-kill", "SIGKILL");
  integrate("status-killed-service", ["opencode", "--status"]);
  observe("service-killed");
  check("tree-c-service-killed", treeC);

  // Scenario 10: `--standalone`, a private server per client: a CLI run and a
  // TUI, each binding Issue work in a linked Worktree.
  trace("scenario", { name: "standalone" });
  const standaloneRun = client("standalone-run", ["run", "--standalone", "--title", "S", "-m", "loop/fixture", "--auto", "PROBE:sa-run-bind"], { cwd: treeB });
  await waitFor(() => command("sa-run-hold", "start"), "standalone run shell", 90000);
  processes("standalone-run");
  observe("standalone-run-working");
  await finished(standaloneRun, 60000);
  await settle(2000);
  observe("standalone-run-exited");
  const standaloneTui = client("standalone-tui", ["--standalone", treeB, "--prompt", "PROBE:sa-tui-bind"], { terminal: true, cwd: root });
  await waitFor(() => command("sa-tui-show"), "standalone TUI bound", 90000);
  await settle();
  processes("standalone-tui");
  observe("standalone-tui-bound");
  check("tree-b-standalone-tui", treeB);
  await quit(standaloneTui, "standalone-ctrl-c");
  await settle(2500);
  observe("standalone-tui-quit");
  stopOrphans("tree-b-orphans", treeB);

  // Scenario 11: the npm package's layout, whose service is `opencode.exe`.
  trace("scenario", { name: "npm" });
  await startService("npm", { bin: npmBin });
  known.n = await session("N", fixture);
  await prompt(known.n, "npm-bind");
  await settle();
  processes("npm");
  observe("npm-bound");
  await stopService("npm-stop", "cli");

  trace("models", { requests: Object.fromEntries(modelRequests) });
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
  for (const state of clients) if (!state.exited) trace("client.screen", { name: state.name, screen: retained(state.output.slice(-2000)) });
} finally {
  clearInterval(sampler);
  trace("helpers", { processes: [...helpers.values()].map((entry) => ({ ...entry, parentCmdline: retained(String(entry.parentCmdline)) })) });
  // The helper's own record of each run: outcomes by kind, the slowest run,
  // and every outcome that did not succeed.
  const outcomes = eventLog().filter((event) => String(event["dashpot.process.kind"] ?? "").startsWith("hook:opencode"));
  const summary = {};
  for (const event of outcomes) {
    const entry = summary[event["dashpot.process.kind"]] ??= { runs: 0, results: {}, slowestSeconds: 0 };
    if (event["event.name"] === "process.end") {
      entry.runs += 1;
      entry.slowestSeconds = Math.max(entry.slowestSeconds, event["dashpot.duration_seconds"] ?? 0);
    }
    if (event["event.name"] === "hook.outcome") entry.results[event["dashpot.outcome.result"]] = (entry.results[event["dashpot.outcome.result"]] ?? 0) + 1;
  }
  trace("events", { summary, unsuccessful: outcomes.filter((event) => event["event.name"] === "hook.outcome" && event["dashpot.outcome.result"] !== "succeeded")
    .map((event) => ({ time: event.time ?? null, kind: event["dashpot.process.kind"], result: event["dashpot.outcome.result"], reason: event["dashpot.hook.reason"] ?? null,
      error: event["error.type"] ?? null })) });
  for (const state of clients) if (!state.exited) state.child.kill("SIGKILL");
  if (service.pid && alive(service.pid)) {
    try { process.kill(service.pid, "SIGTERM"); await waitFor(() => !alive(service.pid), "final service exit", 10000); } catch {}
  }
  service.events?.abort();
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    if (entry.pid === process.pid) continue;
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm, cmdline: retained(entry.cmdline) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid).filter((pid) => pid !== process.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
  process.exit(0);
}
