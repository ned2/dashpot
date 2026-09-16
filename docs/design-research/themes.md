---
status: research
date: 2026-09-16
---

# Themes across the design research corpus

What the twenty-seven research notes contain when read as one body,
without the frame they were collected under. This note executes the
[thematic analysis plan](thematic-analysis-plan.md) on the
[claim inventory](claim-inventory.md): it reports the link-graph baseline,
the four blind clusterings and how far they agree, the mechanical
clustering, the framed placement of every card, the robust groups sorted
into confirmations of the frame and emergent themes, the connections the
corpus draws or fails to draw, the fate of the held-out priors, and what
all of it changes in the [analysis](analysis.md). Card ids (`N08:41`) are
those of the inventory; the [note key](claim-inventory.md#key) maps a
code to its note.

The frame under test is the one the [synthesis](synthesis.md) and the
analysis fixed: three index themes (T1 cognitive debt, T2 the friction
that keeps understanding, T3 work above the session), three axes (W where
the friction lives, D what it demands, E how it is enforced), twelve
tensions (X1–X12) and seventeen gaps (G1–G17). The inventory lists the
[codes in full](claim-inventory.md#placement-codes); the abbreviations
below are those.

## Summary

- The corpus is one connected graph of 27 notes with a load-bearing core
  (evidence-and-mechanisms, track-measurement,
  unfamiliar-code-and-shared-models) and two Phase C notes that nothing
  cites yet.
- Blind clustering by mechanism replicates moderately (NMI 0.62);
  clustering by tension replicates worse (NMI 0.48). Thirty-five groups
  survive the replicate match. Mechanical clustering finds no lexical
  structure at all (silhouette ≤ 0.012), so every grouping here is a
  reading, not a word count.
- The frame places 95 percent of the cards; the residue is bibliographic
  and procedural. Thirty-one of the 35 robust groups confirm a listed
  axis value, tension, or gap — but eighteen of them draw three quarters or
  more of their core from a single note, so they recover that note's
  structure rather than a convergence across notes.
- Six themes survive a negative-case search that the frame names only
  in pieces: staleness without a trigger, habituation of repeated
  friction, the confidence gap, the question-routing economy, the
  authorship inference, and the instruments' blindness to the debt
  (section 5). Two more candidates are demoted to connections. Of
  seven priors held out before clustering, two were found by the blind
  runs and five were not (section 7).
- What they change in the analysis (section 8): five principles gain a
  clause (the instrument named, the default's decay, the artifact's
  coupling, the answer hidden, the ask as an act), the authorless-code
  lens widens, the map gains a cell and loses a claim, three of the four
  Phase C principles are marked single-note, and the method gains two
  lenses.
- The mechanism lens replicates better than the tension lens because a
  mechanism has one subject and a tension two; the runs that disagreed
  most disagreed about where to cut the same material, not what it
  was.

## 1. The link-graph baseline

Every in-repo link between notes was extracted, once over whole notes
and once over their bodies only (mapping tables and source lists
excluded, since those sections cite by obligation). Both graphs are
connected: no pair of notes is unreachable from another.

**Load-bearing sections** (distinct citing notes, body links): the
AI-specific evidence section of
[evidence-and-mechanisms](evidence-and-mechanisms.md) (7), the proxies
and telemetry section of [track-measurement](track-measurement.md) (6),
and, at five each, the corrections in the
[literature addendum](literature-addendum.md), the team-cognition and
ownership-succession sections of
[unfamiliar-code-and-shared-models](unfamiliar-code-and-shared-models.md),
and the expertise-location section of
[track-durable-model](track-durable-model.md). The three most-cited
notes hold 122 of 371 body links between them.

**Communities.** Louvain on the body graph gives five: the learning and
evidence core (adjacent-literatures, answer-ai-sweep, apprenticeship,
evidence-and-mechanisms, flow-wip-limits, literature-addendum,
track-in-loop-friction); the Phase B product tracks with their sweeps
(solve-it-sweep, track-durable-model, track-rationale-as-artifact,
understanding-bottleneck-talk); the gate and labour cluster (cowan,
discourse-and-tooling-addendum, ownership-and-accountability,
review-capacity, track-hand-off-checks); the measurement and team-model
cluster (expert-finding, landscape-sweep, team-level-measurement,
track-explorable-maps, track-measurement,
unfamiliar-code-and-shared-models); and the coordination cluster
(automation-as-a-team-player, chat-centric-agents, handover,
integration-frequency, workspace-awareness). The greedy-modularity
partition differs only at the margins (landscape-sweep moves to the gate
cluster, flow-wip-limits to the measurement cluster). The communities
are the phases of the research, plus one seam: the coordination cluster
is Phase C, written after the frame, and its notes cite the older core
without being cited by it.

**Uncited and non-citing notes.**
[expert-finding-and-transactive-memory](expert-finding-and-transactive-memory.md)
and
[integration-frequency-and-parallel-branches](integration-frequency-and-parallel-branches.md)
are cited by no other note;
[chat-centric-agents-vs-team-sdlc](chat-centric-agents-vs-team-sdlc.md)
cites none. Section headings without any inbound link are concentrated in
the Phase C notes (apprenticeship 8 of 12, integration-frequency 8 of
11, track-durable-model 7 of 9, track-rationale-as-artifact 7 of 8): the
material the corpus has read least is the material it collected last.

This is the reference the clusterings are measured against. A grouping
that reproduces these communities has found the corpus's own filing
system; a grouping that crosses them has found something the filing
system does not express.

## 2. The claim inventory

The [inventory](claim-inventory.md) holds 3,931 cards extracted blind
from the note bodies (opaque note codes, no access to the repository or
the frame): 871 measurements, 817 findings, 689 arguments, 623 tool
descriptions, 228 dead ends, 207 definitions, 204 practices, 148
mechanisms, 144 policies. By evidence level 263 are causal, 744
measured, 273 qualitative, 899 testimonial, 737 argument, and 1,015
carry none (tool descriptions, definitions, dead ends). Verification on
a stratified sample found no extraction errors and no missed claims in
the ten sections checked for recall. 466 cards restate an earlier card
in the same note and were dropped from the clustering export, leaving
3,465 cards.

Each card in the inventory now carries its framed placement (Step 2.3):
one W, D, and E value or `-`, any number of X and G codes, and a T code.
The placer found a place on some axis or list for 3,308 cards (95
percent). Of the 157 that place nowhere, 150 fall into ten residue
groups — product logistics of Solveit and Answer.AI, the Cowan
bibliography, citation corrections, records seen but not read, sample
descriptors, unreachable pages, notes about the corpus's own structure,
tool inventory metadata — and four are unassigned. Nothing in the
residue is a mechanism. The reviewer's prediction held: the frame does
not fail to place a card by being too narrow, it fails only where a card
is not a claim about the subject.

The placement's own distribution is a first result. W places 2,128 cards
(61 percent); the stages it fills are review and merge (534), inside the
loop (450), hand-off (376), continuous (373), onboarding and team (306)
— and task start (89). The demand axis places 2,061 cards, led by verify
or approve (397) and recall (311), with generate-before-seeing at 82.
The enforcement axis places 1,445, the fewest of the three; 2,020 cards
say nothing about how anything is enforced. Among tensions X5 (artifact
against act, 396), X9 (individual against team, 367) and X1 (speed
against understanding, 350) lead; among gaps G15 (no team-model
instrument, 351) and G10 (the uncited human-factors literature, 270).
The index theme T3 (work above the session) takes 1,348 cards to T1's
865 and T2's 643: the corpus has become a corpus about the team.

## 3. The clusterings and their agreement

Four blind clusterings, two lenses run twice each by agents that saw
only the shuffled export: mechanism-A (40 groups, 93 percent of cards
assigned), mechanism-B (40, 96), tension-A (39, 84), tension-B (39, 94).
Group sizes ran 21–132, medians 78–100.

**Replicate agreement**, on cards assigned in both runs of a lens,
first-group-wins labels: mechanism ARI 0.378, NMI 0.619 (3,177 cards);
tension ARI 0.246, NMI 0.479 (2,757 cards). Both are far above chance
and well short of identity. The mechanism lens replicates better because
a mechanism statement has one subject; a tension statement has two, and
the two runs often chose different second poles for the same cards
(tension-A's "review workload against retention" and tension-B's
"spaced retrieval retention against review time" share a core, but
tension-A's "systematic reading against as-needed navigation" and
"holding the program's theory against working without it" split what
mechanism-B held as one group).

**Reconciliation.** Groups were matched by overlap coefficient
(|A∩B| / min(|A|,|B|)) at 0.6 or above, both groups having at least five
cards from at least three notes. Thirty-five pairs match between the
replicates of a lens (24 mechanism, 11 tension); their cores — the cards
both runs placed together — run from 14 to 102 cards. About sixteen more pairs
match in the 0.40–0.60 band, most of them clearly the same mechanism
cut at a different boundary (confidence inflation, vigilance and
habituation, staleness and drift, asking a colleague against asking AI,
transactive memory); the strict threshold rejects them and section 5
treats them as candidates rather than robust groups.

**The mechanical control.** TF-IDF over the card text, k-means at k = 20
to 80, run twice — once plain and once with the frame's vocabulary added
to the stop words — gives silhouette scores between 0.003 and 0.012.
There is no lexical structure in the cards at any k. The clusters that
form are vocabulary clusters (cards with "et al.", cards with figures in
minutes and hours, cards naming Copilot and pull requests, cards naming
Anki and FSRS), and removing the frame's words changes nothing. The
mechanical run's one useful product is the list of note pairs whose
cards are lexically close but that share no body link, in section 6.

**What the framed placement does to the robust groups.** For each robust
core the placement's W, D, X, and G values were counted. A group is
*concentrated* by a value holding 60 percent or more of its core and
*scattered* when its members spread over four or more W values or three
or more X or G values with none concentrating. Thirty groups are
concentrated by at least one value; three are concentrated by none but
not scattered ("mixed"); one is scattered — and that one, the
explain-back group, is concentrated on the demand axis (D3 explain, 37
of 40), which the dispersion test did not consult. There is no robust
group the frame cannot place. What the frame does is split: the same
robust core often lands on a tension *and* a gap *and* a lifecycle
stage, each holding a fragment.

## 4. Robust groups that confirm the frame

The thirty-two robust groups whose core the placement concentrates on
some value — thirty-one on W, X, or G, one on D. The core count is the
cards both replicates placed together; *top note* is
the share of the core drawn from its largest single note; *phase* is
the research pass that supplied 80 percent or more of the core (A the
first evidence pass, B the product tracks, gap the gap-filling notes,
team the chat-centric note, C the lifecycle-and-team pass), or "mixed".

A top-note share of 75 percent or more means the group recovers one
note's own structure: the replicates agree because the note's sections
are already a cluster, not because several notes converge. Eighteen
groups are of that kind; fifteen of them come from a Phase C or gap
note, and most of the gaps and tensions they confirm were added to the
frame from that same note. They are consistent with the frame; they are
not independent evidence for it.

| Robust group (mechanism unless marked) | Core | Notes | Top note | Phase | Confirms |
| --- | ---: | ---: | --- | --- | --- |
| Concurrent isolated work raises conflict and integration cost | 102 | 5 | N12 91% | C | G16 |
| Provenance links "why" to code only while the record survives and someone renders it | 83 | 10 | N24 64% | mixed | W3, G5 |
| Where a tool stops and what it defaults to decide whether the human engages | 82 | 6 | N22 84% | B | W2, X4, G8 |
| Rationale lives in heads because capture costs the writer and benefits unknown readers | 80 | 10 | N24 61% | mixed | X5 |
| Authorship-based knowledge estimates break when authorship stops implying understanding | 78 | 8 | N15 36% | mixed | X12, G15 |
| Handover transfers a state model plus a stance; summaries lose it, the receiver's questions repair it | 77 | 4 | N11 95% | C | W3, G12 |
| Policies re-place accountability for machine output on a named human who can explain it | 74 | 6 | N15 57% | mixed | W4, X12 |
| Automation must be observable, predictable, and directable, so autonomy raises coordination demand | 70 | 4 | N04 89% | C | G11 |
| (tension) Junior automation gains against the apprenticeship pipeline | 68 | 3 | N03 97% | C | X3 |
| Automating entry-level tasks removes the practice supply juniors trained on | 65 | 6 | N03 92% | C | X3 |
| A private chat session as parent object hides work from the team | 63 | 4 | N05 63% | mixed | X10 |
| (tension) Awareness of others' work against uninterrupted focus | 63 | 3 | N27 87% | C | G11 |
| Cheap generation multiplies output faster than review capacity | 61 | 8 | N16 69% | mixed | W4, X11, G14 |
| Newcomers build the model socially, by asking and doing with those who hold it | 61 | 4 | N26 90% | gap | W6 |
| Removing practice through automation or offloading causes skill atrophy | 57 | 8 | N01 79% | gap | G10 |
| Distributed work removes passive awareness, which must then be reconstructed at cost | 56 | 5 | N27 77% | C | X9 |
| Large batches lengthen queues and reduce review effectiveness | 54 | 4 | N10 93% | C | G17 |
| (tension) Documentation freshness against maintenance cost | 54 | 6 | N20 31% | mixed | W5, X5, G3 |
| (tension) Level of automation against operator skill and situation awareness | 48 | 3 | N01 85% | gap | G10 |
| Low-cost contributions consume scarce maintainer attention | 47 | 3 | N16 66% | mixed | W4, X11 |
| Automation relocates work to the residual human and raises the standard | 47 | 4 | N06 79% | gap | X8 |
| Delegating the interesting work erodes autonomy, mastery, and felt ownership | 42 | 6 | N01 62% | mixed | G6 |
| Explaining or teaching back forces mechanism-level understanding and exposes its absence | 40 | 7 | N08 28% | mixed | D3 |
| (tension) Mentoring cost against newcomer ramp-up | 40 | 2 | N26 98% | gap | W6, X3 |
| Narrating and reordering a change for the reader lowers the cost of reading it | 37 | 6 | N21 54% | mixed | W4 |
| (tension) Efficiency gains against rising standards and relocated labour | 31 | 3 | N06 87% | gap | X8 |
| (tension) Approval gates against agent throughput | 30 | 3 | N22 80% | B | W1, X4, G2, G8 |
| (tension) Ownership concentration against knowledge spread | 28 | 5 | N15 54% | mixed | X12, G15 |
| Manipulating an interactive model returns feedback that reading code does not | 26 | 2 | N20 81% | B | W2, X5 |
| (tension) Cognitive offloading against memory and independent skill | 24 | 4 | N01 79% | gap | G10 |
| (tension) Proxy metrics against the behaviour they distort | 15 | 4 | N23 73% | B | X6 |
| (tension) Gate strictness against developer tolerance | 14 | 5 | N22 50% | mixed | W2, X7 |

The three robust groups the placement leaves mixed — working state
held only in a session or a head is lost at a boundary (core 71, N11
75 percent); comprehension is layered and the program layer is the
one tools supply (core 59, N26 56 percent); self-report instruments
score an individual's perception, so team-level understanding is
inferred (core 51, N18 67 percent) — are taken up below: the first two
as connections in section 6, the third as theme 5.6.

Two things the table shows that the frame does not say.

First, the frame's confirmations are strongest exactly where the frame
was written from the fewest notes. G16, G11, G17, X3, W6, and X8 are
each confirmed by a group that is one note; those gaps and tensions
were added to the frame *from* that note. The groups whose core spreads
across several notes — provenance, rationale, authorship inference,
accountability, review flooding, explain-back, documentation freshness
— are the corpus's genuine convergences, and every one of them places
on two or three frame elements at once.

Second, the demand axis is nearly absent from the confirmations. Only
the explain-back group concentrates on a D value, and only because the
test was extended to look. The lifecycle stage and the tension list are
what the notes are organised by; what a device asks of a person is
recorded in the cards but not what they cluster on.

## 5. Emergent themes

An emergent theme is a mechanism that the blind runs grouped — as a
robust group, or as a group in one run matched by a group in the other
lens or in the near-match band — and that no index theme, axis value,
tension, or gap names as such. Nine candidates were drafted from the
reconciliation; an agent that saw only the export and the candidate
statements searched each for counter-cards and a boundary, and
recommended a verdict. Six survive as themes (two of them merged into
one), and two are demoted to connections in section 6. Member counts
are the cards that at least two of the carrying groups share; the
notes are the inventory's codes; evidence levels are the cards'.

### 5.1 Staleness without a trigger

A representation derived from the code — a document, a quiz item, a
map, a provenance link — has no change signal from its referent, so it
goes stale silently unless something couples it to the code or
re-verifies it on a schedule.

- **Where the runs found it.** Mechanism-A "recorded knowledge drifts
  from the code it describes unless something detects the change" (72
  cards, 9 notes) matches the robust tension "documentation freshness
  against maintenance cost" at 0.62; mechanism-B "a stored
  representation has no change trigger from its referent" (98, 5)
  matches tension-B "item stability against codebase change" at 0.53 and
  mechanism-A "spaced retrieval assumes discrete, stable items" at 0.49.
  Six groups across all four runs carry it; 147 cards sit in two or more
  of them, from N19 (85), N24 (31), N13, N20, N14, N23, N26, N08.
- **Best evidence.** M: 68 percent of surveyed developers agree
  documentation is always outdated (N24:175); structural congruence
  between a design model and its code decays across releases (N27:42).
  Most members are T (tool behaviour) and A.
- **Counter-cards.** Coupled artifacts exist and work: CodeTour pins a
  tour to a ref or regex and a CI watcher detects drift (N20:44);
  doctests and executable examples fail a build on drift (N19:107,
  N19:109); Swimm blocks a PR check until a moved snippet is reselected
  (N24:39); adr-kit runs a daily staleness check (N24:60); 74.6 percent
  of outdated comments are detectable from code-change features
  (N19:116). And staleness is tolerated: "useful even if not up to
  date" scores 3.96 of 5 (N24:176, N24:178). Awareness displays are
  event-fed by construction (N27:67) and a handover snapshot is consumed
  once (N11:132), so neither belongs to the theme as first drafted.
- **Boundary.** Holds for artifacts derived from the code that hold no
  executable or reference-level link back to it; does not hold for
  artifacts that execute, pin references, or are event-fed. Nothing
  measures how fast an uncoupled artifact becomes wrong or what that
  costs.
- **What it changes.** The frame has X5 (artifact against act), G3 (no
  evaluation of generated artifacts), G4 (no code change connected to
  review scheduling), and the durable-model track's invalidation problem
  as four separate items; they are one mechanism with one design
  response, *coupling*. It belongs as a property of the map's artifact
  column and the module-revisit row: an artifact cell is stale by
  default unless the cell names its change signal. The three Phase B
  tracks — durable model, rationale as artifact, explorable maps —
  describe it separately (section 6); a candidate on any of them
  inherits it.

### 5.2 Habituation of repeated friction

A gate, prompt, or approval that repeats decays: vigilance over reliable
automation falls with exposure and load, approvals become click-through,
and trust decouples from capability. A friction device must be designed
against its own decay.

- **Where the runs found it.** Mechanism-A "vigilance over reliable
  automation degrades with exposure and load" (79, 15) and mechanism-B
  "repeated monitoring and approval habituate attention" (81, 15) match
  at 0.47 — below the threshold, the same mechanism cut at a different
  edge — and both match tension-B "trust in automation against
  verification effort" (104, 20) at 0.61 and 0.42. 74 cards sit in two
  or more of the groups, from thirteen notes led by N01 (18), N21, N16,
  N14, N22, N23.
- **Best evidence.** C for the automation-bias base: a dependable aid
  that then fails degrades accuracy most (N01:27). M for gates:
  within-reviewer approval rate rose from 30.1 to 36.8 percent over seven
  months while inline comments fell 22 percent (N21:220, N21:221);
  vendor telemetry has 97 percent of permission prompts approved and
  dangerous-command blocking falling from 17 to 5 percent after fifty
  prompts (N22:38); half of CLI users created an allow-rule and a
  quarter of sessions start in bypass mode (N14:73).
- **Counter-cards.** The one software dataset runs the other way on a
  later cut: the no-review share of merged agentic PRs fell from over
  half to about 12 percent and time in review lengthened (N06:65), and
  its direction "can reverse under defensible analysis choices"
  (N16:126, N16:53). Regulated industries' forced manual friction
  "paradoxically preserves cognitive engagement" (N14:29); review
  checklists raised load and performance together (N23:116);
  complacency is greatest under multi-task load and less apparent when
  monitoring is the only task (N01:34). Students abandoning a friction
  method for speed is opt-out, a different decay (N17:135). No card
  shows a comprehension gate persisting or decaying over months
  (N21:174).
- **Boundary.** Holds for repeated, low-variance approvals under
  concurrent load; the software evidence is one disputed dataset plus
  vendor permission telemetry. Whether a quiz or explain-back gate
  habituates is unmeasured either way.
- **What it changes.** The frame records "reviewer habituation" in one
  cell of the analysis's grid and X4 (default against practice) says
  willpower fails; neither says the default fails too. Principle 4
  ("defaults decide; practices fail") needs the corollary that a default
  decays, and the method needs a lens the plan's reviewer would call
  *decay*: what the device is at month six — varied, sampled, faded with
  competence, or measured for persistence. It adds a gap the list lacks:
  no gate-persistence study.

### 5.3 The confidence gap

Fluent, answer-visible output produces a feeling of understanding that
exceeds the understanding held, and the gap hides until the assistant
is removed or wrong.

- **Where the runs found it.** Mechanism-A "assistance inflates
  apparent performance and confidence while understanding is unchanged"
  (92, 13) and mechanism-B "fluent, answer-visible output inflates
  confidence beyond understanding" (100, 18) — the widest mechanism
  group in any run by note span — with tension-A "explanation and
  transparency against overtrust" (44, 14) matching the latter at 0.59.
  70 cards sit in two or more groups, from sixteen notes led by N08
  (19), N01, N03, N23. Its evidence profile is the strongest of the
  nine: 27 of the 70 shared cards are C.
- **Best evidence.** C: judgments of learning are inflated when the
  answer is present (N08:111); 77 against 39 percent failure on a no-AI
  blackout task (N08:53, N21:163); perceived against actual
  understanding correlates at .26, .16, .15 (N23:30); poor explanations
  reduce accuracy while raising confidence (N08:56); internet search
  inflates self-assessed explanatory knowledge (N01:89, N01:90);
  performance rose and comprehension did not (N08:49).
- **Counter-cards.** At the level of stated attitude, confidence falls:
  20 percent of Stack Overflow respondents say they have become less
  confident in their own problem-solving (N23:109); 46 percent distrust
  AI accuracy (N08:61, N23:108); DX's change-confidence index fell over
  four quarters across 500 teams (N14:101). Experience protects against
  following a wrong suggestion (N03:86); a retrieval attempt before the
  reveal reduces the illusion (N08:112, N08:115); a 79-report
  meta-analysis found calculators alongside instruction improved
  paper-and-pencil skill (N01:96); one field study found liking rose
  while trust and telemetry did not move (N18:106).
- **Boundary.** Holds at the task level when the answer is on screen
  and the person judges their own understanding of it — several
  independent controlled designs. It does not describe developers'
  attitudes, which are distrustful in surveys. The two coexist: the
  mechanism is local metacognition, not trust.
- **What it changes.** X1 (speed against understanding) is not this;
  the divergence is between *felt* and *held* understanding, and it
  makes self-assessment useless as an instrument for the debt (5.6).
  Principle 3 ("test the model, not the text") gains its operational
  form: test with the answer off the screen. The hand-off row's quiz
  and explain-back cells should say *answer hidden*; and the retrieval
  attempt before reveal is the one intervention with C-level evidence of
  closing the gap, which places the generate-before column above the
  others on this theme.

### 5.4 The question-routing economy

Asking a colleague costs both parties, so people route around it to
documents, tools, and now AI; who gets asked determines what is learned,
what is shared, and what the team knows it knows. Transactive memory is
built and refreshed by asking, so AI as the cheapest answerer weakens the
team's directory — the last step an inference, not a finding.

- **Where the runs found it.** Mechanism-A "asking a colleague costs
  both parties, so people route around it" (45, 12) matches tension-B
  "knowledge in artifacts against knowledge in people" (108, 9) at 0.71
  and mechanism-B "asking AI first bypasses colleagues, so the team's
  directory weakens" (56, 8) at 0.53; tension-A "asking a person against
  asking the machine" (48, 9) matches both. Six groups carry it; 108
  cards sit in two or more, from N09 (69), N26, N18, N27.
- **Best evidence.** M: Stack Overflow question volume fell 25 percent
  in six months after ChatGPT, difference-in-differences (N09:88), the
  fall concentrated among newer users (N09:89, N09:91); other members
  are the most used information source, sought twenty times to tools'
  four (N27:33, N27:69); 30 percent hit knowledge silos ten or more
  times a week (N24:182). Q: five minutes asking against a day reading
  (N26:87, N26:18); asking an expert interrupts both parties (N26:77).
  T: 51 percent now ask generative AI instead of a teammate, 62 percent
  because it is easier without embarrassment (N09:76).
- **Counter-cards.** Among 152 professionals AI use is associated with
  *higher* knowledge-sharing peer interaction (N09:86); asked whether
  interruptions from colleagues had decreased, 28 percent agree and 32
  disagree (N09:77); the same sample would still ask a teammate how
  something was done (50 percent) or a colleague to clarify business
  rules (65 percent) — routing is by question type (N09:79). An imposed
  directory helps strangers and hurts a pair that already has one
  (N09:12); a clearinghouse member has measured effects, not only a
  bottleneck (N09:26); AI filled part of the social role of teammates
  without loss on the outcome measured (N04:101). No source measures a
  transactive-memory change on a team whose code an agent wrote
  (N09:132, N09:74).
- **Boundary.** The routing-cost half is well evidenced before AI at M
  and Q; the displacement half is self-report and a public Q&A decline,
  which is not a team directory; the consequence is argument only and
  its direct test is a recorded gap.
- **What it changes.** The frame holds "who knows what" as G15, a
  missing instrument. The theme is the mechanism the instrument would
  measure, and it is observable: an *ask* is an act, and who is asked —
  a person, a document, a model — is the team's directory being used or
  bypassed. Principle 9 ("the model is held socially") gains the
  routing corollary, and the map's read-or-navigate column at hand-off
  and at joining gains "ask a person" as a cell distinct from "read".

### 5.5 The authorship inference

Every instrument that locates knowledge or assigns responsibility —
blame, degree of knowledge, truck factor, ownership metrics, reviewer and
expertise recommenders, the Line 10 rule, contribution policies, the DCO
— infers understanding from authorship, and agent authorship breaks the
inference across all of them at once.

- **Where the runs found it.** Robust: mechanism-A "authorship-based
  estimates of knowledge break when authorship no longer implies
  understanding" and mechanism-B "AI authorship severs the
  authorship-implies-comprehension inference" match at 0.69 (core 78,
  8 notes, top note N15 at 36 percent — the most evenly sourced robust
  group in the corpus); tension-A "authorship as evidence of knowledge
  against actual comprehension" (76, 14) matches the latter at 0.50.
  The placement files it under X12 and G15, which is why it is listed as
  a confirmation in section 4; it is listed here too because those two
  elements name a signer and a missing instrument, not the inference.
  94 cards sit in two or more groups, from N15 (29), N23 (26), N26,
  N19, N18, N09. Held-out prior P3 was found independently on the same
  groups.
