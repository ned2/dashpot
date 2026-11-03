// Fresh-Worker dynamic tools and delegation metadata run for Issue #666:
// drives a pinned Codex CLI against a loopback Responses API fixture, with an
// isolated CODEX_HOME whose daemon updater is off, through `codex app-server`
// over stdio. Each multi-agent v2 lead thread is started with one harmless
// client-defined dynamic tool, `fixture_lookup`, which this runner answers
// with a constant marker. Two phases run the same spawn with Codex's
// `multi_agent_v2_dynamic_tools` feature off and then on, each with one
// Worker started with `fork_turns: "none"` and one with the full history. In
// the second phase the fresh Worker is followed up, the lead and the Worker
// are compacted, and the app-server is restarted and the lead resumed before
// both Workers are followed up again. The trace records what each model
// request was offered and carried, every dynamic tool request the client
// received, the live and persisted Sub-agent activity and turn lineage, the
// rollouts' own metadata, and each hook's identity fields, metadata only.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
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
// A fixture hook below a harness process would attach to that harness's
// session in any observer walking the ancestry, so the runner refuses to
// start below one.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-666-"));
console.log(`Isolated fixture: ${root}`);
const workspace = path.join(root, "workspace");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's temporary root
// never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  const kept = record.ancestry ? { ...record, ancestry: record.ancestry.slice(0, 4).map((entry) => ({ pid: entry.pid, ppid: entry.ppid, comm: entry.comm })) } : record;
  appendFileSync(tracePath, JSON.stringify(kept).replaceAll(root, "$ROOT").replaceAll(home, "~").replace(hostName, "<host>") + "\n");
  return record;
};
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");

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
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  // Ancestry walks from hooks end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [workspace, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME, env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) {
  mkdirSync(dir, { recursive: true });
}
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

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
  trace("hook", await body(req));
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The harmless client-defined tool every lead thread is started with. The
// runner answers each call with `TOOLRESULT:<probe>`, or, for the probe
// `deny`, refuses it with `TOOLDENIED:deny`; it reads nothing and runs
// nothing.
const toolName = "fixture_lookup";
const dynamicTool = {
  type: "function",
  name: toolName,
  description: "Return a fixed marker for the given probe. Reads and changes nothing.",
  inputSchema: { type: "object", properties: { probe: { type: "string" } }, required: ["probe"], additionalProperties: false },
};

// The fixture model is scripted per directive. The latest input item that is
// not a tool call and carries `SPIKE:<label>` (a person's prompt, a spawn
// message or a follow-up task) selects the plan `plans[label]`; the number of
// tool outputs after that item selects the step. Each step becomes one tool
// call; when the plan runs out, the model answers `DONE:<label>`. A
// compaction request is answered with a summary and takes no step.
//
// The lead's first prompt in each phase also carries `LEADSECRET:<phase>`, a
// sentinel that reaches a Worker only with the lead's history.
const plans = {
  "off-lead": [{ tool: "off-lead" }, { spawn: ["fresh", "off-fresh", "none", { reasoning_effort: "low" }] }, { spawn: ["full", "off-full", "all"] }, { wait: 30000 }, { wait: 30000 }],
  "off-fresh": [{ tool: "off-fresh" }],
  "off-full": [{ tool: "off-full" }],
  "on-lead": [{ tool: "on-lead" }, { spawn: ["fresh", "on-fresh", "none", { reasoning_effort: "low" }] }, { spawn: ["full", "on-full", "all"] }, { wait: 30000 }, { wait: 30000 }],
  "on-fresh": [{ tool: "on-fresh" }],
  "on-full": [{ tool: "on-full" }],
  "on-follow": [{ followup: ["/root/fresh", "on-fresh2"] }, { wait: 30000 }],
  "on-fresh2": [{ tool: "deny" }, { tool: "on-fresh2" }],
  "on-compacted": [{ followup: ["/root/fresh", "on-fresh3"] }, { wait: 30000 }],
  "on-fresh3": [{ tool: "on-fresh3" }],
  "on-resumed": [{ tool: "on-resumed" }, { followup: ["/root/fresh", "on-fresh4"] }, { wait: 30000 }, { followup: ["/root/full", "on-full2"] }, { wait: 30000 }],
  "on-fresh4": [{ tool: "on-fresh4" }],
  "on-full2": [{ tool: "on-full2" }],
};
// No word boundary: Codex puts a Worker's final message straight after a
// newline, which JSON escapes as `\n`.
const markerPattern = /(SPIKE|DONE|LEADSECRET|TOOLRESULT|TOOLDENIED|SUMMARY):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const outputText = (item) => {
  const output = item.output;
  if (typeof output === "string") return output;
  if (Array.isArray(output)) return output.map((part) => part?.text ?? "").join(" ");
  return JSON.stringify(output ?? null);
};
// The lineage and identity Codex sends with each request, in its client
// metadata and in the `x-codex-turn-metadata` blob within it.
const turnMetadataKeys = ["request_kind", "session_id", "thread_id", "turn_id", "parent_thread_id", "parent_turn_id", "root_turn_id",
  "subagent_kind", "thread_source", "turn_trigger", "forked_from_thread_id", "history_initialization", "agent_name"];
