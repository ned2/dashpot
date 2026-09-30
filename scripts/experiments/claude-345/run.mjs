// Isolated Claude Code experiment for Issue #345: the 2.1.280–2.1.285 changes
// that touch Dashpot's Claude Code integration. Drives a pinned Claude Code
// binary against a loopback Messages API fixture with an isolated
// configuration directory, records hook, shell, listing, and opener evidence
// as a metadata-only trace, and asserts nothing about outcomes: the
// independent verifier checks the trace against the recorded claims.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-345-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const nested = path.join(fixture, "nested");
// A linked Worktree beside the Repository, where Dashpot creates Issue
// Worktrees, and never trusted in the fixture configuration.
const sibling = path.join(root, "repository.worktrees", "sibling");
// A second Repository with no trust entry and no relation to the first.
const unrelated = path.join(root, "unrelated");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root and this directory by
// placeholder: their absolute paths say nothing about Claude Code and would
// repeat in every ancestry entry.
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.285";

const shims = path.join(root, "bin");
const env = {
  PATH: `${shims}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
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
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, nested, shims, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "Disposable fixture");
git("worktree", "add", "-b", "sibling", sibling);
mkdirSync(unrelated);
execFileSync("git", ["-C", unrelated, "init", "--initial-branch=main"], { env, stdio: "pipe" });

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
for (const name of ["xdg-open", "sensible-browser", "x-www-browser", "www-browser", "gio", "open"]) {
  writeFileSync(path.join(shims, name), `#!/bin/sh\nexec ${process.execPath} ${path.join(here, "opener.mjs")} ${name} "$@"\n`);
  chmodSync(path.join(shims, name), 0o755);
}