- **Best evidence.** M for what the instruments measure and for policy
  spread: under 7 percent of kernel commits carry an assistance trailer
  (N16:78); DOK and truck-factor weights (N19:146, N19:148). The break
  itself is argument (Wheeler, N13:95, N23:74, N08:22, N08:23;
  footprint tools infer knowledge from authorship or text and none asks
  a person, N18:95) and policy (agents must not sign off and the human
  must be able to defend the content, N15:42, N15:45, N15:41).
- **Counter-cards.** The inference was weak before any agent wrote
  code: DOK explains R² = .25 of self-rated knowledge (N23:66); the
  ownership–fault relation is weak or absent on seven projects (N15:28);
  co-changer expert suggestion is right under half the time (N26:167);
  69 percent at JetBrains say reviewer recommendation never helps
  (N09:63). DOK has an interaction term that does not depend on
  authorship (N19:126); policies re-place the inference on a person
  rather than abandon it (N15:42, N15:45, N15:49); a maintainer says
  truck factor "is about institutional memory getting lost, which no
  automatic system can account for" (N26:170). Wheeler is a position
  paper (N08:22); one study of DOK under AI authorship exists and its
  result is not in the corpus (N13:96).
- **Boundary.** Holds as an argument about the footprint family and as
  a description of what contribution policies react to. No card
  measures a footprint metric before and after agent authorship on one
  codebase.