const modelRequests = [];
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const lastToolsByThread = new Map();
let phase = "setup";
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
  const lineage = {
    thread: clientMetadata.thread_id ?? null, session: clientMetadata.session_id ?? null, turn: clientMetadata.turn_id ?? null,
    parentTurn: clientMetadata.parent_turn_id ?? null, rootTurn: clientMetadata.root_turn_id ?? null,
    parentThreadHeader: req.headers["x-codex-parent-thread-id"] ?? null,
    metadata: Object.fromEntries(turnMetadataKeys.filter((key) => blob[key] !== undefined).map((key) => [key, blob[key]])),
  };
  const compaction = blob.request_kind === "compaction";
  const input = payload.input ?? [];
  let directiveAt = -1;
  let label = null;
  input.forEach((item, index) => {
    if (isCall(item)) return;
    const found = [...JSON.stringify(item).matchAll(markerPattern)].filter((match) => match[1] === "SPIKE");
    if (found.length) { directiveAt = index; label = found.at(-1)[2]; }
  });
  // Each marker once per item that carries it, in input order, with the
  // item's type, so a marker in a call's own arguments is not mistaken for
  // delivered history.
  const markers = input.flatMap((item, index) => [...new Set([...JSON.stringify(item).matchAll(markerPattern)].map((match) => match[0]))]
    .map((marker) => [index, item.type ?? null, item.role ?? null, marker]));
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? (tool.tools ?? []).map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const toolNames = tools.map(([namespace, name]) => namespace ? `${namespace}/${name}` : name).sort();
  const toolsKey = toolNames.join(",");
  const toolsChanged = lastToolsByThread.get(lineage.thread) !== toolsKey;
  lastToolsByThread.set(lineage.thread, toolsKey);
  const offered = (name) => tools.find(([, candidate]) => candidate === name) ?? null;
  const plan = !compaction && label ? plans[label] ?? [] : [];
  const step = plan[outputs.length] ?? null;
  const callId = `call_${label}_${outputs.length}_${modelRequests.length}`;
  const call = (name, args, { attempt = false } = {}) => {
    const tool = offered(name);
    if (!tool && !attempt) return null;
    return { type: "function_call", call_id: callId, ...(tool?.[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.tool) {
    // The client-defined tool is called whether or not Codex offered it, so
    // the trace shows what Codex does with a call to a tool a thread lacks.
    action = toolName;
    item = call(toolName, { probe: step.tool }, { attempt: true });
  } else if (step?.spawn) {
    const [taskName, child, fork, extra = {}] = step.spawn;
    action = "spawn_agent";
    item = call("spawn_agent", { message: `SPIKE:${child}`, task_name: taskName, fork_turns: fork, ...extra });
  } else if (step?.followup) {
    const [target, child] = step.followup;
    action = "followup_task";
    item = call("followup_task", { target, message: `SPIKE:${child}` });
  } else if (step?.wait) {
    action = "wait_agent";
    item = call("wait_agent", { timeout_ms: step.wait });
  }
  // The latest call output after the directive: a tool result, an error, or
  // a collaboration tool's reply.
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const lastOutput = latestOutput ? { type: latestOutput.type, text: outputText(latestOutput).replaceAll(root, "$ROOT").slice(0, 600) } : null;
  const request = trace("model.request", { phase, ...lineage, compaction, label, step: compaction ? null : outputs.length, inputItems: input.length, directiveAt, markers,
    action, probe: step?.tool ?? null, offeredTool: Boolean(offered(toolName)), missing: Boolean(step && !item), lastOutput,
    tools: toolsChanged ? toolNames : undefined, tail: input.slice(-3).map((entry) => [entry.type ?? null, entry.role ?? null]) });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  const text = compaction ? `SUMMARY:${label ?? "none"} fixture summary.` : label ? `DONE:${label}` : "Fixture complete.";
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The hook events `dashpot integrate codex` subscribes, each routed to the
// metadata-only recorder; nothing is published to Dashpot.
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
// A read-only sandbox under `on-request` approvals: Codex would have to ask
// the client before running anything, and the fixture runs no command, so
// any approval request the trace shows came from the dynamic tool.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-v2"
model_catalog_json = ${JSON.stringify(catalogPath)}
model_provider = "fixture"
approval_policy = "on-request"
sandbox_mode = "read-only"
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

[projects.${JSON.stringify(workspace)}]
trust_level = "trusted"
`);
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
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);

// A Thread item's metadata: its type and id, and for the items this run
// measures, their delegation, model and tool fields. Which keys an item
// carries is kept too, so a null field is told apart from a missing one.
const itemSummary = (item) => {
  if (!item) return null;
  const summary = { type: item.type, id: item.id ?? null };
  if (item.type === "subAgentActivity") {
    Object.assign(summary, { kind: item.kind, agentThreadId: item.agentThreadId, agentPath: item.agentPath, model: item.model, reasoningEffort: item.reasoningEffort,
      keys: Object.keys(item).sort() });
  } else if (item.type === "collabAgentToolCall") {
    Object.assign(summary, { tool: item.tool, status: item.status, senderThreadId: item.senderThreadId ?? null, receiverThreadIds: item.receiverThreadIds ?? null,
      model: item.model, reasoningEffort: item.reasoningEffort, keys: Object.keys(item).sort() });
  } else if (item.type === "dynamicToolCall") {
    Object.assign(summary, { tool: item.tool, namespace: item.namespace ?? null, status: item.status, success: item.success ?? null, probe: item.arguments?.probe ?? null });
  }
  return summary;
};
const recordedItemTypes = new Set(["subAgentActivity", "collabAgentToolCall", "dynamicToolCall", "contextCompaction"]);
const turnSummary = (turn) => turn && ({ id: turn.id, rootTurnId: turn.rootTurnId, rootTurnIdKey: "rootTurnId" in turn, status: turn.status,
  items: (turn.items ?? []).filter((item) => recordedItemTypes.has(item.type)).map(itemSummary) });
const threadSummary = (thread) => thread && ({ id: thread.id, parentThreadId: thread.parentThreadId ?? null, agentPath: thread.agentPath ?? null,
  agentNickname: thread.agentNickname ?? null, threadSource: thread.threadSource ?? null, status: thread.status ?? null, model: thread.model ?? null,
  source: thread.source ?? null, turns: (thread.turns ?? []).map(turnSummary) });

// One `codex app-server` over stdio. It answers each dynamic tool request
// with the fixture's marker and records it; any other server request, which
// an approval would be, is recorded and declined.
const servers = [];
const notifications = [];
const toolCalls = [];
const appServer = async (name, overrides) => {
  const args = overrides.flatMap((override) => ["-c", override]);
  const child = spawn("codex", [...args, "app-server"], { cwd: workspace, env, stdio: ["pipe", "pipe", "pipe"] });
  servers.push(child);
  let next = 0;
  const pending = new Map();
  child.stderr.on("data", (chunk) => appendFileSync(path.join(root, `app-server-${name}.stderr`), chunk));
  const write = (message) => child.stdin.write(JSON.stringify(message) + "\n");
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    const message = parseJson(line);
    if (!message) return;
    const params = message.params ?? {};
    if (message.method && message.id !== undefined) {
      if (message.method === "item/tool/call") {
        const probe = params.arguments?.probe ?? null;
        const success = probe !== "deny";
        toolCalls.push(trace("tool.call", { server: name, phase, thread: params.threadId, turn: params.turnId, callId: params.callId,
          tool: params.tool, namespace: params.namespace ?? null, probe, answered: success ? `TOOLRESULT:${probe}` : "TOOLDENIED:deny", success }));
        write({ id: message.id, result: { contentItems: [{ type: "inputText", text: success ? `TOOLRESULT:${probe}` : "TOOLDENIED:deny" }], success } });
      } else {
        trace("server.request", { server: name, phase, method: message.method, thread: params.threadId ?? null, keys: Object.keys(params).sort() });
        write({ id: message.id, result: { decision: "decline" } });
      }
    } else if (message.method) {
      const turn = params.turn;
      const entry = { server: name, phase, method: message.method, thread: params.threadId ?? params.thread?.id ?? null, turn: turn?.id ?? params.turnId ?? null,
        receivedAt: Date.now() };
      if (turn) Object.assign(entry, { rootTurnId: turn.rootTurnId ?? null, rootTurnIdKey: "rootTurnId" in turn, status: turn.status ?? null });
      if (params.item) entry.item = itemSummary(params.item);
      if (message.method === "thread/started") entry.threadInfo = threadSummary(params.thread);
      notifications.push(entry);
      const kept = /^(turn\/(started|completed)|thread\/(started|status\/changed|compacted|closed))$/.test(message.method)
        || (/^item\/(started|completed)$/.test(message.method) && recordedItemTypes.has(params.item?.type));
      if (kept) trace("rpc.event", entry);
    } else if (pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
  });
  const call = async (method, callParams = {}) => {
    const id = ++next;
    const response = new Promise((resolve) => pending.set(id, resolve));
    write({ id, method, params: callParams });
    return Promise.race([response, delay(30000).then(() => ({ error: { message: `${method} timed out` } }))]);
  };
  const init = await call("initialize", { clientInfo: { name: "fixture-666", version: "0" }, capabilities: { experimentalApi: true } });
  assert(init.result, `${name} initialized: ${JSON.stringify(init.error)}`);
  write({ method: "initialized", params: {} });
  trace("server.start", { server: name, args: overrides, pid: child.pid });
  const stop = async () => {
    child.stdin.end();
    const exited = once(child, "exit");
    const timer = setTimeout(() => child.kill("SIGTERM"), 10000);
    const [status, signal] = await exited;
    clearTimeout(timer);
    trace("server.stop", { server: name, status, signal });
  };
  return { name, call, stop };
};

const completed = (thread, since) => notifications.find((entry) => entry.method === "turn/completed" && entry.thread === thread && entry.receivedAt >= since);
const runTurn = async (server, threadId, text, timeout = 120000) => {
  const startedAt = Date.now();
  const started = await server.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { server: server.name, threadId, turnId, label: text, rootTurnId: started.result?.turn?.rootTurnId ?? null, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  await waitFor(() => completed(threadId, startedAt), `turn ${text} completed`, timeout);
  trace("turn.completed", { server: server.name, threadId, turnId, status: completed(threadId, startedAt).status });
  return { turnId, startedAt };
};
// A Worker's thread, from the Sub-agent activity its lead published.
const workerThread = (lead, agentPath) => notifications.find((entry) => entry.thread === lead && entry.item?.type === "subAgentActivity"
  && entry.item.kind === "started" && entry.item.agentPath === agentPath)?.item.agentThreadId ?? null;
const workersSettle = async (threads, since, label) => {
  await quietly(waitFor(() => threads.every((thread) => thread && completed(thread, since)), `${label}: Workers complete`, 30000));
  await delay(1500);
};
const readThread = async (server, label, threadId) => {
  const read = await server.call("thread/read", { threadId, includeTurns: true });
  return trace("thread.read", { server: server.name, label, threadId, thread: threadSummary(read.result?.thread), error: read.error ?? null });
};
const compact = async (server, label, threadId) => {
  const since = Date.now();
  const response = await server.call("thread/compact/start", { threadId });
  // A refusal ends the attempt: nothing will compact.
  if (response.error) return trace("compact", { label, threadId, response: response.error, done: false, requests: [] });
  const done = await quietly(waitFor(() => notifications.some((entry) => entry.thread === threadId && entry.receivedAt >= since
    && (entry.method === "thread/compacted" || (entry.method === "item/completed" && entry.item?.type === "contextCompaction"))), `${label} compacted`, 30000));
  await quietly(waitFor(() => completed(threadId, since), `${label} compaction turn`, 10000));
  await delay(1000);
  return trace("compact", { label, threadId, response: response.error ?? response.result ?? null, done,
    requests: modelRequests.filter((record) => record.thread === threadId && record.receiptTime >= since && record.compaction).map((record) => record.receipt) });
};

// Codex's own record of each thread, metadata only: its creation metadata
// and the dynamic tools it names, each turn's lineage, and its Sub-agent
// activity.
const rolloutFiles = (dir) => {
  let entries = [];
  try { entries = readdirSync(dir); } catch { return []; }
  return entries.flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? rolloutFiles(full) : entry.endsWith(".jsonl") ? [full] : [];
  });
};
const toolNamesOf = (specs) => specs == null ? null : specs.flatMap((spec) => spec.type === "namespace" ? (spec.tools ?? []).map((tool) => `${spec.name}/${tool.name}`) : [spec.name]);
const rollouts = () => rolloutFiles(path.join(env.CODEX_HOME, "sessions")).map((file) => {
  const lines = readFileSync(file, "utf8").trim().split("\n").map(parseJson).filter(Boolean);
  const metas = lines.filter((line) => line.type === "session_meta").map((line) => line.payload ?? {});
  const meta = metas[0] ?? {};
  const events = lines.filter((line) => line.type === "event_msg").map((line) => line.payload ?? {});
  const items = events.filter((event) => event.type === "item_completed" && event.item).map((event) => ({ turnId: event.turn_id ?? null, item: event.item }));
  return {
    id: meta.id ?? null, sessionMetaCount: metas.length, forkedFromId: meta.forked_from_id ?? null, parentThreadId: meta.parent_thread_id ?? null,
    agentPath: meta.agent_path ?? null, threadSource: meta.thread_source ?? null, source: meta.source ?? null,
    dynamicTools: metas.map((entry) => toolNamesOf(entry.dynamic_tools ?? null)),
    turnsStarted: events.filter((event) => event.type === "task_started").map((event) => ({ turnId: event.turn_id ?? null, rootTurnId: event.root_turn_id ?? null,
      attribution: event.turn_attribution ?? null, keys: Object.keys(event).sort() })),
    subAgentActivity: items.filter((entry) => entry.item.type === "SubAgentActivity").map(({ turnId, item }) => ({ turnId, kind: item.kind,
      agentThreadId: item.agent_thread_id ?? null, agentPath: item.agent_path ?? null, model: item.model, reasoningEffort: item.reasoning_effort,
      keys: Object.keys(item).sort() })),
    dynamicToolCalls: items.filter((entry) => entry.item.type === "DynamicToolCall").map(({ turnId, item }) => ({ turnId, tool: item.tool ?? null,
      probe: item.arguments?.probe ?? null, status: item.status ?? null, success: item.success ?? null })),
    compacted: lines.filter((line) => line.type === "compacted").length,
    turnContexts: lines.filter((line) => line.type === "turn_context").map((line) => ({ turnId: line.payload?.turn_id ?? null, model: line.payload?.model ?? null,
      effort: line.payload?.effort ?? null })),
  };
});

const scripts = ["ancestry.mjs", "hook.mjs", "run.mjs"];
const sources = ["examples/codex-hooks.json"];
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", path.relative(checkout, here)], { encoding: "utf8" }).trim() !== "";
  trace("environment", { version, expectedVersion, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim().replace(home, "~"), binarySHA256: sha(readFileSync(binary)),
    checkout: { head, experimentDirty: dirty }, hookEvents, dynamicTools: [dynamicTool],
    fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2", defaultReasoningLevel: base.default_reasoning_level ?? null,
      supportedReasoningLevels: (base.supported_reasoning_levels ?? []).map((level) => level.effort ?? level) },
    config: readFileSync(configPath, "utf8"), updater: JSON.parse(readFileSync(daemonSettingsPath, "utf8")),
    sourceSHA256: Object.fromEntries([...scripts.map((file) => [file, path.join(here, file)]), ...sources.map((file) => [file, path.join(checkout, file)])]
      .map(([name, file]) => [name, sha(readFileSync(file))])) });

  // Setup: trust the fixture hooks through the ledger.
  phase = "hook-trust";
  trace("scenario", { name: phase });
  const trust = await appServer("trust", []);
  const listed = await trust.call("hooks/list", { cwds: [workspace] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  assert.equal(entries.length, hookEvents.length, `fixture hooks listed: ${JSON.stringify(listed.error ?? listed.result)}`);
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await trust.call("hooks/list", { cwds: [workspace] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");
  await trust.stop();

  // Phase off: the feature explicitly off, one fresh and one full-history Worker.
  const runPhase = async (name, flag) => {
    phase = name;
    trace("scenario", { name, flag });
    const server = await appServer(name, [`features.multi_agent_v2_dynamic_tools=${flag}`]);
    const started = await server.call("thread/start", { cwd: workspace, model: "fixture-v2", dynamicTools: [dynamicTool] });
    const lead = started.result?.thread?.id;
    trace("thread.start", { server: name, name: `${name}-lead`, thread: threadSummary(started.result?.thread), error: started.error ?? null });
    assert(lead, `${name} lead started: ${JSON.stringify(started.error)}`);
    const spawned = await runTurn(server, lead, `SPIKE:${name}-lead LEADSECRET:${name}`);
    const fresh = workerThread(lead, "/root/fresh");
    const full = workerThread(lead, "/root/full");
    await workersSettle([fresh, full], spawned.startedAt, name);
    trace(`${name}.spawned`, { lead, fresh, full, leadTurn: spawned.turnId });
    return { server, lead, fresh, full, leadTurn: spawned.turnId };
  };
  const off = await runPhase("off", false);
  for (const [label, threadId] of [["off-lead", off.lead], ["off-fresh", off.fresh], ["off-full", off.full]]) await readThread(off.server, label, threadId);
  await off.server.stop();

  // Phase on: the same spawn with the feature on, then the fresh Worker's
  // follow-up, compaction, and a restart with the lead resumed.
  const on = await runPhase("on", true);
  const follow = await runTurn(on.server, on.lead, "SPIKE:on-follow");
  await workersSettle([on.fresh], follow.startedAt, "on-follow");
  trace("on.followed", { leadTurn: follow.turnId });

  trace("scenario", { name: "compaction" });
  await compact(on.server, "lead", on.lead);
  await compact(on.server, "fresh", on.fresh);
  const compacted = await runTurn(on.server, on.lead, "SPIKE:on-compacted");
  await workersSettle([on.fresh], compacted.startedAt, "on-compacted");
  trace("on.compacted", { leadTurn: compacted.turnId });
  for (const [label, threadId] of [["on-lead-live", on.lead], ["on-fresh-live", on.fresh], ["on-full-live", on.full]]) await readThread(on.server, label, threadId);
  await on.server.stop();

  // The replacement app-server holds nothing loaded; the lead is resumed
  // without naming any dynamic tool, and each Worker reloads from its
  // rollout when followed up.
  phase = "resumed";
  trace("scenario", { name: phase, flag: true });
  const resumedServer = await appServer("resumed", ["features.multi_agent_v2_dynamic_tools=true"]);
  for (const [label, threadId] of [["on-lead-cold", on.lead], ["on-fresh-cold", on.fresh], ["on-full-cold", on.full]]) await readThread(resumedServer, label, threadId);
  const resumed = await resumedServer.call("thread/resume", { threadId: on.lead });
  trace("thread.resume", { server: "resumed", threadId: on.lead, thread: threadSummary(resumed.result?.thread), error: resumed.error ?? null });
  assert(resumed.result?.thread?.id, `lead resumed: ${JSON.stringify(resumed.error)}`);
  const after = await runTurn(resumedServer, on.lead, "SPIKE:on-resumed");
  await workersSettle([on.fresh, on.full], after.startedAt, "on-resumed");
  trace("on.resumed", { leadTurn: after.turnId });
  for (const [label, threadId] of [["on-lead-resumed", on.lead], ["on-fresh-resumed", on.fresh], ["on-full-resumed", on.full], ["off-lead-cold", off.lead]]) {
    await readThread(resumedServer, label, threadId);
  }
  await resumedServer.stop();
  await delay(1000);

  trace("rollouts", { threads: rollouts() });
  trace("summary", { phases: { off: { lead: off.lead, fresh: off.fresh, full: off.full, leadTurn: off.leadTurn },
    on: { lead: on.lead, fresh: on.fresh, full: on.full, leadTurn: on.leadTurn, followTurn: follow.turnId, compactedTurn: compacted.turnId, resumedTurn: after.turnId } },
    toolCalls: toolCalls.length, notifications: notifications.length, processes: codexProcesses().map((entry) => [entry.pid, entry.comm]) });
  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const child of servers) { try { child.kill("SIGTERM"); } catch {} }
  await delay(1000);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { process: [entry.pid, entry.comm] });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
