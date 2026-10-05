// Live Lead and Worker run for Issue #479: can a Claude Code Lead run its
// Workers as root `claude --bg` sessions, each in its own Issue Worktree, and
// how do they coordinate through cross-session messaging?
//
// A headless `claude -p` Lead in the fixture's main checkout dispatches
// Workers from its own shell with `cd <worktree> && claude --bg`, and Lead
// and Workers message each other with SendMessage. Drives a pinned Claude
// Code binary against a loopback Messages API fixture, with an isolated
// configuration directory, XDG directories and messaging-socket directory,
// so no fixture session can list or message the operator's sessions and no
// operator session can reach the fixture's. Every hook event `dashpot
// integrate claude-code` subscribes goes to this checkout's real publisher;
// the sessions' shells run this checkout's `dashpot work` commands; between
// steps the runner records `dashpot --json`, `dashpot worktree check --json`,
// `claude agents --json` and the fixture's processes. The trace is metadata
// only: prompts, transcripts and message bodies stay out, apart from the
// fixture's own `SPIKE:` labels. The verifier checks the trace against the
// findings.
//
// Usage: node run.mjs <absolute claude binary> [expected version]
// Launch it detached with `setsid -f`, outside every harness session.
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { spawn, spawnSync, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-479-"));
// The messaging sockets live in `$XDG_RUNTIME_DIR/cc-socks/<pid>.sock` unless
// that path is longer than a socket path may be, when Claude Code falls back
// to the shared `/tmp/cc-socks-<uid>/`. A short private directory keeps the
// fixture's sockets apart from the operator's.
const runtime = mkdtempSync("/tmp/dp479-");
console.log(`Isolated fixture: ${root} (runtime ${runtime})`);
const fixture = path.join(root, "repository");
const worktree = (name) => path.join(root, "repository.worktrees", name);
const [A, B, C, P, Q, R, S, Z] = ["a", "b", "c", "p", "q", "r", "s", "z"].map(worktree);
const gates = path.join(root, "gates");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(runtime, "$RUNTIME").replaceAll(here, "$EXPERIMENT")
  .replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.287";
const dashpot = path.join(checkout, ".venv", "bin", "dashpot");
const publisher = path.join(checkout, ".venv", "bin", "dashpot-claude-code-hook");
const python = path.join(checkout, ".venv", "bin", "python");
const uid = os.userInfo().uid;

// A harness session above the runner would be the host Dashpot finds for any
// fixture process it does not recognise, and would collect the fixture's
// hook records, so the runner refuses to start below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || entry.comm.startsWith("codex") || entry.comm === "opencode"
  || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
for (const key of ["CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CODEX_THREAD_ID"]) assert(!process.env[key], `Run this from a scrubbed environment: ${key} is set`);
const launcherDirectory = path.join(root, "bin");
mkdirSync(launcherDirectory);
const launcher = path.join(launcherDirectory, "claude");
symlinkSync(binary, launcher);
const env = {
  PATH: `${launcherDirectory}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  XDG_RUNTIME_DIR: runtime,
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
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_PUBLISHER: publisher,
  SPIKE_GATES: gates,
};
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Local Issue Markdown Project with one Issue per session that binds work.
// Issue 5 is the Lead's, issue 8 the second Lead's.
const issueCount = 8;
mkdirSync(path.join(fixture, ".dashpot"), { recursive: true });
mkdirSync(path.join(fixture, "issues"), { recursive: true });
writeFileSync(path.join(fixture, ".dashpot", "config.json"), JSON.stringify({ projectId: "project:fixture", displayLabel: "Fixture", repositoryId: "repository:fixture", issueSource: { kind: "markdown", path: "issues" } }));
for (let number = 1; number <= issueCount; number++) {
  const reference = `issue-${number}`;
  const front = { id: `I_fixture_${number}`, number, reference, state: "open", stateReason: null, labels: [], assignees: [], author: "fixture",
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${reference}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
}
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.claude/\n/.dashpot/state/\n");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const [name, dir] of [["a", A], ["b", B], ["c", C], ["p", P], ["q", Q], ["r", R], ["s", S], ["z", Z]]) git("worktree", "add", "-b", `issue-${name}`, dir);

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
  trace(url.pathname === "/hook" ? "hook" : "command", record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// Settings files passed with `--settings`: the Lead-link stamp through a
// settings `env`, background isolation turned off, and the allow rules that
// let an asking Worker run the fixture's own commands.
const settingsFile = (name, value) => { const file = path.join(root, `settings-${name}.json`); writeFileSync(file, JSON.stringify(value)); return file; };
// Synthetic credential markers only: a name containing TOKEN and a neutral
// one, never a real credential.
const settingsA = settingsFile("a", { env: { DASHPOT_LEAD_SETTINGS: "settings-a", DASHPOT_479_SETTINGS_TOKEN: "synthetic-settings-a" } });
const settingsB = settingsFile("b", { worktree: { bgIsolation: "none" }, env: { DASHPOT_LEAD_SETTINGS: "settings-b" } });
const settingsAsk = settingsFile("ask", { permissions: { allow: ["Bash(node:*)"] } });
// The second Lead's dispatch `cd`s into Worktrees outside its own checkout, so
// they are added directories too; run 1 found `cd <worktree> && claude --bg`
// denied in dontAsk mode without them.
const settingsLead2 = settingsFile("lead2", { permissions: { allow: ["Bash(node:*)", "Bash(cd:*)", "Bash(claude:*)", "SendMessage", "ListAgents"],
  additionalDirectories: [R, S] } });
const settingsDontAsk = settingsFile("dontask", { permissions: { allow: ["Bash(node:*)", "SendMessage", "ListAgents"] } });
const sessionIdB = randomUUID();

// The fixture model. A turn's script is named by the latest `SPIKE:<label>`
// in a user or system text message, whoever wrote it: the runner, a Lead's dispatch,
// or another session's message. Each tool result after that message advances
// the script by a step. A later user text with no label (a notice) leaves the
// finished script finished, so it is answered with plain text.
const commandScript = path.join(here, "command.mjs");
const bash = (command, extra = {}) => ({ tool: "Bash", input: { command, description: "Fixture step", ...extra } });
const report = (label, hold = 200) => bash(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => bash(`node ${commandScript} ${label} -- work ${args.join(" ")}`);
const hold = (label, gate) => bash(`node ${commandScript} ${label} wait ${gate}`, { timeout: 600000 });
const send = (to, message, extra = {}) => ({ tool: "SendMessage", input: { to, summary: "Fixture message", message, ...extra } });
const listAgents = () => ({ tool: "ListAgents", input: {} });
const sequences = {};
const textParts = (content) => typeof content === "string" ? [content] : (content ?? []).filter((part) => part.type === "text").map((part) => part.text ?? "");
const labelsIn = (text) => [...text.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]);
// How a text reached the model: its labels and the harness's framing tags,
// with only the sender attributes of each tag, never its body.
const framing = (text) => ({
  labels: labelsIn(text),
  tags: [...new Set([...text.matchAll(/<([a-z][a-z0-9_-]*)[\s>]/g)].map((match) => match[1]))],
  attributes: [...text.matchAll(/<([a-z][a-z0-9_-]*)((?:\s+[a-z-]+="[^"]*")+)\s*>/g)].map((match) => ({ tag: match[1],
    ...Object.fromEntries([...match[2].matchAll(/([a-z-]+)="([^"]*)"/g)].filter(([, key]) => /^(from|from-name|from-mode|from-session|from-plugin|hop-chain|state|kind|session|name|status)$/.test(key)).map(([, key, value]) => [key, value])) })),
  taskNotification: text.includes("<task-notification>"),
  length: text.length,
});
const systemText = (system) => typeof system === "string" ? system : (system ?? []).map((part) => part.text ?? "").join("\n");
// What the system prompt says to a background session, as presence only.
const systemDigest = (system) => {
  const text = systemText(system);
  const start = text.indexOf("# Background Session");
  const section = start < 0 ? "" : text.slice(start, (text.indexOf("\n# ", start + 5) + 1 || text.length + 1) - 1);
  return { backgroundSession: start >= 0, sectionMentionsEnterWorktree: section.includes("EnterWorktree"),
    anywhereMentionsEnterWorktree: text.includes("EnterWorktree"), askBeforeCommitting: section.includes("ask before committing"),
    commitWithoutAsking: section.includes("you don't need to ask"), jobDirTmp: section.includes("CLAUDE_JOB_DIR"), length: text.length };
};
const schemaRecorded = new Set();
const seenLabels = {};
const injected = {};
const labelSeen = new Set();
const modelRequests = (label) => records.filter((record) => record.kind === "model.request" && record.label === label);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (url.pathname.endsWith("/count_tokens")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ input_tokens: 100 }));
    return;
  }
  if (!url.pathname.endsWith("/messages")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ type: "error", error: { type: "not_found_error", message: "fixture" } }));
    return;
  }
  const messages = payload.messages ?? [];
  const tools = payload.tools ?? [];
  const toolNames = tools.map((tool) => tool.name);
  let trigger = -1;
  messages.forEach((message, index) => { if (message.role !== "assistant" && labelsIn(textParts(message.content).join("\n")).length) trigger = index; });
  const toolResultsFrom = (start) => messages.slice(start).filter((message) => message.role === "user")
    .reduce((count, message) => count + (Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result").length : 0), 0);
  let label = trigger >= 0 ? labelsIn(textParts(messages[trigger].content).join("\n")).at(-1) : null;
  let done = toolResultsFrom(trigger + 1);
  // Where each label sits: a message that arrives mid-turn comes as a
  // `system`-role message after the tool result, not as a user text, so
  // both roles name a script. A label that first appears anywhere but as
  // the latest labelled message is an injected message: its script starts
  // at the request where it first appears.
  const labelPositions = messages.flatMap((message, index) => (typeof message.content === "string" ? [{ type: "string", text: message.content }] : (message.content ?? []))
    .flatMap((part, partIndex) => labelsIn(JSON.stringify(part)).map((found) => ({ label: found, index, role: message.role, part: part.type, partIndex }))));
  const session = req.headers["x-claude-code-session-id"] ?? "none";
  const known = (seenLabels[session] ??= new Set());
  if (payload.stream) {
    for (const position of labelPositions) {
      if (known.has(position.label)) continue;
      known.add(position.label);
      // A Lead's own dispatch commands name its Workers' labels; only a user
      // or system message can carry a label that is meant for this session.
      if (position.label !== label && position.role !== "assistant") (injected[session] ??= []).push({ label: position.label, at: messages.length, position });
    }
  }
  const latestInjected = (injected[session] ?? []).filter((entry) => entry.at > trigger && labelPositions.some((position) => position.label === entry.label)).at(-1);
  if (latestInjected) { label = latestInjected.label; done = toolResultsFrom(latestInjected.at); }
  const sequence = (label && sequences[label]) || null;
  const step = sequence?.[done] ?? null;
  const available = step ? toolNames.includes(step.tool) : null;
  // What arrived since the model last answered: new user texts and the
  // results of its last tool calls.
  let lastAssistant = -1;
  messages.forEach((message, index) => { if (message.role === "assistant") lastAssistant = index; });
  const fresh = messages.slice(lastAssistant + 1).filter((message) => message.role !== "assistant");
  const uses = new Map(messages.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_use") : []).map((use) => [use.id, use.name]));
  const arrivals = fresh.flatMap((message) => textParts(message.content)).filter((text) => text.trim()).map(framing);
  const results = fresh.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : [])
    .map((part) => ({ tool: uses.get(part.tool_use_id) ?? null, isError: part.is_error ?? null,
      text: retained(typeof part.content === "string" ? part.content : (part.content ?? []).map((item) => item.text ?? "").join(" ")).slice(0, 800) }));
  for (const name of ["SendMessage", "ListAgents"]) {
    const tool = tools.find((entry) => entry.name === name);
    if (tool && !schemaRecorded.has(name)) {
      schemaRecorded.add(name);
      trace("tool.schema", { name, properties: Object.keys(tool.input_schema?.properties ?? {}), required: tool.input_schema?.required ?? [] });
    }
  }
  const first = label && !labelSeen.has(label) && done === 0;
  if (first) labelSeen.add(label);
  // Every label anywhere in the conversation, and the part types of what
  // arrived, so a message injected somewhere other than a fresh text part
  // still shows where it went.
  const labelsAnywhere = [...new Set(labelsIn(JSON.stringify(messages)))];
  const freshParts = fresh.map((message) => typeof message.content === "string" ? ["string"] : (message.content ?? []).map((part) => part.type));
  trace("model.request", { label, step: done, tool: step?.tool ?? null, available, stream: Boolean(payload.stream),
    sessionHeader: req.headers["x-claude-code-session-id"] ?? null, arrivals, results, labelsAnywhere, freshParts, messageCount: messages.length,
    injected: latestInjected ? { label: latestInjected.label, at: latestInjected.at, position: latestInjected.position } : undefined,
    labelPositions: labelPositions.filter((position) => position.index >= trigger - 1),
    system: first || !payload.stream ? systemDigest(payload.system) : undefined,
    tools: first ? toolNames : undefined });
  const final = "Fixture complete.";
  const usage = { input_tokens: 10, output_tokens: 1 };
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [{ type: "text", text: final }],
      stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage } });
  if (step && available) {
    sse("content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label}_${records.length}`, name: step.tool, input: {} } });
    sse("content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(step.input) } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { ...usage, output_tokens: 20 } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: step ? "Fixture tool unavailable." : final } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { ...usage, output_tokens: 4 } });
  }
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// The subscriptions `dashpot integrate claude-code` installs, each publishing,
// and the extra events the run watches without publishing.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import CLAUDE_CODE as c; print(json.dumps({'events': c.events, 'matched': c.matched_events}))"],
  { encoding: "utf8", env: { ...env, PATH: "/usr/bin:/bin" } }));
