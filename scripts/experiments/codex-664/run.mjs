// Worker mail and follow-up run for Issue #664: drives a pinned Codex CLI
// against a loopback Responses API fixture with an isolated CODEX_HOME, whose
// daemon updater is off, and Dashpot's own Codex hook publisher, in a
// disposable Dashpot Project whose Issues are Local Issue Markdown. Three
// multi-agent v2 leads on the managed daemon spawn more workers than their
// residency capacity, so that Codex evicts finished workers to make room.
// Lead L, at the default capacity, sends queue-only mail to finished workers
// before and after Codex evicts them, gives each a `followup_task`, and runs
// into the running-turn limit; one evicted worker started with
// `fork_turns: "none"`, the other with the full history. Leads R and S, at a
// capacity of one, leave mail with an evicted worker across the lead's own
// unload and `thread/resume` (R) and across a daemon restart (S), then
// message and follow up that worker. The trace records every model request's
// fixture markers in input order, `list_agents` replies, the daemon's loaded
// threads, hooks, shells, and Dashpot's own published view, metadata only.
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
const expectedVersion = process.argv[3] ?? "0.162.0";
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-664-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const worktrees = { main: fixture, other };
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
  SPIKE_DASHPOT: dashpotCommand,
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: two Local Issue Markdown Issues, the main
// working tree, and one linked Worktree whose Cleanup check shows the
// `sub-agent` blocker.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2]) {
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
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  trace(url.pathname === "/hook" ? "hook" : "command", await body(req));
  res.end("{}");
});
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` (a person's prompt, a spawn
// message, or a follow-up task) selects the plan `plans[label]`; the number of
// tool outputs after that item selects the step. Each step becomes one tool
// call; when the plan runs out, the model answers `DONE:<label>`, which is the
// worker's final message. Queue-only mail carries `NOTE:<name>`. Every request
// records which markers its input carries, at which input index, and in
// which kind of item, which is how the trace shows what reached a thread, in
// what order, and how many times.
const commandScript = path.join(here, "command.mjs");
const exec = (options = {}) => ({ exec: options });
const plans = {
  // Lead L, at the default capacity: residency and running turns both 3.
  "l-bind": [exec({ work: "start-1" })],
  "l-spawn": [{ spawn: ["worker_a", "wa", "none"] }, { spawn: ["worker_f", "wf", "all"] }, { wait: 30000 }, { wait: 15000 }, { list: true }],
  wa: [exec({ hold: 500 })],
  wf: [exec({ hold: 500 })],
  // Unread mail while both are resident and finished.
  "l-pre": [{ send: ["/root/worker_a", "NOTE:a-pre1"] }, { send: ["/root/worker_a", "NOTE:a-pre2"] }, { send: ["/root/worker_f", "NOTE:f-pre1"] }, { list: true }],
  // Three running workers fill residency, evicting A then F; a fourth spawn
  // while they run meets the running-turn limit, and a follow-up to evicted
  // A finds no slot to reload it into.
  "l-fill": [{ spawn: ["worker_b", "wb", "none"] }, { spawn: ["worker_c", "wc", "none"] }, { spawn: ["worker_d", "wd", "none"] }, { list: true },
    { spawn: ["worker_e", "we", "none"] }, { followup: ["/root/worker_a", "wa-full"] }, { list: true }],
  wb: [exec({ hold: 9000 })], wc: [exec({ hold: 9000 })], wd: [exec({ hold: 9000 })], we: [exec()], "wa-full": [exec()],
  // Mail to the evicted workers once every running worker has finished, so
  // a reload would find room.
  "l-post": [{ send: ["/root/worker_a", "NOTE:a-post1"] }, { send: ["/root/worker_a", "NOTE:a-post2"] }, { send: ["/root/worker_f", "NOTE:f-post1"] }, { list: true }],
  "l-follow": [{ followup: ["/root/worker_a", "wa2"] }, { wait: 30000 }, { followup: ["/root/worker_f", "wf2"] }, { wait: 30000 }, { list: true }],
  wa2: [exec({ hold: 5000 }), exec()],
  wf2: [exec()],
  // A second follow-up: earlier mail must not arrive again.
  "l-again": [{ followup: ["/root/worker_a", "wa3"] }, { wait: 30000 }, { list: true }],
  wa3: [exec()],
  // Lead R, capacity 1: mail left with evicted worker R1 across R's unload.
  "r-spawn1": [{ spawn: ["worker_r1", "r1", "none"] }, { wait: 30000 }],
  r1: [exec()],
  "r-pre": [{ send: ["/root/worker_r1", "NOTE:r1-pre"] }],
  "r-spawn2": [{ spawn: ["worker_r2", "r2", "none"] }, { wait: 30000 }, { list: true }],
  r2: [exec()],
  "r-post": [{ send: ["/root/worker_r1", "NOTE:r1-post"] }, { list: true }],
  "r-cold": [{ list: true }, { send: ["/root/worker_r1", "NOTE:r1-cold"] }, { list: true }],
  "r-follow": [{ followup: ["/root/worker_r1", "r1b"] }, { wait: 30000 }, { list: true }],
  r1b: [exec()],
  // Lead S, capacity 1: the same across a daemon restart.
  "s-spawn1": [{ spawn: ["worker_s1", "s1", "none"] }, { wait: 30000 }],
  s1: [exec()],
  "s-pre": [{ send: ["/root/worker_s1", "NOTE:s1-pre"] }],
  "s-spawn2": [{ spawn: ["worker_s2", "s2", "none"] }, { wait: 30000 }, { list: true }],
  s2: [exec()],
  "s-post": [{ send: ["/root/worker_s1", "NOTE:s1-post"] }, { list: true }],
  "s-cold": [{ list: true }, { send: ["/root/worker_s1", "NOTE:s1-cold"] }, { list: true }],
  "s-follow": [{ followup: ["/root/worker_s1", "s1b"] }, { wait: 30000 }, { list: true }],
  s1b: [exec()],
};
// No word boundary: Codex puts a worker's final message straight after a
// newline, which JSON escapes as `\n`.
const markerPattern = /(SPIKE|NOTE|DONE):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
// Parsed JSON, or null for text that is not JSON.
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
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
  // The `thread_id` header names the root session for every thread in a
  // tree; the request's client metadata names the thread itself.
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const session = payload.client_metadata?.session_id ?? req.headers["session_id"] ?? null;
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) { directiveAt = index; label = found.at(-1)[2]; }
  });
  // Each marker once per item that carries it, in input order; a tool call
  // or its output is labelled by its type, so a marker in a spawn's
  // arguments is not mistaken for delivered mail.
  const markers = input.flatMap((item, index) => [...new Set([...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[0]))]
    .map((marker) => [index, item.type ?? null, item.role ?? null, marker]));
  // Every inter-agent item the thread's input carries: who wrote it, to whom,
  // and the start of its text, which Codex composes from fixture markers.
  const textOf = (item) => [item.content ?? []].flat().map((part) => typeof part === "string" ? part : Object.values(part ?? {}).filter((value) => typeof value === "string" && value !== part.type).join(" ")).join(" | ");
  const agentMessages = input.flatMap((item, index) => item.type === "agent_message"
    ? [[index, item.author ?? null, item.recipient ?? null, textOf(item).slice(0, 200)]] : []);
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsKey = toolNames.join(",");
  const toolsChanged = lastToolsByThread.get(thread) !== toolsKey;
  lastToolsByThread.set(thread, toolsKey);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const plan = label ? plans[label] ?? [] : [];
  const step = plan[outputs.length] ?? null;
  const call = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.exec) {
    const { cd = null, hold = 200, work = "-" } = step.exec;
    action = "exec_command";
    item = call("exec_command", { cmd: `${cd ? `cd ${cd} && ` : ""}node ${commandScript} ${label}.${outputs.length} ${hold} ${work}`, login: false, yield_time_ms: 120000 });
  } else if (step?.spawn) {
    const [taskName, child, fork] = step.spawn;
    action = "spawn_agent";
    item = call("spawn_agent", { message: `SPIKE:${child}`, task_name: taskName, fork_turns: fork });
  } else if (step?.send) {
    const [target, text] = step.send;
    action = "send_message";
    item = call("send_message", { target, message: text });
  } else if (step?.followup) {
    const [target, child] = step.followup;
    action = "followup_task";
    item = call("followup_task", { target, message: `SPIKE:${child}` });
  } else if (step?.wait) {
    action = "wait_agent";
    item = call("wait_agent", { timeout_ms: step.wait });
  } else if (step?.list) {
    action = "list_agents";
    item = call("list_agents", {});
  }
  // The output of the latest call, which Codex may follow with inter-agent
  // items; a `list_agents` reply is kept whole.
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const lastOutput = latestOutput ? String(latestOutput.output ?? "").replaceAll(root, "$ROOT").slice(0, 2000) : null;
  const request = trace("model.request", { thread, label, step: outputs.length, inputItems: input.length, directiveAt, markers, action, missing: Boolean(step && !item),
    lastOutput, tools: toolsChanged ? toolNames : undefined, session, agentMessages,
    tail: input.slice(-3).map((item) => [item.type ?? null, item.role ?? null]), parentThread: req.headers["x-codex-parent-thread-id"] ?? null });
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

// The model catalog names `fixture-v2` only, a copy of a bundled entry
// without a tool set or code mode, declaring multi-agent v2.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const catalogSummary = bundled.models.map((entry) => [entry.slug, entry.multi_agent_version ?? null, entry.tool_mode ?? null]);
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
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => {
  try { return JSON.parse(readFileSync(daemonSettingsPath, "utf8")); } catch (error) { return { unreadable: String(error) }; }
};

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
const daemonPid = () => daemons()[0]?.pid ?? null;
const isSettler = (entry) => / -m dashpot\.hook settle /.test(entry.cmdline);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const processes = (label) => trace("processes", { label, processes: codexProcesses().map(brief), daemons: daemons().map((entry) => entry.pid), socketExists: existsSync(socketPath),
  daemonSettings: daemonSettings() });
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
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
const threadSummary = (thread) => thread && ({ id: thread.id, parentThreadId: thread.parentThreadId ?? null, cwd: thread.cwd ?? null,
  status: thread.status, ephemeral: thread.ephemeral, agentPath: thread.agentPath ?? null, model: thread.model ?? null });
// Hooks in a window, as [event, session, agent, turn, source, time].
const timeline = (since) => hooks().filter((record) => record.receiptTime > since)
  .map((record) => [record.event, record.payload.session_id, record.payload.agent_id ?? null, record.payload.turn_id ?? null, record.payload.source ?? null, record.receiptTime]);
const stoppedSince = (since, agent) => hooks().some((record) => record.receiptTime > since && record.event === "SubagentStop" && record.payload.agent_id === agent);
const requestsOf = (thread, after = 0) => modelRequests.filter((record) => record.thread === thread && record.receiptTime > after);
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;

// Dashpot's published view: the Agent Runs, the diagnostics, `work show`
// from the main Worktree, which names the working sub-agents of each run
// there, and the Cleanup check of the linked Worktree, whose `sub-agent`
// blocker names them too.
const view = (label) => {
  const ran = dashpot(["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  const shown = dashpot(["work", "show"]);
  const checked = dashpot(["worktree", "check", other, "--json"]);
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400),
    agentRuns: (parsed?.agentRuns ?? []).map((agentRun) => ({ issueId: agentRun.issueId, state: agentRun.state, host: agentRun.processOrSession, orphaned: agentRun.orphaned,
      workingDirectory: agentRun.workingDirectory, startedAt: agentRun.startedAt })),
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })),
    workShow: { status: shown.status, stdout: shown.stdout.split("\n").filter((line) => !/^\s+\d{4}-\d\d-\d\dT/.test(line)).join("\n").slice(0, 1500), stderr: shown.stderr.slice(0, 300) },
    otherCheck: { status: checked.status, result: parseJson(checked.stdout), stderr: checked.stderr.slice(0, 300) } });
};

// One-shot Codex commands, launched by name through the fixture PATH.
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const startedAt = Date.now();
  const child = spawn("codex", args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const clean = (text) => stripAnsi(text).replaceAll(root, "<root>");
  const statusLines = (text) => clean(text).split("\n").filter((line) => /^(warning: |hook: |Error: |error: )/.test(line)).join("\n");
  return trace("codex.command", { label, args: args.map((arg) => arg.replaceAll(root, "<root>")), status, signal, startedAt, endedAt: Date.now(),
    stdout: clean(stdout).slice(-600), stderr: statusLines(stderr).slice(-1200) });
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
  const init = await call("initialize", { clientInfo: { name: `dashpot-664-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
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
  const startedAt = Date.now();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, status: started.result?.turn?.status ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, startedAt };
  await waitFor(() => completedTurn(client, turnId), `turn ${text} completed`, options.timeout ?? 90000);
  const completed = completedTurn(client, turnId);
  await quietly(waitFor(() => hooks().some((record) => record.receiptTime >= startedAt && record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000));
  trace("turn.completed", { client: client.name, threadId, turnId, status: completed.status, completedAt: completed.receivedAt });
  return { turnId, startedAt, status: completed.status, completedAt: completed.receivedAt };
};
const startThread = async (client, name, params) => {
  const started = await client.call("thread/start", { cwd: fixture, ...params });
  const thread = started.result?.thread;
  trace("thread.start", { name, params: { ...params, cwd: params.cwd ?? fixture }, thread: threadSummary(thread), error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
const readThread = async (client, threadId) => {
  const read = await client.call("thread/read", { threadId });
  return threadSummary(read.result?.thread) ?? { error: read.error ?? null };
};
// Which threads the daemon holds loaded: the lead and its resident workers.
const residency = async (client, label, threads) => {
  const loaded = (await client.call("thread/loaded/list", {})).result?.data ?? [];
  const read = {};
  for (const [name, id] of Object.entries(threads)) if (id) read[name] = { id, loaded: loaded.includes(id), status: (await readThread(client, id)).status ?? null };
  return trace("residency", { label, loaded, threads: read });
};

const scripts = ["run.mjs", "verify.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "deferred_end.py", "work_reconciliation.py", "hook_records.py", "work.py", "hook_scan.py", "processes.py", "working_directories.py"]
  .map((file) => `src/dashpot/sessions/${file}`).concat(["src/dashpot/repository/cleanup/obstacles.py"]);
let controllers = [];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(os.homedir(), "~"),
    binarySHA256: createHash("sha256").update(readFileSync(binary)).digest("hex"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, dirty }, worktrees, socketPath, hookEvents, catalogSummary,
    fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2" },
    // The runner's own scripts by name, and the lifecycle modules it
    // exercised by repository path.
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });

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

  // The managed daemon hosts every lead; controllers drive it as a client would.
  trace("scenario", { name: "daemon" });
  await codex(["app-server", "daemon", "start"], "daemon-start", { timeout: 60000 });
  await waitFor(() => existsSync(socketPath) && daemons().length === 1, "daemon control socket", 30000);
  processes("daemon-started");
  const c1 = await daemonClient("controller-1");
  controllers.push(c1);

  // Lead L binds Issue 1 in the main Worktree, at the default capacity.
  trace("scenario", { name: "local-eviction" });
  const lead = await startThread(c1, "lead-l", { model: "fixture-v2" });
  await runTurn(c1, lead, "SPIKE:l-bind");
  view("l-bound");

  // Workers A (no history) and F (the lead's full history) run and finish
  // while L waits; both stay resident.
  const spawned = await runTurn(c1, lead, "SPIKE:l-spawn", { timeout: 120000 });
  await quietly(waitFor(() => command("wa.0", "end") && command("wf.0", "end"), "A and F finish their commands", 30000));
  const workerA = threadOf("wa.0");
  const workerF = threadOf("wf.0");
  await quietly(waitFor(() => stoppedSince(spawned.startedAt, workerA) && stoppedSince(spawned.startedAt, workerF), "A and F stop", 30000));
  await delay(1500);
  const lThreads = () => ({ lead, a: workerA, f: workerF, b: threadOf("wb.0"), c: threadOf("wc.0"), d: threadOf("wd.0"), e: threadOf("we.0") });
  await residency(c1, "l-spawned", lThreads());

  // Unread queue-only mail to the finished, resident A and F.
  const pre = await runTurn(c1, lead, "SPIKE:l-pre");
  await delay(3000);
  await residency(c1, "l-pre", lThreads());
  trace("l-pre.outcome", { lead, workerA, workerF, requestsA: requestsOf(workerA, pre.startedAt).map((record) => record.receipt),
    requestsF: requestsOf(workerF, pre.startedAt).map((record) => record.receipt), hooks: timeline(pre.startedAt) });

  // B, C and D take every slot while running; E meets the running-turn limit.
  const fill = await runTurn(c1, lead, "SPIKE:l-fill", { timeout: 120000 });
  await quietly(waitFor(() => command("wb.0") && command("wc.0") && command("wd.0"), "B, C and D start", 30000));
  await residency(c1, "l-filled", lThreads());
  view("l-filled-running");
  const filled = [threadOf("wb.0"), threadOf("wc.0"), threadOf("wd.0")];
  await quietly(waitFor(() => filled.every((worker) => worker && stoppedSince(fill.startedAt, worker)), "B, C and D stop", 60000));
  await delay(2000);
  await residency(c1, "l-filled-stopped", lThreads());
  view("l-filled-stopped");
  trace("l-fill.outcome", { lead, workers: filled, eStarted: Boolean(command("we.0")), requests: requestsOf(lead, fill.startedAt).map((record) => [record.receipt, record.action, record.lastOutput]),
    requestsA: requestsOf(workerA, fill.startedAt).map((record) => record.receipt), requestsF: requestsOf(workerF, fill.startedAt).map((record) => record.receipt), hooks: timeline(fill.startedAt) });

  // More queue-only mail while A and F are evicted and slots are free.
  const post = await runTurn(c1, lead, "SPIKE:l-post");
  await delay(5000);
  await residency(c1, "l-post", lThreads());
  trace("l-post.outcome", { lead, requestsA: requestsOf(workerA, post.startedAt).map((record) => record.receipt),
    requestsF: requestsOf(workerF, post.startedAt).map((record) => record.receipt), hooks: timeline(post.startedAt) });
  view("l-post-idle");

  // Follow-ups reload A and F; the lead waits for each completion.
  const follow = await runTurn(c1, lead, "SPIKE:l-follow", { detached: true });
  await quietly(waitFor(() => command("wa2.0"), "A's follow-up command", 30000));
  await residency(c1, "l-follow-a-running", lThreads());
  view("l-follow-a-running");
  await waitFor(() => completedTurn(c1, follow.turnId), "l-follow completes", 120000);
  trace("turn.completed", { client: c1.name, threadId: lead, turnId: follow.turnId, status: completedTurn(c1, follow.turnId).status, completedAt: completedTurn(c1, follow.turnId).receivedAt });
  await quietly(waitFor(() => stoppedSince(follow.startedAt, workerA) && stoppedSince(follow.startedAt, workerF), "A and F stop again", 30000));
  await delay(2000);
  await residency(c1, "l-followed", lThreads());
  view("l-followed");
  trace("l-follow.outcome", { lead, workerA, workerF, leadRequests: requestsOf(lead, follow.startedAt).map((record) => [record.receipt, record.action, record.lastOutput]),
    requestsA: requestsOf(workerA, follow.startedAt).map((record) => record.receipt), requestsF: requestsOf(workerF, follow.startedAt).map((record) => record.receipt),
    hooks: timeline(follow.startedAt) });

  const again = await runTurn(c1, lead, "SPIKE:l-again", { timeout: 120000 });
  await quietly(waitFor(() => stoppedSince(again.startedAt, workerA), "A stops a third time", 30000));
  await delay(1500);
  await residency(c1, "l-again", lThreads());
  trace("l-again.outcome", { lead, requestsA: requestsOf(workerA, again.startedAt).map((record) => record.receipt), hooks: timeline(again.startedAt) });

  // Lead R, capacity 1, on its own client: R1 holds mail from before and
  // after its eviction when R's last client leaves and the daemon unloads R.
  trace("scenario", { name: "lead-unload" });
  const capacityOne = { "agents.max_threads": 1 };
  const c2 = await daemonClient("controller-2");
  controllers.push(c2);
  const leadR = await startThread(c2, "lead-r", { model: "fixture-v2", config: capacityOne });
  const r1Spawn = await runTurn(c2, leadR, "SPIKE:r-spawn1", { timeout: 90000 });
  const workerR1 = threadOf("r1.0");
  await quietly(waitFor(() => stoppedSince(r1Spawn.startedAt, workerR1), "R1 stops", 30000));
  await runTurn(c2, leadR, "SPIKE:r-pre");
  const r2Spawn = await runTurn(c2, leadR, "SPIKE:r-spawn2", { timeout: 90000 });
  const workerR2 = threadOf("r2.0");
  await quietly(waitFor(() => stoppedSince(r2Spawn.startedAt, workerR2), "R2 stops", 30000));
  await runTurn(c2, leadR, "SPIKE:r-post");
  await delay(2000);
  const rThreads = () => ({ lead: leadR, r1: workerR1, r2: workerR2 });
  await residency(c1, "r-before-unload", rThreads());
  const unsubscribed = await c2.call("thread/unsubscribe", { threadId: leadR });
  c2.close();
  controllers = controllers.filter((client) => client !== c2);
  const leftAt = Date.now();
  const rEnded = () => hooks().some((record) => record.receiptTime > leftAt && record.event === "SessionEnd" && record.payload.session_id === leadR);
  const unloaded = await quietly(waitFor(rEnded, "the daemon unloads lead R", 150000));
  await delay(3000);
  await settlersDone("lead-unload");
  await residency(c1, "r-unloaded", rThreads());
  const c3 = await daemonClient("controller-3");
  controllers.push(c3);
  const resumedAt = Date.now();
  const resumedR = await c3.call("thread/resume", { threadId: leadR, config: capacityOne });
  trace("thread.resume", { client: c3.name, threadId: leadR, thread: threadSummary(resumedR.result?.thread), error: resumedR.error ?? null });
  await delay(2000);
  await residency(c3, "r-resumed", rThreads());
  const rCold = await runTurn(c3, leadR, "SPIKE:r-cold");
  await delay(4000);
  await residency(c3, "r-cold", rThreads());
  const rFollow = await runTurn(c3, leadR, "SPIKE:r-follow", { timeout: 90000 });
  await quietly(waitFor(() => stoppedSince(rFollow.startedAt, workerR1), "R1 stops after its follow-up", 30000));
  await delay(1500);
  await residency(c3, "r-followed", rThreads());
  trace("lead-unload.outcome", { lead: leadR, workerR1, workerR2, unsubscribe: unsubscribed.result ?? unsubscribed.error, leftAt, unloaded, resumedAt,
    coldRequestsR1: requestsOf(workerR1, rCold.startedAt).filter((record) => record.receiptTime < rFollow.startedAt).map((record) => record.receipt),
    followRequestsR1: requestsOf(workerR1, rFollow.startedAt).map((record) => record.receipt), hooks: timeline(r1Spawn.startedAt) });

  // Lead S, capacity 1: S1 holds mail from before and after its eviction
  // when the daemon restarts.
  trace("scenario", { name: "daemon-restart" });
  const leadS = await startThread(c3, "lead-s", { model: "fixture-v2", config: capacityOne });
  const s1Spawn = await runTurn(c3, leadS, "SPIKE:s-spawn1", { timeout: 90000 });
  const workerS1 = threadOf("s1.0");
  await quietly(waitFor(() => stoppedSince(s1Spawn.startedAt, workerS1), "S1 stops", 30000));
  await runTurn(c3, leadS, "SPIKE:s-pre");
  const s2Spawn = await runTurn(c3, leadS, "SPIKE:s-spawn2", { timeout: 90000 });
  const workerS2 = threadOf("s2.0");
  await quietly(waitFor(() => stoppedSince(s2Spawn.startedAt, workerS2), "S2 stops", 30000));
  await runTurn(c3, leadS, "SPIKE:s-post");
  await delay(2000);
  const sThreads = () => ({ lead: leadS, s1: workerS1, s2: workerS2, leadL: lead, leadR });
  await residency(c3, "s-before-restart", sThreads());
  view("s-before-restart");
  const oldDaemon = daemonPid();
  for (const client of controllers) client.close();
  controllers = [];
  const restarted = await codex(["app-server", "daemon", "restart"], "daemon-restart", { timeout: 240000 });
  await quietly(waitFor(() => daemonPid() && daemonPid() !== oldDaemon && existsSync(socketPath), "the replacement daemon", 30000));
  await delay(3000);
  await settlersDone("daemon-restart");
  processes("after-restart");
  const c4 = await daemonClient("controller-4");
  controllers.push(c4);
  await residency(c4, "s-restarted", sThreads());
  view("s-restarted");
  const resumedS = await c4.call("thread/resume", { threadId: leadS, config: capacityOne });
  trace("thread.resume", { client: c4.name, threadId: leadS, thread: threadSummary(resumedS.result?.thread), error: resumedS.error ?? null });
  await delay(2000);
  await residency(c4, "s-resumed", sThreads());
  const sCold = await runTurn(c4, leadS, "SPIKE:s-cold");
  await delay(4000);
  await residency(c4, "s-cold", sThreads());
  const sFollow = await runTurn(c4, leadS, "SPIKE:s-follow", { timeout: 90000 });
  await quietly(waitFor(() => stoppedSince(sFollow.startedAt, workerS1), "S1 stops after its follow-up", 30000));
  await delay(1500);
  await residency(c4, "s-followed", sThreads());
  trace("daemon-restart.outcome", { lead: leadS, workerS1, workerS2, oldDaemon, newDaemon: daemonPid(), restart: { status: restarted.status, startedAt: restarted.startedAt, endedAt: restarted.endedAt },
    coldRequestsS1: requestsOf(workerS1, sCold.startedAt).filter((record) => record.receiptTime < sFollow.startedAt).map((record) => record.receipt),
    followRequestsS1: requestsOf(workerS1, sFollow.startedAt).map((record) => record.receipt), hooks: timeline(s1Spawn.startedAt) });
  view("s-followed");

  trace("scenario", { name: "daemon-stop" });
  for (const client of controllers) client.close();
  controllers = [];
  const finalDaemon = daemonPid();
  await codex(["app-server", "daemon", "stop"], "daemon-stop", { timeout: 120000 });
  await quietly(waitFor(() => !finalDaemon || !existsSync(`/proc/${finalDaemon}`), "daemon gone", 20000));
  await settlersDone("daemon stop");
  processes("after-daemon-stop");

  // Dashpot's Event Log for the fixture, metadata only.
  const events = dashpot(["events", "--json"]);
  const eventList = parseJson(events.stdout);
  const fields = ["time", "event.name", "dashpot.process.kind", "dashpot.agent_session.id", "dashpot.worktree.path", "dashpot.issue.id", "dashpot.hook.event",
    "dashpot.outcome.result", "dashpot.agent_session.state", "dashpot.work_store.change", "dashpot.subcommand"];
  trace("dashpot.events", { status: events.status, stderr: events.stderr.slice(0, 300),
    events: (eventList?.events ?? []).filter((event) => event["event.name"] !== "process.start" && event["event.name"] !== "process.end")
      .map((event) => Object.fromEntries(fields.filter((field) => event[field] !== undefined && event[field] !== null).map((field) => [field, event[field]]))) });
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
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
