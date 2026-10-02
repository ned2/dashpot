// Measurement run for Issue #393: how OpenCode v2 hosts sessions, plugin
// instances and shells, before Dashpot's integration is redesigned for it.
// It drives a pinned OpenCode 2.0.x release against a loopback
// OpenAI-compatible model fixture, in disposable configuration and state,
// with a private background service port, so the operator's own OpenCode
// service is never contacted. A throwaway plugin (plugin.mjs) records every
// plugin instance's setup, events, shell preparation, tool calls and cleanup;
// the shells the fixture model runs (command.mjs) report their environment
// and ancestry; the runner records OpenCode's server event stream and the
// fixture's processes. Dashpot is not involved. The trace is metadata only;
// the runner asserts only what it needs to keep going, and the independent
// verifier checks the trace against the spike's claims.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode binary> <absolute older opencode binary> > log 2>&1
// It is done when it prints "All scenarios completed". SPIKE_SCENARIOS names
// a comma-separated subset of the scenarios; SPIKE_IDLE_MINUTES adds an
// idle-eviction scenario that waits that long, and the retained idle trace
// comes from SPIKE_SCENARIOS=idle SPIKE_IDLE_MINUTES=64. SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import {
  appendFileSync, chmodSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync,
  symlinkSync, writeFileSync,
} from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
// A harness above the runner would be an ancestor of every client the run
// starts, so the runner refuses to start below one; `setsid -f` detaches it.
const above = [];
for (let pid = process.ppid; pid > 1 && above.length < 64;) { try { const entry = describe(pid); above.push(entry); pid = entry.ppid; } catch { break; } }
const host = above.find((entry) => /^(claude|codex|opencode|opencode2|opencode\.exe)$/.test(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const [binary, olderBinary] = process.argv.slice(2);
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the pinned OpenCode binary");
assert(olderBinary && path.isAbsolute(olderBinary), "Pass the absolute path to an older OpenCode 2.0.x binary");
const expectedVersion = "opencode v2.0.22";
const idleMinutes = Number(process.env.SPIKE_IDLE_MINUTES ?? 0);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-393-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree and two linked Worktrees sessions move
// between.
const fixture = path.join(root, "repository");
const treeA = path.join(root, "repository.worktrees", "a");
const treeB = path.join(root, "repository.worktrees", "b");
const tracePath = path.join(root, "trace.jsonl");
const pluginLog = path.join(root, "plugin.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, this directory, the
// checkout, and the operator's home by placeholder.
const retained = (text) => text.replaceAll(path.dirname(binary), "$BINARY_DIR").replaceAll(path.dirname(olderBinary), "$OLDER_BINARY_DIR").replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR").replaceAll(here, "$EXPERIMENT")
  .replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const sha256 = (file) => !existsSync(file) ? null : createHash("sha256").update(readFileSync(file)).digest("hex");

// OpenCode installed as its curl installer does: the binary at
// ~/.opencode/bin/opencode beside the `opencode2` shell shim. The older
// release sits in a directory of its own, for the version-mismatch scenario.
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
  // Ancestry walks from shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
const curlBin = path.join(env.HOME, ".opencode", "bin");
const olderBin = path.join(root, "older", "bin");
// The npm package's layout: the binary linked to `bin/opencode.exe` in the
// package, and npm's `opencode` and `opencode2` links to it.
const npmPackageBin = path.join(root, "npm", "lib", "node_modules", "@opencode", "cli", "bin");
const npmBin = path.join(root, "npm", "bin");
for (const dir of [fixture, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, curlBin, olderBin, npmPackageBin, npmBin]) mkdirSync(dir, { recursive: true });
const place = (source, target) => { try { linkSync(source, target); } catch { execFileSync("cp", [source, target]); } chmodSync(target, 0o755); };
place(binary, path.join(curlBin, "opencode"));
writeFileSync(path.join(curlBin, "opencode2"), "#!/bin/sh\nexec \"$(dirname \"$0\")/opencode\" \"$@\"\n");
chmodSync(path.join(curlBin, "opencode2"), 0o755);
place(olderBinary, path.join(olderBin, "opencode"));
place(binary, path.join(npmPackageBin, "opencode.exe"));
symlinkSync("../lib/node_modules/@opencode/cli/bin/opencode.exe", path.join(npmBin, "opencode"));
symlinkSync("../lib/node_modules/@opencode/cli/bin/opencode.exe", path.join(npmBin, "opencode2"));
const basePath = `${path.dirname(process.execPath)}:/usr/bin:/bin`;
env.PATH = `${curlBin}:${basePath}`;
const version = execFileSync(path.join(curlBin, "opencode"), ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, expectedVersion, `unexpected OpenCode version: ${version}`);
const olderVersion = execFileSync(path.join(olderBin, "opencode"), ["--version"], { env, encoding: "utf8" }).trim();
assert.notEqual(olderVersion, version, "the older binary must be another release");

const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
writeFileSync(path.join(fixture, "README.md"), "Disposable fixture.\n");
git("init", "--initial-branch=main");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "a", treeA);
git("worktree", "add", "-b", "b", treeB);

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
  trace("command", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `PROBE:<label>` text in the latest user turn selects a
// tool sequence, and the turn ends once every step has a tool result. A label
// with no sequence runs one shell command of that name.
const commandScript = path.join(here, "command.mjs");
const known = {};
const shell = (label, hold = 0, extra = "") => ({ name: "shell", arguments: { command: `node ${commandScript} ${label} ${hold}${extra ? " " + extra : ""}` } });
const delegate = (child, background = false) => ({ name: "subagent", arguments: { agent: "general", description: `Fixture ${child}`, prompt: `PROBE:${child}`, ...(background ? { background: true } : {}) } });
const execute = (code) => ({ name: "execute", arguments: { code } });
const sequences = {
  "api-main": () => [shell("api-main"), shell("api-main-clear", 0, "SPIKE_CLEAR")],
  "delegate-sync": () => [delegate("child-sync")],
  "child-sync": () => [shell("child-sync", 1500)],
  "delegate-bg": () => [delegate("child-bg", true)],
  "child-bg": () => [shell("child-bg", 6000)],
  "delegate-bg-deleted": () => [delegate("child-bg-deleted", true)],
  "child-bg-deleted": () => [shell("child-bg-deleted", 15000)],
  "move-tool": () => [execute(`return await tools.opencode.session_move({ directory: ${JSON.stringify(treeA)} })`), shell("after-move-tool")],
  "move-hold": () => [shell("move-hold", 5000), shell("after-move-hold")],
  "evict-hold": () => [shell("evict-hold", 6000)],
  "idle-hold": () => [longShell("idle-hold")],
  "idle-chatty": () => [longShell("idle-chatty", "SPIKE_CHATTY")],
};
// A shell that outlasts the idle wait, with a tool timeout beyond it.
function longShell(label, extra = "") {
  return { name: "shell", arguments: { command: `node ${commandScript} ${label} ${(idleMinutes + 5) * 60000}${extra ? " " + extra : ""}`, timeout: (idleMinutes + 10) * 60000 } };
}
const toolRequests = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const lastUser = messages.findLastIndex((message) => message.role === "user");
  const content = JSON.stringify(messages[lastUser]?.content ?? "");
  const label = content.match(/PROBE:([a-z0-9-]+)/)?.[1] ?? null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const titled = /title generator/i.test(system);
  const step = messages.slice(lastUser + 1).filter((message) => message.role === "tool").length;
  const count = titled ? 0 : (toolRequests.get(label) ?? 0) + 1;
  if (!titled) toolRequests.set(label, count);
  const sequence = (label && (sequences[label]?.() ?? [shell(label)])) || [];
  const tool = titled ? undefined : sequence[step];
  trace("model.request", { label, step, tool: tool?.name ?? null, count, titled, tools: count === 1 ? tools : undefined,
    sessionID: req.headers["x-opencode-session-id"] ?? null, parentSessionID: req.headers["x-opencode-parent-session-id"] ?? null,
    subagent: content.includes("You are a subagent") });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (tool) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${label}_${step}_${count}`, type: "function", function: { name: tool.name, arguments: JSON.stringify(tool.arguments) } }] });
  else chunk({ role: "assistant", content: titled ? "Fixture title" : "Fixture complete." });
  chunk({}, tool ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed, the
// background service on a private port with a known password.
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
mkdirSync(path.join(configHome, "plugins"), { recursive: true });
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
writeFileSync(path.join(configHome, "opencode.json"), JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  permissions: [{ action: "*", resource: "*", effect: "allow" }],
}, null, 2));
const pluginFile = path.join(configHome, "plugins", "spike.js");
const pluginSource = readFileSync(path.join(here, "plugin.mjs"), "utf8").replace("__SPIKE_LOG__", pluginLog);
writeFileSync(pluginFile, pluginSource);

// --- Observation -------------------------------------------------------------

// Every process whose environment names the fixture configuration, so the
// operator's own processes are never observed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`XDG_CONFIG_HOME=${env.XDG_CONFIG_HOME}\0`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const processes = (label) => trace("processes", { label, processes: fixtureProcesses()
  .filter((entry) => !entry.cmdline.includes("command.mjs") && entry.pid !== process.pid)
  .map(({ pid, ppid, pgrp, sid, comm, cmdline, exe, cwd }) => ({ pid, ppid, pgrp, sid, comm, cmdline, exe, cwd })) });
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
// The plugin's records, merged into the trace as they appear.
let pluginOffset = 0;
const drainPlugin = () => {
  let text;
  try { text = readFileSync(pluginLog, "utf8"); } catch { return; }
  const fresh = text.slice(pluginOffset);
  const end = fresh.lastIndexOf("\n");
  if (end < 0) return;
  pluginOffset += end + 1;
  for (const line of fresh.slice(0, end).split("\n")) {
    try { const { kind, ...fields } = JSON.parse(line); trace(kind, fields); } catch {}
  }
};
const sampler = setInterval(drainPlugin, 25);
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
const pluginRecords = (kind, predicate = () => true) => records.filter((record) => record.kind === kind && predicate(record));

// --- The background service and its clients -----------------------------------

const registration = () => { try { return JSON.parse(readFileSync(path.join(env.XDG_STATE_HOME, "opencode", "service.json"), "utf8")); } catch { return null; } };
const service = { url: `http://127.0.0.1:${servicePort}`, events: null };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
const api = async (method, route, data, { directory, base = service.url, auth = authorization, allow = false } = {}) => {
  const headers = { "content-type": "application/json", authorization: auth };
  if (directory) headers["x-opencode-directory"] = encodeURIComponent(directory);
  const response = await fetch(base + route, { method, headers, body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  if (!allow) assert(response.ok, `${method} ${route}: ${response.status} ${raw.slice(0, 700)}`);
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = raw.slice(0, 500); }
  return allow ? { status: response.status, body: parsed } : parsed;
};
const unwrap = (value) => value?.data ?? value;
// OpenCode's server event stream: every location's session events, as a
// client sees them.
const subscribe = (base, name) => {
  const controller = new AbortController();
  (async () => {
    try {
      const response = await fetch(base + "/api/event", { headers: { authorization }, signal: controller.signal });
      trace("stream.open", { name, status: response.status });
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
          if (!/^session\.(created|deleted|moved|execution\.|retry|shell\.)|^server\.|^location\./.test(event.type ?? "")) continue;
          const data = event.data ?? {};
          trace("server.event", { name, type: event.type, location: event.location?.directory ?? null,
            sessionID: data.sessionID ?? data.info?.id ?? null, parentID: data.parentID ?? data.info?.parentID ?? null,
            reason: data.reason ?? null, moved: event.type === "session.moved" ? data : undefined });
        }
      }
      trace("stream.closed", { name });
    } catch (error) {
      if (!controller.signal.aborted) trace("stream.closed", { name, error: String(error).slice(0, 200) });
    }
  })();
  return controller;
};
// The running service, once its registration answers.
const awaitService = async (label, previousPid = null) => {
  let info = null;
  await waitFor(() => (info = registration()) && info.pid !== previousPid && alive(info.pid), `${label}: service registered`, 60000);
  let ready = null;
  for (let attempt = 0; attempt < 200 && !ready; attempt++) {
    const answer = await api("GET", "/api/info", undefined, { allow: true }).catch(() => null);
    if (answer?.status === 200) ready = unwrap(answer.body);
    else await delay(100);
  }
  assert(ready, `${label}: service never ready`);
  service.pid = info.pid;
  service.events?.abort();
  service.events = subscribe(service.url, label);
  trace("service", { label, registration: { ...info, password: info.password ? "<set>" : null }, info: ready, process: describe(info.pid) });
  return info;
};
const created = [];
const session = async (title, directory, extra = {}) => {
  const made = unwrap(await api("POST", "/api/session", { title, location: { directory }, model: { id: "fixture", providerID: "loop" }, ...extra }));
  created.push(made.id);
  trace("session", { title, sessionID: made.id, directory: made.location?.directory ?? null, parentID: made.parentID ?? null });
  return made.id;
};
const wait = (id) => api("POST", `/api/experimental/session/${id}/wait`, {}, { allow: true });
const prompt = async (id, label, { settle = true } = {}) => {
  const started = Date.now();
  await api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}` });
  if (settle) {
    const waited = await wait(id);
    trace("turn", { sessionID: id, label, ms: Date.now() - started, wait: waited.status });
  }
};
const info = async (id) => unwrap(await api("GET", `/api/session/${id}`, undefined, { allow: true }).then((answer) => answer.status === 200 ? answer.body : { missing: answer.status }));
// A client process: a CLI command, or a TUI on a pseudo-terminal.
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const clients = [];
const client = (name, args, { terminal = false, cwd = fixture, extra = {}, bin = curlBin, executable = "opencode" } = {}) => {
  const clientEnv = { ...env, PATH: `${bin}:${basePath}`, PWD: cwd, SPIKE_CLIENT: name, ...extra };
  const quoted = args.map((arg) => /^[\w./:=@-]+$/.test(arg) ? arg : `'${arg.replaceAll("'", "'\\''")}'`);
  const child = terminal
    ? spawn("script", ["-qfec", [executable, ...quoted].join(" "), "/dev/null"], { cwd, env: { ...clientEnv, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] })
    : spawn(executable, args, { cwd, env: clientEnv, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.stderr.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() }; trace("client.exit", { name, code, signal, tail: terminal ? null : retained(state.output.slice(-600)) }); });
  clients.push(state);
  trace("client.spawn", { name, args, cwd, terminal, executable, bin, pid: child.pid, leaked: extra.OPENCODE_SESSION_ID ?? null });
  return state;
};
const finished = async (state, timeout = 60000) => { await waitFor(() => state.exited, `${state.name} exit`, timeout); return state.exited; };
// The OpenCode process a client runs: itself, or the process below `script`.
const opencodeOf = (state) => {
  const all = fixtureProcesses();
  const below = (entry) => {
    for (let current = entry; current;) {
      if (current.pid === state.child.pid || current.ppid === state.child.pid) return true;
      current = all.find((other) => other.pid === current.ppid);
    }
    return false;
  };
  return all.find((entry) => /opencode/.test(entry.comm) && !entry.cmdline.includes(" serve") && below(entry)) ?? null;
};
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
  const started = Date.now();
  if (how === "cli") trace("service.stop", { label, how, ...cli(["service", "stop"]) });
  else process.kill(pid, how);
  await waitFor(() => !alive(pid), `${label}: service ${pid} exit`, 15000);
  await delay(500);
  service.events?.abort();
  service.events = null;
  trace("service.stopped", { label, how, pid, ms: Date.now() - started, registration: registration() ? "kept" : "removed" });
};
const cli = (args, { cwd = fixture, bin = curlBin } = {}) => {
  const result = spawnSync("opencode", args, { cwd, env: { ...env, PATH: `${bin}:${basePath}`, PWD: cwd, SPIKE_CLIENT: `cli-${args[0]}` }, encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const settle = (ms = 1500) => delay(ms);

const scenarios = (process.env.SPIKE_SCENARIOS ?? "shared,subagents,moves,churn,standalone,layouts").split(",");
try {
  trace("environment", { version, olderVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), olderBinary, servicePort, fixture, treeA, treeB, scenarios, idleMinutes,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    sourceSHA256: Object.fromEntries(["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs", "plugin.mjs"].map((file) => [file, sha256(path.join(here, file))])) });

  // Scenario 1: the default mode. A TUI started where a leaked session ID is
  // in its environment spawns the shared background service; a session per
  // Worktree, a CLI `run`, user shells and a terminal follow; the TUI quits.
  if (scenarios.includes("shared")) {
    trace("scenario", { name: "shared" });
    const leaked = "ses_leakedfromanothersession00";
    const tui = known.tui = client("tui", ["--prompt", "PROBE:tui-1"], { terminal: true, extra: { OPENCODE_SESSION_ID: leaked } });
    await waitFor(() => command("tui-1"), "TUI turn reached its shell", 90000);
    await awaitService("shared");
    processes("tui-running");
    const tuiSession = known.tuiSession = command("tui-1", "start").env.OPENCODE_SESSION_ID;
    const a1 = known.a1 = await session("A1", fixture);
    const a2 = known.a2 = await session("A2", fixture);
    const b1 = known.b1 = await session("B1", treeA);
    await prompt(a1, "api-main");
    await prompt(a2, "api-main-2");
    await prompt(b1, "api-tree-a");
    // User shells, as the TUI's `!` sends them, with and without clearing.
    await api("POST", `/api/session/${a1}/shell`, { command: `node ${commandScript} user-shell 0` });
    await waitFor(() => command("user-shell"), "user shell");
    await api("POST", `/api/session/${a1}/shell`, { command: `node ${commandScript} user-shell-clear 0 SPIKE_CLEAR` });
    await waitFor(() => command("user-shell-clear"), "cleared user shell");
    // A terminal the server opens.
    const pty = await api("POST", "/api/pty", { command: process.execPath, args: [commandScript, "pty", "0"], cwd: fixture }, { directory: fixture, allow: true });
    trace("pty", { status: pty.status, id: unwrap(pty.body)?.id ?? null });
    try { await waitFor(() => command("pty"), "PTY command", 15000); } catch (error) { trace("pty.missing", { error: String(error) }); }
    // A CLI run in the second linked Worktree, with its own environment.
    const run = client("run", ["run", "--title", "R", "-m", "loop/fixture", "--auto", "PROBE:cli-run"], { cwd: treeB });
    await finished(run, 90000);
    await settle();
    processes("after-run");
    trace("sessions", { label: "shared", tui: tuiSession, list: unwrap((await api("GET", "/api/session?limit=50", undefined, { allow: true })).body) });
    await quit(tui, "ctrl-c");
    await settle(2500);
    trace("service.after-tui", { pid: service.pid, alive: alive(service.pid), process: alive(service.pid) ? describe(service.pid) : null });
    processes("tui-quit");
  }

  // The remaining scenarios use the shared service, started by a CLI command
  // if the first scenario did not run.
  if (!service.pid) {
    trace("service.start", cli(["service", "start"]));
    await awaitService("started");
  }

  // Scenario 2: sub-agents, in the foreground and in the background, and a
  // background child whose parent is deleted under it.
  if (scenarios.includes("subagents")) {
    trace("scenario", { name: "subagents" });
    const p = known.p = await session("P", fixture);
    await prompt(p, "delegate-sync");
    await settle();
    const q = known.q = await session("Q", treeA);
    const started = Date.now();
    await prompt(q, "delegate-bg");
    trace("parent.settled", { sessionID: q, ms: Date.now() - started, childStarted: Boolean(command("child-bg", "start")), childEnded: Boolean(command("child-bg")) });
    await waitFor(() => command("child-bg"), "background child ended", 60000);
    await settle(3000);
    const r = known.r = await session("R2", treeA);
    await prompt(r, "delegate-bg-deleted");
    await waitFor(() => command("child-bg-deleted", "start"), "background child started", 60000);
    await settle();
    const children = unwrap(await api("GET", `/api/session?parentID=${r}`));
    trace("children", { parent: r, children });
    processes("background-child-running");
    const deleting = Date.now();
    trace("delete", { sessionID: r, ...(await api("DELETE", `/api/session/${r}`, undefined, { allow: true })) });
    await settle(3000);
    const shellPid = command("child-bg-deleted", "start").pid;
    trace("after-delete", { ms: Date.now() - deleting, shellAlive: alive(shellPid), shellEnded: Boolean(command("child-bg-deleted")) });
    await waitFor(() => command("child-bg-deleted") || !alive(shellPid), "deleted child's shell settled", 30000);
    trace("after-delete-settled", { shellAlive: alive(shellPid), shellEnded: Boolean(command("child-bg-deleted")),
      active: unwrap((await api("GET", "/api/session/active", undefined, { allow: true })).body) });
  }

  // Scenario 3: a session moved by the model's tool, by the API while idle,
  // and by the API while a shell runs.
  if (scenarios.includes("moves")) {
    trace("scenario", { name: "moves" });
    const m = known.m = await session("M", fixture);
    await prompt(m, "move-tool");
    await settle();
    trace("session.info", { label: "after-move-tool", info: await info(m) });
    await prompt(m, "after-tool-move");
    trace("move", { sessionID: m, to: treeB, ...(await api("POST", `/api/session/${m}/move`, { directory: treeB }, { allow: true })) });
    await settle();
    trace("session.info", { label: "after-api-move", info: await info(m) });
    await prompt(m, "after-api-move");
    const holding = prompt(m, "move-hold");
    await waitFor(() => command("move-hold", "start"), "move hold started");
    trace("move", { sessionID: m, to: fixture, during: "move-hold", ...(await api("POST", `/api/session/${m}/move`, { directory: fixture }, { allow: true })) });
    await holding;
    await settle();
    trace("session.info", { label: "after-busy-move", info: await info(m) });
  }

  // Scenario 4: plugin generations. A plugin file change, `opencode reload`,
  // a location evicted while idle and while a shell runs, `session delete`
  // from the CLI, a client of another release replacing the service and back,
  // `service stop`, and a service killed outright.
  if (scenarios.includes("churn")) {
    trace("scenario", { name: "churn" });
    const c = known.c = await session("C", fixture);
    const d = known.d = await session("D", treeA);
    await prompt(c, "churn-main");
    await prompt(d, "churn-tree-a");
    trace("mark", { label: "hot-reload" });
    writeFileSync(pluginFile, pluginSource + "\n// Changed.\n");
    await settle(4000);
    await prompt(c, "after-hot-reload");
    trace("mark", { label: "cli-reload" });
    trace("reload", cli(["reload"]));
    await settle(3000);
    await prompt(c, "after-cli-reload");
    trace("mark", { label: "evict-idle" });
    trace("evict", { directory: treeA, ...(await api("DELETE", `/api/debug/location?${new URLSearchParams({ "location[directory]": treeA })}`, undefined, { allow: true })) });
    await settle(2000);
    await prompt(d, "after-evict");
    trace("mark", { label: "evict-busy" });
    const holding = prompt(d, "evict-hold");
    await waitFor(() => command("evict-hold", "start"), "evict hold started");
    trace("evict", { directory: treeA, during: "evict-hold", ...(await api("DELETE", `/api/debug/location?${new URLSearchParams({ "location[directory]": treeA })}`, undefined, { allow: true })) });
    await holding;
    await settle(2000);
    await prompt(d, "after-busy-evict");
    trace("mark", { label: "cli-delete" });
    const e = known.e = await session("E", treeA);
    await prompt(e, "before-cli-delete");
    const deleting = client("cli-delete", ["session", "delete", e], { cwd: treeB });
    await finished(deleting, 30000);
    await settle(2000);
    trace("session.info", { label: "after-cli-delete", info: await info(e) });
    trace("mark", { label: "version-mismatch" });
    // A CLI run of another release uses the service as it is; only a TUI
    // replaces it, here while another session's shell runs.
    const before = service.pid;
    const olderRun = client("older-run", ["run", "--title", "Older", "-m", "loop/fixture", "--auto", "PROBE:older-run"], { cwd: fixture, bin: olderBin });
    await finished(olderRun, 120000);
    trace("service.after-older-run", { before, registered: registration()?.pid ?? null, version: registration()?.version ?? null });
    sequences["mismatch-hold"] = () => [shell("mismatch-hold", 8000), shell("after-mismatch-hold")];
    const mismatchHolding = prompt(c, "mismatch-hold").catch((error) => trace("turn.error", { label: "mismatch-hold", error: String(error).slice(0, 300) }));
    await waitFor(() => command("mismatch-hold", "start"), "mismatch hold started");
    const olderTui = client("older-tui", ["--prompt", "PROBE:older-tui"], { terminal: true, bin: olderBin });
    await awaitService("older", before);
    await waitFor(() => command("older-tui"), "older TUI shell", 90000);
    const held = command("mismatch-hold", "start").pid;
    trace("after-older-tui", { holdEnded: Boolean(command("mismatch-hold")), holdShellAlive: alive(held), oldServiceAlive: alive(before) });
    await mismatchHolding;
    await quit(olderTui, "older-ctrl-c");
    await settle();
    trace("session.info", { label: "on-older-service", info: await info(c) });
    await prompt(c, "on-older-service");
    const olderPid = service.pid;
    const newerTui = client("newer-tui", ["--prompt", "PROBE:newer-tui"], { terminal: true });
    await awaitService("newer", olderPid);
    await waitFor(() => command("newer-tui"), "newer TUI shell", 90000);
    await quit(newerTui, "newer-ctrl-c");
    await settle();
    trace("sessions", { label: "after-mismatch", c: await info(c), d: await info(d) });
    trace("mark", { label: "service-stop" });
    await stopService("service-stop", "cli");
    trace("service.start", cli(["service", "start"]));
    await awaitService("restarted");
    const k = known.k = await session("K", fixture);
    await prompt(k, "before-kill");
    trace("mark", { label: "service-kill" });
    await stopService("service-kill", "SIGKILL");
    trace("service.start", cli(["service", "start"]));
    await awaitService("after-kill");
    await prompt(k, "after-kill");
  }

  // Scenario 5: `--standalone`, a private server per client, beside the
  // shared service: a CLI run and a TUI.
  if (scenarios.includes("standalone")) {
    trace("scenario", { name: "standalone" });
    const run = client("standalone-run", ["run", "--standalone", "--title", "S", "-m", "loop/fixture", "--auto", "PROBE:standalone-hold"], { cwd: treeA });
    sequences["standalone-hold"] = () => [shell("standalone-hold", 3000)];
    await waitFor(() => command("standalone-hold", "start"), "standalone run shell");
    processes("standalone-run");
    await finished(run, 60000);
    await settle(2000);
    processes("standalone-run-exited");
    const tui = client("standalone-tui", ["--standalone", "--prompt", "PROBE:standalone-tui"], { terminal: true, cwd: treeB });
    await waitFor(() => command("standalone-tui"), "standalone TUI shell", 90000);
    await settle();
    processes("standalone-tui");
    await quit(tui, "standalone-ctrl-c");
    await settle(2500);
    processes("standalone-tui-quit");
    trace("sessions", { label: "standalone", list: unwrap((await api("GET", "/api/session?limit=50", undefined, { allow: true })).body) });
  }

  // Scenario 6: the npm package's layout and the `opencode2` shim, each
  // spawning the service afresh, so the service's process is the one each
  // installation runs.
  if (scenarios.includes("layouts")) {
    trace("scenario", { name: "layouts" });
    for (const [name, bin, executable] of [["npm-opencode", npmBin, "opencode"], ["npm-opencode2", npmBin, "opencode2"], ["curl-opencode2", curlBin, "opencode2"]]) {
      await stopService(`before-${name}`, "cli");
      const held = `${name}-hold`;
      sequences[held] = () => [shell(held, 3000)];
      const run = client(name, ["run", "--title", name, "-m", "loop/fixture", "--auto", `PROBE:${held}`], { cwd: fixture, bin, executable });
      await waitFor(() => command(held, "start"), `${name} shell`, 90000);
      processes(name);
      await finished(run, 60000);
      await awaitService(name);
    }
  }

  // Scenario 7 (only with SPIKE_IDLE_MINUTES): past the eviction deadline, a
  // location left idle, one whose shell runs silently throughout, and one
  // whose shell prints every minute. Both shells outlast the wait unless
  // OpenCode stops them.
  if (idleMinutes > 0) {
    trace("scenario", { name: "idle", minutes: idleMinutes });
    const quiet = known.quiet = await session("Quiet", treeA);
    const busy = known.busy = await session("Busy", treeB);
    const chatty = known.chatty = await session("Chatty", fixture);
    await prompt(quiet, "idle-quiet");
    await prompt(busy, "idle-hold", { settle: false });
    await prompt(chatty, "idle-chatty", { settle: false });
    await waitFor(() => command("idle-hold", "start") && command("idle-chatty", "start"), "idle holds started");
    const started = Date.now();
    for (let minute = 1; minute <= idleMinutes; minute++) {
      await delay(60000);
      drainPlugin();
      trace("idle.tick", { minute, busyShellEnded: Boolean(command("idle-hold")), chattyShellEnded: Boolean(command("idle-chatty")),
        active: unwrap(await api("GET", "/api/session/active", undefined, { allow: true }).then((answer) => answer.body)) });
    }
    trace("idle.done", { ms: Date.now() - started, locations: unwrap(await api("GET", "/api/debug/location", undefined, { allow: true }).then((answer) => answer.body)) });
    await prompt(quiet, "after-idle");
    // Each long shell ends, or its session stops, by the end of its hold.
    const active = async () => unwrap(await api("GET", "/api/session/active", undefined, { allow: true }).then((answer) => answer.body)) ?? {};
    const settledAt = Date.now() + 8 * 60000;
    while (Date.now() < settledAt && ((await active())[busy] || (await active())[chatty])) await delay(5000);
    drainPlugin();
    trace("idle.settled", { busyShellEnded: Boolean(command("idle-hold")), chattyShellEnded: Boolean(command("idle-chatty")), active: await active() });
  }
  // Every session the run made, from the shared database: each must have
  // used the fixture model.
  const all = unwrap((await api("GET", "/api/session?limit=500", undefined, { allow: true })).body) ?? [];
  trace("models", { sessions: all.map((item) => ({ id: item.id, parentID: item.parentID ?? null, model: item.model ?? null })) });
  assert(all.length && all.every((item) => item.model?.providerID === "loop"), "a session used a model other than the fixture's");
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
  for (const state of clients) if (!state.exited) trace("client.screen", { name: state.name, screen: retained(state.output.slice(-2000)) });
} finally {
  drainPlugin();
  for (const state of clients) if (!state.exited) state.child.kill("SIGKILL");
  if (service.pid && alive(service.pid)) {
    try { process.kill(service.pid, "SIGTERM"); await waitFor(() => !alive(service.pid), "final service exit", 10000); } catch {}
  }
  service.events?.abort();
  await delay(1000);
  drainPlugin();
  clearInterval(sampler);
  for (const entry of fixtureProcesses()) {
    if (entry.pid === process.pid) continue;
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm, cmdline: entry.cmdline });
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
