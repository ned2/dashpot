// Live background-command run for Issue #466: what becomes of a Claude Code
// Bash command started with `run_in_background` when the turn that started
// it ends, when its session moves to another Worktree with `EnterWorktree`,
// when `/clear` replaces the session, when the person exits, and when a
// headless `claude -p` finishes, and whether Dashpot's `process` Cleanup
// blocker (ADR 0104) names the command in the Worktree it runs in after each.
// Drives a pinned Claude Code binary against a loopback Messages API fixture
// with an isolated configuration. Every subscribed hook event goes to
// Dashpot's real Claude Code publisher, run from this checkout's working
// tree, and after each action the runner records the command's process, the
// session's stored hook record, and `dashpot worktree check --json` of both
// linked Worktrees. The trace is metadata only: prompts and transcripts stay
// out, apart from the fixture's own labels. The verifier checks the trace
// against the findings.
//
// Usage: node run.mjs <absolute claude binary> [expected version]
// SPIKE_SCENARIOS=<comma-separated names> runs a subset.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, spawnSync, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, readlinkSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ancestry, describe } from "./ancestry.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const checkout = path.resolve(here, "..", "..", "..");
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-466-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const worktreeA = path.join(root, "repository.worktrees", "a");
const worktreeB = path.join(root, "repository.worktrees", "b");
const gates = path.join(root, "gates");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const retained = (text) => String(text).replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT").replaceAll(checkout, "$CHECKOUT").replaceAll(os.homedir(), "$HOME");
const trace = (kind, fields = {}) => {
  const record = { kind, ...fields, receipt: records.length + 1, receiptTime: Date.now() };
  records.push(record);
  appendFileSync(tracePath, retained(JSON.stringify(record)) + "\n");
  return record;
};
const binary = process.argv[2];
assert(binary && path.isAbsolute(binary), "Pass the absolute path to the Claude Code binary");
const expectedVersion = process.argv[3] ?? "2.1.289";
const selected = process.env.SPIKE_SCENARIOS ? new Set(process.env.SPIKE_SCENARIOS.split(",")) : null;
const python = path.join(checkout, ".venv", "bin", "python");
const dashpotCommand = path.join(checkout, ".venv", "bin", "dashpot");

// A harness session above the runner would be the host Dashpot finds for
// any fixture process it does not recognise, and would collect the fixture's
// hook records, so the runner refuses to start below one.
const above = ancestry(process.ppid, 64, 1);
const host = above.find((entry) => entry.comm === "claude" || entry.comm.startsWith("codex") || entry.comm === "opencode"
  || /^\S*\/claude\/versions\/[^\s/]+(\s|$)/.test(entry.cmdline));
assert(!host, `Run this outside every harness session (for example with \`setsid -f\`): pid ${host?.pid} is ${host?.comm}`);
const launcherDirectory = path.join(root, "bin");
mkdirSync(launcherDirectory);
const launcher = path.join(launcherDirectory, "claude");
symlinkSync(binary, launcher);

// The publisher is this checkout's working tree (its editable install).
const publisher = path.join(launcherDirectory, "publisher");
writeFileSync(publisher, `#!/bin/sh\nexec '${python}' -c 'import sys; import dashpot.hook as h; sys.exit(h.claude_code_main())'\n`);
chmodSync(publisher, 0o755);
const loadedFrom = () => retained(execFileSync(python, ["-c", "import dashpot.sessions.working_directories as m; print(m.__file__)"], { encoding: "utf8" }).trim());

