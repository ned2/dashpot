---
status: research
date: 2026-09-13
---

# Cognitive debt: synthesis

A documentary map of the sixteen notes in this directory: what the sources
say the loss is, where each remedy sits, what each demands of the person,
how much evidence stands behind each cell of that map, the tensions the
sources state without resolving, and the gaps every pass left. It ranks
nothing and judges fit for nothing; those questions belong to a separate
analysis, which has not been written. Every claim below is a summary of a
cited note; the note carries the primary source.

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
  rather than the standard rising. Effort per hour, which every side of the
  household debate concedes fell, has no counterpart measure for verified
  code ([Cowan, mapping](cowan-more-work-for-mother.md#mapping-to-the-existing-notes)).
- **Individual against team.** Every AI-era remedy is for one person;
  Naur's theory is held by a team, team cognition predicts performance
  (ρ = .38), and the one longitudinal software-team study found models did
  not converge
  ([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model)).

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
revision are both visible. The [index](README.md) lists the notes in
reading order.
