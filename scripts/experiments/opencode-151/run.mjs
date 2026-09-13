import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-151-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
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
  OPENCODE_CONFIG_DIR: path.join(root, "config", "opencode"),
  OPENCODE_DISABLE_PROJECT_CONFIG: "true",
  OPENCODE_DISABLE_DEFAULT_PLUGINS: "true",
  OPENCODE_DISABLE_EXTERNAL_SKILLS: "true",
  OPENCODE_DISABLE_CLAUDE_CODE: "true",
  OPENCODE_DISABLE_AUTOUPDATE: "true",
  OPENCODE_DISABLE_MODELS_FETCH: "true",
  OPENCODE_DISABLE_LSP_DOWNLOAD: "true",
  OPENCODE_DISABLE_FFF: "true",
  OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER: "true",
  OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS: "true",
  SPIKE_DIAGNOSTICS: path.join(root, "diagnostics.jsonl"),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME,
  env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, env.OPENCODE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to OpenCode v1.18.30");
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "1.18.30");
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "Disposable fixture");
git("worktree", "add", "-b", "other", other);
copyFileSync(path.join(here, "plugin.mjs"), path.join(env.OPENCODE_CONFIG_DIR, "probe.mjs"));

const commandScript = path.join(root, "command.mjs");
writeFileSync(commandScript, `
const claim = process.env.DASHPOT_AGENT_SESSION ?? null;
const data = { claim, cwd: process.cwd(), pid: process.pid, ppid: process.ppid,
  instance: process.env.SPIKE_INSTANCE, bootstrapAck: process.env.SPIKE_BOOTSTRAP_ACK };
try { data.evidence = await (await fetch(process.env.SPIKE_SINK + '/evidence?claim=' + claim + '&instance=' + data.instance)).json(); }
catch { data.evidence = false; }
await fetch(process.env.SPIKE_COMMAND_SINK + '/command', {method:'POST',body:JSON.stringify({...data,phase:'start'})});
await new Promise(r => setTimeout(r, Number(process.argv[2] ?? 300)));
await fetch(process.env.SPIKE_COMMAND_SINK + '/command', {method:'POST',body:JSON.stringify({...data,phase:'end'})});
console.log(JSON.stringify(data));
`);

