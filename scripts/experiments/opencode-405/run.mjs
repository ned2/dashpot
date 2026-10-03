// Measurement run for Issue #405: what the rewritten OpenCode plugin relies
// on that ADR 0090 asks to be measured first. It drives OpenCode 2.0.22's
// shared service against a loopback OpenAI-compatible model fixture, in
// disposable configuration and state, with a private service port, so the
// operator's own OpenCode service is never contacted; then it loads the same
// plugin module into an OpenCode 1.18.30 server. A throwaway plugin
// (plugin.mjs) records its instances, the registry they share, every session
// event's envelope, `ctx.session.get` answers and the shells it prepares; the
// shells (command.mjs) report their identity variables. Dashpot is not
// involved. The verifier checks the trace against the spike's claims.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode 2.0.22 binary> <absolute opencode 1.18.30 binary> > log 2>&1
// It is done when it prints "All scenarios completed". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
// A harness above the runner would be an ancestor of every process the run
// starts, so the runner refuses to start below one; `setsid -f` detaches it.
const above = [];
for (let pid = process.ppid; pid > 1 && above.length < 64;) { try { const entry = describe(pid); above.push(entry); pid = entry.ppid; } catch { break; } }
const host = above.find((entry) => /^(claude|codex|opencode|opencode2|opencode\.exe)$/.test(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const [binary, v1Binary] = process.argv.slice(2);
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the OpenCode 2.0.22 binary");
assert(v1Binary && path.isAbsolute(v1Binary), "Pass the absolute path to the OpenCode 1.18.30 binary");

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-405-"));
console.log(`Isolated fixture: ${root}`);
// A Repository with one linked Worktree, a second Repository, and a
// directory in no Repository at all.
const fixture = path.join(root, "repository");
const treeA = path.join(root, "repository.worktrees", "a");
const other = path.join(root, "other");
const plain = path.join(root, "plain");
const tracePath = path.join(root, "trace.jsonl");
const pluginLog = path.join(root, "plugin.jsonl");
const probeFile = path.join(root, "probe.json");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const retained = (text) => text.replaceAll(path.dirname(binary), "$BINARY_DIR").replaceAll(path.dirname(v1Binary), "$V1_BINARY_DIR")
  .replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT")
  .replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const sha256 = (file) => !existsSync(file) ? null : createHash("sha256").update(readFileSync(file)).digest("hex");

const fixtureEnv = (name) => {
  const base = path.join(root, name);
  return {
    HOME: path.join(base, "home"),
    XDG_CONFIG_HOME: path.join(base, "config"),
    XDG_DATA_HOME: path.join(base, "data"),
    XDG_CACHE_HOME: path.join(base, "cache"),
    XDG_STATE_HOME: path.join(base, "state"),
    TMPDIR: path.join(base, "tmp"),
    SHELL: "/bin/bash",
    LANG: "C.UTF-8",
    OPENCODE_DISABLE_AUTOUPDATE: "1",
    OPENCODE_DISABLE_MODELS_FETCH: "1",
    OPENCODE_DISABLE_PROJECT_CONFIG: "1",
    // Nothing but loopback is reachable.
    HTTP_PROXY: "http://127.0.0.1:9", HTTPS_PROXY: "http://127.0.0.1:9", http_proxy: "http://127.0.0.1:9", https_proxy: "http://127.0.0.1:9",
    NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
    SPIKE_STOP_PID: String(process.pid),
  };
};
// The v2 and v1 fixtures keep separate configuration and state, so neither
// release ever reads the other's database.
const env = fixtureEnv("v2");
const v1Env = fixtureEnv("v1");
const bin = path.join(env.HOME, ".opencode", "bin");
const v1Bin = path.join(v1Env.HOME, ".opencode", "bin");
for (const dir of [fixture, other, plain, bin, v1Bin, ...[env, v1Env].flatMap((item) => [item.XDG_DATA_HOME, item.XDG_CACHE_HOME, item.XDG_STATE_HOME, item.TMPDIR])]) mkdirSync(dir, { recursive: true });
const place = (source, target) => { try { linkSync(source, target); } catch { execFileSync("cp", [source, target]); } chmodSync(target, 0o755); };
place(binary, path.join(bin, "opencode"));
place(v1Binary, path.join(v1Bin, "opencode"));
const basePath = `${path.dirname(process.execPath)}:/usr/bin:/bin`;
env.PATH = `${bin}:${basePath}`;
v1Env.PATH = `${v1Bin}:${basePath}`;
const version = execFileSync("opencode", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "opencode v2.0.22", `unexpected OpenCode version: ${version}`);
const v1Version = execFileSync("opencode", ["--version"], { env: v1Env, encoding: "utf8" }).trim();
assert.equal(v1Version, "1.18.30", `unexpected OpenCode v1 version: ${v1Version}`);

const repository = (directory) => {
  const git = (...args) => execFileSync("git", ["-C", directory, ...args], { env, stdio: "pipe" });
  writeFileSync(path.join(directory, "README.md"), "Disposable fixture.\n");
  git("init", "--initial-branch=main");
  git("add", ".");
  git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
  return git;
};
repository(fixture)("worktree", "add", "-b", "a", treeA);
repository(other);
writeFileSync(path.join(plain, "README.md"), "In no Repository.\n");

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
env.SPIKE_SINK = v1Env.SPIKE_SINK = sink.url;

// The fixture model: a `PROBE:<label>` text in the latest user turn selects a
// tool sequence, and the turn ends once every step has a tool result. A label
// with no sequence runs one shell command of that name. v2 names its shell
// tool `shell` and its delegation tool `subagent`; v1 names them `bash` and
// `task`.
const commandScript = path.join(here, "command.mjs");
const sequences = {
  delegate: (v1) => [v1
    ? { name: "task", arguments: { description: "Fixture child", prompt: "PROBE:child", subagent_type: "general" } }
    : { name: "subagent", arguments: { agent: "general", description: "Fixture child", prompt: "PROBE:child" } }],
};
const toolRequests = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const lastUser = messages.findLastIndex((message) => message.role === "user");
  const content = JSON.stringify(messages[lastUser]?.content ?? "");
  const label = content.match(/PROBE:([a-z0-9-]+)/)?.[1] ?? null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const v1 = tools.includes("bash");
  const titled = /title generator/i.test(system) || !tools.length;
  const step = messages.slice(lastUser + 1).filter((message) => message.role === "tool").length;
  const count = titled ? 0 : (toolRequests.get(label) ?? 0) + 1;
  if (!titled) toolRequests.set(label, count);
  const shellCall = { name: v1 ? "bash" : "shell", arguments: { command: `node ${commandScript} ${label} 0`, ...(v1 ? { description: "Fixture step" } : {}) } };
  const sequence = (label && (sequences[label]?.(v1) ?? [shellCall])) || [];
  const tool = titled ? undefined : sequence[step];
  trace("model.request", { label, step, tool: tool?.name ?? null, count, titled, v1 });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (tool) chunk({ role: "assistant", tool_calls: [{ index: 0, id: `call_${label}_${step}_${count}`, type: "function", function: { name: tool.name, arguments: JSON.stringify(tool.arguments) } }] });
  else chunk({ role: "assistant", content: titled ? "Fixture title" : "Fixture complete." });
  chunk({}, tool ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The v2 configuration: the fixture model only, every tool allowed, the
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
const pluginSource = readFileSync(path.join(here, "plugin.mjs"), "utf8").replace("__SPIKE_LOG__", pluginLog).replace("__SPIKE_PROBE__", probeFile);
const pluginFile = path.join(configHome, "plugins", "dashpot.js");
writeFileSync(pluginFile, pluginSource);
writeFileSync(probeFile, "[]");

// --- Observation -------------------------------------------------------------

const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`SPIKE_STOP_PID=${process.pid}\0`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
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
const settle = (ms = 1500) => delay(ms);

// --- The v2 service ------------------------------------------------------------

const registration = () => { try { return JSON.parse(readFileSync(path.join(env.XDG_STATE_HOME, "opencode", "service.json"), "utf8")); } catch { return null; } };
const service = { url: `http://127.0.0.1:${servicePort}` };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
const api = async (method, route, data, { directory, allow = false } = {}) => {
  const headers = { "content-type": "application/json", authorization };
  if (directory) headers["x-opencode-directory"] = encodeURIComponent(directory);
  const response = await fetch(service.url + route, { method, headers, body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  if (!allow) assert(response.ok, `${method} ${route}: ${response.status} ${raw.slice(0, 700)}`);
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = raw.slice(0, 500); }
  return allow ? { status: response.status, body: parsed } : parsed;
};
const unwrap = (value) => value?.data ?? value;
const cli = (args, { cwd = fixture } = {}) => {
  const result = spawnSync("opencode", args, { cwd, env: { ...env, PWD: cwd }, encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const startService = async (label) => {
  trace("service.start", { label, ...cli(["service", "start"]) });
  let info = null;
  await waitFor(() => (info = registration()) && alive(info.pid), `${label}: service registered`, 60000);
  let ready = false;
  for (let attempt = 0; attempt < 200 && !ready; attempt++) {
    ready = (await api("GET", "/api/info", undefined, { allow: true }).catch(() => null))?.status === 200;
    if (!ready) await delay(100);
  }
  assert(ready, `${label}: service never ready`);
  service.pid = info.pid;
  trace("service", { label, pid: info.pid, version: info.version ?? null });
};
const session = async (title, directory) => {
  const made = unwrap(await api("POST", "/api/session", { title, location: { directory }, model: { id: "fixture", providerID: "loop" } }));
  trace("session", { title, sessionID: made.id, directory: made.location?.directory ?? null, parentID: made.parentID ?? null });
  return made.id;
};
const prompt = async (id, label) => {
  const started = Date.now();
  await api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}` });
  const waited = await api("POST", `/api/experimental/session/${id}/wait`, {}, { allow: true });
  trace("turn", { sessionID: id, label, ms: Date.now() - started, wait: waited.status });
};
const info = async (id) => {
  const answer = await api("GET", `/api/session/${id}`, undefined, { allow: true });
  return answer.status === 200 ? unwrap(answer.body) : { missing: answer.status, body: answer.body };
};
const move = async (id, directory, label) => {
  trace("move", { label, sessionID: id, to: directory, ...(await api("POST", `/api/session/${id}/move`, { directory }, { allow: true })) });
  await settle();
  const after = await info(id);
  trace("session.info", { label, sessionID: id, location: after.location?.directory ?? null, parentID: after.parentID ?? null });
};
const instances = () => records.filter((record) => record.kind === "plugin.setup").length;
const reload = async (label, how) => {
  const before = instances();
  trace("mark", { label });
  if (how === "edit") writeFileSync(pluginFile, pluginSource + `\n// ${label}\n`);
  else trace("reload", cli(["reload"]));
  await waitFor(() => instances() > before, `${label}: instances set up again`, 30000);
  await settle(2500);
};

const scenarios = (process.env.SPIKE_SCENARIOS ?? "registry,subagent,fork,moves,recovery,v1").split(",");
const known = {};
try {
  trace("environment", { version, v1Version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), v1Binary, v1BinarySHA256: sha256(v1Binary), servicePort, fixture, treeA, other, plain, scenarios,
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    sourceSHA256: Object.fromEntries(["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs", "plugin.mjs"].map((file) => [file, sha256(path.join(here, file))])) });
  await startService("start");

  // Scenario 1: one session per Worktree, then a plugin file edit and
  // `opencode reload`, each followed by more work.
  if (scenarios.includes("registry")) {
    trace("scenario", { name: "registry" });
    known.main = await session("Main", fixture);
    known.a = await session("A", treeA);
    await prompt(known.main, "registry-main");
    await prompt(known.a, "registry-a");
    await reload("hot-reload", "edit");
    await prompt(known.main, "after-hot-reload");
    await reload("cli-reload", "cli");
    await prompt(known.a, "after-cli-reload");
  }

  // Scenario 2: a synchronous Sub-agent, whose events carry its own session.
  if (scenarios.includes("subagent")) {
    trace("scenario", { name: "subagent" });
    known.parent = await session("Parent", fixture);
    await prompt(known.parent, "delegate");
    await settle();
  }

  // Scenario 3: a fork of a session with history, then a turn in the fork.
  if (scenarios.includes("fork")) {
    trace("scenario", { name: "fork" });
    known.source = await session("Source", fixture);
    await prompt(known.source, "fork-source");
    const forked = await api("POST", `/api/session/${known.source}/fork`, {}, { allow: true, directory: fixture });
    known.fork = unwrap(forked.body)?.id ?? null;
    trace("fork", { status: forked.status, source: known.source, sessionID: known.fork, parentID: unwrap(forked.body)?.parentID ?? null,
      fork: unwrap(forked.body)?.fork ?? null });
    await settle();
    if (known.fork) await prompt(known.fork, "fork-turn");
  }

  // Scenario 4: a session moved within its Repository, to another
  // Repository, outside every Repository, and back, with a turn after each.
  if (scenarios.includes("moves")) {
    trace("scenario", { name: "moves" });
    known.mover = await session("Mover", fixture);
    await prompt(known.mover, "move-start");
    for (const [label, directory] of [["move-worktree", treeA], ["move-other", other], ["move-plain", plain], ["move-back", fixture]]) {
      await move(known.mover, directory, label);
      await prompt(known.mover, `after-${label}`);
    }
  }

  // Scenario 5: recovery on registration. A deleted session, a live one and
  // an ID OpenCode never issued, each read by every instance set up after.
  if (scenarios.includes("recovery")) {
    trace("scenario", { name: "recovery" });
    known.live = await session("Live", treeA);
    known.gone = await session("Gone", treeA);
    await prompt(known.gone, "before-delete");
    trace("delete", { sessionID: known.gone, ...(await api("DELETE", `/api/session/${known.gone}`, undefined, { allow: true })) });
    await settle();
    known.never = known.live.slice(0, -4) + (known.live.endsWith("0000") ? "1111" : "0000");
    trace("probe", { live: known.live, gone: known.gone, never: known.never });
    writeFileSync(probeFile, JSON.stringify([known.live, known.gone, known.never]));
    await reload("recovery-reload", "cli");
    writeFileSync(probeFile, "[]");
  }

  // Scenario 6: the same module under OpenCode 1.18.30: its `server` entry
  // is called, and a model-driven shell carries the refusal variable.
  if (scenarios.includes("v1")) {
    trace("scenario", { name: "v1" });
    const v1Config = path.join(v1Env.XDG_CONFIG_HOME, "opencode");
    mkdirSync(path.join(v1Config, "plugins"), { recursive: true });
    writeFileSync(path.join(v1Config, "opencode.json"), JSON.stringify({
      $schema: "https://opencode.ai/config.json", model: "fixture/fixture", small_model: "fixture/fixture", enabled_providers: ["fixture"],
      provider: { fixture: { npm: "@ai-sdk/openai-compatible", name: "Local fixture", options: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
        models: { fixture: { name: "Fixture", limit: { context: 16000, output: 2000 }, tool_call: true } } } },
      permission: "allow", share: "disabled", snapshot: false, autoupdate: false, lsp: false,
    }, null, 2));
    writeFileSync(path.join(v1Config, "plugins", "dashpot.js"), pluginSource);
    const child = spawn("opencode", ["serve", "--hostname", "127.0.0.1", "--port", "0", "--print-logs"], { cwd: fixture, env: v1Env, stdio: ["ignore", "pipe", "pipe"] });
    let output = "";
    child.stdout.on("data", (chunk) => { output += chunk; });
    child.stderr.on("data", (chunk) => { output += chunk; });
    let url = null;
    await waitFor(() => (url = output.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0] ?? null), "v1 server listening", 30000);
    const v1Api = async (method, route, data) => {
      const response = await fetch(url + route, { method, headers: { "content-type": "application/json", "x-opencode-directory": fixture },
        body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(90000) });
      const raw = await response.text();
      assert(response.ok, `v1 ${method} ${route}: ${response.status} ${raw.slice(0, 700)}`);
      return raw ? JSON.parse(raw) : null;
    };
    const made = await v1Api("POST", "/session", { title: "V1" });
    trace("session", { title: "V1", sessionID: made.id, directory: made.directory });
    await v1Api("POST", `/session/${made.id}/message`, { model: { providerID: "fixture", modelID: "fixture" }, parts: [{ type: "text", text: "PROBE:v1-shell" }] });
    await waitFor(() => command("v1-shell"), "v1 shell", 30000);
    child.kill("SIGTERM");
    await once(child, "exit");
    const lines = output.split("\n");
    trace("v1.logs", { pluginLines: lines.filter((line) => /plugin/i.test(line)).map(retained).slice(0, 40),
      failures: lines.filter((line) => /fail|error/i.test(line) && /plugin/i.test(line)).map(retained).slice(0, 20) });
  }
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
} finally {
  if (service.pid && alive(service.pid)) {
    trace("service.stop", cli(["service", "stop"]));
    try { await waitFor(() => !alive(service.pid), "final service exit", 10000); } catch {}
  }
  await delay(1000);
  drainPlugin();
  clearInterval(sampler);
  for (const entry of fixtureProcesses()) {
    if (entry.pid === process.pid) continue;
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
  process.exit(0);
}
