// Measure waiting-parent approvals, reconnect, turn grants and Guardian stops
// for Issue #665 on Codex 0.162.0. Only disposable paths and a scripted local
// provider are used. Run detached with setsid -f, outside every harness.
//   node permissions-run.mjs <absolute retained codex binary>
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, spawnSync, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";
import { runReconnect } from "./permissions-reconnect.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "../../..");
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass an absolute retained release binary");
assert(!ancestry(process.ppid, 64, 1).some((entry) => /^(codex|claude|opencode)/.test(entry.comm)), "Run detached, outside every harness");
// The named profile has no implicit /tmp write grant. Its root-read rule
// keeps the fixture's outside paths protected even on a temporary filesystem.
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-codex-665-"));
console.log(`Isolated fixture: ${root}`);
const main = path.join(root, "repository");
const tree = path.join(root, "repository.worktrees", "worker");
const idleTree = path.join(root, "repository.worktrees", "idle");
const denied = path.join(root, "denied.txt");
const outside = path.join(root, "outside");
const grantA = path.join(root, "grant-a");
const grantB = path.join(root, "grant-b");
const fixtureHome = path.join(root, "home");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const clean = (text) => String(text).replaceAll(fixtureHome, "$HOME").replaceAll(root, "$ROOT")
  .replaceAll(path.basename(root), "<fixture>").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "~");
const trace = (kind, fields = {}) => {
  const entry = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(entry); appendFileSync(tracePath, clean(JSON.stringify(entry)) + "\n"); return entry;
};
const sha = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const waitFor = async (predicate, label, timeout = 30000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) { if (serverFailure) throw serverFailure; if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const quote = (text) => "'" + String(text).replaceAll("'", "'\\''") + "'";
const parse = (text) => { try { return JSON.parse(text); } catch { return null; } };
const bin = path.join(root, "bin");
for (const dir of [main, tree, outside, grantA, grantB, bin, fixtureHome]) mkdirSync(dir, { recursive: true });
symlinkSync(binary, path.join(bin, "codex"));
writeFileSync(denied, "Disposable denied-read sentinel.\n");
const env = { PATH: `${bin}:${path.dirname(process.execPath)}:/usr/bin:/bin`, HOME: fixtureHome,
  XDG_CONFIG_HOME: path.join(root, "config"), XDG_DATA_HOME: path.join(root, "data"), XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"), CODEX_HOME: path.join(root, "codex-home"),
  TERM: "xterm-256color", LANG: "C.UTF-8", SPIKE_STOP_PID: String(process.pid) };
const fixtureHomes = [env.CODEX_HOME, path.join(root, "reconnect-workspace"), path.join(root, "reconnect-full")];
mkdirSync(env.CODEX_HOME);
const version = execFileSync("codex", ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, "codex-cli 0.162.0");
const publisher = path.join(checkout, ".venv/bin/dashpot-codex-hook");
const dashpot = (args, cwd = main) => {
  const result = spawnSync(path.join(checkout, ".venv/bin/dashpot"), args, { cwd, env, encoding: "utf8", timeout: 30000 });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
};
const git = (...args) => execFileSync("git", ["-C", main, ...args], { env, encoding: "utf8", stdio: "pipe" });
git("init", "--initial-branch=main");
mkdirSync(path.join(main, "issues"));
const issue = { id: "I_fixture_665", number: 1, reference: "fixture-665", state: "open", stateReason: null,
  labels: [], assignees: [], author: null, relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] },
  issueType: null, milestone: null, createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z", closedAt: null };
writeFileSync(path.join(main, "issues/1.md"), `---\n${JSON.stringify(issue)}\n---\n# Fixture Issue\n\nDisposable.\n`);
assert.equal(dashpot(["init", "--markdown", "issues"]).status, 0);
git("add", "-A");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
// The empty directory is replaced only inside this disposable repository.
git("worktree", "add", "-b", "worker", tree);
git("worktree", "add", "-b", "idle", idleTree);

