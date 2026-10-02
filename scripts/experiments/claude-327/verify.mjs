// Independent verifier for the Issue #327 worktree-tool trace: checks each
// claim the Issue-work skill, docs/agent-sessions.md and the harness
// reference make about when Claude Code's EnterWorktree accepts a Dashpot
// Issue Worktree against the recorded tool outcomes, hooks, shells and
// observations.
//
// Usage: node verify.mjs <trace.jsonl> [expected version]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const file = process.argv[2];
assert(file, "Pass the trace to verify");
const expectedVersion = process.argv[3] ?? "2.1.286";
const records = readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const first = "$ROOT/repository.worktrees/first";
const second = "$ROOT/repository.worktrees/second";
const launch = "$ROOT/repository.worktrees/launch";
const managed = "$ROOT/repository/.claude/worktrees/managed";

const hooks = records.filter((record) => record.kind === "hook");
const turn = (label) => {
  const found = records.find((record) => record.kind === "turn" && record.label === label);
  assert(found, `turn ${label}`);
  return found;
};
// The hooks the turn's session published during the turn.
const turnHooks = (label) => {
  const current = turn(label);
  const previous = records.filter((record) => (record.kind === "turn" || record.kind === "client.spawn") && record.receipt < current.receipt).at(-1);
  return hooks.filter((record) => record.payload.session_id === current.session && record.receipt < current.receipt && record.receipt > previous.receipt);
};
const moves = (label) => turnHooks(label).filter((record) => record.event === "PostToolUse").map((record) => [record.payload.tool_name, record.payload.cwd]);
// The worktree-tool and bare `cd` outcomes of a turn, from its final model request.
const outcomes = (label) => records.filter((record) => record.kind === "model.request" && record.label === label).at(-1).outcomes ?? [];
const accepted = (label, target) => {
  const [outcome] = outcomes(label).filter((item) => item.tool === "EnterWorktree").slice(-1);
  assert.equal(outcome.path, target);
  assert.equal(outcome.isError, null, outcome.text);
  assert(outcome.text.startsWith(`Entered worktree at ${target} `), outcome.text);
};
const refused = (label, target, pattern) => {
  const [outcome] = outcomes(label).filter((item) => item.tool === "EnterWorktree");
  assert.equal(outcome.path, target);
  assert.equal(outcome.isError, true);
  assert.match(outcome.text, pattern);
};
const returned = (label, place) => {
  const [outcome] = outcomes(label).filter((item) => item.tool === "ExitWorktree");
  assert.equal(outcome.isError, null, outcome.text);
  assert(outcome.text.endsWith(`Session is now back in ${place}.`), outcome.text);
};
const shell = (label) => {
  const found = records.find((record) => record.kind === "command" && record.label === label && record.phase === "end");
  assert(found, `shell ${label}`);
  return found;
};
const shows = (label, place, pattern) => {
  const found = shell(label);
  assert.equal(found.cwd, place);
  assert.equal(found.dashpot.status, 0, found.dashpot.stderr);
  assert.match(found.dashpot.stdout, pattern);
};
const runs = (label) => {
  const found = records.find((record) => record.kind === "observation" && record.label === label);
  assert(found, `observation ${label}`);
  assert.equal(found.error, null, `${label}: ${found.error}`);
  return found.runs.filter((run) => run.issueId).map((run) => [run.issueId, run.observationTarget, run.orphaned]);
};
const none = /^no active Issue work at this worktree/;
const literal = (text) => text.replace(/[$.()]/g, "\\$&");
const notManaged = (target) => new RegExp(`^Cannot enter worktree: ${literal(`${main}/.claude/worktrees`)} does not exist, so ${literal(target)} cannot be a worktree managed by Claude Code\\.$`);
const notUnder = (target) => new RegExp(`^${literal(`Cannot enter worktree: ${target} is not under ${main}/.claude/worktrees. Switching from this session is limited to worktrees managed by Claude Code (created under .claude/worktrees/ of this repository).`)}$`);

