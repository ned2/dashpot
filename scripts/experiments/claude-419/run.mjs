// Worker-mechanics run for Issue #419: how a Claude Code lead session
// launches background sub-agent workers, hears from them mid-flight and on
// completion, resumes them, and what Dashpot observes of them. Drives a pinned
// Claude Code binary against a loopback Messages API fixture with an isolated
// configuration, in headless stream-json, single-prompt `-p`, interactive
// (pseudo-terminal) and `--bg` launches. The fixture model emits the tool
// calls a lead and its workers would (`Agent`, `SendMessage`, `EnterWorktree`,
// `Skill`), selected by `SPIKE:<label>` in the latest user turn; a worker's
// final message and a lead's messages carry the next label, so a wrapped
// delivery starts the reaction it names. Every hook event goes to this
// checkout's real Claude Code publisher, subscribed as `dashpot integrate
// claude-code` subscribes it, and the shells run this checkout's `dashpot
// work` commands. The trace is metadata only: prompts and transcripts stay
// out, apart from the fixture's own labels and the harness's wrapper text
// around them. The verifier checks the trace against the spike's claims.
//
// Usage: node run.mjs <absolute claude binary> [expected version]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-419-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree, where every lead starts, and a linked
// Worktree beside it, where the workers are told to work.
const fixture = path.join(root, "repository");
const sibling = path.join(root, "repository.worktrees", "sibling");
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
const expectedVersion = process.argv[3] ?? "2.1.287";
const selected = process.env.SPIKE_SCENARIOS ? new Set(process.env.SPIKE_SCENARIOS.split(",")) : null;
const dashpot = path.join(checkout, ".venv", "bin", "dashpot");
const publisher = path.join(checkout, ".venv", "bin", "dashpot-claude-code-hook");
const python = path.join(checkout, ".venv", "bin", "python");

// A Claude Code session above the runner would be the host Dashpot finds for
// any fixture process it does not recognise, so the runner refuses to start
// below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every Claude Code session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const launcherDirectory = path.join(root, "bin");
mkdirSync(launcherDirectory);
const launcher = path.join(launcherDirectory, "claude");
symlinkSync(binary, launcher);
const home = path.join(root, "home");
const env = {
  PATH: `${launcherDirectory}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: home,
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  // The default layout: the configuration directory is the home's `.claude`,
  // so the skills directory `dashpot integrate claude-code` installs into is
  // the one this configuration reads.
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
  SPIKE_DASHPOT: dashpot,
  SPIKE_PUBLISHER: publisher,
  SPIKE_GATES: gates,
};
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Dashpot Project with a markdown Issue Source, one Issue per binding.
const issues = Array.from({ length: 12 }, (_, index) => `issue-${index + 1}`);
mkdirSync(path.join(fixture, ".dashpot"), { recursive: true });
mkdirSync(path.join(fixture, "issues"), { recursive: true });
writeFileSync(path.join(fixture, ".dashpot", "config.json"), JSON.stringify({ projectId: "project:fixture", displayLabel: "Fixture", repositoryId: "repository:fixture", issueSource: { kind: "markdown", path: "issues" } }));
issues.forEach((reference, index) => {
  const number = index + 1;
  const front = { id: `I_fixture_${number}`, number, reference, state: "open", stateReason: null, labels: [], assignees: [], author: "fixture",
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${reference}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
});
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.claude/\n");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "sibling", sibling);

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

// Read from this checkout's integration: the hook subscriptions and the
// skills directory `dashpot integrate claude-code` uses for this home.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import CLAUDE_CODE as c; print(json.dumps({'events': c.events, 'matched': c.matched_events, 'skills': str(c.default_skills_home)}))"],
  { encoding: "utf8", env: { ...env, PATH: "/usr/bin:/bin" } }));
assert.equal(integration.skills, path.join(env.CLAUDE_CONFIG_DIR, "skills"));
const handler = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")}`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: Object.fromEntries([fixture, sibling].map((dir) => [dir, { hasTrustDialogAccepted: true, allowedTools: [] }])),
}, null, 2));
// The bundled Issue-work skill, copied where `integrate` installs it, and two
// fixture skills beside it: one the model may invoke, one only the user may.
cpSync(path.join(checkout, "src", "dashpot", "skills", "dashpot-issue-work"), path.join(integration.skills, "dashpot-issue-work"), { recursive: true });
const fixtureSkill = (name, description, extra) => {
  mkdirSync(path.join(integration.skills, name), { recursive: true });
  writeFileSync(path.join(integration.skills, name, "SKILL.md"),
    `---\nname: ${name}\ndescription: ${description}\n${extra}---\n\n${name.toUpperCase()}-BODY\n`);
};
fixtureSkill("fixture-model-skill", "A fixture skill the model may invoke. FIXTURE-MODEL-SKILL-LISTED", "");
fixtureSkill("fixture-user-skill", "A fixture skill only the user may invoke. FIXTURE-USER-SKILL-LISTED", "disable-model-invocation: true\n");

