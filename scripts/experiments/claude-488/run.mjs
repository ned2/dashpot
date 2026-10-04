// Live idle-start and `/fork` run for Issue #488, with #490's measurement:
// what Claude Code publishes, and what Dashpot's hook record store holds,
// when a session starts and nobody prompts it, and when `/fork` copies a
// conversation into a new background session while a background Sub-agent
// worker is still working. An interactive session opened and left idle, one
// resumed at launch and left idle, a headless stream-json session given no
// input yet, and a `/clear` with no worker left idle show whether any
// `UserPromptSubmit` follows the `SessionStart`. Drives a pinned Claude Code
// binary against a loopback Messages API fixture with an isolated
// configuration, whose own transient background daemon hosts the fork and is
// stopped by the runner. Every subscribed hook event goes to Dashpot's real
// Claude Code publisher, run from this checkout's working tree, subscribed as
// `dashpot integrate claude-code` subscribes it. The trace is metadata only:
// prompts and transcripts stay out, apart from the fixture's own labels. The
// verifier checks the trace against the findings.
//
// Usage: node run.mjs <absolute claude binary> [expected version]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset; SPIKE_PROBE=1
// records the `/fork` screens and stops before running it.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-488-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const gates = path.join(root, "gates");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.289";
const selected = process.env.SPIKE_SCENARIOS ? new Set(process.env.SPIKE_SCENARIOS.split(",")) : null;
const python = path.join(checkout, ".venv", "bin", "python");

// A Claude Code session above the runner would be the host Dashpot finds for
// any fixture process it does not recognise, and would collect the fixture's
// hook records, so the runner refuses to start below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every Claude Code session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const launcherDirectory = path.join(root, "bin");
mkdirSync(launcherDirectory);
const launcher = path.join(launcherDirectory, "claude");
symlinkSync(binary, launcher);

// The publisher is this checkout's working tree (its editable install).
const publisherScript = (name) => {
  const file = path.join(launcherDirectory, name);
  writeFileSync(file, `#!/bin/sh\nexec '${python}' -c 'import sys; import dashpot.hook as h; sys.exit(h.claude_code_main())'\n`);
  chmodSync(file, 0o755);
  return file;
};
const publisher = publisherScript("publisher");
const loadedFrom = () => retained(execFileSync(python, ["-c", "import dashpot.sessions.hook_records as m; print(m.__file__)"], { encoding: "utf8" }).trim());

const home = path.join(root, "home");
const env = {
  PATH: `${launcherDirectory}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: home,
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CLAUDE_CONFIG_DIR: path.join(home, ".claude"),
  ANTHROPIC_API_KEY: "fixture-unused",
  DISABLE_AUTOUPDATER: "1",
  DISABLE_TELEMETRY: "1",
  DISABLE_ERROR_REPORTING: "1",
  DISABLE_BUG_COMMAND: "1",
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  CLAUDE_CODE_DISABLE_TERMINAL_TITLE: "1",
  TERM: "dumb",
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_PUBLISHER: publisher,
  SPIKE_STORE: path.join(fixture, ".dashpot", "state", "sessions"),
  SPIKE_GATES: gates,
};
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Dashpot Project, so the publisher writes the Project-local store.
mkdirSync(path.join(fixture, ".dashpot"), { recursive: true });
mkdirSync(path.join(fixture, "issues"), { recursive: true });
writeFileSync(path.join(fixture, ".dashpot", "config.json"), JSON.stringify({ projectId: "project:fixture", displayLabel: "Fixture", repositoryId: "repository:fixture", issueSource: { kind: "markdown", path: "issues" } }));
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.claude/\n");
git("add", ".");
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
  const record = await body(req);
  trace(url.pathname === "/hook" ? "hook" : "command", record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The subscriptions `dashpot integrate claude-code` installs, read from this
// checkout, each publishing; the compaction events beside them, observed only.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import CLAUDE_CODE as c; print(json.dumps({'events': c.events, 'matched': c.matched_events}))"],
  { encoding: "utf8", env: { ...env, PATH: "/usr/bin:/bin" } }));
const observedOnly = ["PreCompact", "PostCompact"];
const handler = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")}`, timeout: 15 };
const observer = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")} observe`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
for (const event of observedOnly) (subscriptions[event] ??= []).push({ hooks: [observer] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: { [fixture]: { hasTrustDialogAccepted: true, allowedTools: [] } },
}, null, 2));

