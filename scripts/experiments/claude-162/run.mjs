// Real-adapter acceptance run for Issue #162: Claude Code clients and
// supervised workers through Dashpot's shared runtime model (ADR 0067).
// Drives a pinned Claude Code binary against a loopback Messages API fixture
// with an isolated configuration directory. Every hook event goes to this
// checkout's real Claude Code publisher, subscribed exactly as `dashpot
// integrate claude-code` subscribes it, and the sessions' shells run this
// checkout's `dashpot work` commands, as the Issue-work skill does. Between
// steps the runner records what `dashpot --json` observes. The trace is
// metadata only; the runner asserts only what it needs to keep going, and
// the independent verifier checks the trace against the recorded claims.
//
// Usage: node run.mjs <absolute claude binary> [expected version]
// SPIKE_IDLE_MINUTES=<n> runs the idle-eviction scenario instead, waiting up
// to n minutes for the supervisor to retire an idle bound worker.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-162-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree, a sibling linked Worktree where Dashpot
// creates Issue Worktrees, and a linked Worktree nested inside the main one,
// which a persistent shell `cd` reaches without leaving the project.
const fixture = path.join(root, "repository");
const sibling = path.join(root, "repository.worktrees", "sibling");
const nested = path.join(fixture, "nested");
// A sibling no other scenario uses, for asking ExitWorktree to remove a
// Worktree the session entered by path.
const disposable = path.join(root, "repository.worktrees", "disposable");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, this directory, the
// checkout, and the operator's home by placeholder.
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.287";
const idleMinutes = Number(process.env.SPIKE_IDLE_MINUTES ?? 0);
const dashpot = path.join(checkout, ".venv", "bin", "dashpot");
const publisher = path.join(checkout, ".venv", "bin", "dashpot-claude-code-hook");
const python = path.join(checkout, ".venv", "bin", "python");

// Every process above the runner is outside the fixture. A Claude Code
// session among them would be the host Dashpot finds for any fixture process
// it does not recognise, so the runner refuses to start below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every Claude Code session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
// Clients start through a launcher named `claude`, as a person's do, so the
// process Dashpot recognises as their host is named as it is in use.
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
  DISABLE_AUTOUPDATER: "1",
  DISABLE_TELEMETRY: "1",
  DISABLE_ERROR_REPORTING: "1",
  DISABLE_BUG_COMMAND: "1",
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  CLAUDE_CODE_DISABLE_TERMINAL_TITLE: "1",
  TERM: "dumb",
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_PUBLISHER: publisher,
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Dashpot Project with a markdown Issue Source, one Issue per scenario that
// binds work, so no scenario's run is another's.
const issues = ["issue-1", "issue-2", "issue-3", "issue-4", "issue-5", "issue-6", "issue-7"];
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
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/nested/\n/.claude/\n");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "sibling", sibling);
git("worktree", "add", "-b", "nested", nested);
git("worktree", "add", "-b", "disposable", disposable);

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

