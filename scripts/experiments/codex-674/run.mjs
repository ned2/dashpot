// Follow-up hook run for Issue #674: drives a pinned Codex CLI against a
// loopback Responses API fixture, with an isolated CODEX_HOME whose daemon
// updater is off, and records what a lead's `followup_task` (multi-agent v2)
// and `send_input` (v1) publish to hooks: `PreToolUse` and `PostToolUse` on
// the lead, each subscribed once without a matcher and once per candidate
// matcher, beside every subscription `dashpot integrate codex` installs:
// the lifecycle events and its matched `PostToolUse` (ADR 0161), which reach
// Dashpot's real publisher. After each event the publisher handled, the
// trace records the session's listing in Dashpot's store.
//
// Each lead runs in a `codex app-server` over stdio; no daemon is started.
// The v2 lead runs with `agents.max_threads` 1, so Codex holds one worker
// loaded and runs one worker turn at a time. It follows up a resident
// worker by absolute path, relative path and thread ID; one Codex evicted,
// by path and by thread ID; an evicted one while another runs, into the
// running-turn limit; one mid-turn; an unknown path and an unknown thread
// ID; and, after the app-server restarts and the lead is resumed, a worker
// restored from disk, by path and by thread ID. The v1 lead resumes its
// worker with `send_input`, then sends to an unknown ID, a malformed ID and
// a worker it closed. The trace records hook payload keys, tool names, call
// IDs, thread IDs and agent paths, Codex's tool replies to the lead (status
// text Codex composes, never prompt text), loaded threads, and Dashpot's
// session state and listed Sub-agents; never a prompt or a message.
//
//   node run.mjs <absolute codex binary> [expected version] [dashpot bin dir]
//   node verify.mjs <trace.jsonl> [expected version] [--codex-source <checkout>]
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
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
// A fixture below a harness session would join that session's process tree,
// and Dashpot would attach the fixture's hooks to it.
const runnerAncestry = ancestry(process.ppid, 64, 1);
const isHarness = (entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline);
const harnessAbove = runnerAncestry.find(isHarness);
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);
const dashpotBin = path.resolve(process.argv[4] ?? path.join(checkout, ".venv", "bin"));
const publisher = path.join(dashpotBin, "dashpot-codex-hook");
assert(existsSync(publisher), `Dashpot's Codex publisher is installed in ${dashpotBin}`);

// Outside every Dashpot Project and outside `/tmp`, whose shared Codex
// daemon directory belongs to the operator's own sessions.
const root = mkdtempSync(path.join("/var/tmp", "dashpot-codex-674-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
// The operator's home directory, user name, host name, this checkout and the
// fixture's root never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const userName = new RegExp(`\\b${os.userInfo().username}\\b`, "g");
const clean = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(path.basename(root), "<fixture>").replaceAll(here, "$EXPERIMENT")
  .replaceAll(checkout, "$CHECKOUT").replaceAll(home, "~").replace(hostName, "<host>").replace(userName, "<user>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, clean(JSON.stringify(record)) + "\n");
  return record;
};

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
  // Ancestry walks from hooks end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) {
  mkdirSync(dir, { recursive: true });
}
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);
execFileSync("git", ["-C", fixture, "init", "--quiet", "--initial-branch=main"], { env });

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