- **What it changes.** The analysis's authorless-code lens is
  confirmed and widened: any candidate that reuses blame, ownership,
  DOK, truck factor, or a recommender as a proxy for understanding
  inherits an inference that was weak before agents and is now broken
  — so the lens fails such a candidate regardless of AI. G9 should say
  this: the gap is not that no source addresses authorless code, it is
  that every locating instrument assumes a person authored it.

### 5.6 The instruments in use cannot see the debt

The frameworks and studies in use score the wrong construct (perception
rather than the model held), at the wrong level (the individual rather
than the team), over the wrong horizon (one session rather than weeks);
the instruments that could see it exist separately and have not been
run together on a professional team and a living codebase.

- **Where the runs found it.** Two candidates merged on the negative
  case's advice. Self-report against observation: the robust group
  "self-report instruments score an individual's perception, so
  team-level understanding is inferred, not observed" (core 51, N18 67
  percent) with tension-A "self-report against telemetry as evidence"
  (108, 16) at 0.64 and tension-B "survey instrument convenience against
  construct validity" (95, 5); held-out prior P5 found independently on
  the same. The debt invisible to the studies: mechanism-A
  "understanding effects go unobserved because studies stop at speed or
  output within a session" (49, 13) and mechanism-B "instruments count
  output or stop after one session" (118, 17), which no run matched
  because each cut the evidence-quality material differently. 88 and 91
  cards respectively sit in two or more groups; the first from N18 (61)
  and N23 (20), the second from N23 (47) and sixteen other notes, almost
  all of them dead-end cards.
