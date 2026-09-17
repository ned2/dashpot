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

The target is CPython 3.12–3.14 (raised from a 3.11 floor on 2026-09-18, before
publication, by [#222](https://github.com/ned2/dashpot/issues/222), so the
code can use Python 3.12's generic syntax), Linux x86-64 and Apple Silicon
macOS, with both
Codex and Claude Code. CI covers both Python endpoints on both platforms,
intermediate versions on Linux, and maintained Git 2.39.x from Debian 12 as
the minimum compatibility baseline. gh 2.100.0
is the first release's tested baseline for GitHub-backed Projects; it is not
needed for Local Issue Markdown. Exact host/harness evidence is a publication
gate, recorded in [Issue #5](https://github.com/ned2/dashpot/issues/5), including
the macOS checklist consolidated from #4. These targets do not claim
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

## Git baseline clarification

Before publication, [Issue #150](https://github.com/ned2/dashpot/issues/150)
raises the proposed Git minimum from 2.38 to 2.39 with current vendor patches.
The compatibility job installs Debian 12's maintained package and runs the full
suite, replacing the upstream 2.38.0 source build. This follows a concrete
vendor-supported environment and removes compilation from each CI run; it does
not establish compatibility with unpatched upstream 2.39.0 or promise upstream
maintenance for the whole Git 2.x major version. The
[support policy](../installation.md#supported-environments) records when to
revisit this baseline. Other release targets and interface guarantees stand.
