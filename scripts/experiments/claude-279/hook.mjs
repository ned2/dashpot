// Metadata-only hook publisher for the Claude Code 279 experiment.
// Reads the hook payload from stdin and posts every key it carries, the values
// of its identity and location fields, the CLAUDE_* environment, and this
// process's ancestry to the runner's sink.
import { readFileSync } from "node:fs";
import { ancestry } from "./ancestry.mjs";

// Prompts, transcripts, and tool responses stay out of the trace. The fixture
// model's own tool inputs are kept where they name a location: the Bash
// command, and the worktree tools' path.
const retained = ["session_id", "hook_event_name", "cwd", "source", "reason", "agent_id", "agent_type", "prompt_id",
  "tool_name", "tool_use_id", "permission_mode", "stop_hook_active", "model", "old_cwd", "new_cwd",
  "transcript_path", "agent_transcript_path", "worktree_path", "worktree_name"];
let payload = {};
try { payload = JSON.parse(readFileSync(0, "utf8") || "{}"); } catch (error) { payload = { parseError: String(error) }; }
const input = payload.tool_input ?? {};
const record = {
  kind: "hook",
  event: payload.hook_event_name,
  payload: Object.fromEntries(retained.filter((key) => key in payload).map((key) => [key, payload[key]])),
  payloadKeys: Object.keys(payload),
  toolInput: payload.tool_input === undefined ? undefined : {
    keys: Object.keys(input),
    command: typeof input.command === "string" ? input.command.slice(0, 300) : undefined,
    path: input.path, isolation: input.isolation, subagentType: input.subagent_type, action: input.action,
  },
  env: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CLAUDE") && key !== "CLAUDE_CODE_MESSAGING_TOKEN")),
  cwd: process.cwd(),
  pid: process.pid,
  ancestry: ancestry(process.ppid),
};
try {
  await fetch(process.env.SPIKE_SINK + "/hook", { method: "POST", body: JSON.stringify(record), signal: AbortSignal.timeout(3000) });
} catch (error) {
  process.stderr.write(`hook publish failed: ${error}\n`);
}
