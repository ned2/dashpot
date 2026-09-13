---
status: research
date: 2026-09-13
---

# Cognitive debt: evidence and mechanisms

Research date: 2026-09-13

This note is the evidence and mechanism foundation for Dashpot's cognitive-debt
research phase. Part 1 asks whether the loss of a developer's conceptual model
of a codebase under agentic delegation is real and what it is made of; Part 2
asks what learning science says would counter it. Terminal citations are
primary: the paper, the study's own page or preprint, the manual or repository.
Practitioner essays are marked as argument. Dashpot-fit judgments are out of
scope.

## Finding

The loss is real in the specific sense the evidence supports, and narrower than
the popular framing. Naur's 1985 argument that a program's "theory" lives in
its programmers and cannot be rebuilt from text alone is a philosophical
position, but it predicts exactly what four decades of program-comprehension
research observed: what experts hold is a layered mental model (domain,
program, situation) whose most expensive and least documented layer is the
mapping between world and code and the rationale for each part. On AI
specifically, the strongest causal evidence is small but consistent in
direction: a preregistered RCT (n=52) found professional developers who used
AI to learn a library scored 17 percentage points lower on a comprehension
quiz with no significant time saving; a within-subject study (n=15) found
Copilot raised task performance without raising comprehension, with
verification behaviour predicting comprehension; a three-arm study (n=78)
found unrestricted-AI users failed a no-AI maintenance task at 77% versus
39% under a teach-back gate; and a 2026 meta-analysis of 23 studies found a
moderate productivity gain (g=0.33) with no significant learning effect
(g=0.14, CI spans zero). The MIT "Your Brain on ChatGPT" study introduced the
term "cognitive debt" but is an essay-writing preprint with n=54 (18 per
arm), no formal limitations on generalisation beyond essays, and published
methodological critique; it is weak evidence for code. Surveys (Stack
Overflow, DORA, JetBrains) document a trust gap and a verification tax, not
comprehension loss. METR's RCT measured speed, not understanding, and METR has
since retracted the 19% slowdown as outdated. Evidence that "reading and
approving" builds understanding is negative-leaning: reviewers' central
difficulty is understanding, judgement of incorrect AI-generated assertions is
near chance with unchanged confidence, and AI-assisted developers were more
confident in code that was less secure. On mechanisms, retrieval practice
(g≈0.50–0.61), spacing, self-explanation (g=0.55), generation (d=0.40),
teaching (g=0.35–0.56), and interleaving (g=0.42, material-dependent) have
meta-analytic support; all were established on declarative or problem-solving
material, and only self-explanation, code tracing, "explain in plain
English", Parsons problems, and step-wise engagement with AI output have
direct computing-education evidence. Nothing found tests any of them on
retaining a working model of a real, evolving codebase.

## Part 1 — What is lost

### Naur: the theory is not in the text

