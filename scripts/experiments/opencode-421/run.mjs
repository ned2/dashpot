// Measurement run for Issue #421: the worker mechanics a lead session running
// the execute-issues skill relies on under OpenCode 2.0.22. A lead session
// launches background workers with OpenCode's own `subagent` tool, and the
// run records how the lead keeps control, how a worker reports mid-flight,
// how the lead learns a worker finished and resumes it, what Dashpot makes
// of the workers, where they run and whether they can move the lead, where a
// deny of that move can live and what it leaves reachable, what Dashpot keeps
// when the lead moves while a worker runs, what interruption and deletion do
// to the workers, and which skills OpenCode loads.
//
// Copied from the OpenCode acceptance run (opencode-163) and cut down to the
// pinned release. It drives OpenCode 2.0.22 against a loopback
// OpenAI-compatible model fixture, in disposable configuration and state,
// with the background service on a private port, so the operator's own
// OpenCode service is never contacted. Dashpot is built from this checkout
// and installed into a fixture environment, and `dashpot integrate opencode`
// from that installation writes the plugin and skill the run exercises. The
// fixture model emits the tool calls a lead and its workers would make; the
// shells they run report their identity and run `dashpot work` commands.
// The trace is metadata only; the runner asserts only what it needs to keep
// going, and the independent verifier checks the trace against the spike.
//
// Usage: TMPDIR=<private dir> setsid -f node run.mjs <absolute opencode 2.0.22 binary> > log 2>&1
// It is done when it prints "All scenarios completed". SPIKE_REMOVE_FIXTURE=1
// deletes the fixture afterwards.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, writeFileSync } from "node:fs";
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

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-opencode-421-"));
console.log(`Isolated fixture: ${root}`);
// The Repository's main Worktree and three linked Worktrees.
const fixture = path.join(root, "repository");
const treeA = path.join(root, "repository.worktrees", "a");
const treeB = path.join(root, "repository.worktrees", "b");
const treeC = path.join(root, "repository.worktrees", "c");
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
  "sessions/integrate.py", "sessions/agent_bindings.py", "repository/cleanup/obstacles.py", "hook.py"];
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
const git = project(fixture, "fixture", 20);
for (const [name, tree] of [["a", treeA], ["b", treeB], ["c", treeC]]) git("worktree", "add", "-b", name, tree);
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
const sink = await listen(async (req, res) => {
  const reported = await body(req);
  // A worker's `opencode run` prints its lead's reply; keep its head only.
  if (reported.exec) reported.exec = { ...reported.exec, stdout: retained(reported.exec.stdout ?? "").slice(-600), stderr: retained(reported.exec.stderr ?? "").slice(-600) };
  trace("command", reported);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model. The latest user turn holding a `PROBE:<label>` text
// selects a sequence of steps, built when the model is asked so it can name
// sessions the runner learns later; a step is one tool call or several made
// at once, and the turn ends with a text naming the label once every step has
// run. A label with no sequence runs one shell command of that name. A
// notification OpenCode adds to a session, which holds no label, neither
// restarts nor ends the sequence it arrives in.
const commandScript = path.join(here, "command.mjs");
const known = {};
const shell = (command) => ({ name: "shell", arguments: { command } });
const report = (label, hold = 0) => shell(`node ${commandScript} ${label} ${hold}`);
const work = (label, ...args) => shell(`node ${commandScript} ${label} 0 -- work ${args.join(" ")}`);
const exec = (label, ...args) => shell(`node ${commandScript} ${label} 0 -- exec ${args.join(" ")}`);
const bind = (prefix, issue) => [work(`${prefix}-start`, "start", issue), work(`${prefix}-show`, "show")];
const subagent = (child, { background = true, agent = "general", sessionID } = {}) => ({ name: "subagent", arguments: {
  agent, description: `Worker ${child}`, prompt: `PROBE:${child}`, ...(background ? { background: true } : {}), ...(sessionID ? { sessionID } : {}) } });
const execute = (code) => ({ name: "execute", arguments: { code } });
const moveSession = (directory, sessionID) => execute(`return await tools.opencode.session_move(${JSON.stringify({ ...(sessionID ? { sessionID } : {}), directory })})`);
const apiScript = path.join(here, "api.mjs");
const callApi = (label, method, route, data) => shell(`node ${apiScript} ${label} ${method} ${route} '${JSON.stringify(data)}'`);
const skill = (id) => ({ name: "skill", arguments: { id } });
// The child a background launch names, from the lead's latest tool result.
const launched = (context) => context.lastTool?.match(/sessionID: (ses_\w+)/)?.[1];
const sequences = {
  "lead-bind": () => bind("lead", "issue-1"),
  // Three workers launched at once; the lead keeps control and works on.
  "lead-launch": () => [[subagent("w1"), subagent("w2"), subagent("w3")], report("lead-after-launch", 9000), work("lead-after-launch-show", "show")],
  "w1": () => [report("w1-start"), shell(`cd ${treeA} && node ${commandScript} w1-cd 0 -- work start issue-2`), work("w1-show", "show"), report("w1-hold", 5000)],
  "w2": () => [report("w2-hold", 5000)],
  "w3": () => [report("w3-hold", 5000)],
  "idle-bind": () => bind("idle", "issue-3"),
  "idle-launch": () => [subagent("w4")],
  "w4": () => [report("w4-hold", 5000)],
  "rep-bind": () => bind("rep", "issue-4"),
  "rep-launch": () => [subagent("w5")],
  "w5": () => [report("w5-start"), exec("w5-report-idle", "opencode", "run", "--session", known.rep, "PROBE:report-idle"), report("w5-hold", 2000)],
  "rep-busy-launch": () => [subagent("w6"), report("rep-busy-hold", 10000)],
  "w6": () => [report("w6-start", 1000), exec("w6-report-busy", "opencode", "run", "--session", known.rep, "PROBE:report-busy"), report("w6-end")],
  "rep-busy-launch-background": () => [subagent("w16"), report("rep-busy-hold-background", 10000)],
  "w16": () => [report("w16-start", 1000), { name: "shell", arguments: { command: `node ${commandScript} w16-report-background 0 -- exec opencode run --session ${known.rep} PROBE:report-background`,
    background: true } }, report("w16-after")],
  // The worker's report from another directory, and one its shell's timeout
  // cuts short while the lead is busy.
  "rep-cd-launch": () => [subagent("w18")],
  "w18": () => [shell(`cd ${treeB} && node ${commandScript} w18-report-cd 0 -- exec opencode run --session ${known.rep} PROBE:report-cd`), report("w18-after")],
  "rep-timeout-launch": () => [subagent("w19"), report("rep-timeout-hold", 12000)],
  "w19": () => [report("w19-start", 1000), { name: "shell", arguments: { command: `node ${commandScript} w19-report-timeout 0 -- exec opencode run --session ${known.rep} PROBE:report-timeout`,
    timeout: 3000 } }, report("w19-after")],
  "rep-api-launch": () => [subagent("w25"), report("rep-api-hold", 8000)],
  "w25": () => [report("w25-start", 1000), callApi("w25-report-api", "POST", `/api/session/${known.rep}/prompt`, { text: "PROBE:report-api" }), report("w25-after")],
  "rep-resume": () => [subagent("w5-resumed", { sessionID: known.w5 })],
  "w5-resumed": () => [report("w5-resumed")],
  "rep-steer": (context) => [subagent("w7"), subagent("w7-steered", { sessionID: launched(context) })],
  "w7": () => [report("w7-hold", 6000), report("w7-unsteered")],
  "w7-steered": () => [report("w7-steered")],
  "loc-bind": () => bind("loc", "issue-5"),
  "loc-launch": () => [subagent("w8")],
  "w8": () => [report("w8-start"), shell(`cd ${treeB} && node ${commandScript} w8-cd 0 -- work show`),
    { name: "shell", arguments: { command: `node ${commandScript} w8-workdir 0`, workdir: treeC } }, moveSession(treeA), report("w8-after-self-move"),
    work("w8-after-self-move-show", "show")],
  "loc-launch-parent": () => [subagent("w9")],
  "w9": () => [moveSession(treeC, known.loc), report("w9-after-parent-move")],
  "loc-after-move": () => [work("loc-after-move-show", "show")],
  "loc-back": () => [work("loc-back-show", "show")],
  "loc-launch-guarded": () => [subagent("w10", { agent: "dashpot-worker" })],
  "w10": () => [moveSession(treeC, known.loc), report("w10-after-guarded-move")],
  // The lead moved by the runner while its worker runs.
  "mv-bind": () => bind("mv", "issue-11"),
  "mv-launch": () => [subagent("w17")],
  "w17": () => [report("w17-hold", 6000), report("w17-after")],
  "mv-show": () => [work("mv-later-show", "show")],
  "mv-back": () => [work("mv-back-show", "show")],
  // Where a deny of the move binds a worker: a global agent file, a project
  // agent file, the lead session's own permissions, the lead's agent, and
  // the routes around it.
  "guard-bind": () => bind("guard", "issue-12"),
  "guard-md": () => [subagent("w20", { agent: "dashpot-worker-md" })],
  "w20": () => [moveSession(treeC, known.guard), report("w20-after")],
  "guard-project": () => [subagent("w21", { agent: "dashpot-worker-project" })],
  "w21": () => [moveSession(treeC, known.guardProject), report("w21-after")],
  "guard-session": () => [subagent("w22")],
  "w22": () => [moveSession(treeC, known.guardSession), report("w22-after")],
  "guard-agent": () => [subagent("w23")],
  "w23": () => [moveSession(treeC, known.guardAgent), report("w23-after")],
  "guard-bypass": () => [subagent("w24", { agent: "dashpot-worker" })],
  "w24": () => [moveSession(treeC, known.guard), callApi("w24-bypass-api", "POST", `/api/session/${known.guard}/move`, { directory: treeC }), report("w24-after")],
  "dep-bind": () => bind("dep", "issue-6"),
  "dep-launch": () => [subagent("w11")],
  "w11": () => [subagent("reviewer", { background: false }), report("w11-after-reviewer")],
  "dep-launch-deeper": () => [subagent("w12")],
  "w12": () => [subagent("reviewer-deeper", { background: false }), report("w12-after-reviewer")],
  "reviewer-deeper": () => [report("reviewer-deeper"), work("reviewer-deeper-start", "start", "issue-7")],
  "int-bind": () => bind("int", "issue-8"),
  "int-launch": () => [subagent("w13"), report("int-busy", 15000)],
  "w13": () => [report("w13-hold", 6000)],
  "tui-lead": () => [...bind("tui", "issue-9"), subagent("w14")],
  "w14": () => [report("w14-hold", 8000)],
  "del-bind": () => bind("del", "issue-10"),
  "del-launch": () => [subagent("w15")],
  "w15": () => [report("w15-hold", 8000), report("w15-after")],
  "skills-probe": () => [skill("dashpot-issue-work"), skill("fixture-user-only"), skill("fixture-claude-flag")],
};
const text = (message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content ?? "");
const probes = (message) => [...text(message).matchAll(/PROBE:([a-z0-9-]+)/g)].map((match) => match[1]);
const NOTICE = /<subagent sessionID=\\?"(ses_\w+)\\?" state=\\?"(\w+)\\?"(?: description=\\?"[^"\\]*\\?")?>(?:\\n|\n)([^<]{0,120})/g;
const modelRequests = new Map();
let firstTools = null;
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
  const last = messages.at(-1);
  const context = { lastTool: last?.role === "tool" ? text(last) : null };
  const sequence = (label && (sequences[label]?.(context) ?? [report(label)])) || [];
  const planned = titled ? undefined : sequence[step];
  const calls = planned === undefined ? [] : Array.isArray(planned) ? planned : [planned];
  // OpenCode's notice that a background child ended, wherever it sits; fresh
  // when it arrived after this session's previous step.
  const notices = titled ? [] : messages.flatMap((message, index) => message.role === "tool" ? [] :
    [...text(message).matchAll(NOTICE)].map(([, sessionID, state, head]) => ({ sessionID, state, role: message.role, fresh: index > lastAssistant,
      head: head.replaceAll("\\n", " ").trim().slice(0, 60) })));
  const available = system.match(/<available_skills>([\s\S]*?)<\/available_skills>/)?.[1] ?? "";
  const skillContent = [...JSON.stringify(messages).matchAll(/fixture-skill-marker: ([a-z-]+)|dashpot-managed-skill: ([a-z-]+)/g)].map((match) => match[1] ?? match[2]);
  if (!titled && !firstTools) {
    firstTools = (payload.tools ?? []).map((tool) => ({ name: tool.function?.name, parameters: Object.keys(tool.function?.parameters?.properties ?? {}) }));
    trace("tools", { tools: firstTools });
  }
  trace("model.request", { label, step, tools: calls.map((call) => call.name), count, titled,
    sessionID: req.headers["x-opencode-session-id"] ?? null, parentID: req.headers["x-opencode-parent-session-id"] ?? null,
    messages: messages.length, probes: titled ? undefined : messages.filter((message) => message.role === "user").flatMap(probes),
    notices: notices.length ? notices : undefined,
    lastTool: titled || !context.lastTool ? undefined : retained(context.lastTool).slice(0, 400),
    skills: label?.startsWith("skills") ? [...available.matchAll(/<id>([^<]+)<\/id>/g)].map((match) => match[1]) : undefined,
    skillContent: label?.startsWith("skills") ? skillContent : undefined });
  res.writeHead(200, { "content-type": "text/event-stream" });
  const chunk = (delta, finish = null) => res.write("data: " + JSON.stringify({ id: "fixture", object: "chat.completion.chunk", created: 1, model: "fixture", choices: [{ index: 0, delta, finish_reason: finish }] }) + "\n\n");
  if (calls.length) {
    chunk({ role: "assistant", tool_calls: calls.map((call, index) => ({ index, id: `call_${label}_${step}_${count}_${index}`, type: "function",
      function: { name: call.name, arguments: JSON.stringify(call.arguments) } })) });
  } else chunk({ role: "assistant", content: titled ? "Fixture title" : `Fixture complete: ${label}.` });
  chunk({}, calls.length ? "tool_calls" : "stop");
  res.end("data: [DONE]\n\n");
});

