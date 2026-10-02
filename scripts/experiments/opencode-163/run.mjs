// Probe the OpenCode facts the Dashpot OpenCode Harness Adapter builds on,
// against a pinned OpenCode release in a disposable fixture.
//
//   setsid -f node scripts/experiments/opencode-163/run.mjs <opencode> [helper] > log 2>&1
//
// The managed plugin under test is the shipped asset,
// src/dashpot/plugins/opencode.js, installed by discovery into the isolated
// `$XDG_CONFIG_HOME/opencode/plugins/` exactly as `dashpot integrate opencode`
// installs it. Without a helper argument a stub helper forwards each request
// to this runner's receiver, which plays the association rules; with one, the
// installed `dashpot-opencode-hook` runs and the receiver only observes.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import {
  appendFileSync, chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync,
} from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HARNESS_COMMANDS = new Set(["claude", "codex", "opencode"]);
const ancestry = (pid) => {
  const chain = [];
  for (let current = pid; current > 1 && chain.length < 16;) {
    let line;
    try {
      line = execFileSync("ps", ["-o", "ppid=,comm=,args=", "-p", String(current)], { encoding: "utf8" }).trim();
    } catch {
      break;
    }
    const [ppid, comm, ...args] = line.split(/\s+/);
    chain.push({ pid: current, comm, args: args.join(" ") });
    current = Number(ppid);
  }
  return chain;
};
const host = ancestry(process.ppid).find((entry) => HARNESS_COMMANDS.has(path.basename(entry.comm)));
if (host) {
  console.error(`Refusing to run under ${host.comm} (pid ${host.pid}); launch with setsid -f.`);
  process.exit(2);
}

const here = path.dirname(fileURLToPath(import.meta.url));
const pluginSource = path.resolve(here, "../../../src/dashpot/plugins/opencode.js");
const binary = process.argv[2];
const realHelper = process.argv[3];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to OpenCode v1.18.30");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-163-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, JSON.stringify(record) + "\n");
  return record;
};
const env = {
  PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  OPENCODE_TEST_HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  OPENCODE_DISABLE_PROJECT_CONFIG: "true",
  OPENCODE_DISABLE_DEFAULT_PLUGINS: "true",
  OPENCODE_DISABLE_EXTERNAL_SKILLS: "true",
  OPENCODE_DISABLE_CLAUDE_CODE: "true",
  OPENCODE_DISABLE_AUTOUPDATE: "true",
  OPENCODE_DISABLE_MODELS_FETCH: "true",
  OPENCODE_DISABLE_LSP_DOWNLOAD: "true",
  OPENCODE_DISABLE_FFF: "true",
  OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER: "true",
  // Claims a launching harness would leave in the backend's environment; a
  // command inside OpenCode must not inherit them.
  CODEX_THREAD_ID: "inherited-codex-thread",
  DASHPOT_AGENT_SESSION: "codex:inherited",
  DASHPOT_STATE_DIR: path.join(root, "dashpot-state"),
};
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
for (const dir of [fixture, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME,
  env.TMPDIR, path.join(configHome, "plugins"), env.DASHPOT_STATE_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "1.18.30");
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null",
  "commit", "--allow-empty", "-m", "Disposable fixture");

let helper = realHelper;
if (!helper) {
  helper = path.join(root, "stub-helper.mjs");
  writeFileSync(helper, `#!${process.execPath}\n` + readFileSync(path.join(here, "stub-helper.mjs"), "utf8"));
  chmodSync(helper, 0o755);
}
// The installed Dashpot integrates itself, against the isolated configuration
// alone; the stub is bound the same way by hand.
const integration = {};
if (realHelper) {
  const dashpot = path.join(path.dirname(realHelper), "dashpot");
  integration.install = execFileSync(dashpot, ["integrate", "opencode"], { cwd: fixture, env, encoding: "utf8" });
  integration.status = execFileSync(dashpot, ["integrate", "opencode", "--status"], { cwd: fixture, env, encoding: "utf8" });
} else {
  const plugin = readFileSync(pluginSource, "utf8").replace('"__DASHPOT_OPENCODE_HELPER__"', JSON.stringify(helper));
  writeFileSync(path.join(configHome, "plugins", "dashpot.js"), plugin);
}

