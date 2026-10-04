// Worker-mechanics run for Issue #420: drives a pinned Codex CLI against a
// loopback Responses API fixture with an isolated CODEX_HOME, whose daemon
// updater is off, and Dashpot's own Codex hook publisher, in a disposable
// Dashpot Project whose Issues are Local Issue Markdown. A lead thread on the
// managed daemon launches background workers through the sub-agent tools the
// fixture model calls, under both of Codex's tool sets: multi-agent v2, which
// the bundled model catalog selects for its current models, and v1, which a
// model the catalog does not name gets. It measures launch, a worker's
// mid-flight message, completion, a waiting loop, resume, the concurrency
// limit and how to raise it, the shared Agent Session and the location a
// worker works in, the effect of interrupting, unloading and deleting the
// lead, and where Codex loads a skill from, and records each step's hooks,
// shells, model requests, protocol results, and Dashpot's own published view
// as a metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";
import { connectUnixWebSocket } from "./uds-websocket.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.160.0";
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-420-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const third = path.join(root, "third-worktree");
const fourth = path.join(root, "fourth-worktree");
const worktrees = { main: fixture, other, third, fourth };
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's temporary root
// never enter the trace; a hook's or shell's ancestry keeps the processes up
// to the runner's own child.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 5) } : record;
  appendFileSync(tracePath, JSON.stringify(kept).replaceAll(root, "$ROOT").replaceAll(home, "~").replace(hostName, "<host>") + "\n");
  return record;
};