const handler = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")}`, timeout: 15 };
const watcher = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")} --trace-only`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
const traceOnly = { events: ["Notification", "PermissionRequest"], matched: [["PostToolUse", "SendMessage|ListAgents"]] };
for (const event of traceOnly.events) (subscriptions[event] ??= []).push({ hooks: [watcher] });
for (const [event, matcher] of traceOnly.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [watcher] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
// Pre-accept onboarding, trust and the bypass disclaimer so nothing prompts at start.
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: Object.fromEntries([fixture, A, B, C, P, Q, R, S, Z].map((dir) => [dir, { hasTrustDialogAccepted: true, allowedTools: [] }])),
}, null, 2));

// Runner helpers.
const bypass = ["--dangerously-skip-permissions", "--model", "fixture-model"];
const hooks = () => records.filter((record) => record.kind === "hook");
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const mark = () => records.length;
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
// Waits that are themselves the measurement record a timeout, not a failure.
const settle = async (predicate, label, timeout) => {
  const started = Date.now();
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true, ms: Date.now() - started }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const open = (gate) => { writeFileSync(path.join(gates, gate), ""); trace("gate", { gate }); };
const sessionHooks = (session, event, since = 0) => hooks().filter((record) => record.receipt > since && record.payload.session_id === session && record.event === event && !record.payload.agent_id);
const stopsOf = (session) => sessionHooks(session, "Stop").length;
const seenPids = new Set();
// Every process whose environment names the fixture configuration, so the
// operator's own sessions are never observed or signalled.
const probeKeys = ["CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_KIND", "CLAUDE_JOB_DIR",
  "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_BG_BACKEND", "CLAUDE_CODE_SESSION_NAME", "DASHPOT_LEAD", "DASHPOT_LEAD_SETTINGS", "SPIKE_STAMP",
  "DASHPOT_479_MARKER", "DASHPOT_479_TOKEN", "DASHPOT_479_SETTINGS_TOKEN", "DASHPOT_479_LEAD_ENV_TOKEN", "DASHPOT_479_LEAD2_ENV_TOKEN"];
