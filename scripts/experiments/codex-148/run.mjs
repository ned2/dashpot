// Isolated Codex relocation-handoff experiment for Issue #148. Drives a
// pinned Codex CLI against a loopback Responses API fixture with an isolated
// CODEX_HOME, hosts threads on the shared local app-server daemon with an
// interactive terminal attached, moves a thread's working directory from a
// second, controller client, and records hook, shell, and protocol evidence
// as a metadata-only trace.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";
import { connectUnixWebSocket } from "./uds-websocket.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-148-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const third = path.join(root, "third-worktree");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, JSON.stringify(record) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.155.1";

const env = {
  PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "Disposable fixture");
git("worktree", "add", "-b", "other", other);
git("worktree", "add", "-b", "third", third);

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

// The fixture model: a `SPIKE:<label>` text in the latest user message selects
// one exec_command call reporting identity; a request already holding the
// tool output ends the turn.
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
      const match = part.type === "input_text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?/);
      if (match) { label = { name: match[1], hold: match[2] }; latestUser = index; }
    }
  });
  const outputs = input.slice(latestUser + 1).filter((item) => item.type === "function_call_output");
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => `${tool.name}/${nested.name}`) : [tool.name ?? tool.type]);
  const count = (modelRequests.get(label?.name ?? "none") ?? 0) + 1;
  modelRequests.set(label?.name ?? "none", count);
  const useTool = label && outputs.length < 1 && tools.includes("exec_command");
  trace("model.request", { label: label?.name ?? null, count, outputs: outputs.length, model: payload.model, stream: payload.stream, toolCount: tools.length,
    tools: modelRequests.size === 1 && count === 1 ? tools : undefined, previousResponseId: payload.previous_response_id ?? null, store: payload.store ?? null });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  if (useTool) {
    const callId = `call_${label.name}_${count}`;
    const item = { type: "function_call", call_id: callId, name: "exec_command", arguments: JSON.stringify({ cmd: `node ${commandScript} ${label.name} ${label.hold ?? 200}`, login: false }) };
    sse(res, { type: "response.output_item.done", item });
  } else {
    sse(res, { type: "response.output_item.done", item: { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: "Fixture complete." }] } });
  }
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart", "SubagentStop", "SessionEnd", "Interrupt"];
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
}, null, 2));
const configPath = path.join(env.CODEX_HOME, "config.toml");
// `codex app-server daemon` launches only the installer-managed standalone
// release under CODEX_HOME, so the fixture home points that fixed path at the
// pinned binary's own release directory.
const release = path.dirname(path.dirname(execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim()));
mkdirSync(path.join(env.CODEX_HOME, "packages", "standalone"), { recursive: true });
symlinkSync(release, path.join(env.CODEX_HOME, "packages", "standalone", "current"));
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

[projects."${fixture}"]
trust_level = "trusted"

[projects."${other}"]
trust_level = "trusted"