// The fixture model.
const node = process.execPath;
const commandScript = path.join(here, "command.mjs");
const bash = (command) => ({ tool: "Bash", input: { command, description: "Fixture step" } });
const report = (label, hold = 200) => bash(`${node} ${commandScript} ${label} ${hold}`);
const gated = (label, gate) => bash(`${node} ${commandScript} ${label} wait ${gate}`);
const work = (label, ...args) => bash(`${node} ${commandScript} ${label} -- work ${args.join(" ")}`);
const inDir = (dir, step) => bash(`cd ${dir} && ${step.input.command}`);
const delegate = (child, description = `Fixture ${child}`) => ({ tool: "Agent", input: { description, prompt: `SPIKE:${child}`, subagent_type: "general-purpose", run_in_background: true } });
const send = (to, message) => ({ tool: "SendMessage", input: { to, summary: "Fixture message", message } });
const enter = (input) => ({ tool: "EnterWorktree", input });
const exit = (action) => ({ tool: "ExitWorktree", input: { action } });
const skill = (name) => ({ tool: "Skill", input: { skill: name } });
const stop = (id) => ({ tool: "TaskStop", input: { task_id: id } });
const sequences = {};
const watchedTools = new Set(["Agent", "SendMessage", "EnterWorktree", "ExitWorktree", "Skill", "TaskStop"]);
const textParts = (content) => typeof content === "string" ? [content] : (content ?? []).filter((part) => part.type === "text").map((part) => part.text ?? "");
const resultText = (part) => typeof part.content === "string" ? part.content : (part.content ?? []).map((item) => item.text ?? "").join(" ");
const hasResult = (message) => Array.isArray(message.content) && message.content.some((part) => part.type === "tool_result");
const labelsIn = (text) => [...text.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]);
const marksIn = (text) => [...text.matchAll(/MARK:([a-z0-9-]+)/g)].map((match) => match[1]);
// What a delivered text says, without the conversation around it.
const delivery = (text) => {
  const notification = text.match(/<task-notification>([\s\S]*?)<\/task-notification>/);
  const field = (name) => notification?.[1].match(new RegExp(`<${name}>([\\s\\S]*?)</${name}>`))?.[1];
  return {
    agentMessage: text.match(/<agent-message from="([^"]*)"/)?.[1] ?? null,
    crossSession: text.includes("<cross-session-message"),
    interrupted: text.includes("[Request interrupted"),
    notification: notification ? { taskId: field("task-id"), status: field("status"), summary: field("summary"), result: field("result")?.slice(0, 200), outputFile: Boolean(field("output-file")) } : null,
    labels: labelsIn(text), marks: marksIn(text), head: retained(text).slice(0, 240),
  };
};
const seenLength = new Map();
const seenTools = new Set();
let agentSchemaSeen = false;
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
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  // The conversation is named by its first label; the turn by the latest
  // user message whose text carries one. A delivery the harness folds into a
  // tool result's message starts its turn there too.
  let conversation = null;
  let trigger = -1;
  let label = null;
  messages.forEach((message, index) => {
    if (message.role !== "user") return;
    const labels = textParts(message.content).flatMap(labelsIn);
    if (!labels.length) return;
    conversation ??= labels[0];
    trigger = index;
    label = labels.at(-1);
  });
  const done = messages.slice(trigger + 1).filter((message) => message.role === "user" && hasResult(message)).length;
  const sequence = (label && sequences[label]) || null;
  let step = sequence?.steps[done] ?? null;
  // A worker's agentId, from the latest Agent result in this conversation.
  const agentIds = messages.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : [])
    .map((part) => resultText(part).match(/agentId: ([a-z0-9]+)/)?.[1]).filter(Boolean);
  const resolve = (item) => JSON.parse(JSON.stringify(item).replaceAll("$AGENT_ID", agentIds.at(-1) ?? "none"));
  const steps = step ? (Array.isArray(step) ? step : [step]).map(resolve) : [];
  const available = steps.every((item) => tools.includes(item.tool));
  // What arrived since this conversation's previous request: new tool
  // results of the watched tools, and delivered harness wrappers or marks.
  const key = conversation ?? "none";
  const previous = seenLength.get(key) ?? 0;
  seenLength.set(key, messages.length);
  const uses = new Map(messages.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_use") : []).map((use) => [use.id, use]));
  const fresh = messages.slice(Math.min(previous, messages.length));
  const outcomes = fresh.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : [])
    .map((part) => ({ part, use: uses.get(part.tool_use_id) })).filter(({ use }) => use && watchedTools.has(use.name))
    .map(({ part, use }) => ({ tool: use.name, input: { to: use.input.to, path: use.input.path, name: use.input.name, skill: use.input.skill, action: use.input.action },
      isError: part.is_error ?? null, text: retained(resultText(part)).slice(0, 600) }));
  const deliveries = [];
  fresh.forEach((message, offset) => {
    if (message.role === "assistant") return;
    const index = previous + offset;
    const parts = typeof message.content === "string" ? [{ text: message.content, inResult: false }]
      : (message.content ?? []).flatMap((part) => part.type === "text" ? [{ text: part.text ?? "", inResult: false }]
        : part.type === "tool_result" ? [{ text: resultText(part), inResult: true }] : []);
    for (const { text, inResult } of parts) {
      const found = delivery(text);
      if (index === trigger && !found.agentMessage && !found.notification && !found.crossSession && !found.interrupted && !found.marks.length) continue;
      if (found.agentMessage || found.notification || found.crossSession || found.interrupted || found.marks.length || found.labels.length)
        deliveries.push({ index, role: message.role, inResult, withToolResult: hasResult(message), trigger: index === trigger, ...found });
    }
  });
  const everything = JSON.stringify([payload.system, messages]);
  // The Agent tool's parameters and what it says of background launches, once.
  const agentTool = payload.tools?.find((tool) => tool.name === "Agent");
  const agentSchema = agentTool && !agentSchemaSeen ? { parameters: Object.keys(agentTool.input_schema?.properties ?? {}),
    runInBackground: agentTool.input_schema?.properties?.run_in_background?.description?.slice(0, 300) } : undefined;
  if (agentSchema) agentSchemaSeen = true;
  const first = !seenTools.has(key);
  seenTools.add(key);
  trace("model.request", { conversation, label, step: done, tools: steps.map((item) => item.tool), available: steps.length ? available : null,
    messages: messages.length, toolUses: uses.size, stream: Boolean(payload.stream), toolCount: tools.length,
    available_tools: first ? tools : undefined, agentSchema,
    // The skill markers this request's system prompt and messages carry.
    skills: Object.entries({ issueWork: "dashpot-issue-work", modelListed: "FIXTURE-MODEL-SKILL-LISTED", userListed: "FIXTURE-USER-SKILL-LISTED",
      modelBody: "FIXTURE-MODEL-SKILL-BODY", userBody: "FIXTURE-USER-SKILL-BODY" }).filter(([, marker]) => everything.includes(marker)).map(([name]) => name),
    outcomes: outcomes.length ? outcomes : undefined, deliveries: deliveries.length ? deliveries : undefined });
  const final = sequence && done >= sequence.steps.length ? sequence.final ?? "Fixture complete." : "Fixture complete.";
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [{ type: "text", text: "Fixture complete." }],
      stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (steps.length && available) {
    steps.forEach((item, index) => {
      sse("content_block_start", { index, content_block: { type: "tool_use", id: `toolu_${label}_${records.length}_${index}`, name: item.tool, input: {} } });
      sse("content_block_delta", { index, delta: { type: "input_json_delta", partial_json: JSON.stringify(item.input) } });
      sse("content_block_stop", { index });
    });
    sse("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { output_tokens: 20 } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: steps.length ? "Fixture tool unavailable." : final } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 4 } });
  }
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// Runner helpers.
const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "end") => commands().find((record) => record.label === label && record.phase === phase);
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
const stopsOf = (session) => hooks().filter((record) => record.payload.session_id === session && record.event === "Stop" && !record.payload.agent_id).length;
const sessionHooks = (session, since) => hooks().filter((record) => record.receipt > since && record.payload.session_id === session)
  .map((record) => ({ event: record.event, agent: record.payload.agent_id ?? null, reason: record.payload.reason ?? record.payload.source ?? null, cwd: record.payload.cwd, prompt: record.prompt }));