// A sub-agent hook names the worker's transcript. Its first line, Codex's
// session metadata, says which thread it is and which agent path the lead
// spawned it at; nothing else in the transcript is read.
const transcriptMeta = (file, agentId) => {
  if (!file || !existsSync(file)) return null;
  const first = parseJson(readFileSync(file, "utf8").split("\n")[0]);
  const meta = first?.type === "session_meta" ? first.payload ?? {} : {};
  const spawn = meta.source?.subagent?.thread_spawn ?? null;
  return { type: first?.type ?? null, id: meta.id ?? null, nameHasAgentId: Boolean(agentId && path.basename(file).includes(agentId)),
    threadSpawn: spawn && { parent_thread_id: spawn.parent_thread_id ?? null, depth: spawn.depth ?? null, agent_path: spawn.agent_path ?? null,
      agent_role: spawn.agent_role ?? null, keys: Object.keys(spawn) } };
};
// Each record in Dashpot's global hook-record store, where the fixture's
// sessions land since its repository is no configured Project: the session,
// its state and the Sub-agents it lists, with the Host Process tags' keys.
const dashpotStore = () => {
  const store = path.join(env.XDG_STATE_HOME, "dashpot", "runs");
  if (!existsSync(store)) return [];
  return readdirSync(store, { recursive: true }).filter((name) => String(name).endsWith(".json")).sort().map((name) => {
    const stored = parseJson(readFileSync(path.join(store, String(name)), "utf8")) ?? {};
    return { sessionId: stored.sessionId ?? null, state: stored.state ?? null, lastEvent: stored.event ?? null,
      liveSubagents: stored.liveSubagents ?? null, subagentProcesses: Object.keys(stored.subagentProcesses ?? {}),
      followUpStored: "followUp" in stored };
  });
};
const sink = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const received = await body(req);
  if (url.pathname === "/hook") {
    const describeTranscript = (file) => file && { underCodexHome: file.startsWith(env.CODEX_HOME), meta: transcriptMeta(file, received.payload?.agent_id) };
    const { transcriptPath, agentTranscriptPath, ...kept } = received;
    // The hook posts once the publisher has returned, so the store holds
    // this event's effect, and perhaps a concurrent hook's.
    const store = received.publisher ? dashpotStore() : undefined;
    trace("hook", { ...kept, transcript: describeTranscript(transcriptPath), agentTranscript: describeTranscript(agentTranscriptPath), dashpotStore: store, scenario });
  } else {
    trace("command", { ...received, scenario });
  }
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` (a person's prompt, a spawn
// message, or a follow-up task) selects the plan `plans[label]`; the number of
// tool outputs after that item selects the step. Each step becomes one tool
// call, and a step that is a function is resolved when it is due, so it can
// name a thread ID the run learned earlier. When the plan runs out, the
// model answers `DONE:<label>`.
const commandScript = path.join(here, "command.mjs");
const learned = {};
const unknownId = randomUUID();
const plans = {
  // v2: worker A runs once and finishes.
  "v2-spawn": [{ call: "spawn_agent", args: { message: "SPIKE:wa", task_name: "worker_a", fork_turns: "none" } }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  wa: [{ exec: 300 }],
  // Follow-ups to resident A, by absolute path, relative path and thread ID.
  "v2-path": [{ call: "followup_task", args: { target: "/root/worker_a", message: "SPIKE:wa-path" } }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wa-path": [{ exec: 1500 }],
  "v2-relative": [{ call: "followup_task", args: { target: "worker_a", message: "SPIKE:wa-relative" } }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wa-relative": [{ exec: 300 }],
  "v2-id": [() => ({ call: "followup_task", args: { target: learned.workerA, message: "SPIKE:wa-id" } }), { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wa-id": [{ exec: 300 }],
  // Worker B takes the only slot, evicting finished A; a follow-up reloads A.
  "v2-evict": [{ call: "spawn_agent", args: { message: "SPIKE:wb", task_name: "worker_b", fork_turns: "none" } }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  wb: [{ exec: 300 }],
  "v2-evicted": [{ call: "followup_task", args: { target: "/root/worker_a", message: "SPIKE:wa-evicted" } }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wa-evicted": [{ exec: 300 }],
  // While A runs the only worker turn, a follow-up to evicted B meets the
  // running-turn limit, and a second follow-up reaches A itself mid-turn.
  "v2-limit": [{ call: "followup_task", args: { target: "/root/worker_a", message: "SPIKE:wa-long" } },
    { call: "followup_task", args: { target: "/root/worker_b", message: "SPIKE:wb-limit" } },
    { call: "followup_task", args: { target: "/root/worker_a", message: "SPIKE:wa-busy" } },
    { call: "list_agents", args: {} }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wa-long": [{ exec: 5000 }],
  "wb-limit": [{ exec: 300 }],
  "wa-busy": [{ exec: 300 }],
  // Targets Codex cannot resolve.
  // B, evicted again by A's turns, is reloaded by its thread ID.
  "v2-evicted-id": [() => ({ call: "followup_task", args: { target: learned.workerB, message: "SPIKE:wb-evicted-id" } }), { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wb-evicted-id": [{ exec: 300 }],
  "v2-unknown": [{ call: "followup_task", args: { target: "/root/nobody", message: "SPIKE:nobody" } },
    { call: "followup_task", args: { target: unknownId, message: "SPIKE:nobody" } }, { call: "list_agents", args: {} }],
  // After the app-server restarts: B, evicted and on disk only, is restored
  // by path; then A, on disk only too, by its thread ID.
  "v2-restored": [{ call: "followup_task", args: { target: "/root/worker_b", message: "SPIKE:wb-restored" } }, { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wb-restored": [{ exec: 300 }],
  "v2-restored-id": [() => ({ call: "followup_task", args: { target: learned.workerA, message: "SPIKE:wa-restored-id" } }), { call: "wait_agent", args: { timeout_ms: 30000 } }],
  "wa-restored-id": [{ exec: 300 }],
  // v1: worker V runs once; `send_input` resumes it by ID.
  "v1-spawn": [{ call: "spawn_agent", args: { message: "SPIKE:wv" } }, ({ lastOutput }) => {
    learned.workerVFromSpawn = parseJson(lastOutput)?.agent_id ?? null;
    return { call: "wait_agent", args: { targets: [learned.workerVFromSpawn], timeout_ms: 30000 } };
  }],
  wv: [{ exec: 300 }],
  "v1-send": [() => ({ call: "send_input", args: { target: learned.workerV, message: "SPIKE:wv-send" } }),
    () => ({ call: "wait_agent", args: { targets: [learned.workerV], timeout_ms: 30000 } })],
  "wv-send": [{ exec: 1500 }],
  "v1-unknown": [{ call: "send_input", args: { target: unknownId, message: "SPIKE:nobody" } }, { call: "send_input", args: { target: "worker_v", message: "SPIKE:nobody" } }],
  "v1-closed": [() => ({ call: "close_agent", args: { target: learned.workerV } }), () => ({ call: "send_input", args: { target: learned.workerV, message: "SPIKE:wv-closed" } })],
  "wv-closed": [{ exec: 300 }],
};
const markerPattern = /SPIKE:([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
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
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)];
    if (found.length) { directiveAt = index; label = found.at(-1)[1]; }
  });
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsChanged = lastToolsByThread.get(thread) !== toolNames.join(",");
  lastToolsByThread.set(thread, toolNames.join(","));
  const plan = label ? plans[label] ?? [] : [];
  // The reply to the previous call: the text Codex composed for the lead,
  // or, for a call the tool refused, its error.
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  // A worker's final message, which `wait_agent` and `list_agents` relay, is
  // the fixture model's own text, so the trace replaces it.
  const lastOutput = latestOutput ? String(latestOutput.output ?? "").replace(/DONE:[a-z0-9_-]+/g, "<worker reply>") : null;
  let step = plan[outputs.length] ?? null;
  if (typeof step === "function") step = step({ lastOutput });
  const call = (name, args) => {
    const tool = tools.find(([, toolName]) => toolName === name);
    return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  if (step?.exec !== undefined) item = call("exec_command", { cmd: `node ${commandScript} ${label}.${outputs.length} ${step.exec}`, login: false, yield_time_ms: 120000 });
  else if (step?.call) item = call(step.call, step.args);
  const request = trace("model.request", { thread, label, step: outputs.length, action: step?.call ?? (step?.exec !== undefined ? "exec_command" : null),
    callId: item?.call_id ?? null, target: step?.args?.target ?? null, missing: Boolean(step && !item),
    lastOutput: lastOutput?.slice(0, 600) ?? null, lastCallId: latestOutput?.call_id ?? null,
    tools: toolsChanged ? toolNames : undefined, parentThread: req.headers["x-codex-parent-thread-id"] ?? null });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// Every subscription `dashpot integrate codex` installs, as its example
// spells them, reaches Dashpot's publisher: a lifecycle event tagged
// `lifecycle`, a matched one `dashpot:<matcher>`. Each tool event is also
// subscribed without a matcher, and once for each candidate matcher, and
// those are recorded only. Codex treats a matcher of letters, digits, `_`
// and `|` as exact names, and anything else as a regular expression.
const dashpotHooks = JSON.parse(readFileSync(path.join(checkout, "examples", "codex-hooks.json"), "utf8")).hooks;
const lifecycleEvents = Object.keys(dashpotHooks).filter((event) => dashpotHooks[event].every((group) => !group.matcher));
const dashpotMatched = Object.entries(dashpotHooks).flatMap(([event, groups]) => groups.filter((group) => group.matcher).map((group) => [event, group.matcher]));
const matchers = ["followup_task", "send_input", "collaborationfollowup_task", "multi_agent_v1send_input", "followup_task$|send_input$"];
const hookCommand = (tag) => `${process.execPath} ${path.join(here, "hook.mjs")} '${tag}'`;
const handler = (tag) => ({ type: "command", command: hookCommand(tag), timeout: 15 });
const toolGroups = (event) => [{ hooks: [handler("all")] }, ...matchers.map((matcher) => ({ matcher, hooks: [handler(`matcher:${matcher}`)] })),
  ...dashpotMatched.filter(([matched]) => matched === event).map(([, matcher]) => ({ matcher, hooks: [handler(`dashpot:${matcher}`)] }))];
const hooksDocument = { hooks: {
  ...Object.fromEntries(lifecycleEvents.map((event) => [event, [{ hooks: [handler("lifecycle")] }]])),
  PreToolUse: toolGroups("PreToolUse"),
  PostToolUse: toolGroups("PostToolUse"),
} };
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify(hooksDocument, null, 2));

// The model catalog names `fixture-v2` and `fixture-v1`, copies of a bundled
// entry without a tool set or code mode, declaring each multi-agent version.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [
  { ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false },
  // Without tool search, Codex offers the v1 tools directly rather than
  // deferring them behind `tool_search`.
  { ...base, slug: "fixture-v1", display_name: "Fixture v1", multi_agent_version: "v1", prefer_websockets: false, supports_search_tool: false },
] }, null, 2));
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

[projects.${JSON.stringify(fixture)}]
trust_level = "trusted"
`);
// The fixture daemon's updater stays off, though no scenario starts the
// daemon: installing a release could replace the pinned binary mid-run.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));
// The shared daemon directory is only counted, never written.
const sharedDaemonDir = `/tmp/codex-daemon-${os.userInfo().uid}`;
const sharedEntries = () => { try { return readdirSync(sharedDaemonDir).sort(); } catch { return []; } };
const sharedBefore = sharedEntries();

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
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);