const children = [];
const start = (command, args, options = {}) => {
  const child = spawn(command, args, { cwd: main, env, stdio: ["pipe", "pipe", "pipe"], ...options });
  children.push(child); return child;
};
const network = net.createServer((socket) => socket.end());
network.listen(0, "127.0.0.1"); await once(network, "listening");
const port = network.address().port;
const probes = new Map();
const modelRequests = [];
const done = new Set();
const plans = new Map();
let serverFailure = null;
const outputs = (input) => input.filter((item) => /_call_output$/.test(item.type));
const textOf = (item) => typeof item.output === "string" ? item.output : JSON.stringify(item.output);
const strings = (value) => {
  if (typeof value === "string") { const decoded = parse(value); return decoded ? strings(decoded) : [value]; }
  return value && typeof value === "object" ? Object.values(value).flatMap(strings) : [];
};
const probeCommand = (label, target = path.join(outside, label), later = null) =>
  [process.execPath, path.join(here, "permissions-probe.mjs"), label, target, denied, String(port), ...(later ? [later] : [])].map(quote).join(" ");
const command = (cmd, extra = {}) => ({ name: "exec_command", args: { cmd, login: false, yield_time_ms: 1000, ...extra } });
const spawnWorker = (name) => ({ name: "spawn_agent", args: { task_name: "worker", fork_turns: "none", message: `SPIKE:${name}` } });
const model = http.createServer((req, res) => { handleRequest(req, res).catch((error) => {
  serverFailure = error;
  trace("server.error", { error: String(error.stack) });
  if (!res.headersSent) res.writeHead(500);
  res.end();
}); });
const handleRequest = async (req, res) => {
  const chunks = []; for await (const chunk of req) chunks.push(chunk);
  const payload = parse(Buffer.concat(chunks).toString()) ?? {};
  if (req.url === "/hook") { trace("hook", payload); res.end("ok"); return; }
  if (!req.url.endsWith("/responses")) { res.writeHead(404); res.end(); return; }
  const input = payload.input ?? [];
  const guardian = payload.client_metadata?.["x-openai-subagent"] === "guardian";
  let directive = -1, label = null;
  input.forEach((item, index) => {
    if (/_call(?:_output)?$/.test(item.type)) return;
    const matches = [...JSON.stringify(item).matchAll(/SPIKE:([a-z0-9-]+)/g)];
    if (matches.length) { directive = index; label = matches.at(-1)[1]; }
  });
  const offered = (payload.tools ?? []).flatMap((tool) => tool.type === "namespace" ? tool.tools.map((nested) => [tool.name, nested]) : [[null, tool]]);
  const tool = (name) => offered.find(([, item]) => item.name === name);
  const side = !tool("exec_command") && !tool("exec") && !guardian;
  const after = outputs(input.slice(directive + 1));
  const callNames = new Map(input.filter((item) => item.type === "function_call" || item.type === "custom_tool_call").map((item) => [item.call_id, item.name]));
  const planned = after.filter((item) => callNames.get(item.call_id) !== "write_stdin");
  const latest = after.at(-1);
  for (const output of after) for (const match of strings(output).join("\n").matchAll(/PROBE (\{[^\n]*\})/g)) {
    const report = parse(match[1]);
    if (report && !probes.has(report.label)) { probes.set(report.label, report); trace("probe", { report }); }
  }
  const running = latest && /Process running with session ID (\d+)/.exec(textOf(latest));
  let step = running ? { name: "write_stdin", args: { session_id: Number(running[1]), chars: "", yield_time_ms: 1000 } }
    : plans.get(label)?.[planned.length] ?? null;
  if (side || guardian) step = null;
  if (step?.assign) {
    await waitFor(() => records.some((r) => r.kind === "hook" && r.event === "SubagentStart" && r.payload.session_id === payload.client_metadata?.thread_id), "Worker native identity");
    const child = records.findLast((r) => r.kind === "hook" && r.event === "SubagentStart" && r.payload.session_id === payload.client_metadata?.thread_id).payload.agent_id;
    step = command(`${quote(path.join(checkout, ".venv/bin/dashpot"))} work assign 1 --worker ${quote(child)} --worktree ${quote(tree)}`);
  }
  const message = guardian
    ? JSON.stringify({ risk_level: "high", user_authorization: "low", outcome: "deny", rationale: "Harmless fixture denial, no real action authorized." })
    : `DONE:${label ?? "side"}`;
  if (guardian) trace("guardian.review", { thread: payload.client_metadata?.thread_id, decision: JSON.parse(message) });
  const request = trace("model.request", { label, guardian, side, thread: payload.client_metadata?.thread_id ?? null,
    metadata: payload.client_metadata, step: planned.length, action: step?.name ?? null,
    tools: offered.map(([ns, t]) => [ns, t.name, t.type]),
    outputs: after, messages: input.filter((item) => item.type === "agent_message"),
    permissions: input.filter((item) => !/_call(?:_output)?$/.test(item.type) && JSON.stringify(item).includes("permissions instructions")) });
  modelRequests.push(request);
  // Keep a possible continuation pending after three Guardian denials. The
  // circuit breaker, rather than a scripted final answer, ends that Worker.
  if (!guardian && !side && label?.startsWith("worker-guardian") && planned.length >= 4) {
    res.writeHead(200, { "content-type": "text/event-stream" }); res.write(": awaiting circuit breaker\n\n"); return;
  }
  let item;
  if (step) {
    const found = tool(step.name);
    assert(found, `${label}: missing ${step.name}`);
    item = { type: step.code ? "custom_tool_call" : "function_call", call_id: `call_${records.length}`,
      ...(found[0] ? { namespace: found[0] } : {}), name: step.name,
      ...(step.code ? { input: step.code } : { arguments: JSON.stringify(step.args) }) };
  } else {
    if (!guardian && !side && label) done.add(label);
    item = { type: "message", role: "assistant", id: `msg_${records.length}`, content: [{ type: "output_text", text: message }] };
  }
  res.writeHead(200, { "content-type": "text/event-stream" });
  for (const event of [{ type: "response.created", response: { id: `resp_${records.length}` } },
    { type: "response.output_item.done", item }, { type: "response.completed", response: { id: `resp_${records.length}`,
      usage: { input_tokens: 10, output_tokens: 4, total_tokens: 14 } } }]) res.write(`event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
  res.end();
};
model.listen(0, "127.0.0.1"); await once(model, "listening");
const modelURL = `http://127.0.0.1:${model.address().port}`;
env.SPIKE_SINK = modelURL; env.SPIKE_PUBLISHER = publisher;
const catalog = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], { env, encoding: "utf8" }));
const base = catalog.models.find((entry) => !entry.multi_agent_version && !entry.tool_mode);
assert(base);
const catalogPath = path.join(env.CODEX_HOME, "models.json");
writeFileSync(catalogPath, JSON.stringify({ models: [{ ...base, slug: "fixture-v2", display_name: "Fixture",
  multi_agent_version: "v2", auto_review_model_override: "fixture-v2", prefer_websockets: false }] }));
