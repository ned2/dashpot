---
status: research
date: 2026-09-13
---

# Knowing it works: measuring understanding and its loss

Research date: 2026-09-13

This note is the Phase B deep pass on measurement for Dashpot's cognitive-debt research. It
documents how a developer's understanding of a codebase, and its erosion under agentic
delegation, has been detected or measured, and how an intervention's effect on
understanding has been or could be evaluated. It records instruments as the studies
describe them, proxies and telemetry as their documentation defines them, survey items as
their instrument pages word them, position papers as they state their own proposals and
limits, the arguments against measuring, and the evaluation designs the sources used or
call for. Terminal citations are primary: the paper, the preregistration, the tool's
documentation, the survey's own page. Nothing here evaluates fit for Dashpot or any
workflow, ranks, recommends, or designs a metric. Phase A is cited by relative link rather
than repeated.

## The idea

"Knowing it works" is the measurement question left open by every other Phase B track:
whether understanding of a codebase can be observed at all, and if so whether any
countermeasure moves it. Phase A found that every proposal to measure comprehension under
AI authorship is a position paper (the "Substrate Collapse" paper, the Degree-of-Knowledge
study), that the only deployed instrument is a self-report maintainability item, that
Thoughtworks names a cognitive-load technique without a tool, that Kognita and git-ai's
AI-share are proxies, that no comprehension telemetry ships, and that Answer.AI argues
explicitly against quantifying learning
([landscape sweep, Cluster 9](landscape-sweep.md#cluster-9--measurement-and-detection);
[observations for the deep pass](landscape-sweep.md#observations-for-the-deep-pass);
[Answer.AI sweep, core claim 15](answer-ai-sweep.md#core-claims)). The evidence note
catalogued the AI-and-comprehension studies by headline result
([AI-specific evidence, 2023–2026](evidence-and-mechanisms.md#ai-specific-evidence-20232026))
and named "explain in plain English" as "the closest existing instrument to 'does the
developer hold the situation model'"
([computing-education evidence](evidence-and-mechanisms.md#computing-education-evidence-on-reading-code)).
This pass opens each of those instruments and proxies to see what they actually measure.

## Instruments used in studies

### The AI-and-comprehension studies

**Shen and Tamkin (2026).** Skill formation is a score on a post-task quiz about the Python
Trio library, taken immediately after a 35-minute coding task with or without a GPT-4o chat
assistant; N = 52 randomised, 51 analysed. The quiz has "14 questions for a total of 27
points," covers "debugging, code reading, and conceptual questions" and excludes code
writing "to reduce the impact of syntax errors"; "We tested 5 versions (Table 2) of the quiz
in user testing and preliminary studies based on item response theory," checking item–total
correlation, mean item score, and the absence of local item dependence, and the grading
rubric was submitted in the preregistration ([arXiv:2601.20245](https://arxiv.org/html/2601.20245)).
The preregistration scores "1 point for multiple choice questions, 2 points for open answer
questions, and 2 points for multi-select questions (0.5 penalty for an incorrect multi-select
selection)"; its rubric lists 16 scored items plus an attention check, including open items
such as "Review the following code snippet and identify the bug" and fill-in items that
present "a modification of your function from task 1" using a canonical function rather than
the participant's own code ([OSF w49e7](https://osf.io/w49e7)). The paper's 14-item count and
its exclusion of code writing do not reconcile with the preregistration's 16 items and its
"code writing" type; the paper does not state who graded open items or any inter-rater
reliability, and the OSF storage holds no files. The six interaction patterns come from
manual annotation of screen recordings (events such as AI Query, Websearch, Paste, Code
Copying), with annotator count and agreement not reported; annotated transcripts are in the
public repository ([GitHub](https://github.com/safety-research/how-ai-impacts-skill-formation)).
Preregistered outcomes were "Time Per Task (minutes) ~ Treatment; Quiz Score (points) ~
Treatment"; the headline result and Phase A's reading are in the
[evidence note](evidence-and-mechanisms.md#ai-specific-evidence-20232026).

**Qiao, Shihab, Haque, and Hundhausen (2026).** Fifteen graduate students, within-subject,
No-Copilot always first, two 30-minute feature tasks on a 3,818-line web application, each
"concluding with a 10-minute comprehension assessment" of "seven multiple-choice questions
and one open-ended question covering five comprehension dimensions": System Objective,
Implementation, Bug, Reverse Engineering ("Predicting behavior if code were removed," e.g.
"How would the application behavior change if we removed the code block from
editProfileForm.addEventListener() in editProfile.js?"), and an open synthesis item. Open
responses were scored by two authors on a 0–3 rubric with "Krippendorff's α=0.95 for
Control, α=0.86 for Experimental"; the table totals 15 points while results report scores
"out of 13," unexplained. Screen recordings were coded into View Code, Write Code, Test
Code and Copilot categories (three coders, α = 0.828 on a 20% sample); the "verification
loop" is the transition pair WC→VC and VC→WC, and high-comprehension participants had
"P(WC→VC)=0.409 vs 0.200, p=0.002" and "P(VC→WC)=0.329 vs 0.156, p=0.032." The authors
name "the potential shallowness of our comprehension questions" and the fixed condition
order as threats; the full question set is not published
([arXiv:2511.02922](https://arxiv.org/html/2511.02922)).

**Sankaranarayanan (2026).** Three groups of 26 (manual, unrestricted AI, AI with an
"Explanation Gate"), a 90-minute React build scored by "a headless Puppeteer/Jest test
harness that executed 12 end-to-end assertions," then a 30-minute "blackout" in which "AI
access was revoked for all groups" and "a git patch [was used] to inject a logic bomb"
(stripped `await`s and deleted rollback logic). The outcome is "Corrective Competence,
measured as a binary Repair Success (resolved vs. unresolved) and Time-to-Fix"; the
replication protocol's pass rule is a demonstrated enrol, refresh, and persist check within
30 minutes. The gate itself is GPT-4o at temperature 0.1 judging a typed explanation against
a SOLO rubric with "Passing threshold: score ≥ 3"; the paper reports calibration "with the
help of an expert learning designer" and no human-agreement statistic for the judge. The
paper says the patch went into "their functioning codebase," while the protocol hands out a
pre-built buggy app; the construct-validity passage concedes "Critics might argue that this
measures debugging skill rather than understanding"
([arXiv:2602.20206](https://arxiv.org/html/2602.20206);
[replication package](https://github.com/sreecharansankaranarayanan/vibecheck)).

**Kaufman, Brun, Murali, and Endres (2026).** Eighty-six retained participants judged ten
stimuli each, a HumanEval function with one LLM-generated postcondition assertion and an
optional comment: "Participants assessed whether the postcondition accurately described the
function's behavior, assuming the provided implementation was correct," rated completeness,
and "reported confidence using a 0–5 Likert-style scale." Accuracy is agreement with a
dataset ground truth; accuracy was 73.9% on correct and 49.0% on incorrect postconditions
while confidence stayed "uniformly high in all cases (3.98–4.14)." Only the comment
hypotheses were preregistered; the think-aloud codebook was applied by the first author
after joint coding of one transcript, with no reliability statistic; stimuli are
benchmark functions, not the participant's code
([arXiv:2607.08885](https://arxiv.org/html/2607.08885);
[OSF, view-only](https://osf.io/q6d2m/overview?view_only=442a1b8d82554de0baa4b4083987a6b6)).

**Perry, Srivastava, Kumar, and Boneh (2023).** Forty-seven analysed participants, five
security tasks; "two raters manually coded each response" into Secure, Partially Secure, or
Insecure, with Cohen's kappa "0.7-0.96 for correctness and 0.68-0.88 for security." The
belief measure is a per-task exit survey: "I think I solved this task correctly," "I think I
solved this task securely," "I feel comfortable in this programming language," and, for the
AI group, "I trusted the AI to produce secure code," on a five-point agreement scale whose
deployed anchors are not printed in the paper (the repository's in-app definition lists
Strongly Agree to Strongly Disagree plus "I Don't Know"). No comprehension or learning test
was taken ([arXiv:2211.03622](https://arxiv.org/html/2211.03622);
[repository](https://github.com/NeilAPerry/Do-Users-Write-More-Insecure-Code-with-AI-Assistants)).

**Maier, Gunzenhäuser, Schweisthal, Schneider, and Feuerriegel (2026).** The meta-analysis
defines learning as "the measurable acquisition of programming skills," "primarily measured
via exam scores following a learning phase," and where midterms and finals both exist "we
selected the final exam score." The ten learning studies (11 effect sizes, 1,069
participants) all use course exams or post-tests scored 0–100 or 0–10, including a midterm
(Kosar et al. 2024), pre-test-controlled programming-ability tests (Choi and Kim 2025; Yang
et al. 2025), a beginner final that "tested retention" with "AI allowed during study period
but not during exam" (Suh et al. 2025), and Kazemitabaar et al.'s immediate post-test with
authoring tasks; one study's outcome scale is "not explicitly stated." Pooled g = 0.14
[−0.18, 0.47], I² = 86%; the one significant moderator is exam environment, and the authors
note "the actual GenAI use was often not controlled for, which implies that the study design
captures treatment assignment, not adherence"
([arXiv:2605.04779](https://arxiv.org/html/2605.04779);
[data](https://github.com/SM2982/MetaanalysisGenAICoding)).

**Kosmyna et al. (2025).** Fifty-four analysed participants, three sessions of a 20-minute
SAT-style essay under EEG, a fourth crossover session for 18. The comprehension-adjacent
instrument is a five-minute post-session interview whose template includes "Can you quote
any sentence from your essay without looking at it? If yes, please, provide the quote" and
"Can you summarize the main points or arguments you made in your essay?"; quoting is
scored as two binary counts, ability to quote and correct quoting, and the paper describes
no procedure for judging a quote correct. Session 1: "83.3% of participants (15/18) [LLM]
failed to provide a correct quotation, whereas only 11.1% (2/18) in both the Search-Engine
and Brain-Only groups." Essays were scored 0–5 by two English teachers on Uniqueness,
Vocabulary, Grammar, Organization, Content, Length and a "ChatGPT" judgement, with no
inter-teacher statistic, and by an agentic AI judge that "was more statistically inclined to
evaluate everything around a score of 4." EEG connectivity (dDTF) is offered as an
engagement and load proxy; the link to quoting is interpretive: reduced connectivity
"likely reflected a bypass of deep memory encoding processes"
([arXiv:2506.08872](https://arxiv.org/pdf/2506.08872)).

**Kazemitabaar et al. (2024).** Study 1 (N = 82, eight engagement techniques) balanced groups
on "five multiple-choice code tracing questions" and evaluated with "two manual coding tasks
without AI assistance," each "isomorphic" to a training task, in the same session after a
break; rubrics were applied by the first author alone. Study 2 (N = 42, within-subject)
evaluated with "six fill-in-the-blank tasks" after a 15-minute break and asked one five-point
item on confidence "to independently write, modify, or extend code of similar complexity";
Spearman correlations between perceived and actual ability were r = .26 (Lead-and-Reveal),
.16 (Baseline), .15 (Trace-and-Predict), and Study 1 was "underpowered... To reach 90%
power, a sample size of 153 would be required"
([arXiv:2410.08922](https://arxiv.org/html/2410.08922)).

| Study | N | Instrument | Grader and reliability | Delay | Tests the participant's own code? | Instrument public? |
|---|---|---|---|---|---|---|
| Shen and Tamkin | 51 | 27-point Trio quiz (MCQ, multi-select, open) | not stated | immediate | no, canonical task code | rubric text in OSF registration only |
| Qiao et al. | 15 | 8 questions per feature, five dimensions | two authors, α .95/.86 on open item | immediate | legacy codebase just modified | sample items only |
| Sankaranarayanan | 78 | blackout repair task; GPT-4o SOLO gate | functional check; judge validity unreported | immediate | own app (paper) / pre-built app (protocol) | full package |
| Kaufman et al. | 86 + 10 | assertion judgement plus 0–5 confidence | dataset ground truth | none | no, benchmark functions | OSF view-only |
| Perry et al. | 47 | security classification plus belief Likert | two raters, κ .68–.96 | immediate | own code | repository and data |
| Maier et al. | 10 studies | included studies' exam or test scores | varies | mostly end of course | n/a | data spreadsheet |
| Kosmyna et al. | 54 | interview quoting and summary; teacher and AI essay scores | unspecified; two teachers | immediate; session 4 recall | own essay | no |
| Kazemitabaar et al. 2024 | 82 / 42 | isomorphic and fill-in-the-blank coding tasks plus confidence item | first author only | same session after break | isomorphic to training code | tool source only |

### Classic comprehension instruments

**Explain in Plain English (EiPE).** The item and SOLO rubric originate in Whalley et al.
(ACE 2006): "In plain English, explain what the following segment of code does:" over a
loop that checks an array is ordered, scored Relational, Multistructural, Unistructural,
Prestructural or Blank, with 69 responses at one institution and no inter-rater statistic
([AUT repository](https://openrepository.aut.ac.nz/bitstreams/fc672554-55f2-4982-bc53-c016749b74ef/download)).
Sheard et al. (2008) added sub-categories (relational-with-error, incomplete, and so on) and
the rule that a response giving both a relational and a multistructural answer "was deemed
to be relational" ([UTS repository](https://opus.lib.uts.edu.au/bitstream/10453/10719/1/2008001283.pdf)).
The only verified inter-rater figures for the SOLO rubric are Corney et al. (2014): five
analysts, pairwise Spearman rho averaging 0.817 and 0.885 on two problems before
negotiation and 0.921 and 0.936 after, with a rho of 0.508 between SOLO level and the rest
of the exam ([QUT ePrints](https://eprints.qut.edu.au/68093/3/68093.pdf)). Chen et al.
(SIGCSE 2020) replaced SOLO with a seven-point rubric because it "didn't adequately handle
the three dimensions of answer quality: correctness, level of abstraction, and ambiguity";
on 10,024 responses the "median Krippendorff's alpha was 0.775," Cronbach's alpha 0.954,
and Pearson r = 0.555 with code writing; ties go to the lower category
([Zilles group](https://zilles.cs.illinois.edu/papers/EiPE_rubric_sigcse_2020.pdf)). Fowler,
Chen, and Zilles (ICER 2021) is an interview study of eleven graders, not a rubric paper:
"All of our subjects appeared to use a distance metric from gold standard answers to assign
partial credit," and "Incompleteness and ambiguity tend to be more acceptable than
incorrectness" ([Zilles group](https://zilles.cs.illinois.edu/papers/how_to_eipe_icer_2021.pdf)).
Autograding: a bag-of-words logistic classifier reached "87–89%, which is similar in
performance to course teaching assistants" ([SIGCSE 2021](https://zilles.cs.illinois.edu/papers/fowler_EiPE_NLP_SIGCSE_2021.pdf));
Code Generation Based Grading splices the explanation into a fixed prompt ("Generate a
function 'studentCode' that `<StudentResponse>`"), runs the generated function against unit
tests, and agrees with humans at Cohen's κ = .58 with "leniency with respect to low-level
and line-by-line descriptions" ([ITiCSE 2024](https://zilles.cs.illinois.edu/papers/smith_eipe_cgbg_ITiCSE_2024.pdf)).
Phase A's placement of EiPE is in the
[evidence note](evidence-and-mechanisms.md#computing-education-evidence-on-reading-code).

**Code-tracing tests.** The 2004 ITiCSE working group used twelve multiple-choice items in
fixed-code (select the output) and skeleton-code (select the completing line) forms, chosen
"to score student performance on the MCQs that did not require subjective judgment," with
941 students, quartile distractor analysis, 37 think-aloud interviews and categorised
"doodles"; no reliability coefficient is reported and all items are in the appendix
([CiteSeerX](https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=161d617890001703cb3dc6334cbc175f264a2a57)).
Lopez et al. (2008) Rasch-scaled one exam into Basics, Sequence, Tracing, Explain, and
Writing and found tracing and explaining "account for 46% of the variance in Writing"
([UTS repository](https://opus.lib.uts.edu.au/bitstream/10453/10806/1/2008001530.pdf)).

**Pennington's question types.** The primary texts were not obtained (see Dead ends).
Feitelson's secondary account: "Pennington suggested using questions on the program's
control flow (will the last record be counted?) and data flow (does the value of variable a
affect that of b?), its states (will c have a certain value after the loop?), and specific
operations (is d initialized to 0?)" ([EMSE 2022 preprint](http://www.cs.huji.ac.il/~feit/papers/Pitfalls22EmpSE.pdf));
the fifth ("function") type and the program-model versus situation-model mapping are
unverified here.

**Sillito, Murphy, and De Volder's 44 questions.** The primary papers were blocked; the full
list is verified from its verbatim reproduction in Kubelka, Bergel, and Robbes (2014), in
four groups: finding focus points (1–5, e.g. "Where in the code is the text in this error
message or UI element?"), expanding focus points (6–20, e.g. "Where is this method called
or type referenced?"), understanding a subgraph (21–33, e.g. "How is control getting (from
here to) here?", "Under what circumstances is this method called or an exception thrown?"),
and questions over groups of subgraphs (34–44, e.g. "What will the total impact of this
change be?", "Will this completely solve the problem or provide the enhancement?")
([Kubelka et al.](https://bergel.eu/MyPapers/Kube14a-ProgrammingPharo.pdf)). Session
counts and coding method of the original are unverified.

**LaToza and Myers.** Both 2010 papers are chapters of LaToza's dissertation. The
hard-to-answer-questions survey asked 460 Microsoft respondents "What other hard to answer
questions about code have you recently asked?"; 374 questions were clustered into 92 and
18 categories, with Rationale (42 reports) and Contracts (54) the largest and hardness
established by self-nomination. The reachability survey rated twelve questions drawn from
Sillito for frequency and difficulty "on a 7 point scale from very hard to very easy";
developers asked more than nine of these questions a day, 1.9 rated hard or very hard, and
"What are the implications of this change?" was hardest (63% at least somewhat difficult);
the observational study coded 17 think-aloud sessions minute by minute
([CMU-ISR-12-104](http://reports-archive.adm.cs.cmu.edu/anon/isr2012/CMU-ISR-12-104.pdf)).

**Mental-model elicitation.** Concept maps as defined by Novak and Cañas: "graphical tools
for organizing and representing knowledge" built from concepts, linking words, and
propositions to a focus question, usable "not only as a learning tool but also as an
evaluation tool," with CmapTools' compare-to-expert function
([IHMC](https://cmap.ihmc.us/docs/theory-of-concept-maps.php)). Think-aloud protocols are
used as the supplementary instrument in Lister et al. (2004), LaToza (2012), and Hassan and
Zilles (2023), whose EiPE prompt reads "Write a short, high-level English language
description of the code below. Do not give a line-by-line description."
([Zilles group](https://zilles.cs.illinois.edu/papers/)). Teach-back interviews, Ericsson
and Simon, von Mayrhauser and Vans, and Rouse and Morris's limits on mental-model
elicitation were not reached and are unverified here.

**Knowledge tracing.** Bayesian Knowledge Tracing is "typically specified by four
parameters": prior mastery, learning transition, guess, and slip, with the assumption that
"K cannot transition from 1 to 0," a binary knowledge state, and skills known in advance
([Khajah, Lindsey, Mozer](https://arxiv.org/pdf/1604.02416)). Deep Knowledge Tracing
predicts the next response from one-hot exercise–correctness pairs with an LSTM and
reports AUC 0.86 versus BKT's 0.67 on Assistments ([Piech et al.](https://arxiv.org/abs/1506.05908));
Khajah et al. attribute 31.6% of that gap to "a biased procedure for computing the AUC
for BKT" and another 50.6% to BKT lacking forgetting. Corbett and Anderson's primary text
is a scanned image; programming applications of knowledge tracing were not fetched.

**Standardised tests and methodology reviews.** Siegmund et al.'s fMRI study operationalised
comprehension as determining the output of short obfuscated Java snippets, pre-selected in
a 41-student prestudy ([ICSE 2014](https://www.cs.cmu.edu/~ckaestne/pdf/icse14_fmri.pdf));
their programming-experience questionnaire found self-estimated experience correlating
0.539 with the number of correct comprehension answers ([EMSE 2014](https://www.cs.cmu.edu/~ckaestne/pdf/ese13.pdf)).
Oliveira et al.'s review of 54 readability studies counts correctness in 45, opinion in 30,
time in 27, eye tracking in 4, brain measures in 3 ([arXiv:2110.00785](https://arxiv.org/abs/2110.00785)).
Feitelson's task taxonomy runs from recognition and parsing through "what does this print,"
"name this function," bug fixing, modification, API use and refactoring, flags recall tasks
as problematic, and says "we also need to find a way to operationalize what 'comprehension'
actually means" ([EMSE 2022 preprint](http://www.cs.huji.ac.il/~feit/papers/Pitfalls22EmpSE.pdf));
his CACM article adds that error rate "is not equivalent to the metric of time to correct
answer" ([CACM 2023 preprint](http://www.cs.huji.ac.il/~feit/papers/Comp23CACM.pdf)).
Wyrich, Bogner, and Wagner's base rates are in [Evaluation designs](#evaluation-designs).

## Proxies and telemetry

**Code ownership.** Bird et al. (2011) define "Proportion of Ownership... the ratio of number
of commits that the contributor has made relative to the total number of commits for that
component," a minor contributor as one below 5% and a major one at or above it, and the
component metrics Minor, Major, Total, and Ownership; the knowledge framing is explicit:
"there is a wealth of literature that uses the prior development activity on a component
as a proxy for expertise and knowledge," and "If ownership... is a valid proxy for
expertise, then what is the effect of having most changes made by those with little
expertise?" Minor "had a higher correlation with both pre- and post-release defects in
Vista and pre-release defects in Windows 7 than any other metric that Microsoft collects!";
the authors caution that Microsoft "employs strong ownership practices" and that open
source is untested ([Microsoft Research PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf)).
Rahman and Devanbu use line-level blame ("contribution ratio for author a is r_a = N_ab /
N_b. We call this authorship") and find "lack of specialized experience on a particular
file is associated with implicated code" while "lack of general (non-specialized) experience
is not consistently associated" ([archived PDF](https://web.archive.org/web/20160208035713id_/http://www.inf.usi.ch:80/faculty/lanza/Education/SDE-2011/papers/Rahm2011a.pdf)).
Greiler, Herzig, and Czerwonka's replication moves the threshold to 50%, adds directory
level, and states "code ownership relates to the knowledge engineers have about code"
alongside "strong ownership prohibits knowledge transfer"
([MSR 2015 PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2015/05/MSR-2015-Source-Code-Ownership-IEEE_camera-ready.pdf)).
Foucault, Falleri, and Blanc find in open source that "the relationship between ownership
metrics and module faults is weak. At best, less than half of projects exhibit a significant
correlation, and at worst, no projects at all," with no knowledge framing at all
([HAL via scholar.archive.org](https://scholar.archive.org/work/veyzrlolbvggdolb2rcu5umc2u/access/wayback/https://hal.archives-ouvertes.fr/hal-00976024/document)).

**Expertise recommenders and models.** Expertise Browser counts "experience atoms," the
atomic change, and its authors write that their studies "do not provide definitive evidence
that EAs are a valid measure of expertise" ([Mockus and Herbsleb](https://herbsleb.org/web-pubs/pdfs/mockus-expertise-2002.pdf)).
Fritz, Murphy, and Hill (2007) tested nineteen IBM developers with recall questionnaires
generated from their Mylyn interaction data: knowledge differed between high- and
low-interest elements, but "We did not find any evidence that the frequency or recency of
activity alone with an element indicated knowledge," and "All subjects stated that he or
she knows more about elements he or she authored"
([UBC PDF](https://www.cs.ubc.ca/~murphy/papers/knowledge/interestKnowledge_fse07.pdf)).
The Degree-of-Knowledge model is a regression on 246 self-ratings from seven developers,
"DOK = 3.293 + 1.098 ∗ FA + 0.164 ∗ DL − 0.321 ∗ ln(1 + AC) + 0.19 ∗ ln(1 + DOI)," with
R² = 0.25 ("our model does not predict the user rating completely"), a second-site Spearman
of 0.38, and 55% agreement with developer-named owners
([ICSE 2010 PDF](https://www.cs.ubc.ca/~fritz/papers/icse10_dok_web.pdf)); the 2014 TOSEM
version is closed access and unverified. Schuler and Zimmermann separate "implementation
expertise" from "usage expertise," gained by calling methods, with a "preliminary" evaluation
([MSR 2008 PDF](https://thomas-zimmermann.com/publications/files/schuler-msr-2008.pdf)).
Kovalenko et al. state the reviewer-recommendation assumption verbatim: "The main proxy for
suitability estimation is expertise (or familiarity) of candidates with code under review,
which is estimated through analysis of artifacts of developers' prior work"
([TU Delft preprint](https://pure.tudelft.nl/ws/files/46774016/revrec_preprint.pdf)).
Phase A's entry on the DOK study is in the
[landscape sweep](landscape-sweep.md#cluster-9--measurement-and-detection).

**Truck factor.** Avelino et al. (2016) compute DOA with Fritz's weights ("DOA(md, fp) =
3.293 + 1.098 × FA + 0.164 × DL − 0.321 × ln(1 + AC)"), normalise to [0, 1], count an author
when normalised DOA exceeds k = 0.75 and absolute DOA is at least 3.293, and remove top
authors until coverage falls below 50%; 65% of 133 systems had TF ≤ 2, 84% of surveyed
developers at least partially agreed the named authors were the main ones, and the paper
lists as limits that "it considers all files in a system as equally important" and "does
not account the last time a file is changed" ([arXiv:1604.06766](https://arxiv.org/abs/1604.06766)).
The tool's `config.properties` carries `normalizedDOA=0.75`, `absoluteDOA=3.293`,
`tfCoverage=0.5`, `minPercentage=0.1` and has no AI-related option
([GitHub](https://github.com/aserg-ufmg/Truck-Factor)). Ferreira, Valente, and Ferreira
found the Avelino algorithm most accurate against a 35-project oracle
([ICPC 2017 PDF](https://homepages.dcc.ufmg.br/~mtov/pub/2017-icpc.pdf)). Jabrayilzade et
al. surveyed 269 engineers (commits ranked first as a knowledge source, MRR 0.560, reviews
0.403, meetings 0.214) and add reviews and meetings with decay so that "knowledge from a
contribution halves in about five months" ([arXiv:2202.01523](https://arxiv.org/abs/2202.01523)).
Cury and Avelino's Degree of Expertise, "DOE(d, f(v)) = 5.28223 + 0.23173·ln(1+Adds) +
0.36151·(FA) − 0.28761·ln(Size) − 0.19421·ln(1+NumDays)," was chosen because it counts
lines and so "enables us to discount lines attributed to GenAI"; matching ChatGPT share
links to committed lines gave a mean copied share of 39%, and deducting that share on 10–50%
of files in 24 popular repositories moved 87 of 120 truck-factor values, 86 downward
([arXiv:2507.08160](https://arxiv.org/abs/2507.08160)). Wheeler's paper names the whole
family, "The truck factor, Degree-of-Authorship, degree-of-knowledge, and the turnover-loss
models built on them," as invalidated for AI-generated code ([arXiv:2606.20882](https://arxiv.org/abs/2606.20882);
see [Position papers and proposals](#position-papers-and-proposals)). GitHub repository
searches for truck- or bus-factor tools that treat AI-authored lines specially returned
nothing relevant; this is a negative result limited to the searches run (see Dead ends).

**AI-share metrics.** git-ai's `git ai stats` reports `human_additions`, `unknown_additions`
("Added lines with no attestation at all"), `ai_additions`, and `ai_accepted` ("AI-generated
lines committed without any human edits. Currently equal to `ai_additions`"), keyed by
tool and model; the three additions "always equals git_diff_added_lines," attribution is by
checkpoints stored in git notes, and there is no reviewed-or-read field
([commit-stats docs](https://usegitai.com/docs/cli/commit-stats);
[how it works](https://usegitai.com/docs/cli/how-git-ai-works);
[repository](https://github.com/git-ai-project/git-ai)). Agent Trace v0.1.0 (RFC) records
per-file `conversations` with `contributor` types `human`, `ai`, `mixed` ("Human-edited AI
output or AI-edited human code"), and `unknown`, and no human-reviewed field
([agent-trace.dev](https://agent-trace.dev); [Cognition blog](https://cognition.com/blog/agent-trace)).
Cursor's "AI Share of Committed Code" matches "the signature of every AI line (Tab or Agent)
that is suggested" against commits, and its tracking API reports `tabLinesAdded`,
`composerLinesAdded`, and `nonAiLinesAdded` = "max(0, totalLines - AI lines)" for accepted
suggestions only ([analytics docs](https://cursor.com/docs/account/teams/analytics);
[tracking API](https://cursor.com/docs/account/teams/ai-code-tracking-api)). Phase A's
entries on git-ai and Agent Trace are in the
[landscape sweep](landscape-sweep.md#cluster-9--measurement-and-detection).

**Assistant telemetry.** GitHub Copilot's current usage report defines
`user_initiated_interaction_count`, `code_generation_activity_count`,
`code_acceptance_activity_count`, `loc_suggested_to_add_sum`, `loc_added_sum` ("Lines of
code actually added to the editor (accepted completions, applied code blocks, agent and
edit mode)"), `used_copilot_code_review_active`, and pull-request fields such as
`median_minutes_to_merge_copilot_reviewed`; lines of code are "a directional measure," and
comparisons are "directional associations, not proof"
([usage metrics reference](https://docs.github.com/en/copilot/reference/copilot-usage-metrics/copilot-usage-metrics);
[REST](https://docs.github.com/en/rest/copilot/copilot-metrics)). Ziegler et al. define
acceptance rate, persistence rate ("Percentage of accepted completions unchanged after 30,
120, 300, and 600 seconds"), fuzzy persistence, and contribution speed, and find "acceptance
rate correlates best with aggregate productivity (ρ = 0.24, P < 0.0001)" with "All
persistence measures... less well correlated" ([arXiv:2205.06537](https://arxiv.org/abs/2205.06537)).
Cursor's admin API exposes `totalTabsShown`, `totalTabsAccepted`, `totalAccepts`,
`totalRejects`, `agentRequests`, and similar counts ([admin API](https://cursor.com/docs/account/teams/admin-api));
JetBrains IDE Services reports enabled and active AI users and suggestion acceptance
categories without enumerating fields ([AI analytics API](https://www.jetbrains.com/help/ide-services/2026.1/ai-analytics-api.html));
Claude Code's OpenTelemetry export carries `claude_code.lines_of_code.count`,
`claude_code.code_edit_tool.decision` (accept or reject, by source), `claude_code.active_time.total`,
and `tool_decision` events ([monitoring docs](https://code.claude.com/docs/en/monitoring-usage)).
None of these carries a reading, review-time, or comprehension field.

**Review-time and read-time signals.** GitHub's per-viewer "Viewed" checkbox: "After you
finish reviewing a file, you can mark the file as viewed. The file will collapse," and "If
the file changes after you view the file, it will be unmarked as viewed"
([GitHub Docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/filtering-files-in-a-pull-request)).
The GraphQL schema exposes it as `PullRequestChangedFile.viewerViewedState: FileViewedState!`
("The state of the file for the viewer") with `DISMISSED` ("The file has new changes since
last viewed"), `UNVIEWED`, and `VIEWED`, plus `markFileAsViewed` and `unmarkFileAsViewed`
mutations; only the viewer's own state is exposed and nothing about time or attention is
recorded ([schema](https://raw.githubusercontent.com/octokit/graphql-schema/master/schema.graphql)).
Vendor cycle-time products define review windows without a reading measure: LinearB's
"Pickup Time: From PR creation until the first review starts" and "Review Time: From review
start to PR merge" ([LinearB](https://linearb.io/resources/quickstart-guide-cycle-time)),
Swarmia's "Time to First Review" with bot reviews excluded
([Swarmia](https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review)),
Graphite's "Median review response time" and "Average number of review cycles until merge"
([Graphite](https://graphite.com/docs/insights)). McIntosh et al.'s review-participation
metrics include "proportion of hastily reviewed changes... approved for integration at a
rate that is faster than 200 lines per hour" and "proportion of changes without discussion,"
framed as process quality rather than understanding
([MSR 2014 PDF](https://rebels.cs.uwaterloo.ca/papers/msr2014_mcintosh.pdf)). Faros reports
"PR review time increases by 91%" and "154% increase in average PR size" among AI-heavy teams
([Faros](https://www.faros.ai/blog/ai-software-engineering)). Eye-tracking studies of code
review (Uwano et al. 2006; Begel and Vrzakova 2018; Sharif) were not reachable and are
unverified.

**"Did look-back happen" instrumentation.** CodeRabbit wraps its walkthrough in a
collapsible block, estimates "how much effort the PR requires to review" on a 1–5 scale,
and reports "Reviewer Time Saved," "Acceptance Rate," and time to first and last human
review; it does not record whether a walkthrough was opened
([walkthroughs](https://docs.coderabbit.ai/pr-reviews/walkthroughs);
[dashboard metrics](https://docs.coderabbit.ai/guides/dashboard-metrics)). Litt's
`/explain-diff` skill generates "five questions that test the reader's knowledge of this
PR" as client-side multiple choice that "tells them whether they were correct," and persists
nothing ([gist](https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524)).
Three hobby-scale tools do log: `learn-codebase` keeps "a learning journal in
`.claude/learning-journal.md` that tracks what you confidently know vs. what you're still
bluffing" with a mastery map and spaced review queue
([GitHub](https://github.com/ktaletsk/learn-codebase)); UnSlop's chaos-monkey-learn plants a
bug in the user's own code and appends `{"run_id", "timestamp", "region", "severity",
"outcome", "time_to_fix_seconds", "self_rated_difficulty", ...}` to `.chaos/progress.jsonl`
([GitHub](https://github.com/NachiketKandari/UnSlop)); `comprehension-debt` records graded,
author-confirmed rationale with freshness decay ([GitHub](https://github.com/RonaldSit/comprehension-debt)).
`code-comprehension-quiz` prints "Quiz Results: X/N" and stores nothing
([GitHub](https://github.com/Haroutkhac/code-comprehension-quiz)).

**Comprehension-debt metric formulas.** The one explicit formula found in a shipped tool is
`comprehension-debt`'s "debt(file) = difficulty × exposure × (1 − verified understanding),"
with difficulty from cognitive complexity, exposure from recency-weighted churn or import
blast radius, coverage from passively mined rationale "(capped at 0.6)" plus confirmed
rationale that "can reach 1.0," decay "fresh x1.0 / aging x0.6 / stale x0.25," and an
`assume_ai` flag; its own validity note reads "Text artifacts cannot prove a human privately
understands code; capable models can fool text-level judges... We therefore do not sell 'AI
detection'" and "treat the default weights as a reasoned prior, not a promise"
([GitHub](https://github.com/RonaldSit/comprehension-debt)). Osmani, Gorman, Storey,
Thoughtworks, and Wheeler give no formula (see the next two sections); the ESWA
"Hidden Cost of Vibe Coding" repository measures maintainability index and complexity of
generated code, not human understanding ([GitHub](https://github.com/J34NH4/vibe-coding-comprehension-debt)).

## Self-report and survey instruments

**DX: Core 4, DXI, DevEx, AI Measurement Framework.** The DX Core 4 pairs each dimension
with a key metric: Speed "Diffs per engineer* (PRs or MRs)" ("*Not at individual level"),
Effectiveness "Developer Experience Index (DXI)," Quality "Change failure rate," Impact
"Percentage of time spent on new capabilities," collected "through several methods
including system metrics, self-report, and experience sampling," with the caution "Avoid
fear and gamification. Speed and throughput metrics, when used in isolation, often incite
fear and counterproductive behaviors from developers"
([DX Core 4](https://getdx.com/research/measuring-developer-productivity-with-the-dx-core-4/);
[PDF](https://getdx.com/uploads/dx-core-4.pdf)). The DXI is "an aggregated score from 14
standardized Likert-scale survey items" whose drivers include "Code Maintainability, Local
Iteration Speed, CI/CD, and Documentation," measured "on a quarterly or semi-annual
cadence"; the item wording and the full driver list are not published
([DXI whitepaper](https://getdx.com/research/the-one-number-you-need-to-increase-roi-per-engineer/);
[docs](https://docs.getdx.com/concepts/)). The DevEx paper's example metrics for cognitive
load are "Perceived complexity of codebase," "Ease of debugging production systems," and
"Ease of understanding documentation," and it warns that "Poorly designed survey questions
lead to inaccurate and unreliable results" ([ACM Queue 2023](https://queue.acm.org/detail.cfm?id=3595878)).
"DevEx in Action" publishes the items: the cognitive-load construct (CR 0.820, AVE 0.534)
is "For the primary team you work on, how would you rate the ease of deploying changes?",
"How often can you easily understand the code you work with?" (mean 3.827, SD 0.788, on a
Never–Always scale), "In general, the processes I need to follow to do my work are easy for
me to figure out," and "In general, the developer tools I have are intuitive and easy to
use"; 219 of 2,213 invited developers completed it, and the headline is "Developers who
report a high degree of understanding the code they work with feel 42 percent more
productive than those who report low to no understanding"
([ACM Queue 2024](https://queue.acm.org/detail.cfm?id=3639443)). The AI Measurement
Framework's Impact row lists "Code maintainability" and "Change confidence" as metric names
only, alongside "AI-driven time savings," and cautions that "Metrics like code generation
volume are particularly susceptible to gaming"; it holds no item on understanding AI-assisted
code ([DX](https://getdx.com/research/measuring-ai-code-assistants-and-agents/);
[PDF](https://getdx.com/uploads/ai-measurement-framework.pdf)). Phase A's entry is in the
[landscape sweep](landscape-sweep.md#cluster-9--measurement-and-detection).

**DORA.** The 2025 instrument measures AI adoption as "a factor composed of three highly
interrelated variables, reliance, trust, and reflexive use": "In the last 3 months, how much
have you relied on AI at work?", "In the last 3 months, how much did you trust the quality of
AI-generated output at work?", and "when you encountered a problem to solve or a task to
complete at work, how frequently did you use AI?"; a task-reliance battery includes "Code
review," "Debugging," "Maintaining legacy code," "Modifying existing code," and
"Understanding technical documents"; a skills ranking includes "Understanding your team's
codebase" and "Reading / reviewing code"; the AI-fluency block asks effort on "critically
evaluating an AI's response for accuracy"; and a general cognitive-offloading scale asks
about grocery lists and phone reminders ([2025 questions](https://dora.dev/research/2025/questions/);
[AI Capabilities Model](https://dora.dev/ai/capabilities-model/questions/)). The 2024
instrument has "Code explanation" in its task battery, "how much did you trust the quality
of the output from AI-generated code," and the code-complexity item "how much has your
primary application or service been hindered by code complexity"; the core
code-maintainability items are "It's easy for me to find examples in our codebase" and
"It's easy for us to change code maintained by other teams if we need to"
([2024 questions](https://dora.dev/research/2024/questions/);
[core questions](https://dora.dev/research/core/questions/)). The 2024 report notes that
"measuring usage frequency is likely not as meaningful as measuring reliance" and that
"It is possible that we're gaining speed through an over-reliance on AI"
([2024 report PDF](https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf)).
DORA's measurement-frameworks page says self-report "may be more susceptible to biases
(including recall bias and social desirability bias)" and "It is also a common misconception
that logs-based metrics are objective" ([dora.dev](https://dora.dev/research/2025/measurement-frameworks/));
its interview study records "Deskilling" concerns from five of eight participants
([dora.dev](https://dora.dev/insights/concerns-beyond-accuracy-of-ai-output/)). Phase A's
reading of these surveys is in the
[evidence note](evidence-and-mechanisms.md#surveys-trust-and-verification-not-comprehension).

**SPACE.** Five dimensions; "Activity metrics alone do not reveal which of these is the
case, so they should never be used in isolation either to reward or to penalize
developers"; "at least one of the metrics include perceptual measures such as survey data";
"Metrics shape behavior"; "report only anonymized, aggregate results at the team or group
level" ([ACM Queue 2021](https://queue.acm.org/detail.cfm?id=3454124), read via an archived copy).

**Stack Overflow 2025.** "How much do you trust the accuracy of the output from AI tools as
part of your development workflow?" (46% distrust, 33% trust, 3% "highly trusting"); the
frustration list includes "AI solutions that are almost right, but not quite" (66%),
"Debugging AI-generated code is more time-consuming" (45%), "I've become less confident in
my own problem-solving" (20%), and "It's hard to understand how or why the code works"
(16.3%); the human-help list includes "When I want to fully understand something" (61.3%);
agent statements include "AI agents have accelerated my learning about new technologies or
codebases" ([survey](https://survey.stackoverflow.co/2025/ai);
[methodology](https://survey.stackoverflow.co/2025/methodology): 49,009 responses, opt-in).

**JetBrains 2025.** "What is your biggest concern about AI in coding and software
development?" with shares Quality of generated code 23%, "Limited understanding of complex
code and logic by AI tools" 18%, "Negative effect on my coding and development skills" 11%;
a delegation item lists "Understanding code," "Understanding recent code changes," and
"Performing code reviews"; the questionnaire is in the CC-BY raw-data package
([survey page](https://devecosystem-2025.jetbrains.com/artificial-intelligence);
[raw data](https://resources.jetbrains.com/storage/products/research/DevEco2025/RawData.zip)).

**GitHub 2024.** Wakefield Research, 2,000 non-student, non-manager enterprise respondents in
four countries; "60-71% of respondents reported that these tools make it 'easy' to adopt a
new programming language or understand an existing codebase"; the questionnaire wording is
not published ([GitHub blog](https://github.blog/news-insights/research/survey-ai-wave-grows/)).
Ziegler et al.'s Copilot survey items are published: "I learn from the suggestions GitHub
Copilot shows me" and "I spend less mental effort on repetitive programming tasks when
using GitHub Copilot" ([arXiv:2205.06537](https://arxiv.org/abs/2205.06537)).

**Cognitive-load scales.** NASA-TLX gives "an overall workload score based on a weighted
average of ratings on six subscales: Mental Demands, Physical Demands, Temporal Demands,
Own Performance, Effort, and Frustration," each on a 0–100 line in steps of 5, with Mental
Demand defined as "How much mental and perceptual activity was required (e.g., thinking,
deciding, calculating, remembering, looking, searching, etc)?"
([NASA TLX package, NTRS](https://ntrs.nasa.gov/api/citations/20000021488/downloads/20000021488.pdf)).
Leppink and van den Heuvel's eight-item revision separates intrinsic load ("The content of
this activity was very complex," "I invested a very high mental effort in the complexity of
this activity") from extraneous load ("The explanations and instructions in this activity
were very unclear") on 0–10 scales ([Europe PMC](https://europepmc.org/article/PMC/PMC4456454));
the 2013 ten-item original and Paas's single-item scale were not reachable. SE uses:
Fakhoury et al. combined fNIRS, eye tracking, and a post-snippet self-report and found
linguistic antipatterns "significantly increases the developers' cognitive load"
([preprint](https://veneraarnaoudova.com/wp-content/uploads/2018/03/2018-ICPC-Effect-lexicon-cognitive-load.pdf));
Gonçalves et al.'s registered report on review checklists found "higher cognitive load led
to better performance," with the instrument used unverified behind Springer's block
([EMSE 2022](https://doi.org/10.1007/s10664-022-10123-8)); the Gonçales et al. mapping study
of cognitive-load measurement in SE is confirmed bibliographically only
([DOI](https://doi.org/10.1109/ICPC.2019.00018)). Kazemitabaar et al. (2024) administered
NASA-TLX per condition ([arXiv:2410.08922](https://arxiv.org/html/2410.08922)).

**Thoughtworks and Team Topologies.** The "Codebase cognitive debt" blip's only
measurement pointer is "tracking team cognitive load," which links to the 2022 "Team
cognitive load" blip (Adopt; "NOT ON THE CURRENT EDITION"): "we think it's particularly
important to measure and keep track of the team cognitive load, which indicates how easy or
difficult teams find building, testing and maintaining their services. We've been using a
template to assess team cognitive load that is based on ideas by the authors of the Team
Topologies book" ([codebase cognitive debt](https://www.thoughtworks.com/radar/techniques/codebase-cognitive-debt);
[team cognitive load](https://www.thoughtworks.com/radar/techniques/team-cognitive-load)).
That template is a Google Form, "Engineering Experience Feedback (Cognitive Load
Assessment)," whose intro reads "With this survey we want to assess how easy/hard you find
it to build, test, run and support the services your team responsible for. Note: answers
will not be used in any kind of evaluation/review/appraisal context. Results will be
aggregated at the team level"; its items rate the experience of building, testing,
deploying, operating, being on call, and compliance from "Very poor" to "Very good," with
prompts such as "Are failures easy to diagnose?" and "Are data flows across services
relatively easy to follow?"; no item asks about understanding code
([Team Topologies template](https://github.com/TeamTopologies/Team-Cognitive-Load-Assessment);
[form](https://forms.gle/UD4e1uGzwnrikCDYA)). Phase A's radar entry is in the
[landscape sweep](landscape-sweep.md#cluster-9--measurement-and-detection).

**A direct "do you understand the AI code you ship" item.** None was found in any instrument
fetched. The nearest verified items are DX's "How often can you easily understand the code
you work with?" (not AI-specific), Stack Overflow's "It's hard to understand how or why the
code works," DORA 2025's effort on "critically evaluating an AI's response for accuracy,"
JetBrains' delegation of "Understanding recent code changes," and GitHub's unpublished
"understand an existing codebase" item. Atlassian's 2025 DevEx report (Wakefield, 3,500
developers) publishes no understanding or trust item
([PDF](https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf)).

## Position papers and proposals

**Wheeler, "The Substrate Collapse" (2026).** The argument rests on one inference, "A
developer's footprint on a region of code is evidence of their understanding of that region.
Authored ⇒ understands," which AI generation "severs... at its root," so that "The truck
factor, Degree-of-Authorship, degree-of-knowledge, and the turnover-loss models built on
them go down together." The paper proposes nothing in their place: "This paper does not
propose a comprehension instrument, specify a probe, or describe a mechanism for measuring
theory retention at system and team scale... That absence is a choice, not an oversight."
It names the target, "theory retention," and the admissible evidence, "a developer's
ability to predict the system's behavior under inputs they have not seen, to locate where
a specified change must be made, to tell the load-bearing behaviors from the incidental
ones, to reconstruct the rationale behind a design decision that does not explain itself,"
and the missing instrument, "at the scale of a whole system and a whole team, continuous
and unobtrusive." Its prediction: "systems with a healthy authorship truck factor... but low
comprehension-measured retention will suffer disproportionate incident-resolution failures
(longer time-to-resolution, more escalation, more failed first fixes)," which "cannot be run
until the comprehension-retention instrument of §5 exists." It concedes "A comprehension
measure is gameable in ways a running test is not" and that theory retention may be
"destined to be estimated coarsely rather than measured precisely"; it does not cite Cury
and Avelino ([arXiv:2606.20882](https://arxiv.org/html/2606.20882)). Phase A's entry is in
the [landscape sweep](landscape-sweep.md#cluster-9--measurement-and-detection).

**Cury and Avelino (2025).** The DOE simulation above rests on two stated assumptions,
"The exact matching lines identified correspond to instances of code directly copied and
pasted from ChatGPT-generated outputs" and "Developers do not acquire the same level of
knowledge from integrating copied ChatGPT-generated code"; the source repositories were
tiny (median one contributor), the paper has no threats-to-validity section, proposes no
replacement, and closes with "models used to estimate developer expertise should reflect
the potential impact of GenAI-assisted code generation on code understanding"
([arXiv:2507.08160](https://arxiv.org/html/2507.08160); [artifacts](https://doi.org/10.5281/zenodo.15334705)).

**Storey (2026).** The paper's "Diagnosing Cognitive Debt" list is the fullest signal set in
the sources: "Cognitive debt is harder to see and measure than technical debt because it is
distributed across people and not directly visible in the codebase. But it leaves some
visible traces and signals:" resistance to change; unexpected results ("a reliable signal of
cognitive debt is when a team member makes a change expecting one set of observable
outcomes, but sees something else entirely"); slow or unpredictable onboarding; loss of
transactive memory; low bus factor. Its single measurement paragraph is hedged: "Monitor
the three layers in tandem... perhaps through onboarding time tracking, knowledge
concentration metrics, requirements coverage analysis, and regular audits of the gap
between documented intent and actual behavior," with the warnings "not just the one that is
easiest to measure" and "Resist the automation of understanding... makes cognitive debt
harder to detect" ([arXiv:2603.22106](https://arxiv.org/pdf/2603.22106v4)). The blog lists
warning signs ("team members hesitating to make changes for fear of unintended
consequences, increased reliance on 'tribal knowledge' held by just one or two people, or a
growing sense that the system is becoming a black box") and poses "How do we measure
cognitive debt?" as open ([margaretstorey.com](https://margaretstorey.com/blog/2026/02/09/cognitive-debt/));
the DX republication adds "Where cognitive load is what developers experience in the
moment, cognitive debt is a project-level property" and practitioner-reported symptoms
([DX](https://getdx.com/blog/cognitive-debt-the-hidden-risk-in-ai-driven-software-development/)).
Storey's candidate "knowledge concentration metrics" belong to the class Wheeler's paper
declares invalid; neither paper cites the other on this point.

**Kognita.** A "Managed agent runtime" that indexes "services, functions, routes, jobs,
database touchpoints, dependencies, ownership, business intent, and cross-repository
behavior" and serves them to people and to agents over MCP; no bus-factor, knowledge, or
comprehension score appears on the site, the "KPI needles" ("Context-rediscovery time per
session," "Time to a verified system answer") are aspirational, and the bus-factor blog's
table (a senior engineer's "Reviewers who fully understand: 2-3" before and "still 2-3"
after AI) is illustrative, with the fix stated as "indexing what the code already knows"
([kognita.co](https://www.kognita.co); [blog](https://www.kognita.co/blog/ai-coding-bus-factor-problem)).
Phase A's entry is in the [landscape sweep](landscape-sweep.md#cluster-9--measurement-and-detection).

**Osmani and Gorman.** Osmani defines comprehension debt as "The growing gap between how
much code exists in your system and how much of it any human being genuinely understands"
and states the measurement gap without filling it: "nothing in your current measurement
system captures it. Velocity metrics look immaculate. DORA metrics hold steady. PR counts
are up. Code coverage is green" ([addyosmani.com](https://addyosmani.com/blog/comprehension-debt/));
Gorman's post is qualitative ([codemanship](https://codemanship.wordpress.com/2025/09/30/comprehension-debt-the-ticking-time-bomb-of-llm-generated-code/)).
Phase A's reading of both is in the
[evidence note](evidence-and-mechanisms.md#practitioner-framings-argument-not-evidence).

**Other metric proposals.** Aiersilan's Vibe-Check Protocol is the only paper found with
explicit formulas: a Cold Start Refactor score M_CSR = (V_rec / V_build)·Ω(C) with skill
decay S(t) = S0·e^(−λt), a hallucination-trap d′ = Z(Hit Rate) − Z(False Alarm Rate), an
Explainability Gap E_gap = 1 − H(E)/(H(C)+ε) between the entropy of the code's control-flow
graph and "the semantic entropy of the student's explanation," and a weighted composite;
"the VCP framework awaits full empirical validation" ([arXiv:2601.02410](https://arxiv.org/html/2601.02410)).
Sankaranarayanan's epistemic debt is E_d(t) = U_f(t) − C_c(t), functional utility minus
corrective competence, giving 69.3 points for unrestricted AI, 27.6 with the gate, and −4.0
for manual building; "whether this proxy generalizes to chronic, career-long debt
accumulation is an open question" ([arXiv:2602.20206](https://arxiv.org/html/2602.20206)).
Ahmad's diary study (621 diaries, 207 students) names "explanation latency, modification
difficulty" as potential indicators for future work ([arXiv:2604.13277](https://arxiv.org/html/2604.13277)).
SHIELD defines "Knowledge Debt... incurred when an agent makes changes to the codebase that
the developer does not fully understand" and sketches a per-developer concept map, a
"Probe Generator Agent," and a "Knowledge Assessor Agent," with "empirical evaluation... part
of the proposed future work" ([arXiv:2607.06101](https://arxiv.org/html/2607.06101)). Russo's
proposition P6 operationalises comprehension debt as "the fraction of commits falling below
a legibility threshold" using code-understandability instruments, an artifact property
rather than a measure of what people hold ([arXiv:2604.19827](https://arxiv.org/html/2604.19827)).
Casserini and Facchini propose in prose "a lightweight cognitive debt index that estimates
how consistently reviewers engage with, and can reconstruct, the agent's causal chain,"
with no formula ([arXiv:2604.16323](https://arxiv.org/html/2604.16323)). Meng's economics
model of cognitive debt as "the stock of unverified reasoning obligations"
([arXiv:2606.15078](https://arxiv.org/abs/2606.15078)) and Zhang's indie-team
autoethnography ([arXiv:2512.08942](https://arxiv.org/abs/2512.08942)) propose no metric.

**Validity of LLM-generated and LLM-graded comprehension checks.** Doughty et al. compared
651 GPT-4 and 449 human multiple-choice questions: "4.9% of the automatically generated MCQs
had multiple correct answer choices (compared to only 1.1% of the human-crafted MCQs)," and
answer-revealing distractors ran 4.0% versus 0.9%, while generated items aligned better
with learning objectives; "their pedagogical impact is not known"
([arXiv:2312.03173](https://arxiv.org/abs/2312.03173)). Tran et al. checked generated items
by whether GPT-4 could answer them (78.5%) ([DOI](https://doi.org/10.1109/fie58773.2023.10342898),
abstract only); CODE-GEN's human-in-the-loop generator reports "human-validated success
rates ranging from 79.9% to 98.6%" across dimensions with distractors still needing humans
([arXiv:2604.03926](https://arxiv.org/html/2604.03926)). On grading, CGBG's κ = .58 and
Fowler et al.'s autograder accuracies "in the 86–88% range" with "slightly more lenient
grading standards" for code-generation grading ([TiiS 2025](https://doi.org/10.1145/3774752),
abstract only) are the published figures; no source reports item-response validation of
LLM-generated questions on developer responses, and the one preregistered, IRT-piloted
quiz in the AI-and-code literature (Shen and Tamkin) was human-authored.

**PR-quiz tools.** All 2026 and hobby-scale, none with validity evidence: sphinx-ci
("generates an AI quiz from each Pull Request diff. The developer proves they understand
their own code before the merge," default 10 questions, 70% pass, 3 attempts, merge blocked
by a status check) ([GitHub](https://github.com/AGuyNextDoor/sphinx-ci)); PopPR (a bundled
bank of "108" regex-matched questions plus an optional LLM half, per-user history in
`~/.poppr/history.json`, "PopPR publishes no score") ([GitHub](https://github.com/QuokkaPride/PopPR));
VibeQuiz (VS Code, writes a score into the PR template) ([GitHub](https://github.com/EklabDev/vibequiz));
PRep ([GitHub](https://github.com/Brendan-Z/PRep)) and jeo-prd ([GitHub](https://github.com/ValdoTR/jeo-prd)).
Litt's quiz and its Phase A treatment are in the
[talk note](understanding-bottleneck-talk.md#proposal-2-quizzes-as-a-speed-regulator).
## Arguments against measuring

**Answer.AI.** The one Answer.AI text on tracking understanding is Rachel Thomas's
"I Don't Want a Learning Dashboard for My Child" (2026-02-17). The dashboard proposal comes
from a parent ("I want a dashboard to track what my child is learning, their proficiencies
in different areas"); her husband Jeremy's reply is "I actively do not want that." Thomas's
argument has three parts. (1) Historical: high-stakes testing, from 1990s Texas through No
Child Left Behind, made teachers "assessors, examiners, data collectors" (quoting Gabbie
Stroud, 2016). (2) Goodhart: "When the measure becomes the target, it ceases to be a good
measure. This is Goodhart's Law." (3) The AI-education charge: "many AI education approaches
are exacerbating the problems created by the tyranny of metrics: doubling down on trying to
quantify everything, working only with discrete decomposable units, or discounting the value
of human relationships." What she wants instead is not an alternative measure but a
different object: "Learning, building with creativity, and then sharing what you've learnt
and built with others are essential parts of being human," with community (forums, sharing
channels) and teacher relationships as the mechanism. The post does not name Muller's book
and does not say which forms of assessment, if any, it would accept
([fast.ai](https://www.fast.ai/posts/2026-02-17-education/)). Her 2019 essay gives the
general case in four points — "We can't measure the things that matter most," "Metrics can,
and will, be gamed," "Metrics tend to overemphasize short-term concerns," and "Many metrics
gather data of what we do in highly addictive environments" — and allows metrics only as
multiple data points read in context with qualitative information
([fast.ai 2019](https://www.fast.ai/posts/2019-09-24-metrics.html)). Phase A's reading of
the position is in the [Answer.AI sweep, claim 15](answer-ai-sweep.md#core-claims).

**Goodhart and Campbell, primary formulations.** Campbell's law, from the 1976 Dartmouth
occasional paper reprinted in the *Journal of MultiDisciplinary Evaluation*: "The more any
quantitative social indicator is used for social decision-making, the more subject it will
be to corruption pressures and the more apt it will be to distort and corrupt the social
processes it is intended to monitor." His own first example is the comprehension-adjacent
one: "achievement tests may well be valuable indicators of general school achievement under
conditions of normal teaching aimed at general competence. But when test scores become the
goal of the teaching process, they both lose their value as indicators of educational status
and distort the educational process in undesirable ways," and "Achievement tests are, in
fact, highly corruptible indicators." He describes his evidence as "predominantly anecdotal"
(Campbell 1976/1979, pp. 34–35 of the reprint,
[jmde.com](https://jmde.com/index.php/jmde_1/article/view/297); journal version
[doi:10.1016/0149-7189(79)90048-X](https://doi.org/10.1016/0149-7189%2879%2990048-X)).
Strathern's abstract states the audit version — "audit does more than monitor—it has a life
of its own that jeopardizes the life it audits" — but the popular one-line wording usually
attributed to her was not visible in the abstract fetched ([Cambridge](https://www.cambridge.org/core/journals/european-review/article/improving-ratings-audit-in-the-british-university-system/FC2EE640C0C44E3DB87C29FB666E9AAB)).
Manheim and Garrabrant separate four mechanisms: regressional ("When selecting for a proxy
measure, you select not only for the true goal, but also for the difference between the
proxy and the goal"), extremal ("Worlds in which the proxy takes an extreme value may be
very different from the ordinary worlds in which the relationship" held), causal ("When the
causal path between the proxy and the goal is indirect, intervening can change the
relationship between the measure and proxy"), and adversarial, where another agent "applies
selection pressure knowing the regulator will apply different selection pressure on the
basis of the metric" ([arXiv:1803.04585](https://arxiv.org/abs/1803.04585)).

**SE-metrics literature.** DORA's four-keys guide lists "Setting metrics as a goal. Ignoring
Goodhart's law and making broad statements like, 'Every application must deploy multiple
times per day by year's end'" and "Focusing on measurement at the expense of improvement"
among anti-patterns, states that "These metrics are meant to be applied at the application
or service level," and gives the goal as "improve your team's performance over time, not to
compete against other teams or organizations"
([dora.dev](https://dora.dev/guides/dora-metrics-four-keys/)). SPACE's abstract: developer
productivity "cannot be measured by a single metric or dimension"
([Microsoft Research](https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/);
the ACM Queue full text, which carries the gaming warnings, returned 403). Beck and Orosz's
reply to McKinsey lays out an effort → output → outcome → impact chain and states "The
earlier in the cycle you measure, the easier it is to measure. And also the more likely that
you introduce unintended consequences"; Beck's Facebook example is a survey that worked
until scores entered performance reviews, after which "managers started negotiating with
individual contributors for better survey scores"
([Pragmatic Engineer, 2023-08-29](https://newsletter.pragmaticengineer.com/p/measuring-developer-productivity)).

**Memory is not understanding (the retrieval-practice side's own caveat).** Matuschak's
prompt-writing essay: "the ability to parrot these answers isn't at all the same as knowing
*what stock is*"; "just because you can answer a factual question about an idea, that
doesn't mean the idea will spontaneously occur to you when it's useful"; and the failure
mode in which one learns "the *shape* of that question and learn[s] its corresponding
answer—not because you're really thinking about the knowledge involved, but through a
mechanical pattern association" ([andymatuschak.org/prompts](https://andymatuschak.org/prompts/)).
Matuschak and Nielsen on Quantum Country: "learning those subjects is about much more than
memory," and users of memory systems "sometimes report that while they can remember
answers when being tested by their system, that doesn't mean they can recall them when they
really need them" ([numinous.productions/ttft](https://numinous.productions/ttft/)).
Litt's official talk page carries the same caveat for his quiz (see the
[Phase A note on the talk](understanding-bottleneck-talk.md#proposal-2-quizzes-as-a-speed-regulator)).

**Documented harm.** Campbell's achievement-test passage above is the canonical documented
case, and Thomas's post reports the same history for Texas and No Child Left Behind. No
SE-specific documented harm from a comprehension or knowledge gate was found (see Dead
ends); Kaufman et al.'s finding that under-specified comments lowered accuracy while raising
confidence is the nearest measured adverse effect of an understanding aid, not of a metric
([arXiv:2607.08885](https://arxiv.org/abs/2607.08885)).

## Evaluation designs

**Designs used in the AI-and-code studies.** The productivity RCTs measured speed and
throughput only: Peng et al. (HTTP server task, treatment "completed the task 55.8% faster,"
[arXiv:2302.06590](https://arxiv.org/abs/2302.06590)); Paradis et al. (96 Google engineers,
about 21% less time, "although our confidence interval is large,"
[arXiv:2410.12944](https://arxiv.org/abs/2410.12944)); Cui et al. (three field experiments,
about 4,867 developers, "a 26.08% increase (SE: 10.3%) in completed tasks,"
[Microsoft Research](https://www.microsoft.com/en-us/research/publication/the-effects-of-generative-ai-on-high-skilled-work-evidence-from-three-field-experiments-with-software-developers/));
and METR (task-level randomisation, self-reported time, screen recordings; see the
[Phase A entry](evidence-and-mechanisms.md#ai-specific-evidence-20232026)). None took a
comprehension or retention measure. The designs that did are all single-session: Shen and
Tamkin's between-subjects RCT with an immediate quiz; Qiao et al.'s within-subject design
with a ten-minute assessment after each thirty-minute condition and the AI condition always
second; Sankaranarayanan's three-arm design with a thirty-minute no-AI repair task
immediately after construction; Kazemitabaar et al. (2024) with a transfer task in the same
session after a break (details in [Instruments used in studies](#instruments-used-in-studies)).

**Delayed and transfer designs.** The nearest models come from education. Bastani et al.
gave nearly a thousand high-school students GPT-4 during practice and then an exam without
it: practice grades rose 48% (GPT Base) and 127% (GPT Tutor), but "when access is
subsequently taken away, students actually perform worse than those who never had access
(17% reduction in grades for GPT Base)," an effect "largely mitigated by the safeguards in
GPT Tutor" ([PNAS 2025, abstract via Europe PMC](https://europepmc.org/article/MED/40527749)).
Kazemitabaar et al. (2023) tested 69 novices one week later: Codex learners "performed
slightly better on the evaluation post-tests conducted one week later, although this
difference did not reach statistical significance," and access "did not decrease
performance on manual code-modification tasks"
([arXiv:2302.07427](https://arxiv.org/abs/2302.07427)). Maier et al.'s only significant
learning moderator was whether the exam allowed GenAI (g = 0.76 with access, −0.06 without),
which the authors read as "tool-augmented performance rather than durable skill acquisition"
([arXiv:2605.04779](https://arxiv.org/abs/2605.04779)). Prather et al. used 21 observed,
interviewed, and eye-tracked lab sessions and report that struggling students "finished with
an illusion of competence" — a qualitative design, no scored outcome
([arXiv:2405.17739](https://arxiv.org/abs/2405.17739)).

**Retention curves as evidence: Quantum Country.** Matuschak and Nielsen define a card's
"demonstrated retention" as "the maximum time between a successful review of that card, and
the prior review of that card." Six months after release, "195 users had demonstrated one
full month of retention on at least 80% of cards"; demonstrated retention rose from "just
over 2 days" per card after the first review to "an average of 54 days" after the sixth,
for "about 95 minutes of total review time" across 112 questions. Their one controlled
comparison was an informal two-week delay on eight cards: the delayed group (25 users) fell
from 91% to 87% accuracy while the regular-schedule group (16 users) rose from 89% to 96%,
with 95% intervals of ±3–5 points; they call these "preliminary results," note self-selection
of heavy reviewers, and write "We don't yet have a good model of exactly what those people
are learning" ([numinous.productions/ttft](https://numinous.productions/ttft/)). The
measure is per-prompt recall over time, not understanding.

**Self-report and N-of-1.** Litt's evidence for his quiz is a personal rule — "I won't send
code to others until I can pass the quiz, and I do the same when reviewing others' code" —
and the observation that "many coworkers have found [it] valuable"; the essay reports no pass
rates, and the `/explain-diff` skill neither scores nor persists answers (the quiz is
client-side multiple choice that "tells them whether they were correct and gives feedback")
([geoffreylitt.com](https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck),
[gist](https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524)). Ma's
follow-on essay adds a playable quiz and no data
([dspn.substack.com](https://dspn.substack.com/p/understanding-is-the-new-bottleneck)).
For what a self-experiment would need to count as evidence, the What Works Clearinghouse
single-case standards require the outcome to be measured "systematically over time by more
than one assessor" with inter-assessor agreement on at least 20% of sessions (0.80–0.90
agreement or kappa ≥ 0.60), and "at least three attempts to demonstrate an intervention
effect at three different points in time or with three different phase repetitions";
AB, ABA, and BAB designs do not meet the standard, a reversal design needs at least four
phases of five data points each, and a multiple-baseline design at least six phases
([WWC SCD Technical Documentation, 2010](https://ies.ed.gov/ncee/wwc/Docs/ReferenceResources/wwc_scd.pdf)).
Roberts's defence of self-experimentation claims only that it "seems to be a good way to
generate plausible new ideas" ([BBS 2004](https://doi.org/10.1017/S0140525X04000068)).

**What the sources say about minimum viable evidence.** Shen and Tamkin: "Our study
measures skill formation through a comprehensive quiz. Other studies could use the
completion of another task or design coding as alternative evaluation strategies"; "Ideally,
skill formation takes place over months to years. We measured skill formation for a
specific Python library over a one-hour period"; future work should cover agentic tools,
"longitudinal measurement of the impacts of AI adoption," novices "within a real company,"
and "the effect of feedback from AI vs humans"; their power analysis "assumed a conservative
effect size of d = 0.85 (half of the observed learning effect)" from a pilot
([arXiv:2601.20245](https://arxiv.org/html/2601.20245)). METR's redesign note lists the
threats that broke task-level randomisation — "30% to 50% of developers told us that they
were choosing not to submit some tasks because they did not want to do them without AI,"
and with agents developers "would often work an unrelated task while waiting" — and the
alternatives it is weighing: shorter intensive experiments, observational data, survey
instruments, fixed assigned tasks, autonomous evaluations, and developer-level
randomisation; it also notes unmeasured differences in "subjective code quality, or the
amount of documentation or tests" ([METR, 2026-02-24](https://metr.org/blog/2026-02-24-uplift-update/)).
Wyrich, Bogner, and Wagner's mapping of 95 comprehension experiments (1979–2019) gives the
field's base rates: samples "from 5 to 277, with a median of 34"; 53.7% all-student samples
and 9.5% all-professional; 81% of studies use a "provide information about the code" task
(answering comprehension questions in 33 studies, determining output in 26, summarising in
22, recalling code in 7); correctness is measured in 73.7% of papers, with time, subjective
rating, and — in over a quarter of 2010–2019 papers — physiological measures; and the
authors' first action item is that "hardly any primary study defines what it actually
intends to measure," so "what is measured is often implicitly defined by how it is measured"
([arXiv:2206.11102](https://arxiv.org/abs/2206.11102)). Feitelson's companion paper warns
that "decisions that were taken in an effort to avoid one threat to validity may pose a
larger threat than the one they removed"
([EMSE 2022](https://link.springer.com/article/10.1007/s10664-022-10160-3)).

## Open questions in the sources

Stated by the sources themselves, in their words where the wording matters.

- Storey: "How do we measure cognitive debt? What practices are most effective at
  preventing or reducing it in AI-augmented development environments? How does cognitive
  debt scale across distributed teams or open-source projects"
  ([blog](https://margaretstorey.com/blog/2026/02/09/cognitive-debt/)); "knowing how much
  debt is acceptable in a particular organization or project remains uncertain"
  ([arXiv:2603.22106](https://arxiv.org/pdf/2603.22106v4)).
- Wheeler: the system- and team-scale instrument "does not exist"; whether theory retention
  can be measured rather than "estimated coarsely"; the incident-resolution prediction is
  untestable until it does ([arXiv:2606.20882](https://arxiv.org/html/2606.20882)).
- Shen and Tamkin: quiz versus task completion or design as the skill measure; skill
  formation over "months to years" rather than one hour; agentic tools; "longitudinal
  measurement of the impacts of AI adoption"; novices "within a real company"; "feedback from
  AI vs humans" ([arXiv:2601.20245](https://arxiv.org/html/2601.20245)).
- Sankaranarayanan: "whether this proxy generalizes to chronic, career-long debt accumulation
  is an open question"; whether repair success "measures debugging skill rather than
  understanding" ([arXiv:2602.20206](https://arxiv.org/html/2602.20206)).
- Qiao et al.: "the potential shallowness of our comprehension questions"; participants "were
  not explicitly prompted to understand the code" ([arXiv:2511.02922](https://arxiv.org/html/2511.02922)).
- Maier et al.: designs capture "treatment assignment, not adherence"; whether gains with
  AI-permitted exams are "tool-augmented performance rather than durable skill acquisition"
  ([arXiv:2605.04779](https://arxiv.org/html/2605.04779)).
- Wyrich, Bogner, and Wagner: "hardly any primary study defines what it actually intends to
  measure"; "No clear operationalization for the construct"; "There is a lack of theoretical
  foundations" ([arXiv:2206.11102](https://arxiv.org/abs/2206.11102)). Feitelson: "we also
  need to find a way to operationalize what 'comprehension' actually means"
  ([preprint](http://www.cs.huji.ac.il/~feit/papers/Pitfalls22EmpSE.pdf)).
- Ahmad: "Future work should develop operational and measurable indicators to enable
  empirical validation. Potential indicators include: explanation latency, modification
  difficulty" ([arXiv:2604.13277](https://arxiv.org/html/2604.13277)). SHIELD: "We also
  intend to operationalize Knowledge Debt as a measurable construct"
  ([arXiv:2607.06101](https://arxiv.org/html/2607.06101)). Casserini and Facchini: "develop
  empirical benchmarks for CIT" ([arXiv:2604.16323](https://arxiv.org/html/2604.16323)).
  Russo: "constructive claims require instrument validation before substantive testing can
  begin" ([arXiv:2604.19827](https://arxiv.org/html/2604.19827)). Aiersilan: "the proposed
  thresholds, weightings, and mathematical formulations require confirmation through
  real-world implementation" ([arXiv:2601.02410](https://arxiv.org/html/2601.02410)).
- Doughty et al.: "it remains to see how effective these auto-generated MCQs are at
  assessing student learning"; difficulty not compared ([arXiv:2312.03173](https://arxiv.org/abs/2312.03173)).
- Matuschak and Nielsen: "We don't yet have a good model of exactly what those people are
  learning" ([ttft](https://numinous.productions/ttft/)).
- METR: which redesign (shorter experiments, observational data, surveys, fixed tasks,
  autonomous evaluations, developer-level randomisation) recovers a valid uplift estimate
  under agentic workflows ([METR](https://metr.org/blog/2026-02-24-uplift-update/)).
- DORA: "A common question organizations are facing is the impact of AI on code quality...
  there is a particular concern that we are compromising quality for speed"
  ([dora.dev](https://dora.dev/research/2025/measurement-frameworks/)).
- Fritz et al. (2007): whether authorship, frequency, and recency of interaction indicate
  knowledge beyond the observed authored-element effect
  ([UBC PDF](https://www.cs.ubc.ca/~murphy/papers/knowledge/interestKnowledge_fse07.pdf));
  Cury and Avelino: "investigate other knowledge models and Truck Factor algorithms using a
  similar methodology" and survey developers ([arXiv:2507.08160](https://arxiv.org/html/2507.08160)).
- `comprehension-debt` (tool): "Text artifacts cannot prove a human privately understands
  code" ([GitHub](https://github.com/RonaldSit/comprehension-debt)).

## Dead ends

- WebSearch's session budget was exhausted (200/200) before this pass; arXiv search and
  export API, Semantic Scholar, DBLP, and OpenAlex rate-limited (429) mid-task. All findings
  rest on direct fetches of known URLs, so absence claims (no direct "do you understand the
  AI code" item; no AI-aware truck-factor tool; no "comprehension coverage" metric) are
  limited to the pages and repository searches actually run.
- Blocked or unreachable: ACM DL and ACM Queue (SPACE, DevEx papers read via archived
  copies; Sillito 2006/2008, Lister 2006, Murphy 2012 full texts not obtained); PNAS and
  SSRN (Bastani via Europe PMC; Cui et al. via the Microsoft Research page); Springer
  (Leppink 2013, Gonçalves 2022, Corbett and Anderson 1995 login redirect; Feitelson EMSE via
  the author preprint); ScienceDirect and PsycNet (Pennington 1987, Paas 1992, Rouse and
  Morris 1986, Agarwal 2014); ERIC's Campbell PDF (the open JMDE reprint was used instead);
  UBC cIRcle ("unusual activity"); DTIC; ResearchGate; IEEE Xplore; NASA's TLX site (NTRS
  copy used); the DORA 2025 report PDF (gated; questions pages used).
- Not located or not published: the 14 DXI drivers and item wording; GitHub's 2024
  questionnaire; JetBrains' per-field AI analytics names and its methodology page (404);
  Copilot's legacy metrics API (removed from the current OpenAPI; verified in a mid-2025
  commit only); Cursor's public "% of code written by AI" claim; the Faros 2026 report cited
  by Wheeler; the Agent Trace GitHub repository; Kognita's founders, dates, and case studies;
  Jaspan and Sadowski's page (404); Pluralsight's Developer Thriving report (404); Ozkaya's
  "perceived cognitive load" article; a Thoughtworks or martinfowler.com article on "tracking
  team cognitive load" beyond the radar blip; Lehmann et al.; the Fritz 2014 TOSEM text;
  the Sillito coding method and session counts; Pennington's fifth question type and
  program-model versus situation-model mapping; teach-back's origin; Ericsson and Simon;
  von Mayrhauser and Vans; Novak and Gowin scoring; Ruiz-Primo and Shavelson; Sanders 2008;
  knowledge-tracing applications to programming (Kasurinen 2009, Rivers 2016, Wang 2017,
  Code-DKT); eye-tracking code-review texts (Uwano 2006, Begel and Vrzakova 2018, Sharif);
  Thongtanunam and Bosu; Starr and Storey's troubleshooting paper; Willison's February 2026
  post; Storey's ACM Queue version.
- Artefact gaps inside the studies: Shen and Tamkin's OSF storage is empty, the 14-versus-16
  item count is unreconciled, and grader identity and annotator agreement are unstated;
  Qiao et al.'s 13-versus-15 point total is unexplained and the questions unpublished;
  Sankaranarayanan reports no judge-validity statistic and no preregistration; Kaufman et
  al.'s registration is not retrievable through the view-only node; Maier et al.'s OSF
  registration requires authentication; Kosmyna et al. give no quote-judging procedure, no
  inter-teacher statistic, no session interval, and no data statement; Kazemitabaar et
  al.'s Study 2 reports N = 30 in one test and 42 elsewhere; Perry et al.'s deployed survey
  anchors are unverifiable.
- Negative searches: GitHub repository search for `"truck factor" ai-generated`, `"bus
  factor" "ai-generated"`, `"bus factor" copilot`, and `"bus factor" llm` returned nothing
  relevant beyond a zero-star LLM narrative tool; arXiv had no relevant hits for
  "understanding debt," "comprehension coverage," or "understanding coverage" as software
  metrics before throttling; no paper on "reviewer comprehension" as a metric was found;
  no SE-specific documented harm from a comprehension or knowledge gate was found (the
  documented-harm cases are educational: Campbell's achievement tests and the Texas and No
  Child Left Behind history in Thomas's post).
- Popular one-line wording of "Goodhart's law" attributed to Strathern was not visible in the
  abstract fetched; Goodhart's original 1975 text was not fetched (Manheim and Garrabrant
  and Campbell are the primary formulations cited here).
- Phase A's own dead ends are in the [landscape sweep](landscape-sweep.md#dead-ends) and the
  [evidence note](evidence-and-mechanisms.md#dead-ends-and-gaps); none was resolved here
  except that the Team Topologies template's content, GitHub's "Viewed" API surface, and
  the Cury and Avelino simulation were opened.

## References

Primary sources cited above, alphabetical. Vendor documentation is listed under the vendor.

- Ahmad, "Comprehension Debt in GenAI-Assisted Software Engineering Projects" (2026). https://arxiv.org/abs/2604.13277
- Aiersilan, "The Vibe-Check Protocol: Quantifying Cognitive Offloading in AI Programming" (2026). https://arxiv.org/abs/2601.02410
- Atlassian, "State of Developer Experience 2025". https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf
- Avelino, Passos, Hora, Valente, "A Novel Approach for Estimating Truck Factors" (2016). https://arxiv.org/abs/1604.06766 ; tool: https://github.com/aserg-ufmg/Truck-Factor
- Bastani et al., "Generative AI without guardrails can harm learning" (PNAS 2025), via Europe PMC. https://europepmc.org/article/MED/40527749
- Beck and Orosz, "Measuring developer productivity? A response to McKinsey" (2023). https://newsletter.pragmaticengineer.com/p/measuring-developer-productivity
- Bird, Nagappan, Murphy, Gall, Devanbu, "Don't Touch My Code!" (2011). https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf
- Campbell, "Assessing the Impact of Planned Social Change" (1976; reprint 2011). https://jmde.com/index.php/jmde_1/article/view/297 ; journal version https://doi.org/10.1016/0149-7189%2879%2990048-X
- Casserini and Facchini, "Beyond the 'Diff': Addressing Agentic Entropy in Agentic Software Development" (2026). https://arxiv.org/abs/2604.16323
- Chen, Azad, Haldar, West, Zilles, "A Validated Scoring Rubric for Explain-in-Plain-English Questions" (2020). https://zilles.cs.illinois.edu/papers/EiPE_rubric_sigcse_2020.pdf
- Claude Code, "Monitoring usage". https://code.claude.com/docs/en/monitoring-usage
- CodeRabbit docs, walkthroughs and dashboard metrics. https://docs.coderabbit.ai/pr-reviews/walkthroughs ; https://docs.coderabbit.ai/guides/dashboard-metrics
- Cognition, "Agent Trace" (2026). https://cognition.com/blog/agent-trace ; spec https://agent-trace.dev
- Corney et al., "'Explain in Plain English' Questions Revisited: Data Structures Problems" (2014). https://eprints.qut.edu.au/68093/3/68093.pdf
- Cui et al., "The Effects of Generative AI on High-Skilled Work: Evidence from Three Field Experiments" (abstract). https://www.microsoft.com/en-us/research/publication/the-effects-of-generative-ai-on-high-skilled-work-evidence-from-three-field-experiments-with-software-developers/
- Cursor docs, team analytics, AI code tracking API, admin API. https://cursor.com/docs/account/teams/analytics ; https://cursor.com/docs/account/teams/ai-code-tracking-api ; https://cursor.com/docs/account/teams/admin-api
- Cury and Avelino, "The Impact of Generative AI on Code Expertise Models" (2025). https://arxiv.org/abs/2507.08160 ; artifacts https://doi.org/10.5281/zenodo.15334705
- DORA, questions pages and guides. https://dora.dev/research/2025/questions/ ; https://dora.dev/research/2024/questions/ ; https://dora.dev/research/core/questions/ ; https://dora.dev/ai/capabilities-model/questions/ ; https://dora.dev/guides/dora-metrics-four-keys/ ; https://dora.dev/research/2025/measurement-frameworks/ ; https://dora.dev/insights/concerns-beyond-accuracy-of-ai-output/ ; 2024 report https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf
- Doughty et al., "A Comparative Study of AI-Generated (GPT-4) and Human-crafted MCQs in Programming Education" (2024). https://arxiv.org/abs/2312.03173
- DX, "DX Core 4", DXI whitepaper, "AI Measurement Framework", docs, Storey republication. https://getdx.com/research/measuring-developer-productivity-with-the-dx-core-4/ ; https://getdx.com/uploads/dx-core-4.pdf ; https://getdx.com/research/the-one-number-you-need-to-increase-roi-per-engineer/ ; https://getdx.com/research/measuring-ai-code-assistants-and-agents/ ; https://getdx.com/uploads/ai-measurement-framework.pdf ; https://docs.getdx.com/concepts/ ; https://getdx.com/blog/cognitive-debt-the-hidden-risk-in-ai-driven-software-development/
- Fakhoury, Ma, Arnaoudova, Adaimi, "The effect of poor source code lexicon and readability on developers' cognitive load" (2018). https://veneraarnaoudova.com/wp-content/uploads/2018/03/2018-ICPC-Effect-lexicon-cognitive-load.pdf
- Faros AI, "AI software engineering" report page. https://www.faros.ai/blog/ai-software-engineering
- Feitelson, "Considerations and Pitfalls for Reducing Threats to the Validity of Controlled Experiments on Code Comprehension" (2022). http://www.cs.huji.ac.il/~feit/papers/Pitfalls22EmpSE.pdf ; https://link.springer.com/article/10.1007/s10664-022-10160-3 ; "From Code Complexity Metrics to Program Comprehension" (2023). http://www.cs.huji.ac.il/~feit/papers/Comp23CACM.pdf
- Ferreira, Valente, Ferreira, "A Comparison of Three Algorithms for Computing Truck Factors" (2017). https://homepages.dcc.ufmg.br/~mtov/pub/2017-icpc.pdf
- Forsgren, Noda, Storey, Greiler, "DevEx in Action" (2024). https://queue.acm.org/detail.cfm?id=3639443
- Forsgren et al., "The SPACE of Developer Productivity" (2021). https://queue.acm.org/detail.cfm?id=3454124 ; abstract https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/
- Foucault, Falleri, Blanc, "Code Ownership in Open-Source Software" (2014). https://scholar.archive.org/work/veyzrlolbvggdolb2rcu5umc2u/access/wayback/https://hal.archives-ouvertes.fr/hal-00976024/document
- Fowler, Chen, Zilles, "How should we 'Explain in plain English'?" (2021). https://zilles.cs.illinois.edu/papers/how_to_eipe_icer_2021.pdf ; Fowler et al., autograding EiPE with NLP (2021). https://zilles.cs.illinois.edu/papers/fowler_EiPE_NLP_SIGCSE_2021.pdf ; Fowler et al., "Evaluating AI Models for Autograding Explain in Plain English Questions" (2025). https://doi.org/10.1145/3774752
- Fritz, Murphy, Hill, "Does a Programmer's Activity Indicate Knowledge of Code?" (2007). https://www.cs.ubc.ca/~murphy/papers/knowledge/interestKnowledge_fse07.pdf ; Fritz, Ou, Murphy, Murphy-Hill, "A Degree-of-Knowledge Model" (2010). https://www.cs.ubc.ca/~fritz/papers/icse10_dok_web.pdf
- git-ai docs and repository. https://usegitai.com/docs/cli/commit-stats ; https://usegitai.com/docs/cli/how-git-ai-works ; https://github.com/git-ai-project/git-ai
- GitHub, Copilot usage metrics reference and REST API. https://docs.github.com/en/copilot/reference/copilot-usage-metrics/copilot-usage-metrics ; https://docs.github.com/en/rest/copilot/copilot-metrics
- GitHub, "Filtering files in a pull request" (Viewed). https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/filtering-files-in-a-pull-request ; GraphQL schema https://raw.githubusercontent.com/octokit/graphql-schema/master/schema.graphql
- GitHub, "Survey: The AI wave continues to grow" (2024). https://github.blog/news-insights/research/survey-ai-wave-grows/
- Gonçales et al., "Measuring the Cognitive Load of Software Developers: A Systematic Mapping Study" (2019). https://doi.org/10.1109/ICPC.2019.00018
- Gonçalves et al., "Do explicit review strategies improve code review performance?" (2022). https://doi.org/10.1007/s10664-022-10123-8
- Gorman, "Comprehension Debt: The Ticking Time Bomb of LLM-Generated Code" (2025). https://codemanship.wordpress.com/2025/09/30/comprehension-debt-the-ticking-time-bomb-of-llm-generated-code/
- Graphite, "Insights". https://graphite.com/docs/insights
- Greiler, Herzig, Czerwonka, "Code Ownership and Software Quality: A Replication Study" (2015). https://www.microsoft.com/en-us/research/wp-content/uploads/2015/05/MSR-2015-Source-Code-Ownership-IEEE_camera-ready.pdf
- Hobby PR-quiz and comprehension tools. https://github.com/AGuyNextDoor/sphinx-ci ; https://github.com/QuokkaPride/PopPR ; https://github.com/EklabDev/vibequiz ; https://github.com/Brendan-Z/PRep ; https://github.com/ValdoTR/jeo-prd ; https://github.com/ktaletsk/learn-codebase ; https://github.com/NachiketKandari/UnSlop ; https://github.com/RonaldSit/comprehension-debt ; https://github.com/Haroutkhac/code-comprehension-quiz ; https://github.com/J34NH4/vibe-coding-comprehension-debt
- Jabrayilzade, Evtikhiev, Tüzün, Kovalenko, "Bus Factor In Practice" (2022). https://arxiv.org/abs/2202.01523
- JetBrains, "State of Developer Ecosystem 2025", AI section and raw data. https://devecosystem-2025.jetbrains.com/artificial-intelligence ; https://resources.jetbrains.com/storage/products/research/DevEco2025/RawData.zip ; IDE Services AI analytics API https://www.jetbrains.com/help/ide-services/2026.1/ai-analytics-api.html
- Kaufman, Brun, Murali, Endres, "Programmers Are Poor and Overconfident Judges of LLM-Generated Assertions" (2026). https://arxiv.org/abs/2607.08885 ; https://osf.io/q6d2m/overview?view_only=442a1b8d82554de0baa4b4083987a6b6
- Kazemitabaar et al., "Studying the effect of AI Code Generators on Supporting Novice Learners" (2023). https://arxiv.org/abs/2302.07427 ; "Exploring the Design Space of Cognitive Engagement Techniques with AI-Generated Code" (2024). https://arxiv.org/abs/2410.08922
- Khajah, Lindsey, Mozer, "How deep is knowledge tracing?" (2016). https://arxiv.org/pdf/1604.02416
- Kognita. https://www.kognita.co ; https://www.kognita.co/blog/ai-coding-bus-factor-problem
- Kosmyna et al., "Your Brain on ChatGPT" (2025). https://arxiv.org/pdf/2506.08872
- Kovalenko et al., "Does Reviewer Recommendation Help Developers?" (preprint). https://pure.tudelft.nl/ws/files/46774016/revrec_preprint.pdf
- Kubelka, Bergel, Robbes, "Asking and Answering Questions during a Programming Change Task in Pharo" (2014). https://bergel.eu/MyPapers/Kube14a-ProgrammingPharo.pdf
- LaToza, "Answering Reachability Questions" (CMU-ISR-12-104, 2012). http://reports-archive.adm.cs.cmu.edu/anon/isr2012/CMU-ISR-12-104.pdf
- Leppink and van den Heuvel, "The evolution of cognitive load theory and its application to medical education" (2015). https://europepmc.org/article/PMC/PMC4456454
- LinearB, "Quickstart guide: cycle time". https://linearb.io/resources/quickstart-guide-cycle-time
- Lister et al., "A Multi-National Study of Reading and Tracing Skills in Novice Programmers" (2004). https://citeseerx.ist.psu.edu/document?repid=rep1&type=pdf&doi=161d617890001703cb3dc6334cbc175f264a2a57
- Litt, "Understanding is the new bottleneck" (2026). https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck ; `/explain-diff` gist https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524
- Lopez, Whalley, Robbins, Lister, "Relationships between reading, tracing and writing skills in introductory programming" (2008). https://opus.lib.uts.edu.au/bitstream/10453/10806/1/2008001530.pdf
- Ma, "Understanding is the new bottleneck" (2026). https://dspn.substack.com/p/understanding-is-the-new-bottleneck
- Maier et al., "A meta-analysis of the effect of generative AI on productivity and learning in programming" (2026). https://arxiv.org/abs/2605.04779 ; data https://github.com/SM2982/MetaanalysisGenAICoding
- Manheim and Garrabrant, "Categorizing Variants of Goodhart's Law" (2018). https://arxiv.org/abs/1803.04585
- Matuschak, "How to write good prompts" (2020). https://andymatuschak.org/prompts/ ; Matuschak and Nielsen, "How can we develop transformative tools for thought?" (2019). https://numinous.productions/ttft/
- McIntosh, Kamei, Adams, Hassan, "The Impact of Code Review Coverage and Code Review Participation on Software Quality" (2014). https://rebels.cs.uwaterloo.ca/papers/msr2014_mcintosh.pdf
- Mehra et al., "Agents That Teach" (SHIELD, 2026). https://arxiv.org/abs/2607.06101
- Meng, "Cognitive Debt: AI as Intellectual Leverage and the Dynamics of Systemic Fragility" (2026). https://arxiv.org/abs/2606.15078
- METR, "Measuring AI uplift: an update" (2026-02-24). https://metr.org/blog/2026-02-24-uplift-update/
- Mockus and Herbsleb, "Expertise Browser" (2002). https://herbsleb.org/web-pubs/pdfs/mockus-expertise-2002.pdf
- NASA, "Task Load Index (TLX) v1.0 Paper and Pencil Package". https://ntrs.nasa.gov/api/citations/20000021488/downloads/20000021488.pdf
- Noda, Storey, Forsgren, Greiler, "DevEx: What Actually Drives Productivity" (2023). https://queue.acm.org/detail.cfm?id=3595878
- Novak and Cañas, "The Theory Underlying Concept Maps and How to Construct and Use Them" (2008). https://cmap.ihmc.us/docs/theory-of-concept-maps.php
- Oliveira, Bruno, Madeiral, Castor, "Evaluating Code Readability and Legibility: An Examination of Human-centric Studies" (2020). https://arxiv.org/abs/2110.00785
- Osmani, "Comprehension Debt" (2026). https://addyosmani.com/blog/comprehension-debt/
- Paradis et al., "How much does AI impact development speed? An enterprise-based randomized controlled trial" (2024). https://arxiv.org/abs/2410.12944
- Peng et al., "The Impact of AI on Developer Productivity: Evidence from GitHub Copilot" (2023). https://arxiv.org/abs/2302.06590
- Perry, Srivastava, Kumar, Boneh, "Do Users Write More Insecure Code with AI Assistants?" (2023). https://arxiv.org/abs/2211.03622 ; https://github.com/NeilAPerry/Do-Users-Write-More-Insecure-Code-with-AI-Assistants
- Piech et al., "Deep Knowledge Tracing" (2015). https://arxiv.org/abs/1506.05908
- Prather et al., "The Widening Gap: The Benefits and Harms of Generative AI for Novice Programmers" (2024). https://arxiv.org/abs/2405.17739
- Qiao, Shihab, Haque, Hundhausen, "Code Comprehension with GitHub Copilot" (2026). https://arxiv.org/abs/2511.02922
- Rahman and Devanbu, "Ownership, Experience and Defects" (2011). https://web.archive.org/web/20160208035713id_/http://www.inf.usi.ch:80/faculty/lanza/Education/SDE-2011/papers/Rahm2011a.pdf
- Roberts, "Self-experimentation as a source of new ideas" (2004). https://doi.org/10.1017/S0140525X04000068
- Russo, "More Is Different: Toward a Theory of Emergence in AI-Native Software Ecosystems" (2026). https://arxiv.org/abs/2604.19827
- Sankaranarayanan, "Mitigating 'Epistemic Debt' in Generative AI-Scaffolded Novice Programming" (2026). https://arxiv.org/abs/2602.20206 ; https://github.com/sreecharansankaranarayanan/vibecheck
- Schuler and Zimmermann, "Mining Usage Expertise from Version Archives" (2008). https://thomas-zimmermann.com/publications/files/schuler-msr-2008.pdf
- Sheard et al., "Going SOLO to Assess Novice Programmers" (2008). https://opus.lib.uts.edu.au/bitstream/10453/10719/1/2008001283.pdf
- Shen and Tamkin, "How AI Impacts Skill Formation" (2026). https://arxiv.org/abs/2601.20245 ; https://osf.io/w49e7 ; https://github.com/safety-research/how-ai-impacts-skill-formation
- Siegmund et al., "Understanding Understanding Source Code with fMRI" (2014). https://www.cs.cmu.edu/~ckaestne/pdf/icse14_fmri.pdf ; "Measuring and Modeling Programming Experience" (2014). https://www.cs.cmu.edu/~ckaestne/pdf/ese13.pdf
- Smith and Zilles, "Code Generation Based Grading" (2024). https://zilles.cs.illinois.edu/papers/smith_eipe_cgbg_ITiCSE_2024.pdf ; Hassan and Zilles, "On Students' Usage of Tracing for Understanding Code" (2023), via https://zilles.cs.illinois.edu/papers/
- Stack Overflow, "2025 Developer Survey", AI section and methodology. https://survey.stackoverflow.co/2025/ai ; https://survey.stackoverflow.co/2025/methodology
- Storey, "From Technical Debt to Cognitive and Intent Debt" (2026). https://arxiv.org/pdf/2603.22106v4 ; blog https://margaretstorey.com/blog/2026/02/09/cognitive-debt/
- Strathern, "'Improving ratings': audit in the British University system" (1997), abstract. https://www.cambridge.org/core/journals/european-review/article/improving-ratings-audit-in-the-british-university-system/FC2EE640C0C44E3DB87C29FB666E9AAB
- Swarmia, "Time to first review". https://help.swarmia.com/features/metrics/pull-request-cycle-time/time-to-review
- Team Topologies, "Team Cognitive Load Assessment" template. https://github.com/TeamTopologies/Team-Cognitive-Load-Assessment ; form https://forms.gle/UD4e1uGzwnrikCDYA
- Thomas, "I Don't Want a Learning Dashboard for My Child" (2026). https://www.fast.ai/posts/2026-02-17-education/ ; "The problem with metrics is a big problem for AI" (2019). https://www.fast.ai/posts/2019-09-24-metrics.html
- Thoughtworks Technology Radar, "Codebase cognitive debt" and "Team cognitive load". https://www.thoughtworks.com/radar/techniques/codebase-cognitive-debt ; https://www.thoughtworks.com/radar/techniques/team-cognitive-load
- Tran et al., "Generating Multiple Choice Questions for Computing Courses Using Large Language Models" (2023). https://doi.org/10.1109/fie58773.2023.10342898 ; CODE-GEN, "A Human-in-the-Loop RAG-Based Agentic AI System for Multiple-Choice Question Generation" (2026). https://arxiv.org/abs/2604.03926
- What Works Clearinghouse, "Single-Case Design Technical Documentation" (2010). https://ies.ed.gov/ncee/wwc/Docs/ReferenceResources/wwc_scd.pdf
- Whalley et al., "An Australasian study of reading and comprehension skills in novice programmers" (2006). https://openrepository.aut.ac.nz/bitstreams/fc672554-55f2-4982-bc53-c016749b74ef/download
- Wheeler, "The Substrate Collapse: AI Code Generation Invalidates Authorship-Based Knowledge Metrics" (2026). https://arxiv.org/abs/2606.20882
- Wyrich, Bogner, Wagner, "40 Years of Designing Code Comprehension Experiments" (2023). https://arxiv.org/abs/2206.11102
- Zhang, "Beyond Technical Debt: Comprehension Debt in Resource-Constrained Indie Teams" (2025). https://arxiv.org/abs/2512.08942
- Ziegler et al., "Productivity Assessment of Neural Code Completion" (2022). https://arxiv.org/abs/2205.06537