// The fixture model: a `SPIKE:<label>` text in the latest user turn selects a
// fixed tool sequence, and the turn ends once every step has a tool result.
const commandScript = path.join(here, "command.mjs");
const bash = (command) => ({ tool: "Bash", input: { command, description: "Fixture step" } });
const report = (label, hold = 200) => bash(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => bash(`node ${commandScript} ${label} -- work ${args.join(" ")}`);
const enter = (input) => ({ tool: "EnterWorktree", input });
const exit = (action) => ({ tool: "ExitWorktree", input: { action } });
const delegate = (child, extra = {}) => ({ tool: "Agent", input: { description: `Fixture ${child}`, prompt: `SPIKE:${child}`, subagent_type: "general-purpose", ...extra } });
const sequences = {
  "unbound-move": [enter({ path: sibling }), report("unbound-entered"), exit("keep"), report("unbound-returned")],
  "bind-1": [work("c1-start", "start", "issue-1"), work("c1-show-main", "show")],
  "enter-sibling": [enter({ path: sibling }), work("c1-show-sibling", "show")],
  "exit-keep": [exit("keep"), work("c1-show-returned", "show")],
  "delegate-bg": [delegate("child-hold", { run_in_background: true })],
  "child-hold": [report("child-hold", 8000)],
  "bind-2-cd": [work("c2-start", "start", "issue-2"), bash(`cd ${nested}`), work("c2-show-nested", "show")],
  "bind-7-cd": [work("c4-start", "start", "issue-7"), bash(`cd ${nested}`), report("c4-in-nested")],
  "enter-nested": [enter({ path: nested }), work("c4-show-entered", "show")],
  "rebind-2": [work("c2-start-nested", "start", "issue-2"), work("c2-show-rebound", "show")],
  "managed-remove": [work("c3-start", "start", "issue-3"), enter({ name: "managed" }), work("c3-show-managed", "show"), exit("remove"), work("c3-show-removed", "show")],
  "path-remove": [enter({ path: disposable }), exit("remove"), report("c3-after-path-remove"), exit("keep"), report("c3-after-keep")],
  "worker-carry": [work("w1-start", "start", "issue-1"), enter({ path: sibling }), work("w1-show-sibling", "show")],
  "worker-bound": [work("w2-start", "start", "issue-4"), work("w2-show", "show")],
  "worker-plain": [report("w3")],
  "after-replace": [work("w1-show-replaced", "show"), report("w1-replaced")],
  "worker-respawn": [work("w5-start", "start", "issue-6"), work("w5-show", "show")],
  "after-respawn": [work("w5-show-respawned", "show"), report("w5-respawned")],
  "worker-idle": [work("w4-start", "start", "issue-5"), work("w4-show", "show")],
  "after-idle": [work("w4-show-after", "show")],
};
const modelRequests = new Map();
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
      const match = part.type === "text" && part.text?.match(/SPIKE:([a-z0-9-]+)/);
      if (match) { label = match[1]; latestUser = index; }
    }
  });
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  const later = messages.slice(latestUser + 1);
  const results = later.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : []);
  // The worktree tools' outcomes are evidence; other results stay out of the trace.
  const worktreeOutcomes = later.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_use" && /Worktree$/.test(part.name)) : [])
    .map((use) => {
      const result = results.find((part) => part.tool_use_id === use.id);
      const text = typeof result?.content === "string" ? result.content : result?.content?.map((part) => part.text ?? "").join(" ") ?? "";
      return { tool: use.name, isError: result?.is_error ?? null, text: text.slice(0, 400) };
    });
  const sequence = (label && sequences[label]) || [];
  const step = sequence[results.length];
  const count = (modelRequests.get(label ?? "none") ?? 0) + 1;
  modelRequests.set(label ?? "none", count);
  trace("model.request", { label, step: results.length, tool: step?.tool ?? null, available: step ? tools.includes(step.tool) : null, count,
    worktreeOutcomes: worktreeOutcomes.length ? worktreeOutcomes : undefined });
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [{ type: "text", text: "Fixture complete." }],
      stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (step && tools.includes(step.tool)) {
    sse("content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label}_${records.length}`, name: step.tool, input: {} } });
    sse("content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(step.input) } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { output_tokens: 20 } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: "Fixture complete." } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 4 } });
  }
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// Subscribe the hook exactly as `dashpot integrate claude-code` does, read
// from this checkout's integration, with the wrapper in place of the
// publisher. Only the timeout is the fixture's: the wrapper adds a hop.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import integration; c = integration('claude-code'); print(json.dumps({'events': c.events, 'matched': c.matched_events}))"], { encoding: "utf8" }));
const handler = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")}`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
// Pre-accept onboarding and trust so neither clients nor workers prompt.
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: Object.fromEntries([fixture, sibling, nested, disposable].map((dir) => [dir, { hasTrustDialogAccepted: true, allowedTools: [] }])),
}, null, 2));

