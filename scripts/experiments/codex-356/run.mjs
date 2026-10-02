// Real-adapter acceptance run for Issue #356: drives a pinned Codex CLI
// against a loopback Responses API fixture with an isolated CODEX_HOME, whose
// daemon updater is off, and Dashpot's own Codex hook publisher, in a
// disposable Dashpot Project whose Issues are Local Issue Markdown. It
// measures what a managed daemon's SessionEnd hooks see on an idle unload, a
// `daemon restart` and a `daemon stop` (when Codex kills the hook, when the
// daemon exits, whether a detached process outlives both), and checks
// Dashpot's answer through the real publisher and its settler: an unload
// ends the run; a restart or stop, even one that first drains a running
// turn, leaves it an Orphaned Agent Run that `work start` recovers; a thread
// the restart reloaded unloads from the replacement; and an `exec` exit or a
// standalone `/exit` ends its run at once. Everything is recorded as a
// metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";
import { connectUnixWebSocket } from "./uds-websocket.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.160.0";
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every Codex and Claude Code session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-356-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const worktrees = { main: fixture, other };
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory and host name never enter the trace; a
// hook's or shell's ancestry keeps the processes up to the runner's own child.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, JSON.stringify(kept).replaceAll(home, "~").replace(hostName, "<host>") + "\n");
  return record;
};

const env = {
  PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  // Dashpot's machine-local state, like Codex's, stays inside the fixture.
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  SPIKE_PUBLISHER: publisher,
  SPIKE_DASHPOT: dashpotCommand,
  SPIKE_MODE_FILE: path.join(root, "hook-mode.json"),
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
// What the hook wrapper does beyond publishing: `watchHost` starts a detached
// waiter on SessionEnd, `sessionEndHoldMs` holds the SessionEnd hook.
const hookMode = (mode) => { writeFileSync(env.SPIKE_MODE_FILE, JSON.stringify(mode)); trace("hook.mode", { mode }); };
hookMode({});
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: six Local Issue Markdown Issues, the main
// working tree, and one linked Worktree.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2, 3, 4, 5, 6]) {
  const metadata = { id: `I_fixture_${number}`, number, reference: `fixture-${number}`, state: "open", stateReason: null, labels: [], assignees: [], author: null,
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${number}.md`), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue ${number}\n\nDisposable.\n`);
}
const dashpot = (args, cwd = fixture) => {
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "other", other);

const listen = async (handler) => {
  const server = http.createServer(async (req, res) => {
    try { await handler(req, res); } catch (error) {
      trace("server.error", { path: req.url, error: String(error?.stack ?? error) });
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
// Hooks, beats and waiters name their own kind; shells post to /command.
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const posted = await body(req);
  trace(url.pathname === "/hook" ? posted.kind ?? "hook" : "command", posted);
  res.end("{}");
});
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
env.SPIKE_SINK = sink.url;

// The fixture model: `SPIKE:<label> hold=<ms> work=<start-N|show|stop>` in
// the latest user message selects one exec_command call reporting identity
// and running that `dashpot work` command; `busy hold=<ms>` instead holds the
// model's own response for that long, so the turn is running with no command;
// a request already holding the tool output ends the turn.
const commandScript = path.join(here, "command.mjs");
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/responses")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  const input = payload.input ?? [];
  let label = null;
  let latestUser = -1;
  input.forEach((item, index) => {
    if (item.type !== "message" || item.role !== "user") return;
    for (const part of Array.isArray(item.content) ? item.content : []) {
      const match = part.type === "input_text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?(?: work=([a-z0-9-]+))?/);
      if (match) { label = { name: match[1], hold: match[2] ?? "200", work: match[3] ?? "-" }; latestUser = index; }
    }
  });
  const outputs = input.slice(latestUser + 1).filter((item) => item.type === "function_call_output");
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => `${tool.name}/${nested.name}`) : [tool.name ?? tool.type]);
  const busy = label?.name === "busy";
  const useTool = label && !busy && outputs.length < 1 && tools.includes("exec_command");
  trace("model.request", { label: label?.name ?? null, outputs: outputs.length, busy });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  if (busy) {
    const until = Date.now() + Number(label.hold);
    while (Date.now() < until && !req.socket.destroyed) await delay(100);
    trace("model.busy-released", { closed: req.socket.destroyed });
    if (req.socket.destroyed) return;
  }
  if (useTool) {
    sse(res, { type: "response.output_item.done", item: { type: "function_call", call_id: `call_${label.name}_${records.length}`, name: "exec_command",
      arguments: JSON.stringify({ cmd: `node ${commandScript} ${label.name} ${label.hold} ${label.work}`, login: false, yield_time_ms: 120000 }) } });
  } else {
    sse(res, { type: "response.output_item.done", item: { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: "Fixture complete." }] } });
  }
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The hook events `dashpot integrate codex` subscribes, each routed through
// the metadata wrapper to Dashpot's real publisher. The configured timeout is
// longer than any hold, so a hook Codex stops early was stopped by Codex's own
// clamp, not by this configuration.
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 30 }] }]])),
}, null, 2));
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-model"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"

