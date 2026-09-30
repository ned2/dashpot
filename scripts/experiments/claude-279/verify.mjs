// Independent verifier for a Claude Code 279 experiment trace.
// Checks the recorded hook and shell evidence against the claims for 2.1.285
// without importing the runner or publisher: what SubagentStart and
// SubagentStop carry, what their `cwd` means, and that a sub-agent's change of
// directory reaches no hook.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "2.1.285";
assert.equal(expectedVersion, "2.1.285", "claims are recorded for 2.1.285 only");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `${expectedVersion} (Claude Code)`);
assert(!records.some((record) => record.kind === "server.error"), "the fixture servers raised no error");

const within = (name) => {
  const start = records.findIndex((record) => record.kind === "scenario" && record.name === name);
  assert(start !== -1, `scenario ${name} ran`);
  const next = records.findIndex((record, index) => index > start && record.kind === "scenario");
  return records.slice(start + 1, next === -1 ? undefined : next);
};
const hooks = (from, event) => from.filter((record) => record.kind === "hook" && (!event || record.event === event));
const command = (from, label) => {
  const found = from.filter((record) => record.kind === "command" && record.phase === "start" && record.label === label);
  assert.equal(found.length, 1, `one ${label} command`);
  return found[0];
};
const ROOT = "$ROOT/repository";
const NESTED = `${ROOT}/nested`;
const SIBLING = "$ROOT/repository.worktrees/sibling";
const START_KEYS = ["session_id", "transcript_path", "cwd", "prompt_id", "agent_id", "agent_type", "hook_event_name"];
const STOP_KEYS = ["session_id", "transcript_path", "cwd", "prompt_id", "permission_mode", "agent_id", "agent_type", "effort",
  "hook_event_name", "stop_hook_active", "agent_transcript_path", "last_assistant_message", "background_tasks", "session_crons"];

// One sub-agent per scenario: its Start and Stop carry the listed keys, the
// parent's session, one agent id, and the same `cwd`; every hook the
// sub-agent's tool calls fire carries that id and that `cwd` too.
const subagent = (name, expectedCwd) => {
  const scope = within(name);
  const [start] = hooks(scope, "SubagentStart");
  const stops = hooks(scope, "SubagentStop");
  assert.equal(hooks(scope, "SubagentStart").length, 1, `${name}: one SubagentStart`);
  assert.equal(stops.length, 1, `${name}: one SubagentStop`);
  const [stop] = stops;
  assert.deepEqual([...start.payloadKeys].sort(), [...START_KEYS].sort(), `${name}: SubagentStart keys`);
  assert.deepEqual([...stop.payloadKeys].sort(), [...STOP_KEYS].sort(), `${name}: SubagentStop keys`);
  const session = hooks(scope, "SessionStart")[0].payload.session_id;
  const agent = start.payload.agent_id;
  assert(agent, `${name}: the sub-agent has an id`);
  for (const hook of [start, stop]) {
    assert.equal(hook.payload.session_id, session, `${name}: ${hook.event} carries the parent's session`);
    assert.equal(hook.payload.agent_id, agent, `${name}: ${hook.event} names the sub-agent`);
    assert.equal(hook.payload.cwd, expectedCwd, `${name}: ${hook.event} cwd`);
  }
  const tools = hooks(scope).filter((hook) => hook.payload.agent_id === agent && /ToolUse$/.test(hook.event));
  assert(tools.length >= 2, `${name}: the sub-agent's tool hooks carry its id`);
  for (const hook of tools) assert.equal(hook.payload.cwd, expectedCwd, `${name}: sub-agent ${hook.event} cwd`);
  assert(!hooks(scope, "CwdChanged").some((hook) => hook.payload.agent_id), `${name}: no CwdChanged names a sub-agent`);
  return { scope, agent, tools };
};

// The parent at its launch directory: the sub-agent's `cd X && cmd` runs in X,
// but every hook of its keeps the parent's cwd, and the next call is back.
for (const [name, prefix] of [["parent-root", "child"], ["parent-bg", "child-bg"]]) {
  const { scope } = subagent(name, ROOT);
  assert.equal(command(scope, `${prefix}-start`).cwd, ROOT);
  assert.equal(command(scope, `${prefix}-after-cd`).cwd, SIBLING, `${name}: the command after cd ran in the sibling`);
  assert.equal(command(scope, `${prefix}-next`).cwd, ROOT, `${name}: the next command is back at the parent's cwd`);
  assert(!hooks(scope, "CwdChanged").length, `${name}: no CwdChanged`);
}
// A standalone `cd` in a sub-agent neither persists nor fires CwdChanged.
{
  const { scope } = subagent("parent-child-cd-alone", ROOT);
  assert.equal(command(scope, "child-after-cd-nested").cwd, ROOT);
  assert.equal(command(scope, "child-after-cd-sibling").cwd, ROOT);
  assert(!hooks(scope, "CwdChanged").length, "no CwdChanged for a sub-agent's cd");
}
// The parent's own persisting `cd` moves the cwd the sub-agent inherits.
{
  const { scope } = subagent("parent-cd-nested", NESTED);
  const [changed] = hooks(scope, "CwdChanged");
  assert.equal(changed.payload.old_cwd, ROOT);
  assert.equal(changed.payload.new_cwd, NESTED);
  assert.equal(command(scope, "child").cwd, NESTED);
}
// A `cd` outside the project is reset: CwdChanged names the target, but the
// hook cwd, the sub-agent's cwd, and its shell stay at the launch directory.
{
  const { scope } = subagent("parent-cd-sibling", ROOT);
  const changed = hooks(scope, "CwdChanged");
  assert.equal(changed.length, 1, "one CwdChanged, none for the reset");
  assert.equal(changed[0].payload.new_cwd, SIBLING);
  assert.equal(changed[0].payload.cwd, ROOT);
  assert.equal(command(scope, "parent-sibling").cwd, ROOT);
  assert.equal(command(scope, "child").cwd, ROOT);
}
// EnterWorktree moves the parent, and the sub-agent spawned after it.
{
  const { scope } = subagent("parent-enter", SIBLING);
  assert.equal(command(scope, "child").cwd, SIBLING);
}
// A sub-agent isolated by the Agent tool has a cwd of its own.
{
  const { scope, agent } = subagent("parent-isolated", `${ROOT}/.claude/worktrees/agent-${agentOf("parent-isolated")}`);
  assert.equal(command(scope, "child").cwd, `${ROOT}/.claude/worktrees/agent-${agent}`);
}
function agentOf(name) {
  return hooks(within(name), "SubagentStart")[0].payload.agent_id;
}
console.log(`Verified ${records.length} records against the ${expectedVersion} claims.`);