// The run.
const environment = records.find((record) => record.kind === "environment");
check(`Claude Code ${expectedVersion}`, () => assert.equal(environment.version, `${expectedVersion} (Claude Code)`));
check("subscribed as `dashpot integrate claude-code` subscribes", () => assert.deepEqual(environment.subscriptions, {
  events: ["SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"],
  matched: [["PostToolUse", "EnterWorktree"], ["PostToolUse", "ExitWorktree"]],
}));
check("every hook reached the real publisher, which succeeded", () => {
  assert(hooks.length > 0);
  for (const hook of hooks) assert.equal(hook.publisher.status, 0, `${hook.event}: ${hook.publisher.stderr}`);
});
check("no fixture process outlived the run", () => assert.deepEqual(records.find((record) => record.kind === "cleanup.remaining").pids, []));
check("the tool's own description limits a switch from a worktree to `.claude/worktrees/`", () => {
  const description = records.find((record) => record.kind === "tools").descriptions.EnterWorktree;
  assert.match(description, /On first entry from the launch directory, the path must appear in `git worktree list`/);
  assert.match(description, /Switching with `path` also works when the session is already in a worktree .* the target must be a worktree under `\.claude\/worktrees\/` of the same repository/s);
});

// Scenario A: from the main checkout, with no `.claude/worktrees/`.
check("from the main checkout, EnterWorktree enters an Issue Worktree by path", () => {
  accepted("a-enter-first", first);
  assert.deepEqual(moves("a-enter-first"), [["EnterWorktree", first]]);
  shows("a-show-entered-first", first, none);
  shows("a-show-bound-1", first, /issue-1 \(I_fixture_1\)/);
  assert.deepEqual(runs("a-enter-first"), [["I_fixture_1", first, false]]);
});
check("from an entered Issue Worktree, a direct EnterWorktree to another is refused and moves nothing", () => {
  refused("a-direct-second", second, notManaged(second));
  assert.deepEqual(moves("a-direct-second"), []);
  shows("a-show-after-direct", first, /issue-1 \(I_fixture_1\)/);
  assert.deepEqual(runs("a-direct-second"), [["I_fixture_1", first, false]]);
});
check("after `work stop`, ExitWorktree(keep) returns the session to the main checkout, carrying nothing", () => {
  assert.equal(shell("a-stop-1").dashpot.status, 0);
  returned("a-finish-1", main);
  assert.deepEqual(moves("a-finish-1"), [["ExitWorktree", main]]);
  shows("a-show-returned-1", main, none);
  assert.deepEqual(runs("a-finish-1"), []);
});
check("the session then enters the next Issue Worktree, where `work start` binds it", () => {
  accepted("a-enter-second", second);
  assert.deepEqual(moves("a-enter-second"), [["EnterWorktree", second]]);
  shows("a-show-entered-second", second, none);
  shows("a-show-bound-2", second, /issue-2 \(I_fixture_2\)/);
  assert.deepEqual(runs("a-enter-second"), [["I_fixture_2", second, false]]);
});
check("it can leave that one and enter the first Issue Worktree again", () => {
  returned("a-finish-2", main);
  assert.deepEqual(moves("a-finish-2"), [["ExitWorktree", main]]);
  assert.deepEqual(runs("a-finish-2"), []);
  accepted("a-reenter-first", first);
  assert.deepEqual(moves("a-reenter-first"), [["EnterWorktree", first]]);
  shows("a-show-reentered", first, none);
  assert.deepEqual(runs("a-reenter-first"), [["I_fixture_1", first, false]]);
});
check("ExitWorktree(keep) of a bound session carries its run back", () => {
  returned("a-leave-bound", main);
  shows("a-show-left-bound", main, /issue-1 \(I_fixture_1\)/);
});