// The pinned release runs through a fixture-local `codex` on PATH.
const fixtureBin = path.join(root, "bin");
mkdirSync(fixtureBin);
symlinkSync(binary, path.join(fixtureBin, "codex"));
const env = {
  PATH: `${fixtureBin}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  // Dashpot's machine-local state, like Codex's, stays inside the fixture.
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  SPIKE_PUBLISHER: publisher,
  SPIKE_DASHPOT: dashpotCommand,
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable Dashpot Project: four Local Issue Markdown Issues, the main
// working tree, and three linked Worktrees.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2, 3, 4]) {
  const metadata = { id: `I_fixture_${number}`, number, reference: `fixture-${number}`, state: "open", stateReason: null, labels: [], assignees: [], author: null,
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${number}.md`), `---\n${JSON.stringify(metadata, null, 2)}\n---\n# Fixture Issue ${number}\n\nDisposable.\n`);
}
const dashpot = (args, cwd = fixture) => {
  const ran = spawnSync(dashpotCommand, args, { cwd, env, encoding: "utf8", timeout: 60000 });
  return { status: ran.status, stdout: ran.stdout ?? "", stderr: ran.stderr ?? "" };
};
const initialized = dashpot(["init", "--markdown", "issues"]);
assert.equal(initialized.status, 0, `dashpot init: ${initialized.stderr}`);
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const [name, dir] of Object.entries(worktrees)) if (name !== "main") git("worktree", "add", "-b", name, dir);

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
  trace(url.pathname === "/hook" ? "hook" : "command", await body(req));
  res.end("{}");
});
const stripAnsi = (text) => text.replace(/\u001b\[[0-9;?]*[ -\/]*[@-~]/g, "").replace(/\u001b\][^\u0007]*\u0007/g, "");
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` (a user prompt, or the message a
// lead sent a worker) selects the plan `plans[label]`; the number of tool
// outputs after that item selects the step. Each step becomes one tool call;
// when the plan runs out, the model answers `DONE:<label>`, which is the
// worker's final message. A worker's mid-flight message is `NOTE:<label>`.
// Every request records which of these markers its input carries, where, and
// in which kind of item, which is how the trace shows what reached a lead and
// when. Steps name a tool, never a tool set: the call goes to whichever
// namespace offers that tool, and a missing tool ends the plan.
const commandScript = path.join(here, "command.mjs");
const exec = (options = {}) => ({ exec: options });
const plans = {
  // Multi-agent v2 lead L.
  "a-bind": [exec({ work: "start-1" })],
  "a-explicit": [],
  "a-launch": [{ spawn: ["worker_a", "wa"] }, { spawn: ["worker_b", "wb"] }],
  wa: [exec({ cd: other, hold: 500, work: "start-2" }), exec({ cd: other, work: "relocate" }), exec({ cd: other, work: "show" }),
    { send: ["/root", "NOTE:wa"] }, exec({ cd: other, hold: 8000 })],
  wb: [exec({ work: "start-2" }), exec({ hold: 14000, work: "show" })],
  "a-collect": [],
  "a-wait": [{ spawn: ["worker_c", "wc"] }, exec({ hold: 6000 }), { wait: 60000 }],
  wc: [exec({ hold: 2000 }), { send: ["/root", "NOTE:wc"] }, exec({ hold: 8000 })],
  "a-resume": [{ send: ["/root/worker_b", "NOTE:to-wb"] }, exec({ hold: 4000 }), { followup: ["/root/worker_a", "wa2"] }, { wait: 60000 }],
  // A command without `cd` after one with it shows where the next shell starts.
  wa2: [exec({ cd: other, work: "show" }), exec()],
  // A waiting loop: the first wait asks for less than the minimum, and the
  // last outlasts the worker.
  "a-loop": [{ spawn: ["worker_l", "wl"] }, { wait: 5000 }, { wait: 10000 }, { wait: 10000 }, { wait: 10000 }, { list: true }],
  wl: [exec({ hold: 3000 }), { send: ["/root", "NOTE:wl1"] }, exec({ hold: 3000 }), { send: ["/root", "NOTE:wl2"] }, exec({ hold: 3000 })],
  "a-limit": [1, 2, 3, 4].map((index) => ({ spawn: [`worker_d${index}`, `wd${index}`] })),
  "a-limit-again": [{ spawn: ["worker_d5", "wd5"] }, { list: true }],
  wd1: [exec({ hold: 12000 })], wd2: [exec({ hold: 12000 })], wd3: [exec({ hold: 12000 })], wd4: [exec({ hold: 12000 })], wd5: [exec({ hold: 1000 })],
  "a-cut": [{ spawn: ["worker_e", "we"] }, exec({ hold: 3000 }), { interrupt: "/root/worker_e" }],
  we: [exec({ work: "stop" }), exec({ hold: 20000 })],
  // Multi-agent v2 leads M, N and P for the interruption scenarios.
  "m-wait": [{ spawn: ["worker_f", "wf"] }, { wait: 60000 }],
  wf: [exec({ hold: 15000 })],
  "m-after": [{ list: true }],
  "n-spawn": [exec({ work: "start-3" }), { spawn: ["worker_g", "wg"] }],
  // Codex returns an exec call after 30 s at most, so a long hold is several calls.
  wg: [exec({ hold: 25000 }), exec({ hold: 25000 }), exec({ hold: 25000 }), exec({ hold: 25000 })],
  "p-spawn": [{ spawn: ["worker_h", "wh"] }],
  wh: [exec({ hold: 20000 })],
  // Multi-agent v1 lead V.
  "v1-launch": [{ spawn: ["-", "v1a"] }],
  v1a: [exec({ hold: 6000 }), { send: ["/root", "NOTE:v1a"] }],
  "v1-collect": [],
  "v1-resume": [{ followup: ["v1a", "v1a2"] }, { wait: 60000 }],
  v1a2: [exec({ work: "show" })],
  // Lead F: the v2 feature flag on a model the catalog does not name.
  "f-launch": [{ spawn: ["worker_flag", "fc"] }, { wait: 30000 }],
  fc: [{ send: ["/root", "NOTE:fc"] }, exec()],
  // Lead Q: a raised thread limit.
  "q-spawn": [1, 2, 3, 4, 5].map((index) => ({ spawn: [`worker_q${index}`, `wq${index}`] })).concat([{ wait: 30000 }]),
  ...Object.fromEntries([1, 2, 3, 4, 5].map((index) => [`wq${index}`, [exec({ hold: 4000 })]])),
};
// No word boundary: Codex puts a worker's final message straight after a
// newline, which JSON escapes as `\n`.
const markerPattern = /(SPIKE|NOTE|DONE):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
// Parsed JSON, or null for text that is not JSON.
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const modelRequests = [];
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const lastToolsByThread = new Map();
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/responses")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  // The `thread_id` header names the root session for every thread in a
  // tree; the request's client metadata names the thread itself.
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const session = payload.client_metadata?.session_id ?? req.headers["session_id"] ?? null;
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) { directiveAt = index; label = found.at(-1)[2]; }
  });
  const markers = input.flatMap((item, index) => [...new Set([...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[0]))]
    .map((marker) => [index, item.type ?? null, item.role ?? null, marker]));
  // Every inter-agent item the thread's input carries: who wrote it, to whom,
  // and the start of its text, which Codex composes from fixture markers.
  const textOf = (item) => [item.content ?? []].flat().map((part) => typeof part === "string" ? part : Object.values(part ?? {}).filter((value) => typeof value === "string" && value !== part.type).join(" ")).join(" | ");
  const agentMessages = input.flatMap((item, index) => item.type === "agent_message"
    ? [[index, item.author ?? null, item.recipient ?? null, textOf(item).slice(0, 160)]] : []);
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsKey = toolNames.join(",");
  const toolsChanged = lastToolsByThread.get(thread) !== toolsKey;
  lastToolsByThread.set(thread, toolsKey);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const v2 = Boolean(offered("list_agents"));
  // Skill evidence: whether the context Codex sent names each fixture skill,
  // outside the person's own prompts, and whether either skill's body was
  // injected.
  const context = JSON.stringify([payload.instructions ?? null, input.filter((item) => !(item.type === "message" && item.role === "user" && JSON.stringify(item).includes("SPIKE:")))]);
  const whole = JSON.stringify(payload);
  const skills = { implicitListed: context.includes("fixture-implicit"), explicitListed: context.includes("fixture-explicit"),
    implicitBody: whole.includes("FIXTURE-IMPLICIT-BODY"), explicitBody: whole.includes("FIXTURE-EXPLICIT-BODY") };
  // A v1 worker is addressed by the agent id its spawn returned.
  const spawnCalls = input.filter((item) => item.type === "function_call" && item.name === "spawn_agent");
  const spawnedIdOf = (call) => parseJson(input.find((item) => item.type === "function_call_output" && item.call_id === call.call_id)?.output)?.agent_id ?? null;
  const agentIdOf = (childLabel) => {
    const call = spawnCalls.find((item) => String(item.arguments).includes(`SPIKE:${childLabel}`));
    return call ? spawnedIdOf(call) : null;
  };
  const spawnedIds = () => spawnCalls.map(spawnedIdOf).filter(Boolean);
  const plan = label ? plans[label] ?? [] : [];
  const step = plan[outputs.length] ?? null;
  const call = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.exec) {
    const { cd = null, hold = 200, work = "-" } = step.exec;
    action = "exec_command";
    item = call("exec_command", { cmd: `${cd ? `cd ${cd} && ` : ""}node ${commandScript} ${label}.${outputs.length} ${hold} ${work}`, login: false, yield_time_ms: 120000 });
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = call("spawn_agent", v2 ? { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" } : { message: `SPIKE:${child}` });
  } else if (step?.send) {
    const [target, text] = step.send;
    action = v2 ? "send_message" : "send_input";
    item = v2 ? call("send_message", { target, message: text }) : call("send_input", { target: agentIdOf(target) ?? target, message: text });
  } else if (step?.followup) {
    const [target, child] = step.followup;
    action = v2 ? "followup_task" : "send_input";
    item = v2 ? call("followup_task", { target, message: `SPIKE:${child}` }) : call("send_input", { target: agentIdOf(target) ?? target, message: `SPIKE:${child}` });
  } else if (step?.wait) {
    action = "wait_agent";
    item = call("wait_agent", v2 ? { timeout_ms: step.wait } : { targets: spawnedIds(), timeout_ms: step.wait });
  } else if (step?.interrupt) {
    action = "interrupt_agent";
    item = call("interrupt_agent", { target: step.interrupt });
  } else if (step?.list) {
    action = "list_agents";
    item = call("list_agents", {});
  }
  // The output of the latest call, which Codex may follow with inter-agent items.
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const lastOutput = latestOutput ? String(latestOutput.output ?? "").replaceAll(root, "$ROOT").slice(0, 400) : null;
  const request = trace("model.request", { thread, label, step: outputs.length, inputItems: input.length, directiveAt, markers, action, missing: Boolean(step && !item),
    lastOutput, tools: toolsChanged ? toolNames : undefined, v2, skills, session, agentMessages,
    tail: input.slice(-3).map((item) => [item.type ?? null, item.role ?? null]), parentThread: req.headers["x-codex-parent-thread-id"] ?? null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The hook events `dashpot integrate codex` subscribes, each routed through
// the metadata wrapper to Dashpot's real publisher.
const hookEvents = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks);
const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 15 }] }]])),
}, null, 2));

// The model catalog: the bundled one decides which tool set each real model
// gets. The fixture's catalog names `fixture-v2` only, a copy of the bundled
// entry without a tool set or code mode, declaring multi-agent v2; the
// default `fixture-model` stays unnamed, as in the earlier Codex runs.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const catalogSummary = bundled.models.map((entry) => [entry.slug, entry.multi_agent_version ?? null, entry.tool_mode ?? null]);
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

// Two fixture skills where `dashpot integrate codex` installs its skill: one
// the model may invoke implicitly, one marked for explicit `$name` use only.
const skillsHome = path.join(env.HOME, ".agents", "skills");
const skill = (name, description, bodyMarker, policy) => {
  const dir = path.join(skillsHome, name);
  mkdirSync(path.join(dir, "agents"), { recursive: true });
  writeFileSync(path.join(dir, "SKILL.md"), `---\nname: ${name}\ndescription: ${description}\n---\n\n# ${name}\n\n${bodyMarker}\n`);
  if (policy) writeFileSync(path.join(dir, "agents", "openai.yaml"), `policy:\n  allow_implicit_invocation: false\n`);
};
skill("fixture-implicit", "Fixture skill the model may invoke on its own.", "FIXTURE-IMPLICIT-BODY", false);
skill("fixture-explicit", "Fixture skill invoked only when the person names it.", "FIXTURE-EXPLICIT-BODY", true);

