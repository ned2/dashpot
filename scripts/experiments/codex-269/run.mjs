// Isolated Codex declared-relocation experiment for Issue #269. Drives a
// pinned Codex CLI against a loopback Responses API fixture with an isolated
// CODEX_HOME and measures the sequential `codex resume <id> -C <path>` route
// of ADR 0029 on three hosting states of the thread: no managed daemon, a
// daemon-hosted thread still loaded inside its unload window, and a
// daemon-hosted thread already unloaded. Records hook, shell, and protocol
// evidence as a metadata-only trace.
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
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-269-"));
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
      const match = part.type === "input_text" && part.text?.match(/SPIKE:([a-z0-9-]+)/);
      if (match) { label = match[1]; latestUser = index; }
    }
  });
  const outputs = input.slice(latestUser + 1).filter((item) => item.type === "function_call_output");
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => `${tool.name}/${nested.name}`) : [tool.name ?? tool.type]);
  const count = (modelRequests.get(label ?? "none") ?? 0) + 1;
  modelRequests.set(label ?? "none", count);
  const useTool = label && outputs.length < 1 && tools.includes("exec_command");
  trace("model.request", { label, count, outputs: outputs.length, model: payload.model, stream: payload.stream, toolCount: tools.length, previousResponseId: payload.previous_response_id ?? null, store: payload.store ?? null });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  if (useTool) {
    const item = { type: "function_call", call_id: `call_${label}_${count}`, name: "exec_command", arguments: JSON.stringify({ cmd: `node ${commandScript} ${label} 200`, login: false }) };
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
const processList = () => codexProcesses().map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.slice(0, 100)]);
const daemonPid = () => codexProcesses().find((entry) => /--managed-daemon/.test(entry.cmdline))?.pid ?? null;
const hooks = () => records.filter((record) => record.kind === "hook");
// Each hook since a mark: event, thread, source or reason, cwd, and the
// milliseconds since the mark's time when one is given.
const hooksSince = (count, since = null) => hooks().slice(count).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source ?? null, record.payload.cwd, since === null ? null : record.receiptTime - since]);
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const waitQuietly = async (predicate, timeout) => waitFor(predicate, "", timeout).catch(() => false);
// The thread fields the trace keeps: identity and hosting, never content.
const threadSummary = (thread) => thread && ({ id: thread.id, sessionId: thread.sessionId, cwd: thread.cwd ?? thread.environments?.[0]?.cwd ?? null, source: thread.source, status: thread.status, ephemeral: thread.ephemeral });
const lockFiles = () => { try { return readdirSync(path.join(env.CODEX_HOME, "thread-writer-locks")); } catch { return []; } };
// The shell's hosting: the daemon when its pid is in the shell's ancestry,
// otherwise the nearest `codex` ancestor.
const hostOf = (shell) => {
  if (!shell) return null;
  const daemon = daemonPid();
  const inDaemon = daemon !== null && shell.ancestry.some((entry) => entry.pid === daemon);
  const codex = shell.ancestry.find((entry) => entry.comm === "codex");
  return { daemonHosted: inDaemon, hostPid: inDaemon ? daemon : codex?.pid ?? null, hostCmdline: (inDaemon ? shell.ancestry.find((entry) => entry.pid === daemon) : codex)?.cmdline?.slice(0, 100) ?? null };
};

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
// A JSON-RPC client on the daemon's control socket. The runner's controller
// only reads (`thread/read`, `thread/loaded/list`, `hooks/list`) and never
// subscribes, so the terminals are the threads' only subscribers.
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(socketPath);
  let nextId = 0;
  const pending = new Map();
  socket.on("message", (text) => {
    let parsed;
    try { parsed = JSON.parse(text); } catch { return; }
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); }
  });
  const call = (method, params = {}) => new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); });
  const init = await Promise.race([call("initialize", { clientInfo: { name: `dashpot-269-${name}`, version: "0" }, capabilities: { experimentalApi: true } }), delay(15000).then(() => ({ timeout: true }))]);
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: "unix-websocket", socket: socketPath, userAgent: init.result?.userAgent, error: init.error ?? null, timeout: init.timeout ?? false });
  assert(init.result, `${name} initialized on the control socket: ${JSON.stringify(init)}`);
  return { name, call, close: () => socket.close() };
};
const readThread = async (client, threadId) => {
  if (!client) return { unavailable: "no daemon" };
  const read = await client.call("thread/read", { threadId });
  return read.result ? threadSummary(read.result.thread) : { error: read.error };
};
const loadedThreads = async (client) => client ? ((await client.call("thread/loaded/list", {})).result?.data ?? []) : [];