// Scenario C: launched in a linked Worktree, with no `.claude/worktrees/`.
check("a session launched in a linked Worktree enters a sibling, carrying its run", () => {
  assert.deepEqual(runs("c-bind"), [["I_fixture_3", launch, false]]);
  accepted("c-enter-sibling", first);
  assert.deepEqual(moves("c-enter-sibling"), [["EnterWorktree", first]]);
  assert.deepEqual(runs("c-enter-sibling"), [["I_fixture_3", first, false]]);
});
check("it cannot enter the main checkout", () => {
  refused("c-enter-main", main, /^Cannot enter worktree: \$ROOT\/repository is the main working tree, not a linked worktree\.$/);
  assert.deepEqual(moves("c-enter-main"), []);
});
check("its ExitWorktree(keep) returns it to the Worktree it was launched in", () => {
  returned("c-exit", launch);
  assert.deepEqual(moves("c-exit"), [["ExitWorktree", launch]]);
  assert.deepEqual(runs("c-exit"), [["I_fixture_3", launch, false]]);
});
check("a shell `cd` to the main checkout is reset", () => {
  const [outcome] = outcomes("c-cd-main");
  assert.equal(outcome.tool, "Bash");
  assert.equal(outcome.text, `Shell cwd was reset to ${launch}`);
  assert.equal(shell("c-after-cd").cwd, launch);
});
check("from there it enters the other sibling", () => {
  accepted("c-enter-second", second);
  assert.deepEqual(runs("c-enter-second"), [["I_fixture_3", second, false]]);
});

// With `.claude/worktrees/` present.
check("with `.claude/worktrees/` present, a session launched in a linked Worktree still enters a sibling", () => {
  assert(records.some((record) => record.kind === "managed-directory"));
  accepted("d-enter-sibling", first);
  assert.deepEqual(runs("d-enter-sibling"), [["I_fixture_4", first, false]]);
});
check("from there it enters a Worktree under `.claude/worktrees/` directly", () => {
  accepted("d-enter-managed", managed);
  assert.deepEqual(runs("d-enter-managed"), [["I_fixture_4", managed, false]]);
});
check("from an entered Issue Worktree, a direct switch is refused with the Issue's wording", () => {
  accepted("b-enter-first", first);
  refused("b-direct-second", second, notUnder(second));
  assert.deepEqual(moves("b-direct-second"), []);
  assert.deepEqual(runs("b-direct-second"), [["I_fixture_5", first, false]]);
});
check("while a direct switch to a Worktree under `.claude/worktrees/` is accepted", () => {
  accepted("b-direct-managed", managed);
  assert.deepEqual(runs("b-direct-managed"), [["I_fixture_5", managed, false]]);
});
check("ExitWorktree(keep) then EnterWorktree reaches the Issue Worktree, carrying the run", () => {
  returned("b-exit-reenter", main);
  accepted("b-exit-reenter", second);
  assert.deepEqual(moves("b-exit-reenter"), [["ExitWorktree", main], ["EnterWorktree", second]]);
  shows("b-show-returned", main, /issue-5 \(I_fixture_5\)/);
  assert.deepEqual(runs("b-exit-reenter"), [["I_fixture_5", second, false]]);
});

// Scenario E: resumed inside the Worktree it had entered.
check("a session resumed in the Worktree it entered keeps its id and its worktree session", () => {
  const resumed = records.find((record) => record.kind === "client.spawn" && record.name === "e-resumed");
  assert.equal(resumed.cwd, first);
  assert.equal(turn("e-direct-second").session, resumed.resume);
  const start = turnHooks("e-direct-second").find((record) => record.event === "SessionStart");
  assert.deepEqual([start.payload.source, start.payload.cwd], ["resume", first]);
  refused("e-direct-second", second, notUnder(second));
  assert.deepEqual(moves("e-direct-second"), []);
});
check("its shell `cd` to the main checkout is reset to the Worktree", () => {
  const [outcome] = outcomes("e-cd-main");
  assert.equal(outcome.text, `Shell cwd was reset to ${first}`);
});
check("its ExitWorktree(keep) returns it to the directory it entered from, and EnterWorktree then succeeds", () => {
  returned("e-exit", main);
  assert.deepEqual(moves("e-exit"), [["ExitWorktree", main]]);
  accepted("e-enter-second", second);
  assert.deepEqual(moves("e-enter-second"), [["EnterWorktree", second]]);
});

check("ExitWorktree(keep) removed no Worktree", () => {
  assert.deepEqual(records.find((record) => record.kind === "worktrees").paths.sort(), [main, first, launch, second, managed].sort());
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified against ${file}`);
