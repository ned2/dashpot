// Sandbox run for Issue #637: drives a pinned Codex CLI under its
// `workspace-write` sandbox against a loopback Responses API fixture, with an
// isolated CODEX_HOME, in a disposable repository whose linked Worktrees sit
// beside it as `<repository>.worktrees/<name>`, as `dashpot worktree create`
// places them. Lead threads on a loopback app-server spawn workers under both
// of Codex's tool sets, and each lead and worker runs `probe.mjs`, which tries
// every write the execute-issues skill's messaging needs and one commit, then
// prints its outcomes. It measures where a lead and a worker can write and
// commit with no writable roots configured, with the Worktrees directory as a
// writable root, and with the main checkout's Git directory added too; where
// a lead bound in a linked Worktree can write; and whether a v2 lead's
// `send_message` reaches a worker that is still running. Each step's model
// requests and probe outcomes are recorded as a metadata-only trace.
//
//   node run.mjs <absolute codex binary> [expected version]
//   node verify.mjs <trace.jsonl> [expected version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Codex binary");
const expectedVersion = process.argv[3] ?? "0.160.0";
// A fixture below a harness session would run inside that session's own
// sandbox, if it has one, and its processes would join that session's tree.
const harnessAbove = ancestry(process.ppid, 64, 1).find((entry) => entry.comm.startsWith("codex") || entry.comm === "claude"
  || entry.comm === "opencode" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!harnessAbove, `Run this outside every harness session (for example with \`setsid -f\`): pid ${harnessAbove?.pid} is ${harnessAbove?.comm}`);

