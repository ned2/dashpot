// Isolated Claude Code experiment for Issue #326: what `ps` reports for every
// process Claude Code's background supervisor runs, so that a supervised
// worker can be told apart from its supervisor, its PTY host, an unclaimed
// spare, and unrelated processes. Drives a pinned Claude Code binary against a
// loopback Messages API fixture with an isolated configuration directory,
// probes each fixture process with the same `ps` columns and environment
// Dashpot's process adapter uses, and records a metadata-only trace. The
// runner asserts only what it needs to keep going; the independent verifier
// checks the trace against the recorded claims.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync, spawnSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-326-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const other = path.join(root, "other-worktree");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root, this directory, and
// the operator's home by placeholder; none of them says anything about Claude
// Code, and the executable's position under the home directory is kept.
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.285";

const env = {
  PATH: `${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: path.join(root, "home"),
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CLAUDE_CONFIG_DIR: path.join(root, "claude-config"),
  ANTHROPIC_API_KEY: "fixture-unused",
  DISABLE_AUTOUPDATER: "1",
  DISABLE_TELEMETRY: "1",
  DISABLE_ERROR_REPORTING: "1",
  DISABLE_BUG_COMMAND: "1",
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  CLAUDE_CODE_DISABLE_TERMINAL_TITLE: "1",
  TERM: "dumb",
  // Ancestry walks from hooks and shells end at this runner.
  SPIKE_STOP_PID: String(process.pid),
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "Disposable fixture");
git("worktree", "add", "-b", "other", other);

// The probe Dashpot's process adapter runs: one `ps` for the fixed-width
// identity columns with `comm` last, one for `args`, in the C locale and UTC.
const ps = (pid, columns) => {
  const result = spawnSync("ps", ["-p", String(pid), ...columns.flatMap((column) => ["-o", `${column}=`])],
    { encoding: "utf8", env: { ...process.env, LC_ALL: "C", TZ: "UTC" } });
  return result.status === 0 ? result.stdout.trim() : null;
};
const probe = (pid) => {
  const identity = ps(pid, ["pid", "ppid", "lstart", "comm"]);
  if (identity === null) return { pid, present: false };
  const fields = identity.split(/\s+/);
  return { pid, present: true, ppid: Number(fields[1]), lstart: fields.slice(2, 7).join(" "), comm: fields.slice(7).join(" "), args: ps(pid, ["args"]) };
};
// Each harness process is probed once, the first time a hook or shell names it.
const probed = new Set();
const probeHarness = (pid, source) => {
  if (!pid || probed.has(pid)) return;
  probed.add(pid);
  trace("probe.harness", { source, ...probe(pid) });
};

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
  const record = await body(req);
  if (record.env) delete record.env.CLAUDE_CODE_MESSAGING_TOKEN;
  const kind = url.pathname === "/hook" ? "hook" : "command";
  trace(kind, record);
  // The hook or shell is still running, so the process it names is too.
  probeHarness(Number(record.env?.CLAUDE_PID), `${kind}:${record.event ?? record.label}`);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `SPIKE:<label>` text in the latest user turn selects
// one Bash tool call reporting identity; a turn holding a tool result ends.
const commandScript = path.join(here, "command.mjs");
const sse = (res, event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/messages")) {
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ type: "error", error: { type: "not_found_error", message: "fixture" } }));
    return;
  }
  const messages = payload.messages ?? [];
  let label = null;
  let latestUser = -1;
  messages.forEach((message, index) => {
    const parts = typeof message.content === "string" ? [{ type: "text", text: message.content }] : message.content ?? [];
    for (const part of parts) {
      const match = part.type === "text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?/);
      if (match) { label = { name: match[1], hold: match[2] }; latestUser = index; }
    }
  });
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  const toolResults = messages.slice(latestUser + 1).reduce((total, message) => total + (Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result").length : 0), 0);
  trace("model.request", { label: label?.name ?? null, toolResults });
  const useTool = label && toolResults === 0 && tools.includes("Bash");
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse(res, "message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (useTool) {
    const input = { command: `node ${commandScript} ${label.name} ${label.hold ?? 200}`, description: "Report fixture identity" };
    sse(res, "content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label.name}_${records.length}`, name: "Bash", input: {} } });
    sse(res, "content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(input) } });
    sse(res, "content_block_stop", { index: 0 });
    sse(res, "message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { output_tokens: 20 } });
  } else {
    sse(res, "content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse(res, "content_block_delta", { index: 0, delta: { type: "text_delta", text: "Fixture complete." } });
    sse(res, "content_block_stop", { index: 0 });
    sse(res, "message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 4 } });
  }
  sse(res, "message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"];
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
}, null, 2));
// Pre-accept onboarding and trust so the supervised workers neither prompt nor phone home.
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  // A PTY-hosted worker asks before using an environment API key; -p does not.
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: { [fixture]: { hasTrustDialogAccepted: true, allowedTools: [] }, [other]: { hasTrustDialogAccepted: true, allowedTools: [] } },
}, null, 2));