const hooks = Object.keys(JSON.parse(readFileSync(path.join(checkout, "examples/codex-hooks.json"))).hooks);
writeFileSync(path.join(env.CODEX_HOME, "hooks.json"), JSON.stringify({ hooks: Object.fromEntries(hooks.map((event) => [event,
  [{ hooks: [{ type: "command", command: [process.execPath, path.join(here, "permissions-hook.mjs")].map(quote).join(" "), timeout: 15 }] }]])) }));
const config = path.join(env.CODEX_HOME, "config.toml");
writeFileSync(config, `model = "fixture-v2"
model_catalog_json = ${JSON.stringify(catalogPath)}
model_provider = "fixture"
approval_policy = "on-request"
approvals_reviewer = "user"
default_permissions = "fixture"
check_for_update_on_startup = false
suppress_unstable_features_warning = true
[features]
multi_agent = true
multi_agent_v2 = true
hooks = true
plugins = false
apps = false
request_permissions_tool = true
guardian_approval = true
[analytics]
enabled = false
[model_providers.fixture]
name = "Fixture"
base_url = "${modelURL}/v1"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
[projects.${JSON.stringify(main)}]
trust_level = "trusted"
[projects.${JSON.stringify(tree)}]
trust_level = "trusted"
[permissions.fixture.filesystem]
":root" = "read"
${JSON.stringify(main)} = "write"
${JSON.stringify(tree)} = "write"
${JSON.stringify(denied)} = "deny"
[permissions.fixture.network]
enabled = false
`);
mkdirSync(path.join(env.CODEX_HOME, "app-server-daemon"));
writeFileSync(path.join(env.CODEX_HOME, "app-server-daemon/settings.json"), JSON.stringify({ updater: { autoUpdateEnabled: false } }));
const allowRule = `prefix_rule(pattern = ["touch", ${JSON.stringify(path.join(outside, "command-allow-rule"))}], decision = "allow")\n`;
mkdirSync(path.join(env.CODEX_HOME, "rules"));
writeFileSync(path.join(env.CODEX_HOME, "rules/default.rules"), allowRule);