const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-637-"));
console.log(`Isolated fixture: ${root}`);
const main = path.join(root, "repository");
const worktreesDir = path.join(root, "repository.worktrees");
// A directory outside every writable root: the probe's control write.
const outside = path.join(root, "outside");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The operator's home directory, host name and the fixture's temporary root
// never enter the trace.
const home = os.homedir();
const hostName = new RegExp(`\\b${os.hostname().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g");
const clean = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(home, "~").replace(hostName, "<host>");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, clean(JSON.stringify(record)) + "\n");
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
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CODEX_HOME: path.join(root, "codex-home"),
  TERM: "dumb",
};
for (const dir of [main, worktreesDir, outside, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CODEX_HOME]) mkdirSync(dir, { recursive: true });
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `codex-cli ${expectedVersion}`, `unexpected Codex version: ${version}`);

// The disposable repository: the main checkout holds the mail directory
// proposed for #637 inside an Arc's ledger directory, with a broadcast in it, and each probe gets a Worktree of its
// own, with no `.dashpot/state/` yet, so a probe's commit and its first
// state write meet a fresh Worktree.
const git = (...args) => execFileSync("git", ["-C", main, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(main, "README.md"), "Disposable fixture.\n");
const mailDir = path.join(main, ".dashpot", "state", "skills", "dashpot-execute-issues", "arcs", "fixture", "mail");
mkdirSync(mailDir, { recursive: true });
writeFileSync(path.join(main, ".dashpot", "state", ".gitignore"), "*\n");
writeFileSync(path.join(mailDir, "broadcast.md"), "## 1 fixture\nBROADCAST\n-- end 1\n");
git("add", "README.md");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
const probeLabels = ["lead-v2", "worker-v2", "worker-v1", "lead-roots", "worker-roots", "worker-v1-roots", "lead-git", "worker-git", "lead-linked"];
const worktreeOf = (label) => path.join(worktreesDir, label);
for (const label of probeLabels) git("worktree", "add", "-b", label, worktreeOf(label));

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

// The fixture model is scripted per directive, as in the codex-420 run. The
// latest input item that is not a tool call and carries `SPIKE:<label>`
// selects the plan `plans[label]`; the number of tool outputs after that item
// selects the step. When the plan runs out, the model answers `DONE:<label>`.
// A lead's message to a worker is `NOTE:<label>`, and every request records
// which markers its input carries, where, and in which kind of item.
const probeScript = path.join(here, "probe.mjs");
const plans = {
  // No writable roots: the v2 lead probes from the main checkout, against a
  // Worktree of its own, then spawns a worker that probes its Worktree.
  "lead-v2": [{ probe: true }, { spawn: ["worker_a", "worker-v2"] }],
  "worker-v2": [{ probe: true }],
  // The v1 lead only spawns: a lead's own shell does not depend on its tool set.
  "lead-v1": [{ spawn: ["-", "worker-v1"] }],
  "worker-v1": [{ probe: true }],
  // The Worktrees directory as a writable root.
  "lead-roots": [{ probe: true }, { spawn: ["worker_b", "worker-roots"] }],
  "worker-roots": [{ probe: true }],
  "lead-v1-roots": [{ spawn: ["-", "worker-v1-roots"] }],
  "worker-v1-roots": [{ probe: true }],
  // The Worktrees directory and the main checkout's Git directory.
  "lead-git": [{ probe: true }, { spawn: ["worker_c", "worker-git"] }],
  "worker-git": [{ probe: true }],
  // A lead bound in a linked Worktree probes the main checkout's mail.
  "lead-linked": [{ probe: true }],
  // A message to a running worker: the worker sleeps through two commands
  // while the lead sends it a message during the first, then waits.
  "lead-message": [{ spawn: ["worker_s", "worker-message"] }, { sleep: 2 }, { send: ["/root/worker_s", "NOTE:to-worker"] }, { wait: 60000 }],
  "worker-message": [{ sleep: 8 }, { sleep: 1 }],
};
const markerPattern = /(SPIKE|NOTE|DONE):([a-z0-9_-]+)/g;
const isCall = (item) => /(_call|_call_output)$/.test(item.type ?? "");
const isCallOutput = (item) => /_call_output$/.test(item.type ?? "");
const parseJson = (text) => { try { return JSON.parse(text); } catch { return null; } };
const outputText = (item) => typeof item.output === "string" ? item.output : JSON.stringify(item.output ?? "");
const probes = new Map();
const modelRequests = [];
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
  const thread = payload.client_metadata?.thread_id ?? req.headers["thread_id"] ?? null;
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
  // A probe's outcome line, from whichever tool output carries it.
  for (const item of input.filter(isCallOutput)) {
    for (const match of outputText(item).matchAll(/PROBE (\{.*\})/g)) {
      const report = parseJson(match[1]);
      if (report && !probes.has(report.label)) { probes.set(report.label, report); trace("probe", { thread, report }); }
    }
  }
  const outputs = input.slice(directiveAt + 1).filter(isCallOutput);
  const tools = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested.name]) : [[null, tool.name ?? tool.type]]);
  const offered = (name) => tools.find(([, toolName]) => toolName === name) ?? null;
  const v2 = Boolean(offered("list_agents"));
  const spawnCalls = input.filter((item) => item.type === "function_call" && item.name === "spawn_agent");
  const spawnedIds = () => spawnCalls.map((spawned) => parseJson(input.find((item) => item.type === "function_call_output" && item.call_id === spawned.call_id)?.output)?.agent_id).filter(Boolean);
  const plan = label ? plans[label] ?? [] : [];
  const step = plan[outputs.length] ?? null;
  const toolCall = (name, args) => {
    const tool = offered(name);
    return tool && { type: "function_call", call_id: `call_${label}_${outputs.length}_${modelRequests.length}`, ...(tool[0] ? { namespace: tool[0] } : {}), name, arguments: JSON.stringify(args) };
  };
  let item = null;
  let action = null;
  if (step?.probe) {
    action = "exec_command";
    const worktree = worktreeOf(label);
    // A worker reaches its Worktree by a per-command `cd`; a lead probes
    // from where its thread started.
    const cd = label.startsWith("worker") ? `cd ${worktree} && ` : "";
    item = toolCall("exec_command", { cmd: `${cd}node ${probeScript} ${label} ${main} ${worktree} ${outside}`, login: false, yield_time_ms: 60000 });
  } else if (step?.sleep) {
    action = "exec_command";
    item = toolCall("exec_command", { cmd: `sleep ${step.sleep}`, login: false, yield_time_ms: 60000 });
  } else if (step?.spawn) {
    const [taskName, child] = step.spawn;
    action = "spawn_agent";
    item = toolCall("spawn_agent", v2 ? { message: `SPIKE:${child}`, task_name: taskName, fork_turns: "none" } : { message: `SPIKE:${child}` });
  } else if (step?.send) {
    const [target, text] = step.send;
    action = "send_message";
    item = toolCall("send_message", { target, message: text });
  } else if (step?.wait) {
    action = "wait_agent";
    item = toolCall("wait_agent", v2 ? { timeout_ms: step.wait } : { targets: spawnedIds(), timeout_ms: step.wait });
  }
  const latestOutput = input.slice(directiveAt + 1).findLast(isCallOutput);
  const request = trace("model.request", { thread, label, step: outputs.length, inputItems: input.length, directiveAt, markers, action, missing: Boolean(step && !item), v2,
    lastOutput: latestOutput ? clean(outputText(latestOutput)).slice(0, 400) : null, tail: input.slice(-3).map((entry) => [entry.type ?? null, entry.role ?? null]) });
  modelRequests.push(request);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  const responseId = `resp_${records.length}`;
  sse(res, { type: "response.created", response: { id: responseId } });
  sse(res, { type: "response.output_item.done", item: item ?? { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: label ? `DONE:${label}` : "Fixture complete." }] } });
  sse(res, { type: "response.completed", response: { id: responseId, usage: { input_tokens: 10, input_tokens_details: null, output_tokens: 4, output_tokens_details: null, total_tokens: 14 } } });
  res.end();
});

// The model catalog: `fixture-v2` declares multi-agent v2, and the unnamed
// `fixture-model` gets v1, as in the codex-420 run.
const bundled = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }));
const base = bundled.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base, "a bundled model without a tool set or code mode");
const catalogPath = path.join(env.CODEX_HOME, "fixture-models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture v2", multi_agent_version: "v2", prefer_websockets: false }] }, null, 2));

// The sandbox under test. The fixture lives under the system temporary
// directory, which `workspace-write` makes writable by default; excluding it
// and TMPDIR models a checkout outside it, as a person's checkout is.
const configPath = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(configPath, `model = "fixture-model"
model_catalog_json = "${catalogPath}"
approval_policy = "never"
sandbox_mode = "workspace-write"
model_provider = "fixture"

[sandbox_workspace_write]
network_access = false
exclude_slash_tmp = true
exclude_tmpdir_env_var = true

[features]
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
${[main, ...probeLabels.map(worktreeOf)].map((dir) => `\n[projects."${dir}"]\ntrust_level = "trusted"\n`).join("")}`);
// The fixture daemon's updater stays off, though this run starts no daemon.
const daemonSettingsPath = path.join(env.CODEX_HOME, "app-server-daemon", "settings.json");
mkdirSync(path.dirname(daemonSettingsPath), { recursive: true });
writeFileSync(daemonSettingsPath, JSON.stringify({ updater: { autoUpdateEnabled: false } }));

// Every process whose environment names the fixture CODEX_HOME.
const codexProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let entry;
    try { entry = describe(Number(name)); } catch { continue; }
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CODEX_HOME=${env.CODEX_HOME}`) || entry.pid === process.pid) continue;
    found.push(entry);
  }
  return found;
};
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quietly = (promise) => promise.then(() => true, () => false);
const freePort = async () => {
  const probe = net.createServer();
  probe.listen(0, "127.0.0.1");
  await once(probe, "listening");
  const port = probe.address().port;
  probe.close();
  return port;
};
const rpcClient = async (name, port) => {
  const socket = new WebSocket(`ws://127.0.0.1:${port}`);
  await once(socket, "open");
  let nextId = 0;
  const pending = new Map();
  const notifications = [];
  socket.addEventListener("message", (message) => {
    const parsed = parseJson(message.data);
    if (parsed === null) return;
    if (parsed.id !== undefined && pending.has(parsed.id)) { pending.get(parsed.id)(parsed); pending.delete(parsed.id); return; }
    if (parsed.method?.startsWith("turn/")) notifications.push({ method: parsed.method, threadId: parsed.params?.threadId, turnId: parsed.params?.turn?.id, status: parsed.params?.turn?.status, receivedAt: Date.now() });
  });
  const call = (method, params = {}) => Promise.race([
    new Promise((resolve) => { const id = ++nextId; pending.set(id, resolve); socket.send(JSON.stringify({ id, method, params })); }),
    delay(30000).then(() => ({ error: { message: `${method} timed out` } })),
  ]);
  const init = await call("initialize", { clientInfo: { name: `dashpot-637-${name}`, version: "0" }, capabilities: { experimentalApi: true } });
  socket.send(JSON.stringify({ method: "initialized", params: {} }));
  assert(init.result, `${name} initialized: ${JSON.stringify(init)}`);
  return { name, call, notifications, close: () => socket.close() };
};
const runTurn = async (client, threadId, text, timeout = 60000) => {
  const startedAt = Date.now();
  const started = await client.call("turn/start", { threadId, input: [{ type: "text", text }] });
  const turnId = started.result?.turn?.id;
  trace("turn.start", { threadId, turnId, label: text, error: started.error ?? null });
  assert(turnId, `turn started: ${JSON.stringify(started.error)}`);
  await waitFor(() => client.notifications.some((entry) => entry.method === "turn/completed" && entry.turnId === turnId), `turn ${text} completed`, timeout);
  const completed = client.notifications.find((entry) => entry.method === "turn/completed" && entry.turnId === turnId);
  trace("turn.completed", { threadId, turnId, status: completed.status, completedAt: completed.receivedAt });
  return { turnId, startedAt, completedAt: completed.receivedAt };
};
const startThread = async (client, name, params) => {
  const started = await client.call("thread/start", { cwd: main, ...params });
  const thread = started.result?.thread;
  trace("thread.start", { name, params: { ...params, cwd: params.cwd ?? main }, thread: thread && { id: thread.id, cwd: thread.cwd ?? null, model: thread.model ?? null },
    sandbox: started.result?.sandbox ?? null, error: started.error ?? null });
  assert(thread?.id, `${name} started: ${JSON.stringify(started.error)}`);
  return thread.id;
};
const probed = (label, timeout = 60000) => quietly(waitFor(() => probes.has(label), `probe ${label}`, timeout));
const requestsOf = (label) => modelRequests.filter((record) => record.label === label);

