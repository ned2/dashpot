---
status: superseded
date: 2026-09-16
superseded-by: themes.md, claim-inventory.md
---

# Thematic analysis: plan

A plan for clustering the ideas across the whole corpus and finding
themes it is not yet tracking. It runs before the analysis's candidate
stage so that candidates are drawn from what the corpus contains rather
than from the frame it was collected under. Executed 2026-09-16: its
results are in [themes.md](themes.md) and its claim inventory in
[claim-inventory.md](claim-inventory.md), and the departures from the
plan as written are recorded in the themes note's method section.

Revised 2026-09-16 after an independent review of the first draft; the
changes are noted where they apply.

## The problem it is designed around

The corpus carries a frame: the three themes in the [index](README.md)
(cognitive debt; the friction that keeps understanding; the work rather
than the session), the three axes of the [synthesis](synthesis.md#the-map)
(where friction lives; what it demands; how it is enforced), and its lists
of [tensions](synthesis.md#tensions-the-sources-state) and
[gaps](synthesis.md#gaps-every-pass-left). A pass that reads the notes
through that frame will find the frame. Emergent themes are, by
definition, the ones the frame does not name — and the ones worth finding
are *cross-cutting*: each of their members fits some cell of the frame,
which is why the frame never named the whole. So the method separates
extraction from clustering, blinds extraction and most of the clustering
to the frame, replicates the blind runs so a stable grouping can be told
from one agent's reading, and defines an emergent theme as a blind group
whose members the frame *scatters* rather than as a group the frame cannot
place at all.

The inputs are the 27 research notes. The index, the synthesis, the
analysis, and this plan are excluded from extraction and from the link
graph's edge sources: they are the frame, not the corpus.

## Step 0: the link graph (mechanical, no agents)

The notes cite one another by section — the gap and Phase C notes end in
mapping tables that are a citation graph waiting to be drawn. Parse every
in-repo link between research notes into a directed graph of sections and
report: link communities (dense clusters of mutually citing sections);
sections cited by many notes (the corpus's load-bearing findings); and
sections cited by none. Two graphs are kept: one with all edges, one
without the edges from mapping tables, since the mapping tables make the
note-level graph nearly complete and hide which connections the bodies
drew unprompted. This costs nothing and is an annotation the clusterings
are read against, not a clustering in its own right.

## Step 1: the claim inventory

Decompose every research note into atomic **idea cards**. One card is one
claim, mechanism, definition, practice, tool, policy, argument,
measurement, or substantive dead end. Six extractor agents, each given
four or five notes as scratchpad copies of the bodies — dead-end sections
and mapping tables included; reference lists excluded — and instructed
not to read the repository, so that neither the frame nor this plan is
available to them. Extractors extract; they do not group, rank, or
synthesise.

**Calibration first (added on review).** Before dispatch, all six
extractors extract the same short note
(`chat-centric-agents-vs-team-sdlc.md`). The six results are compared
for count and granularity; the rules below are tightened until the six
agree to within a factor of about 1.5; only then is the corpus dispatched.
Without this, the notes extracted finely would dominate every clustering.

Card schema, one card per list item in `claim-inventory.md`, one `##`
section per note (a list, not a table: two thousand rows with a link each
is unreadable as a table, and a list is still anchor-checkable):

| Field | Content |
| --- | --- |
| `id` | `<note-code>:<n>` — the note's opaque code (N01–N27, assigned in the inventory's key) and a number in document order |
| `claim` | One sentence in the note's own terms; at most forty words, sixty for a `measurement` |
| `figures` | The numbers in the claim, verbatim, with their units and conditions; empty if none |
| `kind` | finding / mechanism / definition / practice / tool / policy / argument / measurement / dead-end |
| `evidence` | C causal / M measured / Q qualitative / T testimonial / A argument / — none, as the note states it |
| `unit` | what the claim is about: hunk, file, change, PR, module, repository, session, person, team, organisation |
| `where` | where in the work the note places it, in the note's own words; free text, normalised after clustering, never a fixed vocabulary handed to the extractor |
| `actor` | person / agent / team / tool / — |
| `source` | terminal citation in short form (author year, or product and page) |
| `anchor` | relative link to the note section the card was read from |
| `counterpart` | `none` when the card comes from a mapping-table row saying no other note covers it; otherwise empty |
| `restates` | the id of an earlier card in the same note that this one restates; otherwise empty |

The `counterpart` and `restates` fields were added on review. A "no
counterpart" row is not a dead end: it is the note's claim that the idea
is new to the corpus, which is the strongest in-corpus signal of an
emergent idea and must not be conflated with a literature absence. And
every note restates itself — the Finding section restates the body, the
summary tables restate the sections, the mapping tables restate both —
so restatements are recorded and dropped from the clustering export
rather than triplicating a claim and inflating its group.

Extraction rules:

- Every body section yields at least one card; the Finding section yields
  cards only for claims stated nowhere else in the note.
- A catalogue entry (a tool, a product, a policy) yields one `tool` or
  `policy` card carrying name, mechanism, trigger, and evidence status.
- A table row with a number yields its own `measurement` card.
- A claim the note marks `(corrected …)` or `(qualified …)` is carried in
  its corrected form, with the marker in `figures`.
- A substantive dead end ("no source measures reviewer-hours per PR")
  yields a `dead-end` card; a procedural one (a blocked page, a search
  budget) yields no card.
- A claim stated in two notes yields two cards; the duplication across
  notes is data — it is how cross-note connections are found.

Expect 1,800–2,500 cards: the landscape sweep alone has 93 catalogue
entries, and the evidence note has a dozen study entries with several
claims each plus an eleven-row table.

**Verification (revised on review).** One agent takes a stratified sample
— three cards from every note, `measurement` cards oversampled, about
eighty in all — opens each anchor, and checks the claim and its figures
against the section. Two or more errors in a note's sample send that note
back for re-extraction; single errors are corrected in place. The same
agent then takes ten random body sections and checks recall: every claim
in the section has a card. A recall failure in a section sends its note
back.

## Step 2: the clusterings

Each clusterer receives the clustering export: every card's `id`,
`claim`, `figures`, `kind`, and `evidence`, with the note code but no
slug, in shuffled order, restatements dropped. The slug and document
order were removed on review because a slug such as
`track-hand-off-checks` is the where-axis in plain text, and cards
arriving grouped by note cluster by note.

The export is 125–175k tokens. A clusterer is asked for roughly fifteen
to forty groups of five to eighty cards, a card allowed in at most two
groups, and writes its result as a JSON file to the scratchpad, where a
local script checks that every id is assigned or explicitly unassigned
and that no id appears more than twice; the agent iterates until coverage
is at least 98%. If a single agent cannot hold the export, the fallback is
to split it into halves by a random cut, cluster each, and have the same
agent merge the two group lists — never a sample-then-label pass, whose
first pass would become a frame.

1. **Blind, by mechanism — two independent runs.** No frame supplied.
   Group cards by *what causes what*: cards that describe the same causal
   story, from any note, go together. Name each group by the mechanism.
2. **Blind, by tension — two independent runs.** No frame supplied.
   Group cards by *what trades against what*: cards on either side of the
   same trade-off go together. Name each group by the tension.
3. **Framed: placement of every card.** The frame supplied in full: the
   three index themes, the three axes with their values, the synthesis's
   tensions and gaps. Place every card — one where-value, one demand, one
   enforcement, and any tension or gap that applies, or `none` for each —
   and return the placement as a column of the inventory. The residue (no
   placement at all) is grouped by whatever it has in common and reported,
   but it is the weaker signal: a cross-cutting theme leaves no residue.
4. **Mechanical.** TF-IDF over card claims and agglomerative clustering
   with the cut chosen by silhouette, run twice — once as is, once with the
   frame's vocabulary (hand-off, review, gate, friction, session, and the
   axis values) as stop words — in a scratchpad environment, not the
   project lockfile. Its use is two reports: which blind groups are
   lexically coherent and which are held together by meaning alone; and
   pairs of cards with high lexical similarity whose notes have no link
   path in the Step 0 graph without mapping-table edges — connections
   nobody drew.

The two blind lenses are chosen because neither coincides with the axes:
the axes place friction (where, what, how enforced); the blind runs ask
about causation and trade-off, which cut across placement. The replicate
of each lens was added on review: without it a stable theme cannot be
told from one agent's reading. The tension lens will rediscover much of
the synthesis's tension list; that is confirmation, and is recorded as
such rather than counted as a discovery.

Five clustering agents; the mechanical runs are the session's scripts.

## Step 3: reconciliation

Revised on review: the first draft counted votes across the four
clusterings, which is unsound — the lenses answer different questions, so
a mechanism group and a tension group with the same members would be a
coincidence, and a framed run that returns residue can never confirm a
group. Instead, groups are matched pairwise under a stated rule, and
robustness and emergence are separate questions.

**Matching.** Two groups match when their overlap coefficient
— |A ∩ B| / min(|A|, |B|) — is at least 0.6 and both have at least five
cards spanning at least three notes. The script also reports the adjusted
Rand index and normalised mutual information between the two runs of each
lens, so the write-up states how far the replicates agree at all before
any group is trusted.

**Robust.** A group is robust when it matches between the two runs of its
lens. A group matched across lenses as well (a mechanism group that is
also a tension group) is noted, but cross-lens agreement is
triangulation, not a requirement.

**Emergent.** A robust group is emergent when the framed run scatters its
members: their placements cover at least four where-values, or at least
three tensions, or at least three gaps, and the group as a whole matches
no single index theme, axis value, listed tension, or listed gap. A robust
group the framed run concentrates in one cell or one tension confirms the
frame and is recorded as confirmation. A robust group whose members come
from one phase only (all Phase C, all tracks) is that phase's theme, not
the corpus's, and is marked so.

**Connections.** A group found in one run only, or a matched group with
fewer than three notes, is a connection — a link between ideas, not a
theme — and is listed with the mechanical run's undrawn-connection pairs.

**Negative cases (added on review).** For each emergent theme, one agent
searches the full inventory for cards that contradict it or mark where it
fails to hold, and the theme is written up with its counter-cards.

**For each emergent theme:** name it; list its member cards by note; state
the evidence level of its best member; list the counter-cards; and state
what it would change — a new axis or axis value, a new row in the
analysis's lifecycle map, a new principle, or a new research gap.

## Held-out priors

Cross-cutting patterns the session already suspects. They are held out of
every agent prompt — the extractors and clusterers cannot read this note —
and matched afterwards. On review, the matching was moved off the session:
the holder of the priors should not be the one judging whether they were
found. An agent given the clusterings and the list below, but not the
session's reading of them, matches each prior under one rule — *found
independently* when a robust blind group contains at least three of the
prior's named exemplars from at least two notes; *found when looked for*
when the exemplars are in the inventory but no robust group holds them
together; *not found* when the exemplars are not in the inventory. The
session reviews the matching rather than originating it.

- Grain or batch size as one variable under five names: step grain in the
  loop, change size at review, WIP count, compaction size, quiz
  granularity.
- The receiver's questions as the mechanism of model reconstruction —
  teach-back, shift handover, Fagan inspection, the comprehension question
  catalogues, Socratic follow-up — against summaries and artifacts.
- Recency as the locator of knowledge — the Line 10 rule, degree of
  knowledge, circumstantial responsibility — and an Agent Run as the case
  where the last toucher is not a person.
- Anticipation: awareness excludes the future; generate-before-seeing,
  plan approval, and the handover stance all demand it.
- Self-report diverging from observation: TMS r = .77 self-reported against
  .38 observed; awareness rated unimportant because easily obtained; the
  illusion of competence; survey-based delivery metrics.
- Two-sided opacity: "strong, silent" automation and inaccurate agent
  self-report on one side, the illusion of competence on the other.
- The amnesiac discourse: five precedents restated without citation, which
  is the corpus's own subject at the level of the field.

## Deliverables

- `claim-inventory.md` (status: research, dated) — the note key, then the
  cards as a list under one `##` section per note, each carrying its
  framed placement once Step 2.3 has run; a durable asset the candidate
  stage can cite by card id.
- `themes.md` (status: research, dated) — the link-graph baseline; the
  replicate agreement figures; the robust groups, sorted into
  confirmations of the frame and emergent themes, each emergent theme with
  members, counter-cards, and what it changes; the connections; the
  held-out priors and their fate; and a short "what this changes" section
  addressed to the [analysis](analysis.md), which is then revised in its
  own commit.
- This note marked superseded by both.

## Sequence and cost

| Step | Who | Runs |
| --- | --- | --- |
| 0 Link graph | session, local script | before extraction |
| 1c Calibration | six agents, one short note each | before extraction |
| 1 Extraction | six agents, in parallel | one batch |
| 1v Verification | one agent | after extraction |
| 2.1–2.3 Clustering | five agents, in parallel | after verification |
| 2.4 Mechanical | session, local script | alongside 2.1–2.3 |
| 3 Matching and priors | local script, then one agent | after clustering |
| 3n Negative cases | one agent | after emergent themes are named |
| 3 Reconciliation and write-up | session | last |

About fifteen agent dispatches (the six calibration runs are short), no
web access needed, so it runs in one session. Commit points, all the
session's: after Step 1v (inventory), after Step 3 (themes and this
note's status), and the analysis revision separately.