// The native configuration: the fixture model only, every tool allowed, the
// background service on a private port with a known password, and a worker
// agent and a lead agent whose permissions deny OpenCode's session move.
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
const denyMove = [{ action: "*session_move", resource: "*", effect: "deny" }];
const opencodeConfig = (extra = {}) => JSON.stringify({
  model: "loop/fixture", update: "disable", share: "disabled", snapshots: false, lsp: false, formatter: false,
  providers: { loop: { name: "Loop", package: "aisdk:@ai-sdk/openai-compatible",
    settings: { baseURL: model.url + "/v1", apiKey: "fixture-unused" },
    models: { fixture: { name: "Fixture", capabilities: { tools: true, input: ["text"], output: ["text"] }, limit: { context: 128000, output: 4096 } } } } },
  permissions: [{ action: "*", resource: "*", effect: "allow" }],
  agents: { "dashpot-worker": { mode: "subagent", description: "A worker that cannot move sessions.", permissions: denyMove },
    "dashpot-lead": { mode: "primary", description: "A lead that cannot move sessions.", permissions: denyMove } },
  ...extra,
}, null, 2);

// --- Observation -------------------------------------------------------------

const run = (command, args, { cwd = fixture, extra = {} } = {}) => {
  const result = spawnSync(command, args, { cwd, env: { ...env, ...extra }, encoding: "utf8", timeout: 60000 });
  return { status: result.status, stdout: retained(result.stdout ?? ""), stderr: retained(result.stderr ?? "").slice(-1500) };
};
const integrate = (label, args, options = {}) => trace("integrate", { label, args, ...run(dashpot, ["integrate", ...args], options) });
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label, cwd = fixture) => {
  const result = run(dashpot, ["--json"], { cwd });
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
  let report = null;
  try { report = JSON.parse(result.stdout); } catch {}
  return trace("cleanup", { label, worktree, status: result.status,
    obstacles: report ? (report.obstacles ?? []).map(({ kind, detail }) => ({ kind, detail: String(detail ?? "").slice(0, 400) })) : null,
    error: report ? undefined : (result.stdout + result.stderr).slice(0, 1500) });
};
const storeOf = (worktree) => path.join(worktree, ".dashpot", "state", "sessions");
const readJson = (file) => { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return null; } };
// The hook record of each session the Agent Session list names, by
// Worktree: its location, state and live children.
const stateFiles = (label) => {
  const sessions = {};
  for (const worktree of worktrees) {
    let names = [];
    try { names = readdirSync(storeOf(worktree)).filter((name) => name.endsWith(".json")); } catch { continue; }
    for (const name of names) {
      const record = readJson(path.join(storeOf(worktree), name));
      if (!record) continue;
      sessions[`${worktree}/${name}`] = { state: record.state ?? null, event: record.event ?? null, cwd: record.cwd ?? null,
        subagents: record.subagents ?? record.liveSubagents ?? null, keys: Object.keys(record) };
    }
  }
  return trace("state", { label, sessions });
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
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(50); }
  throw new Error(`Timed out: ${label}`);
};
const settle = (ms = 1500) => delay(ms);
// A model request in one session carrying a fresh notice that a child ended.
const noticed = (sessionID, child) => records.some((record) => record.kind === "model.request" && record.sessionID === sessionID
  && record.notices?.some((notice) => notice.fresh && (!child || notice.sessionID === child)));
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
// The TCP ports a process listens on, from its socket descriptors.
const listening = (pid) => {
  const inodes = new Set();
  try {
    for (const fd of readdirSync(`/proc/${pid}/fd`)) {
      try { const inode = readlinkSync(`/proc/${pid}/fd/${fd}`).match(/^socket:\[(\d+)\]$/)?.[1]; if (inode) inodes.add(inode); } catch {}
    }
  } catch { return null; }
  const found = [];
  for (const table of ["tcp", "tcp6"]) {
    let lines = [];
    try { lines = readFileSync(`/proc/net/${table}`, "utf8").trim().split("\n").slice(1); } catch { continue; }
    for (const line of lines) {
      const fields = line.trim().split(/\s+/);
      if (fields[3] !== "0A" || !inodes.has(fields[9])) continue;
      const [address, port] = fields[1].split(":");
      found.push({ table, address, port: parseInt(port, 16) });
    }
  }
  return found;
};

