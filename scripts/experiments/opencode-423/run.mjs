// Acceptance run for Issue #423: a root OpenCode 2.0.22 Agent Session moving
// itself as the dashpot-issue-work skill's OpenCode move describes
// (ADR 0094). The fixture model follows the skill's dispatch, finish and
// switch flows, choosing each step from the output of the one before, as a
// model reading the skill would: `work show`, the move through `execute`,
// the next step's `pwd` and `integrate opencode --status`, then `work show`
// and, only when no run came along, `work start`. It also drives the
// failures the skill hands off on, a move made in the same step as other
// work, a move held while a worker runs, and the move's permission paths.
//
// Copied from the worker-mechanics run (opencode-421) and cut down. It
// drives OpenCode 2.0.22 against a loopback OpenAI-compatible model fixture,
// in disposable configuration and state, with the background service on a
// private port, so the operator's own OpenCode service is never contacted.
// Dashpot is built from this checkout and installed into a fixture
// environment, and `dashpot integrate opencode` from that installation writes
// the plugin and the skill the run exercises. The trace is metadata only; the
// runner asserts only what it needs to keep going, and the independent
// verifier checks the trace against the acceptance record.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode 2.0.22 binary> > log 2>&1
// It is done when it prints "All scenarios completed". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
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

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-423-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree and five linked Worktrees: `e`'s state
// directory is made unwritable, so a move there leaves Dashpot no evidence.
const fixture = path.join(root, "repository");
const tree = (name) => path.join(root, "repository.worktrees", name);
const [treeA, treeB, treeC, treeD, treeE] = ["a", "b", "c", "d", "e"].map(tree);
const missing = path.join(root, "repository.worktrees", "missing");
const plainFile = path.join(root, "repository.worktrees", "not-a-directory");
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
const exercised = ["plugins/opencode.js", "sessions/opencode_publish.py", "sessions/opencode_publisher_records.py", "sessions/hook_claims.py",
  "sessions/hook_scan.py", "sessions/hook_publish.py", "sessions/hook_records.py", "sessions/harnesses.py", "sessions/work.py",
  "sessions/work_store.py", "sessions/integrate/across.py", "sessions/integrate/agent_copies.py", "sessions/integrate/arguments.py",
  "sessions/integrate/diagnostics.py", "sessions/integrate/environment.py", "sessions/integrate/harness.py",
  "sessions/integrate/installer.py", "sessions/integrate/opencode_plugin.py", "sessions/integrate/publisher.py",
  "sessions/integrate/registry.py", "sessions/integrate/skill_copies.py", "sessions/integrate/writes.py", "sessions/agent_bindings.py",
  "repository/cleanup/obstacles.py", "hook.py", "agents/dashpot-worker.md"];