const mark = () => records.length;
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
const claude = async (args, options = {}) => {
  const child = spawn(launcher, args, { cwd: options.cwd ?? fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), options.timeout ?? 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  trace("action.claude", { args, cwd: options.cwd ?? fixture, status, signal, stdout: stdout.slice(-1000), stderr: stderr.slice(-1000) });
  return { status, stdout, stderr };
};
const stateFiles = () => Object.fromEntries([fixture, sibling].map((worktree) => {
  const directory = path.join(worktree, ".dashpot", "state");
  const files = [];
  const walk = (dir) => {
    let entries;
    try { entries = readdirSync(dir); } catch { return; }
    for (const entry of entries) {
      const full = path.join(dir, entry);
      if (statSync(full).isDirectory()) walk(full); else if (!full.includes(`${path.sep}events${path.sep}`)) files.push(path.relative(directory, full));
    }
  };
  walk(directory);
  return [worktree, files.sort()];
}));
// What a person's dashboard reads, and what Cleanup reports for the sibling.
const observe = (label) => {
  let snapshot = null;
  let error = null;
  try { snapshot = JSON.parse(execFileSync(dashpot, ["--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 })); } catch (failure) { error = String(failure).slice(0, 500); }
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((project) => project.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: retained(message).slice(0, 300) }));
  let check = null;
  try {
    const parsed = JSON.parse(execFileSync(dashpot, ["worktree", "check", "--json", sibling], { cwd: fixture, env, encoding: "utf8", timeout: 60000 }));
    check = { removable: parsed.removable, obstacles: parsed.obstacles.map(({ kind, detail }) => ({ kind, detail: retained(detail).slice(0, 500) })) };
  } catch (failure) {
    const output = failure.stdout ? (() => { try { return JSON.parse(failure.stdout); } catch { return null; } })() : null;
    check = output ? { removable: output.removable, obstacles: output.obstacles.map(({ kind, detail }) => ({ kind, detail: retained(detail).slice(0, 500) })) } : { error: String(failure).slice(0, 300) };
  }
  return trace("observation", { label, error, runs, diagnostics, check, stateFiles: stateFiles() });
};
const sessionStartAfter = (since, predicate = () => true) => hooks().find((record) => record.receipt > since && record.event === "SessionStart" && predicate(record));

// The stream messages an SDK host acts on: the session's and its tasks'
// system messages and each turn's result, not the conversation itself.
const streamed = (message) => message.type !== "stream_event" && message.type !== "assistant" && message.type !== "user"
  && message.subtype !== "hook_started" && message.subtype !== "hook_response";
// A headless client: one `claude -p` process taking its user turns as
// stream-json on stdin. Its stream's message kinds are traced, so what an
// SDK host sees of background work is on record.
const headless = (name, cwd, extraEnv = {}) => {
  const child = spawn(launcher, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", ...commonArgs],
    { cwd, env: { ...env, ...extraEnv }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, exited: null, mode: "headless" };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      try {
        const message = JSON.parse(line);
        if (message.session_id && !state.session) state.session = message.session_id;
        if (streamed(message)) trace("client.stream", { client: name, type: message.type, subtype: message.subtype ?? null, status: message.status ?? undefined,
          taskId: message.task_id ?? undefined, result: typeof message.result === "string" ? retained(message.result).slice(0, 120) : undefined });
      } catch {}
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal, at: Date.now() }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, mode: "headless", cwd, pid: child.pid, extraEnv });
  state.send = (text) => child.stdin.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text }] } }) + "\n");
  state.turn = async (text, wait = true) => {
    const before = state.session ? stopsOf(state.session) : 0;
    state.send(text);
    trace("turn.sent", { client: name, text });
    if (wait) await waitFor(() => state.session && stopsOf(state.session) > before, `${name} ${text} Stop`, 90000);
  };
  state.interrupt = () => {
    child.stdin.write(JSON.stringify({ type: "control_request", request_id: "fixture-interrupt", request: { subtype: "interrupt" } }) + "\n");
    trace("action.interrupt", { client: name, how: "control_request interrupt" });
  };
  state.end = () => { child.stdin.end(); trace("action.end", { client: name, how: "close stdin" }); };
  return state;
};