const home = path.join(root, "home");
const env = {
  PATH: `${launcherDirectory}:${path.dirname(process.execPath)}:/usr/bin:/bin`,
  HOME: home,
  XDG_CONFIG_HOME: path.join(root, "config"),
  XDG_DATA_HOME: path.join(root, "data"),
  XDG_CACHE_HOME: path.join(root, "cache"),
  XDG_STATE_HOME: path.join(root, "state"),
  TMPDIR: path.join(root, "tmp"),
  CLAUDE_CONFIG_DIR: path.join(home, ".claude"),
  ANTHROPIC_API_KEY: "fixture-unused",
  DISABLE_AUTOUPDATER: "1",
  DISABLE_TELEMETRY: "1",
  DISABLE_ERROR_REPORTING: "1",
  DISABLE_BUG_COMMAND: "1",
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
  CLAUDE_CODE_DISABLE_TERMINAL_TITLE: "1",
  TERM: "dumb",
  SPIKE_STOP_PID: String(process.pid),
  SPIKE_PUBLISHER: publisher,
  SPIKE_GATES: gates,
};
for (const dir of [fixture, gates, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);

// A Dashpot Project with two linked Worktrees, `a` and `b`, beside it.
mkdirSync(path.join(fixture, ".dashpot"), { recursive: true });
mkdirSync(path.join(fixture, "issues"), { recursive: true });
writeFileSync(path.join(fixture, "issues", ".keep"), "");
writeFileSync(path.join(fixture, ".dashpot", "config.json"), JSON.stringify({ projectId: "project:fixture", displayLabel: "Fixture", repositoryId: "repository:fixture", issueSource: { kind: "markdown", path: "issues" } }));
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
// Hook stores and Claude Code's own files stay out of every Worktree's status.
writeFileSync(path.join(fixture, ".git", "info", "exclude"), "/.claude/\n/.dashpot/state/\n");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
for (const [name, worktree] of [["a", worktreeA], ["b", worktreeB]]) git("worktree", "add", "-b", name, worktree);

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
  trace(url.pathname === "/hook" ? "hook" : "command", record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The subscriptions `dashpot integrate claude-code` installs, read from this
// checkout, each publishing.
const integration = JSON.parse(execFileSync(python, ["-c",
  "import json; from dashpot.sessions.integrate import integration; c = integration('claude-code'); print(json.dumps({'events': c.events, 'matched': c.matched_events}))"],
  { encoding: "utf8", env: { ...env, PATH: "/usr/bin:/bin" } }));
const handler = { type: "command", command: `${process.execPath} ${path.join(here, "hook.mjs")}`, timeout: 15 };
const subscriptions = {};
for (const event of integration.events) (subscriptions[event] ??= []).push({ hooks: [handler] });
for (const [event, matcher] of integration.matched) (subscriptions[event] ??= []).push({ matcher, hooks: [handler] });
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({ hooks: subscriptions }, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: Object.fromEntries([fixture, worktreeA, worktreeB].map((dir) => [dir, { hasTrustDialogAccepted: true, allowedTools: [] }])),
}, null, 2));

