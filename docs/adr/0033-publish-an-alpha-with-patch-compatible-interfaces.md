---
status: accepted
date: 2026-09-11
---

# Publish an alpha with patch-compatible interfaces

Dashpot's first release is `0.1.0`, with the Alpha development-status classifier.
It establishes the first compatibility baseline; there are no existing external
users or unreleased-format migration obligations. Within `0.1.x`, documented
command behavior, JSON key sets and semantics, Local Issue Markdown, and
`.dashpot/config.json` remain compatible. Breaking changes require a new minor
version and explicit release notes. An added field rejected by a strict reader
is a compatibility change too. Python internals and exact terminal layout are
not supported extension interfaces.

This chooses usable, ordinary tool installation over requiring an explicit
prerelease selector, and a narrow patch-release promise over either claiming
1.0 stability or allowing silent breaking patch upgrades. It preserves the
existing [JSON contract](../../src/dashpot/serialization.py). Work Store records
remain private, versioned persistence: future supported upgrades preserve
active Agent Runs or document a procedure that first ends them. Ignored runtime
state is not automatically disposable while it contains active declared work.

## Distribution and support

Ship a wheel and source distribution through PyPI. Recommend `uv tool install`
so application dependencies are isolated; retain the exact Textual pin because
the UI depends on tested DataTable and layout behavior. Other dependency bounds
remain unchanged. Source tests use the lockfile, while installed-artifact tests
resolve the runtime dependencies an application user receives.

The target is CPython 3.11–3.14, Linux x86-64 and Apple Silicon macOS, with both
Codex and Claude Code. CI covers both Python endpoints on both platforms,
intermediate versions on Linux, and Git 2.38 as the proposed minimum. gh 2.100.0
is the first release's tested baseline for GitHub-backed Projects; it is not
needed for Local Issue Markdown. Exact host/harness evidence is a publication
gate, recorded in [Issue #4](https://github.com/ned2/dashpot/issues/4) and
[Issue #5](https://github.com/ned2/dashpot/issues/5). These targets do not claim
unperformed host validation. See [installation](../installation.md) and
[the release checklist](../releasing.md#host-acceptance).

## Publication

One `vMAJOR.MINOR.PATCH` tag push triggers production publication. The revision
must belong to `main`, and its version and changelog must agree with the tag.
Build the source distribution and its wheel once, test those files, then pass
them to a separate top-level publishing job. PyPI Trusted Publishing provides
short-lived credentials; the PyPA publishing action generates attestations.
A protected GitHub environment carries the operator's final release approval.
Manual dispatch performs verification, with separately approved TestPyPI
publication available for rehearsal; it cannot publish to production.

Published files are immutable. Retain archives, checksums, release notes, and
build context for recovery rather than rebuilding a partially published version.
This costs an explicit publisher setup and a separate artifact handoff, but
ties the published bytes to the ones that passed the release gates.
