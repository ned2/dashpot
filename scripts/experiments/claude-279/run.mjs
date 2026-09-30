// Isolated Claude Code experiment for Issue #279: what SubagentStart and
// SubagentStop carry, what their `cwd` means, and whether a sub-agent that
// changes directory is visible in any hook. Drives a pinned Claude Code binary
// against a loopback Messages API fixture with an isolated configuration
// directory, records hook and shell evidence as a metadata-only trace, and
// asserts nothing about outcomes: the independent verifier checks the trace.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";
import { appendFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(path.join(os.tmpdir(), "dashpot-claude-279-"));
console.log(`Isolated fixture: ${root}`);
const fixture = path.join(root, "repository");
const nested = path.join(fixture, "nested");
// A linked Worktree beside the Repository, where Dashpot creates Issue Worktrees.
const sibling = path.join(root, "repository.worktrees", "sibling");
const tracePath = path.join(root, "trace.jsonl");
const records = [];
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// The retained stream names the disposable fixture root and this directory by
// placeholder: their absolute paths say nothing about Claude Code.
const retained = (text) => text.replaceAll(root, "$ROOT").replaceAll(here, "$EXPERIMENT");
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
for (const dir of [fixture, nested, env.HOME, env.XDG_CONFIG_HOME, env.XDG_DATA_HOME, env.XDG_CACHE_HOME,
  env.XDG_STATE_HOME, env.TMPDIR, env.CLAUDE_CONFIG_DIR]) mkdirSync(dir, { recursive: true });
const version = execFileSync(binary, ["--version"], { env, encoding: "utf8" }).trim();
assert.equal(version, `${expectedVersion} (Claude Code)`, `unexpected Claude Code version: ${version}`);
const git = (...args) => execFileSync("git", ["-C", fixture, ...args], { env, stdio: "pipe" });
git("init", "--initial-branch=main");
writeFileSync(path.join(nested, ".keep"), "");
git("add", ".");
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.hooksPath=/dev/null", "commit", "-m", "Disposable fixture");
git("worktree", "add", "-b", "sibling", sibling);

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
  trace(url.pathname.slice(1), record);
  res.end("{}");
});
env.SPIKE_SINK = sink.url;

// The fixture model: a `SPIKE:<label>` text in the conversation selects a
// fixed tool sequence, and the turn ends once every step has a tool result.
const commandScript = path.join(here, "command.mjs");
const bash = (command) => ({ tool: "Bash", input: { command, description: "Report fixture identity" } });
const report = (label, hold = 200) => bash(`node ${commandScript} ${label} ${hold}`);
const delegate = (child, extra = {}) => ({ tool: "Agent", input: { description: `Fixture ${child}`, prompt: `SPIKE:${child}`, subagent_type: "general-purpose", ...extra } });
const sequences = {
  // Parent stays at the launch directory; the child changes directory.
  "parent-root": () => [delegate("child-cd")],
  // Parent changes directory inside and outside the project before spawning.
  "parent-cd-nested": () => [bash(`cd ${nested}`), report("parent-nested"), delegate("child-report")],
  "parent-cd-sibling": () => [bash(`cd ${sibling}`), report("parent-sibling"), delegate("child-report")],
  // Parent moves with EnterWorktree, as Dashpot's Issue work does, then spawns.
  "parent-enter": () => [{ tool: "EnterWorktree", input: { path: sibling } }, report("parent-entered"), delegate("child-report")],
  // The sub-agent gets its own worktree from the Agent tool.
  "parent-isolated": () => [delegate("child-report", { isolation: "worktree" })],
  // A sub-agent whose `cd` is a command of its own, inside and outside the project.
  "parent-child-cd-alone": () => [delegate("child-cd-alone")],
  // A background sub-agent that changes directory.
  "parent-bg": () => [delegate("child-cd-bg", { run_in_background: true })],
  "child-report": () => [report("child")],
  "child-cd": () => [report("child-start"), bash(`cd ${sibling} && node ${commandScript} child-after-cd 200`), report("child-next")],
  "child-cd-alone": () => [bash(`cd ${nested}`), report("child-after-cd-nested"), bash(`cd ${sibling}`), report("child-after-cd-sibling")],
  "child-cd-bg": () => [report("child-bg-start"), bash(`cd ${sibling} && node ${commandScript} child-bg-after-cd 200`), report("child-bg-next")],
};
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
  const toolResults = messages.slice(latestUser + 1).flatMap((message) => Array.isArray(message.content) ? message.content.filter((part) => part.type === "tool_result") : []);
  const sequence = label && sequences[label] ? sequences[label]() : [];
  const step = sequence[toolResults.length];
  trace("model.request", { label, step: toolResults.length, tool: step?.tool ?? null, available: step ? tools.includes(step.tool) : null,
    stream: Boolean(payload.stream), messageCount: messages.length, toolCount: tools.length,
    toolResultHeads: toolResults.map((part) => (typeof part.content === "string" ? part.content : (part.content ?? []).map((item) => item.text ?? "").join(" ")).slice(0, 200)) });
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