const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-model"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"

[features]
hooks = true
multi_agent = true
# The curated plugin marketplace sync clones a GitHub repository at startup.
plugins = false
apps = false

[analytics]
enabled = false

[model_providers.fixture]
name = "Fixture"
base_url = "${model.url}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
${Object.values(worktrees).map((dir) => `\n[projects."${dir}"]\ntrust_level = "trusted"\n`).join("")}`);
// The fixture daemon's updater stays off: it would fetch the standalone
// installer over the network, and installing a release could replace or
// restart the pinned daemon mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const daemonSettings = () => {
  try { return JSON.parse(readFileSync(daemonSettingsPath, "utf8")); } catch (error) { return { unreadable: String(error) }; }
};

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let entry;
    try { entry = describe(Number(name)); } catch { continue; }
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`)) continue;
    if (entry.pid === process.pid) continue;
    found.push(entry);
  }
  return found;
};
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline.replaceAll(root, "<root>").slice(0, 240)];
const isDaemon = (entry) => entry.comm.startsWith("codex") && / app-server /.test(entry.cmdline) && / --managed-daemon/.test(entry.cmdline);
const daemons = () => codexProcesses().filter(isDaemon);
const isSettler = (entry) => / -m dashpot\.hook settle /.test(entry.cmdline);
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const processes = (label) => trace("processes", { label, processes: codexProcesses().map(brief), daemons: daemons().map((entry) => entry.pid), socketExists: existsSync(socketPath),
  daemonSettings: daemonSettings() });
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const hostOf = (record) => record?.ancestry?.find((entry) => entry.comm.startsWith("codex"))?.pid ?? null;
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const settlersDone = async (label) => {
  await delay(500);
  await quietly(waitFor(() => !codexProcesses().some(isSettler), `${label}: settlers exit`, 15000));
};
const threadSummary = (thread) => thread && ({ id: thread.id, forkedFromId: thread.forkedFromId ?? null, parentThreadId: thread.parentThreadId ?? null, cwd: thread.cwd ?? null,
  status: thread.status, ephemeral: thread.ephemeral, agentPath: thread.agentPath ?? null, model: thread.model ?? null });