const fixtureProcesses = (withEnv = false) => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CLAUDE_CONFIG_DIR=${env.CLAUDE_CONFIG_DIR}`)) continue;
    try {
      const entry = describe(Number(name));
      seenPids.add(entry.pid);
      if (withEnv) entry.env = Object.fromEntries(environ.split("\0").map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]).filter(([key]) => probeKeys.includes(key)));
      found.push(entry);
    } catch {}
  }
  return found;
};
const processes = (label) => trace("processes", { label, processes: fixtureProcesses(true).filter((entry) => !["node", "bash", "sh"].includes(entry.comm) || entry.cmdline.includes(" --bg")) });
const claude = async (args, label, timeout = 30000, cwd = fixture) => {
  const child = spawn(launcher, args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  let agents;
  if (args[0] === "agents") {
    try {
      agents = JSON.parse(stdout).map((entry) => ({ keys: Object.keys(entry),
        ...Object.fromEntries(["id", "kind", "name", "pid", "sessionId", "state", "status", "waitingFor", "cwd", "startedAt"].filter((key) => key in entry).map((key) => [key, entry[key]])) }));
    } catch { agents = null; }
  }
  trace("action.claude", { label, args, cwd, status, signal, agents, stdout: agents === undefined ? retained(stdout).slice(-600) : undefined, stderr: retained(stderr).slice(-600) });
  return { status, stdout, stderr, agents };
};
const agents = (label, extra = []) => claude(["agents", "--json", ...extra], label);
// `dashpot worktree check --json`, run from the main checkout.
const check = (dir) => {
  const ran = spawnSync(dashpot, ["worktree", "check", ...(dir ? [dir] : []), "--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  let parsed = null;
  try { parsed = JSON.parse(ran.stdout); } catch {}
  if (!parsed) return { status: ran.status, stderr: retained(ran.stderr ?? "").slice(-400) };
  const summarize = (item) => ({ path: item.path, removable: item.removable,
    blockers: (item.obstacles ?? []).map((obstacle) => ({ kind: obstacle.kind, session: obstacle.detail?.match(/session ([0-9a-f-]{36})/)?.[1] ?? null,
      pids: obstacle.kind === "process" ? [...(obstacle.detail ?? "").matchAll(/pid (\d+)/g)].map((match) => Number(match[1])) : undefined,
      detail: retained(obstacle.detail ?? "").slice(0, 400) })) });
  return { status: ran.status, keys: Object.keys(parsed), ...(Array.isArray(parsed.worktrees) ? { worktrees: parsed.worktrees.map(summarize) } : summarize(parsed)) };
};
const checks = (label, dirs = { a: A, b: B, c: C }) => trace("checks", { label, ...Object.fromEntries(Object.entries(dirs).map(([name, dir]) => [name, check(dir)])) });
// Every hook record Dashpot holds for a session, in each checkout's store.
const stores = [["main", fixture], ["a", A], ["b", B], ["c", C], ["p", P], ["q", Q], ["r", R], ["s", S], ["z", Z]];
const storedSession = (session) => stores.flatMap(([name, dir]) => {
  const directory = path.join(dir, ".dashpot", "state", "sessions");
  let names = [];
  try { names = readdirSync(directory).filter((file) => file.endsWith(".json")); } catch { return []; }
  return names.flatMap((file) => {
    try {
      const record = JSON.parse(readFileSync(path.join(directory, file), "utf8"));
      if (record.sessionId !== session) return [];
      return [{ store: name, event: record.event, state: record.state, cwd: retained(record.cwd ?? ""), liveSubagents: record.liveSubagents ?? null }];
    } catch (error) { return [{ store: name, file, error: String(error).slice(0, 200) }]; }
  });
});
const stored = (label, sessions) => trace("stored", { label, sessions: Object.fromEntries(Object.entries(sessions).filter(([, id]) => id).map(([name, id]) => [name, storedSession(id)])) });
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label) => {
  let snapshot = null;
  let error = null;
  try { snapshot = JSON.parse(execFileSync(dashpot, ["--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 })); } catch (failure) { error = String(failure).slice(0, 500); }
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((project) => project.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: retained(message).slice(0, 300) }));
  return trace("observation", { label, error, runs, diagnostics });
};
// The shared directories the operator's own sessions use: the run records
// which entries appeared or went, relative to those present when it started.
const listDir = (dir) => { try { return readdirSync(dir).sort(); } catch { return []; } };
const daemonRoot = `/tmp/cc-daemon-${uid}`;
const socksRoot = `/tmp/cc-socks-${uid}`;
const expectedDaemonEntry = createHash("sha256").update(path.resolve(env.CLAUDE_CONFIG_DIR)).digest("hex").slice(0, 8);
const baseline = { daemon: listDir(daemonRoot), socks: listDir(socksRoot) };
const sharedDirectories = (label) => {
  const daemon = listDir(daemonRoot);
  const socks = listDir(socksRoot);
  return trace("shared.directories", { label,
    daemon: { preexisting: baseline.daemon.length, preexistingKept: baseline.daemon.every((name) => daemon.includes(name)),
      added: daemon.filter((name) => !baseline.daemon.includes(name)), expectedEntry: expectedDaemonEntry, expectedPreexisting: baseline.daemon.includes(expectedDaemonEntry) },
    socks: { preexisting: baseline.socks.length, added: socks.filter((name) => !baseline.socks.includes(name)).length,
      addedByFixture: socks.filter((name) => !baseline.socks.includes(name) && seenPids.has(Number.parseInt(name, 10))) },
    fixtureSockets: listDir(path.join(runtime, "cc-socks")),
    fixtureSessionFiles: listDir(path.join(env.CLAUDE_CONFIG_DIR, "sessions")).filter((name) => name.endsWith(".json")) });
};

// A headless Lead: one `claude -p` process taking its user turns as
// stream-json on stdin. Its stdout's message kinds are kept, never content.
const leadClient = async (name, cwd, args, extraEnv = {}) => {
  const child = spawn(launcher, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--name", name, ...args],
    { cwd, env: { ...env, ...extraEnv }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, exited: null };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      let message;
      try { message = JSON.parse(line); } catch { continue; }
      if (message.session_id && !state.session) state.session = message.session_id;
      if (message.type === "stream_event") continue;
      const content = message.message?.content;
      // The harness's own fields for holds, denials, notices, tasks and queued
      // commands; never message content.
      const kept = ["state", "lane", "from_name", "cause", "outcome", "tool_name", "decision_reason_type", "level", "is_backgrounded", "task_type", "queued_turn_count", "terminal_reason"];
      trace("lead.stream", { lead: name, type: message.type, subtype: message.subtype ?? null, keys: Object.keys(message),
        texts: message.type === "user" && Array.isArray(content) ? content.filter((part) => part.type === "text").map((part) => framing(part.text ?? "")) : undefined,
        status: message.type === "system" ? message.status ?? undefined : undefined,
        fields: Object.fromEntries(kept.filter((key) => key in message && (typeof message[key] !== "object" || message[key] === null)).map((key) => [key, message[key]])),
        from: message.subtype === "peer_message_hold" ? retained(String(message.from ?? "")) : undefined,
        notice: message.subtype === "informational" ? retained(String(message.content ?? "")).slice(0, 400) : undefined });
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, cwd, pid: child.pid, args });
  state.send = (label) => {
    child.stdin.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text: `SPIKE:${label}` }] } }) + "\n");
    trace("turn.sent", { lead: name, label });
  };
  state.turn = async (label) => {
    const before = state.session ? stopsOf(state.session) : 0;
    state.send(label);
    await waitFor(() => state.session && stopsOf(state.session) > before, `${name} ${label} Stop`, 90000);
    trace("turn", { lead: name, label, session: state.session });
  };
  return state;
};
// Find a dispatched Worker in the listing once its first shell has reported.
const findWorker = async (name, label) => {
  await settle(() => command(label, "start"), `${name} first shell`, 90000);
  const listed = await agents(`${name}-listed`);
  return trace("worker", { ...entryOf(listed, name), shellSession: command(label, "start")?.env.CLAUDE_CODE_SESSION_ID ?? null });
};
// A Worker's listing entry, whose own `kind` is kept as `agentKind` so that
// it does not replace the record's.
const entryOf = (listing, name) => {
  const { kind: agentKind = null, ...entry } = listing.agents?.find((candidate) => candidate.name === name) ?? {};
  return { ...entry, name, agentKind };
};

const sha = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
let lead = null;
let lead2 = null;
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    subscriptions: integration, traceOnly,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key.startsWith("XDG_RUNTIME") || key === "ANTHROPIC_BASE_URL")),
    fixture, worktrees: { a: A, b: B, c: C, p: P, q: Q, r: R, s: S, z: Z },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    worktreeDirty: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean),
    experimentSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"].map((file) => [file, sha(path.join(here, file))])),
    sourceSHA256: Object.fromEntries(["sessions/harnesses.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/work.py", "sessions/work_reconciliation.py",
      "sessions/processes.py", "repository/cleanup/obstacles.py", "hook.py"].map((file) => [`src/dashpot/${file}`, sha(path.join(checkout, "src", "dashpot", file))])) });
  sharedDirectories("baseline");

  // Scenario 0: the Lead binds its own Issue, and the fixture's messaging
  // is shown to be isolated before any message is sent.
  trace("scenario", { name: "lead-and-isolation" });
  // The Lead's own process carries a marker of its own, which reaches a
  // Worker only if the supervisor, first started from the Lead's shell,
  // passes its environment on.
  lead = await leadClient("lead", fixture, bypass, { DASHPOT_479_LEAD_ENV_TOKEN: "synthetic-lead-process" });
  sequences["lead-identify"] = [report("lead-shell"), work("lead-start", "start", "issue-5"), listAgents()];
  await lead.turn("lead-identify");
  const leadShell = command("lead-shell", "start");
  const leadSocket = leadShell.env.CLAUDE_CODE_MESSAGING_SOCKET;
  const listing = modelRequests("lead-identify").flatMap((record) => record.results).find((result) => result.tool === "ListAgents");
  fixtureProcesses();
  const shared = sharedDirectories("lead-started");
  const isolation = {
    leadSocketPrivate: Boolean(leadSocket) && leadSocket.startsWith(`${runtime}/`),
    noFixtureSocketInShared: shared.socks.addedByFixture.length === 0,
    fixtureSessionFilesOnly: shared.fixtureSessionFiles.every((file) => seenPids.has(Number.parseInt(file, 10))),
    daemonEntryDistinct: !baseline.daemon.includes(expectedDaemonEntry),
    listingFixtureOnly: Boolean(listing) && !/\$HOME|\$CHECKOUT/.test(listing.text),
  };
  trace("isolation", { ...isolation, leadSocket, listing: listing?.text ?? null });
  assert(Object.values(isolation).every(Boolean), `messaging is not isolated: ${JSON.stringify(isolation)}`);
  observe("lead-bound");

  // Every script is registered before the first dispatch, since a session's
  // message can reach its peer before the runner reaches that scenario.
  const L = lead.session;
  const dispatchAsk = (dir, name, label) => bash(`(cd ${dir} && claude --bg --name ${name} --permission-mode manual --model fixture-model --settings ${settingsAsk} "SPIKE:${label}")`);
  Object.assign(sequences, {
    "lead-dispatch-z": [bash(`cd ${Z} && DASHPOT_LEAD=shell-z:${L} DASHPOT_479_MARKER=shell-z DASHPOT_479_TOKEN=synthetic-shell-z SPIKE_STAMP=z claude --bg --name worker-z ${bypass.join(" ")} "SPIKE:wz-start"`)],
    "wz-start": [report("wz-shell")],
    "lead-hears-a-name": [report("lead-on-a-name")],
    "lead-hears-b-uds": [report("lead-on-b-uds")],
    "lead-busy": [hold("lead-busy", "lead-busy-go")],
    "lead-notify-b": [send("worker-b", "SPIKE:wb-steer", { notify_when_idle: true })],
    "wb-steer": [report("wb-steered"), hold("wb-steer-hold", "wb-steer-go")],
    "lead-mid-b": [send("worker-b", "SPIKE:wb-mid")],
    "wb-mid": [report("wb-mid-seen")],
    "lead-review-a": [send("worker-a", "SPIKE:wa-review")],
    "wa-review": [{ tool: "Agent", input: { description: "Fixture reviewer", prompt: "SPIKE:wa-reviewer", subagent_type: "general-purpose", run_in_background: true } }],
    "wa-reviewer": [hold("reviewer-hold", "reviewer-go")],
    "lead-commit-a": [send("worker-a", "SPIKE:wa-commit")],
    "wa-commit": [bash("git add fixture-a.txt && git -c user.name=Fixture -c user.email=fixture@example.invalid commit -m 'Fixture commit'"), report("wa-committed")],
    "lead-finish-a": [send("worker-a", "SPIKE:wa-finish")],
    "wa-finish": [work("wa-stop", "stop"), work("wa-show-stopped", "show")],
    "lead-dispatch-pq": [dispatchAsk(P, "worker-p", "wp-start"), dispatchAsk(Q, "worker-q", "wq-start")],
    "wp-start": [report("wp-shell"), work("wp-start", "start", "issue-3"), send("lead", "SPIKE:lead-hears-p")],
    "lead-hears-p": [report("lead-on-p")],
    "wq-start": [report("wq-shell"), work("wq-start", "start", "issue-4"), bash(`touch ${path.join(Q, "asked-file")}`)],
    "lead-to-p": [send("worker-p", "SPIKE:wp-msg")],
    "wp-msg": [report("wp-on-msg")],
    "lead2-identify": [report("lead2-shell"), work("lead2-start", "start", "issue-8")],
    // No subshell here, as the evidence note's dispatch line has it: the
    // second Lead's Worktrees are added directories, so its `cd` persists.
    "lead2-dispatch": [
      bash(`cd ${R} && claude --bg --name worker-r --permission-mode auto --model fixture-model "SPIKE:wr-start"`),
      bash(`cd ${S} && claude --bg --name worker-s --permission-mode dontAsk --model fixture-model --settings ${settingsDontAsk} "SPIKE:ws-start"`)],
    "wr-start": [send("lead2", "SPIKE:lead2-hears-r"), report("wr-shell"), work("wr-start", "start", "issue-6")],
    "ws-start": [send("lead2", "SPIKE:lead2-hears-s"), report("ws-shell"), work("ws-start", "start", "issue-7")],
    "lead2-hears-r": [report("lead2-on-r")],
    "lead2-hears-s": [report("lead2-on-s")],
    "lead2-to-rs": [send("worker-r", "SPIKE:wr-msg"), send("worker-s", "SPIKE:ws-msg")],
    "wr-msg": [report("wr-on-msg")],
    "ws-msg": [report("ws-on-msg")],
    "lead-to-s": [send("worker-s", "SPIKE:ws-from-lead")],
    "ws-from-lead": [report("ws-on-lead")],
    "lead-to-b-resumed": [send("worker-b", "SPIKE:wb-resumed")],
    "wb-resumed": [report("wb-resumed-shell"), work("wb-resumed-show", "show")],
  });

  // Scenario 1: dispatch from the Lead's shell. Worker Z's dispatch starts
  // the supervisor from that shell, with Z's stamps; A's and B's find it
  // running. Each carries a Lead-link stamp in its launch environment and
  // A and B another in their `--settings`.
  trace("scenario", { name: "dispatch" });
  await lead.turn("lead-dispatch-z");
  await settle(() => command("wz-shell", "start"), "worker-z first shell", 90000);
  await settle(() => records.some((record) => record.kind === "hook" && record.event === "Stop" && record.env?.CLAUDE_CODE_SESSION_ID === command("wz-shell", "start")?.env.CLAUDE_CODE_SESSION_ID), "worker-z Stop", 30000);
  processes("supervisor-started");
  sequences["lead-dispatch"] = [
    bash(`cd ${A} && DASHPOT_LEAD=shell-a:${L} DASHPOT_479_MARKER=shell-a DASHPOT_479_TOKEN=synthetic-shell-a SPIKE_STAMP=a claude --bg --name worker-a ${bypass.join(" ")} --settings ${settingsA} "SPIKE:wa-start"`),
    bash(`(cd ${B} && DASHPOT_LEAD=shell-b:${L} DASHPOT_479_MARKER=shell-b DASHPOT_479_TOKEN=synthetic-shell-b SPIKE_STAMP=b claude --bg --name worker-b --session-id ${sessionIdB} ${bypass.join(" ")} --settings ${settingsB} "SPIKE:wb-start")`),
    report("lead-after-dispatch"), work("lead-show", "show")];
  sequences["wa-start"] = [report("wa-shell"), work("wa-start", "start", "issue-1"), work("wa-show", "show"),
    { tool: "Write", input: { file_path: path.join(A, "fixture-a.txt"), content: "fixture\n" } },
    hold("wa-hold", "wa-send-go"), send("lead", "SPIKE:lead-hears-a-name")];
  sequences["wb-start"] = [report("wb-shell"), work("wb-start", "start", "issue-2"), work("wb-show", "show"),
    hold("wb-hold", "wb-send-go"), send(`uds:${leadSocket}`, "SPIKE:lead-hears-b-uds")];
  await lead.turn("lead-dispatch");
  const wa = await findWorker("worker-a", "wa-shell");
  const wb = await findWorker("worker-b", "wb-shell");
  await settle(() => command("wa-hold", "start") && command("wb-hold", "start"), "both workers bound and holding", 90000);
  await agents("dispatched-cwd-a", ["--cwd", A]);
  processes("dispatched");
  sharedDirectories("dispatched");
  stored("dispatched", { lead: L, a: wa.sessionId, b: wb.sessionId });
  observe("dispatched");

  // Scenario 2: occupancy, each Worker bound in its own Worktree.
  trace("scenario", { name: "occupancy" });
  checks("bound");

  // Scenario 3: Worker to Lead, by name while the Lead is idle.
  trace("scenario", { name: "worker-to-idle-lead" });
  let since = mark();
  open("wa-send-go");
  await settle(() => sessionHooks(wa.sessionId, "PostToolUse", since).some((record) => record.payload.tool_name === "SendMessage"), "worker-a SendMessage", 30000);
  await settle(() => command("lead-on-a-name"), "lead turn from worker-a's message", 45000);
  await settle(() => stopsOf(L) > 0 && sessionHooks(L, "Stop", since).length > 0, "lead Stop after worker-a's message", 30000);
  await delay(2000);
  trace("probe", { label: "idle-lead", leadPrompts: sessionHooks(L, "UserPromptSubmit", since).length, leadStops: sessionHooks(L, "Stop", since).length });

  // Worker B to the Lead by `uds:` address while the Lead is busy in a tool.
  trace("scenario", { name: "worker-to-busy-lead" });
  since = mark();
  lead.send("lead-busy");
  await waitFor(() => command("lead-busy", "start"), "lead busy hold", 60000);
  open("wb-send-go");
  await settle(() => sessionHooks(wb.sessionId, "PostToolUse", since).some((record) => record.payload.tool_name === "SendMessage"), "worker-b SendMessage", 30000);
  await delay(5000);
  trace("probe", { label: "busy-lead-holding", leadRequestsDuringHold: records.filter((record) => record.receipt > since && record.kind === "model.request" && record.label === "lead-busy").length });
  open("lead-busy-go");
  await settle(() => command("lead-on-b-uds"), "lead read worker-b's message", 45000);
  await settle(() => sessionHooks(L, "Stop", since).length >= 1, "lead Stop after busy turn", 30000);
  await delay(3000);
  trace("probe", { label: "busy-lead", leadPrompts: sessionHooks(L, "UserPromptSubmit", since).length, leadStops: sessionHooks(L, "Stop", since).length });
  await agents("after-worker-messages");

  // Scenario 4: Lead to Worker B with notify_when_idle, then a message
  // mid-turn; the notice should follow B's Stop.
  trace("scenario", { name: "lead-to-worker" });
  since = mark();
  await lead.turn("lead-notify-b");
  await settle(() => command("wb-steer-hold", "start"), "worker-b steered turn holding", 45000);
  await lead.turn("lead-mid-b");
  await delay(3000);
  const bStopsBefore = stopsOf(wb.sessionId);
  const leadStopsBefore = stopsOf(L);
  open("wb-steer-go");
  await settle(() => command("wb-mid-seen"), "worker-b read the mid-turn message", 45000);
  await settle(() => stopsOf(wb.sessionId) > bStopsBefore, "worker-b Stop", 45000);
  await settle(() => stopsOf(L) > leadStopsBefore, "lead turn from the idle notice", 60000);
  await delay(3000);
  trace("probe", { label: "notify", bStops: sessionHooks(wb.sessionId, "Stop", since).map((record) => record.receiptTime),
    leadPrompts: sessionHooks(L, "UserPromptSubmit", since).map((record) => record.receiptTime), leadStops: sessionHooks(L, "Stop", since).map((record) => record.receiptTime) });

  // Scenario 2, continued: Worker A's reviewer Sub-agent, then A's own
  // Stop and `work stop`, as a finished but live Worker.
  trace("scenario", { name: "reviewer" });
  since = mark();
  await lead.turn("lead-review-a");
  await settle(() => command("reviewer-hold", "start"), "reviewer holding", 60000);
  await delay(2000);
  stored("reviewer-running", { a: wa.sessionId });
  checks("reviewer-running");
  observe("reviewer-running");
  open("reviewer-go");
  await settle(() => sessionHooks(wa.sessionId, "SubagentStop", since).length > 0 || hooks().some((record) => record.receipt > since && record.event === "SubagentStop" && record.payload.session_id === wa.sessionId), "reviewer SubagentStop", 60000);
  await delay(4000);
  checks("reviewer-finished");

  // Scenario 7: the commit prompt. Worker A, in a Worktree it did not create,
  // commits; the run records any ask, and what the system prompt said.
  trace("scenario", { name: "commit" });
  since = mark();
  await lead.turn("lead-commit-a");
  await settle(() => command("wa-committed"), "worker-a committed", 60000);
  await delay(2000);
  trace("commits", { a: execFileSync("git", ["-C", A, "log", "--format=%s", "-n", "3"], { encoding: "utf8" }).trim().split("\n"),
    asks: hooks().filter((record) => record.receipt > since && ["Notification", "PermissionRequest"].includes(record.event)).map((record) => [record.event, record.payload.session_id === wa.sessionId]) });

  // Scenario 2, finished: Worker A runs `work stop` and stays live.
  trace("scenario", { name: "finished-worker" });
  await lead.turn("lead-finish-a");
  await settle(() => command("wa-show-stopped"), "worker-a work stop", 60000);
  await delay(3000);
  checks("a-work-stopped");
  observe("a-work-stopped");
  await agents("a-work-stopped");

  // Scenario 6: permission classes. P and Q ask for permission (manual mode,
  // with the fixture's own commands allowed); the Lead bypasses.
  trace("scenario", { name: "permission-classes" });
  since = mark();
  await lead.turn("lead-dispatch-pq");
  const wp = await findWorker("worker-p", "wp-shell");
  const wq = await findWorker("worker-q", "wq-shell");
  await settle(() => command("wp-start") && command("wq-start"), "asking workers bound", 60000);
  await settle(() => hooks().some((record) => record.receipt > since && record.payload.session_id === wp.sessionId && (record.event === "PostToolUse" || record.event === "Notification" || record.event === "PermissionRequest")), "worker-p SendMessage or ask", 30000);
  await settle(() => command("lead-on-p"), "lead turn from asking worker-p", 30000);
  await settle(() => hooks().some((record) => record.receipt > since && record.payload.session_id === wq.sessionId && ["Notification", "PermissionRequest"].includes(record.event)), "worker-q ask", 45000);
  await delay(3000);
  await agents("asking-workers");
  stored("asking-workers", { p: wp.sessionId, q: wq.sessionId });
  observe("asking-workers");
  const leadToP = mark();
  await lead.turn("lead-to-p");
  await settle(() => command("wp-on-msg"), "worker-p turn from the bypassing lead's message", 30000);
  await delay(2000);
  await agents("lead-to-asking");
  trace("probe", { label: "permission-classes", pPrompts: sessionHooks(wp.sessionId, "UserPromptSubmit", leadToP).length,
    leadPrompts: sessionHooks(L, "UserPromptSubmit", since).length });

  // Scenario 3b: a second Lead in a prompting class (dontAsk) with Workers
  // in auto and dontAsk modes: messages within one non-bypass class.
  trace("scenario", { name: "prompting-class" });
  lead2 = await leadClient("lead2", fixture, ["--permission-mode", "dontAsk", "--model", "fixture-model", "--settings", settingsLead2], { DASHPOT_479_LEAD2_ENV_TOKEN: "synthetic-lead2-process" });
  await lead2.turn("lead2-identify");
  since = mark();
  await lead2.turn("lead2-dispatch");
  await settle(() => hooks().some((record) => record.receipt > since && record.event === "SessionStart" && record.payload.cwd === R), "worker-r started", 60000);
  await settle(() => hooks().some((record) => record.receipt > since && record.event === "SessionStart" && record.payload.cwd === S), "worker-s started", 60000);
  await settle(() => command("lead2-on-s"), "lead2 turn from worker-s", 45000);
  await settle(() => command("ws-start"), "worker-s bound", 30000);
  await settle(() => command("lead2-on-r"), "lead2 turn from worker-r", 20000);
  await settle(() => command("wr-start"), "worker-r bound", 10000);
  await delay(3000);
  const listedPrompting = await agents("prompting-workers");
  const wr = trace("worker", entryOf(listedPrompting, "worker-r"));
  const ws = trace("worker", entryOf(listedPrompting, "worker-s"));
  await lead2.turn("lead2-to-rs");
  await settle(() => command("ws-on-msg"), "worker-s turn from lead2", 30000);
  await settle(() => command("wr-on-msg"), "worker-r turn from lead2", 10000);
  await lead.turn("lead-to-s");
  await settle(() => command("ws-on-lead"), "worker-s turn from the bypassing lead", 30000);
  await delay(2000);
  await agents("prompting-after-messages");
  stored("prompting", { lead2: lead2.session, r: wr.sessionId, s: ws.sessionId });
  observe("prompting");

  // Scenario 5: `claude stop` ends Worker A; SIGTERM of Worker B's process.
  trace("scenario", { name: "stop" });
  since = mark();
  await claude(["stop", wa.id], "stop-a");
  await settle(() => sessionHooks(wa.sessionId, "SessionEnd", since).length > 0, "worker-a SessionEnd", 30000);
  await delay(3000);
  trace("worker.stop", { worker: "worker-a", hooks: hooks().filter((record) => record.receipt > since && record.payload.session_id === wa.sessionId).map((record) => [record.event, record.payload.reason ?? record.payload.source ?? null]) });
  checks("a-stopped", { a: A });
  observe("a-stopped");
  const bPid = (await agents("before-term")).agents?.find((entry) => entry.name === "worker-b")?.pid;
  since = mark();
  if (bPid && fixtureProcesses().some((entry) => entry.pid === bPid)) {
    process.kill(bPid, "SIGTERM");
    trace("action.kill", { worker: "worker-b", pid: bPid, signal: "SIGTERM" });
  }
  await settle(() => sessionHooks(wb.sessionId, "SessionStart", since).length > 0, "worker-b replaced after SIGTERM", 30000);
  await delay(3000);
  trace("worker.term", { worker: "worker-b", pid: bPid, hooks: hooks().filter((record) => record.receipt > since && record.payload.session_id === wb.sessionId).map((record) => [record.event, record.payload.reason ?? record.payload.source ?? null, record.env?.CLAUDE_PID ?? null]) });
  await agents("after-term", ["--all"]);
  observe("b-terminated");
  processes("b-terminated");
  // The replacement's next turn: whether its shells carry the same stamps,
  // and whether its Orphaned Agent Run continues (ADR 0053).
  await lead.turn("lead-to-b-resumed");
  await settle(() => command("wb-resumed-show"), "worker-b replacement's turn", 45000);
  await delay(2000);
  observe("b-resumed-turn");
  checks("b-resumed-turn", { b: B });
  // A -p Lead drops a held message once the approval deadline passes; wait
  // for worker-p's to go, five minutes after it was held.
  const held = records.find((record) => record.kind === "lead.stream" && record.subtype === "peer_message_hold" && record.fields?.from_name === "worker-p" && record.fields?.state === "held");
  if (held) await settle(() => records.some((record) => record.kind === "lead.stream" && record.subtype === "peer_message_hold" && record.fields?.from_name === "worker-p" && record.fields?.state !== "held"), "lead drops worker-p's held message", Math.max(1000, held.receiptTime + 360000 - Date.now()));
  // And a background Worker past the same deadline: is the Lead's message to
  // worker-p still held, delivered, or gone?
  const pHeld = hooks().find((record) => record.event === "Notification" && record.payload.session_id === wp.sessionId && /approval/.test(record.notification ?? ""));
  if (pHeld) {
    await delay(Math.max(0, pHeld.receiptTime + 330000 - Date.now()));
    await agents("after-hold-deadline");
    trace("probe", { label: "worker-hold-deadline", heldForMs: Date.now() - pHeld.receiptTime, delivered: Boolean(command("wp-on-msg")),
      pHooks: hooks().filter((record) => record.receipt > pHeld.receipt && record.payload.session_id === wp.sessionId).map((record) => [record.event, record.notification ?? null]) });
  }
  console.log(`Scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)).slice(0, 1200) });
  console.log(`Run failed: ${error}`);
} finally {
  // Stop every fixture Worker by id and end the Leads by closing their input;
  // the supervisor and any process left are signalled by the fixture
  // configuration in their environment, never by name.
  const listed = await agents("cleanup", ["--all"]).catch(() => ({ agents: [] }));
  for (const entry of listed.agents ?? []) if (entry.kind === "background" && entry.id && entry.state !== "stopped") await claude(["stop", entry.id], `cleanup-stop-${entry.name}`).catch(() => {});
  for (const client of [lead, lead2]) if (client && !client.exited) client.child.stdin.end();
  await delay(5000);
  if (lead?.session) trace("lead.end", { hooks: hooks().filter((record) => record.payload.session_id === lead.session && record.event === "SessionEnd").map((record) => record.payload.reason ?? null) });
  for (const entry of fixtureProcesses()) {
    trace("cleanup.term", { pid: entry.pid, comm: entry.comm, cmdline: entry.cmdline.slice(0, 120) });
    try { process.kill(entry.pid, "SIGTERM"); } catch {}
  }
  await delay(3000);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  sharedDirectories("cleanup");
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  try { rmSync(runtime, { recursive: true }); } catch {}
  writeFileSync(path.join(root, "done"), "");
}