// The fixture model. A turn is named by the `SPIKE:<label>` in the latest
// user text message; each tool result since then advances its sequence by a
// step. A user text message with no label (a compaction prompt, a task
// notification, a post-compaction summary) is answered with plain text.
const node = process.execPath;
const commandScript = path.join(here, "command.mjs");
const bash = (command) => ({ tool: "Bash", input: { command, description: "Fixture step" } });
const report = (label, hold = 200) => bash(`${node} ${commandScript} ${label} ${hold}`);
const gated = (label, gate) => bash(`${node} ${commandScript} ${label} wait ${gate}`);
const delegate = (child, description = `Fixture ${child}`) => ({ tool: "Agent", input: { description, prompt: `SPIKE:${child}`, subagent_type: "general-purpose", run_in_background: true } });
const sequences = {};
const textParts = (content) => typeof content === "string" ? [content] : (content ?? []).filter((part) => part.type === "text").map((part) => part.text ?? "");
const hasResult = (message) => Array.isArray(message.content) && message.content.some((part) => part.type === "tool_result");
const labelsIn = (text) => [...text.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (url.pathname.endsWith("/count_tokens")) {
    trace("model.count_tokens", {});
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
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  // The latest user message that is not purely tool results starts the turn.
  let trigger = -1;
  messages.forEach((message, index) => { if (message.role === "user" && textParts(message.content).join("").trim()) trigger = index; });
  const triggerText = trigger >= 0 ? textParts(messages[trigger].content).join("\n") : "";
  // A task notification is answered with plain text, whatever it quotes.
  const label = triggerText.includes("<task-notification>") ? null : labelsIn(triggerText).at(-1) ?? null;
  const last = messages.at(-1);
  const done = messages.slice(trigger + 1).filter((message) => message.role === "user" && hasResult(message)).length;
  const sequence = (label && sequences[label]) || null;
  const step = sequence?.steps[done] ?? null;
  const steps = step ? (Array.isArray(step) ? step : [step]) : [];
  const available = steps.every((item) => tools.includes(item.tool));
  const inflate = sequence?.inflate && sequence.inflate.step === done ? sequence.inflate.inputTokens : null;
  const sessionHeaders = Object.fromEntries(Object.entries(req.headers).filter(([key]) => key.includes("session")));
  trace("model.request", { label, step: done, tools: steps.map((item) => item.tool), available: steps.length ? available : null,
    messages: messages.length, toolCount: tools.length, stream: Boolean(payload.stream), lastHasResult: last ? hasResult(last) : null,
    triggerLabels: labelsIn(triggerText), triggerNotification: triggerText.includes("<task-notification>"),
    // Whether the turn's prompt reads as a compaction request; the text stays out.
    summaryPrompt: /summar/i.test(triggerText) && !labelsIn(triggerText).length && !triggerText.includes("<task-notification>"), inflate, sessionHeaders });
  const final = sequence && done >= sequence.steps.length ? sequence.final ?? "Fixture complete." : "Fixture complete.";
  const usage = { input_tokens: inflate ?? 10, output_tokens: 1 };
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [{ type: "text", text: "Fixture complete." }],
      stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage } });
  if (steps.length && available) {
    steps.forEach((item, index) => {
      sse("content_block_start", { index, content_block: { type: "tool_use", id: `toolu_${label}_${records.length}_${index}`, name: item.tool, input: {} } });
      sse("content_block_delta", { index, delta: { type: "input_json_delta", partial_json: JSON.stringify(item.input) } });
      sse("content_block_stop", { index });
    });
    sse("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { ...usage, output_tokens: 20 } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: steps.length ? "Fixture tool unavailable." : final } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { ...usage, output_tokens: 4 } });
  }
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// Runner helpers.
const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
const hooks = () => records.filter((record) => record.kind === "hook");
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
// Waits that are themselves the measurement record a timeout, not a failure.
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const waitCommand = (label, phase = "end", timeout = 90000) => waitFor(() => command(label, phase), `${label} ${phase}`, timeout);
const open = (gate) => { writeFileSync(path.join(gates, gate), ""); trace("gate", { gate }); };
const alive = (pid) => { try { process.kill(pid, 0); return !/\) Z /.test(readFileSync(`/proc/${pid}/stat`, "utf8")); } catch { return false; } };
const mark = () => records.length;
const hostHooks = (client, since) => hooks().filter((record) => record.receipt > since && record.hostPid === client.host);
const mainStopAfter = (client, since) => hostHooks(client, since).some((record) => record.event === "Stop" && !record.payload.agent_id);
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`SPIKE_GATES=${gates}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");

// An interactive lead on a pseudo-terminal, typed into as a person would.
const interactive = async (name, extraEnv = {}, extraArgs = []) => {
  const since = mark();
  const child = spawn("script", ["-qfec", [launcher, ...commonArgs, ...extraArgs].join(" "), "/dev/null"],
    { cwd: fixture, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40", ...extraEnv }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, host: null, exited: null, mode: "interactive", output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); if (state.output.length > 200000) state.output = state.output.slice(-100000); });
  child.on("exit", (status, signal) => { state.exited = { status, signal, at: Date.now() }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, mode: "interactive", pid: child.pid, extraEnv: Object.keys(extraEnv), extraArgs: extraArgs.map(retained) });
  const started = () => hooks().find((record) => record.receipt > since && record.event === "SessionStart" && record.ancestry.some((entry) => entry.pid === child.pid));
  try { await waitFor(started, `${name} SessionStart`, 60000); } catch (error) {
    writeFileSync(path.join(root, `screen-${name}.txt`), state.output);
    throw error;
  }
  state.session = started().payload.session_id;
  state.host = started().hostPid;
  trace("client.ready", { name, session: state.session, host: state.host });
  await delay(3000);
  state.type = async (text) => { child.stdin.write(text); await delay(400); child.stdin.write("\r"); };
  state.turn = async (text, wait = true) => {
    const before = mark();
    await state.type(text);
    trace("turn.sent", { client: name, text });
    if (wait) {
      try { await waitFor(() => mainStopAfter(state, before), `${name} ${text} Stop`, 90000); } catch (error) {
        writeFileSync(path.join(root, `screen-${name}.txt`), state.output);
        throw error;
      }
    }
  };
  state.screen = (label) => trace("screen", { client: name, label, tail: retained(state.output.slice(-900)).replace(/\s+/g, " ") });
  state.end = async () => {
    await state.type("/exit");
    trace("action.end", { client: name, how: "/exit typed" });
    await settle(() => state.exited, `${name} exit`, 20000);
    if (!state.exited) { state.screen(`${name}-exit`); child.kill("SIGKILL"); trace("action.close", { client: name }); await settle(() => state.exited, `${name} exit after close`, 10000); }
  };
  return state;
};

// A headless stream-json lead: one `claude -p` process taking its user turns
// on stdin.
const headless = async (name) => {
  const child = spawn(launcher, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", ...commonArgs],
    { cwd: fixture, env, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, host: child.pid, exited: null, mode: "headless" };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      try {
        const message = JSON.parse(line);
        if (message.type === "system" || message.type === "result")
          trace("client.stream", { client: name, type: message.type, subtype: message.subtype ?? null, session: message.session_id ?? null,
            result: typeof message.result === "string" ? retained(message.result).slice(0, 120) : undefined });
      } catch {}
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal, at: Date.now() }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, mode: "headless", pid: child.pid });
  state.type = async (text) => child.stdin.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text }] } }) + "\n");
  state.turn = async (text, wait = true) => {
    const before = mark();
    await state.type(text);
    trace("turn.sent", { client: name, text });
    if (wait) await waitFor(() => mainStopAfter(state, before), `${name} ${text} Stop`, 90000);
  };
  state.screen = () => {};
  state.end = async () => {
    child.stdin.end();
    trace("action.end", { client: name, how: "close stdin" });
    await settle(() => state.exited, `${name} exit`, 30000);
    if (!state.exited) { child.kill("SIGTERM"); await settle(() => state.exited, `${name} exit after SIGTERM`, 10000); }
  };
  return state;
};

// The lead starts a background worker whose Bash call holds on a gate.
const startWorker = async (p, client, leadSequence) => {
  sequences[`${p}-lead`] = leadSequence ?? { steps: [delegate(`${p}-worker`)], final: "Lead dispatched a worker." };
  sequences[`${p}-worker`] = { steps: [gated(`${p}-w-hold`, `${p}-go`), report(`${p}-w-after`)], final: `MARK:${p}-final` };
  await client.turn(`SPIKE:${p}-lead`, !leadSequence);
  await waitCommand(`${p}-w-hold`, "start");
  await delay(1500);
};
// After the action: the worker is still holding, then is released, and its
// SubagentStop is awaited; a further lead turn shows which session goes on.
const finishWorker = async (p, client, since) => {
  const hold = command(`${p}-w-hold`, "start");
  trace("worker.check", { scenario: p, holdPid: hold.pid, holdAlive: alive(hold.pid), holdEnded: Boolean(command(`${p}-w-hold`)), clientAlive: !client.exited });
  client.screen(`${p}-after-action`);
  open(`${p}-go`);
  await settle(() => command(`${p}-w-after`), `${p} worker continued after the gate`, 60000);
  // Whichever session and Host Process the worker's stop names.
  await settle(() => hooks().some((record) => record.receipt > since && record.event === "SubagentStop"), `${p} SubagentStop`, 60000);
  // The lead hears of the completion as a task notification.
  await delay(6000);
  if (client.exited) return;
  sequences[`${p}-after`] = { steps: [report(`${p}-after`)], final: "After." };
  const turned = await (async () => { try { await client.turn(`SPIKE:${p}-after`); return true; } catch { return false; } })();
  trace("after.turn", { scenario: p, stopped: turned, session: command(`${p}-after`)?.env.CLAUDE_CODE_SESSION_ID ?? null });
};

// A Claude Code subcommand in the fixture's environment, such as `agents`.
const claude = async (args, label, timeout = 30000) => {
  const child = spawn(launcher, args, { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
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
      agents = JSON.parse(stdout).map(({ id, kind, name, pid, sessionId, state, status: agentStatus }) => ({ id, kind, name, pid, sessionId, state, status: agentStatus }));
    } catch { agents = null; }
  }
  trace("action.claude", { label, args, status, signal, agents, stdout: agents === undefined ? retained(stdout).slice(-400) : undefined, stderr: retained(stderr).slice(-400) });
  return { status, stdout, stderr, agents };
};
// The daemons' directories under /tmp/cc-daemon-<uid>/, which the user's own
// sessions share: the run records only which entries appeared or went
// relative to those present when it started, so a fixture daemon is shown to
// be its own and to be gone afterwards.
const daemonRoot = `/tmp/cc-daemon-${os.userInfo().uid}`;
const daemonDirectories = () => { try { return readdirSync(daemonRoot).sort(); } catch { return []; } };
let daemonBaseline = [];
const daemonChange = () => {
  const now = daemonDirectories();
  return { preexisting: daemonBaseline.length, preexistingKept: daemonBaseline.every((name) => now.includes(name)),
    added: now.filter((name) => !daemonBaseline.includes(name)), removed: daemonBaseline.filter((name) => !now.includes(name)) };
};
// A wait that is itself the measurement: nothing is typed or sent.
const idle = async (client, label, ms) => {
  const since = mark();
  trace("idle.start", { client: client.name, label, ms });
  await delay(ms);
  trace("idle.end", { client: client.name, label, ms, hooks: hooks().filter((record) => record.receipt > since).map((record) => record.event) });
  client.screen(label);
};
const IDLE_MS = 20000;

const scenarios = [];
const scenario = (name, run) => scenarios.push({ name, run });
const shared = {};

// An interactive session opened with no prompt and left idle, then given one
// turn.
scenario("idle-startup", async () => {
  const p = "is";
  const client = await interactive(p);
  await idle(client, `${p}-idle`, IDLE_MS);
  sequences[`${p}-turn`] = { steps: [report(`${p}-turn`)], final: "Turn done." };
  await client.turn(`SPIKE:${p}-turn`);
  await client.end();
  shared.idleSession = client.session;
});

// The same session resumed at launch, `claude --resume <id>`, and left idle.
scenario("idle-resume", async () => {
  assert(shared.idleSession, "idle-startup's session");
  const client = await interactive("ir", {}, ["--resume", shared.idleSession]);
  await idle(client, "ir-idle", IDLE_MS);
  await client.end();
});

// A headless stream-json session sent no user turn yet, then one.
scenario("idle-headless", async () => {
  const p = "ih";
  const client = await headless(p);
  await idle(client, `${p}-idle`, IDLE_MS);
  sequences[`${p}-turn`] = { steps: [report(`${p}-turn`)], final: "Turn done." };
  await client.turn(`SPIKE:${p}-turn`);
  await client.end();
});

// `/clear` with no worker, left idle.
scenario("clear-idle", async () => {
  const p = "ci";
  const client = await interactive(p);
  sequences[`${p}-turn`] = { steps: [report(`${p}-turn`)], final: "Turn done." };
  await client.turn(`SPIKE:${p}-turn`);
  const since = mark();
  await client.type("/clear");
  trace("action", { scenario: p, action: "/clear" });
  await settle(() => hostHooks(client, since).some((record) => record.event === "SessionStart"), `${p} SessionStart`, 20000);
  await idle(client, `${p}-idle`, IDLE_MS);
  await client.end();
});

// `/fork` while a background worker works: the lead's worker holds on a gate
// across the fork, which this release hosts in a new background session
// under the fixture's own transient daemon.
scenario("fork-worker", async () => {
  const p = "fw";
  const client = await interactive(p);
  await startWorker(p, client);
  trace("daemon.directories", { label: `${p}-before`, ...daemonChange() });
  const since = mark();
  client.child.stdin.write("/fork");
  await delay(3000);
  client.screen(`${p}-menu`);
  if (process.env.SPIKE_PROBE === "1") {
    writeFileSync(path.join(root, `screen-${p}-probe.txt`), client.output);
    client.child.stdin.write("\u0015");
    open(`${p}-go`);
    return;
  }
  client.child.stdin.write("\r");
  trace("action", { scenario: p, action: "/fork" });
  const forked = () => hooks().find((record) => record.receipt > since && record.event === "SessionStart" && record.payload.session_id !== client.session);
  await settle(forked, `${p} fork SessionStart`, 30000);
  await delay(5000);
  client.screen(`${p}-forked`);
  trace("daemon.directories", { label: `${p}-forked`, ...daemonChange() });
  await claude(["agents", "--json", "--all"], `${p}-agents`);
  // The fork is left idle: whether it begins a turn of its own.
  await idle(client, `${p}-idle`, IDLE_MS);
  await finishWorker(p, client, since);
  await claude(["agents", "--json", "--all"], `${p}-agents-after`);
  // Stopping the fixture's daemon ends the background session it hosts.
  const stopping = mark();
  await claude(["daemon", "stop", "--any"], `${p}-daemon-stop`);
  const fork = forked();
  if (fork) await settle(() => hooks().some((record) => record.receipt > stopping && record.event === "SessionEnd" && record.payload.session_id === fork.payload.session_id), `${p} fork SessionEnd`, 20000);
  trace("daemon.directories", { label: `${p}-daemon-stopped`, ...daemonChange() });
  await client.end();
});

const sha = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
try {
  const sources = ["sessions/hook_publish.py", "sessions/hook_records.py", "sessions/hook_scan.py", "sessions/integrate.py", "hook.py"];
  daemonBaseline = daemonDirectories();
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    subscriptions: { events: integration.events, matched: integration.matched, observedOnly },
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")),
    fixture, scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    worktreeDirty: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean),
    publisher: loadedFrom(),
    experimentSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"].map((file) => [file, sha(path.join(here, file))])),
    worktreeSourceSHA256: Object.fromEntries(sources.map((file) => [`src/dashpot/${file}`, sha(path.join(checkout, "src", "dashpot", file))])) });
  for (const { name, run } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await run(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    for (const entry of fixtureProcesses()) { try { process.kill(entry.pid, "SIGKILL"); } catch {} }
    await delay(1000);
  }
  console.log(`Scenarios completed: ${root}`);
} finally {
  // The fixture's own transient daemon, stopped rather than killed, removes
  // its directory under /tmp/cc-daemon-<uid>/.
  await claude(["daemon", "stop", "--any"], "cleanup").catch(() => {});
  await delay(1000);
  trace("daemon.directories", { label: "cleanup", ...daemonChange() });
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  writeFileSync(path.join(root, "done"), "");
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