// The fixture model: a `SPIKE:<label>` text in the conversation selects a
// fixed tool sequence, and the turn ends once every step has a tool result.
// A request whose system prompt is not the main loop's is traced with its
// opening words so a helper request can be told from a turn.
const commandScript = path.join(here, "command.mjs");
const modelRequests = new Map();
const sse = (res, event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
const report = (label, hold) => ({ tool: "Bash", input: { command: `node ${commandScript} ${label} ${hold ?? 200}`, description: "Report fixture identity" } });
// A child hands its report back with SubagentHandback where the tool is
// offered, as a model following its description would; `child-plain` ends
// with text alone.
const handback = { tool: "SubagentHandback", input: { message: "Fixture report." } };
const delegate = (child, background = false) => () => [{ tool: "Agent", input: { description: `Fixture ${child}`, prompt: `SPIKE:${child}`, subagent_type: "general-purpose", ...(background ? { run_in_background: true } : {}) } }];
const sequences = {
  report: (label) => [report(label.name, label.hold)],
  delegate: delegate("child"),
  "delegate-bg": delegate("child-bg hold=3000", true),
  "delegate-plain": delegate("child-plain"),
  child: (label) => [report(label.name), handback],
  "child-bg": (label) => [report(label.name, label.hold), handback],
  "child-plain": (label) => [report(label.name)],
};
const systemText = (system) => typeof system === "string" ? system : Array.isArray(system) ? system.map((part) => part.text ?? "").join(" ") : "";
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
      const match = part.type === "text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?/);
      if (match) { label = { name: match[1], hold: match[2] }; latestUser = index; }
    }
  });
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  const toolResults = messages.slice(latestUser + 1).reduce((total, message) => total + (Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result").length : 0), 0);
  const sequence = label ? (sequences[label.name] ?? sequences.report)(label) : [];
  const step = sequence[toolResults];
  const count = (modelRequests.get(label?.name ?? "none") ?? 0) + 1;
  modelRequests.set(label?.name ?? "none", count);
  const system = systemText(payload.system);
  if (process.env.SPIKE_DEBUG_REQUESTS === "1") writeFileSync(path.join(root, `request-${records.length}.json`), JSON.stringify(payload, null, 2));
  const lastUser = messages.at(-1);
  const lastText = typeof lastUser?.content === "string" ? lastUser.content : (lastUser?.content ?? []).filter((part) => part.type === "text").map((part) => part.text).join(" ");
  // The auto mode classifier asks for a harm score; the fixture allows every
  // action so the sub-agent under test runs.
  const classifier = /<severity>/.test(lastText) && tools.length === 0;
  trace("model.request", { label: label?.name ?? null, classifier, step: toolResults, tool: step?.tool ?? null, available: step ? tools.includes(step.tool) : null, count, model: payload.model,
    messageCount: messages.length, toolCount: tools.length, maxTokens: payload.max_tokens,
    systemHead: system.slice(0, 90), systemSHA256: createHash("sha256").update(system).digest("hex").slice(0, 12),
    // Only the fixture's own markers: helper prompts are named by their opening words.
    lastUserHead: lastText.includes("SPIKE:") ? undefined : lastText.slice(0, 90),
    // The fixture's own tool results say whether a call ran or was refused.
    toolResultHeads: messages.slice(latestUser + 1).flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : [])
      .map((part) => (typeof part.content === "string" ? part.content : (part.content ?? []).map((item) => item.text ?? "").join(" ")).slice(0, 160)),
    querySource: req.headers["x-claude-code-query-source"] ?? payload.metadata?.query_source ?? undefined });
  if (!payload.stream) {
    // The classifier asks without streaming and stops at `</severity>`, which
    // the API leaves out of the text.
    const content = classifier ? [{ type: "text", text: "<severity>5" }] : [{ type: "text", text: "Fixture complete." }];
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content,
      stop_reason: classifier ? "stop_sequence" : "end_turn", stop_sequence: classifier ? "</severity>" : null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse(res, "message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (step && tools.includes(step.tool)) {
    sse(res, "content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label.name}_${count}`, name: step.tool, input: {} } });
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

// The user-scope settings carry the hooks, as `dashpot integrate` installs them.
const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"];
const settings = {
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
};
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify(settings, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  // Prompt suggestions sit behind a remotely served flag the isolated fixture
  // cannot fetch; the value is read only by sessions given
  // CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF.
  cachedGrowthBookFeatures: { tengu_prompt_suggestion: true },
  // Only the Repository is trusted: `nested` inherits from it, the sibling
  // linked Worktree has no entry.
  projects: { [fixture]: { hasTrustDialogAccepted: true, allowedTools: [] } },
}, null, 2));

const bypass = ["--dangerously-skip-permissions", "--model", "fixture-model"];
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
const hooksSince = (count) => hooks().slice(count).map((record) => ({ event: record.event, session: record.payload.session_id, agentId: record.payload.agent_id ?? null,
  agentType: record.payload.agent_type ?? null, source: record.payload.source ?? null, reason: record.payload.reason ?? null, claudePid: record.env.CLAUDE_PID }));
const commands = () => records.filter((record) => record.kind === "command");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
// SPIKE_ONLY narrows a run to scenarios whose names start with a listed prefix.
const only = (name) => !process.env.SPIKE_ONLY || process.env.SPIKE_ONLY.split(",").some((prefix) => name.startsWith(prefix));
const settle = async (label, predicate, timeout) => { try { return await waitFor(predicate, label, timeout); } catch (error) { trace("wait.timeout", { label, error: String(error) }); return false; } };

// Interactive sessions run on a pseudo-terminal hosted by `script`; only the
// markers the runner waits for are read from the screen.
const terminals = [];
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
// A null in extraEnv removes that variable from the session's environment.
const terminal = (name, args, cwd, extraEnv = {}) => {
  const sessionEnv = { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40", ...extraEnv };
  for (const [key, value] of Object.entries(extraEnv)) if (value === null) delete sessionEnv[key];
  const child = spawn("script", ["-qfec", [binary, ...args].map((arg) => `'${arg.replace(/'/g, "'\\''")}'`).join(" "), "/dev/null"],
    { cwd, env: sessionEnv, stdio: ["pipe", "pipe", "pipe"] });
  const session = { name, child, output: "", exited: null, scriptPid: child.pid };
  child.stdout.on("data", (chunk) => { session.output += stripAnsi(String(chunk)); });
  child.on("exit", (status, signal) => { session.exited = { status, signal }; trace("terminal.exit", { name, status, signal }); });
  terminals.push(session);
  trace("terminal", { name, cwd, args, scriptPid: child.pid, extraEnv: Object.keys(extraEnv) });
  return session;
};
// `script` runs the command through `sh -c`, so the session is its grandchild.
const interactivePid = (session) => {
  const processes = claudeProcesses();
  const shells = processes.filter((entry) => entry.ppid === session.scriptPid).map((entry) => entry.pid);
  return processes.find((entry) => shells.includes(entry.ppid))?.pid ?? null;
};
const closeTerminal = async (session) => {
  if (session.exited) return;
  session.child.stdin.write("/exit\r");
  if (!(await settle(`${session.name} exit`, () => session.exited, 15000))) { session.child.kill("SIGTERM"); await settle(`${session.name} killed`, () => session.exited, 5000); }
};
const subagentPairs = (since, session) => {
  const events = hooks().slice(since).filter((record) => record.payload.session_id === session && /^Subagent/.test(record.event));
  return events.map((record) => ({ event: record.event, agentId: record.payload.agent_id ?? null, agentType: record.payload.agent_type ?? null, at: record.receiptTime }));
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")), fixture, nested, sibling,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "opener.mjs", "verify.mjs"].map((file) => {
      try { return [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")]; } catch { return [file, null]; }
    })) });

  // Scenario 1: foreground and background sub-agents, under bypass and auto
  // permission modes. Dashpot needs every SubagentStart to meet its Stop.
  for (const [mode, args] of [["bypass", bypass], ["auto", ["--permission-mode", "auto", "--model", "fixture-model"]]]) {
    for (const label of ["delegate", "delegate-bg", "delegate-plain"]) {
      const name = `subagent-${mode}-${label}`;
      if (!only(name)) continue;
      trace("scenario", { name });
      const before = hooks().length;
      const requestsBefore = records.length;
      const run = await claude(["-p", `SPIKE:${label}`, "--output-format", "json", ...args], { timeout: 90000 });
      let output = null;
      try { output = JSON.parse(run.stdout); } catch {}
      await delay(1500);
      const session = output?.session_id ?? hooks().slice(before).find((record) => record.event === "SessionStart")?.payload.session_id;
      const sequence = hooks().slice(before).filter((record) => record.payload.session_id === session).map((record) => [record.event, record.payload.agent_id ?? null, record.payload.agent_type ?? null, record.receiptTime]);
      trace("subagent.outcome", { name, mode, label, status: run.status, session, isError: output?.is_error ?? null, numTurns: output?.num_turns ?? null, sequence,
        pairs: subagentPairs(before, session),
        childRequests: records.slice(requestsBefore).filter((record) => record.kind === "model.request" && !record.classifier && record.label?.startsWith("child"))
          .map((record) => ({ step: record.step, tool: record.tool, available: record.available, enforced: /handback-send-enforce/.test(record.lastUserHead ?? "") })),
        stopHookActive: hooks().slice(before).filter((record) => record.event === "SubagentStop" && record.payload.session_id === session).map((record) => record.payload.stop_hook_active ?? null),
        childCommands: commands().filter((record) => record.env.CLAUDE_CODE_SESSION_ID === session).map((record) => [record.label, record.phase, Number(record.env.CLAUDE_PID)]) });
    }
  }

  // Scenario 2: an interactive turn with and without the prompt-suggestion
  // flag, and with it in auto mode; what fires after the main turn's Stop.
  const flagOn = { CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF: "1" };
  const auto = ["--permission-mode", "auto", "--model", "fixture-model"];
  // An interactive auto-mode session otherwise waits minutes for the
  // server-side classifier the loopback fixture does not provide; `-p` does not.
  for (const [variant, extraEnv, args] of [["flag-off", {}, bypass], ["flag-on", flagOn, bypass],
    ["flag-on-auto", { ...flagOn, CLAUDE_CODE_AUTO_MODE_SERVER: "0" }, auto]]) {
    const name = `interactive-${variant}`;
    if (!only(name)) continue;
    trace("scenario", { name });
    const before = hooks().length;
    const requestsBefore = records.length;
    const session = terminal(name, ["SPIKE:report", ...args], fixture, extraEnv);
    await settle(`${name} Stop`, () => hooks().slice(before).some((record) => record.event === "Stop"), 180000);
    const stopAt = hooks().slice(before).find((record) => record.event === "Stop")?.receiptTime ?? Date.now();
    await delay(10000);
    const sessionId = hooks().slice(before).find((record) => record.event === "SessionStart")?.payload.session_id;
    trace("interactive.outcome", { name, session: sessionId, pid: interactivePid(session), stopAt, newHooks: hooksSince(before),
      afterStop: hooks().slice(before).filter((record) => record.receiptTime > stopAt).map((record) => ({ event: record.event, agentId: record.payload.agent_id ?? null, agentType: record.payload.agent_type ?? null, payloadKeys: record.payloadKeys, delayMs: record.receiptTime - stopAt })),
      requestsAfterStop: records.slice(requestsBefore).filter((record) => record.kind === "model.request" && record.receiptTime > stopAt).map((record) => ({ systemHead: record.systemHead, lastUserHead: record.lastUserHead, maxTokens: record.maxTokens, toolCount: record.toolCount, querySource: record.querySource })) });
    await closeTerminal(session);
    await delay(1500);
  }

  // Scenario 3: resume a session that is running in the background.
  let before = hooks().length;
  let listing = [];
  let job = null;
  // 2.1.280 says "is running as a background session", 2.1.285 "is running in
  // the background"; either is the refusal.
  const backgroundRefusal = /running\s*(?:in\s*the\s*background|as\s*a\s*background\s*session)/i;
  const screenTail = (session) => session.output.replace(/\s+/g, " ").trim().slice(-400);
  if (only("resume-running-background")) {
    trace("scenario", { name: "resume-running-background" });
    const dispatch = await claude(["--bg", "SPIKE:bg-first", "--name", "fixture-bg", ...bypass], { timeout: 60000 });
    trace("dispatch", { status: dispatch.status, stdout: dispatch.stdout, stderr: dispatch.stderr });
    await settle("background worker Stop", () => hooks().slice(before).some((record) => record.event === "Stop"), 90000);
    listing = await agentsJSON("background-idle");
    job = listing.find((entry) => entry.name === "fixture-bg");
    const worker = job ? claudeProcesses().find((entry) => entry.pid === job.pid) : null;
    trace("background.job", { job, worker, hooks: hooksSince(before) });
    if (job?.sessionId) {
      // 3a: an interactive `claude --resume <id>`, with a prompt, without one
      // (a prompt is then typed), and without the bypass flag. Each carries a
      // session-configuring flag (`--model`, and the bypass), which 2.1.285
      // treats as configuration the running session cannot adopt; 3d omits them.
      for (const [variant, args] of [["prompt", ["SPIKE:resumed-prompt", ...bypass]], ["bare", bypass], ["default-mode", ["SPIKE:resumed-default-mode", "--model", "fixture-model"]]]) {
        const name = `resume-interactive-${variant}`;
        const label = variant === "bare" ? "resumed-bare" : `resumed-${variant}`;
        before = hooks().length;
        const resumed = terminal(name, ["--resume", job.sessionId, ...args], fixture);
        await settle(`${name} settled`, () => resumed.exited || backgroundRefusal.test(resumed.output) || commands().some((record) => record.label === label), 20000);
        if (variant === "bare" && !resumed.exited && !backgroundRefusal.test(resumed.output)) {
          resumed.child.stdin.write(`SPIKE:${label}\r`);
        }
        await settle(`${name} command`, () => resumed.exited || backgroundRefusal.test(resumed.output) || commands().some((record) => record.label === label && record.phase === "end"), 30000);
        await delay(2000);
        listing = await agentsJSON(`after-${name}`, true);
        const resumedPid = interactivePid(resumed);
        const resumedCommand = commands().find((record) => record.label === label && record.phase === "start");
        trace("resume.interactive", { variant, job: job.sessionId, workerPid: job.pid, terminalClaudePid: resumedPid, terminalProcess: claudeProcesses().find((entry) => entry.pid === resumedPid) ?? null,
          exited: resumed.exited, refused: backgroundRefusal.test(resumed.output),
          screen: screenTail(resumed),
          workerAlive: claudeProcesses().some((entry) => entry.pid === job.pid),
          command: resumedCommand ? { session: resumedCommand.env.CLAUDE_CODE_SESSION_ID, claudePid: Number(resumedCommand.env.CLAUDE_PID), cwd: resumedCommand.cwd, ancestry: resumedCommand.ancestry.map((entry) => [entry.pid, entry.comm, entry.cmdline.slice(0, 80)]) } : null,
          newHooks: hooksSince(before), listing: listing.filter((entry) => entry.sessionId === job.sessionId || entry.pid === resumedPid) });
        before = hooks().length;
        await closeTerminal(resumed);
        await delay(2000);
        trace("resume.interactive-exit", { variant, workerAlive: claudeProcesses().some((entry) => entry.pid === job.pid), newHooks: hooksSince(before) });
      }

      // 3b: headless `claude -p --resume <id>` against the same session.
      before = hooks().length;
      const headless = await claude(["-p", "SPIKE:resumed-headless", "--resume", job.sessionId, "--output-format", "json", ...bypass], { timeout: 60000 });
      let headlessOutput = null;
      try { headlessOutput = JSON.parse(headless.stdout); } catch {}
      await delay(2000);
      const headlessCommand = commands().find((record) => record.label === "resumed-headless" && record.phase === "start");
      listing = await agentsJSON("after-headless-resume", true);
      trace("resume.headless", { job: job.sessionId, workerPid: job.pid, headlessPid: headless.pid, status: headless.status, sessionId: headlessOutput?.session_id ?? null, stderr: headless.stderr.slice(-600),
        workerAlive: claudeProcesses().some((entry) => entry.pid === job.pid),
        command: headlessCommand ? { session: headlessCommand.env.CLAUDE_CODE_SESSION_ID, claudePid: Number(headlessCommand.env.CLAUDE_PID) } : null, newHooks: hooksSince(before), listing: listing.filter((entry) => entry.sessionId === job.sessionId) });

      // 3c: `claude --bg --resume <id>` while the session is running.
      before = hooks().length;
      const copy = await claude(["--bg", "--resume", job.sessionId, "SPIKE:resumed-bg", ...bypass], { timeout: 60000 });
      await settle("background resume command", () => commands().some((record) => record.label === "resumed-bg" && record.phase === "end"), 60000);
      await delay(2000);
      const copyCommand = commands().find((record) => record.label === "resumed-bg" && record.phase === "start");
      listing = await agentsJSON("after-background-resume", true);
      trace("resume.background", { job: job.sessionId, workerPid: job.pid, status: copy.status, stdout: copy.stdout.slice(-600), stderr: copy.stderr.slice(-600),
        command: copyCommand ? { session: copyCommand.env.CLAUDE_CODE_SESSION_ID, claudePid: Number(copyCommand.env.CLAUDE_PID) } : null, newHooks: hooksSince(before), listing: listing.filter((entry) => entry.kind === "background") });

      // 3d: an interactive `claude --resume <id>` with no session-configuring
      // flag, with a prompt and without one (a prompt is then typed once the
      // session is open). The fixture model ignores the model name, and a
      // forwarded prompt runs under the worker's own permission mode.
      for (const [variant, args] of [["open-prompt", ["SPIKE:resumed-open-prompt"]], ["open-bare", []]]) {
        const name = `resume-interactive-${variant}`;
        const label = `resumed-${variant}`;
        before = hooks().length;
        const opened = terminal(name, ["--resume", job.sessionId, ...args], fixture);
        await settle(`${name} settled`, () => opened.exited || backgroundRefusal.test(opened.output) || /background session/i.test(opened.output) || commands().some((record) => record.label === label), 20000);
        await delay(3000);
        if (variant === "open-bare" && !opened.exited) opened.child.stdin.write(`SPIKE:${label}\r`);
        await settle(`${name} command`, () => opened.exited || commands().some((record) => record.label === label && record.phase === "end"), 30000);
        await settle(`${name} Stop`, () => opened.exited || hooks().slice(before).some((record) => record.event === "Stop"), 15000);
        await delay(2000);
        listing = await agentsJSON(`after-${name}`, true);
        const openedPid = interactivePid(opened);
        const openedCommand = commands().find((record) => record.label === label && record.phase === "start");
        trace("resume.open", { variant, job: job.sessionId, workerPid: job.pid, terminalClaudePid: openedPid, terminalProcess: claudeProcesses().find((entry) => entry.pid === openedPid) ?? null,
          exited: opened.exited, refused: backgroundRefusal.test(opened.output), screen: screenTail(opened),
          workerAlive: claudeProcesses().some((entry) => entry.pid === job.pid),
          command: openedCommand ? { session: openedCommand.env.CLAUDE_CODE_SESSION_ID, claudePid: Number(openedCommand.env.CLAUDE_PID), cwd: openedCommand.cwd, ancestry: openedCommand.ancestry.map((entry) => [entry.pid, entry.comm, entry.cmdline.slice(0, 80)]) } : null,
          newHooks: hooksSince(before), listing: listing.filter((entry) => entry.sessionId === job.sessionId || entry.pid === openedPid) });
        snapshot(`${name} open`, { workerPid: job.pid, terminalClaudePid: openedPid });
        // `/exit` in the opened view leaves the client running; what it runs
        // next is recorded before the terminal is closed.
        before = hooks().length;
        opened.child.stdin.write("/exit\r");
        await settle(`${name} exit`, () => opened.exited, 10000);
        const afterExit = claudeProcesses().find((entry) => entry.pid === openedPid) ?? null;
        const exitedOnExit = opened.exited;
        await closeTerminal(opened);
        await delay(2000);
        listing = await agentsJSON(`after-${name}-exit`, true);
        trace("resume.open-exit", { variant, exitedOnExit, clientAfterExit: afterExit, exited: opened.exited, workerAlive: claudeProcesses().some((entry) => entry.pid === job.pid), newHooks: hooksSince(before),
          listing: listing.filter((entry) => entry.sessionId === job.sessionId) });
      }

      // 3e: stop the worker, then an interactive resume opens the saved conversation.
      before = hooks().length;
      const stopped = await claude(["stop", job.id], { timeout: 30000 });
      await delay(2500);
      const reopened = terminal("resume-stopped", ["--resume", job.sessionId, "SPIKE:resumed-stopped", ...bypass], fixture);
      await settle("stopped resume command", () => commands().some((record) => record.label === "resumed-stopped" && record.phase === "end"), 60000);
      await delay(1500);
      const reopenedPid = interactivePid(reopened);
      const reopenedCommand = commands().find((record) => record.label === "resumed-stopped" && record.phase === "start");
      trace("resume.stopped", { job: job.sessionId, stopStatus: stopped.status, terminalClaudePid: reopenedPid, terminalProcess: claudeProcesses().find((entry) => entry.pid === reopenedPid),
        command: reopenedCommand ? { session: reopenedCommand.env.CLAUDE_CODE_SESSION_ID, claudePid: Number(reopenedCommand.env.CLAUDE_PID), ancestry: reopenedCommand.ancestry.map((entry) => [entry.pid, entry.comm]) } : null, newHooks: hooksSince(before) });
      await closeTerminal(reopened);
    }
  }

  // Scenario 4: `claude --desktop`, with and without a session to open, on a
  // host without the desktop app: redirected, then on a pseudo-terminal. The
  // opener shims record any launch it attempts.
  const desktopTarget = job?.sessionId ?? "00000000-0000-4000-8000-000000000000";
  for (const [name, args] of [["desktop-redirected", ["--desktop"]], ["desktop-terminal", ["--desktop"]], ["desktop-terminal-resume", ["--desktop", "--resume", desktopTarget]]]) {
    if (!only(name)) continue;
    trace("scenario", { name });
    const openersBefore = records.filter((record) => record.kind === "opener").length;
    const hooksBefore = hooks().length;
    if (name === "desktop-redirected") {
      const result = await claude(args, { timeout: 30000 });
      await delay(1000);
      trace("desktop.outcome", { name, status: result.status, signal: result.signal, stdout: result.stdout.slice(-800), stderr: result.stderr.slice(-800),
        openers: records.filter((record) => record.kind === "opener").slice(openersBefore).map((record) => ({ name: record.name, args: record.args })), newHooks: hooksSince(hooksBefore) });
      continue;
    }
    const session = terminal(name, args, fixture);
    await settle(`${name} exit`, () => session.exited, 15000);
    await delay(1000);
    trace("desktop.outcome", { name, exited: session.exited, screen: session.output.replace(/\s+/g, " ").trim().slice(-400),
      openers: records.filter((record) => record.kind === "opener").slice(openersBefore).map((record) => ({ name: record.name, args: record.args })), newHooks: hooksSince(hooksBefore) });
    if (!session.exited) await closeTerminal(session);
  }

  // Scenario 5: background dispatch, without a terminal, into directories with
  // no trust entry of their own: one nested in the trusted main working tree,
  // its sibling linked Worktree, and an unrelated Repository, the last also
  // without the bypass flag.
  for (const [name, cwd, args] of [["bg-trust-nested", nested, bypass], ["bg-trust-sibling", sibling, bypass], ["bg-trust-unrelated", unrelated, bypass], ["bg-trust-unrelated-default-mode", unrelated, ["--model", "fixture-model"]]]) {
    if (!only(name)) continue;
    trace("scenario", { name });
    before = hooks().length;
    const result = await claude(["--bg", `SPIKE:${name}`, "--name", name, ...args], { cwd, timeout: 60000 });
    await settle(`${name} command`, () => commands().some((record) => record.label === name && record.phase === "end"), 20000);
    trace("bg-trust.outcome", { name, cwd, status: result.status, stdout: result.stdout.slice(-600), stderr: result.stderr.slice(-600), ran: commands().some((record) => record.label === name), newHooks: hooksSince(before) });
  }

  // Scenario 6: `--setting-sources` without `user` drops the user-scope hooks
  // from a headless session and from a background worker.
  for (const [name, args] of [["sources-headless", ["-p", "SPIKE:sources-headless", "--setting-sources", "project,local"]], ["sources-bg", ["--bg", "SPIKE:sources-bg", "--name", "sources-bg", "--setting-sources", "project,local"]]]) {
    if (!only(name)) continue;
    trace("scenario", { name });
    before = hooks().length;
    const result = await claude([...args, ...bypass], { timeout: 60000 });
    await settle(`${name} command`, () => commands().some((record) => record.label === name && record.phase === "end"), 30000);
    await delay(2000);
    const ran = commands().find((record) => record.label === name && record.phase === "start");
    trace("sources.outcome", { name, status: result.status, stderr: result.stderr.slice(-400), ran: Boolean(ran), session: ran?.env.CLAUDE_CODE_SESSION_ID ?? null,
      hooksForSession: hooks().slice(before).filter((record) => record.payload.session_id === ran?.env.CLAUDE_CODE_SESSION_ID).map((record) => record.event) });
  }

  snapshot("before-cleanup");
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const session of terminals) {
    if (process.env.SPIKE_DEBUG_TERMINAL === "1") writeFileSync(path.join(root, `terminal-${session.name}.txt`), session.output);
    if (!session.exited) { try { session.child.kill("SIGTERM"); } catch {} }
  }
  await claude(["daemon", "stop", "--any"], { timeout: 30000 }).catch(() => {});
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
