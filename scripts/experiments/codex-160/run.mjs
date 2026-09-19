// Isolated Codex identity and lifecycle experiment for Issue #160. Drives a
// pinned Codex CLI against a loopback Responses API fixture with an isolated
// CODEX_HOME, hosts root threads, a fork, a sub-agent, and attached clients on
// one app-server beside ordinary `codex exec` processes, records hook and
// shell evidence as a metadata-only trace, and asserts the observable outcomes.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-160-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, JSON.stringify(record) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.155.1";

const env = {
  PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "Disposable fixture");
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

// The fixture model: a `SPIKE:<label>` text in the latest user message selects
// one exec_command call reporting identity; `delegate` spawns a sub-agent and
// waits for it; a request already holding the tool outputs ends the turn.
const commandScript = path.join(here, "command.mjs");
const modelRequests = new Map();
const sse = (res, event) => res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/responses")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: { type: "not_found", message: "fixture" } }));
    return;
  }
  const input = payload.input ?? [];
  let label = null;
  let latestUser = -1;
  input.forEach((item, index) => {
    if (item.type !== "message" || item.role !== "user") return;
    for (const part of Array.isArray(item.content) ? item.content : []) {
      const match = part.type === "input_text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?/);
      if (match) { label = { name: match[1], hold: match[2] }; latestUser = index; }
    }
  });
  const outputs = input.slice(latestUser + 1).filter((item) => item.type === "function_call_output");
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => `${tool.name}/${nested.name}`) : [tool.name ?? tool.type]);
  const count = (modelRequests.get(label?.name ?? "none") ?? 0) + 1;
  modelRequests.set(label?.name ?? "none", count);
  const delegate = label?.name === "delegate" && tools.includes("multi_agent_v1/spawn_agent");
  const needed = delegate ? 2 : 1;
  const useTool = label && outputs.length < needed && tools.includes("exec_command");
  trace("model.request", { label: label?.name ?? null, count, outputs: outputs.length, model: payload.model, stream: payload.stream, toolCount: tools.length,
    tools: modelRequests.size === 1 && count === 1 ? tools : undefined, previousResponseId: payload.previous_response_id ?? null, store: payload.store ?? null });
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  if (useTool) {
    const callId = `call_${label.name}_${count}`;
    let item;
    if (delegate && outputs.length === 0) {
      item = { type: "function_call", call_id: callId, namespace: "multi_agent_v1", name: "spawn_agent", arguments: JSON.stringify({ message: "SPIKE:child" }) };
    } else if (delegate) {
      // The spawn result names the child; wait for it before ending the turn.
      let agentId = null;
      try { agentId = JSON.parse(outputs[0].output).agent_id; } catch { agentId = String(outputs[0].output).match(/[0-9a-f-]{36}/)?.[0] ?? null; }
      trace("model.delegate", { agentId, outputKeys: (() => { try { return Object.keys(JSON.parse(outputs[0].output)); } catch { return null; } })() });
      item = { type: "function_call", call_id: callId, namespace: "multi_agent_v1", name: "wait_agent", arguments: JSON.stringify({ targets: [agentId], timeout_ms: 60000 }) };
    } else {
      item = { type: "function_call", call_id: callId, name: "exec_command", arguments: JSON.stringify({ cmd: `node ${commandScript} ${label.name} ${label.hold ?? 200}`, login: false }) };
    }
    sse(res, { type: "response.output_item.done", item });
  } else {
    sse(res, { type: "response.output_item.done", item: { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: "Fixture complete." }] } });
  }
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart", "SubagentStop", "SessionEnd", "Interrupt"];
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
}, null, 2));
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-model"
approval_policy = "never"
sandbox_mode = "danger-full-access"
model_provider = "fixture"

[features]
hooks = true
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

[projects."${fixture}"]
trust_level = "trusted"

