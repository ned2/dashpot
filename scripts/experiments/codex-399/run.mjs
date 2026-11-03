// Interruption run for Issue #399: drives a pinned Codex CLI against a
// loopback Responses API fixture, with an isolated CODEX_HOME whose daemon
// updater is off and Dashpot's real Codex hook publisher, in a disposable
// Dashpot Project whose Issues are Local Issue Markdown. A multi-agent v2
// lead spawns sub-agents that run a held command, and the run interrupts in
// the three ways #399 names, beside an ordinary interruption as control:
//
//   - `daemon-esc` (control): Esc in a terminal attached to the managed
//     daemon, with the lead's own thread on screen and its turn in
//     `wait_agent`;
//   - `daemon-picker`: the same terminal kind, with a child selected in the
//     agent picker (`/subagents`) and Esc pressed on it while the lead waits
//     and a sibling works, then the lead's unload once the terminal exits;
//   - `interrupt-agent`: the lead model's `interrupt_agent` on a working
//     child, the 0.160.0 measurement of #420 repeated on the daemon;
//   - `standalone-esc`: Esc in a `--no-daemon` terminal, with no daemon
//     running and the lead's own thread on screen;
//   - `standalone-picker`: a child selected in that terminal kind's agent
//     picker, then Esc.
//
// Terminals run in a private tmux server whose socket is inside the fixture.
// For every scenario the trace records the hooks Codex publishes, each
// shell's identity and lifetime, the model requests by thread, every
// thread's turn outcomes from Codex's own rollout files (event types, turn
// IDs and reasons only), the agent picker's rows and the thread each
// terminal shows, a controller's `thread/read` where a daemon hosts the
// threads, and Dashpot's published view, `worktree check` and `work show`;
// never a prompt or a screen's text.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict] [--codex-source <checkout>]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";
import { connectUnixWebSocket } from "./uds-websocket.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.166.0";
// A fixture below a harness session would join that session's process tree,
// and Dashpot would attach the fixture's hooks to it.
const runnerAncestry = ancestry(process.ppid, 64, 1);
const isHarness = (entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline);
const harnessAbove = runnerAncestry.find(isHarness);
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

