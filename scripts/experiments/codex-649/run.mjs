// Goal-driven Lead run for Issue #649: drives a pinned Codex CLI against a
// loopback Responses API fixture with an isolated CODEX_HOME, whose daemon
// updater is off, and Dashpot's own Codex hook publisher, in a disposable
// Dashpot Project whose Issues are Local Issue Markdown. Every multi-agent v2
// Lead runs on one `codex app-server --listen` over loopback, a hosting mode
// Dashpot supports, with a thread goal (Codex's `goals` feature, on by
// default). Five Leads:
//
// - L1 creates its goal with `create_goal` on a skill's instruction, spawns
//   two Workers and ends its turn; its goal turns wait in `wait_agent` while
//   the Workers message and finish, run a command once they have, wait at
//   least four more times with no progress and an empty final message, and
//   finally set the goal `blocked`.
// - L2 spawns a Worker with no goal and ends its turn; the Worker messages
//   and finishes; then the client sets a goal, and its goal turns end with
//   text until the third sets it `complete`.
// - L3 creates a goal, spawns a Worker, and its client unsubscribes; the
//   goal keeps it running; the client pauses the goal, the app-server unloads
//   it, the client sets the goal active again while it is unloaded, and then
//   resumes it.
// - L4's goal turns answer with empty messages, and L5's model requests
//   fail, to show which runtime stop blocks each.
//
// The trace records each model request's turn trigger, lineage, markers and
// tools, the app-server's turn and goal notifications, each hook's identity
// fields and Dashpot's publisher outcome, the shells' identity, and
// Dashpot's own published view, metadata only.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--strict] [--codex-source <checkout>]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.166.0";
// Dashpot attributes a fixture process it does not recognise to the first
// harness process above it, so the runner refuses to start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const dashpotCommand = path.join(dashpotBin, "dashpot");
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(dashpotCommand) && existsSync(publisher), `Dashpot's commands are installed in ${dashpotBin}`);