[projects."${third}"]
trust_level = "trusted"
`);

// Every process whose environment names the fixture CODEX_HOME, found by
// reading each /proc entry's environment.
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
const snapshot = (label) => trace("processes", { label, processes: codexProcesses() });
const hooks = () => records.filter((record) => record.kind === "hook");
const hooksSince = (count) => hooks().slice(count).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source ?? record.payload.agent_id ?? null, record.payload.cwd]);
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
// The thread fields the trace keeps: identity and hosting, never content.
const threadSummary = (thread) => thread && ({ id: thread.id, sessionId: thread.sessionId, forkedFromId: thread.forkedFromId, parentThreadId: thread.parentThreadId, cwd: thread.cwd ?? thread.environments?.[0]?.cwd ?? null,
  source: thread.source, status: thread.status, historyMode: thread.historyMode, originator: thread.originator, agentRole: thread.agentRole, ephemeral: thread.ephemeral });
const runTurn = async (client, threadId, text, options = {}) => {
  const hooksBefore = hooks().length;
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }], ...(options.cwd ? { cwd: options.cwd } : {}) });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, hooksBefore };
  await waitFor(() => client.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === turnId), `turn ${text} completed`, options.timeout ?? 60000);
  const completed = client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
  trace("turn.completed", { client: client.name, threadId, turnId, status: completed.status, newHooks: hooksSince(hooksBefore) });
  return { turnId, hooksBefore, status: completed.status };
};
const lockFiles = () => { try { return readdirSync(path.join(env.CODEX_HOME, "thread-writer-locks")); } catch { return []; } };


// The shared local daemon: `codex app-server daemon start` in the fixture
// CODEX_HOME, addressed through its control socket.
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const daemonCommand = async (args, label) => {
  const child = spawn(binary, ["app-server", "daemon", ...args], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  trace("daemon.command", { label, args, status, signal, stdout: stripAnsi(stdout).slice(-1500), stderr: stripAnsi(stderr).slice(-1500) });
  return { status, stdout, stderr };
};
// A JSON-RPC client on the daemon's control socket, which speaks WebSocket
// over a Unix domain socket (`codex app-server proxy` only relays bytes, so a
// stdio client still has to speak WebSocket itself).
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(socketPath);
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  socket.on("message", (text) => {
    let parsed;
    try { parsed = JSON.parse(text); } catch { return; }
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method === "hook/started" || parsed.method === "hook/completed") {
      notifications.push({ method: parsed.method, threadId: parsed.params.threadId, turnId: parsed.params.turnId, event: parsed.params.run.eventName, status: parsed.params.run.status, receivedAt: Date.now() });
    } else if (parsed.method?.startsWith("thread/") || parsed.method?.startsWith("turn/")) {
      const { threadId, turn, status, thread } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id, status: status ?? turn?.status, receivedAt: Date.now() });
    }
  });
  const call = (method, params = {}) => new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); });
  const init = await Promise.race([call("initialize", { clientInfo: { name: `dashpot-148-${name}`, version: "0" }, capabilities: { experimentalApi: true } }), delay(15000).then(() => ({ timeout: true }))]);
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: "unix-websocket", socket: socketPath, userAgent: init.result?.userAgent, codexHome: init.result?.codexHome, error: init.error ?? null, timeout: init.timeout ?? false });
  assert(init.result, `${name} initialized on the control socket: ${JSON.stringify(init)}`);
  return { name, call, notifications, close: () => socket.close() };
};
// An interactive terminal attached to the daemon, hosted by `script`; only
// the markers the runner waits for are kept from its screen.
const terminals = [];
const attachTerminal = async (name, cwd, prompt, { remote = true } = {}) => {
  const args = [...(remote ? ["--remote", `unix://${socketPath}`] : []), "-C", cwd, prompt];
  const child = spawn("script", ["-qfec", [binary, ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  // The composer treats a burst of keys as a paste, so Enter follows the text
  // after a pause; the screen is flattened to letters for marker matching.
  const terminal = { name, child, output: "", exited: null,
    type: async (text) => { child.stdin.write(text); await delay(600); child.stdin.write("\r"); },
    screen: () => terminal.output.replace(/[^A-Za-z0-9:\/.-]/g, "").replace(/78/g, "") };
  child.stdout.on("data", (chunk) => { terminal.output += stripAnsi(String(chunk)); });
  child.on("exit", (status, signal) => { terminal.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(terminal);
  trace("terminal.start", { name, cwd, args, scriptPid: child.pid });
  return terminal;
};

let daemonStarted = false;
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, binary, binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    env: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CODEX") || key === "SPIKE_SINK")), fixture, other, third, hookEvents, socketPath,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // Scenario 0: start the shared daemon and trust the fixture hooks through the ledger.
  trace("scenario", { name: "daemon-start" });
  const started = await daemonCommand(["start"], "start");
  daemonStarted = true;
  await waitFor(() => existsSync(socketPath), "daemon control socket", 30000);
  const daemonVersion = await daemonCommand(["version"], "version");
  snapshot("daemon-started");
  trace("daemon.identity", { socket: socketPath, exists: existsSync(socketPath), processes: codexProcesses().map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline]),
    versionJSON: (() => { try { return JSON.parse(daemonVersion.stdout); } catch { return null; } })() });
  const controller = await daemonClient("controller");
  const listed = await controller.call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { before: entries.map((entry) => [entry.eventName, entry.source, entry.trustStatus, entry.enabled]) });
  assert(entries.length === hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await controller.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  const methods = ["thread/backgroundTerminals/list", "thread/loaded/list"];
  const probes = {};
  for (const method of methods) {
    const response = await controller.call(method, method === "thread/loaded/list" ? {} : { threadId: "00000000-0000-0000-0000-000000000000" });
    probes[method] = response.error ? { code: response.error.code, message: String(response.error.message).slice(0, 200) } : { ok: true, keys: Object.keys(response.result ?? {}) };
  }
  trace("daemon.methods", probes);

  // Scenario 1: an interactive terminal attached to the daemon hosts thread A
  // in the linked Worktree; a controller client finds it by its cwd.
  trace("scenario", { name: "attached-terminal" });
  let hooksBefore = hooks().length;
  const tui = await attachTerminal("tui-a", other, "SPIKE:tui-a");
  await waitFor(() => command("tui-a") || tui.exited, "tui-a command", 90000);
  assert(!tui.exited, `terminal exited early: ${tui.output.slice(-1500)}`);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop"), "tui-a Stop", 60000);
  const shellA = command("tui-a");
  const threadAId = shellA.env.CODEX_SESSION_ID ?? shellA.env.CODEX_THREAD_ID;
  const loaded = (await controller.call("thread/loaded/list", {})).result?.data ?? [];
  const readA = await controller.call("thread/read", { threadId: threadAId });
  trace("attached.identity", { threadId: threadAId, shellEnv: shellA.env, shellCwd: shellA.cwd, shellAncestry: shellA.ancestry.slice(0, 5), loaded, thread: threadSummary(readA.result?.thread), readError: readA.error ?? null,
    newHooks: hooksSince(hooksBefore), remoteBanner: /remote/i.test(tui.screen()), processes: codexProcesses().map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline]) });
  assert(loaded.includes(threadAId), "the terminal's thread is loaded on the daemon");
  assert.equal(shellA.cwd, other);

  // Scenario 2: the controller subscribes to A and starts a turn with a cwd
  // override to the main Worktree; the terminal's next turn stays there.
  trace("scenario", { name: "controller-relocation" });
  hooksBefore = hooks().length;
  const subscribed = await controller.call("thread/resume", { threadId: threadAId, cwd: fixture });
  await delay(1000);
  trace("controller.subscribe", { thread: threadSummary(subscribed.result?.thread), error: subscribed.error ?? null, hooksAtSubscribe: hooksSince(hooksBefore), cwdOverrideHonoured: subscribed.result?.thread?.cwd === fixture });
  const moved = await runTurn(controller, threadAId, "SPIKE:controller-move", { cwd: fixture });
  const movedShell = command("controller-move");
  trace("controller.move", { turnId: moved.turnId, status: moved.status, shellCwd: movedShell?.cwd ?? null, shellEnv: movedShell?.env ?? null, newHooks: hooksSince(moved.hooksBefore),
    thread: threadSummary((await controller.call("thread/read", { threadId: threadAId })).result?.thread), terminalSawTurn: /SPIKE:controller-move/.test(tui.screen()) });
  hooksBefore = hooks().length;
  await tui.type("SPIKE:tui-after-move");
  await waitFor(() => command("tui-after-move"), "terminal turn after the move", 60000).catch((error) => { trace("terminal.screen", { name: "tui-a", tail: tui.screen().slice(-600) }); throw error; });
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop"), "terminal turn Stop", 60000);
  const afterShell = command("tui-after-move");
  trace("terminal.after-move", { shellCwd: afterShell.cwd, shellEnv: afterShell.env, newHooks: hooksSince(hooksBefore), thread: threadSummary((await controller.call("thread/read", { threadId: threadAId })).result?.thread) });

  // Scenario 3: a second terminal thread B on the daemon is untouched by A's move.
  trace("scenario", { name: "sibling-thread" });
  hooksBefore = hooks().length;
  const tuiB = await attachTerminal("tui-b", third, "SPIKE:tui-b");
  await waitFor(() => command("tui-b") || tuiB.exited, "tui-b command", 90000);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === command("tui-b").env.CODEX_SESSION_ID), "tui-b Stop", 60000);
  const threadBId = command("tui-b").env.CODEX_SESSION_ID;
  hooksBefore = hooks().length;
  await controller.call("thread/resume", { threadId: threadAId });
  const movedAgain = await runTurn(controller, threadAId, "SPIKE:controller-move-2", { cwd: other });
  await tuiB.type("SPIKE:tui-b-after");
  await waitFor(() => command("tui-b-after"), "tui-b turn after A's move", 60000);
  await waitFor(() => hooks().slice(hooksBefore).filter((record) => record.event === "Stop").length >= 2, "both Stops", 60000);
  const loadedNow = (await controller.call("thread/loaded/list", {})).result?.data ?? [];
  const others = [];
  for (const id of loadedNow.filter((id) => id !== threadAId && id !== threadBId)) others.push(threadSummary((await controller.call("thread/read", { threadId: id })).result?.thread) ?? { id, unreadable: true });
  trace("sibling.outcome", { a: { turn: movedAgain.turnId, shellCwd: command("controller-move-2")?.cwd }, b: { threadId: threadBId, shellCwd: command("tui-b-after")?.cwd, shellSession: command("tui-b-after")?.env.CODEX_SESSION_ID },
    newHooks: hooksSince(hooksBefore), loaded: loadedNow, otherLoaded: others });

  // Scenario 4: a controller turn/start while the terminal's turn runs; the
  // response names which turn the request landed in.
  trace("scenario", { name: "busy-thread" });
  hooksBefore = hooks().length;
  await tui.type("SPIKE:tui-hold hold=8000");
  await waitFor(() => command("tui-hold"), "hold command start", 60000);
  const busyStart = await controller.call("turn/start", { threadId: threadAId, input: [{ type: "text", text: "SPIKE:controller-busy" }], cwd: third });
  const busyAt = Date.now();
  trace("busy.request", { result: busyStart.result ? { turnId: busyStart.result.turn?.id, status: busyStart.result.turn?.status } : null, error: busyStart.error ?? null });
  const terminalsList = await controller.call("thread/backgroundTerminals/list", { threadId: threadAId });
  trace("busy.background-terminals", { result: terminalsList.result ?? null, error: terminalsList.error ?? null });
  await waitFor(() => command("tui-hold", "end"), "hold command end", 60000);
  const holdEnded = Date.now();
  await waitFor(() => command("controller-busy") || Date.now() - holdEnded > 20000, "busy controller turn ran", 30000);
  await delay(2000);
  trace("busy.outcome", { requestedAt: busyAt, holdEndedAt: holdEnded, controllerTurnRanAt: command("controller-busy")?.receiptTime ?? null, controllerShellCwd: command("controller-busy")?.cwd ?? null,
    newHooks: hooksSince(hooksBefore), thread: threadSummary((await controller.call("thread/read", { threadId: threadAId })).result?.thread) });

  // Scenario 4b: a plain `codex` terminal, launched without `--remote` while
  // the daemon runs: where its thread is hosted and whether a controller can
  // subscribe to it.
  trace("scenario", { name: "plain-terminal" });
  hooksBefore = hooks().length;
  const plain = await attachTerminal("plain", third, "SPIKE:plain", { remote: false });
  await waitFor(() => command("plain") || plain.exited, "plain command", 90000);
  assert(!plain.exited, `plain terminal exited early: ${plain.screen().slice(-800)}`);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === command("plain").env.CODEX_SESSION_ID), "plain Stop", 60000);
  const plainShell = command("plain");
  const plainId = plainShell.env.CODEX_SESSION_ID;
  const plainResume = await controller.call("thread/resume", { threadId: plainId, cwd: fixture });
  const plainRead = await controller.call("thread/read", { threadId: plainId });
  trace("plain.outcome", { threadId: plainId, shellCwd: plainShell.cwd, shellAncestry: plainShell.ancestry.slice(0, 4).map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline?.slice(0, 80)]),
    loaded: (await controller.call("thread/loaded/list", {})).result?.data ?? [], resumeError: plainResume.error ?? null, resumed: plainResume.result ? threadSummary(plainResume.result.thread) : null,
    read: plainRead.result ? threadSummary(plainRead.result.thread) : null, readError: plainRead.error ?? null, locks: lockFiles(), processes: codexProcesses().map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.slice(0, 80)]) });
  if (plainResume.result) await controller.call("thread/unsubscribe", { threadId: plainId });
  hooksBefore = hooks().length;
  await plain.type("/exit");
  await waitFor(() => plain.exited, "plain terminal exit", 30000).catch(() => { plain.child.kill("SIGTERM"); });
  await delay(2000);
  trace("plain.exit", { exited: plain.exited, newHooks: hooksSince(hooksBefore), locks: lockFiles() });

  // Scenario 5: the terminal exits; the daemon-hosted thread unloads later.
  trace("scenario", { name: "terminal-exit" });
  hooksBefore = hooks().length;
  const lockedBefore = lockFiles();
  await tui.type("/exit");
  await waitFor(() => tui.exited, "terminal exit", 30000).catch(() => { tui.child.kill("SIGTERM"); });
  await delay(2000);
  trace("terminal.exit-outcome", { exited: tui.exited, newHooks: hooksSince(hooksBefore), locksBefore: lockedBefore, locksAfter: lockFiles(), loaded: (await controller.call("thread/loaded/list", {})).result?.data ?? [] });
  const unsubscribed = await controller.call("thread/unsubscribe", { threadId: threadAId });
  const unsubscribedAt = Date.now();
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "SessionEnd" && record.payload.session_id === threadAId), "thread A SessionEnd after unsubscribe", 120000);
  const endA = hooks().slice(hooksBefore).find((record) => record.event === "SessionEnd" && record.payload.session_id === threadAId);
  trace("unload.outcome", { unsubscribe: unsubscribed.result ?? unsubscribed.error, delayMs: endA.receiptTime - unsubscribedAt, endCwd: endA.payload.cwd, reason: endA.payload.reason, locks: lockFiles(), loaded: (await controller.call("thread/loaded/list", {})).result?.data ?? [] });

  await tuiB.type("/exit");
  await waitFor(() => tuiB.exited, "terminal b exit", 30000).catch(() => { tuiB.child.kill("SIGTERM"); });
  controller.close();
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const terminal of terminals) {
    if (process.env.SPIKE_DEBUG_TERMINAL === "1") writeFileSync(path.join(root, `terminal-${terminal.name}.txt`), terminal.output);
    if (!terminal.exited) { try { terminal.child.kill("SIGTERM"); } catch {} }
  }
  if (daemonStarted) await daemonCommand(["stop"], "stop").catch(() => {});
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