- **Best evidence.** M: transactive memory correlates with performance
  at .77 self-reported and .38 observer-rated (N09:23); psychological
  safety at .80 with self-rated learning and .47 with observer-rated
  performance (N18:67); only 17 percent rate coworker awareness
  important because it is so easily obtained (N27:70); 76 percent rate
  "not understanding generated code" unimportant (N01:142). C: the
  productivity RCTs measured speed and throughput only (N23:159); EEG
  shows reduced engagement where self-report would not (N14:16). The
  DORA metrics are self-reports about a service by whoever answers
  (N18:30, N23:105).
- **Counter-cards.** Self-report converges with external criteria in
  places: a self-reported TMS composite correlates .57 with manager
  ratings (N18:55); Lewis aggregates to the team only after within-team
  agreement (N18:57); the Team Tacit Knowledge Measure is scored as
  distance from an expert profile (N18:79); DORA itself calls the
  objectivity of logs-based metrics a misconception (N23:105). And the
  missing instruments exist: the blackout task detects the debt within a
  session (N08:53, N21:163); comprehension time is inferred from IDE
  logs on professionals (N26:92, N26:97); cdebt and comprehension-debt
  ship a verified-understanding score (N19:12, N23:92); a two-month
  programming retest exists pre-AI (N14:87) and a three-year retest in
  the adjacent GPS literature (N01:94); the seven-month reviewer dataset
  is public (N21:220).