const strip = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");
const terminals = [];
const terminal = (name, args) => {
  const child = start("script", ["-qfec", `stty cols 180 rows 60; exec ${["codex", ...args].map(quote).join(" ")}`, "/dev/null"]);
  let screen = "";
  child.stdout.on("data", (chunk) => { screen += strip(String(chunk)); });
  child.stderr.on("data", (chunk) => { screen += strip(String(chunk)); });
  const handle = { child, name, exited: false, text: () => screen,
    screen: (label) => trace("screen", { name, label, text: screen.slice(-7000) }),
    key: (key, label) => { trace("terminal.key", { name, key: label }); child.stdin.write(key); },
    type: async (text) => { trace("terminal.type", { name, text }); child.stdin.write(text); await delay(400); child.stdin.write("\r"); } };
  child.on("exit", (status, signal) => { handle.exited = true; trace("terminal.exit", { name, status, signal }); });
  trace("terminal.start", { name, args }); terminals.push(handle); return handle;
};
const requestFor = (label) => modelRequests.filter((r) => r.label === label && !r.side && !r.guardian);
const stopTerminal = async (t) => {
  if (t.exited) return;
  await t.type("/exit");
  try { await waitFor(() => t.exited, "terminal exit", 10000); }
  catch { t.key("\u0003", "ctrl-c"); await delay(100); t.key("\u0003", "ctrl-c"); }
};
const observation = (label, lead) => {
  const stored = [main, tree].flatMap((cwd) => {
    const sessions = path.join(cwd, ".dashpot/state/sessions");
    return existsSync(sessions) ? readdirSync(sessions).filter((name) => name.endsWith(".json")).map((name) => parse(readFileSync(path.join(sessions, name), "utf8"))) : [];
  });
  const checked = dashpot(["worktree", "check", tree, "--json"]);
  const idleChecked = dashpot(["worktree", "check", idleTree, "--json"]);
  const snapshot = dashpot(["--compact-json"]);
  trace("observation", { label, lead, stored, cleanup: { status: checked.status, result: parse(checked.stdout), stderr: checked.stderr },
    idleCleanup: { status: idleChecked.status, result: parse(idleChecked.stdout), stderr: idleChecked.stderr },
    snapshot: { status: snapshot.status, result: parse(snapshot.stdout), stderr: snapshot.stderr } });
};
const runWaiting = async (name, answer) => {
  trace("scenario", { name });
  const worker = `worker-${name}`, lead = `lead-${name}`;
  plans.set(lead, [command(`${quote(path.join(checkout, ".venv/bin/dashpot"))} work start 1`),
    command(`touch ${quote(path.join(outside, "command-allow-rule"))}`), spawnWorker(worker), { assign: true },
    { name: "wait_agent", args: { timeout_ms: 30000 } }, { name: "list_agents", args: {} }]);
  plans.set(worker, [command(probeCommand(`plain-${worker}`)),
    command(probeCommand(worker), { sandbox_permissions: "require_escalated", justification: "Disposable fixture write; preserve denied reads and network" })]);
  const t = terminal(name, ["-C", tree, "--no-daemon", "--dangerously-bypass-hook-trust", `SPIKE:${lead}`]);
  await waitFor(() => t.text().includes("Would you like to run"), `${name} approval prompt`);
  await waitFor(() => requestFor(lead).some((r) => r.action === "wait_agent"), "parent waiting");
  await delay(1200); t.screen("approval-pending");
  observation(`${name}-pending`, requestFor(lead)[0].thread);
  trace("approval.answer", { name, answer, leadRequests: requestFor(lead).length });
  t.key(answer === "approve" ? "y" : "\u001b", answer);
  await waitFor(() => done.has(lead), `${name} parent hand-back`, 45000);
  await delay(1000); t.screen("after-answer");
  observation(`${name}-after`, requestFor(lead)[0].thread);
  await stopTerminal(t);
  observation(`${name}-exited`, requestFor(lead)[0].thread);
};