const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
// Servers live in this process, so every Claude invocation is asynchronous.
const claude = async (args, options = {}) => {
  const child = spawn(binary, args, { cwd: options.cwd ?? fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), options.timeout ?? 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  trace("action.claude", { args, pid: child.pid, status, signal, stdout: stdout.slice(-1000), stderr: stderr.slice(-1000) });
  return { status, stdout, stderr };
};
// Every process whose environment names the fixture configuration, so the
// operator's own Claude Code sessions are never probed or signalled.
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CLAUDE_CONFIG_DIR=${env.CLAUDE_CONFIG_DIR}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const snapshot = (label) => trace("probe.snapshot", { label, processes: fixtureProcesses().map((entry) => probe(entry.pid)).filter((entry) => entry.present) });
const agentsJSON = async (label, all = false) => {
  const result = await claude(["agents", "--json", ...(all ? ["--all"] : [])], { timeout: 30000 });
  let parsed = null;
  try { parsed = JSON.parse(result.stdout); } catch {}
  trace("agents", { label, all, agents: parsed });
  return parsed ?? [];
};
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const started = (session, since) => hooks().slice(since).find((record) => record.event === "SessionStart" && record.payload.session_id === session);

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")), fixture, other,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // Scenario 1: two workers under one supervisor. The first is spawned
  // directly; the second, dispatched once the supervisor has pre-warmed a
  // spare, is expected to claim it.
  trace("scenario", { name: "background-workers" });
  const dispatchA = await claude(["--bg", "SPIKE:worker-a hold=1500", "--name", "fixture-a", ...commonArgs]);
  assert.equal(dispatchA.status, 0, `dispatch a: ${dispatchA.stderr}`);
  await waitFor(() => commands().some((record) => record.label === "worker-a"), "worker a command", 90000);
  snapshot("worker-a-running");
  const dispatchB = await claude(["--bg", "SPIKE:worker-b hold=4000", "--name", "fixture-b", ...commonArgs], { cwd: other });
  assert.equal(dispatchB.status, 0, `dispatch b: ${dispatchB.stderr}`);
  await waitFor(() => commands().some((record) => record.label === "worker-b"), "worker b command", 90000);
  snapshot("both-running");
  const listing = (await agentsJSON("both-running")).filter((entry) => entry.kind === "background");
  const jobA = listing.find((entry) => entry.name === "fixture-a");
  const jobB = listing.find((entry) => entry.name === "fixture-b");
  assert(jobA?.pid && jobB?.pid, `both workers listed: ${JSON.stringify(listing)}`);
  await waitFor(() => hooks().some((record) => record.event === "Stop" && record.payload.session_id === jobA.sessionId), "worker a Stop", 60000);
  await waitFor(() => hooks().some((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId), "worker b Stop", 60000);

  // Scenario 2: a settled worker dies abruptly and the supervisor replaces it.
  trace("scenario", { name: "worker-abrupt-exit" });
  const beforeKill = hooks().length;
  assert(fixtureProcesses().some((entry) => entry.pid === jobA.pid), "worker a is a fixture process");
  process.kill(jobA.pid, "SIGKILL");
  trace("action.kill", { worker: "a", pid: jobA.pid, signal: "SIGKILL" });
  await waitFor(() => started(jobA.sessionId, beforeKill), "worker a SessionStart after kill", 60000);
  await delay(1500);
  snapshot("after-worker-a-killed");
  await agentsJSON("after-worker-a-killed");

  // Scenario 3: an explicit stop, then respawn, of the second worker.
  trace("scenario", { name: "worker-stop-respawn" });
  const stopped = await claude(["stop", jobB.id], { timeout: 30000 });
  trace("worker.stop", { worker: "b", status: stopped.status });
  await delay(2500);
  const beforeRespawn = hooks().length;
  const respawned = await claude(["respawn", jobB.id], { timeout: 30000 });
  trace("worker.respawn", { worker: "b", status: respawned.status });
  await waitFor(() => started(jobB.sessionId, beforeRespawn), "worker b SessionStart after respawn", 60000);
  await delay(1500);
  snapshot("after-worker-b-respawned");
  await agentsJSON("after-worker-b-respawned");

  // Scenario 4: a third worker after the respawn, to see which process kind
  // a later dispatch lands in.
  trace("scenario", { name: "third-worker" });
  const dispatchC = await claude(["--bg", "SPIKE:worker-c hold=500", "--name", "fixture-c", ...commonArgs]);
  assert.equal(dispatchC.status, 0, `dispatch c: ${dispatchC.stderr}`);
  await waitFor(() => commands().some((record) => record.label === "worker-c"), "worker c command", 90000);
  await delay(1500);
  snapshot("third-worker-running");
  await agentsJSON("third-worker-running");

  // Scenario 5: stop the supervisor with its workers.
  trace("scenario", { name: "supervisor-stop" });
  await claude(["daemon", "stop", "--any"], { timeout: 30000 });
  await delay(3000);
  snapshot("after-supervisor-stop");
  console.log(`All scenarios completed: ${root}`);
} finally {
  // Leave nothing of the isolated supervisor behind, whatever the outcome.
  await claude(["daemon", "stop", "--any"], { timeout: 30000 }).catch(() => {});
  await delay(1000);
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