- **Boundary.** What is absent is the conjunction — a professional
  sample, a living codebase, a horizon beyond one session, a
  comprehension outcome — not any one element. The "one cause" the
  first draft offered (study economics, telemetry fields, vendor
  ownership) is conjecture; the team-cognition literature has
  agreement-checked and profile-scored instruments that software has
  not adopted.
- **What it changes.** Principle 7 ("bring the instrument") should
  name the instrument and the horizon rather than say nothing measures:
  a blackout or explain-back task, scored against the code, on a
  professional team, repeated over weeks, with the team's directory
  measured by agreement rather than by a survey of individuals. The
  gaps G1, G2, G6, G14, G15, and G17 are one gap under six headings, and
  X6 (measure against Goodhart) is about a different failure — a
  measure that distorts — than this one, a measure that does not see.

## 6. Connections

**Two candidates demoted from theme to connection.** Both were drafted
as mechanisms and failed the negative-case check as mechanisms while
surviving as links the corpus does not draw.

- *The regenerability boundary.* The draft said a tool can regenerate
  only the program layer of comprehension, and regenerating overwrites
  what people added, so maps, wikis, and tours plateau. The layers are
  Pennington's (N08:15, N08:16) and "tools support the program model,
  rarely the situation model" is Storey's 2005 finding already in the
  corpus (N20:95, N08:18) — it is the robust group "comprehension is
  layered", one of the three section 4 lists as mixed, not a new
  theme. The overwrite clause is a
  design choice of particular tools (N20:21, N24:54) and belongs to
  5.1. And transcript-fed tools do regenerate rationale at prototype
  level: AfterVibe recovers a specification from code plus conversation
  trajectory, validated by blind regeneration at 5.06 of 6 (N24:139);
  48 percent of issues had their complete rationale in chat (N27:92).
  What remains is a connection: the maps track, the rationale track,
  and the comprehension literature describe the same boundary and none
  measures whether any artifact builds the situation layer (N20:109).