// Hooks in a window, as [event, session, agent, turn, cwd, time].
const timeline = (since) => hooks().slice(since).map((record) => [record.event, record.payload.session_id, record.payload.agent_id ?? null, record.payload.turn_id ?? null, record.payload.cwd, record.receiptTime]);
const stopped = (since, agent) => hooks().slice(since).some((record) => record.event === "SubagentStop" && record.payload.agent_id === agent);
const requestsOf = (thread, after = 0) => modelRequests.filter((record) => record.thread === thread && record.receiptTime > after);
const loadedThreads = async (client) => (await client.call("thread/loaded/list", {})).result?.data ?? [];
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;

// Dashpot's published view of the fixture: the Agent Runs, the diagnostics,
// and each Worktree's state files by name.
const stateFiles = (dir) => {
  const found = [];
  const walk = (current, prefix) => {
    let entries = [];
    try { entries = readdirSync(current, { withFileTypes: true }); } catch { return; }
    for (const entry of entries) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) walk(path.join(current, entry.name), relative); else found.push(relative);
    }
  };
  walk(path.join(dir, ".dashpot", "state"), "");
  return found.filter((name) => !name.startsWith("events/") && name !== ".gitignore").sort();
};
const view = (label, extra = {}) => {
  const ran = dashpot(["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400), agentRuns: parsed?.agentRuns ?? null,
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })),
    stateFiles: Object.fromEntries(Object.entries(worktrees).map(([name, dir]) => [name, stateFiles(dir)])), ...extra });
};
const worktreeCheck = (label, dir) => {
  const ran = dashpot(["worktree", "check", dir, "--json"]);
  const parsed = parseJson(ran.stdout);
  return trace("dashpot.worktree-check", { label, worktree: dir, status: ran.status, result: parsed, stderr: ran.stderr.slice(0, 300) });
};
const shellSummary = (label) => {
  const shell = command(label);
  const work = command(label, "work")?.work ?? null;
  return shell && { label, cwd: shell.cwd, thread: shell.env.CODEX_THREAD_ID ?? null, session: shell.env.CODEX_SESSION_ID ?? null, host: hostOf(shell),
    ended: command(label, "end")?.receiptTime ?? null, started: shell.receiptTime,
    work: work && { args: work.args, status: work.status, stdout: work.stdout, stderr: work.stderr } };
};

