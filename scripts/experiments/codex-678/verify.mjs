// Independent verifier for a Codex 678 launch qualification trace. Checks
// the leads' checks, the workers' cycles, the turn contexts Codex recorded,
// the hooks' Host Process and the `codex sandbox` probes against the claims
// the spike makes for the pinned release, without importing the runner or
// Dashpot. With `--codex-source`, it also checks each Codex source fact the
// spike cites against a `rust-v0.166.0` checkout.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict] [--codex-source <checkout>]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const strict = argv.includes("--strict");
const sourceAt = argv.indexOf("--codex-source");
const codexSource = sourceAt >= 0 ? argv[sourceAt + 1] : null;
assert(sourceAt < 0 || (codexSource && !codexSource.startsWith("--")), "--codex-source needs a checkout path");
// The positional arguments: every one that is neither a flag nor the
// checkout `--codex-source` names.
const positionals = argv.filter((argument, index) => !argument.startsWith("--") && !(sourceAt >= 0 && index === sourceAt + 1));
const unknown = argv.filter((argument) => argument.startsWith("--") && !["--strict", "--codex-source"].includes(argument));
assert.deepEqual(unknown, [], "Unknown option: pass --strict, or --codex-source <checkout> as two arguments");
assert(argv.filter((argument) => argument === "--codex-source").length <= 1, "Pass --codex-source once");
assert(positionals.length <= 2, "Pass at most the trace path and the expected version");
const [tracePath, expectedVersion = "0.166.0"] = positionals;
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

// The trace names the exact sources that produced it.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["ancestry.mjs", "checks.mjs", "cycle.mjs", "hook.mjs", "probe.mjs", "run.mjs"];
const modules = ["harnesses.py", "hook_publish.py", "hook_records.py", "processes.py"].map((file) => `src/dashpot/sessions/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.match(environment.binaryTarget, new RegExp(`/${expectedVersion.replaceAll(".", "\\.")}-x86_64-unknown-linux-musl/bin/codex$`));
assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
assert.deepEqual(environment.selected, ["all"]);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", "seed-a", "seed-b", "control", "pfresh", "presume", "ppin", "nogit",
  "approve", "psandbox", "sandbox-probes", "base-profile-probes", "base", "bmeasured", "bpfresh", "bpextends", "bpresume"]);

const hooks = of("hook");
const requests = of("model.request");
const launch = (name) => one("launch", (record) => record.name === name);
const leadChecks = (name) => one("checks", (record) => record.report.label === launch(name).label).report;
const cycle = (worker) => one("cycle", (record) => record.report.label === worker).report;
const probeOf = (name) => one("sandbox.probe", (record) => record.name === name);
const windowOf = (name) => [one("terminal.start", (record) => record.name === name).receiptTime, launch(name).receiptTime];
const threads = one("rollouts").threads;
const threadOf = (id) => { const found = threads.filter((thread) => thread.id === id); assert.equal(found.length, 1, `one rollout for ${id}`); return found[0]; };
// The turns Codex recorded while a launch ran, its lead's or a worker's.
const turnsIn = (name, id) => {
  const [start, end] = windowOf(name);
  return threadOf(id).turns.filter((turn) => Date.parse(turn.timestamp) >= start && Date.parse(turn.timestamp) <= end);
};
const leadTurn = (name) => { const turns = turnsIn(name, launch(name).thread); assert.equal(turns.length, 1, `${name}: one lead turn`); return turns[0]; };
const workerThreads = (name) => threads.filter((thread) => thread.source?.subagent?.thread_spawn?.parent_thread_id === launch(name).thread
  && thread.turns.some((turn) => { const [start, end] = windowOf(name); return Date.parse(turn.timestamp) >= start && Date.parse(turn.timestamp) <= end; }));
const workerTurn = (name) => { const found = workerThreads(name); assert.equal(found.length, 1, `${name}: one worker`); return found[0].turns[0]; };
const root = "$ROOT";
const worktreeRoot = `${root}/repository.worktrees`;
const gitDir = `${root}/repository/.git`;
const uvCache = `${worktreeRoot}/.cache/uv`;
const preCommitCache = `${worktreeRoot}/.cache/pre-commit`;
const caches = { UV_CACHE_DIR: uvCache, PRE_COMMIT_HOME: preCommitCache };
const outcomes = (report) => Object.fromEntries(Object.entries(report.results).map(([key, value]) => [key, value.ok]));
const writable = (probe) => probe.testW;
const pass = (name, worktrees) => {
  const report = leadChecks(name);
  assert.deepEqual(outcomes(report), { worktreeRoot: true, gitDir: true, network: true, caches: true, outside: false,
    ...Object.fromEntries(worktrees.map((worktree) => [`worktreeAdd:${worktree}`, true])) }, `${name}: the four checks pass and the control write is refused`);
  assert.deepEqual(writable(report.probe), { worktreeRoot: true, gitDir: true, uvCache: true, preCommitCache: true, outside: false }, `${name}: test -w`);
  assert.equal(report.probe.network.ok, true);
  assert.deepEqual([report.probe.env.UV_CACHE_DIR, report.probe.env.PRE_COMMIT_HOME], [uvCache, preCommitCache], `${name}: the lead's shell has both variables`);
  return report;
};
const fullCycle = (name, worker) => {
  const report = cycle(worker);
  for (const [step, outcome] of Object.entries(report.steps)) assert.equal(outcome.ok, true, `${worker}: ${step}`);
  assert.equal(report.cwd, `${worktreeRoot}/${worker}`);
  assert.deepEqual({ UV_CACHE_DIR: report.inherited.UV_CACHE_DIR, PRE_COMMIT_HOME: report.inherited.PRE_COMMIT_HOME }, caches, `${worker}: the worker's shell`);
  assert.deepEqual(report.steps.commit.hookEnv, caches, `${worker}: the commit's hook`);
  assert.equal(report.inherited.terminal, name, `${worker}: the launching terminal's environment reached the worker`);
};
const named = (turn) => turn.active_permission_profile?.id ?? null;
const legacy = (turn, roots, network) => {
  assert.equal(named(turn), null, "no named permissions profile");
  assert.equal(turn.sandbox_policy.type, "workspace-write");
  assert.deepEqual(turn.sandbox_policy.writable_roots ?? [], roots);
  assert.equal(turn.sandbox_policy.network_access, network);
};