let receiverMode = "normal";
let receiverDelay = 0;
let receiverDelayKinds;
const currentInstances = new Map();
const lastSequence = new Map();
const evidence = new Set();
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
  if (url.pathname === "/evidence") {
    res.end(JSON.stringify(receiverMode !== "unavailable" && evidence.has(`${url.searchParams.get("instance")}:${url.searchParams.get("claim")}`)));
    return;
  }
  const record = await body(req);
  if (url.pathname === "/command") {
    trace("command", record); res.end("{}"); return;
  }
  const delayMs = !receiverDelayKinds || receiverDelayKinds.has(record.kind) ? receiverDelay : 0;
  const received = trace("receiver.arrival", { publication: record, delayMs });
  if (receiverMode === "unavailable") { res.destroy(); return; }
  await delay(delayMs);
  if (record.kind === "plugin.init") currentInstances.set(record.directory, record.instance);
  const key = `${record.instance}:${record.sessionID ?? "instance"}`;
  const accepted = currentInstances.get(record.directory) === record.instance && record.sequence > (lastSequence.get(key) ?? 0);
  if (accepted) {
    lastSequence.set(key, record.sequence);
    if (record.kind === "shell.bootstrap") evidence.add(`${record.instance}:opencode:${record.sessionID}`);
  }
  trace("receiver.applied", { publication: record, accepted, arrival: received.receipt });
  res.end(JSON.stringify({ accepted }));
});
env.SPIKE_SINK = sink.url;
env.SPIKE_COMMAND_SINK = sink.url;
const attempts = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const lastUser = messages.findLastIndex((m) => m.role === "user");
  const content = JSON.stringify(messages[lastUser]?.content ?? "");
  const scenario = content.match(/SPIKE:([a-z-]+)/)?.[1] ?? "finish";
  const usedTool = messages.slice(lastUser + 1).some((m) => m.role === "tool");
  const count = (attempts.get(scenario) ?? 0) + 1;
  attempts.set(scenario, count);
  trace("model.request", { scenario, usedTool, count, tools: payload.tools?.map((t) => t.function?.name) });
  if (scenario === "retry" && count === 1) {
    res.writeHead(503, { "content-type": "application/json", "retry-after-ms": "150" });
    res.end(JSON.stringify({ error: { message: "fixture retry", type: "server_error" } })); return;
  }
  let tool;
  if (!usedTool && scenario !== "finish") {
    if (scenario === "foreground" || scenario === "background") {
      tool = { name: "task", arguments: JSON.stringify({ description: "Fixture child", prompt: "SPIKE:child", subagent_type: "general", background: scenario === "background" }) };
    } else {
      const duration = scenario === "interrupt" ? 5000 : scenario === "client-detach" ? 1200 : scenario === "child" ? 900 : scenario === "a" ? 700 : 300;
      tool = { name: "bash", arguments: JSON.stringify({ command: `node ${commandScript} ${duration}`, description: "Report fixture identity and cwd", workdir: scenario === "location" ? other : fixture }) };
    }
  }
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish_reason = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason }] }) + "\n\n");
  if (tool) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${scenario}_${count}`, type: "function", function: tool }] });
  else chunk({ role: "assistant", content: "Fixture complete." });
  chunk({}, tool ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});
const configPath = path.join(env.OPENCODE_CONFIG_DIR, "opencode.json");
const config = {
  $schema: "https://opencode.ai/config.json", model: "fixture/fixture", small_model: "fixture/fixture",
  enabled_providers: ["fixture"], plugin: [`file://${env.OPENCODE_CONFIG_DIR}/probe.mjs`],
  provider: { fixture: { npm: "@ai-sdk/openai-compatible", name: "Local fixture", options: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", limit: { context: 16000, output: 2000 }, tool_call: true } } } },
  permission: "allow", share: "disabled", snapshot: false, autoupdate: false, lsp: false,
};
writeFileSync(configPath, JSON.stringify(config));

let backend;
let backendURL;
const launch = async () => {
  backendURL = undefined;
  backend = spawn(binary, ["serve", "--hostname", "127.0.0.1", "--port", "0"], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let output = "";
  const read = (chunk) => { output += chunk.toString(); };
  backend.stdout.on("data", read); backend.stderr.on("data", read);
  for (let i = 0; i < 150; i++) {
    const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
    if (match) { backendURL = match[0]; break; }
    if (backend.exitCode !== null) throw new Error(`backend exited: ${output.slice(-3000)}`);
    await delay(100);
  }
  assert(backendURL, `backend startup timeout: ${output.slice(-3000)}`);
  trace("action.backend-start", { pid: backend.pid });
};
const api = async (method, route, data, directory = fixture) => {
  const response = await fetch(backendURL + route, { method,
    headers: { "content-type": "application/json", "x-opencode-directory": directory },
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(20000) });
  const raw = await response.text();
  assert(response.ok, `${method} ${route}: ${response.status} ${raw.slice(0,700)}`);
  return raw ? JSON.parse(raw) : null;
};
const prompt = (id, scenario) => api("POST", `/session/${id}/message`, { model: { providerID: "fixture", modelID: "fixture" }, parts: [{ type: "text", text: `SPIKE:${scenario}` }] });
const waitFor = async (predicate, label, timeout = 15000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(25); }
  throw new Error(`Timed out: ${label}`);
};
const stop = async (signal = "SIGTERM") => {
  const done = once(backend, "exit"); backend.kill(signal);
  const [code, exitSignal] = await done;
  trace("action.backend-exit", { pid: backend.pid, code, signal: exitSignal });
};
const publications = () => records.filter((r) => r.kind === "receiver.applied" && r.accepted).map((r) => r.publication);
const commands = () => records.filter((r) => r.kind === "command" && r.phase === "start");
const replay = async (publication, label) => {
  trace("action.replay", { label, instance: publication.instance, sequence: publication.sequence });
  const response = await fetch(sink.url + "/publish", { method: "POST", body: JSON.stringify(publication) });
  assert.equal((await response.json()).accepted, false);
};
const clients = [];
const cliClients = [];
const attachCLI = (id, scenario) => {
  const child = spawn(binary, ["run", "--attach", backendURL, "--dir", fixture, "--session", id,
    "--model", "fixture/fixture", "--format", "json", `SPIKE:${scenario}`], { cwd: fixture, env, stdio: "ignore" });
  cliClients.push(child);
  trace("action.cli-attach", { sessionID: id, pid: child.pid, backendPID: backend.pid });
  return child;
};
const attach = async (label) => {
  const controller = new AbortController();
  const response = await fetch(backendURL + "/event", { headers: { "x-opencode-directory": fixture }, signal: controller.signal });
  assert(response.ok);
  const reader = response.body.getReader();
  await reader.read();
  trace("action.client-attach", { label, pid: backend.pid });
  const connection = { controller, reader };
  clients.push(connection);
  return connection;
};
const detach = async (connection, label) => {
  connection.controller.abort();
  await connection.reader.cancel().catch(() => {});
  trace("action.client-detach", { label, pid: backend.pid });
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE_"))), fixture, other,
    sourceSHA256: Object.fromEntries(["run.mjs", "plugin.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });
  receiverDelay = 100;
  receiverDelayKinds = new Set(["plugin.init", "shell.bootstrap"]);
  trace("action.bootstrap-delay", { milliseconds: receiverDelay });
  await launch();
  const a = await api("POST", "/session", { title: "Fixture A" });
  const b = await api("POST", "/session", { title: "Fixture B" });
  trace("action.sessions", { a: a.id, b: b.id, directoryA: a.directory, directoryB: b.directory });
  const clientA = await attach("A");
  await attach("B");
  await Promise.all([prompt(a.id, "a"), prompt(b.id, "b")]);
  assert.deepEqual(new Set(commands().map((r) => r.claim)), new Set([`opencode:${a.id}`, `opencode:${b.id}`]));
  const ends = records.filter((r) => r.kind === "command" && r.phase === "end");
  assert(Math.max(...commands().map((r) => r.receiptTime)) < Math.min(...ends.map((r) => r.receiptTime)), "Commands must overlap");
  assert(commands().every((r) => r.evidence && r.bootstrapAck === "true"));
  assert.equal(new Set(publications().map((r) => r.pid)).size, 1);
  receiverDelay = 0;
  receiverDelayKinds = undefined;
  await prompt(a.id, "location");
  assert.equal(commands().at(-1).cwd, other);
  assert.equal(commands().at(-1).claim, `opencode:${a.id}`);
  assert.equal(publications().findLast((r) => r.kind === "shell.bootstrap").sessionDirectory, fixture);
  trace("action.location-after", { sessionID: a.id, directory: (await api("GET", `/session/${a.id}`)).directory });
  await detach(clientA, "A");
  await delay(150);
  assert.equal((await api("GET", `/session/${a.id}`)).id, a.id);
  await attach("A-reconnected");
  await prompt(a.id, "reconnect");
  const beforeDetach = records.length;
  const attached = attachCLI(a.id, "client-detach");
  await waitFor(() => records.slice(beforeDetach).some((r) => r.kind === "command" && r.phase === "start"), "attached CLI command");
  const detachedCommand = commands().at(-1);
  const clientExited = once(attached, "exit");
  attached.kill("SIGTERM");
  await clientExited;
  trace("action.cli-detach", { sessionID: a.id, pid: attached.pid, backendPID: backend.pid });
  await waitFor(() => records.slice(beforeDetach).some((r) => r.kind === "command" && r.pid === detachedCommand.pid && r.phase === "end"), "backend continues after client exit");
  await delay(250);
  const reattached = attachCLI(a.id, "client-reconnect");
  const [clientCode] = await once(reattached, "exit");
  assert.equal(clientCode, 0);
  trace("action.cli-reconnected", { sessionID: a.id, pid: reattached.pid, backendPID: backend.pid });
  const fork = await api("POST", `/session/${a.id}/fork`, {});
  assert.notEqual(fork.id, a.id);
  trace("action.fork", { origin: a.id, sessionID: fork.id, parentID: fork.parentID, directory: fork.directory });
  await prompt(fork.id, "fork");
  await prompt(a.id, "foreground");
  await prompt(b.id, "background");
  await delay(1600);
  await prompt(a.id, "retry");
  const start = records.length;
  const interrupted = prompt(a.id, "interrupt");
  await waitFor(() => records.slice(start).some((r) => r.kind === "command" && r.phase === "start"), "interrupt command start");
  trace("action.abort", { sessionID: a.id });
  await api("POST", `/session/${a.id}/abort`);
  await interrupted;
  await prompt(a.id, "resume");
  await waitFor(() => publications().some((r) => r.sessionID === a.id && r.activity === "retry"), "native retry");

  trace("action.pty-create");
  const pty = await api("POST", "/pty", { command: "/bin/sh", args: ["-c", "sleep 1"], cwd: fixture });
  await waitFor(() => publications().some((r) => r.kind === "shell.identity-missing"), "PTY absent identity");
  await api("DELETE", `/pty/${pty.id}`);

  receiverDelay = 100;
  trace("action.receiver-delay", { milliseconds: receiverDelay });
  const delayed = await api("POST", "/session", { title: "Delayed first command" });
  await Promise.all([prompt(delayed.id, "delayed"), prompt(b.id, "ordered")]);
  await delay(1500);
  assert(commands().filter((r) => r.claim === `opencode:${delayed.id}`).every((r) => r.evidence && r.bootstrapAck === "true"));
  receiverDelay = 0;
  const oldBusy = publications().find((r) => r.sessionID === delayed.id && r.activity === "busy");
  const latestIdle = publications().findLast((r) => r.sessionID === delayed.id && r.activity === "idle");
  assert(latestIdle);
  await replay(latestIdle, "duplicate idle");
  await replay(oldBusy, "stale busy after idle");

  receiverMode = "unavailable";
  trace("action.receiver-unavailable");
  const failed = await api("POST", "/session", { title: "Unavailable receiver" });
  const failedStart = Date.now();
  await prompt(failed.id, "unavailable");
  const failedCommand = commands().find((r) => r.claim === `opencode:${failed.id}`);
  assert(failedCommand && !failedCommand.evidence && failedCommand.bootstrapAck === "false");
  trace("action.failure-completed", { sessionID: failed.id, milliseconds: Date.now() - failedStart });
  receiverMode = "normal";
  await delay(300);

  receiverDelay = 600;
  trace("action.receiver-timeout", { milliseconds: receiverDelay });
  const timed = await api("POST", "/session", { title: "Timed receiver" });
  const timedStart = Date.now();
  await prompt(timed.id, "timed");
  const timedCommand = commands().find((r) => r.claim === `opencode:${timed.id}`);
  assert(timedCommand && !timedCommand.evidence && timedCommand.bootstrapAck === "false");
  trace("action.timeout-completed", { sessionID: timed.id, milliseconds: Date.now() - timedStart });
  receiverDelay = 0;
  await delay(1500);

  const oldBootstrap = publications().findLast((r) => r.kind === "shell.bootstrap" && r.sessionID === a.id);
  trace("action.dispose", { pid: backend.pid });
  await api("POST", "/instance/dispose");
  await waitFor(() => publications().some((r) => r.kind === "plugin.dispose"), "plugin disposal");
  const resumed = await api("GET", `/session/${a.id}`);
  assert.equal(resumed.id, a.id);
  trace("action.reload", { sessionID: resumed.id, directory: resumed.directory, pid: backend.pid });
  await prompt(a.id, "reload");
  assert.notEqual(commands().at(-1).instance, oldBootstrap.instance);
  await replay(oldBootstrap, "retired publisher after replacement");

  trace("action.plugin-remove", { pid: backend.pid });
  await api("PATCH", "/global/config", { plugin: [] });
  await api("POST", "/instance/dispose");
  await prompt(a.id, "observation-loss");
  assert.equal(commands().at(-1).claim, null);
  trace("action.observation-loss", { sessionID: a.id, pid: backend.pid, sessionSurvived: (await api("GET", `/session/${a.id}`)).id === a.id });
  await api("PATCH", "/global/config", { plugin: config.plugin });
  await api("POST", "/instance/dispose");
  await prompt(a.id, "restored");
  assert.equal(commands().at(-1).claim, `opencode:${a.id}`);

  trace("action.delete", { sessionID: fork.id });
  await api("DELETE", `/session/${fork.id}`);
  await waitFor(() => publications().some((r) => r.kind === "session.deleted" && r.sessionID === fork.id), "conversation deletion");
  await delay(300);
  const previousPID = backend.pid;
  await stop();
  await launch();
  const restarted = await api("GET", `/session/${a.id}`);
  assert.equal(restarted.id, a.id);
  trace("action.restart-resume", { sessionID: a.id, directory: restarted.directory, oldPID: previousPID, pid: backend.pid });
  await prompt(a.id, "restart");
  await delay(300);
  await stop("SIGKILL");
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const child of cliClients) if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
  for (const connection of clients) connection.controller.abort();
  if (backend && backend.exitCode === null && backend.signalCode === null) await stop();
  if (existsSync(env.SPIKE_DIAGNOSTICS)) {
    for (const line of readFileSync(env.SPIKE_DIAGNOSTICS, "utf8").trim().split("\n")) if (line) trace("publisher.diagnostic", { publication: JSON.parse(line) });
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
