// Live-SessionStart run for Issue #448: drives a pinned Codex CLI against a
// loopback Responses API fixture with an isolated CODEX_HOME, whose daemon
// updater is off, and Dashpot's own Codex hook publisher, in a disposable
// Dashpot Project. In every scenario a lead has first spawned a multi-agent
// v2 worker that runs a long command, so the worker is demonstrably at work
// across the action. The actions are the ones that could make Codex publish
// a `SessionStart` for a session that is still live: manual compaction (the
// app-server's `thread/compact/start` and the terminal's `/compact`),
// automatic compaction mid-turn, the terminal's `/clear` and `/new`, and a
// second client resuming a thread the daemon still has loaded. It records
// every hook with its Host Process and Dashpot's stored hook record after it,
// as a metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
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
const expectedVersion = process.argv[3] ?? "0.160.0";
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-448-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's temporary root
// never enter the trace; a hook's or shell's ancestry keeps the processes up
// to the runner's own child.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, JSON.stringify(kept).replaceAll(root, "$ROOT").replaceAll(home, "~").replace(hostName, "<host>") + "\n");
  return record;
};

// The pinned release runs through a fixture-local `codex` on PATH.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
// The hook events `dashpot integrate codex` subscribes, each routed through
// the metadata wrapper to Dashpot's real publisher; the wrapper also records
// the compaction events, which Dashpot does not subscribe.
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const recordedOnly = ["PreCompact", "PostCompact"];
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
  SPIKE_SUBSCRIBED: hookEvents.join(","),
  SPIKE_SESSIONS_DIR: path.join(fixture, ".dashpot", "state", "sessions"),
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: one Local Issue Markdown Issue.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
const metadata = { id: "I_fixture_1", number: 1, reference: "fixture-1", state: "open", stateReason: null, labels: [], assignees: [], author: null,
  relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
  createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
writeFileSync(path.join(fixture, "issues", "1.md"), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue 1\n\nDisposable.\n`);
const dashpot = (args, cwd = fixture) => {
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");

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

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` selects the plan `plans[label]`,
// and each request of that thread under that label takes the plan's next
// step, so a plan carries on across a compaction that drops its earlier tool
// outputs. Each step becomes one tool call; when the plan runs out, the
// model answers `DONE:<label>`. A request whose last item is a message that
// carries no directive is Codex's own compaction prompt, answered with a
// summary. A step may report a large token usage, which is how the fixture
// pushes a thread over its automatic compaction limit.
const commandScript = path.join(here, "command.mjs");
const exec = (hold) => ({ exec: { hold } });
const longWorker = (count) => Array.from({ length: count }, () => exec(20000));
const plans = {
  // Standalone terminal lead: `/compact`, then `/clear`, while worker S works.
  "s-spawn": [{ spawn: ["worker_s", "ws"] }], ws: longWorker(3), "s-next": [], "s-after": [],
  // Daemon lead C: `thread/compact/start` while worker C works.
  "c-spawn": [{ spawn: ["worker_c", "wc"] }], wc: longWorker(2), "c-next": [],
  // Daemon lead A: automatic compaction mid-turn, after its spawn's response
  // reports more tokens than the thread's limit.
  "ac-spawn": [{ spawn: ["worker_ac", "wac"], usage: 200000 }, exec(2000), exec(200)], wac: longWorker(2), "ac-next": [],
  // Daemon terminal lead N: `/new`, then the new thread's `/clear`.
  "n-spawn": [{ spawn: ["worker_n", "wn"] }], wn: longWorker(3), "n-after": [],
  "n2-spawn": [{ spawn: ["worker_n2", "wn2"] }], wn2: longWorker(3), "n3-after": [],
  // Daemon lead R: a second client resumes it while worker R works.
  "r-spawn": [{ spawn: ["worker_r", "wr"] }], wr: longWorker(3), "r-after": [], "r-tui": [],
};
const markerPattern = /(SPIKE|DONE|SUMMARY):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const textOf = (item) => [item.content ?? []].flat().map((part) => typeof part === "string" ? part : Object.values(part ?? {}).filter((value) => typeof value === "string" && value !== part.type).join(" ")).join(" | ");
const modelRequests = [];
const stepCounters = new Map();
const toolsSeen = new Map();
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/responses")) {
    trace("model.other", { path: url.pathname, method: req.method, thread: payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  // The request's client metadata names the thread itself; the `thread_id`
  // header names the root session for every thread in a tree.
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const session = payload.client_metadata?.session_id ?? req.headers["session_id"] ?? null;
  const input = payload.input ?? [];
  let label = null;
  input.forEach((item) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) label = found.at(-1)[2];
  });
  const last = input.at(-1) ?? {};
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  // A compaction request offers no tools and ends with Codex's compaction
  // prompt, a message carrying no directive. The prompt is Codex's own text,
  // not the person's; only whether it names a summary or compaction is kept.
  const compaction = tools.length === 0 && last.type === "message" && !textOf(last).includes("SPIKE:");
  const compactionPrompt = compaction ? /summar|compact|checkpoint/i.test(textOf(last)) : null;
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const v2 = Boolean(offered("list_agents"));
  const counterKey = `${thread}:${label}`;
  const stepIndex = compaction ? null : stepCounters.get(counterKey) ?? 0;
  if (!compaction) stepCounters.set(counterKey, stepIndex + 1);
  // The terminal also sends each prompt to a side thread of its own, offered
  // fewer tools and no shell, and publishing no hooks; it gets text only, so
  // it spawns nothing.
  const sideThread = !offered("exec_command");
  const plan = label && !sideThread ? plans[label] ?? [] : [];
  const step = compaction ? null : plan[stepIndex] ?? null;
  const call = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${label}_${stepIndex}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.exec) {
    action = "exec_command";
    item = call("exec_command", { cmd: `node ${commandScript} ${label}.${stepIndex} ${step.exec.hold}`, login: false, yield_time_ms: 120000 });
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = call("spawn_agent", { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" });
  }
  const usage = step?.usage ?? 14;
  const latestOutput = input.findLast((entry) => /_call_output$/.test(entry.type ?? ""));
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort().join(",");
  const toolsChanged = toolsSeen.get(thread) !== toolNames;
  toolsSeen.set(thread, toolNames);
  const request = trace("model.request", { thread, session, label, step: stepIndex, compaction, compactionPrompt, sideThread, inputItems: input.length, action, missing: Boolean(step && !item), v2,
    tools: toolsChanged ? toolNames.split(",") : undefined,
    reportedTokens: usage, toolCount: tools.length, lastOutput: latestOutput ? String(latestOutput.output ?? "").replaceAll(root, "$ROOT").slice(0, 200) : null,
    tail: input.slice(-3).map((entry) => [entry.type ?? null, entry.role ?? null]), parentThread: req.headers["x-codex-parent-thread-id"] ?? null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  const text = compaction ? `SUMMARY:${label ?? "none"} fixture summary.` : label ? `DONE:${label}` : "Fixture complete.";
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: usage - 4, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: usage } } });
  res.end();
});

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries([...hookEvents, ...recordedOnly].map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])),
}, null, 2));

