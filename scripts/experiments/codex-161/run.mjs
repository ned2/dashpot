// Real-adapter acceptance run for Issue #161: drives a pinned Codex CLI
// against a loopback Responses API fixture with an isolated CODEX_HOME and
// Dashpot's own Codex hook publisher, in a disposable Dashpot Project whose
// Issues are Local Issue Markdown. It measures the hosting modes ADR 0067
// leaves to #161 (a standalone terminal, daemon autostart, `codex exec`,
// `codex remote-control start`, input joined to a running turn), then
// exercises the shared runtime core through the real Codex adapter on the
// managed daemon, and records each step's hooks, shells, protocol results,
// and Dashpot's own published view as a metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version]
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
import { describe } from "./ancestry.mjs";
import { connectUnixWebSocket } from "./uds-websocket.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.159.3";
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-161-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const third = path.join(root, "third-worktree");
const fourth = path.join(root, "fourth-worktree");
const worktrees = { main: fixture, other, third, fourth };
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory never enters the trace; a hook's or shell's
// ancestry keeps the processes up to the runner's own child.
const home = os.homedir();
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, JSON.stringify(kept).replaceAll(home, "~") + "\n");
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
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: four Local Issue Markdown Issues, the main
// working tree, and three linked Worktrees.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2, 3, 4]) {
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
for (const [name, dir] of Object.entries(worktrees)) if (name !== "main") git("worktree", "add", "-b", name, dir);

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
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  trace(url.pathname === "/hook" ? "hook" : "command", await body(req));
  res.end("{}");
});
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
env.SPIKE_SINK = sink.url;