check("Every hook reached Dashpot's real publisher, which exited 0 and recorded each outcome as succeeded; the fixture model answered every request with an offered tool; every control write outside the grants was refused; no fixture process outlived the run, and the fixture daemon left no socket in the shared daemon directory", () => {
  assert(hooks.length > 0);
  for (const record of hooks) assert.equal(record.publisher.status, 0, `${record.event} publisher status`);
  const events = one("dashpot.events").outcomes;
  assert(events.length > 0 && events.every((event) => event.result === "succeeded"));
  assert.equal(of("server.error").length, 0);
  assert.equal(of("failure").length, 0);
  assert(requests.every((record) => !record.missing), "every planned tool was offered");
  assert.equal(of("cleanup.kill").length, 0);
  assert.deepEqual(one("outside").entries, []);
  one("completed");
  const shared = one("shared-daemon-dir");
  assert.deepEqual([shared.ownLeft, shared.ownAfter], [[], []]);
});

check("A plain launch, `codex -C <checkout>` on a trusted project, runs on the managed daemon under the built-in `:workspace` profile: no Worktree Root, no Git directory, no network, no cache variables; its commands and hooks carry the environment of the terminal that started the daemon, and its SessionEnd comes from the daemon when it unloads the thread, after the client has exited", () => {
  for (const name of ["seed-a", "seed-b"]) {
    const report = leadChecks(name);
    assert.deepEqual(outcomes(report), { worktreeRoot: false, gitDir: false, network: false, caches: false, outside: false });
    const turn = leadTurn(name);
    assert.equal(named(turn), ":workspace");
    assert.equal(turn.permission_profile.network, "restricted");
    assert.equal(report.probe.env.terminal, "seed-a", `${name}: the daemon's environment`);
    // Later scenarios resume these threads in their own clients, so only
    // the daemon-hosted hooks belong to the plain launch.
    const own = hooks.filter((record) => record.payload.session_id === launch(name).thread && /app-server-daemon\//.test(record.ancestry[0].cmdline));
    assert.deepEqual(own.map((record) => record.event), ["SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"], `${name}: hooks`);
    for (const record of own) assert.equal(record.terminal, "seed-a", `${name}: ${record.event} ran with the daemon's environment`);
    const live = launch(name).dashpot.find((record) => record.sessionId === launch(name).thread);
    assert.match(live.process.arguments, / app-server --listen unix:\/\/ .*--managed-daemon/);
    const end = hooks.find((record) => record.event === "SessionEnd" && record.payload.session_id === launch(name).thread);
    assert.match(end.ancestry[0].cmdline, /app-server-daemon\/releases\/.*--managed-daemon/);
    assert(end.receipt > one("terminal.exit", (record) => record.name === name).receipt);
  }
});

const optioned = ["control", "pfresh", "presume", "ppin", "nogit", "approve", "psandbox", "bmeasured", "bpfresh", "bpextends", "bpresume"];
check("Every launch that passes `--profile` or a `-c` override runs in its own TUI client, the Host Process: Dashpot's record names that client, each of its hooks runs under it with its terminal's environment, and its SessionEnd comes from it as it exits", () => {
  for (const name of optioned) {
    const thread = launch(name).thread;
    const live = launch(name).dashpot.find((record) => record.sessionId === thread);
    assert.match(live.process.arguments, /^codex (resume |-C )/, `${name}: Dashpot's record`);
    const [start, end] = windowOf(name);
    const own = hooks.filter((record) => record.payload.session_id === thread && record.receiptTime >= start && record.receiptTime <= end + 1)
      .filter((record) => !(record.event === "SessionEnd" && record.terminal !== name));
    assert(own.length >= 3, `${name}: hooks`);
    for (const record of own) {
      assert.equal(record.terminal, name, `${name}: ${record.event} environment`);
      assert.match(record.ancestry[0].cmdline, /^codex (resume |-C )/, `${name}: ${record.event} host`);
    }
    const ended = own.filter((record) => record.event === "SessionEnd");
    assert.equal(ended.length, 1, `${name}: one SessionEnd`);
    assert(ended[0].receipt < one("terminal.exit", (record) => record.name === name).receipt);
  }
});

check("The measured resume command passes on 0.166.0: the lead's four checks pass and its control write is refused, a fresh v2 worker completes its whole cycle with both cache variables in its shell and its commit hook, and Codex records a legacy `workspace-write` turn with the two writable roots, the network on, and no named permissions profile; the resumed client first finds the thread open in another app, as the first resume of B does, while no later resume of a thread last hosted by a client does", () => {
  pass("control", ["w-control"]);
  fullCycle("control", "w-control");
  legacy(leadTurn("control"), [worktreeRoot, gitDir], true);
  legacy(workerTurn("control"), [worktreeRoot, gitDir], true);
  assert(one("lead.started", (record) => record.name === "control").conflicts >= 1);
  assert(one("lead.started", (record) => record.name === "presume").conflicts >= 1);
  for (const name of ["ppin", "approve", "psandbox", "bmeasured", "bpresume"]) assert.equal(one("lead.started", (record) => record.name === name).conflicts, 0, name);
});

check("A fresh `codex -C <checkout> --profile dashpot-arc` passes: its lead and its worker run under the named `dashpot-arc` profile with the network enabled, the four checks pass, the control write is refused, and the worker's cycle passes with both variables in its shell and its hook", () => {
  pass("pfresh", ["w-pfresh"]);
  fullCycle("pfresh", "w-pfresh");
  for (const turn of [leadTurn("pfresh"), workerTurn("pfresh")]) {
    assert.equal(named(turn), "dashpot-arc");
    assert.equal(turn.permission_profile.network, "enabled");
  }
});

check("`codex resume <id> --profile dashpot-arc` of a thread saved under `:workspace` keeps `:workspace`: the Worktree Root, the Git directory and the network are refused, `git worktree add` fails, and no worker cycle runs, while the profile file's cache variables still reach the lead's shell", () => {
  const report = leadChecks("presume");
  assert.deepEqual(outcomes(report), { worktreeRoot: false, gitDir: false, network: false, caches: true, outside: false, "worktreeAdd:w-presume": false });
  assert.deepEqual(writable(report.probe), { worktreeRoot: false, gitDir: false, uvCache: false, preCommitCache: false, outside: false });
  assert.equal(named(threadOf(launch("presume").thread).turns.filter((turn) => Date.parse(turn.timestamp) < windowOf("presume")[0]).at(-1)), ":workspace");
  assert.equal(named(leadTurn("presume")), ":workspace");
  assert.equal(of("cycle").filter((record) => record.report.label === "w-presume").length, 0);
});

check("The same resume with `-c default_permissions=\"dashpot-arc\"` passes: the override replaces the saved profile, the lead and worker run under `dashpot-arc`, and the worker's cycle passes", () => {
  pass("ppin", ["w-ppin"]);
  fullCycle("ppin", "w-ppin");
  assert.equal(named(leadTurn("ppin")), "dashpot-arc");
  assert.equal(named(workerTurn("ppin")), "dashpot-arc");
});

check("A profile that grants the Worktree Root but names no rule for the Git directory leaves that directory read-only, though it lies inside the checkout, a workspace root: the Git directory check and its `test -w` fail and `git worktree add` is refused, while the Worktree Root and the network pass", () => {
  const report = leadChecks("nogit");
  assert.deepEqual(outcomes(report), { worktreeRoot: true, gitDir: false, network: true, caches: true, outside: false, "worktreeAdd:w-nogit": false });
  assert.equal(writable(report.probe).gitDir, false);
  assert.equal(named(leadTurn("nogit")), "dashpot-arc-nogit");
});

check("`--approve-for-me` or `--sandbox workspace-write` beside `--profile dashpot-arc` replaces the profile's permissions with a legacy `workspace-write` sandbox that has no extra writable root and no network, so the Worktree Root, the Git directory and the network checks fail; the profile file's cache variables still reach the shell. `--approve-for-me` sets the automatic reviewer and `on-request`, and the resumed thread keeps both in its later resumes", () => {
  for (const name of ["approve", "psandbox"]) {
    const report = leadChecks(name);
    assert.deepEqual(outcomes(report), { worktreeRoot: false, gitDir: false, network: false, caches: true, outside: false });
    legacy(leadTurn(name), [], false);
  }
  const before = threadOf(launch("approve").thread).turns.filter((turn) => Date.parse(turn.timestamp) < windowOf("approve")[0]).at(-1);
  assert.deepEqual([before.approvals_reviewer, before.approval_policy], ["user", "never"]);
  for (const name of ["approve", "psandbox", "bmeasured", "bpresume"]) {
    assert.deepEqual([leadTurn(name).approvals_reviewer, leadTurn(name).approval_policy], ["auto_review", "on-request"], `${name}: reviewer`);
  }
});

const sandboxed = (name, expected) => {
  const record = probeOf(name);
  assert.equal(record.status, 0, `${name}: exit`);
  assert.deepEqual(writable(record.probe), expected.testW, `${name}: test -w`);
  assert.equal(record.probe.network.ok, expected.network, `${name}: network`);
  assert.equal(record.probe.deniedRead.ok, expected.deniedRead, `${name}: denied read`);
  assert.deepEqual([record.probe.env.UV_CACHE_DIR, record.probe.env.PRE_COMMIT_HOME], expected.caches ? [uvCache, preCommitCache] : [null, null], `${name}: variables`);
  // `codex sandbox` replaces its helper-binary directory under
  // `$CODEX_HOME/tmp/arg0-linux/` and writes nothing else there.
  const changes = [...record.codexHomeChanges.added, ...record.codexHomeChanges.removed, ...record.codexHomeChanges.changed];
  assert(changes.every((file) => file.startsWith("tmp/arg0-linux/")), `${name}: CODEX_HOME writes ${changes}`);
};
const granted = { worktreeRoot: true, gitDir: true, uvCache: true, preCommitCache: true, outside: false };
const nothing = { worktreeRoot: false, gitDir: false, uvCache: false, preCommitCache: false, outside: false };
check("`codex sandbox` probes, run with no session or daemon, report what a fresh launch with the same options measured in-session: `--profile dashpot-arc`, with or without `-P dashpot-arc -C <checkout>`, and the legacy `-c` equivalent of the resume command grant the Worktree Root, the Git directory, both caches and the network and set both variables; the profile without a Git directory rule leaves it read-only; with no option it falls back to read-only, and `-P :workspace` grants nothing outside the checkout; it writes under `$CODEX_HOME` only its helper binaries", () => {
  for (const name of ["sandbox-arc-file", "sandbox-arc", "sandbox-legacy"]) sandboxed(name, { testW: granted, network: true, deniedRead: true, caches: true });
  sandboxed("sandbox-arc-nogit", { testW: { ...granted, gitDir: false }, network: true, deniedRead: true, caches: true });
  for (const name of ["sandbox-default", "sandbox-workspace"]) sandboxed(name, { testW: nothing, network: false, deniedRead: true, caches: false });
  // The same grants as the in-session probes of the matching launches.
  assert.deepEqual(writable(probeOf("sandbox-arc").probe), writable(leadChecks("pfresh").probe));
  assert.deepEqual(writable(probeOf("sandbox-legacy").probe), writable(leadChecks("control").probe));
  assert.deepEqual(writable(probeOf("sandbox-arc-nogit").probe), writable(leadChecks("nogit").probe));
});

check("With a base `default_permissions` profile that denies one file and turns the network on, a plain launch and `codex sandbox` with no option or with `-P base` apply it: the denied read fails with EACCES, the network passes, and nothing outside the checkout is writable", () => {
  const report = leadChecks("base");
  assert.deepEqual(outcomes(report), { worktreeRoot: false, gitDir: false, network: true, caches: false, outside: false });
  assert.deepEqual(report.probe.deniedRead, { ok: false, code: "EACCES" });
  assert.equal(named(leadTurn("base")), "base");
  for (const name of ["base-sandbox-default", "base-sandbox-base"]) {
    sandboxed(name, { testW: nothing, network: true, deniedRead: false, caches: false });
    assert.equal(probeOf(name).probe.deniedRead.code, "EACCES");
  }
});

check("Over that base profile, the measured resume command still passes with a full worker cycle, but its legacy sandbox replaces the base profile, deny rule included: the denied file reads; `codex sandbox` with the legacy `-c` options shows the same", () => {
  const report = pass("bmeasured", ["w-bmeasured"]);
  fullCycle("bmeasured", "w-bmeasured");
  legacy(leadTurn("bmeasured"), [worktreeRoot, gitDir], true);
  assert.equal(report.probe.deniedRead.ok, true);
  sandboxed("base-sandbox-legacy", { testW: granted, network: true, deniedRead: true, caches: true });
});

check("Over that base profile, a fresh `--profile dashpot-arc` passes with a full worker cycle under `dashpot-arc`, whose own rules replace the base profile's, deny rule included; `codex sandbox --profile dashpot-arc -P dashpot-arc` shows the same; a resume with `--profile` of a thread whose last turn ran without a named profile also takes `dashpot-arc`, and reads the denied file", () => {
  const report = pass("bpfresh", ["w-bpfresh"]);
  fullCycle("bpfresh", "w-bpfresh");
  assert.equal(named(leadTurn("bpfresh")), "dashpot-arc");
  assert.equal(report.probe.deniedRead.ok, true);
  sandboxed("base-sandbox-arc", { testW: granted, network: true, deniedRead: true, caches: true });
  pass("bpresume", []);
  const before = threadOf(launch("bpresume").thread).turns.filter((turn) => Date.parse(turn.timestamp) < windowOf("bpresume")[0]).at(-1);
  assert.equal(named(before), null);
  assert.equal(named(leadTurn("bpresume")), "dashpot-arc");
  assert.equal(leadChecks("bpresume").probe.deniedRead.ok, true);
});

check("A profile file whose permissions profile extends the base configuration's own, adding the Worktree Root and the Git directory, keeps the base profile's deny rule and network: a fresh launch passes the four checks with a full worker cycle while the denied read still fails with EACCES, and `codex sandbox` with the same profile shows the same", () => {
  const report = pass("bpextends", ["w-bpextends"]);
  fullCycle("bpextends", "w-bpextends");
  assert.deepEqual(report.probe.deniedRead, { ok: false, code: "EACCES" });
  assert.equal(named(leadTurn("bpextends")), "dashpot-arc-extends");
  assert.equal(named(workerTurn("bpextends")), "dashpot-arc-extends");
  assert.equal(leadTurn("bpextends").permission_profile.network, "enabled");
  sandboxed("base-sandbox-extends", { testW: granted, network: true, deniedRead: false, caches: true });
});

check("Every passing worker pushed its branch to the loopback remote and appended to its Arc Ledger file", () => {
  const workers = ["w-bmeasured", "w-bpextends", "w-bpfresh", "w-control", "w-pfresh", "w-ppin"];
  assert.deepEqual(one("remote.refs").refs.sort(), ["refs/heads/main", ...workers.map((worker) => `refs/heads/${worker}`)].sort());
  assert.deepEqual(one("ledger").files.sort(), workers);
});

check("Where the sandbox restricts the network, a Node child of Node exits 0 but prints nothing; where the network is on, it prints", () => {
  const probes = [...of("checks").map((record) => record.report.probe), ...of("sandbox.probe").map((record) => record.probe)];
  for (const probe of probes) assert.equal(probe.nestedNode.printed, probe.env.networkDisabled !== "1", probe.label);
  assert(probes.some((probe) => !probe.nestedNode.printed) && probes.some((probe) => probe.nestedNode.printed));
});

// Each source fact the spike cites, as `file:lines` and text that range
// holds at rust-v0.166.0.
const sourceFacts = [
  ["tui/src/daemon_startup.rs", 78, 79, ["cli.config_profile_v2.is_some()", "Some(\"--profile\")"]],
  ["tui/src/daemon_startup.rs", 97, 118, ["\"suppress_unstable_features_warning\"", "command-line configuration overrides"]],
  ["cli/src/lib.rs", 125, 131, ["requires = \"permissions_profile\""]],
  ["cli/src/debug_sandbox.rs", 693, 731, ["uses_legacy_sandbox_mode_override", "SandboxMode::ReadOnly"]],
  ["cli/src/debug_sandbox.rs", 762, 768, ["get(\"default_permissions\")"]],
  ["cli/src/main.rs", 1973, 1998, ["Subcommand::Resume(_)", "Subcommand::Sandbox(_)"]],
  ["config/src/loader/mod.rs", 292, 294, ["profile config as a second user layer"]],
  ["config/src/loader/mod.rs", 316, 325, ["legacy_profile_is_selected || legacy_profile_table_exists", "cannot be used while"]],
  ["config/src/permissions_toml.rs", 78, 78, ["UnsupportedBuiltInParent"]],
  ["core/src/config/mod.rs", 2690, 2692, ["sandbox_mode_override.is_some()", "PermissionConfigSyntax::Legacy"]],
  ["core/src/config/mod.rs", 3527, 3532, ["`sandbox_mode` and `default_permissions` overrides cannot both be set"]],
  ["core/src/config/mod.rs", 3668, 3676, ["persisted_permission_profile_id"]],
  ["core/src/config/mod.rs", 5110, 5115, ["default_permissions_override.or(valid_persisted_profile_id)"]],
  ["app-server/src/request_processors/thread_processor.rs", 313, 345, ["contains_key(\"default_permissions\")", "persisted_permission_profile_id"]],
  ["utils/cli/src/shared_options.rs", 43, 50, ["long = \"approve-for-me\"", "conflicts_with_all = [\"sandbox_mode\""]],
  ["utils/cli/src/shared_options.rs", 80, 93, ["sandbox_mode=\"workspace-write\"", "approvals_reviewer=\"auto_review\""]],
  ["protocol/src/permissions.rs", 860, 871, ["append_default_read_only_project_root_subpath_if_no_explicit_rule(&mut entries, \".git\")", "default_read_only_subpaths_for_writable_root"]],
];
if (codexSource) {
  const tag = execFileSync("git", ["-C", codexSource, "describe", "--tags", "--exact-match"], { encoding: "utf8" }).trim();
  check(`Each cited Codex source range holds its text at ${tag}`, () => {
    assert.equal(tag, `rust-v${expectedVersion}`);
    const commits = { "0.166.0": "6ff1e1ca3b30fc8b914720681fcf5fe62e95f856" };
    assert.equal(execFileSync("git", ["-C", codexSource, "rev-parse", "HEAD"], { encoding: "utf8" }).trim(), commits[expectedVersion], "the tag's commit");
    for (const [file, first, last, needles] of sourceFacts) {
      const text = readFileSync(path.join(codexSource, "codex-rs", file), "utf8").split("\n").slice(first - 1, last).join("\n");
      for (const needle of needles) assert(text.includes(needle), `${file}:${first}-${last} holds ${needle}`);
    }
  });
}

console.log(`Verified ${checks.length} claims for codex-cli ${expectedVersion}:`);
for (const claim of checks) console.log(`- ${claim}`);
if (drifted.length) console.log(`Note: Dashpot modules changed since the run: ${drifted.join(", ")}`);
if (!codexSource) console.log("Codex source facts not checked: pass --codex-source <rust-v0.166.0 checkout>.");