const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
const claude = async (args, options = {}) => {
  const child = spawn(launcher, args, { cwd: options.cwd ?? fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), options.timeout ?? 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  trace("action.claude", { args, cwd: options.cwd ?? fixture, pid: child.pid, status, signal, stdout: stdout.slice(-1000), stderr: stderr.slice(-1000) });
  return { status, stdout, stderr };
};
// Every process whose environment names the fixture configuration, so the
// operator's own Claude Code sessions are never observed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CLAUDE_CONFIG_DIR=${env.CLAUDE_CONFIG_DIR}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const agentsJSON = async (label, all = false) => {
  const result = await claude(["agents", "--json", ...(all ? ["--all"] : [])], { timeout: 30000 });
  let parsed = null;
  try { parsed = JSON.parse(result.stdout); } catch {}
  const agents = (parsed ?? []).filter((entry) => entry.kind === "background")
    .map(({ id, name, pid, sessionId, state, status, cwd }) => ({ id, name, pid, sessionId, state, status, cwd }));
  trace("agents", { label, all, agents });
  return agents;
};
// Each Worktree's Dashpot state files, by name: where hook records and Work
// Stores are, and so whether an ended session's records were removed.
const stateFiles = () => Object.fromEntries([fixture, sibling, nested, disposable, path.join(fixture, ".claude", "worktrees", "managed")].map((worktree) => {
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
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label) => {
  let snapshot = null;
  let error = null;
  try { snapshot = JSON.parse(execFileSync(dashpot, ["--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 })); } catch (failure) { error = String(failure).slice(0, 500); }
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const issueRuns = Object.fromEntries(Object.entries(snapshot?.issueRuns ?? {}).filter(([, value]) => value.length));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((project) => project.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: retained(message).slice(0, 300) }));
  return trace("observation", { label, error, runs, issueRuns, diagnostics, stateFiles: stateFiles() });
};
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const hookOf = (session, event, since = 0) => hooks().slice(since).find((record) => record.payload.session_id === session && record.event === event && !record.payload.agent_id);
const stopsOf = (session) => hooks().filter((record) => record.payload.session_id === session && record.event === "Stop").length;

// A headless client: one `claude -p` process taking its user turns as
// stream-json on stdin, so the runner can observe between turns and end the
// session by closing its input, or kill it.
const client = async (name, cwd) => {
  const child = spawn(launcher, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", ...commonArgs],
    { cwd, env, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, exited: null };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      try { const message = JSON.parse(line); if (message.session_id && !state.session) state.session = message.session_id; } catch {}
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, cwd, pid: child.pid });
  state.turn = async (label) => {
    const before = state.session ? stopsOf(state.session) : 0;
    child.stdin.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text: `SPIKE:${label}` }] } }) + "\n");
    await waitFor(() => state.session && stopsOf(state.session) > before, `${name} ${label} Stop`, 90000);
    trace("turn", { client: name, label, session: state.session });
  };
  return state;
};
// A supervised worker: dispatched with `--bg`, found by name in the listing
// once its first turn has stopped.
const worker = async (name, label, cwd) => {
  const dispatched = await claude(["--bg", `SPIKE:${label}`, "--name", name, ...commonArgs], { cwd });
  assert.equal(dispatched.status, 0, `dispatch ${name}: ${dispatched.stderr}`);
  let job;
  const end = Date.now() + 90000;
  while (Date.now() < end) {
    job = (await agentsJSON(`${name}-dispatched`)).find((entry) => entry.name === name && entry.sessionId);
    if (job && stopsOf(job.sessionId) > 0) break;
    await delay(1000);
  }
  assert(job && stopsOf(job.sessionId) > 0, `${name} stopped its first turn`);
  trace("worker", { name, label, ...job });
  return job;
};