// Outside every Dashpot Project and outside `/tmp`, whose shared Codex
// daemon directory belongs to the operator's own sessions; short enough for
// the daemon's control socket.
const root = mkdtempSync(path.join("/var/tmp", "dashpot-codex-399-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const spare = path.join(root, "spare-worktree");
const worktrees = { main: fixture, spare };
const tracePath = path.join(root, "trace.jsonl");
const screensDir = path.join(root, "screens");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
// The operator's home directory, user name, host name, this checkout and the
// fixture's root never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const userName = new RegExp(`\\b${os.userInfo().username}\\b`, "g");
const clean = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(path.basename(root), "<fixture>").replaceAll(here, "$EXPERIMENT")
  .replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>").replace(userName, "<user>");
let scenario = "setup";
const trace = (kind, fields = {}) => {
  const record = { kind, scenario, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, clean(JSON.stringify(record)) + "\n");
  return record;
};

// The pinned release runs read-only through a fixture-local `codex` on PATH.
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
  TERM: "xterm-256color",
  LANG: "C.UTF-8",
  SPIKE_PUBLISHER: publisher,
  SPIKE_DASHPOT: dashpotCommand,
  // Ancestry walks from hooks end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, screensDir, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) {
  mkdirSync(dir, { recursive: true });
}
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: Local Issue Markdown Issues, the main
// working tree, and one linked Worktree no session works in, whose
// `worktree check` shows the Repository-wide `sub-agent` blocker.
const issueNumbers = [1, 2, 3, 4, 5];
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of issueNumbers) {
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
git("worktree", "add", "-b", "spare", spare);

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
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` (a person's prompt or a spawn
// message) selects the plan `plans[label]`; the number of tool outputs after
// that item selects the step. Each step becomes one tool call; when the plan
// runs out, the model answers `DONE:<label>`. Steps name a tool, never a tool
// set: the call goes to whichever namespace offers it.
const commandScript = path.join(here, "command.mjs");
const exec = (hold = 200, work = "-") => ({ exec: { hold, work } });
// Each lead binds its own Issue in the main Worktree, spawns its children
// and waits; `interrupt-agent`'s lead interrupts its child itself.
const plans = {
  de: [exec(200, "start-1"), { spawn: ["worker_c", "dc"] }, { wait: 60000 }],
  dc: [exec(20000)],
  dp: [exec(200, "start-2"), { spawn: ["worker_p", "dpp"] }, { spawn: ["worker_s", "dps"] }, { wait: 60000 }, { list: true }],
  dpp: [exec(20000)],
  // The sibling outlives the interrupted child, then reads `work show`.
  dps: [exec(25000), exec(200, "show")],
  ia: [exec(200, "start-3"), { spawn: ["worker_e", "iae"] }, exec(3000), { interrupt: "/root/worker_e" }, { list: true }],
  iae: [exec(20000)],
  se: [exec(200, "start-4"), { spawn: ["worker_x", "sex"] }, { wait: 60000 }],
  sex: [exec(20000)],
  sp: [exec(200, "start-5"), { spawn: ["worker_q", "spq"] }, { spawn: ["worker_r", "spr"] }, { wait: 60000 }, { list: true }],
  spq: [exec(20000)],
  spr: [exec(25000), exec(200, "show")],
};
const markerPattern = /SPIKE:([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const modelRequests = [];
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const lastToolsByThread = new Map();
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
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)];
    if (found.length) { directiveAt = index; label = found.at(-1)[1]; }
  });
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsChanged = lastToolsByThread.get(thread) !== toolNames.join(",");
  lastToolsByThread.set(thread, toolNames.join(","));
  const plan = label ? plans[label] ?? [] : [];
  const step = plan[outputs.length] ?? null;
  const call = (name, args) => {
    const tool = tools.find(([, toolName]) => toolName === name);
    return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.exec) {
    action = "exec_command";
    item = call("exec_command", { cmd: `node ${commandScript} ${label}.${outputs.length} ${step.exec.hold} ${step.exec.work}`, login: false, yield_time_ms: 120000 });
  } else if (step?.spawn) {
    action = "spawn_agent";
    item = call("spawn_agent", { message: `SPIKE:${step.spawn[1]}`, task_name: step.spawn[0], fork_turns: "none" });
  } else if (step?.wait) {
    action = "wait_agent";
    item = call("wait_agent", { timeout_ms: step.wait });
  } else if (step?.interrupt) {
    action = "interrupt_agent";
    item = call("interrupt_agent", { target: step.interrupt });
  } else if (step?.list) {
    action = "list_agents";
    item = call("list_agents", {});
  }
  // The reply to the previous call, which Codex composes. A worker's final
  // message, which `wait_agent` and `list_agents` relay, is the fixture
  // model's own text, so the trace replaces it.
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const lastOutput = latestOutput ? String(latestOutput.output ?? "").replace(/DONE:[a-z0-9_-]+/g, "<worker reply>").slice(0, 600) : null;
  const request = trace("model.request", { thread, label, step: outputs.length, action, missing: Boolean(step && !item), lastOutput,
    lastCallId: latestOutput?.call_id ?? null, tools: toolsChanged ? toolNames : undefined, parentThread: req.headers["x-codex-parent-thread-id"] ?? null });
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
const hooksDocument = { hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])) };
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify(hooksDocument, null, 2));

// The model catalog names `fixture-v2`, a copy of a bundled entry without a
// tool set or code mode, declaring multi-agent v2, the tool set the bundled
// catalog gives current models and the one that offers `interrupt_agent`.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = ${JSON.stringify(catalogPath)}
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"
check_for_update_on_startup = false
suppress_unstable_features_warning = true

[features]
hooks = true
multi_agent = true
multi_agent_v2 = true
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
${Object.values(worktrees).map((dir) => `\n[projects.${JSON.stringify(dir)}]\ntrust_level = "trusted"\n`).join("")}`);
// The fixture daemon's updater stays off: installing a release could replace
// or restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => parseJson(readFileSync(daemonSettingsPath, "utf8"));
// The shared daemon directory is only read, never written by the runner.
// Codex binds a daemon's control socket there, named by the SHA-256 of the
// socket path it advertises, beside a `.lock`; other processes' entries come
// and go, so only the fixture's own are attributed.
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
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.slice(0, 200)];
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemons = () => codexProcesses().filter(isDaemon);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const sharedSocketName = () => {
  try { return sha(path.join(realpathSync(path.dirname(socketPath)), path.basename(socketPath))); } catch { return null; }
};
const fixtureShared = () => {
  const name = sharedSocketName();
  return { socket: Boolean(name) && existsSync(path.join(sharedDaemonDir, name)), lock: Boolean(name) && existsSync(path.join(sharedDaemonDir, `${name}.lock`)) };
};
const processes = (label) => trace("processes", { label, processes: codexProcesses().map(brief), daemons: daemons().map((entry) => entry.pid),
  socketExists: existsSync(socketPath), fixtureShared: fixtureShared(), daemonSettings: daemonSettings() });
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const hooks = () => records.filter((record) => record.kind === "hook");
const command = (label, phase = "start") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;
const hookSince = (since, predicate) => hooks().some((record) => record.receiptTime >= since && predicate(record));
const requestsOf = (thread, after = 0) => modelRequests.filter((record) => record.thread === thread && record.receiptTime > after);
const settlersDone = async () => {
  await delay(500);
  await quietly(waitFor(() => !codexProcesses().some((entry) => / -m dashpot\.hook settle /.test(entry.cmdline)), "settlers exit", 15000));
};

