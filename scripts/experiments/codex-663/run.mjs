// Unload and resume run for Issue #663: what a pinned Codex CLI's managed
// app-server daemon does with a thread after its last client leaves, and
// what a sequential resume of that thread then meets. Drives the pinned
// release against a loopback Responses API fixture with an isolated HOME,
// XDG directories and CODEX_HOME, whose daemon updater is off, under the
// `workspace-write` sandbox, with Dashpot's real Codex hook publisher, in a
// disposable Dashpot Project with two linked Issue Worktrees. It records:
//
// - `ordinary`: a plain daemon-hosted terminal in Issue Worktree A binds an
//   Agent Run with `work start`, exits, and the execute-issues skill's resume
//   command, without its cache options, resumes the same thread at A at once;
// - `relocate`: the same, but the session declares `work relocate` to Issue
//   Worktree B before exiting, and the resume names B;
// - `slow-release`: after the client exits, the runner holds the writer
//   coordination lock, as Codex's own regression test does, so the daemon's
//   unload cleanup outlasts its ten-second warning, then releases it;
// - `slow-timeout`: the same hold kept past Codex's thirty-second wait for
//   that lock;
// - `mcp-disconnect`: a controller starts a thread whose required MCP server
//   blocks in `initialize`, disconnects during that startup, and the runner
//   then lets the server start.
//
// For each it records the daemon's `thread/loaded/list`, its `thread/closed`
// notifications, its own log of the unload and of slow shutdown, the state
// of the thread's writer lock, every resume's outcome, each turn's directory,
// writable roots and network setting, every hook and what Dashpot reports.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset; SPIKE_FIXTURE_PARENT
// names the directory the fixture is created in (default /var/tmp).
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
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