[features]
hooks = true
# The curated plugin marketplace sync clones a GitHub repository at startup.
plugins = false
apps = false

[analytics]
enabled = false

[model_providers.fixture]
name = "Fixture"
base_url = "${model.url}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
${Object.values(worktrees).map((dir) => `\n[projects."${dir}"]\ntrust_level = "trusted"\n`).join("")}`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => {
  try { return JSON.parse(readFileSync(daemonSettingsPath, "utf8")); } catch (error) { return { unreadable: String(error) }; }
};

// Every process whose environment names the fixture CODEX_HOME: Codex's
// own, and the hooks, waiters and Dashpot settlers it started.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let entry;
    try { entry = describe(Number(name)); } catch { continue; }
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`)) continue;
    if (entry.pid === process.pid) continue;
    found.push(entry);
  }
  return found;
};
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.replaceAll(root, "<root>").replace(/ settle \{.*$/, " settle {…}").slice(0, 240)];
// The managed daemon: `codex app-server ... --managed-daemon`.
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const isSettler = (entry) => / -m dashpot\.hook settle /.test(entry.cmdline);
const daemons = () => fixtureProcesses().filter(isDaemon);
const settlers = () => fixtureProcesses().filter(isSettler);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const processes = (label) => trace("processes", { label, processes: fixtureProcesses().map(brief), daemons: daemons().map((entry) => entry.pid),
  daemonCmdlines: daemons().map((entry) => entry.cmdline.replaceAll(root, "<root>")), settlers: settlers().map((entry) => entry.pid),
  socketExists: existsSync(socketPath), daemonSettings: daemonSettings() });
const hooks = () => records.filter((record) => record.kind === "hook");
const hooksSince = (count) => hooks().slice(count);
const sessionEnds = (since, threads) => hooksSince(since).filter((record) => record.event === "SessionEnd" && threads.includes(record.payload.session_id));
const waiters = (since) => records.filter((record) => record.kind === "waiter" && record.receipt > since);
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const hostOf = (record) => record?.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
// Dashpot's settler decides within 10 s of the SessionEnd it was handed.
const SETTLE_MS = 13000;
const settled = async (label) => {
  await delay(SETTLE_MS);
  await quietly(waitFor(() => settlers().length === 0, `${label}: settlers exit`, 10000));
};

// Dashpot's published view of the fixture.
const view = (label, extra = {}) => {
  const ran = dashpot(["--compact-json"]);
  let parsed = null;
  try { parsed = JSON.parse(ran.stdout); } catch {}
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400),
    agentRuns: (parsed?.agentRuns ?? []).map((run) => ({ issueId: run.issueId, orphaned: run.orphaned, state: run.state, processOrSession: run.processOrSession,
      workingDirectory: run.workingDirectory, startedAt: run.startedAt, lastActivityAt: run.lastActivityAt })),
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })),
    ...extra });
};