// The fixture model: `SPIKE:<label> hold=<ms> work=<start-N|show|stop>` in
// the latest user message selects one exec_command call reporting identity
// and running that `dashpot work` command; `delegate` spawns a sub-agent whose
// own prompt carries the same hold and work, and waits for it; a request
// already holding the tool outputs ends the turn.
const commandScript = path.join(here, "command.mjs");
const modelRequests = new Map();
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
  const count = (modelRequests.get(label?.name ?? "none") ?? 0) + 1;
  modelRequests.set(label?.name ?? "none", count);
  const delegate = label?.name === "delegate" && tools.includes("multi_agent_v1/spawn_agent");
  const needed = delegate ? 2 : 1;
  const useTool = label && outputs.length < needed && tools.includes("exec_command");
  trace("model.request", { label: label?.name ?? null, count, outputs: outputs.length, toolCount: tools.length, delegateAvailable: tools.includes("multi_agent_v1/spawn_agent") });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  if (useTool) {
    const callId = `call_${label.name}_${count}`;
    let item;
    if (delegate && outputs.length === 0) {
      item = { type: "function_call", call_id: callId, namespace: "multi_agent_v1", name: "spawn_agent", arguments: JSON.stringify({ message: `SPIKE:child hold=${label.hold} work=${label.work}` }) };
    } else if (delegate) {
      let agentId = null;
      try { agentId = JSON.parse(outputs[0].output).agent_id; } catch { agentId = String(outputs[0].output).match(/[0-9a-f-]{36}/)?.[0] ?? null; }
      item = { type: "function_call", call_id: callId, namespace: "multi_agent_v1", name: "wait_agent", arguments: JSON.stringify({ targets: [agentId], timeout_ms: 90000 }) };
    } else {
      item = { type: "function_call", call_id: callId, name: "exec_command", arguments: JSON.stringify({ cmd: `node ${commandScript} ${label.name} ${label.hold} ${label.work}`, login: false, yield_time_ms: 120000 }) };
    }
    sse(res, { type: "response.output_item.done", item });
  } else {
    sse(res, { type: "response.output_item.done", item: { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: "Fixture complete." }] } });
  }
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The hook events `dashpot integrate codex` subscribes, each routed through
// the metadata wrapper to Dashpot's real publisher.
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])),
}, null, 2));
const configPath = path.join(env.CODEX_HOME, "config.toml");
// No `packages/standalone` release is linked into the fixture home: daemon
// autostart is measured from the pinned binary alone.
writeFileSync(configPath, `model = "fixture-model"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"

[features]
hooks = true
multi_agent = true
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

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
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
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.replaceAll(root, "<root>").slice(0, 120)];
// The managed daemon: `codex app-server ... --managed-daemon`, never its
// `app-server daemon pid-update-loop` companion or a loopback `--listen` server.
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemons = () => codexProcesses().filter(isDaemon);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const processes = (label) => trace("processes", { label, processes: codexProcesses().map(brief), daemons: daemons().map((entry) => entry.pid), socketExists: existsSync(socketPath) });
const hooks = () => records.filter((record) => record.kind === "hook");
const hooksSince = (count) => hooks().slice(count).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source ?? null, record.payload.agent_id ?? null, record.payload.cwd, record.publisher.status]);
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
// The first Codex process above a hook or shell: the process hosting it.
const hostOf = (record) => record?.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const threadSummary = (thread) => thread && ({ id: thread.id, forkedFromId: thread.forkedFromId, parentThreadId: thread.parentThreadId, cwd: thread.cwd ?? null, status: thread.status, ephemeral: thread.ephemeral });

// Dashpot's published view of the fixture: the Agent Runs, the diagnostics,
// and each Worktree's state files by name.
const stateFiles = (dir) => {
  const found = [];
  const walk = (current, prefix) => {
    let entries = [];
    try { entries = readdirSync(current, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) walk(path.join(current, entry.name), relative); else found.push(relative);
    }
  };
  walk(path.join(dir, ".dashpot", "state"), "");
  return found.filter((name) => !name.startsWith("events/") && name !== ".gitignore").sort();
};
const view = (label, extra = {}) => {
  const ran = dashpot(["--compact-json"]);
  let parsed = null;
  try { parsed = JSON.parse(ran.stdout); } catch {}
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400), agentRuns: parsed?.agentRuns ?? null,
    issueRuns: parsed ? Object.fromEntries(Object.entries(parsed.issueRuns ?? {}).map(([issue, runs]) => [issue, runs])) : null,
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })),
    stateFiles: Object.fromEntries(Object.entries(worktrees).map(([name, dir]) => [name, stateFiles(dir)])), ...extra });
};
const runsOf = (snapshot) => snapshot.agentRuns ?? [];
const runFor = (snapshot, issueNumber) => runsOf(snapshot).find((run) => run.issueId === `I_fixture_${issueNumber}`);
const worktreeCheck = (label, dir) => {
  const ran = dashpot(["worktree", "check", dir, "--json"]);
  let parsed = null;
  try { parsed = JSON.parse(ran.stdout); } catch {}
  return trace("dashpot.worktree-check", { label, worktree: dir, status: ran.status, result: parsed, stderr: ran.stderr.slice(0, 300) });
};

// One-shot Codex commands (`exec`, `remote-control`, `app-server daemon`).
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const child = spawn(binary, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const clean = (text) => stripAnsi(text).replaceAll(root, "<root>").replace(/WARNING: proceeding, even though we could not create PATH aliases[^\n]*\n?/g, "");
  trace("codex.command", { label, args: args.map((arg) => arg.replaceAll(root, "<root>")), status, signal, stdout: clean(stdout).slice(-1200), stderr: clean(stderr).slice(-1200) });
  return { status, signal, stdout, stderr };
};
const stopDaemon = async (label) => {
  if (daemons().length === 0 && !existsSync(socketPath)) return;
  await codex(["app-server", "daemon", "stop"], label);
  await waitFor(() => daemons().length === 0, `${label}: daemon gone`, 20000).catch(() => {});
};

// A loopback app-server used only to trust the fixture hooks through the
// ledger before any session runs.
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
  const init = await call("initialize", { clientInfo: { name: `dashpot-161-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
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
const runTurn = async (client, threadId, text, options = {}) => {
  const hooksBefore = hooks().length;
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }], ...(options.cwd ? { cwd: options.cwd } : {}) });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, cwd: options.cwd ?? null, status: started.result?.turn?.status ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, hooksBefore };
  await waitFor(() => client.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === turnId), `turn ${text} completed`, options.timeout ?? 60000);
  const completed = client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
  // The Stop hook publishes after the turn settles for its clients.
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000).catch(() => {});
  trace("turn.completed", { client: client.name, threadId, turnId, status: completed.status, newHooks: hooksSince(hooksBefore) });
  return { turnId, hooksBefore, status: completed.status };
};

