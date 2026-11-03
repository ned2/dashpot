// Goal-driven Lead run for Issue #649: drives a pinned Claude Code binary's
// `/goal` against a loopback Messages API fixture with an isolated
// configuration directory. The goal's evaluator runs on the small fast
// model, which the fixture names `fixture-evaluator`, so the runner scripts
// each verdict. Every hook event goes to this checkout's real Claude Code
// publisher, subscribed exactly as `dashpot integrate claude-code`
// subscribes it, and between steps the runner records what `dashpot --json`
// observes. Three headless Leads (`claude -p` with stream-json input):
//
// - C1 binds Issue 1, sets a goal phrased as the skill's end (every Worker's
//   pull request open and its CI green), and launches two background
//   Workers; the evaluator is answered "not met" once after both finish,
//   while the continuation runs a command, and "met" after.
// - C2's evaluator always answers "not met": its continuations first each
//   run a command, then answer with text only, until Claude Code ends the
//   turn; a later prompt shows whether the goal survived, and an
//   "impossible" verdict whether it clears.
// - C3 sets a one-minute check-in interval and waits on two background
//   Workers, the second finishing about half a minute after the first, so
//   a turn ends with work still running once evaluation has been deferred
//   for over a minute.
//
// The trace is metadata only: each request's kind, markers and tool, each
// evaluator request's shape, each hook's identity fields, and Dashpot's view.
//
//   node run.mjs <absolute claude binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.317";
// A harness session above the runner would be the host Dashpot finds for any
// fixture process it does not recognise, so the runner refuses to start below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || entry.comm.startsWith("codex") || entry.comm === "opencode"
  || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const dashpot = path.join(checkout, ".venv", "bin", "dashpot");
const publisher = path.join(checkout, ".venv", "bin", "dashpot-claude-code-hook");
const python = path.join(checkout, ".venv", "bin", "python");
for (const file of [dashpot, publisher, python]) assert(existsSync(file), `Run \`uv sync --locked --group dev\` in this checkout first: ${file} is missing`);