// One-shot Codex commands (`exec`, `app-server daemon`).
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const began = Date.now();
  const child = spawn(binary, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const clean = (text) => stripAnsi(text).replaceAll(root, "<root>");
  // Only Codex's own status lines: never the prompt, the model's output, or
  // the commands it ran.
  const statusLines = (text) => clean(text).split("\n").filter((line) => /^(OpenAI Codex v|warning: |hook: |Installing |Error: )/.test(line)).join("\n");
  trace("codex.command", { label, args: args.map((arg) => arg.replaceAll(root, "<root>")), status, signal, began, ms: Date.now() - began,
    stdout: args[0] === "exec" ? null : clean(stdout).slice(-1200), stderr: statusLines(stderr).slice(-1200) });
  return { status, signal, stdout, stderr };
};
// When a process exits, polled every 25 ms from now.
const exitOf = (pid, timeout = 120000) => {
  const watch = { pid, exitedAt: null };
  watch.done = (async () => {
    const end = Date.now() + timeout;
    while (Date.now() < end) { if (!existsSync(`/proc/${pid}`)) { watch.exitedAt = Date.now(); return; } await delay(25); }
  })();
  return watch;
};

const freePort = async () => {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = probe.address().port;
  probe.close();
  return port;
};
// A JSON-RPC client over a WebSocket: loopback TCP, or the daemon's control
// socket, which speaks WebSocket over a Unix domain socket.
const rpcClient = async (name, socket) => {
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  const onMessage = (text) => {
    let parsed;
    try { parsed = JSON.parse(text); } catch { return; }
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method?.startsWith("thread/") || parsed.method?.startsWith("turn/")) {
      const { threadId, turn, status, thread } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id, status: status ?? turn?.status, receivedAt: Date.now() });
    }
  };
  socket.on(onMessage);
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-356-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: socket.transport, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, notifications, close: () => socket.close() };
};
const tcpClient = async (name, port) => {
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  return rpcClient(name, { transport: "loopback-websocket", on: (listener) => socket.addEventListener("message", (message) => listener(message.data)), send: (text) => socket.send(text), close: () => socket.close() });
};
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(socketPath);
  return rpcClient(name, { transport: "unix-websocket", on: (listener) => socket.on("message", listener), send: (text) => socket.send(text), close: () => socket.close() });
};
const startThread = async (client, cwd) => {
  const thread = (await client.call("thread/start", { cwd })).result?.thread;
  assert(thread?.id, "thread started");
  return thread.id;
};
const runTurn = async (client, threadId, text, options = {}) => {
  const hooksBefore = hooks().length;
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, status: started.result?.turn?.status ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, hooksBefore };
  await waitFor(() => client.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === turnId), `turn ${text} completed`, 60000);
  // The Stop hook publishes after the turn settles for its clients.
  await waitFor(() => hooksSince(hooksBefore).some((record) => record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000).catch(() => {});
  return { turnId, hooksBefore };
};

