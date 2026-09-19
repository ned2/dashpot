// Independent verifier for a Claude Code 148 experiment trace.
// Checks the recorded channel, hook, shell and listing evidence against the
// relocation claims without importing the runner, the channel server, or the
// publisher.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const tracePath = process.argv[2];
assert(tracePath, "Pass the trace.jsonl path");
const expectedVersion = process.argv[3] ?? "2.1.278";
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const hooks = of("hook");
const commands = of("command").filter((record) => record.phase === "start");
const channels = of("channel");
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `${expectedVersion} (Claude Code)`);
assert(environment.channelArgs.includes("--dangerously-load-development-channels"), "sessions load the development channel");
const { fixture, other, third } = environment;
const scenarios = of("scenario").map((record) => record.name);
for (const name of ["channel-registration", "relocate-direct-launch", "relocate-direct-launch-to-linked", "relocate-entered-session", "busy-delivery", "background-job", "relocate-isolated-to-linked"]) {
  assert(scenarios.includes(name), `scenario ${name} ran`);
}

// Every hook and shell carries the session claim of the process that ran it.
for (const hook of hooks) {
  assert.equal(hook.env.CLAUDE_CODE_SESSION_ID, hook.payload.session_id, `hook ${hook.event} claim matches payload`);
  assert(hook.ancestry.some((entry) => entry.pid === Number(hook.env.CLAUDE_PID)), `hook ${hook.event} descends from CLAUDE_PID`);
}
for (const command of commands) {
  assert(command.ancestry.some((entry) => entry.pid === Number(command.env.CLAUDE_PID)), `command ${command.label} descends from CLAUDE_PID`);
}

// The channel server is a child of the session it serves, carries that
// session's identity in its environment, and completed the MCP handshake.
const identity = of("channel.identity")[0];
assert.equal(identity.channelPpid, identity.workerPid);
assert.equal(identity.channelEnv.CLAUDE_CODE_SESSION_ID, identity.session);
assert.equal(identity.initialize.clientInfo.version, expectedVersion);
assert(channels.some((record) => record.phase === "listening" && record.env.CLAUDE_CODE_SESSION_ID === identity.session), "channel listening for session A");

// Every relocation request reached the model as a channel-tagged turn that
// began with the requested worktree tool, and every one was acknowledged
// back through the channel's own tool.
const pushes = channels.filter((record) => record.phase === "pushed" && record.meta?.request === "relocate");
assert(pushes.length >= 6, `six relocation pushes, saw ${pushes.length}`);
const firstSteps = of("model.request").filter((record) => record.viaChannel && record.step === 0 && /^(relocate|relocate-direct|exit)$/.test(record.label));
assert(firstSteps.every((record) => /Worktree$/.test(record.tool)), "each channel relocation turn opens with a worktree tool");
const acks = channels.filter((record) => record.phase === "ack");
assert(acks.length >= pushes.length, `every push acknowledged: ${acks.length} of ${pushes.length}`);

// A session launched directly in a linked worktree cannot reach the main
// worktree: EnterWorktree refuses it and ExitWorktree has nothing to exit.
const direct = of("relocate.outcome")[0];
assert.equal(direct.listing.cwd, other);
assert.equal(direct.shellCwd, other);
assert.deepEqual(direct.worktreeOutcomes.map((outcome) => [outcome.tool, outcome.isError]), [["EnterWorktree", true], ["ExitWorktree", true]]);
assert.match(direct.worktreeOutcomes[0].text, /main working tree/);
assert.match(direct.worktreeOutcomes[1].text, /no active EnterWorktree session/);
// The same session can enter a sibling linked worktree and keeps its identity.
const linked = of("relocate-linked.outcome")[0];
assert.equal(linked.session, direct.session);
assert.equal(linked.listing.pid, direct.listing.pid);
assert.equal(linked.listing.cwd, third);
assert.equal(linked.shellCwd, third);
assert.deepEqual(linked.worktreeOutcomes.map((outcome) => [outcome.tool, outcome.isError]), [["EnterWorktree", null]]);
assert(linked.newHooks.some(([event, , tool, cwd]) => event === "PostToolUse" && tool === "EnterWorktree" && cwd === third), "PostToolUse reports the new cwd");

// A session that entered the linked worktree from the main worktree returns
// there on ExitWorktree, keeping its session id and pid.
const entered = of("enter.outcome")[0];
const exited = of("exit.outcome")[0];
assert.equal(entered.listing.cwd, other);
assert.equal(exited.session, entered.session);
assert.equal(exited.listing.pid, entered.listing.pid);
assert.equal(exited.listing.cwd, fixture);
assert.equal(exited.shellCwd, fixture);
assert(exited.newHooks.some(([event, , tool, cwd]) => event === "PostToolUse" && tool === "ExitWorktree" && cwd === fixture), "PostToolUse reports the original cwd");
assert(!hooks.some((record) => record.event === "SessionEnd" && record.payload.session_id === exited.session && record.receipt < exited.receipt), "no SessionEnd during relocation");

// A channel event pushed mid-turn is delivered after that turn, as the next
// turn, with no Stop hook between them.
const busy = of("busy.outcome")[0];
assert.equal(busy.deliveredAfterHold, true);
assert.equal(busy.stopsDuringBusy, 1);

// A background shell job does not block a relocation, and the listing shows
// the session busy while the job runs.
const background = of("background.outcome")[0];
assert.equal(background.backgroundJobEndedBeforeRelocation, false);
assert.equal(background.listing.cwd, other);
assert.equal(background.listing.status, "busy");

// A session isolated by EnterWorktree cannot enter a linked worktree outside
// `.claude/worktrees/`.
const isolated = of("relocate-isolated.outcome")[0];
assert.equal(isolated.listing.cwd, other);
assert.equal(isolated.shellCwd, other);
assert.deepEqual(isolated.worktreeOutcomes.map((outcome) => [outcome.tool, outcome.isError]), [["EnterWorktree", true]]);
assert.match(isolated.worktreeOutcomes[0].text, /\.claude\/worktrees does not exist/);

// Both sessions ended on /exit with the interactive exit reason.
const exit = of("channel.exit")[0];
assert.deepEqual(exit.sessionEnds.map(([, reason]) => reason).sort(), ["prompt_input_exit", "prompt_input_exit"]);

// The trace is ordered by receipt and free of prompt or transcript content.
records.forEach((record, index) => assert.equal(record.receipt, index + 1));
// The publisher lists payload key names; none of them carries a value.
const text = readFileSync(tracePath, "utf8");
for (const key of ["transcript_path", "prompt", "tool_input", "tool_response"]) assert(!text.includes(`"${key}":`), `${key} value absent`);
console.log(`Verified ${records.length} records: ${scenarios.length} scenarios, ${hooks.length} hooks, ${commands.length} shells, ${channels.length} channel events.`);