// One-shot Codex commands, launched by name through the fixture PATH.
const codex = async (args, label, { cwd = fixture, timeout = 60000 } = {}) => {
  const child = spawn("codex", args, { cwd, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const clean = (text) => stripAnsi(text).replaceAll(root, "<root>");
  const statusLines = (text) => clean(text).split("\n").filter((line) => /^(OpenAI Codex v|warning: |hook: |Installing |Error: )/.test(line)).join("\n");
  trace("codex.command", { label, args: args.map((arg) => arg.replaceAll(root, "<root>")), status, signal, stdout: clean(stdout).slice(-600), stderr: statusLines(stderr).slice(-1200) });
  return { status, signal, stdout, stderr };
};

const freePort = async () => {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = probe.address().port;
  probe.close();
  return port;
};
// A JSON-RPC client over a WebSocket: loopback TCP, or the daemon's control
// socket, which speaks WebSocket over a Unix domain socket.
const rpcClient = async (name, socket) => {
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  const onMessage = (text) => {
    const parsed = parseJson(text);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method?.startsWith("thread/") || parsed.method?.startsWith("turn/")) {
      const { threadId, turn, status, thread } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id, status: status ?? turn?.status, receivedAt: Date.now() });
    }
  };
  socket.on(onMessage);
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-420-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, transport: socket.transport, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, notifications, close: () => socket.close() };
};
const tcpClient = async (name, port) => {
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  return rpcClient(name, { transport: "loopback-websocket", on: (listener) => socket.addEventListener("message", (message) => listener(message.data)), send: (text) => socket.send(text), close: () => socket.close() });
};
const daemonClient = async (name) => {
  const socket = await connectUnixWebSocket(socketPath);
  return rpcClient(name, { transport: "unix-websocket", on: (listener) => socket.on("message", listener), send: (text) => socket.send(text), close: () => socket.close() });
};
const completedTurn = (client, turnId) => client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
const runTurn = async (client, threadId, text, options = {}) => {
  const hooksBefore = hooks().length;
  const startedAt = Date.now();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, status: started.result?.turn?.status ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, hooksBefore, startedAt };
  await waitFor(() => completedTurn(client, turnId), `turn ${text} completed`, options.timeout ?? 60000);
  const completed = completedTurn(client, turnId);
  await waitFor(() => hooks().slice(hooksBefore).some((record) => record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000).catch(() => {});
  trace("turn.completed", { client: client.name, threadId, turnId, status: completed.status, completedAt: completed.receivedAt });
  return { turnId, hooksBefore, startedAt, status: completed.status, completedAt: completed.receivedAt };
};
const startThread = async (client, name, params) => {
  const started = await client.call("thread/start", { cwd: fixture, ...params });
  const thread = started.result?.thread;
  trace("thread.start", { name, params: { ...params, cwd: params.cwd ?? fixture }, thread: threadSummary(thread), error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
const readThread = async (client, threadId) => {
  const read = await client.call("thread/read", { threadId });
  return threadSummary(read.result?.thread) ?? { error: read.error ?? null };
};

const scripts = ["run.mjs", "verify.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "deferred_end.py", "work_reconciliation.py", "hook_records.py", "work.py", "hook_scan.py", "processes.py"].map((file) => `src/dashpot/sessions/${file}`);
let controllers = [];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(os.homedir(), "~"),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, dirty }, worktrees, socketPath, hookEvents, catalogSummary,
    fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2" }, skillsHome,
    // The runner's own scripts by name, and the lifecycle modules it
    // exercised by repository path.
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });

  // Setup: trust the fixture hooks through the ledger on a loopback server.
  trace("scenario", { name: "hook-trust" });
  const port = await freePort();
  const trustServer = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let trustBanner = "";
  trustServer.stderr.on("data", (chunk) => { trustBanner += chunk; });
  trustServer.stdout.on("data", () => {});
  await waitFor(() => trustBanner.includes("listening on"), "trust server listening", 20000);
  const trust = await tcpClient("trust", port);
  const listed = await trust.call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await trust.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  trust.close();
  trustServer.kill("SIGTERM");
  await once(trustServer, "exit");
  await delay(500);

  // The managed daemon hosts every lead; controllers drive it as a client would.
  trace("scenario", { name: "daemon" });
  await codex(["app-server", "daemon", "start"], "daemon-start", { timeout: 60000 });
  await waitFor(() => existsSync(socketPath) && daemons().length === 1, "daemon control socket", 30000);
  processes("daemon-started");
  const daemonPid = daemons()[0].pid;
  const c1 = await daemonClient("controller-1");
  controllers.push(c1);

  // Q8 and the bound lead: a v2 lead binds Issue 1 in the main Worktree; its
  // first request shows which fixture skill Codex lists, and a prompt naming
  // the explicit-only skill shows whether `$name` injects it.
  trace("scenario", { name: "skills" });
  const lead = await startThread(c1, "lead", { model: "fixture-v2" });
  const bind = await runTurn(c1, lead, "SPIKE:a-bind");
  const explicit = await runTurn(c1, lead, "SPIKE:a-explicit $fixture-explicit");
  trace("skills.outcome", { lead, bind: requestsOf(lead, bind.startedAt).filter((record) => record.label === "a-bind").map((record) => record.skills),
    explicit: requestsOf(lead, explicit.startedAt).filter((record) => record.label === "a-explicit").map((record) => record.skills), shell: shellSummary("a-bind.0") });
  view("lead-bound");

  // Q1-Q3, Q5, Q6: the lead spawns two workers and its turn ends. Worker A
  // works in `other` by a per-command `cd`, tries `work start` and `work
  // relocate` there, reads `work show`, messages the lead mid-flight, and
  // keeps working; worker B works in the lead's directory. The lead stays
  // idle while both report and finish.
  trace("scenario", { name: "launch" });
  const launch = await runTurn(c1, lead, "SPIKE:a-launch");
  const launchedAt = Date.now();
  await waitFor(() => command("wa.0") && command("wb.0"), "both workers' first commands", 60000);
  const workerA = threadOf("wa.0");
  const workerB = threadOf("wb.0");
  view("launch-workers-running");
  worktreeCheck("launch-workers-running-other", other);
  worktreeCheck("launch-workers-running-fourth", fourth);
  await waitFor(() => command("wa.4"), "worker A's command after its message", 60000);
  await delay(3000);
  view("launch-worker-a-messaged");
  await waitFor(() => stopped(launch.hooksBefore, workerA) && stopped(launch.hooksBefore, workerB), "both workers stop", 60000);
  await delay(5000);
  trace("launch.outcome", { lead, workerA, workerB, launchTurn: launch.turnId, leadStoppedAt: launch.completedAt, launchedAt,
    leadRequestsAfterStop: requestsOf(lead, launch.completedAt).map((record) => record.receipt),
    leadNotificationsAfterStop: c1.notifications.filter((entry) => entry.threadId === lead && entry.receivedAt > launch.completedAt).map((entry) => [entry.method, entry.turnId ?? null, entry.status ?? null]),
    shells: ["wa.0", "wa.1", "wa.2", "wa.4", "wb.0", "wb.1"].map(shellSummary), hooks: timeline(launch.hooksBefore),
    workerARead: await readThread(c1, workerA), workerBRead: await readThread(c1, workerB) });
  view("launch-workers-stopped");
  worktreeCheck("launch-workers-stopped-other", other);

  // Q2 and Q3 on the lead's next turn: what the idle lead receives.
  trace("scenario", { name: "collect" });
  const collect = await runTurn(c1, lead, "SPIKE:a-collect");
  trace("collect.outcome", { requests: requestsOf(lead, collect.startedAt).map((record) => record.receipt) });

  // Q2 and Q3 with a busy lead: the lead spawns worker C, runs a 6 s command
  // while C messages it, then waits; C finishes during the wait.
  trace("scenario", { name: "wait" });
  const waiting = await runTurn(c1, lead, "SPIKE:a-wait", { timeout: 120000 });
  trace("wait.outcome", { worker: threadOf("wc.0"), requests: requestsOf(lead, waiting.startedAt).map((record) => record.receipt), shells: ["a-wait.1", "wc.0", "wc.2"].map(shellSummary),
    hooks: timeline(waiting.hooksBefore) });

  // Q4: the lead queues a message to finished worker B, runs a command, then
  // gives finished worker A a follow-up task and waits for it.
  trace("scenario", { name: "resume" });
  const resumeTurn = await runTurn(c1, lead, "SPIKE:a-resume", { timeout: 120000 });
  await delay(2000);
  trace("resume.outcome", { workerA, workerB, requestsA: requestsOf(workerA, resumeTurn.startedAt).map((record) => record.receipt),
    requestsB: requestsOf(workerB, resumeTurn.startedAt).map((record) => record.receipt), leadRequests: requestsOf(lead, resumeTurn.startedAt).map((record) => record.receipt),
    shells: ["wa2.0", "wa2.1"].map(shellSummary), hooks: timeline(resumeTurn.hooksBefore), workerARead: await readThread(c1, workerA) });
  view("after-resume");

  // Q2 and Q3 in one waiting loop: lead L spawns worker L and waits four
  // times in one turn while L messages twice and finishes, then lists.
  trace("scenario", { name: "wait-loop" });
  const loop = await runTurn(c1, lead, "SPIKE:a-loop", { timeout: 120000 });
  await delay(1500);
  trace("wait-loop.outcome", { worker: threadOf("wl.0"), requests: requestsOf(lead, loop.startedAt).filter((record) => record.label === "a-loop").map((record) => [record.receipt, record.receiptTime, record.action, record.lastOutput]),
    workerRequests: requestsOf(threadOf("wl.0"), loop.startedAt).map((record) => [record.receipt, record.receiptTime, record.action]),
    shells: ["wl.0", "wl.2", "wl.4"].map(shellSummary), hooks: timeline(loop.hooksBefore) });

  // Q1: the concurrency limit. Four spawns in one turn, then a fifth once
  // they have finished.
  trace("scenario", { name: "limit" });
  const limit = await runTurn(c1, lead, "SPIKE:a-limit");
  await delay(1500);
  const limitWorkers = ["wd1.0", "wd2.0", "wd3.0", "wd4.0"].map(threadOf).filter(Boolean);
  await quietly(waitFor(() => limitWorkers.every((worker) => stopped(limit.hooksBefore, worker)), "limit workers stop", 40000));
  await delay(1500);
  const again = await runTurn(c1, lead, "SPIKE:a-limit-again");
  await quietly(waitFor(() => command("wd5.0", "end"), "fifth worker's command ends", 30000));
  await delay(3000);
  trace("limit.outcome", { started: ["wd1.0", "wd2.0", "wd3.0", "wd4.0", "wd5.0"].map((label) => Boolean(command(label))), workers: limitWorkers,
    requests: requestsOf(lead, limit.startedAt).map((record) => record.receipt), hooks: timeline(limit.hooksBefore), againTurn: again.turnId,
    loaded: await loadedThreads(c1) });

  // Q1 and Q3 under v1: lead V spawns a worker whose plan also tries to
  // message the lead, and its turn ends; then V's next turn, then V resumes
  // the finished worker with `send_input` and waits.
  trace("scenario", { name: "v1" });
  const v1 = await startThread(c1, "v1-lead", { model: "fixture-model" });
  const v1Launch = await runTurn(c1, v1, "SPIKE:v1-launch");
  await waitFor(() => command("v1a.0"), "v1 worker's command", 60000);
  const v1Worker = threadOf("v1a.0");
  await waitFor(() => stopped(v1Launch.hooksBefore, v1Worker), "v1 worker stops", 60000);
  await delay(5000);
  const v1Collect = await runTurn(c1, v1, "SPIKE:v1-collect");
  const v1Resume = await runTurn(c1, v1, "SPIKE:v1-resume", { timeout: 120000 });
  await delay(1500);
  trace("v1.outcome", { lead: v1, worker: v1Worker, launchStoppedAt: v1Launch.completedAt, leadRequestsAfterStop: requestsOf(v1, v1Launch.completedAt).filter((record) => record.receiptTime < v1Collect.startedAt).map((record) => record.receipt),
    collect: requestsOf(v1, v1Collect.startedAt).filter((record) => record.receiptTime < v1Resume.startedAt).map((record) => record.receipt),
    resume: requestsOf(v1, v1Resume.startedAt).map((record) => record.receipt), workerRequests: requestsOf(v1Worker).map((record) => record.receipt),
    shells: ["v1a.0", "v1a2.0"].map(shellSummary), hooks: timeline(v1Launch.hooksBefore), workerRead: await readThread(c1, v1Worker) });

  // The v2 feature flag on a model the catalog does not name: the tools the
  // lead and its worker get.
  trace("scenario", { name: "flag" });
  const flagged = await startThread(c1, "flag-lead", { model: "fixture-model", config: { "features.multi_agent_v2": true } });
  const flagTurn = await runTurn(c1, flagged, "SPIKE:f-launch", { timeout: 90000 });
  await delay(1500);
  trace("flag.outcome", { lead: flagged, requests: requestsOf(flagged, flagTurn.startedAt).map((record) => record.receipt),
    worker: threadOf("fc.0") ?? threadOf("fc.1"), hooks: timeline(flagTurn.hooksBefore) });

  // Q1: a lead started with a raised thread limit spawns five workers.
  trace("scenario", { name: "limit-raised" });
  const leadQ = await startThread(c1, "lead-q", { model: "fixture-v2", config: { "agents.max_threads": 5 } });
  const qTurn = await runTurn(c1, leadQ, "SPIKE:q-spawn", { timeout: 90000 });
  const qLabels = [1, 2, 3, 4, 5].map((index) => `wq${index}.0`);
  await quietly(waitFor(() => qLabels.every((label) => command(label, "end")), "raised-limit workers' commands end", 30000));
  await delay(2000);
  trace("limit-raised.outcome", { lead: leadQ, started: qLabels.map((label) => Boolean(command(label))),
    spawns: requestsOf(leadQ, qTurn.startedAt).filter((record) => record.label === "q-spawn").map((record) => [record.receipt, record.action, record.lastOutput]), hooks: timeline(qTurn.hooksBefore) });

  // Q5 and Q7: worker E tries `work stop`, then the lead interrupts it with
  // `interrupt_agent` while it works.
  trace("scenario", { name: "agent-interrupt" });
  const cut = await runTurn(c1, lead, "SPIKE:a-cut", { timeout: 90000 });
  const cutAt = Date.now();
  const cutWorker = threadOf("we.0");
  await quietly(waitFor(() => command("we.1", "end"), "interrupted worker's command ends", 30000));
  await quietly(waitFor(() => stopped(cut.hooksBefore, cutWorker), "interrupted worker stops", 5000));
  await delay(2000);
  trace("agent-interrupt.outcome", { lead, worker: cutWorker, cutAt, requests: requestsOf(lead, cut.startedAt).map((record) => record.receipt),
    workerRequests: requestsOf(cutWorker).map((record) => record.receipt), shells: ["we.0", "we.1"].map(shellSummary), hooks: timeline(cut.hooksBefore), workerRead: await readThread(c1, cutWorker) });
  view("after-agent-interrupt");
  worktreeCheck("after-agent-interrupt-fourth", fourth);

  // Q7: a controller interrupts lead M's turn while it waits on worker F.
  trace("scenario", { name: "lead-interrupt" });
  const leadM = await startThread(c1, "lead-m", { model: "fixture-v2" });
  const mWait = await runTurn(c1, leadM, "SPIKE:m-wait", { detached: true });
  await waitFor(() => command("wf.0"), "worker F's command", 60000);
  const workerF = threadOf("wf.0");
  await waitFor(() => requestsOf(leadM).some((record) => record.action === "wait_agent"), "lead M waits", 30000);
  await delay(1000);
  const mInterrupted = await c1.call("turn/interrupt", { threadId: leadM, turnId: mWait.turnId });
  const mInterruptedAt = Date.now();
  await waitFor(() => completedTurn(c1, mWait.turnId), "lead M's turn settles", 30000);
  await quietly(waitFor(() => stopped(mWait.hooksBefore, workerF), "worker F stops", 40000));
  await delay(5000);
  const mAfter = await runTurn(c1, leadM, "SPIKE:m-after");
  trace("lead-interrupt.outcome", { lead: leadM, worker: workerF, response: mInterrupted.error ?? "ok", interruptedAt: mInterruptedAt, status: completedTurn(c1, mWait.turnId).status,
    leadRequestsBetween: requestsOf(leadM, mInterruptedAt).filter((record) => record.receiptTime < mAfter.startedAt).map((record) => record.receipt),
    after: requestsOf(leadM, mAfter.startedAt).map((record) => record.receipt), shell: shellSummary("wf.0"), hooks: timeline(mWait.hooksBefore) });

  // Q7: lead N, bound to Issue 3 in the third Worktree, loses its last
  // client while worker G works; the daemon unloads N, and the SessionEnd
  // settler of ADR 0086 decides N's run while G still works.
  trace("scenario", { name: "lead-unload" });
  const c2 = await daemonClient("controller-2");
  controllers.push(c2);
  const leadN = await startThread(c2, "lead-n", { model: "fixture-v2", cwd: third });
  const nSpawn = await runTurn(c2, leadN, "SPIKE:n-spawn");
  await waitFor(() => command("wg.0"), "worker G's command", 60000);
  const workerG = threadOf("wg.0");
  view("lead-unload-bound");
  worktreeCheck("lead-unload-bound-fourth", fourth);
  const unsubscribed = await c2.call("thread/unsubscribe", { threadId: leadN });
  c2.close();
  controllers = controllers.filter((client) => client !== c2);
  const leftAt = Date.now();
  const nEnded = () => hooks().slice(nSpawn.hooksBefore).some((record) => record.event === "SessionEnd" && record.payload.session_id === leadN);
  await quietly(waitFor(() => nEnded() || command("wg.3", "end"), "lead N unloads or worker G ends", 150000));
  await delay(2000);
  const loadedWhile = await loadedThreads(c1);
  view("lead-unload-first");
  const settlerSeen = codexProcesses().some(isSettler);
  await settlersDone("lead-unload-settler");
  const settledAt = Date.now();
  const workingAtSettle = !stopped(nSpawn.hooksBefore, workerG);
  view("lead-unload-settled");
  worktreeCheck("lead-unload-settled-fourth", fourth);
  await quietly(waitFor(() => command("wg.3", "end") || stopped(nSpawn.hooksBefore, workerG), "worker G finishes", 150000));
  await quietly(waitFor(() => nEnded(), "lead N unloads", 90000));
  await delay(3000);
  await settlersDone("lead-unload");
  trace("lead-unload.outcome", { lead: leadN, worker: workerG, unsubscribe: unsubscribed.result ?? unsubscribed.error, leftAt, settlerSeen, settledAt, workingAtSettle, loadedWhile,
    loadedAfter: await loadedThreads(c1), shells: ["wg.0", "wg.1", "wg.2", "wg.3"].map(shellSummary), hooks: timeline(nSpawn.hooksBefore),
    workerRequests: requestsOf(workerG).map((record) => record.receipt) });
  view("after-lead-unload");

  // Q7: lead P is deleted while worker H works.
  trace("scenario", { name: "lead-delete" });
  const leadP = await startThread(c1, "lead-p", { model: "fixture-v2" });
  const pSpawn = await runTurn(c1, leadP, "SPIKE:p-spawn");
  await waitFor(() => command("wh.0"), "worker H's command", 60000);
  const workerH = threadOf("wh.0");
  await delay(1000);
  const deleted = await c1.call("thread/delete", { threadId: leadP });
  const deletedAt = Date.now();
  await delay(2000);
  const afterDelete = { lead: await readThread(c1, leadP), worker: await readThread(c1, workerH), loaded: await loadedThreads(c1) };
  view("lead-deleted");
  await quietly(waitFor(() => command("wh.0", "end"), "worker H's command ends", 40000));
  await quietly(waitFor(() => stopped(pSpawn.hooksBefore, workerH), "worker H stops", 10000));
  await delay(3000);
  await settlersDone("lead-delete");
  trace("lead-delete.outcome", { lead: leadP, worker: workerH, response: deleted.error ?? deleted.result ?? null, deletedAt, afterDelete,
    workerRequests: requestsOf(workerH).map((record) => [record.receipt, record.receiptTime - deletedAt]), shell: shellSummary("wh.0"), hooks: timeline(pSpawn.hooksBefore),
    loadedAfter: await loadedThreads(c1) });
  view("after-lead-delete");
  worktreeCheck("after-lead-delete-fourth", fourth);

  trace("scenario", { name: "daemon-stop" });
  for (const client of controllers) client.close();
  controllers = [];
  await codex(["app-server", "daemon", "stop"], "daemon-stop", { timeout: 60000 });
  await quietly(waitFor(() => !existsSync(`/proc/${daemonPid}`), "daemon gone", 20000));
  await settlersDone("daemon stop");
  processes("after-daemon-stop");

  // Dashpot's Event Log for the fixture, metadata only.
  const events = dashpot(["events", "--json"]);
  const eventList = parseJson(events.stdout);
  const fields = ["time", "event.name", "dashpot.process.kind", "dashpot.agent_session.id", "dashpot.worktree.path", "dashpot.issue.id", "dashpot.hook.event",
    "dashpot.outcome.result", "dashpot.agent_session.state", "dashpot.work_store.change", "dashpot.subcommand"];
  trace("dashpot.events", { status: events.status, stderr: events.stderr.slice(0, 300),
    events: (eventList?.events ?? []).filter((event) => event["event.name"] !== "process.start" && event["event.name"] !== "process.end")
      .map((event) => Object.fromEntries(fields.filter((field) => event[field] !== undefined && event[field] !== null).map((field) => [field, event[field]]))) });
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const client of controllers) { try { client.close(); } catch {} }
  if (daemons().length > 0) await codex(["app-server", "daemon", "stop"], "cleanup-stop").catch(() => {});
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