const commandScript = path.join(root, "command.mjs");
writeFileSync(commandScript, `
import { execFileSync } from "node:child_process";
const names = ["DASHPOT_OPENCODE_SESSION_ID", "DASHPOT_OPENCODE_GENERATION", "DASHPOT_OPENCODE_PID",
  "DASHPOT_OPENCODE_UNCORROBORATED", "DASHPOT_AGENT_SESSION", "CODEX_THREAD_ID"];
const chain = [];
for (let pid = process.pid; pid > 1 && chain.length < 6;) {
  const [ppid, comm, ...args] = execFileSync("ps", ["-o", "ppid=,comm=,args=", "-p", String(pid)], { encoding: "utf8" }).trim().split(/\\s+/);
  chain.push({ pid, comm, args: args.join(" ").slice(0, 120) });
  pid = Number(ppid);
}
const data = { label: process.argv[3] ?? null, cwd: process.cwd(), pid: process.pid,
  env: Object.fromEntries(names.map((name) => [name, process.env[name] ?? null])), chain };
${realHelper ? `// Identifying the session validates its claim; with no Issue work held,
// work stop changes nothing.
try { data.stop = { status: 0, stdout: execFileSync(process.env.PROBE_DASHPOT, ["work", "stop"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }) }; }
catch (error) { data.stop = { status: error.status, stdout: String(error.stdout), stderr: String(error.stderr) }; }` : ""}
await fetch(process.env.PROBE_SINK + "/command", { method: "POST", body: JSON.stringify(data) });
await new Promise((resolve) => setTimeout(resolve, Number(process.argv[2] ?? 200)));
console.log("done");
`);

// The receiver plays the association rules for the stub helper: one active
// generation per backend and directory, tombstoned retirements, claims only
// for an accepted root bootstrap.
const active = new Map();
const retired = new Set();
const listen = async (handler) => {
  const server = http.createServer(handler);
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
  const record = await body(req);
  if (url.pathname === "/command") {
    trace("command", record);
    res.end("{}");
    return;
  }
  const { request } = record;
  const key = `${request.pid}:${request.directory}`;
  let acknowledgment;
  if (request.kind === "register") {
    if (retired.has(request.generation)) acknowledgment = { result: "retired" };
    else if (active.get(key) === request.generation) acknowledgment = { result: "duplicate" };
    else if (!active.has(key)) {
      active.set(key, request.generation);
      acknowledgment = { result: "accepted" };
    } else acknowledgment = { result: "conflict" };
  } else if (request.kind === "retire") {
    retired.add(request.generation);
    if (active.get(key) === request.generation) active.delete(key);
    acknowledgment = { result: "accepted" };
  } else if (active.get(key) !== request.generation) {
    acknowledgment = { result: "rejected", reason: "publisher-not-active" };
  } else if (request.kind === "bootstrap") {
    acknowledgment = request.session.id === request.root
      ? { result: "accepted", command: request.command,
        claim: { sessionID: request.session.id, generation: request.generation, pid: request.pid } }
      : { result: "accepted", command: request.command, reason: "delegated-session" };
  } else acknowledgment = { result: "accepted" };
  trace("helper", { ...record, acknowledgment });
  res.end(JSON.stringify(acknowledgment));
});
env.PROBE_SINK = sink.url;
if (realHelper) env.PROBE_DASHPOT = path.join(path.dirname(realHelper), "dashpot");