// Codex's own record of every thread: the first line of each rollout names
// the thread and, for a sub-agent, its parent and agent path; of the rest,
// only turn events are kept, by type, turn ID and reason.
const rollouts = () => {
  const threads = {};
  const walk = (dir) => {
    let entries = [];
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) { walk(file); continue; }
      if (!entry.name.endsWith(".jsonl")) continue;
      const lines = readFileSync(file, "utf8").split("\n").map(parseJson).filter(Boolean);
      const meta = lines.find((line) => line.type === "session_meta")?.payload ?? {};
      const spawned = meta.source?.subagent?.thread_spawn ?? null;
      const turns = lines.filter((line) => line.type === "event_msg" && /^(task_started|task_complete|turn_aborted)$/.test(line.payload?.type ?? ""))
        .map((line) => ({ type: line.payload.type, turn: line.payload.turn_id ?? null, rootTurn: line.payload.root_turn_id ?? line.payload.turn_attribution?.root_turn_id ?? null,
          reason: line.payload.reason ?? null, at: line.timestamp ?? null }));
      if (meta.id) threads[meta.id] = { parent: spawned?.parent_thread_id ?? null, agentPath: spawned?.agent_path ?? null, turns };
    }
  };
  walk(path.join(env.CODEX_HOME, "sessions"));
  return threads;
};

// Dashpot's published view of the fixture, and its Worktree checks.
const view = (label) => {
  const ran = dashpot(["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400), agentRuns: parsed?.agentRuns ?? null,
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })) });
};
const worktreeCheck = (label, dir = spare) => {
  const ran = dashpot(["worktree", "check", dir, "--json"]);
  return trace("dashpot.worktree-check", { label, worktree: dir, status: ran.status, result: parseJson(ran.stdout), stderr: ran.stderr.slice(0, 300) });
};
const observe = (label) => { view(label); worktreeCheck(label); };

