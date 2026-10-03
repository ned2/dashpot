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
// The dashboard's default local Refresh Period, which the runner's pane
// imitates with a write every 15 s.
const redrawMs = 15_000;
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

check("A silent drop of a silent session detached the tmux client once sshd's ClientAliveInterval timed the client out, counting from sshd's last send before the drop", () => {
  const name = "drop-client-alive-quiet";
  const { interval, countMax } = scenario(name).clientAlive;
  attachedUntilDetached(name);
  const [first] = of("socket", name);
  assert(first, `socket samples of ${name}`);
  const lastSend = first.t - Number(first.state.match(/ lastsnd:(\d+)/)[1]);
  assert(lastSend < one("end", name).t, String(lastSend));
  const timeout = logged(name, "sshd", /^Timeout, client not responding from user \$USER 127\.0\.0\.1 port \d+$/);
  assert(timeout);
  // sshd checks once per silent interval and gives up on the check after
  // ClientAliveCountMax unanswered ones.
  const checksAfter = (countMax + 1) * interval * 1_000;
  assert(Math.abs(timeout.t - lastSend - checksAfter) <= 1_000, String(timeout.t - lastSend));
  assert(detached(name) >= timeout.t - one("end", name).t, String(detached(name)));
});

// Linux's tcp_retries2 of 15 gives a hypothetical 924.6 s timeout, a lower
// bound: TCP aborts at the first retransmission timeout past it, at most one
// 120 s maximum timeout later. Both count from the first retransmitted
// segment, which the pane's next write sends within one redraw of the drop.
const retries2Ms = 924_600;
const maxRtoMs = 120_000;
for (const [name, settings] of [["drop-client-alive", "under a 60 s ClientAliveInterval"], ["drop", "with only the client's ServerAliveInterval and sshd's TCPKeepAlive"]]) {
  check(`A silent drop of a redrawing session ${settings} left the tmux client attached until TCP gave up retransmitting, ${minutes(detached(name))} after the drop`, () => {
    attachedUntilDetached(name);
    retransmitting(name);
    const end = one("end", name);
    const firstRetransmitting = of("socket", name).find((record) => / backoff:\d+/.test(record.state));
    assert(firstRetransmitting && firstRetransmitting.afterEnd <= redrawMs + 1_000, JSON.stringify(firstRetransmitting));
    assert(Number(firstRetransmitting.state.match(/ backoff:(\d+)/)[1]) >= 2, firstRetransmitting.state);
    const abort = logged(name, "sshd", /^Read error from remote host 127\.0\.0\.1 port \d+: Connection timed out$/);
    assert(abort);
    const abortAfter = abort.t - end.t;
    assert(abortAfter - firstRetransmitting.afterEnd >= retries2Ms, String(abortAfter));
    assert(abortAfter <= retries2Ms + maxRtoMs + firstRetransmitting.afterEnd, String(abortAfter));
    assert(detached(name) >= abortAfter && detached(name) - abortAfter <= 2_000, String(detached(name)));
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

// Writes less than a second apart belong to one burst. The first burst is
// the first load's paint; each later one of over 20 KB is a redraw, and once
// a minute one is about twice the size of the others.
const chunks = readFileSync(timingFile, "utf8").trim().split("\n").map((line) => line.split(" ").map(Number));
const bursts = [];
let elapsed = 0;
for (const [gap, bytes] of chunks) {
  elapsed += gap;
  if (bursts.length === 0 || gap >= 1) bursts.push({ start: elapsed, bytes: 0, writes: 0 });
  bursts.at(-1).bytes += bytes;
  bursts.at(-1).writes += 1;
}
const redraws = bursts.slice(1).filter((burst) => burst.bytes >= 20_000);
const doubled = redraws.filter((redraw) => redraw.bytes >= 40_000);
const ordinary = redraws.filter((redraw) => redraw.bytes < 40_000);
const longestGap = Math.max(...chunks.map(([gap]) => gap));
const pairs = (items) => items.slice(1).map((item, index) => [items[index], item]);
check(`An open dashboard wrote to its tmux client ${chunks.length} times in ${Math.round(elapsed)} s, never more than ${Math.ceil(longestGap * 10) / 10} s apart, redrawing ${Math.round(Math.min(...ordinary.map((redraw) => redraw.bytes)) / 1_000)} to ${Math.round(Math.max(...ordinary.map((redraw) => redraw.bytes)) / 1_000)} KB every Refresh Period and about twice that once a minute`, () => {
  assert(elapsed >= 170, String(elapsed));
  for (const [, bytes] of chunks) assert(bytes > 0);
  assert(longestGap <= 14.6, String(longestGap));
  assert(redraws.length >= 10, String(redraws.length));
  for (const [previous, next] of pairs(redraws)) {
    assert(next.start - previous.start <= redrawMs / 1_000 + 0.5, JSON.stringify([previous, next]));
  }
  for (const redraw of ordinary) {
    assert(redraw.bytes >= 21_500 && redraw.bytes < 24_500, JSON.stringify(redraw));
    assert(redraw.writes >= 20 && redraw.writes <= 40, JSON.stringify(redraw));
  }
  assert(doubled.length >= 2, String(doubled.length));
  for (const redraw of doubled) assert(redraw.bytes >= 1.8 * 21_500 && redraw.bytes <= 2.2 * 24_500, JSON.stringify(redraw));
  for (const [previous, next] of pairs(doubled)) assert(Math.abs(next.start - previous.start - 60) <= 1, JSON.stringify([previous, next]));
});

for (const claim of checks) console.log(`ok - ${claim}`);
console.log(`${checks.length} claims verified against ${records.length} records`);