const attempts = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const lastUser = messages.findLastIndex((m) => m.role === "user");
  const content = JSON.stringify(messages[lastUser]?.content ?? "");
  const scenario = content.match(/PROBE:([a-z-]+)/)?.[1] ?? "finish";
  const usedTool = messages.slice(lastUser + 1).some((m) => m.role === "tool");
  const count = (attempts.get(scenario) ?? 0) + 1;
  attempts.set(scenario, count);
  trace("model.request", { scenario, usedTool, count });
  if (scenario === "retry" && count === 1) {
    res.writeHead(503, { "content-type": "application/json", "retry-after-ms": "150" });
    res.end(JSON.stringify({ error: { message: "fixture retry", type: "server_error" } }));
    return;
  }
  if (scenario === "error") {
    // A request the provider refuses outright: OpenCode does not retry it.
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: "fixture refusal", type: "invalid_request_error" } }));
    return;
  }
  let tool;
  if (!usedTool && scenario !== "finish") {
    if (scenario === "delegate") {
      tool = { name: "task", arguments: JSON.stringify({ description: "Fixture child", prompt: "PROBE:child", subagent_type: "general" }) };
    } else {
      tool = { name: "bash", arguments: JSON.stringify({ command: `node ${commandScript} 200 ${scenario}`, description: "Report the fixture command", workdir: fixture }) };
    }
  }
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish_reason = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason }] }) + "\n\n");
  if (tool) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${scenario}_${count}`, type: "function", function: tool }] });
  else chunk({ role: "assistant", content: "Fixture complete." });
  chunk({}, tool ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});
writeFileSync(path.join(configHome, "opencode.json"), JSON.stringify({
  $schema: "https://opencode.ai/config.json", model: "fixture/fixture", small_model: "fixture/fixture",
  enabled_providers: ["fixture"],
  provider: { fixture: { npm: "@ai-sdk/openai-compatible", name: "Local fixture", options: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", limit: { context: 16000, output: 2000 }, tool_call: true } } } },
  permission: "allow", share: "disabled", snapshot: false, autoupdate: false, lsp: false,
}));

let backend;
let backendURL;
const launch = async () => {
  backendURL = undefined;
  backend = spawn(binary, ["serve", "--hostname", "127.0.0.1", "--port", "0"], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let output = "";
  const read = (chunk) => { output += chunk.toString(); };
  backend.stdout.on("data", read);
  backend.stderr.on("data", read);
  for (let i = 0; i < 300; i++) {
    const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
    if (match) { backendURL = match[0]; break; }
    if (backend.exitCode !== null) throw new Error(`backend exited: ${output.slice(-3000)}`);
    await delay(100);
  }
  assert(backendURL, `backend startup timeout: ${output.slice(-3000)}`);
  trace("action.backend-start", { pid: backend.pid, process: ancestry(backend.pid)[0] });
};
const api = async (method, route, data, directory = fixture) => {
  const response = await fetch(backendURL + route, { method,
    headers: { "content-type": "application/json", "x-opencode-directory": directory },
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(30000) });
  const raw = await response.text();
  assert(response.ok, `${method} ${route}: ${response.status} ${raw.slice(0, 700)}`);
  return raw ? JSON.parse(raw) : null;
};
const prompt = (id, scenario) => api("POST", `/session/${id}/message`, { model: { providerID: "fixture", modelID: "fixture" }, parts: [{ type: "text", text: `PROBE:${scenario}` }] });
const waitFor = async (predicate, label, timeout = 20000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(25); }
  throw new Error(`Timed out: ${label}`);
};
const stop = async (signal = "SIGTERM") => {
  const done = once(backend, "exit");
  backend.kill(signal);
  const [code, exitSignal] = await done;
  trace("action.backend-exit", { pid: backend.pid, code, signal: exitSignal });
};
const helperRows = () => records.filter((r) => r.kind === "helper");
// With the installed helper, what it wrote is the observation: every hook and
// publisher record under the isolated state directory, and its Event Log.
const snapshot = (label) => {
  if (!realHelper) return;
  const files = execFileSync("find", [env.DASHPOT_STATE_DIR, path.join(env.XDG_STATE_HOME, "dashpot"), "-type", "f", "-name", "*.json*"], { encoding: "utf8" })
    .split("\n").filter(Boolean);
  trace("state", { label, files: Object.fromEntries(files.map((file) => [path.relative(root, file),
    file.endsWith(".jsonl") ? readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line))
      : JSON.parse(readFileSync(file, "utf8"))])) });
};
const commandRows = () => records.filter((r) => r.kind === "command");

try {
  trace("environment", { version, integration, node: process.version, platform: os.platform(), release: os.release(), fixture,
    helper: realHelper ? "installed" : "stub",
    sourceSHA256: Object.fromEntries([["run.mjs", path.join(here, "run.mjs")], ["stub-helper.mjs", path.join(here, "stub-helper.mjs")],
      ["opencode.js", pluginSource]].map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });
  await launch();
  // An instance, and with it the plugin, starts at the first request naming
  // its directory.
  const a = await api("POST", "/session", { title: "Fixture A" });
  if (!realHelper) await waitFor(() => helperRows().some((r) => r.request.kind === "register"), "discovered plugin registers");
  trace("action.session", { sessionID: a.id, directory: a.directory });
  await prompt(a.id, "root");
  snapshot("root");
  await prompt(a.id, "retry");
  await prompt(a.id, "error").catch((error) => trace("action.prompt-refused", { message: String(error).slice(0, 300) }));
  // Each status runs one helper; let the turn's last one land.
  await delay(2000);
  snapshot("error");
  await prompt(a.id, "delegate");
  snapshot("delegate");
  const fork = await api("POST", `/session/${a.id}/fork`, {});
  trace("action.fork", { sessionID: fork.id, parentID: fork.parentID ?? null });
  await prompt(fork.id, "fork");
  trace("action.pty-create");
  const pty = await api("POST", "/pty", { command: process.execPath, args: [commandScript, "100", "pty"], cwd: fixture });
  await waitFor(() => commandRows().some((r) => r.label === "pty"), "PTY command");
  await api("DELETE", `/pty/${pty.id}`).catch(() => {});
  trace("action.dispose", { pid: backend.pid });
  await api("POST", "/instance/dispose");
  await prompt(a.id, "reloaded");
  snapshot("reloaded");
  trace("action.delete", { sessionID: fork.id });
  await api("DELETE", `/session/${fork.id}`);
  await delay(1500);
  snapshot("deleted");
  await stop();
  console.log(`All probes completed: ${root}`);
} finally {
  if (backend && backend.exitCode === null && backend.signalCode === null) await stop();
  sink.server.closeAllConnections(); sink.server.close();
  model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.PROBE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