// An interactive client on a pseudo-terminal, typed into as a person would.
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
const interactive = async (name, cwd) => {
  const since = mark();
  const child = spawn("script", ["-qfec", [launcher, ...commonArgs].join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, exited: null, mode: "interactive", output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); if (state.output.length > 200000) state.output = state.output.slice(-100000); });
  child.on("exit", (status, signal) => { state.exited = { status, signal, at: Date.now() }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, mode: "interactive", cwd, pid: child.pid });
  try {
    await waitFor(() => sessionStartAfter(since, (record) => record.ancestry.some((entry) => entry.pid === child.pid)), `${name} SessionStart`, 60000);
  } catch (error) {
    writeFileSync(path.join(root, `screen-${name}.txt`), state.output);
    throw error;
  }
  state.session = sessionStartAfter(since, (record) => record.ancestry.some((entry) => entry.pid === child.pid)).payload.session_id;
  state.claudePid = Number(sessionStartAfter(since, (record) => record.ancestry.some((entry) => entry.pid === child.pid)).env.CLAUDE_PID);
  await delay(3000);
  state.type = async (text) => { child.stdin.write(text); await delay(400); child.stdin.write("\r"); };
  state.turn = async (text, wait = true) => {
    const before = stopsOf(state.session);
    await state.type(text);
    trace("turn.sent", { client: name, text });
    if (wait) {
      try { await waitFor(() => stopsOf(state.session) > before, `${name} ${text} Stop`, 90000); } catch (error) {
        writeFileSync(path.join(root, `screen-${name}.txt`), state.output);
        throw error;
      }
    }
  };
  state.screen = (label) => trace("screen", { client: name, label, tail: retained(state.output.slice(-700)).replace(/\s+/g, " ") });
  state.interrupt = () => { child.stdin.write("\u001b"); trace("action.interrupt", { client: name, how: "Escape on the terminal" }); };
  state.end = async () => { await state.type("/exit"); trace("action.end", { client: name, how: "/exit typed" }); };
  state.close = () => { child.kill("SIGKILL"); trace("action.close", { client: name, how: "terminal closed (script killed)" }); };
  return state;
};

// A single-prompt `claude -p` launch.
const single = (name, label, cwd) => {
  const child = spawn(launcher, ["-p", `SPIKE:${label}`, "--output-format", "stream-json", "--verbose", ...commonArgs], { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, session: null, exited: null, mode: "single" };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      try {
        const message = JSON.parse(line);
        if (message.session_id && !state.session) state.session = message.session_id;
        if (streamed(message)) trace("client.stream", { client: name, type: message.type, subtype: message.subtype ?? null, status: message.status ?? undefined,
          taskId: message.task_id ?? undefined, result: typeof message.result === "string" ? retained(message.result).slice(0, 120) : undefined });
      } catch {}
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal, at: Date.now() }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, mode: "single", cwd, pid: child.pid, label });
  return state;
};

// A `--bg` lead under the background supervisor.
const agentsJSON = async (label) => {
  const result = await claude(["agents", "--json", "--all"], { timeout: 30000 });
  let parsed = null;
  try { parsed = JSON.parse(result.stdout); } catch {}
  const agents = (parsed ?? []).filter((entry) => entry.kind === "background")
    .map(({ id, name, pid, sessionId, state, status, cwd }) => ({ id, name, pid, sessionId, state, status, cwd }));
  trace("agents", { label, agents });
  return agents;
};
const background = async (name, label) => {
  const dispatched = await claude(["--bg", `SPIKE:${label}`, "--name", name, ...commonArgs], { cwd: fixture });
  assert.equal(dispatched.status, 0, `dispatch ${name}: ${dispatched.stderr}`);
  let job;
  const end = Date.now() + 90000;
  while (Date.now() < end) {
    job = (await agentsJSON(`${name}-dispatched`)).find((entry) => entry.name === name && entry.sessionId);
    if (job && stopsOf(job.sessionId) > 0) break;
    await delay(1000);
  }
  assert(job && stopsOf(job.sessionId) > 0, `${name} stopped its first turn`);
  trace("background", { name, label, ...job });
  return { ...job, session: job.sessionId, mode: "background" };
};