// One `codex app-server` over stdio. Every server request is declined.
let scenario = "setup";
const servers = [];
const appServer = async (name, overrides = []) => {
  const child = spawn("codex", [...overrides.flatMap((override) => ["-c", override]), "app-server"], { cwd: fixture, env, stdio: ["pipe", "pipe", "pipe"] });
  servers.push(child);
  let next = 0;
  const pending = new Map();
  const notifications = [];
  child.stderr.on("data", (chunk) => appendFileSync(path.join(root, `app-server-${name}.stderr`), chunk));
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    const message = parseJson(line);
    if (!message) return;
    if (message.method && message.id !== undefined) {
      trace("server.request", { server: name, method: message.method });
      child.stdin.write(JSON.stringify({ id: message.id, result: { decision: "decline" } }) + "\n");
    } else if (message.method) {
      const params = message.params ?? {};
      const entry = { method: message.method, thread: params.threadId ?? params.thread?.id ?? null, turn: params.turn?.id ?? null,
        status: params.turn?.status ?? params.status ?? null, receivedAt: Date.now() };
      notifications.push(entry);
      if (/^(turn|thread)\//.test(message.method)) trace("rpc.event", { server: name, scenario, ...entry });
      // The lead's own record of each collaboration call: its tool, status
      // and receivers, never its prompt.
      const item = params.item;
      if (/^item\/(started|completed)$/.test(message.method) && item?.type === "collabAgentToolCall") {
        trace("rpc.collab", { server: name, scenario, method: message.method, thread: entry.thread, id: item.id, tool: item.tool, status: item.status,
          sender: item.senderThreadId ?? null, receivers: item.receiverThreadIds ?? null });
      }
    } else if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
  });
  const call = async (method, params = {}) => {
    const id = ++next;
    const response = new Promise((resolve) => pending.set(id, resolve));
    child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    const result = await Promise.race([response, delay(30000).then(() => ({ error: { message: `${method} timed out` } }))]);
    trace("rpc.result", { server: name, method, error: result.error ?? null, thread: result.result?.thread?.id ?? null, turn: result.result?.turn?.id ?? null });
    return result;
  };
  const init = await call("initialize", { clientInfo: { name: "fixture-674", version: "0" }, capabilities: { experimentalApi: true } });
  assert(init.result, `${name} initialized: ${JSON.stringify(init.error)}`);
  child.stdin.write(JSON.stringify({ method: "initialized" }) + "\n");
  const stop = async () => {
    child.stdin.end();
    child.kill("SIGTERM");
    if (child.exitCode === null && child.signalCode === null) await once(child, "exit");
  };
  return { name, child, call, notifications, stop };
};