// Outside every Dashpot Project and outside `/tmp`, whose shared Codex
// daemon directory belongs to the operator's own sessions; a short path
// keeps every socket under the length limit.
const root = mkdtempSync(path.join(process.env.SPIKE_ROOT_BASE ?? "/var/tmp", "dashpot-649-codex-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const worktrees = { main: fixture, other };
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, user and host names, this checkout and the
// fixture's root never enter the trace.
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
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");

// The pinned release runs read-only through a fixture-local `codex` on PATH.
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

// The shared daemon directory names an entry by the SHA-256 of its control
// socket path. This fixture starts no daemon; the run records whether an
// entry for its own socket path appeared, and removes only that.
const socketPath = path.join(env.CODEX_HOME, "app-server-control", "app-server-control.sock");
const daemonDirectory = `/tmp/codex-daemon-${os.userInfo().uid}`;
const ownDaemonEntries = [sha(socketPath), `${sha(socketPath)}.lock`];
const ownDaemonEntriesPresent = () => ownDaemonEntries.filter((name) => existsSync(path.join(daemonDirectory, name)));

// The disposable Dashpot Project: three Local Issue Markdown Issues, the
// main working tree and one linked Worktree.
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(fixture, "issues"));
for (const number of [1, 2, 3]) {
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
git("worktree", "add", "-b", "other", other);

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
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` selects the plan: a person's
// prompt, a spawn message, or the goal continuation Codex injects, which
// quotes the goal's objective `SPIKE:<lead>-goal`. The number of tool outputs
// after that item selects the step. Each step becomes one tool call; when the
// plan runs out, the model answers `DONE:<label>`. A Worker's mid-flight
// message is `NOTE:<label>`. A goal turn's plan is chosen once, at its first
// request, from the runner's phase for that Lead.
const commandScript = path.join(here, "command.mjs");
const exec = (options = {}) => ({ exec: options });
const goalObjective = (lead) => `SPIKE:${lead}-goal Every fixture Worker has reported and finished, and the goal's own scenario is done.`;
const phases = { l1: "workers", l3: "run" };
const goalPlans = {
  l1: { workers: [{ wait: 30000 }], observe: [exec({ hold: 8000 })], noprogress: [{ wait: 10000 }], block: [{ goal: "blocked" }] },
  l3: { run: [exec({ hold: 5000 })], finish: [{ goal: "complete" }] },
};
const plans = {
  // L1: the skill asks for a goal; the Lead binds Issue 1, creates the goal,
  // spawns two Workers, and ends its turn.
  "l1-start": [exec({ work: "start-1" }), { create: goalObjective("l1") }, { spawn: ["worker_a", "wa"] }, { spawn: ["worker_b", "wb"] }],
  wa: [exec({ hold: 3000 }), { send: ["/root", "NOTE:wa"] }, exec({ hold: 6000 })],
  wb: [exec({ hold: 15000 })],
  // L2: no goal; a Worker messages and finishes while the Lead is idle.
  "l2-start": [exec({ work: "start-3" }), { spawn: ["worker_c", "wc"] }],
  wc: [exec({ hold: 2000 }), { send: ["/root", "NOTE:wc"] }, exec({ hold: 3000 })],
  // L3: binds Issue 2 in the other Worktree, creates a goal, spawns a Worker.
  "l3-start": [exec({ work: "start-2" }), { create: goalObjective("l3") }, { spawn: ["worker_d", "wd"] }],
  wd: [exec({ hold: 20000 }), exec({ hold: 20000 })],
};
// L2's goal turns by ordinal: two end with text, the third completes.
const l2GoalPlan = (ordinal) => ordinal >= 3 ? [{ goal: "complete" }] : [];
const markerPattern = /(SPIKE|NOTE|DONE):([a-z0-9_-]+)/g;
const continuationText = "Continue working toward the active thread goal";
const skillBody = "FIXTURE-GOAL-SKILL-BODY";
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const turnMetadataKeys = ["request_kind", "session_id", "thread_id", "turn_id", "parent_thread_id", "parent_turn_id", "root_turn_id",
  "subagent_kind", "thread_source", "turn_trigger", "agent_name"];
const modelRequests = [];
const goalTurns = new Map();
const goalTurnPlans = new Map();
const failing = new Set();
const empty = new Set();
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
  const clientMetadata = payload.client_metadata ?? {};
  const blob = parseJson(clientMetadata["x-codex-turn-metadata"] ?? "") ?? {};
  const thread = clientMetadata.thread_id ?? blob.thread_id ?? null;
  const turn = clientMetadata.turn_id ?? blob.turn_id ?? null;
  const metadata = Object.fromEntries(turnMetadataKeys.filter((key) => blob[key] !== undefined).map((key) => [key, blob[key]]));
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
  // Where Codex put the goal continuation and the skill's body: each item's
  // index, type and role, never its text.
  const where = (text) => input.flatMap((item, index) => JSON.stringify(item).includes(text) ? [[index, item.type ?? null, item.role ?? null]] : []);
  const continuation = where(continuationText);
  const skill = { inInput: where(skillBody), inInstructions: String(payload.instructions ?? "").includes(skillBody) };
  const textOf = (item) => [item.content ?? []].flat().map((part) => typeof part === "string" ? part : Object.values(part ?? {}).filter((value) => typeof value === "string" && value !== part.type).join(" ")).join(" | ");
  const agentMessages = input.flatMap((item, index) => item.type === "agent_message"
    ? [[index, item.author ?? null, item.recipient ?? null, [...new Set([...textOf(item).matchAll(markerPattern)].map((match) => match[0]))]]] : []);
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? (tool.tools ?? []).map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsKey = toolNames.join(",");
  const toolsChanged = lastToolsByThread.get(thread) !== toolsKey;
  lastToolsByThread.set(thread, toolsKey);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const goalTools = ["get_goal", "create_goal", "update_goal"].filter((name) => offered(name));
  // A goal turn's ordinal among its thread's goal turns, counted by turn id.
  const goalTurn = metadata.turn_trigger === "goal";
  let ordinal = null;
  if (goalTurn && thread && turn) {
    const seen = goalTurns.get(thread) ?? [];
    if (!seen.includes(turn)) seen.push(turn);
    goalTurns.set(thread, seen);
    ordinal = seen.indexOf(turn) + 1;
  }
  const lead = label?.match(/^(l\d)-goal$/)?.[1] ?? null;
  let plan = label ? plans[label] ?? [] : [];
  let phase = null;
  if (lead && goalTurn) {
    if (!goalTurnPlans.has(turn)) goalTurnPlans.set(turn, lead === "l2" ? { phase: `ordinal-${ordinal}`, plan: l2GoalPlan(ordinal) }
      : goalPlans[lead] ? { phase: phases[lead], plan: goalPlans[lead][phases[lead]] } : { phase: "none", plan: [] });
    ({ phase, plan } = goalTurnPlans.get(turn));
  } else if (lead) {
    plan = [];
  }
  const step = plan[outputs.length] ?? null;
  const stepLabel = `${label}${ordinal ? `-t${ordinal}` : ""}.${outputs.length}`;
  const call = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${stepLabel}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.exec) {
    const { cd = null, hold = 200, work = "-" } = step.exec;
    action = "exec_command";
    item = call("exec_command", { cmd: `${cd ? `cd ${cd} && ` : ""}node ${commandScript} ${stepLabel} ${hold} ${work}`, login: false, yield_time_ms: 120000 });
  } else if (step?.create) {
    action = "create_goal";
    item = call("create_goal", { objective: step.create });
  } else if (step?.goal) {
    action = "update_goal";
    item = call("update_goal", { status: step.goal });
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = call("spawn_agent", { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" });
  } else if (step?.send) {
    const [target, text] = step.send;
    action = "send_message";
    item = call("send_message", { target, message: text });
  } else if (step?.wait) {
    action = "wait_agent";
    item = call("wait_agent", { timeout_ms: step.wait });
  }
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const lastOutput = latestOutput ? clean(String(typeof latestOutput.output === "string" ? latestOutput.output : JSON.stringify(latestOutput.output ?? null))).slice(0, 400) : null;
  // L1's no-progress goal turns end with an empty message after their wait,
  // as L4's end with one and nothing else.
  const emptyFinal = (empty.has(thread) && goalTurn) || (lead === "l1" && phase === "noprogress" && !item);
  const response = failing.has(thread) ? "error" : emptyFinal ? "empty" : item ? "tool" : "text";
  const request = trace("model.request", { thread, turn, metadata, label, lead, phase, goalTurn, ordinal, step: outputs.length, inputItems: input.length, directiveAt,
    markers, continuation, skill, agentMessages, goalTools, action, missing: Boolean(step && !item), lastOutput, response,
    tools: toolsChanged ? toolNames : undefined, tail: input.slice(-3).map((entry) => [entry.type ?? null, entry.role ?? null]) });
  modelRequests.push(request);
  if (response === "error") {
    // A non-retryable request error, as an invalid request would be.
    res.writeHead(400, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "invalid_request_error", message: "fixture refuses this request", code: "fixture_refusal" } }));
    return;
  }
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  const text = response === "empty" ? "" : label ? `DONE:${label}` : "Fixture complete.";
  sse(res, { type: "response.output_item.done", item: response === "tool" ? item : { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text }] } });
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

