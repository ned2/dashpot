// Measurement run for Issue #448: does anything make Dashpot write a
// `SessionStart` for an OpenCode 2.0.22 root session that is still live in
// the same Host Process while one of its child sessions (a Sub-agent) is
// executing? Claude Code does so on compaction; this run compacts OpenCode
// roots manually and automatically while a child runs, and tries the other
// cheap ways a live root might be started again: a fork, a second client, a
// TUI attaching, a configuration reload, a move to another Project, and a
// standalone server opening the same session.
//
// Adapted from the worker mechanics run (opencode-421). It drives the pinned
// OpenCode release, run read-only through a fixture-local PATH symlink,
// against a loopback OpenAI-compatible model fixture, in disposable
// configuration and state, with the background service on a private port,
// so the operator's own OpenCode service is never contacted. Dashpot is built
// from this checkout's committed HEAD (or, with SPIKE_DASHPOT_SOURCE=worktree,
// its working tree) and installed into a fixture environment, and
// `dashpot integrate opencode` from that installation writes the plugin. Two
// fixture probes sit beside it: a plugin recording every event a plugin
// instance receives, and a wrapper around the helper recording every hook
// event Dashpot writes and the hook record after each write. The trace is
// metadata only; the independent verifier checks it against the findings.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode 2.0.22 binary> > log 2>&1
// It is done when it prints "Metadata trace:". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, inFixture } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
// A harness above the runner would be an ancestor of every client the run
// starts, and the Host Process Dashpot finds for a process it does not
// recognise, so the runner refuses to start below one; `setsid -f` detaches it.
const above = [];
for (let pid = process.ppid; pid > 1 && above.length < 64;) { try { const entry = describe(pid); above.push(entry); pid = entry.ppid; } catch { break; } }
const host = above.find((entry) => /^(claude|codex|opencode|opencode2|opencode\.exe)$/.test(entry.comm) || /\/claude\/versions\//.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const [binary] = process.argv.slice(2);
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the OpenCode 2.0.22 binary");
const uv = execFileSync("sh", ["-c", "command -v uv"], { encoding: "utf8" }).trim();

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-448-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree, one linked Worktree, and a second Project.
const fixture = path.join(root, "repository");
const treeA = path.join(root, "repository.worktrees", "a");
const other = path.join(root, "other");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, the binary's
// directory, this directory, the checkout, and the operator's home by
// placeholder.
const retained = (text) => String(text).replaceAll(path.dirname(binary), "$BINARY_DIR").replaceAll(root, "$ROOT").replaceAll(path.dirname(root), "$TMPDIR")
  .replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const sha256 = (file) => !existsSync(file) ? null : createHash("sha256").update(readFileSync(file)).digest("hex");

// Dashpot, built from the committed HEAD unless the working tree is asked
// for, and installed outside every Worktree, as a person's installation is.
const dashpotSource = process.env.SPIKE_DASHPOT_SOURCE === "worktree" ? "worktree" : "HEAD";
const buildSource = dashpotSource === "worktree" ? checkout : path.join(root, "source");
if (dashpotSource === "HEAD") {
  mkdirSync(buildSource);
  execFileSync("sh", ["-c", 'git -C "$1" archive HEAD | tar -x -C "$2"', "sh", checkout, buildSource], { stdio: "pipe" });
}
const venv = path.join(root, "venv");
execFileSync(uv, ["build", "-q", "--wheel", "-o", path.join(root, "dist"), buildSource], { stdio: "pipe" });
const [wheel] = readdirSync(path.join(root, "dist")).filter((name) => name.endsWith(".whl"));
execFileSync(uv, ["venv", "-q", "--python", path.join(checkout, ".venv", "bin", "python"), venv], { stdio: "pipe" });
execFileSync(uv, ["pip", "install", "-q", "--offline", "--python", path.join(venv, "bin", "python"), path.join(root, "dist", wheel)], { stdio: "pipe" });
const dashpot = path.join(venv, "bin", "dashpot");
const helper = path.join(venv, "bin", "dashpot-opencode-hook");
// The helper wrapper, run by the fixture environment's Python.
const probeHelper = path.join(venv, "bin", "dashpot-opencode-hook-probe");
writeFileSync(probeHelper, `#!${path.join(venv, "bin", "python")}\n` + readFileSync(path.join(here, "helper_probe.py"), "utf8"));
chmodSync(probeHelper, 0o755);
const installed = execFileSync(path.join(venv, "bin", "python"), ["-c", "import dashpot, os; print(os.path.dirname(dashpot.__file__))"], { encoding: "utf8" }).trim();
// The Dashpot sources the run exercises; the installed copies must be them.
const exercised = ["plugins/opencode.js", "sessions/opencode_publish.py", "sessions/opencode_publishers.py", "sessions/hook_scan.py",
  "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/harnesses.py", "sessions/integrate.py", "repository/cleanup/obstacles.py", "hook.py"];

const env = {
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  SHELL: "/bin/bash",
  LANG: "C.UTF-8",
  OPENCODE_DISABLE_AUTOUPDATE: "1",
  OPENCODE_DISABLE_MODELS_FETCH: "1",
  OPENCODE_DISABLE_PROJECT_CONFIG: "1",
  // Nothing but loopback is reachable: a model OpenCode chose over the
  // fixture's would otherwise be a hosted one.
  HTTP_PROXY: "http://127.0.0.1:9", HTTPS_PROXY: "http://127.0.0.1:9", http_proxy: "http://127.0.0.1:9", https_proxy: "http://127.0.0.1:9",
  NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
  DASHPOT_STATE_DIR: path.join(root, "dashpot-state"),
  // Ancestry walks from shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_PLUGIN_EVENTS: path.join(root, "plugin-events.jsonl"),
  SPIKE_PUBLICATIONS: path.join(root, "publications.jsonl"),
};
// OpenCode where its curl installer puts it, as a symlink to the pinned
// release: the release is only ever run, never written.
const curlBin = path.join(env.HOME, ".opencode", "bin");
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
for (const dir of [fixture, other, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, curlBin, configHome]) mkdirSync(dir, { recursive: true });
symlinkSync(binary, path.join(curlBin, "opencode"));
env.PATH = `${curlBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`;
const version = execFileSync(path.join(curlBin, "opencode"), ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "opencode v2.0.22", `unexpected OpenCode version: ${version}`);

// A Dashpot Project with a markdown Issue Source.
const project = (directory, name) => {
  mkdirSync(path.join(directory, ".dashpot"), { recursive: true });
  mkdirSync(path.join(directory, "issues"), { recursive: true });
  writeFileSync(path.join(directory, ".dashpot", "config.json"), JSON.stringify({ projectId: `project:${name}`, displayLabel: name,
    repositoryId: `repository:${name}`, issueSource: { kind: "markdown", path: "issues" } }));
  const front = { id: `I_${name}_1`, number: 1, reference: "issue-1", state: "open", stateReason: null, labels: [], assignees: [],
    author: "fixture", relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(directory, "issues", "issue-1.md"), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue 1\n\nBody.\n`);
  const git = (...args) => execFileSync("git", ["-C", directory, ...args], { env, stdio: "pipe" });
  git("init", "--initial-branch=main");
  git("add", ".");
  git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
  return git;
};
project(fixture, "fixture")("worktree", "add", "-b", "a", treeA);
project(other, "other");
const worktrees = [fixture, treeA, other];

const listen = async (handler) => {
  const server = http.createServer(async (req, res) => {
    try { await handler(req, res); } catch (error) {
      trace("server.error", { path: req.url, error: retained(String(error?.stack ?? error)).slice(0, 1000) });
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
  trace("command", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The probes' files, tailed into the trace as they grow.
const tails = [{ file: env.SPIKE_PLUGIN_EVENTS, offset: 0, kind: "plugin" }, { file: env.SPIKE_PUBLICATIONS, offset: 0, kind: "publication" }];
const drain = () => {
  for (const tail of tails) {
    let buffer;
    try { buffer = readFileSync(tail.file); } catch { continue; }
    const text = buffer.subarray(tail.offset).toString("utf8");
    const end = text.lastIndexOf("\n");
    if (end < 0) continue;
    const chunk = text.slice(0, end + 1);
    tail.offset += Buffer.byteLength(chunk);
    for (const line of chunk.split("\n")) {
      if (!line) continue;
      let item;
      try { item = JSON.parse(line); } catch { trace("tail.error", { source: tail.kind, line: retained(line).slice(0, 300) }); continue; }
      if (tail.kind === "plugin") trace(`plugin.${item.phase}`, item);
      else trace("publication", item);
    }
  }
};
const tailing = setInterval(drain, 100);

// The fixture model. The latest user message holding a `PROBE:<label>`
// selects a sequence of steps; a step is one tool call or several made at
// once, and the session's turn ends with a text once every step has run.
// Progress is kept per session and label, not counted from the messages,
// since a compaction replaces the messages a count would read. A label with
// no sequence runs one shell command of that name. A compaction's summary
// request is answered with the summary template's headings.
const HOLD = 40000;
const commandScript = path.join(here, "command.mjs");
const shell = (command, options = {}) => ({ name: "shell", arguments: { command, ...options } });
const report = (label, hold = 0) => shell(`node ${commandScript} ${label} ${hold}`);
const subagent = (child) => ({ name: "subagent", arguments: { agent: "general", description: `Worker ${child}`, prompt: `PROBE:${child}`, background: true } });
const PREFIXES = ["c", "cb", "a", "o", "x", "r", "m", "s"];
const sequences = {
  // The root's own turn while its child holds, with the compaction steered
  // into it at the next step boundary.
  "cb-launch": () => [subagent("cb-child"), report("cb-root-hold", 12000), report("cb-root-after")],
  // The step whose response reports a context nearly full.
  "a-launch": () => [subagent("a-child"), report("a-root-hold", 6000), report("a-root-after")],
  // The step whose first request the provider refuses as too long.
  "o-launch": () => [subagent("o-child"), report("o-root-hold", 6000), report("o-root-after")],
};
for (const prefix of PREFIXES) {
  sequences[`${prefix}-warm`] = () => [report(`${prefix}-warm`)];
  sequences[`${prefix}-launch`] ??= () => [subagent(`${prefix}-child`)];
  sequences[`${prefix}-child`] = () => [report(`${prefix}-child-hold`, HOLD), report(`${prefix}-child-after`)];
}
const HIGH_USAGE = new Set(["a-launch:1"]);
const OVERFLOW = new Set(["o-launch:2"]);
const overflowed = new Set();
const SUMMARY = ["## Objective", "- Fixture.", "## Requirements", "- (none)", "## Decisions", "- (none)", "## Work State", "### Completed", "- (none)",
  "### Active", "- (none)", "### Blocked", "- (none)", "## Next Move", "1. (none)", "## Relevant Files", "- (none)", "## Important Context", "- (none)"].join("\n");
const text = (message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
const probes = (message) => [...text(message).matchAll(/PROBE:([a-z0-9-]+)/g)].map((match) => match[1]);
const progress = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const sessionID = req.headers["x-opencode-session-id"] ?? null;
  const parentID = req.headers["x-opencode-parent-session-id"] ?? null;
  // A child's label in a root's messages is its launch, or a compaction's
  // record of it, and never the root's own sequence.
  const own = (message) => probes(message).filter((found) => parentID || !found.endsWith("-child"));
  const anchor = messages.findLastIndex((message) => message.role === "user" && own(message).length);
  const label = anchor >= 0 ? own(messages[anchor]).at(-1) : null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const last = messages.at(-1);
  const compaction = last?.role === "user" && /## Objective|required summary template/.test(text(last));
  const titled = !compaction && (/title generator/i.test(system) || !tools.length);
  const key = `${sessionID}\0${label}`;
  const step = compaction || titled ? null : progress.get(key) ?? 0;
  const mark = `${label}:${step}`;
  if (step !== null && OVERFLOW.has(mark) && !overflowed.has(`${sessionID}:${mark}`)) {
    overflowed.add(`${sessionID}:${mark}`);
    trace("model.request", { label, step, request: "overflow", sessionID, parentID, messages: messages.length });
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: "This model's maximum context length is 128000 tokens (context_length_exceeded).",
      type: "invalid_request_error", code: "context_length_exceeded" } }));
    return;
  }
  if (step !== null) progress.set(key, step + 1);
  const planned = step === null || !label ? undefined : (sequences[label]?.() ?? [report(label)])[step];
  const calls = planned === undefined ? [] : Array.isArray(planned) ? planned : [planned];
  const high = step !== null && HIGH_USAGE.has(mark);
  trace("model.request", { label, step, request: compaction ? "compaction" : titled ? "title" : "step", tools: calls.map((call) => call.name),
    sessionID, parentID, messages: messages.length, highUsage: high || undefined });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null, usage) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture",
    choices: [{ index: 0, delta, finish_reason: finish }], ...(usage ? { usage } : {}) }) + "\n\n");
  if (calls.length) {
    chunk({ role: "assistant", tool_calls: calls.map((call, index) => ({ index, id: `call_${label}_${step}_${index}`, type: "function",
      function: { name: call.name, arguments: JSON.stringify(call.arguments) } })) });
  } else chunk({ role: "assistant", content: compaction ? SUMMARY : titled ? "Fixture title" : `Fixture complete: ${label}.` });
  chunk({}, calls.length ? "tool_calls" : "stop", high ? { prompt_tokens: 120000, completion_tokens: 20, total_tokens: 120020 } : undefined);
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed, the
// background service on a private port with a known password.
const freePort = async () => {
  const server = net.createServer().listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  server.close();
  return port;
};
const servicePort = await freePort();
const password = "fixture-password";
writeFileSync(path.join(configHome, "service.json"), JSON.stringify({ hostname: "127.0.0.1", port: servicePort, password }));
writeFileSync(path.join(configHome, "opencode.json"), JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  permissions: [{ action: "*", resource: "*", effect: "allow" }],
}, null, 2));

// --- Processes ----------------------------------------------------------------

// A subprocess that never blocks the runner's event loop, so the sink keeps
// answering the shells while it runs.
const runAsync = (command, args, { cwd = fixture, extra = {}, without = [], timeout = 60000 } = {}) => new Promise((resolve) => {
  const started = Date.now();
  const child = spawn(command, args, { cwd, env: Object.fromEntries(Object.entries({ ...env, PWD: cwd, ...extra }).filter(([key]) => !without.includes(key))),
    stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "", stderr = "";
  child.stdout.on("data", (data) => { stdout += data; });
  child.stderr.on("data", (data) => { stderr += data; });
  const timer = setTimeout(() => child.kill("SIGKILL"), timeout);
  let done = false;
  const finish = (status, signal) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    resolve({ status, signal, ms: Date.now() - started, stdout: retained(stdout).slice(0, 1500), stderr: retained(stderr).slice(-1500) });
  };
  // A daemon the command starts may keep its pipes open: its exit ends it.
  child.on("exit", (status, signal) => setTimeout(() => finish(status, signal), 300));
  child.on("close", finish);
});
const cli = (args, options) => runAsync("opencode", args, options);
const readJson = (file) => { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return null; } };
const storeOf = (worktree) => path.join(worktree, ".dashpot", "state", "sessions");
// Every hook record in the fixture's stores: state, last event, live
// Sub-agents and the Host Process it names.
const stateFiles = (label) => {
  drain();
  const sessions = {};
  for (const worktree of worktrees) {
    let names = [];
    try { names = readdirSync(storeOf(worktree)).filter((name) => name.endsWith(".json")); } catch { continue; }
    for (const name of names) {
      const record = readJson(path.join(storeOf(worktree), name));
      if (!record?.event) continue;
      sessions[`${worktree}/${name}`] = { state: record.state ?? null, event: record.event ?? null, liveSubagents: record.liveSubagents ?? null,
        hostPid: record.sessionProcess?.pid ?? null, unobservable: record.sessionProcessUnobservable ?? null, cwd: record.cwd ?? null };
    }
  }
  return trace("state", { label, sessions });
};
// What Cleanup says about the linked Worktree.
const check = async (label) => {
  const result = await runAsync(dashpot, ["worktree", "check", treeA, "--json"]);
  let assessment = null;
  try { assessment = JSON.parse(result.stdout); } catch {}
  return trace("cleanup", { label, worktree: treeA, status: result.status,
    obstacles: assessment ? (assessment.obstacles ?? []).map(({ kind, detail }) => ({ kind, detail: String(detail ?? "").slice(0, 300) })) : null,
    error: assessment ? undefined : (result.stdout + result.stderr).slice(0, 1500) });
};
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const pluginEvent = (predicate) => records.find((record) => record.kind === "plugin.event" && predicate(record));
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { drain(); if (predicate()) return true; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
const settle = (ms = 1500) => delay(ms);
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || !inFixture(name, env.XDG_CONFIG_HOME)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };

// --- The background service and its clients -----------------------------------

const registration = () => readJson(path.join(env.XDG_STATE_HOME, "opencode", "service.json"));
const service = { url: `http://127.0.0.1:${servicePort}`, pid: null };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
const request = async (method, route, data) => {
  const response = await fetch(service.url + route, { method, headers: { "content-type": "application/json", authorization },
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = raw.slice(0, 500); }
  return { status: response.status, body: parsed?.data ?? parsed };
};
const api = async (method, route, data) => {
  const answer = await request(method, route, data);
  assert(answer.status >= 200 && answer.status < 300, `${method} ${route}: ${answer.status} ${JSON.stringify(answer.body).slice(0, 700)}`);
  return answer.body;
};
const awaitService = async (label) => {
  let info = null;
  await waitFor(() => (info = registration()) && alive(info.pid), `${label}: service registered`, 60000);
  let ready = false;
  for (let attempt = 0; attempt < 200 && !ready; attempt++) {
    ready = (await request("GET", "/api/info").catch(() => null))?.status === 200;
    if (!ready) await delay(100);
  }
  assert(ready, `${label}: service never ready`);
  service.pid = info.pid;
  trace("service", { label, pid: info.pid, version: info.version ?? null });
};
const known = {};
const session = async (title, directory) => {
  const made = await api("POST", "/api/session", { title, location: { directory }, model: { id: "fixture", providerID: "loop" } });
  trace("session", { title, sessionID: made.id, directory: made.location?.directory ?? null, parentID: made.parentID ?? null });
  return made.id;
};
const send = (id, label) => api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}` });
const idle = async (id, label) => {
  const waited = await request("POST", `/api/experimental/session/${id}/wait`, {});
  assert(waited.status >= 200 && waited.status < 300, `${label}: wait ${waited.status}`);
};
const prompt = async (id, label) => {
  const started = Date.now();
  await send(id, label);
  await idle(id, label);
  trace("turn", { sessionID: id, label, ms: Date.now() - started });
};
const claimOf = (label) => command(label, "start")?.env?.OPENCODE_SESSION_ID ?? null;
// An action on a live root, recorded with when it began and ended.
const action = (label, fields) => trace("action", { label, ...fields });
const summarise = (value) => retained(JSON.stringify(value ?? null)).slice(0, 400);
// The child held at an instant: its hold started before and ended after.
const holding = (prefix, at) => {
  const start = command(`${prefix}-child-hold`, "start");
  const end = command(`${prefix}-child-hold`);
  return Boolean(start && start.startedAt < at && (!end || end.endedAt > at));
};

// A root that has run one turn, then launched a child that now holds.
const launch = async (prefix, { wait = true } = {}) => {
  const id = await session(`Root ${prefix}`, fixture);
  known[prefix] = id;
  await prompt(id, `${prefix}-warm`);
  if (wait) await prompt(id, `${prefix}-launch`);
  else await send(id, `${prefix}-launch`);
  await waitFor(() => command(`${prefix}-child-hold`, "start"), `${prefix} child holding`, 60000);
  known[`${prefix}-child`] = claimOf(`${prefix}-child-hold`);
  await settle(1000);
  stateFiles(`${prefix}-before`);
  return id;
};
// The child's end: its own execution's end and its stop's publication, then
// the root woken by the notice and idle again.
const finish = async (prefix) => {
  const id = known[prefix];
  const child = known[`${prefix}-child`];
  await waitFor(() => command(`${prefix}-child-after`), `${prefix} child ended`, 90000);
  await waitFor(() => records.some((record) => record.kind === "publication" && record.request?.session?.id === child
    && record.request?.event?.type?.startsWith("session.execution.") && record.request.event.type !== "session.execution.started"),
  `${prefix} child stop published`, 30000).catch((error) => trace("missing", { label: `${prefix}-child-stop`, error: String(error) }));
  await settle(3000);
  await idle(id, `${prefix}-notice`);
  await settle(1000);
  stateFiles(`${prefix}-child-ended`);
  await check(`${prefix}-child-ended`);
};
const compactionEnd = (id, after) => pluginEvent((record) => record.sessionID === id && record.receipt > after
  && /^session\.compaction\.(ended|failed)$/.test(record.type));

const pluginFile = path.join(configHome, "plugins", "dashpot.js");
const clients = [];
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), servicePort, fixture, treeA, other, wheel, hold: HOLD,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotSource, dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(buildSource, "src", "dashpot", file))),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "command.mjs", "ancestry.mjs", "probe-plugin.js", "helper_probe.py"].map((file) => [file, sha256(path.join(here, file))]),
      ...exercised.map((file) => [`src/dashpot/${file}`, sha256(path.join(buildSource, "src", "dashpot", file))]),
    ]) });

  // The integration, as a person installs it, with the helper wrapper bound
  // in the helper's place and the event probe beside the plugin.
  trace("scenario", { name: "installer" });
  const integrated = await runAsync(dashpot, ["integrate", "opencode"]);
  trace("integrate", { label: "install", ...integrated });
  const plugin = readFileSync(pluginFile, "utf8");
  assert(plugin.includes(JSON.stringify(helper)), "the plugin names the installed helper");
  const bound = plugin.replace(JSON.stringify(helper), JSON.stringify(probeHelper));
  writeFileSync(pluginFile, bound);
  copyFileSync(path.join(here, "probe-plugin.js"), path.join(configHome, "plugins", "fixture-probe.js"));
  trace("files", { label: "installed", plugin: createHash("sha256").update(plugin).digest("hex"), bound: sha256(pluginFile),
    onlyHelperChanged: bound.replace(JSON.stringify(probeHelper), JSON.stringify(helper)) === plugin });
  trace("service.start", { label: "start", ...(await cli(["service", "start"])) });
  await awaitService("start");
  await settle(1000);

  // Scenario 1: the root compacted through the HTTP API, the route the
  // TUI's and ACP's /compact call, while it is idle and its child holds.
  trace("scenario", { name: "compact" });
  {
    const id = await launch("c");
    const before = trace("action", { label: "c-compact", phase: "start" }).receipt;
    const at = Date.now();
    const answer = await request("POST", `/api/session/${id}/compact`, {});
    action("c-compact", { phase: "end", status: answer.status, body: summarise(answer.body), childHolding: holding("c", at) });
    await waitFor(() => compactionEnd(id, before), "c compaction ended", 60000).catch((error) => trace("missing", { label: "c-compaction", error: String(error) }));
    await settle(1500);
    await idle(id, "c-compacted");
    await settle(1000);
    action("c-compacted", { childHolding: holding("c", Date.now()) });
    stateFiles("c-after");
    await check("c-after");
    await finish("c");
  }

  // Scenario 2: the root compacted while its own turn runs a shell and its
  // child holds; the request is steered into the turn.
  trace("scenario", { name: "compact-busy" });
  {
    const id = await launch("cb", { wait: false });
    await waitFor(() => command("cb-root-hold", "start"), "cb root holding", 30000);
    const before = trace("action", { label: "cb-compact", phase: "start" }).receipt;
    const at = Date.now();
    const answer = await request("POST", `/api/session/${id}/compact`, {});
    action("cb-compact", { phase: "end", status: answer.status, body: summarise(answer.body), childHolding: holding("cb", at) });
    await waitFor(() => compactionEnd(id, before), "cb compaction ended", 60000).catch((error) => trace("missing", { label: "cb-compaction", error: String(error) }));
    action("cb-compacted", { childHolding: holding("cb", Date.now()) });
    await idle(id, "cb-turn");
    await settle(1000);
    stateFiles("cb-after");
    await check("cb-after");
    await finish("cb");
  }

  // Scenario 3: automatic compaction, from a step whose response reports a
  // context nearly full, before the root's next step while its child holds.
  trace("scenario", { name: "auto-compact" });
  {
    const before = records.length;
    const id = await launch("a", { wait: false });
    await waitFor(() => compactionEnd(id, before), "a compaction ended", 60000).catch((error) => trace("missing", { label: "a-compaction", error: String(error) }));
    action("a-compacted", { childHolding: holding("a", Date.now()) });
    await idle(id, "a-turn");
    await settle(1000);
    stateFiles("a-after");
    await check("a-after");
    await finish("a");
  }

  // Scenario 4: automatic compaction on a provider's context overflow.
  trace("scenario", { name: "overflow-compact" });
  {
    const before = records.length;
    const id = await launch("o", { wait: false });
    await waitFor(() => compactionEnd(id, before) || records.some((record) => record.kind === "plugin.event" && record.sessionID === id
      && record.receipt > before && /^session\.execution\.(failed|succeeded)$/.test(record.type) && command("o-root-hold")), "o compaction or turn end", 60000)
      .catch((error) => trace("missing", { label: "o-compaction", error: String(error) }));
    action("o-compacted", { childHolding: holding("o", Date.now()) });
    await idle(id, "o-turn");
    await settle(1000);
    stateFiles("o-after");
    await check("o-after");
    await finish("o");
  }

  // Scenario 5: a fork of the live root, a second client prompting it from
  // another Worktree, and a TUI attaching to it, while its child holds.
  trace("scenario", { name: "others" });
  {
    const id = await launch("x");
    let at = Date.now();
    const forked = await request("POST", `/api/session/${id}/fork`, {});
    known["x-fork"] = forked.body?.id ?? null;
    action("x-fork", { status: forked.status, forkID: known["x-fork"], childHolding: holding("x", at) });
    await settle(2000);
    stateFiles("x-after-fork");
    at = Date.now();
    const attached = await cli(["run", "--session", id, "PROBE:x-attach"], { cwd: treeA, timeout: 60000 });
    action("x-attach", { args: ["run", "--session", "<root>", "PROBE:x-attach"], cwd: treeA, status: attached.status, ms: attached.ms,
      stderr: attached.stderr.slice(-400), childHolding: holding("x", at) && holding("x", Date.now()) });
    await settle(2000);
    stateFiles("x-after-attach");
    at = Date.now();
    const quoted = ["opencode", "--session", id].join(" ");
    const tui = spawn("script", ["-qfec", quoted, "/dev/null"], { cwd: fixture,
      env: { ...env, PWD: fixture, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "ignore", "ignore"] });
    const client = { child: tui, exited: null };
    clients.push(client);
    tui.on("exit", (code, signal) => { client.exited = { code, signal }; });
    await settle(6000);
    for (let attempt = 0; attempt < 4 && !client.exited; attempt++) { tui.stdin.write("\u0003"); await delay(1500); }
    action("x-tui", { args: ["--session", "<root>"], cwd: fixture, exited: client.exited, childHolding: holding("x", at) && holding("x", Date.now()) });
    await settle(2000);
    stateFiles("x-after-tui");
    await check("x-after-tui");
    await finish("x");
  }

  // Scenario 6: the service's configuration reloaded while the child holds,
  // then a turn of the root.
  trace("scenario", { name: "reload" });
  {
    const id = await launch("r");
    const at = Date.now();
    const reloaded = await cli(["reload"]);
    action("r-reload", { status: reloaded.status, ms: reloaded.ms, stderr: reloaded.stderr.slice(-400), childHolding: holding("r", at) });
    await settle(4000);
    stateFiles("r-after-reload");
    await check("r-after-reload");
    await prompt(id, "r-after-reload-turn");
    action("r-turn", { childHolding: holding("r", Date.now()) });
    await settle(1000);
    stateFiles("r-after-turn");
    await finish("r");
  }

  // Scenario 7: the root moved to another Project while its child holds,
  // then a turn there.
  trace("scenario", { name: "move-other-project" });
  {
    const id = await launch("m");
    const at = Date.now();
    const moved = await request("POST", `/api/session/${id}/move`, { directory: other });
    action("m-move", { status: moved.status, to: other, childHolding: holding("m", at) });
    await settle(2000);
    stateFiles("m-after-move");
    await prompt(id, "m-there");
    action("m-turn", { childHolding: holding("m", Date.now()) });
    await settle(1000);
    stateFiles("m-after-turn");
    await finish("m");
  }

  // Scenario 8: a standalone server, its own Host Process, prompting the
  // live root while the service runs its child.
  trace("scenario", { name: "standalone" });
  {
    const id = await launch("s");
    const at = Date.now();
    const standalone = await cli(["run", "--standalone", "--session", id, "PROBE:s-standalone"], { timeout: 60000 });
    action("s-standalone", { args: ["run", "--standalone", "--session", "<root>", "PROBE:s-standalone"], status: standalone.status, ms: standalone.ms,
      stderr: standalone.stderr.slice(-600), childHolding: holding("s", at) && holding("s", Date.now()) });
    await settle(2000);
    stateFiles("s-after-standalone");
    await check("s-after-standalone");
    await finish("s");
  }

  trace("known", { sessions: known });
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
} finally {
  for (const client of clients) if (!client.exited) client.child.kill("SIGKILL");
  if (service.pid && alive(service.pid)) {
    trace("service.stop", { label: "final", ...(await cli(["service", "stop"])) });
    try { await waitFor(() => !alive(service.pid), "final service exit", 10000); } catch {}
  }
  await delay(1500);
  drain();
  clearInterval(tailing);
  // The helper's own record of each run, from Dashpot's Event Log: every
  // outcome that did not succeed.
  const events = [];
  for (const directory of [...worktrees.map((worktree) => path.join(worktree, ".dashpot", "state", "events")), path.join(env.DASHPOT_STATE_DIR, "events")]) {
    let names = [];
    try { names = readdirSync(directory); } catch { continue; }
    for (const name of names) for (const line of readFileSync(path.join(directory, name), "utf8").split("\n")) {
      if (!line) continue;
      const flat = {};
      const merge = (value) => { for (const [key, item] of Object.entries(value)) { if (item && typeof item === "object" && !Array.isArray(item)) merge(item); else flat[key] = item; } };
      try { merge(JSON.parse(line)); } catch { continue; }
      events.push(flat);
    }
  }
  const outcomes = events.filter((event) => event["event.name"] === "hook.outcome" && String(event["dashpot.process.kind"] ?? "").startsWith("hook:opencode"));
  trace("events", { outcomes: outcomes.length, unsuccessful: outcomes.filter((event) => event["dashpot.outcome.result"] !== "succeeded")
    .map((event) => ({ kind: event["dashpot.process.kind"], result: event["dashpot.outcome.result"], reason: event["dashpot.hook.reason"] ?? null })) });
  for (const entry of fixtureProcesses()) {
    if (entry.pid === process.pid) continue;
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm, cmdline: retained(entry.cmdline) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid).filter((pid) => pid !== process.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
  process.exit(0);
}
