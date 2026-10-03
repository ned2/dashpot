---
status: accepted
date: 2026-10-01
---

# Pause GitHub queries while the dashboard is unattended

A dashboard's GitHub Refresh Period ran whether or not anyone was looking.
A dashboard left in a tmux session on a cloud machine can run for weeks, and
at about 300 points an hour
([GitHub rate limits](../github-rate-limits.md#how-dashpot-spends-the-allowance))
that is around 50,000 points a week spent on data nobody reads
([#354](https://github.com/ned2/dashpot/issues/354), part of
[#308](https://github.com/ned2/dashpot/issues/308)). Local observation costs
no allowance, so it is not the concern here; its process spend is
[#317](https://github.com/ned2/dashpot/issues/317)'s.

## Decision

- **Two signals show the dashboard unattended.**
  - **No tmux client attached.** When the dashboard runs inside tmux (both
    `TMUX` and `TMUX_PANE` set), it asks
    `tmux display-message -p -t $TMUX_PANE '#{session_attached}'`. That
    names the session holding the dashboard's own pane, and reports 0 once
    every client has detached. An answer that cannot be read (tmux missing,
    a timeout, a non-zero exit, output that is not a count) changes
    nothing.
  - **No input for the idle period.** No key or mouse event for
    `unattended_seconds`, a machine-local setting with the
    `--unattended-seconds` flag, 7,200 seconds (two hours) by default. Zero
    turns this signal off; a detached tmux session still pauses.
- **Terminal blur alone is not a signal.** A visible dashboard beside a
  person's work, unfocused, is a core use. Blur is also unreliable under
  tmux: with tmux 3.6 and `focus-events on`, `detach-client` delivers
  focus-out and then focus-in about 10 ms later, and an SSH drop delivers
  nothing.
- **Both are checked on the GitHub tick.** Each tick of the GitHub Refresh
  Period checks the idle period and starts the tmux probe off the event
  loop, one at a time, so the probe costs one process per GitHub Refresh
  Period (a minute by default). A pause therefore starts within one period
  of its signal. The idle check needs no process.
- **While the Unattended Pause holds, a GitHub tick sends nothing.** The
  tick checks the two signals again and returns without refreshing Query
  Pages, Project Totals or Resolved Issues. Local observation continues on
  its own period, but a change in which Issues its Agent Runs are bound to
  waits for the resume to resolve them.
- **Any sign of someone attending resumes, with a GitHub refresh at once.**
  A key, a mouse event, the terminal reporting focus-in, or the probe
  finding a client attached again after it found none ends the pause. The
  GitHub refresh it skipped runs immediately and the GitHub Refresh Period
  restarts from then. `r` resumes the same way, and its manual refresh
  follows. Whether a key reaches its binding is known only after the
  dashboard has dispatched it: an `r` typed into a search field refreshes
  nothing itself, so no key's resume waits on one. A client that stayed
  attached ends nothing: an idle pause outlasts it.
- **Resuming lifts nothing else.** The Unattended Pause and the Rate Limit
  Pause
  ([ADR 0065](0065-pause-github-queries-after-a-rate-limit-refusal.md)) are
  independent holds. A key that ends an Unattended Pause leaves a Rate Limit
  Pause in force, and its refresh's requests are held as that ADR describes;
  only `r` lifts a Rate Limit Pause for one attempt.
- **Only a GitHub Query Source pauses.** A dashboard whose Query Sources are
  all local watches no attendance: its refreshes spend nothing.
- **The pause shows in three places, as the Rate Limit Pause does.**
  - One `github-unattended-paused` Diagnostic line, at `info` severity,
    naming since when queries have been paused, which signal paused them,
    and that any key resumes. It is an observation, not a fault, so it does
    not colour the Diagnostics box amber.
  - A standalone `unattended_pause.changed` Runtime Event at `standard`,
    `started` or `ended`, with the signal that started the pause:
    `detached` or `idle`. The ending carries the same signal, so the Event
    Log pairs the two without a reason field of free text.
  - Runtime Stats leads its GitHub allowance section with an `unattended`
    row naming when the pause started and why, after the Rate Limit Pause's
    `paused` row when both hold.

## Consequences

- **An abandoned dashboard stops spending.** Detaching from an attended
  dashboard costs at most one more GitHub refresh, the one whose tick
  started the probe. Any other unattended dashboard spends for the idle
  period and then nothing, however long it runs.
- **Pages keep what they last observed.** While paused, each Query Page,
  Project Totals and Resolved Issue stays as its last observation landed,
  and the Diagnostic line says since when the pause has held. That is when the
  tick or probe that started it saw nobody, so the data can be up to one GitHub
  Refresh Period older; Runtime Stats names the last GitHub refresh.
  Nothing is marked stale, since nothing failed.
- **A dashboard someone only looks at pauses after the idle period.**
  Reading a dashboard without touching it for two hours is
  indistinguishable from leaving it. The first key or mouse movement
  refreshes it at once, and the period can be lengthened or turned off.
- **A spurious focus-in costs a refresh or two.** A focus-in that is not
  someone returning ends the pause as if it were, and restarts the idle
  period. tmux delivers one about 10 ms after a detach. Detaching from an
  attended dashboard ends nothing, since no pause holds yet. Detaching from
  one already in an idle pause ends it: the resume refreshes, the next tick
  refreshes again because the idle period restarted, and the probe that
  tick starts pauses it as detached. The Event Log shows the ended and
  started pair.
- **A dropped SSH connection pauses about 16 to 19 minutes later.** tmux
  counts a client attached until the sshd session holding it ends, and the
  next probe pauses once it has
  ([measured for #410](../spikes/tmux-dropped-ssh-client-spike.md) on tmux
  3.6 and OpenSSH 10.2 over loopback). Killing the client's `ssh` or ending
  the process holding its terminal ends the session within a second. A
  silent drop, a laptop sleeping or losing its network, ends it only when
  TCP gives up retransmitting the dashboard's redraws: after 16 minutes in
  the measurement, and within 18 on Linux's default `tcp_retries2`. A
  `ClientAliveInterval` longer than the local Refresh Period, 15 seconds by
  default, does not shorten that while a dashboard is on screen: sshd probes
  only after a whole interval in which neither the session nor the client
  sends anything, and the dashboard redraws every local Refresh Period.
  `ssh`'s `ServerAliveInterval` ends only the client. Either way the pause
  starts long before the idle period.
- **The pause belongs to one dashboard.** Two dashboards in one tmux
  session pause together only because they see the same signals.

## Considered options

- **Pause on terminal blur.** Rejected for the reasons in the decision: it
  would pause a dashboard a person is reading beside their work, and tmux
  does not report detachment reliably as blur.
- **Probe tmux on the local Refresh Period.** It would notice detachment
  within 15 seconds rather than 60, at four times the processes. The
  GitHub tick is the one the pause holds, so checking on it is enough.
- **Generalise the Rate Limit Pause to carry a reason.** The two pauses
  start, end and are lifted by different things: one by GitHub's refusal and
  its reset, held at the gateway; the other by the person, held at the
  timer. One event and one term would need a reason to tell them apart and
  would blur which keys lift which. A sibling term and event keep each one's
  lifecycle whole.
- **Hold the requests at the gateway, as the Rate Limit Pause does.** A
  held request fails and marks its observation stale, which would report a
  dashboard nobody watched as broken. Skipping the tick sends nothing and
  fails nothing.