// A turn typed into a running worker through `claude attach` on a
// pseudo-terminal; closing the terminal detaches without stopping the worker.
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
const attachTurn = async (job, label) => {
  const before = stopsOf(job.sessionId);
  const child = spawn("script", ["-qfec", `${launcher} attach ${job.id}`, "/dev/null"],
    { cwd: fixture, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  let output = "";
  child.stdout.on("data", (chunk) => { output += stripAnsi(String(chunk)); });
  trace("attach", { job: job.id, label, pid: child.pid });
  try {
    await delay(4000);
    child.stdin.write(`SPIKE:${label}`);
    await delay(500);
    child.stdin.write("\r");
    await waitFor(() => stopsOf(job.sessionId) > before, `${job.name} attached ${label} Stop`, 90000);
  } catch (error) {
    if (process.env.SPIKE_DEBUG_TERMINAL === "1") writeFileSync(path.join(root, `attach-${label}.txt`), output);
    throw error;
  } finally {
    child.kill("SIGTERM");
    await delay(1000);
  }
  trace("turn", { worker: job.name, label, session: job.sessionId });
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), subscriptions: integration,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")),
    fixture, sibling, nested, disposable, idleMinutes,
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    sourceSHA256: Object.fromEntries([...["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) => [file, path.join(here, file)]),
      ...["harnesses.py", "hook_publish.py", "work_reconciliation.py", "hook_records.py", "work.py"].map((file) => [`src/dashpot/sessions/${file}`, path.join(checkout, "src", "dashpot", "sessions", file)])]
      .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });

  // The acceptance scenarios, unless the run is the idle-eviction one.
  if (idleMinutes === 0) {
    // Scenario 1: a headless client moved by the worktree tools. Unbound, it
    // carries nothing; bound, EnterWorktree and ExitWorktree(keep) carry its
    // run; a background sub-agent outlives the parent's turn; closing the
    // client ends the run.
    trace("scenario", { name: "client-worktree-tools" });
    const c1 = await client("c1", fixture);
    await c1.turn("unbound-move");
    observe("c1-unbound-moved");
    await c1.turn("bind-1");
    observe("c1-bound");
    await c1.turn("enter-sibling");
    observe("c1-entered-sibling");
    await c1.turn("exit-keep");
    observe("c1-returned");
    await c1.turn("delegate-bg");
    observe("c1-parent-settled-child-working");
    await waitFor(() => commands().some((record) => record.label === "child-hold" && record.phase === "end"), "child hold ended", 60000);
    await waitFor(() => hooks().some((record) => record.event === "SubagentStop" && record.payload.session_id === c1.session), "c1 SubagentStop", 60000);
    await delay(1000);
    observe("c1-child-finished");
    c1.child.stdin.end();
    await waitFor(() => c1.exited && hookOf(c1.session, "SessionEnd"), "c1 SessionEnd and exit", 60000);
    observe("c1-ended");

    // Scenario 2: a persistent shell `cd` into the nested Worktree places the
    // session there but never carries its run; `work start` there switches
    // it. The client then dies without SessionEnd.
    trace("scenario", { name: "client-shell-cd" });
    const c2 = await client("c2", fixture);
    await c2.turn("bind-2-cd");
    observe("c2-shell-in-nested");
    await c2.turn("rebind-2");
    observe("c2-rebound-in-nested");
    c2.child.kill("SIGKILL");
    trace("action.kill", { client: "c2", pid: c2.child.pid, signal: "SIGKILL" });
    await waitFor(() => c2.exited, "c2 exit", 30000);
    await delay(1000);
    observe("c2-killed");

    // Scenario 2b: after the same persistent `cd`, EnterWorktree to the
    // Worktree the shell already reached is refused, so it cannot carry the
    // run there.
    trace("scenario", { name: "client-cd-then-enter" });
    const c4 = await client("c4", fixture);
    await c4.turn("bind-7-cd");
    observe("c4-shell-in-nested");
    await c4.turn("enter-nested");
    observe("c4-entered-nested");
    c4.child.stdin.end();
    await waitFor(() => c4.exited && hookOf(c4.session, "SessionEnd"), "c4 SessionEnd and exit", 60000);
    observe("c4-ended");

    // Scenario 3: ExitWorktree(remove) leaving a Worktree EnterWorktree created.
    trace("scenario", { name: "client-managed-remove" });
    const c3 = await client("c3", fixture);
    await c3.turn("managed-remove");
    observe("c3-removed");
    await c3.turn("path-remove");
    trace("disposable", { exists: (() => { try { return statSync(disposable).isDirectory(); } catch { return false; } })() });
    observe("c3-path-remove");
    c3.child.stdin.end();
    await waitFor(() => c3.exited && hookOf(c3.session, "SessionEnd"), "c3 SessionEnd and exit", 60000);
    observe("c3-ended");

    // Scenario 4: two supervised workers under one supervisor. The first
    // binds and enters the sibling Worktree, then dies abruptly and is
    // replaced; the second stays bound in the main Worktree throughout.
    trace("scenario", { name: "workers" });
    const w1 = await worker("fixture-w1", "worker-carry", fixture);
    const w2 = await worker("fixture-w2", "worker-bound", fixture);
    observe("two-workers-bound");
    const beforeKill = hooks().length;
    assert(fixtureProcesses().some((entry) => entry.pid === w1.pid), "w1 is a fixture process");
    process.kill(w1.pid, "SIGKILL");
    trace("action.kill", { worker: "w1", pid: w1.pid, signal: "SIGKILL" });
    await waitFor(() => hookOf(w1.sessionId, "SessionStart", beforeKill), "w1 replacement SessionStart", 90000);
    const replacement = Number(hookOf(w1.sessionId, "SessionStart", beforeKill).env.CLAUDE_PID);
    const probeReplacement = (label) => { try { trace("replacement", { label, ...describe(replacement) }); } catch { trace("replacement", { label, pid: replacement, gone: true }); } };
    probeReplacement("started");
    await delay(2000);
    probeReplacement("settled");
    await agentsJSON("w1-replaced");
    observe("w1-replaced");
    // The replacement's next turn, typed into the attached worker as a person would.
    await attachTurn(w1, "after-replace");
    probeReplacement("after-turn");
    observe("w1-replaced-turn");

    // Scenario 5: the supervisor is replaced while its workers keep running.
    trace("scenario", { name: "supervisor-replacement" });
    await claude(["daemon", "stop", "--any", "--keep-workers"], { timeout: 30000 });
    await delay(2000);
    trace("processes", { label: "supervisor-stopped", processes: fixtureProcesses().map(({ pid, ppid, comm, cmdline }) => ({ pid, ppid, comm, cmdline })) });
    observe("supervisor-stopped");
    await worker("fixture-w3", "worker-plain", sibling);
    await delay(2000);
    await agentsJSON("supervisor-replaced");
    trace("processes", { label: "supervisor-replaced", processes: fixtureProcesses().map(({ pid, ppid, comm, cmdline }) => ({ pid, ppid, comm, cmdline })) });
    observe("supervisor-replaced");

    // Scenario 6: an explicit stop of a bound worker, then its respawn.
    trace("scenario", { name: "worker-stop-respawn" });
    let before = hooks().length;
    await claude(["stop", w2.id], { timeout: 30000 });
    await delay(3000);
    trace("worker.stop", { worker: "w2", hooks: hooks().slice(before).map((record) => [record.event, record.payload.session_id === w2.sessionId, record.payload.reason ?? record.payload.source ?? null]) });
    observe("w2-stopped");
    before = hooks().length;
    await claude(["respawn", w2.id], { timeout: 30000 });
    await waitFor(() => hookOf(w2.sessionId, "SessionStart", before), "w2 respawn SessionStart", 90000);
    await delay(2000);
    observe("w2-respawned");
    // The replaced worker dies again and is stopped before its replacement
    // runs any turn, so the only hook at its Worktree is its SessionEnd.
    trace("scenario", { name: "replacement-stopped-before-turn" });
    const current = Number(hooks().filter((record) => record.payload.session_id === w1.sessionId && record.env?.CLAUDE_PID).at(-1).env.CLAUDE_PID);
    before = hooks().length;
    process.kill(current, "SIGKILL");
    trace("action.kill", { worker: "w1", pid: current, signal: "SIGKILL" });
    await waitFor(() => hookOf(w1.sessionId, "SessionStart", before), "w1 second replacement SessionStart", 90000);
    await delay(2000);
    observe("w1-replaced-again");
    before = hooks().length;
    await claude(["stop", w1.id], { timeout: 30000 });
    await delay(3000);
    trace("worker.stop", { worker: "w1", hooks: hooks().slice(before).map((record) => [record.event, record.payload.session_id === w1.sessionId, record.payload.reason ?? record.payload.source ?? null]) });
    observe("w1-stopped");

    // Scenario 8: a bound worker dies while no supervisor runs, so nothing
    // replaces it until `claude respawn` brings it back.
    trace("scenario", { name: "respawn-after-abrupt-exit" });
    const w5 = await worker("fixture-w5", "worker-respawn", fixture);
    observe("w5-bound");
    await claude(["daemon", "stop", "--any", "--keep-workers"], { timeout: 30000 });
    await delay(2000);
    before = hooks().length;
    assert(fixtureProcesses().some((entry) => entry.pid === w5.pid), "w5 is a fixture process");
    process.kill(w5.pid, "SIGKILL");
    trace("action.kill", { worker: "w5", pid: w5.pid, signal: "SIGKILL" });
    await delay(15000);
    trace("worker.unsupervised-kill", { hooks: hooks().slice(before).filter((record) => record.payload.session_id === w5.sessionId).map((record) => [record.event, record.payload.source ?? record.payload.reason ?? null]) });
    await agentsJSON("w5-killed", true);
    observe("w5-killed");
    before = hooks().length;
    await claude(["respawn", w5.id], { timeout: 30000 });
    await waitFor(() => hookOf(w5.sessionId, "SessionStart", before), "w5 respawn SessionStart", 90000);
    const respawned = Number(hookOf(w5.sessionId, "SessionStart", before).env.CLAUDE_PID);
    try { trace("respawned", { label: "started", ...describe(respawned) }); } catch { trace("respawned", { label: "started", pid: respawned, gone: true }); }
    await delay(2000);
    await agentsJSON("w5-respawned");
    observe("w5-respawned");
    await attachTurn(w5, "after-respawn");
    observe("w5-respawned-turn");
  }

  // The idle-eviction run: a bound worker left idle until the supervisor
  // retires it, then attached again.
  if (idleMinutes > 0) {
    trace("scenario", { name: "idle-eviction", minutes: idleMinutes });
    const w4 = await worker("fixture-w4", "worker-idle", fixture);
    observe("w4-bound");
    const deadline = Date.now() + idleMinutes * 60000;
    let alive = true;
    while (alive && Date.now() < deadline) {
      await delay(60000);
      alive = fixtureProcesses().some((entry) => entry.pid === w4.pid);
      let state = null;
      try { state = JSON.parse(readFileSync(path.join(env.CLAUDE_CONFIG_DIR, "jobs", w4.id, "state.json"), "utf8")); } catch {}
      trace("idle.poll", { alive, state: state && { state: state.state, tempo: state.tempo, inFlight: state.inFlight, updatedAt: state.updatedAt } });
    }
    await delay(3000);
    trace("idle.outcome", { retired: !alive, hooks: hooks().filter((record) => record.payload.session_id === w4.sessionId).map((record) => [record.event, record.payload.reason ?? record.payload.source ?? null, record.receiptTime]) });
    await agentsJSON("w4-idle", true);
    observe("w4-idle");
    if (!alive) {
      await attachTurn(w4, "after-idle");
      await agentsJSON("w4-attached", true);
      observe("w4-attached");
    }
  }
  console.log(`All scenarios completed: ${root}`);
} finally {
  // Leave nothing of the isolated clients and supervisor behind.
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
