// Hook command for the Claude Code 466 run. It hands the hook input to
// Dashpot's real Claude Code publisher (SPIKE_PUBLISHER), then posts the
// input's identity and lifecycle fields, the background tasks a stop
// reports, this process's ancestry and the publisher's exit status to the
// runner's sink. The publisher's output is passed on to Claude Code
// unchanged.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, summaries and tool responses stay out of the trace.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active", "prompt_id"];
const identityEnv = ["CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const prompt = typeof payload.prompt === "string" ? payload.prompt : null;
const published = spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 20000 });
const chain = ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm }));
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  prompt: prompt === null ? undefined : {
    labels: [...prompt.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]),
    taskNotification: prompt.includes("<task-notification>"),
    slash: prompt.trimStart().startsWith("/") ? prompt.trimStart().split(/\s/)[0] : false,
  },
  // The background tasks a stop reports, by identity and status only.
  backgroundTasks: Array.isArray(payload.background_tasks) ? payload.background_tasks.map((task) => ({ keys: Object.keys(task ?? {}),
    ...Object.fromEntries(["id", "task_id", "type", "status", "kind"].filter((key) => key in (task ?? {})).map((key) => [key, task[key]])) })) : undefined,
  publisher: published.status === 0 && !published.signal && !published.stdout && !published.stderr ? { status: 0 }
    : { status: published.status, signal: published.signal, stdout: published.stdout?.slice(0, 2000), stderr: published.stderr?.slice(-2000) },
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => identityEnv.includes(key))),
  // The Claude Code process this hook ran under: the Host Process.
  hostPid: Number(process.env.CLAUDE_PID) || chain.find((entry) => entry.comm === "claude")?.pid || null,
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: chain,
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(5000) });
} catch (error) {
  process.stderr.write(`hook trace failed: ${error}\n`);
}
if (published.stdout) process.stdout.write(published.stdout);
process.exitCode = published.status ?? 1;
