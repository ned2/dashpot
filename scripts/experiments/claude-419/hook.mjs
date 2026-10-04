// Hook command for the Claude Code 419 worker-mechanics run: hands the hook
// input to Dashpot's real Claude Code publisher, then posts the input's
// identity and location fields, the Claude Code identity variables, this
// process's ancestry, and the publisher's exit status and any output to the
// runner's sink.
// The publisher's output is passed on to Claude Code unchanged.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts and tool responses stay out of the trace. The worktree
// tools' inputs are kept: they say where the session was asked to go. A
// prompt is reduced to what kind of turn it started, by the fixture's labels
// and the harness's wrappers.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "tool_use_id", "permission_mode", "stop_hook_active"];
// The Claude Code variables that say which session and process a shell or
// hook belongs to; the rest are the fixture's own settings, recorded once.
const identityEnv = ["CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_CODE_CHILD_SESSION",
  "CLAUDE_JOB_DIR", "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const input = payload.tool_input ?? {};
const prompt = typeof payload.prompt === "string" ? payload.prompt : null;
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 20000 });
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  prompt: prompt === null ? undefined : {
    labels: [...prompt.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]),
    marks: [...prompt.matchAll(/MARK:([a-z0-9-]+)/g)].map((match) => match[1]),
    agentMessage: prompt.includes("<agent-message"),
    taskNotification: prompt.includes("<task-notification>"),
    slash: prompt.trimStart().startsWith("/"),
  },
  backgroundTasks: Array.isArray(payload.background_tasks) ? payload.background_tasks.length : undefined,
  toolInput: payload.tool_input === undefined ? undefined : { keys: Object.keys(input), path: input.path, name: input.name, action: input.action },
  // A clean publish is recorded by its status alone.
  publisher: published.status === 0 && !published.signal && !published.stdout && !published.stderr ? { status: 0 }
    : { status: published.status, signal: published.signal, stdout: published.stdout?.slice(0, 2000), stderr: published.stderr?.slice(-2000) },
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => identityEnv.includes(key))),
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm })),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(5000) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
if (published.stdout) process.stdout.write(published.stdout);
process.exitCode = published.status ?? 1;
