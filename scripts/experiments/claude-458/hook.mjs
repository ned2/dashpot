// Hook command for the Claude Code 458 run. `node hook.mjs` hands the hook
// input to Dashpot's real Claude Code publisher (SPIKE_PUBLISHER), then posts
// the input's identity and lifecycle fields, this process's ancestry, the
// publisher's exit status, and the session records Dashpot's Project-local
// hook store holds once it has written. `node hook.mjs observe` records an
// event Dashpot does not subscribe, without publishing it.
// The publisher's output is passed on to Claude Code unchanged.
import { spawnSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { ancestry } from "./ancestry.mjs";

const observeOnly = process.argv[2] === "observe";
// Prompts, transcripts, summaries and tool responses stay out of the trace.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "trigger", "agent_id", "agent_type",
  "tool_name", "permission_mode", "stop_hook_active", "prompt_id"];
const identityEnv = ["CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION"];
const raw = readFileSync(0, "utf8");
let payload = {};
try { payload = JSON.parse(raw || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const prompt = typeof payload.prompt === "string" ? payload.prompt : null;
const published = observeOnly ? null : spawnSync(process.env.SPIKE_PUBLISHER, [], { input: raw, encoding: "utf8", timeout: 20000 });
// What Dashpot's store holds for every session once this event is published.
const store = () => {
  const directory = process.env.SPIKE_STORE;
  let names = [];
  try { names = readdirSync(directory).filter((name) => name.endsWith(".json")); } catch { return []; }
  return names.sort().flatMap((name) => {
    try {
      const record = JSON.parse(readFileSync(path.join(directory, name), "utf8"));
      return [{ sessionId: record.sessionId, event: record.event, source: record.source ?? null, reason: record.reason ?? null, agentId: record.agentId ?? null,
        state: record.state, liveSubagents: record.liveSubagents ?? null, turnStartedAt: record.turnStartedAt ?? null,
        lastSessionStartAt: record.lastSessionStartAt ?? null,
        processPid: record.sessionProcess?.pid ?? null, processStartedAt: record.sessionProcess?.startedAt ?? null }];
    } catch (error) { return [{ file: name, error: String(error).slice(0, 200) }]; }
  });
};
const chain = ancestry(process.ppid).map(({ pid, ppid, comm }) => ({ pid, ppid, comm }));
const record = {
  kind: "hook",
  observeOnly,
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  prompt: prompt === null ? undefined : {
    labels: [...prompt.matchAll(/SPIKE:([a-z0-9-]+)/g)].map((match) => match[1]),
    marks: [...prompt.matchAll(/MARK:([a-z0-9-]+)/g)].map((match) => match[1]),
    taskNotification: prompt.includes("<task-notification>"),
    slash: prompt.trimStart().startsWith("/") ? prompt.trimStart().split(/\s/)[0] : false,
  },
  customInstructions: typeof payload.custom_instructions === "string" ? payload.custom_instructions.length : undefined,
  compactSummary: typeof payload.compact_summary === "string" ? payload.compact_summary.length : undefined,
  // The background tasks a stop reports, by identity and status only.
  backgroundTasks: Array.isArray(payload.background_tasks) ? payload.background_tasks.map((task) => ({ keys: Object.keys(task ?? {}),
    ...Object.fromEntries(["id", "task_id", "agent_id", "type", "status", "kind"].filter((key) => key in (task ?? {})).map((key) => [key, task[key]])) })) : undefined,
  publisher: published === null ? null
    : published.status === 0 && !published.signal && !published.stdout && !published.stderr ? { status: 0 }
      : { status: published.status, signal: published.signal, stdout: published.stdout?.slice(0, 2000), stderr: published.stderr?.slice(-2000) },
  store: observeOnly ? undefined : store(),
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
if (published?.stdout) process.stdout.write(published.stdout);
process.exitCode = published === null ? 0 : published.status ?? 1;
