---
status: research
date: 2026-09-13
---

# Literature addendum

A web-search sweep for the studies the earlier notes could not look for. The
previous session exhausted its search budget after Phase A, so each track note
records a set of searches that could not be run; this note runs them, with
roughly 65 WebSearch calls plus direct fetches of arXiv, the GitHub and Hacker
News APIs, and vendor research blogs on 2026-09-13. Six targets were fixed in
advance (below). The rules are the same as the other notes: documentary only,
primary sources as terminal citations, figures reported as the source gives
them, and preprint distinguished from venue-published, with a statement of
which version was read. Nothing here assesses fit for any tool or workflow.
Semantic Scholar, the arXiv export API, DBLP, and OpenAlex all rate-limited or
blocked scripted queries again, so discovery ran through WebSearch and the
arXiv HTML search page; the ACM Digital Library and Wiley returned 403 on
every landing page, so three venue-published items below are cited from
metadata only, and are marked.

## The gap

The track notes converge on the same absences. The evidence note found "no
study … that measures retention of a developer's model of a real, evolving
codebase over weeks or months under agentic delegation" and no venue-published
comprehension RCT on professionals beyond Shen and Tamkin's preprint
([evidence note, dead ends](evidence-and-mechanisms.md#dead-ends-and-gaps));
the hand-off note could not search for "other teach-back or
explain-in-plain-English studies on AI-generated production code beyond
Sankaranarayanan" and found no walkthrough A/B
([hand-off checks, dead ends](track-hand-off-checks.md#dead-ends),
[evidence](track-hand-off-checks.md#evidence)); the maps note found "no
evaluation with humans" of any generated wiki or tour and could not retrieve
SWD-Bench's identifier ([explorable maps, dead
ends](track-explorable-maps.md#dead-ends)); the rationale note's coverage of
"2025–2026 preprints on generated-documentation hallucination" is
"incomplete" ([rationale, dead ends](track-rationale-as-artifact.md#dead-ends));
the in-loop note found "no study … that measures understanding as a function
of plan/hunk/command approval" ([in-loop friction, dead
ends](track-in-loop-friction.md#dead-ends)); the durable-model note found no
spaced retrieval on a real codebase ([durable model, research on
SRS](track-durable-model.md#research-on-srs-for-programming)); the measurement
note's absence claims are "limited to the pages and repository searches
actually run" ([measurement, dead ends](track-measurement.md#dead-ends)); and
the adjacent-literatures note found "no study … that measures motivation,
ownership or flow under agentic delegation with more than ~20 professionals"
([adjacent literatures, dead ends](adjacent-literatures.md#dead-ends)). The
six targets below map onto those sentences one to one.

## Target 1: comprehension, ownership, and skill studies of professionals, 2025–2026

Searched: WebSearch on comprehension/skill/ownership/deskilling with
"professional developers", "coding agent", CHI/CSCW/ICSE/FSE/ASE 2025–2026,
SSRN, and the Anthropic, Microsoft Research, Google Research and GitHub Next
blogs; arXiv HTML search for "AI-generated code" + comprehension, "cognitive
debt", and "comprehension debt" OR "knowledge debt" OR "epistemic debt". The
plain result: **no new study was found that measures a professional
developer's comprehension of code an AI wrote for them with a controlled
design**, beyond those already in the [evidence
note](evidence-and-mechanisms.md#ai-specific-evidence-20232026). What exists
is (a) professional-sample studies that measure something adjacent —
maintainability by a second developer, physiology, self-reported experience,
autonomy preferences — and (b) novice studies with a retention interval, which
the earlier notes lacked. Each entry gives design, sample, measure, result,
limits, and publication status.

**Borg et al., "Echoes of AI: Investigating the Downstream Effects of AI
Assistants on Software Maintainability"**
([arXiv:2507.00788](https://arxiv.org/abs/2507.00788), v3 2026-02-26; abstract
page and HTML read). Preregistered, in-principle acceptance at the ICSME 2025
Registered Reports track. Two-phase controlled experiment on a Java web
application (RecipeFinder): Phase 1, 76 participants (59 without AI, 17 with)
add a feature; Phase 2, 75 different participants, randomised, evolve the
Phase 1 code without AI. 151 participants in all, "95% professional
developers". Measures: completion time, CodeHealth, test coverage, SPACE-style
perceived productivity. Result: Phase 1 "AI assistants significantly reduced
task completion time, with a median improvement of 30.7%"; Phase 2 found "no
significant differences in subsequent evolution with respect to completion
time or code quality", with Bayesian effects "at most small and highly
uncertain". Limits stated: Phase 2 reached 75 of a targeted 128; self-reported
times for interrupted sessions; second-generation assistants rather than
agents. Relevance here: the outcome is a second developer's speed on
AI-originated code, not the author's understanding; no comprehension
instrument was used, and the authors name "cognitive debt risks" as future
work.

**Vella and Blincoe, "The Impact of AI Coding Assistants on Software
Engineering: A Longitudinal Study"**
([arXiv:2605.23135](https://arxiv.org/abs/2605.23135), v1 2026-05-22; abstract
page and HTML read; preprint). Two questionnaires six months apart (October
2024, April 2025), "158 eligible participants at the first time point, 101 at
the second, and a matched longitudinal cohort of 95" professional software
engineers using AI assistants, recruited by convenience and referral through
LinkedIn, X, Facebook, Discord, Slack communities and nine organisations.
Measures are perceptions: time per task, productivity, and three DX
dimensions (cognitive load, feedback loops, flow state). Results: "82%
reporting less [time] on writing code"; "a broader shift in focus from
creation to verification activities" the authors call "supervisory engineering
work"; productivity perceptions stable ("84% reporting improvement at both
time points") while "the proportion reporting worsened developer experience in
at least one dimension nearly doubled from 14% to 27%, with flow state and
cognitive load eroding while feedback loops improved"; within the worsened
cohort, flow state was "the predominant issue, affecting 54% at Q1" and "76% at
Q2". Limits stated: attrition, survivor bias (non-users excluded), 85% male
English-speaking sample, perception-based measures, tools of late 2024. No
comprehension, skill or ownership item.

**Chen, Talwalkar, Brennan, Neubig, "Code with Me or for Me? How Increasing AI
Automation Transforms Developer Workflows"**
([arXiv:2507.08149](https://arxiv.org/abs/2507.08149), v2 2025-09-13; HTML
read; venue-published as *CHI 2026*,
[doi:10.1145/3772318.3790850](https://dl.acm.org/doi/10.1145/3772318.3790850)).
Controlled within-subjects study, N = 20 (students, of whom 60% reported 3–5
years' professional programming experience; all weekly Copilot users, none
with prior agent experience), GitHub Copilot versus OpenHands on six tasks
across data analysis, feature addition and bug fixing, 90 minutes total,
April–May 2025. Results: agent success 60% versus 25% (p = 0.02); effort 12.5
versus 25.1 minutes (p = 0.01); 70% "were able to accomplish new tasks with
OpenHands" (p = 0.0013); on understanding, only 25% reported "a better
understanding of OpenHands outputs than Github Copilot outputs" (p = 0.07) —
a self-report item on understanding the tool's output, not a test. Limits
stated: one tool per category, students, 90 minutes, pre-defined tasks.

**Burelli et al., "Using Biometrics to Understand AI-Assisted Coding
Performance and its Perception"**
([arXiv:2606.20598](https://arxiv.org/abs/2606.20598), v1 2026-05-19; abstract
page read). Stage 2 Registered Report "under review at EMSE"; Stage 1 protocol
on OSF (doi:10.31219/osf.io/mex39_v2). Within-subjects crossover at two
universities (Bari, Copenhagen) with EEG, eye tracking, EDA, HRV, a rubric
performance score and NASA-TLX. Results: under AI "the EEG θ/α ratio was lower
during the first task and the gaze blink rate was higher during the second,
both consistent with reduced cognitive engagement when developers offload
generative effort"; no difference between undergraduate and graduate
students; EDA correlated with performance only without AI. Students, not
professionals; no comprehension test; N not in the abstract.

**Brandebusemeyer, Zunic, Zimmermann, Schimmer, Arnrich, "Developers'
Experience with Generative AI Beyond Productivity Assessment"**
([arXiv:2607.02337](https://arxiv.org/abs/2607.02337), v2 2026-07-09; abstract
page read; preprint). Mixed-methods field study of professional developers
combining controlled sessions with natural work periods; Copilot in-code
suggestions versus chat. Findings are about satisfaction, workload and
interaction-type preference ("combining these interaction types within a
single task diminishes benefits"; "perceived cognitive load arises from AI
interaction, while perceived productivity depends on AI output quality"). N
not in the abstract; no comprehension or skill measure.

**Huang, Reyna, Lerner, Xia, Hempel, "Professional Software Developers Don't
Vibe, They Control: AI Agent Use for Coding in 2025"**
([arXiv:2512.14012](https://arxiv.org/abs/2512.14012), v2 2026-08-18; abstract
page read; preprint). Field observations N = 13 and qualitative surveys
N = 99 of experienced developers. Finding: developers "retain their agency in
software design and implementation out of insistence on fundamental software
quality attributes" and "enjoy working with agents as source of collaboration
rather than complete delegation". Qualitative; no comprehension measure; the
ownership-adjacent content is the stated preference for control.

**Choudhuri, Bird, Badea, Gerosa, Sarma, "You Shall Not Pass! Where and Why
Developers Draw The Line on AI Autonomy"**
([arXiv:2607.00533](https://arxiv.org/abs/2607.00533), v2 2026-07-11; abstract
page and HTML read; preprint). 448 Microsoft developers (1,193 responses from
a stratified sample of 8,000; 14.9% response rate) rated tasks in five SDLC
categories on value, identity, accountability and demands and described the AI
involvement they would accept, coded to five autonomy levels. Cumulative link
mixed model on 1,476 task ratings: task identity β = −0.13 (p = 0.017), AI
experience β = 0.26 (p = 0.007), risk tolerance β = 0.33 (p = 0.013);
accountability lowered the odds of letting AI produce artefacts (OR = 0.82,
p = 0.027); identity lowered the odds of letting AI decide without approval
(OR = 0.78, p = 0.01) while task demand raised them (OR = 1.20, p = 0.03).
The paper warns of "cognitive debt accrual" when "skill gaps hide until AI
fails" and quotes a participant: "I do not want to hand AI a design and have
it write all code because I enjoy coding". Limits stated: one AI-forward
company, cross-sectional, self-selection, single-item appraisals, LLM-assisted
coding of free text. Relevant to ownership as identity; no comprehension
measure. The same group's earlier survey, **"AI Where It Matters"**
([arXiv:2510.00762](https://arxiv.org/abs/2510.00762), v2 2026-01-02; abstract
page read; *ICSE-SEIP 2026*), N = 860, reports demand for AI in coding,
testing and administrative work and "resistance to AI in mentoring and
relationship-focused work".

**Murphy-Hill, Butler, Savelieva, "Adoption and Impact of Command-Line AI
Coding Agents: A Study of Microsoft's Early 2026 Rollout of Claude Code and
GitHub Copilot CLI"** ([arXiv:2607.01418](https://arxiv.org/abs/2607.01418), v1
2026-07-01; abstract page read; preprint). Telemetry on "tens of thousands" of
engineers over four months; adopters "merged roughly 24% more pull requests
than they would have otherwise" (95% CI 14.5–33.7% per the search summary;
not verified in the PDF). No skill, comprehension or ownership measure.

**Sergeyuk et al., "Evolving with AI: A Longitudinal Analysis of Developer
Logs"** ([arXiv:2601.10258](https://arxiv.org/abs/2601.10258), v2 2026-03-30;
abstract page read; *ICSE 2026* research track). Two-year IDE telemetry from
800 developers plus a survey of 62 professionals across productivity, code
quality, editing, reuse and context switching: "AI users produce substantially
more code but also delete significantly more". No comprehension measure.

**Vukovic et al., "Usage, Effects and Requirements for AI Coding Assistants
in the Enterprise"** ([arXiv:2601.20112](https://arxiv.org/abs/2601.20112);
abstract page read; ICSE 2026 LLM4Code workshop). Survey of 57 developers at
one company plus 35 prior surveys; requirements-oriented; nothing on
comprehension.

**Baltes, Cheong, Treude, "'An Endless Stream of AI Slop'"**
([arXiv:2603.27249](https://arxiv.org/abs/2603.27249), v4 2026-08-28; abstract
page read; preprint). Qualitative coding of 1,154 Reddit and Hacker News
posts into 15 codes; one cluster is "Quality Degradation (damage to
codebases, knowledge resources, and developer competence)" and another names
"craft erosion". Discourse, not measurement.

**Shukla and Sharma, "Psychological Ownership in AI-Assisted Software
Development: A Qualitative Study of Developer's Authorship, Responsibility and
Cognitive Engagement in Collaborative Projects"** (Stockholm University
master's thesis, spring 2026;
[DiVA full text](https://su.diva-portal.org/smash/get/diva2:2073688/FULLTEXT01.pdf),
read from the PDF). Eleven semi-structured interviews with professional
developers in Sweden spanning startups and regulated banking, reflexive
thematic analysis. Themes: authorship migrated "from syntax construction to
architectural intent"; a "responsibility paradox where developers feel 100%
liable for code they did not manually author"; a "cognitive engagement gap,
where frictionless speed leads to mental model decay, though institutional
guardrails in regulated industries were found to paradoxically preserve
cognitive engagement through forced manual friction"; ownership maintained by
"appropriation practices, such as intentionally choosing manual pain during
onboarding or conducting high-intensity fidelity reviews". Not peer reviewed;
n = 11; the closest interview evidence found on ownership of agent-written
code in professionals, which the evidence note listed as absent.

**Seo, Deldari, Mentis, "Whose Code Is It? How AI Autonomy Reshapes Ownership,
Responsibility, and Disclosure in AI-Assisted Programming"**, *IUI 2026*,
[doi:10.1145/3742413.3789121](https://dl.acm.org/doi/10.1145/3742413.3789121).
The ACM page returned 403; title, authors and venue only. A search result
associated it with arXiv:2609.09022, but that identifier is Camargo's
research note "It Is Not My Code Anymore"
([arXiv:2609.09022](https://arxiv.org/abs/2609.09022), 2026-09-08; abstract
read), which "reports no new empirical results". Seo et al.'s design and
sample are therefore unknown here.

**Anthropic, "How AI is transforming work at Anthropic"**
([anthropic.com](https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic),
2025-12-02; page read). Internal survey N = 132 engineers and researchers plus
53 interviews, data from August 2025. Skill-relevant quotations: "When
producing output is so easy and fast, it gets harder and harder to actually
take the time to learn something"; "skills atrophying as [they] delegate
more"; "You're going to spend time reading docs and code that isn't directly
useful for solving your problem — but this entire time you're building a model
of how the system works"; "More than half said they can 'fully delegate' only
between 0-20% of their work". Limits stated by Anthropic: convenience and
purposive sampling, non-anonymous responses, recall over 12 months. Vendor
self-study; no comprehension measure. Its companion, **"How Claude Code is
used in practice"**
([anthropic.com](https://www.anthropic.com/research/claude-code-expertise),
2026-06-16; page read), analyses ~400,000 sessions from ~235,000 people
(October 2025–April 2026): "people make about 70% of the planning decisions
but only 20% of the execution decisions"; each prompt triggers "around 10
actions"; verified success 15% for novice sessions versus 28–33% for
intermediate and expert. Classifier-based; no human outcome measured.

**Not code, but professional-adjacent and new since the notes.** Liu,
Christian, Dumbalska, Bakker, Dubey, "AI Assistance Reduces Persistence and
Hurts Independent Performance" ([arXiv:2604.04721](https://arxiv.org/abs/2604.04721);
the adjacent note lists it as "seen but not read"): RCTs, N = 1,222, on
mathematical reasoning and reading comprehension, not code; after AI removal
the fraction-task solve rate was 0.57 versus 0.73 and skip rate 0.20 versus
0.11 (figures from the search summary; abstract not re-fetched). Choudhuri,
Sanchez, Burnett, Sarma, "Thinking Less, Trusting More"
([arXiv:2601.22430](https://arxiv.org/abs/2601.22430), v2 2026-04-10; abstract
page read): PLS-SEM survey of 299 STEM students across five universities;
high-trust routine users reported "significantly lower cognitive engagement";
students, self-report.

**Novice studies with a retention interval.** Gardella, Prather, Leinonen,
Denny, Pettit, Riggs, "Fast and Forgettable: A Controlled Study of Novices'
Performance, Learning, Workload, and Emotion in AI-Assisted and Human Pair
Programming Paradigms" ([arXiv:2604.18538](https://arxiv.org/abs/2604.18538),
v1; HTML read; *ICER 2026*). N = 22 (11 pairs) from CS2/CS3 at a selective US
university, within-subjects and counterbalanced: 20-minute sessions with a
human partner or with GitHub Copilot, then a solo retest of the same HumanEval
tasks about a week later, with NASA-TLX and a valence/arousal measure. Session
1: "roughly 14 points higher out of 100 when the teammate was Copilot"
(p_adj < .001, g = .99); retest: "Relative retest performance was worse for
the AI condition, a marginally significant difference (p < .05 < p_adj < .1)"
— coefficient −18.88, p = .015, p_adj = .054 after Benjamini–Hochberg,
g = −1.13; mental demand, temporal demand and effort lower with AI (g −1.21 to
−1.28); valence change +0.36 with a human versus −0.82 with AI (p < .001).
Limits stated: small sample, one university, convenience pairs, fixed time
limits, HumanEval simplicity. This is the first study in these notes with a
delay between AI-assisted work and the test, and it is on novices and toy
tasks. Brender et al., "Reflective Dialogue or Prompt Refinement?"
([arXiv:2607.03303](https://arxiv.org/abs/2607.03303); abstract page read;
*AIED 2026*, best paper per the comments line): 66 graduate robotics students,
quasi-experimental, six weeks with a Socratic or a prompt-refinement tutor
then three weeks of unconstrained LLM use (52 followed up); "similar immediate
performance" but Socratic guidance produced higher learning gains and
"understanding-driven prompting strategies" afterwards. Barth et al., "When
More Engagement Doesn't Mean More Learning: LLM Tutors and Self-Regulated
Learning in CS1" (*ICER 2026*; published as "Steering AI Tutors Through System
Prompts",
[doi:10.1145/3765964.3811656](https://dl.acm.org/doi/10.1145/3765964.3811656)):
a preregistered six-week within-subjects crossover in a CS1 class of over
1,500 with three tutor prompts; the ACM page returned 403 and the figures are
not recorded here.

What remained unfound: any RCT or quasi-experiment on professionals with a
comprehension, transfer or retention outcome beyond Shen and Tamkin; any
quantitative ownership instrument on professionals; anything from Google
Research or GitHub Next on comprehension (the Google results were code-review
assistance and readability; GitHub's were adoption).

## Target 2: teach-back, explain-in-plain-English, and LLM-graded explanations

Searched: WebSearch on "explain in plain English" + LLM grading, self-explanation
+ AI-generated code, teach-back + programming, oral assessment/code review
interviews, LLM-as-a-judge for code explanations; arXiv HTML search for
"explain in plain English"; the ICER 2026 accepted-papers list; SIGCSE TS 2026.

**No study was found that applies a teach-back or explain-it-back gate to
AI-generated production code with professionals beyond Sankaranarayanan**
([hand-off checks, explain-it-back](track-hand-off-checks.md#other-explain-it-back-work-found)).
What was found is classroom work, plus grading-validity evidence beyond CGBG.

**Oral explain-back in courses under AI.** Fowles, Falor, Bhattarai, Edwards,
Poulsen, "Combating Harms of Generative AI in CS1 with Code Review Interviews
and a Flipped Classroom" ([arXiv:2605.21374](https://arxiv.org/abs/2605.21374),
v1 2026-05-20; abstract page read; preprint): weekly oral code-review
assessments "incentivize students to understand their submitted code,
regardless of whether or not the code was generated by AI tools"; three
semesters of exam scores, keystroke logs and surveys; "a statistically
insignificant increase in average scores for Fall 2025 compared to previous
semesters"; keystroke logs "show a significant increase in characters pasted
per total characters input" in Fall 2025; the authors read this as students
"still show adequate understanding of material covered in written exams,
despite dramatic increases in LLM usage". Quasi-experimental across cohorts;
enrolment not in the abstract. A SIGCSE TS 2026 talk, "AI-Driven Oral
Examinations for Code Assessment: Evaluating Understanding Beyond the Commit"
([doi:10.1145/3770761.3777032](https://doi.org/10.1145/3770761.3777032)),
describes chat-based oral exams as a scalable substitute; ACM returned 403, so
title and venue only. Frankford, Cikalleshi, Breu, "Chatbot-Based Assessment
of Code Understanding in Automated Programming Assessment Systems"
([arXiv:2604.07304](https://arxiv.org/abs/2604.07304); abstract page read;
*CSEDU 2026*) is a scoping review proposing a "Hybrid Socratic Framework"; no
agreement statistics.

**LLM-graded explanations beyond CGBG.** The two ITiCSE 2025 papers the
hand-off note listed as "not read" were read in HTML:

- Smith, Fowler, Denny, Zilles, "Counting the Trees in the Forest"
  ([arXiv:2503.12216](https://arxiv.org/abs/2503.12216); *ITiCSE 2025*). An
  LLM segments the student's description and the code and classifies the
  response as multi-structural (line by line) or relational by segment-count
  threshold. 841 of 889 enrolled students; 200 responses per question
  hand-labelled for two questions (human–human κ = 0.80 and 0.83); LLM versus
  human "81% agreement, a Cohen's κ of 0.61, an F1 score of 0.80" after
  post-processing (κ 0.30 before). Limit stated: whether the segmentation
  "aligns with human expectations" is open.
- Smith, Fowler, Denny, Zilles, "ReDefining Code Comprehension: Function
  Naming as a Mechanism for Evaluating Code Comprehension"
  ([arXiv:2503.12207](https://arxiv.org/abs/2503.12207); *ITiCSE 2025*).
  Replaces the prose explanation with a function name, graded by generating
  code from the name (GPT-4o, temperature 0; one attempt, or five of five must
  pass). 366 students, 647 responses to four questions; SOLO coding by two
  researchers κ = 0.75; 2PL IRT discrimination a ≥ 0.65 on all items. Limit
  stated: four questions, one course, week 12 of 16.

Lekshmi-Narayanan, Hassany, Brusilovsky, "Exploring the Effectiveness of
Using LLMs for Automated Assessment of Student Self-Explanations in
Programming Education" ([arXiv:2605.21614](https://arxiv.org/abs/2605.21614),
v1 2026-05-20; HTML read; preprint): binary correct/incorrect scoring of
line-by-line self-explanations from SelfCode2.0 (60 students, 1,854 pairs of
which only 60 incorrect, so 1,794 synthetic negatives were generated with
GPT-OSS 20B); GPT-3.5-Turbo-16k reached F1 = 0.98, accuracy 0.96, against
F1 0.69–0.72 for Deep-Tutor, RoBERTa and GPT sentence-embedding similarity.
Limits stated: synthetic negatives "briefly verified with 2 annotators using a
sample of 100 explanations", one language, no prompt optimisation. The
classification is of worked-example explanations, not of code the student
generated with AI. For comparison, an LLM-as-judge framework for human–AI
co-creation in coding contests (Amin et al.,
[arXiv:2604.27727](https://arxiv.org/abs/2604.27727), 2026-04-30; abstract
page read) reports mean pairwise Cohen's κ = 0.16 and Fleiss' κ = 0.07 among
LLM judges — it judges code artefacts, not human explanations, and is cited
only as a reliability datum.

Other relevant ICER 2026 titles from the accepted list
([2026.icer.acm.org](https://2026.icer.acm.org/info/accepted-papers)), not
read: "When AI Is Wrong on Purpose: How Students Respond to Buggy GenAI Code"
(Pădurean et al.), "Scaffolding Autocomplete: Improving Guidance for Learners
using Generative Code Suggestions" (Prather et al.), and "Measuring Student
Self-Efficacy for Programming with Generative AI" (Prather et al.).

What remained unfound: any teach-back on AI-generated code in a professional
setting; any judge–human agreement figure for a SOLO-style gate on
AI-generated code (Sankaranarayanan still reports none); any explain-back
study with a delayed test.

## Target 3: human evaluations of generated wikis, maps and tours; accuracy of generated documentation

Searched: WebSearch on DeepWiki / Code Wiki / Codemaps / walkthrough / code
tour + user study or accuracy; arXiv HTML search for "DeepWiki"; WebSearch on
hallucination in code summaries and documentation with human annotation.

**Human evaluations of generated tours — two found, both 2026.**

- Balfroid, Albert, Aliti, Devroey, Vanderose, "How Developers Experience
  Debugging Unfamiliar Codebases with Code Tours Generated and Evaluated by
  Local LLMs" ([arXiv:2607.26987](https://arxiv.org/abs/2607.26987), v2
  2026-08-05; abstract page read; preprint). Twenty-six developers, 26 code
  tours generated from real 2025 Java bug-fix commits by open-weight models,
  each tour judged by two LLMs (52 configurations), think-aloud and interviews
  coded by three authors. Findings: developers "preferred tours that scaled
  detail with the code length, avoided merely restating code, were easily
  scannable, and adopted a guiding tone"; they "trusted descriptions they
  perceived as human-written more than those they believed were AI-generated";
  and "LLM-generated annotations of tour quality were unreliable: sycophancy,
  confabulation, and incoherence were pervasive". Qualitative; no
  comprehension or task-outcome measure reported in the abstract. This is the
  successor to the FSE 2025 research plan the maps note cites.
- Kara et al., "LACY: Simulating Expert Mentoring for Software Onboarding with
  Code Tours" ([arXiv:2603.25391](https://arxiv.org/abs/2603.25391), v1
  2026-03-26; abstract page and HTML read; "accepted … at ACM FSE 2026 Industry
  Track"). A hybrid system at Beko in which experts' voice explanations are
  captured into tours, with AI generation, comprehension quizzes and
  dashboards, deployed on a 30K-line legacy finance system. Evaluation: two
  experts (16 and 22 years) and five learners (three new hires, two
  transfers; mean 4.6 years' experience), within-subjects, counterbalanced,
  ~60 minutes per condition on different features. Ten-question quizzes:
  "83% quiz scores versus 57%" for expert-guided versus AI-only tours; an
  expert rubric on learners' verbal explanations gave 79% versus 76.8%.
  Limits stated: self-report subjectivity, tours "may become outdated as
  codebases evolve", small pool. n = 5 learners; the only human quiz result on
  a generated tour found.

**Generated wikis.** No human evaluation of DeepWiki, Google Code Wiki,
Codemaps, Swimm or a comparable product was found; the arXiv search for
"DeepWiki" returns only CodeWiki
([arXiv:2510.24428](https://arxiv.org/abs/2510.24428); *ACL 2026 Findings*),
whose CodeWikiBench is LLM-scored (68.79% versus DeepWiki's 64.06%), as the
maps note already records. SWD-Bench's identifier is now retrievable: Wang,
Hu, Gao, Gao, Peng, "Evaluating Repository-level Software Documentation via
Question Answering and Feature-Driven Development"
([arXiv:2604.06793](https://arxiv.org/abs/2604.06793), v1 2026-04-08; abstract
page read); 4,170 entries from pull requests; documentation quality is
measured by an LLM's ability to detect, localise and complete functionality,
and "high-quality documentation improved an issue-solving agent's performance
by 20 percent"; no human reader. Alebachew, "AI-Guided Exploration of
Large-Scale Codebases" ([arXiv:2508.05799](https://arxiv.org/abs/2508.05799);
abstract page read) is a prototype with "empirical evaluation" as future work.

**Walkthroughs on pull requests — observational, not a user study.** Xiao,
Hata, Treude, Matsumoto, "Generative AI for Pull Request Descriptions:
Adoption, Impact, and Developer Interventions"
([arXiv:2402.08967](https://arxiv.org/abs/2402.08967); HTML read; *PACMSE /
FSE 2024*). 18,256 PRs with Copilot-for-PRs descriptions across 146
repositories against 54,188 other PRs in the same repositories: Copilot
descriptions were associated with a reduction of 19.3 hours in review time
(p < 0.001) and 1.57× the odds of merge (95% CI 1.35–1.84); in 311 PRs with
1,437 revisions developers edited the generated text, most often adding
template information (22.8%) and links (22.7%), then intent (12.8%) and
testing information (9.2%); deletion was the commonest edit (22.9%). Limits
stated: bot detection, manual-coding subjectivity, confounders, beta-period
early adopters. Review time is not comprehension, and the effect is
correlational. Two 2026 mining studies on the AIDev dataset add that agent PR
description style correlates with reviewer engagement and merge (Watanabe et
al., [arXiv:2602.17084](https://arxiv.org/abs/2602.17084), abstract page read)
and that "most AI-generated PRs receive no review and, when reviewed, are
largely dominated by AI agents rather than humans" (Duma et al.,
[arXiv:2605.02273](https://arxiv.org/abs/2605.02273), abstract page read;
*EASE 2026*). No study asks whether a reader of a walkthrough understood the
change.

**Factual accuracy of generated code documentation, 2024–2026.** The
literature measures hallucination in code *summaries* with detectors, not the
error rate readers meet in a product:

- Maharaj et al., "ETF: An Entity Tracing Framework for Hallucination
  Detection in Code Summaries" ([arXiv:2410.14748](https://arxiv.org/abs/2410.14748),
  v4 2025-09-06; abstract page read; *ACL 2025* main). Static analysis plus
  LLM entity verification on CodeSumEval, "~10K samples" curated for
  hallucination detection; detector F1 73%. The abstract gives no base rate
  of hallucination in the summaries.
- Bae et al., "ReFEree: Reference-Free and Fine-Grained Method for Evaluating
  Factual Consistency in Real-World Code Summarization"
  ([arXiv:2604.10520](https://arxiv.org/abs/2604.10520), v1 2026-04-12;
  abstract page read; *ACL 2026* main). Segment-level consistency scoring
  against a benchmark "with human-annotated factual consistency labels";
  "15-18% improvement over the previous state-of-the-art" in correlation with
  human judgement. Base rates not in the abstract.

No study measuring hallucination rates in DeepWiki-style repository wikis, or
their effect on a reader's model, was found; the rationale note's statement
that neither vendor publishes an accuracy evaluation
([rationale, accuracy](track-rationale-as-artifact.md#accuracy-of-generated-documentation-and-rationale))
stands.

## Target 4: comprehension effects of approval gates and learning modes

Searched: WebSearch on plan/hunk/command approval + comprehension, Claude Code
Learning/Explanatory output style evaluation, Copilot learner guidance, Cursor
Ask/Plan mode studies, agent autonomy + checkpoints + understanding; the
Claude Code repository's plugin README; Anthropic's auto-mode post.

**No study measures comprehension as a function of an approval gate or a
learning mode.** The in-loop note's statement stands
([in-loop friction, arguments and evidence](track-in-loop-friction.md#arguments-and-evidence)).
What was found is approval-behaviour telemetry from one vendor, a checkpoint
study outside code, a plan-mode study outside code, and interview work.

**Anthropic on permission prompts.** "Auto mode is now the default in Claude
Code for Pro, Max, and Team plans"
([claude.com/blog](https://claude.com/blog/auto-mode-default-in-claude-code),
2026-08-07; page read). "Research conducted internally suggests that users
approve 97% of permission prompts in Claude Code"; "when Claude presents a
plan for approval, users reject 39% of them. But for individual permissions
requests, the rejection rate is only 3%"; "an approval rate that high suggests
many users are clicking through reflexively rather than reviewing each
command"; in an internal exercise with dangerous commands, "they blocked
about 17% of dangerous commands early in a session, dropping to about 5% after
50 or more prior prompts"; "As of June 2026, 49.5% of active CLI users have
manually created a Bash allow-rule — 5% allow any shell command outright";
"62% of users have used `bypassPermissions` or clicked 'don't ask again'";
"25% of interactive sessions start in bypass permissions mode". These are
vendor telemetry without method detail (no N, period, or definition of
"dangerous"), and they measure blocking of risky commands, not understanding
of code. Note that Liu, Zhao, Shang, Shen, "Dive into Claude Code"
([arXiv:2604.14228](https://arxiv.org/html/2604.14228v1); HTML read) quotes the
figure as "users approve 93% of permission prompts" citing a "Hughes, 2026"
source that the HTML truncates; the vendor post says 97%. Which is right, or
whether they are different measurements, is unresolved.

**Checkpoint placement, outside code.** Zhou, Roy, Gupta, Weitekamp,
MacLellan, "When Should Users Check? Modeling Confirmation Frequency in
Multi-Step Agentic AI Tasks" ([arXiv:2510.05307](https://arxiv.org/abs/2510.05307),
v3 2026-05-07; abstract page read; *CHI 2026*). Formative study N = 8 finds a
"Confirmation-Diagnosis-Correction-Redo" pattern; a decision-theoretic
scheduler of confirmation points is evaluated within-subjects with 48
participants monitoring agents: "81 percent of participants preferred our
intermediate confirmation approach over the confirm-at-end approach" and
completion time fell 13.54%. Not coding; time and preference only.

**Plan mode, outside code.** Kumar, Dutta, Gulwani, Soares, Sarkar,
Murphy-Hill, "Plans Work in Mysterious Ways: Evaluating a Plan Mode for
Spreadsheet Agents" ([arXiv:2607.23670](https://arxiv.org/abs/2607.23670), v2
2026-07-29; abstract page read; *IEEE VL/HCC 2026*). Within-subjects N = 24
spreadsheet programmers, plan mode versus no plan: "similar task outcomes"
but "a reduction in refinement and a better perception of the tool across
dimensions of creativity support and human-machine collaboration". No
comprehension measure; the only controlled evaluation of a plan mode found.

**Oversight practice, interviews.** Dhanorkar, Passi, Vorvoreanu, "Human
oversight of agentic systems in practice"
([arXiv:2606.05391](https://arxiv.org/abs/2606.05391), v1 2026-06-03;
abstract page read; preprint): 17 experienced developers; four forms of
oversight work — "a priori control, co-planning, real-time monitoring, and
post hoc review" — and the challenge of "difficulty reviewing agent-generated
code", met with heuristics such as "using test results as guarantees for code
correctness". Shukla, Feng, Wang, Rostami, Zhang, "Hedwig: Dynamic Autonomy
for Coding Agents Under Local Oversight"
([arXiv:2605.11495](https://arxiv.org/abs/2605.11495); abstract page read;
*CAIS 2026* demo): a formative survey of 21 engineers reporting "frustration
with calibrating autonomy" and evolving oversight preferences; no outcome
study. Mitchell, Ghosh, Passi, "AI Agents Push Humans Out of the Loop"
([arXiv:2608.23642](https://arxiv.org/abs/2608.23642), v3 2026-09-06; abstract
page read) is a position paper arguing that agent design "contribute[s] to
[the] degradation" of oversight capacity; no data. Schmalbach, "Software
Delegation Contracts: Measuring Reviewability in AI Coding-Agent Work"
([arXiv:2606.17099](https://arxiv.org/abs/2606.17099); abstract page read)
reports evidence-sufficiency gains from explicit contracts (+0.83 on a
five-point scale, p < 0.0001) but its 192 reviews were by "condition-blinded
model-based reviewers", not humans. Lulla et al., "Loop Engineering"
([arXiv:2608.21884](https://arxiv.org/abs/2608.21884), v2 2026-08-26;
abstract page read) mines 36,710 repositories and ends "by outlining a
planned controlled study of agent autonomy levels and their effect on effort
and outcomes" — planned, not run, and framed on effort rather than
understanding.

**Learning modes.** The `learning-output-style` plugin README
([github.com/anthropics/claude-code](https://github.com/anthropics/claude-code/blob/main/plugins/learning-output-style/README.md);
read) states the rationale — "Learning by doing is more effective than passive
observation" — and no evaluation; the in-loop note already quotes the hook
text ([in-loop friction, Claude Code](track-in-loop-friction.md#claude-code)).
A comprehension-improvement percentage for Learning mode circulates in
third-party guides surfaced by search, attributed to an unnamed instructor
with no source; it is unsourced and not recorded as a figure here. No
evaluation of GitHub Copilot's learner guidance or of Cursor's Ask or Plan
modes was found; the only Cursor-mode data surfaced is a screen-reader user
study noting that 12 of 15 participants preferred Ask mode "because it
required explicit confirmation before modifying files"
([arXiv:2506.13270](https://arxiv.org/abs/2506.13270); search summary only,
not read).

## Target 5: retention, spacing, and spaced repetition on a codebase

Searched: WebSearch on spaced repetition / retrieval practice + codebase,
professionals, LLM-generated questions; forgetting + source code + developers;
delayed-test studies of programmers; GitHub repository search for "spaced
repetition codebase", "anki codebase", "flashcards git diff", "spaced
repetition code review"; HN Algolia for "spaced repetition codebase" and "anki
for your codebase".

**No controlled study of spaced retrieval on a real codebase, in professionals
or students, was found**; the durable-model note's statement stands. What was
added:

- **A pre-AI field measurement of code memory over two months.** Fekete and
  Porkoláb, "Field Experiment of the Memory Retention of Programmers Regarding
  Source Code", *Studia Universitatis Babeș-Bolyai Informatica* 68(1), 2023,
  [doi:10.24193/subbi.2023.1.05](https://www.cs.ubbcluj.ro/~studia-i/journal/journal/article/view/89)
  (journal page read; N not on the page). CS MSc students implemented a small
  feature in a C++ project and repeated the same task two months later after a
  questionnaire on what they remembered: returning students "solved the task
  faster in the second trial" while "the vast majority of students could not
  precisely remember more than two or three identifiers from the original
  code"; compared to Ebbinghaus's curve. Complements Krüger et al. (ICSE 2018)
  in the durable-model note with a re-test rather than a survey; students,
  not professionals.
- **The one AI-era delayed test** is Gardella et al.'s one-week retest
  (Target 1): novices, HumanEval tasks, Copilot as partner.
- **LLM-generated retrieval practice, not code.** An, Liu, Acharya, Hashmi,
  "Enhancing Student Learning with LLM-Generated Retrieval Practice Questions"
  ([arXiv:2507.05629](https://arxiv.org/abs/2507.05629), v2 2025-07-29;
  abstract page read; preprint): about 60 students in two data-science
  courses, a week with LLM-generated multiple-choice retrieval practice versus
  a week without, 89% versus 73% accuracy; the authors say "instructors must
  still manually verify and revise" the questions. Not spaced, not code.
- **Prototypes, none evaluated.** The GitHub API returns five repositories for
  "spaced repetition codebase": `nessielabs/codequiz` (13 stars, already in the
  durable-model note), `maxwellyoung/doomscroll` ("Swipe-to-learn spaced
  repetition for codebases", a React Native "product experiment", 0 stars,
  created 2026-02-18; [README](https://github.com/maxwellyoung/doomscroll)),
  `scawful/cartograph` ("Local-first codebase tutorial platform with guided
  reading paths", 1 star, 2026-03-30), and `tompicamoles/learning-system`
  (Claude Code skills for skill-up courses, 0 stars). "anki codebase" adds
  `Zasder3/py2anki` ("Transform entire codebases into Anki flashcards", 1
  star, created 2025-01-10; [README](https://github.com/Zasder3/py2anki), one
  line). None publishes usage or learning data. HN Algolia returns no new
  Show HN beyond Doculearn (already in the durable-model note) and an
  "Ask HN: How do you retain both technical and domain knowledge long-term?"
  (4 points, 2025-04-24).

What remained unfound: any professional-sample retention study with an
interval longer than a session under AI assistance; any study of spacing or
retrieval on a living repository; any invalidation-aware scheduler.

## Target 6: motivation, ownership, and flow under agentic delegation, n > 20 professionals

Searched: WebSearch on flow / job satisfaction / meaningfulness / ownership /
psychological ownership / self-determination + professional developers +
agents, 2026; Stack Overflow, JetBrains, DORA and DX 2026 reports; Wiley and
arXiv for Altork 2026.

Three sources meet the threshold, all self-report and none an experiment:

- **Vella and Blincoe (Target 1)**: matched cohort n = 95 professionals over
  six months; flow-state and cognitive-load erosion with stable productivity
  perception — the only longitudinal flow measure found.
- **Choudhuri et al. (Target 1)**: 448 Microsoft developers; task identity and
  accountability lower the autonomy developers accept; the paper grounds this
  in "people experience work as meaningful when they author it and when they
  hold the decisions that govern it". Cross-sectional; ownership as
  identity-appraisal, not a psychological-ownership scale.
- **Anthropic internal study (Target 1)**: n = 132 survey plus 53 interviews of
  the vendor's own staff; enjoyment quotations ("Spending your day prompting
  Claude is not very fun or fulfilling"; "I thought that I really enjoyed
  writing code, and instead I actually just enjoy what I get out of writing
  code") alongside productivity gains; convenience sample, non-anonymous.

Below threshold or not professionals: Huang et al. (99 survey respondents,
qualitative; Target 1); Shukla and Sharma (11 interviews; Target 1); Alami et
al. and Feng et al., already in the [adjacent
note](adjacent-literatures.md#developer-studies-applying-these-frameworks);
Gurgul, Gubela, Lessmann, "The State of Generative AI in Software
Development" ([arXiv:2603.16975](https://arxiv.org/abs/2603.16975), v1
2026-03-17; abstract page read), a survey of 65 developers on task benefits
with a stated risk of "skill erosion" but no motivation instrument; Gardella
et al.'s valence and arousal results (22 novices); Tran, Harper, Price, "Why
Put In This Much Effort? How AI Availability Shapes Students' Motivation in
Introductory Programming" (*ICER 2026*, from the accepted list; not read);
Altork, "Motivation and Psychological Well-Being of Software Engineers in the
Generative AI Era: An Analysis of the Online Discourse", *Journal of Software:
Evolution and Process* (2026),
[doi:10.1002/smr.70162](https://onlinelibrary.wiley.com/doi/10.1002/smr.70162)
— Wiley returned 403; per the search summary it is a thematic analysis of blog
posts, so discourse rather than a sample of people.

Industry reports touch the constructs without instruments that can be
checked: DX's "The State of AI Impact in Engineering: Q2 2026"
([getdx.com](https://getdx.com/blog/the-state-of-ai-impact-in-engineering-q2-2026/),
2026-07-22; page read) states "The Developer Experience Index (DXI) dropped
from 67 to 65 over four quarters" and "Change Confidence decreased by 6.1%"
across "500+ teams", and concedes that "comparing AI users against a non-user
control group is no longer a viable measurement strategy"; no N of engineers,
no item wording. JetBrains' "AI Coding Agents: Adoption Trends"
([blog.jetbrains.com](https://blog.jetbrains.com/research/2026/08/ai-coding-agent-adoption-2026/),
August 2026; page read), from the 2026 Developer Ecosystem Survey of "more
than 15,000 professional developers" fielded May–July 2026, reports adoption
only ("90% … at least weekly", "68% … daily"); the full 2026 report with
attitude items was not located. The Stack Overflow 2026 survey opened on
2026-06-23 ([stackoverflow.blog](https://stackoverflow.blog/2026/06/23/the-2026-developer-survey-is-now-open-for-human-developers-only/));
the figures search results attach to it are the 2025 numbers already in the
evidence note, so nothing from 2026 is recorded here.

What remained unfound: any validated psychological-ownership, intrinsic
motivation or flow scale administered to more than 20 professionals under
agentic delegation; any experiment manipulating delegation and measuring
motivation.

## Corrections proposed

Wrong or superseded sentences in the existing notes, with the evidence. Each
is a proposal; the notes are not edited here.

1. **adjacent-literatures.md, Dead ends**: "Feng et al. 2026 has no arXiv ID;
   read from the author PDF; the ACM landing page was not fetched (403)." —
   Superseded: the paper is
   [arXiv:2602.00496](https://arxiv.org/abs/2602.00496), submitted 2026-01-31,
   revised 2026-02-11, comments line "To appear in CHI'26" (abstract page
   read).
2. **track-explorable-maps.md, Dead ends**: "SWD-Bench's arXiv identifier was
   not retrieved (OpenAlex record without DOI)." — and the Evidence section's
   "(OpenAlex record; arXiv id not retrieved)". Superseded:
   [arXiv:2604.06793](https://arxiv.org/abs/2604.06793), Wang, Hu, Gao, Gao,
   Peng, 2026-04-08 (Target 3).
3. **track-explorable-maps.md, Dead ends**: "No evaluation with humans of
   DeepWiki, Code Wiki, Codemaps, Swimm Explore, Understand Anything,
   GitDiagram, CodeBoarding, or any AI-generated tour was found". —
   Superseded for tours: Balfroid et al.
   ([arXiv:2607.26987](https://arxiv.org/abs/2607.26987), 26 developers,
   qualitative) and LACY
   ([arXiv:2603.25391](https://arxiv.org/abs/2603.25391), FSE 2026 Industry, 5
   learners, quiz 83% versus 57%) both evaluate LLM-generated code tours with
   humans (Target 3). The wiki half of the sentence stands.
4. **track-explorable-maps.md, Evidence**: "The code-tours plan lists
   automatic evaluation as an open challenge" — still true of the 2025 plan,
   but the same group's 2026 study found LLM evaluation of tours "unreliable:
   sycophancy, confabulation, and incoherence were pervasive"
   ([arXiv:2607.26987](https://arxiv.org/abs/2607.26987)); a pointer is
   proposed.
5. **track-hand-off-checks.md, Evidence, item 8**: "Walkthrough A/B. None
   found. CodeRabbit, Sourcery, and GitHub publish no outcome data on
   walkthroughs" — the vendor half stands; the sentence should acknowledge Xiao
   et al. (*FSE 2024*, [arXiv:2402.08967](https://arxiv.org/abs/2402.08967)),
   an observational study of 18,256 Copilot-for-PRs descriptions with review
   time −19.3 h and merge odds 1.57× — not an A/B, and not a comprehension
   measure, but outcome data on a generated walkthrough (Target 3).
6. **evidence-and-mechanisms.md, Dead ends**: "every AI-specific study above
   is a single session of one hour or less, except METR … and Kosmyna" —
   true of the studies listed there; a supplement is proposed noting Gardella
   et al. ([arXiv:2604.18538](https://arxiv.org/abs/2604.18538), ICER 2026),
   the first AI-coding study found with a retention interval (one week, 22
   novices, Target 1), and Borg et al.
   ([arXiv:2507.00788](https://arxiv.org/abs/2507.00788)), a 151-participant,
   95%-professional two-phase experiment without a comprehension instrument.
7. **evidence-and-mechanisms.md, Dead ends**: "No study found on ownership or
   authorship perception of agent-written code in professional teams" — a
   supplement is proposed: Shukla and Sharma's eleven-interview thesis (not
   peer reviewed) and Choudhuri et al.'s 448-developer identity/accountability
   survey (Target 1); still no quantitative ownership instrument.
8. **track-in-loop-friction.md, Claude Code**: the section quotes the
   best-practices page's "After the tenth approval you're clicking through" —
   a supplement is proposed with the vendor's own telemetry (97% approval, 39%
   plan rejection versus 3% per-permission rejection, 17% → 5% blocking of
   dangerous commands after 50 prompts;
   [claude.com/blog](https://claude.com/blog/auto-mode-default-in-claude-code)),
   and a note that a secondary source quotes the approval rate as 93%
   (Target 4).

## Dead ends

- **APIs.** The arXiv export API (HTTP 429 "Rate exceeded"), Semantic Scholar
  (429, via curl and WebFetch), DBLP (bot challenge) and OpenAlex ("insufficient
  budget", resets midnight UTC) all refused scripted queries on 2026-09-13.
  Discovery therefore used WebSearch (about 65 calls), the arXiv HTML search
  page through WebFetch, the GitHub search API, and HN Algolia.
- **Paywalls.** ACM DL returned 403 for Seo et al. (IUI 2026), the SIGCSE TS
  2026 oral-examinations talk, and Barth et al. (ICER 2026); Wiley for Altork
  (JSEP 2026). These are cited from metadata or search summaries and marked.
- **Not found after bounded search.** A comprehension, transfer or retention
  RCT on professionals with agentic tools beyond Shen and Tamkin; a
  teach-back on AI-generated production code beyond Sankaranarayanan; a
  human evaluation of DeepWiki, Google Code Wiki, Codemaps, CodeRabbit or
  Sourcery walkthroughs, or Swimm; a hallucination base rate for
  repository-level generated documentation; any comprehension outcome for
  plan, hunk or command approval, for Claude Code's Learning or Explanatory
  styles, for Copilot learner guidance, or for Cursor Ask/Plan modes; any
  spaced-retrieval study on a codebase; any validated motivation, ownership
  or flow instrument on more than 20 professionals under delegation; anything
  on comprehension from Google Research or GitHub Next in 2026 (Google results
  were code-review assistance and readability tips; GitHub's were adoption).
- **Unresolved discrepancies.** 93% versus 97% approval of permission
  prompts (Target 4); the IUI 2026 paper's mis-association with
  arXiv:2609.09022 in a search result (Target 1); the CI on Microsoft's 24% PR
  lift is from a search summary, not the PDF.
- **Not read.** Barth et al. ICER 2026 body; Seo et al.; the ICER 2026 papers
  by Pădurean et al., Prather et al. and Tran et al.; the Anthropic internal
  study's appendix beyond the limitations list; Liu et al.
  ([arXiv:2604.04721](https://arxiv.org/abs/2604.04721)) beyond the search
  summary; the screen-reader study
  ([arXiv:2506.13270](https://arxiv.org/abs/2506.13270)).
- **Unsourced claims declined.** A "65% improvement in code comprehension
  assessments" for Claude Code's Learning mode appears in third-party guides
  with no named source; a "Hughes, 2026" reference for the 93% figure could
  not be resolved from the truncated HTML.

## References

- Alebachew, "AI-Guided Exploration of Large-Scale Codebases" (2025). https://arxiv.org/abs/2508.05799
- Altork, "Motivation and Psychological Well-Being of Software Engineers in the Generative AI Era", *JSEP* (2026). https://onlinelibrary.wiley.com/doi/10.1002/smr.70162
- Amin et al., "LLM-as-a-Judge for Human-AI Co-Creation" (2026). https://arxiv.org/abs/2604.27727
- An, Liu, Acharya, Hashmi, "Enhancing Student Learning with LLM-Generated Retrieval Practice Questions" (2025). https://arxiv.org/abs/2507.05629
- Anthropic, "How AI is transforming work at Anthropic" (2025-12-02). https://www.anthropic.com/research/how-ai-is-transforming-work-at-anthropic
- Anthropic, "How Claude Code is used in practice" (2026-06-16). https://www.anthropic.com/research/claude-code-expertise
- Anthropic, "Auto mode is now the default in Claude Code for Pro, Max, and Team plans" (2026-08-07). https://claude.com/blog/auto-mode-default-in-claude-code
- Anthropic, `learning-output-style` plugin README. https://github.com/anthropics/claude-code/blob/main/plugins/learning-output-style/README.md
- Bae et al., "ReFEree", *ACL 2026*. https://arxiv.org/abs/2604.10520
- Balfroid, Albert, Aliti, Devroey, Vanderose, "How Developers Experience Debugging Unfamiliar Codebases with Code Tours Generated and Evaluated by Local LLMs" (2026). https://arxiv.org/abs/2607.26987
- Baltes, Cheong, Treude, "'An Endless Stream of AI Slop'" (2026). https://arxiv.org/abs/2603.27249
- Barth et al., "Steering AI Tutors Through System Prompts", *ICER 2026*. https://dl.acm.org/doi/10.1145/3765964.3811656
- Borg et al., "Echoes of AI", ICSME 2025 Registered Reports. https://arxiv.org/abs/2507.00788
- Brandebusemeyer et al., "Developers' Experience with Generative AI Beyond Productivity Assessment" (2026). https://arxiv.org/abs/2607.02337
- Brender et al., "Reflective Dialogue or Prompt Refinement?", *AIED 2026*. https://arxiv.org/abs/2607.03303
- Burelli et al., "Using Biometrics to Understand AI-Assisted Coding Performance and its Perception" (2026). https://arxiv.org/abs/2606.20598
- Camargo, "It Is Not My Code Anymore" (2026). https://arxiv.org/abs/2609.09022
- Chen, Talwalkar, Brennan, Neubig, "Code with Me or for Me?", *CHI 2026*. https://arxiv.org/abs/2507.08149 ; https://dl.acm.org/doi/10.1145/3772318.3790850
- Choudhuri, Badea, Bird, Butler, DeLine, Houck, "AI Where It Matters", *ICSE-SEIP 2026*. https://arxiv.org/abs/2510.00762
- Choudhuri, Bird, Badea, Gerosa, Sarma, "You Shall Not Pass!" (2026). https://arxiv.org/abs/2607.00533
- Choudhuri, Sanchez, Burnett, Sarma, "Thinking Less, Trusting More" (2026). https://arxiv.org/abs/2601.22430
- Dhanorkar, Passi, Vorvoreanu, "Human oversight of agentic systems in practice" (2026). https://arxiv.org/abs/2606.05391
- Duma et al., "These Aren't the Reviews You're Looking For", *EASE 2026*. https://arxiv.org/abs/2605.02273
- DX, "The State of AI Impact in Engineering: Q2 2026" (2026-07-22). https://getdx.com/blog/the-state-of-ai-impact-in-engineering-q2-2026/
- Fekete and Porkoláb, "Field Experiment of the Memory Retention of Programmers Regarding Source Code", *Studia UBB Informatica* 68(1) (2023). https://www.cs.ubbcluj.ro/~studia-i/journal/journal/article/view/89
- Feng, Yun, Wang, "From Junior to Senior", *CHI 2026*. https://arxiv.org/abs/2602.00496
- Fowles, Falor, Bhattarai, Edwards, Poulsen, "Combating Harms of Generative AI in CS1 with Code Review Interviews and a Flipped Classroom" (2026). https://arxiv.org/abs/2605.21374
- Frankford, Cikalleshi, Breu, "Chatbot-Based Assessment of Code Understanding in Automated Programming Assessment Systems", *CSEDU 2026*. https://arxiv.org/abs/2604.07304
- Gardella, Prather, Leinonen, Denny, Pettit, Riggs, "Fast and Forgettable", *ICER 2026*. https://arxiv.org/abs/2604.18538
- Gurgul, Gubela, Lessmann, "The State of Generative AI in Software Development" (2026). https://arxiv.org/abs/2603.16975
- Huang, Reyna, Lerner, Xia, Hempel, "Professional Software Developers Don't Vibe, They Control" (2025/2026). https://arxiv.org/abs/2512.14012
- ICER 2026 accepted papers. https://2026.icer.acm.org/info/accepted-papers
- JetBrains, "AI Coding Agents: Adoption Trends" (2026-08). https://blog.jetbrains.com/research/2026/08/ai-coding-agent-adoption-2026/
- Kara et al., "LACY: Simulating Expert Mentoring for Software Onboarding with Code Tours", *FSE 2026 Industry*. https://arxiv.org/abs/2603.25391
- Kumar, Dutta, Gulwani, Soares, Sarkar, Murphy-Hill, "Plans Work in Mysterious Ways", *VL/HCC 2026*. https://arxiv.org/abs/2607.23670
- Lekshmi-Narayanan, Hassany, Brusilovsky, "Exploring the Effectiveness of Using LLMs for Automated Assessment of Student Self-Explanations in Programming Education" (2026). https://arxiv.org/abs/2605.21614
- Liu, Christian, Dumbalska, Bakker, Dubey, "AI Assistance Reduces Persistence and Hurts Independent Performance" (2026). https://arxiv.org/abs/2604.04721
- Liu, Zhao, Shang, Shen, "Dive into Claude Code" (2026). https://arxiv.org/abs/2604.14228
- Lulla et al., "Loop Engineering: Building Blocks, Adoption, and Impact" (2026). https://arxiv.org/abs/2608.21884
- Maharaj et al., "ETF: An Entity Tracing Framework for Hallucination Detection in Code Summaries", *ACL 2025*. https://arxiv.org/abs/2410.14748
- Mitchell, Ghosh, Passi, "AI Agents Push Humans Out of the Loop" (2026). https://arxiv.org/abs/2608.23642
- Murphy-Hill, Butler, Savelieva, "Adoption and Impact of Command-Line AI Coding Agents" (2026). https://arxiv.org/abs/2607.01418
- Prototypes: https://github.com/maxwellyoung/doomscroll ; https://github.com/Zasder3/py2anki ; https://github.com/scawful/cartograph
- Schmalbach, "Software Delegation Contracts: Measuring Reviewability in AI Coding-Agent Work" (2026). https://arxiv.org/abs/2606.17099
- Seo, Deldari, Mentis, "Whose Code Is It?", *IUI 2026*. https://dl.acm.org/doi/10.1145/3742413.3789121
- Sergeyuk et al., "Evolving with AI: A Longitudinal Analysis of Developer Logs", *ICSE 2026*. https://arxiv.org/abs/2601.10258
- Shukla and Sharma, "Psychological Ownership in AI-Assisted Software Development", Stockholm University master's thesis (2026). https://su.diva-portal.org/smash/get/diva2:2073688/FULLTEXT01.pdf
- Shukla, Feng, Wang, Rostami, Zhang, "Hedwig", *CAIS 2026* demo. https://arxiv.org/abs/2605.11495
- SIGCSE TS 2026, "AI-Driven Oral Examinations for Code Assessment". https://doi.org/10.1145/3770761.3777032
- Smith, Fowler, Denny, Zilles, "Counting the Trees in the Forest", *ITiCSE 2025*. https://arxiv.org/abs/2503.12216
- Smith, Fowler, Denny, Zilles, "ReDefining Code Comprehension", *ITiCSE 2025*. https://arxiv.org/abs/2503.12207
- Stack Overflow, "The 2026 Developer Survey is now open" (2026-06-23). https://stackoverflow.blog/2026/06/23/the-2026-developer-survey-is-now-open-for-human-developers-only/
- Vella and Blincoe, "The Impact of AI Coding Assistants on Software Engineering: A Longitudinal Study" (2026). https://arxiv.org/abs/2605.23135
- Vukovic et al., "Usage, Effects and Requirements for AI Coding Assistants in the Enterprise", ICSE 2026 LLM4Code. https://arxiv.org/abs/2601.20112
- Wang, Hu, Gao, Gao, Peng, "Evaluating Repository-level Software Documentation via Question Answering and Feature-Driven Development" (SWD-Bench, 2026). https://arxiv.org/abs/2604.06793
- Watanabe et al., "How AI Coding Agents Communicate" (2026). https://arxiv.org/abs/2602.17084
- Xiao, Hata, Treude, Matsumoto, "Generative AI for Pull Request Descriptions", *FSE 2024*. https://arxiv.org/abs/2402.08967
- Zhou, Roy, Gupta, Weitekamp, MacLellan, "When Should Users Check?", *CHI 2026*. https://arxiv.org/abs/2510.05307
- Zhou et al. CodeWiki / CodeWikiBench, *ACL 2026 Findings*. https://arxiv.org/abs/2510.24428