// The fixture catalog names `fixture-v2`, a copy of a bundled entry without
// a tool set or code mode, declaring multi-agent v2, as in the #420 run.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"
check_for_update_on_startup = false

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

[projects."${fixture}"]
trust_level = "trusted"
`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => {
  try { return JSON.parse(readFileSync(daemonSettingsPath, "utf8")); } catch (error) { return { unreadable: String(error) }; }
};
// The shared per-user daemon directory, which the operator's own Codex
// sessions use too: the run only lists its entries, by name, and never
// removes any.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

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
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.replaceAll(root, "<root>").slice(0, 240)];
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemons = () => codexProcesses().filter(isDaemon);
const isSettler = (entry) => / -m dashpot\.hook settle /.test(entry.cmdline);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const processes = (label) => trace("processes", { label, processes: codexProcesses().map(brief), daemons: daemons().map((entry) => entry.pid), socketExists: existsSync(socketPath),
  daemonSettings: daemonSettings() });
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const hostOf = (record) => record?.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const settlersDone = async (label) => {
  await delay(500);
  await quietly(waitFor(() => !codexProcesses().some(isSettler), `${label}: settlers exit`, 15000));
};
const threadSummary = (thread) => thread && ({ id: thread.id, forkedFromId: thread.forkedFromId ?? null, parentThreadId: thread.parentThreadId ?? null, cwd: thread.cwd ?? null,
  status: thread.status, ephemeral: thread.ephemeral, model: thread.model ?? null });
// Hooks in a window, as [receipt, event, session, agent, source/trigger, host, stored state, stored live sub-agents].
const timeline = (since) => hooks().filter((record) => record.receipt > since).map((record) => [record.receipt, record.event, record.payload.session_id, record.payload.agent_id ?? null,
  record.payload.source ?? record.payload.trigger ?? null, hostOf(record), record.stored?.state ?? null, record.stored?.liveSubagents ?? null]);
const hookSince = (since, predicate) => hooks().find((record) => record.receipt > since && predicate(record));
const stopped = (agent) => hooks().some((record) => record.event === "SubagentStop" && record.payload.agent_id === agent);
const mark = () => records.length;
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;
const sessionOf = (label) => command(label)?.env.CODEX_SESSION_ID ?? null;

// Dashpot's stored hook record for a session, read from the fixture's
// project store, and Dashpot's published view.
// Dashpot keys a Codex record by its native session id, or by the scoped key
// when another harness claims that id.
const storedPath = (sessionId) => [sessionId, `codex-session-${createHash("sha256").update(sessionId).digest("hex")}`]
  .map((key) => path.join(env.SPIKE_SESSIONS_DIR, `${key}.json`)).find((file) => existsSync(file)) ?? path.join(env.SPIKE_SESSIONS_DIR, `${sessionId}.json`);
const stored = (label, sessionIds) => trace("stored", { label, records: Object.fromEntries(sessionIds.filter(Boolean).map((sessionId) => {
  const record = parseJson(existsSync(storedPath(sessionId)) ? readFileSync(storedPath(sessionId), "utf8") : "null");
  return [sessionId, record && { event: record.event ?? null, source: record.source ?? null, state: record.state ?? null, liveSubagents: record.liveSubagents ?? null,
    lastSessionStartAt: record.lastSessionStartAt ?? null, sessionProcess: record.sessionProcess ? { pid: record.sessionProcess.pid, startedAt: record.sessionProcess.startedAt } : null }];
})) });
const view = (label) => {
  const ran = dashpot(["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400), agentRuns: parsed?.agentRuns ?? null,
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })) });
};

// One-shot Codex commands, launched by name through the fixture PATH.
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const child = spawn("codex", args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const clean = (text) => stripAnsi(text).replaceAll(root, "<root>");
  const statusLines = (text) => clean(text).split("\n").filter((line) => /^(OpenAI Codex v|warning: |hook: |Installing |Error: )/.test(line)).join("\n");
  trace("codex.command", { label, args: args.map((arg) => arg.replaceAll(root, "<root>")), status, signal, stdout: clean(stdout).slice(-600), stderr: statusLines(stderr).slice(-1200) });
  return { status, signal, stdout, stderr };
};

// An interactive terminal hosted by `script`. Its screen goes to a log in the
// fixture root for diagnosis, never into the trace.
const terminals = [];
const terminal = async (name, args) => {
  const child = spawn("script", ["-qfec", ["codex", ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd: fixture, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  // The composer treats a burst of keys as a paste, so Enter follows the text
  // after a pause.
  const handle = { name, child, exited: null,
    type: async (text) => { trace("terminal.type", { name, text }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text) => child.stdin.write(text) };
  child.stdout.on("data", (chunk) => { appendFileSync(logPath, stripAnsi(String(chunk))); });
  child.stderr.on("data", (chunk) => { appendFileSync(logPath, stripAnsi(String(chunk))); });
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, args: args.map((arg) => arg.replaceAll(root, "<root>")), scriptPid: child.pid });
  return handle;
};
// Type a prompt into a terminal and wait for that turn's Stop, of whichever
// session the terminal now shows.
const terminalTurn = async (handle, label, timeout = 60000) => {
  const since = mark();
  await handle.type(`SPIKE:${label}`);
  await waitFor(() => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id) || handle.exited, `${label} Stop`, timeout);
  assert(!handle.exited, `${handle.name} exited early`);
  return hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id).payload.session_id;
};
// `/compact` in a terminal: Enter again if the first did not start it.
const terminalCompact = async (handle) => {
  const since = mark();
  await handle.type("/compact");
  if (!(await quietly(waitFor(() => hookSince(since, (record) => record.event === "PostCompact"), "terminal compaction", 8000)))) {
    trace("terminal.retry", { name: handle.name, key: "Enter" });
    handle.key("\r");
    await quietly(waitFor(() => hookSince(since, (record) => record.event === "PostCompact"), "terminal compaction retry", 15000));
  }
  await delay(2000);
};
const exitTerminal = async (handle) => {
  if (handle.exited) return;
  await handle.type("/exit");
  if (!(await quietly(waitFor(() => handle.exited, `${handle.name} exit`, 10000)))) {
    handle.key("\u0003"); await delay(500); handle.key("\u0003");
    await quietly(waitFor(() => handle.exited, `${handle.name} interrupt exit`, 10000));
  }
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
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method?.startsWith("thread/") || parsed.method?.startsWith("turn/") || parsed.method === "item/completed" || parsed.method === "item/started") {
      const { threadId, turn, status, thread, item } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id ?? parsed.params?.turnId, status: status ?? turn?.status, itemType: item?.type ?? null, receivedAt: Date.now() });
    }
  };
  socket.on(onMessage);
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-448-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
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
const completedTurn = (client, turnId) => client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
const runTurn = async (client, threadId, text, options = {}) => {
  const since = mark();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, status: started.result?.turn?.status ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  await waitFor(() => completedTurn(client, turnId), `turn ${text} completed`, options.timeout ?? 60000);
  await quietly(waitFor(() => hookSince(since, (record) => record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000));
  trace("turn.completed", { client: client.name, threadId, turnId, status: completedTurn(client, turnId).status });
  return { turnId, since };
};
const startThread = async (client, name, params = {}) => {
  const started = await client.call("thread/start", { cwd: fixture, model: "fixture-v2", ...params });
  const thread = started.result?.thread;
  trace("thread.start", { name, params, thread: threadSummary(thread), error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
// Wait for a lead's worker to start its long command, by its label.
const workerOf = async (label, timeout = 60000) => {
  await waitFor(() => command(`${label}.0`), `${label}'s first command`, timeout);
  return { worker: threadOf(`${label}.0`), session: sessionOf(`${label}.0`) };
};
// Whether a worker was still at work at a point: its last command had not
// ended and it had not stopped.
const working = (label, worker) => ({ worker, stopped: stopped(worker), commandsStarted: commands().filter((record) => record.phase === "start" && record.label.startsWith(`${label}.`)).length,
  commandsEnded: commands().filter((record) => record.phase === "end" && record.label.startsWith(`${label}.`)).length, at: Date.now() });