const root = mkdtempSync(path.join("/var/tmp", "dashpot-649-claude-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const userName = new RegExp(`\\b${os.userInfo().username}\\b`, "g");
const clean = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT")
  .replaceAll(home, "~").replace(hostName, "<host>").replace(userName, "<user>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 4).map((entry) => ({ pid: entry.pid, ppid: entry.ppid, comm: entry.comm })) } : record;
  appendFileSync(tracePath, clean(JSON.stringify(kept)) + "\n");
  return record;
};
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
// The shared Claude Code daemon directory belongs to the operator's own
// sessions: the run only counts the entries it gained, and removes none.
const daemonDirectory = `/tmp/cc-daemon-${os.userInfo().uid}`;
const daemonEntries = () => { try { return readdirSync(daemonDirectory); } catch { return []; } };
const daemonBefore = new Set(daemonEntries());

// Clients start through a launcher named `claude`, as a person's do.
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
  TMPDIR: path.join(root, "tmp"),
  CLAUDE_CONFIG_DIR: path.join(root, "claude-config"),
  ANTHROPIC_API_KEY: "fixture-unused",
  // The goal evaluator runs on the small fast model; naming it lets the
  // fixture tell an evaluator request from the Lead's own.
  ANTHROPIC_DEFAULT_HAIKU_MODEL: "fixture-evaluator",
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
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(launcher, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Dashpot Project with a markdown Issue Source.
mkdirSync(path.join(fixture, "issues"), { recursive: true });
for (const number of [1, 2, 3]) {
  const front = { id: `I_fixture_${number}`, number, reference: `issue-${number}`, state: "open", stateReason: null, labels: [], assignees: [], author: "fixture",
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `issue-${number}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
}
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
const initialized = execFileSync(dashpot, ["init", "--markdown", "issues"], { cwd: fixture, env, encoding: "utf8" });
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
  if (record.env) delete record.env.CLAUDE_CODE_MESSAGING_TOKEN;
  trace(url.pathname === "/hook" ? "hook" : "command", record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model. The latest user message that is not only tool results
// is the directive; its kind is what Claude Code put there: a person's
// `SPIKE:<label>` prompt, the goal's own start (`/goal`), the evaluator's
// "not met" feedback, a background task's notification, or anything else,
// which a check-in would be. A goal's start and feedback quote its
// condition, `SPIKE:<lead>-goal`, so both select that Lead's goal plan for
// the runner's current phase, chosen once per directive. The tool results
// after the directive select the step; each step is one tool call, and the
// directive's plan ending ends the turn with `DONE:<label>`.
const commandScript = path.join(here, "command.mjs");
const bash = (label, hold = 200) => ({ tool: "Bash", input: { command: `node ${commandScript} ${label} ${hold}`, description: "Fixture step" } });
const work = (label, ...args) => ({ tool: "Bash", input: { command: `node ${commandScript} ${label} -- work ${args.join(" ")}`, description: "Fixture step" } });
const background = (child) => ({ tool: "Agent", input: { description: `Fixture ${child}`, prompt: `SPIKE:${child}`, subagent_type: "general-purpose", run_in_background: true } });
const condition = (lead) => `SPIKE:${lead}-goal Every fixture Worker's pull request is open and its CI checks are green.`;
const phases = { c1: "start", c2: "tools", c3: "start" };
// Each Lead's session, once its first result names it.
const sessionsByLead = {};
const plans = {
  "c1-bind": [work("c1-start", "start", "issue-1")],
  wa: [bash("wa", 25000)],
  wb: [bash("wb", 70000)],
  // Under the Bash tool's 120 s timeout, so each Worker's command ends in place.
  wc: [bash("wc", 80000)],
  wd: [bash("wd", 110000)],
};
const goalPlans = {
  // The goal's start turn launches the Workers; notifications end with text
  // until both have finished; the first feedback after both runs a command.
  c1: { start: [background("wa"), background("wb")], workers: [], continue: [bash("c1-continuation", 8000)], met: [] },
  c2: { tools: [bash("c2-progress", 200)], idle: [] },
  c3: { start: [background("wc"), background("wd")], workers: [] },
};
const notificationPlans = { c1: (index) => index === 1 ? [bash("c1-notified", 6000)] : [], c3: () => [] };
// Verdicts the evaluator returns, by Lead and phase.
const verdictFor = (lead) => {
  if (lead === "c1") return phases.c1 === "met" ? { ok: true, reason: "fixture: every pull request is open and green" } : { ok: false, reason: "fixture: not yet" };
  if (lead === "c2") return phases.c2 === "impossible" ? { ok: false, impossible: true, reason: "fixture: can never hold" } : { ok: false, reason: "fixture: not yet" };
  if (lead === "c3") return phases.c3 === "met" ? { ok: true, reason: "fixture: met" } : { ok: false, reason: "fixture: not yet" };
  return { ok: false, reason: "fixture: unknown" };
};
const textOf = (message) => typeof message.content === "string" ? message.content
  : (message.content ?? []).filter((part) => part.type === "text").map((part) => part.text).join("\n");
const onlyResults = (message) => Array.isArray(message.content) && message.content.length > 0 && message.content.every((part) => part.type === "tool_result");
// Claude Code may merge consecutive user messages, so the directive's kind
// is the one whose marker comes last in it: a person's prompt (a label that
// is not a goal's), the goal's start, its feedback, or a notification.
const classify = (text) => {
  const prompts = [...text.matchAll(/SPIKE:([a-z0-9-]+)/g)].filter((match) => !match[1].endsWith("-goal"));
  const goals = [...text.matchAll(/SPIKE:([a-z0-9-]+-goal)/g)];
  const found = [["goal-start", text.lastIndexOf("Stop hook is now active with condition")], ["goal-feedback", text.lastIndexOf("Stop hook feedback:")],
    ["task-notification", text.lastIndexOf("<task-notification>")], ["prompt", prompts.at(-1)?.index ?? -1]].filter(([, at]) => at >= 0).sort((a, b) => b[1] - a[1]);
  const kind = found[0]?.[0] ?? "other";
  const label = kind === "prompt" ? prompts.at(-1)[1] : kind.startsWith("goal") ? goals.at(-1)?.[1] ?? null : null;
  return { kind, label };
};
const sessionOf = (payload) => {
  const raw = String(payload.metadata?.user_id ?? "");
  return raw.match(/session[_-]?id"?\s*[:=]\s*"?([0-9a-f-]{36})/i)?.[1] ?? raw.match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/)?.[1] ?? null;
};
const directivePlans = new Map();
const notificationCounts = new Map();
const modelRequests = [];
const evaluations = [];
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
  const session = sessionOf(payload);
  let response;
  if (payload.model === "fixture-evaluator") {
    // The evaluator's request: its shape, the condition as it arrived, and
    // the hook input it quotes, with neither the transcript nor prompts.
    const last = textOf(messages.at(-1) ?? {});
    const quoted = last.match(/ARGUMENTS: (\{.*\})\s*$/s)?.[1];
    let hookInput = null;
    try { hookInput = JSON.parse(quoted); } catch {}
    const conditionText = last.match(/Condition: (.*)\n/)?.[1] ?? null;
    const lead = conditionText?.match(/SPIKE:(c\d)-goal/)?.[1] ?? null;
    const verdict = verdictFor(lead);
    const system = (payload.system ?? []).map((part) => part.text ?? "").join("\n");
    const evaluation = trace("model.evaluator", { lead, session: hookInput?.session_id ?? session, verdict, phase: lead ? phases[lead] : null,
      conditionVerbatim: lead ? conditionText === condition(lead) : null, tools: (payload.tools ?? []).length, messages: messages.length,
      format: payload.output_config?.format?.type ?? null, schemaKeys: Object.keys(payload.output_config?.format?.schema?.properties ?? {}).sort(),
      systemNamesShapes: ["\"ok\": true", "\"ok\": false", "\"impossible\": true"].map((shape) => system.includes(shape)),
      hookInput: hookInput && { event: hookInput.hook_event_name, stopHookActive: hookInput.stop_hook_active, keys: Object.keys(hookInput).sort(),
        backgroundTasks: Array.isArray(hookInput.background_tasks) ? hookInput.background_tasks.length : null } });
    evaluations.push(evaluation);
    response = { type: "text", text: JSON.stringify(verdict) };
  } else {
    let directiveAt = -1;
    messages.forEach((message, index) => { if (message.role === "user" && !onlyResults(message) && /SPIKE:|<task-notification>|Stop hook|goal/i.test(textOf(message))) directiveAt = index; });
    const text = directiveAt >= 0 ? textOf(messages[directiveAt]) : "";
    const { kind, label } = directiveAt >= 0 ? classify(text) : { kind: "none", label: null };
    const lead = label?.match(/^(c\d)-goal$/)?.[1] ?? label?.match(/^(c\d)-/)?.[1] ?? null;
    const results = messages.slice(directiveAt + 1).flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : []);
    const key = `${session}:${directiveAt}:${kind}:${label}`;
    if (!directivePlans.has(key)) {
      let phase = null;
      let plan = [];
      if (kind === "prompt") plan = plans[label] ?? [];
      else if (kind === "goal-start" || kind === "goal-feedback") { phase = phases[lead]; plan = goalPlans[lead]?.[phase] ?? []; }
      else if (kind === "task-notification") {
        const owner = Object.keys(notificationPlans).find((name) => sessionsByLead[name] === session) ?? null;
        const index = (notificationCounts.get(session) ?? 0) + 1;
        notificationCounts.set(session, index);
        phase = owner ? `notification-${index}` : null;
        plan = owner ? notificationPlans[owner](index) : [];
      }
      directivePlans.set(key, { phase, plan });
    }
    const { phase, plan } = directivePlans.get(key);
    const step = plan[results.length] ?? null;
    const tools = payload.tools?.map((tool) => tool.name) ?? [];
    const available = step ? tools.includes(step.tool) : null;
    // A check-in or other harness text names no label: its opening words
    // are Claude Code's own and are kept, scrubbed, to name it.
    const request = trace("model.request", { session, directiveKind: kind, label, lead, phase, step: results.length, tool: step?.tool ?? null, available,
      directiveAt, messages: messages.length, opening: kind === "other" || kind === "task-notification" ? clean(text.slice(0, 160)) : undefined,
      markers: [...new Set(messages.flatMap((message) => textOf(message).match(/(SPIKE|DONE):[a-z0-9-]+/g) ?? []))].slice(-6) });
    modelRequests.push(request);
    response = step && available ? { type: "tool_use", id: `toolu_${label}_${records.length}`, name: step.tool, input: step.input }
      : { type: "text", text: label ? `DONE:${label}` : "Fixture complete." };
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model, content: [response],
      stop_reason: response.type === "tool_use" ? "tool_use" : "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model, content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (response.type === "tool_use") {
    sse("content_block_start", { index: 0, content_block: { type: "tool_use", id: response.id, name: response.name, input: {} } });
    sse("content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(response.input) } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: response.text } });
  }
  sse("content_block_stop", { index: 0 });
  sse("message_delta", { delta: { stop_reason: response.type === "tool_use" ? "tool_use" : "end_turn", stop_sequence: null }, usage: { output_tokens: 4 } });
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// Subscribe the hook exactly as `dashpot integrate claude-code` does.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import integration; c = integration('claude-code'); print(json.dumps({'events': c.events, 'matched': c.matched_events}))"], { encoding: "utf8" }));
const handler = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")}`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: { [fixture]: { hasTrustDialogAccepted: true, allowedTools: [] } },
}, null, 2));

const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CLAUDE_CONFIG_DIR=${env.CLAUDE_CONFIG_DIR}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const observe = (label, extra = {}) => {
  let snapshot = null;
  let error = null;
  try { snapshot = JSON.parse(execFileSync(dashpot, ["--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 })); } catch (failure) { error = clean(String(failure).slice(0, 500)); }
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, issueId, workingDirectory, turnStartedAt, orphaned }) =>
    ({ harness, processOrSession, state, issueId, workingDirectory, turnStartedAt, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((project) => project.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: clean(String(message ?? "")).slice(0, 300) }));
  return trace("observation", { label, error, runs, diagnostics, ...extra });
};
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const leadHooks = (session, event, since = 0) => hooks().filter((record) => record.receiptTime >= since && record.payload.session_id === session && record.event === event && !record.payload.agent_id);
const subagentStops = (session, since = 0) => hooks().filter((record) => record.receiptTime >= since && record.payload.session_id === session && record.event === "SubagentStop");
const evaluationsOf = (lead, since = 0) => evaluations.filter((record) => record.lead === lead && record.receiptTime >= since);

// A headless Lead: one `claude -p` process taking its user turns as
// stream-json on stdin. Its result lines and system notices are kept by
// type and subtype; a notice's text is Claude Code's own and is kept.
const client = async (name, extraEnv = {}) => {
  const child = spawn(launcher, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--dangerously-skip-permissions", "--model", "fixture-model"],
    { cwd: fixture, env: { ...env, ...extraEnv }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, exited: null, results: 0 };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      let message = null;
      try { message = JSON.parse(line); } catch { continue; }
      if (message.session_id && !state.session) state.session = message.session_id;
      if (message.type === "result") { state.results += 1; trace("client.result", { client: name, subtype: message.subtype, stopReason: message.stop_reason ?? null, numTurns: message.num_turns ?? null }); }
      if (message.type === "system" && !["init", "hook_started", "hook_response", "task_progress"].includes(message.subtype)) trace("client.system", { client: name, subtype: message.subtype, key: message.key ?? null, text: clean(String(message.text ?? message.content ?? "")).slice(0, 300) });
      if (message.type === "user" && message.isSynthetic) trace("client.synthetic", { client: name, opening: clean(textOf(message.message ?? {}).slice(0, 120)) });
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, pid: child.pid, extraEnv });
  state.send = (text) => {
    trace("client.send", { client: name, text: text.startsWith("/goal") ? `/goal ${text.match(/SPIKE:[a-z0-9-]+/)?.[0]}` : text });
    child.stdin.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text }] } }) + "\n");
  };
  state.untilResult = async (before, label, timeout = 120000) => { await waitFor(() => state.results > before, `${name} ${label} result`, timeout); };
  return state;
};