// --- The background service and its clients -----------------------------------

const registration = () => readJson(path.join(env.XDG_STATE_HOME, "opencode", "service.json"));
const service = { url: `http://127.0.0.1:${servicePort}`, pid: null, events: null };
const authorization = "Basic " + Buffer.from(`opencode:${password}`).toString("base64");
// One API request: its status and parsed body.
const request = async (method, route, data, { directory } = {}) => {
  const headers = { "content-type": "application/json", authorization };
  if (directory) headers["x-opencode-directory"] = encodeURIComponent(directory);
  const response = await fetch(service.url + route, { method, headers, body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(120000) });
  const raw = await response.text();
  let parsed = null;
  try { parsed = raw ? JSON.parse(raw) : null; } catch { parsed = raw.slice(0, 500); }
  return { status: response.status, body: parsed?.data ?? parsed };
};
// One API request that must succeed: its parsed body.
const api = async (method, route, data, options) => {
  const answer = await request(method, route, data, options);
  assert(answer.status >= 200 && answer.status < 300, `${method} ${route}: ${answer.status} ${JSON.stringify(answer.body).slice(0, 700)}`);
  return answer.body;
};
// OpenCode's server event stream: every location's session events, as a
// client sees them.
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
          if (!/^session\.(created|deleted|moved|execution\.)/.test(event.type ?? "")) continue;
          const data = event.data ?? {};
          trace("server.event", { name, type: event.type, location: event.location?.directory ?? null, sessionID: data.sessionID ?? null,
            parentID: data.parentID ?? null, reason: data.reason ?? null, to: event.type === "session.moved" ? data.location?.directory ?? null : undefined });
        }
      }
    } catch {}
  })();
  return controller;
};
// The running service, once its registration answers.
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
  service.events?.abort();
  service.events = subscribe(label);
  trace("service", { label, pid: info.pid, version: info.version ?? null, listening: listening(info.pid) });
  return info;
};
const session = async (title, directory) => {
  const made = await api("POST", "/api/session", { title, location: { directory }, model: { id: "fixture", providerID: "loop" } });
  trace("session", { title, sessionID: made.id, directory: made.location?.directory ?? null, parentID: made.parentID ?? null });
  return made.id;
};
const send = (id, label, extra = {}) => api("POST", `/api/session/${id}/prompt`, { text: `PROBE:${label}`, ...extra });
const idle = async (id, label) => {
  const waited = await request("POST", `/api/experimental/session/${id}/wait`, {});
  assert(waited.status >= 200 && waited.status < 300, `${label}: wait ${waited.status}`);
};
const prompt = async (id, label, extra) => {
  const started = Date.now();
  await send(id, label, extra);
  await idle(id, label);
  trace("turn", { sessionID: id, label, ms: Date.now() - started });
};
const info = async (id) => {
  const answer = await request("GET", `/api/session/${id}`);
  return answer.status === 200 ? { location: answer.body?.location?.directory ?? null, parentID: answer.body?.parentID ?? null } : { missing: answer.status };
};
const sessionInfo = async (label, id) => trace("session.info", { label, sessionID: id, ...(await info(id)) });
const move = async (id, directory, label) => {
  const answer = await request("POST", `/api/session/${id}/move`, { directory });
  await settle();
  trace("move", { label, sessionID: id, to: directory, status: answer.status, after: await info(id) });
};
const active = async (label) => {
  const answer = (await request("GET", "/api/session/active")).body ?? {};
  return trace("active", { label, sessions: Array.isArray(answer) ? answer.map((item) => item?.id ?? item?.sessionID ?? item) : Object.keys(answer) });
};
const cli = (args, { cwd = fixture, without = [] } = {}) => {
  const result = spawnSync("opencode", args, { cwd, env: Object.fromEntries(Object.entries({ ...env, PWD: cwd }).filter(([key]) => !without.includes(key))),
    encoding: "utf8", timeout: 60000 });
  return { args, status: result.status, stdout: retained(result.stdout ?? "").slice(0, 1500), stderr: retained(result.stderr ?? "").slice(-1500) };
};
// A TUI on a pseudo-terminal, in an environment of the fixture installation.
const stripAnsi = (value) => value.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007\u001b]*(\u0007|\u001b\\)/g, "").replace(/\u001b[()][A-Z0-9]/g, "");
const clients = [];
const tuiClient = (name, args, { cwd = root } = {}) => {
  const quoted = args.map((arg) => /^[\w./:=@-]+$/.test(arg) ? arg : `'${arg.replaceAll("'", "'\\''")}'`);
  const child = spawn("script", ["-qfec", ["opencode", ...quoted].join(" "), "/dev/null"], { cwd,
    env: { ...env, PWD: cwd, SPIKE_CLIENT: name, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.stderr.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); });
  child.on("exit", (code, signal) => { state.exited = { code, signal, at: Date.now() }; trace("client.exit", { name, code, signal }); });
  clients.push(state);
  trace("client.spawn", { name, args, cwd, pid: child.pid });
  return state;
};
const quit = async (state, label) => {
  const started = Date.now();
  for (let attempt = 0; attempt < 4 && !state.exited; attempt++) {
    state.child.stdin.write("\u0003");
    try { await waitFor(() => state.exited, `${state.name} quit`, 3000); } catch {}
  }
  if (!state.exited) {
    state.child.stdin.write("/exit\r");
    try { await waitFor(() => state.exited, `${state.name} /exit`, 5000); } catch {}
  }
  assert(state.exited, `${state.name} did not quit: ${state.output.slice(-800)}`);
  trace("tui.quit", { label, client: state.name, ms: state.exited.at - started });
};
// The sessions OpenCode created as children of one session, by the stream.
const childrenOf = (parentID) => records.filter((record) => record.kind === "server.event" && record.type === "session.created" && record.parentID === parentID)
  .map((record) => record.sessionID);
