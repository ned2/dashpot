// Independent verifier for the Issue #162 acceptance trace: checks each claim
// docs/agent-sessions.md and the harness reference make about Claude Code
// clients and supervised workers through Dashpot's shared runtime model
// against the recorded hook, shell, listing and observation evidence.
//
// Usage: node verify.mjs <trace.jsonl> [<idle trace.jsonl>]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const load = (file) => readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };
const main = "$ROOT/repository";
const sibling = "$ROOT/repository.worktrees/sibling";
const nested = "$ROOT/repository/nested";
const managed = "$ROOT/repository/.claude/worktrees/managed";
// The pinned release, which the trace's environment and its replacement
// worker's command line both name.
const pinned = "2.1.287";

const evidence = (records) => {
  const hooks = records.filter((record) => record.kind === "hook");
  const observation = (label) => {
    const found = records.find((record) => record.kind === "observation" && record.label === label);
    assert(found, `observation ${label}`);
    assert.equal(found.error, null, `${label}: ${found.error}`);
    return found;
  };
  const runs = (label) => observation(label).runs.filter((run) => run.issueId)
    .map((run) => [run.issueId, run.observationTarget, run.orphaned]).sort();
  return { hooks, observation, runs };
};

const verifyEnvironment = (records, label) => {
  const environment = records.find((record) => record.kind === "environment");
  check(`${label}: pinned Claude Code release`, () => assert.equal(environment.version, `${pinned} (Claude Code)`));
  check(`${label}: subscribed as \`dashpot integrate claude-code\` subscribes`, () => assert.deepEqual(environment.subscriptions, {
    events: ["SessionStart", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "SessionEnd"],
    matched: [["PostToolUse", "EnterWorktree"], ["PostToolUse", "ExitWorktree"]],
  }));
  check(`${label}: every hook reached the real publisher, which succeeded`, () => {
    const hooks = records.filter((record) => record.kind === "hook");
    assert(hooks.length > 0);
    for (const hook of hooks) assert.equal(hook.publisher.status, 0, `${hook.event}: ${hook.publisher.stderr}`);
  });
  check(`${label}: no fixture process outlived the run`, () => {
    assert.deepEqual(records.find((record) => record.kind === "cleanup.remaining").pids, []);
  });
};

