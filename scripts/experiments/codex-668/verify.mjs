// Independent verifier for the Codex 668 managed-worktree trace. Checks the
// recorded model requests, tool replies, Git state, attachment reads and
// Dashpot's own preparation and Cleanup checks against the claims the spike
// makes for the pinned release, without importing the runner or Dashpot.
//
//   node verify.mjs <trace.jsonl> [expected version] [--strict]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const strict = process.argv.includes("--strict");
const [tracePath, expectedVersion = "0.166.0"] = process.argv.slice(2).filter((argument) => argument !== "--strict");
assert(tracePath, "Pass the trace.jsonl path");
const records = readFileSync(tracePath, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const of = (kind) => records.filter((record) => record.kind === kind);
const one = (kind, predicate = () => true) => {
  const found = of(kind).filter(predicate);
  assert.equal(found.length, 1, `exactly one ${kind} record`);
  return found[0];
};
const hooks = of("hook");
const requests = of("model.request");
const FIXTURE = "$ROOT/repository";
const POOL = "$ROOT/codex-home/worktrees";
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

// The trace names the exact sources that produced it.
const environment = records[0];
assert.equal(environment.kind, "environment");
assert.equal(environment.version, `codex-cli ${expectedVersion}`);
const scripts = ["run.mjs", "hook.mjs", "probe.mjs", "ancestry.mjs", "uds-websocket.mjs"];
const modules = ["sessions/hook_publish.py", "sessions/hook_records.py", "repository/worktrees/create.py", "repository/cleanup/obstacles.py"]
  .map((file) => `src/dashpot/${file}`);
assert.deepEqual(Object.keys(environment.sourceSHA256).sort(), [...scripts, ...modules].sort());
assert.deepEqual(one("sources.after").sourceSHA256, environment.sourceSHA256, "no source changed during the run");
const digestOf = (file) => existsSync(file) ? createHash("sha256").update(readFileSync(file)).digest("hex") : null;
// The runner's scripts change only with a new trace, so they must match.
for (const file of scripts) assert.equal(digestOf(path.join(here, file)), environment.sourceSHA256[file], `${file} matches the hash the run recorded`);
// Dashpot's modules keep changing after the trace is retained; a difference
// is reported, and fails only under --strict.
const checkout = path.resolve(here, "..", "..", "..");
const drifted = modules.filter((file) => digestOf(path.join(checkout, file)) !== environment.sourceSHA256[file]);
assert(!(strict && drifted.length), `Dashpot modules differ from the run's: ${drifted.join(", ")}`);
assert.match(environment.binaryTarget, new RegExp(`/${expectedVersion.replaceAll(".", "\\.")}-x86_64-unknown-linux-musl/bin/codex$`));
assert.match(environment.binarySHA256, /^[0-9a-f]{64}$/);
const SCENARIOS = ["standalone", "restart", "untrusted", "exec", "exec-worktree", "app-server-client", "daemon", "dashpot"];
assert.deepEqual(environment.scenarios, SCENARIOS);
assert.deepEqual(of("scenario").map((record) => record.name), ["hook-trust", ...SCENARIOS]);
const refs = environment.refs;
assert.equal(new Set([refs.originMain, refs.localMain, refs.feature]).size, 3, "the three bases are distinct commits");

// Requests by label, on the turn's own thread rather than an auxiliary one.
const turn = (label, thread) => requests.filter((record) => record.label === label && (!thread || record.thread === thread));
const replies = (label, thread) => turn(label, thread).map((record) => record.latest).filter((latest) => latest?.kind === "reply");
const searched = (label) => turn(label).map((record) => record.latest).find((latest) => latest?.kind === "search")?.tools ?? null;
const probeOf = (label) => turn(label).map((record) => record.latest).find((latest) => latest?.kind === "probe")?.probe ?? null;
const writes = (probe) => Object.fromEntries(probe.writes.map(([target, result]) => [target, result.ok ? "ok" : result.code]));
const listed = (label, thread) => replies(label, thread).filter((latest) => latest.name === "list_worktrees").map((latest) => latest.reply);
const managed = (root) => assert.match(root, new RegExp(`^\\${POOL}/[0-9a-f]{4}/repository$`), `${root} is a managed checkout in Codex's pool`);
const TOOLS = ["create_worktree", "list_worktrees", "get_worktree_creation_status"];
const offered = (namespace) => TOOLS.map((name) => ({ namespace, name, deferLoading: true }));
const PENDING = "Creation is running. Poll status; do not repeat creation. Work on independent tasks while waiting.";
const CREATED = "Keep the task cwd. Use the returned workspaceRoot explicitly and request filesystem permissions if needed.";
const FAILED = "Checkout retained; registration failed. Do not create a duplicate. Inspect the worktree browser to recover.";
const UNKNOWN = "Unknown operation. Inspect this task's worktree attachments before creating another checkout.";

check("Every scenario finished, every wait but the untrusted folder's consent was met, every hook reached Dashpot's real publisher and exited 0, no fixture process outlived the run, and the fixture left no entry in the shared daemon directory", () => {
  assert(of("scenario.end").every((record) => record.ok));
  assert.deepEqual(of("wait").filter((record) => !record.met).map((record) => record.label).filter((label) => label !== "ut-avail first request"), []);
  assert(hooks.length > 0);
  for (const record of hooks) assert.equal(record.publisher.status, 0, `${record.event} publisher status`);
  assert(one("hooks.list").after[0].every(([, trust]) => trust === "trusted"));
  assert.deepEqual(one("cleanup.remaining").pids, []);
  // The attribution is sound: the daemon's own entry was there while it ran.
  assert.equal(one("daemon.socket").fixtureEntryPresent, true);
  const shared = one("shared-daemon-dir");
  assert.equal(shared.fixtureEntriesBefore, 0);
  assert.equal(shared.fixtureEntriesAfter, 0);
});

const sa = one("sa.avail");
const DIRECT = ["apply_patch", "create_goal", "exec_command", "get_goal", "list_mcp_resource_templates", "list_mcp_resources", "read_mcp_resource",
  "request_user_input", "tool_search", "update_goal", "view_image", "web_search", "write_stdin"];
check("A standalone terminal (embedded app-server) offers no worktree tool directly: the thirteen direct tools are unchanged, and the three managed-worktree tools are deferred behind tool_search in the codex_worktrees namespace", () => {
  const first = turn("sa-avail", sa.session).find((record) => record.tools);
  assert.deepEqual(first.tools, DIRECT);
  assert.deepEqual(first.toolSearchSources, ["Multi-agent tools", "codex_worktrees"]);
  assert.deepEqual(searched("sa-avail"), offered("mcp__codex_worktrees"));
});

check("An explicitly untrusted folder, `codex exec`, and a thread an app-server client starts offer no managed-worktree tool: the search finds none and codex_worktrees is not a search source", () => {
  for (const label of ["ut-avail", "ex-avail", "as-avail"]) {
    const root = turn(label).find((record) => record.tools?.includes("tool_search"));
    assert(root, `${label} root request`);
    assert(!root.toolSearchSources.some((source) => /worktree|codex_tui/.test(source)), `${label} sources`);
    assert(!root.tools.some((tool) => TOOLS.includes(tool.split("/").at(-1))), `${label} direct tools`);
    assert.deepEqual(searched(label), [], `${label} search`);
  }
  const untrusted = one("ut.avail");
  assert.equal(untrusted.consentHeld, true, "the saved untrusted folder held the session at folder consent");
  assert.equal(one("ex.avail").status, 0);
  assert.equal(one("as.avail").startError, null);
});

check("A terminal attached to the managed daemon offers the same three deferred tools in the codex_tui namespace", () => {
  assert.deepEqual(searched("dm-avail"), offered("mcp__codex_tui"));
});

const create = one("sa.create");
const createReplies = replies("sa-create", create.session);
const operation = createReplies[0].reply.operationId;
const first = createReplies.find((latest) => latest.reply.type === "created").reply.worktree;
check("Creation is asynchronous: create_worktree answers pending with an operation id at once, a duplicate request while it is pending gets the same id without a new operation, and status polls stay pending until the result is `created`", () => {
  assert.equal(createReplies[0].name, "create_worktree");
  assert.deepEqual(createReplies[0].reply, { type: "pending", operationId: operation, message: PENDING });
  assert.equal(createReplies[1].name, "create_worktree");
  assert.deepEqual(createReplies[1].reply, { type: "pending", operationId: operation });
  const statuses = createReplies.filter((latest) => latest.name === "get_worktree_creation_status").map((latest) => latest.reply);
  assert(statuses.length >= 2);
  assert(statuses.slice(0, -1).every((reply) => reply.type === "pending" && reply.operationId === operation && !reply.message));
  assert.deepEqual(statuses.at(-1), { type: "created", worktree: first, message: CREATED });
  assert.deepEqual(create.created, [first.root], "one checkout for two create requests");
});

check("While creation was held after `git worktree add`, the checkout was already registered in Git, detached at origin/main, with no owner record yet", () => {
  assert.deepEqual(create.held.pool, [first.root]);
  const entry = create.held.inventory.find((found) => found.path === first.root);
  assert.deepEqual(entry, { path: first.root, head: refs.originMain, branch: null, detached: true });
  assert.equal(create.held.ownerWhileHeld[0].exists, false);
});

check("The default base is origin's remote HEAD, not the source checkout's HEAD or its uncommitted work: a detached, clean checkout in Codex's pool at origin/main, with no ignored or untracked file and no uncommitted change copied, and no Git hook run", () => {
  managed(first.root);
  assert.equal(first.workspaceRoot, `${first.root}/`);
  assert.equal(first.sourceCwd, FIXTURE);
  const found = create.checkout;
  assert.equal(found.head, refs.originMain);
  assert.equal(found.symbolicRef.status, 1, "detached HEAD");
  assert.equal(found.clean, true);
  assert.equal(found.tracked, "committed");
  assert.equal(found.ignoredCopied, false);
  assert.equal(found.untrackedCopied, false);
  assert.equal(create.hookMarker, false, "the source's post-checkout hook did not run");
  const git = create.git.map((entry) => entry.args.join(" "));
  assert(git.includes("for-each-ref --format=%(refname) %(symref) refs/remotes refs/heads"));
  assert(git.includes("rev-parse --verify --end-of-options refs/remotes/origin/main^{commit}"));
  assert(git.includes(`worktree add --detach --no-checkout ${first.root} ${refs.originMain}`));
  assert(git.includes(`--work-tree=. reset --hard --no-recurse-submodules ${refs.originMain}`));
  assert(!git.some((args) => /^(branch|switch|checkout)\b|worktree add .*-b /.test(args)), "no Branch created");
});

check("The tool binds the creating thread in a private owner record in the source repository's Git admin directory and attaches the checkout to the thread, identified by its root path", () => {
  assert.equal(create.checkout.owner.exists, true);
  assert.match(create.checkout.owner.file, /^\$ROOT\/repository\/\.git\/worktrees\/[^/]+\/codex-thread\.json$/);
  assert.deepEqual(create.checkout.owner.record, { version: 1, ownerThreadId: create.session });
  const read = one("rs.read").attachments;
  const attachment = read.worktrees.find((entry) => entry.payload.root === first.root);
  assert.deepEqual(attachment, { type: "worktree", identityKey: first.root, payload: first });
});

check("The Codex thread keeps its cwd and sandbox: after creation the shell still runs in the source checkout, which it may write, while a write inside the new checkout is refused (EROFS) under workspace-write", () => {
  const probe = probeOf("sa-create");
  assert.equal(probe.cwd, FIXTURE);
  assert.equal(probe.thread, create.session);
  assert.deepEqual(writes(probe), { [`${FIXTURE}/.dashpot/state/probe-sa`]: "ok", [`${first.root}/probe-sa`]: "EROFS" });
  assert(create.hooks.every(([, session, cwd]) => session === create.session && cwd === FIXTURE), "every hook kept the source cwd");
});

const again = one("sa.again");
const second = replies("sa-again", again.session).find((latest) => latest.reply.type === "created").reply.worktree;
check("A later request with an explicit ref is a new operation and a new checkout, detached at that ref; list_worktrees returns one attachment per page and follows nextCursor", () => {
  const ids = replies("sa-again", again.session).filter((latest) => latest.reply.operationId).map((latest) => latest.reply.operationId);
  assert(ids.length && ids.every((id) => id === ids[0]) && ids[0] !== operation);
  assert.deepEqual(again.created, [second.root]);
  managed(second.root);
  assert.notEqual(path.dirname(second.root), path.dirname(first.root));
  assert.equal(again.checkout.head, refs.feature);
  assert.equal(again.checkout.symbolicRef.status, 1);
  const pages = listed("sa-again", again.session);
  assert(pages.length >= 2);
  assert(pages.every((page) => page.data.length <= 1));
  assert.equal(pages.at(-1).nextCursor, null);
  assert(pages.slice(0, -1).every((page) => typeof page.nextCursor === "string"));
  assert.deepEqual(pages.flatMap((page) => page.data.map((entry) => entry.root)).sort(), [first.root, second.root].sort());
});

const same = one("sa.same");
const third = replies("sa-same", same.session).find((latest) => latest.reply.type === "created").reply.worktree;
check("Nothing reuses a checkout: a request at the default base while an attached checkout at that base exists makes a third checkout, again at origin/main", () => {
  const ids = replies("sa-same", same.session).filter((latest) => latest.reply.operationId).map((latest) => latest.reply.operationId);
  assert(ids.length && ids.every((id) => id === ids[0]) && ids[0] !== operation);
  assert.deepEqual(same.created, [third.root]);
  managed(third.root);
  assert(![first.root, second.root].includes(third.root));
  assert.equal(same.checkout.head, refs.originMain);
  assert.equal(same.checkout.head, create.checkout.head, "the same base as the first checkout");
});

check("A ref that does not resolve fails the operation through status, before any checkout is allocated", () => {
  const missing = one("sa.missing");
  const status = replies("sa-missing", missing.session).at(-1);
  assert.equal(status.name, "get_worktree_creation_status");
  assert.match(status.reply.error, /Needed a single revision/);
  assert.deepEqual(missing.created, []);
  assert(!missing.git.some((entry) => entry.args[0] === "worktree"));
});

const interrupt = one("sa.interrupt");
const orphan = interrupt.created[0];
check("Killing the terminal's Codex process after `git worktree add` leaves an orphan: a registered, detached Git worktree in the pool with no files checked out, no owner record and no attachment", () => {
  assert.equal(one("sa.kill").comm, "codex");
  assert.equal(interrupt.created.length, 1);
  managed(orphan);
  assert.deepEqual(interrupt.inventory.find((entry) => entry.path === orphan), { path: orphan, head: refs.originMain, branch: null, detached: true });
  assert.deepEqual(interrupt.checkout.files, []);
  assert.equal(interrupt.checkout.clean, false);
  assert.equal(interrupt.checkout.owner.exists, false);
  assert.equal(interrupt.git.at(-1).args.slice(0, 2).join(" "), "worktree add");
  const read = one("rs.read");
  assert(!read.attachments.worktrees.some((entry) => entry.payload.root === orphan));
  assert.deepEqual(read.owners.orphan, []);
});

check("After the terminal is gone, an independent app-server reads the thread's three worktree attachments and their owner through the documented attachment methods", () => {
  const read = one("rs.read");
  assert.equal(read.session, sa.session);
  assert.equal(read.attachments.error, null);
  assert.equal(read.attachments.count, 3);
  assert.deepEqual(read.attachments.types, ["worktree"]);
  assert.deepEqual(read.attachments.worktrees.map((entry) => entry.payload.root).sort(), [first.root, second.root, third.root].sort());
  assert.deepEqual(read.owners.first, [{ threadId: sa.session, archived: false }]);
  assert.deepEqual(read.owners.second, [{ threadId: sa.session, archived: false }]);
});

check("Operation status does not survive the process: the resumed thread is told the interrupted operation is unknown, and list_worktrees returns the three attachments and not the orphan", () => {
  const resumed = one("rs.resume");
  assert.equal(resumed.resumedSession, sa.session);
  assert.deepEqual(resumed.starts, [[sa.session, "resume"]]);
  const status = replies("rs-resume", sa.session).find((latest) => latest.name === "get_worktree_creation_status");
  assert.deepEqual(status.reply, { error: UNKNOWN });
  assert.deepEqual(listed("rs-resume", sa.session).flatMap((page) => page.data.map((entry) => entry.root)).sort(), [first.root, second.root, third.root].sort());
});

check("`codex exec --worktree` starts the session inside a new pool checkout detached at the source's HEAD (local main, not origin/main), binds the owner record, and adds no attachment; its sandbox may write that checkout and not the source", () => {
  const run = one("cw.run");
  assert.equal(run.status, 0);
  assert.deepEqual(run.created, [run.cwd]);
  managed(run.cwd);
  assert.equal(run.checkout.head, refs.localMain);
  assert.equal(run.checkout.symbolicRef.status, 1);
  assert.deepEqual(run.checkout.owner.record, { version: 1, ownerThreadId: run.session });
  assert.equal(run.attachments.error, null);
  assert.equal(run.attachments.count, 0);
  assert.deepEqual(run.owners, []);
  const probe = probeOf("cw-run");
  assert.equal(probe.cwd, run.cwd);
  assert.deepEqual(writes(probe), { [`${FIXTURE}/.dashpot/state/probe-cw`]: "EROFS", [`${run.cwd}/probe-cw`]: "ok" });
});

const dm = one("dm.create");
const dmRoot = replies("dm-create", dm.session).find((latest) => latest.reply.type === "created").reply.worktree.root;
check("When attachment fails, the result is `registrationFailed`: the checkout is retained and owner-bound but unattached, and the attachment owner query returns no thread for it. Once the controller removed its 99 fillers, the thread's one worktree attachment survived the daemon's replacement by a restart", () => {
  const fill = one("dm.fill");
  assert.equal(fill.existing, 1);
  assert.equal(fill.added, 99);
  assert.equal(fill.overflow, "thread attachment identity count exceeds 100");
  const full = one("dm.full");
  const result = replies("dm-full", full.session).find((latest) => latest.reply.type && latest.reply.type !== "pending").reply;
  assert.equal(result.type, "registrationFailed");
  assert.equal(result.message, FAILED);
  assert.deepEqual(full.created, [result.worktree.root]);
  assert.equal(full.checkout.clean, true);
  assert.deepEqual(full.checkout.owner.record, { version: 1, ownerThreadId: full.session });
  assert.equal(full.attachments.count, 100);
  assert(!full.attachments.worktrees.some((entry) => entry.payload.root === result.worktree.root));
  assert.deepEqual(full.owners.failed, []);
  const unfill = one("dm.unfill");
  assert.equal(unfill.removed, 99);
  assert.deepEqual(unfill.other, []);
  assert.deepEqual(unfill.left, ["worktree"]);
  assert.equal(one("daemon.restart").status, 0);
  const restart = one("dm.restart");
  assert(Number.isInteger(restart.daemonPidBefore) && Number.isInteger(restart.daemonPid));
  assert.notEqual(restart.daemonPid, restart.daemonPidBefore, "a new daemon process");
  assert.deepEqual(restart.attachments.worktrees.map((entry) => entry.payload.root), [dmRoot]);
  assert.deepEqual(restart.owners.created, [{ threadId: dm.session, archived: false }]);
  assert.deepEqual(restart.owners.failed, []);
});

check("Dashpot's own preparation differs: a named Branch at origin/main in the sibling Worktree root, the source's post-checkout hook run, and nothing ignored or untracked copied", () => {
  const compare = one("dashpot.compare");
  for (const plan of [compare.dryRun, compare.create]) {
    assert.equal(plan.branch, "fixture-1");
    assert.equal(plan.baseRef, "refs/remotes/origin/main");
    assert.equal(plan.baseCommit, refs.originMain);
    assert.equal(plan.path, "$ROOT/repository.worktrees/fixture-1");
    assert.deepEqual(plan.refusals, []);
  }
  assert.equal(compare.create.created, true);
  assert.deepEqual(compare.issueCheckout, { head: refs.originMain, branch: "refs/heads/fixture-1", ignoredCopied: false, untrackedCopied: false });
  assert.equal(compare.hookMarkerBefore, false);
  assert.equal(compare.hookMarker, true);
  assert(compare.createMs < 1000, "a synchronous creation in under a second");
});

check("Dashpot's Cleanup check sees nothing of Codex's ownership: `worktree check` reports an attached, owner-bound managed checkout and the exec --worktree checkout removable, and only the interrupted orphan is held, as dirty", () => {
  const { checks: found } = one("dashpot.compare");
  assert.deepEqual(found.managed, { status: 0, removable: true, kinds: [], details: [] });
  assert.deepEqual(found.execWorktree, { status: 0, removable: true, kinds: [], details: [] });
  assert.equal(found.orphan.removable, false);
  assert.deepEqual(found.orphan.kinds, ["dirty"]);
  assert.deepEqual(found.issue, { status: 0, removable: true, kinds: [], details: [] });
});

check("Dashpot's Cleanup preview offers the same managed checkout: `worktree remove --dry-run` plans its removal as an available target with no blocker, while Codex's attachment owner query still names the thread that holds it", () => {
  const cleanup = one("dashpot.cleanup");
  assert.equal(cleanup.target, first.root);
  assert.equal(cleanup.checkStatus, 0);
  assert(cleanup.checkLines.some((line) => /^Removable\s+yes$/.test(line)));
  assert(cleanup.checkLines.some((line) => /^Branch\s+\(detached\)$/.test(line)));
  assert.equal(cleanup.previewStatus, 0);
  const [target] = cleanup.preview.preview.targets;
  assert.equal(cleanup.preview.preview.targets.length, 1);
  assert.equal(target.path, first.root);
  assert.equal(target.available, true);
  assert.deepEqual(target.blockers, []);
  assert.deepEqual(cleanup.preview.planned, [`worktree:${first.root}`]);
  assert.equal(cleanup.preview.performed, false);
  assert.equal(cleanup.stillExists, true);
  assert.deepEqual(cleanup.owners, [{ threadId: sa.session, archived: false }]);
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`Verified ${checks.length} claims against ${records.length} records${drifted.length ? `; Dashpot modules changed since the run: ${drifted.join(", ")}` : ""}.`);