Naur, "Programming as Theory Building" (1985), argues that the primary product
of programming is not the program text but a theory held by the programmers,
in Ryle's sense of an intellectual capacity to explain, justify, and extend
(Naur 1985). He names three things the theory-holder knows that the documented
products cannot carry: how each part of the program maps to "the affairs of
the world" it handles and, conversely, how any world aspect is mapped into
the text; why each part is what it is (a justification whose final basis is
the programmer's "direct, intuitive knowledge"); and how to respond
constructively to a demand for modification, which depends on perceiving
similarity between the new demand and existing facilities — a similarity
"between aspects of the world" that "cannot be reduced to any limited set of
criteria or rules." He then defines program life, death, and revival: a
program dies "when the programmer team possessing its theory is dissolved";
death "becomes visible when demands for modifications of the program cannot be
intelligently answered"; and "program revival, that is reestablishing the
theory of a program merely from the documentation, is strictly impossible"
(Naur 1985, pp. 253–261; quotations from the reprint at
[pages.cs.wisc.edu/~remzi/Naur.pdf](https://pages.cs.wisc.edu/~remzi/Naur.pdf);
publisher record
[doi:10.1016/0165-6074(85)90032-8](https://www.sciencedirect.com/science/article/abs/pii/0165607485900328)).
His remedy for onboarding is working "in close contact with the programmers
who already possess the theory," doing the relevant things under supervision,
because this is knowledge-how rather than knowledge-that.

Implication for agent-written code, read strictly from the text: the agent's
session held whatever mapping and justification produced the code, and that
session ends. If Naur is right, the code is born in the "dead" state unless a
person builds the theory alongside it, and rebuilding it later from the text
is the costly revival he advises against. This is an argument, not a
measurement; the comprehension literature below is what gives it empirical
shape.

### Program comprehension: what a mental model of code consists of

The classic results define the object that is lost.

- Brooks (1983) proposed comprehension as top-down hypothesis refinement
  across a chain of domains from problem to program, with "beacons" in the
  code confirming or refuting hypotheses. Brooks, R. "Towards a theory of the
  comprehension of computer programs." *IJMMS* 18(6):543–554,
  [doi:10.1016/S0020-7373(83)80031-5](https://doi.org/10.1016/S0020-7373(83)80031-5).
- Soloway and Ehrlich (1984) showed experts hold "programming plans" (stereotyped
  code fragments for goals) and "rules of programming discourse"; when
  code violates those conventions, expert advantage over novices largely
  disappears. *IEEE TSE* SE-10(5):595–609,
  [doi:10.1109/TSE.1984.5010283](https://doi.org/10.1109/TSE.1984.5010283).
  Wiedenbeck (1986) confirmed beacons empirically. "Beacons in computer
  program comprehension." *IJMMS* 25(6):697–709,
  [doi:10.1016/S0020-7373(86)80083-9](https://doi.org/10.1016/S0020-7373(86)80083-9).
- Letovsky (1987) observed programmers combining top-down and bottom-up
  strategies opportunistically, asking "why", "how", and "what" questions,
  and forming conjectures whose confirmation depends on the availability of
  rationale. "Cognitive processes in program comprehension." *J. Systems and
  Software* 7(4):325–339,
  [doi:10.1016/0164-1212(87)90032-X](https://doi.org/10.1016/0164-1212(87)90032-X).
- Pennington (1987) distinguished the *program model* (control flow, built
  first) from the *domain* or *situation model* (what the program does in
  world terms, data flow, function), and found that programmers who built the
  situation model, not just the program model, performed better on
  modification tasks. "Stimulus structures and mental representations in
  expert comprehension of computer programs." *Cognitive Psychology*
  19(3):295–341,
  [doi:10.1016/0010-0285(87)90007-7](https://doi.org/10.1016/0010-0285(87)90007-7).
- von Mayrhauser and Vans (1995) integrated these into the Integrated
  Metamodel: top-down (domain), program, and situation models plus a
  knowledge base, with maintainers switching among them; large-scale
  maintenance was dominated by understanding time. "Program comprehension
  during software maintenance and evolution." *IEEE Computer* 28(8):44–55,
  [doi:10.1109/2.402076](https://doi.org/10.1109/2.402076).
- Storey (2005/2006) reviews these theories and notes that tools mostly
  support the program model and rarely the situation or domain model.
  "Theories, methods and tools in program comprehension: past, present and
  future." *Software Quality Journal* 14(3):187–208,
  [doi:10.1007/s11219-006-9216-4](https://doi.org/10.1007/s11219-006-9216-4).
- LaToza, Venolia, and DeLine (2006), from two surveys and eleven interviews
  at Microsoft, found that much of what developers need is implicit knowledge
  held only in colleagues' memories; the hardest questions were about design
  rationale and the intent behind code, recovered by exploring code and
  interrupting teammates. "Maintaining mental models: a study of developer
  work habits." *ICSE 2006*,
  [doi:10.1145/1134285.1134355](https://dl.acm.org/doi/10.1145/1134285.1134355).
  Ko, DeLine, and Venolia (2007) found questions about why code was
  implemented a particular way among the information needs most often left
  unanswered.
  "Information needs in collocated software development teams." *ICSE 2007*,
  [doi:10.1109/ICSE.2007.45](https://dl.acm.org/doi/10.1109/ICSE.2007.45).
- Ownership as a knowledge proxy: Bird et al. (2011) associated
  authorship-based ownership metrics with lower defect density in Windows
  components. "Don't touch my code! Examining the effects of ownership on
  software quality." *ESEC/FSE 2011*,
  [doi:10.1145/2025113.2025119](https://doi.org/10.1145/2025113.2025119).
  Wheeler (2026), a position paper with no empirical data, argues that
  AI-generated code severs the inference from authorship to comprehension that
  such metrics (truck factor, degree-of-authorship) rely on, and states a
  falsifiable prediction that systems with high authorship-derived truck
  factor but low comprehension will show incident-resolution failures the
  metric cannot predict.
  [arXiv:2606.20882](https://arxiv.org/abs/2606.20882).
- Cognitive dimensions: Green and Petre's framework names properties of a
  notation such as hidden dependencies, premature commitment, and role
  expressiveness; it is a vocabulary for what makes structure hard to see,
  not a measurement of comprehension. "Usability analysis of visual
  programming environments: a 'cognitive dimensions' framework." *J. Visual
  Languages & Computing* 7(2):131–174 (1996),
  [doi:10.1006/jvlc.1996.0009](https://doi.org/10.1006/jvlc.1996.0009).

What these results define as "the model": a layered representation whose
program layer (control and data flow) is recoverable from text with effort,
whose situation layer (world mapping, function) is expensive to build and is
what modification tasks depend on, and whose rationale (why) is largely
undocumented and socially held. That last layer is what Naur said cannot be
rebuilt from text and what LaToza and Ko found developers already struggled to
recover before AI.

### AI-specific evidence, 2023–2026

Each entry: what was measured, headline result, sample and design, limits the
authors state.

**Kosmyna et al. (2025), "Your Brain on ChatGPT: Accumulation of Cognitive
Debt when Using an AI Assistant for Essay Writing Task."**
[arXiv:2506.08872](https://arxiv.org/abs/2506.08872) (v1 June 2025, v2
December 2025; marked "Preprint, under review"). Measured EEG connectivity
(dDTF), NLP features of essays, human and AI scoring, and post-session
interviews including quoting and ownership questions. Design: 54 participants
in three arms (LLM, Search Engine, Brain-only) over three sessions, 18 of
whom returned for a crossover session 4. Headline results: Brain-only showed
the strongest and most distributed connectivity, LLM the weakest; in session
1, 83.3% (15/18) of the LLM group failed to produce a correct quotation from
the essay they had just written versus 11.1% (2/18) in each other group
(p < .001); by session 2 most participants in all groups could quote. The
paper defines cognitive debt as "a condition in which repeated reliance on
external systems like LLMs replaces the effortful cognitive processes required
for independent thinking." Authors' stated limitations: limited participants
from one geographic area and a few institutions, not gender balanced; ChatGPT
only; EEG connectivity only, no spectral power, poor spatial resolution;
findings "context-dependent and are focused on writing an essay in an
educational setting and may not generalize across tasks." Stanković et al.
(2025) published a methodological comment citing sample size, reproducibility
of analyses, EEG-analysis issues, reporting inconsistencies, and transparency
gaps, urging more conservative interpretation
([arXiv:2601.00856](https://arxiv.org/abs/2601.00856)). Net: the paper coined
the term, measured essay writing, and is not evidence about code.

**METR (2025), "Measuring the Impact of Early-2025 AI on Experienced
Open-Source Developer Productivity."**
[metr.org](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/),
[arXiv:2507.09089](https://arxiv.org/abs/2507.09089). Measured task completion
time. RCT: 16 developers, 246 real issues in mature repositories (average
about 10 years old, >1.1M lines, developers averaging 5 years and 1,500
commits on them), each issue randomised to AI-allowed or not, mostly Cursor
Pro with Claude 3.5/3.7 Sonnet. Headline: AI-allowed issues took 19% longer
(95% CI roughly +2% to +39%), while developers forecast a 24% speedup and
afterwards believed they had been sped up 20%. Understanding was not
measured. Relevant factor findings: slowdown was larger on issues where
developers reported high prior task exposure and low external-resource needs
(Appendix C.1.2); developers accepted fewer than 44% of Cursor generations,
75% reported reading every line of AI code, 56% often made major clean-up
changes, and about 9% of AI-condition time went to reviewing and cleaning AI
output on the 44 labelled recordings (C.1.4); developers said AI lacks tacit
repository context (C.1.5). Authors' stated limits: does not show AI fails
most developers, does not generalise beyond the setting, does not show no
effective usage strategy exists. On 2026-02-24 METR reported that the 19%
finding is "now outdated": follow-on data from August 2025 onward estimated
−18% (CI −38% to +9%) for original developers and −4% (CI −15% to +9%) for new
recruits, but METR judges those numbers unreliable because developers
declined to work without AI, 30–50% withheld tasks, and concurrent agent use
made timing hard, and it is redesigning the experiment
([METR update](https://metr.org/blog/2026-02-24-uplift-update/)). Net:
evidence about perception–reality gaps and where AI helps least (familiar
code), not about comprehension.

**Lee et al. (2025), "The Impact of Generative AI on Critical Thinking:
Self-Reported Reductions in Cognitive Effort and Confidence Effects From a
Survey of Knowledge Workers."** *CHI 2025*,
[doi:10.1145/3706598.3713778](https://dl.acm.org/doi/full/10.1145/3706598.3713778),
[PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/01/lee_2025_ai_critical_thinking_survey.pdf).
Measured self-reported enaction of and effort in critical thinking. Survey of
319 knowledge workers on Prolific (weekly GenAI users at work), 936 examples.
Headline: participants reported some critical thinking on about 60% (555/936)
of examples; in mixed-effects regressions, confidence in GenAI predicted less
perceived critical thinking (b = −0.69, p < 0.001) and less effort across the
six Bloom categories, while self-confidence predicted more (b = 0.26,
p = 0.026). Qualitatively, critical thinking shifts toward verification,
integration, and stewardship. Authors' limitations: participants conflated
reduced effort with reduced critical thinking; self-confidence may be
miscalibrated; English-only; sample skewed young and tech-skilled; tools are
changing. Net: self-report and correlational; no code-specific measure.

**Shen and Tamkin (2026), "How AI Impacts Skill Formation."**
[arXiv:2601.20245](https://arxiv.org/abs/2601.20245) (Anthropic; preregistered
at [osf.io/w49e7](https://osf.io/w49e7)). Measured task time and a 27-point
quiz on the Trio async library covering debugging, code reading, and concepts.
RCT: 52 professional or freelance Python developers new to Trio (26 per arm),
recruited as crowd workers, up to 35 minutes on two tasks with or
without a chat AI, then the quiz. Headline: AI condition scored 4.15 points
lower (17%, "2 grade points"; Cohen's d = 0.738, p = 0.01; d = 0.725 after
covariate control) with no significant time advantage; largest deficit on
debugging questions. Six interaction patterns were identified; those with
cognitive engagement (conceptual inquiry, generation-then-comprehension,
hybrid code-explanation) preserved quiz scores while patterns that delegated
did not. Authors' limitations: one task with a chat interface (agentic tools
"would require even less human" engagement, so the effect may differ); skill
measured over about an hour, not months; participants were not learning for
their real job; AI familiarity self-reported; quiz as the only skill measure;
no comparison with human help. Net: the cleanest causal evidence found that
delegation lowers comprehension of code just written, in a novel-library
learning setting.

**Qiao, Shihab, Haque, and Hundhausen (2025), "Code Comprehension with GitHub
Copilot: Performance Gains, Comprehension Trade-offs, and Behavioral
Predictors in Brownfield Programming."**
[arXiv:2511.02922](https://arxiv.org/abs/2511.02922). Measured task
performance and comprehension in an existing codebase. Within-subject, 15
graduate CS students, feature implementation with and without Copilot.
Headline: performance rose significantly; comprehension did not (p = 0.59);
performance gain correlated negatively with reverse-engineering comprehension
(ρ = −0.57, p = 0.026); engaging in code-verification loops strongly
predicted comprehension (r = 0.96, p < 0.001), and high-comprehension
participants verified 4.7 times more often. Limits: n = 15, students, single
context. Net: small, but the only study found on brownfield code, and it
locates the effect in behaviour rather than tool availability.

**Sankaranarayanan (2026), "Mitigating 'Epistemic Debt' in Generative
AI-Scaffolded Novice Programming using Metacognitive Scripts."**
[arXiv:2602.20206](https://arxiv.org/abs/2602.20206). Defines epistemic debt
as the knowledge gap from outsourcing cognitive work to AI, producing "fragile
experts" with high functional output and low corrective competence. Three
arms, n = 78 (Prolific and UserInterviews): manual, unrestricted AI, and AI
behind an "Explanation Gate" requiring teach-back before proceeding, in a
Cursor plugin with Claude 3.5 Sonnet; outcome was a 30-minute no-AI
"blackout" maintenance task. Headline: 77% failure for unrestricted AI versus
39% with the gate; both AI arms beat manual on functional output. Limits not
stated in the abstract, but the v2 body has a "Threats to Validity" section
(checked 2026-09-13): a Hawthorne effect from monitored sessions, novice-only
participants ("results may not generalize to experienced programmers"),
repair success as a proxy for corrective competence, and a single two-hour
task ("whether this proxy generalizes to chronic, career-long debt
accumulation is an open question"); no judge–human agreement statistic is
reported, only that the rubric was calibrated with an expert learning
designer. Net: direct test of a countermeasure, on novices.

**Kaufman, Brun, Murali, and Endres (2026), "Programmers Are Poor and
Overconfident Judges of LLM-Generated Assertions."**
[arXiv:2607.08885](https://arxiv.org/abs/2607.08885). Controlled experiment
with 86 Python programmers plus think-aloud follow-up. Headline: 74% accuracy
judging correct assertions, 49% judging incorrect ones (OR = 2.94), with
similar confidence in both (p < 0.001); natural-language explanations gave no
overall benefit, and poor explanations reduced accuracy (OR = 0.58,
p = 0.037) while raising confidence. Limits: Python only, 86 participants.

**Perry, Srivastava, Kumar, and Boneh (2023), "Do Users Write More Insecure
Code with AI Assistants?"** *CCS 2023*,
[doi:10.1145/3576915.3623157](https://dl.acm.org/doi/10.1145/3576915.3623157),
[arXiv:2211.03622](https://arxiv.org/abs/2211.03622). User study with a
codex-davinci-002 assistant: assisted participants wrote significantly less
secure code on several tasks and were more likely to believe their code was
secure; those who trusted the assistant less and engaged more with prompts
wrote more secure code. Pre-agentic tooling; security tasks only.

**Maier, Gunzenhäuser, Schweisthal, Schneider, and Feuerriegel (2026), "A
meta-analysis of the effect of generative AI on productivity and learning in
programming."** [arXiv:2605.04779](https://arxiv.org/abs/2605.04779). 23
studies, 27 effect sizes. Productivity g = 0.33 (95% CI 0.09–0.58), larger in
controlled settings than open-source or enterprise; learning g = 0.14 (95% CI
−0.18 to 0.47), not significant. Authors note substantial heterogeneity.
Preprint; inclusion criteria not verified here.

**Kazemitabaar, Huang, Suh, Henley, and Grossman (2024), "Exploring the Design
Space of Cognitive Engagement Techniques with AI-Generated Code for Enhanced
Learning."** [arXiv:2410.08922](https://arxiv.org/abs/2410.08922). Seven
techniques for engaging novices with AI-generated code; between-subjects
n = 82 and within-subjects n = 42. The most effective was a step-by-step
dialogue in which the learner states what must happen next before the
corresponding code is revealed, measured by transfer to a similar task and by
alignment of perceived and actual ability. Novices; short tasks.

**Sarkar and Drosos (2025), "Vibe coding: programming through conversation
with artificial intelligence."** [arXiv:2506.23253](https://arxiv.org/abs/2506.23253).
Framework analysis of over 8 hours of think-aloud vibe-coding video. Finds
iterative prompt–evaluate–edit cycles, evaluation by "rapid scanning and
application testing," and a stance the authors call "material disengagement"
with selective oversight. Qualitative, self-selected streamers; no
comprehension measure.

### Surveys: trust and verification, not comprehension

- Stack Overflow 2025 Developer Survey
  ([survey.stackoverflow.co/2025/ai](https://survey.stackoverflow.co/2025/ai)):
  84% using or planning to use AI tools; 46% distrust AI accuracy versus 33%
  trusting it, 3% "highly trust"; 66% cite solutions that are "almost right,
  but not quite" and 45% say debugging AI code takes longer. Self-selected
  online sample.
- Google DORA 2025, *State of AI-assisted Software Development*
  ([dora.dev/dora-report-2025](https://dora.dev/dora-report-2025/)): about
  30% report little or no trust in AI-generated code while over 80% report a
  productivity gain; DORA frames a "verification tax" and AI as an amplifier
  of existing organisational strengths and weaknesses. Survey-based.
- JetBrains *State of Developer Ecosystem 2025*
  ([devecosystem-2025.jetbrains.com/artificial-intelligence](https://devecosystem-2025.jetbrains.com/artificial-intelligence)):
  24,534 respondents; 85% use AI regularly; top concerns are code quality
  (23%), AI's limited understanding of complex logic (18%), and, at 11%,
  "negative effect on coding and development skills."
- GitHub 2024 survey (Wakefield Research, 2,000 enterprise developers in four
  countries; published April 2025,
  [github.blog](https://github.blog/news-insights/research/survey-ai-wave-grows/)):
  over 97% had used AI coding tools at work; 60–90% by country perceived
  higher code quality. Perception only.

None of these measures whether developers understand the code they ship; the
JetBrains skills item is the closest and is a concern, not an outcome.

### Practitioner framings (argument, not evidence)

- Osmani, "Comprehension Debt: The Hidden Cost of AI-Generated Code"
  (2026-03-14, [addyosmani.com](https://addyosmani.com/blog/comprehension-debt/);
  also on O'Reilly Radar). Defines comprehension debt as "the growing gap
  between how much code exists in your system and how much of it any human
  being genuinely understands," argues it breeds false confidence unlike
  technical debt's visible friction, and cites Shen and Tamkin (2026) as its
  quantitative support.
- Storey, "From Technical Debt to Cognitive and Intent Debt: Rethinking
  Software Health in the Age of AI" (2026,
  [arXiv:2603.22106](https://arxiv.org/abs/2603.22106); also *ACM Queue*).
  Conceptual "triple debt" model: cognitive debt as team-level erosion of
  shared understanding leaving collective mental models inadequate for safe
  modification; intent debt as missing or degraded explicit rationale,
  objectives, and limitations. No new empirical data.
- Kosmyna et al. (2025) is the origin of "cognitive debt" as a term in this
  discourse, but its evidence is about essays (above).

## Part 2 — Mechanisms

Each subsection gives the canonical sources, evidence strength, conditions,
and a sketch of the mechanism applied to a codebase rather than a card deck.
The sketches are descriptive; they are not recommendations.

### Retrieval practice (testing effect)

Sources: Roediger and Karpicke (2006), *Psychological Science* 17(3):249–255,
[doi:10.1111/j.1467-9280.2006.01693.x](https://doi.org/10.1111/j.1467-9280.2006.01693.x)
— prose passages; restudy beat testing at 5 minutes, testing beat restudy at
2 days and 1 week (verified 2026-09-13 from the author-hosted PDF,
<https://learninglab.psych.purdue.edu/downloads/2006/2006_Roediger_Karpicke_PsychSci.pdf>:
Experiment 1 recall 81% vs 75% at 5 min, 68% vs 54% at 2 days, 56% vs 42%
at 1 week for tested vs restudied; Experiment 2 at 1 week, STTT 61%, SSST
56%, SSSS 40%). Karpicke and Blunt (2011), *Science* 331:772–775,
[doi:10.1126/science.1199327](https://doi.org/10.1126/science.1199327) —
retrieval practice beat elaborative concept mapping on inference questions a
week later, and learners predicted the opposite. Meta-analyses: Rowland
(2014), *Psychological Bulletin* 140(6):1432–1463,
[doi:10.1037/a0037559](https://doi.org/10.1037/a0037559), g = 0.50 (159 effects),
larger for recall than recognition tests, supporting effortful retrieval as
the mechanism; Adesope, Trevisan, and Sundararajan (2017), *Review of
Educational Research* 87(3):659–701,
[doi:10.3102/0034654316689306](https://doi.org/10.3102/0034654316689306),
practice tests beat restudy and other conditions (reported g = 0.61 across
formats; full text paywalled — the abstract carries no effect size, but two
open-access papers quote it as g = 0.61 [95% CI 0.58, 0.65], PMC6760123 and
PMC6288371, checked 2026-09-13). Dunlosky et al. (2013), *PSPI* 14(1):4–58,
[doi:10.1177/1529100612453266](https://doi.org/10.1177/1529100612453266),
rate practice testing "high utility." Strength: strongest in the set.
Conditions: retrieval must succeed or be followed by feedback; effortful
recall beats recognition; benefit appears at delays, not immediately; learners
do not choose it spontaneously (Karpicke, Butler, and Roediger 2009, *Memory*
17(4):471–479,
[doi:10.1080/09658210802647009](https://doi.org/10.1080/09658210802647009)).
Applied to a codebase: prompting a developer to state from memory, before
opening the file, which module owns a piece of state, what invariant a
function preserves, or why a boundary exists, then checking against the code;
questions framed as free recall rather than yes/no; scheduled after a delay
from the change that introduced the fact.

### Spaced repetition and its schedulers

Sources: Cepeda, Pashler, Vul, Wixted, and Rohrer (2006), *Psychological
Bulletin* 132(3):354–380,
[doi:10.1037/0033-2909.132.3.354](https://doi.org/10.1037/0033-2909.132.3.354)
— 839 assessments in 317 experiments; the interstudy interval that maximises
retention grows with the retention interval. Cepeda et al. (2008),
*Psychological Science* 19(11):1095–1102,
[doi:10.1111/j.1467-9280.2008.02209.x](https://doi.org/10.1111/j.1467-9280.2008.02209.x)
— optimal gap is a decreasing fraction of the retention interval, roughly
10–20% for the ranges tested. Dunlosky et al. (2013) rate distributed practice
"high utility." Schedulers: SM-2 (SuperMemo 1.0, 1987) assigns each item an
E-Factor starting at 2.5, multiplies the previous interval by it, and adjusts
it from a 0–5 recall grade
([supermemo.guru/wiki/Algorithm_SM-2](https://www.supermemo.guru/wiki/Algorithm_SM-2)).
Anki's legacy scheduler is SM-2-derived with starting ease 250%; its FSRS
scheduler models each card's difficulty, stability, and retrievability, targets
a desired retention (default 90%), and the manual warns that workload grows
steeply above about 97% and that monthly re-optimisation is enough
([docs.ankiweb.net/deck-options.html](https://docs.ankiweb.net/deck-options.html)).
FSRS is documented in its repository and papers: Ye, Su, and Cao (2022), *KDD
'22*, [doi:10.1145/3534678.3539081](https://doi.org/10.1145/3534678.3539081);
Su, Ye, Nie, Cao, and Su (2023), *IEEE TKDE*,
[doi:10.1109/TKDE.2023.3251721](https://doi.org/10.1109/TKDE.2023.3251721);
algorithm description at
[open-spaced-repetition/fsrs4anki wiki](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm).
Strength: the spacing effect is among the most replicated in psychology; the
schedulers are engineering on top of it, validated on flashcard review logs,
not on comprehension of structures. Conditions: items must be discrete and
re-testable; the target retention interval must be known; the memory model
assumes the item does not change between reviews. Applied to a codebase:
each retrievable fact (a module's responsibility, a data-flow path, a
decision's rationale) becomes an item whose review interval expands with
successful recall, with the complication that code items are invalidated by
edits — an event a card scheduler has no notion of — and that the fact set
grows with every agent change.

### Desirable difficulties

Sources: Bjork (1994), "Memory and metamemory considerations in the training
of human beings," in Metcalfe and Shimamura (eds.), *Metacognition*, MIT
Press, pp. 185–205; Bjork and Bjork (2011), "Making things hard on yourself,
but in a good way," in Gernsbacher et al. (eds.), *Psychology and the Real
World*, Worth, pp. 56–64
([PDF, Bjork Learning and Forgetting Lab](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/EBjork_RBjork_2011.pdf)).
The framing: conditions that slow acquisition and depress performance during
training (spacing, interleaving, testing, generation, varying conditions)
often improve long-term retention and transfer, and the reverse holds for
conditions that make training feel fluent. Strength: an organising principle
whose components are individually meta-analysed above and below; the
principle itself is not a single measured effect. Conditions: the difficulty
must be one the learner can overcome (Bjork's own qualification); otherwise
it is just difficulty. Applied to a codebase: friction that forces recall,
prediction, or explanation before an answer is shown, sized so that the
developer usually succeeds.

### Generation effect

Sources: Slamecka and Graf (1978), *JEP: Human Learning and Memory*
4(6):592–604, [doi:10.1037/0278-7393.4.6.592](https://doi.org/10.1037/0278-7393.4.6.592);
Bertsch, Pesta, Wiscott, and McDaniel (2007), *Memory & Cognition*
35(2):201–210, [doi:10.3758/BF03193441](https://doi.org/10.3758/BF03193441),
d = 0.40 over 445 effects in 86 studies. Strength: robust for memory of
generated items. Conditions: generation must be of the target itself (or its
meaningful relation), from a cue the learner can act on; the effect can
reverse for complex, novel material where generation fails (a worked-example
regime, below). Applied to a codebase: writing the expected signature,
invariant, or call sequence before seeing the agent's version; predicting a
test's outcome before running it; the developer producing the design sketch
the agent then implements, rather than reading the agent's.

### Elaborative interrogation and self-explanation

Sources: Chi, Bassok, Lewis, Reimann, and Glaser (1989), *Cognitive Science*
13(2):145–182, [doi:10.1207/s15516709cog1302_1](https://doi.org/10.1207/s15516709cog1302_1)
— good problem solvers spontaneously explained worked examples to themselves;
Chi, de Leeuw, Chiu, and LaVancher (1994), *Cognitive Science* 18(3):439–477,
[doi:10.1207/s15516709cog1803_3](https://doi.org/10.1207/s15516709cog1803_3)
— prompting self-explanation improved understanding of a biology text and
mental-model quality. Meta-analysis: Bisra, Liu, Nesbit, Salimi, and Winne
(2018), *Educational Psychology Review* 30:703–725,
[doi:10.1007/s10648-018-9434-x](https://doi.org/10.1007/s10648-018-9434-x),
g = 0.55 over 69 effects, effective across problem solving, worked examples,
and text. Elaborative interrogation ("why would this be true?"): Pressley et
al. (1987), *JEP: LMC* 13(2):291–300; Dunlosky et al. (2013) rate it and
self-explanation "moderate utility," noting most evidence is short-term and
laboratory. Conditions: prompts must ask for mechanism ("why does this hold?"),
not paraphrase; benefits depend on prior knowledge to elaborate with; time
cost is real. Applied to a codebase: asking the developer to explain, in
their own words, why a change is correct and what it depends on before
approving it; requiring a rationale for a design boundary rather than a
restatement of what the code does. The Explanation Gate in Sankaranarayanan
(2026) and the "hybrid code-explanation" pattern in Shen and Tamkin (2026)
are the nearest direct tests.

### Interleaving

Sources: Rohrer and Taylor (2007), *Instructional Science* 35:481–498,
[doi:10.1007/s11251-007-9015-8](https://doi.org/10.1007/s11251-007-9015-8);
meta-analysis Brunmair and Richter (2019), *Psychological Bulletin*
145(11):1029–1052, [doi:10.1037/bul0000209](https://doi.org/10.1037/bul0000209),
g = 0.42 over 238 effects; larger for visual categories (paintings g = 0.67),
small for mathematics (g = 0.34), null for expository text, and reversed for
word lists (g = −0.39); stronger when categories are similar to each other
and complex. Dunlosky et al. (2013) rate it "moderate utility." Conditions:
benefits discrimination between confusable categories; harms when material is
unrelated. Applied to a codebase: mixing review of similar-but-distinct
constructs (two modules with parallel responsibilities, two state machines)
so the developer must discriminate them, rather than reviewing one area in a
block; the text-material null is a caution that interleaving unrelated files
has no support.

### Worked examples and the expertise-reversal effect

Sources: Sweller and Cooper (1985), *Cognition and Instruction* 2(1):59–89,
[doi:10.1207/s1532690xci0201_3](https://doi.org/10.1207/s1532690xci0201_3)
— novices learned algebra better from studying worked examples than from
solving problems; Kalyuga, Ayres, Chandler, and Sweller (2003), *Educational
Psychologist* 38(1):23–31,
[doi:10.1207/S15326985EP3801_4](https://doi.org/10.1207/S15326985EP3801_4)
— guidance that helps novices becomes redundant or harmful as expertise
grows. Strength: well replicated within cognitive load theory; the reversal is
the important part here. Conditions: worked examples help when the learner
lacks schemas; for experts, problem solving and generation win. Applied to a
codebase: an agent's output is a worked example. For a developer new to a
subsystem, studying it with self-explanation is the appropriate regime; for
a developer who already holds the theory of that subsystem, reading the
worked example is redundant and generation-first is predicted to serve
retention better. This is the mechanism-level reading of METR's finding that
AI helped least on familiar code.

### Teaching and explaining to others (protégé effect)

Sources: Chase, Chin, Oppezzo, and Schwartz (2009), *J. Science Education and
Technology* 18:334–352,
[doi:10.1007/s10956-009-9180-4](https://doi.org/10.1007/s10956-009-9180-4)
— students teaching a software agent learned more than students learning for
themselves; Fiorella and Mayer (2013), *Contemporary Educational Psychology*
38(4):281–288, [doi:10.1016/j.cedpsych.2013.06.001](https://doi.org/10.1016/j.cedpsych.2013.06.001)
— actually teaching, not just preparing to teach, produced durable gains.
Meta-analysis: Kobayashi (2019), *Japanese Psychological Research*
61(3):192–203, [doi:10.1111/jpr.12221](https://doi.org/10.1111/jpr.12221),
g = 0.35 for preparing to teach and g = 0.56 for teaching after preparing,
over 28 studies, holding for deep learning and after delay. Conditions: the
explanation must be generated, not read; an audience (even simulated) adds to
preparation alone. Applied to a codebase: the developer explaining a
subsystem to a colleague, to a newcomer, or to an agent that asks follow-up
questions; Naur's onboarding prescription runs the other way (novice works
with theory-holder) and is compatible.

### Illusion of competence and fluency

Sources: Koriat and Bjork (2005), *JEP: LMC* 31(2):187–194,
[doi:10.1037/0278-7393.31.2.187](https://doi.org/10.1037/0278-7393.31.2.187)
— judgments of learning are inflated when the answer is present at study
("foresight bias"); Koriat and Bjork (2006), *Memory & Cognition*
34(5):959–972, [doi:10.3758/BF03193244](https://doi.org/10.3758/BF03193244)
— the illusion is reduced by conditions that mimic the test (retrieval
attempts). Bjork, Dunlosky, and Kornell (2013), *Annual Review of Psychology*
64:417–444, [doi:10.1146/annurev-psych-113011-143823](https://doi.org/10.1146/annurev-psych-113011-143823)
review fluency-driven misjudgement. Strength: robust in the laboratory.
Conditions: any presentation in which the answer is visible while the learner
judges their own knowledge. Applied to a codebase: reading a diff with the
answer on screen is the archetypal foresight-bias condition; METR's
developers estimated a 20% speedup after a 19% slowdown, Perry et al.'s
assisted participants were more confident in less secure code, and Kaufman
et al.'s judges were equally confident when 49% accurate. Retrieval before
reveal is the documented remedy.

### Computing-education evidence on reading code

- Tracing: Lister et al. (2004), ITiCSE working group, *SIGCSE Bulletin*
  36(4):119–150, [doi:10.1145/1041624.1041673](https://doi.org/10.1145/1041624.1041673)
  — many novices could not trace code reliably; Lopez, Whalley, Robbins, and
  Lister (2008), *ICER 2008*,
  [doi:10.1145/1404520.1404531](https://doi.org/10.1145/1404520.1404531) —
  tracing and explaining predicted writing in a hierarchy; Xie et al. (2019),
  *Computer Science Education* 29(2–3):205–253,
  [doi:10.1080/08993408.2019.1565235](https://doi.org/10.1080/08993408.2019.1565235)
  — a theory of instruction ordering reading semantics, reading templates,
  writing semantics, writing templates.
- Explain in plain English (EiPE): Whalley et al. (2006), *ACE 2006*,
  introduced code-purpose questions scored with SOLO; Murphy, Fitzgerald,
  Lister, and McCauley (2012), "Ability to 'explain in plain English' linked
  to proficiency in computer-based programming," *ICER 2012*,
  [doi:10.1145/2361276.2361299](https://doi.org/10.1145/2361276.2361299) —
  EiPE performance correlated with code-writing ability; Fowler, Chen, and
  Zilles (2021), *ICER 2021*,
  [doi:10.1145/3446871.3469738](https://doi.org/10.1145/3446871.3469738)
  ([PDF](https://zilles.cs.illinois.edu/papers/how_to_eipe_icer_2021.pdf))
  on how the community frames the questions. EiPE is the closest existing
  instrument to "does the developer hold the situation model."
- Parsons problems: Parsons and Haden (2006), *ACE 2006*; Ericson,
  Margulieux, and Rick (2017), *Koli Calling 2017*,
  [doi:10.1145/3141880.3141895](https://doi.org/10.1145/3141880.3141895) —
  two-dimensional Parsons problems with distractors took significantly less
  time than fixing or writing code with no significant difference in learning
  or one-week retention; Ericson et al. (2022), ITiCSE working group,
  *Parsons Problems and Beyond*,
  [doi:10.1145/3571785.3574127](https://doi.org/10.1145/3571785.3574127).
  Evidence is on novices and small programs.
- Engagement with AI output: Kazemitabaar et al. (2024) and Sankaranarayanan
  (2026), above, are the direct tests; Shen and Tamkin's pattern analysis is
  observational within an RCT.

### Does "reading and approving" build understanding?

- Bacchelli and Bird (2013), *ICSE 2013*,
  [Microsoft Research page](https://www.microsoft.com/en-us/research/publication/expectations-outcomes-and-challenges-of-modern-code-review/):
  from observation, interviews, and survey at Microsoft, understanding the
  change and its context is the central challenge of review, met by
  mechanisms tools do not support; reviews do transfer knowledge, but as a
  by-product of effortful understanding rather than of approval.
- Sadowski, Söderberg, Church, Sipko, and Bacchelli (2018), *ICSE-SEIP 2018*,
  [doi:10.1145/3183519.3183525](https://doi.org/10.1145/3183519.3183525):
  12 interviews, 44 survey responses, and about nine million reviewed changes
  at Google; education and knowledge spreading are stated motivations, and
  the practice is lightweight (most changes have one reviewer).
- Pascarella, Spadini, Palomba, Bruntink, and Bacchelli (2018), *CSCW 2018*,
  [doi:10.1145/3274404](https://doi.org/10.1145/3274404): reviewers'
  information needs include the change's rationale and whether it is
  correct, and reviewers frequently obtain them from the author rather than
  from the code.
- Baum, Schneider, and Bacchelli (2019), *Empirical Software Engineering*
  24:1762–1798, [doi:10.1007/s10664-018-9676-8](https://doi.org/10.1007/s10664-018-9676-8):
  controlled experiment; working-memory capacity was associated with finding
  delocalised defects — review performance is bounded by the reviewer's
  cognitive resources, not only by diligence.
- Qiao et al. (2025) and Kaufman et al. (2026), above: verification loops
  predicted comprehension, while passive judgement of incorrect AI output was
  near chance with intact confidence.

Reading these together: reading confers the program model at best; the
situation model and rationale come from effortful verification, explanation,
or generation. No study found measures retention of understanding after
approving agent-written code.

### Summary table

| Mechanism | Evidence strength | Key conditions | Applied-to-code sketch |
| --- | --- | --- | --- |
| Retrieval practice | Meta-analytic, g≈0.50–0.61 (Rowland 2014; Adesope 2017); "high utility" (Dunlosky 2013) | Free recall over recognition; feedback; benefit at delay; learners avoid it unprompted | Recall a module's role, invariant, or rationale before opening the file; check against code |
| Spaced repetition | Spacing effect meta-analytic (Cepeda 2006, 2008); schedulers (SM-2, FSRS) validated on card logs | Discrete, stable, re-testable items; known retention horizon | Expanding review intervals per codebase fact; edits invalidate items, which card schedulers do not model |
| Desirable difficulties | Organising principle (Bjork 1994); components measured separately | Difficulty must be surmountable | Friction that forces recall or prediction before reveal, sized for usual success |
| Generation effect | Meta-analytic, d=0.40 (Bertsch 2007) | Generate the target from an actionable cue; reverses when generation fails | Write the expected signature, invariant, or design before seeing the agent's |
| Self-explanation / elaborative interrogation | Meta-analytic, g=0.55 (Bisra 2018); "moderate utility" (Dunlosky 2013) | Ask for mechanism, not paraphrase; needs prior knowledge; costs time | Explain why a change is correct and what it depends on before approval; teach-back gate (n=78 study) |
| Interleaving | Meta-analytic, g=0.42, material-dependent, null for text (Brunmair & Richter 2019) | Similar, confusable categories | Alternate review across parallel modules to force discrimination; no support for unrelated files |
| Worked examples / expertise reversal | Replicated within cognitive load theory (Sweller & Cooper 1985; Kalyuga 2003) | Helps novices; redundant or harmful for experts | Agent output as worked example for unfamiliar subsystems; generation-first where the developer holds the theory |
| Teaching / protégé effect | Meta-analytic, g=0.35 prepare, 0.56 teach (Kobayashi 2019) | Explanation must be produced; audience helps | Explain a subsystem to a colleague, newcomer, or questioning agent |
| Illusion of competence | Robust laboratory effect (Koriat & Bjork 2005, 2006) | Answer visible while judging own knowledge | Diff reading is the bias condition; retrieval before reveal is the remedy |
| Code tracing / EiPE / Parsons | Computing-education studies on novices (Lister 2004; Lopez 2008; Murphy 2012; Ericson 2017) | Small programs; correlational for EiPE | EiPE-style purpose questions as a situation-model probe; tracing a data path by hand |
| Reading and approving | Negative-leaning (Bacchelli & Bird 2013; Kaufman 2026; Qiao 2025) | Understanding is the bottleneck; verification predicts comprehension | Approval without verification or explanation transfers the program model at most |

## Dead ends and gaps

- No study found that measures retention of a developer's model of a real,
  evolving codebase over weeks or months under agentic delegation; every
  AI-specific study above is a single session of one hour or less, except
  METR (weeks, but time-only) and Kosmyna (four sessions, essays). (added
  2026-09-13: Gardella et al., ICER 2026, <https://arxiv.org/abs/2604.18538>,
  is the first AI-coding study found with a retention interval — one week,
  22 novices, retest −18.9 points; Borg et al.,
  <https://arxiv.org/abs/2507.00788>, is a 151-participant, 95%-professional
  two-phase experiment without a comprehension instrument; see the
  [literature addendum](literature-addendum.md#corrections-proposed).)
- No study found that applies spaced retrieval to code comprehension in
  professionals; searches for "spaced repetition" with "code comprehension"
  or "software maintenance" returned flashcard tools for syntax and no
  controlled study.
- No study found on ownership or authorship perception of agent-written code
  in professional teams; the ownership evidence is Kosmyna's essay
  interviews and the authorship-metric literature (Bird 2011; Wheeler 2026,
  position only). (added 2026-09-13: Shukla and Sharma's eleven-interview
  thesis, not peer reviewed, and Choudhuri et al.'s 448-developer
  identity/accountability survey are the nearest; still no quantitative
  ownership instrument — see the
  [literature addendum](literature-addendum.md#corrections-proposed).)
- Searches of CHI, ICSE, FSE, and CSCW 2025–2026 titles for "comprehension"
  with "AI-generated code" surfaced Qiao et al. (arXiv, venue unconfirmed),
  Kaufman et al. (arXiv), and grey-literature reviews of vibe coding
  (Ericson et al. 2017 aside); no venue-published comprehension RCT on
  professionals was found beyond Shen and Tamkin's preprint.
- Effect sizes for Adesope et al. (2017) and the Roediger and Karpicke (2006)
  percentages were confirmed only from secondary reports and memory of the
  papers, not the paywalled full texts. Updated 2026-09-13: the Roediger and
  Karpicke percentages are now verified from the Purdue learning-lab PDF
  (above); Adesope's g = 0.61 remains unverified against the full text
  (Crossref, ERIC, Semantic Scholar, Unpaywall and CORE returned abstract or
  nothing) but is quoted with a confidence interval by two open-access
  papers, so treat it as secondary-corroborated.
- Storey's *ACM Queue* article and Osmani's O'Reilly republication returned
  403; the arXiv version and the author's own site were used instead.
- The Anthropic study's participant platform is described from the paper's
  demographics section; the recruitment site name was not extracted.
- Cognitive-dimensions research (Green and Petre) is a notation-analysis
  framework and yielded no measurement of comprehension loss; listed for
  completeness.
- Kosmyna et al. cite "absence of ownership of generated content at 16%" and
  "deskilling happening in 3 months" from other reports ([129], [130] in the
  preprint). Resolved 2026-09-13 from the v2 reference list: [129] is The
  Economist, "At home and at school: AI is transforming childhood",
  2025-12-04 (paywalled; the 16% figure could not be checked), and [130] is
  Budzyń et al., "Endoscopist deskilling risk after exposure to artificial
  intelligence in colonoscopy", *Lancet Gastroenterology & Hepatology*
  10(10):896–903, 2025, doi:10.1016/S2468-1253(25)00133-5 — a retrospective
  study at four Polish centres in which the adenoma detection rate of non-AI
  colonoscopies fell from 28.4% to 22.4% in the three months after AI tools
  were introduced (abstract via Europe PMC). Neither concerns software
  development; the "3 months" is that study's observation window.

## References

Primary sources, alphabetical. URLs above are the terminal citations.

- Adesope, O. O., Trevisan, D. A., Sundararajan, N. (2017). Rethinking the use of tests: a meta-analysis of practice testing. *Review of Educational Research* 87(3):659–701. doi:10.3102/0034654316689306.
- Anki manual. Deck options: FSRS and legacy scheduler. https://docs.ankiweb.net/deck-options.html
- Bacchelli, A., Bird, C. (2013). Expectations, outcomes, and challenges of modern code review. *ICSE 2013*. https://www.microsoft.com/en-us/research/publication/expectations-outcomes-and-challenges-of-modern-code-review/
- Baum, T., Schneider, K., Bacchelli, A. (2019). Associating working memory capacity and code change ordering with code review performance. *Empirical Software Engineering* 24:1762–1798. doi:10.1007/s10664-018-9676-8.
- Bertsch, S., Pesta, B. J., Wiscott, R., McDaniel, M. A. (2007). The generation effect: a meta-analytic review. *Memory & Cognition* 35(2):201–210. doi:10.3758/BF03193441.
- Bird, C., Nagappan, N., Murphy, B., Gall, H., Devanbu, P. (2011). Don't touch my code! *ESEC/FSE 2011*. doi:10.1145/2025113.2025119.
- Bisra, K., Liu, Q., Nesbit, J. C., Salimi, F., Winne, P. H. (2018). Inducing self-explanation: a meta-analysis. *Educational Psychology Review* 30:703–725. doi:10.1007/s10648-018-9434-x.
- Bjork, R. A. (1994). Memory and metamemory considerations in the training of human beings. In Metcalfe, J., Shimamura, A. (eds.), *Metacognition*, MIT Press, 185–205.
- Bjork, E. L., Bjork, R. A. (2011). Making things hard on yourself, but in a good way. In *Psychology and the Real World*, Worth, 56–64.
- Bjork, R. A., Dunlosky, J., Kornell, N. (2013). Self-regulated learning: beliefs, techniques, and illusions. *Annual Review of Psychology* 64:417–444. doi:10.1146/annurev-psych-113011-143823.
- Brooks, R. (1983). Towards a theory of the comprehension of computer programs. *IJMMS* 18(6):543–554.
- Brunmair, M., Richter, T. (2019). Similarity matters: a meta-analysis of interleaved learning and its moderators. *Psychological Bulletin* 145(11):1029–1052. doi:10.1037/bul0000209.
- Cepeda, N. J., Pashler, H., Vul, E., Wixted, J. T., Rohrer, D. (2006). Distributed practice in verbal recall tasks. *Psychological Bulletin* 132(3):354–380.
- Cepeda, N. J., et al. (2008). Spacing effects in learning: a temporal ridgeline of optimal retention. *Psychological Science* 19(11):1095–1102.
- Chase, C. C., Chin, D. B., Oppezzo, M. A., Schwartz, D. L. (2009). Teachable agents and the protégé effect. *J. Science Education and Technology* 18:334–352.
- Chi, M. T. H., Bassok, M., Lewis, M. W., Reimann, P., Glaser, R. (1989). Self-explanations. *Cognitive Science* 13(2):145–182.
- Chi, M. T. H., de Leeuw, N., Chiu, M.-H., LaVancher, C. (1994). Eliciting self-explanations improves understanding. *Cognitive Science* 18(3):439–477.
- DORA (2025). State of AI-assisted Software Development. https://dora.dev/dora-report-2025/
- Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., Willingham, D. T. (2013). Improving students' learning with effective learning techniques. *PSPI* 14(1):4–58. doi:10.1177/1529100612453266.
- Ericson, B. J., Margulieux, L. E., Rick, J. (2017). Solving Parsons problems versus fixing and writing code. *Koli Calling 2017*. doi:10.1145/3141880.3141895.
- Ericson, B. J., et al. (2022). Parsons problems and beyond. ITiCSE working group. doi:10.1145/3571785.3574127.
- Fiorella, L., Mayer, R. E. (2013). The relative benefits of learning by teaching and teaching expectancy. *Contemporary Educational Psychology* 38(4):281–288.
- Fowler, M., Chen, B., Zilles, C. (2021). How should we "Explain in plain English"? *ICER 2021*. https://zilles.cs.illinois.edu/papers/how_to_eipe_icer_2021.pdf
- FSRS. open-spaced-repetition/fsrs4anki wiki, The Algorithm. https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm
- GitHub (2025). Survey: the AI wave continues to grow on software development teams. https://github.blog/news-insights/research/survey-ai-wave-grows/
- Green, T. R. G., Petre, M. (1996). Usability analysis of visual programming environments: a "cognitive dimensions" framework. *JVLC* 7(2):131–174.
- JetBrains (2025). State of Developer Ecosystem 2025, AI section. https://devecosystem-2025.jetbrains.com/artificial-intelligence
- Kalyuga, S., Ayres, P., Chandler, P., Sweller, J. (2003). The expertise reversal effect. *Educational Psychologist* 38(1):23–31.
- Karpicke, J. D., Blunt, J. R. (2011). Retrieval practice produces more learning than elaborative studying with concept mapping. *Science* 331:772–775.
- Karpicke, J. D., Butler, A. C., Roediger, H. L. (2009). Metacognitive strategies in student learning. *Memory* 17(4):471–479.
- Kaufman, Z., Brun, Y., Murali, A., Endres, M. (2026). Programmers are poor and overconfident judges of LLM-generated assertions. arXiv:2607.08885.
- Kazemitabaar, M., Huang, O., Suh, S., Henley, A. Z., Grossman, T. (2024). Exploring the design space of cognitive engagement techniques with AI-generated code for enhanced learning. arXiv:2410.08922.
- Ko, A. J., DeLine, R., Venolia, G. (2007). Information needs in collocated software development teams. *ICSE 2007*.
- Kobayashi, K. (2019). Learning by preparing-to-teach and teaching: a meta-analysis. *Japanese Psychological Research* 61(3):192–203.
- Koriat, A., Bjork, R. A. (2005). Illusions of competence in monitoring one's knowledge during study. *JEP: LMC* 31(2):187–194.
- Koriat, A., Bjork, R. A. (2006). Illusions of competence during study can be remedied. *Memory & Cognition* 34(5):959–972.
- Kosmyna, N., et al. (2025). Your brain on ChatGPT. arXiv:2506.08872.
- LaToza, T. D., Venolia, G., DeLine, R. (2006). Maintaining mental models: a study of developer work habits. *ICSE 2006*.
- Lee, H.-P. (H.), Sarkar, A., Tankelevitch, L., Drosos, I., Rintel, S., Banks, R., Wilson, N. (2025). The impact of generative AI on critical thinking. *CHI 2025*. doi:10.1145/3706598.3713778.
- Letovsky, S. (1987). Cognitive processes in program comprehension. *J. Systems and Software* 7(4):325–339.
- Lister, R., et al. (2004). A multi-national study of reading and tracing skills in novice programmers. *SIGCSE Bulletin* 36(4):119–150.
- Lopez, M., Whalley, J., Robbins, P., Lister, R. (2008). Relationships between reading, tracing and writing skills in introductory programming. *ICER 2008*.
- Maier, S., Gunzenhäuser, M., Schweisthal, J., Schneider, M., Feuerriegel, S. (2026). A meta-analysis of the effect of generative AI on productivity and learning in programming. arXiv:2605.04779.
- METR (2025). Measuring the impact of early-2025 AI on experienced open-source developer productivity. arXiv:2507.09089; and METR (2026-02-24), We are changing our developer productivity experiment design. https://metr.org/blog/2026-02-24-uplift-update/
- Murphy, L., Fitzgerald, S., Lister, R., McCauley, R. (2012). Ability to "explain in plain English" linked to proficiency in computer-based programming. *ICER 2012*.
- Naur, P. (1985). Programming as theory building. *Microprocessing and Microprogramming* 15(5):253–261.
- Osmani, A. (2026). Comprehension debt: the hidden cost of AI-generated code. https://addyosmani.com/blog/comprehension-debt/
- Parsons, D., Haden, P. (2006). Parson's programming puzzles. *ACE 2006*.
- Pascarella, L., Spadini, D., Palomba, F., Bruntink, M., Bacchelli, A. (2018). Information needs in contemporary code review. *CSCW 2018*. doi:10.1145/3274404.
- Pennington, N. (1987). Stimulus structures and mental representations in expert comprehension of computer programs. *Cognitive Psychology* 19(3):295–341.
- Perry, N., Srivastava, M., Kumar, D., Boneh, D. (2023). Do users write more insecure code with AI assistants? *CCS 2023*.
- Pressley, M., McDaniel, M. A., Turnure, J. E., Wood, E., Ahmad, M. (1987). Generation and precision of elaboration. *JEP: LMC* 13(2):291–300.
- Qiao, Y., Shihab, M. I. H., Haque, S., Hundhausen, C. (2025). Code comprehension with GitHub Copilot. arXiv:2511.02922.
- Roediger, H. L., Karpicke, J. D. (2006). Test-enhanced learning. *Psychological Science* 17(3):249–255.
- Rohrer, D., Taylor, K. (2007). The shuffling of mathematics problems improves learning. *Instructional Science* 35:481–498.
- Rowland, C. A. (2014). The effect of testing versus restudy on retention. *Psychological Bulletin* 140(6):1432–1463.
- Sadowski, C., Söderberg, E., Church, L., Sipko, M., Bacchelli, A. (2018). Modern code review: a case study at Google. *ICSE-SEIP 2018*.
- Sankaranarayanan, S. (2026). Mitigating "epistemic debt" in generative AI-scaffolded novice programming using metacognitive scripts. arXiv:2602.20206.
- Sarkar, A., Drosos, I. (2025). Vibe coding: programming through conversation with artificial intelligence. arXiv:2506.23253.
- Shen, J. H., Tamkin, A. (2026). How AI impacts skill formation. arXiv:2601.20245.
- Slamecka, N. J., Graf, P. (1978). The generation effect. *JEP: Human Learning and Memory* 4(6):592–604.
- Soloway, E., Ehrlich, K. (1984). Empirical studies of programming knowledge. *IEEE TSE* SE-10(5):595–609.
- Stack Overflow (2025). 2025 Developer Survey, AI section. https://survey.stackoverflow.co/2025/ai
- Stanković, M., Hirche, E., Kollatzsch, S., Doetsch, J. N. (2025). Comment on: Your brain on ChatGPT. arXiv:2601.00856.
- Storey, M.-A. (2006). Theories, methods and tools in program comprehension. *Software Quality Journal* 14(3):187–208.
- Storey, M.-A. (2026). From technical debt to cognitive and intent debt. arXiv:2603.22106.
- SuperMemo. Algorithm SM-2. https://www.supermemo.guru/wiki/Algorithm_SM-2
- Su, J., Ye, J., Nie, L., Cao, Y., Su, Y. (2023). Optimizing spaced repetition schedule by capturing the dynamics of memory. *IEEE TKDE*. doi:10.1109/TKDE.2023.3251721.
- Sweller, J., Cooper, G. A. (1985). The use of worked examples as a substitute for problem solving in learning algebra. *Cognition and Instruction* 2(1):59–89.
- von Mayrhauser, A., Vans, A. M. (1995). Program comprehension during software maintenance and evolution. *IEEE Computer* 28(8):44–55.
- Whalley, J., et al. (2006). An Australasian study of reading and comprehension skills in novice programmers. *ACE 2006*.
- Wheeler, B. (2026). The substrate collapse: AI code generation invalidates authorship-based knowledge metrics. arXiv:2606.20882.
- Wiedenbeck, S. (1986). Beacons in computer program comprehension. *IJMMS* 25(6):697–709.
- Xie, B., et al. (2019). A theory of instruction for introductory programming skills. *Computer Science Education* 29(2–3):205–253.
- Ye, J., Su, J., Cao, Y. (2022). A stochastic shortest path algorithm for optimizing spaced repetition scheduling. *KDD 2022*. doi:10.1145/3534678.3539081.
