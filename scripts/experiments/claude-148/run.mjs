// Isolated Claude Code relocation-handoff experiment for Issue #148.
// Drives a pinned Claude Code binary against a loopback Messages API fixture
// with an isolated configuration directory, opts a background session into a
// development channel, pushes relocation requests through that channel, and
// records hook, shell, channel, and listing evidence as a metadata-only trace.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-148-"));
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
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.278";

const env = {
  PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CLAUDE_CONFIG_DIR: path.join(root, "claude-config"),
  ANTHROPIC_API_KEY: "fixture-unused",
  DISABLE_AUTOUPDATER: "1",
  DISABLE_TELEMETRY: "1",
  DISABLE_ERROR_REPORTING: "1",
  DISABLE_BUG_COMMAND: "1",
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  CLAUDE_CODE_DISABLE_TERMINAL_TITLE: "1",
  TERM: "dumb",
  // Read the seeded feature-flag cache although telemetry is off; see the
  // `.claude.json` seed below.
  CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF: "1",
  // Ancestry walks from hooks, shells, and the channel end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);
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
  const record = await body(req);
  if (record.env) delete record.env.CLAUDE_CODE_MESSAGING_TOKEN;
  trace(url.pathname.slice(1), record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `SPIKE:<label>` text in the latest user turn (typed
// or delivered by the channel) selects a fixed tool sequence, then the turn
// ends once every step of that sequence has a tool result.
const commandScript = path.join(here, "command.mjs");
const modelRequests = new Map();
const sse = (res, event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
const report = (label, hold) => ({ tool: "Bash", input: { command: `node ${commandScript} ${label} ${hold ?? 200}`, description: "Report fixture identity" } });
const ack = (label) => ({ tool: (tools) => tools.find((name) => name.endsWith("__ack")), input: { cwd: "reported-by-shell", outcome: label } });
const sequences = {
  idle: () => [],
  hold: (label) => [report(label.name, label.hold)],
  enter: (label) => [{ tool: "EnterWorktree", input: { path: label.cwd } }, report(label.name)],
  relocate: (label) => [{ tool: "EnterWorktree", input: { path: label.cwd } }, report(label.name), ack(label.name)],
  "relocate-direct": (label) => [{ tool: "EnterWorktree", input: { path: label.cwd } }, { tool: "ExitWorktree", input: { action: "keep" } }, report(label.name), ack(label.name)],
  exit: (label) => [{ tool: "ExitWorktree", input: { action: "keep" } }, report(label.name), ack(label.name)],
  background: (label) => [{ tool: "Bash", input: { command: `node ${commandScript} ${label.name} ${label.hold ?? 30000}`, description: "Hold a background job", run_in_background: true } }, report(`${label.name}-fg`)],
};
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/messages")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ type: "error", error: { type: "not_found_error", message: "fixture" } }));
    return;
  }
  const messages = payload.messages ?? [];
  let label = null;
  let latestUser = -1;
  messages.forEach((message, index) => {
    const parts = typeof message.content === "string" ? [{ type: "text", text: message.content }] : message.content ?? [];
    for (const part of parts) {
      const match = part.type === "text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?(?: cwd=(\S+))?/);
      if (match) { label = { name: match[1], hold: match[2], cwd: match[3], channel: /<channel\b/.test(part.text) }; latestUser = index; }
    }
  });
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  const results = messages.slice(latestUser + 1).flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : []);
  const toolResults = results.length;
  // The worktree tools' outcomes are the evidence; other results stay out of the trace.
  const worktreeOutcomes = messages.slice(latestUser + 1).flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_use" && /Worktree$/.test(part.name)) : [])
    .map((use) => { const result = results.find((part) => part.tool_use_id === use.id); const text = typeof result?.content === "string" ? result.content : result?.content?.map((part) => part.text ?? "").join(" ") ?? ""; return { tool: use.name, isError: result?.is_error ?? null, text: text.slice(0, 400) }; });
  const sequence = label ? (sequences[label.name] ?? sequences.hold)(label) : [];
  const step = sequence[toolResults];
  const toolName = step ? (typeof step.tool === "function" ? step.tool(tools) : step.tool) : null;
  const count = (modelRequests.get(label?.name ?? "none") ?? 0) + 1;
  modelRequests.set(label?.name ?? "none", count);
  trace("model.request", { label: label?.name ?? null, viaChannel: label?.channel ?? null, step: toolResults, tool: toolName, available: toolName ? tools.includes(toolName) : null, count, model: payload.model,
    toolCount: tools.length, tools: modelRequests.size === 1 && count === 1 ? tools : undefined, worktreeOutcomes: worktreeOutcomes.length ? worktreeOutcomes : undefined });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse(res, "message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (toolName && tools.includes(toolName)) {
    sse(res, "content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label.name}_${count}`, name: toolName, input: {} } });
    sse(res, "content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(step.input) } });
    sse(res, "content_block_stop", { index: 0 });
    sse(res, "message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { output_tokens: 20 } });
  } else {
    sse(res, "content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse(res, "content_block_delta", { index: 0, delta: { type: "text_delta", text: "Fixture complete." } });
    sse(res, "content_block_stop", { index: 0 });
    sse(res, "message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 4 } });
  }
  sse(res, "message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart", "SubagentStop", "SessionEnd", "CwdChanged"];
const settings = {
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
};
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify(settings, null, 2));
// Pre-accept onboarding so background workers neither prompt nor phone home.
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  // Channels are a research preview behind a remotely served feature flag.
  // The isolated fixture cannot fetch flags, so it seeds the cached value the
  // operator's own account already holds; without it the session logs
  // "Channel notifications skipped: channels feature is not currently available".
  cachedGrowthBookFeatures: { tengu_harbor: true },
  projects: Object.fromEntries([fixture, other, third].map((dir) => [dir, { hasTrustDialogAccepted: true, allowedTools: [] }])),
}, null, 2));
// The development channel is an ordinary stdio MCP server; only the launch
// flag makes it a channel.
const mcpConfig = path.join(root, "mcp.json");
writeFileSync(mcpConfig, JSON.stringify({ mcpServers: { dashpot: { command: process.execPath, args: [path.join(here, "channel.mjs")], env: { SPIKE_SINK: sink.url, SPIKE_STOP_PID: env.SPIKE_STOP_PID } } } }, null, 2));

const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
const channelArgs = ["--mcp-config", mcpConfig, "--strict-mcp-config", "--dangerously-load-development-channels", "server:dashpot"];
const claude = async (args, options = {}) => {
  const child = spawn(binary, args, { cwd: options.cwd ?? fixture, env: { ...env, ...options.env }, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), options.timeout ?? 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const result = { status, signal, stdout, stderr, pid: child.pid };
  trace("action.claude", { args, cwd: options.cwd ?? fixture, pid: child.pid, status, signal, stdout: stdout.slice(-2000), stderr: stderr.slice(-2000) });
  return result;
};
const claudeProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let entry;
    try { entry = describe(Number(name)); } catch { continue; }
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CLAUDE_CONFIG_DIR=${env.CLAUDE_CONFIG_DIR}`)) continue;
    const vars = Object.fromEntries(environ.split("\0").filter((item) => item.startsWith("CLAUDE") && !item.startsWith("CLAUDE_CODE_MESSAGING_TOKEN=")).map((item) => { const at = item.indexOf("="); return [item.slice(0, at), item.slice(at + 1)]; }));
    found.push({ ...entry, env: vars });
  }
  return found;
};
const snapshot = (label, extra = {}) => trace("processes", { label, processes: claudeProcesses(), ...extra });
const agentsJSON = async (label, all = false) => {
  const result = await claude(["agents", "--json", ...(all ? ["--all"] : [])], { timeout: 30000 });
  let parsed = null;
  try { parsed = JSON.parse(result.stdout); } catch {}
  trace("agents", { label, all, status: result.status, agents: parsed, raw: parsed ? undefined : result.stdout.slice(-1000) });
  return parsed ?? [];
};
const hooks = () => records.filter((record) => record.kind === "hook");
const hooksSince = (count) => hooks().slice(count).map((record) => [record.event, record.payload.session_id, record.payload.tool_name ?? record.payload.reason ?? record.payload.source, record.payload.cwd]);
const commands = () => records.filter((record) => record.kind === "command");
const channels = () => records.filter((record) => record.kind === "channel");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
// Deliver a relocation request through the session's own channel process.
const push = async (session, content, meta = {}) => {
  const listening = channels().filter((record) => record.phase === "listening" && record.env.CLAUDE_CODE_SESSION_ID === session.sessionId);
  assert(listening.length === 1, `one channel for session ${session.sessionId}: ${listening.length}`);
  const response = await fetch(listening[0].control + "/push", { method: "POST", body: JSON.stringify({ content, meta }) });
  trace("push", { session: session.sessionId, label: content.match(/SPIKE:[a-z0-9-]+/)?.[0], meta, status: response.status });
};
// Development channels load only in an interactive session, whose startup
// confirmation a person answers, so each fixture session is a terminal
// session hosted by `script`. Only the markers the runner waits for are kept
// from its output.
const terminals = [];
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
const dispatch = async (label, cwd, name) => {
  const hooksBefore = hooks().length;
  const args = [label, "--name", name, "--debug-file", path.join(root, `debug-${name}.txt`), ...channelArgs, ...commonArgs];
  const child = spawn("script", ["-qfec", [binary, ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const terminal = { name, child, output: "", exited: null };
  child.stdout.on("data", (chunk) => { terminal.output += stripAnsi(String(chunk)); });
  child.on("exit", (status, signal) => { terminal.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(terminal);
  trace("dispatch", { name, cwd, args, scriptPid: child.pid });
  const seen = (pattern) => pattern.test(terminal.output);
  await waitFor(() => seen(/Loading\s*development\s*channels/i) || seen(/I\s*am\s*using\s*this\s*for\s*local\s*development/i) || terminal.exited, `${name} development channel confirmation`, 60000);
  trace("terminal.marker", { name, marker: "development-channels-confirmation", exited: terminal.exited });
  assert(!terminal.exited, `${name} exited before confirmation: ${terminal.output.slice(-1500)}`);
  child.stdin.write("\r");
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop"), `${name} first Stop hook`, 90000);
  const stop = hooks().slice(hooksBefore).find((record) => record.event === "Stop");
  const listing = await agentsJSON(`${name}-dispatched`);
  const job = listing.find((entry) => entry.sessionId === stop.payload.session_id) ?? { sessionId: stop.payload.session_id, pid: Number(stop.env.CLAUDE_PID), unlisted: true };
  await waitFor(() => channels().some((record) => record.phase === "initialize") && channels().some((record) => record.phase === "listening" && record.env.CLAUDE_CODE_SESSION_ID === job.sessionId), `${name} channel initialized`, 30000);
  trace("terminal.marker", { name, marker: "channels-notice", noticed: seen(/Channels\s*\(experimental\)/i), warned: seen(/ignored|not on the approved|skipped/i) });
  return { ...job, terminal };
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")), fixture, other, third, channelArgs,
    sourceSHA256: Object.fromEntries(["run.mjs", "channel.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // Scenario 1: a background session launched directly in the linked
  // Worktree registers the development channel.
  trace("scenario", { name: "channel-registration" });
  const jobA = await dispatch("SPIKE:idle", other, "fixture-a");
  const channelA = channels().find((record) => record.phase === "listening" && record.env.CLAUDE_CODE_SESSION_ID === jobA.sessionId);
  trace("channel.identity", { session: jobA.sessionId, workerPid: jobA.pid, channelPid: channelA.pid, channelPpid: channelA.ppid, channelEnv: channelA.env, ancestry: channelA.ancestry.map((entry) => [entry.pid, entry.comm]),
    initialize: channels().find((record) => record.phase === "initialize"), tools: records.find((record) => record.kind === "model.request" && record.tools)?.tools });
  snapshot("a-registered");

  // Scenario 2: a relocation request pushed through the channel moves the
  // directly launched session to the main Worktree with EnterWorktree.
  trace("scenario", { name: "relocate-direct-launch" });
  let hooksBefore = hooks().length;
  await push(jobA, `SPIKE:relocate-direct cwd=${fixture}`, { request: "relocate", destination: fixture });
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === jobA.sessionId), "a relocation turn Stop", 90000);
  await delay(1500);
  const listingA = await agentsJSON("a-after-relocate");
  const relocateCommand = commands().find((record) => record.label === "relocate-direct");
  trace("relocate.outcome", { session: jobA.sessionId, listing: listingA.find((entry) => entry.sessionId === jobA.sessionId), shellCwd: relocateCommand?.cwd, shellEnv: relocateCommand?.env,
    newHooks: hooksSince(hooksBefore), ack: channels().find((record) => record.phase === "ack"), toolSteps: records.filter((record) => record.kind === "model.request" && record.label === "relocate-direct").map((record) => [record.step, record.tool, record.available]),
    worktreeOutcomes: records.filter((record) => record.kind === "model.request" && record.label === "relocate-direct").at(-1)?.worktreeOutcomes });

  // Scenario 2b: the same session can enter another linked Worktree, so a
  // sibling checkout is a reachable destination where the main Worktree is not.
  trace("scenario", { name: "relocate-direct-launch-to-linked" });
  hooksBefore = hooks().length;
  await push(jobA, `SPIKE:relocate cwd=${third}`, { request: "relocate", destination: third });
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === jobA.sessionId), "a linked relocation turn Stop", 90000);
  await delay(1500);
  const listingA2 = await agentsJSON("a-after-linked-relocate");
  trace("relocate-linked.outcome", { session: jobA.sessionId, listing: listingA2.find((entry) => entry.sessionId === jobA.sessionId), shellCwd: commands().find((record) => record.label === "relocate")?.cwd,
    newHooks: hooksSince(hooksBefore), worktreeOutcomes: records.filter((record) => record.kind === "model.request" && record.label === "relocate").at(-1)?.worktreeOutcomes });

  // Scenario 3: a session that entered the linked Worktree from the main
  // Worktree returns with ExitWorktree on request.
  trace("scenario", { name: "relocate-entered-session" });
  const jobB = await dispatch(`SPIKE:enter cwd=${other}`, fixture, "fixture-b");
  const enterCommand = commands().find((record) => record.label === "enter");
  const listingB = await agentsJSON("b-entered");
  trace("enter.outcome", { session: jobB.sessionId, listing: listingB.find((entry) => entry.sessionId === jobB.sessionId), shellCwd: enterCommand?.cwd,
    toolSteps: records.filter((record) => record.kind === "model.request" && record.label === "enter").map((record) => [record.step, record.tool, record.available]) });
  hooksBefore = hooks().length;
  await push(jobB, "SPIKE:exit", { request: "relocate", destination: fixture });
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId), "b exit turn Stop", 90000);
  await delay(1500);
  const listingB2 = await agentsJSON("b-after-exit");
  const exitCommand = commands().find((record) => record.label === "exit");
  trace("exit.outcome", { session: jobB.sessionId, listing: listingB2.find((entry) => entry.sessionId === jobB.sessionId), shellCwd: exitCommand?.cwd, newHooks: hooksSince(hooksBefore),
    ack: channels().filter((record) => record.phase === "ack").at(-1), toolSteps: records.filter((record) => record.kind === "model.request" && record.label === "exit").map((record) => [record.step, record.tool, record.available]) });

  // Scenario 4: a request pushed while a turn is running waits for that turn.
  trace("scenario", { name: "busy-delivery" });
  hooksBefore = hooks().length;
  await push(jobA, "SPIKE:hold hold=8000", { request: "busy" });
  await waitFor(() => commands().some((record) => record.label === "hold" && record.phase === "start"), "hold started", 60000);
  const pushedAt = Date.now();
  await push(jobA, `SPIKE:relocate cwd=${other}`, { request: "relocate", destination: other });
  await waitFor(() => commands().some((record) => record.label === "hold" && record.phase === "end"), "hold ended", 60000);
  const holdEnded = Date.now();
  await waitFor(() => records.some((record) => record.kind === "model.request" && record.label === "relocate" && record.receiptTime > pushedAt && record.step === 3), "queued relocation turn finished", 90000);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === jobA.sessionId), "busy turns Stop", 90000);
  const relocateRequests = records.filter((record) => record.kind === "model.request" && record.label === "relocate" && record.receiptTime > pushedAt);
  const stopsDuringBusy = hooks().slice(hooksBefore).filter((record) => record.event === "Stop" && record.payload.session_id === jobA.sessionId).length;
  trace("busy.outcome", { pushedDuringHoldAt: pushedAt, holdEndedAt: holdEnded, firstRelocateRequestAt: relocateRequests[0]?.receiptTime, deliveredAfterHold: (relocateRequests[0]?.receiptTime ?? 0) > holdEnded, stopsDuringBusy,
    newHooks: hooksSince(hooksBefore), toolSteps: relocateRequests.map((record) => [record.step, record.tool, record.available]) });

  // Scenario 5: a background job keeps running across a relocation.
  trace("scenario", { name: "background-job" });
  hooksBefore = hooks().length;
  await push(jobB, "SPIKE:background hold=20000", { request: "background" });
  await waitFor(() => commands().some((record) => record.label === "background" && record.phase === "start"), "background job started", 60000);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId), "background turn Stop", 90000);
  const backgroundHooks = hooks().length;
  await push(jobB, `SPIKE:relocate cwd=${other}`, { request: "relocate", destination: other });
  await waitFor(() => hooks().slice(backgroundHooks).some((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId), "b relocation with background job Stop", 90000);
  const backgroundEnded = commands().some((record) => record.label === "background" && record.phase === "end");
  const listingB3 = await agentsJSON("b-relocated-with-background-job");
  trace("background.outcome", { session: jobB.sessionId, backgroundJobEndedBeforeRelocation: backgroundEnded, listing: listingB3.find((entry) => entry.sessionId === jobB.sessionId), newHooks: hooksSince(backgroundHooks),
    toolSteps: records.filter((record) => record.kind === "model.request" && record.label === "relocate" && record.receipt > backgroundHooks).map((record) => [record.step, record.tool, record.available]) });
  await waitFor(() => commands().some((record) => record.label === "background" && record.phase === "end"), "background job ended", 60000);

  // Scenario 6: a session already isolated by EnterWorktree asked to enter a
  // third linked Worktree outside `.claude/worktrees/`.
  trace("scenario", { name: "relocate-isolated-to-linked" });
  hooksBefore = hooks().length;
  await push(jobB, `SPIKE:relocate cwd=${third}`, { request: "relocate", destination: third });
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId), "b third relocation turn Stop", 90000);
  await delay(1500);
  const listingB4 = await agentsJSON("b-after-third-relocate");
  trace("relocate-isolated.outcome", { session: jobB.sessionId, listing: listingB4.find((entry) => entry.sessionId === jobB.sessionId), shellCwd: commands().filter((record) => record.label === "relocate").at(-1)?.cwd,
    newHooks: hooksSince(hooksBefore), worktreeOutcomes: records.filter((record) => record.kind === "model.request" && record.label === "relocate").at(-1)?.worktreeOutcomes });

  snapshot("before-exit");
  for (const terminal of terminals) terminal.child.stdin.write("/exit\r");
  await waitFor(() => terminals.every((terminal) => terminal.exited), "terminals exited", 30000).catch((error) => trace("terminal.exit-timeout", { error: String(error) }));
  await delay(2000);
  trace("channel.exit", { events: channels().filter((record) => record.phase === "stdin-closed").length, sessionEnds: hooks().filter((record) => record.event === "SessionEnd").map((record) => [record.payload.session_id, record.payload.reason]) });
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const terminal of terminals) {
    // Screen text is fixture-only but stays out of the retained trace unless asked for.
    if (process.env.SPIKE_DEBUG_TERMINAL === "1") writeFileSync(path.join(root, `terminal-${terminal.name}.txt`), terminal.output);
    if (!terminal.exited) { try { terminal.child.kill("SIGTERM"); } catch {} }
  }
  await delay(1000);
  for (const entry of claudeProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