// The model catalog names `fixture-v2` only, a copy of a bundled entry
// without a tool set or code mode, declaring multi-agent v2.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

// A fixture skill where `dashpot integrate codex` installs skills, whose
// body asks for a goal, as a Lead skill would.
const skillsHome = path.join(env.HOME, ".agents", "skills");
mkdirSync(path.join(skillsHome, "fixture-goal-lead"), { recursive: true });
writeFileSync(path.join(skillsHome, "fixture-goal-lead", "SKILL.md"), `---\nname: fixture-goal-lead\ndescription: Fixture Lead skill that asks for a thread goal.\n---\n\n# fixture-goal-lead\n\n${skillBody}: create a thread goal whose objective is the Arc's end, then launch the Workers.\n`);

const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = ${JSON.stringify(catalogPath)}
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"
check_for_update_on_startup = false
suppress_unstable_features_warning = true

[features]
hooks = true
multi_agent = true
multi_agent_v2 = true
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
${Object.values(worktrees).map((dir) => `\n[projects.${JSON.stringify(dir)}]\ntrust_level = "trusted"\n`).join("")}`);
// The fixture daemon's updater stays off, though no scenario starts the
// daemon: installing a release could replace the pinned binary mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name) || Number(name) === process.pid) continue;
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const brief = (entry) => [entry.pid, entry.ppid, entry.comm, clean(entry.cmdline).slice(0, 200)];
const isSettler = (entry) => / -m dashpot\.hook settle /.test(entry.cmdline);
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const settlersDone = async (label) => {
  await delay(500);
  await quietly(waitFor(() => !codexProcesses().some(isSettler), `${label}: settlers exit`, 20000));
};
const requestsOf = (thread, after = 0) => modelRequests.filter((record) => record.thread === thread && record.receiptTime > after);
const stopped = (agent) => hooks().some((record) => record.event === "SubagentStop" && record.payload.agent_id === agent);
const threadOf = (label) => command(label)?.env.CODEX_THREAD_ID ?? null;
const sessionEnded = (thread) => hooks().some((record) => record.event === "SessionEnd" && record.payload.session_id === thread);

// Dashpot's published view of the fixture: the Agent Runs and diagnostics.
const view = (label, extra = {}) => {
  const ran = dashpot(["--compact-json"]);
  const parsed = parseJson(ran.stdout);
  const runs = (parsed?.agentRuns ?? []).map(({ id, harness, processOrSession, state, issueId, workingDirectory, turnStartedAt, orphaned }) =>
    ({ id, harness, processOrSession, state, issueId, workingDirectory, turnStartedAt, orphaned }));
  return trace("dashpot.view", { label, status: ran.status, stderr: ran.stderr.slice(0, 400), agentRuns: runs,
    diagnostics: (parsed?.diagnostics ?? []).map((diagnostic) => ({ code: diagnostic.code, severity: diagnostic.severity, message: String(diagnostic.message ?? "").slice(0, 300) })), ...extra });
};

const freePort = async () => {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = probe.address().port;
  probe.close();
  return port;
};
// A JSON-RPC client on the app-server's loopback WebSocket. Turn, thread and
// goal notifications are kept with their metadata only.
const notifications = [];
const rpcClient = async (name, port) => {
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  let nextId = 0;
  const pending = new Map();
  socket.addEventListener("message", (message) => {
    const parsed = parseJson(String(message.data));
    if (parsed === null) return;
    if (parsed.id !== undefined && parsed.method === undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.id !== undefined && parsed.method) {
      // Any server request, which an approval would be, is recorded and declined.
      trace("server.request", { client: name, method: parsed.method, keys: Object.keys(parsed.params ?? {}).sort() });
      socket.send(JSON.stringify({ id: parsed.id, result: { decision: "decline" } }));
      return;
    }
    const method = parsed.method ?? "";
    if (!/^(turn\/(started|completed)|thread\/(goal\/(updated|cleared)|status\/changed|closed|started))$/.test(method)) return;
    const params = parsed.params ?? {};
    const entry = { client: name, method, thread: params.threadId ?? params.thread?.id ?? params.goal?.threadId ?? null, turn: params.turn?.id ?? params.turnId ?? null,
      status: params.turn?.status ?? null, receivedAt: Date.now() };
    if (params.turn?.error) entry.turnError = { keys: Object.keys(params.turn.error), codexErrorInfo: params.turn.error.codexErrorInfo ?? null };
    if (params.goal) entry.goal = { status: params.goal.status, objectiveLabel: String(params.goal.objective ?? "").match(/SPIKE:[a-z0-9-]+/)?.[0] ?? null };
    if (method === "thread/status/changed") entry.threadStatus = params.status ?? null;
    notifications.push(entry);
    trace("rpc.event", entry);
  });
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-649-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, error: init.error ?? null });
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, close: () => socket.close() };
};
const completedTurn = (turnId) => notifications.find((entry) => entry.method === "turn/completed" && entry.turn === turnId);
const runTurn = async (client, threadId, text, timeout = 90000) => {
  const startedAt = Date.now();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  await waitFor(() => completedTurn(turnId), `turn ${text} completed`, timeout);
  trace("turn.completed", { threadId, turnId, status: completedTurn(turnId).status });
  return { turnId, startedAt, completedAt: completedTurn(turnId).receivedAt };
};
const startThread = async (client, name, params) => {
  const started = await client.call("thread/start", { cwd: fixture, model: "fixture-v2", ...params });
  const thread = started.result?.thread;
  trace("thread.start", { name, cwd: params.cwd ?? fixture, thread: thread?.id ?? null, error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
const goalOf = async (client, label, threadId) => {
  const got = await client.call("thread/goal/get", { threadId });
  const goal = got.result?.goal ?? null;
  return trace("goal.get", { label, threadId, goal: goal && { status: goal.status, objectiveLabel: goal.objective.match(/SPIKE:[a-z0-9-]+/)?.[0] ?? null }, error: got.error ?? null });
};
const setGoal = async (client, label, threadId, params) => {
  const set = await client.call("thread/goal/set", { threadId, origin: "user", ...params });
  return trace("goal.set", { label, threadId, params, goal: set.result?.goal ? { status: set.result.goal.status } : null, error: set.error ?? null });
};
const loaded = async (client) => (await client.call("thread/loaded/list", {})).result?.data ?? [];
const goalStatus = (thread) => notifications.filter((entry) => entry.method === "thread/goal/updated" && entry.thread === thread).at(-1)?.goal?.status ?? null;
const leadTurns = (thread) => notifications.filter((entry) => entry.thread === thread && entry.method === "turn/started").map((entry) => entry.turn);
// Hooks in a window, as [event, session, agent, turn, time].
const timeline = (thread, since = 0) => hooks().filter((record) => record.receiptTime >= since && (record.payload.session_id === thread))
  .map((record) => [record.event, record.payload.agent_id ?? null, record.payload.turn_id ?? null, record.receiptTime]);

const scripts = ["run.mjs", "verify.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "deferred_end.py", "work_reconciliation.py", "hook_records.py", "work.py", "hook_scan.py", "processes.py"].map((file) => `src/dashpot/sessions/${file}`);
let server = null;
let client = null;
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", path.relative(checkout, here)], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, expectedVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(home, "~"), binarySHA256: sha(readFileSync(binary)),
    dashpot: { version: dashpot(["--version"]).stdout.trim(), head, experimentDirty: dirty }, worktrees, hookEvents,
    fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2" }, config: readFileSync(configPath, "utf8"),
    updater: JSON.parse(readFileSync(daemonSettingsPath, "utf8")), ownDaemonEntriesBefore: ownDaemonEntriesPresent(),
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, sha(readFileSync(file))])) });

  // Setup: trust the fixture hooks through the ledger on a stdio app-server.
  trace("scenario", { name: "hook-trust" });
  {
    const trust = spawn("codex", ["app-server"], { cwd: fixture, env, stdio: ["pipe", "pipe", "pipe"] });
    const replies = new Map();
    readline.createInterface({ input: trust.stdout }).on("line", (line) => { const message = parseJson(line); if (message?.id !== undefined) replies.get(message.id)?.(message); });
    trust.stderr.on("data", () => {});
    let id = 0;
    const call = (method, params) => new Promise((resolve) => { const callId = ++id; replies.set(callId, resolve); trust.stdin.write(JSON.stringify({ id: callId, method, params }) + "\n"); });
    await call("initialize", { clientInfo: { name: "fixture-649-trust", version: "0" }, capabilities: { experimentalApi: true } });
    trust.stdin.write(JSON.stringify({ method: "initialized", params: {} }) + "\n");
    const entries = (await call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
    assert.equal(entries.length, hookEvents.length, "fixture hooks listed");
    appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
    const relisted = (await call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
    trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
    assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
    trust.stdin.end();
    await once(trust, "exit");
  }

  // The Leads' Host Process: one app-server on a loopback WebSocket.
  trace("scenario", { name: "server" });
  const port = await freePort();
  server = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let banner = "";
  server.stderr.on("data", (chunk) => { banner += chunk; appendFileSync(path.join(root, "app-server.stderr"), chunk); });
  server.stdout.on("data", () => {});
  await waitFor(() => banner.includes("listening on"), "app-server listening", 30000);
  trace("server.start", { pid: server.pid });
  client = await rpcClient("controller", port);

  // L1: a goal the Lead creates on a skill's instruction, with Workers.
  trace("scenario", { name: "l1-skill-goal" });
  const l1 = await startThread(client, "l1", {});
  const l1Start = await runTurn(client, l1, "$fixture-goal-lead SPIKE:l1-start");
  const workerA = threadOf("wa.0") ?? (await waitFor(() => threadOf("wa.0"), "worker A's first command", 30000), threadOf("wa.0"));
  await waitFor(() => threadOf("wb.0"), "worker B's first command", 30000);
  const workerB = threadOf("wb.0");
  await waitFor(() => leadTurns(l1).length >= 2, "L1's first goal turn", 30000);
  await delay(1500);
  view("l1-goal-turn-workers-running");
  await goalOf(client, "l1-workers-running", l1);
  await waitFor(() => command("wa.2"), "worker A's command after its message", 60000);
  await waitFor(() => stopped(workerA) && stopped(workerB), "both L1 Workers stop", 90000);
  phases.l1 = "observe";
  const observeSince = Date.now();
  await waitFor(() => commands().some((record) => record.phase === "start" && record.label.startsWith("l1-goal-t") && record.receiptTime > observeSince), "L1's observing goal turn runs its command", 90000);
  await delay(2500);
  view("l1-goal-turn-after-workers");
  const observeCommand = commands().find((record) => record.phase === "start" && record.label.startsWith("l1-goal-t") && record.receiptTime > observeSince);
  await waitFor(() => command(observeCommand.label, "end"), "L1's observing command ends", 30000);
  phases.l1 = "noprogress";
  const noProgressSince = Date.now();
  const noProgressTurns = () => [...goalTurnPlans.entries()].filter(([turnId, entry]) => entry.phase === "noprogress" && completedTurn(turnId)).length;
  await waitFor(() => noProgressTurns() >= 4, "four L1 goal turns with no progress", 120000);
  await goalOf(client, "l1-after-no-progress", l1);
  phases.l1 = "block";
  await waitFor(() => goalStatus(l1) === "blocked", "L1's goal blocked", 60000);
  const blockedAt = Date.now();
  await delay(5000);
  view("l1-blocked-idle");
  await goalOf(client, "l1-blocked", l1);
  trace("l1.outcome", { lead: l1, workerA, workerB, startTurn: l1Start.turnId, startCompletedAt: l1Start.completedAt, observeSince, noProgressSince, blockedAt,
    turns: leadTurns(l1), turnsAfterBlocked: notifications.filter((entry) => entry.thread === l1 && entry.method === "turn/started" && entry.receivedAt > blockedAt).length,
    hooks: timeline(l1), workerHooks: hooks().filter((record) => [workerA, workerB].includes(record.payload.agent_id)).map((record) => [record.event, record.payload.agent_id, record.receiptTime]) });

  // L2: a Worker reports to an idle Lead with no goal; then the client sets one.
  trace("scenario", { name: "l2-client-goal" });
  const l2 = await startThread(client, "l2", {});
  const l2Start = await runTurn(client, l2, "SPIKE:l2-start");
  await waitFor(() => threadOf("wc.0"), "worker C's first command", 30000);
  const workerC = threadOf("wc.0");
  await waitFor(() => stopped(workerC), "worker C stops", 60000);
  await delay(5000);
  const idleRequests = requestsOf(l2, l2Start.completedAt).map((record) => record.receipt);
  const idleTurns = notifications.filter((entry) => entry.thread === l2 && entry.method === "turn/started" && entry.receivedAt > l2Start.completedAt).length;
  view("l2-idle-no-goal");
  const goalSetAt = Date.now();
  await setGoal(client, "l2-set-active", l2, { objective: goalObjective("l2"), status: "active" });
  await waitFor(() => goalStatus(l2) === "complete", "L2's goal complete", 60000);
  await delay(3000);
  await goalOf(client, "l2-complete", l2);
  view("l2-goal-complete");
  trace("l2.outcome", { lead: l2, workerC, startTurn: l2Start.turnId, startCompletedAt: l2Start.completedAt, idleRequests, idleTurns, goalSetAt,
    turns: leadTurns(l2), hooks: timeline(l2) });

  // L3 (#492): an unsubscribed Lead with an active goal, paused, unloaded,
  // set active while unloaded, and resumed.
  trace("scenario", { name: "l3-unload" });
  const l3 = await startThread(client, "l3", { cwd: other });
  const l3Start = await runTurn(client, l3, "SPIKE:l3-start");
  await waitFor(() => threadOf("wd.0"), "worker D's first command", 30000);
  const workerD = threadOf("wd.0");
  const unsubscribed = await client.call("thread/unsubscribe", { threadId: l3 });
  const leftAt = Date.now();
  trace("thread.unsubscribe", { threadId: l3, result: unsubscribed.result ?? null, error: unsubscribed.error ?? null });
  const loadedPolls = [];
  while (Date.now() - leftAt < 80000) {
    await delay(10000);
    loadedPolls.push([Date.now() - leftAt, (await loaded(client)).includes(l3), requestsOf(l3, leftAt).filter((record) => record.goalTurn).length, sessionEnded(l3)]);
  }
  view("l3-unsubscribed-goal-active");
  const pausedAt = Date.now();
  await setGoal(client, "l3-set-paused", l3, { status: "paused" });
  await quietly(waitFor(() => sessionEnded(l3), "L3 unloads", 150000));
  const unloadedAt = Date.now();
  await delay(3000);
  await settlersDone("l3 unload");
  await delay(12000);
  await settlersDone("l3 unload settled");
  const loadedAfterUnload = (await loaded(client)).includes(l3);
  view("l3-unloaded");
  await quietly(waitFor(() => stopped(workerD), "worker D stops", 60000));
  const reactivatedAt = Date.now();
  await setGoal(client, "l3-set-active-unloaded", l3, { status: "active" });
  await delay(15000);
  const afterReactivate = { requests: requestsOf(l3, reactivatedAt).length, loaded: (await loaded(client)).includes(l3), sessionStarts: hooks().filter((record) => record.event === "SessionStart" && record.payload.session_id === l3 && record.receiptTime > reactivatedAt).length };
  await goalOf(client, "l3-unloaded-reactivated", l3);
  phases.l3 = "finish";
  const resumedAt = Date.now();
  const resumed = await client.call("thread/resume", { threadId: l3 });
  trace("thread.resume", { threadId: l3, thread: resumed.result?.thread?.id ?? null, error: resumed.error ?? null });
  await quietly(waitFor(() => goalStatus(l3) === "complete", "L3's resumed goal completes", 60000));
  await delay(3000);
  await goalOf(client, "l3-resumed", l3);
  view("l3-resumed");
  trace("l3.outcome", { lead: l3, workerD, startTurn: l3Start.turnId, leftAt, loadedPolls, pausedAt, unloadedAt, loadedAfterUnload, reactivatedAt, afterReactivate, resumedAt,
    goalTurnsWhileUnsubscribed: requestsOf(l3, leftAt).filter((record) => record.goalTurn && record.receiptTime < pausedAt).map((record) => record.turn).filter((turn, index, all) => all.indexOf(turn) === index).length,
    requestsAfterResume: requestsOf(l3, resumedAt).map((record) => [record.receipt, record.goalTurn, record.action]), hooks: timeline(l3) });

  // L4 and L5: the runtime's own stops.
  trace("scenario", { name: "l4-empty-responses" });
  const l4 = await startThread(client, "l4", {});
  empty.add(l4);
  await setGoal(client, "l4-set-active", l4, { objective: goalObjective("l4"), status: "active" });
  await quietly(waitFor(() => goalStatus(l4) === "blocked", "L4's goal blocked", 60000));
  await delay(3000);
  await goalOf(client, "l4-after", l4);
  trace("l4.outcome", { lead: l4, turns: leadTurns(l4), goalTurnRequests: requestsOf(l4).filter((record) => record.goalTurn).length, hooks: timeline(l4) });

  trace("scenario", { name: "l5-turn-error" });
  const l5 = await startThread(client, "l5", {});
  failing.add(l5);
  await setGoal(client, "l5-set-active", l5, { objective: goalObjective("l5"), status: "active" });
  await quietly(waitFor(() => goalStatus(l5) === "blocked", "L5's goal blocked", 60000));
  await delay(3000);
  await goalOf(client, "l5-after", l5);
  trace("l5.outcome", { lead: l5, turns: leadTurns(l5), requests: requestsOf(l5).length, hooks: timeline(l5) });

  trace("scenario", { name: "server-stop" });
  client.close();
  client = null;
  server.kill("SIGTERM");
  await once(server, "exit");
  server = null;
  await settlersDone("server stop");
  console.log(`All scenarios completed: ${root}`);
} finally {
  try { client?.close(); } catch {}
  if (server) { server.kill("SIGTERM"); await delay(2000); }
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: brief(entry) });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const ownAfter = ownDaemonEntriesPresent();
  for (const name of ownAfter) { try { rmSync(path.join(daemonDirectory, name), { force: true }); } catch {} }
  trace("summary", { processes: codexProcesses().map(brief), ownDaemonEntriesAfter: ownAfter, ownDaemonEntriesRemoved: ownAfter });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