// A stdio client retains actual app-server notifications and answers only
// disposable permission requests with explicit turn scope.
const appClient = async (extra = []) => {
  const child = start("codex", ["--dangerously-bypass-hook-trust", ...extra, "app-server"]);
  let next = 0; const pending = new Map(); const notifications = [];
  child.stderr.on("data", (chunk) => appendFileSync(path.join(root, "app-server.stderr"), chunk));
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    const msg = parse(line); if (!msg) return;
    if (msg.method) {
      trace("rpc.event", { message: msg }); notifications.push(msg);
      if (msg.id !== undefined) {
        assert.equal(msg.method, "item/permissions/requestApproval", "only fixture permission requests are auto-answered");
        trace("permission.grant", { thread: msg.params.threadId, turn: msg.params.turnId, permissions: msg.params.permissions, scope: "turn" });
        child.stdin.write(JSON.stringify({ id: msg.id, result: { permissions: msg.params.permissions, scope: "turn" } }) + "\n");
      }
    } else if (pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  });
  const call = async (method, params) => {
    const id = ++next;
    trace("rpc.call", { id, method, params });
    const response = new Promise((resolve) => pending.set(id, resolve));
    child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
    const result = await Promise.race([response, delay(30000).then(() => { throw new Error(`RPC timeout ${method}`); })]);
    trace("rpc.result", { id, method, result }); assert(!result.error, JSON.stringify(result.error)); return result.result;
  };
  await call("initialize", { clientInfo: { name: "fixture-665", version: "0" }, capabilities: { experimentalApi: true } });
  child.stdin.write(JSON.stringify({ method: "initialized" }) + "\n");
  return { call, child, notifications };
};
const code = (text) => ({ name: "exec", code: text });
const runBackground = async () => {
  trace("scenario", { name: "background" });
  const gate = path.join(main, "release-background");
  const app = await appClient(["-c", "features.code_mode_only=true"]);
  const started = await app.call("thread/start", { cwd: main, model: "fixture-v2" });
  const thread = started.thread.id;
  plans.set("background-first", [code(`text(await tools.request_permissions({permissions:{file_system:{write:[${JSON.stringify(grantA)}]}}}));`),
    code(`text(await tools.exec_command({cmd:${JSON.stringify(probeCommand("background-before", path.join(grantA, "before")))}}));
yield_control();
text(await tools.exec_command({cmd:${JSON.stringify(`while [ ! -f ${quote(gate)} ]; do sleep 0.1; done`)},yield_time_ms:30000}));
text(await tools.exec_command({cmd:${JSON.stringify(probeCommand("background-after", path.join(grantA, "after"), path.join(grantB, "borrowed")))}}));`)]);
  plans.set("background-next", [code(`text(await tools.request_permissions({permissions:{file_system:{write:[${JSON.stringify(grantB)}]}}}));`),
    code(`text(await tools.exec_command({cmd:${JSON.stringify(probeCommand("next-own", path.join(grantB, "own"), path.join(grantA, "borrowed")))}}));`),
    code(`text(await tools.exec_command({cmd:${JSON.stringify(`touch ${quote(gate)}`)}}));`)]);
  const first = await app.call("turn/start", { threadId: thread, input: [{ type: "text", text: "SPIKE:background-first" }] });
  await waitFor(() => app.notifications.some((n) => n.method === "turn/completed" && n.params.turn.id === first.turn.id), "first background turn completed");
  const firstOut = requestFor("background-first").flatMap((r) => r.outputs).flatMap(strings).join("\n");
  const cell = /Script running with cell ID ([^\s]+)/.exec(firstOut)?.[1];
  assert(cell, "background cell yielded");
  plans.get("background-next").push({ name: "wait", args: { cell_id: cell, yield_time_ms: 10000 } });
  const next = await app.call("turn/start", { threadId: thread, input: [{ type: "text", text: "SPIKE:background-next" }] });
  assert.notEqual(first.turn.id, next.turn.id, "the grant tests must span distinct turns, never steering one turn");
  await waitFor(() => app.notifications.some((n) => n.method === "turn/completed" && n.params.turn.id === next.turn.id), "next turn and original cell complete");
  trace("background.outcome", { thread, firstTurn: first.turn.id, nextTurn: next.turn.id, cell,
    files: { before: existsSync(path.join(grantA, "before")), after: existsSync(path.join(grantA, "after")),
      own: existsSync(path.join(grantB, "own")), borrowedA: existsSync(path.join(grantA, "borrowed")), borrowedB: existsSync(path.join(grantB, "borrowed")) } });
  app.child.stdin.end();
};
const runGuardian = async (setting) => {
  const name = `guardian-${setting}`, lead = `lead-${name}`, worker = `worker-${name}`;
  trace("scenario", { name });
  plans.set(lead, [command(`${quote(path.join(checkout, ".venv/bin/dashpot"))} work start 1`), spawnWorker(worker), { assign: true },
    { name: "wait_agent", args: { timeout_ms: 10000 } }, { name: "list_agents", args: {} }]);
  plans.set(worker, [command("sleep 1"), ...[1, 2, 3].map((n) => command(`echo harmless-fixture-${n}`, { sandbox_permissions: "require_escalated", justification: "Fixture classifier denial only" }))]);
  const t = terminal(name, ["-C", tree, "--no-daemon", "--dangerously-bypass-hook-trust", "-c", 'approvals_reviewer="auto_review"',
    "-c", `auto_review.circuit_break_action="${setting}"`, `SPIKE:${lead}`]);
  await waitFor(() => done.has(lead), `${name} hand-back`, 45000);
  await delay(1000); t.screen("stopped"); observation(name, requestFor(lead)[0].thread);
  await stopTerminal(t);
  observation(`${name}-exited`, requestFor(lead)[0].thread);
};
const runInterrupt = async () => {
  trace("scenario", { name: "ordinary-interrupt" });
  plans.set("lead-interrupt", [command(`${quote(path.join(checkout, ".venv/bin/dashpot"))} work start 1`), spawnWorker("worker-interrupt"), { assign: true },
    command("sleep 1"), { name: "interrupt_agent", args: { target: "worker" } },
    { name: "wait_agent", args: { timeout_ms: 10000 } }, { name: "list_agents", args: {} }]);
  plans.set("worker-interrupt", [command(`sleep 30`, { workdir: tree, yield_time_ms: 30000 })]);
  const t = terminal("ordinary-interrupt", ["-C", tree, "--no-daemon", "--dangerously-bypass-hook-trust",
    "-c", 'approvals_reviewer="auto_review"', "-c", 'auto_review.circuit_break_action="strict"', "SPIKE:lead-interrupt"]);
  await waitFor(() => done.has("lead-interrupt"), "ordinary interruption hand-back", 45000);
  await delay(1000); t.screen("interrupted"); observation("ordinary-interrupt", requestFor("lead-interrupt")[0].thread);
  await stopTerminal(t);
  observation("ordinary-interrupt-exited", requestFor("lead-interrupt")[0].thread);
};

