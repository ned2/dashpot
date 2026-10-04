// Measurement run for Issue #379: the OpenCode 2.0.22 scenarios left after
// the acceptance run, on the shared service and, where it applies,
// `--standalone`. It records what Dashpot shows while a model's background
// shell command outlives its session's execution, and what moving,
// interrupting, deleting and stopping do to that command; what an `opencode
// run` does when a tool asks for permission under a person's default
// permissions, with and without `--auto`, and when a worker's `opencode run
// --session <lead>` report starts a lead turn that asks; what Dashpot shows
// while an ask waits for its answer; and what a retried and a failed
// execution look like to Dashpot.
//
// Copied from the self-relocation run (opencode-423) and cut down. It drives
// OpenCode 2.0.22 against a loopback OpenAI-compatible model fixture, in
// disposable configuration and state, with the background service on a
// private port, so the operator's own OpenCode service is never contacted.
// Dashpot is built from this checkout and installed into a fixture
// environment, and `dashpot integrate opencode` from that installation writes
// the plugin, the skills and the worker agent the run exercises. The trace is
// metadata only; the runner asserts only what it needs to keep going, and the
// independent verifier checks the trace against the spike.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode 2.0.22 binary> > log 2>&1
// It is done when it prints "All scenarios completed". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
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

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-379-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree and three linked Worktrees.
const fixture = path.join(root, "repository");
const tree = (name) => path.join(root, "repository.worktrees", name);
const [treeA, treeB, treeC] = ["a", "b", "c"].map(tree);
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
const sha256Tree = (directory) => {
  if (!existsSync(directory)) return null;
  const hash = createHash("sha256");
  for (const name of readdirSync(directory, { recursive: true }).map(String).toSorted()) {
    const file = path.join(directory, name);
    try { hash.update(name + "\0" + readFileSync(file)); } catch {}
  }
  return hash.digest("hex");
};

// Dashpot, built from this checkout and installed outside every Worktree, as
// a person's installation is; its helper is what the plugin is bound to.
const venv = path.join(root, "venv");
execFileSync(uv, ["build", "-q", "--wheel", "-o", path.join(root, "dist"), checkout], { stdio: "pipe" });
const [wheel] = readdirSync(path.join(root, "dist")).filter((name) => name.endsWith(".whl"));
execFileSync(uv, ["venv", "-q", "--python", path.join(checkout, ".venv", "bin", "python"), venv], { stdio: "pipe" });
execFileSync(uv, ["pip", "install", "-q", "--offline", "--python", path.join(venv, "bin", "python"), path.join(root, "dist", wheel)], { stdio: "pipe" });
const dashpot = path.join(venv, "bin", "dashpot");
const helper = path.join(venv, "bin", "dashpot-opencode-hook");
const installed = execFileSync(path.join(venv, "bin", "python"), ["-c", "import dashpot, os; print(os.path.dirname(dashpot.__file__))"], { encoding: "utf8" }).trim();
// The Dashpot sources the run exercises; the installed copies must be them.
const exercised = ["plugins/opencode.js", "sessions/opencode_publish.py", "sessions/opencode_publishers.py", "sessions/hook_claims.py",
  "sessions/hook_scan.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/harnesses.py", "sessions/work.py",
  "sessions/work_store.py", "sessions/integrate.py", "sessions/agent_bindings.py", "repository/cleanup/obstacles.py", "hook.py", "agents/dashpot-worker.md"];

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
  // Sessions outside a configured checkout would publish here.
  DASHPOT_STATE_DIR: path.join(root, "dashpot-state"),
  // Ancestry walks from shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_HELPER: helper,
};
// OpenCode installed as its curl installer does, at ~/.opencode/bin/opencode,
// as a copy: nothing the fixture does can reach the operator's binary.
const curlBin = path.join(env.HOME, ".opencode", "bin");
const configHome = path.join(env.XDG_CONFIG_HOME, "opencode");
for (const dir of [fixture, env.HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, curlBin, configHome]) mkdirSync(dir, { recursive: true });
copyFileSync(binary, path.join(curlBin, "opencode"));
chmodSync(path.join(curlBin, "opencode"), 0o755);
const basePath = `${path.dirname(process.execPath)}:/usr/bin:/bin`;
env.PATH = `${curlBin}:${basePath}`;
const version = execFileSync(path.join(curlBin, "opencode"), ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "opencode v2.0.22", `unexpected OpenCode version: ${version}`);