// A JSON-RPC client over the daemon's control socket, which speaks WebSocket
// over a Unix domain socket. It only reads threads; it starts no turn on a
// terminal's thread.
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(socketPath);
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  socket.on("message", (text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (/^(thread|turn)\//.test(parsed.method ?? "")) {
      const { threadId, turn, status, thread } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id, status: status ?? turn?.status, receivedAt: Date.now() });
    }
  });
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-399-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, notifications, close: () => socket.close() };
};
const readThread = async (client, threadId) => {
  const read = await client.call("thread/read", { threadId });
  const thread = read.result?.thread;
  return thread ? { id: thread.id, status: thread.status } : { id: threadId, error: read.error?.message ?? null };
};

// Interactive terminals in a private tmux server, whose socket and
// configuration are the fixture's own.
const tmuxSocket = path.join(root, "tmux.sock");
const tmux = (...args) => execFileSync("tmux", ["-S", tmuxSocket, "-f", "/dev/null", ...args], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
let screenCount = 0;
const terminals = [];
const terminal = (name, args, cwd = fixture) => {
  tmux("new-session", "-d", "-s", name, "-x", "220", "-y", "50", "-c", cwd, "--", "codex", ...args);
  const panePid = Number(tmux("display-message", "-p", "-t", name, "#{pane_pid}").trim());
  const handle = {
    name, panePid,
    alive: () => existsSync(`/proc/${panePid}`),
    // The screen stays in the fixture for debugging; the trace keeps only
    // what the runner derives from it.
    screen: (tag) => {
      let text = "";
      try { text = tmux("capture-pane", "-p", "-t", name); } catch { return ""; }
      if (tag) writeFileSync(path.join(screensDir, `${String(++screenCount).padStart(3, "0")}-${name}-${tag}.txt`), text);
      return text;
    },
    keys: (...keys) => tmux("send-keys", "-t", name, ...keys),
    // The composer treats a burst of keys as a paste, so Enter follows the
    // text after a pause.
    type: async (text) => { tmux("send-keys", "-t", name, "-l", text); await delay(700); tmux("send-keys", "-t", name, "Enter"); },
  };
  terminals.push(handle);
  trace("terminal.start", { name, args, cwd, panePid, process: (() => { try { return brief(describe(panePid)); } catch { return null; } })() });
  return handle;
};
const exitTerminal = async (handle) => {
  await handle.type("/exit");
  const exited = await quietly(waitFor(() => !handle.alive(), `${handle.name} exits`, 20000));
  trace("terminal.exit", { name: handle.name, exited });
  if (!exited) try { tmux("kill-session", "-t", handle.name); } catch {}
};
// The agent picker's rows as the screen draws them: the selection marker, a
// row's name, whether it is the thread on screen, and the thread ID it shows.
const pickerRows = (screen) => screen.split("\n").flatMap((line) => {
  const match = line.match(/^\s*(›)?\s*\d+\.\s+•\s+(\S.*?)\s{2,}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$/);
  if (!match) return [];
  const current = / \(current\)$/.test(match[2]);
  return [{ selected: Boolean(match[1]), name: match[2].replace(/ \(current\)$/, ""), current, thread: match[3] }];
});
// The thread a terminal has on screen, as its status line names it after the
// model and directory: `Main [default]` for the lead, an agent path for a
// sub-agent. A sub-agent's composer also says its input is disabled.
const onScreen = (screen) => {
  const status = screen.split("\n").findLast((line) => /Fixture v2/.test(line) && / · /.test(line));
  return { viewing: status ? status.trim().split(" · ").at(-1).replaceAll("`", "") : null,
    inputDisabled: /Viewing sub-agent — direct input is disabled/.test(screen) };
};
// What the terminal shows once Esc has taken effect: the thread on screen
// and the interrupt notice, which the terminal draws a moment after the hook.
const afterEsc = async (handle) => {
  const noticed = await quietly(waitFor(() => /Conversation interrupted/.test(handle.screen()), "the interrupt notice", 10000));
  trace("screen.after-esc", { terminal: handle.name, ...onScreen(handle.screen("after-esc")), interruptedNotice: noticed });
};
// Open `/subagents`, move the selection to the child's row and choose it.
const selectInPicker = async (handle, child) => {
  await handle.type("/subagents");
  let rows = [];
  const found = await quietly(waitFor(() => { rows = pickerRows(handle.screen()); return rows.some((row) => row.thread === child); }, "the picker lists the child", 15000));
  const opened = handle.screen("picker-opened");
  const openedRows = pickerRows(opened);
  trace("picker.opened", { terminal: handle.name, child, found, rows: openedRows, title: /Subagents/.test(opened) });
  assert(found, `the agent picker lists ${child}`);
  for (let moves = 0; moves < 10; moves += 1) {
    rows = pickerRows(handle.screen());
    if (rows.find((row) => row.selected)?.thread === child) break;
    handle.keys("Down");
    await delay(300);
  }
  const chosen = pickerRows(handle.screen("picker-chosen"));
  trace("picker.chosen", { terminal: handle.name, child, rows: chosen });
  assert.equal(chosen.find((row) => row.selected)?.thread, child, "the child's row is selected");
  handle.keys("Enter");
  await delay(1500);
  const after = handle.screen("child-selected");
  trace("picker.selected", { terminal: handle.name, child, pickerClosed: pickerRows(after).length === 0, ...onScreen(after) });
};

// One interrupted scenario's bounded observation: until the interrupted
// child's command has ended and a further `quietMs` has passed, or `capMs`
// after the interrupt, whichever is sooner, and until every `waitFor` agent
// that should stop has done so.
const observeWindow = async ({ interruptedAt, child, siblings = [], quietMs = 15000, capMs = 60000 }) => {
  const childLabel = records.find((record) => record.kind === "command" && record.phase === "start" && record.env.CODEX_THREAD_ID === child)?.label;
  await quietly(waitFor(() => (command(childLabel, "end") || command(childLabel, "signal")) && Date.now() - Math.max((command(childLabel, "end") ?? command(childLabel, "signal")).receiptTime, interruptedAt) >= quietMs,
    "the interrupted child's window", capMs));
  for (const sibling of siblings) await quietly(waitFor(() => hookSince(interruptedAt, (record) => record.event === "SubagentStop" && record.payload.agent_id === sibling), "sibling stops", capMs));
  await delay(2000);
  const windowEnd = Date.now();
  return { interruptedAt, windowEnd, childLabel, childEnd: command(childLabel, "end")?.receiptTime ?? null, childSignal: command(childLabel, "signal")?.signal ?? null };
};
const waitForLeadWaiting = (lead, after) => waitFor(() => requestsOf(lead, after).some((record) => record.action === "wait_agent"), "the lead calls wait_agent", 60000);
const leadStopped = (lead, after) => hookSince(after, (record) => record.event === "Stop" && record.payload.session_id === lead && !record.payload.agent_id);

const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "uds-websocket.mjs", "verify.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "hook_scan.py", "processes.py", "session_exits.py", "work.py"].map((file) => `src/dashpot/sessions/${file}`)
  .concat(["src/dashpot/repository/cleanup/obstacles.py"]);
let controller = null;
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", path.relative(checkout, here)], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, expectedVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    tmux: execFileSync("tmux", ["-V"], { encoding: "utf8" }).trim(),
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), binarySHA256: sha(readFileSync(binary)),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, experimentDirty: dirty }, worktrees, socketPath, hookEvents, hooksDocument,
    config: readFileSync(configPath, "utf8"), updater: daemonSettings(), fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2" },
    runnerAncestry: runnerAncestry.map((entry) => ({ pid: entry.pid, comm: entry.comm, harness: isHarness(entry) })), sharedDaemonDirBefore: sharedBefore.length,
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, sha(readFileSync(file))])) });

  // Trust the fixture hooks through Codex's ledger, on a stdio app-server.
  scenario = "hook-trust";
  trace("scenario", { name: scenario });
  const trust = spawn("codex", ["app-server"], { cwd: fixture, env, stdio: ["pipe", "pipe", "pipe"] });
  const trustReplies = new Map();
  readline.createInterface({ input: trust.stdout }).on("line", (line) => { const message = parseJson(line); if (message?.id !== undefined) trustReplies.set(message.id, message); });
  trust.stderr.on("data", () => {});
  const trustCall = async (id, method, params) => {
    trust.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    await waitFor(() => trustReplies.has(id), `${method} replied`, 30000);
    return trustReplies.get(id);
  };
  await trustCall(1, "initialize", { clientInfo: { name: "fixture-399", version: "0" }, capabilities: { experimentalApi: true } });
  trust.stdin.write(JSON.stringify({ method: "initialized" }) + "\n");
  const entries = (await trustCall(2, "hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, "fixture hooks listed");
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await trustCall(3, "hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.length === hookEvents.length && relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  trust.stdin.end();
  trust.kill("SIGTERM");
  if (trust.exitCode === null && trust.signalCode === null) await once(trust, "exit");
  await delay(500);

  // Control: Esc in a daemon-attached terminal, on the lead's own thread,
  // while its turn waits on a working child. The first plain terminal
  // starts the managed daemon.
  scenario = "daemon-esc";
  trace("scenario", { name: scenario });
  const deStart = Date.now();
  const td = terminal("daemon-esc", ["-C", fixture, "SPIKE:de"]);
  await waitFor(() => command("dc.0"), "the control child's command", 90000);
  const deLead = threadOf("de.0");
  const deChild = threadOf("dc.0");
  await waitForLeadWaiting(deLead, deStart);
  await waitFor(() => daemons().length === 1 && existsSync(socketPath), "the managed daemon", 30000);
  processes("daemon-esc-running");
  controller = await daemonClient("reader");
  const deBefore = { lead: await readThread(controller, deLead), child: await readThread(controller, deChild) };
  observe("daemon-esc-before");
  await delay(1500);
  const deScreen = onScreen(td.screen("before-esc"));
  td.keys("Escape");
  const deEsc = Date.now();
  trace("interrupt", { how: "esc", terminal: td.name, lead: deLead, child: deChild, ...deScreen });
  await quietly(waitFor(() => hookSince(deEsc, (record) => record.event === "Interrupt" && record.payload.session_id === deLead), "Esc publishes the lead's Interrupt", 10000));
  await afterEsc(td);
  const deWindow = await observeWindow({ interruptedAt: deEsc, child: deChild, siblings: [deChild], quietMs: 5000 });
  trace("daemon-esc.outcome", { lead: deLead, child: deChild, ...deWindow, before: deBefore,
    after: { lead: await readThread(controller, deLead), child: await readThread(controller, deChild) }, rollouts: rollouts() });
  observe("daemon-esc-after");
  await exitTerminal(td);

  // The agent picker on the daemon: a child is selected and Esc pressed on
  // it while the lead waits and a sibling works.
  scenario = "daemon-picker";
  trace("scenario", { name: scenario });
  const dpStart = Date.now();
  const tp = terminal("daemon-picker", ["-C", fixture, "SPIKE:dp"]);
  await waitFor(() => command("dpp.0") && command("dps.0"), "both children's commands", 90000);
  const dpLead = threadOf("dp.0");
  const dpChild = threadOf("dpp.0");
  const dpSibling = threadOf("dps.0");
  await waitForLeadWaiting(dpLead, dpStart);
  observe("daemon-picker-before");
  await selectInPicker(tp, dpChild);
  const dpBefore = { lead: await readThread(controller, dpLead), child: await readThread(controller, dpChild), sibling: await readThread(controller, dpSibling) };
  const dpScreen = onScreen(tp.screen("before-esc"));
  tp.keys("Escape");
  const dpEsc = Date.now();
  trace("interrupt", { how: "picker-esc", terminal: tp.name, lead: dpLead, child: dpChild, sibling: dpSibling, ...dpScreen });
  await delay(1500);
  await afterEsc(tp);
  const dpWindow = await observeWindow({ interruptedAt: dpEsc, child: dpChild, siblings: [dpSibling] });
  await quietly(waitFor(() => leadStopped(dpLead, dpStart), "the picker lead's turn stops", 30000));
  await delay(1500);
  trace("daemon-picker.outcome", { lead: dpLead, child: dpChild, sibling: dpSibling, ...dpWindow, before: dpBefore,
    after: { lead: await readThread(controller, dpLead), child: await readThread(controller, dpChild), sibling: await readThread(controller, dpSibling) }, rollouts: rollouts() });
  observe("daemon-picker-after");
  await exitTerminal(tp);
  // With its last terminal gone, the daemon unloads the lead about 60 s
  // later with `SessionEnd`, and keeps running.
  const dpExit = Date.now();
  const dpUnloaded = await quietly(waitFor(() => hookSince(dpExit, (record) => record.event === "SessionEnd" && record.payload.session_id === dpLead), "the picker lead unloads", 120000));
  await settlersDone();
  await delay(12000);
  trace("daemon-picker.unload", { lead: dpLead, child: dpChild, unloaded: dpUnloaded, daemons: daemons().map((entry) => entry.pid) });
  observe("daemon-picker-unloaded");

  // The lead model's `interrupt_agent` on a working child, as in #420: a
  // controller drives a lead on the daemon.
  scenario = "interrupt-agent";
  trace("scenario", { name: scenario });
  const started = await controller.call("thread/start", { cwd: fixture, model: "fixture-v2" });
  const iaLead = started.result?.thread?.id;
  assert(iaLead, `interrupt_agent lead started: ${JSON.stringify(started.error)}`);
  const iaStart = Date.now();
  const iaTurn = await controller.call("turn/start", { threadId: iaLead, input: [{ type: "text", text: "SPIKE:ia" }] });
  trace("turn.start", { lead: iaLead, turn: iaTurn.result?.turn?.id ?? null, error: iaTurn.error ?? null });
  await waitFor(() => requestsOf(iaLead, iaStart).some((record) => record.action === "interrupt_agent"), "the lead calls interrupt_agent", 90000);
  const iaAt = Date.now();
  const iaChild = threadOf("iae.0");
  trace("interrupt", { how: "interrupt_agent", lead: iaLead, child: iaChild });
  const iaWindow = await observeWindow({ interruptedAt: iaAt, child: iaChild });
  await quietly(waitFor(() => leadStopped(iaLead, iaStart), "the interrupt_agent lead's turn stops", 30000));
  trace("interrupt-agent.outcome", { lead: iaLead, child: iaChild, ...iaWindow,
    after: { lead: await readThread(controller, iaLead), child: await readThread(controller, iaChild) }, rollouts: rollouts() });
  observe("interrupt-agent-after");

  // The daemon stops, so the standalone terminals run with none.
  scenario = "daemon-stop";
  trace("scenario", { name: scenario });
  controller.close();
  controller = null;
  const daemonPids = daemons().map((entry) => entry.pid);
  const stopped = spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  trace("daemon.stop", { status: stopped.status, signal: stopped.signal });
  await quietly(waitFor(() => daemonPids.every((pid) => !existsSync(`/proc/${pid}`)), "the daemon exits", 30000));
  await settlersDone();
  processes("after-daemon-stop");
  observe("after-daemon-stop");

  // Esc in a standalone terminal, on the lead's own thread, while its turn
  // waits on a working child.
  scenario = "standalone-esc";
  trace("scenario", { name: scenario });
  assert.equal(daemons().length, 0, "no daemon runs");
  const seStart = Date.now();
  const ts = terminal("standalone-esc", ["--no-daemon", "-C", fixture, "SPIKE:se"]);
  await waitFor(() => command("sex.0"), "the standalone child's command", 90000);
  const seLead = threadOf("se.0");
  const seChild = threadOf("sex.0");
  await waitForLeadWaiting(seLead, seStart);
  processes("standalone-esc-running");
  observe("standalone-esc-before");
  await delay(1500);
  const seScreen = onScreen(ts.screen("before-esc"));
  ts.keys("Escape");
  const seEsc = Date.now();
  trace("interrupt", { how: "esc", terminal: ts.name, lead: seLead, child: seChild, ...seScreen });
  await quietly(waitFor(() => hookSince(seEsc, (record) => record.event === "Interrupt" && record.payload.session_id === seLead), "Esc publishes the lead's Interrupt", 10000));
  await afterEsc(ts);
  const seWindow = await observeWindow({ interruptedAt: seEsc, child: seChild, siblings: [seChild], quietMs: 5000 });
  trace("standalone-esc.outcome", { lead: seLead, child: seChild, ...seWindow, rollouts: rollouts() });
  observe("standalone-esc-after");
  await exitTerminal(ts);
  await settlersDone();

  // The agent picker in a standalone terminal.
  scenario = "standalone-picker";
  trace("scenario", { name: scenario });
  assert.equal(daemons().length, 0, "no daemon runs");
  const spStart = Date.now();
  const tq = terminal("standalone-picker", ["--no-daemon", "-C", fixture, "SPIKE:sp"]);
  await waitFor(() => command("spq.0") && command("spr.0"), "both standalone children's commands", 90000);
  const spLead = threadOf("sp.0");
  const spChild = threadOf("spq.0");
  const spSibling = threadOf("spr.0");
  await waitForLeadWaiting(spLead, spStart);
  observe("standalone-picker-before");
  await selectInPicker(tq, spChild);
  const spScreen = onScreen(tq.screen("before-esc"));
  tq.keys("Escape");
  const spEsc = Date.now();
  trace("interrupt", { how: "picker-esc", terminal: tq.name, lead: spLead, child: spChild, sibling: spSibling, ...spScreen });
  await delay(1500);
  await afterEsc(tq);
  const spWindow = await observeWindow({ interruptedAt: spEsc, child: spChild, siblings: [spSibling] });
  await quietly(waitFor(() => leadStopped(spLead, spStart), "the standalone picker lead's turn stops", 30000));
  await delay(1500);
  trace("standalone-picker.outcome", { lead: spLead, child: spChild, sibling: spSibling, ...spWindow, rollouts: rollouts() });
  observe("standalone-picker-after");
  // The terminal's exit ends its process, which hosted the stranded child.
  await exitTerminal(tq);
  await settlersDone();
  await delay(2000);
  processes("after-standalone-exit");
  observe("after-standalone-exit");

  scenario = "end";
  // Dashpot's Event Log for the fixture, metadata only.
  const events = dashpot(["events", "--json"]);
  const fields = ["time", "event.name", "dashpot.agent_session.id", "dashpot.issue.id", "dashpot.hook.event", "dashpot.outcome.result",
    "dashpot.agent_session.state", "dashpot.work_store.change"];
  trace("dashpot.events", { status: events.status, stderr: events.stderr.slice(0, 300),
    events: (parseJson(events.stdout)?.events ?? []).filter((event) => !/^process\./.test(event["event.name"] ?? ""))
      .map((event) => Object.fromEntries(fields.filter((field) => event[field] !== undefined && event[field] !== null).map((field) => [field, event[field]]))) });
  trace("outcome", { completed: true });
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: String(error?.stack ?? error).slice(0, 2000) });
  process.exitCode = 1;
} finally {
  scenario = "cleanup";
  try { controller?.close(); } catch {}
  for (const handle of terminals) if (handle.alive()) try { handle.screen("final"); } catch {}
  try { tmux("kill-server"); } catch {}
  if (daemons().length > 0) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, timeout: 60000 });
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const sharedAfter = sharedEntries();
  const fixtureName = sharedSocketName();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length,
    fixtureNameKnown: Boolean(fixtureName), fixtureEntries: fixtureName ? sharedAfter.filter((name) => name.startsWith(fixtureName)).length : null });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