// Every hook event a sub-agent could appear in, including the tool hooks and
// CwdChanged that Dashpot's integration does not subscribe to.
const hookCommand = `${process.execPath} ${path.join(here, "hook.mjs")}`;
const hookEvents = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart", "SubagentStop", "CwdChanged", "SessionEnd"];
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, "settings.json"), JSON.stringify({
  hooks: Object.fromEntries(hookEvents.map((event) => [event, [{ hooks: [{ type: "command", command: hookCommand, timeout: 10 }] }]])),
}, null, 2));
writeFileSync(path.join(env.CLAUDE_CONFIG_DIR, ".claude.json"), JSON.stringify({
  hasCompletedOnboarding: true, theme: "dark", bypassPermissionsModeAccepted: true,
  customApiKeyResponses: { approved: [env.ANTHROPIC_API_KEY.slice(-20)], rejected: [] },
  projects: { [fixture]: { hasTrustDialogAccepted: true, allowedTools: [] } },
}, null, 2));

const claude = async (args) => {
  const child = spawn(binary, args, { cwd: fixture, env, stdio: ["ignore", "pipe", "pipe"] });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const timer = setTimeout(() => child.kill("SIGTERM"), 120000);
  const [status, signal] = await once(child, "exit");
  clearTimeout(timer);
  trace("action.claude", { args, pid: child.pid, status, signal, stdout: stdout.slice(-1500), stderr: stderr.slice(-1500) });
  return { status, signal, stdout };
};

try {
  trace("environment", { version, platform: os.platform(), release: os.release(), arch: os.arch(), node: process.version, fixture, nested, sibling,
    sourceSHA256: Object.fromEntries(["run.mjs", "hook.mjs", "command.mjs", "ancestry.mjs", "verify.mjs"].map((file) => {
      try { return [file, createHash("sha256").update(readFileSync(path.join(here, file))).digest("hex")]; } catch { return [file, null]; }
    })) });
  for (const name of ["parent-root", "parent-cd-nested", "parent-cd-sibling", "parent-enter", "parent-isolated", "parent-child-cd-alone", "parent-bg"]) {
    if (process.env.SPIKE_ONLY && !process.env.SPIKE_ONLY.split(",").includes(name)) continue;
    trace("scenario", { name });
    await claude(["-p", `SPIKE:${name}`, "--output-format", "json", "--dangerously-skip-permissions", "--model", "fixture-model"]);
    // Late hooks from a background sub-agent land inside their scenario.
    await delay(2000);
    trace("worktrees", { list: git("worktree", "list", "--porcelain").toString() });
  }
} finally {
  trace("done", {});
  sink.server.close();
  model.server.close();
  console.log(`Trace: ${tracePath}`);
}