// Outside the system temporary directory, which `workspace-write` makes
// writable, so the fixture is sandboxed as a checkout in a home directory is.
const root = mkdtempSync(path.join(process.env.SPIKE_FIXTURE_PARENT ?? "/var/tmp", "dashpot-codex-663-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const worktreeRoot = path.join(root, "repository.worktrees");
const issueA = path.join(worktreeRoot, "issue-a");
const issueB = path.join(worktreeRoot, "issue-b");
const gitDir = path.join(fixture, ".git");
const outside = path.join(root, "outside");
const worktrees = { main: fixture, "issue-a": issueA, "issue-b": issueB };
const gates = path.join(root, "gates");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's root never
// enter the trace.
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
for (const dir of [fixture, gates, outside, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: the main Worktree and two linked Issue
// Worktrees, with two Markdown Issues.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2]) {
  const metadata = { id: `I_fixture_${number}`, number, reference: `fixture-${number}`, state: "open", stateReason: null, labels: [], assignees: [], author: null,
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${number}.md`), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue ${number}\n\nDisposable.\n`);
}
const run = (command, args, { cwd = fixture, timeout = 60000 } = {}) => new Promise((resolve) => {
  const child = spawn(command, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  child.on("exit", (status, signal) => { clearTimeout(timer); resolve({ status, signal, stdout, stderr }); });
});
const dashpotSync = (args, cwd = fixture) => {
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpotSync(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.dashpot/state/\n");
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "issue-a", issueA);
git("worktree", "add", "-b", "issue-b", issueB);
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
  return { server, url: `http://127.0.0.1:${server.address().port}`, port: server.address().port };
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
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };

// The fixture model. The latest input item that is not a tool call and
// carries `SPIKE:<label>` selects the plan `plans[label]`; the number of tool
// outputs after it selects the step. Each step runs command.mjs, with the
// `dashpot work` command the step names. When the plan runs out, the model
// answers `DONE:<label>`. Each request records its thread, its label and step,
// and the probe report it received.
const commandScript = path.join(here, "command.mjs");
const plans = {};
const plan = (label, steps) => { plans[label] = steps; };
const markerPattern = /SPIKE:([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const probeOf = (output) => {
  const line = String(output ?? "").split("\n").find((entry) => entry.startsWith("PROBE "));
  return line ? parseJson(line.slice("PROBE ".length)) : null;
};
const writeTargets = (name) => [...Object.values(worktrees).map((worktree) => path.join(worktree, ".dashpot", "state", `probe-${name}`)), path.join(outside, `probe-${name}`)];
const modelRequests = [];
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
let modelPort = null;
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
    const found = [...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[1]);
    if (found.length) { directiveAt = index; label = found.at(-1); }
  });
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? (tool.tools ?? []).map((nested) => [tool.name, nested.name ?? nested.type]) : [[null, tool.name ?? tool.type]]);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const steps = label ? plans[label] ?? [] : [];
  const step = steps[outputs.length] ?? null;
  let item = null;
  if (step) {
    const tool = offered("exec_command");
    const name = `${label}.${outputs.length}`;
    item = tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name: "exec_command",
      arguments: JSON.stringify({ cmd: `node ${commandScript} ${name} ${dashpotCommand} ${step.work ?? "-"} ${modelPort} ${writeTargets(name).join(" ")}`, login: false, yield_time_ms: 120000 }) };
  }
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const request = trace("model.request", { thread, label, step: outputs.length, action: item ? "exec_command" : null, missing: Boolean(step && !item),
    probe: latestOutput ? probeOf(latestOutput.output) : null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});
modelPort = model.port;

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

// Codex's default for a trusted project, `workspace-write` with the network
// off, no approval ever asked (`never`), every checkout trusted.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_provider = "fixture"
check_for_update_on_startup = false

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
// The entry this fixture's daemon binds there; other users' daemons, the
// operator's or a concurrent experiment's, add and remove entries of their own.
let ownSharedEntry = null;

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
// The daemon runs from its own copy of the release under CODEX_HOME, whose
// long path pushes its flags past the ancestry record's short command line.
const fullCommand = (pid) => { try { return readFileSync(`/proc/${pid}/cmdline`, "utf8").split("\0").join(" "); } catch { return ""; } };
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(fullCommand(entry.pid)) && / --managed-daemon/.test(fullCommand(entry.pid));
const daemonPids = new Set();
const daemonPid = () => { const pid = codexProcesses().find(isDaemon)?.pid ?? null; if (pid) daemonPids.add(pid); return pid; };
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
const sessionEnd = (since, session) => hookSince(since, (record) => record.event === "SessionEnd" && record.payload.session_id === session);
const hookTimeline = (session) => hooks().filter((record) => record.payload.session_id === session)
  .map((record) => ({ receipt: record.receipt, at: record.receiptTime, event: record.event, source: record.payload.source ?? null, reason: record.payload.reason ?? null,
    cwd: retained(record.payload.cwd ?? ""), host: record.ancestry?.[0] ? { pid: record.ancestry[0].pid, comm: record.ancestry[0].comm, daemon: daemonPids.has(record.ancestry[0].pid) } : null,
    publisher: record.publisher.status, publisherOut: retained(record.publisher.stdout ?? "").slice(0, 300), publisherErr: retained(record.publisher.stderr ?? "").slice(0, 300) }));

// The writer lock of a thread, probed without taking the coordination lock
// and without creating the file: `absent`, `held` by a Codex process (the
// daemon or a terminal client), or `free`.
const lockDir = path.join(env.CODEX_HOME, "thread-writer-locks");
const lockHelper = path.join(here, "lock.py");
const lockState = (thread) => spawnSync("python3", ["-I", lockHelper, "probe", path.join(lockDir, `${thread}.lock`)], { encoding: "utf8", timeout: 10000 }).stdout.trim();
const lockCheck = (scenario, label, thread) => trace("lock", { scenario, label, thread, state: lockState(thread) });
// Holding the coordination lock from another process, as Codex's regression
// test for slow unloads does: a Codex process's writer cleanup waits for it.
const holdCoordination = async (scenario) => {
  const child = spawn("python3", ["-I", lockHelper, "hold", path.join(lockDir, ".coordination.lock")], { env, stdio: ["pipe", "pipe", "pipe"] });
  const holder = { child, acquiredAt: null, releasedAt: null, exited: false };
  let out = "";
  child.stdout.on("data", (chunk) => {
    out += chunk;
    holder.acquiredAt = Number(out.match(/acquired (\d+)/)?.[1] ?? 0) || null;
    holder.releasedAt = Number(out.match(/released (\d+)/)?.[1] ?? 0) || null;
  });
  child.on("exit", () => { holder.exited = true; });
  await settle(() => holder.acquiredAt, `${scenario} coordination held`, 30000);
  trace("coordination", { scenario, phase: "held", at: holder.acquiredAt, pid: child.pid });
  holder.release = async () => {
    child.stdin.end();
    await settle(() => holder.releasedAt && holder.exited, `${scenario} coordination released`, 10000);
    trace("coordination", { scenario, phase: "released", at: holder.releasedAt });
  };
  return holder;
};

// Codex's own log, which every Codex process of the fixture writes to one
// database in CODEX_HOME: the daemon's unload of an idle thread, its slow
// shutdown warning, writer-lock refusals and cleanup failures.
const logPatterns = ["has no subscribers and is idle", "taking longer than expected", "active writer", "writer coordination lock", "failed to coordinate thread writer lock cleanup",
  "replaced or removed before teardown", "failed to submit Shutdown", "is closing", "failed to remove thread writer lock"];
const codexLog = () => {
  const file = readdirSync(env.CODEX_HOME).filter((name) => /^logs_\d+\.sqlite$/.test(name)).sort().at(-1);
  if (!file) return { file: null, entries: [] };
  const db = new DatabaseSync(path.join(env.CODEX_HOME, file), { readOnly: true });
  const columns = db.prepare("pragma table_info(logs)").all().map((column) => column.name);
  const rows = db.prepare(`select * from logs where ${logPatterns.map(() => "feedback_log_body like ?").join(" or ")} order by id`).all(...logPatterns.map((pattern) => `%${pattern}%`));
  db.close();
  return { file, columns, entries: rows.map((row) => {
    const text = String(row.feedback_log_body ?? "");
    return { id: row.id, atMs: row.ts * 1000 + Math.floor((row.ts_nanos ?? 0) / 1e6), level: row.level, target: row.target, pid: Number(String(row.process_uuid ?? "").match(/^pid:(\d+)/)?.[1] ?? 0) || null,
      message: retained(text.slice(text.lastIndexOf("}: ") >= 0 ? text.lastIndexOf("}: ") + 3 : 0)).slice(0, 300) };
  }) };
};

// Codex's own record of each thread: per turn, the directory, sandbox and
// approval policy it ran with.
const rolloutFiles = (dir) => {
  let entries = [];
  try { entries = readdirSync(dir); } catch { return []; }
  return entries.flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? rolloutFiles(full) : entry.endsWith(".jsonl") ? [full] : [];
  });
};
const compactProfile = (profile) => profile && { type: profile.type, network: profile.network ?? null,
  entries: (profile.file_system?.entries ?? []).map((entry) => [entry.path?.path ?? entry.path?.value?.kind ?? null, entry.access]) };
