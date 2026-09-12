---
status: accepted
date: 2026-09-13
---

# Review locally and verify the PR head before integration

Dashpot development requires independent review and successful CI before
integration into remote `main`. The former push-then-watch sequence could
discover failures only after integration; collecting coverage solely in CI
also delayed coverage-informed review until an expensive matrix had run.

The local full-suite gate collects coverage once and associates the report
with the source content and review base. The implementing agent dispatches
independent review with that evidence, resolves findings, and records the
outcome before opening a PR. Content-preserving commits retain review validity;
source changes require refreshed validation and appropriate follow-up review.
Coverage has no percentage threshold and is evidence of execution, not proof
of test assertions. CI coverage remains diagnostic evidence, not a trigger
for another routine review of unchanged code.

PR CI checks the exact signed head commit, verifies that it includes the
event's base, and publishes both identities. One aggregate required check
rejects any unsuccessful prerequisite. Integration verifies that evidence
against the current PR and remote base and performs a fast-forward guarded
by an explicit expected-base lease. The implementing agent holds exclusive
ownership of the remote PR branch during final verification and integration;
without coordination of all writers, integration stops. This process rule
prevents head changes while the server-enforced lease prevents base changes.
The lease alone does not protect the PR head. Existing signatures, linear-history
requirements, and protection against history replacement remain intact.
Removing ordinary main-push CI avoids repeating the same matrix after this
verification. Manual CI and reusable release verification remain available.

Agent review is initially a repository process gate rather than a GitHub
approving review or service attestation. GitHub required checks supply server
enforcement for CI. These mechanisms have distinct evidence and authority;
documentation must not claim settings are installed merely because the
workflow defines a check.

This decision concerns developing Dashpot. It adds no rules to the application
or distributed Issue-work skill about how other Projects develop or integrate
their work. The operational contracts live in the
[local review gate](../../README.md#local-review-gate),
[agent instructions](../../AGENTS.md#independent-review-before-integration),
and [development integration procedure](../development-integration.md).
