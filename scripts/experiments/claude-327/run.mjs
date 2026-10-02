// Worktree-tool route experiment for Issue #327: when Claude Code's
// EnterWorktree accepts a Dashpot Issue Worktree, and whether a session can
// leave one with ExitWorktree(keep) and enter another, or the same one again.
// Drives a pinned Claude Code binary as headless clients against a loopback
// Messages API fixture with an isolated configuration directory. Every hook
// event goes to this checkout's real Claude Code publisher through the
// #162 acceptance runner's wrapper, subscribed exactly as `dashpot integrate
// claude-code` subscribes it, and the sessions' shells run this checkout's
// `dashpot work` commands, as the Issue-work skill does. The Issue Worktrees
// are linked Worktrees beside the main checkout, where Dashpot's default
// Worktree Root puts them. The trace is metadata only; the verifier checks
// the claims against it.
//
// Usage: node run.mjs <absolute claude binary> [expected version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "../claude-162/ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
// The hook wrapper, shell command and ancestry walk are the #162 runner's.
const shared = path.resolve(here, "..", "claude-162");
const checkout = path.resolve(here, "..", "..", "..");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-327-"));
console.log(`Isolated fixture: ${root}`);
// The main checkout and three linked Worktrees in the sibling pool Dashpot's
// default Worktree Root names: two Issue Worktrees to move between, and one
// a session is launched in. `managed` is a linked Worktree under Claude
// Code's own `.claude/worktrees/`, added once that directory exists.
const fixture = path.join(root, "repository");
const pool = path.join(root, "repository.worktrees");
const first = path.join(pool, "first");
const second = path.join(pool, "second");
const launch = path.join(pool, "launch");
const managedDirectory = path.join(fixture, ".claude", "worktrees");
const managed = path.join(managedDirectory, "managed");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(shared, "$SHARED").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.286";
const dashpot = path.join(checkout, ".venv", "bin", "dashpot");
const publisher = path.join(checkout, ".venv", "bin", "dashpot-claude-code-hook");
const python = path.join(checkout, ".venv", "bin", "python");

// A Claude Code session above the runner would be the host Dashpot finds for
// any fixture process it does not recognise, so refuse to start below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every Claude Code session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
// Clients start through a launcher named `claude`, as a person's do.
const launcherDirectory = path.join(root, "bin");
mkdirSync(launcherDirectory);
const launcher = path.join(launcherDirectory, "claude");
symlinkSync(binary, launcher);
const env = {
  PATH: `${launcherDirectory}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
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
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_DASHPOT: dashpot,
  SPIKE_PUBLISHER: publisher,
};
for (const dir of [fixture, pool, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Dashpot Project with a markdown Issue Source, one Issue per binding.
const issues = ["issue-1", "issue-2", "issue-3", "issue-4", "issue-5"];
mkdirSync(path.join(fixture, ".dashpot"), { recursive: true });
mkdirSync(path.join(fixture, "issues"), { recursive: true });
writeFileSync(path.join(fixture, ".dashpot", "config.json"), JSON.stringify({ projectId: "project:fixture", displayLabel: "Fixture", repositoryId: "repository:fixture", issueSource: { kind: "markdown", path: "issues" } }));
issues.forEach((reference, index) => {
  const number = index + 1;
  const front = { id: `I_fixture_${number}`, number, reference, state: "open", stateReason: null, labels: [], assignees: [], author: "fixture",
    relationships: { parent: null, subIssues: [], blockedBy: [], blocking: [] }, issueType: null, milestone: null,
    createdAt: "2026-10-01T00:00:00Z", updatedAt: "2026-10-01T00:00:00Z", closedAt: null };
  writeFileSync(path.join(fixture, "issues", `${reference}.md`), `---\n${JSON.stringify(front)}\n---\n# Fixture Issue ${number}\n\nBody.\n`);
});
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.claude/\n");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const [branch, worktree] of [["first", first], ["second", second], ["launch", launch]]) git("worktree", "add", "-b", branch, worktree);

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