// An interactive terminal hosted by `script`; only the markers the runner
// waits for are kept from its screen.
const terminals = [];
const terminal = async (name, cwd, args) => {
  const child = spawn("script", ["-qfec", [binary, ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  // The composer treats a burst of keys as a paste, so Enter follows the text
  // after a pause.
  const handle = { name, child, exited: null,
    type: async (text) => { child.stdin.write(text); await delay(600); child.stdin.write("\r"); } };
  child.stdout.on("data", () => {});
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, cwd, args: args.map((arg) => arg.replaceAll(root, "<root>")), scriptPid: child.pid });
  return handle;
};
const exitTerminal = async (handle) => {
  await handle.type("/exit");
  if (!await quietly(waitFor(() => handle.exited, `${handle.name} exit`, 20000))) handle.child.kill("SIGTERM");
};
const shellSummary = (label) => {
  const shell = command(label);
  const work = command(label, "work")?.work ?? null;
  return shell && { label, cwd: shell.cwd, thread: shell.env.CODEX_THREAD_ID ?? null, host: hostOf(shell),
    work: work && { args: work.args, status: work.status, stdout: work.stdout.replaceAll(root, "<root>"), stderr: work.stderr.replaceAll(root, "<root>") } };
};
// Dashpot's Event Log at every Worktree: hook outcomes only, with the fields
// that say what Dashpot did and which process did it.
const eventLog = (label) => {
  const fields = ["time", "service.instance.id", "event.name", "dashpot.process.kind", "dashpot.agent_session.id", "dashpot.worktree.path", "dashpot.issue.id",
    "dashpot.hook.event", "dashpot.outcome.result", "dashpot.agent_session.state", "dashpot.work_store.change", "error.type"];
  const outcomes = [];
  for (const dir of Object.values(worktrees)) {
    const ran = dashpot(["events", "--json"], dir);
    let parsed = null;
    try { parsed = JSON.parse(ran.stdout); } catch {}
    for (const event of parsed?.events ?? []) {
      if (event["event.name"] !== "hook.outcome") continue;
      const kept = Object.fromEntries(fields.filter((field) => event[field] !== undefined && event[field] !== null).map((field) => [field, event[field]]));
      if (!outcomes.some((seen) => seen["service.instance.id"] === kept["service.instance.id"])) outcomes.push(kept);
    }
  }
  return trace("dashpot.events", { label, outcomes });
};

const scripts = ["run.mjs", "verify.mjs", "hook.mjs", "waiter.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["src/dashpot/hook.py", ...["deferred_end.py", "harnesses.py", "hook_publish.py", "work_reconciliation.py", "work_store.py", "liveness.py", "processes.py"]
  .map((file) => `src/dashpot/sessions/${file}`)];
let clients = [];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(os.homedir(), "~"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, dirty }, worktrees, hookEvents,
    // The runner's own scripts by name, and the modules it exercised by
    // repository path.
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  trace("scenario", { name: "hook-trust" });
  const port = await freePort();
  const trustServer = spawn(binary, ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let trustBanner = "";
  trustServer.stderr.on("data", (chunk) => { trustBanner += chunk; });
  trustServer.stdout.on("data", () => {});
  await waitFor(() => trustBanner.includes("listening on"), "trust server listening", 20000);
  const trust = await tcpClient("trust", port);
  const listed = await trust.call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await trust.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  trust.close();
  trustServer.kill("SIGTERM");
  await once(trustServer, "exit");
  await delay(500);
  processes("after-trust");

  // `codex exec` with no daemon running binds Issue 5; its SessionEnd ends
  // the run at once.
  trace("scenario", { name: "exec" });
  await codex(["exec", "-C", fixture, "SPIKE:exec work=start-5"], "exec", { timeout: 90000 });
  await delay(1500);
  trace("exec.outcome", { shell: shellSummary("exec") });
  processes("after-exec");
  view("after-exec");

  // A standalone terminal (autostart disabled, no daemon running) binds
  // Issue 6 in `other`; its `/exit` ends the run at once.
  trace("scenario", { name: "standalone-exit" });
  const ts = await terminal("standalone", other, ["--disable", "daemon_auto_start", "-C", other, "SPIKE:ts-start work=start-6"]);
  await waitFor(() => command("ts-start", "end") || ts.exited, "ts-start command", 90000);
  const tsThread = command("ts-start").env.CODEX_THREAD_ID;
  await waitFor(() => hooks().some((record) => record.event === "Stop" && record.payload.session_id === tsThread), "ts-start Stop", 30000);
  trace("standalone.identity", { shell: shellSummary("ts-start"), daemons: daemons().map((entry) => entry.pid) });
  view("standalone-bound");
  await exitTerminal(ts);
  await quietly(waitFor(() => hooks().some((record) => record.event === "SessionEnd" && record.payload.session_id === tsThread), "standalone SessionEnd", 10000));
  await delay(1500);
  processes("after-standalone-exit");
  view("after-standalone-exit");

  // The managed daemon, started from the pinned binary.
  trace("scenario", { name: "daemon-start" });
  const started = await codex(["app-server", "daemon", "start"], "daemon-start");
  assert.equal(started.status, 0, "daemon started");
  await waitFor(() => existsSync(socketPath) && daemons().length === 1, "daemon control socket", 30000);
  processes("daemon-started");
  const firstDaemon = daemons()[0].pid;

  // An idle unload: R3 (bound to Issue 3) and U1 (unbound) lose their last
  // client while R4 (bound to Issue 4) keeps one. Each SessionEnd hook holds
  // for 6 s and starts a waiter on the daemon.
  trace("scenario", { name: "unload" });
  const keeper = await daemonClient("keeper");
  clients.push(keeper);
  const r4 = await startThread(keeper, other);
  await runTurn(keeper, r4, "SPIKE:r4-start work=start-4");
  const leaving = await daemonClient("leaving");
  clients.push(leaving);
  const r3 = await startThread(leaving, fixture);
  await runTurn(leaving, r3, "SPIKE:r3-start work=start-3");
  const u1 = await startThread(leaving, fixture);
  await runTurn(leaving, u1, "SPIKE:u1-start");
  view("unload-bound");
  hookMode({ sessionEndHoldMs: 6000, watchHost: true });
  let since = records.length;
  let hooksBefore = hooks().length;
  leaving.close();
  clients = clients.filter((client) => client !== leaving);
  const leftAt = Date.now();
  await waitFor(() => sessionEnds(hooksBefore, [r3, u1]).length === 2, "R3 and U1 unload", 90000);
  await waitFor(() => waiters(since).length >= 2, "unload waiters report", 25000);
  await delay(1000);
  trace("unload.outcome", { leftAt, threads: { r3, u1, r4 }, firstDaemon });
  hookMode({});
  await settled("unload");
  processes("after-unload");
  view("after-unload");

  // `daemon restart` with R1 (Issue 1, main), R2 (Issue 2, other), U2
  // (unbound) and R4 loaded; the hooks run Dashpot's publisher only, and a
  // waiter watches the old daemon.
  trace("scenario", { name: "restart" });
  const r1 = await startThread(keeper, fixture);
  await runTurn(keeper, r1, "SPIKE:r1-start work=start-1");
  const r2 = await startThread(keeper, other);
  await runTurn(keeper, r2, "SPIKE:r2-start work=start-2");
  const u2 = await startThread(keeper, fixture);
  await runTurn(keeper, u2, "SPIKE:u2-start");
  trace("restart.loaded", { loaded: (await keeper.call("thread/loaded/list", {})).result?.data ?? [], threads: { r1, r2, u2, r4 } });
  view("restart-bound");
  hookMode({ watchHost: true });
  keeper.close();
  clients = [];
  await delay(300);
  since = records.length;
  hooksBefore = hooks().length;
  const firstExit = exitOf(firstDaemon);
  await codex(["app-server", "daemon", "restart"], "daemon-restart", { timeout: 90000 });
  await waitFor(() => existsSync(socketPath) && daemons().length === 1 && daemons()[0].pid !== firstDaemon, "replacement daemon", 30000);
  await firstExit.done;
  await quietly(waitFor(() => sessionEnds(hooksBefore, [r1, r2, u2, r4]).length === 4, "restart SessionEnds", 15000));
  await quietly(waitFor(() => waiters(since).length >= 4, "restart waiters report", 25000));
  const secondDaemon = daemons()[0].pid;
  trace("restart.outcome", { firstDaemon, secondDaemon, firstDaemonExitedAt: firstExit.exitedAt });
  hookMode({});
  await settled("restart");
  processes("after-restart");
  view("after-restart");

  // The replacement holds the threads it reloaded. R1's next turn publishes
  // from it and binds nothing; `work start` recovers Issue 1 on it.
  trace("scenario", { name: "reload-recover" });
  const controller = await daemonClient("controller");
  clients.push(controller);
  hooksBefore = hooks().length;
  const reloaded = (await controller.call("thread/loaded/list", {})).result?.data ?? [];
  const resumed = await controller.call("thread/resume", { threadId: r1 });
  trace("reload.loaded", { loaded: reloaded, resumeError: resumed.error ?? null, newHooks: hooksSince(hooksBefore).length });
  await runTurn(controller, r1, "SPIKE:r1-show work=show");
  trace("reload.show", { shell: shellSummary("r1-show"), hooks: hooksSince(hooksBefore).map((record) => [record.event, record.payload.session_id, hostOf(record), record.publisher.stdout.length > 0]) });
  view("reloaded-unbound");
  await runTurn(controller, r1, "SPIKE:r1-recover work=start-1");
  trace("reload.recover", { shell: shellSummary("r1-recover") });
  view("recovered");

  // The threads the replacement reloaded with no client, R2, U2 and R4,
  // unload about 60 s after the restart. Their SessionEnds come from the
  // replacement, so they end nothing of R2's and R4's orphaned runs, which
  // name the old daemon.
  trace("scenario", { name: "reload-unload" });
  await waitFor(() => sessionEnds(hooksBefore, [r2, u2, r4]).length === 3, "reloaded threads unload", 120000);
  trace("reload.unload", { threads: { r2, u2, r4 }, secondDaemon, restartedAt: firstExit.exitedAt });
  await delay(1500);
  processes("after-reload-unload");
  view("after-reload-unload");

  // `daemon stop` while R1's turn waits on the model and R5 (Issue 5, other)
  // sits idle beside it: the daemon lets the turn finish before it ends
  // either thread. Each SessionEnd hook holds for 6 s and starts a waiter.
  trace("scenario", { name: "stop-busy" });
  const r5 = await startThread(controller, other);
  await runTurn(controller, r5, "SPIKE:r5-start work=start-5");
  view("stop-bound");
  const busy = await runTurn(controller, r1, "SPIKE:busy hold=20000", { detached: true });
  await waitFor(() => records.some((record) => record.kind === "model.request" && record.busy), "busy model request", 30000);
  hookMode({ sessionEndHoldMs: 6000, watchHost: true });
  since = records.length;
  hooksBefore = hooks().length;
  const secondExit = exitOf(secondDaemon);
  const stopped = codex(["app-server", "daemon", "stop"], "daemon-stop", { timeout: 120000 });
  await waitFor(() => controller.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === busy.turnId) || secondExit.exitedAt, "busy turn settles", 90000).catch(() => {});
  await stopped;
  await secondExit.done;
  await quietly(waitFor(() => sessionEnds(hooksBefore, [r1, r5]).length === 2, "stop SessionEnds", 15000));
  await quietly(waitFor(() => waiters(since).length >= 2, "stop waiters report", 25000));
  trace("stop.outcome", { threads: { r1, r5 }, secondDaemon, secondDaemonExitedAt: secondExit.exitedAt, busyTurn: busy.turnId,
    busyCompleted: controller.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === busy.turnId) ?? null });
  hookMode({});
  controller.close();
  clients = [];
  await settled("stop");
  processes("after-stop");
  view("after-stop");
  eventLog("final");
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const client of clients) { try { client.close(); } catch {} }
  for (const handle of terminals) if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} }
  if (daemons().length > 0) await codex(["app-server", "daemon", "stop"], "cleanup-stop").catch(() => {});
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