const rolloutTurns = (thread) => {
  const file = rolloutFiles(path.join(env.CODEX_HOME, "sessions")).find((name) => name.endsWith(`${thread}.jsonl`));
  if (!file) return null;
  const lines = readFileSync(file, "utf8").trim().split("\n").map(parseJson).filter(Boolean);
  return lines.filter((line) => line.type === "turn_context").map((line) => ({ timestamp: line.timestamp ?? null, cwd: retained(line.payload?.cwd ?? ""),
    approvalPolicy: line.payload?.approval_policy ?? null, sandboxPolicy: parseJson(retained(JSON.stringify(line.payload?.sandbox_policy ?? null))),
    permissions: parseJson(retained(JSON.stringify(compactProfile(line.payload?.permission_profile) ?? null))) }));
};

// What Dashpot reports: its published view's Agent Runs and Diagnostics, and
// each Worktree's Event Log of hook outcomes and Work Store changes for the
// sessions named.
const view = async (scenario, label) => {
  const ran = await run(dashpotCommand, ["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  return trace("dashpot.view", { scenario, label, status: ran.status, stderr: retained(ran.stderr).slice(0, 400),
    agentRuns: parseJson(retained(JSON.stringify(parsed?.agentRuns ?? null))),
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: retained(String(diagnostic.message ?? "")).slice(0, 400) })) });
};
const eventLog = async (scenario, sessions) => {
  const events = new Map();
  for (const [name, dir] of Object.entries(worktrees)) {
    const ran = await run(dashpotCommand, ["events", "--json"], { cwd: dir });
    for (const line of ran.stdout.split("\n")) {
      const event = parseJson(line);
      if (!event || !sessions.includes(event["dashpot.agent_session.id"]) || event["event.name"] === "process.start") continue;
      const kept = Object.fromEntries(Object.entries(event).filter(([key, value]) => value !== null
        && (key === "time" || key === "event.name" || key === "error.type" || key === "process.exit.code" || key.startsWith("dashpot."))));
      const key = `${event.time}|${event["event.name"]}|${event["dashpot.process.kind"]}`;
      if (!events.has(key)) events.set(key, { stores: [], ...parseJson(retained(JSON.stringify(kept))) });
      events.get(key).stores.push(name);
    }
  }
  return trace("dashpot.events", { scenario, events: [...events.values()].sort((a, b) => a.time.localeCompare(b.time)) });
};