const hooks = () => records.filter((record) => record.kind === "hook");
const command = (label, phase = "start") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const stoppedSince = (since, agent) => hooks().some((record) => record.receiptTime > since && record.event === "SubagentStop" && record.payload.agent_id === agent);
const runTurn = async (server, threadId, text, timeout = 90000) => {
  const startedAt = Date.now();
  const started = await server.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  assert(turnId, `turn ${text} started: ${JSON.stringify(started.error)}`);
  await waitFor(() => server.notifications.some((entry) => entry.method === "turn/completed" && entry.turn === turnId), `turn ${text} completed`, timeout);
  await quietly(waitFor(() => hooks().some((record) => record.receiptTime >= startedAt && record.event === "Stop" && record.payload.turn_id === turnId), `turn ${text} Stop`, 15000));
  return { turnId, startedAt };
};
const residency = async (server, label, threads) => {
  const loaded = (await server.call("thread/loaded/list", {})).result?.data ?? [];
  return trace("residency", { label, loaded, threads: Object.fromEntries(Object.entries(threads).map(([name, id]) => [name, { id, loaded: loaded.includes(id) }])) });
};
// One scenario: the lead's turn, then the worker's stop when one is
// expected, then a pause so late hooks land inside the scenario.
const step = async (server, lead, name, { worker = null, timeout = 90000 } = {}) => {
  scenario = name;
  trace("scenario", { name });
  const turn = await runTurn(server, lead, `SPIKE:${name}`, timeout);
  if (worker) await quietly(waitFor(() => stoppedSince(turn.startedAt, worker()), `${name}: worker stops`, 30000));
  await delay(1500);
  return turn;
};

