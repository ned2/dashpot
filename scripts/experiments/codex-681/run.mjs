// Root-session departure run for Issue #681: can a root Codex Agent Session
// leave its own Issue Worktree, and what does each route Codex offers do to
// its identity, hooks, permissions and Dashpot's Cleanup check? Drives a
// pinned Codex CLI against a loopback Responses API fixture with an isolated
// CODEX_HOME, whose daemon updater is off, under the `workspace-write`
// sandbox, with Dashpot's own Codex hook publisher, in a disposable Dashpot
// Project with one linked Issue Worktree. It records:
//
// - the tools Codex offers the model in a root thread, standalone and on the
//   managed daemon;
// - whether the session's own sandboxed commands can reach the daemon's
//   control socket;
// - `/cd` from the Issue Worktree to the main Worktree, typed by the person
//   in a standalone terminal and in a daemon-hosted one: the thread that
//   follows, its hooks, its history, its directory and write permissions,
//   the old thread's end, and the Cleanup check of the Issue Worktree;
// - the daemon's `thread/settings/update` `cwd`, sent by an external
//   controller to the daemon-hosted thread while it is idle and while a
//   command of its turn runs, with the same observations.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
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
const expectedVersion = process.argv[3] ?? "0.166.0";
const selected = process.env.SPIKE_SCENARIOS ? new Set(process.env.SPIKE_SCENARIOS.split(",")) : null;
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-681-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const issue = path.join(root, "repository.worktrees", "issue");
const worktrees = { main: fixture, issue };
const gates = path.join(root, "gates");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's temporary root
// never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, retained(JSON.stringify(kept)) + "\n");
  return record;
};

// The pinned release runs through a fixture-local `codex` on PATH.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
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
  // Ancestry walks from hooks end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: the main Worktree and one linked Issue