// The sequences each launch mode runs, by label prefix.
const core = (p, leadIssue, workerIssue, resumeExtra = []) => Object.assign(sequences, {
  [`${p}-lead`]: { steps: [work(`${p}-lead-start`, "start", leadIssue), delegate(`${p}-worker`), report(`${p}-lead-after-dispatch`)], final: "Lead dispatched a worker." },
  [`${p}-worker`]: { steps: [gated(`${p}-w-start`, `${p}-go`), work(`${p}-w-show`, "show"), send("main", `SPIKE:${p}-lead-on-report MARK:${p}-report`),
    inDir(sibling, report(`${p}-w-cd`)), inDir(sibling, work(`${p}-w-start-sibling`, "start", workerIssue)), gated(`${p}-w-hold`, `${p}-release`), report(`${p}-w-after-hold`)],
  final: `SPIKE:${p}-lead-on-done MARK:${p}-final` },
  [`${p}-lead-on-report`]: { steps: [report(`${p}-lead-got-report`), send("$AGENT_ID", `MARK:${p}-broadcast`)], final: "Report noted." },
  [`${p}-lead-on-done`]: { steps: [report(`${p}-lead-got-done`), send("$AGENT_ID", `SPIKE:${p}-worker-resume MARK:${p}-resume`)], final: "Worker resumed." },
  [`${p}-worker-resume`]: { steps: [report(`${p}-w-resumed`), ...resumeExtra], final: `SPIKE:${p}-lead-on-resumed MARK:${p}-resumed-final` },
  [`${p}-lead-on-resumed`]: { steps: [report(`${p}-lead-got-resumed`)], final: "Arc done." },
});
const busy = (p) => Object.assign(sequences, {
  [`${p}-busy-lead`]: { steps: [delegate(`${p}-busy-worker`), gated(`${p}-busy-lead-hold`, `${p}-busy-lead-go`), report(`${p}-busy-lead-after`)], final: "Busy lead done." },
  [`${p}-busy-worker`]: { steps: [send("main", `MARK:${p}-busy-report`), report(`${p}-busy-w-sent`)], final: `MARK:${p}-busy-final` },
});
const interrupted = (p) => Object.assign(sequences, {
  [`${p}-int-lead`]: { steps: [delegate(`${p}-int-worker`), gated(`${p}-int-lead-hold`, `${p}-int-never`)], final: "Interrupted lead done." },
  [`${p}-int-worker`]: { steps: [gated(`${p}-int-w-hold`, `${p}-int-w-go`), report(`${p}-int-w-after`)], final: `SPIKE:${p}-int-lead-on-done MARK:${p}-int-final` },
  [`${p}-int-lead-on-done`]: { steps: [report(`${p}-int-lead-got-done`)], final: "Noted." },
  [`${p}-int-after`]: { steps: [report(`${p}-int-after`)], final: "After the interrupt." },
});
const ending = (p, issue = null) => Object.assign(sequences, {
  [`${p}-end-lead`]: { steps: [...(issue ? [work(`${p}-end-lead-start`, "start", issue)] : []), delegate(`${p}-end-worker`)], final: "Lead dispatched a worker." },
  [`${p}-end-worker`]: { steps: [gated(`${p}-end-w-hold`, `${p}-end-w-go`), report(`${p}-end-w-after`)], final: `MARK:${p}-end-final` },
});

const scenarios = [];
const scenario = (name, run) => scenarios.push({ name, run });

// The core arc: dispatch, a mid-flight report to an idle lead, a lead's
// message to a running worker, completion, and a resume of the finished
// worker. The worker tries `work start` from the sibling Worktree.
const runCore = async (p, client, start) => {
  await start();
  await waitCommand(`${p}-w-start`, "start");
  await waitFor(() => stopsOf(client.session) > 0, `${p} lead Stop`, 60000);
  await delay(1500);
  observe(`${p}-lead-idle-worker-live`);
  open(`${p}-go`);
  await waitCommand(`${p}-lead-got-report`);
  await waitCommand(`${p}-w-hold`, "start");
  await delay(2500);
  observe(`${p}-worker-holding`);
  open(`${p}-release`);
  await waitCommand(`${p}-lead-got-resumed`, "end", 120000);
  await delay(3000);
  observe(`${p}-arc-done`);
};
scenario("headless-core", async () => {
  core("h", "issue-1", "issue-2", [work("h-w-start-main", "start", "issue-3")]);
  const client = headless("h", fixture);
  await runCore("h", client, () => client.turn("SPIKE:h-lead", false).then(() => waitFor(() => client.session, "h session")));
  const since = mark();
  client.end();
  await settle(() => client.exited, "h exit", 60000);
  trace("ended", { client: "h", hooks: sessionHooks(client.session, since) });
  observe("h-ended");
});
scenario("single-core", async () => {
  core("p", "issue-4", "issue-5");
  let client;
  await runCore("p", { get session() { return client?.session; } }, async () => { client = single("p", "p-lead", fixture); await waitFor(() => client.session, "p session"); });
  await settle(() => client.exited, "p exit after the arc", 60000);
  observe("p-ended");
});
scenario("interactive-core", async () => {
  core("i", "issue-6", "issue-7");
  const client = await interactive("i", fixture);
  await runCore("i", client, () => client.turn("SPIKE:i-lead", false));
  const since = mark();
  await client.end();
  await settle(() => client.exited, "i exit after /exit", 30000);
  if (!client.exited) { client.screen("i-after-exit"); client.close(); await settle(() => client.exited, "i exit after close", 10000); }
  trace("ended", { client: "i", hooks: sessionHooks(client.session, since) });
  observe("i-ended");
});