// An interactive terminal hosted by `script`; only the markers the runner
// waits for are kept from its screen.
const terminals = [];
const terminal = async (name, cwd, args) => {
  const child = spawn("script", ["-qfec", [binary, ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  // The composer treats a burst of keys as a paste, so Enter follows the text
  // after a pause.
  const handle = { name, child, output: "", exited: null,
    type: async (text) => { child.stdin.write(text); await delay(600); child.stdin.write("\r"); } };
  child.stdout.on("data", (chunk) => { handle.output += stripAnsi(String(chunk)); });
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, cwd, args: args.map((arg) => arg.replaceAll(root, "<root>")), scriptPid: child.pid });
  return handle;
};
// A terminal turn: type (or launch with) a prompt and wait for its shell and Stop.
// `prompt` is `<label>[ hold=<ms>][ work=<command>]`; the shell reports `<label>`.
const terminalTurn = async (handle, prompt, typed = true, timeout = 90000) => {
  const label = prompt.split(" ")[0];
  const hooksBefore = hooks().length;
  if (typed) await handle.type(`SPIKE:${prompt}`);
  await waitFor(() => command(label) || handle.exited, `${label} command`, timeout);
  assert(!handle.exited, `${handle.name} exited early`);
  const thread = command(label).env.CODEX_THREAD_ID;
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === thread), `${label} Stop`, timeout);
  return { hooksBefore, thread, shell: command(label) };
};
const exitTerminal = async (handle) => {
  await handle.type("/exit");
  if (!await quietly(waitFor(() => handle.exited, `${handle.name} exit`, 20000))) handle.child.kill("SIGTERM");
};
const shellSummary = (label) => {
  const shell = command(label);
  const work = command(label, "work")?.work ?? null;
  return shell && { label, cwd: shell.cwd, thread: shell.env.CODEX_THREAD_ID ?? null, session: shell.env.CODEX_SESSION_ID ?? null, host: hostOf(shell),
    work: work && { args: work.args, status: work.status, stdout: work.stdout.replaceAll(root, "<root>"), stderr: work.stderr.replaceAll(root, "<root>") } };
};

