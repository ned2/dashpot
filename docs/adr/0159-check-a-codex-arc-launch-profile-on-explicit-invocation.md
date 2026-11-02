---
status: accepted
date: 2026-11-02
---

# Check a Codex Arc launch profile on explicit invocation

Starting an Arc exposes missing directory grants, gate-cache variables,
Git transport and GitHub authentication one failure at a time.
[Issue #679](https://github.com/ned2/dashpot/issues/679) puts a consolidated
check in Dashpot, so it serves every operator rather than one launcher's
users. [ADR 0008](0008-let-management-commands-mutate-on-explicit-invocation.md)
left launching harnesses outside its boundary. The
[launch qualification](https://github.com/ned2/dashpot/pull/690) now measures
the narrower operation this check needs: on Codex 0.166.0 on Linux,
`codex sandbox --profile` agrees with a fresh session's grants and cache
variables, without starting an Agent Session.

## Decision

Add an explicitly invoked `dashpot preflight codex --profile <name>`
command, separate from integration status and passive observation. It
checks an operator-written profile; it neither writes that profile nor
constructs launch flags. Integration status remains a check of the installed
hooks and skills, without running Codex or contacting a Git remote.

Dashpot resolves the Worktree Root through the existing option, environment,
machine setting and main-checkout default, and resolves the shared Git
directory through Git. Inside the named profile's sandbox it checks:

- write-free `test -w` results for those directories and each gate cache;
- that `UV_CACHE_DIR` and `PRE_COMMIT_HOME` name absolute, writable cache
  directories;
- the selected Git remote's transport, SSH configuration where applicable,
  and `git ls-remote`;
- `gh auth status`, by exit status only.

Each check reports its result and an actionable remedy, in text or JSON.
All failures are collected; any failure makes the command exit non-zero.
A failed probe launch is a failed check, never evidence that provisioning
passes. Commands have bounded waits. Their raw output, profile contents and
credential values are excluded from the report and Event Log. GitHub login
status does not establish Issue/PR write, push or merge permission.

The filesystem probes create no files. Dashpot directly changes no
Repository, profile, credential store, Issue Binding or Cleanup state.
Codex refreshes its helper binaries under `$CODEX_HOME/tmp/arg0-linux/`;
the qualification measured that write. Operator-configured transport and
authentication tools may execute configuration commands and update their
own state within the profile's existing grants: for example SSH's
`Match exec`, known-hosts or control-socket state, and credential-helper
storage. The command's help and report disclose these effects and withhold
their output. It does not rewrite those tools, choose credentials or widen
grants. The ordinary Event Log remains Dashpot's ignored local state.

The maintainer explicitly approved this transitive-write boundary after
review demonstrated an SSH configuration creating a file during `ssh -G`
([decision](https://github.com/ned2/dashpot/issues/679#issuecomment-6576138036)).
Requiring additional filesystem isolation would change the environment
being checked and require its own qualification. This exception permits
the sandbox tool and the operator's configured transport/authentication
programs, rather than starting an Agent Session or provisioning one.

Only a qualified release and platform can report a passing preflight.
The initial boundary is Codex 0.166.0 on Linux. Another release or platform
requires renewed evidence, including the sandbox tool's writes. Tests use
a fake process seam and never launch Codex.

## Limits and alternatives

The result predicts a fresh launch with the checked profile. It cannot
inspect a resumed thread's saved permissions or a managed daemon's
environment, runs no Worker and grants no permission. A resume's profile
pin and the checks inside the session remain authoritative. The profile
is the operator's policy: the command neither replaces its deny rules nor
chooses credential injection, snapshot filtering or approval routing.

An operator launcher may load credentials and call this command. Keeping
all checks in such a launcher was rejected because the bundled skill must
serve other operators. Adding the probes to every integration-status check
was rejected because inspecting an installation should not execute a
harness or contact its Git remote. Generating or rewriting profiles was
rejected because it would let a checker choose the permissions it verifies.