// An interactive terminal hosted by `script`; only the markers the runner
// waits for are kept from its screen.
const terminals = [];
const startTerminal = async (name, cwd, args) => {
  const child = spawn("script", ["-qfec", [binary, ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  // The composer treats a burst of keys as a paste, so Enter follows the text
  // after a pause; the screen is flattened to letters for marker matching.
  const terminal = { name, child, output: "", exited: null, startedAt: Date.now(),
    type: async (text) => { child.stdin.write(text); await delay(600); child.stdin.write("\r"); },
    screen: () => terminal.output.replace(/[^A-Za-z0-9:\/.-]/g, "") };
  child.stdout.on("data", (chunk) => { terminal.output += stripAnsi(String(chunk)); });
  child.on("exit", (status, signal) => { terminal.exited = { status, signal, at: Date.now() }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(terminal);
  trace("terminal.start", { name, cwd, args, scriptPid: child.pid });
  return terminal;
};
const exitTerminal = async (terminal) => {
  await terminal.type("/exit");
  await waitFor(() => terminal.exited, `${terminal.name} exit`, 30000).catch(() => { terminal.child.kill("SIGTERM"); });
  return terminal.exited?.at ?? Date.now();
};
// What the resumed terminal's screen says about its state, as booleans only.
const screenState = (terminal) => ({ readOnlyNotice: /read-?only|another(app|client)|activewriter/i.test(terminal.screen()), picker: /Resume a previous session|ResumeSession/i.test(terminal.screen()) });

// One measurement: a plain terminal in `other` completes a turn and exits;
// `codex resume <id> -C third` follows after `resumeAfter` decides the moment;
// the resumed terminal runs the positional prompt and a typed second turn,
// then the runner watches for a late SessionEnd of the thread before exiting
// the resumed terminal and waiting for the thread's end.
const measure = async (name, client, resumeAfter) => {
  trace("scenario", { name });
  const hooksAtStart = hooks().length;
  const first = await startTerminal(`${name}-first`, other, ["-C", other, `SPIKE:${name}-first`]);
  await waitFor(() => command(`${name}-first`) || first.exited, `${name} first command`, 90000);
  assert(!first.exited, `${name} first terminal exited early`);
  const firstShell = command(`${name}-first`);
  const threadId = firstShell.env.CODEX_SESSION_ID;
  await waitFor(() => hooks().slice(hooksAtStart).some((record) => record.event === "Stop" && record.payload.session_id === threadId), `${name} first Stop`, 60000);
  trace("first.identity", { scenario: name, threadId, shellCwd: firstShell.cwd, shellEnv: firstShell.env, host: hostOf(firstShell), loaded: await loadedThreads(client), thread: await readThread(client, threadId),
    locks: lockFiles(), hooks: hooksSince(hooksAtStart), processes: processList() });
  assert.equal(firstShell.cwd, other);

  const hooksAtExit = hooks().length;
  const exitedAt = await exitTerminal(first);
  // `resumeDelayMs` is when the scenario released the resume; the launch
  // itself follows the state snapshot below, and `resume.outcome` records it.
  const resumeDelayMs = await resumeAfter({ threadId, hooksAtExit, exitedAt });
  trace("first.exit", { scenario: name, threadId, exited: first.exited, resumeDelayMs, hooksSinceExit: hooksSince(hooksAtExit, exitedAt), locks: lockFiles(), loaded: await loadedThreads(client), thread: await readThread(client, threadId), processes: processList() });

  const hooksAtResume = hooks().length;
  const resumedAt = Date.now();
  const resumed = await startTerminal(`${name}-resumed`, third, ["resume", threadId, "-C", third, `SPIKE:${name}-resumed`]);
  const ran = await waitQuietly(() => command(`${name}-resumed`) || resumed.exited, 90000);
  const resumedShell = command(`${name}-resumed`);
  if (resumedShell) await waitQuietly(() => hooks().slice(hooksAtResume).some((record) => record.event === "Stop" && record.receiptTime > resumedShell.receiptTime), 60000);
  trace("resume.outcome", { scenario: name, threadId, launchDelayMs: resumedAt - exitedAt, ran: Boolean(resumedShell), exited: resumed.exited, screen: screenState(resumed), shellCwd: resumedShell?.cwd ?? null, shellEnv: resumedShell?.env ?? null, host: hostOf(resumedShell),
    sameThread: resumedShell ? resumedShell.env.CODEX_SESSION_ID === threadId : null, hooks: hooksSince(hooksAtResume, resumedAt), loaded: await loadedThreads(client), thread: await readThread(client, threadId), locks: lockFiles(), processes: processList() });
  assert(ran && resumedShell, `${name}: the resumed terminal ran its prompt`);

  // The terminal's own next turn shows where the thread now lives.
  const hooksAtSecond = hooks().length;
  await resumed.type(`SPIKE:${name}-second`);
  await waitFor(() => command(`${name}-second`), `${name} second turn`, 60000);
  await waitFor(() => hooks().slice(hooksAtSecond).some((record) => record.event === "Stop"), `${name} second Stop`, 60000);
  const secondShell = command(`${name}-second`);
  trace("resume.second-turn", { scenario: name, threadId, shellCwd: secondShell.cwd, shellEnv: secondShell.env, host: hostOf(secondShell), hooks: hooksSince(hooksAtSecond), thread: await readThread(client, threadId) });

  // A late SessionEnd for the thread while the resumed terminal is alive would
  // be the old runtime ending after the resume.
  const hooksAtWatch = hooks().length;
  const lateEnd = () => hooks().slice(hooksAtResume).find((record) => record.event === "SessionEnd" && record.payload.session_id === threadId);
  await waitQuietly(() => lateEnd() || resumed.exited, 90000);
  const late = lateEnd();
  trace("resume.late-end-watch", { scenario: name, threadId, lateSessionEnd: late ? { cwd: late.payload.cwd, reason: late.payload.reason, msAfterFirstExit: late.receiptTime - exitedAt, msAfterResume: late.receiptTime - resumedAt } : null,
    resumedExited: resumed.exited, hooksWhileWatching: hooksSince(hooksAtWatch, resumedAt), thread: await readThread(client, threadId), loaded: await loadedThreads(client), locks: lockFiles() });

  const hooksAtFinal = hooks().length;
  const finalExitAt = await exitTerminal(resumed);
  const ended = () => hooks().slice(hooksAtFinal).find((record) => record.event === "SessionEnd" && record.payload.session_id === threadId);
  await waitQuietly(ended, 120000);
  const end = ended();
  trace("resume.final-exit", { scenario: name, threadId, exited: resumed.exited, sessionEnd: end ? { cwd: end.payload.cwd, reason: end.payload.reason, msAfterExit: end.receiptTime - finalExitAt } : null,
    hooks: hooksSince(hooksAtFinal, finalExitAt), loaded: await loadedThreads(client), locks: lockFiles(), processes: processList() });
  return threadId;
};

let daemonStarted = false;
let controller = null;
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, binary, binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    env: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CODEX") || key === "SPIKE_SINK")), fixture, other, third, hookEvents, socketPath,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // Setup: start the daemon once to trust the fixture hooks through the
  // ledger, then stop it so the control scenario runs without one.
  trace("scenario", { name: "hook-trust" });
  await daemonCommand(["start"], "start");
  daemonStarted = true;
  await waitFor(() => existsSync(socketPath), "daemon control socket", 30000);
  controller = await daemonClient("trust");
  const listed = await controller.call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert(entries.length === hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await controller.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  controller.close();
  controller = null;
  await daemonCommand(["stop"], "stop-for-control");
  daemonStarted = false;
  await delay(1000);
  trace("processes", { label: "after-daemon-stop", processes: processList(), socketExists: existsSync(socketPath) });

  // Scenario 3 of the Issue, run first: the no-daemon control ADR 0029 was
  // verified against. Its `resumeAfter` records how the first terminal ended.
  await measure("no-daemon", null, async ({ threadId, hooksAtExit, exitedAt }) => {
    await waitQuietly(() => hooks().slice(hooksAtExit).some((record) => record.event === "SessionEnd" && record.payload.session_id === threadId), 15000);
    return Date.now() - exitedAt;
  });
  trace("processes", { label: "after-no-daemon", processes: processList(), socketExists: existsSync(socketPath) });

  // Scenario 1: daemon-hosted thread, resume immediately after the terminal
  // exits, inside the unload window.
  await daemonCommand(["start"], "start");
  daemonStarted = true;
  await waitFor(() => existsSync(socketPath), "daemon control socket", 30000);
  controller = await daemonClient("controller");
  trace("processes", { label: "daemon-restarted", processes: processList(), daemonPid: daemonPid() });
  await measure("in-window", controller, async ({ exitedAt }) => Date.now() - exitedAt);

  // Scenario 2: the same thread lifecycle, resumed only after the daemon has
  // unloaded the thread and its SessionEnd was observed.
  await measure("after-unload", controller, async ({ threadId, hooksAtExit, exitedAt }) => {
    await waitFor(() => hooks().slice(hooksAtExit).some((record) => record.event === "SessionEnd" && record.payload.session_id === threadId), "SessionEnd before the after-unload resume", 120000);
    return Date.now() - exitedAt;
  });

  controller.close();
  controller = null;
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const terminal of terminals) {
    if (process.env.SPIKE_DEBUG_TERMINAL === "1") writeFileSync(path.join(root, `terminal-${terminal.name}.txt`), terminal.output);
    if (!terminal.exited) { try { terminal.child.kill("SIGTERM"); } catch {} }
  }
  if (controller) controller.close();
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