const verifyAcceptance = (records) => {
  verifyEnvironment(records, "acceptance");
  const { hooks, observation, runs } = evidence(records);
  const elsewhere = (label) => observation(label).diagnostics.filter((item) => item.code === "work-session-elsewhere");
  const shell = (label) => records.find((record) => record.kind === "command" && record.label === label && record.phase === "end");
  const turnHooks = (label) => {
    const turn = records.find((record) => record.kind === "turn" && record.label === label);
    const previous = records.filter((record) => record.kind === "turn" && record.receipt < turn.receipt).at(-1);
    return hooks.filter((record) => record.payload.session_id === turn.session && record.receipt < turn.receipt && record.receipt > (previous?.receipt ?? 0));
  };

  // A headless client: an unbound move carries nothing, a bound session's
  // run follows EnterWorktree and ExitWorktree(keep), and SessionEnd ends it.
  check("an unbound client's worktree tools carry nothing", () => {
    const moved = turnHooks("unbound-move").filter((record) => record.event === "PostToolUse");
    assert.deepEqual(moved.map((record) => [record.payload.tool_name, record.payload.cwd]), [["EnterWorktree", sibling], ["ExitWorktree", main]]);
    assert.deepEqual(runs("c1-unbound-moved"), []);
  });
  check("`work start` binds the client where it is", () => {
    assert.equal(shell("c1-start").dashpot.status, 0);
    assert.deepEqual(runs("c1-bound"), [["I_fixture_1", main, false]]);
  });
  check("EnterWorktree carries the client's run to the Worktree it enters", () => {
    assert.deepEqual(runs("c1-entered-sibling"), [["I_fixture_1", sibling, false]]);
    assert.deepEqual(elsewhere("c1-entered-sibling"), []);
    assert.equal(shell("c1-show-sibling").cwd, sibling);
    assert.match(shell("c1-show-sibling").dashpot.stdout, /issue-1 \(I_fixture_1\)/);
  });
  check("ExitWorktree(keep) carries it back", () => {
    assert.deepEqual(runs("c1-returned"), [["I_fixture_1", main, false]]);
    assert.match(shell("c1-show-returned").dashpot.stdout, /issue-1 \(I_fixture_1\)/);
  });
  check("a background sub-agent holds the session running after its parent's Stop", () => {
    assert.deepEqual(observation("c1-parent-settled-child-working").runs.map((run) => [run.issueId, run.state]), [["I_fixture_1", "running"]]);
    assert.deepEqual(observation("c1-child-finished").runs.map((run) => [run.issueId, run.state]), [["I_fixture_1", "waiting"]]);
  });
  check("a client's SessionEnd ends the run and removes every record of the session", () => {
    const end = hooks.filter((record) => record.event === "SessionEnd" && record.receipt < observation("c1-ended").receipt).at(-1);
    assert.equal(end.payload.cwd, main);
    assert.deepEqual(observation("c1-ended").runs, []);
    for (const files of Object.values(observation("c1-ended").stateFiles)) assert.deepEqual(files.filter((file) => file !== ".gitignore"), []);
  });

  // A persistent shell `cd` places the session but never carries its run.
  check("a persistent shell `cd` into a nested Worktree places the session there", () => {
    const stop = turnHooks("bind-2-cd").find((record) => record.event === "Stop");
    assert.equal(stop.payload.cwd, nested);
    assert.equal(shell("c2-show-nested").cwd, nested);
  });
  check("the run stays where `work start` put it, and observation says so", () => {
    assert.deepEqual(runs("c2-shell-in-nested"), [["I_fixture_2", main, false]]);
    const [diagnostic] = elsewhere("c2-shell-in-nested");
    assert(diagnostic.message.includes(nested) && diagnostic.message.includes("dashpot work sta"), diagnostic.message);
  });
  check("`work start` where the session now is switches the run there", () => {
    assert.match(shell("c2-start-nested").dashpot.stdout, /^switched from issue-2 at \$ROOT\/repository to issue-2 at \$ROOT\/repository\/nested/);
    assert.deepEqual(runs("c2-rebound-in-nested"), [["I_fixture_2", nested, false]]);
    assert.deepEqual(elsewhere("c2-rebound-in-nested"), []);
  });
  check("EnterWorktree refuses the Worktree a persistent `cd` already reached, so the run stays behind", () => {
    assert.deepEqual(runs("c4-shell-in-nested").filter(([issue]) => issue === "I_fixture_7"), [["I_fixture_7", main, false]]);
    const outcomes = records.filter((record) => record.kind === "model.request" && record.label === "enter-nested").at(-1).worktreeOutcomes;
    assert.deepEqual(outcomes.map((outcome) => [outcome.tool, outcome.isError]), [["EnterWorktree", true]]);
    assert.match(outcomes[0].text, /Cannot enter worktree: .* is the current working directory/);
    assert.deepEqual(turnHooks("enter-nested").filter((record) => record.event === "PostToolUse"), []);
    assert.deepEqual(runs("c4-entered-nested").filter(([issue]) => issue === "I_fixture_7"), [["I_fixture_7", main, false]]);
    assert(elsewhere("c4-entered-nested").some((item) => item.message.includes("issue-7")));
  });
  check("a client killed without SessionEnd leaves an Orphaned Agent Run", () => {
    assert.deepEqual(runs("c2-killed"), [["I_fixture_2", nested, true]]);
  });

  // ExitWorktree(remove).
  check("ExitWorktree(remove) deletes a Worktree EnterWorktree created, with the run in it", () => {
    const moved = turnHooks("managed-remove").filter((record) => record.event === "PostToolUse");
    assert.deepEqual(moved.map((record) => [record.payload.tool_name, record.toolInput.action ?? null, record.payload.cwd]),
      [["EnterWorktree", null, managed], ["ExitWorktree", "remove", main]]);
    assert.match(shell("c3-show-managed").dashpot.stdout, /issue-3 \(I_fixture_3\)/);
    assert.match(shell("c3-show-removed").dashpot.stdout, /^no active Issue work/);
    assert.deepEqual(observation("c3-removed").runs.filter((run) => run.issueId === "I_fixture_3"), []);
    assert.deepEqual(observation("c3-removed").stateFiles[managed], []);
  });
  check("ExitWorktree(remove) refuses a Worktree entered by path and publishes no PostToolUse", () => {
    const outcomes = records.filter((record) => record.kind === "model.request" && record.label === "path-remove").at(-1).worktreeOutcomes;
    assert.deepEqual(outcomes.map((outcome) => [outcome.tool, outcome.isError]), [["EnterWorktree", null], ["ExitWorktree", true], ["ExitWorktree", null]]);
    assert.match(outcomes[1].text, /not the owner of the worktree/);
    const moved = turnHooks("path-remove").filter((record) => record.event === "PostToolUse");
    assert.deepEqual(moved.map((record) => record.toolInput.action ?? "enter"), ["enter", "keep"]);
    assert.equal(records.find((record) => record.kind === "disposable").exists, true);
  });

  // Supervised workers.
  const worker = (name) => records.find((record) => record.kind === "worker" && record.name === name);
  const w1 = worker("fixture-w1");
  const w2 = worker("fixture-w2");
  check("two workers under one supervisor hold their own runs, one carried by EnterWorktree", () => {
    assert.notEqual(w1.pid, w2.pid);
    assert.deepEqual(runs("two-workers-bound").filter(([issue]) => issue !== "I_fixture_2"), [["I_fixture_1", sibling, false], ["I_fixture_4", main, false]]);
    const bound = observation("two-workers-bound").runs.filter((run) => run.issueId === "I_fixture_4" || run.issueId === "I_fixture_1");
    assert.deepEqual(bound.map((run) => run.processOrSession).sort(), [`claude-code pid ${w1.pid}`, `claude-code pid ${w2.pid}`].sort());
  });
  const replacementStart = hooks.find((record) => record.event === "SessionStart" && record.payload.session_id === w1.sessionId && record.payload.source === "resume");
  check("a SIGKILLed worker is replaced in a new process whose SessionStart reports the launch directory", () => {
    assert.notEqual(Number(replacementStart.env.CLAUDE_PID), w1.pid);
    assert.equal(replacementStart.payload.cwd, main);
    const probe = records.find((record) => record.kind === "replacement" && record.label === "started");
    assert.equal(probe.cwd, sibling);
    assert(probe.cmdline.includes(`/claude/versions/${pinned} --resume `), probe.cmdline);
  });
  check("until its next turn the run is orphaned and the other worker's is untouched", () => {
    assert.deepEqual(runs("w1-replaced").filter(([issue]) => issue !== "I_fixture_2"), [["I_fixture_1", sibling, true], ["I_fixture_4", main, false]]);
  });
  check("the replacement's next turn continues the run where its predecessor left it", () => {
    const prompt = hooks.find((record) => record.event === "UserPromptSubmit" && record.payload.session_id === w1.sessionId && record.receipt > replacementStart.receipt);
    assert.equal(prompt.payload.cwd, sibling);
    assert.match(prompt.publisher.stdout, /still holds Issue work on issue-1/);
    assert.deepEqual(runs("w1-replaced-turn").filter(([issue]) => issue === "I_fixture_1"), [["I_fixture_1", sibling, false]]);
    assert.equal(observation("w1-replaced-turn").runs.find((run) => run.issueId === "I_fixture_1").processOrSession, `claude-code pid ${replacementStart.env.CLAUDE_PID}`);
  });
  check("replacing the supervisor leaves both workers and their runs as they were", () => {
    const before = runs("w1-replaced-turn");
    assert.deepEqual(runs("supervisor-stopped"), before);
    assert.deepEqual(runs("supervisor-replaced"), before);
    const scenario = records.find((record) => record.kind === "scenario" && record.name === "supervisor-replacement").receipt;
    const next = records.find((record) => record.kind === "scenario" && record.name === "worker-stop-respawn").receipt;
    assert.deepEqual(hooks.filter((record) => record.receipt > scenario && record.receipt < next && [w1.sessionId, w2.sessionId].includes(record.payload.session_id)), []);
    const listed = records.find((record) => record.kind === "processes" && record.label === "supervisor-replaced").processes.map((entry) => entry.pid);
    assert(listed.includes(w2.pid) && listed.includes(Number(replacementStart.env.CLAUDE_PID)));
  });
  check("`claude stop` publishes SessionEnd and ends the worker's run; its respawn finds none", () => {
    const stop = records.find((record) => record.kind === "worker.stop" && record.worker === "w2");
    assert.deepEqual(stop.hooks, [["SessionEnd", true, "other"]]);
    assert.deepEqual(runs("w2-stopped").filter(([issue]) => issue === "I_fixture_4"), []);
    assert.deepEqual(runs("w2-respawned").filter(([issue]) => issue === "I_fixture_4"), []);
    assert(observation("w2-respawned").runs.some((run) => run.processOrSession === `${w2.sessionId} hook` && run.issueId === null));
  });
  check("a replacement stopped before any turn ends the orphaned run it holds", () => {
    assert.deepEqual(runs("w1-replaced-again").filter(([issue]) => issue === "I_fixture_1"), [["I_fixture_1", sibling, true]]);
    const stop = records.find((record) => record.kind === "worker.stop" && record.worker === "w1");
    assert.deepEqual(stop.hooks, [["SessionEnd", true, "other"]]);
    const end = hooks.filter((record) => record.event === "SessionEnd" && record.payload.session_id === w1.sessionId).at(-1);
    assert.equal(end.payload.cwd, sibling);
    assert.deepEqual(runs("w1-stopped").filter(([issue]) => issue === "I_fixture_1"), []);
  });
  const w5 = worker("fixture-w5");
  check("a worker killed while no supervisor runs is listed failed, publishes nothing, and leaves its run orphaned", () => {
    assert.deepEqual(records.find((record) => record.kind === "worker.unsupervised-kill").hooks, []);
    const listed = records.find((record) => record.kind === "agents" && record.label === "w5-killed").agents.find((entry) => entry.id === w5.id);
    assert.equal(listed.state, "failed");
    assert.equal(listed.pid, undefined);
    assert.deepEqual(runs("w5-killed").filter(([issue]) => issue === "I_fixture_6"), [["I_fixture_6", main, true]]);
  });
  check("`claude respawn` after that exit runs a claimed spare whose SessionStart continues the run", () => {
    const respawned = records.find((record) => record.kind === "respawned");
    assert.match(respawned.cmdline, /^claude bg-spare --bg-spare /);
    const start = hooks.find((record) => record.event === "SessionStart" && record.payload.session_id === w5.sessionId && record.payload.source === "resume");
    assert.equal(Number(start.env.CLAUDE_PID), respawned.pid);
    assert.equal(start.payload.cwd, main);
    assert.match(start.publisher.stdout, /still holds Issue work on issue-6/);
    for (const label of ["w5-respawned", "w5-respawned-turn"]) {
      const run = observation(label).runs.find((entry) => entry.issueId === "I_fixture_6");
      assert.deepEqual([run.orphaned, run.processOrSession, run.observationTarget], [false, `claude-code pid ${respawned.pid}`, main]);
    }
    const since = (label) => shell(label).dashpot.stdout.match(/issue-6 \(I_fixture_6\) since (\S+)/)[1];
    assert.equal(since("w5-show-respawned"), since("w5-show"));
  });
};

