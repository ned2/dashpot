// Isolated Claude Code identity and lifecycle experiment for Issue #160.
// Drives a pinned Claude Code binary against a loopback Messages API fixture
// with an isolated configuration directory, records hook and shell evidence
// as a metadata-only trace, and asserts the observable outcomes.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-160-"));
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
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.276";

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
};
for (const dir of [fixture, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);
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
  const record = await body(req);
  if (record.env) delete record.env.CLAUDE_CODE_MESSAGING_TOKEN;
  trace(url.pathname === "/hook" ? "hook" : "command", record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `SPIKE:<label>` text in the latest user turn selects
// one Bash tool call reporting identity; a turn holding a tool result ends.
const commandScript = path.join(here, "command.mjs");
const modelRequests = new Map();
const sse = (res, event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (!url.pathname.endsWith("/messages")) {
    trace("model.other", { path: url.pathname, method: req.method });
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
      const match = part.type === "text" && part.text?.match(/SPIKE:([a-z0-9-]+)(?: hold=(\d+))?(?: cwd=(\S+))?/);
      if (match) { label = { name: match[1], hold: match[2], cwd: match[3] }; latestUser = index; }
    }
  });
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  const toolResults = messages.slice(latestUser + 1).reduce((total, message) => total + (Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result").length : 0), 0);
  // A worker asked to edit first relocates with EnterWorktree, then reports.
  const relocate = label?.name === "worker-edit" && toolResults === 0 && tools.includes("EnterWorktree");
  const usedTool = toolResults >= (label?.name === "worker-edit" ? 2 : 1);
  const count = (modelRequests.get(label?.name ?? "none") ?? 0) + 1;
  modelRequests.set(label?.name ?? "none", count);
  trace("model.request", { label: label?.name ?? null, usedTool, count, model: payload.model, stream: payload.stream, toolCount: tools.length, hasBash: tools.includes("Bash"), tools: modelRequests.size === 1 && count === 1 ? tools : undefined });
  const useTool = label && !usedTool && label.name !== "finish" && tools.includes("Bash");
  const delegate = useTool && label.name === "delegate" && tools.includes("Agent");
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse(res, "message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (useTool) {
    const command = `node ${commandScript} ${delegate ? "child" : label.name} ${label.hold ?? 200}`;
    const input = delegate
      ? { description: "Fixture child", prompt: "SPIKE:child", subagent_type: "general-purpose" }
      : relocate ? { name: "fixture-edit" }
      : { command, description: "Report fixture identity" };
    sse(res, "content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label.name}_${count}`, name: delegate ? "Agent" : relocate ? "EnterWorktree" : "Bash", input: {} } });
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
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart", "SubagentStop", "SessionEnd", "CwdChanged"];
const settings = {
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
};
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify(settings, null, 2));
// Pre-accept onboarding so headless runs neither prompt nor phone home.
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  // A PTY-hosted worker asks before using an environment API key; -p does not.
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: { [fixture]: { hasTrustDialogAccepted: true, allowedTools: [] }, [other]: { hasTrustDialogAccepted: true, allowedTools: [] } },
}, null, 2));

const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
// Servers live in this process, so every Claude invocation is asynchronous.
const claude = async (args, options = {}) => {
  const child = spawn(binary, args, { cwd: options.cwd ?? fixture, env: { ...env, ...options.env }, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), options.timeout ?? 60000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  const result = { status, signal, stdout, stderr, pid: child.pid };
  trace("action.claude", { args, cwd: options.cwd ?? fixture, pid: child.pid, status, signal, stdout: stdout.slice(-2000), stderr: stderr.slice(-2000) });
  return result;
};
const claudeProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let entry;
    try { entry = describe(Number(name)); } catch { continue; }
    let environ = "";
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`CLAUDE_CONFIG_DIR=${env.CLAUDE_CONFIG_DIR}`)) continue;
    const vars = Object.fromEntries(environ.split("\0").filter((item) => item.startsWith("CLAUDE") && !item.startsWith("CLAUDE_CODE_MESSAGING_TOKEN=")).map((item) => { const at = item.indexOf("="); return [item.slice(0, at), item.slice(at + 1)]; }));
    found.push({ ...entry, env: vars });
  }
  return found;
};
const snapshot = (label, extra = {}) => trace("processes", { label, processes: claudeProcesses(), ...extra });
const agentsJSON = async (label, all = false) => {
  const result = await claude(["agents", "--json", ...(all ? ["--all"] : [])], { timeout: 30000 });
  let parsed = null;
  try { parsed = JSON.parse(result.stdout); } catch {}
  trace("agents", { label, all, status: result.status, agents: parsed, raw: parsed ? undefined : result.stdout.slice(-1000) });
  return parsed ?? [];
};
const daemonStatus = async (label) => {
  const result = await claude(["daemon", "status"], { timeout: 30000 });
  trace("daemon.status", { label, status: result.status, stdout: result.stdout, stderr: result.stderr });
  return result;
};
const hooks = () => records.filter((record) => record.kind === "hook");
const commands = () => records.filter((record) => record.kind === "command");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")), fixture, other,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) =>
      [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")])) });

  // Scenario 1: ordinary headless session in the fixture checkout.
  trace("scenario", { name: "headless-baseline" });
  const baseline = await claude(["-p", "SPIKE:baseline", "--output-format", "json", ...commonArgs]);
  assert.equal(baseline.status, 0, `baseline exit ${baseline.status}: ${baseline.stderr}`);
  const baselineOutput = JSON.parse(baseline.stdout);
  trace("baseline.output", { sessionId: baselineOutput.session_id, isError: baselineOutput.is_error, numTurns: baselineOutput.num_turns });
  const baselineStart = hooks().find((record) => record.event === "SessionStart");
  assert(baselineStart, "baseline SessionStart hook");
  assert.equal(baselineStart.payload.session_id, baselineOutput.session_id);
  assert.equal(baselineStart.payload.source, "startup");
  const baselineCommand = commands().find((record) => record.label === "baseline" && record.phase === "start");
  assert(baselineCommand, "baseline command ran");
  assert.equal(baselineCommand.env.CLAUDE_CODE_SESSION_ID, baselineOutput.session_id);
  assert.equal(Number(baselineCommand.env.CLAUDE_PID), baseline.pid);
  assert.equal(baselineCommand.ancestry[1].pid, baseline.pid);
  assert(hooks().some((record) => record.event === "SessionEnd" && record.payload.session_id === baselineOutput.session_id));

  // Scenario 2: the saved conversation resumes in a new process, then forks.
  trace("scenario", { name: "headless-resume" });
  const resumed = await claude(["-p", "SPIKE:resumed", "--resume", baselineOutput.session_id, "--output-format", "json", ...commonArgs]);
  assert.equal(resumed.status, 0, `resume exit ${resumed.status}: ${resumed.stderr}`);
  const resumedOutput = JSON.parse(resumed.stdout);
  trace("resume.output", { sessionId: resumedOutput.session_id, numTurns: resumedOutput.num_turns });
  assert.equal(resumedOutput.session_id, baselineOutput.session_id);
  const resumedStart = hooks().filter((record) => record.event === "SessionStart").at(-1);
  assert.equal(resumedStart.payload.session_id, baselineOutput.session_id);
  assert.equal(resumedStart.payload.source, "resume");
  const resumedCommand = commands().find((record) => record.label === "resumed" && record.phase === "start");
  assert.equal(resumedCommand.env.CLAUDE_CODE_SESSION_ID, baselineOutput.session_id);
  assert.equal(Number(resumedCommand.env.CLAUDE_PID), resumed.pid);
  assert.notEqual(resumed.pid, baseline.pid);
  trace("scenario", { name: "headless-fork" });
  const forked = await claude(["-p", "SPIKE:forked", "--resume", baselineOutput.session_id, "--fork-session", "--output-format", "json", ...commonArgs]);
  assert.equal(forked.status, 0, `fork exit ${forked.status}: ${forked.stderr}`);
  const forkedOutput = JSON.parse(forked.stdout);
  const forkedStart = hooks().filter((record) => record.event === "SessionStart").at(-1);
  trace("fork.output", { sessionId: forkedOutput.session_id, origin: baselineOutput.session_id, source: forkedStart.payload.source, startPayloadKeys: forkedStart.payloadKeys });
  assert.notEqual(forkedOutput.session_id, baselineOutput.session_id);
  assert.equal(forkedStart.payload.session_id, forkedOutput.session_id);
  assert.equal(commands().find((record) => record.label === "forked").env.CLAUDE_CODE_SESSION_ID, forkedOutput.session_id);

  // Scenario 3: a delegated subagent runs a command inside the same session.
  trace("scenario", { name: "headless-subagent" });
  const delegated = await claude(["-p", "SPIKE:delegate", "--output-format", "json", ...commonArgs]);
  assert.equal(delegated.status, 0, `delegate exit ${delegated.status}: ${delegated.stderr}`);
  const delegatedOutput = JSON.parse(delegated.stdout);
  const childCommand = commands().find((record) => record.label === "child" && record.phase === "start");
  assert(childCommand, "child command ran");
  const subagentStart = hooks().find((record) => record.event === "SubagentStart");
  const subagentStop = hooks().find((record) => record.event === "SubagentStop");
  assert(subagentStart && subagentStop, "subagent hooks");
  trace("subagent.identity", { sessionId: delegatedOutput.session_id, startPayload: subagentStart.payload, stopPayloadKeys: subagentStop.payloadKeys,
    childCommandEnv: childCommand.env, childSessionId: childCommand.env.CLAUDE_CODE_SESSION_ID, childPid: Number(childCommand.env.CLAUDE_PID), parentPid: delegated.pid });
  assert.equal(childCommand.env.CLAUDE_CODE_SESSION_ID, delegatedOutput.session_id);
  assert.equal(Number(childCommand.env.CLAUDE_PID), delegated.pid);
  const childHooks = hooks().filter((record) => record.payload.agent_id !== undefined);
  trace("subagent.hooks", { events: childHooks.map((record) => [record.event, record.payload.agent_id, record.payload.session_id]) });

  // Scenario 4: two background workers under one supervisor, in two Worktrees.
  trace("scenario", { name: "background-workers" });
  snapshot("before-background");
  const dispatchA = await claude(["--bg", "SPIKE:worker-a hold=1500", "--name", "fixture-a", ...commonArgs], { timeout: 60000 });
  trace("dispatch", { worker: "a", status: dispatchA.status, stdout: dispatchA.stdout, stderr: dispatchA.stderr });
  assert.equal(dispatchA.status, 0, `dispatch a: ${dispatchA.stderr}`);
  const dispatchB = await claude(["--bg", "SPIKE:worker-b hold=60000", "--name", "fixture-b", ...commonArgs], { cwd: other, timeout: 60000 });
  trace("dispatch", { worker: "b", status: dispatchB.status, stdout: dispatchB.stdout, stderr: dispatchB.stderr });
  assert.equal(dispatchB.status, 0, `dispatch b: ${dispatchB.stderr}`);
  await waitFor(() => commands().some((record) => record.label === "worker-b" && record.phase === "start"), "worker b command start", 90000);
  const listing = await agentsJSON("both-running");
  await daemonStatus("both-running");
  snapshot("both-running");
  const background = listing.filter((entry) => entry.kind === "background");
  assert.equal(background.length, 2, `two background sessions: ${JSON.stringify(listing)}`);
  const jobA = background.find((entry) => entry.name === "fixture-a") ?? background.find((entry) => entry.cwd === fixture);
  const jobB = background.find((entry) => entry.name === "fixture-b") ?? background.find((entry) => entry.cwd === other);
  assert(jobA && jobB && jobA.id !== jobB.id, "distinct jobs");
  await waitFor(() => commands().some((record) => record.label === "worker-a" && record.phase === "end"), "worker a command end", 60000);
  await waitFor(() => hooks().some((record) => record.event === "Stop" && record.payload.session_id === jobA.sessionId), "worker a Stop hook", 60000);
  const workerACommand = commands().find((record) => record.label === "worker-a" && record.phase === "start");
  const workerBCommand = commands().find((record) => record.label === "worker-b" && record.phase === "start");
  assert.equal(workerACommand.env.CLAUDE_CODE_SESSION_ID, jobA.sessionId);
  assert.equal(workerBCommand.env.CLAUDE_CODE_SESSION_ID, jobB.sessionId);
  assert.equal(Number(workerACommand.env.CLAUDE_PID), jobA.pid);
  assert.equal(Number(workerBCommand.env.CLAUDE_PID), jobB.pid);
  assert.notEqual(jobA.pid, jobB.pid);
  const workerAStart = hooks().find((record) => record.event === "SessionStart" && record.payload.session_id === jobA.sessionId);
  const workerBStart = hooks().find((record) => record.event === "SessionStart" && record.payload.session_id === jobB.sessionId);
  assert(workerAStart && workerBStart, "worker SessionStart hooks");
  const daemonAtDispatch = claudeProcesses().find((entry) => entry.cmdline.includes("daemon run"));
  assert(daemonAtDispatch, "supervisor running");
  const workerAncestor = (command) => command.ancestry.map((entry) => entry.pid);
  assert(workerAncestor(workerACommand).includes(jobA.pid) && workerAncestor(workerACommand).includes(daemonAtDispatch.pid), "worker a command descends from worker and supervisor");
  assert(workerAncestor(workerBCommand).includes(jobB.pid) && workerAncestor(workerBCommand).includes(daemonAtDispatch.pid), "worker b command descends from worker and supervisor");
  trace("workers.identity", { supervisor: daemonAtDispatch,
    a: { job: jobA, hookCwd: workerAStart.payload.cwd, source: workerAStart.payload.source, commandCwd: workerACommand.cwd, env: workerACommand.env, ancestry: workerACommand.ancestry.slice(0, 5) },
    b: { job: jobB, hookCwd: workerBStart.payload.cwd, source: workerBStart.payload.source, commandCwd: workerBCommand.cwd, env: workerBCommand.env, ancestry: workerBCommand.ancestry.slice(0, 5) } });
  // A terminal attaches to the running worker b, then dies without stopping it.
  const hooksBeforeAttach = hooks().length;
  const attach = spawn("script", ["-q", "-e", "-c", `${binary} attach ${jobB.id}`, "/dev/null"], { cwd: other, env: { ...env, TERM: "xterm" }, stdio: ["ignore", "pipe", "pipe"] });
  let attachOutput = "";
  attach.stdout.on("data", (chunk) => { attachOutput += chunk; });
  attach.stderr.on("data", (chunk) => { attachOutput += chunk; });
  await delay(5000);
  const attachedListing = await agentsJSON("b-attached");
  const attachAlive = attach.exitCode === null && attach.signalCode === null;
  attach.kill("SIGTERM");
  const [attachCode, attachSignal] = attachAlive ? await once(attach, "exit") : [attach.exitCode, attach.signalCode];
  await delay(1500);
  trace("attach", { worker: "b", attachPid: attach.pid, attachAlive, attachCode, attachSignal, outputSample: attachOutput.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").replace(/\s+/g, " ").slice(-400),
    listingWhileAttached: attachedListing.find((entry) => entry.id === jobB.id), workerAlive: claudeProcesses().some((entry) => entry.pid === jobB.pid),
    newHooks: hooks().slice(hooksBeforeAttach).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source, record.env.CLAUDE_PID]) });
  assert(claudeProcesses().some((entry) => entry.pid === jobB.pid), "worker b survives its attached terminal dying");
  const afterA = await agentsJSON("a-finished-b-running");
  const stillB = afterA.find((entry) => entry.id === jobB.id);
  assert(stillB && stillB.pid === jobB.pid, "worker b unaffected by worker a finishing");
  const jobStateKeys = (id) => { try { return Object.keys(JSON.parse(readFileSync(path.join(env.CLAUDE_CONFIG_DIR, "jobs", id, "state.json"), "utf8"))); } catch (error) { return String(error); } };
  trace("job.state-keys", { a: jobStateKeys(jobA.id), rosterKeys: (() => { try { const roster = JSON.parse(readFileSync(path.join(env.CLAUDE_CONFIG_DIR, "daemon", "roster.json"), "utf8")); return Array.isArray(roster) ? Object.keys(roster[0] ?? {}) : Object.keys(roster); } catch (error) { return String(error); } })() });

  // Scenario 4b: a worker that edits a file moves into a managed Worktree.
  trace("scenario", { name: "background-worker-edit" });
  const hooksBeforeEdit = hooks().length;
  const dispatchD = await claude(["--bg", `SPIKE:worker-edit cwd=${fixture}`, "--name", "fixture-d", ...commonArgs], { timeout: 60000 });
  trace("dispatch", { worker: "d", status: dispatchD.status, stdout: dispatchD.stdout, stderr: dispatchD.stderr });
  assert.equal(dispatchD.status, 0, `dispatch d: ${dispatchD.stderr}`);
  let jobD = null;
  for (let attempt = 0; attempt < 20 && !jobD?.sessionId; attempt++) { await delay(1000); jobD = (await agentsJSON("worker-d-poll")).find((entry) => entry.name === "fixture-d"); }
  assert(jobD?.sessionId, "worker d listed with a session");
  await waitFor(() => hooks().slice(hooksBeforeEdit).some((record) => record.event === "Stop" && record.payload.session_id === jobD.sessionId), "worker d Stop hook", 90000);
  await delay(1500);
  jobD = (await agentsJSON("after-worker-edit", true)).find((entry) => entry.name === "fixture-d");
  const editHooks = hooks().filter((record) => record.payload.session_id === jobD.sessionId);
  const worktrees = execFileSync("git", ["-C", fixture, "worktree", "list", "--porcelain"], { env, encoding: "utf8" }).trim().split("\n\n").map((block) => block.split("\n")[0].replace("worktree ", ""));
  const editCommand = commands().find((record) => record.label === "worker-edit" && record.phase === "start");
  trace("worker.edit", { d: jobD, hooks: editHooks.map((record) => [record.event, record.payload.cwd, record.payload.tool_name ?? null, record.payload.old_cwd ?? null, record.payload.new_cwd ?? null, record.env.CLAUDE_PROJECT_DIR]),
    worktrees, commandCwd: editCommand?.cwd ?? null, commandSession: editCommand?.env.CLAUDE_CODE_SESSION_ID ?? null, commandPid: editCommand ? Number(editCommand.env.CLAUDE_PID) : null });
  assert(editCommand && editCommand.cwd !== fixture && worktrees.includes(editCommand.cwd), "worker d's command ran inside a new linked Worktree");
  assert.equal(editCommand.env.CLAUDE_CODE_SESSION_ID, jobD.sessionId);

  // Scenario 5: a settled worker dies abruptly while the supervisor runs.
  trace("scenario", { name: "worker-abrupt-exit" });
  const hooksBeforeKill = hooks().length;
  process.kill(jobA.pid, "SIGKILL");
  trace("action.kill", { worker: "a", pid: jobA.pid, signal: "SIGKILL", supervisor: daemonAtDispatch.pid });
  let restartedA = null;
  try {
    await waitFor(() => hooks().slice(hooksBeforeKill).some((record) => record.event === "SessionStart" && record.payload.session_id === jobA.sessionId), "worker a restart after kill", 30000);
    restartedA = hooks().slice(hooksBeforeKill).find((record) => record.event === "SessionStart" && record.payload.session_id === jobA.sessionId);
  } catch (error) { trace("worker.no-restart", { worker: "a", error: String(error) }); }
  await delay(2000);
  const afterKill = await agentsJSON("after-worker-a-killed", true);
  snapshot("after-worker-a-killed");
  const killedA = afterKill.find((entry) => entry.id === jobA.id);
  trace("worker.after-kill", { a: killedA, restartSource: restartedA?.payload.source ?? null, restartPid: restartedA?.env.CLAUDE_PID ?? null,
    newHooks: hooks().slice(hooksBeforeKill).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source, record.env.CLAUDE_PID]) });
  assert(!hooks().slice(hooksBeforeKill).some((record) => record.event === "SessionEnd" && record.payload.session_id === jobA.sessionId), "no SessionEnd for a killed worker");
  assert(hooks().slice(hooksBeforeKill).every((record) => record.payload.session_id !== jobB.sessionId || record.event !== "SessionEnd"), "worker b untouched by worker a's death");

  // Scenario 6: replace the supervisor while the workers stay alive.
  trace("scenario", { name: "supervisor-replacement" });
  const hooksBeforeReplace = hooks().length;
  const keep = await claude(["daemon", "stop", "--any", "--keep-workers"], { timeout: 30000 });
  trace("daemon.stop", { keepWorkers: true, status: keep.status, stdout: keep.stdout, stderr: keep.stderr, previousDaemon: daemonAtDispatch.pid });
  await delay(1500);
  snapshot("supervisor-stopped-workers-kept");
  await daemonStatus("supervisor-stopped-workers-kept");
  const survivors = claudeProcesses();
  assert(survivors.some((entry) => entry.pid === jobB.pid), "worker b survives supervisor stop");
  assert(!survivors.some((entry) => entry.pid === daemonAtDispatch.pid), "old supervisor gone");
  const orphanListing = await agentsJSON("workers-without-supervisor");
  trace("workers.without-supervisor", { b: orphanListing.find((entry) => entry.id === jobB.id), a: orphanListing.find((entry) => entry.id === jobA.id), supervisorRunning: claudeProcesses().some((entry) => entry.cmdline.includes("daemon run")) });
  // A third dispatch starts the replacement supervisor, which re-adopts the survivors.
  const dispatchC = await claude(["--bg", "SPIKE:worker-c hold=1000", "--name", "fixture-c", ...commonArgs], { timeout: 60000 });
  trace("dispatch", { worker: "c", status: dispatchC.status, stdout: dispatchC.stdout, stderr: dispatchC.stderr });
  assert.equal(dispatchC.status, 0, `dispatch c: ${dispatchC.stderr}`);
  await delay(2500);
  const relisted = await agentsJSON("after-supervisor-replacement");
  await daemonStatus("after-supervisor-replacement");
  snapshot("supervisor-replaced");
  const newDaemon = claudeProcesses().find((entry) => entry.cmdline.includes("daemon run"));
  const reattachedB = relisted.find((entry) => entry.id === jobB.id);
  const jobC = relisted.find((entry) => entry.name === "fixture-c");
  trace("workers.after-replacement", { supervisor: newDaemon, a: relisted.find((entry) => entry.id === jobA.id), b: reattachedB, c: jobC, bParent: claudeProcesses().find((entry) => entry.pid === jobB.pid)?.ppid,
    newHooks: hooks().slice(hooksBeforeReplace).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source, record.env.CLAUDE_PID]) });
  assert(newDaemon && newDaemon.pid !== daemonAtDispatch.pid, "replacement supervisor running");
  assert(reattachedB && reattachedB.pid === jobB.pid && reattachedB.sessionId === jobB.sessionId, "worker b listed with same pid and session after replacement");
  assert(!hooks().slice(hooksBeforeReplace).some((record) => record.event === "SessionEnd" && [jobA.sessionId, jobB.sessionId].includes(record.payload.session_id)), "no SessionEnd during supervisor replacement");
  await waitFor(() => commands().some((record) => record.label === "worker-b" && record.phase === "end"), "worker b command end", 90000);
  await waitFor(() => hooks().some((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId), "worker b Stop hook after replacement", 60000);
  const stopB = hooks().find((record) => record.event === "Stop" && record.payload.session_id === jobB.sessionId);
  assert.equal(Number(stopB.env.CLAUDE_PID), jobB.pid);
  const settledB = await agentsJSON("b-settled-under-replacement");
  trace("workers.settled", { b: settledB.find((entry) => entry.id === jobB.id), c: settledB.find((entry) => entry.id === jobC?.id) });

  // Scenario 7: explicit stop, then respawn the saved conversation.
  trace("scenario", { name: "worker-stop-respawn" });
  const hooksBeforeStop = hooks().length;
  const stopped = await claude(["stop", jobB.id], { timeout: 30000 });
  trace("worker.stop", { worker: "b", status: stopped.status, stdout: stopped.stdout, stderr: stopped.stderr });
  await delay(2500);
  const afterStop = await agentsJSON("after-worker-b-stopped", true);
  snapshot("after-worker-b-stopped");
  trace("worker.after-stop", { b: afterStop.find((entry) => entry.id === jobB.id), newHooks: hooks().slice(hooksBeforeStop).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source, record.env.CLAUDE_PID]) });
  assert(!claudeProcesses().some((entry) => entry.pid === jobB.pid), "worker b process gone after stop");
  const hooksBeforeRespawn = hooks().length;
  const respawned = await claude(["respawn", jobB.id], { timeout: 30000 });
  trace("worker.respawn", { worker: "b", status: respawned.status, stdout: respawned.stdout, stderr: respawned.stderr });
  await waitFor(() => hooks().slice(hooksBeforeRespawn).some((record) => record.event === "SessionStart" && record.payload.session_id === jobB.sessionId), "worker b SessionStart after respawn", 60000);
  await delay(3000);
  const afterRespawn = await agentsJSON("after-worker-b-respawned", true);
  snapshot("after-worker-b-respawned");
  const respawnedB = afterRespawn.find((entry) => entry.id === jobB.id);
  const respawnStart = hooks().slice(hooksBeforeRespawn).find((record) => record.event === "SessionStart" && record.payload.session_id === jobB.sessionId);
  trace("worker.after-respawn", { b: respawnedB, source: respawnStart.payload.source, hookPid: respawnStart.env.CLAUDE_PID, newHooks: hooks().slice(hooksBeforeRespawn).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source, record.env.CLAUDE_PID]) });
  assert(respawnedB && respawnedB.sessionId === jobB.sessionId && respawnedB.pid !== jobB.pid, "respawned worker keeps its conversation with a new pid");

  // Scenario 8: stop the supervisor together with its workers.
  trace("scenario", { name: "supervisor-stop" });
  const hooksBeforeDaemonStop = hooks().length;
  const stopAll = await claude(["daemon", "stop", "--any"], { timeout: 30000 });
  trace("daemon.stop", { keepWorkers: false, status: stopAll.status, stdout: stopAll.stdout, stderr: stopAll.stderr });
  await delay(3000);
  snapshot("supervisor-and-workers-stopped");
  trace("workers.after-supervisor-stop", { newHooks: hooks().slice(hooksBeforeDaemonStop).map((record) => [record.event, record.payload.session_id, record.payload.reason ?? record.payload.source, record.env.CLAUDE_PID]), processes: claudeProcesses().map((entry) => [entry.pid, entry.cmdline]) });
  const finalListing = await agentsJSON("after-supervisor-stop", true);
  snapshot("listing-after-supervisor-stop");
  trace("workers.final", { jobs: finalListing.filter((entry) => entry.kind === "background") });
  trace("daemon.log", { lines: readFileSync(path.join(env.CLAUDE_CONFIG_DIR, "daemon.log"), "utf8").trim().split("\n").map((line) => line.slice(0, 300)) });

  // Scenario 9: Remote Control server mode with API-key credentials only.
  trace("scenario", { name: "remote-control-eligibility" });
  const remote = await claude(["remote-control", "--no-create-session-in-dir"], { timeout: 20000 });
  trace("remote-control", { status: remote.status, signal: remote.signal, stdout: remote.stdout, stderr: remote.stderr });
  await claude(["daemon", "stop", "--any"], { timeout: 30000 });

  console.log(`All scenarios completed: ${root}`);
} finally {
  // Leave nothing of the isolated supervisor behind, whatever the outcome.
  await claude(["daemon", "stop", "--any"], { timeout: 30000 }).catch(() => {});
  await delay(1000);
  for (const entry of claudeProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, cmdline: entry.cmdline });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