// An interactive terminal hosted by `script`, started in the fixture root,
// outside every checkout. Its screen goes to a log in the fixture root; the
// trace keeps only a labelled tail.
const terminals = [];
const terminal = (name, args, cwd = root) => {
  // The pseudo-terminal gets a size first, which the TUI needs to draw.
  const child = spawn("script", ["-qfec", `stty cols 160 rows 50; exec ${["codex", ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" ")}`, "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "160", LINES: "50" }, stdio: ["pipe", "pipe", "pipe"] });
  const logPath = path.join(root, `terminal-${name}.log`);
  let screen = "";
  const handle = { name, child, exited: null, seen: 0, exitedAt: null,
    text: () => screen,
    type: async (text) => { trace("terminal.type", { name, text: retained(text) }); child.stdin.write(text); await delay(700); child.stdin.write("\r"); await delay(300); },
    key: (text, label) => { trace("terminal.key", { name, key: label }); child.stdin.write(text); },
    // The TUI elides long paths with an ellipsis, past the reach of the
    // placeholders, so an elided word is dropped.
    screen: (label) => trace("screen", { name, label, tail: retained(screen.slice(-1500)).replace(/\S*\u2026/g, "\u2026").replace(/\s+/g, " ") }) };
  const keep = (chunk) => { const text = stripAnsi(String(chunk)); appendFileSync(logPath, text); screen = (screen + text).slice(-40000); };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  child.on("exit", (status, signal) => { handle.exited = { status, signal }; handle.exitedAt = Date.now(); trace("terminal.exit", { name, status, signal }); });
  terminals.push(handle);
  trace("terminal.start", { name, args: args.map(retained), scriptPid: child.pid, cwd: retained(cwd) });
  return handle;
};
const exitTerminal = async (handle) => {
  if (handle.exited) return;
  await handle.type("/exit");
  if (!(await settle(() => handle.exited, `${handle.name} exit`, 15000))) {
    handle.screen(`${handle.name}-exit`);
    handle.key("\u0003", "ctrl-c"); await delay(500); handle.key("\u0003", "ctrl-c");
    await settle(() => handle.exited, `${handle.name} interrupt exit`, 10000);
  }
};
const submitted = (since, label) => hookSince(since, (record) => record.event === "UserPromptSubmit" && !record.payload.agent_id)
  && modelRequests.find((record) => record.receipt > since && record.label === label);
const turnEnded = (since, session) => hookSince(since, (record) => record.event === "Stop" && !record.payload.agent_id && (!session || record.payload.session_id === session));
const probeFor = (name) => modelRequests.find((record) => record.probe?.label === name)?.probe ?? null;
const promptTurn = async (tui, label, session) => {
  const since = mark();
  await tui.type(`SPIKE:${label}`);
  await settle(() => submitted(since, label) && turnEnded(since, session), `${label} Stop`, 90000);
  await delay(500);
};
// A plain terminal's first turn: its positional prompt, in the Worktree named.
const firstTurn = async (name, cwd, label) => {
  const since = mark();
  const tui = terminal(name, ["-C", cwd, `SPIKE:${label}`]);
  await settle(() => turnEnded(since), `${label} Stop`, 120000);
  await delay(1000);
  const session = hookSince(since, (record) => record.event === "SessionStart")?.payload.session_id ?? null;
  trace("first.turn", { name, label, session });
  return { tui, session };
};
// A resumed terminal shows a read-only transcript while another Codex
// process (the daemon or a terminal client) still holds the thread, and a
// person presses `r` to retry. The runner records that screen, then presses
// `r` about every 8 s: 5 s after each refusal it presses, then watches for
// 3 s and, unrefused, 2 s more for the prompt. A retry that resumes the
// thread without sending the prompt given on the command line has it typed.
const asked = (label) => modelRequests.some((record) => record.label === label && record.step === 0);
const resumeWithRetries = async (handle, label, timeout = 200000) => {
  const started = Date.now();
  const presses = [];
  let conflicts = 0;
  let typed = false;
  let firstConflictAt = null;
  while (Date.now() - started < timeout && !handle.exited) {
    if (asked(label)) break;
    const fresh = handle.text().slice(handle.seen);
    if (/open in another app/i.test(fresh)) {
      conflicts += 1;
      firstConflictAt ??= Date.now();
      if (conflicts === 1) handle.screen(`${handle.name}-conflict`);
      handle.seen = handle.text().length;
      await delay(5000);
      if (asked(label)) break;
      handle.key("r", "r");
      presses.push(Date.now());
      await delay(3000);
      if (!asked(label) && !/open in another app/i.test(handle.text().slice(handle.seen))) {
        await delay(2000);
        if (!asked(label) && !/open in another app/i.test(handle.text().slice(handle.seen))) { typed = true; await handle.type(`SPIKE:${label}`); }
      }
      continue;
    }
    await delay(200);
  }
  const host = codexProcesses().find((entry) => entry.comm.startsWith("codex") && entry.ppid === handle.child.pid) ?? null;
  return trace("resume.started", { name: handle.name, label, met: asked(label), conflicts, presses, typed, firstConflictAt,
    firstRequestAt: modelRequests.find((record) => record.label === label)?.receiptTime ?? null, ms: Date.now() - started, hostPid: host?.pid ?? null, daemonPid: daemonPid() });
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
  const listeners = [];
  socket.on((text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method) for (const listener of listeners) listener(parsed, Date.now());
  });
  const send = (method, params = {}, onReply = null) => {
    const id = ++nextId;
    if (onReply) pending.set(id, onReply);
    socket.send(JSON.stringify({ id, method, params }));
    return id;
  };
  const call = (method, params = {}, timeout = 30000) => Promise.race([
    new Promise((resolve) => send(method, params, resolve)),
    delay(timeout).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-663-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: socket.transport, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, send, onNotification: (listener) => listeners.push(listener), close: () => socket.close() };
};
const tcpClient = async (name, port) => {
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  return rpcClient(name, { transport: "loopback-websocket", on: (listener) => socket.addEventListener("message", (message) => listener(message.data)), send: (text) => socket.send(text), close: () => socket.close() });
};
// The advertised socket path is a symlink to the socket Codex binds in its
// shared daemon directory; a fixture path can be too long to connect to.
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(realpathSync(socketPath));
  return rpcClient(name, { transport: "unix-websocket", on: (listener) => socket.on("message", listener), send: (text) => socket.send(text), close: () => socket.close() });
};

// The observer: a daemon client that never subscribes to a thread. It keeps
// every `thread/closed` and `thread/started` notification, and polls
// `thread/loaded/list`, recording each change.
let observer = null;
let loadedPoll = null;
const closedAt = new Map();
const lockProbedOnClose = new Set();
const startObserver = async () => {
  observer = await daemonClient("observer");
  observer.onNotification((message, at) => {
    if (message.method === "thread/closed") {
      const thread = message.params?.threadId ?? null;
      if (!closedAt.has(thread)) closedAt.set(thread, at);
      trace("notification", { method: message.method, thread, at, lock: lockProbedOnClose.has(thread) ? lockState(thread) : undefined });
    } else if (message.method === "thread/started") {
      const thread = message.params?.thread ?? {};
      trace("notification", { method: message.method, thread: thread.id ?? null, at, cwd: retained(thread.cwd ?? ""), ephemeral: thread.ephemeral ?? null });
    }
  });
  let last = null;
  let stop = false;
  const loop = (async () => {
    while (!stop) {
      const listed = await observer.call("thread/loaded/list", {}, 10000);
      const ids = (listed.result?.data ?? []).slice().sort();
      const key = JSON.stringify(ids);
      if (key !== last) { last = key; trace("loaded", { ids, error: listed.error ?? null }); }
      await delay(500);
    }
  })();
  loadedPoll = async () => { stop = true; await loop; };
};
const loadedNow = async (scenario, label) => {
  const listed = await observer.call("thread/loaded/list", {});
  return trace("loaded.snapshot", { scenario, label, ids: (listed.result?.data ?? []).slice().sort(), error: listed.error ?? null });
};
// Codex's log keeps a bounded number of rows, so each scenario keeps its own
// lines when it ends: those naming its thread, and those since it began that
// name none, such as a writer-lock cleanup warning.
const threadId = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/;
let scenarioStart = 0;
const unloadLog = (thread) => codexLog().entries.filter((entry) => entry.message.includes(thread) || (entry.atMs >= scenarioStart && !threadId.test(entry.message)));

const scenarios = [];
const scenario = (name, runScenario) => scenarios.push({ name, run: runScenario });
const grant = ["--sandbox", "workspace-write", "--add-dir", worktreeRoot, "--add-dir", gitDir, "-c", "sandbox_workspace_write.network_access=true"];

scenario("daemon-start", async () => {
  const started = await run("codex", ["app-server", "daemon", "start"]);
  trace("daemon.start", { status: started.status });
  await waitFor(() => existsSync(socketPath) && daemonPid(), "daemon control socket", 30000);
  ownSharedEntry = path.basename(realpathSync(socketPath));
  trace("daemon.ready", { pid: daemonPid(), sharedSocket: path.dirname(realpathSync(socketPath)) === sharedDaemonDir });
  await startObserver();
});

// A daemon-hosted session exits and is resumed at once with explicit sandbox
// roots and network: at its own Worktree (`ordinary`), or at another after
// declaring the move (`relocate`).
const exitAndResume = async (prefix, { issue, target, declare }) => {
  plan(`${prefix}-first`, [{ work: `start-${issue}` }]);
  if (declare) plan(`${prefix}-declare`, [{ work: `relocate:${target}` }, { work: "show" }]);
  plan(`${prefix}-resume`, [{ work: "show" }]);
  const { tui, session } = await firstTurn(`${prefix}-t1`, issueA, `${prefix}-first`);
  lockProbedOnClose.add(session);
  await view(prefix, "after-start");
  if (declare) {
    await promptTurn(tui, `${prefix}-declare`, session);
    await view(prefix, "after-declare");
  }
  lockCheck(prefix, "before-exit", session);
  const exitMark = mark();
  await exitTerminal(tui);
  const exitedAt = tui.exitedAt;
  lockCheck(prefix, "after-exit", session);
  await loadedNow(prefix, "after-exit");
  // What Dashpot reports once the daemon unloads the thread: just after its
  // `SessionEnd`, and once the settler that hook starts has decided.
  const unloadViews = (async () => {
    if (!(await settle(() => sessionEnd(exitMark, session), `${prefix} unload SessionEnd`, 150000))) return;
    await delay(1000);
    await view(prefix, "after-unload");
    await delay(12000);
    await view(prefix, "after-unload-settle");
  })();
  const resumeMark = mark();
  const t2 = terminal(`${prefix}-t2`, ["resume", session, "-C", target, ...grant, `SPIKE:${prefix}-resume`]);
  const resumed = await resumeWithRetries(t2, `${prefix}-resume`);
  await settle(() => turnEnded(resumeMark, session), `${prefix}-resume Stop`, 60000);
  await delay(1000);
  lockCheck(prefix, "after-resume", session);
  await loadedNow(prefix, "after-resume");
  await unloadViews;
  await view(prefix, "after-resume");
  // The settler Dashpot starts on a daemon-hosted `SessionEnd` decides
  // within about 10 s.
  await delay(13000);
  await view(prefix, "after-resume-settle");
  const endMark = mark();
  await exitTerminal(t2);
  await settle(() => sessionEnd(endMark, session), `${prefix} resumed SessionEnd`, 30000);
  await delay(13000);
  lockCheck(prefix, "after-resumed-exit", session);
  await view(prefix, "after-resumed-exit");
  await eventLog(prefix, [session]);
  trace(`${prefix}.outcome`, { session, exitedAt, closedAt: closedAt.get(session) ?? null, resumed: resumed.receipt, firstUnloadEnd: sessionEnd(exitMark, session)?.receipt ?? null,
    hooks: hookTimeline(session), turns: rolloutTurns(session), log: unloadLog(session),
    probes: Object.fromEntries([`${prefix}-first.0`, `${prefix}-declare.0`, `${prefix}-declare.1`, `${prefix}-resume.0`].map((name) => [name, probeFor(name)]).filter(([, found]) => found)) });
};
scenario("ordinary", () => exitAndResume("or", { issue: 1, target: issueA, declare: false }));
scenario("relocate", () => exitAndResume("rl", { issue: 2, target: issueB, declare: true }));

// The daemon's unload of an idle thread, its cleanup slowed by the writer
// coordination lock another process holds until `releaseAfter` ms after the
// client exits. A controller tries to resume the thread while its cleanup is
// blocked, and `codex exec resume` resumes it once it has closed.
const slowUnload = async (prefix, releaseAfter, issue) => {
  plan(`${prefix}-first`, [{ work: `start-${issue}` }]);
  plan(`${prefix}-exec`, [{ work: "show" }]);
  const { tui, session } = await firstTurn(`${prefix}-t1`, issueA, `${prefix}-first`);
  lockProbedOnClose.add(session);
  const exitMark = mark();
  await exitTerminal(tui);
  const exitedAt = tui.exitedAt;
  const holder = await holdCoordination(prefix);
  lockCheck(prefix, "after-exit", session);
  await settle(() => sessionEnd(exitMark, session), `${prefix} SessionEnd`, 100000);
  await delay(1000);
  await view(prefix, "after-unload");
  await delay(4000);
  lockCheck(prefix, "during-cleanup", session);
  await loadedNow(prefix, "during-cleanup");
  const resumer = await daemonClient(`${prefix}-resumer`);
  const attempt = await resumer.call("thread/resume", { threadId: session });
  if (attempt.result) await resumer.call("thread/unsubscribe", { threadId: session });
  trace("resume.attempt", { scenario: prefix, phase: "during-cleanup", via: "daemon thread/resume", error: attempt.error ? { code: attempt.error.code, message: retained(attempt.error.message) } : null,
    result: attempt.result ? { id: attempt.result.thread?.id ?? null } : null });
  resumer.close();
  await delay(7000);
  await view(prefix, "during-cleanup-settle");
  lockCheck(prefix, "during-cleanup-settle", session);
  await waitFor(() => Date.now() >= exitedAt + releaseAfter || closedAt.has(session), `${prefix} hold`, releaseAfter + 10000).catch(() => {});
  if (closedAt.has(session)) {
    lockCheck(prefix, "closed-while-held", session);
    await loadedNow(prefix, "closed-while-held");
    await waitFor(() => Date.now() >= exitedAt + releaseAfter, `${prefix} hold`, releaseAfter + 10000).catch(() => {});
  }
  await holder.release();
  await settle(() => closedAt.has(session), `${prefix} thread/closed`, 60000);
  await delay(1000);
  lockCheck(prefix, "after-release", session);
  await loadedNow(prefix, "after-release");
  const execMark = mark();
  const resumed = await run("codex", ["exec", "-C", issueA, ...grant, "resume", session, `SPIKE:${prefix}-exec`], { cwd: root, timeout: 90000 });
  trace("resume.attempt", { scenario: prefix, phase: "after-close", via: "codex exec resume", status: resumed.status,
    stderr: retained(stripAnsi(resumed.stderr)).split("\n").filter((line) => /error|writer|conflict|closing/i.test(line)).join("\n").slice(-800) });
  await settle(() => sessionEnd(execMark, session), `${prefix} exec SessionEnd`, 30000);
  await delay(13000);
  lockCheck(prefix, "after-exec", session);
  await view(prefix, "after-exec");
  await eventLog(prefix, [session]);
  trace(`${prefix}.outcome`, { session, exitedAt, closedAt: closedAt.get(session) ?? null, holdAcquiredAt: holder.acquiredAt, holdReleasedAt: holder.releasedAt,
    unloadEnd: sessionEnd(exitMark, session)?.receipt ?? null, hooks: hookTimeline(session), turns: rolloutTurns(session), log: unloadLog(session),
    probes: Object.fromEntries([`${prefix}-first.0`, `${prefix}-exec.0`].map((name) => [name, probeFor(name)]).filter(([, found]) => found)) });
};
scenario("slow-release", () => slowUnload("sr", 80000, 1));
scenario("slow-timeout", () => slowUnload("so", 130000, 2));

// A controller's `thread/start` whose required MCP server blocks in
// `initialize`; the controller disconnects during that startup, and the
// runner then lets the server answer.
scenario("mcp-disconnect", async () => {
  const prefix = "md";
  const statusPath = path.join(root, "mcp-status.jsonl");
  const gatePath = path.join(gates, "mcp");
  const mcpStatus = () => { try { return readFileSync(statusPath, "utf8").trim().split("\n").map(parseJson).filter(Boolean); } catch { return []; } };
  const mcpEvent = (event) => mcpStatus().find((entry) => entry.event === event) ?? null;
  const starter = await daemonClient(`${prefix}-starter`);
  const startId = starter.send("thread/start", { cwd: issueA, config: { "mcp_servers.blocked": {
    command: process.execPath, args: [path.join(here, "mcp-blocked.mjs"), statusPath, gatePath], required: true, startup_timeout_sec: 120 } } });
  trace("mcp.thread-start", { scenario: prefix, requestId: startId });
  await settle(() => mcpEvent("initialize-received"), `${prefix} MCP initialize received`, 30000);
  const mcpPid = mcpEvent("start")?.pid ?? null;
  await loadedNow(prefix, "startup-blocked");
  starter.close();
  const disconnectedAt = Date.now();
  trace("mcp.disconnect", { scenario: prefix, at: disconnectedAt });
  await delay(3000);
  await loadedNow(prefix, "after-disconnect");
  const before = new Set((await observer.call("thread/loaded/list", {})).result?.data ?? []);
  writeFileSync(gatePath, "");
  const openedAt = Date.now();
  trace("mcp.gate", { scenario: prefix, at: openedAt });
  await settle(() => mcpEvent("initialize-answered"), `${prefix} MCP initialize answered`, 30000);
  let thread = null;
  await settle(() => {
    thread = records.find((record) => record.kind === "notification" && record.method === "thread/started" && record.receiptTime >= disconnectedAt - 5000 && record.cwd === retained(issueA))?.thread ?? null;
    return thread;
  }, `${prefix} thread started`, 30000);
  if (!thread) {
    const after = (await observer.call("thread/loaded/list", {})).result?.data ?? [];
    thread = after.find((id) => !before.has(id)) ?? null;
  }
  lockProbedOnClose.add(thread);
  await delay(1000);
  lockCheck(prefix, "loaded", thread);
  await loadedNow(prefix, "after-startup");
  await settle(() => closedAt.has(thread), `${prefix} thread/closed`, 150000);
  await settle(() => mcpEvent("stdin-end") || mcpEvent("signal") || (mcpPid && !existsSync(`/proc/${mcpPid}`)), `${prefix} MCP process exit`, 20000);
  await delay(1000);
  lockCheck(prefix, "after-closed", thread);
  await loadedNow(prefix, "after-closed");
  const resumer = await daemonClient(`${prefix}-resumer`);
  const attempt = await resumer.call("thread/resume", { threadId: thread });
  trace("resume.attempt", { scenario: prefix, phase: "after-close", via: "daemon thread/resume", error: attempt.error ? { code: attempt.error.code, message: retained(attempt.error.message) } : null,
    result: attempt.result ? { id: attempt.result.thread?.id ?? null, cwd: retained(attempt.result.thread?.cwd ?? ""), turns: attempt.result.thread?.turns?.length ?? null,
      sandbox: parseJson(retained(JSON.stringify(attempt.result.sandbox ?? null))) } : null });
  if (attempt.result) await resumer.call("thread/unsubscribe", { threadId: thread });
  resumer.close();
  // Codex writes its log in batches.
  await delay(6000);
  trace(`${prefix}.outcome`, { thread, disconnectedAt, openedAt, closedAt: closedAt.get(thread) ?? null, mcp: mcpStatus().map((entry) => ({ event: entry.event, pid: entry.pid, at: entry.at, signal: entry.signal ?? null })),
    mcpAlive: mcpPid ? existsSync(`/proc/${mcpPid}`) : null, hooks: hookTimeline(thread), log: unloadLog(thread) });
});

scenario("daemon-stop", async () => {
  if (loadedPoll) await loadedPoll();
  if (observer) { observer.close(); observer = null; }
  const pid = daemonPid();
  const stopped = await run("codex", ["app-server", "daemon", "stop"]);
  trace("daemon.stop", { status: stopped.status });
  await settle(() => !pid || !existsSync(`/proc/${pid}`), "daemon gone", 30000);
});

const scripts = ["run.mjs", "hook.mjs", "command.mjs", "mcp-blocked.mjs", "lock.py", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["hook.py", ...["hook_publish.py", "hook_records.py", "hook_scan.py", "deferred_end.py", "session_exits.py", "work.py", "work_store.py", "work_reconciliation.py", "liveness.py", "processes.py"]
  .map((file) => `sessions/${file}`)].map((file) => `src/dashpot/${file}`);
const digests = () => Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
  .map(([name, file]) => [name, existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null]));
try {
  let bwrap = null;
  try { bwrap = execFileSync("bwrap", ["--version"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim(); } catch {}
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, bwrap,
    python: execFileSync("python3", ["--version"], { encoding: "utf8" }).trim(),
    binaryTarget: retained(execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim()),
    binarySHA256: createHash("sha256").update(readFileSync(binary)).digest("hex"),
    dashpot: { version: dashpotSync(["--version"]).stdout.trim(), head: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      dirtySource: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean) },
    hookEvents, worktrees: Object.fromEntries(Object.entries(worktrees).map(([name, dir]) => [name, retained(dir)])), worktreeRoot: retained(worktreeRoot), gitDir: retained(gitDir),
    outside: retained(outside), grant: grant.map(retained), scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name) || name.startsWith("daemon-")),
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

  for (const { name, run: runScenario } of scenarios) {
    if (selected && !selected.has(name) && !name.startsWith("daemon-")) continue;
    trace("scenario", { name });
    scenarioStart = Date.now();
    try { await runScenario(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
    await delay(500);
  }
  trace("codex.log", codexLog());
  trace("sources.after", { sourceSHA256: digests() });
  console.log(`Scenarios completed: ${root}`);
} catch (error) {
  trace("runner.error", { error: retained(String(error?.stack ?? error)).slice(0, 2000) });
  throw error;
} finally {
  if (loadedPoll) { try { await loadedPoll(); } catch {} }
  if (observer) { try { observer.close(); } catch {} }
  for (const handle of terminals) { if (!handle.exited) { try { handle.child.kill("SIGTERM"); } catch {} } }
  if (daemonPid()) spawnSync("codex", ["app-server", "daemon", "stop"], { cwd: fixture, env, timeout: 60000 });
  await delay(1000);
  const left = codexProcesses();
  trace("cleanup.left", { processes: left.map((entry) => ({ pid: entry.pid, comm: entry.comm })) });
  for (const entry of left) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: codexProcesses().map((entry) => entry.pid) });
  const sharedAfter = sharedEntries();
  const own = (name) => ownSharedEntry !== null && (name === ownSharedEntry || name === `${ownSharedEntry}.lock`);
  trace("shared-daemon-dir", { ownBound: ownSharedEntry !== null, ownLeft: sharedAfter.filter(own).length, ownBefore: sharedBefore.filter(own).length,
    othersAdded: sharedAfter.filter((name) => !own(name) && !sharedBefore.includes(name)).length, othersRemoved: sharedBefore.filter((name) => !own(name) && !sharedAfter.includes(name)).length });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  writeFileSync(path.join(root, "done"), "");
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