const bundledSkill = path.join("skills", "dashpot-issue-work");

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
const git = project(fixture, "fixture", 10);
for (const [name, linked] of [["a", treeA], ["b", treeB], ["c", treeC], ["d", treeD], ["e", treeE]]) git("worktree", "add", "-b", name, linked);
writeFileSync(plainFile, "Not a directory.\n");
const worktrees = [fixture, treeA, treeB, treeC, treeD, treeE];

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
  if (req.url === "/command" && typeof record?.label === "string" && ["start", "end"].includes(record.phase)) trace("command", record);
  else trace("sink.foreign", { method: req.method, url: retained(String(req.url)).slice(0, 80) });
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// --- The fixture model -------------------------------------------------------
//
// The latest user turn holding a `PROBE:<label>` text selects what the model
// does. A label in `flows` is one of the skill's flows: the model reads the
// previous step's outcome (the command it ran and that command's output, or
// the move tool's result) and chooses the next step as the skill says, or
// ends the turn with a text naming its decision. A label in `sequences` is a
// fixed list of steps, for the patterns the skill rules out; a step is one
// tool call or several made at once. A label with neither runs one shell
// command of that name.
const commandScript = path.join(here, "command.mjs");
const known = {};
const shell = (command, options = {}) => ({ name: "shell", arguments: { command, ...options } });
const report = (label, hold = 0) => shell(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => shell(`node ${commandScript} ${label} 0 -- work ${args.join(" ")}`);
// The skill's step 3: `pwd` and `integrate opencode --status` in one shell,
// with no `cd` or `workdir`; the reporter records the shell's directory.
const where = (label) => shell(`node ${commandScript} ${label} 0 -- integrate opencode --status`);
const subagent = (child) => ({ name: "subagent", arguments: { agent: "dashpot-worker", description: `Worker ${child}`, prompt: `PROBE:${child}`, background: true } });
const execute = (code) => ({ name: "execute", arguments: { code } });
const moveSession = (directory) => execute(`return await tools.opencode.session_move(${JSON.stringify({ directory })})`);
const end = (decision) => ({ end: decision });

// A flow can run one label again in a later turn, so the latest record is
// the step's own.
const command = (label, phase = "end") => records.findLast((record) => record.kind === "command" && record.label === label && record.phase === phase);
const output = (record) => `${record?.dashpot?.stdout ?? ""}${record?.dashpot?.stderr ?? ""}`;
// The tool's answer to a move it accepted: its output, `{sessionID, directory}`.
const moved = (result) => { try { const answer = JSON.parse(result); return /^ses_\w+$/.test(answer.sessionID) && Boolean(answer.directory); } catch { return false; } };
// The skill's confirmation: the shell ran in the destination, and the status
// confirms this session's identity there.
const confirmedAt = (record, directory) => {
  const line = output(record).split("\n").find((item) => item.startsWith("Agent Session identity claimed here:")) ?? "";
  const id = record?.env?.OPENCODE_SESSION_ID;
  return record?.cwd === directory && Boolean(id) && line.includes(`OpenCode session ${id} `) && /, confirmed by its \w+ hook record$/.test(line);
};
const holding = (record, issue) => output(record).split("\n").some((line) => line.includes(`: ${issue} (`));

// Dispatch: steps 1 to 4 of the OpenCode move. A move that took effect but
// is not confirmed moves back to `origin` with steps 2 and 3 before the
// handoff.
const dispatch = (prefix, target, issue, origin = fixture) => (last) => {
  if (!last) return work(`${prefix}-show`, "show");
  if (last.kind === "move" && last.target === target) return moved(last.result) ? where(`${prefix}-check`) : end(`${prefix}: handoff, the move failed`);
  if (last.kind === "move") return moved(last.result) ? where(`${prefix}-back`) : end(`${prefix}: tell the user, the session is in the Worktree unrecorded`);
  switch (last.label) {
    case `${prefix}-show`: return /listed as working/.test(output(last.record)) ? end(`${prefix}: waiting for this session's workers`) : moveSession(target);
    case `${prefix}-check`: return confirmedAt(last.record, target) ? work(`${prefix}-arrived`, "show")
      : last.record?.cwd === target ? moveSession(origin) : end(`${prefix}: handoff, the move is not confirmed`);
    case `${prefix}-back`: return confirmedAt(last.record, origin) ? end(`${prefix}: handoff, moved back`)
      : end(`${prefix}: tell the user, the session is in the Worktree unrecorded`);
    case `${prefix}-arrived`: return holding(last.record, issue) ? end(`${prefix}: retained the Agent Run`) : work(`${prefix}-start`, "start", issue);
    case `${prefix}-start`: return work(`${prefix}-verify`, "show");
    case `${prefix}-verify`: return holding(last.record, issue) ? end(`${prefix}: bound`) : end(`${prefix}: not bound`);
    default: return end(`${prefix}: done`);
  }
};
// Finish: `work stop`, `work show`, then the move to the main Worktree with
// steps 2 and 3, and no `work start`.
const finish = (prefix) => (last) => {
  if (!last) return work(`${prefix}-stop`, "stop");
  if (last.kind === "move") return moved(last.result) ? where(`${prefix}-check`) : end(`${prefix}: tell the user, the move failed`);
  switch (last.label) {
    case `${prefix}-stop`: return work(`${prefix}-show`, "show");
    case `${prefix}-show`: return /no active Issue work/.test(output(last.record)) && !/listed as working/.test(output(last.record))
      ? moveSession(fixture) : end(`${prefix}: not finished`);
    case `${prefix}-check`: return confirmedAt(last.record, fixture) ? end(`${prefix}: finished`) : end(`${prefix}: tell the user, the move is not confirmed`);
    default: return end(`${prefix}: done`);
  }
};
// Switch: finish the current Issue, then dispatch to the next, in one turn.
const switching = (prefix, target, issue) => {
  const out = finish(`${prefix}-finish`);
  const into = dispatch(`${prefix}-into`, target, issue);
  return (last) => {
    if (!last) return out(null);
    if (last.kind === "move") return last.target === fixture ? out(last) : into(last);
    if (!last.label.startsWith(`${prefix}-finish-`)) return into(last);
    const next = out(last);
    return next.end?.endsWith(": finished") ? into(null) : next;
  };
};
const flows = {
  "bound-bind": () => (last) => last ? (last.label === "bound-bind" ? work("bound-bind-show", "show") : end("bound-bind: bound")) : work("bound-bind", "start", "issue-1"),
  "bound-dispatch": () => dispatch("bound", treeA, "issue-1"),
  "bound-again": () => (last) => last ? end("bound-again: done") : work("bound-again", "show"),
  "unbound-dispatch": () => dispatch("unbound", treeB, "issue-2"),
  "switch": () => switching("switch", treeC, "issue-3"),
  "finish": () => finish("finish"),
  "missing-bind": () => (last) => last ? end("missing-bind: bound") : work("missing-bind", "start", "issue-4"),
  "missing-dispatch": () => dispatch("missing", missing, "issue-4"),
  "file-dispatch": () => dispatch("file", plainFile, "issue-4"),
  "unwritable-dispatch": () => dispatch("unwritable", treeE, "issue-5"),
  "denied-dispatch": () => dispatch("denied", treeD, "issue-6"),
  "asked-dispatch": () => dispatch("asked", treeD, "issue-7"),
  "default-dispatch": () => dispatch("default", treeD, "issue-8"),
  "workers-bind": () => (last) => last ? end("workers-bind: bound") : work("workers-bind", "start", "issue-9"),
  "workers-dispatch": () => dispatch("workers", treeD, "issue-9"),
};
const sequences = {
  // A move made beside another tool call in its step, which the skill rules
  // out, then the step after it.
  "same-step": () => [[moveSession(treeB), report("same-step-beside")], report("same-step-next"), where("same-step-check")],
  "workers-launch": () => [subagent("worker")],
  "worker": () => [report("worker-hold", 8000)],
};

const text = (message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
const probes = (message) => [...text(message).matchAll(/PROBE:([a-z0-9-]+)/g)].map((match) => match[1]);
// The previous step's outcome: null when the turn holds no step yet, or when
// its last step ended with a text, as a turn woken by a notice does.
const previous = (messages, anchor) => {
  const index = messages.findLastIndex((message) => message.role === "assistant");
  if (index <= anchor) return null;
  const [call] = messages[index].tool_calls ?? [];
  if (!call) return null;
  let args = {};
  try { args = JSON.parse(call.function?.arguments || "{}"); } catch {}
  const result = messages.slice(index + 1).filter((message) => message.role === "tool").map(text)[0] ?? "";
  if (call.function?.name === "execute" && /session_move/.test(args.code ?? "")) {
    const directory = args.code.match(/"directory":("(?:[^"\\]|\\.)*")/)?.[1];
    return { kind: "move", target: directory ? JSON.parse(directory) : null, result };
  }
  const label = String(args.command ?? "").match(/command\.mjs (\S+)/)?.[1] ?? null;
  return { kind: call.function?.name ?? null, label, record: label ? command(label) : null, result };
};
const modelRequests = new Map();
const model = await listen(async (req, res) => {
  const payload = await body(req);
  const messages = payload.messages ?? [];
  const system = JSON.stringify(messages.filter((message) => message.role === "system"));
  const anchor = messages.findLastIndex((message) => message.role === "user" && probes(message).length);
  const label = anchor >= 0 ? probes(messages[anchor]).at(-1) : null;
  const tools = (payload.tools ?? []).map((tool) => tool.function?.name);
  const titled = /title generator/i.test(system) || !tools.length;
  const step = messages.slice(anchor + 1).filter((message) => message.role === "assistant").length;
  const count = titled ? 0 : (modelRequests.get(label) ?? 0) + 1;
  if (!titled) modelRequests.set(label, count);
  const last = titled ? null : previous(messages, anchor);
  let calls = [];
  let decision = null;
  if (!titled && label && flows[label]) {
    const next = flows[label]()(last);
    if (next.end) decision = next.end; else calls = [next];
  } else if (!titled && label) {
    const sequence = sequences[label]?.() ?? [report(label)];
    const planned = sequence[step];
    calls = planned === undefined ? [] : Array.isArray(planned) ? planned : [planned];
  }
  trace("model.request", { label, step, tools: calls.map((call) => call.name), count, titled,
    sessionID: req.headers["x-opencode-session-id"] ?? null, parentID: req.headers["x-opencode-parent-session-id"] ?? null,
    messages: messages.length, probes: titled ? undefined : messages.filter((message) => message.role === "user").flatMap(probes),
    previous: last ? { kind: last.kind, label: last.label ?? undefined, target: last.target ?? undefined, result: retained(last.result).slice(0, 400) } : undefined,
    decision: decision ?? undefined });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (calls.length) {
    chunk({ role: "assistant", tool_calls: calls.map((call, index) => ({ index, id: `call_${label}_${step}_${count}_${index}`, type: "function",
      function: { name: call.name, arguments: JSON.stringify(call.arguments) } })) });
  } else chunk({ role: "assistant", content: titled ? "Fixture title" : decision ?? `Fixture complete: ${label}.` });
  chunk({}, calls.length ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed
// unless a scenario says otherwise, and the background service on a private
// port with a known password.
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
// is recorded, and each Agent Run's identity, start and Issue Binding.
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

// --- The background service --------------------------------------------------

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
// OpenCode's server event stream: session and permission events, as a client
// sees them.
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
          if (!/^(session\.(created|deleted|moved|execution\.)|permission\.)/.test(event.type ?? "")) continue;
          const data = event.data ?? {};
          trace("server.event", { name, type: event.type, location: event.location?.directory ?? null, sessionID: data.sessionID ?? null,
            parentID: data.parentID ?? null, reason: data.reason ?? null, to: event.type === "session.moved" ? data.location?.directory ?? null : undefined,
            action: data.action ?? undefined, reply: data.reply ?? undefined, requestID: data.id ?? data.requestID ?? undefined });
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
  trace("service", { label, pid: found.pid, version: found.version ?? null });
  return found;
};
const cli = (args) => {
  const result = spawnSync("opencode", args, { cwd: fixture, env: { ...env, PWD: fixture }, encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const restartService = async (label, config) => {
  writeFileSync(path.join(configHome, "opencode.json"), config);
  const stopping = service.pid;
  trace("service.stop", { label, ...cli(["service", "stop"]) });
  await waitFor(() => !alive(stopping), `${label}: service stopped`, 15000);
  trace("service.start", { label, ...cli(["service", "start"]) });
  await awaitService(label);
};
const session = async (title, directory, extra = {}) => {
  const made = await api("POST", "/api/session", { title, location: { directory }, model: { id: "fixture", providerID: "loop" }, ...extra });
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
// A turn during which the runner answers every permission OpenCode asks the
// person for: the move with `moveReply`, anything else once.
const answering = async (id, label, moveReply) => {
  const asked = [];
  let done = false;
  const turn = prompt(id, label).finally(() => { done = true; });
  while (!done) {
    const pending = (await request("GET", `/api/session/${id}/permission`)).body;
    for (const item of Array.isArray(pending) ? pending : []) {
      if (asked.some((entry) => entry.id === item.id)) continue;
      const reply = /session_move/.test(item.action ?? "") ? moveReply : "once";
      const answer = await request("POST", `/api/session/${id}/permission/${item.id}/reply`, { decision: reply });
      asked.push({ id: item.id, action: item.action ?? null, resources: item.resources ?? null, reply, status: answer.status });
    }
    await delay(100);
  }
  await turn;
  return trace("permissions", { label, asked: asked.map(({ action, resources, reply, status }) => ({ action, resources: retained(JSON.stringify(resources)), reply, status })) });
};
const decisions = (label) => records.filter((record) => record.kind === "model.request" && record.label === label && record.decision).map((record) => record.decision);

const pluginFile = path.join(configHome, "plugins", "dashpot.js");
const skillsHome = path.join(configHome, "skills");
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), servicePort, fixture, trees: { a: treeA, b: treeB, c: treeC, d: treeD, e: treeE }, missing, plainFile, wheel,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(checkout, "src", "dashpot", file)))
      && sha256Tree(path.join(installed, bundledSkill)) === sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill)),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "verify.mjs", "command.mjs", "ancestry.mjs"].map((file) => [file, sha256(path.join(here, file))]),
      ...exercised.map((file) => [`src/dashpot/${file}`, sha256(path.join(checkout, "src", "dashpot", file))]),
      [`src/dashpot/${bundledSkill}/`, sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill))],
    ]) });

  // The integration, as a person installs it.
  trace("scenario", { name: "installer" });
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig());
  integrate("install", ["opencode"]);
  assert(readFileSync(pluginFile, "utf8").includes(JSON.stringify(helper)), "the plugin names the installed helper");
  trace("files", { label: "installed", plugin: sha256(pluginFile), skill: sha256Tree(path.join(skillsHome, "dashpot-issue-work")),
    skillMatchesSource: sha256Tree(path.join(skillsHome, "dashpot-issue-work")) === sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill)),
    workerAgent: existsSync(path.join(configHome, "agent", "dashpot-worker.md")) });
  trace("service.start", { label: "start", ...cli(["service", "start"]) });
  await awaitService("start");

  // A bound root session dispatches itself into Worktree `a`: its Agent Run
  // moves with it, and `work start` is never run there.
  trace("scenario", { name: "bound" });
  known.bound = await session("Bound", fixture);
  await prompt(known.bound, "bound-bind");
  stateFiles("bound-before");
  await prompt(known.bound, "bound-dispatch");
  await settle();
  await sessionInfo("bound-after", known.bound);
  stateFiles("bound-after");
  observe("bound-after");
  check("tree-a-bound-after", treeA);
  // The next turn: the conversation went on in the same session.
  await prompt(known.bound, "bound-again");

  // An unbound root session dispatches itself into Worktree `b`: nothing
  // moves with it, so it runs `work start` there.
  trace("scenario", { name: "unbound" });
  known.unbound = await session("Unbound", fixture);
  await prompt(known.unbound, "unbound-dispatch");
  await settle();
  await sessionInfo("unbound-after", known.unbound);
  stateFiles("unbound-after");
  observe("unbound-after");

  // The bound session finishes: `work stop`, then the move to the main
  // Worktree, which frees `a` for Cleanup.
  trace("scenario", { name: "finish" });
  check("tree-a-before-finish", treeA);
  await prompt(known.bound, "finish");
  await settle();
  await sessionInfo("finish-after", known.bound);
  stateFiles("finish-after");
  observe("finish-after");
  check("tree-a-after-finish", treeA);

  // The unbound session, now bound in `b`, switches to Issue 3 in `c`:
  // finish, then dispatch, in one turn; the run on Issue 2 ends rather than
  // moving.
  trace("scenario", { name: "switch" });
  await prompt(known.unbound, "switch");
  await settle();
  await sessionInfo("switch-after", known.unbound);
  stateFiles("switch-after");
  observe("switch-after");
  check("tree-b-after-switch", treeB);

  // A move made beside another tool call in its step: the other call runs
  // where the session was; the move takes effect when the step ends.
  trace("scenario", { name: "same-step" });
  known.same = await session("SameStep", fixture);
  await prompt(known.same, "same-step");
  await settle();
  await sessionInfo("same-step-after", known.same);

  // Destinations the move refuses: a missing path and a file. The bound run
  // stays where it was.
  trace("scenario", { name: "refused-destination" });
  known.refused = await session("Refused", fixture);
  await prompt(known.refused, "missing-bind");
  await prompt(known.refused, "missing-dispatch");
  await sessionInfo("missing-after", known.refused);
  await prompt(known.refused, "file-dispatch");
  await sessionInfo("file-after", known.refused);
  stateFiles("refused-after");
  observe("refused-after");

  // A move OpenCode makes but Dashpot cannot record: Worktree `e`'s state
  // directory is unwritable, so the next step's check finds no evidence.
  trace("scenario", { name: "unwritable" });
  mkdirSync(path.join(treeE, ".dashpot", "state"), { recursive: true });
  chmodSync(path.join(treeE, ".dashpot", "state"), 0o555);
  known.unwritable = await session("Unwritable", fixture);
  await prompt(known.unwritable, "unwritable-dispatch");
  await settle();
  await sessionInfo("unwritable-after", known.unwritable);
  chmodSync(path.join(treeE, ".dashpot", "state"), 0o755);
  stateFiles("unwritable-after");

  // A session whose permissions deny the move: the tool is unknown.
  trace("scenario", { name: "denied" });
  known.denied = await session("Denied", fixture, { permissions: [{ action: "*session_move", resource: "*", effect: "deny" }] });
  await prompt(known.denied, "denied-dispatch");
  await sessionInfo("denied-after", known.denied);

  // A session whose permissions ask for the move: whether OpenCode asks the
  // person, who would reject it.
  trace("scenario", { name: "asked" });
  known.asked = await session("Asked", fixture, { permissions: [{ action: "*session_move", resource: "*", effect: "ask" }] });
  await answering(known.asked, "asked-dispatch", "reject");
  await sessionInfo("asked-after", known.asked);

  // A bound lead with a running worker waits, and moves once the worker has
  // ended and its notice wakes the lead.
  trace("scenario", { name: "workers" });
  known.workers = await session("Workers", fixture);
  await prompt(known.workers, "workers-bind");
  await prompt(known.workers, "workers-launch");
  await waitFor(() => command("worker-hold", "start"), "worker holding", 30000);
  await prompt(known.workers, "workers-dispatch");
  await sessionInfo("workers-while-running", known.workers);
  stateFiles("workers-while-running");
  await waitFor(() => command("worker-hold"), "worker ended", 30000);
  await waitFor(() => decisions("workers-dispatch").length >= 2, "lead woken and moved", 60000);
  await idle(known.workers, "workers-woken");
  await settle();
  await sessionInfo("workers-after", known.workers);
  stateFiles("workers-after");
  observe("workers-after");
  check("tree-d-workers-after", treeD);

  // A person's default configuration, with no permission rules: whether the
  // move asks the person, who would reject it.
  trace("scenario", { name: "default-permissions" });
  await restartService("default-permissions", opencodeConfig({ permissions: null }));
  known.defaulted = await session("Default", fixture);
  await answering(known.defaulted, "default-dispatch", "reject");
  await sessionInfo("default-after", known.defaulted);

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
  try { chmodSync(path.join(treeE, ".dashpot", "state"), 0o755); } catch {}
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