// The fixture model. A turn is named by the `SPIKE:<label>` in the latest
// user text message; each tool result since then advances its sequence by a
// step. A user text message with no label (a task notification) is answered
// with plain text.
const node = process.execPath;
const commandScript = path.join(here, "command.mjs");
const backgrounded = (label, gate) => ({ tool: "Bash", input: { command: `${node} ${commandScript} ${label} wait ${gate}`, description: "Fixture background step", run_in_background: true } });
const enter = (target) => ({ tool: "EnterWorktree", input: { path: target } });
const sequences = {};
const textParts = (content) => typeof content === "string" ? [content] : (content ?? []).filter((part) => part.type === "text").map((part) => part.text ?? "");
const hasResult = (message) => Array.isArray(message.content) && message.content.some((part) => part.type === "tool_result");
const labelsIn = (text) => [...text.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]);
const model = await listen(async (req, res) => {
  const url = new URL(req.url, "http://fixture");
  const payload = await body(req);
  if (url.pathname.endsWith("/count_tokens")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ input_tokens: 100 }));
    return;
  }
  if (!url.pathname.endsWith("/messages")) {
    trace("model.other", { path: url.pathname, method: req.method });
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ type: "error", error: { type: "not_found_error", message: "fixture" } }));
    return;
  }
  const messages = payload.messages ?? [];
  const tools = payload.tools?.map((tool) => tool.name) ?? [];
  let trigger = -1;
  messages.forEach((message, index) => { if (message.role === "user" && textParts(message.content).join("").trim()) trigger = index; });
  const triggerText = trigger >= 0 ? textParts(messages[trigger].content).join("\n") : "";
  const notification = triggerText.includes("<task-notification>");
  const label = notification ? null : labelsIn(triggerText).at(-1) ?? null;
  const done = messages.slice(trigger + 1).filter((message) => message.role === "user" && hasResult(message)).length;
  const sequence = (label && sequences[label]) || null;
  const step = sequence?.steps[done] ?? null;
  const available = step ? tools.includes(step.tool) : null;
  trace("model.request", { label, step: done, tool: step?.tool ?? null, available, messages: messages.length, stream: Boolean(payload.stream), triggerNotification: notification });
  const final = sequence && done >= sequence.steps.length ? sequence.final ?? "Fixture complete." : "Fixture complete.";
  const usage = { input_tokens: 10, output_tokens: 1 };
  if (!payload.stream) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [{ type: "text", text: "Fixture complete." }],
      stop_reason: "end_turn", stop_sequence: null, usage: { input_tokens: 10, output_tokens: 4 } }));
    return;
  }
  const sse = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify({ type: event, ...data })}\n\n`);
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  sse("message_start", { message: { id: `msg_${records.length}`, type: "message", role: "assistant", model: payload.model ?? "fixture", content: [], stop_reason: null, stop_sequence: null, usage } });
  if (step && available) {
    sse("content_block_start", { index: 0, content_block: { type: "tool_use", id: `toolu_${label}_${records.length}`, name: step.tool, input: {} } });
    sse("content_block_delta", { index: 0, delta: { type: "input_json_delta", partial_json: JSON.stringify(step.input) } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "tool_use", stop_sequence: null }, usage: { ...usage, output_tokens: 20 } });
  } else {
    sse("content_block_start", { index: 0, content_block: { type: "text", text: "" } });
    sse("content_block_delta", { index: 0, delta: { type: "text_delta", text: step ? "Fixture tool unavailable." : final } });
    sse("content_block_stop", { index: 0 });
    sse("message_delta", { delta: { stop_reason: "end_turn", stop_sequence: null }, usage: { ...usage, output_tokens: 4 } });
  }
  sse("message_stop", {});
  res.end();
});
env.ANTHROPIC_BASE_URL = model.url;

// Runner helpers.
const commonArgs = ["--dangerously-skip-permissions", "--model", "fixture-model"];
const hooks = () => records.filter((record) => record.kind === "hook");
const command = (label, phase = "end") => records.find((record) => record.kind === "command" && record.label === label && record.phase === phase);
const waitFor = async (predicate, label, timeout = 60000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (predicate()) return true; await delay(100); }
  throw new Error(`Timed out: ${label}`);
};
// Waits that are themselves the measurement record a timeout, not a failure.
const settle = async (predicate, label, timeout) => {
  try { await waitFor(predicate, label, timeout); trace("wait", { label, met: true }); return true; } catch { trace("wait", { label, met: false, timeout }); return false; }
};
const open = (gate) => { writeFileSync(path.join(gates, gate), ""); trace("gate", { gate }); };
const mark = () => records.length;
const mainStopAfter = (client, since) => hooks().some((record) => record.receipt > since && record.hostPid === client.host && record.event === "Stop" && !record.payload.agent_id);
const fixtureProcesses = () => {
  const found = [];
  for (const name of readdirSync("/proc")) {
    if (!/^\d+$/.test(name)) continue;
    let environ;
    try { environ = readFileSync(`/proc/${name}/environ`, "utf8"); } catch { continue; }
    if (!environ.includes(`SPIKE_GATES=${gates}`)) continue;
    try { found.push(describe(Number(name))); } catch {}
  }
  return found;
};
const stripAnsi = (text) => text.replace(/\u001b\][^\u0007\u001b]*(?:\u0007|\u001b\\)/g, "").replace(/\u001b\[[0-9;?<=>]*[ -\/]*[@-~]/g, "").replace(/\u001b[()][0-9A-Za-z]|\u001b[=>78]/g, "");

// A process as the host's process table shows it now: whether it runs, and
// its parent, process group, session and working directory.
const processState = (pid) => {
  let stat;
  try { stat = readFileSync(`/proc/${pid}/stat`, "utf8"); } catch { return { pid, alive: false }; }
  const close = stat.lastIndexOf(")");
  const fields = stat.slice(close + 2).split(" ");
  if (fields[0] === "Z") return { pid, alive: false, zombie: true };
  let cwd = null;
  try { cwd = retained(readlinkSync(`/proc/${pid}/cwd`)); } catch {}
  return { pid, alive: true, comm: stat.slice(stat.indexOf("(") + 1, close), ppid: Number(fields[1]), pgid: Number(fields[2]), sid: Number(fields[3]), cwd };
};
// `dashpot worktree check --json` of a Worktree, run from the main checkout,
// reduced to each blocker's kind, the session it names, and the processes a
// `process` blocker names.
const check = (worktree) => {
  const ran = spawnSync(dashpotCommand, ["worktree", "check", worktree, "--json"], { cwd: fixture, env, encoding: "utf8", timeout: 60000 });
  let parsed = null;
  try { parsed = JSON.parse(ran.stdout); } catch {}
  if (!parsed) return { status: ran.status, stderr: retained(ran.stderr ?? "").slice(-400) };
  return { status: ran.status, removable: parsed.removable, uncheckedProcesses: parsed.uncheckedProcesses,
    blockers: parsed.obstacles.map((obstacle) => ({ kind: obstacle.kind,
      session: obstacle.detail.match(/session ([0-9a-f-]{36})/)?.[1] ?? null,
      processes: obstacle.kind === "process" ? [...obstacle.detail.matchAll(/pid (\d+) \(([^)]*)\) at (\S+?)(?=; |\. Removing)/g)].map((match) => ({ pid: Number(match[1]), comm: match[2], cwd: retained(match[3]) })) : undefined,
      command: obstacle.kind === "process" ? obstacle.command : undefined })) };
};
// Every hook record Dashpot holds for a session, in each checkout's store.
const storedSession = (session) => [["main", fixture], ["a", worktreeA], ["b", worktreeB]].flatMap(([name, checkoutPath]) => {
  const directory = path.join(checkoutPath, ".dashpot", "state", "sessions");
  let names = [];
  try { names = readdirSync(directory).filter((file) => file.endsWith(".json")); } catch { return []; }
  return names.flatMap((file) => {
    try {
      const record = JSON.parse(readFileSync(path.join(directory, file), "utf8"));
      if (record.sessionId !== session) return [];
      return [{ store: name, event: record.event, state: record.state, cwd: retained(record.cwd ?? ""), turnStartedAt: record.turnStartedAt ?? null, liveSubagents: record.liveSubagents ?? null }];
    } catch (error) { return [{ store: name, file, error: String(error).slice(0, 200) }]; }
  });
});
// What the run sees at one point of a scenario: the background command, its
// session's records, and both Worktrees' checks.
const probe = (p, label, sessions) => {
  const started = command(`${p}-bg`, "start");
  return trace("probe", { scenario: p, label,
    command: started ? processState(started.pid) : null,
    shell: started ? processState(started.ppid) : null,
    commandEnded: Boolean(command(`${p}-bg`)),
    stored: Object.fromEntries(sessions.filter(Boolean).map((session) => [session, storedSession(session)])),
    checks: { a: check(worktreeA), b: check(worktreeB) } });
};

// An interactive session on a pseudo-terminal, typed into as a person would.
const interactive = async (name, cwd) => {
  const since = mark();
  const child = spawn("script", ["-qfec", [launcher, ...commonArgs].join(" "), "/dev/null"],
    { cwd, env: { ...env, TERM: "xterm-256color", COLUMNS: "120", LINES: "40" }, stdio: ["pipe", "pipe", "pipe"] });
  const state = { name, child, session: null, host: null, exited: null, output: "" };
  child.stdout.on("data", (chunk) => { state.output += stripAnsi(String(chunk)); if (state.output.length > 200000) state.output = state.output.slice(-100000); });
  child.on("exit", (status, signal) => { state.exited = { status, signal, at: Date.now() }; trace("client.exit", { name, status, signal }); });
  trace("client.spawn", { name, mode: "interactive", pid: child.pid, cwd: retained(cwd) });
  const started = () => hooks().find((record) => record.receipt > since && record.event === "SessionStart" && record.ancestry.some((entry) => entry.pid === child.pid));
  try { await waitFor(started, `${name} SessionStart`, 60000); } catch (error) {
    writeFileSync(path.join(root, `screen-${name}.txt`), state.output);
    throw error;
  }
  state.session = started().payload.session_id;
  state.host = started().hostPid;
  trace("client.ready", { name, session: state.session, host: state.host });
  await delay(3000);
  state.type = async (text) => { child.stdin.write(text); await delay(400); child.stdin.write("\r"); };
  state.turn = async (text) => {
    const before = mark();
    await state.type(text);
    trace("turn.sent", { client: name, text });
    try { await waitFor(() => mainStopAfter(state, before), `${name} ${text} Stop`, 90000); } catch (error) {
      writeFileSync(path.join(root, `screen-${name}.txt`), state.output);
      throw error;
    }
  };
  state.screen = (label) => trace("screen", { client: name, label, tail: retained(state.output.slice(-900)).replace(/\s+/g, " ") });
  return state;
};
const exitClient = async (client) => {
  if (client.exited) return;
  await client.type("/exit");
  trace("action.end", { client: client.name, how: "/exit typed" });
  await settle(() => client.exited, `${client.name} exit`, 20000);
  if (!client.exited) { client.screen(`${client.name}-exit`); writeFileSync(path.join(root, `screen-${client.name}-exit.txt`), client.output); client.child.kill("SIGKILL"); trace("action.close", { client: client.name }); await settle(() => client.exited, `${client.name} exit after close`, 10000); }
};

// The session starts a background command in Worktree `a`, which holds on a
// gate, and its turn ends.
const startBackground = async (p, client) => {
  sequences[`${p}-start`] = { steps: [backgrounded(`${p}-bg`, `${p}-go`)], final: "Started in the background." };
  await client.turn(`SPIKE:${p}-start`);
  await waitFor(() => command(`${p}-bg`, "start"), `${p}-bg start`, 30000);
  await delay(2000);
};
// The gate opens; the command's end, and any notice of it, are awaited.
const release = async (p, client) => {
  const since = mark();
  open(`${p}-go`);
  await settle(() => command(`${p}-bg`), `${p}-bg end`, 20000);
  await settle(() => hooks().some((record) => record.receipt > since && record.event === "UserPromptSubmit" && record.prompt?.taskNotification), `${p} task notification`, 15000);
  if (client && !client.exited) await settle(() => mainStopAfter(client, since), `${p} notification Stop`, 30000);
};

const scenarios = [];
const scenario = (name, run) => scenarios.push({ name, run });

// The turn that started the command ends; the command's end wakes the session.
scenario("turn-end", async () => {
  const p = "te";
  const client = await interactive(p, worktreeA);
  await startBackground(p, client);
  probe(p, "after-turn", [client.session]);
  await release(p, client);
  probe(p, "after-release", [client.session]);
  await exitClient(client);
});

// The session moves to Worktree `b` with `EnterWorktree` while its command
// runs in `a`.
scenario("move", async () => {
  const p = "mv";
  const client = await interactive(p, worktreeA);
  await startBackground(p, client);
  sequences[`${p}-move`] = { steps: [enter(worktreeB)], final: "Moved." };
  await client.turn(`SPIKE:${p}-move`);
  await delay(2000);
  probe(p, "after-move", [client.session]);
  await release(p, client);
  probe(p, "after-release", [client.session]);
  await exitClient(client);
});

// `/clear` replaces the session while its command runs.
scenario("clear", async () => {
  const p = "cl";
  const client = await interactive(p, worktreeA);
  await startBackground(p, client);
  const since = mark();
  await client.type("/clear");
  trace("action", { scenario: p, action: "/clear" });
  const cleared = () => hooks().find((record) => record.receipt > since && record.event === "SessionStart" && record.hostPid === client.host);
  await settle(cleared, `${p} SessionStart`, 20000);
  await delay(2000);
  client.screen(`${p}-cleared`);
  probe(p, "after-clear", [client.session, cleared()?.payload.session_id]);
  await release(p, client);
  probe(p, "after-release", [client.session, cleared()?.payload.session_id]);
  await exitClient(client);
});

// The person types `/exit` while the command runs, and answers the dialog
// that names the running work with `choice`: Enter for its first option,
// or Down and Enter for its second.
const exitWith = async (p, client, choice) => {
  const shown = client.output.length;
  await client.type("/exit");
  trace("action.end", { client: client.name, how: "/exit typed" });
  const dialog = () => /Background work is running/.test(client.output.slice(shown).replace(/\s+/g, " "));
  await settle(dialog, `${p} exit dialog`, 15000);
  client.screen(`${p}-exit-dialog`);
  if (choice === "second") { client.child.stdin.write("\u001b[B"); await delay(400); }
  client.child.stdin.write("\r");
  trace("action.choose", { client: client.name, choice });
  await settle(() => client.exited, `${p} exit`, 30000);
};
// The daemons' directories under /tmp/cc-daemon-<uid>/, which the user's own
// sessions share: the run records only how many entries appeared or went
// relative to those present when it started.
const daemonRoot = `/tmp/cc-daemon-${os.userInfo().uid}`;
const daemonDirectories = () => { try { return readdirSync(daemonRoot).sort(); } catch { return []; } };
let daemonBaseline = [];
const daemonChange = () => {
  const now = daemonDirectories();
  return { preexisting: daemonBaseline.length, preexistingKept: daemonBaseline.every((name) => now.includes(name)),
    added: now.filter((name) => !daemonBaseline.includes(name)).length, removed: daemonBaseline.filter((name) => !now.includes(name)).length };
};
// A Claude Code subcommand in the fixture's environment, such as `agents`.
const claude = async (args, label, timeout = 30000) => {
  const child = spawn(launcher, args, { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), timeout);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  let agents;
  if (args[0] === "agents") {
    try {
      agents = JSON.parse(stdout).map(({ id, kind, pid, sessionId, state, status: agentStatus, cwd }) => ({ id, kind, pid, sessionId, state, status: agentStatus, cwd: cwd && retained(cwd) }));
    } catch { agents = null; }
  }
  trace("action.claude", { label, args, status, signal, agents, stdout: agents === undefined ? retained(stdout).slice(-400) : undefined, stderr: retained(stderr).slice(-400) });
  return { status, stdout, stderr, agents };
};

// `/exit`, choosing "Exit and stop tasks".
scenario("exit-stop", async () => {
  const p = "es";
  const client = await interactive(p, worktreeA);
  await startBackground(p, client);
  await exitWith(p, client, "first");
  await delay(2000);
  probe(p, "after-exit", [client.session]);
  await release(p, null);
  probe(p, "after-release", [client.session]);
});

// `/exit`, choosing "Move to background and exit".
scenario("exit-background", async () => {
  const p = "eb";
  const client = await interactive(p, worktreeA);
  await startBackground(p, client);
  trace("daemon.directories", { label: `${p}-before`, ...daemonChange() });
  const since = mark();
  await exitWith(p, client, "second");
  await delay(5000);
  trace("daemon.directories", { label: `${p}-exited`, ...daemonChange() });
  await claude(["agents", "--json", "--all"], `${p}-agents`);
  const sessions = [...new Set([client.session, ...hooks().filter((record) => record.receipt > since).map((record) => record.payload.session_id)])];
  probe(p, "after-exit", sessions);
  await release(p, null);
  probe(p, "after-release", sessions);
  await claude(["agents", "--json", "--all"], `${p}-agents-after`);
  await claude(["daemon", "stop", "--any"], `${p}-daemon-stop`);
  await settle(() => !fixtureProcesses().some((entry) => entry.comm === expectedVersion), `${p} daemon processes gone`, 20000);
  trace("daemon.directories", { label: `${p}-daemon-stopped`, ...daemonChange() });
});

// A headless `claude -p` whose only turn starts the command.
scenario("headless", async () => {
  const p = "hl";
  sequences[`${p}-start`] = { steps: [backgrounded(`${p}-bg`, `${p}-go`)], final: "Started in the background." };
  const child = spawn(launcher, ["-p", `SPIKE:${p}-start`, "--output-format", "json", ...commonArgs], { cwd: worktreeA, env, stdio: ["ignore", "pipe", "pipe"] });
  let exited = null;
  child.stdout.on("data", () => {});
  child.stderr.on("data", () => {});
  child.on("exit", (status, signal) => { exited = { status, signal }; trace("client.exit", { name: p, status, signal }); });
  trace("client.spawn", { name: p, mode: "headless", pid: child.pid, cwd: retained(worktreeA) });
  await waitFor(() => command(`${p}-bg`, "start"), `${p}-bg start`, 60000);
  // Whether `claude -p` waits for its background command before it exits.
  await settle(() => exited, `${p} exit while the command runs`, 30000);
  await delay(2000);
  const session = hooks().find((record) => record.event === "SessionStart" && record.ancestry.some((entry) => entry.pid === child.pid))?.payload.session_id ?? null;
  probe(p, "after-turn", [session]);
  await release(p, null);
  await settle(() => exited, `${p} exit`, 30000);
  if (!exited) { child.kill("SIGTERM"); await settle(() => exited, `${p} exit after SIGTERM`, 10000); }
  probe(p, "after-release", [session]);
});

const sha = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
try {
  const sources = ["sessions/hook_publish.py", "sessions/hook_records.py", "sessions/hook_scan.py", "sessions/working_directories.py",
    "repository/cleanup/obstacles.py", "hook.py"];
  daemonBaseline = daemonDirectories();
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version,
    binary, executable: execFileSync("readlink", ["-f", binary], { encoding: "utf8" }).trim(),
    subscriptions: { events: integration.events, matched: integration.matched },
    flags: Object.fromEntries(Object.entries(env).filter(([key]) => key.startsWith("CLAUDE") || key.startsWith("DISABLE") || key === "ANTHROPIC_BASE_URL")),
    fixture, worktrees: { a: worktreeA, b: worktreeB }, scenarios: scenarios.map((entry) => entry.name).filter((name) => !selected || selected.has(name)),
    dashpotHead: execFileSync("git", ["-C", checkout, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
    worktreeDirty: execFileSync("git", ["-C", checkout, "status", "--porcelain", "--", "src"], { encoding: "utf8" }).trim().split("\n").filter(Boolean),
    dashpot: loadedFrom(),
    experimentSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs"].map((file) => [file, sha(path.join(here, file))])),
    worktreeSourceSHA256: Object.fromEntries(sources.map((file) => [`src/dashpot/${file}`, sha(path.join(checkout, "src", "dashpot", file))])) });
  for (const { name, run } of scenarios) {
    if (selected && !selected.has(name)) continue;
    trace("scenario", { name });
    try { await run(); trace("scenario.end", { name, ok: true }); } catch (error) {
      trace("scenario.end", { name, ok: false, error: retained(String(error?.stack ?? error)).slice(0, 600) });
      console.log(`Scenario ${name} failed: ${error}`);
    }
    for (const entry of fixtureProcesses()) { trace("scenario.kill", { scenario: name, pid: entry.pid, comm: entry.comm }); try { process.kill(entry.pid, "SIGKILL"); } catch {} }
    await delay(1000);
  }
  console.log(`Scenarios completed: ${root}`);
} finally {
  // The fixture's own transient daemon, if any, is stopped rather than killed,
  // which removes its directory under /tmp/cc-daemon-<uid>/.
  await claude(["daemon", "stop", "--any"], "cleanup").catch(() => {});
  await delay(1000);
  trace("daemon.directories", { label: "cleanup", ...daemonChange() });
  for (const entry of fixtureProcesses()) {
    trace("cleanup.kill", { pid: entry.pid, comm: entry.comm });
    try { process.kill(entry.pid, "SIGKILL"); } catch {}
  }
  await delay(500);
  trace("cleanup.remaining", { pids: fixtureProcesses().map((entry) => entry.pid) });
  sink.server.closeAllConnections(); sink.server.close(); model.server.closeAllConnections(); model.server.close();
  trace("artifact", { root });
  console.log(`Metadata trace: ${tracePath}`);
  writeFileSync(path.join(root, "done"), "");
  if (process.env.SPIKE_REMOVE_FIXTURE === "1") rmSync(root, { recursive: true });
}
