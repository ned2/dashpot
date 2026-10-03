---
status: research
date: 2026-10-03
---

# tmux dropped SSH client experiment

The experiment for [Issue #410](https://github.com/ned2/dashpot/issues/410)
measures how long tmux keeps counting a client attached after the SSH
connection carrying it ends, on the installed **tmux 3.6** and **OpenSSH
10.2**. The Unattended Pause's tmux signal reads that count, as
`#{session_attached}` for the dashboard's own pane, on each GitHub tick
([ADR 0068](../adr/0068-pause-github-queries-while-the-dashboard-is-unattended.md)),
and ADR 0068 left open whether a dropped connection would pause a dashboard
before its idle period. The reusable result now lives in ADR 0068's
consequences and in
[Staying inside the limit](../github-rate-limits.md#staying-inside-the-limit);
this document is the dated evidence record with its fixtures and trace.

tmux counts a client attached exactly as long as the sshd session holding it
runs, so the question is when sshd notices its client is gone. Killing the
client's `ssh` or closing the terminal it runs in tells sshd at once, and
tmux reported the client detached within 11 ms. A silent drop, where
the client's packets simply stop as a laptop's do when it sleeps or loses
its network, tells sshd nothing. While the pane keeps writing, as a dashboard
does every local Refresh Period, sshd learns of it only when TCP gives up
retransmitting that output: 16 minutes after the drop on Linux's default
`tcp_retries2`, with or without a 60-second `ClientAliveInterval`. sshd's
keepalive needs a whole interval in which nothing arrives from the session
or the client, and a dashboard is never silent for 15 seconds; only a
silent session's drop was timed out by it, after 230 seconds. The client's own
`ServerAliveInterval` made `ssh` give up within 13 seconds, but the server
never heard. A dropped connection therefore pauses a dashboard about
seventeen minutes after the drop, well inside the two-hour idle period, and
no change to Dashpot's probe would detect it sooner.

## Reproduce

The retained experiment uses Node built-ins, OpenSSH's `sshd`, `ssh` and
`ssh-keygen`, tmux, util-linux `script`, `ss` and nftables. The drop
scenarios need root for `nft`, through `sudo -n`, so cache credentials first
in the terminal that runs the experiment:

```bash
sudo -v && node scripts/experiments/tmux-410/run.mjs
node scripts/experiments/tmux-410/verify.mjs /tmp/dashpot-tmux-410-SUFFIX/trace.jsonl docs/spikes/measurements/issue-410-dashboard-output-timing.txt
```

Replace the trace path with the exact one the runner prints. The run takes
about seventeen minutes: the two scenarios that end a connection outright
run first, then the three drops run together. The runner rejects a tmux other
than 3.6 unless an argument names the expected `tmux -V`, and the verifier
takes the same optional third argument. `SPIKE_SCENARIOS` runs a
comma-separated subset; without a drop scenario, the run needs no root.

- [Runner](../../scripts/experiments/tmux-410/run.mjs) starts, for each
  scenario, a private tmux server on its own socket and a private sshd as
  the invoking user on a free loopback port. The sshd has its own host key
  and authorized key, and its forced command attaches the tmux session, so
  the operator's sshd, tmux server and SSH configuration are never used. It
  connects with `ssh -tt`, waits 16 seconds for the pane to write once, ends
  the connection, and then reads `#{session_attached}` every second until it
  reports 0 or the scenario's cap passes. It records each change in that
  count and in whether the tmux client, `ssh` and sshd processes are alive,
  every sshd and `ssh` log line, and for a drop, the server socket's `ss
  -tnoi` state every 15 seconds.
- A drop adds two rules to one nftables table, `inet dashpot_410`, matching
  only that connection's two ports on the loopback interface, so neither
  side's packets arrive and no FIN or RST is seen. Each scenario deletes its
  rules when it ends, and the run deletes the table, on exit or interrupt
  too. The runner refreshes `sudo` every minute, so the rules are still
  deletable after sudo's default fifteen-minute credential cache.
- [Independent trace verifier](../../scripts/experiments/tmux-410/verify.mjs)
  checks the claims below against the trace and the timing log without
  importing the runner.
- [Retained trace](measurements/issue-410-tmux-trace.jsonl) is the complete
  metadata stream from the successful run: 246 records. Its first
  record includes the runner's SHA-256. The fixture root, the operator's home
  directory and username appear as `$ROOT`, `$HOME` and `$USER`.
- [Dashboard output timing](measurements/issue-410-dashboard-output-timing.txt)
  is `script --log-timing`'s record of every write tmux made to a client
  attached to a real dashboard on this Repository, at the default Refresh
  Periods, for 180 seconds after its first load: one line per write, the
  seconds since the previous write and the bytes written. It was recorded
  with:

  ```bash
  tmux -S "$SOCKET" -f /dev/null new-session -d -s fixture -x 200 -y 50 .venv/bin/dashpot
  sleep 20
  sleep 185 | script -q -O output.log -T timing.log -c "tmux -S $SOCKET attach-session -t fixture"
  ```

  The screen contents in `output.log` are not retained.

## Tested configuration and evidence boundary

| Fact | Tested value |
| --- | --- |
| Date | 2026-10-03 AEST |
| Dashpot base | `69c7d72ff920a86980766be6a93f0c2b09333e8b` |
| tmux | `tmux 3.6`, started with `-f /dev/null`, so its default status line |
| OpenSSH | `OpenSSH_10.2p1 Ubuntu-2ubuntu3.6`, one `sshd -D` per scenario as the invoking user, `UsePAM no`, `TCPKeepAlive yes` |
| Operating system | Ubuntu 26.04.1, Linux `7.0.0-34-generic`, x86-64 |
| TCP | `tcp_retries2` 15, `tcp_keepalive_time` 7200, `tcp_keepalive_intvl` 75, `tcp_keepalive_probes` 9, the defaults |
| Controller | Node `v24.18.0` |
| Pane | `while :; do date +%T; sleep 15; done`, a write every local Refresh Period; the quiet control runs `sleep infinity` with the status line off |

The connections run over loopback, so their round-trip time is a few
milliseconds and the retransmission timeout starts near Linux's 200 ms
minimum. Over a real network the timeout starts at least as high, so a
silent drop takes at least as long to notice; the 924.6-second lower bound
below holds either way, and the 120-second cap on a single retransmission
timeout bounds how far past it the abort can land. A drop here discards
both directions at the server; a network that instead answers with an ICMP
error or a RST would end the connection sooner. Sessions run with
`UsePAM no` as a non-root sshd, which does not change how a session ends.
macOS and other tmux and OpenSSH releases are unmeasured.

## Scenario results

| Scenario | How the connection ends | sshd's settings | Detached after | What ended the session |
| --- | --- | --- | --- | --- |
| `kill-ssh` | `SIGKILL` to the client's `ssh` | defaults | 11 ms | The kernel closes `ssh`'s socket; sshd logs `Connection closed` |
| `close-terminal` | `SIGKILL` to the `script` process holding the terminal `ssh` runs in | defaults | 7 ms | `ssh` gets `SIGHUP` and disconnects; sshd logs `disconnected by user` |
| `drop-client-alive-quiet` | Both directions dropped; the pane and status line are silent | `ClientAliveInterval 60`, `ClientAliveCountMax 3` | 229.9 s | sshd logs `Timeout, client not responding` |
| `drop-client-alive` | Both directions dropped | `ClientAliveInterval 60`, `ClientAliveCountMax 3` | 966.8 s | TCP gives up; sshd logs `Connection timed out` |
| `drop` | Both directions dropped; `ssh` sets `ServerAliveInterval 5`, `ServerAliveCountMax 2` | defaults | 966.7 s | TCP gives up; sshd logs `Connection timed out` |

In every scenario the tmux client exited with the sshd session that held it,
and the next probe read 0. The server socket of each redrawing drop stayed
established and retransmitting until the abort, its retransmission timeout
doubling from about 200 ms to the 120-second cap.

## Findings

### Ending `ssh` detaches at once

A killed `ssh` leaves the kernel to close its socket, and sshd reads the end
of the stream. A closed terminal sends `ssh` `SIGHUP`, and `ssh` disconnects
cleanly. Either way sshd ends the session, the pseudo-terminal closes under
the tmux client, and the client exits; tmux reported 0 at the next probe.
A dashboard in that session pauses at its next GitHub tick, within a GitHub
Refresh Period.

### A silent drop lasts until TCP gives up

When the client's packets stop without a FIN, nothing reaches sshd. The pane
keeps writing, so sshd keeps sending, and the kernel retransmits each
unacknowledged segment with exponential backoff. Linux's documentation for
[`tcp_retries2`](https://docs.kernel.org/networking/ip-sysctl.html) gives
its default of 15 a hypothetical timeout of 924.6 seconds, a lower bound:
TCP aborts at the first retransmission timeout past it, and a single timeout
is capped at 120 seconds. The first unacknowledged segment follows the drop
within one pane write: in the `drop` scenario the server socket had already
retransmitted twice 15.2 seconds after the drop. Both redrawing drops were
detached 966.7 and 966.8 seconds after the drop, about 952 seconds after
their first unacknowledged segment, inside that window. sshd's next read
failed with `Connection timed out`, it ended the session, and tmux reported
0.

TCP keepalive, on by sshd's default `TCPKeepAlive yes`, plays no part: its
first probe waits for two hours of idleness, and a connection with
unacknowledged data is never idle. By the kernel's settings, a silent drop of
a session that writes nothing and has no client-alive probes would last until
those probes fail, 7,875 seconds or about two hours and eleven minutes,
longer than the idle period. This run did not measure it, since a dashboard
is never such a session.

### sshd's keepalive needs silence

OpenSSH 10.2's server loop, in `wait_until_can_do_something` in
[`serverloop.c`](https://github.com/openssh/openssh-portable/blob/V_10_2_P1/serverloop.c),
sends a client-alive probe only when its `ppoll` returns with nothing ready
after a whole `ClientAliveInterval`. Output from the session wakes `ppoll`
too, so a pane that writes more often than the interval never lets a probe
go out, and the count that ends the session after `ClientAliveCountMax`
unanswered probes never starts. With a silent pane, sshd checked every 60
seconds from the last data the client sent, 16 seconds before the drop, and
ended the session on the fourth check, 230 seconds after the drop. With the
redrawing pane and the same settings, sshd logged no client-alive timeout,
and TCP ended the session as it did without keepalives.

A dashboard leaves no silence that long. The retained timing log holds 535
writes over 180 seconds, roughly 1 to 2 KB redrawn every 15 seconds, and no
gap between writes longer than 14.5 seconds. So a `ClientAliveInterval` of
the usual minute or more never sends a probe while a dashboard is on screen.
An interval below the 15-second redraw would let probes out between
redraws, but it applies to every SSH session on the host, and with the
default `ClientAliveCountMax` of 3 it would cut any of them through a network
pause of under a minute. This run measured only the 60-second interval.

### `ServerAliveInterval` ends only the client

With `ServerAliveInterval 5` and `ServerAliveCountMax 2`, `ssh` logged
`Timeout, server 127.0.0.1 not responding.` and exited 12.8 seconds after
the drop. Its goodbye could not reach the server, so tmux counted the client
attached for the full 966.7 seconds. The setting helps the person, whose
terminal comes back, not the dashboard.

## Implications for Dashpot

- A dashboard whose SSH connection drops silently pauses about seventeen
  minutes later: the TCP abort, then up to one GitHub Refresh Period for
  the next probe. At the measured 300 points an hour, that is under 100
  points, where the idle period alone would have allowed about 600.
- No tmux setting shortens that, and no sshd setting does without
  affecting every SSH session on the host: a `ClientAliveInterval` below
  the 15-second redraw, or a lower `tcp_retries2` for every TCP connection.
  Neither is Dashpot's to recommend.
- The probe needs no change. It already reads the one count that changes
  when sshd ends the session, and a dead client that tmux still counts is
  indistinguishable from a live one that is not looking: neither the probe
  nor tmux sees the connection beneath the pseudo-terminal. The scope note
  on #410 allowed a code change only if the probe could tell the two apart,
  and it cannot.

## Validation

The retained trace and timing log pass the independent verifier, which also
checks that the trace's recorded runner hash matches the retained runner.
After the run, `sudo nft list table inet dashpot_410` reported no such
table, and `pgrep` found no fixture `sshd` or tmux server left.