// A report and a completion that arrive while the lead is in a tool call.
const runBusy = async (p, client) => {
  await client.turn(`SPIKE:${p}-busy-lead`, false);
  await waitCommand(`${p}-busy-lead-hold`, "start");
  await waitCommand(`${p}-busy-w-sent`);
  await waitFor(() => hooks().some((record) => record.event === "SubagentStop" && record.payload.session_id === client.session && record.receipt > command(`${p}-busy-w-sent`).receipt), `${p} busy SubagentStop`, 60000);
  await delay(2000);
  const since = mark();
  open(`${p}-busy-lead-go`);
  await waitCommand(`${p}-busy-lead-after`);
  await delay(6000);
  trace("busy.after", { client: p, hooks: sessionHooks(client.session, since) });
};
scenario("headless-busy", async () => {
  busy("h");
  const client = headless("hb", fixture);
  await runBusy("h", client);
  client.end();
  await settle(() => client.exited, "hb exit", 60000);
});
scenario("interactive-busy", async () => {
  busy("i");
  const client = await interactive("ib", fixture);
  await runBusy("i", client);
  await client.end();
  await settle(() => client.exited, "ib exit", 30000);
  if (!client.exited) client.close();
});

// The lead's turn is interrupted while its worker runs.
const runInterrupt = async (p, client) => {
  await client.turn(`SPIKE:${p}-int-lead`, false);
  await waitCommand(`${p}-int-lead-hold`, "start");
  await waitCommand(`${p}-int-w-hold`, "start");
  await delay(1000);
  const since = mark();
  client.interrupt();
  await delay(4000);
  const leadHold = command(`${p}-int-lead-hold`, "start");
  const workerHold = command(`${p}-int-w-hold`, "start");
  trace("interrupt.after", { client: p, hooks: sessionHooks(client.session, since), leadHoldAlive: alive(leadHold.pid), workerHoldAlive: alive(workerHold.pid), clientAlive: !client.exited });
  if (client.screen) client.screen(`${p}-interrupted`);
  observe(`${p}-int-interrupted`);
  open(`${p}-int-w-go`);
  await settle(() => command(`${p}-int-w-after`), `${p} worker continued after the interrupt`, 30000);
  await settle(() => command(`${p}-int-lead-got-done`), `${p} lead woke on the worker's completion`, 30000);
  await delay(2000);
  observe(`${p}-int-done`);
  open(`${p}-int-never`);
  // The lead's next turn: what it is told of a worker the interrupt stopped.
  await client.turn(`SPIKE:${p}-int-after`);
  await delay(2000);
  observe(`${p}-int-after`);
};
scenario("headless-interrupt", async () => {
  interrupted("h");
  const client = headless("hi", fixture);
  await runInterrupt("h", client);
  const since = mark();
  client.end();
  await settle(() => client.exited, "hi exit", 60000);
  await delay(2000);
  trace("ended", { client: "hi", hooks: sessionHooks(client.session, since) });
  observe("h-int-ended");
});
scenario("interactive-interrupt", async () => {
  interrupted("i");
  const client = await interactive("ii", fixture);
  await runInterrupt("i", client);
  const since = mark();
  await client.end();
  await settle(() => client.exited, "ii exit", 30000);
  if (!client.exited) { client.screen("ii-after-exit"); client.close(); await settle(() => client.exited, "ii exit after close", 10000); }
  await delay(2000);
  trace("ended", { client: "ii", hooks: sessionHooks(client.session, since) });
  observe("i-int-ended");
});

// The lead stops its running worker with TaskStop.
const runTaskStop = async (p, client) => {
  Object.assign(sequences, {
    [`${p}-ts-lead`]: { steps: [delegate(`${p}-ts-worker`)], final: "Lead dispatched a worker." },
    [`${p}-ts-worker`]: { steps: [gated(`${p}-ts-w-hold`, `${p}-ts-w-go`), report(`${p}-ts-w-after`)], final: `MARK:${p}-ts-final` },
    [`${p}-ts-stop`]: { steps: [stop("$AGENT_ID")], final: "Worker stopped." },
    [`${p}-ts-after`]: { steps: [report(`${p}-ts-after`)], final: "After the stop." },
  });
  await client.turn(`SPIKE:${p}-ts-lead`);
  await waitCommand(`${p}-ts-w-hold`, "start");
  await delay(1500);
  observe(`${p}-ts-worker-live`);
  const since = mark();
  const workerHold = command(`${p}-ts-w-hold`, "start");
  await client.turn(`SPIKE:${p}-ts-stop`);
  await delay(4000);
  trace("taskstop.after", { client: p, hooks: sessionHooks(client.session, since), workerHoldAlive: alive(workerHold.pid) });
  observe(`${p}-ts-stopped`);
  open(`${p}-ts-w-go`);
  await settle(() => command(`${p}-ts-w-after`), `${p} worker continued after TaskStop`, 10000);
  await client.turn(`SPIKE:${p}-ts-after`);
  await delay(2000);
  observe(`${p}-ts-after`);
};
scenario("headless-taskstop", async () => {
  const client = headless("hts", fixture);
  await runTaskStop("h", client);
  const since = mark();
  client.end();
  await settle(() => client.exited, "hts exit", 60000);
  await delay(2000);
  trace("ended", { client: "hts", hooks: sessionHooks(client.session, since) });
  observe("h-ts-ended");
});
scenario("interactive-taskstop", async () => {
  const client = await interactive("its", fixture);
  await runTaskStop("i", client);
  const since = mark();
  await client.end();
  await settle(() => client.exited, "its exit", 30000);
  if (!client.exited) { client.close(); await settle(() => client.exited, "its exit after close", 10000); }
  await delay(2000);
  trace("ended", { client: "its", hooks: sessionHooks(client.session, since) });
  observe("i-ts-ended");
});