// The runner's own scripts; the verifier is versioned with the trace in Git.
const scripts = ["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["hook_records.py", "hook_publish.py", "harnesses.py", "processes.py"].map((file) => `src/dashpot/sessions/${file}`);
const digests = () => Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
  .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")]));
let controllers = [];
let daemonPid = null;
const daemonLeads = [];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim();
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(os.homedir(), "~"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, dirtySource: dirty.split("\n").filter(Boolean) }, hookEvents, recordedOnly, socketPath,
    fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2" }, sharedDaemonDirBefore: sharedBefore, sourceSHA256: digests() });

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
  assert.equal(entries.length, hookEvents.length + recordedOnly.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await trust.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  trust.close();
  trustServer.kill("SIGTERM");
  await once(trustServer, "exit");
  await delay(500);

  // Scenario: a standalone terminal (no daemon) hosts lead S in its own
  // process. S spawns worker S, then the person runs `/compact`, a prompt,
  // `/clear`, and another prompt while S works.
  trace("scenario", { name: "standalone" });
  {
    const since = mark();
    const tui = await terminal("standalone", ["--disable", "daemon_auto_start", "-m", "fixture-v2", "-C", fixture, "SPIKE:s-spawn"]);
    const { worker, session } = await workerOf("ws", 90000);
    await quietly(waitFor(() => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id), "s-spawn Stop", 15000));
    await delay(1000);
    stored("standalone-before", [session]);
    const compactAt = mark();
    await terminalCompact(tui);
    stored("standalone-after-compact", [session]);
    const compactWorking = working("ws", worker);
    const nextSession = await terminalTurn(tui, "s-next");
    stored("standalone-after-next", [session, nextSession]);
    const clearAt = mark();
    await tui.type("/clear");
    await delay(3000);
    const clearedSession = await terminalTurn(tui, "s-after");
    const clearWorking = working("ws", worker);
    stored("standalone-after-clear", [session, clearedSession]);
    view("standalone-after-clear");
    await quietly(waitFor(() => stopped(worker), "worker S stops", 90000));
    await delay(1500);
    stored("standalone-worker-stopped", [session, clearedSession]);
    await exitTerminal(tui);
    await quietly(waitFor(() => hookSince(clearAt, (record) => record.event === "SessionEnd" && record.payload.session_id === clearedSession), "standalone SessionEnd", 15000));
    await delay(1500);
    stored("standalone-exited", [session, clearedSession]);
    trace("standalone.outcome", { lead: session, worker, compactAt, clearAt, nextSession, clearedSession, compactWorking, clearWorking, hooks: timeline(since) });
  }

  // The managed daemon hosts every remaining lead; controllers drive it as a
  // client would.
  trace("scenario", { name: "daemon" });
  await codex(["app-server", "daemon", "start"], "daemon-start", { timeout: 60000 });
  await waitFor(() => existsSync(socketPath) && daemons().length === 1, "daemon control socket", 30000);
  processes("daemon-started");
  daemonPid = daemons()[0].pid;
  const c1 = await daemonClient("controller-1");
  controllers.push(c1);

  // Scenario: `thread/compact/start` on lead C while worker C works, then a
  // prompt on C.
  trace("scenario", { name: "compact" });
  {
    const since = mark();
    const lead = await startThread(c1, "lead-c");
    daemonLeads.push(lead);
    await runTurn(c1, lead, "SPIKE:c-spawn");
    const { worker } = await workerOf("wc");
    stored("compact-before", [lead]);
    view("compact-before");
    const compactAt = mark();
    const compacted = await c1.call("thread/compact/start", { threadId: lead });
    trace("compact.response", { lead, response: compacted.error ?? compacted.result ?? null });
    await quietly(waitFor(() => hookSince(compactAt, (record) => record.event === "PostCompact" && record.payload.session_id === lead), "PostCompact", 20000));
    await delay(2000);
    const compactWorking = working("wc", worker);
    stored("compact-after", [lead]);
    view("compact-after");
    const nextAt = mark();
    await runTurn(c1, lead, "SPIKE:c-next");
    await delay(1000);
    const nextWorking = working("wc", worker);
    stored("compact-after-next", [lead]);
    await quietly(waitFor(() => stopped(worker), "worker C stops", 60000));
    await delay(1500);
    stored("compact-worker-stopped", [lead]);
    view("compact-worker-stopped");
    trace("compact.outcome", { lead, worker, daemonPid, compactAt, nextAt, compactWorking, nextWorking,
      notifications: c1.notifications.filter((entry) => entry.threadId === lead && entry.receivedAt >= records[compactAt - 1].receiptTime).map((entry) => [entry.method, entry.turnId ?? null, entry.status ?? null, entry.itemType]),
      hooks: timeline(since) });
  }

  // Scenario: lead A's thread has an automatic compaction limit of 5 000
  // tokens; the response carrying its spawn reports 200 000, so Codex
  // compacts mid-turn while worker A works.
  trace("scenario", { name: "auto-compact" });
  {
    const since = mark();
    const lead = await startThread(c1, "lead-ac", { config: { model_auto_compact_token_limit: 5000 } });
    daemonLeads.push(lead);
    await runTurn(c1, lead, "SPIKE:ac-spawn", { timeout: 90000 });
    const { worker } = await workerOf("wac");
    await delay(1000);
    const turnWorking = working("wac", worker);
    stored("auto-compact-after-turn", [lead]);
    const nextAt = mark();
    await runTurn(c1, lead, "SPIKE:ac-next");
    await delay(1000);
    const nextWorking = working("wac", worker);
    stored("auto-compact-after-next", [lead]);
    await quietly(waitFor(() => stopped(worker), "worker A stops", 60000));
    await delay(1500);
    stored("auto-compact-worker-stopped", [lead]);
    trace("auto-compact.outcome", { lead, worker, nextAt, turnWorking, nextWorking,
      requests: modelRequests.filter((record) => record.thread === lead).map((record) => [record.receipt, record.label, record.step, record.compaction, record.compactionPrompt, record.action, record.reportedTokens]),
      hooks: timeline(since) });
  }

  // Scenario: a terminal attached to the daemon hosts lead N, which spawns
  // worker N; the person runs `/new` and a prompt; the new thread spawns
  // worker N2; the person runs `/clear` and a prompt.
  trace("scenario", { name: "daemon-terminal" });
  let terminalSessions = [];
  {
    const since = mark();
    const tui = await terminal("daemon", ["--remote", `unix://${socketPath}`, "-m", "fixture-v2", "-C", fixture, "SPIKE:n-spawn"]);
    const { worker, session } = await workerOf("wn", 90000);
    await quietly(waitFor(() => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id), "n-spawn Stop", 15000));
    await delay(1000);
    stored("daemon-terminal-before", [session]);
    const newAt = mark();
    await tui.type("/new");
    await delay(3000);
    const newSession = await terminalTurn(tui, "n-after");
    const newWorking = working("wn", worker);
    stored("daemon-terminal-after-new", [session, newSession]);
    const spawnAt = mark();
    await tui.type("SPIKE:n2-spawn");
    const second = await workerOf("wn2");
    await quietly(waitFor(() => hookSince(spawnAt, (record) => record.event === "Stop" && !record.payload.agent_id), "n2-spawn Stop", 15000));
    await delay(1000);
    const clearAt = mark();
    await tui.type("/clear");
    await delay(3000);
    const clearedSession = await terminalTurn(tui, "n3-after");
    const clearWorking = working("wn2", second.worker);
    stored("daemon-terminal-after-clear", [session, newSession, clearedSession]);
    view("daemon-terminal-after-clear");
    trace("daemon-terminal.loaded", { loaded: (await c1.call("thread/loaded/list", {})).result?.data ?? null });
    await quietly(waitFor(() => stopped(worker) && stopped(second.worker), "workers N and N2 stop", 90000));
    await delay(1500);
    stored("daemon-terminal-workers-stopped", [session, newSession, clearedSession]);
    await exitTerminal(tui);
    terminalSessions = [session, newSession, clearedSession];
    trace("daemon-terminal.outcome", { lead: session, worker, newAt, newSession, newWorking, secondWorker: second.worker, secondSession: second.session, clearAt, clearedSession, clearWorking,
      hooks: timeline(since) });
  }

  // Scenario: a second client resumes lead R, which the daemon still has
  // loaded and controller 1 still subscribes, while worker R works; the
  // second client then runs a prompt, and a terminal resumes R too.
  trace("scenario", { name: "second-client-resume" });
  {
    const since = mark();
    const lead = await startThread(c1, "lead-r");
    daemonLeads.push(lead);
    await runTurn(c1, lead, "SPIKE:r-spawn");
    const { worker } = await workerOf("wr");
    stored("resume-before", [lead]);
    const c2 = await daemonClient("controller-2");
    controllers.push(c2);
    const resumeAt = mark();
    const resumed = await c2.call("thread/resume", { threadId: lead });
    trace("resume.response", { lead, thread: threadSummary(resumed.result?.thread), error: resumed.error ?? null });
    await delay(3000);
    const resumeWorking = working("wr", worker);
    stored("resume-after-resume", [lead]);
    const turnAt = mark();
    await runTurn(c2, lead, "SPIKE:r-after");
    await delay(1000);
    stored("resume-after-turn", [lead]);
    const tuiAt = mark();
    const tui = await terminal("resume", ["resume", "--remote", `unix://${socketPath}`, "-C", fixture, lead, "SPIKE:r-tui"]);
    await quietly(waitFor(() => hookSince(tuiAt, (record) => record.event === "Stop" && !record.payload.agent_id) || tui.exited, "r-tui Stop", 60000));
    await delay(1000);
    const tuiWorking = working("wr", worker);
    stored("resume-after-terminal", [lead]);
    view("resume-after-terminal");
    await quietly(waitFor(() => stopped(worker), "worker R stops", 90000));
    await delay(1500);
    stored("resume-worker-stopped", [lead]);
    await exitTerminal(tui);
    trace("second-client-resume.outcome", { lead, worker, daemonPid, resumeAt, turnAt, tuiAt, resumeWorking, tuiWorking, hooks: timeline(since) });
  }

  // Every client leaves; the daemon unloads each lead about 60 s later.
  trace("scenario", { name: "unload" });
  {
    const since = mark();
    for (const client of controllers) client.close();
    controllers = [];
    const leads = [...daemonLeads, ...terminalSessions].filter(Boolean);
    await quietly(waitFor(() => leads.every((lead) => hooks().some((record) => record.event === "SessionEnd" && record.payload.session_id === lead)), "leads unload", 100000));
    await delay(2000);
    await settlersDone("unload");
    trace("unload.outcome", { leads, hooks: timeline(since) });
  }

  trace("scenario", { name: "daemon-stop" });
  await codex(["app-server", "daemon", "stop"], "daemon-stop", { timeout: 60000 });
  await quietly(waitFor(() => !existsSync(`/proc/${daemonPid}`), "daemon gone", 20000));
  await settlersDone("daemon stop");
  processes("after-daemon-stop");
  trace("sources.after", { sourceSHA256: digests() });
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: String(error?.stack ?? error).slice(0, 2000) });
  throw error;
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
  if (daemons().length > 0) await codex(["app-server", "daemon", "stop"], "cleanup-stop").catch(() => {});
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)), removed: sharedBefore.filter((name) => !sharedAfter.includes(name)) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