[projects."${other}"]
trust_level = "trusted"
`);

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
const snapshot = (label) => trace("processes", { label, processes: codexProcesses() });
const hooks = () => records.filter((record) => record.kind === "hook");
const hooksSince = (count) => hooks().slice(count).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source ?? record.payload.agent_id ?? null, record.payload.cwd]);
const commands = () => records.filter((record) => record.kind === "command");
const command = (label, phase = "start") => commands().find((record) => record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const freePort = async () => {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = probe.address().port;
  probe.close();
  return port;
};

// One app-server process listening on loopback WebSocket for several clients.
const startServer = async (label) => {
  const port = await freePort();
  const child = spawn(binary, ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  child.stdout.on("data", () => {});
  const exit = once(child, "exit").then(([status, signal]) => { trace("server.exit", { label, pid: child.pid, status, signal, stderr: stderr.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").slice(-1500) }); return { status, signal }; });
  await waitFor(() => stderr.includes("listening on"), `${label} listening`, 20000);
  trace("server.start", { label, pid: child.pid, port, banner: stderr.split("\n")[0] });
  return { child, port, pid: child.pid, exit, label };
};
const connect = async (server, name) => {
  const socket = new WebSocket(`ws://127.0.0.1:${server.port}`);
  await once(socket, "open");
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  socket.addEventListener("message", (message) => {
    const parsed = JSON.parse(message.data);
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method === "hook/started" || parsed.method === "hook/completed") {
      notifications.push({ method: parsed.method, threadId: parsed.params.threadId, turnId: parsed.params.turnId, event: parsed.params.run.eventName, status: parsed.params.run.status, scope: parsed.params.run.scope, receivedAt: Date.now() });
    } else if (parsed.method?.startsWith("thread/") || parsed.method?.startsWith("turn/")) {
      const { threadId, turn, status, thread } = parsed.params ?? {};
      notifications.push({ method: parsed.method, threadId: threadId ?? thread?.id, turnId: turn?.id, status: status ?? turn?.status, receivedAt: Date.now() });
    }
  });
  const closed = once(socket, "close").then(([event]) => ({ code: event.code, reason: event.reason }));
  const call = (method, params = {}) => new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); });
  const init = await call("initialize", { clientInfo: { name: `dashpot-160-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  trace("client.connect", { client: name, server: server.label, userAgent: init.result?.userAgent, codexHome: init.result?.codexHome, error: init.error ?? null });
  return { name, socket, call, notifications, closed, close: () => socket.close() };
};
// The thread fields the trace keeps: identity and hosting, never content.
const threadSummary = (thread) => thread && ({ id: thread.id, sessionId: thread.sessionId, forkedFromId: thread.forkedFromId, parentThreadId: thread.parentThreadId, cwd: thread.cwd ?? thread.environments?.[0]?.cwd ?? null,
  source: thread.source, status: thread.status, historyMode: thread.historyMode, originator: thread.originator, agentRole: thread.agentRole, ephemeral: thread.ephemeral });
const runTurn = async (client, threadId, text, options = {}) => {
  const hooksBefore = hooks().length;
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }], ...(options.cwd ? { cwd: options.cwd } : {}) });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { client: client.name, threadId, turnId, label: text, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  if (options.detached) return { turnId, hooksBefore };
  await waitFor(() => client.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === turnId), `turn ${text} completed`, options.timeout ?? 60000);
  const completed = client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
  trace("turn.completed", { client: client.name, threadId, turnId, status: completed.status, newHooks: hooksSince(hooksBefore) });
  return { turnId, hooksBefore, status: completed.status };
};
const codex = async (args, options = {}) => {
  const child = spawn(binary, args, { cwd: options.cwd ?? fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), options.timeout ?? 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  // `exec --json` prints one event per line; keep the identity-bearing ones.
  const events = stdout.split("\n").filter(Boolean).map((line) => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean)
    .map((event) => ({ type: event.type, threadId: event.thread_id ?? null, itemType: event.item?.type ?? null }));
  trace("action.codex", { args, cwd: options.cwd ?? fixture, pid: child.pid, status, signal, events, stderr: stderr.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").slice(-1500) });
  return { status, signal, stdout, stderr, pid: child.pid, events };
};
const lockFiles = () => { try { return readdirSync(path.join(env.CODEX_HOME, "thread-writer-locks")); } catch { return []; } };

let server = null;
let replacement = null;
try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, binary, binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    env: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CODEX") || key === "SPIKE_SINK")), fixture, other, hookEvents,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // Scenario 0: trust the fixture hooks the way `/hooks` would, through the ledger.
  trace("scenario", { name: "hook-trust" });
  server = await startServer("primary");
  const client1 = await connect(server, "one");
  const listed = await client1.call("hooks/list", { cwds: [fixture] });
  const entries = listed.result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { before: entries.map((entry) => [entry.eventName, entry.source, entry.trustStatus, entry.enabled]) });
  assert(entries.length === hookEvents.length && entries.every((entry) => entry.trustStatus === "untrusted"), "fixture hooks start untrusted");
  appendFileSync(configPath, "\n" + entries.map((entry) => `[hooks.state.${JSON.stringify(entry.key)}]\ntrusted_hash = ${JSON.stringify(entry.currentHash)}\n`).join("\n"));
  const relisted = (await client1.call("hooks/list", { cwds: [fixture] })).result?.data?.[0]?.hooks ?? [];
  trace("hooks.list", { after: relisted.map((entry) => [entry.eventName, entry.trustStatus, entry.enabled]) });
  assert(relisted.every((entry) => entry.trustStatus === "trusted"), "fixture hooks trusted through the ledger");

  // Scenario 1: two root threads in two Worktrees on one app-server.
  trace("scenario", { name: "two-root-threads" });
  const threadA = (await client1.call("thread/start", { cwd: fixture })).result?.thread;
  const threadB = (await client1.call("thread/start", { cwd: other })).result?.thread;
  assert(threadA?.id && threadB?.id, "two threads started");
  trace("threads.started", { a: threadSummary(threadA), b: threadSummary(threadB) });
  assert.notEqual(threadA.id, threadB.id);
  await runTurn(client1, threadA.id, "SPIKE:root-a");
  await runTurn(client1, threadB.id, "SPIKE:root-b");
  snapshot("two-threads-idle");
  const loaded = (await client1.call("thread/loaded/list", {})).result?.data ?? [];
  trace("threads.loaded", { label: "two-threads-idle", loaded });
  for (const [label, thread] of [["root-a", threadA], ["root-b", threadB]]) {
    const start = hooks().find((record) => record.event === "SessionStart" && record.payload.session_id === thread.id);
    const shell = command(label);
    assert(start && shell, `${label} start hook and command`);
    assert.equal(start.payload.source, "startup");
    assert.equal(thread.sessionId, thread.id, "root thread sessionId equals its id");
    assert.equal(shell.env.CODEX_THREAD_ID, thread.id);
    assert.equal(shell.env.CODEX_SESSION_ID, thread.id);
    assert.equal(shell.cwd, label === "root-a" ? fixture : other);
    assert.equal(start.payload.cwd, shell.cwd);
    assert(shell.ancestry.some((entry) => entry.pid === server.pid), `${label} shell descends from the app-server`);
    assert(start.ancestry.some((entry) => entry.pid === server.pid), `${label} hook descends from the app-server`);
    trace("identity", { label, threadId: thread.id, sessionId: thread.sessionId, hookSessionId: start.payload.session_id, hookCwd: start.payload.cwd, hookEnv: start.env,
      shellEnv: shell.env, shellCwd: shell.cwd, shellAncestry: shell.ancestry.slice(0, 4), hookAncestry: start.ancestry.slice(0, 3), serverPid: server.pid });
  }
  assert(loaded.includes(threadA.id) && loaded.includes(threadB.id), "both threads loaded on one server");
  const serverEntry = codexProcesses().find((entry) => entry.pid === server.pid);
  trace("server.identity", { pid: server.pid, comm: serverEntry?.comm, cmdline: serverEntry?.cmdline, otherProcesses: codexProcesses().filter((entry) => entry.pid !== server.pid).map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline]) });

  // Scenario 2: fork thread A into a new identity and run a turn there.
  trace("scenario", { name: "fork" });
  const forkResult = await client1.call("thread/fork", { threadId: threadA.id, cwd: fixture });
  const threadF = forkResult.result?.thread;
  assert(threadF?.id, `fork: ${JSON.stringify(forkResult.error)}`);
  trace("thread.forked", { origin: threadA.id, fork: threadSummary(threadF) });
  assert.notEqual(threadF.id, threadA.id);
  const forkTurn = await runTurn(client1, threadF.id, "SPIKE:fork");
  const forkStart = hooks().slice(forkTurn.hooksBefore).find((record) => record.event === "SessionStart");
  const forkShell = command("fork");
  trace("fork.identity", { forkId: threadF.id, forkSessionId: threadF.sessionId, forkedFromId: threadF.forkedFromId, startSource: forkStart?.payload.source ?? null, startSessionId: forkStart?.payload.session_id ?? null,
    startPayloadKeys: forkStart?.payloadKeys ?? null, shellEnv: forkShell?.env ?? null });
  assert(forkStart && forkStart.payload.session_id === threadF.id, "fork publishes its own SessionStart id");
  assert.equal(forkShell.env.CODEX_THREAD_ID, threadF.id);

  // Scenario 3: a sub-agent spawned inside thread A runs its own command.
  trace("scenario", { name: "subagent" });
  const delegateTurn = await runTurn(client1, threadA.id, "SPIKE:delegate", { timeout: 90000 });
  const childShell = command("child");
  assert(childShell, "child command ran");
  const subagentHooks = hooks().slice(delegateTurn.hooksBefore);
  const subagentStart = subagentHooks.find((record) => record.event === "SubagentStart");
  const subagentStop = subagentHooks.find((record) => record.event === "SubagentStop");
  const childToolHooks = subagentHooks.filter((record) => record.payload.agent_id !== undefined && record.event.endsWith("ToolUse"));
  const childSessionStart = subagentHooks.filter((record) => record.event === "SessionStart");
  const childThreadId = childShell.env.CODEX_THREAD_ID;
  const childRead = await client1.call("thread/read", { threadId: childThreadId });
  const loadedWithChild = (await client1.call("thread/loaded/list", {})).result?.data ?? [];
  trace("subagent.identity", { parentThreadId: threadA.id, childShellEnv: childShell.env, childShellCwd: childShell.cwd, childShellAncestry: childShell.ancestry.slice(0, 4),
    subagentStart: subagentStart?.payload ?? null, subagentStop: subagentStop ? { payload: subagentStop.payload, keys: subagentStop.payloadKeys } : null,
    childToolHooks: childToolHooks.map((record) => [record.event, record.payload.session_id, record.payload.agent_id, record.payload.agent_type, record.payload.cwd]),
    sessionStartsDuringDelegate: childSessionStart.map((record) => [record.payload.session_id, record.payload.source]),
    childThread: threadSummary(childRead.result?.thread), childReadError: childRead.error ?? null, loadedWithChild, otherThreadHooks: hooksSince(delegateTurn.hooksBefore) });
  assert(subagentStart && subagentStop, "subagent hooks");
  assert.equal(childShell.env.CODEX_SESSION_ID, threadA.id, "child shell keeps the root session id");
  assert.notEqual(childThreadId, threadA.id, "child shell carries its own thread id");
  assert(childShell.ancestry.some((entry) => entry.pid === server.pid), "child shell descends from the same app-server");

  // Scenario 4: a second client attaches to loaded threads; the first leaves mid-turn.
  trace("scenario", { name: "second-client-attach" });
  const client2 = await connect(server, "two");
  const hooksBeforeAttach = hooks().length;
  const attachA = await client2.call("thread/resume", { threadId: threadA.id });
  const attachB = await client2.call("thread/resume", { threadId: threadB.id });
  const attachF = await client2.call("thread/resume", { threadId: threadF.id });
  await delay(1000);
  trace("client.attach", { a: threadSummary(attachA.result?.thread), b: threadSummary(attachB.result?.thread), f: threadSummary(attachF.result?.thread), errors: [attachA.error, attachB.error, attachF.error].filter(Boolean),
    newHooks: hooksSince(hooksBeforeAttach), loaded: (await client2.call("thread/loaded/list", {})).result?.data ?? [] });
  assert.equal(attachB.result?.thread?.id, threadB.id);
  assert.equal(hooks().length, hooksBeforeAttach, "attaching to a loaded thread publishes no hook");
  const longB = await runTurn(client1, threadB.id, "SPIKE:root-b-long hold=6000", { detached: true });
  await waitFor(() => command("root-b-long"), "long command start", 30000);
  client1.close();
  const closed1 = await client1.closed;
  trace("client.close", { client: "one", ...closed1, turnId: longB.turnId, commandPid: command("root-b-long").pid });
  await waitFor(() => client2.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === longB.turnId), "long turn completes for the remaining client", 60000);
  const longEnd = command("root-b-long", "end");
  const longCompleted = client2.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === longB.turnId);
  trace("client.departure", { commandEnded: Boolean(longEnd), turnStatus: longCompleted.status, newHooks: hooksSince(longB.hooksBefore), loaded: (await client2.call("thread/loaded/list", {})).result?.data ?? [] });
  assert(longEnd && longCompleted.status === "completed", "the turn outlives the client that started it");
  assert(!hooks().slice(longB.hooksBefore).some((record) => ["Interrupt", "SessionEnd"].includes(record.event)), "no Interrupt or SessionEnd when a client leaves");

  // Scenario 5: interrupt a running turn.
  trace("scenario", { name: "interrupt" });
  const interruptTurn = await runTurn(client2, threadB.id, "SPIKE:interrupt hold=30000", { detached: true });
  await waitFor(() => command("interrupt"), "interrupt command start", 30000);
  const interruptedPid = command("interrupt").pid;
  const interrupted = await client2.call("turn/interrupt", { threadId: threadB.id, turnId: interruptTurn.turnId });
  await waitFor(() => client2.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === interruptTurn.turnId), "interrupted turn settles", 30000);
  await delay(1500);
  const interruptCompleted = client2.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === interruptTurn.turnId);
  trace("interrupt.result", { response: interrupted.result ?? interrupted.error, turnStatus: interruptCompleted.status, commandEnded: Boolean(command("interrupt", "end")), commandAlive: existsSync(`/proc/${interruptedPid}`),
    newHooks: hooksSince(interruptTurn.hooksBefore), interruptHook: hooks().slice(interruptTurn.hooksBefore).find((record) => record.event === "Interrupt")?.payload ?? null });
  assert(hooks().slice(interruptTurn.hooksBefore).some((record) => record.event === "Interrupt" && record.payload.session_id === threadB.id && record.payload.turn_id === interruptTurn.turnId), "Interrupt hook names the thread and turn");

  // Scenario 6: leave the fork without subscribers and time its unload.
  trace("scenario", { name: "unsubscribe-unload" });
  const unsubscribe = await client2.call("thread/unsubscribe", { threadId: threadF.id });
  const unsubscribedAt = Date.now();
  trace("thread.unsubscribe", { threadId: threadF.id, response: unsubscribe.result ?? unsubscribe.error });

  // Scenario 7: ordinary `codex exec` processes share the CODEX_HOME beside the server.
  trace("scenario", { name: "exec-cli" });
  const hooksBeforeExec = hooks().length;
  const exec = await codex(["exec", "--json", "--skip-git-repo-check", "-C", fixture, "SPIKE:exec"], { timeout: 60000 });
  const execThreadId = exec.events.find((event) => event.type === "thread.started")?.threadId ?? null;
  const execShell = command("exec");
  const execHooks = hooks().slice(hooksBeforeExec);
  trace("exec.identity", { pid: exec.pid, status: exec.status, threadId: execThreadId, shellEnv: execShell?.env ?? null, shellCwd: execShell?.cwd ?? null, shellAncestry: execShell?.ancestry.slice(0, 4) ?? null,
    hooks: execHooks.map((record) => [record.event, record.payload.session_id, record.payload.source ?? record.payload.reason ?? null, record.payload.cwd, record.ancestry.some((entry) => entry.pid === exec.pid), record.ancestry.some((entry) => entry.pid === server.pid)]) });
  assert.equal(exec.status, 0, `exec exit ${exec.status}: ${exec.stderr}`);
  assert(execThreadId && execShell && execShell.env.CODEX_THREAD_ID === execThreadId, "exec shell carries the exec thread id");
  assert(execShell.ancestry.some((entry) => entry.pid === exec.pid) && !execShell.ancestry.some((entry) => entry.pid === server.pid), "exec shell descends from the exec process, not the server");
  assert(execHooks.some((record) => record.event === "SessionEnd" && record.payload.session_id === execThreadId), "exec publishes SessionEnd at exit");
  const hooksBeforeResume = hooks().length;
  // `exec resume` has no `-C`; the process itself starts in the other Worktree.
  const execResume = await codex(["exec", "resume", "--json", "--skip-git-repo-check", execThreadId, "SPIKE:exec-resumed"], { cwd: other, timeout: 60000 });
  const resumedShell = command("exec-resumed");
  const resumeStart = hooks().slice(hooksBeforeResume).find((record) => record.event === "SessionStart");
  trace("exec.resume", { pid: execResume.pid, status: execResume.status, threadId: execThreadId, startSource: resumeStart?.payload.source ?? null, startSessionId: resumeStart?.payload.session_id ?? null, startCwd: resumeStart?.payload.cwd ?? null,
    shellEnv: resumedShell?.env ?? null, shellCwd: resumedShell?.cwd ?? null, newHooks: hooksSince(hooksBeforeResume) });
  assert.equal(execResume.status, 0, `exec resume exit ${execResume.status}: ${execResume.stderr}`);
  assert(resumeStart && resumeStart.payload.session_id === execThreadId && resumeStart.payload.source === "resume", "exec resume keeps the thread id with source resume");
  assert(resumedShell, "resumed exec ran its command");

  // Scenario 8: a competing resume of a thread the server holds loaded.
  trace("scenario", { name: "competing-resume" });
  const hooksBeforeCompete = hooks().length;
  const locksBefore = lockFiles();
  const compete = await codex(["exec", "resume", "--json", "--skip-git-repo-check", threadA.id, "SPIKE:compete"], { timeout: 60000 });
  await delay(1000);
  const competeOutput = (compete.stderr + compete.stdout).replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "");
  trace("compete.result", { route: "exec resume", status: compete.status, signal: compete.signal, conflict: /active writer/i.test(competeOutput), commandRan: Boolean(command("compete")), newHooks: hooksSince(hooksBeforeCompete), locks: locksBefore,
    message: competeOutput.split("\n").find((line) => /active writer|error/i.test(line))?.slice(0, 300) ?? null });
  assert.notEqual(compete.status, 0, "competing exec resume of a loaded thread is refused");
  assert(!command("compete"), "the refused resume runs no command");
  // A second app-server on the same CODEX_HOME asks for the same thread.
  const competitor = await startServer("competitor");
  const clientX = await connect(competitor, "competitor");
  const competeResume = await clientX.call("thread/resume", { threadId: threadA.id });
  const competeRead = await clientX.call("thread/read", { threadId: threadA.id });
  await delay(500);
  trace("compete.result", { route: "app-server thread/resume", error: competeResume.error ?? null, resumed: threadSummary(competeResume.result?.thread), read: threadSummary(competeRead.result?.thread), newHooks: hooksSince(hooksBeforeCompete) });
  assert(competeResume.error, "a second app-server cannot resume the loaded thread");
  process.kill(competitor.pid, "SIGTERM");
  await Promise.race([competitor.exit, delay(15000)]);

  // Scenario 6 continued: wait for the fork's unload after its last subscriber left.
  trace("scenario", { name: "unsubscribe-unload-wait" });
  const forkEnded = () => hooks().some((record) => record.event === "SessionEnd" && record.payload.session_id === threadF.id);
  let unloadError = null;
  try { await waitFor(forkEnded, "fork SessionEnd after unsubscribe", Math.max(1000, 110000 - (Date.now() - unsubscribedAt))); } catch (error) { unloadError = String(error); }
  const forkEnd = hooks().find((record) => record.event === "SessionEnd" && record.payload.session_id === threadF.id);
  trace("unload.result", { threadId: threadF.id, ended: Boolean(forkEnd), elapsedMs: forkEnd ? forkEnd.receiptTime - unsubscribedAt : null, reason: forkEnd?.payload.reason ?? null, error: unloadError,
    closedNotifications: client2.notifications.filter((entry) => entry.method === "thread/closed").map((entry) => [entry.threadId, entry.receivedAt - unsubscribedAt]),
    loaded: (await client2.call("thread/loaded/list", {})).result?.data ?? [] });

  // Scenario 9: the server dies abruptly with threads loaded.
  trace("scenario", { name: "abrupt-server-exit" });
  const hooksBeforeKill = hooks().length;
  const locksAtKill = lockFiles();
  const loadedAtKill = (await client2.call("thread/loaded/list", {})).result?.data ?? null;
  process.kill(server.pid, "SIGKILL");
  trace("action.kill", { pid: server.pid, signal: "SIGKILL", loadedBefore: loadedAtKill, locks: locksAtKill });
  const serverExit = await server.exit;
  const closed2 = await client2.closed;
  await delay(3000);
  snapshot("after-server-kill");
  trace("kill.result", { serverExit, clientClose: closed2, newHooks: hooksSince(hooksBeforeKill), locksAfter: lockFiles(), leftover: codexProcesses().map((entry) => [entry.pid, entry.ppid, entry.comm, entry.cmdline]) });
  assert(!hooks().slice(hooksBeforeKill).some((record) => record.event === "SessionEnd"), "no SessionEnd after SIGKILL");

  // Scenario 10: a replacement server resumes the stored thread in another Worktree.
  trace("scenario", { name: "stored-thread-resume" });
  replacement = await startServer("replacement");
  const client3 = await connect(replacement, "three");
  const read = await client3.call("thread/read", { threadId: threadA.id });
  const hooksBeforeStored = hooks().length;
  const resumedA = await client3.call("thread/resume", { threadId: threadA.id, cwd: other });
  trace("thread.resumed", { read: threadSummary(read.result?.thread), readError: read.error ?? null, resumed: threadSummary(resumedA.result?.thread), error: resumedA.error ?? null, hooksAtResume: hooksSince(hooksBeforeStored) });
  assert.equal(resumedA.result?.thread?.id, threadA.id, `stored thread resumes: ${JSON.stringify(resumedA.error)}`);
  const storedTurn = await runTurn(client3, threadA.id, "SPIKE:root-a-stored");
  const storedStart = hooks().slice(hooksBeforeStored).find((record) => record.event === "SessionStart");
  const storedShell = command("root-a-stored");
  trace("stored.identity", { startSource: storedStart?.payload.source ?? null, startSessionId: storedStart?.payload.session_id ?? null, startCwd: storedStart?.payload.cwd ?? null, shellCwd: storedShell?.cwd ?? null, shellEnv: storedShell?.env ?? null,
    shellAncestry: storedShell?.ancestry.slice(0, 4) ?? null, replacementPid: replacement.pid, locks: lockFiles() });
  assert(storedStart && storedStart.payload.session_id === threadA.id && storedStart.payload.source === "resume", "stored resume publishes SessionStart resume");
  assert(storedShell.ancestry.some((entry) => entry.pid === replacement.pid), "stored resume runs under the replacement server");
  assert.equal(storedShell.cwd, other, "the resume cwd override relocates the thread");

  // Scenario 11: graceful server exit ends the loaded thread.
  trace("scenario", { name: "graceful-server-exit" });
  const hooksBeforeTerm = hooks().length;
  process.kill(replacement.pid, "SIGTERM");
  const replacementExit = await Promise.race([replacement.exit, delay(30000).then(() => ({ timeout: true }))]);
  await delay(1500);
  trace("graceful.result", { exit: replacementExit, newHooks: hooksSince(hooksBeforeTerm), locksAfter: lockFiles(), leftover: codexProcesses().map((entry) => [entry.pid, entry.comm, entry.cmdline]) });
  assert(hooks().slice(hooksBeforeTerm).some((record) => record.event === "SessionEnd" && record.payload.session_id === threadA.id), "graceful exit publishes SessionEnd");

  console.log(`All scenarios completed: ${root}`);
} finally {
  for (const running of [server, replacement]) { if (running && running.child.exitCode === null && running.child.signalCode === null) { try { process.kill(running.pid, "SIGKILL"); } catch {} } }
  await delay(500);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