// The lead's session ends while its worker runs.
const runEnd = async (p, client, end) => {
  await waitCommand(`${p}-end-w-hold`, "start");
  await delay(1500);
  observe(`${p}-end-worker-live`);
  const since = mark();
  const workerHold = command(`${p}-end-w-hold`, "start");
  const started = Date.now();
  await end();
  await delay(8000);
  trace("end.after", { client: p, hooks: sessionHooks(client.session, since), workerHoldAlive: alive(workerHold.pid), clientAlive: client.exited === undefined ? null : !client.exited,
    exitedAfterMs: client.exited?.at ? client.exited.at - started : null, processes: fixtureProcesses().map(({ pid, comm, cmdline }) => ({ pid, comm, cmdline: retained(cmdline) })) });
  if (client.screen && !client.exited) client.screen(`${p}-after-end`);
  observe(`${p}-end-ended`);
  open(`${p}-end-w-go`);
  await settle(() => command(`${p}-end-w-after`), `${p} worker continued after its lead ended`, 20000);
  if (client.exited === null) await settle(() => client.exited, `${p} exit once the worker was released`, 30000);
  await delay(2000);
  trace("end.final", { client: p, hooks: sessionHooks(client.session, since), clientAlive: client.exited === undefined ? null : !client.exited });
  observe(`${p}-end-final`);
};
scenario("headless-end", async () => {
  ending("h");
  const client = headless("he", fixture);
  await client.turn("SPIKE:h-end-lead");
  await runEnd("h", client, async () => client.end());
  if (!client.exited) { client.child.kill("SIGTERM"); await settle(() => client.exited, "he exit after SIGTERM", 15000); }
});
scenario("interactive-end", async () => {
  ending("i");
  const client = await interactive("ie", fixture);
  await client.turn("SPIKE:i-end-lead");
  await runEnd("i", client, async () => client.end());
  if (!client.exited) { client.close(); await settle(() => client.exited, "ie exit after close", 15000); }
});
// `/exit` with a running worker asks what to do with it; each answer in turn.
const answerExit = (client, p, choice) => async () => {
  await client.end();
  await delay(2500);
  client.screen(`${p}-exit-dialog`);
  client.child.stdin.write(choice);
  trace("action.answer", { client: client.name, choice });
  await delay(2000);
  if (!client.exited) { client.child.stdin.write("\r"); trace("action.answer", { client: client.name, choice: "Enter" }); }
};
scenario("interactive-exit-stop", async () => {
  ending("ix");
  const client = await interactive("ix", fixture);
  await client.turn("SPIKE:ix-end-lead");
  await runEnd("ix", client, answerExit(client, "ix", "1"));
  if (!client.exited) { client.screen("ix-final"); client.close(); await settle(() => client.exited, "ix exit after close", 15000); }
});
scenario("interactive-exit-background", async () => {
  ending("iy", "issue-10");
  const client = await interactive("iy", fixture);
  await client.turn("SPIKE:iy-end-lead");
  await runEnd("iy", client, answerExit(client, "iy", "2"));
  const forked = (await agentsJSON("iy-backgrounded"))[0];
  if (!client.exited) { client.screen("iy-final"); client.close(); await settle(() => client.exited, "iy exit after close", 15000); }
  // Attach to the session the move started and ask it what Issue work it holds.
  if (forked) {
    sequences["iy-fork-show"] = { steps: [work("iy-fork-show", "show")], final: "Fork checked." };
    const attached = spawn("script", ["-qfec", `${launcher} attach ${forked.id}`, "/dev/null"],
      { cwd: fixture, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
    let screen = "";
    attached.stdout.on("data", (chunk) => { screen += stripAnsi(String(chunk)); });
    trace("client.spawn", { name: "iy-attach", mode: "attach", pid: attached.pid, id: forked.id });
    await delay(5000);
    attached.stdin.write("SPIKE:iy-fork-show");
    await delay(400);
    attached.stdin.write("\r");
    trace("turn.sent", { client: "iy-attach", text: "SPIKE:iy-fork-show" });
    await settle(() => command("iy-fork-show"), "iy fork ran work show", 60000);
    await delay(2000);
    trace("screen", { client: "iy-attach", label: "iy-attached", tail: retained(screen.slice(-700)).replace(/\s+/g, " ") });
    observe("iy-fork-shown");
    attached.kill("SIGKILL");
    trace("action.close", { client: "iy-attach", how: "attach terminal closed (script killed)" });
    await delay(1000);
  }
  // The supervisor the move started removes its own directory under
  // /tmp/cc-daemon-<uid>/ when it is stopped rather than killed.
  await claude(["daemon", "stop", "--any"], { timeout: 30000 });
  await delay(2000);
  observe("iy-daemon-stopped");
});
scenario("interactive-close", async () => {
  ending("ic");
  const client = await interactive("ic", fixture);
  await client.turn("SPIKE:ic-end-lead");
  await runEnd("ic", client, async () => client.close());
});
scenario("background-stop", async () => {
  ending("bs");
  const job = await background("fixture-lead-stop", "bs-end-lead");
  const client = { session: job.session, exited: undefined };
  await runEnd("bs", client, () => claude(["stop", job.id], { timeout: 30000 }));
  await agentsJSON("bs-stopped");
});
scenario("background-rm", async () => {
  ending("br");
  const job = await background("fixture-lead-rm", "br-end-lead");
  const client = { session: job.session, exited: undefined };
  await runEnd("br", client, () => claude(["rm", job.id], { timeout: 30000 }));
  await agentsJSON("br-removed");
});

// A worker's EnterWorktree, by path and by name.
scenario("headless-enter", async () => {
  Object.assign(sequences, {
    "en-lead": { steps: [work("en-lead-start", "start", "issue-8"), delegate("en-worker")], final: "Lead dispatched a worker." },
    "en-worker": { steps: [report("en-w-before-enter"), enter({ path: sibling }), report("en-w-after-enter"), exit("keep"), report("en-w-after-exit")], final: "MARK:en-final" },
    "en-lead-check": { steps: [report("en-lead-cwd"), work("en-lead-show", "show")], final: "Checked." },
    "em-lead": { steps: [work("em-lead-start", "start", "issue-9"), delegate("em-worker")], final: "Lead dispatched a worker." },
    "em-worker": { steps: [enter({ name: "em-managed" }), report("em-w-after-enter"), exit("keep"), report("em-w-after-exit")], final: "MARK:em-final" },
    "em-lead-check": { steps: [report("em-lead-cwd"), work("em-lead-show", "show")], final: "Checked." },
  });
  for (const p of ["en", "em"]) {
    const client = headless(p, fixture);
    await client.turn(`SPIKE:${p}-lead`);
    await waitCommand(`${p}-w-after-exit`);
    await waitFor(() => hooks().some((record) => record.event === "SubagentStop" && record.payload.session_id === client.session), `${p} SubagentStop`, 60000);
    await delay(4000);
    observe(`${p}-worker-done`);
    await client.turn(`SPIKE:${p}-lead-check`);
    observe(`${p}-lead-checked`);
    client.end();
    await settle(() => client.exited, `${p} exit`, 60000);
  }
});

// Several workers at once, under the default cap and under a cap of two.
scenario("headless-concurrency", async () => {
  for (const [p, extraEnv] of [["cd", {}], ["c2", { CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS: "2" }]]) {
    Object.assign(sequences, {
      [`${p}-lead`]: { steps: [[1, 2, 3].map((n) => delegate(`${p}-w${n}`))], final: "Lead dispatched three workers." },
      ...Object.fromEntries([1, 2, 3].map((n) => [`${p}-w${n}`, { steps: [gated(`${p}-w${n}-hold`, `${p}-go`)], final: `MARK:${p}-w${n}-final` }])),
    });
    const client = headless(p, fixture, extraEnv);
    await client.turn(`SPIKE:${p}-lead`);
    await delay(5000);
    trace("concurrency", { client: p, extraEnv, holding: [1, 2, 3].filter((n) => command(`${p}-w${n}-hold`, "start")).map((n) => `w${n}`) });
    open(`${p}-go`);
    await delay(6000);
    client.end();
    await settle(() => client.exited, `${p} exit`, 60000);
  }
});

// Skills from the directory `integrate` installs into.
scenario("headless-skills", async () => {
  Object.assign(sequences, {
    "hs-model": { steps: [skill("fixture-model-skill"), skill("fixture-user-skill"), skill("dashpot-issue-work"), delegate("hs-worker")], final: "Skills tried." },
    "hs-worker": { steps: [skill("fixture-model-skill"), skill("fixture-user-skill")], final: "MARK:hs-final" },
  });
  const client = headless("hs", fixture);
  await client.turn("/fixture-user-skill SPIKE:hs-user");
  await client.turn("SPIKE:hs-model");
  await waitFor(() => hooks().some((record) => record.event === "SubagentStop" && record.payload.session_id === client.session), "hs SubagentStop", 60000);
  await delay(4000);
  client.end();
  await settle(() => client.exited, "hs exit", 60000);
});
scenario("interactive-skills", async () => {
  const client = await interactive("is", fixture);
  await client.turn("/fixture-user-skill SPIKE:is-user");
  await client.turn("/fixture-model-skill SPIKE:is-model");
  await client.end();
  await settle(() => client.exited, "is exit", 30000);
  if (!client.exited) client.close();
});

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), subscriptions: { events: integration.events, matched: integration.matched },
    skillsDirectory: integration.skills,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")),
    fixture, sibling, scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    sourceSHA256: Object.fromEntries([...["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"].map((file) => [file, path.join(here, file)]),
      ...["sessions/harnesses.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/hook_scan.py", "sessions/work.py", "sessions/work_reconciliation.py", "repository/cleanup/obstacles.py"]
        .map((file) => [`src/dashpot/${file}`, path.join(checkout, "src", "dashpot", file)]),
      ...["SKILL.md"].map((file) => [`src/dashpot/skills/dashpot-issue-work/${file}`, path.join(checkout, "src", "dashpot", "skills", "dashpot-issue-work", file)])]
      .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });
  for (const { name, run } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await run(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    // Nothing of one scenario runs into the next.
    for (const entry of fixtureProcesses()) { try { process.kill(entry.pid, "SIGKILL"); } catch {} }
    await delay(1000);
  }
  console.log(`Scenarios completed: ${root}`);
} finally {
  await claude(["daemon", "stop", "--any"], { timeout: 30000 }).catch(() => {});
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