const claimOf = (label) => command(label, "start")?.env?.OPENCODE_SESSION_ID ?? null;

const pluginFile = path.join(configHome, "plugins", "dashpot.js");
const skillsHome = path.join(configHome, "skills");
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, binarySHA256: sha256(binary), servicePort, fixture, treeA, treeB, treeC, wheel,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("OPENCODE"))), proxy: { HTTPS_PROXY: env.HTTPS_PROXY, NO_PROXY: env.NO_PROXY },
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    installedMatchesSource: exercised.every((file) => sha256(path.join(installed, file)) === sha256(path.join(checkout, "src", "dashpot", file)))
      && sha256Tree(path.join(installed, bundledSkill)) === sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill)),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "verify.mjs", "command.mjs", "api.mjs", "ancestry.mjs"].map((file) => [file, sha256(path.join(here, file))]),
      ...exercised.map((file) => [`src/dashpot/${file}`, sha256(path.join(checkout, "src", "dashpot", file))]),
      [`src/dashpot/${bundledSkill}/`, sha256Tree(path.join(checkout, "src", "dashpot", bundledSkill))],
    ]) });

  // Scenario 1: the integration, as a person installs it.
  trace("scenario", { name: "installer" });
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig());
  integrate("install", ["opencode"]);
  assert(readFileSync(pluginFile, "utf8").includes(JSON.stringify(helper)), "the plugin names the installed helper");
  trace("files", { label: "installed", plugin: sha256(pluginFile), skill: existsSync(path.join(skillsHome, "dashpot-issue-work", "SKILL.md")) });
  trace("service.start", { label: "start", ...cli(["service", "start"]) });
  await awaitService("start");
  integrate("status", ["opencode", "--status"]);

  // Scenario 2 (questions 1, 3 and 5): a bound lead launches three workers
  // in one step, then keeps working while they run; they finish while its
  // own shell still holds.
  trace("scenario", { name: "launch" });
  known.lead = await session("Lead", fixture);
  await prompt(known.lead, "lead-bind");
  const launching = (async () => { const started = Date.now(); await send(known.lead, "lead-launch"); trace("prompt.admitted", { label: "lead-launch", ms: Date.now() - started }); })();
  await waitFor(() => ["w1-hold", "w2-hold", "w3-hold"].every((label) => command(label, "start")), "three workers holding", 60000);
  await settle(1000);
  await active("workers-running");
  stateFiles("workers-running");
  observe("workers-running");
  check("tree-a-workers-running", treeA);
  await launching;
  await idle(known.lead, "lead-launch");
  trace("turn", { sessionID: known.lead, label: "lead-launch" });
  await waitFor(() => ["w1-hold", "w2-hold", "w3-hold"].every((label) => command(label)), "three workers ended", 30000);
  await settle(4000);
  await idle(known.lead, "lead-launch-notices");
  await active("workers-finished");
  observe("workers-finished");
  check("tree-a-workers-finished", treeA);

  // Scenario 3 (question 3): a lead whose turn ended when it launched its
  // worker is woken when the worker finishes.
  trace("scenario", { name: "idle-wake" });
  known.idle = await session("Idle", fixture);
  await prompt(known.idle, "idle-bind");
  await prompt(known.idle, "idle-launch");
  trace("parent.settled", { sessionID: known.idle, childStarted: Boolean(command("w4-hold", "start")), childEnded: Boolean(command("w4-hold")) });
  await waitFor(() => command("w4-hold", "start"), "w4 holding", 30000);
  await settle(1000);
  await active("idle-lead-worker-running");
  observe("idle-lead-worker-running");
  check("tree-a-idle-lead-worker-running", treeA);
  known.w4 = claimOf("w4-hold");
  await waitFor(() => noticed(known.idle, known.w4), "idle lead noticed w4", 30000);
  await settle(2000);
  await idle(known.idle, "idle-woken");
  observe("idle-lead-woken");
  check("tree-a-idle-lead-woken", treeA);

  // Scenario 4 (question 2): a worker sends its lead a message with
  // `opencode run --session`, first while the lead is idle, then while the
  // lead's own shell holds.
  trace("scenario", { name: "report" });
  known.rep = await session("Reporter", fixture);
  await prompt(known.rep, "rep-bind");
  stateFiles("rep-before-report");
  observe("rep-before-report");
  await prompt(known.rep, "rep-launch");
  await waitFor(() => command("w5-hold"), "w5 ended", 90000);
  known.w5 = claimOf("w5-start");
  await waitFor(() => noticed(known.rep, known.w5), "reporter noticed w5", 30000);
  await settle(2000);
  await idle(known.rep, "rep-launch-notice");
  await sessionInfo("rep-after-idle-report", known.rep);
  stateFiles("rep-after-idle-report");
  observe("rep-after-idle-report");
  const busy = (async () => { await send(known.rep, "rep-busy-launch"); })();
  await waitFor(() => command("rep-busy-hold", "start"), "reporter holding", 30000);
  await busy;
  await waitFor(() => command("w6-report-busy", "start"), "w6 reporting", 60000);
  await settle(1500);
  stateFiles("rep-during-busy-report");
  observe("rep-during-busy-report");
  await waitFor(() => command("w6-end"), "w6 ended", 90000);
  known.w6 = claimOf("w6-start");
  await waitFor(() => noticed(known.rep, known.w6), "reporter noticed w6", 30000);
  await settle(2000);
  await idle(known.rep, "rep-busy-notice");
  const busyBackground = (async () => { await send(known.rep, "rep-busy-launch-background"); })();
  await waitFor(() => command("rep-busy-hold-background", "start"), "reporter holding again", 30000);
  await busyBackground;
  await waitFor(() => command("w16-after"), "w16 went on", 60000);
  trace("worker.went-on", { label: "w16-after", reportEnded: Boolean(command("w16-report-background")), leadHeld: Boolean(command("rep-busy-hold-background")) });
  await waitFor(() => command("w16-report-background"), "w16 report ended", 60000);
  known.w16 = claimOf("w16-start");
  await waitFor(() => noticed(known.rep, known.w16), "reporter noticed w16", 60000);
  await settle(2000);
  await idle(known.rep, "rep-busy-background-notice");
  // From a shell in another Worktree.
  await prompt(known.rep, "rep-cd-launch");
  await waitFor(() => command("w18-after"), "w18 went on", 60000);
  known.w18 = claimOf("w18-after");
  await waitFor(() => noticed(known.rep, known.w18), "reporter noticed w18", 60000);
  await settle(2000);
  await idle(known.rep, "rep-cd-notice");
  const cdInfo = await sessionInfo("rep-after-cd-report", known.rep);
  stateFiles("rep-after-cd-report");
  observe("rep-after-cd-report");
  if (cdInfo.location !== fixture) await move(known.rep, fixture, "rep-cd-back");
  // Cut short by the worker's shell timeout while the lead is busy.
  const timing = (async () => { await send(known.rep, "rep-timeout-launch"); })();
  await waitFor(() => command("rep-timeout-hold", "start"), "reporter holding for the timeout", 30000);
  await timing;
  await waitFor(() => command("w19-after"), "w19 went on", 60000);
  trace("worker.timeout", { label: "w19-after", reportEnded: Boolean(command("w19-report-timeout")), reportStarted: Boolean(command("w19-report-timeout", "start")),
    leadHeld: Boolean(command("rep-timeout-hold")) });
  known.w19 = claimOf("w19-start");
  await waitFor(() => noticed(known.rep, known.w19), "reporter noticed w19", 60000);
  await settle(3000);
  await idle(known.rep, "rep-timeout-notice");
  trace("delivered", { label: "report-timeout", seen: records.some((record) => record.kind === "model.request" && record.sessionID === known.rep && record.probes?.includes("report-timeout")) });
  // Through the HTTP API, which admits the message and returns.
  const viaApi = (async () => { await send(known.rep, "rep-api-launch"); })();
  await waitFor(() => command("rep-api-hold", "start"), "reporter holding for the API report", 30000);
  await viaApi;
  await waitFor(() => command("w25-after"), "w25 went on", 60000);
  known.w25 = claimOf("w25-start");
  await waitFor(() => noticed(known.rep, known.w25), "reporter noticed w25", 60000);
  await settle(3000);
  await idle(known.rep, "rep-api-notice");
  trace("delivered", { label: "report-api", seen: records.some((record) => record.kind === "model.request" && record.sessionID === known.rep && record.probes?.includes("report-api")) });

  // Scenario 5 (question 4): the lead resumes a finished worker with its
  // session ID, then steers a running one.
  trace("scenario", { name: "resume" });
  await prompt(known.rep, "rep-resume");
  await waitFor(() => command("w5-resumed"), "w5 resumed", 60000);
  await waitFor(() => records.filter((record) => record.kind === "model.request" && record.sessionID === known.rep
    && record.notices?.some((notice) => notice.fresh && notice.sessionID === known.w5)).length >= 1 && command("w5-resumed"), "resumed notice", 30000);
  await settle(3000);
  await idle(known.rep, "rep-resume-notice");
  await prompt(known.rep, "rep-steer");
  await waitFor(() => command("w7-hold"), "w7 held", 60000);
  known.w7 = claimOf("w7-hold");
  await waitFor(() => noticed(known.rep, known.w7), "reporter noticed w7", 60000);
  await settle(3000);
  await idle(known.rep, "rep-steer-notice");

  // Scenario 6 (question 6): where a worker's shell starts, a per-command
  // `cd`, and the move tool called by a worker on itself, on its lead, and
  // by a worker whose agent denies it.
  trace("scenario", { name: "location" });
  known.loc = await session("Locator", fixture);
  await prompt(known.loc, "loc-bind");
  await prompt(known.loc, "loc-launch");
  await waitFor(() => command("w8-after-self-move-show"), "w8 ended", 60000);
  known.w8 = claimOf("w8-start");
  await waitFor(() => noticed(known.loc, known.w8), "locator noticed w8", 30000);
  await settle(2000);
  await idle(known.loc, "loc-launch-notice");
  await sessionInfo("w8-after-self-move", known.w8);
  await sessionInfo("loc-after-child-self-move", known.loc);
  stateFiles("child-moved-itself");
  observe("child-moved-itself");
  await prompt(known.loc, "loc-launch-parent");
  await waitFor(() => command("w9-after-parent-move"), "w9 ended", 60000);
  known.w9 = claimOf("w9-after-parent-move");
  await waitFor(() => noticed(known.loc, known.w9), "locator noticed w9", 30000);
  await settle(2000);
  await idle(known.loc, "loc-parent-notice");
  await sessionInfo("loc-after-child-moved-it", known.loc);
  stateFiles("child-moved-lead");
  observe("child-moved-lead");
  check("tree-b-child-moved-lead", treeB);
  await prompt(known.loc, "loc-after-move");
  await settle();
  observe("lead-after-move-shell");
  await move(known.loc, fixture, "loc-back");
  await prompt(known.loc, "loc-back");
  await settle();
  stateFiles("lead-moved-back");
  observe("lead-moved-back");
  check("tree-b-lead-moved-back", treeB);
  await prompt(known.loc, "loc-launch-guarded");
  await waitFor(() => command("w10-after-guarded-move"), "w10 ended", 60000);
  known.w10 = claimOf("w10-after-guarded-move");
  await waitFor(() => noticed(known.loc, known.w10), "locator noticed w10", 30000);
  await settle(2000);
  await idle(known.loc, "loc-guarded-notice");
  await sessionInfo("loc-after-guarded-child", known.loc);
  observe("guarded-child-ended");

  // Scenario 6b (questions 5 and 6): the runner moves a bound lead while its
  // worker runs; what Dashpot holds once the worker ends.
  trace("scenario", { name: "move-while-working" });
  known.mv = await session("Mover", fixture);
  await prompt(known.mv, "mv-bind");
  await prompt(known.mv, "mv-launch");
  await waitFor(() => command("w17-hold", "start"), "w17 holding", 30000);
  known.w17 = claimOf("w17-hold");
  await settle(500);
  stateFiles("mv-before-move");
  await move(known.mv, treeB, "mv-lead-moved");
  stateFiles("mv-moved-worker-running");
  observe("mv-moved-worker-running");
  check("tree-b-mv-worker-running", treeB);
  await waitFor(() => command("w17-after"), "w17 ended", 30000);
  await waitFor(() => noticed(known.mv, known.w17), "mover noticed w17", 30000);
  await settle(2000);
  await idle(known.mv, "mv-notice");
  stateFiles("mv-worker-ended");
  observe("mv-worker-ended");
  check("tree-b-mv-worker-ended", treeB);
  check("tree-a-mv-worker-ended", treeA);
  await prompt(known.mv, "mv-show");
  await settle(3000);
  stateFiles("mv-later");
  check("tree-b-mv-later", treeB);
  check("tree-a-mv-later", treeA);
  // Back where it dispatched the worker, so later scenarios start clear.
  await move(known.mv, fixture, "mv-back");
  await prompt(known.mv, "mv-back");
  await settle();
  stateFiles("mv-back");
  check("tree-a-mv-back", treeA);

  // Scenario 6c (question 6): where a deny of the move binds a worker.
  trace("scenario", { name: "guard" });
  const agentFile = (directory, name, mode) => {
    mkdirSync(directory, { recursive: true });
    writeFileSync(path.join(directory, `${name}.md`), `---\ndescription: A worker that cannot move sessions.\nmode: ${mode}\npermissions:\n  - action: "*session_move"\n    resource: "*"\n    effect: deny\n---\n\nYou are a fixture worker.\n`);
  };
  agentFile(path.join(configHome, "agent"), "dashpot-worker-md", "subagent");
  // A location's agents load after its built-in ones: wait for the one named.
  const agentIds = async (expected) => {
    let list = null;
    const has = () => Array.isArray(list) && list.some((item) => (item.id ?? item.name) === expected);
    for (let attempt = 0; attempt < 100 && !has(); attempt++) {
      if (attempt) await delay(100);
      list = (await request("GET", "/api/agent", undefined, { directory: fixture })).body;
    }
    return (Array.isArray(list) ? list : []).map((item) => ({ id: item.id ?? item.name, mode: item.mode ?? null,
      denies: (item.permissions ?? []).filter((rule) => rule.effect === "deny").map((rule) => rule.action) }));
  };
  await settle(3000);
  let agents = await agentIds("dashpot-worker-md");
  if (!agents.some((item) => item.id === "dashpot-worker-md")) {
    trace("reload", { label: "agents", ...cli(["reload"]) });
    await settle(4000);
    agents = await agentIds("dashpot-worker-md");
  }
  trace("agents.listed", { label: "guard", agents });
  const attempt = async (lead, label, child) => {
    await prompt(lead, label);
    await waitFor(() => command(`${child}-after`), `${child} ended`, 60000);
    known[child] = claimOf(`${child}-after`);
    await waitFor(() => noticed(lead, known[child]), `${label} noticed ${child}`, 30000);
    await settle(2000);
    await idle(lead, `${label}-notice`);
    const after = await sessionInfo(`${label}-lead`, lead);
    if (after.location !== fixture) await move(lead, fixture, `${label}-back`);
  };
  known.guard = await session("Guard", fixture);
  await prompt(known.guard, "guard-bind");
  await attempt(known.guard, "guard-md", "w20");
  await attempt(known.guard, "guard-bypass", "w24");
  const made = await api("POST", "/api/session", { title: "GuardSession", location: { directory: fixture }, model: { id: "fixture", providerID: "loop" }, permissions: denyMove });
  known.guardSession = made.id;
  trace("session", { title: "GuardSession", sessionID: made.id, directory: made.location?.directory ?? null, permissions: made.permissions ?? null });
  await attempt(known.guardSession, "guard-session", "w22");
  const lead = await api("POST", "/api/session", { title: "GuardAgent", location: { directory: fixture }, model: { id: "fixture", providerID: "loop" }, agent: "dashpot-lead" });
  known.guardAgent = lead.id;
  trace("session", { title: "GuardAgent", sessionID: lead.id, directory: lead.location?.directory ?? null, agent: lead.agent ?? null });
  await attempt(known.guardAgent, "guard-agent", "w23");

  // Scenario 7 (question 1, and how a worker dispatches its own reviewer): a
  // worker's own sub-agent under the default nesting depth, and under a
  // depth of two.
  trace("scenario", { name: "depth" });
  known.dep = await session("Depth", fixture);
  await prompt(known.dep, "dep-bind");
  await prompt(known.dep, "dep-launch");
  await waitFor(() => command("w11-after-reviewer"), "w11 ended", 60000);
  known.w11 = claimOf("w11-after-reviewer");
  await waitFor(() => noticed(known.dep, known.w11), "depth lead noticed w11", 30000);
  await settle(2000);
  await idle(known.dep, "dep-notice");
  writeFileSync(path.join(configHome, "opencode.json"), opencodeConfig({ experimental: { subagent_depth: 2 } }));
  trace("reload", { label: "depth-two", ...cli(["reload"]) });
  await settle(4000);
  await prompt(known.dep, "dep-launch-deeper");
  await waitFor(() => command("w12-after-reviewer"), "w12 ended", 60000);
  known.w12 = claimOf("w12-after-reviewer");
  await waitFor(() => noticed(known.dep, known.w12), "depth lead noticed w12", 30000);
  await settle(2000);
  await idle(known.dep, "dep-deeper-notice");
  observe("depth-two-ended");

  // Scenario 8 (question 7): the lead's turn interrupted while its own shell
  // holds and a worker runs.
  trace("scenario", { name: "interrupt" });
  known.int = await session("Interrupted", fixture);
  await prompt(known.int, "int-bind");
  await send(known.int, "int-launch");
  await waitFor(() => command("int-busy", "start") && command("w13-hold", "start"), "lead and worker holding", 60000);
  await settle(500);
  trace("interrupt", { label: "lead-turn", sessionID: known.int, ...(await request("POST", `/api/session/${known.int}/interrupt`)) });
  await settle(1500);
  await active("lead-interrupted");
  observe("lead-interrupted-worker-running");
  check("tree-a-lead-interrupted", treeA);
  await waitFor(() => command("w13-hold"), "w13 ended", 30000).catch((error) => trace("missing", { label: "w13-hold", error: String(error) }));
  known.w13 = claimOf("w13-hold");
  await waitFor(() => noticed(known.int, known.w13), "interrupted lead noticed w13", 20000).catch((error) => trace("missing", { label: "int-notice", error: String(error) }));
  await settle(2000);
  await idle(known.int, "int-notice");
  observe("lead-interrupted-worker-ended");

  // Scenario 9 (question 7): a lead in a TUI launches a worker and the TUI
  // quits while the worker runs.
  trace("scenario", { name: "tui" });
  const tui = tuiClient("tui", [treeC, "--prompt", "PROBE:tui-lead"]);
  await waitFor(() => command("w14-hold", "start"), "TUI worker holding", 90000);
  known.tui = claimOf("tui-start");
  await quit(tui, "ctrl-c");
  await settle(1000);
  await active("tui-quit-worker-running");
  observe("tui-quit-worker-running");
  check("tree-c-tui-quit-worker-running", treeC);
  await waitFor(() => command("w14-hold"), "w14 ended", 30000);
  known.w14 = claimOf("w14-hold");
  await waitFor(() => noticed(known.tui, known.w14), "client-less lead noticed w14", 20000).catch((error) => trace("missing", { label: "tui-notice", error: String(error) }));
  await settle(2000);
  await idle(known.tui, "tui-notice");
  observe("tui-quit-worker-ended");
  check("tree-c-tui-quit-worker-ended", treeC);

  // Scenario 10 (question 7): the lead deleted while its worker runs.
  trace("scenario", { name: "delete" });
  known.del = await session("Deleted", treeA);
  await prompt(known.del, "del-bind");
  await prompt(known.del, "del-launch");
  await waitFor(() => command("w15-hold", "start"), "w15 holding", 30000);
  known.w15 = claimOf("w15-hold");
  await settle(500);
  observe("delete-worker-running");
  check("tree-b-delete-worker-running", treeB);
  trace("delete", { sessionID: known.del, ...(await request("DELETE", `/api/session/${known.del}`)) });
  await settle(9000);
  trace("worker.after-delete", { held: Boolean(command("w15-hold")), after: Boolean(command("w15-after", "start")), info: await info(known.w15) });
  await active("lead-deleted");
  stateFiles("lead-deleted");
  observe("lead-deleted");
  check("tree-b-lead-deleted", treeB);

  // Scenario 11 (question 8): the skills OpenCode offers and loads, with the
  // Issue-work skill where `integrate` put it, two user-only candidates
  // beside it, and skills in Claude Code's and the shared `.agents`
  // directories present for this scenario only.
  trace("scenario", { name: "skills" });
  const skillFile = (directory, id, front) => {
    mkdirSync(path.join(directory, id), { recursive: true });
    writeFileSync(path.join(directory, id, "SKILL.md"), `---\n${front}\n---\n\nfixture-skill-marker: ${id}\n`);
  };
  skillFile(skillsHome, "fixture-user-only", `name: fixture-user-only\ndescription: A fixture skill marked user-invoked only for OpenCode.\nmetadata:\n  opencode/autoinvoke: false`);
  skillFile(skillsHome, "fixture-claude-flag", `name: fixture-claude-flag\ndescription: A fixture skill marked user-invoked only for Claude Code.\ndisable-model-invocation: true`);
  const external = [path.join(env.HOME, ".claude", "skills"), path.join(env.HOME, ".agents", "skills")];
  skillFile(external[0], "fixture-external-claude", "name: fixture-external-claude\ndescription: A fixture skill in Claude Code's directory.");
  skillFile(external[1], "fixture-external-agents", "name: fixture-external-agents\ndescription: A fixture skill in the shared agents directory.");
  const listed = async () => (await request("GET", "/api/skill", undefined, { directory: fixture })).body;
  const ids = (list) => (Array.isArray(list) ? list : []).map((item) => item.id).toSorted();
  try { await waitFor(() => false, "never", 3000); } catch {}
  let skills = await listed();
  if (!ids(skills).includes("fixture-external-agents")) {
    trace("reload", { label: "skills", ...cli(["reload"]) });
    await settle(4000);
    skills = await listed();
  }
  trace("skills.listed", { skills: (Array.isArray(skills) ? skills : []).map((item) => ({ id: item.id, name: item.name, autoinvoke: item.autoinvoke ?? null,
    path: retained(item.path ?? "") })), raw: Array.isArray(skills) ? undefined : retained(JSON.stringify(skills)).slice(0, 600) });
  known.skills = await session("Skills", fixture);
  await prompt(known.skills, "skills-probe");
  known.skillsUser = await session("SkillsUser", fixture);
  await prompt(known.skillsUser, "skills-user", { skills: [{ id: "fixture-user-only" }] });
  for (const directory of external) rmSync(path.dirname(directory), { recursive: true, force: true });
  integrate("status-skills", ["opencode", "--status"]);

  // Scenario 12 (question 6): a worker agent defined in the Project's own
  // configuration, which the run enables for this scenario only, after
  // checking that no directory above the fixture holds configuration.
  trace("scenario", { name: "project-agent" });
  const ancestors = [];
  for (let directory = path.dirname(root); ; directory = path.dirname(directory)) {
    for (const name of [".opencode", ".claude", ".agents", "opencode.json", "opencode.jsonc", "AGENTS.md", "CLAUDE.md"]) if (existsSync(path.join(directory, name))) ancestors.push(path.join(directory, name));
    if (directory === path.dirname(directory)) break;
  }
  trace("project.ancestors", { found: ancestors.map(retained) });
  assert.equal(ancestors.length, 0, "a directory above the fixture holds configuration");
  agentFile(path.join(fixture, ".opencode", "agent"), "dashpot-worker-project", "subagent");
  const stopping = service.pid;
  trace("service.stop", { label: "project-config", ...cli(["service", "stop"]) });
  await waitFor(() => !alive(stopping), "service stopped for project configuration", 15000);
  trace("service.start", { label: "project-config", ...cli(["service", "start"], { without: ["OPENCODE_DISABLE_PROJECT_CONFIG"] }) });
  await awaitService("project-config");
  trace("agents.listed", { label: "project-config", agents: await agentIds("dashpot-worker-project") });
  known.guardProject = await session("GuardProject", fixture);
  await attempt(known.guardProject, "guard-project", "w21");
  rmSync(path.join(fixture, ".opencode"), { recursive: true, force: true });

  trace("models", { requests: Object.fromEntries(modelRequests) });
  trace("known", { sessions: known });
  trace("done");
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: retained(String(error?.stack ?? error)) });
  console.error(error);
  for (const state of clients) if (!state.exited) trace("client.screen", { name: state.name, screen: retained(state.output.slice(-2000)) });
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
    .map((event) => ({ kind: event["dashpot.process.kind"], result: event["dashpot.outcome.result"], reason: event["dashpot.hook.reason"] ?? null })) });
  for (const state of clients) if (!state.exited) state.child.kill("SIGKILL");
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
