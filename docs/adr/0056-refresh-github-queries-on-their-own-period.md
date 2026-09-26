---
status: accepted
date: 2026-09-26
---

# Refresh GitHub queries on their own period

One period, `--refresh-seconds` (15 seconds by default), paced every automatic
refresh of the dashboard. It paced two kinds of work with different costs:

- **Local observation.** Worktrees, Branches, Agent Sessions and Agent Runs
  come from Git, the filesystem and the lifecycle hooks, and cost nothing.
  This is how a person sees agents start, stop and move, so it has to be
  quick.
- **GitHub queries.** Both Query Pages, both kinds' Project Totals, and the
  Resolved Issues that Agent Runs are bound to change more slowly. Each
  request spends the hourly GraphQL allowance the account shares with every
  other tool acting as the same user.

With one period, a person had to choose between stale Agent Sessions and a
dashboard that spent most of the allowance. The period was also only a flag,
so it had to be passed on every launch
([#310](https://github.com/ned2/dashpot/issues/310)).

## Decision

- **Two Refresh Periods.** The local period paces local observation. The
  GitHub period paces a GitHub Query Source's Query Pages, Project Totals and
  Resolved Issues. Each runs its own timer.
- **Defaults.** The local period stays at 15 seconds. The GitHub period is 60
  seconds.
- **Query Sources that cost nothing follow the local period.** A Local
  Markdown Issue Source's queries keep pace with local observation, so an
  edited Issue file shows up as quickly as before. Only a GitHub Query Source
  takes the GitHub period.
- **Both periods are machine-local settings.** `refresh_seconds` and
  `github_refresh_seconds` are read from `config.toml`
  ([ADR 0052](0052-read-machine-local-settings-as-toml.md)). The flags
  `--refresh-seconds` and `--github-refresh-seconds` override them.
  Precedence is flag, then setting, then default.
- **Zero switches a period off.** TOML has no null, so 0 is the spelling in
  the settings file, and an absent setting means the default. Each setting
  must be a finite number of seconds, zero or more.
- **Unreadable settings leave the defaults.** A settings file that cannot be
  read or does not validate already disables the Worktree launcher and
  reports a Diagnostic on the dashboard
  ([ADR 0035](0035-open-worktrees-on-explicit-key-press.md)). The periods then
  keep their defaults, and a flag still applies; the dashboard still opens.
- **A manual refresh (`r`) refreshes both kinds of work at once and restarts
  both timers.**
- **Bound Issues resolve on the GitHub period, unless they change.** A GitHub
  tick resolves the bound Issues, the selected Issue and its direct
  relationships. Agent Runs land on the local period. A landing resolves them
  again only when the set of Issues to resolve differs from the last one
  requested, so a run starting Issue work is resolved without waiting for the
  next GitHub tick. Opening an Issue resolves its relationships immediately,
  as before.

## Consequences

- **The GitHub spend falls to under a quarter.** An open dashboard's GitHub
  spend is paced by the GitHub period. Measured on 2026-09-26, a dashboard on
  this Repository sent 7 requests a minute, where it had sent 8 every 15
  seconds. The cost figures are in
  [GitHub rate limits](../github-rate-limits.md#how-dashpot-spends-the-allowance).
- **One resolution per tick.** Because an unchanged set is not resolved
  again when Agent Runs land, a tick resolves its bound Issues once, where
  every tick used to resolve them twice
  ([#304](https://github.com/ned2/dashpot/issues/304)).
- **GitHub observations can be up to a minute old.** A Query Page's
  freshness is its status, not its age, so a page from the previous GitHub
  tick still reads as fresh. `r` refreshes it on demand.
- **"Refresh Period" joins the domain language.** A refresh of one kind of
  work is no longer a refresh of the whole dashboard.

## Considered options

- **Keep one period and raise its default.** Agent Sessions would take a
  minute to appear or change, and that is the dashboard's reason to exist.
- **Name the second period after queries (`query_refresh_seconds`).** A Local
  Markdown Issue Source's queries do not follow it, so the name would promise
  more than it paces. The period exists because GitHub meters its requests.
- **Resolve bound Issues on every Agent Runs landing.** That ties resolution
  to the local period again, which spends GitHub points every 15 seconds.