// The fixture model: a `SPIKE:<label>` text in the latest user turn selects a
// fixed tool sequence, and the turn ends once every step has a tool result.
const commandScript = path.join(shared, "command.mjs");
const bash = (command) => ({ tool: "Bash", input: { command, description: "Fixture step" } });
const report = (label) => bash(`node ${commandScript} ${label} 200`);
const work = (label, ...args) => bash(`node ${commandScript} ${label} -- work ${args.join(" ")}`);
const enter = (target) => ({ tool: "EnterWorktree", input: { path: target } });
const exit = () => ({ tool: "ExitWorktree", input: { action: "keep" } });
const sequences = {
  // From the main checkout: enter, bind, switch directly, finish, leave,
  // enter the next Worktree, finish, leave, and enter the first one again.
  "a-enter-first": [enter(first), work("a-show-entered-first", "show"), work("a-start-1", "start", "issue-1"), work("a-show-bound-1", "show")],
  "a-direct-second": [enter(second), work("a-show-after-direct", "show")],
  "a-finish-1": [work("a-stop-1", "stop"), exit(), work("a-show-returned-1", "show")],
  "a-enter-second": [enter(second), work("a-show-entered-second", "show"), work("a-start-2", "start", "issue-2"), work("a-show-bound-2", "show")],
  "a-finish-2": [work("a-stop-2", "stop"), exit(), work("a-show-returned-2", "show")],
  "a-reenter-first": [enter(first), work("a-show-reentered", "show"), work("a-start-1-again", "start", "issue-1"), work("a-show-bound-1-again", "show")],
  "a-leave-bound": [exit(), work("a-show-left-bound", "show"), work("a-stop-left", "stop")],
  // Launched in a linked Worktree: enter a sibling, enter the main checkout,
  // exit, change the shell's directory to the main checkout, and enter the
  // other sibling.
  "c-bind": [work("c-start-3", "start", "issue-3"), work("c-show-bound", "show")],
  "c-enter-sibling": [enter(first), work("c-show-after-enter", "show")],
  "c-enter-main": [enter(fixture), report("c-after-enter-main")],
  "c-exit": [exit(), report("c-after-exit")],
  "c-cd-main": [bash(`cd ${fixture}`), report("c-after-cd")],
  "c-enter-second": [enter(second), work("c-show-entered-second", "show")],
  "c-stop": [work("c-stop-3", "stop")],
  // The same with `.claude/worktrees/` present.
  "d-enter-sibling": [work("d-start-4", "start", "issue-4"), enter(first), work("d-show-after-enter", "show")],
  "d-enter-managed": [enter(managed), work("d-show-after-managed", "show")],
  "d-stop": [work("d-stop-4", "stop")],
  // From the main checkout with `.claude/worktrees/` present: a direct switch
  // to a sibling, then to a Worktree under it, then exit and enter again.
  "b-enter-first": [enter(first), work("b-start-5", "start", "issue-5"), work("b-show-bound", "show")],
  "b-direct-second": [enter(second), work("b-show-after-direct", "show")],
  "b-direct-managed": [enter(managed), work("b-show-after-managed", "show")],
  "b-exit-reenter": [exit(), work("b-show-returned", "show"), enter(second), work("b-show-entered-second", "show")],
  "b-stop": [work("b-stop-5", "stop"), exit()],
  // A session that entered a Worktree and ended there, resumed in it as the
  // Sessions pane's copied `cd <worktree> && claude --resume <id>` does.
  "e-enter-first": [enter(first), report("e-entered-first")],
  "e-direct-second": [enter(second), work("e-show-after-direct", "show")],
  "e-cd-main": [bash(`cd ${fixture}`), report("e-after-cd")],
  "e-exit": [exit(), work("e-show-returned", "show")],
  "e-enter-second": [enter(second), work("e-show-entered-second", "show")],
};
// The worktree tools' outcomes and those of a bare `cd` are evidence; every
// other tool result stays out of the trace.
const evidential = (use) => /Worktree$/.test(use.name) || (use.name === "Bash" && /^cd \S+$/.test(use.input?.command ?? ""));
let toolsRecorded = false;
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
      const match = part.type === "text" && part.text?.match(/SPIKE:([a-z0-9-]+)/);
      if (match) { label = match[1]; latestUser = index; }
    }
  });
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  // Claude Code's own statement of the worktree tools' rules, once.
  if (!toolsRecorded && tools.includes("EnterWorktree")) {
    toolsRecorded = true;
    trace("tools", { descriptions: Object.fromEntries(payload.tools.filter((tool) => /Worktree$/.test(tool.name)).map((tool) => [tool.name, tool.description])) });
  }
  const later = messages.slice(latestUser + 1);
  const results = later.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : []);
  const outcomes = later.flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_use" && evidential(part)) : [])
    .map((use) => {
      const result = results.find((part) => part.tool_use_id === use.id);
      const text = typeof result?.content === "string" ? result.content : result?.content?.map((part) => part.text ?? "").join(" ") ?? "";
      return { tool: use.name, path: use.input?.path, isError: result?.is_error ?? null, text: text.slice(0, 600) };
    });
  const sequence = (label && sequences[label]) || [];
  const step = sequence[results.length];
  trace("model.request", { label, step: results.length, tool: step?.tool ?? null, available: step ? tools.includes(step.tool) : null,
    outcomes: outcomes.length ? outcomes : undefined });
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [{ type: "text", text: "Fixture complete." }],
      stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage: { input_tokens: 10, output_tokens: 1 } } });
  if (step && tools.includes(step.tool)) {
    sse("content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label}_${records.length}`, name: step.tool, input: {} } });
    sse("content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(step.input) } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { output_tokens: 20 } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: "Fixture complete." } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { output_tokens: 4 } });
  }
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// Subscribe the hook exactly as `dashpot integrate claude-code` does, with the
// #162 wrapper in place of the publisher.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import CLAUDE_CODE as c; print(json.dumps({'events': c.events, 'matched': c.matched_events}))"], { encoding: "utf8" }));
const handler = { type: "command", command: `${process.execPath} ${path.join(shared, "hook.mjs")}`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: Object.fromEntries([fixture, first, second, launch, managed].map((dir) => [dir, { hasTrustDialogAccepted: true, allowedTools: [] }])),
}, null, 2));