try {
  trace("environment", { version, expectedVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(home, "~"), binarySHA256: sha(readFileSync(binary)),
    subscriptions: integration, init: clean(initialized).slice(0, 300),
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key.startsWith("ANTHROPIC_DEFAULT"))),
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    experimentDirty: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", path.relative(checkout, here)], { encoding: "utf8" }).trim() !== "",
    sourceSHA256: Object.fromEntries([...["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) => [file, path.join(here, file)]),
      ...["harnesses.py", "hook_publish.py", "work_reconciliation.py", "hook_records.py", "work.py"].map((file) => [`src/dashpot/sessions/${file}`, path.join(checkout, "src", "dashpot", "sessions", file)])]
      .map(([name, file]) => [name, sha(readFileSync(file))])) });

  // C1: a goal phrased as the skill's end, with two background Workers.
  trace("scenario", { name: "c1-background-workers" });
  const c1 = await client("c1");
  c1.send("SPIKE:c1-bind");
  await c1.untilResult(0, "bind");
  sessionsByLead.c1 = c1.session;
  observe("c1-bound");
  const goalAt = Date.now();
  const beforeGoal = c1.results;
  c1.send(`/goal ${condition("c1")}`);
  phases.c1 = "start";
  await waitFor(() => command("wa") && command("wb"), "C1's Workers run", 60000);
  phases.c1 = "workers";
  await quietly(c1.untilResult(beforeGoal, "goal start", 30000));
  await delay(3000);
  observe("c1-workers-running", { evaluations: evaluationsOf("c1", goalAt).length });
  await waitFor(() => command("wa", "end"), "worker A ends", 60000);
  await quietly(waitFor(() => command("c1-notified"), "C1's first notification turn runs a command", 30000));
  await delay(2000);
  observe("c1-notification-turn", { evaluations: evaluationsOf("c1", goalAt).length });
  await waitFor(() => command("wb", "end"), "worker B ends", 90000);
  const workersDoneAt = Date.now();
  phases.c1 = "continue";
  await quietly(waitFor(() => command("c1-continuation"), "C1's continuation runs a command", 60000));
  await delay(3000);
  observe("c1-continuation-running", { evaluations: evaluationsOf("c1", goalAt).length });
  phases.c1 = "met";
  await quietly(waitFor(() => evaluationsOf("c1").some((record) => record.verdict.ok), "C1's goal met", 60000));
  await delay(4000);
  observe("c1-goal-met");
  // A prompt after the goal is met: no evaluation follows if it cleared.
  const afterMetAt = Date.now();
  const beforeAfter = c1.results;
  c1.send("SPIKE:c1-after");
  await quietly(c1.untilResult(beforeAfter, "after", 60000));
  await delay(2000);
  trace("c1.outcome", { session: c1.session, goalAt, workersDoneAt, afterMetAt, evaluationsAfterMet: evaluationsOf("c1", afterMetAt).length,
    evaluations: evaluationsOf("c1").map((record) => [record.receipt, record.phase, record.verdict.ok, record.hookInput?.stopHookActive, record.hookInput?.backgroundTasks]),
    stops: leadHooks(c1.session, "Stop").map((record) => [record.receipt, record.payload.stop_hook_active ?? null, record.backgroundTasks?.count ?? null]),
    prompts: leadHooks(c1.session, "UserPromptSubmit").map((record) => record.receipt) });
  c1.child.stdin.end();
  await quietly(waitFor(() => c1.exited, "C1 exits", 30000));

  // C2: an evaluator that never says met.
  trace("scenario", { name: "c2-never-met" });
  const c2 = await client("c2");
  c2.send("SPIKE:c2-hello");
  await c2.untilResult(0, "hello");
  sessionsByLead.c2 = c2.session;
  const c2GoalAt = Date.now();
  const c2Before = c2.results;
  c2.send(`/goal ${condition("c2")}`);
  // Twelve continuations with a command each; then text only.
  await quietly(waitFor(() => commands().filter((record) => record.label === "c2-progress" && record.phase === "end").length >= 12 || c2.results > c2Before, "twelve C2 continuations with a command", 180000));
  const toolRounds = commands().filter((record) => record.label === "c2-progress" && record.phase === "end").length;
  const endedDuringTools = c2.results > c2Before;
  phases.c2 = "idle";
  const idleAt = Date.now();
  await quietly(c2.untilResult(c2Before, "goal turn ends", 180000));
  const endedAt = Date.now();
  await delay(2000);
  observe("c2-turn-ended");
  const c2AfterAt = Date.now();
  const beforeAfter2 = c2.results;
  c2.send("SPIKE:c2-after");
  await quietly(waitFor(() => evaluationsOf("c2", c2AfterAt).length > 0 || c2.results > beforeAfter2, "C2 after prompt evaluated or ended", 60000));
  phases.c2 = "impossible";
  await quietly(c2.untilResult(beforeAfter2, "after", 120000));
  await delay(2000);
  const finalAt = Date.now();
  const beforeFinal = c2.results;
  c2.send("SPIKE:c2-final");
  await quietly(c2.untilResult(beforeFinal, "final", 60000));
  await delay(2000);
  trace("c2.outcome", { session: c2.session, c2GoalAt, toolRounds, endedDuringTools, idleAt, endedAt, c2AfterAt, finalAt,
    evaluationsDuringTools: evaluationsOf("c2", c2GoalAt).filter((record) => record.receiptTime < idleAt).length,
    evaluationsWhileIdle: evaluationsOf("c2", idleAt).filter((record) => record.receiptTime < endedAt).length,
    evaluationsAfterPrompt: evaluationsOf("c2", c2AfterAt).filter((record) => record.receiptTime < finalAt).map((record) => [record.verdict.ok, record.verdict.impossible ?? false]),
    evaluationsAfterFinal: evaluationsOf("c2", finalAt).length,
    stops: leadHooks(c2.session, "Stop").length, prompts: leadHooks(c2.session, "UserPromptSubmit").length });
  c2.child.stdin.end();
  await quietly(waitFor(() => c2.exited, "C2 exits", 30000));

  // C3: a one-minute check-in interval while one Worker runs long.
  trace("scenario", { name: "c3-check-in" });
  const c3 = await client("c3", { CLAUDE_CODE_GOAL_CHECKIN_MINUTES: "1" });
  c3.send("SPIKE:c3-hello");
  await c3.untilResult(0, "hello");
  sessionsByLead.c3 = c3.session;
  const c3GoalAt = Date.now();
  c3.send(`/goal ${condition("c3")}`);
  await waitFor(() => command("wc") && command("wd"), "C3's Workers run", 60000);
  phases.c3 = "workers";
  await delay(30000);
  observe("c3-waiting", { evaluations: evaluationsOf("c3", c3GoalAt).length });
  await waitFor(() => command("wc", "end"), "worker C ends", 120000);
  const c3FirstDoneAt = Date.now();
  await waitFor(() => command("wd", "end"), "worker D ends", 120000);
  const c3DoneAt = Date.now();
  phases.c3 = "met";
  await quietly(waitFor(() => evaluationsOf("c3").some((record) => record.verdict.ok), "C3's goal met", 60000));
  await delay(3000);
  observe("c3-goal-met");
  trace("c3.outcome", { session: c3.session, c3GoalAt, c3FirstDoneAt, c3DoneAt,
    requestsWhileWaiting: modelRequests.filter((record) => record.session === c3.session && record.receiptTime > c3GoalAt + 5000 && record.receiptTime < c3DoneAt).map((record) => [record.directiveKind, record.opening ?? null]),
    evaluationsWhileWaiting: evaluationsOf("c3", c3GoalAt + 5000).filter((record) => record.receiptTime < c3DoneAt).length,
    evaluations: evaluationsOf("c3").map((record) => [record.receipt, record.verdict.ok, record.hookInput?.backgroundTasks]) });
  c3.child.stdin.end();
  await quietly(waitFor(() => c3.exited, "C3 exits", 30000));
  await delay(5000);
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { process: [entry.pid, entry.ppid, entry.comm] });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const gained = daemonEntries().filter((name) => !daemonBefore.has(name));
  trace("summary", { processes: fixtureProcesses().map((entry) => [entry.pid, entry.comm]), daemonEntriesGained: gained.length });
  if (gained.length) console.log(`Entries gained in the shared daemon directory (left in place): ${gained.join(", ")}`);
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