// Worktree, which the session starts in and tries to leave.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
writeFileSync(path.join(fixture, "issues", ".keep"), "");
const dashpot = (args, cwd = fixture) => {
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.dashpot/state/\n");
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "issue", issue);
// The probe's write targets: an ignored file in each checkout.
const writeTarget = (worktree, label) => path.join(worktree, ".dashpot", "state", `probe-${label}`);
for (const worktree of Object.values(worktrees)) mkdirSync(path.join(worktree, ".dashpot", "state"), { recursive: true });

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
  trace("hook", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;
const stripAnsi = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");

// The fixture model. The latest input item that is not a tool call and
// carries `SPIKE:<label>` selects the plan `plans[label]`; the number of tool
// outputs after it selects the step. A `probe` step runs probe.mjs at once;
// a `hold` step runs it once the runner opens the gate named for the label.
// When the plan runs out, the model answers `DONE:<label>`. Each request
// records the tools offered (once per thread, and again when they change),
// which earlier labels its input carries, and the probe report it received.
const probeScript = path.join(here, "probe.mjs");
const plans = {};
const plan = (label, steps) => { plans[label] = steps; };
const markerPattern = /SPIKE:([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const probeOf = (output) => {
  const line = String(output ?? "").split("\n").find((entry) => entry.startsWith("PROBE "));
  return line ? parseJson(line.slice("PROBE ".length)) : null;
};
const modelRequests = [];
const lastToolsByThread = new Map();
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
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  // Every label an input item carries, in input order: the earlier ones are
  // the conversation history the thread holds.
  const labels = [];
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[1]);
    if (found.length) { directiveAt = index; label = found.at(-1); labels.push(...found); }
  });
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? (tool.tools ?? []).map((nested) => [tool.name, nested.name ?? nested.type]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsKey = toolNames.join(",");
  const toolsChanged = lastToolsByThread.get(thread) !== toolsKey;
  lastToolsByThread.set(thread, toolsKey);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const steps = label ? plans[label] ?? [] : [];
  const step = steps[outputs.length] ?? null;
  let item = null;
  if (step) {
    const tool = offered("exec_command");
    const name = `${label}.${outputs.length}`;
    const gate = step === "hold" ? path.join(gates, name) : "-";
    const targets = Object.values(worktrees).map((worktree) => writeTarget(worktree, name));
    item = tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name: "exec_command",
      arguments: JSON.stringify({ cmd: `node ${probeScript} ${name} ${gate} ${targets.join(" ")}`, login: false, yield_time_ms: 120000 }) };
  }
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const request = trace("model.request", { thread, label, step: outputs.length, action: item ? "exec_command" : null, missing: Boolean(step && !item),
    labels, tools: toolsChanged ? toolNames : undefined, probe: latestOutput ? probeOf(latestOutput.output) : null,
    session: payload.client_metadata?.session_id ?? req.headers["session_id"] ?? null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
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

// The model catalog names `fixture` only, a copy of a bundled entry without a
// tool set or code mode.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture", display_name: "Fixture", prefer_websockets: false }] }, null, 2));

// The `workspace-write` sandbox without network, no approval ever asked
// (`never`), and both checkouts trusted, so `/cd` asks nothing.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_provider = "fixture"
check_for_update_on_startup = false

[sandbox_workspace_write]
# The fixture lives under /tmp: without these the sandbox would let every
# command write in both checkouts, whichever one the session is in.
exclude_slash_tmp = true
exclude_tmpdir_env_var = true

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
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only counts its entries and never removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemonPid = () => codexProcesses().find(isDaemon)?.pid ?? null;
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const hooks = () => records.filter((record) => record.kind === "hook");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const mark = () => records.length;
const hookSince = (since, predicate) => hooks().find((record) => record.receipt > since && predicate(record));
const hookTimeline = (since) => hooks().filter((record) => record.receipt > since)
  .map((record) => [record.receipt, record.event, record.payload.session_id ?? null, record.payload.source ?? null, record.payload.reason ?? null, retained(record.payload.cwd ?? ""), record.publisher.status]);
const open = (gate) => { writeFileSync(path.join(gates, gate), ""); trace("gate", { gate }); };

// Dashpot's Cleanup check of a Worktree, its blockers by kind, and every hook
// record Dashpot holds for a session, in each checkout's store.
const check = (worktree) => {
  const ran = dashpot(["worktree", "check", worktree, "--json"]);
  const parsed = parseJson(ran.stdout);
  if (!parsed) return { status: ran.status, stderr: retained(ran.stderr).slice(-400) };
  return { status: ran.status, removable: parsed.removable, uncheckedProcesses: parsed.uncheckedProcesses,
    blockers: parsed.obstacles.map((obstacle) => ({ kind: obstacle.kind, session: obstacle.detail.match(/session ([0-9a-f-]{36})/)?.[1] ?? null,
      live: /is live here/.test(obstacle.detail),
      processes: obstacle.kind === "process" ? [...obstacle.detail.matchAll(/pid \d+ \(([^)]*)\)/g)].map((match) => path.basename(match[1].split(" ")[0])) : undefined })) };
};
const storedSession = (session) => Object.entries(worktrees).flatMap(([name, checkoutPath]) => {
  const directory = path.join(checkoutPath, ".dashpot", "state", "sessions");
  let names = [];
  try { names = readdirSync(directory).filter((file) => file.endsWith(".json")); } catch { return []; }
  return names.flatMap((file) => {
    const record = parseJson(readFileSync(path.join(directory, file), "utf8"));
    if (!record || record.sessionId !== session) return [];
    return [{ store: name, event: record.event, state: record.state, cwd: retained(record.cwd ?? "") }];
  });
});
const observe = (scenario, label, sessions) => trace("observe", { scenario, label,
  stored: Object.fromEntries(sessions.filter(Boolean).map((session) => [session, storedSession(session)])),
  checks: { issue: check(issue), main: check(fixture) } });

// An interactive terminal hosted by `script`, started outside both checkouts
// so that its own process is never inside the Worktree it leaves, unless a
// scenario starts it inside one as a person's shell would. Its screen goes to
// a log in the fixture root; the trace keeps only a labelled tail.
const terminals = [];
const terminal = async (name, args, cwd = root) => {
  const child = spawn("script", ["-qfec", ["codex", ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "160", LINES: "50" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  let screen = "";
  const handle = { name, child, exited: null,
    type: async (text) => { trace("terminal.type", { name, text: retained(text) }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text) => child.stdin.write(text),
    tail: () => retained(screen.slice(-1500)).replace(/\s+/g, " "),
    screen: (label) => trace("screen", { name, label, tail: retained(screen.slice(-1500)).replace(/\s+/g, " ") }) };
  const keep = (chunk) => { const text = stripAnsi(String(chunk)); appendFileSync(logPath, text); screen = (screen + text).slice(-20000); };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, args: args.map(retained), scriptPid: child.pid, cwd: retained(cwd) });
  return handle;
};
const exitTerminal = async (handle) => {
  if (handle.exited) return;
  await handle.type("/exit");
  if (!(await settle(() => handle.exited, `${handle.name} exit`, 15000))) {
    handle.screen(`${handle.name}-exit`);
    handle.key("\u0003"); await delay(500); handle.key("\u0003");
    await settle(() => handle.exited, `${handle.name} interrupt exit`, 10000);
  }
};
// A turn the person submits: its UserPromptSubmit hook names the session and
// the directory the turn runs in.
const submitted = (since, label) => hookSince(since, (record) => record.event === "UserPromptSubmit" && retained(JSON.stringify(record)).includes(label))
  ?? hookSince(since, (record) => record.event === "UserPromptSubmit");
const turnEnded = (since, session) => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id && (!session || record.payload.session_id === session));
const probeFor = (name) => modelRequests.find((record) => record.probe?.label === name)?.probe ?? null;
const promptTurn = async (tui, label) => {
  const since = mark();
  await tui.type(`SPIKE:${label}`);
  await settle(() => submitted(since, label) && turnEnded(submitted(since, label).receipt, submitted(since, label).payload.session_id), `${label} Stop`, 45000);
  const prompt = submitted(since, label);
  return trace("prompt.turn", { label, session: prompt?.payload.session_id ?? null, cwd: retained(prompt?.payload.cwd ?? ""), submitted: Boolean(prompt), since });
};
// The terminal's first turn is its positional prompt, in the Issue Worktree.
const firstTurn = async (name, hosting, label, cwd = root) => {
  const since = mark();
  const tui = await terminal(name, [...hosting, "-C", issue, `SPIKE:${label}`], cwd);
  await settle(() => turnEnded(since), `${label} Stop`, 90000);
  await delay(1000);
  const session = hookSince(since, (record) => record.event === "SessionStart")?.payload.session_id ?? null;
  trace("first.turn", { name, label, session, since });
  return { tui, session, since };
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
  socket.on((text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method) notifications.push({ method: parsed.method, threadId: parsed.params?.threadId ?? parsed.params?.thread?.id ?? null, receivedAt: Date.now(),
      cwd: parsed.params?.threadSettings?.cwd ?? parsed.params?.thread?.cwd ?? null });
  });
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-681-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
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
const readThread = async (client, threadId) => {
  const read = await client.call("thread/read", { threadId });
  const thread = read.result?.thread;
  return thread ? { id: thread.id, cwd: retained(thread.cwd ?? ""), status: thread.status?.type ?? thread.status ?? null, forkedFrom: thread.forkedFromId ?? thread.forkedFromThreadId ?? null } : { error: read.error ?? null };
};

const scenarios = [];
const scenario = (name, run) => scenarios.push({ name, run });
const standalone = ["--disable", "daemon_auto_start"];
let controllers = [];

// `/cd` typed by the person: from the Issue Worktree to the main Worktree.
const cdScenario = async (p, hosting, cwd = root) => {
  plan(`${p}-first`, ["probe"]);
  plan(`${p}-after`, ["probe"]);
  const { tui, session } = await firstTurn(p, hosting, `${p}-first`, cwd);
  observe(p, "before-cd", [session]);
  const cdAt = mark();
  await tui.type(`/cd ${fixture}`);
  await delay(4000);
  tui.screen(`${p}-after-cd`);
  const after = await promptTurn(tui, `${p}-after`);
  const forked = after.session && after.session !== session ? after.session : null;
  observe(p, "after-cd-turn", [session, forked]);
  // The old thread ends when its runtime unloads or its client exits.
  const oldEnded = await settle(() => hookSince(cdAt, (record) => record.event === "SessionEnd" && record.payload.session_id === session), `${p} old SessionEnd`, 100000);
  await delay(2000);
  observe(p, "after-old-end", [session, forked]);
  const exitAt = mark();
  await exitTerminal(tui);
  await settle(() => hookSince(exitAt, (record) => record.event === "SessionEnd" && record.payload.session_id === forked), `${p} new SessionEnd`, 100000);
  await delay(2000);
  observe(p, "after-exit", [session, forked]);
  trace(`${p}.outcome`, { session, forked, oldEnded, hooks: hookTimeline(cdAt - 1), first: probeFor(`${p}-first.0`), after: probeFor(`${p}-after.0`),
    afterLabels: modelRequests.find((record) => record.label === `${p}-after`)?.labels ?? null });
};
scenario("cd-standalone", () => cdScenario("cs", standalone));

scenario("daemon-start", async () => {
  const started = spawnSync("codex", ["app-server", "daemon", "start"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.start", { status: started.status });
  await waitFor(() => existsSync(socketPath) && daemonPid(), "daemon control socket", 30000);
  trace("daemon.ready", { pid: daemonPid() });
});

scenario("cd-daemon", () => cdScenario("cd", []));

// `/cd` from a terminal whose shell was started inside the Issue Worktree, as
// a person's usually is: Codex never changes its own process's directory.
scenario("cd-inside", () => cdScenario("ci", [], issue));

// The daemon's `thread/settings/update` `cwd`, sent by an external
// controller: once while the thread is idle, once while a command of its
// turn is still running.
scenario("settings-daemon", async () => {
  const p = "st";
  plan(`${p}-first`, ["probe"]);
  plan(`${p}-after`, ["probe"]);
  plan(`${p}-mid`, ["hold", "probe"]);
  plan(`${p}-next`, ["probe"]);
  const { tui, session } = await firstTurn(p, [], `${p}-first`);
  observe(p, "before-update", [session]);
  const controller = await daemonClient("controller");
  controllers.push(controller);
  const before = await readThread(controller, session);
  const updateAt = mark();
  const updated = await controller.call("thread/settings/update", { threadId: session, cwd: fixture });
  await delay(2000);
  const afterUpdate = await readThread(controller, session);
  trace("settings.update", { phase: "idle", threadId: session, cwd: "$ROOT/repository", result: updated.result ?? null, error: updated.error ?? null, before, after: afterUpdate,
    notifications: controller.notifications.filter((entry) => entry.receivedAt >= records[updateAt - 1].receiptTime).map((entry) => ({ ...entry, cwd: entry.cwd && retained(entry.cwd) })) });
  tui.screen(`${p}-after-update`);
  observe(p, "after-update", [session]);
  const after = await promptTurn(tui, `${p}-after`);
  observe(p, "after-update-turn", [session]);
  // Back to the Issue Worktree while a command of the turn runs.
  const midAt = mark();
  await tui.type(`SPIKE:${p}-mid`);
  // The Codex hooks Dashpot installs include no tool event, so the fixture
  // model's own record of the held call is the sign that its command runs;
  // exec_command yields within 30 s, so the update lands well inside that.
  await settle(() => modelRequests.some((record) => record.label === `${p}-mid` && record.step === 0 && record.action === "exec_command"), `${p}-mid command started`, 45000);
  await delay(3000);
  const midUpdate = await controller.call("thread/settings/update", { threadId: session, cwd: issue });
  trace("settings.update", { phase: "running", threadId: session, cwd: "$ROOT/repository.worktrees/issue", result: midUpdate.result ?? null, error: midUpdate.error ?? null,
    during: await readThread(controller, session) });
  await delay(1000);
  open(`${p}-mid.0`);
  await settle(() => turnEnded(midAt, session), `${p}-mid Stop`, 60000);
  await delay(1000);
  observe(p, "after-mid-turn", [session]);
  const next = await promptTurn(tui, `${p}-next`);
  observe(p, "after-next-turn", [session]);
  const exitAt = mark();
  await exitTerminal(tui);
  await settle(() => hookSince(exitAt, (record) => record.event === "SessionEnd" && record.payload.session_id === session), `${p} SessionEnd`, 100000);
  await delay(2000);
  observe(p, "after-exit", [session]);
  trace(`${p}.outcome`, { session, afterSession: after.session, nextSession: next.session, hooks: hookTimeline(updateAt - 1),
    probes: Object.fromEntries([`${p}-first.0`, `${p}-after.0`, `${p}-mid.0`, `${p}-mid.1`, `${p}-next.0`].map((name) => [name, probeFor(name)])),
    labels: Object.fromEntries([`${p}-after`, `${p}-next`].map((label) => [label, modelRequests.find((record) => record.label === label)?.labels ?? null])) });
  controller.close();
  controllers = controllers.filter((client) => client !== controller);
});

scenario("daemon-stop", async () => {
  const pid = daemonPid();
  const stopped = spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.stop", { status: stopped.status });
  await settle(() => !pid || !existsSync(`/proc/${pid}`), "daemon gone", 20000);
});

const scripts = ["run.mjs", "hook.mjs", "probe.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["sessions/hook_publish.py", "sessions/hook_records.py", "sessions/hook_scan.py", "sessions/working_directories.py", "repository/cleanup/obstacles.py"].map((file) => `src/dashpot/${file}`);
const digests = () => Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
  .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")]));
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: retained(execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim()),
    binarySHA256: createHash("sha256").update(readFileSync(binary)).digest("hex"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      dirtySource: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean) },
    hookEvents, worktrees, scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    sharedDaemonDirBefore: sharedBefore.length, sourceSHA256: digests() });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  trace("scenario", { name: "hook-trust" });
  const port = await freePort();
  const trustServer = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
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

  for (const { name, run } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await run(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
    await delay(500);
  }
  trace("sources.after", { sourceSHA256: digests() });
  console.log(`Scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: retained(String(error?.stack ?? error)).slice(0, 2000) });
  throw error;
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
  if (daemonPid()) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, timeout: 60000 });
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: codexProcesses().map((entry) => entry.pid) });
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  writeFileSync(path.join(root, "done"), "");
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