const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
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
// What a person's dashboard reads: the headless snapshot of the Project.
const observe = (label) => {
  let snapshot = null;
  let error = null;
  try { snapshot = JSON.parse(execFileSync(dashpot, ["--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 })); } catch (failure) { error = String(failure).slice(0, 500); }
  const runs = (snapshot?.agentRuns ?? []).map(({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }) =>
    ({ harness, processOrSession, state, observationTarget, issueId, workingDirectory, orphaned }));
  const diagnostics = [...(snapshot?.diagnostics ?? []), ...(snapshot?.projects ?? []).flatMap((project) => project.snapshot?.diagnostics ?? [])]
    .map(({ code, severity, message }) => ({ code, severity, message: retained(message).slice(0, 300) }));
  return trace("observation", { label, error, runs, diagnostics });
};
const hooks = () => records.filter((record) => record.kind === "hook");
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
const hookOf = (session, event, since = 0) => hooks().slice(since).find((record) => record.payload.session_id === session && record.event === event && !record.payload.agent_id);
const stopsOf = (session) => hooks().filter((record) => record.payload.session_id === session && record.event === "Stop").length;

// A headless client: one `claude -p` process taking its user turns as
// stream-json on stdin, observed after every turn and ended by closing its
// input.
const client = async (name, cwd, resume = null) => {
  const child = spawn(launcher, ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", ...commonArgs, ...(resume ? ["--resume", resume] : [])],
    { cwd, env, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: resume, exited: null };
  let buffer = "";
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      try { const message = JSON.parse(line); if (message.session_id && !state.session) state.session = message.session_id; } catch {}
    }
  });
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { state.exited = { status, signal }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, cwd, pid: child.pid, resume });
  state.turn = async (label) => {
    const before = state.session ? stopsOf(state.session) : 0;
    child.stdin.write(JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text: `SPIKE:${label}` }] } }) + "\n");
    await waitFor(() => state.session && stopsOf(state.session) > before, `${name} ${label} Stop`, 90000);
    trace("turn", { client: name, label, session: state.session });
    await delay(500);
    observe(label);
  };
  state.end = async () => {
    const before = hooks().length;
    child.stdin.end();
    await waitFor(() => state.exited && hookOf(state.session, "SessionEnd", before), `${name} SessionEnd and exit`, 60000);
    observe(`${name}-ended`);
  };
  return state;
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(), subscriptions: integration,
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")),
    fixture, first, second, launch, managed,
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    sourceSHA256: Object.fromEntries([
      ...["run.mjs", "verify.mjs"].map((file) => [file, path.join(here, file)]),
      ...["hook.mjs", "command.mjs", "ancestry.mjs"].map((file) => [`claude-162/${file}`, path.join(shared, file)]),
      ...["harnesses.py", "hook_publish.py", "work_reconciliation.py", "hook_records.py", "work.py"].map((file) => [`src/dashpot/sessions/${file}`, path.join(checkout, "src", "dashpot", "sessions", file)])]
      .map(([name, file]) => [name, createHash("sha256").update(readFileSync(file)).digest("hex")])) });

  // Scenario A: a client launched in the main checkout, with no
  // `.claude/worktrees/`, moves between Issue Worktrees.
  trace("scenario", { name: "from-main-checkout" });
  const a = await client("a", fixture);
  for (const label of ["a-enter-first", "a-direct-second", "a-finish-1", "a-enter-second", "a-finish-2", "a-reenter-first", "a-leave-bound"]) await a.turn(label);
  await a.end();

  // Scenario C: a client launched in a linked Worktree.
  trace("scenario", { name: "launched-in-linked-worktree" });
  const c = await client("c", launch);
  for (const label of ["c-bind", "c-enter-sibling", "c-enter-main", "c-exit", "c-cd-main", "c-enter-second", "c-stop"]) await c.turn(label);
  await c.end();

  // `.claude/worktrees/` exists from here on, as it does once Claude Code has
  // created a managed worktree in the Repository, with one linked Worktree in it.
  mkdirSync(managedDirectory, { recursive: true });
  git("worktree", "add", "-b", "managed", managed);
  trace("managed-directory", { created: managedDirectory, worktree: managed });

  // Scenario D: Scenario C with `.claude/worktrees/` present.
  trace("scenario", { name: "launched-in-linked-worktree-managed-directory" });
  const d = await client("d", launch);
  for (const label of ["d-enter-sibling", "d-enter-managed", "d-stop"]) await d.turn(label);
  await d.end();

  // Scenario B: Scenario A's moves with `.claude/worktrees/` present.
  trace("scenario", { name: "from-main-checkout-managed-directory" });
  const b = await client("b", fixture);
  for (const label of ["b-enter-first", "b-direct-second", "b-direct-managed", "b-exit-reenter", "b-stop"]) await b.turn(label);
  await b.end();

  // Scenario E: a session ended inside the Worktree it entered, then resumed
  // there. Its transcript restores the worktree session it was in.
  trace("scenario", { name: "resumed-in-entered-worktree" });
  const e = await client("e", fixture);
  await e.turn("e-enter-first");
  await e.end();
  const resumed = await client("e-resumed", first, e.session);
  for (const label of ["e-direct-second", "e-cd-main", "e-exit", "e-enter-second"]) await resumed.turn(label);
  await resumed.end();
  // ExitWorktree(keep) removes nothing: every Worktree the sessions visited stays registered.
  trace("worktrees", { paths: git("worktree", "list", "--porcelain").toString().split("\n").filter((line) => line.startsWith("worktree ")).map((line) => line.slice(9)) });
  console.log(`All scenarios completed: ${root}`);
} finally {
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
