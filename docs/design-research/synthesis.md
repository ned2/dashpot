---
status: research
date: 2026-09-13
---

# Cognitive debt: synthesis

A documentary map of the sixteen cognitive-debt notes in this directory
(the [team lens](README.md#the-team-lens) note was researched separately
and is cited where it bears on a tension; the ten Phase C notes on the
lifecycle and the team are summarised in
[their own section](#what-phase-c-adds-added-2026-09-15) below): what the sources say the loss
is, where each remedy sits, what each demands of the person, how much
evidence stands behind each cell of that map, the tensions the sources
state without resolving, and the gaps every pass left. It ranks nothing and
judges fit for nothing; those questions belong to the separate
[analysis](analysis.md). Every claim below is a summary of a cited note;
the note carries the primary source.

## Finding

The loss is real in a narrower sense than the discourse implies, and every
remedy in the landscape addresses a different slice of it. What the evidence
supports is that professional developers using AI to learn or produce code
score lower on immediate comprehension measures with no time saved
(−17 points in a preregistered RCT), that verification behaviour rather than
exposure predicts comprehension (r = 0.96 in a small within-subject study),
that a teach-back gate cut later unassisted failure from 77% to 39% at a
velocity cost of d = 1.52, and that reading and approving is the textbook
condition for the illusion of competence
([evidence, finding](evidence-and-mechanisms.md#finding);
[hand-off checks, evidence](track-hand-off-checks.md#evidence)). Every one
of those results is a single session; the first AI-coding study with any
retention interval is one week with 22 novices
([literature addendum](literature-addendum.md#corrections-proposed)).
Nothing measures a developer's model of a real, evolving codebase over
weeks, nothing measures it for a team, and nothing tests any remedy on code
whose only author was an agent
([unfamiliar code, finding](unfamiliar-code-and-shared-models.md#finding)).

The remedies split along one line. **Bookend** remedies — explainers,
quizzes, teach-back, review policies — check understanding after the agent
finishes; they are the most built (three PR-quiz gates in Phase A, fifteen
more found later), the only family with a causal result, and the family whose
questions are known to leak the answer from the text
([hand-off checks](track-hand-off-checks.md#open-questions-in-the-sources)).
**In-loop** remedies keep the person authoring or verifying at each step;
step gates ship in every agent, but the one tool that inverts the authorship
default — AI output inert until the person promotes it, completions
withheld, no automatic follow-up — is a notebook, and no editor or agent CLI
has ported it
([in-loop friction](track-in-loop-friction.md#inversion-outside-notebooks);
[Solveit, product mechanics](solve-it-sweep.md#product-mechanics)). Beside
both sit **artifacts** — maps, wikis, living docs, provenance traces — whose
existence is the whole mechanism: no tool records that a person read one,
and the pre-AI rationale literature measured capture cost as the constant
that defeated them
([rationale, evidence](track-rationale-as-artifact.md#evidence)). Under all
three, the human-factors literature had already measured the pattern the
coding sources assert — routine performance up, failure performance and
awareness down, skills decaying without practice, a ten-minute return to
manual control restoring detection — and none of the coding sources cites it
([adjacent literatures, finding](adjacent-literatures.md#finding)). The
history of technology had measured a second pattern the coding sources
restate: Cowan's finding that "labour-saving" household technology
relocated work onto one generalist and raised the standard rather than
reducing hours, with the same year, the same word — irony — and no
cross-citation with Bainbridge; nobody in software discourse cites her
either ([Cowan, finding](cowan-more-work-for-mother.md#finding)).

## The loss, as the sources define it

The object at risk is a layered mental model — domain, program, situation —
whose most expensive and least documented layer is the mapping from the
world to the code and the rationale for each part
([evidence, program comprehension](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of)).
Naur's 1985 argument that this "theory" lives in the programmers and cannot
be rebuilt from text is the philosophical anchor, and was read from the
primary text: revival "merely from the documentation, is strictly
impossible"
([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model)).
The question catalogues agree on what is hardest: "why was it done this
way?" is the largest category of hard-to-answer questions across 179
developers, and the usual answer — ask a teammate — fails when the teammate
has gone
([explorable maps, evidence](track-explorable-maps.md#evidence)).

The naming is recent and contested. "Cognitive debt" was coined by an
essay-writing EEG preprint (n = 54) that its own authors caution against
generalising; Storey's "cognitive debt" and later "triple debt" are
practitioner framings with a signal list but no instrument; Wheeler's
"substrate collapse" refuses to specify one; the two do not cite each other
([track measurement, position papers](track-measurement.md#position-papers-and-proposals)).
Answer.AI names the same thing "understanding debt" and locates it in tool
defaults rather than in the person
([Answer.AI, core claims](answer-ai-sweep.md#core-claims)). The one
professional deskilling measurement in any field is colonoscopy: adenoma
detection fell from 28.4% to 22.4% after three months of AI exposure, an
observational result
([adjacent literatures, supervising automation](adjacent-literatures.md#supervising-automation)).

Two accounts of *why* it happens coexist. The cognitive account is the
illusion of competence: judging one's own knowledge while the answer is
visible, which diff reading is
([evidence, illusion of competence](evidence-and-mechanisms.md#illusion-of-competence-and-fluency));
the offloading literature adds that search inflates self-assessed
explanatory knowledge (d = 0.43–0.63) without changing performance, and that
the popular "Google effect" on memory failed replication
([adjacent literatures, cognitive offloading](adjacent-literatures.md#cognitive-offloading)).
The motivational account, from Answer.AI, is self-determination theory:
delegation erodes autonomy and competence, not only knowledge; Ryan and Deci
support the mechanism, while the "junk flow" and gambling analogies are the
team's own inference
([adjacent literatures, motivation](adjacent-literatures.md#the-motivational-account)).

## The map

Two axes organise everything found, with a third dimension that Answer.AI
made explicit.

**Where the friction lives.** Task start; inside the loop (each step);
hand-off (agent done, before commit or review); review and merge; continuous
(scheduled, independent of any task); onboarding and team (a person joining
or a model shared). The landscape sweep found the first slot empty for
agentic work and the last untouched by any AI-era item
([landscape sweep, observations](landscape-sweep.md#observations-for-the-deep-pass);
[unfamiliar code, mapping](unfamiliar-code-and-shared-models.md#mapping-to-the-existing-notes)).

**What it demands of the person.** Generate or predict before seeing;
write; explain (teach-back); recall (retrieval); verify or approve; read;
navigate or ask; nothing (the artifact exists). The mechanisms with
meta-analytic support cluster at the demanding end — retrieval g ≈ 0.5–0.6,
self-explanation g = 0.55, teaching g = 0.56, generation d = 0.40 — and the
negative-leaning evidence at the passive end
([evidence, summary table](evidence-and-mechanisms.md#summary-table)).

**How it is enforced.** A tool default; an opt-in mode; a personal practice;
a policy enforced socially; a gate enforced by tooling. Answer.AI's claim
that willpower-based practices fail and that defaults must make the
understanding path the easy one is the only source to name this axis;
Hora et al.'s 281-policy survey shows the social end (close 48%, ban 21%,
never tooling)
([Answer.AI, core claims](answer-ai-sweep.md#core-claims);
[hand-off checks, gate placement](track-hand-off-checks.md#gate-placement-and-enforcement)).

The grid, populated with what the notes found. Evidence level: **C** causal
(randomised, comprehension outcome); **M** measured (telemetry or
observational, not comprehension); **Q** qualitative study; **T** testimonial
or self-report; **—** nothing.

| Where \ demands | Generate / write | Explain | Recall | Verify / approve | Read / navigate | Nothing (artifact) |
| --- | --- | --- | --- | --- | --- | --- |
| **Task start** | Solveit restate-the-problem, Default Code (T); Kiro/Claude Code/Devin plan approval (M: 39% plan rejection vs 3% per-permission); no predict-before-reveal tool (—) | — | Learning Opportunities start-of-session check-in (T) | — | — | AGENTS.md, rules, steering (—) |
| **Inside the loop** | Solveit inert-until-promoted, `TODO(human)` (T); copilot.lua manual trigger (—); no editor default (—) | `quiz-me` Socratic follow-up (T) | — | Per-command, per-hunk, per-file gates in every agent (M: CUPS verifying 22.4%; Chen/Kuo boundary timing; "tenth approval") | Hunk review-first viewer (T) | Curated dialog as artifact (T) |
| **Hand-off** | — | Litt `/explain-diff` + quiz (T); teach-back gate (C: 61.5% vs 23.1% repair, d = 1.52 velocity); Covate, AIditor, diffquiz (T) | Litt quiz, ~18 quiz tools (T; MCQ leak reports) | Walkthroughs: CodeRabbit, Sourcery, Copilot (M: Xiao FSE'24 review −19.3 h, no comprehension) | Literate diffs (T) | Explainer HTML, session transcript (—) |
| **Review / merge** | — | OSS "explain every line" policies, PostHog (Q: Hora et al.; socially enforced) | dkamm, Revodata, Tidewave PR quizzes (T; threat models stated) | Reviewer habituation (M: approvals rising, inline comments −22%); GitHub `Viewed` state (—) | — | Agent Trace (RFC, repo vanished); git-ai, Entire (—) |
| **Continuous** | — | — | codequiz, learn-codebase, cdebt (T; none read diffs); no SRS on a repo (—) | AI-free days (T); human-factors manual return (C in aviation, not code) | DeepWiki, Code Wiki, Codemaps, Understand Anything (LLM-judged only) | Swimm auto-sync, Kiro hooks, ADR skills (—); read attestation only pre-AI (g3doc `reviewed:`, AWS ADR slot) |
| **Onboarding / team** | — | Fagan inspection "education", pairing with novice driving (Q/M, pre-AI) | — | Review spreads files known +66–150% (M, pre-AI) | Tours: CodeTour, LACY (Q: 83% vs 57% quiz, 5 learners; Balfroid 26 devs) | Shared spaces, Notion agents (T); no AI-era team item (—) |

Sources per cell: [in-loop friction](track-in-loop-friction.md#existing-modes-and-tools),
[hand-off checks](track-hand-off-checks.md#question-and-explainer-generation),
[durable model](track-durable-model.md#prior-attempts),
[explorable maps](track-explorable-maps.md#explorable-code-maps),
[rationale as artifact](track-rationale-as-artifact.md#agent-maintained-living-documentation),
[measurement](track-measurement.md#proxies-and-telemetry),
[discourse and tooling addendum](discourse-and-tooling-addendum.md#the-gap),
[unfamiliar code](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model).

## What the grid shows

**One causal result, in one cell.** The only randomised comprehension
outcome for any remedy is the teach-back gate at hand-off, on novices, in a
single session, with 62% of rejected explanations tautological and no
judge–human agreement statistic
([hand-off checks, teach-back](track-hand-off-checks.md#explain-it-back-and-teach-back)).
Every other cell is testimonial, a proxy, or a pre-AI or non-code result.

**Adoption and evidence are inversely placed.** The most-built cells —
step gates inside the loop, quizzes at hand-off, maps and wikis continuously
— have no comprehension measurement at all; the vendors of step gates
describe them as overhead ("after the tenth approval you're clicking through
rather than reviewing"), the quiz tools have leak reports but no
discrimination data, and every wiki benchmark is LLM-judged
([in-loop friction, arguments](track-in-loop-friction.md#arguments-and-evidence);
[explorable maps, evidence](track-explorable-maps.md#evidence)).

**The demanding column is nearly empty of tools.** Generation before reveal
— the mechanism the evidence note names as the remedy for the diff-reading
bias — exists as a notebook default and a Neovim plugin setting, and as
nothing else
([in-loop friction, generation-first](track-in-loop-friction.md#generation-first-interactions)).

**The artifact column is full and unread.** Living docs, wikis, traces, and
transcripts are the largest and most commercial cluster; none records a
reader, the spec with the most backers vanished, transcript retention
silently breaks commit links, and the pre-AI rationale literature found
capture cost defeats the practice (60% cite time; "why chosen over
alternatives" rarely written) while what is written answers 41% of rationale
questions
([rationale, provenance](track-rationale-as-artifact.md#provenance-and-intent-capture);
[rationale, evidence](track-rationale-as-artifact.md#evidence)).

**Two rows have no AI-era occupant.** Continuous retrieval on a repository
exists as three hobby tools that never read a diff; card schedulers assume
stable items, content-hash identity resets rather than detects drift, and
the updating literature warns that reminder testing can protect the *old*
association
([durable model, invalidation](track-durable-model.md#item-invalidation-and-drift)).
Onboarding and team-level sharing — the pre-AI answer to code one did not
write, built "socially and by doing" over months — is absent from every
AI-era item; the practices that measurably spread a model are review,
pairing, and inspection
([unfamiliar code, finding](unfamiliar-code-and-shared-models.md#finding)).

## Tensions the sources state

Recorded as the sources leave them, unresolved.

- **Speed against understanding.** The teach-back gate's velocity cost is
  d = 1.52; Litt's rule is personal; the productivity meta-analysis finds
  g = 0.33 for output and 0.14 for learning; developers' flow rose 54→76%
  while worsened developer experience rose 14→27% in the one longitudinal
  professional study
  ([hand-off checks, evidence](track-hand-off-checks.md#evidence);
  [literature addendum](literature-addendum.md#the-gap)).
- **Text against model.** Generated questions test the diff's text unless
  prevented: two independent leak reports, Revodata's anti-search rules,
  LLM grading at κ 0.58–0.75 with a leniency bias, and no tool measuring
  whether questions discriminate readers who understood from readers who
  skimmed
  ([hand-off checks, open questions](track-hand-off-checks.md#open-questions-in-the-sources);
  [measurement, instruments](track-measurement.md#instruments-used-in-studies)).
- **Expert against novice.** Expertise reversal makes worked examples
  redundant or harmful for experts; Sankaranarayanan raises it as the cost of
  gating experts and proposes adaptive fading no tool implements; Answer.AI
  places the risk in the middle (2–20 years); comprehension time falls from
  66% to 44% of the day with experience
  ([evidence, summary table](evidence-and-mechanisms.md#summary-table);
  [unfamiliar code, comprehension strategies](unfamiliar-code-and-shared-models.md#comprehension-strategies-and-practice)).
- **Default against practice.** Answer.AI says willpower fails and defaults
  decide; every quiz, policy, and AI-free day in the landscape is a practice;
  Solveit's own reported failure mode is students going "too far, too fast
  with AI" despite the defaults
  ([Solveit, finding](solve-it-sweep.md#finding)).
- **Artifact against act.** Docs are "always outdated, yet useful anyway";
  Kiro closed "detect that anything changed" as not planned; Google asks
  whether documentation can be measured for accuracy and freshness ("tools
  have still not caught up")
  ([rationale, open questions](track-rationale-as-artifact.md#open-questions-in-the-sources)).
- **Measure against Goodhart.** Storey asks how to measure cognitive debt;
  Wheeler says the instrument does not exist; Rachel Thomas argues against
  quantifying learning; documented harm from comprehension metrics is
  educational only; the one deployed instrument is a self-report item
  ([measurement, arguments against](track-measurement.md#arguments-against-measuring)).
- **Interrupt against flow.** Proactive prompts are preferred at task
  boundaries (80–90% vs 47%) and dismissed mid-task (62%); the pre-AI
  interruption cost literature applies; no source says where a comprehension
  check should sit to be tolerated
  ([in-loop friction, open questions](track-in-loop-friction.md#open-questions-in-the-sources)).
- **Saved against relocated.** Cowan's thesis is that the tool eliminated
  the parts others had done and left "the imposition of the entire job" on
  one person, with output rising to absorb the saving; the corpus asserts
  the first half about AI coding without her — creation shifted to
  verification, no time saved, a "verification tax" — while its review
  telemetry runs *opposite* to the second: approvals rise and scrutiny falls
  rather than the standard rising (qualified 2026-09-15: that rests on one
  direction of evidence, Yu et al.'s within-reviewer habituation; Agarwal et
  al.'s observational data has unreviewed agentic merges falling from over
  50% to about 12% and time-to-merge lengthening from about 20 minutes to
  2–3 hours, which the authors state "runs opposite" to Yu et al., and Faros
  2026 has time in review up 441.5% beside unreviewed merges up 31.3% — the
  studies disagree ([review capacity, finding](review-capacity-and-volume.md#finding));
  the "verification tax" phrase is not in DORA's report and its attribution
  is unverified). Effort per hour, which every side of the
  household debate concedes fell, has no counterpart measure for verified
  code ([Cowan, mapping](cowan-more-work-for-mother.md#mapping-to-the-existing-notes)).
- **Individual against team.** Every AI-era remedy is for one person;
  Naur's theory is held by a team, team cognition predicts performance
  (ρ = .38), and the one longitudinal software-team study found models did
  not converge
  ([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model)).
  (added 2026-09-14: a separately researched note supplies the AI-era
  measurement this tension lacked — one person both reviewed and modified
  the agent's contribution in 78.9% of 25,264 agentic pull requests,
  multi-human patterns 11.3% — and the product responses to it
  ([chat-centric agents](chat-centric-agents-vs-team-sdlc.md#bottom-line)).)

## Gaps every pass left

Consolidated from the notes' dead-end sections; each is stated as an absence
after a bounded search, with the note that searched.

1. No study measures retention of a codebase model over weeks under agentic
   delegation, for professionals, on real code
   ([evidence](evidence-and-mechanisms.md#dead-ends-and-gaps);
   [literature addendum](literature-addendum.md#dead-ends)).
2. No study measures the comprehension effect of any approval gate, plan
   mode, or learning mode
   ([in-loop friction](track-in-loop-friction.md#dead-ends)).
3. No human evaluation of any generated wiki, map, or walkthrough; tours
   have two small studies
   ([explorable maps](track-explorable-maps.md#dead-ends)).
4. No tool connects code change to review scheduling; no spaced retrieval on
   a repository has been built or studied
   ([durable model](track-durable-model.md#dead-ends)).
5. No tool records that a person read a generated artifact; the only
   attestation precedents are pre-AI, and VOUCH's endorsement records admit
   "no comprehension quiz"
   ([rationale](track-rationale-as-artifact.md#dead-ends);
   [discourse and tooling addendum](discourse-and-tooling-addendum.md#dead-ends)).
6. No validated instrument for ownership, motivation, or flow under
   delegation beyond ~20 professionals; no comprehension telemetry ships
   ([measurement](track-measurement.md#dead-ends);
   [adjacent literatures](adjacent-literatures.md#dead-ends)).
   (qualified 2026-09-15: for ownership, DORA's 2025 questionnaire fields a
   five-item psychological-ownership-of-code scale to nearly 5,000
   respondents, with no published validation and no published analysis
   against AI adoption, and Seo et al. measure it within-subjects on 30 —
   the gap narrows to "no published analysis of a fielded instrument"
   ([team-level measurement, finding](team-level-measurement.md#finding);
   [ownership, finding](ownership-and-accountability-for-delegated-work.md#finding)).)
7. No company describes an internal comprehension ritual with enforcement
   detail; PostHog's review question is the nearest
   ([discourse and tooling addendum](discourse-and-tooling-addendum.md#dead-ends)).
8. No editor or agent CLI ships, or has announced, a manual-trigger-only or
   no-automatic-follow-up default; Claude Code 2.1.200's `AskUserQuestion`
   is the nearest change
   ([discourse and tooling addendum](discourse-and-tooling-addendum.md#dead-ends)).
9. No source addresses code whose only author was never a person who could
   be asked; the pre-AI answer to unfamiliar code is a mentor, a small task,
   and running it
   ([unfamiliar code](unfamiliar-code-and-shared-models.md#dead-ends)).
10. No AI-coding source cites the human-factors literature it restates, nor
    the history-of-technology literature on relocated labour; the corpus
    itself never uses the rebound or Jevons framing
    ([adjacent literatures, mapping](adjacent-literatures.md#mapping-to-the-existing-notes);
    [Cowan, software discourse](cowan-more-work-for-mother.md#travel-into-technology-criticism-and-software-discourse)).

## What Phase C adds (added 2026-09-15)

The ten [Phase C notes](README.md#phase-c-the-lifecycle-and-the-team) take
the team and the lifecycle as their unit. They do not change the map's
axes; they populate the row the map had left empty — "onboarding / team" —
and add rows the original where-axis did not have, because no AI-era
source had placed friction there: handover at a session boundary,
integration order across parallel branches, and the rate at which changes
arrive at review. Summarised as the map summarised the tracks, each claim
a précis of the cited note.

**What a team needs to see.** Awareness is defined as the up-to-the-moment
understanding of another's interaction with a shared workspace — who
(presence, identity, authorship), what (action, intention, artifact), and
where, with their histories, the future deliberately excluded. Its value is
instrumental: when the people whose work depends on each other's actually
talk, changes resolve faster and fail less (structural congruence cut
estimated failure probability 18.6% and 7.6% in two projects). "What have
my coworkers been doing?" was the second most sought information need in
the one field count, obtained from coworkers and email, not tools; the
controlled evidence that awareness tooling changes outcomes is two
laboratory experiments and a six-person field study. Bots are studied as
noise and as conduits; no source treats an automated actor as an awareness
*subject* whose who/what/where must be shown to people
([awareness, finding](workspace-awareness-and-coordination.md#finding)).
The chat-versus-durable-record argument has the same shape across three
generations — IRC kept off the list in 2004 because it is "not archived",
IM pasted into the tracker in 2010, "Slack is where context goes to die"
since 2019 — which is the team-lens note's split with a twenty-year record
(same note; [chat-centric agents](chat-centric-agents-vs-team-sdlc.md#two-competing-responses)).

**Team-level friction devices.** WIP limits and pull are justified in their
own texts by queueing theory as analogy; the software evidence is two
single-company before–after studies (lead time roughly halved; 37% shorter
with 24% fewer defects at one nine-person team) and three systematic
reviews of mostly single cases with no controlled experiment. The one place
WIP meets comprehension with measurement is batch size at review: 59%
versus 35% review effectiveness for small versus large changes (n = 50,
confirmatory), and useful-comment density falling with file count across
1.5 million comments. Of the ceremonies, the stand-up has mixed
knowledge-transfer evidence (34% of meeting time on the three questions;
low knowledge redundancy makes members uninterested in each other's
reports) and retrospectives have none by their own researchers' account.
No source measures whether a WIP limit, batch rule, or gate changes what a
team member *understands*
([flow, finding](flow-wip-limits-and-constraints.md#finding)).

**Handover.** In every observed setting the thing transferred is a state
model plus a stance — what the outgoing holder believes, was about to do,
expects, and would do if wrong — and the update is interactive: in four of
five investigated shift-change incidents written communication failed, all
six misunderstandings in sixteen taped nuclear handovers were repaired only
because the receiver asked, the sender's single most important item failed
to reach the receiver 60% of the time while senders believed it had, and a
structured protocol cut medical errors 23% across 10,740 admissions with no
added time. Interruption research says the same of handover to one's later
self: programmers navigated before editing in 93% of 10,000 resumptions and
restored position, goal, plan, context from cues, not memory. Agent-era
compaction and handoff artifacts re-implement the artifact side — the
vendors' own texts say what is dropped — and no source measures what a
human recovers from an agent's summary
([handover, finding](handover-between-sessions-people-and-agents.md#finding)).

**Automation as a team player.** The joint-activity strand's answer is one
argument across two decades: automation fails as a teammate because it is
"strong, silent, difficult to direct", so the target is observability and
directability, not a level of automation; coordination has a cost
(synchronisation, communication, redirection, diagnosis) every member must
help control; treating the machine as a substitute or multiplier is the
substitution myth. Human–autonomy-teaming experiments measured the cost
only in simulation, where human–human teams did better. The AI-teammate and
coding-agent literature restates the requirements — explain why, support
correction, notify of changes, "use friction to avoid overreliance" —
without citing the strand; the coding measurements are agent–agent
(coordinating agents lose 30–41% of solo success, 20% of steps to
communication), agent–successor (trace or notes cut a successor's events
20–59%), or reviewer-side ("reviewers reward agent behaviours that reduce
coordination cost"), with 22.58% of misalignment episodes involving
inaccurate self-report. Nothing measures the coordination cost an agent
imposes on a human team
([team player, finding](automation-as-a-team-player.md#finding)).

**Rate against capacity.** No source measures reviewer-hours per pull
request before and after agents on one population. Pre-agent: 3.2 hours a
week reviewing at Google, "hard finding time" already a top challenge at
Microsoft in 2018. Since: 43.2 million PRs merged a month, over a million
Copilot-agent PRs in five months; agentic PRs concentrated in a few
repositories (75% of projects below a 0.25 participation ratio); the
direction of review scrutiny disputed between studies (unreviewed agentic
merges falling from over 50% to 12% and time-to-merge lengthening, against
within-reviewer habituation, against vendor telemetry with time in review
up 441% and unreviewed merges up 31%); curl's triage record (20% slop, 5%
genuine, three or four people per report) ending its bug bounty. Of the
policies read in full none sets a numeric rate limit but one three-PR rule
and one hard stop; the tooling sold as capacity adds no human reviewer;
practitioners reach for Jevons — generation grows multiplicatively per
developer, review linearly with headcount
([review capacity, finding](review-capacity-and-volume.md#finding)).

**Who signs.** Every policy, forge rule, and vendor term read places
accountability for an agent-written change on a named person and none on
the agent or vendor: the kernel's "only humans can legally certify the
DCO", 122 of 281 policies explicit and the rest silent, GitHub requiring
another approver when its agent authored, vendor terms making review the
customer's duty in near-identical words; licence instruments diverge on
whether a person *can* certify agent output. Strong ownership predicted
quality at Microsoft (up to 72% of failure variance) with weak open-source
replication; under AI authorship possession "decreased continuously" with
autonomy while willingness to accept accountability held (30 participants),
and agent-written code was 15.8 points less likely to be modified later
under an "ownership hypothesis" its authors call untested. Nissenbaum's
1996 four barriers to accountability — many hands, bugs, blaming the
computer, ownership without liability — are the vocabulary the 2026
policies restate without citing
([ownership, finding](ownership-and-accountability-for-delegated-work.md#finding)).

**Who knows what.** Transactive memory correlates with performance at
r = .44 in the laboratory but r = .77 when self-reported and .38 when
observed; the "Line 10 rule" — ask whoever last touched the code — is
circumstantial responsibility as work practice; recommenders were evaluated
offline and the one in-vivo deployment found no influence because
reviewers already knew whom to pick. Under AI, 51% of 131 professionals now
ask the model instead of a teammate, split by question (71% for an
algorithm, 65% still a colleague for business logic), and Stack Overflow
fell 25% in six months; nothing measures a transactive memory whose "who" is
a transcript
([expert finding, finding](expert-finding-and-transactive-memory.md#finding)).
Nothing measures a team's shared model of its codebase at all: every
instrument scores teamwork, safety, tacit project knowledge, or delivery,
and every AI-adoption survey scores the individual
([team-level measurement, finding](team-level-measurement.md#finding)).

**The junior pipeline.** Apprenticeship theory says juniors learn by doing
real low-stakes work whose value pays for their training; the economics say
that if agents take that work the firm loses its reason to train and
seniors "can no longer observe whether juniors are learning or just
prompting". The hiring evidence is descriptive and contested (a 16–20%
relative decline for 22–25-year-olds in exposed occupations against
precise zeros elsewhere); telemetry has novice-rated sessions succeeding
15% against 28–33%, and juniors both least likely to try and gaining the
largest PR lift once they do. No source measures a junior's skill under an
agent beyond a session
([apprenticeship, finding](apprenticeship-under-agents.md#finding)).

**Parallel branches.** Pre-agent merge conflict rates sit between one in
six and one in three; conflict probability rose from 5% to 40% with the
count of concurrent changes at Uber; branch activity predicted up to 59%
more post-release failures. Agent-authored PRs conflict at 27.67%, 79.4%
are open concurrently with another, and replayed cross-agent pairs conflict
41.7%; the frequency prescriptions ("less than a day", "fewer than three
active branches") rest on argument and cross-sectional survey; no vendor
text states how many parallel runs is too many or in what order their
branches should land
([integration, finding](integration-frequency-and-parallel-branches.md#finding)).

**Tensions Phase C adds** to the list above: *session against work graph*
(make the session multiplayer, or attach it to the issue and branch — the
team-lens note's split, now with ChatOps as its precedent); *rate against
capacity* (generation multiplicative, review linear); *a named person
against many hands* (every policy names one signer; Nissenbaum's barriers
say why that fails).

**Gaps Phase C adds.** 11. No source treats an automated actor as an
awareness subject. 12. No source measures what a human recovers from an
agent's compaction summary or handoff artifact. 13. No source measures the
coordination cost a coding agent imposes on a human team. 14. No
before-and-after measure of reviewer hours per change exists. 15. No
instrument measures a team's shared model of its codebase, pre- or
post-AI. 16. No source measures conflict or quality as a function of the
number of concurrent Agent Runs on one repository. 17. No source measures
whether a WIP limit or batch rule changes what a team member understands.
And gap 10 now has five instances: the AI-coding sources restate
Bainbridge, Cowan, the joint-activity strand, Nissenbaum, and three
generations of the chat-versus-record argument, citing none.

## Provenance of this corpus

Five seed notes, six feature-idea tracks, three gap notes, two search
addenda, and a verification pass, all dated 2026-09-13; seventeen background
agents in two sessions, the first of which exhausted its web-search budget
after the seed notes, so the track notes' discovery ran on direct fetches
and structured indexes and their dead-end sections say so. The verification
pass checked fifteen claims: nine verified and filled, four corrected, three
left marked; the addenda proposed fourteen further corrections, all applied.
Corrections are inline, marked `(corrected 2026-09-13: …)`,
`(qualified …)`, or `(added …)`, so a note's original claim and its
revision are both visible. The team-lens note was researched separately on
2026-09-14; the ten Phase C notes on 2026-09-15 in a third session — eleven
agents, ten writing and one verifying the Finding paragraphs against their
sources — which proposed nine further corrections, all applied. The
[index](README.md) lists the notes in reading order.