const verifyIdle = (records) => {
  verifyEnvironment(records, "idle");
  const { hooks, observation, runs } = evidence(records);
  const shell = (label) => records.find((record) => record.kind === "command" && record.label === label && record.phase === "end");
  const listed = (label) => records.find((record) => record.kind === "agents" && record.label === label).agents;
  const w4 = records.find((record) => record.kind === "worker" && record.name === "fixture-w4");
  const outcome = records.find((record) => record.kind === "idle.outcome");
  check("idle: the supervisor retired the bound worker about an hour after its last turn", () => {
    assert.equal(outcome.retired, true);
    const retired = records.find((record) => record.kind === "idle.poll" && !record.alive).receiptTime;
    const minutes = (retired - outcome.hooks.at(-1)[2]) / 60000;
    assert(minutes > 55 && minutes < 70, `retired after ${minutes} minutes`);
    assert.deepEqual(listed("w4-idle").map((agent) => [agent.id, agent.state, agent.pid]), [[w4.id, "done", undefined]]);
  });
  check("idle: retirement publishes no hook and leaves the run orphaned", () => {
    assert.deepEqual(outcome.hooks.map(([event]) => event), ["SessionStart", "UserPromptSubmit", "Stop"]);
    assert.deepEqual(runs("w4-idle"), [["I_fixture_5", main, true]]);
  });
  check("idle: attaching respawns the worker, whose SessionStart continues the run", () => {
    const [attached] = listed("w4-attached");
    assert.notEqual(attached.pid, w4.pid);
    const start = hooks.find((record) => record.event === "SessionStart" && record.payload.session_id === w4.sessionId && record.payload.source === "resume");
    assert.equal(Number(start.env.CLAUDE_PID), attached.pid);
    assert.equal(start.payload.cwd, main);
    assert.match(start.publisher.stdout, /still holds Issue work on issue-5/);
    const run = observation("w4-attached").runs.find((entry) => entry.issueId === "I_fixture_5");
    assert.deepEqual([run.orphaned, run.processOrSession, run.observationTarget], [false, `claude-code pid ${attached.pid}`, main]);
    const since = (label) => shell(label).dashpot.stdout.match(/issue-5 \(I_fixture_5\) since (\S+)/)[1];
    assert.equal(since("w4-show-after"), since("w4-show"));
  });
};

const [trace, idleTrace] = process.argv.slice(2);
assert(trace, "Pass the acceptance trace, and optionally the idle-eviction trace");
verifyAcceptance(load(trace));
if (idleTrace) verifyIdle(load(idleTrace));
for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified`);