const sources = ["permissions-run.mjs", "permissions-hook.mjs", "permissions-probe.mjs", "permissions-reconnect.mjs", "permissions-verify.mjs", "ancestry.mjs"];
const packageSources = () => {
  const walk = (dir) => readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? (name === "__pycache__" ? [] : walk(full)) : name.endsWith(".py") ? [full] : [];
  });
  return Object.fromEntries(walk(path.join(checkout, "src/dashpot")).map((file) => [path.relative(checkout, file), sha(file)]));
};
const rolloutContexts = () => {
  const walk = (dir) => existsSync(dir) ? readdirSync(dir).flatMap((name) => {
    const file = path.join(dir, name); return statSync(file).isDirectory() ? walk(file) : name.endsWith(".jsonl") ? [file] : [];
  }) : [];
  return walk(path.join(env.CODEX_HOME, "sessions")).map((file) => {
    const lines = readFileSync(file, "utf8").trim().split("\n").map(parse).filter(Boolean);
    return { session: lines.find((r) => r.type === "session_meta")?.payload?.id,
      turns: lines.filter((r) => r.type === "turn_context").map((r) => r.payload),
      aborted: lines.filter((r) => r.payload?.type === "turn_aborted").map((r) => r.payload) };
  });
};
try {
  trace("environment", { version, binary: clean(binary), binarySHA256: sha(binary), platform: os.platform(), release: os.release(), arch: os.arch(),
    node: process.version, head: gitRevision(), root, main, tree, denied, outside, grantA, grantB, networkPort: port,
    sourceSHA256: Object.fromEntries(sources.map((file) => [file, sha(path.join(here, file))])), dashpotSHA256: packageSources(),
    config: readFileSync(config, "utf8"), allowRule, hooks, fixtureHomes,
    updater: JSON.parse(readFileSync(path.join(env.CODEX_HOME, "app-server-daemon/settings.json"))),
    ancestry: ancestry(process.ppid, 64, 1) });
  const selected = new Set((process.env.SPIKE_SCENARIOS ?? "approve,decline,reconnect,background,strict,default,interrupt").split(","));
  if (selected.has("approve")) await runWaiting("waiting-approve", "approve");
  if (selected.has("decline")) await runWaiting("waiting-decline", "decline");
  if (selected.has("reconnect")) {
    trace("scenario", { name: "reconnect" });
    for (const mode of ["workspace", "full"]) await runReconnect({ root, main, env, trace, terminal, waitFor, delay, mode });
  }
  if (selected.has("background")) await runBackground();
  if (selected.has("strict")) await runGuardian("strict");
  if (selected.has("default")) await runGuardian("default");
  if (selected.has("interrupt")) await runInterrupt();
  trace("rollouts", { threads: rolloutContexts() });
  trace("command-allow-rule", { written: existsSync(path.join(outside, "command-allow-rule")) });
  const finalSources = Object.fromEntries(sources.map((file) => [file, sha(path.join(here, file))]));
  assert.deepEqual(finalSources, records.find((r) => r.kind === "environment").sourceSHA256, "fixture sources stayed fixed during measurement");
  assert.deepEqual(packageSources(), records.find((r) => r.kind === "environment").dashpotSHA256, "publisher sources stayed fixed during measurement");
  trace("completed", { selected: [...selected] });
} catch (error) { trace("failure", { error: String(error.stack) }); process.exitCode = 1; }
finally {
  for (const terminal of terminals) await stopTerminal(terminal).catch(() => {});
  for (const child of children) { try { child.kill("SIGTERM"); } catch {} }
  await delay(500);
  const fixtureProcesses = readdirSync("/proc").filter((name) => /^\d+$/.test(name)).flatMap((name) => {
    try {
      const entries = readFileSync(`/proc/${name}/environ`, "utf8").split("\0");
      return fixtureHomes.some((home) => entries.includes(`CODEX_HOME=${home}`)) ? [describe(Number(name))] : [];
    } catch { return []; }
  });
  for (const entry of fixtureProcesses) { trace("cleanup.kill", { pid: entry.pid, comm: entry.comm }); try { process.kill(entry.pid, "SIGKILL"); } catch {} }
  model.closeAllConnections(); model.close(); network.close();
  trace("cleanup", { children: children.length, fixtureProcesses: fixtureProcesses.length });
  console.log(`Metadata trace: ${tracePath}`);
}
function gitRevision() { return execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(); }