const scripts = ["ancestry.mjs", "command.mjs", "hook.mjs", "run.mjs", "verify.mjs"];
const modules = ["src/dashpot/sessions/harnesses.py", "src/dashpot/sessions/hook_records.py", "src/dashpot/sessions/hook_scan.py", "src/dashpot/sessions/integrate/registry.py"];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", path.relative(checkout, here)], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, expectedVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), binarySHA256: sha(readFileSync(binary)),
    dashpot: { head, experimentDirty: dirty }, lifecycleEvents, matchers, hooksDocument,
    config: readFileSync(configPath, "utf8"), updater: JSON.parse(readFileSync(daemonSettingsPath, "utf8")),
    runnerAncestry: runnerAncestry.map((entry) => ({ pid: entry.pid, comm: entry.comm, harness: isHarness(entry) })), sharedDaemonDirBefore: sharedBefore.length,
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...modules.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, sha(readFileSync(file))])) });

  // Trust the fixture hooks through Codex's ledger, then restart so the
  // trusted configuration is the one every lead loads.
  scenario = "hook-trust";
  const trust = await appServer("trust");
  const entries = (await trust.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  await trust.stop();
  const checking = await appServer("trust-check");
  const relisted = (await checking.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { entries: relisted.map((entry) => ({ event: entry.eventName, matcher: entry.matcher ?? null, trust: entry.trustStatus, enabled: entry.enabled,
    tag: String(entry.command ?? entry.handler?.command ?? "").match(/hook\.mjs '([^']+)'/)?.[1] ?? null, keys: Object.keys(entry) })) });
  await checking.stop();
  assert(relisted.length > 0 && relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");

  // v2: one worker loaded, one worker turn running.
  const v2Overrides = ["features.multi_agent_v2=true", "agents.max_threads=1"];
  let v2 = await appServer("v2-first", v2Overrides);
  const started = await v2.call("thread/start", { cwd: fixture, model: "fixture-v2" });
  const lead = started.result?.thread?.id;
  assert(lead, `v2 lead started: ${JSON.stringify(started.error)}`);
  trace("lead", { version: "v2", lead });
  const workerAThread = () => command("wa.0")?.env.CODEX_THREAD_ID;
  await step(v2, lead, "v2-spawn", { worker: workerAThread });
  learned.workerA = workerAThread();
  assert(learned.workerA, "worker A reported its thread");
  await step(v2, lead, "v2-path", { worker: () => learned.workerA });
  await step(v2, lead, "v2-relative", { worker: () => learned.workerA });
  await step(v2, lead, "v2-id", { worker: () => learned.workerA });
  await residency(v2, "v2-before-evict", { lead, a: learned.workerA });
  await step(v2, lead, "v2-evict", { worker: () => command("wb.0")?.env.CODEX_THREAD_ID });
  learned.workerB = command("wb.0")?.env.CODEX_THREAD_ID;
  await residency(v2, "v2-evicted", { lead, a: learned.workerA, b: learned.workerB });
  await step(v2, lead, "v2-evicted", { worker: () => learned.workerA });
  await residency(v2, "v2-reloaded", { lead, a: learned.workerA, b: learned.workerB });
  await step(v2, lead, "v2-limit", { worker: () => learned.workerA, timeout: 120000 });
  await residency(v2, "v2-limited", { lead, a: learned.workerA, b: learned.workerB });
  await step(v2, lead, "v2-evicted-id", { worker: () => learned.workerB });
  await residency(v2, "v2-reloaded-id", { lead, a: learned.workerA, b: learned.workerB });
  await step(v2, lead, "v2-unknown");

  // The app-server stops; a new one resumes the lead, and B is restored from
  // disk by its follow-up.
  scenario = "v2-restart";
  trace("scenario", { name: "v2-restart" });
  await v2.stop();
  await quietly(waitFor(() => codexProcesses().length === 0, "first v2 server gone", 15000));
  v2 = await appServer("v2-second", v2Overrides);
  const resumed = await v2.call("thread/resume", { threadId: lead });
  trace("thread.resume", { lead, resumed: resumed.result?.thread?.id ?? null, error: resumed.error ?? null });
  await residency(v2, "v2-resumed", { lead, a: learned.workerA, b: learned.workerB });
  await step(v2, lead, "v2-restored", { worker: () => learned.workerB });
  await residency(v2, "v2-restored", { lead, a: learned.workerA, b: learned.workerB });
  await step(v2, lead, "v2-restored-id", { worker: () => learned.workerA });
  await residency(v2, "v2-restored-id", { lead, a: learned.workerA, b: learned.workerB });
  await v2.stop();

  // v1: the lead resumes its worker with `send_input`.
  const v1 = await appServer("v1", ["features.multi_agent_v2=false"]);
  const v1Started = await v1.call("thread/start", { cwd: fixture, model: "fixture-v1" });
  const v1Lead = v1Started.result?.thread?.id;
  assert(v1Lead, `v1 lead started: ${JSON.stringify(v1Started.error)}`);
  trace("lead", { version: "v1", lead: v1Lead });
  scenario = "v1-spawn";
  trace("scenario", { name: "v1-spawn" });
  const v1Spawn = runTurn(v1, v1Lead, "SPIKE:v1-spawn");
  await waitFor(() => command("wv.0"), "worker V reports its thread", 30000);
  learned.workerV = command("wv.0").env.CODEX_THREAD_ID;
  await v1Spawn;
  await quietly(waitFor(() => stoppedSince(0, learned.workerV), "worker V stops", 30000));
  await delay(1500);
  await step(v1, v1Lead, "v1-send", { worker: () => learned.workerV });
  await step(v1, v1Lead, "v1-unknown");
  await step(v1, v1Lead, "v1-closed");
  await delay(3000);
  await v1.stop();

  scenario = "end";
  trace("outcome", { learned, unknownId, leads: { v2: lead, v1: v1Lead } });
  console.log(`All scenarios completed: ${root}`);
} catch (error) {
  trace("failure", { error: String(error?.stack ?? error).slice(0, 2000) });
  process.exitCode = 1;
} finally {
  for (const child of servers) { try { child.kill("SIGTERM"); } catch {} }
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: [entry.pid, entry.comm] });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  const sharedAfter = sharedEntries();
  trace("shared-daemon-dir", { added: sharedAfter.filter((name) => !sharedBefore.includes(name)).length, removed: sharedBefore.filter((name) => !sharedAfter.includes(name)).length });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
