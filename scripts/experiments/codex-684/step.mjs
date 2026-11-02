// The shell command the fixture model asks a Worker to run in its Worktree:
// one or more Git steps against the fixture's `origin`, in order, each
// attempted whatever the step before it did. Prints one `STEP {json}` line
// per step, which reaches the runner as the tool output in the Worker's next
// model request. A report carries names, statuses, scheme classes, digests
// and classified error lines only: never an environment or Git configuration
// value, and never a credential.
//
//   node step.mjs <label> <branch> <outside directory> <step> [<step> ...]
//
// Steps:
//   probe        the shell's own view: uid, environment names, effective Git
//                configuration keys by scope, the transport `origin`
//                resolves to, the system SSH files' ownership, `ssh -G`
//                through the system configuration and through
//                GIT_SSH_COMMAND, the agent, and a control write outside
//                every writable root;
//   ls-remote    `git ls-remote origin`;
//   commit       a new commit on the Worktree's branch;
//   push         the first push, `git push origin HEAD:refs/heads/<branch>`;
//   amend        rewrite the pushed commit;
//   lease        `git push --force-with-lease=refs/heads/<branch>:<pushed head>`;
//   stale-lease  amend again, then lease against the head the lease replaced,
//                which the remote must refuse;
//   unknown-host `git ls-remote origin` with a known-hosts file that does not
//                yet name the host, in a directory the sandbox does not grant.
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { appendFileSync, existsSync, lstatSync, readFileSync, readlinkSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";

const [label, branch, outside, ...steps] = process.argv.slice(2);
const fragment = "/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf";
// Classified error and progress lines: what failed, and where.
const notable = /fatal:|error:|Bad owner|Permission denied|Could not|could not|rejected|stale info|denied|Host key|Failed to add|Permanently added|unable to|Authentication failed|Read-only file system|->/;
const lines = (text) => String(text ?? "").split("\n").map((line) => line.trim()).filter((line) => notable.test(line) && !line.startsWith("PREPUSH ")).map((line) => line.slice(0, 300)).slice(0, 12);
const prepush = (text) => String(text ?? "").split("\n").flatMap((line) => {
  const found = /^PREPUSH (\{.*\})$/.exec(line.trim());
  if (!found) return [];
  try { return [JSON.parse(found[1])]; } catch { return []; }
});
const run = (command, args, extraEnv = {}) => {
  const started = Date.now();
  const ran = spawnSync(command, args, { env: { ...process.env, ...extraEnv }, encoding: "utf8", timeout: 120000, maxBuffer: 1 << 24 });
  return { status: ran.status, signal: ran.signal, ms: Date.now() - started, stdout: ran.stdout ?? "", stderr: `${ran.stderr ?? ""}${ran.error ? `\n${ran.error.message}` : ""}` };
};
const git = (...args) => run("git", args);
const head = () => git("rev-parse", "HEAD").stdout.trim() || null;
const scheme = (url) => {
  const value = url.trim();
  if (!value) return null;
  if (/^https:\/\//.test(value)) return "https";
  if (/^http:\/\//.test(value)) return "http";
  if (/^ssh:\/\//.test(value) || /^[^/:]+:/.test(value)) return "ssh";
  return "other";
};
const digest = (text) => createHash("sha256").update(text).digest("hex");
// The fixture's per-Worktree state, in the Worktree's own Git directory,
// which the sandbox grants: which head the remote holds for this branch.
const stateFile = path.join(git("rev-parse", "--absolute-git-dir").stdout.trim(), "fixture-684-state.json");
const state = () => existsSync(stateFile) ? JSON.parse(readFileSync(stateFile, "utf8")) : {};
const save = (update) => writeFileSync(stateFile, JSON.stringify({ ...state(), ...update }));
const owner = (file) => {
  try {
    const link = lstatSync(file);
    const target = statSync(file);
    return { symlink: link.isSymbolicLink(), target: link.isSymbolicLink() ? readlinkSync(file) : null, uid: target.uid, gid: target.gid, mode: (target.mode & 0o7777).toString(8) };
  } catch (error) { return { error: error.code ?? String(error.message) }; }
};
const writeAt = (file) => {
  try { writeFileSync(file, "fixture\n"); return { ok: true }; } catch (error) { return { ok: false, error: error.code ?? String(error.message).slice(0, 120) }; }
};
const outsideWrite = (name) => writeAt(path.join(outside, name));
// A git operation's outcome: status, classified lines, the pre-push hook's
// reports, and the head before and after.
const gitOutcome = (ran) => ({ status: ran.status, ok: ran.status === 0, ms: ran.ms, lines: lines(ran.stderr), prepush: prepush(ran.stderr) });
const edit = (text) => appendFileSync("fixture.txt", `${text}\n`);
const amend = () => {
  const before = head();
  edit(`${label} amended at ${Date.now()}`);
  const ran = git("commit", "--amend", "--no-edit", "-a");
  return { before, after: head(), status: ran.status, lines: lines(ran.stderr) };
};

const actions = {
  probe: () => {
    const sshThroughSystem = run("ssh", ["-F", "/etc/ssh/ssh_config", "-G", "fixture-forge"]);
    const sshCommand = process.env.GIT_SSH_COMMAND ? run("sh", ["-c", `${process.env.GIT_SSH_COMMAND} -G fixture-forge`]) : null;
    // Whether the resolved known-hosts file already names the fixture host,
    // read from inside the sandbox.
    const seeded = (ran) => {
      const file = /^userknownhostsfile (\S+)/m.exec(ran.stdout)?.[1];
      return file ? run("ssh-keygen", ["-F", "fixture-forge", "-f", file]).status === 0 : null;
    };
    const resolved = (ran) => ran && { status: ran.status, lines: lines(ran.stderr),
      hostname127: /^hostname 127\.0\.0\.1$/m.test(ran.stdout), port: Number(/^port (\d+)$/m.exec(ran.stdout)?.[1] ?? 0) || null,
      batchMode: /^batchmode yes$/m.test(ran.stdout), identitiesOnly: /^identitiesonly yes$/m.test(ran.stdout),
      strictHostKeyChecking: /^stricthostkeychecking (\S+)$/m.exec(ran.stdout)?.[1] ?? null, knownHostsSeeded: ran.status === 0 ? seeded(ran) : null };
    const agent = process.env.SSH_AUTH_SOCK ? run("ssh-add", ["-l"]) : null;
    const configKeys = git("config", "--list", "--show-scope", "--name-only").stdout.trim().split("\n").filter(Boolean).map((line) => line.split("\t"));
    const url = git("config", "--get", "remote.origin.url").stdout;
    return {
      uid: process.getuid(), gid: process.getgid(), cwd: process.cwd(),
      envNames: Object.keys(process.env).sort(),
      sandbox: { CODEX_SANDBOX: process.env.CODEX_SANDBOX ?? null, CODEX_SANDBOX_NETWORK_DISABLED: process.env.CODEX_SANDBOX_NETWORK_DISABLED ?? null },
      thread: process.env.CODEX_THREAD_ID ?? null,
      gitConfigKeys: configKeys,
      transport: { fetch: scheme(git("ls-remote", "--get-url", "origin").stdout), push: scheme(git("remote", "get-url", "--push", "origin").stdout) },
      remoteUrl: { scheme: scheme(url), sha256: digest(url.trim()), pushUrls: git("config", "--get-all", "remote.origin.pushurl").stdout.trim().split("\n").filter(Boolean).length },
      systemConfig: owner("/etc/ssh/ssh_config"), fragment: owner(fragment),
      sshThroughSystem: resolved(sshThroughSystem), sshCommand: resolved(sshCommand),
      agent: agent && { status: agent.status, keys: agent.stdout.trim().split("\n").filter(Boolean).length, lines: lines(agent.stderr),
        // A control write beside the socket: refused when its directory is
        // outside every writable root.
        directoryWrite: writeAt(path.join(path.dirname(process.env.SSH_AUTH_SOCK), `${label}-probe`)) },
      outsideWrite: outsideWrite(`${label}-probe`),
    };
  },
  "ls-remote": () => {
    const ran = git("ls-remote", "origin");
    return { ...gitOutcome(ran), refs: ran.stdout.trim().split("\n").filter(Boolean).map((line) => line.split("\t")[1]) };
  },
  commit: () => {
    const before = head();
    edit(`${label} committed at ${Date.now()}`);
    git("add", "fixture.txt");
    const ran = git("commit", "-m", `Fixture commit for ${label}`);
    return { before, after: head(), status: ran.status, lines: lines(ran.stderr) };
  },
  push: () => {
    const local = head();
    const ran = git("push", "origin", `HEAD:refs/heads/${branch}`);
    if (ran.status === 0) save({ pushed: local });
    return { ...gitOutcome(ran), local };
  },
  amend,
  lease: () => {
    const old = state().pushed ?? null;
    const local = head();
    const ran = git("push", `--force-with-lease=refs/heads/${branch}:${old}`, "origin", `HEAD:refs/heads/${branch}`);
    if (ran.status === 0) save({ pushed: local, replaced: old });
    return { ...gitOutcome(ran), old, local };
  },
  "stale-lease": () => {
    const rewritten = amend();
    const stale = state().replaced ?? null;
    const ran = git("push", `--force-with-lease=refs/heads/${branch}:${stale}`, "origin", `HEAD:refs/heads/${branch}`);
    return { ...gitOutcome(ran), amend: rewritten, stale, local: head(), remoteHolds: state().pushed ?? null };
  },
  "unknown-host": () => {
    const knownHosts = path.join(outside, `known_hosts-${label}`);
    const command = `${process.env.GIT_SSH_COMMAND ?? "ssh"} -o UserKnownHostsFile=${knownHosts} -o StrictHostKeyChecking=accept-new`;
    const ran = run("git", ["ls-remote", "origin"], { GIT_SSH_COMMAND: command });
    return { ...gitOutcome(ran), refs: ran.stdout.trim().split("\n").filter(Boolean).length, knownHostsWritten: existsSync(knownHosts) };
  },
};
for (const step of steps) {
  let report;
  try { report = actions[step] ? actions[step]() : { error: `unknown step ${step}` }; } catch (error) { report = { error: String(error?.stack ?? error).slice(0, 400) }; }
  console.log(`STEP ${JSON.stringify({ label, step, ...report })}`);
}
