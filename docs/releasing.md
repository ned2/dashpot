---
status: living
date: 2026-09-11
---

# Release Dashpot

Publication is an explicit operator action after acceptance. Implementation of
this workflow is not permission to publish. The release policy is
[ADR 0034](adr/0034-publish-an-alpha-with-patch-compatible-interfaces.md).

## One-time publisher setup

The project owner performs the account steps below. No long-lived PyPI token is
stored in GitHub or a checkout.

1. Confirm ownership and eligibility of the `dashpot` project name on PyPI and
   TestPyPI. A missing public project page does not establish name availability.
2. Create GitHub environments named `pypi` and `testpypi` in `ned2/dashpot`.
   Require reviewer approval for each. Restrict `pypi` deployments to version
   tags and `testpypi` to `main`. Protect release tags against replacement.
3. In each package index account, configure a pending Trusted Publisher with
   project `dashpot`, owner `ned2`, repository `dashpot`, workflow filename
   `release.yml`, and the matching environment name. Pending publishers do not
   reserve names. The first successful upload creates the project.
4. Verify the environment protections before dispatching a publication. They
   are account configuration, not settings the workflow can create safely on
   the operator's behalf.

See [PyPI's pending-publisher instructions](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publisher fields](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
The [publishing action](https://github.com/pypa/gh-action-pypi-publish) generates
attestations using the same OIDC identity. Only its top-level publish jobs have
`id-token: write`; reusable CI has no publishing authority.

## Prepare a candidate

- Confirm the release scope, supported environments, and all outstanding
  acceptance evidence in [#5](https://github.com/ned2/dashpot/issues/5).
- Keep `pyproject.toml`'s version, `ISSUE_WORK_SKILL_VERSION` in
  [integrate.py](../src/dashpot/integrate.py), and the two version occurrences in
  [the bundled skill](../src/dashpot/skills/dashpot-issue-work/SKILL.md) aligned.
  A version or dependency change requiring `uv.lock` is its own explicitly
  scoped task; do not relock or upgrade dependencies incidentally.
- Write the matching `## X.Y.Z` changelog entry and update support evidence.
  Before tagging, remove the “not yet published” qualification in the changelog
  and installation guide and set the intended publication date.
- Land the reviewed preparation on `main` through the repository's normal
  workflow. Do not close #5 just because preparation has landed.

Run locally in the assigned checkout:

```bash
uv sync --locked --group dev
uv run pre-commit run --all-files
uv run pytest -q
uv build --no-sources
uv run python scripts/check_distributions.py dist
uvx --from twine==7.0.0 twine check --strict dist/*
uv run python scripts/smoke_install.py dist/*.whl dist/*.tar.gz
```

The archive check expects exactly one wheel and one source distribution for
the declared version. Use a fresh output directory if `dist` contains other
versions. Twine is a separately pinned release tool, not an application or
development dependency. [README-pypi.md](../README-pypi.md) is the compact PyPI
description; its links are absolute so they work on the package index. Preview
that page after TestPyPI publication as well as checking metadata locally.

CI runs the source suite on both endpoint Python versions for Ubuntu/macOS,
the intermediate Python versions on Ubuntu, and Git 2.38. The build job creates
the source distribution and its wheel with `uv build --no-sources`, checks
metadata, and uploads one `distributions` artifact containing:

- `dist/`: the two package files;
- `SHA256SUMS`: hashes of those files;
- `release-notes.md`: the selected changelog entry;
- `build.json`: source commit/ref, workflow run, Python/platform, and uv version.

Installed-artifact jobs download those files, verify the hashes, and install
each independently. They run outside the source checkout with fresh runtime
dependency resolution, exercise a Local Issue Markdown Project without gh,
open the TUI at two sizes, and execute both hook publishers from an environment
whose path contains spaces. Unrelated harness settings survive install/remove.
These tests do not replace real-host acceptance.

## Host acceptance

Record the candidate commit and artifact hashes with every result, plus OS
version, architecture, Python, Git, gh, terminal, Codex, and Claude Code versions.
Final publication requires passing evidence for every claimed combination.
Record all host evidence in [#5](https://github.com/ned2/dashpot/issues/5).
The macOS checklist was consolidated from #4 and runs on `omar`; install the
locked development environment there and run the complete test suite and
package build as well as the installed-candidate checks below. Verify BSD
`ps -o` process identity against a live Codex Agent Session.

- [ ] Install the candidate through `uv tool install /absolute/path/to/wheel`;
  verify `dashpot --version` and `--help` outside the Dashpot source checkout.
- [ ] Collect a real GitHub-backed Project headlessly and interactively. Confirm
  Issue, Pull Request, and Repository freshness and inspect Diagnostics.
- [ ] Collect Local Issue Markdown without gh. Exercise missing Git and missing
  or unauthenticated gh; verify the actionable failure rather than empty data.
- [ ] Verify main/linked Worktree configuration discovery and ignored state
  cleanliness. Exercise Branch integration with Git 2.38 or the validated CI leg.
- [ ] Open compact and wide terminals; navigate Issues, Pull Requests, Legend,
  and configuration controls, then quit cleanly.
- [ ] For each supported harness, install and diagnose integration, verify hook
  trust and the live process adapter, and start/switch/stop Issue work from an
  already-running Agent Session.
- [ ] Verify running/waiting lifecycle, normal exit, killed-session recovery,
  linked Worktree routing, and the documented relocation/resume procedure.
- [ ] Reinstall a candidate in another temporary tool location and rerun
  integration; confirm repaired publisher paths and matching managed skills.
  Remove integration and verify unrelated hooks remain.

The initial host baselines to validate are Codex 0.154.0 and Claude Code
2.1.261. Record a newer tested version if the host has moved on. Failures in a
claimed contract block publication until fixed or the supported surface is
explicitly narrowed and the docs/metadata updated. A newly filed follow-up
Issue does not by itself waive acceptance.

## Rehearse

After this workflow is on the default Branch, run a verification-only rehearsal:

```bash
gh workflow run release.yml --ref main -f candidate-tag=v0.1.0
```

Manual dispatch verifies the selected revision belongs to `main` and matches
the candidate version. It runs the same CI workflow as a tag release. It never
publishes to production. After separate authorization, request TestPyPI upload:

```bash
gh workflow run release.yml --ref main -f candidate-tag=v0.1.0 -F publish-testpypi=true
```

Review the `testpypi` environment approval, watch the run, and inspect the
attestations and rendered package page. Download the exact wheel from that
TestPyPI release and compare its SHA-256 with the workflow artifact before
installing it in a fresh environment with dependencies from production PyPI.
The same smoke script accepts a downloaded local wheel. TestPyPI has a separate,
incomplete dependency inventory; do not make both indexes candidates for every
dependency. See [TestPyPI guidance](https://packaging.python.org/en/latest/guides/using-testpypi/).
Record the successful download/install evidence in #5. Changed candidate bytes
cannot overwrite a TestPyPI filename; use a new explicitly scoped candidate
version when another upload is necessary.

## Publish

After the host checklist and rehearsal pass, obtain explicit publication
authorization. From the verified `main` commit, the operator creates and pushes
one tag:

```bash
git tag -a v0.1.0 -m 'Dashpot 0.1.0'
git push origin refs/tags/v0.1.0
```

The workflow validates the tag/version and main ancestry, runs all required CI
jobs, then waits for `pypi` environment approval. Check the exact commit and
acceptance evidence before approving. The publisher downloads and verifies the
same artifact that passed installation tests; it does not rebuild. In-flight
release runs are not cancelled by later pushes. After PyPI succeeds, a separate
job creates the GitHub Release using the same archives, checksums, build context,
and release notes. The GitHub Release is informational, not another trigger.

Verify `uv tool install --python 3.14 dashpot` from production PyPI in a fresh
tool environment. Confirm the version, help, headless and interactive collection,
both public files, their hashes, and their provenance links. Record the public
installation evidence and close #5 only then.

## Recover an interrupted release

Download and preserve the original workflow's `distributions` artifact before
its 30-day retention expires. Run `sha256sum -c SHA256SUMS` from its root (`shasum
-a 256 -c SHA256SUMS` on macOS). Inspect the failing job and compare index file
hashes with these exact files before doing anything else.

- **Nothing uploaded:** fix account/configuration failures and rerun failed
  jobs using the original verified artifacts. Source changes require a new
  candidate and all gates again.
- **Only some files uploaded:** compare every existing index filename and hash
  with the originals. A mismatch stops recovery; publish corrected code as a
  new version. For matching partial uploads, the operator can approve a narrowly
  reviewed recovery workflow using the same `release.yml` publisher identity:
  download the original run's artifacts, verify hashes, put only missing files
  in the upload directory, and use the same attesting publish action. Keep
  environment approval and OIDC permissions. Do not blindly rerun a full upload
  or enable `skip-existing` to hide mismatched bytes.
- **PyPI succeeded, GitHub Release failed:** verify both PyPI hashes, then rerun
  only the GitHub Release job. If a Release was already created, inspect it and
  attach only missing assets from the original artifact; do not publish again.
- **A released version is defective:** document the problem, consider yanking
  that version on PyPI, and prepare a new version. Do not move an existing tag
  or delete files expecting to reuse their names.

[PyPI filenames cannot be reused](https://pypi.org/help/#file-name-reuse), even
after deletion. Recovery must preserve the relationship between tested bytes,
published bytes, and provenance.
