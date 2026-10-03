// Independent verifier for the Issue #410 dropped SSH client trace: checks
// each claim the spike and ADR 0068 make about how long tmux keeps counting a
// client attached after its SSH connection ends, against the recorded probe
// samples, sshd and ssh log lines and server socket states, and the claim
// about how often a dashboard writes to its client against the `script`
// timing log of one.
//
// Usage: node verify.mjs <trace.jsonl> <dashboard timing log> [expected tmux version]
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const [file, timingFile] = process.argv.slice(2);
assert(file && timingFile, "Pass the trace and the dashboard timing log to verify");
const expectedVersion = process.argv[4] ?? "tmux 3.6";
const records = readFileSync(file, "utf8").trim().split("\n").map((line) => JSON.parse(line));
const checks = [];
const check = (claim, test) => { test(); checks.push(claim); };

const of = (kind, scenario) => records.filter((record) => record.kind === kind && record.scenario === scenario);
const one = (kind, scenario) => {
  const [found] = of(kind, scenario);
  assert(found, `${kind} of ${scenario}`);
  return found;
};
const environment = records[0];
const scenario = (name) => environment.scenarios.find((item) => item.name === name);
const detached = (name) => one("detached", name).afterEnd;
const logged = (name, source, pattern) => of("log", name).find((record) => record.source === source && pattern.test(record.line));
const minutes = (ms) => `${(ms / 60_000).toFixed(1)} min`;
// Every probe before the client detached saw it attached, and the tmux
// client process had exited by the probe that saw it detached.
const attachedUntilDetached = (name) => {
  const samples = of("sample", name);
  assert(samples.length > 0, `samples of ${name}`);
  for (const sample of samples.slice(0, -1)) assert.equal(sample.attached, 1, JSON.stringify(sample));
  assert.equal(samples.at(-1).attached, 0);
  assert.equal(samples.at(-1).tmuxClient, false);
};
// Every socket sample after the drop showed the server's connection
// established and retransmitting, its timeout grown from near the 200 ms
// minimum to the 120 s cap.
const rto = (state) => Number(state.match(/ rto:(\d+)/)[1]);
const retransmitting = (name) => {
  const states = of("socket", name).map((record) => record.state);
  assert(states.length > 0, `socket samples of ${name}`);
  assert(rto(states[0]) < 250, states[0]);
  for (const state of states.slice(1)) assert.match(state, /^ESTAB .* timer:\(on,/, state);
  assert.equal(rto(states.at(-1)), 120_000, states.at(-1));
};

check("The trace was recorded by the retained runner", () => {
  const runner = readFileSync(new URL("run.mjs", import.meta.url));
  assert.equal(environment.runner, createHash("sha256").update(runner).digest("hex"));
});

check(`The trace was recorded on ${expectedVersion} with Linux's default TCP retransmission and keepalive settings`, () => {
  assert.equal(environment.kind, "environment");
  assert.equal(environment.tmux, expectedVersion);
  assert.match(environment.openssh, /^OpenSSH_/);
  assert.deepEqual(environment.sysctl, { tcp_retries2: 15, tcp_keepalive_time: 7200, tcp_keepalive_intvl: 75, tcp_keepalive_probes: 9 });
  assert.deepEqual(environment.scenarios.map((item) => item.name), ["kill-ssh", "close-terminal", "drop-client-alive-quiet", "drop-client-alive", "drop"]);
});

check("Every scenario attached one tmux client through the fixture sshd, and each drop matched only its own connection's two ports", () => {
  for (const { name, end } of environment.scenarios) {
    const attached = one("attached", name);
    assert(attached.tmuxClient > 0 && attached.clientPort > 0, name);
    assert(one("end", name).t > attached.t, name);
    if (end === "drop") {
      assert.deepEqual(one("nft", name).rules, [
        `iifname "lo" tcp sport ${attached.clientPort} tcp dport ${attached.port} drop`,
        `iifname "lo" tcp sport ${attached.port} tcp dport ${attached.clientPort} drop`,
      ]);
    }
  }
});

check("Killing the client's ssh detached the tmux client within a second", () => {
  attachedUntilDetached("kill-ssh");
  assert(detached("kill-ssh") < 1_000, String(detached("kill-ssh")));
  assert(logged("kill-ssh", "sshd", /^Connection closed by 127\.0\.0\.1 port \d+$/));
});

check("Closing the terminal ssh ran in detached the tmux client within a second, after ssh disconnected cleanly", () => {
  attachedUntilDetached("close-terminal");
  assert(detached("close-terminal") < 1_000, String(detached("close-terminal")));
  assert(logged("close-terminal", "sshd", /^Received disconnect from 127\.0\.0\.1 port \d+:11: disconnected by user$/));
});

check("A silent drop of a silent session detached the tmux client once sshd's ClientAliveInterval timed the client out", () => {
  const { interval, countMax } = scenario("drop-client-alive-quiet").clientAlive;
  attachedUntilDetached("drop-client-alive-quiet");
  assert(detached("drop-client-alive-quiet") >= countMax * interval * 1_000, String(detached("drop-client-alive-quiet")));
  assert(detached("drop-client-alive-quiet") <= (countMax + 1) * interval * 1_000 + 2_000, String(detached("drop-client-alive-quiet")));
  assert(logged("drop-client-alive-quiet", "sshd", /^Timeout, client not responding from user \$USER 127\.0\.0\.1 port \d+$/));
});

// The window Linux's tcp_retries2 of 15 gives: its hypothetical 924.6 s
// timeout is a lower bound, and TCP aborts at the first retransmission
// timeout past it, at most one 120 s maximum RTO later. Both count from the
// first unacknowledged segment, which the pane writes within 15 s of the
// drop; the probe adds up to a second.
const retransmissionWindow = [924_600, 15_000 + 924_600 + 120_000 + 1_000];
for (const name of ["drop-client-alive", "drop"]) {
  check(`A silent drop of a redrawing session${name === "drop" ? " without keepalives" : " under ClientAliveInterval"} left the tmux client attached until TCP retransmission gave up after ${minutes(detached(name))}`, () => {
    attachedUntilDetached(name);
    assert(detached(name) >= retransmissionWindow[0] && detached(name) <= retransmissionWindow[1], String(detached(name)));
    retransmitting(name);
    assert(logged(name, "sshd", /Connection timed out/));
    assert(!logged(name, "sshd", /^Timeout, client not responding/));
  });
}

check("The client's ServerAliveInterval made ssh give up within a minute while tmux still counted it attached", () => {
  const { interval, countMax } = scenario("drop").serverAlive;
  const exit = one("client.exit", "drop");
  const after = exit.t - one("end", "drop").t;
  assert(after <= (countMax + 1) * interval * 1_000 + 2_000, String(after));
  assert.equal(exit.code, 255);
  assert(logged("drop", "ssh", /^Timeout, server 127\.0\.0\.1 not responding\.$/));
  assert(after < detached("drop"));
});

check("An open dashboard sent its tmux client output at least every 15 seconds", () => {
  const chunks = readFileSync(timingFile, "utf8").trim().split("\n").map((line) => line.split(" ").map(Number));
  const total = chunks.reduce((sum, [gap]) => sum + gap, 0);
  assert(total >= 170, String(total));
  for (const [gap, bytes] of chunks) {
    assert(bytes > 0);
    assert(gap <= 15, String(gap));
  }
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified against ${records.length} records`);