const scripts = ["run.mjs", "verify.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "work_reconciliation.py", "hook_records.py", "work.py"].map((file) => `src/dashpot/sessions/${file}`);
let controllers = [];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(os.homedir(), "~"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, dirty }, worktrees, socketPath, hookEvents,
    // The runner's own scripts by name, and the lifecycle modules it
    // exercised by repository path.
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
  assert.equal(daemons().length, 0, "the loopback server starts no daemon");

  // Measurement: `codex exec` with no daemon running.
  trace("scenario", { name: "exec-no-daemon" });
  let hooksBefore = hooks().length;
  await codex(["exec", "-C", fixture, "SPIKE:exec"], "exec", { timeout: 90000 });
  trace("exec.outcome", { shell: shellSummary("exec"), newHooks: hooksSince(hooksBefore) });
  processes("after-exec");
  await stopDaemon("stop-after-exec");

  // Measurement: `codex remote-control start` with no daemon and no account.
  trace("scenario", { name: "remote-control" });
  await codex(["remote-control", "start", "--json"], "remote-control-start", { timeout: 30000 });
  processes("after-remote-control-start");
  await codex(["remote-control", "stop", "--json"], "remote-control-stop", { timeout: 30000 });
  await stopDaemon("stop-after-remote-control");
  processes("after-remote-control-stop");

  // Measurement: a standalone terminal (autostart disabled, no daemon
  // running) binds Issue 3 in `third`; its hooks and shells are hosted by the
  // terminal's own process.
  trace("scenario", { name: "standalone-terminal" });
  const standalone = ["--disable", "daemon_auto_start"];
  const ts = await terminal("standalone", third, [...standalone, "-C", third, "SPIKE:ts-start work=start-3"]);
  const tsStart = await terminalTurn(ts, "ts-start work=start-3", false);
  const tsThread = tsStart.thread;
  const tsHost = hostOf(tsStart.shell);
  processes("standalone-running");
  trace("standalone.identity", { shell: shellSummary("ts-start"), newHooks: hooksSince(tsStart.hooksBefore), hookHosts: hooks().slice(tsStart.hooksBefore).map((record) => [record.event, hostOf(record)]), daemons: daemons().map((entry) => entry.pid) });
  view("standalone-bound", { expectHost: tsHost });

  // Measurement: input typed into the standalone terminal while its turn runs.
  trace("scenario", { name: "terminal-joined-input" });
  hooksBefore = hooks().length;
  await ts.type("SPIKE:ts-hold hold=6000");
  await waitFor(() => command("ts-hold"), "ts-hold command", 60000);
  await delay(1000);
  await ts.type("SPIKE:ts-joined");
  const typedAt = Date.now();
  await waitFor(() => command("ts-joined"), "ts-joined command", 60000);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === tsThread), "ts joined Stop", 60000);
  await delay(1500);
  trace("terminal-joined.outcome", { hold: shellSummary("ts-hold"), joined: shellSummary("ts-joined"), typedAt, holdEnded: command("ts-hold", "end")?.receiptTime ?? null, joinedStarted: command("ts-joined")?.receiptTime ?? null,
    hooks: hooks().slice(hooksBefore).map((record) => [record.event, record.payload.turn_id ?? null, record.payload.cwd, record.receiptTime]) });

  // Measurement: the standalone host is killed, then the conversation resumes
  // in a new standalone terminal; recovery is an explicit `work start`.
  trace("scenario", { name: "standalone-gone" });
  hooksBefore = hooks().length;
  process.kill(tsHost, "SIGKILL");
  await waitFor(() => !existsSync(`/proc/${tsHost}`), "standalone host gone", 10000);
  await quietly(waitFor(() => ts.exited, "standalone script exit", 10000));
  await delay(1500);
  trace("standalone-gone.hooks", { newHooks: hooksSince(hooksBefore) });
  view("standalone-gone");
  const ts2 = await terminal("standalone-resumed", third, [...standalone, "resume", tsThread, "-C", third]);
  await delay(4000);
  const ts2First = await terminalTurn(ts2, "ts2-first work=show");
  const ts2Host = hostOf(ts2First.shell);
  trace("standalone-resumed.first", { shell: shellSummary("ts2-first"), newHooks: hooksSince(ts2First.hooksBefore), hookHosts: hooks().slice(ts2First.hooksBefore).map((record) => [record.event, hostOf(record)]),
    continuation: hooks().slice(ts2First.hooksBefore).map((record) => [record.event, record.publisher.stdout.length > 0]), daemons: daemons().map((entry) => entry.pid) });
  view("standalone-resumed", { expectHost: ts2Host });
  const ts2Recover = await terminalTurn(ts2, "ts2-recover work=start-3");
  trace("standalone-resumed.recover", { shell: shellSummary("ts2-recover"), newHooks: hooksSince(ts2Recover.hooksBefore) });
  view("standalone-recovered", { expectHost: ts2Host });

  // Measurement: a plain terminal with autostart left on, in `other`, starts
  // the managed daemon and binds Issue 1 there.
  trace("scenario", { name: "autostart-terminal" });
  const ta = await terminal("autostart", other, ["-C", other, "SPIKE:ta-start work=start-1"]);
  const taStart = await terminalTurn(ta, "ta-start work=start-1", false);
  const taThread = taStart.thread;
  processes("autostart-running");
  const daemonPid = daemons()[0]?.pid ?? null;
  trace("autostart.identity", { shell: shellSummary("ta-start"), newHooks: hooksSince(taStart.hooksBefore), hookHosts: hooks().slice(taStart.hooksBefore).map((record) => [record.event, hostOf(record), record.ancestry.slice(0, 4).map((entry) => [entry.pid, entry.comm])]),
    daemonPid, daemonCmdline: daemons()[0] ? [...brief(daemons()[0]).slice(0, 3), daemons()[0].cmdline.replaceAll(root, "<root>")] : null, socketExists: existsSync(socketPath),
    installed: (() => { try { return readdirSync(path.join(env.CODEX_HOME, "packages"), { recursive: true }).filter((entry) => entry.split(path.sep).length <= 3).sort(); } catch { return null; } })() });
  view("autostart-bound", { expectHost: daemonPid });

  // The standalone terminal's next turn, now that a daemon runs beside it,
  // and a new terminal launched with autostart disabled while it runs.
  const ts2Second = await terminalTurn(ts2, "ts2-second");
  trace("standalone.second", { shell: shellSummary("ts2-second"), hookHosts: hooks().slice(ts2Second.hooksBefore).map((record) => [record.event, hostOf(record)]) });
  trace("scenario", { name: "autostart-disabled-beside-daemon" });
  const ts3 = await terminal("autostart-disabled", third, [...standalone, "-C", third, "SPIKE:ts3-start"]);
  const ts3Start = await terminalTurn(ts3, "ts3-start", false);
  trace("autostart-disabled.identity", { shell: shellSummary("ts3-start"), hookHosts: hooks().slice(ts3Start.hooksBefore).map((record) => [record.event, hostOf(record)]), daemonPid });
  hooksBefore = hooks().length;
  await exitTerminal(ts3);
  await delay(2000);
  trace("autostart-disabled.exit", { newHooks: hooksSince(hooksBefore) });

  // The standalone terminal exits: its SessionEnd ends Issue 3's run at once.
  trace("scenario", { name: "standalone-exit" });
  hooksBefore = hooks().length;
  await exitTerminal(ts2);
  await quietly(waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "SessionEnd" && record.payload.session_id === tsThread), "standalone SessionEnd", 10000));
  trace("standalone.exit", { newHooks: hooksSince(hooksBefore) });
  view("standalone-exited");

  // Acceptance on the daemon: two root threads in the main Worktree beside
  // the terminal's thread in `other`, all hosted by one daemon process.
  trace("scenario", { name: "daemon-roots" });
  assert(daemonPid, "a daemon runs");
  const c1 = await daemonClient("controller-1");
  controllers.push(c1);
  const r1 = (await c1.call("thread/start", { cwd: fixture })).result?.thread;
  const r2 = (await c1.call("thread/start", { cwd: fixture })).result?.thread;
  assert(r1?.id && r2?.id, "two root threads started");
  await runTurn(c1, r1.id, "SPIKE:r1-start work=start-2");
  await runTurn(c1, r2.id, "SPIKE:r2-start work=start-4");
  trace("daemon-roots.identity", { r1: shellSummary("r1-start"), r2: shellSummary("r2-start"), r1Thread: r1.id, r2Thread: r2.id, daemonPid, loaded: (await c1.call("thread/loaded/list", {})).result?.data ?? [] });
  view("daemon-roots", { expectHost: daemonPid });

  // Attach and detach while a turn continues.
  trace("scenario", { name: "attach-detach" });
  const c2 = await daemonClient("controller-2");
  controllers.push(c2);
  hooksBefore = hooks().length;
  const attached = await c2.call("thread/resume", { threadId: r1.id });
  await delay(1000);
  trace("attach.outcome", { thread: threadSummary(attached.result?.thread), error: attached.error ?? null, newHooks: hooksSince(hooksBefore) });
  const long = await runTurn(c1, r1.id, "SPIKE:r1-long hold=6000", { detached: true });
  await waitFor(() => command("r1-long"), "r1-long command", 30000);
  view("attach-turn-running");
  c1.close();
  controllers = controllers.filter((client) => client !== c1);
  await waitFor(() => c2.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === long.turnId), "long turn completes for the remaining client", 60000);
  await delay(1500);
  trace("detach.outcome", { commandEnded: Boolean(command("r1-long", "end")), status: c2.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === long.turnId)?.status, newHooks: hooksSince(long.hooksBefore) });
  view("after-detach");
  const c3 = await daemonClient("controller-3");
  controllers.push(c3);

  // Interrupt a running turn.
  trace("scenario", { name: "interrupt" });
  await c3.call("thread/resume", { threadId: r2.id });
  const interruptTurn = await runTurn(c3, r2.id, "SPIKE:r2-interrupt hold=30000", { detached: true });
  await waitFor(() => command("r2-interrupt"), "interrupt command", 30000);
  view("interrupt-running");
  const interrupted = await c3.call("turn/interrupt", { threadId: r2.id, turnId: interruptTurn.turnId });
  await waitFor(() => c3.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === interruptTurn.turnId), "interrupted turn settles", 30000);
  await quietly(waitFor(() => hooks().slice(interruptTurn.hooksBefore).some((record) => record.event === "Interrupt"), "Interrupt hook", 10000));
  await delay(1000);
  trace("interrupt.outcome", { response: interrupted.error ?? "ok", status: c3.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === interruptTurn.turnId)?.status, newHooks: hooksSince(interruptTurn.hooksBefore) });
  view("after-interrupt");

  // A delegated sub-agent thread inside R1: its shell's identity, what
  // `dashpot work show` reports from it, and the Worktree check while it works.
  trace("scenario", { name: "delegate" });
  const delegateTurn = await runTurn(c2, r1.id, "SPIKE:delegate hold=8000 work=show", { detached: true });
  await waitFor(() => command("child"), "child command", 60000);
  await waitFor(() => command("child", "work"), "child work show", 40000);
  view("delegate-running");
  worktreeCheck("delegate-running", fixture);
  // An empty Worktree is blocked by the working sub-agent alone (ADR 0066).
  worktreeCheck("delegate-running-fourth", fourth);
  await waitFor(() => c2.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === delegateTurn.turnId), "delegate turn completes", 90000);
  await delay(1500);
  const childThread = command("child").env.CODEX_THREAD_ID;
  trace("delegate.outcome", { child: shellSummary("child"), childThread, newHooks: hooksSince(delegateTurn.hooksBefore),
    childRead: threadSummary((await c2.call("thread/read", { threadId: childThread })).result?.thread) });
  view("after-delegate");

  // A fork of R1: a new conversation that inherits no Agent Run.
  trace("scenario", { name: "fork" });
  const forked = await c3.call("thread/fork", { threadId: r1.id, cwd: fixture });
  const fork = forked.result?.thread;
  assert(fork?.id, `fork: ${JSON.stringify(forked.error)}`);
  const forkTurn = await runTurn(c3, fork.id, "SPIKE:fork work=show");
  trace("fork.outcome", { fork: threadSummary(fork), origin: r1.id, shell: shellSummary("fork"), newHooks: hooksSince(forkTurn.hooksBefore) });
  view("after-fork");

  // Live Relocation: a controller's `turn/start` with a `cwd` override on the
  // terminal's thread carries Issue 1's run from `other` to `fourth`; the
  // terminal's own next turn runs there too.
  trace("scenario", { name: "live-relocation" });
  const beforeMove = view("before-relocation");
  const subscribed = await c3.call("thread/resume", { threadId: taThread });
  trace("relocation.subscribe", { thread: threadSummary(subscribed.result?.thread), error: subscribed.error ?? null });
  const moved = await runTurn(c3, taThread, "SPIKE:ta-move work=show", { cwd: fourth });
  trace("relocation.move", { shell: shellSummary("ta-move"), newHooks: hooksSince(moved.hooksBefore), runBefore: runFor(beforeMove, 1) ?? null });
  view("after-relocation");
  worktreeCheck("after-relocation-other", other);
  worktreeCheck("after-relocation-fourth", fourth);
  const taAfter = await terminalTurn(ta, "ta-after work=show");
  trace("relocation.terminal", { shell: shellSummary("ta-after"), newHooks: hooksSince(taAfter.hooksBefore) });
  view("after-relocation-terminal");

  // Measurement: input joined to a running controller turn with a `cwd`
  // override: which hooks it publishes, where, and where its shell runs.
  trace("scenario", { name: "joined-input" });
  const holdTurn = await runTurn(c2, r1.id, "SPIKE:r1-hold hold=6000", { detached: true });
  await waitFor(() => command("r1-hold"), "r1-hold command", 30000);
  const joined = await c2.call("turn/start", { threadId: r1.id, input: [{ type: "text", text: "SPIKE:r1-joined work=show" }], cwd: third });
  const joinedAt = Date.now();
  trace("joined.request", { turnId: joined.result?.turn?.id ?? null, sameTurn: joined.result?.turn?.id === holdTurn.turnId, status: joined.result?.turn?.status ?? null, error: joined.error ?? null });
  await delay(1000);
  view("joined-while-running");
  await waitFor(() => c2.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === holdTurn.turnId), "joined turn completes", 60000);
  await quietly(waitFor(() => command("r1-joined"), "joined command", 10000));
  await delay(1500);
  trace("joined.outcome", { hold: shellSummary("r1-hold"), joined: shellSummary("r1-joined"), holdEnded: command("r1-hold", "end")?.receiptTime ?? null,
    newHooks: hooksSince(holdTurn.hooksBefore), turns: hooks().slice(holdTurn.hooksBefore).map((record) => [record.event, record.payload.session_id, record.payload.turn_id ?? null, record.payload.cwd, record.receiptTime]), joinedAt,
    thread: threadSummary((await c2.call("thread/read", { threadId: r1.id })).result?.thread) });
  view("after-joined");

  // One thread unloads and a terminal exits while another thread's turn runs.
  trace("scenario", { name: "unload-while-running" });
  const span = await runTurn(c2, r1.id, "SPIKE:r1-span hold=75000", { detached: true, timeout: 120000 });
  await waitFor(() => command("r1-span"), "r1-span command", 30000);
  hooksBefore = hooks().length;
  await c3.call("thread/unsubscribe", { threadId: r2.id });
  await c3.call("thread/unsubscribe", { threadId: taThread });
  await c3.call("thread/unsubscribe", { threadId: fork.id });
  await exitTerminal(ta);
  const leftAt = Date.now();
  const ended = (thread) => hooks().slice(hooksBefore).some((record) => record.event === "SessionEnd" && record.payload.session_id === thread);
  await quietly(waitFor(() => ended(r2.id) && ended(taThread), "R2 and the terminal thread unload", 90000));
  await delay(1500);
  trace("unload.outcome", { leftAt, newHooks: hooksSince(hooksBefore), endedAfterMs: hooks().slice(hooksBefore).filter((record) => record.event === "SessionEnd").map((record) => [record.payload.session_id, record.receiptTime - leftAt]),
    spanRunning: !command("r1-span", "end"), loaded: (await c2.call("thread/loaded/list", {})).result?.data ?? [] });
  view("after-unload");
  await waitFor(() => c2.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === span.turnId), "span turn completes", 60000);
  await delay(1000);

  // A thread resumed after its unload: the same conversation, a new incarnation.
  trace("scenario", { name: "resume-after-unload" });
  hooksBefore = hooks().length;
  const resumed = await c3.call("thread/resume", { threadId: r2.id });
  const resumedTurn = await runTurn(c3, r2.id, "SPIKE:r2-resumed work=show");
  trace("resume.outcome", { thread: threadSummary(resumed.result?.thread), error: resumed.error ?? null, shell: shellSummary("r2-resumed"), newHooks: hooksSince(hooksBefore) });
  view("after-resume");

  // The daemon is killed: no hook runs, so the bound run is orphaned.
  trace("scenario", { name: "daemon-gone" });
  hooksBefore = hooks().length;
  for (const client of controllers) client.close();
  controllers = [];
  process.kill(daemonPid, "SIGKILL");
  await waitFor(() => !existsSync(`/proc/${daemonPid}`), "daemon gone", 10000);
  await delay(2000);
  processes("daemon-killed");
  trace("daemon-gone.hooks", { newHooks: hooksSince(hooksBefore) });
  view("daemon-gone");

  // A new daemon resumes R1: Codex is not an exclusive session process, so
  // the orphaned run is not continued; `work start` recovers it explicitly.
  trace("scenario", { name: "daemon-recovery" });
  for (const stale of codexProcesses()) { trace("cleanup.kill", { process: brief(stale) }); try { process.kill(stale.pid, "SIGKILL"); } catch {} }
  rmSync(socketPath, { force: true });
  await codex(["app-server", "daemon", "start"], "daemon-start", { timeout: 60000 });
  await waitFor(() => existsSync(socketPath), "daemon control socket", 30000);
  processes("daemon-restarted");
  const newDaemonPid = daemons()[0]?.pid ?? null;
  const c4 = await daemonClient("controller-4");
  controllers.push(c4);
  hooksBefore = hooks().length;
  const coldResume = await c4.call("thread/resume", { threadId: r1.id });
  const coldFirst = await runTurn(c4, r1.id, "SPIKE:r1-cold work=show");
  trace("cold-resume.outcome", { thread: threadSummary(coldResume.result?.thread), error: coldResume.error ?? null, shell: shellSummary("r1-cold"), newHooks: hooksSince(hooksBefore),
    continuation: hooks().slice(hooksBefore).map((record) => [record.event, record.publisher.stdout.length > 0]) });
  view("cold-resumed", { expectHost: newDaemonPid });
  await runTurn(c4, r1.id, "SPIKE:r1-recover work=start-2");
  trace("recover.outcome", { shell: shellSummary("r1-recover") });
  view("recovered", { expectHost: newDaemonPid });
  void coldFirst;

  // `daemon stop` with the recovered thread loaded.
  trace("scenario", { name: "daemon-stop" });
  hooksBefore = hooks().length;
  for (const client of controllers) client.close();
  controllers = [];
  await codex(["app-server", "daemon", "stop"], "daemon-stop", { timeout: 60000 });
  await quietly(waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "SessionEnd"), "SessionEnd on daemon stop", 15000));
  await delay(1500);
  trace("daemon-stop.outcome", { newHooks: hooksSince(hooksBefore) });
  processes("after-daemon-stop");
  view("after-daemon-stop");

  // Dashpot's Event Log for the fixture, metadata only.
  const events = dashpot(["events", "--json"]);
  let eventList = null;
  try { eventList = JSON.parse(events.stdout); } catch {}
  // Hook and command outcomes only, with the fields that say what Dashpot did.
  const fields = ["time", "event.name", "dashpot.process.kind", "dashpot.agent_session.id", "dashpot.worktree.path", "dashpot.issue.id", "dashpot.hook.event",
    "dashpot.outcome.result", "dashpot.agent_session.state", "dashpot.work_store.change", "dashpot.subcommand"];
  trace("dashpot.events", { status: events.status, stderr: events.stderr.slice(0, 300),
    events: (eventList?.events ?? []).filter((event) => event["event.name"] !== "process.start" && event["event.name"] !== "process.end")
      .map((event) => Object.fromEntries(fields.filter((field) => event[field] !== undefined && event[field] !== null).map((field) => [field, event[field]]))) });
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  for (const handle of terminals) {
    if (process.env.SPIKE_DEBUG_TERMINAL === "1") writeFileSync(path.join(root, `terminal-${handle.name}.txt`), handle.output);
    if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} }
  }
  if (daemons().length > 0) await codex(["app-server", "daemon", "stop"], "cleanup-stop").catch(() => {});
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