const scripts = ["run.mjs", "probe.mjs", "verify.mjs", "ancestry.mjs"];
let server = null;
let client = null;
try {
  const head = execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const dirty = execFileSync("git", ["-C", checkout, "status", "--porcelain"], { encoding: "utf8" }).trim() !== "";
  let bwrap = null;
  try { bwrap = execFileSync("bwrap", ["--version"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim(); } catch {}
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, bwrap,
    binaryTarget: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), dashpot: { head, dirty },
    main, worktreesDir, outside, probeLabels, fixtureCatalog: { base: base.slug, slug: "fixture-v2", multi_agent_version: "v2" },
    sourceSHA256: Object.fromEntries(scripts.map((file) => [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  const port = await freePort();
  server = spawn("codex", ["app-server", "--listen", `ws://127.0.0.1:${port}`], { cwd: main, env, stdio: ["ignore", "pipe", "pipe"] });
  let banner = "";
  server.stderr.on("data", (chunk) => { banner += chunk; });
  server.stdout.on("data", () => {});
  await waitFor(() => banner.includes("listening on"), "app-server listening", 20000);
  client = await rpcClient("controller", port);

  // Q1 and Q2 with no writable roots configured.
  trace("scenario", { name: "default" });
  const leadV2 = await startThread(client, "lead-v2", { model: "fixture-v2" });
  await runTurn(client, leadV2, "SPIKE:lead-v2");
  const leadV1 = await startThread(client, "lead-v1", { model: "fixture-model" });
  await runTurn(client, leadV1, "SPIKE:lead-v1");
  for (const label of ["lead-v2", "worker-v2", "worker-v1"]) await probed(label);

  // Q1 and Q2 with the Worktrees directory as a writable root, for the
  // lead's thread; whether its workers inherit it is part of the answer.
  trace("scenario", { name: "roots" });
  const roots = { "sandbox_workspace_write.writable_roots": [worktreesDir] };
  const leadRoots = await startThread(client, "lead-roots", { model: "fixture-v2", config: roots });
  await runTurn(client, leadRoots, "SPIKE:lead-roots");
  const leadV1Roots = await startThread(client, "lead-v1-roots", { model: "fixture-model", config: roots });
  await runTurn(client, leadV1Roots, "SPIKE:lead-v1-roots");
  for (const label of ["lead-roots", "worker-roots", "worker-v1-roots"]) await probed(label);

  // Q2: the main checkout's Git directory as a writable root as well.
  trace("scenario", { name: "git-roots" });
  const leadGit = await startThread(client, "lead-git", { model: "fixture-v2", config: { "sandbox_workspace_write.writable_roots": [worktreesDir, path.join(main, ".git")] } });
  await runTurn(client, leadGit, "SPIKE:lead-git");
  for (const label of ["lead-git", "worker-git"]) await probed(label);

  // A lead bound in a linked Worktree, with no writable roots.
  trace("scenario", { name: "linked-lead" });
  const leadLinked = await startThread(client, "lead-linked", { model: "fixture-v2", cwd: worktreeOf("lead-linked") });
  await runTurn(client, leadLinked, "SPIKE:lead-linked");
  await probed("lead-linked");

  // Q5: the lead sends a message while its worker runs a command.
  trace("scenario", { name: "message" });
  const leadMessage = await startThread(client, "lead-message", { model: "fixture-v2" });
  const message = await runTurn(client, leadMessage, "SPIKE:lead-message", 120000);
  await quietly(waitFor(() => requestsOf("worker-message").some((record) => record.step === 2), "worker's last request", 30000));
  await delay(1000);
  trace("message.outcome", { lead: leadMessage, turn: message.turnId,
    lead_requests: requestsOf("lead-message").map((record) => ({ receiptTime: record.receiptTime, step: record.step, action: record.action, lastOutput: record.lastOutput })),
    worker_requests: requestsOf("worker-message").map((record) => ({ thread: record.thread, receiptTime: record.receiptTime, step: record.step, action: record.action,
      markers: record.markers, tail: record.tail })) });

  trace("probes.outcome", { missing: probeLabels.filter((label) => !probes.has(label)), probes: Object.fromEntries(probes) });
  console.log(`All scenarios completed: ${root}`);
} finally {
  try { client?.close(); } catch {}
  if (server && server.exitCode === null) { server.kill("SIGTERM"); await quietly(Promise.race([once(server, "exit"), delay(5000)])); }
  await delay(500);
  for (const entry of codexProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