- *Suspension and resumption as one mechanism.* The draft joined
  interruption, WIP, compaction, and shift handover as one loss under
  four names. The human-interruption and agent-compaction pair holds
  and is already a robust group — a finite store sheds suspended state,
  with C-level memory-for-goals evidence (N11:71, N11:73, N11:84) and
  M-level compaction benchmarks (N11:139, N11:141) — but its core is 75
  percent one note. WIP is a queue mechanism measured as time, not
  state (N10:77, N10:84); handover is a transfer between two stores with
  its own literature and a structured handoff cut errors 23–46 percent
  (N11:58, N11:59), which no interruption study shows within a person;
  one interruption study found no loss in the work at all (N22:113).
  The unification is the session's analogy; the cards that would test
  it — what a human recovers from a compaction summary (N11:181), what
  is understood after a switch (N10:84) — are recorded as absent.

**Groups found in one run only.** Eighty-eight eligible groups match nothing
in the other replicate of their lens; the reconciliation report lists
them all. Most are the material of section 5 cut differently. Those that
name something the robust groups do not:

- *Reliance drags the least experienced down most* (mechanism-A, 73
  cards, 12 notes): the gains inside the tool's competence and the losses
  outside it both land on the novice — a corollary of X3 that no
  tension states.
- *A check that rewards surface cues can be passed without the
  construct* (mechanism-B, 56 cards, 7 notes; tension-A "quiz validity
  against gameability", 92 cards, 14 notes; tension-B "assessment
  automation against grading validity", 94 cards, 10 notes): the same
  concern under three names, matched across lenses but not within either
  — X2 (text against model) and X6 (measure against Goodhart) each hold
  half of it.
- *Vendor evidence against independent evidence* (tension-A, 118 cards,
  22 notes) and *research rigour against realism* (tension-B, 121 cards,
  25 notes): the two widest groups in the corpus by note span, and
  neither replicated, because each run split the evidence-quality
  material along a different line. The corpus has a great deal to say
  about the quality of its own evidence and no frame element to say it
  under.
- *Curated context against accumulated context* (tension-A, 44 cards,
  8 notes): the human editing, pinning, and deleting the model's context
  as a practice of understanding — placed under X10 and G12 but named
  by no tension.
- *Agent as teammate against agent as tool* (tension-A, 76 cards, 15
  notes): G11 and G13 name measurements missing; the tension the
  clusterer saw is the design choice behind them.

**Undrawn connections.** Note pairs whose cards are lexically close
(cosine ≥ 0.45 on TF-IDF) but that share no body link:

- answer-ai-sweep ↔ solve-it-sweep, 19 pairs. The two Phase A sweeps
  of the same product line do not link to each other at all. The
  dialog-engineering claims appear in both; the inventory's *restates*
  field is within-note by design, so it did not catch the repeats.
- track-durable-model ↔ track-measurement (5) and
  track-durable-model ↔ track-rationale-as-artifact (4): item
  invalidation and drift are the same problem as documentation
  staleness and as the retention instrument's item stability; the three
  Phase B tracks describe it separately.
- automation-as-a-team-player ↔ handover-between-sessions (3): common
  ground and the Basic Compact against the handover's stance — the same
  claim about what a receiving party must hold, from two literatures the
  notes read apart.
- automation-as-a-team-player ↔ review-capacity-and-volume (2), and
  singletons joining review-capacity to expert-finding, apprenticeship,
  unfamiliar-code, and track-rationale: reviewer attention is a resource
  every Phase C note draws on and only one note measures.

## 7. The held-out priors

Seven patterns the session suspected before clustering were written
down and withheld from the clusterers. An agent that had not seen the
clusterings' provenance matched each against the four runs under a
stated rule: a run *finds* a prior only if one group holds at least
three of the prior's exemplar cards from at least two notes *and* its
name or statement expresses the pattern rather than a shared topic.
*Found independently* means at least one run did that; *found when
looked for* means the exemplars are in the corpus and were grouped, but
under a different pattern or one note at a time.

| Prior | Fate | What the runs did with it |
| --- | --- | --- |
| P1 Grain as one variable under five names (step grain, change size, WIP, context size, quiz granularity) | found when looked for | Every run pairs change size with WIP (N10:2 half-states the join); no group joins three of the five, and no statement says they are one variable. |
| P2 The receiver's questions as the mechanism of reconstruction (teach-back, I-PASS read-back, Fagan paraphrase, Sillito's questions, Socratic follow-up) | found when looked for | The handover half is stated outright — mechanism-B: "written summaries lose it and the receiver's questions repair it" — but from N11 alone; teach-back, Fagan, the question catalogues, and Socratic follow-up went to four other groups in every run. Mechanism-B coined "question-driven foraging" for the catalogues without joining it to handover. |
| P3 Recency locates knowledge; an Agent Run as the last toucher breaks it | found independently | Mechanism-B and tension-A each put the Line 10 rule (N09:36), degree of knowledge (N19:126), blame (N24:85) and the Agent-Run card (N09:100) in one group and state both halves — under "authorship", the broader family the recency devices sit inside. |
| P4 Anticipation (awareness frameworks stop at the present; generate-before, predict-before, plan approval, and the handover stance all demand the future) | found when looked for | Generate-before and predict-before are joined in two runs; plan approval, stance, and the awareness card N27:15 sit in three other groups in all four. No statement uses the future as its organising idea. |
| P5 Self-report diverging from observation | found independently | Tension-A joins the r = .77 against .38 card (N09:23) with the DORA and SPACE cards under self-report against telemetry; mechanism-B states the divergence over the survey cards. Narrower than the prior: the illusion-of-competence cards went elsewhere in every run. |
| P6 Two-sided opacity (silent automation and inaccurate agent self-report; the human's illusion of competence) | found when looked for | One tension group holds both sides but states a different relation — transparency driving overtrust. The inaccurate-self-report card (N04:117) was never grouped with the illusion cards. |
| P7 The amnesiac discourse (precedents restated without citation) | found when looked for | The cards state it in so many words (N01:1, N06:1, N04:123) and every run filed each under the mechanism its precedent is about; the tension runs attach the precedents as support, the opposite of noting their omission. |

Two of seven found independently is the expected result for priors
formed by reading the notes in order: P3 and P5 are the two whose
exemplars are measurements in several notes; the other five are joins
across notes that the corpus states piecewise. P7 could not have been
found by any clustering of claim content, and is listed to record
that. The plan's condition for the priors — that they not be
smuggled in as themes — is met for P1, P2, P4, P6, and P7: they are
reported here as the session's reading, not as findings, and the
analysis may use them only as such.

## 8. What this changes in the analysis

Addressed to the [analysis](analysis.md), which is revised in its own
commit. In order of how much they move.

1. **Principle 7 names its instrument.** "Nothing measures a codebase
   model over weeks" is true only as a conjunction (5.6). The principle
   should say what the instrument is — a blackout or explain-back task
   scored against the code, answer hidden (5.3), on a professional team
   over weeks, with the team's directory measured by within-team
   agreement rather than by a survey of individuals — and that
   self-assessed understanding is not it. The gap list's G1, G2, G6,
   G14, G15, G17 collapse into that one sentence.

2. **Principle 4 gains a decay clause.** Defaults decide, practices
   fail — and defaults decay (5.2). A friction device that repeats must
   be designed against habituation: varied, sampled, faded with
   competence, or measured for persistence; and the method needs a
   *decay* lens beside *enforcement and relocation*. The one software
   dataset on gate decay is disputed in direction, so the lens asks a
   question no candidate can yet answer from evidence, which is the
   point of asking it.

3. **Principle 6 gains a coupling clause.** "Record the act, not only
   the artifact" holds; 5.1 adds that an artifact with no change signal
   from its referent is stale by default. The map's artifact column
   should carry the signal each cell depends on (a ref, an executable
   check, an event feed, a schedule) or say it has none; the
   module-revisit row's "invalidated by change" is this clause's one
   existing instance.

4. **Principle 3 gets its operational form.** "Test the model, not the
   text" becomes *test with the answer off the screen*: the confidence
   gap (5.3) is produced by the answer's presence, and the retrieval
   attempt before the reveal is the one intervention with controlled
   evidence of closing it. The hand-off row's quiz and explain-back
   cells should say answer-hidden; the generate-before column rises on
   this theme.

5. **Principle 9 gains the routing corollary, and the map a cell.** The
   model is held socially *by asking* (5.4): who is asked — a person, a
   document, a model — is the team's directory in use or bypassed, and
   an ask is an observable act. The read-or-navigate column at hand-off
   and at joining should distinguish "ask a person" from "read"; the
   claim that AI as cheapest answerer weakens the directory stays
   marked as inference.

6. **The authorless-code lens is widened.** Any candidate that reuses
   blame, ownership, DOK, truck factor, or a recommender as a proxy for
   understanding inherits an inference that was weak before agents (R²
   = .25) and is now broken (5.5); the lens should fail such a candidate
   whether or not an agent wrote the code, and G9 should be reworded to
   say every locating instrument assumes a person authored it.

7. **Principles 12 to 14 are single-note.** The confirmations of G11,
   G12, G16, G17, and X3 are each one Phase C note recovered by the
   clusterers (section 4). The analysis's principles 12 to 14 rest on
   the same notes and are consistent with the corpus rather than
   converged on by it; a candidate that depends on one of them needs a
   second source. The review-capacity half of principle 14 and all of
   principle 15 are the exceptions: the review-flooding, accountability,
   and authorship groups are among the most evenly sourced robust groups
   in the corpus.

8. **The demand axis is a design choice, not a finding.** Only the
   explain column concentrates a robust group; the notes cluster on
   stage and mechanism, not on what a device asks of a person. The map's
   columns remain the right way to compare candidates, but the method
   should stop treating a column as evidence-bearing in itself: a
   candidate's demand is what it *is*; its evidence attaches to the
   mechanism (sections 4 and 5), not the column.

9. **Task start is the thinnest stage.** W1 places 89 cards against
   W4's 534; the map's "Issue declared" row is the least evidenced row
   on it, and the plan's reviewer was right that the corpus was
   collected around the loop, the hand-off, and review.

10. **Add an evidence-source lens.** The two widest groups in any run —
    vendor against independent evidence, rigour against realism — have
    no frame element to sit under. The method should ask of every
    candidate's supporting claim whether it is vendor-run, single
    session, or self-report, since 5.6 shows those are the three ways
    the corpus's evidence fails to see the debt.

Two things the themes do not change. The three index themes hold: no
robust group crosses T1, T2, and T3 in a way that suggests a fourth,
and the placement's drift toward T3 is the corpus's growth, not a
misfiling. And the lifecycle-and-team lens the analysis adopted after
Phase C is confirmed as the corpus's own centre of mass — 1,348 of 3,465
cards place on T3 — even though the Phase C notes are the ones the
corpus has read least.

## Method notes

Departures from the plan, for a reader checking it against what ran:

- The dispersion test as first run counted W, X, and G but not D; the
  explain-back group was flagged as scattered until D was consulted. The
  table above reports the corrected result; the reconciliation script in
  the scratchpad was not rerun, since no other group's verdict depends
  on D.
- The near-match band (0.40–0.60) was inspected by hand rather than by
  a second rule, and its pairs are reported as candidates, not as robust
  groups.
- The one scattered-or-mixed flag the plan defined as *emergent* was
  supplemented with the top-note share, which the plan did not ask for
  and which turned out to separate the confirmations that mean something
  from those that recover one note.
