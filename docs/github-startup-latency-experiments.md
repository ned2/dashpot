---
status: research
date: 2026-09-06
---

# First-load GitHub observation latency

Experiments for [Issue 138](https://github.com/ned2/dashpot/issues/138) selected
three changes to Snapshot Seed startup: fold the settled-seed probe into the
mandatory later Issue delta; confirm a pending Pull Request prefix before
Reconciliation so its closing targets share the complete identity reads; and
fold that pending probe into the first prefix page.
[ADR 0030](adr/0030-combine-startup-evidence-with-mandatory-reads.md) records the
selected order and its trust boundaries. Other experiments below did not clear
their adoption gates and do not change production behavior.

## Method and limits

The baseline is `a0fd9e6`. All measurements used Python 3.14.7, Textual 8.2.8,
the same checkout, GitHub authentication, 160×50 headless dashboard, and the
same frozen seed for `ned2/dashpot` (94 Issues and 44 all-state Pull Requests).
The timestamp of the measurement session was September 5 UTC / September 6
Australia/Melbourne. Each sample ran in a separate Python process with its own
temporary Work Store-independent Snapshot Seed store. GitHub was only read;
synthetic future cursors and pending candidates changed those temporary inputs.
No live Issues or Pull Requests were created, edited, or deleted for this work.

Each comparison alternated baseline and experiment, reversing their order in
the following pair. The first three comparisons changed one variable at a
time, four pairs each. The final comparison used another four pairs for each
of five startup states. All 64 retained dashboard samples completed with 94
fresh Issues. There were no concurrent latency experiments; no sample was
discarded for being slow. Minima and maxima below describe the observed tails;
four samples per state/variant cannot estimate a reliable population p95.

The retained [profiling command](../scripts/profile_github_startup.py) builds the
real coordinator, validates the Repository Anchor live, and runs the real
headless Textual event loop. It measures collector setup, `on_ready`, each
observation, publication, and the first actual Issue table row. Its GitHub
runner records operation names, request start/end times, response bytes,
returned connection-entry counts (including nested entries), rate-limit facts,
and exit status. Entry counts are returned payload counts, not GitHub's
theoretical schema-expansion node limit. Elapsed process times start inside
the script before Dashpot imports; OS process launch and `uv` startup are
outside that measurement.

The earlier raw samples record the first populated row mapping immediately
after the real table update, with 1 ms polling. The retained command additionally
records publication calls and checks the table's actual `row_count`. It avoids
overriding a Textual lifecycle handler and calling its parent, which would
dispatch the inherited handler twice and produce extra refreshes. Preparatory
harness-development runs are not included in the comparison evidence.

```bash
# Run inside a configured GitHub-backed checkout. These requests use live GitHub.
uv run python scripts/profile_github_startup.py --state no-seed \
  --output-seed /tmp/dashpot-startup-seed.json
uv run python scripts/profile_github_startup.py --ref a0fd9e6 \
  --state settled --seed /tmp/dashpot-startup-seed.json
uv run python scripts/profile_github_startup.py --ref current \
  --state settled --seed /tmp/dashpot-startup-seed.json
```

Repeat in alternating order, also using `pending`, `future-issue`, `future-pr`,
and `no-seed`. Each seeded invocation copies the supplied file into an isolated
temporary store. `pending` retains the previous live settled timestamp as the
candidate and clears the settled mark, forcing an inclusive all-state prefix.
`future-pr` places both persisted Pull Request marks in 2099.

The network-free [startup tests](../tests/test_github_startup.py) assign 600 ms
to each serial request or concurrent identity wave, pin the exact request
order, and require all four identity requests to be in flight together. For
94 Issues, settled startup falls from three serial stages/six requests to two
stages/five requests (1.8 → 1.2 simulated seconds). A two-page pending prefix
falls from six stages/nine requests to four stages/seven requests (3.6 → 2.4
simulated seconds). Actual identity requests are slower than a small probe,
so live savings differ from the uniform-latency model.

## Individual changes

Times are seconds from `on_ready` to the first Issue row.

| Experiment | Before median (min–max) | After median (min–max) | Issue requests | Decision |
| --- | --- | --- | --- | --- |
| 3: prefix before full identity Reconciliation | 5.435 (5.027–5.764) | 3.677 (3.635–4.359) | 9 → 8 | Adopt |
| 4: probe beside first prefix page, after experiment 3 | 3.884 (3.774–4.028) | 3.341 (3.123–3.487) | 8 → 7 | Adopt |
| 1: probe beside settled-seed delta | 2.824 (2.457–3.338) | 2.083 (1.848–2.357) | 6 → 5 | Adopt |

Raw evidence: [experiment 3](measurements/issue-138-experiment3.json),
[experiment 4](measurements/issue-138-experiment4.json),
[experiment 1](measurements/issue-138-experiment1.json). In these files `current`
means the one additional change under test at that stage. The temporary source
paths in later comparisons name frozen versions of the preceding experiment.

## Final comparison

| Startup state | Baseline median (min–max), s | Selected changes median (min–max), s | Issue requests / GraphQL points |
| --- | --- | --- | --- |
| No Snapshot Seed | 2.796 (2.271–3.131) | 2.344 (2.095–3.024) | 1 / 6 → 1 / 6 |
| Settled Snapshot Seed | 2.789 (2.666–3.239) | 2.308 (1.919–2.710) | 6 / 6 → 5 / 5 |
| Pending candidate across restart | 5.303 (4.753–6.069) | 3.325 (3.139–3.773) | 9 / 9 → 7 / 7 |
| Future Issue cursor | 2.587 (2.488–3.460) | 2.573 (2.393–2.798) | 6 / 6 → 6 / 6 |
| Future settled/candidate Pull Request cursors | 5.220 (5.007–5.336) | 3.299 (3.289–3.800) | 9 / 9 → 7 / 7 |

The no-seed path is identical in production and serves as a variance control:
its apparent median gain is not attributed to these changes. The future Issue
cursor path deliberately spends its saved request on a corrected inclusive
delta, so no latency gain is claimed there either. Settled-seed gains repeated
in both windows, although the final window's individual distributions overlap.
Pending-candidate distributions were separated in both individual-change
windows and the final comparison.

In the final comparison, median time from script entry to first content was
3.557 → 3.088 s for settled seeds and 6.102 → 4.118 s for pending candidates.
Repository resolution still took approximately 0.50–0.52 s. Publication plus
row population was approximately 6–8 ms; it does not explain the savings.

Settled startup returned 361,881 → 361,730 Issue-response bytes and 389 → 389
connection entries. Pending startup returned 455,707 → 370,476 bytes and
540 → 453 entries by eliminating the redundant 21-Issue affected-target batch
and standalone probe. Every Issue GraphQL request cost one point except the
unchanged no-seed sweep, which cost six. The separate Pull Request pane spent
one additional GraphQL request/point, and Repository Identity validation spent
one separate REST request in every sample.
[Complete final samples](measurements/issue-138-final.json).

## Other experiments and adoption decisions

### 2. Repository Identity validation

An existing startup delta can carry a second top-level
`referenceProof: repository(owner: "ned2", name: "dashpot") { id nameWithOwner }`
beside its identity-rooted observation. Four alternating pairs confirmed the
expected opaque identity; both query shapes cost one point. Median query time
was 0.658 s without the proof and 0.628 s with it, with 75 additional bytes in
the decoded/re-encoded response. The difference is within request variance;
the useful potential saving is the separate roughly 0.5 s REST round trip.
[Query evidence](measurements/issue-138-identity.json).

Do not adopt this consolidation or pipelining yet. The current resolver validates
every configured Repository Anchor before grouping valid anchors and deciding
Workspace scope. Moving its proof into one Issue Source response would couple
the success of otherwise independent sources to that response and would not
establish the other anchors' proofs. Correct overlap needs a separate
all-anchor publication barrier, including failure/discard and scope-diagnostic
equivalence. This experiment establishes query feasibility and the available
latency ceiling; it does not establish that lifecycle contract. No optimistic
Project publication or skipped identity validation is introduced.

### 5. Pull Request page width

The exact combined startup prefix query was issued at widths 24, 48, 50, and
100 against `ned2/dashpot`, `cli/cli`, and `Textualize/textual`. Each response's
`closingIssuesReferences` nodes and `pageInfo` were compared with one individual
Pull Request point query, including duplicate appearances across widths. There
were 244 distinct point queries, at most four in flight, and no mismatches.

| Repository | Width 24 time | Width 48 time | Width 50 time | Width 100 time | Targets returned at width 100 |
| --- | --- | --- | --- | --- | --- |
| ned2/dashpot | 0.713 s | 0.710 s | 0.755 s | 0.858 s | 21 across 44 Pull Requests |
| cli/cli | 0.691 s | 0.901 s | 0.897 s | 1.098 s | 61 across 100 Pull Requests |
| Textualize/textual | 0.804 s | 0.808 s | 0.806 s | 0.923 s | 66 across 100 Pull Requests |

Each request cost one point. The largest measured decoded/re-encoded response
was 20,756 bytes. Dashpot's 44 Pull Requests fit on one page at every tested
larger width; the other repositories still reported a next page. No secondary
limit was observed during these samples. That is not a stress test or a proof
against silent truncation for high-fanout nested connections: these modest
target sets do not exercise a hundred-plus closing targets on many parents.
Retain width 24 until that additional live completeness and pagination evidence
exists. [Measurements and comparison counts](measurements/issue-138-width.json).

### 6. Start during Textual composition

The measured collector-to-`on_ready` interval is roughly 70–90 ms. Starting
observations during composition can overlap at most that interval and cannot
remove a GitHub dependency stage. Against the measured hundreds of milliseconds
of network variance, this is a small ceiling. Do not introduce a second startup
path and earlier shutdown ownership for this saving. The production lifecycle
continues to start observation at `on_ready`.

### 7. Reuse transport connections

Eight alternating pairs compared the production combined probe through
`gh api graphql` with the same authenticated GraphQL body over one reusable
standard-library `http.client.HTTPSConnection`. Authentication stayed in memory
and was sent only to `api.github.com`. The first reused-transport request was
cold and is retained in the results. Both variants cost one GraphQL point.

The `gh` median was 0.549 s (0.499–0.600); the reusable connection median was
0.429 s (0.404–0.745). After the cold request, reuse ranged from 0.404 to
0.492 s. Reuse therefore looks promising, but the 0.120 s median difference
combines process setup, TLS/DNS reuse, and GitHub/network variance; it does not
isolate server processing. The prototype establishes a potential benefit,
not equivalent authentication discovery, proxy behavior, timeouts, error
classification, rate-limit handling, connection ownership, and concurrent
failure behavior for a replacement gateway. Retain `gh` in production until a
dedicated transport change demonstrates those contracts. No dependency or
lockfile change is needed for the selected ordering changes.
[Transport evidence](measurements/issue-138-transport.json).

### 8. Earlier non-Issue panes

The real loop confirms that Agent Runs complete in milliseconds, Repository
State in roughly 60–80 ms, and the Pull Request pane in roughly 0.5–0.6 s.
Those results could make the dashboard useful before the 2–3 s Issue startup
finishes. The coordinator currently composes its first Project only after all
three source observations exist. Its published model has no pending-source
state: using an empty tuple with `fresh` or treating pending as an observation
failure would misrepresent the source. Keep the composition barrier for this
change. A separate presentation/model change can evaluate an honest pending
state, Agent Run binding deferral, and independent source failure behavior.
This experiment measures the opportunity; it does not claim an implemented
perceived-latency improvement.

## Correctness coverage

The source tests retain the no-seed sweep, startup failure/unavailable and later
last-good behavior, current count disagreement followed by an independently
budgeted fallback sweep, and existing incremental-refresh semantics. Additional
tests pin the shortened request graph and cover:

- the later delta winning equal-timestamp identity reads;
- current closing targets absent from the seed and previous targets losing links;
- deleted and cross-repository targets and newly discovered relationship counterparts;
- both future Pull Request cursors being bounded before choosing a prefix boundary;
- future Issue cursors requiring a corrected delta and empty GitHub dropping a future mark;
- malformed combined probes, wrong Repository Identity, and missing page cursors;
- permission failure at each startup stage leaving the seed private and unchanged;
- each combined request and concurrent identity wave spending the same Refresh Budget.

The empty-repository, deletion/transfer, count-disagreement, and changed-target
cases use deterministic fake GitHub responses. Live mutation of a repository
was unnecessary to exercise these contracts. Nothing in the test suite talks
to GitHub; only the explicit profiling commands do.