// A Dashpot Project with a markdown Issue Source, one Issue per binding.
const project = (directory, name, issues) => {
  mkdirSync(path.join(directory, ".dashpot"), { recursive: true });
  mkdirSync(path.join(directory, "issues"), { recursive: true });
  writeFileSync(path.join(directory, ".dashpot", "config.json"), JSON.stringify({ projectId: `project:${name}`, displayLabel: name,
    repositoryId: `repository:${name}`, issueSource: { kind: "markdown", path: "issues" } }));
  for (let number = 1; number <= issues; number++) {
    const front = { id: `I_${name}_${number}`, number, reference: `issue-${number}`, state: "open", stateReason: null, labels: [], assignees: [],
      author: "fixture", relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
      createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
    writeFileSync(path.join(directory, "issues", `issue-${number}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
  }
  const git = (...args) => execFileSync("git", ["-C", directory, ...args], { env, stdio: "pipe" });
  git("init", "--initial-branch=main");
  git("add", ".");
  git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
  return git;
};
const git = project(fixture, "fixture", 12);
for (const [name, linked] of [["a", treeA], ["b", treeB], ["c", treeC]]) git("worktree", "add", "-b", name, linked);
const worktrees = [fixture, treeA, treeB, treeC];

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
// The sink takes only the shell reporter's records: a stray client of an
// earlier experiment can still post to a reused loopback port, and its
// payload holds paths and prompts the trace must not retain.
const sink = await listen(async (req, res) => {
  let record = null;
  try { record = await body(req); } catch {}
  if (req.url === "/command" && typeof record?.label === "string" && ["start", "end"].includes(record.phase)) {
    // A worker's `opencode run` prints its lead's reply; keep its tail only.
    if (record.exec) record.exec = { ...record.exec, stdout: retained(record.exec.stdout ?? "").slice(-600), stderr: retained(record.exec.stderr ?? "").slice(-600) };
    trace("command", record);
  } else trace("sink.foreign", { method: req.method, url: retained(String(req.url)).slice(0, 80) });
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// --- The fixture model -------------------------------------------------------
//
// The latest user turn holding a `PROBE:<label>` text selects a sequence of
// steps; a step is one tool call or several made at once, and the turn ends
// with a text naming the label once every step has run. A label with no
// sequence runs one shell command of that name. A notice OpenCode adds to a
// session, which holds no label, neither restarts nor ends the sequence it
// arrives in. A label in `failures` is answered with an HTTP error instead,
// for its first `times` requests.
const commandScript = path.join(here, "command.mjs");
const known = {};
// A shell call; options are the tool's own `workdir`, `timeout` and `background`.
const shell = (command, options = {}) => ({ name: "shell", arguments: { command, ...options } });
const report = (label, hold = 0, options = {}) => shell(`node ${commandScript} ${label} ${hold}`, options);
const background = (label, hold) => report(label, hold, { background: true });
const work = (label, ...args) => shell(`node ${commandScript} ${label} 0 -- work ${args.join(" ")}`);
const bind = (prefix, issue) => [work(`${prefix}-start`, "start", issue), work(`${prefix}-show`, "show")];
// The cheapest tool call OpenCode's default rules ask for: reading `.env`,
// decided before the file is opened, so the file need not exist.
const readEnv = () => ({ name: "read", arguments: { path: ".env" } });
const subagent = (child) => ({ name: "subagent", arguments: { agent: "dashpot-worker", description: `Worker ${child}`, prompt: `PROBE:${child}`, background: true } });
const sequences = {
  "bg-bind": () => bind("bg", "issue-1"),
  // A background command that outlives the execution that started it.
  "bg-launch": () => [background("bg-hold", 12000)],
  "bg-move-bind": () => bind("bg-move", "issue-2"),
  "bg-move-launch": () => [background("bg-move-hold", 12000)],
  // A background command beside a foreground one the runner interrupts.
  "bg-int-launch": () => [background("bg-int-hold", 12000), report("bg-int-busy", 20000)],
  "bg-del-bind": () => bind("bg-del", "issue-3"),
  "bg-del-launch": () => [background("bg-del-hold", 10000)],
  "bg-stop-bind": () => bind("bg-stop", "issue-4"),
  "bg-stop-launch": () => [background("bg-stop-hold", 120000)],
  "retry-bind": () => bind("retry", "issue-5"),
  "retry": () => [report("retry-after")],
  // Under default permissions: bound, then a read the rules ask for, then a
  // command that shows whether the turn went on.
  "run-ask": () => [...bind("run-ask", "issue-6"), readEnv(), report("run-ask-after")],
  "run-auto": () => [readEnv(), report("run-auto-after")],
  "ask-bind": () => bind("ask", "issue-7"),
  "ask-hold": () => [readEnv(), report("ask-after")],
  // A worker reporting to its lead with `opencode run --session`, as the
  // execute-issues skill directs, from a background shell; the lead's turn
  // it starts asks. The prompt's colon is escaped, so the shell's completion
  // notice, which quotes the command, holds no label.
  "lead-bind": () => bind("lead", "issue-8"),
  "lead-launch": () => [subagent("worker")],
  "worker": () => [shell(`node ${commandScript} worker-report 0 -- exec opencode run --session ${known.lead} PROBE\\:lead-ask`, { background: true }),
    report("worker-after", 8000)],
  "lead-ask": () => [readEnv(), report("lead-ask-after")],
  "sa-bg": () => [background("sa-bg-hold", 8000)],
};
const failures = {
  // Retried: OpenCode's classifier retries a 5xx.
  "retry": { status: 500, times: 2 },
  // Not retried: a 400 is an invalid request.
  "fail": { status: 400, times: Infinity },
  "run-fail": { status: 400, times: Infinity },
};
const text = (message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
const probes = (message) => [...text(message).matchAll(/PROBE:([a-z0-9-]+)/g)].map((match) => match[1]);
// OpenCode's notices that a background child or a background shell ended.
const SUBAGENT_NOTICE = /<subagent sessionID=\\?"(ses_\w+)\\?" state=\\?"(\w+)\\?"/g;
const SHELL_NOTICE = /<shell id=\\?"([^"\\]+)\\?" state=\\?"(\w+)\\?"[^>]*>(?:\\n|\n)?([^<]{0,160})/g;
const modelRequests = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const anchor = messages.findLastIndex((message) => message.role === "user" && probes(message).length);
  const label = anchor >= 0 ? probes(messages[anchor]).at(-1) : null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const titled = /title generator/i.test(system) || !tools.length;
  const lastAssistant = messages.findLastIndex((message) => message.role === "assistant");
  const step = messages.slice(anchor + 1).filter((message) => message.role === "assistant").length;
  const count = titled ? 0 : (modelRequests.get(label) ?? 0) + 1;
  if (!titled) modelRequests.set(label, count);
  const failure = !titled && failures[label] && count <= failures[label].times ? failures[label] : null;
  const sequence = (label && (sequences[label]?.() ?? [report(label)])) || [];
  const planned = titled || failure ? undefined : sequence[step];
  const calls = planned === undefined ? [] : Array.isArray(planned) ? planned : [planned];
  // Each notice, wherever it sits; fresh when it arrived after this
  // session's previous step.
  const notices = titled ? [] : messages.flatMap((message, index) => message.role === "tool" ? [] : [
    ...[...text(message).matchAll(SUBAGENT_NOTICE)].map(([, id, state]) => ({ of: "subagent", id, state, fresh: index > lastAssistant })),
    ...[...text(message).matchAll(SHELL_NOTICE)].map(([, id, state, head]) => ({ of: "shell", id, state, fresh: index > lastAssistant,
      head: retained(head.replaceAll("\\n", " ")).trim().slice(0, 120) })),
  ]);
  const last = messages.at(-1);
  trace("model.request", { label, step, tools: calls.map((call) => call.name), count, titled, failure: failure?.status,
    sessionID: req.headers["x-opencode-session-id"] ?? null, parentID: req.headers["x-opencode-parent-session-id"] ?? null,
    messages: messages.length, probes: titled ? undefined : messages.filter((message) => message.role === "user").flatMap(probes),
    notices: notices.length ? notices : undefined,
    lastTool: titled || last?.role !== "tool" ? undefined : retained(text(last)).slice(0, 400) });
  if (failure) {
    res.writeHead(failure.status, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { message: `Fixture failure ${failure.status}`, type: failure.status >= 500 ? "server_error" : "invalid_request_error" } }));
    return;
  }
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (calls.length) {
    chunk({ role: "assistant", tool_calls: calls.map((call, index) => ({ index, id: `call_${label}_${step}_${count}_${index}`, type: "function",
      function: { name: call.name, arguments: JSON.stringify(call.arguments) } })) });
  } else chunk({ role: "assistant", content: titled ? "Fixture title" : `Fixture complete: ${label}.` });
  chunk({}, calls.length ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed
// until the run switches to a person's default rules, and the background
// service on a private port with a known password.
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
const opencodeConfig = ({ permissions = [{ action: "*", resource: "*", effect: "allow" }] } = {}) => JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  ...(permissions ? { permissions } : {}),
}, null, 2);

// --- Observation -------------------------------------------------------------

const run = (program, args, { cwd = fixture } = {}) => {
  const result = spawnSync(program, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: result.status, stdout: retained(result.stdout ?? ""), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const integrate = (label, args, options = {}) => trace("integrate", { label, args, ...run(dashpot, ["integrate", ...args], options) });
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label) => {
  const result = run(dashpot, ["--json"]);
  let snapshot = null;
  try { snapshot = JSON.parse(result.stdout); } catch {}
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((item) => item.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: String(message).slice(0, 400) }));
  return trace("observation", { label, error: snapshot ? null : result.stderr, runs, diagnostics });
};
// What Cleanup says about one linked Worktree.
const check = (label, worktree) => {
  const result = run(dashpot, ["worktree", "check", worktree, "--json"]);
  let assessment = null;
  try { assessment = JSON.parse(result.stdout); } catch {}
  return trace("cleanup", { label, worktree, status: result.status,
    obstacles: assessment ? (assessment.obstacles ?? []).map(({ kind, detail }) => ({ kind, detail: String(detail ?? "").slice(0, 400) })) : null,
    error: assessment ? undefined : (result.stdout + result.stderr).slice(0, 1500) });
};
const readJson = (file) => { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return null; } };
const listJson = (directory) => { try { return readdirSync(directory).filter((name) => name.endsWith(".json")); } catch { return []; } };
// Every hook record and Work Store record, by Worktree: where each session
// is recorded, its state, and each Agent Run's Issue Binding.
const stateFiles = (label) => {
  const sessions = {};
  const runs = {};
  for (const worktree of worktrees) {
    const state = path.join(worktree, ".dashpot", "state");
    for (const name of listJson(path.join(state, "sessions"))) {
      const record = readJson(path.join(state, "sessions", name));
      if (record) sessions[`${worktree}/${name}`] = { state: record.state ?? null, event: record.event ?? null, cwd: record.cwd ?? null,
        session: record.sessionId ?? null, subagents: record.liveSubagents ?? null };
    }
    for (const name of listJson(path.join(state, "work"))) {
      const record = readJson(path.join(state, "work", name));
      if (record) runs[`${worktree}/${name}`] = { harness: record.harness, issue: record.issueReference, startedAt: record.startedAt,
        workingDirectory: record.workingDirectory, session: record.sessionId ?? null };
    }
  }
  return trace("state", { label, sessions, runs });
};
// Every Runtime Event the fixture's Dashpot processes recorded, flattened.
const eventLog = () => {
  const events = [];
  const directories = [...worktrees.map((worktree) => path.join(worktree, ".dashpot", "state", "events")), path.join(env.XDG_STATE_HOME, "dashpot", "events"),
    path.join(env.DASHPOT_STATE_DIR, "events")];
  for (const directory of directories) {
    let names = [];
    try { names = readdirSync(directory); } catch { continue; }
    for (const name of names) {
      for (const line of readFileSync(path.join(directory, name), "utf8").split("\n")) {
        if (!line) continue;
        const flat = {};
        const merge = (value) => { for (const [key, item] of Object.entries(value)) { if (item && typeof item === "object" && !Array.isArray(item)) merge(item); else flat[key] = item; } };
        try { merge(JSON.parse(line)); } catch { continue; }
        events.push(flat);
      }
    }
  }
  return events;
};
const command = (label, phase = "end") => records.findLast((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (await predicate()) return; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
const settle = (ms = 1500) => delay(ms);
// Every process whose environment names the fixture configuration, so the
// operator's own processes are never observed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    if (!inFixture(name, env.XDG_CONFIG_HOME)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
// A background command's process, by the reporter's own pid: whether it
// still runs, where, and in which process group and session.
const sample = (label, reporter) => {
  const pid = command(reporter, "start")?.pid;
  let entry = null;
  try { entry = describe(pid); } catch {}
  return trace("process", { label, reporter, pid: pid ?? null, alive: Boolean(entry), cwd: entry?.cwd ?? null, pgrp: entry?.pgrp ?? null,
    sid: entry?.sid ?? null, servicePid: service.pid });
};
// A model request in one session carrying a fresh notice.
const noticed = (sessionID, of, after = 0) => records.some((record) => record.kind === "model.request" && record.receipt > after
  && record.sessionID === sessionID && record.notices?.some((notice) => notice.fresh && notice.of === of));
const serverEvents = (sessionID, type) => records.filter((record) => record.kind === "server.event" && record.sessionID === sessionID && record.type === type);
// Whether OpenCode started an execution of the session after a receipt.
const woke = (sessionID, after) => serverEvents(sessionID, "session.execution.started").some((record) => record.receipt > after);

// --- The background service and its clients -----------------------------------

const registration = () => readJson(path.join(env.XDG_STATE_HOME, "opencode", "service.json"));
const service = { url: `http://127.0.0.1:${servicePort}`, pid: null, events: null };
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
// OpenCode's server event stream: session lifecycle, executions, retries,
// background shells and permissions, as a client sees them.
const STREAMED = /^(session\.(created|deleted|moved|execution\.|retry\.|shell\.)|permission\.)/;
const subscribe = (name) => {
  const controller = new AbortController();
  (async () => {
    try {
      const response = await fetch(service.url + "/api/event", { headers: { authorization }, signal: controller.signal });
      const decoder = new TextDecoder();
      let buffer = "";
      for await (const chunk of response.body) {
        buffer += decoder.decode(chunk, { stream: true });
        let at;
        while ((at = buffer.indexOf("\n\n")) >= 0) {
          const block = buffer.slice(0, at);
          buffer = buffer.slice(at + 2);
          let event;
          try { event = JSON.parse(block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5)).join("")); } catch { continue; }
          if (!STREAMED.test(event.type ?? "")) continue;
          const data = event.data ?? {};
          trace("server.event", { name, type: event.type, location: event.location?.directory ?? null, sessionID: data.sessionID ?? null,
            parentID: data.parentID ?? null, reason: data.reason ?? null, to: event.type === "session.moved" ? data.location?.directory ?? null : undefined,
            action: data.action ?? undefined, resources: data.resources ?? undefined, reply: data.reply ?? undefined, requestID: data.id ?? data.requestID ?? undefined,
            attempt: data.attempt ?? undefined, error: data.error ? { type: data.error.type ?? null, status: data.error.status ?? null } : undefined });
        }
      }
    } catch {}
  })();
  return controller;
};
const awaitService = async (label) => {
  let found = null;
  await waitFor(() => (found = registration()) && alive(found.pid), `${label}: service registered`, 60000);
  let ready = false;
  for (let attempt = 0; attempt < 200 && !ready; attempt++) {
    ready = (await request("GET", "/api/info").catch(() => null))?.status === 200;
    if (!ready) await delay(100);
  }
  assert(ready, `${label}: service never ready`);
  service.pid = found.pid;
  service.events?.abort();
  service.events = subscribe(label);
  await settle(500);
  trace("service", { label, pid: found.pid, version: found.version ?? null });
  return found;
};
const cli = (args, { cwd = fixture } = {}) => {
  const result = spawnSync("opencode", args, { cwd, env: { ...env, PWD: cwd }, encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const restartService = async (label, config) => {
  writeFileSync(path.join(configHome, "opencode.json"), config);
  const stopping = service.pid;
  trace("service.stop", { label, ...cli(["service", "stop"]) });
  await waitFor(() => !alive(stopping), `${label}: service stopped`, 15000);
  trace("service.stopped", { label, pid: stopping });
  return stopping;
};
// A CLI client run in the background, stdin closed, as a script runs it.
const stripAnsi = (value) => value.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const client = (name, args, { cwd = fixture } = {}) => {
  const child = spawn("opencode", args, { cwd, env: { ...env, PWD: cwd, SPIKE_CLIENT: name }, stdio: ["ignore", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.stderr.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() };
    trace("client.exit", { name, code, signal, output: retained(state.output).slice(-1200) }); });
  trace("client.spawn", { name, args, cwd, pid: child.pid });
  return state;
};
const finished = async (state, timeout = 90000) => { await waitFor(() => state.exited, `${state.name} exit`, timeout); return state.exited; };
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
const sessionInfo = async (label, id) => {
  const answer = await request("GET", `/api/session/${id}`);
  return trace("session.info", { label, sessionID: id, ...(answer.status === 200 ? { location: answer.body?.location?.directory ?? null } : { missing: answer.status }) });
};
// The commands OpenCode's shell API lists as running at one location, named
// by its query and by its location header.
const shells = async (label, directory) => {
  const listed = async (headers, query) => {
    const response = await fetch(`${service.url}/api/shell${query}`, { headers: { authorization, ...headers }, signal: AbortSignal.timeout(10000) });
    let parsed = null;
    try { parsed = await response.json(); } catch {}
    const list = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.data) ? parsed.data : [];
    return { status: response.status, keys: parsed && !Array.isArray(parsed) ? Object.keys(parsed) : null, shells: list.map((item) => ({ id: item.id,
      status: item.status, cwd: item.cwd, pid: item.pid ?? null, session: item.metadata?.sessionID ?? null, command: retained(item.command ?? "").slice(0, 200) })) };
  };
  return trace("shells", { label, directory, byQuery: await listed({}, `?directory=${encodeURIComponent(directory)}`),
    byHeader: await listed({ "x-opencode-directory": encodeURIComponent(directory) }, "") });
};
const pending = async (label, id) => {
  const answer = await request("GET", `/api/session/${id}/permission`);
  const list = Array.isArray(answer.body) ? answer.body : [];
  return trace("permissions.pending", { label, sessionID: id, status: answer.status, asks: list.map((item) => ({ id: item.id, action: item.action ?? null,
    resources: retained(JSON.stringify(item.resources ?? null)) })) });
};

const pluginFile = path.join(configHome, "plugins", "dashpot.js");
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), servicePort, fixture, trees: { a: treeA, b: treeB, c: treeC }, wheel,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(checkout, "src", "dashpot", file))),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs"].map((file) => [file, sha256(path.join(here, file))]),
      ...exercised.map((file) => [`src/dashpot/${file}`, sha256(path.join(checkout, "src", "dashpot", file))]),
    ]) });

  // The integration, as a person installs it, every tool allowed.
  trace("scenario", { name: "installer" });
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig());
  integrate("install", ["opencode"]);
  assert(readFileSync(pluginFile, "utf8").includes(JSON.stringify(helper)), "the plugin names the installed helper");
  trace("files", { label: "installed", plugin: sha256(pluginFile), workerAgent: existsSync(path.join(configHome, "agent", "dashpot-worker.md")) });
  trace("service.start", { label: "start", ...cli(["service", "start"]) });
  await awaitService("start");

  // A bound session in Worktree `a` starts a background command; its turn
  // ends while the command runs, and the command's end wakes it.
  trace("scenario", { name: "background" });
  known.bg = await session("Background", treeA);
  await prompt(known.bg, "bg-bind");
  await prompt(known.bg, "bg-launch");
  await waitFor(() => command("bg-hold", "start"), "background command started", 15000);
  await settle();
  sample("bg-running", "bg-hold");
  await shells("bg-running", treeA);
  stateFiles("bg-running");
  observe("bg-running");
  check("tree-a-bg-running", treeA);
  await waitFor(() => command("bg-hold"), "background command ended", 30000);
  await waitFor(() => woke(known.bg, command("bg-hold").receipt), "session woken by the notice", 30000);
  await idle(known.bg, "bg-woken");
  await settle();
  sample("bg-ended", "bg-hold");
  stateFiles("bg-after");
  observe("bg-after");

  // The same, then the session moves to the main Worktree while its command
  // still runs in `b`.
  trace("scenario", { name: "background-move" });
  known.bgMove = await session("BackgroundMove", treeB);
  await prompt(known.bgMove, "bg-move-bind");
  await prompt(known.bgMove, "bg-move-launch");
  await waitFor(() => command("bg-move-hold", "start"), "background command started", 15000);
  const moved = await request("POST", `/api/session/${known.bgMove}/move`, { directory: fixture });
  trace("move", { label: "bg-move", sessionID: known.bgMove, to: fixture, status: moved.status });
  await settle();
  await sessionInfo("bg-move-moved", known.bgMove);
  sample("bg-move-running", "bg-move-hold");
  await shells("bg-move-running-old", treeB);
  await shells("bg-move-running-new", fixture);
  stateFiles("bg-move-running");
  observe("bg-move-running");
  check("tree-b-bg-move-running", treeB);
  await waitFor(() => command("bg-move-hold"), "background command ended", 30000);
  await waitFor(() => woke(known.bgMove, command("bg-move-hold").receipt), "moved session woken by the notice", 30000);
  await idle(known.bgMove, "bg-move-woken");
  stateFiles("bg-move-after");
  observe("bg-move-after");

  // A background command beside a foreground one; the runner interrupts the
  // session while both run.
  trace("scenario", { name: "background-interrupt" });
  known.bgInt = await session("BackgroundInterrupt", fixture);
  const intTurn = records.length;
  await send(known.bgInt, "bg-int-launch");
  await waitFor(() => command("bg-int-hold", "start") && command("bg-int-busy", "start"), "both commands started", 15000);
  await settle(1000);
  const interrupted = await request("POST", `/api/session/${known.bgInt}/interrupt`, {});
  trace("interrupt", { label: "bg-int", sessionID: known.bgInt, status: interrupted.status, body: interrupted.body });
  await idle(known.bgInt, "bg-int-interrupted");
  await settle();
  sample("bg-int-hold-after-interrupt", "bg-int-hold");
  sample("bg-int-busy-after-interrupt", "bg-int-busy");
  await shells("bg-int-after-interrupt", fixture);
  stateFiles("bg-int-after-interrupt");
  try { await waitFor(() => command("bg-int-hold"), "background command ended", 30000); } catch {}
  try { await waitFor(() => woke(known.bgInt, command("bg-int-hold")?.receipt ?? intTurn), "interrupted session woken", 15000); } catch {}
  await idle(known.bgInt, "bg-int-woken");
  trace("woken", { label: "bg-int", woke: woke(known.bgInt, command("bg-int-hold")?.receipt ?? intTurn), noticed: noticed(known.bgInt, "shell", intTurn) });

  // A bound session in `c` starts a background command and is deleted while
  // it runs.
  trace("scenario", { name: "background-delete" });
  known.bgDel = await session("BackgroundDelete", treeC);
  await prompt(known.bgDel, "bg-del-bind");
  const delTurn = records.length;
  await prompt(known.bgDel, "bg-del-launch");
  await waitFor(() => command("bg-del-hold", "start"), "background command started", 15000);
  trace("session.delete", { label: "bg-del", ...cli(["session", "delete", known.bgDel]) });
  await settle();
  await sessionInfo("bg-del-deleted", known.bgDel);
  sample("bg-del-running", "bg-del-hold");
  await shells("bg-del-running", treeC);
  stateFiles("bg-del-running");
  observe("bg-del-running");
  check("tree-c-bg-del-running", treeC);
  try { await waitFor(() => command("bg-del-hold"), "background command ended", 30000); } catch {}
  await settle(3000);
  trace("woken", { label: "bg-del", woke: woke(known.bgDel, command("bg-del-hold")?.receipt ?? delTurn), noticed: noticed(known.bgDel, "shell", delTurn) });

  // A retried execution: the provider answers 500 twice; and a failed one:
  // it answers 400.
  trace("scenario", { name: "retry" });
  known.retry = await session("Retry", fixture);
  await prompt(known.retry, "retry-bind");
  await send(known.retry, "retry");
  await waitFor(() => serverEvents(known.retry, "session.retry.scheduled").length >= 1, "a retry scheduled", 30000);
  stateFiles("retry-waiting");
  observe("retry-waiting");
  await idle(known.retry, "retry");
  await settle();
  stateFiles("retry-after");
  observe("retry-after");
  trace("scenario", { name: "failed" });
  await send(known.retry, "fail");
  await idle(known.retry, "fail");
  await settle();
  stateFiles("fail-after");
  observe("fail-after");
  const runFail = client("run-fail", ["run", "--title", "RunFail", "-m", "loop/fixture", "PROBE:run-fail"]);
  await finished(runFail);

  // A bound background command still running when the service stops; the
  // service comes back with a person's default permission rules.
  trace("scenario", { name: "background-stop" });
  known.bgStop = await session("BackgroundStop", treeB);
  await prompt(known.bgStop, "bg-stop-bind");
  await prompt(known.bgStop, "bg-stop-launch");
  await waitFor(() => command("bg-stop-hold", "start"), "background command started", 15000);
  await settle();
  const stopTurn = records.length;
  const stopped = await restartService("background-stop", opencodeConfig({ permissions: null }));
  await settle();
  sample("bg-stop-after-stop", "bg-stop-hold");
  stateFiles("bg-stop-after-stop");
  trace("service.start", { label: "default-permissions", ...cli(["service", "start"]) });
  await awaitService("default-permissions");
  assert.notEqual(service.pid, stopped);
  await settle(3000);
  sample("bg-stop-after-start", "bg-stop-hold");
  trace("woken", { label: "bg-stop-restart", woke: woke(known.bgStop, stopTurn) });
  await prompt(known.bgStop, "bg-stop-again");
  trace("woken", { label: "bg-stop", noticed: noticed(known.bgStop, "shell", stopTurn) });

  // `opencode run` under the default rules: without `--auto`, then with it.
  trace("scenario", { name: "run-default" });
  const runAsk = client("run-ask", ["run", "--title", "RunAsk", "-m", "loop/fixture", "PROBE:run-ask"], { cwd: treeC });
  await finished(runAsk);
  known.runAsk = command("run-ask-start", "start")?.env?.OPENCODE_SESSION_ID ?? null;
  await settle();
  stateFiles("run-ask-after");
  observe("run-ask-after");
  check("tree-c-run-ask-after", treeC);
  const runAuto = client("run-auto", ["run", "--auto", "--title", "RunAuto", "-m", "loop/fixture", "PROBE:run-auto"], { cwd: treeC });
  await finished(runAuto);

  // An ask no client answers, as one a TUI shows the person: Dashpot's view
  // while it waits, then the runner's answer.
  trace("scenario", { name: "ask-pending" });
  known.ask = await session("Ask", treeA);
  await prompt(known.ask, "ask-bind");
  const askTurn = records.length;
  await send(known.ask, "ask-hold");
  await waitFor(() => records.some((record) => record.receipt > askTurn && record.kind === "server.event" && record.type === "permission.asked"
    && record.sessionID === known.ask), "permission asked", 30000);
  await settle(2000);
  const asks = await pending("ask-pending", known.ask);
  stateFiles("ask-pending");
  observe("ask-pending");
  for (const ask of asks.asks) {
    const answer = await request("POST", `/api/session/${known.ask}/permission/${ask.id}/reply`, { decision: "once" });
    trace("permission.reply", { label: "ask-pending", decision: "once", status: answer.status });
  }
  await idle(known.ask, "ask-answered");
  await settle();
  stateFiles("ask-after");
  observe("ask-after");

  // A worker's report to its idle lead starts a lead turn that asks.
  trace("scenario", { name: "worker-report" });
  known.lead = await session("Lead", fixture);
  await prompt(known.lead, "lead-bind");
  await prompt(known.lead, "lead-launch");
  await waitFor(() => command("worker-report"), "worker's report ended", 90000);
  await waitFor(() => command("worker-after"), "worker ended", 30000);
  await idle(known.lead, "lead-after-report");
  await settle(2000);
  await pending("lead-after-report", known.lead);
  stateFiles("lead-after-report");
  observe("lead-after-report");

  // A `--standalone` run whose model leaves a background command running.
  trace("scenario", { name: "standalone-background" });
  const standalone = client("sa-bg", ["run", "--standalone", "--auto", "--title", "StandaloneBackground", "-m", "loop/fixture", "PROBE:sa-bg"], { cwd: treeC });
  await waitFor(() => command("sa-bg-hold", "start"), "standalone background command started", 90000);
  sample("sa-bg-running", "sa-bg-hold");
  await finished(standalone);
  await settle(1000);
  sample("sa-bg-after-exit", "sa-bg-hold");
  await delay(10000);
  sample("sa-bg-later", "sa-bg-hold");
  trace("standalone.ended", { label: "sa-bg", reported: Boolean(command("sa-bg-hold")) });

  trace("models", { requests: Object.fromEntries(modelRequests) });
  trace("known", { sessions: known });
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
} finally {
  // The helper's own record of each run: outcomes by kind, and every outcome
  // that did not succeed.
  const outcomes = eventLog().filter((event) => String(event["dashpot.process.kind"] ?? "").startsWith("hook:opencode"));
  const summary = {};
  for (const event of outcomes) {
    const entry = summary[event["dashpot.process.kind"]] ??= { runs: 0, results: {} };
    if (event["event.name"] === "process.end") entry.runs += 1;
    if (event["event.name"] === "hook.outcome") entry.results[event["dashpot.outcome.result"]] = (entry.results[event["dashpot.outcome.result"]] ?? 0) + 1;
  }
  trace("events", { summary, unsuccessful: outcomes.filter((event) => event["event.name"] === "hook.outcome" && event["dashpot.outcome.result"] !== "succeeded")
    .map((event) => ({ kind: event["dashpot.process.kind"], result: event["dashpot.outcome.result"], reason: event["dashpot.hook.reason"] ?? null,
      error: event["error.type"] ?? null, session: event["dashpot.agent_session.id"] ?? null })) });
  if (service.pid && alive(service.pid)) {
    trace("service.stop", { label: "final", ...cli(["service", "stop"]) });
    try { await waitFor(() => !alive(service.pid), "final service exit", 10000); } catch {}
  }
  service.events?.abort();
  await delay(1000);
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
