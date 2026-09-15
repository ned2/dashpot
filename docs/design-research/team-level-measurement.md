---
status: research
date: 2026-09-15
---

# Team-level measurement

Research date: 2026-09-15

This note documents the instruments that measure a team's shared understanding, its
developer experience, and its delivery outcomes, and records which of them have been used
under AI adoption: what each instrument asks, at what level of analysis it is scored, on how
many teams it was validated, and how "AI adoption" is operationalised where an AI-era survey
publishes its items. It extends the corpus's individual-level measurement note,
[track-measurement.md](track-measurement.md), to the team, and returns to the sentence in the
unfamiliar-code note's dead ends that "No pre-AI source found that measures a shared model of
a codebase directly". It is documentary: it records what the sources say, with evidence type
and sample size, and assesses no fit for Dashpot or any tool. Terminal citations are primary —
the paper, the questionnaire page, the framework text — and the read level is marked per
source: "full text", "abstract", "metadata", or "secondary"; anything recalled rather than
read is marked "unverified". Where an existing note already covers a source (DeChurch and
Mesmer-Magnus, Levesque, Schmidt, Ryan and O'Connor 2013, Fritz, Rigby and Bird, truck
factor, DX Core 4, the DORA and DX item wording already transcribed, the Stack Overflow and
JetBrains 2025 items), this note links to it rather than repeating it. Throughput and
stability numbers from DORA are in the sibling note
[review-capacity-and-volume.md](review-capacity-and-volume.md#survey-based-estimates); only
the instruments are documented here. A sibling note on expert finding and transactive memory
was being written in the same pass and is not linked because it did not yet exist when this
note was checked.

## Finding

The instruments that measure a software team fall into three families that do not share a
level of analysis, and none of them measures a shared model of a codebase. The
developer-productivity frameworks are frameworks, not questionnaires: SPACE names five
dimensions at three levels (individual, team or group, system), recommends "at least three"
metrics of which "at least one" is perceptual, and lists example metrics such as
"Discoverability of documentation and expertise" and "Onboarding time for and experience of
new members" without specifying an item ([Forsgren et al. 2021](https://queue.acm.org/detail.cfm?id=3454124),
full text via an archived copy, figure 1 not retrievable); DevEx names three dimensions and
tells organisations to "Break down results by team and persona"
([Noda et al. 2023](https://queue.acm.org/detail.cfm?id=3595878), full text); the one published
DevEx instrument is a cross-sectional survey of 219 developers (9.9% of 2,213 invited) at DX's
customers, analysed with PLS, whose "team outcomes" are self-reported code quality and
technical debt and whose team-level claim is that "Teams that provide fast responses to
developers' questions report 50 percent less technical debt"
([Forsgren et al. 2024](https://queue.acm.org/detail.cfm?id=3639443), full text, table images
not retrievable). DORA's five delivery metrics are survey items scored per "primary
application or service", not per team ("How often does your organization deploy code to
production...", "What is your lead time for changes...", two percentage items for change
failure and rework, one for recovery time), and its guide says they are "best suited for
measuring one application or service at a time"
([core questions](https://dora.dev/research/core/questions/);
[four keys guide](https://dora.dev/guides/dora-metrics-four-keys/), both full text). DORA's
team-level constructs are five perceptual items on adapting, relying on each other,
innovating, collaborating, and working efficiently, with a team defined in 2025 as "the group
of people you work with on a day-to-day basis to build, maintain, or support the same
application or service ... it's about the shared work, not the org chart"; AI adoption is
measured in 2024 by task-reliance and overall-reliance items, in 2025 by a reliance–trust–
reflexive-use factor plus "how much has your team relied on AI at work?", and in a separate
1,000-response survey by "approximately what percentage of your team's work is supported by
AI?" ([2024 questions](https://dora.dev/research/2024/questions/);
[2025 questions](https://dora.dev/research/2025/questions/);
[adoption insight](https://dora.dev/insights/adopt-gen-ai/), all full text). The
team-cognition instruments are older and validated on more teams: Lewis's 15-item transactive
memory scale (specialization, credibility, coordination; 5-point) was tested on 124 laboratory
teams, 64 MBA consulting teams and 27 teams from 11 technology companies, with team-level
alphas .84/.81/.83 and a composite correlating r = .73 with team-rated and r = .57 with
manager-rated performance in the field sample
([Lewis 2003](https://doi.org/10.1037/0021-9010.88.4.587), full text); Edmondson's 7-item
psychological-safety scale was validated on 51 teams (427 members) in one manufacturing
company with α = .82 and ICC = .39 ([Edmondson 1999](https://doi.org/10.2307/2666999), full
text); Google's Project Aristotle studied 180 teams (115 engineering, 65 sales), measured
effectiveness four ways (executive, lead and member ratings, sales against quota), ran "over
35 different statistical models", published five dynamics and five sample survey items, and
published no coefficients, no per-dynamic statistic and no instrument
([re:Work guide](https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/introduction/),
full text of archived steps; the current site returns a 404 shell). Instruments validated on
software teams with more than 30 teams exist but measure teamwork, tacit project knowledge,
safety, or Scrum process, not code: Teamwork Quality on 145 German software teams
([Hoegl and Gemuenden 2001](https://doi.org/10.1287/orsc.12.4.435.10635), abstract), the
14-item expert-profile Team Tacit Knowledge Measure on 48 teams in 46 SMEs (rwg = .96,
α = .71, r = .35 with effectiveness; [Ryan and O'Connor 2009](https://doi.org/10.1016/j.jss.2008.05.037),
full text), Schmidt et al.'s dyadic agreement items on 81 Scrum teams
([unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research)),
Teamwork Quality again on 71 agile teams ([Lindsjørn et al. 2016](https://doi.org/10.1016/j.jss.2016.09.028),
abstract), psychological safety and norm clarity on 38 teams ([Lenberg and Feldt 2018](https://arxiv.org/abs/1802.01378),
abstract), and a 7-point Scrum instrument on 1,978 teams and 4,940 respondents whose one
shared-understanding item is "Members of this team have a shared understanding of what quality
means to them" ([Verwijs and Russo 2023](https://arxiv.org/abs/2105.12439), full text). Under
AI adoption, every survey with a published instrument is scored at the individual: the DORA
items above; Microsoft's "Dear Diary" trial (228 intake, 106 final; "I trust AI coding
tools" unchanged, "I like using AI coding tools" 2.72 → 3.61;
[Butler et al. 2024](https://arxiv.org/abs/2410.18334), full text); a GitHub–Microsoft
trust-and-adoption model (N = 238; [Choudhuri et al. 2025](https://arxiv.org/abs/2505.17418),
abstract); and the one TMS-grounded AI study, which adapted Human–AI and Human–Human
specialization and coordination items for 152 professionals (51 via LinkedIn and open source,
101 via Prolific) and found AI use in specialization work associated with more knowledge-sharing
peer interaction (β = .25, p = .014) and, in coordination work, with less communication
fragmentation (β = −.41, p = .001) — individuals reporting on their teams, not teams
([Annunziata et al. 2026](https://arxiv.org/abs/2608.03462), full text). Nothing found measures
the team's shared model of its codebase: the nearest items are Schmidt's "similar
understanding of our software architecture" (dyadic self-report), DX's "How often can you
easily understand the code you work with?", DORA 2025's ranking of "Understanding your team's
codebase" among eight skills, and DORA's core "It's easy for me to find examples in our
codebase"; the footprint tools (truck factor, ConceptRealm on 518 projects, Knowledge Islands)
infer knowledge from authorship and issue text. The unfamiliar-code note's dead end stands,
extended to the AI era.

## Developer-productivity frameworks as instruments

### SPACE (2021): a framework, not a questionnaire

Forsgren (GitHub), Storey (University of Victoria), Maddila, Zimmermann, Houck and Butler
(Microsoft Research), "The SPACE of Developer Productivity", *ACM Queue* 19(1), March–April
2021 ([queue.acm.org](https://queue.acm.org/detail.cfm?id=3454124); full text read via a
Wayback capture; the ACM host returns 403 and the figure-1 image is not captured). The
article is argument and framework; it reports no study.

What it prescribes:

- Five dimensions — "satisfaction and well-being; performance; activity; communication and
  collaboration; and efficiency and flow" — and three levels of measure: "figure 1 lists
  concrete metrics ... The figure provides examples of individual-, team- or group-, and
  system-level measures."
- A count and a mix: "teams and leaders (and even individuals) should capture several metrics
  across multiple dimensions of the framework—at least three are recommended", and "at least
  one of the metrics include perceptual measures such as survey data."
- Where self-report belongs: "Self-reported measures of productivity are best captured at the
  individual level: asking a developer whether the team is productive is subject to blind
  spots, while asking if that member felt productive or was able to complete work with minimal
  distractions is a useful signal."
- Aggregation and privacy: "report only anonymized, aggregate results at the team or group
  level. (In some countries, reporting on individual productivity isn't legal.)"
- Reactivity: "Metrics shape behavior"; activity metrics "should never be used in isolation to
  make decisions about individual or team productivity".

What it does not prescribe: any item wording, any scale, any validation. The team-relevant
example metrics it lists, verbatim, are for communication and collaboration "Discoverability
of documentation and expertise", "How quickly work is integrated", "Quality of reviews of work
contributed by team members", "Network metrics that show who is connected to whom and how",
and "Onboarding time for and experience of new members"; for satisfaction "Employee
satisfaction ... whether they would recommend their team to others", "Developer efficacy" and
"Burnout"; for efficiency and flow "Number of handoffs in a process; number of handoffs across
different teams", "Perceived ability to stay in flow", interruptions, and "Time measures
through a system: total time, value-added time, wait time". The article names "morale
building, mentoring, and knowledge sharing" as "invisible" work that "yet are often not
measured", and gives no metric for them. Evidence type: framework and argument.

### DevEx (2023) and "DevEx in Action" (2024): the published survey

Noda (DX), Storey, Forsgren (Microsoft Research) and Greiler (DX), "DevEx: What Actually
Drives Productivity", *ACM Queue* 21(2), 2023
([queue.acm.org](https://queue.acm.org/detail.cfm?id=3595878); full text via Wayback; table 1
is an image not captured). Three dimensions — feedback loops, cognitive load, flow state —
"distilled" from "more than 25 sociotechnical factors" in the authors' prior work. On
measurement it prescribes perceptual plus workflow measures and "KPIs", and gives survey
guidance rather than items: "Poorly designed survey questions lead to inaccurate and
unreliable results. At a minimum, survey questions should be based on well-defined constructs
and be rigorously tested in interviews for consistent interpretation"; "Break down results by
team and persona ... developer experience is highly contextual and can differ radically across
teams or roles"; "Compare results against benchmarks"; "Mix in transactional surveys". The
cognitive-load example metrics the measurement note transcribed ("Perceived complexity of
codebase", "Ease of debugging production systems", "Ease of understanding documentation") are
in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments). Evidence
type: framework and practitioner guidance ("our collective experience in partnering with
hundreds of organizations").

Forsgren, Noda, Storey and Greiler, "DevEx in Action: A study of its tangible impacts", *ACM
Queue* 22(1), 2024 ([queue.acm.org](https://queue.acm.org/detail.cfm?id=3639443); full text
via Wayback; tables 1–3 and figure 2 are images that neither Wayback nor the ACM host served
in this pass — the four cognitive-load items and their statistics are transcribed in
[track-measurement.md](track-measurement.md#self-report-and-survey-instruments)). This is the
instrument:

- Design: "A cross-sectional survey was created using items that were previously validated in
  the literature, or were developed and refined over time with expert input ... refined over
  three years"; hypotheses that each dimension "positively impacts (a) developer, (b) team,
  and (c) organization outcomes."
- Team outcomes as operationalised: "Team outcomes are those that ... more likely accrue at the
  team level of work and are therefore operationalized and studied at this level ... we ...
  capture this as code quality and technical debt." An alternative model treating "technical
  debt and code quality" as environmental moderators "were not significant".
- Sample: "administered by DX ... The participants were developers at companies that were DX
  customers"; "2,213 participants were invited to take the research survey and 219 completed
  it, a response rate of 9.9 percent. The completion rate for participants who viewed the
  research survey was 87 percent. The median time ... was 2.5 minutes"; 170 (77.6%) from
  technology companies and 200 (91.3%) from companies with more than 500 employees; no
  demographics collected "Because of privacy concerns".
- Analysis: PLS; "Our sample size of 219 is far larger than the minimum sample size of 30"
  (the ten-times rule for three paths); convergent validity by loadings ≥ 0.50, composite
  reliability and AVE > 0.50; discriminant validity by HTMT.
- Results: H1 (flow) "fully supported"; H2 (feedback loops) "partially supported; feedback
  loops influence team outcomes but not developer or organization outcomes"; H3 (cognitive
  load) "fully supported". Headline ratios from the IPMA: deep work +50% felt productivity,
  engaging work +30%, "a high degree of understanding the code they work with" +42% felt
  productivity, intuitive tools +50% felt innovation, fast review +20% felt innovation, and
  the one team-level headline, "Teams that provide fast responses to developers' questions
  report 50 percent less technical debt than teams whose responses are slow."
- Limits the authors state: DX customers only ("a population that cares about developer
  experience"); feedback loops "focused on only a small subset of developers' work: answers to
  questions and code reviews ... which may explain why this only influenced team outcomes";
  cross-sectional.

Evidence type: cross-sectional self-report, n = 219, individual respondents; "team outcomes"
are individual perceptions of the team's code quality and debt, not aggregated team scores.
The article invites reuse: "You can use or adapt the survey used in this study, included in
table 1".

### DX Core 4

Documented in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments)
(four dimensions, the DXI as "14 standardized Likert-scale survey items" whose wording is not
published, "Diffs per engineer ... Not at individual level"). One addition from the DX PDF
read here ([dx-core-4.pdf](https://getdx.com/uploads/dx-core-4.pdf), full text, table
extracted with garbling): the Effectiveness column's secondary metrics are "Time to 10th PR",
"Ease of delivery" and "Regrettable attrition (only at organizational level)"; "Time to 10th
PR" is the framework's only onboarding metric, and no metric names knowledge of the codebase.
Evidence type: vendor framework.

### DORA: delivery metrics as survey items, and the team constructs

DORA's questionnaires are published per year with the response options
([core](https://dora.dev/research/core/questions/), [2023](https://dora.dev/research/2023/questions/),
[2024](https://dora.dev/research/2024/questions/), [2025](https://dora.dev/research/2025/questions/),
[AI Capabilities Model](https://dora.dev/ai/capabilities-model/questions/); all full text;
CC BY 4.0). Respondent counts are in the reports, read by the sibling note: about 3,000 in
2024 and "nearly 5,000" in 2025
([review-capacity-and-volume.md](review-capacity-and-volume.md#survey-based-estimates)). No
2026 report or question page existed at `dora.dev/research/2026/` on the research date (404).

**The delivery metrics are items scored per application or service.** The core page's outcome
block is prefaced "For the primary application or service you work on..." and asks: change
failure — "Approximately what percentage of changes to production or released to users result
in degraded service ... and subsequently require remediation (for example, require a hotfix,
rollback, fix forward or patch), if at all?" (0–100%); rework — "Approximately what
percentage of deployments in the last 6 months were not planned but were performed to address
a user-facing bug in the application?" (0–100%); recovery — "How long does it generally take
to restore service after a change to production or release to users results in degraded
service" (six bands from "More than six months" to "Less than one hour"); frequency — "How
often does your organization deploy code to production or release it to end users?" (six
bands from "Fewer than once per six months" to "On demand (multiple deploys per day)"); lead
time — "What is your lead time for changes (i.e., how long does it take to go from code
committed to code successfully running in production)?" (six bands). The 2025 page groups
the first two as "Software delivery instability" and the last three as "Software delivery
throughput". The guide (last updated 2026-01-05) names the five as change lead time,
deployment frequency, failed deployment recovery time, change fail rate and deployment rework
rate; states "These metrics ... are best suited for measuring one application or service at a
time"; and lists among pitfalls "Making disparate comparisons. These metrics are meant to be
applied at the application or service level" and "Setting metrics as a goal. Ignoring
Goodhart's law" ([four keys guide](https://dora.dev/guides/dora-metrics-four-keys/)). The
metrics are therefore self-reports about a service by whoever answers, not team aggregates,
and DORA's own page on frameworks says self-report "may be more susceptible to biases" while
"It is also a common misconception that logs-based metrics are objective"
([track-measurement.md](track-measurement.md#self-report-and-survey-instruments)).

**Team performance and team definition.** 2024: "'Team' can have many different meanings. When
we say 'team,' we are talking about the people who work with you on the same primary
application or service. To what extent do you agree or disagree with the following statements
about how your team performed over the last year?" — "We delivered innovative solutions", "We
were able to adapt to change", "We were able to effectively collaborate with each other", "We
were able to rely on each other", "We worked efficiently" (7-point agree–disagree plus "I
don't know or NA"). 2025 redefines the team — "the group of people you work with on a
day-to-day basis to build, maintain, or support the same application or service. This group
may include people who report to a different manager but share your immediate work goals; it's
about the shared work, not the org chart" — and rates "your team's current performance" from
"Extremely poor" to "Extremely good" on "Adapting to change", "Being able to rely on each
other", "Delivering innovative solutions", "Effectively collaborating with each other",
"Efficiently working together". 2024 also asks "Team stability": "In the last 3 months, to
what extent has your team experienced unnecessary churn from frustration caused by internal
sources?" Team tenure is a demographic ("How many years have you worked on the team you're
currently on?").

**Other team-scored constructs in 2025** are structural or procedural: "Loosely coupled
teams" ("My team can deploy our product or service independently of other services it depends
upon"; "To complete my own work, I don't need to communicate and coordinate with people
outside my team"), "Learning culture" ("How clear are your team's current goals?"; "To what
extent is being curious and asking questions on your team discouraged or encouraged?"),
"Monitoring & metrics" (whether the team monitors "Developer Well-being"), and value-stream
review ("How often, if ever, does your team collectively review all of the steps involved in
taking a piece of work from its initial concept to being delivered"). The core page adds "My
team has tooling in place that provides the ability to find information about things we did
not previously know ('unknown unknowns')".

**How AI adoption is measured.** 2024: "For the primary application or service you work on,
how much have you relied on AI for each of the following tasks over the last 3 months?" (Not
at all / Minimally / Somewhat / Moderately / Extensively relied on; "We do not perform this
task"), over tasks including "Code explanation", "Code reviews", "Debugging", "Modernizing
legacy codebases" and "Writing tests"; an overall "how much have you relied on AI over the
last 3 months?"; and "In the last 3 months, how has AI impacted your productivity at work?"
(seven bands). 2025: the adoption factor "composed of three highly interrelated variables,
reliance, trust, and reflexive use" (items transcribed in
[track-measurement.md](track-measurement.md#self-report-and-survey-instruments)), months of
use, hours interacting with AI on the most recent day, a per-task reliance battery of 27
tasks (including "Maintaining legacy code", "Modifying existing code", "Code review"), and
two team-referenced items: "In the last 3 months, how much has your team relied on AI at
work?" (Not at all – A great deal) and "In the last 3 months, how has AI impacted your team's
productivity at work?" (Extremely decreased – Extremely increased). "AI policy" asks "Has your
organization introduced centralized training practices across teams on how to use AI tools?"
and "How frequently does your team have brown bag sessions, peer demos, or informal
walkthroughs about the use of AI?" (Never – Multiple times a week). "Prompt saving" asks where
prompts for complex tasks are stored: "Checked into version control", "Embedded in version
controlled artifacts", "Shared team docs", "Personal files", "Temporary copy", "Don't save".
The separate adoption-strategy survey (page dated 2025-01-31, updated 2025-03-19) states "We
obtained 1000 responses from developer and developer-adjacent roles" and measured team
adoption as "the survey question: 'Over the last 3 months, approximately what percentage of
your team's work is supported by AI?'", analysed with "a Bayesian regression model"; its
estimates are +11.4% team adoption where AI plans are communicated, +125% where "developer
anxieties" are addressed, +27% where integration is encouraged, and +451% where an
acceptable-use policy exists ([adopt-gen-ai](https://dora.dev/insights/adopt-gen-ai/)).
Evidence type: survey; the percentages are model estimates the page presents without
intervals.

**Items touching understanding, ownership and skills, 2025.** "Skill reprioritization": "Please
rank the following skills from most important to least important as they relate to your
ability to successfully do your current job" — "Creating technical documentation",
"Problem-solving skills", "Programming language syntax memorization", "Prompt engineering",
"Reading / reviewing code", "Teamwork and collaboration", "Understanding your team's codebase",
"Writing code". "Psychological ownership", prefaced "Think about the home, boat or cabin that
you own or co-own ... The following questions deal with the 'sense of ownership' that you
feel for the code you write": "I feel a very high degree of personal ownership for the code I
write", "I sense that the code I write is MY code", "It is hard for me to think of the code I
write as mine", "Most of the people I work with feel as though the code they write is theirs",
"The code I write is MY code" (7-point). "Code quality" is a single self-rating ("Low /
Moderate / High quality") and a separate item on AI's impact on "my code quality". The core
maintainability items ("It's easy for me to find examples in our codebase"; "It's easy for us
to change code maintained by other teams if we need to"; "It's easy for me to add new
dependencies to my project") and the documentation block ("I can rely on our technical
documentation"; "When there's an incident or problem that needs troubleshooting, I reach for
the documentation") are the nearest DORA comes to a codebase-knowledge item. The 2025 report's
analysis of these items is not reproduced here; the sibling note records that the 2025 PDF
gives standardized coefficients rather than percentages
([review-capacity-and-volume.md](review-capacity-and-volume.md#survey-based-estimates)).

## Team-cognition instruments

### Lewis 2003: the transactive memory system scale

Kyle Lewis, "Measuring transactive memory systems in the field: Scale development and
validation", *Journal of Applied Psychology* 88(4):587–604
([doi:10.1037/0021-9010.88.4.587](https://doi.org/10.1037/0021-9010.88.4.587); full text from
a CiteSeerX PDF in the Wayback Machine; the APA page and the live CiteSeerX path are closed).

- **The instrument.** Fifteen items in three five-item subscales, "All items use a 5-point
  disagree–agree response format". Specialization: "Each team member has specialized knowledge
  of some aspect of our project"; "I have knowledge about an aspect of the project that no
  other team member has"; "Different team members are responsible for expertise in different
  areas"; "The specialized knowledge of several different team members was needed to complete
  the project deliverables"; "I know which team members have expertise in specific areas".
  Credibility: "I was comfortable accepting procedural suggestions from other team members";
  "I trusted that other members' knowledge about the project was credible"; "I was confident
  relying on the information that other team members brought to the discussion"; "When other
  members gave information, I wanted to double-check it for myself" (reversed); "I did not
  have much faith in other members' 'expertise'" (reversed). Coordination: "Our team worked
  together in a well-coordinated fashion"; "Our team had very few misunderstandings about what
  to do"; "Our team needed to backtrack and start over a lot" (reversed); "We accomplished the
  task smoothly and efficiently"; "There was much confusion about how we would accomplish the
  task" (reversed). The design goal was a field measure "task-independent" enough to "allow
  comparisons between different teams and tasks".
- **Validation.** Study 1: 124 laboratory teams on a radio-assembly task; subscale alphas
  .80/.83/.78 at member level and .84/.81/.83 at team level; average rwg .90 "with 96% of the
  estimates above .70"; CFA supported three first-order factors. Study 2: 64 MBA consulting
  teams; average rwg .89. Study 3: 27 teams from "11 high-technology companies in the southwest
  United States" ("two electronics/components manufacturers, six hardware and software
  producers, and one company in each of the telecommunications, chemical, and aerospace
  industries"), nine project, seven cross-functional and eleven functional teams; average rwg
  .92; the team-level sample "is too small for structural equation modeling", so a weighted
  composite was used; the composite correlated r = .48 with member-expertise agreement, r = .79
  with functional communication, r = .73 with "team assessments of performance" and r = .57
  with "manager performance ratings"; "One unexpected finding was that the specialization
  subscale was not significantly correlated with the performance variables", with
  specialization–performance r = .04 for functional teams.
- **Scoring level.** Items are answered by individuals and aggregated to the team after
  checking within-team agreement (rwg); the paper reports both member- and team-level
  reliabilities.

Evidence type: scale development with three samples; measured. The scale's later use on
software teams (Ryan and O'Connor 2013, 48 teams, TMS alone R² = .09 for team tacit
knowledge) is in the
[unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research).

### Team mental model measurement: elicitation, metric, aggregation

- **Cooke, Salas, Cannon-Bowers and Stout (2000), "Measuring team knowledge"**, *Human
  Factors* 42(1):151–173 ([doi:10.1518/001872000779656561](https://doi.org/10.1518/001872000779656561);
  abstract via PubMed; the Sage PDF returns 403). The abstract's taxonomy: "Team knowledge
  features include type, homogeneity versus heterogeneity, and rate of knowledge change.
  Measurement features include knowledge elicitation method, team metric, and aggregation
  method"; team knowledge "comprises relatively generic knowledge in the form of team mental
  models and more specific team situation models". Evidence type: methodological review.
- **Mohammed, Ferzandi and Hamilton (2010), "Metaphor no more"**, *Journal of Management*
  36(4):876–910 ([doi:10.1177/0149206309356804](https://doi.org/10.1177/0149206309356804);
  abstract only; Sage closed, no repository copy found). The abstract: "there has been a
  proliferation of published studies over the past decade that have directly measured TMMs
  using a variety of methodologies and research designs ... we overview the conceptual
  underpinnings of TMMs, discuss measurement issues, and review the empirical record related
  to the outcomes, antecedents, and longitudinal work on TMMs." The specific methods the seed
  attributes to it — similarity ratings, concept maps, Pathfinder, card sorts — were not read
  in the paper and are recorded here as unverified; the one method verified in this corpus is
  Mathieu et al.'s "individually completed paired-comparisons matrices analyzed using a
  network-based algorithm" on 56 dyads
  ([unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research)).
  Lewis's own review names "communication patterns of aircraft crews to assess the similarity
  of members' models of their task and team" and Faraj and Sproull's expertise-coordination
  scale as the nearest prior field measures ([Lewis 2003](https://doi.org/10.1037/0021-9010.88.4.587)).
- **DeChurch and Mesmer-Magnus (2010)** — the meta-analysis (65 studies, 3,738 groups,
  ρ = .38 with performance; compilational "who knows what" .62 with process versus .29) is
  read in full in the [unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research)
  and not repeated.

### Edmondson 1999: the psychological-safety scale

Amy C. Edmondson, "Psychological safety and learning behavior in work teams", *Administrative
Science Quarterly* 44(2):350–383 ([doi:10.2307/2666999](https://doi.org/10.2307/2666999);
full text from an MIT course copy linked from Harvard DASH, whose own bitstream returned 405).

- **Instrument.** Seven items: "If you make a mistake on this team, it is often held against
  you" (reverse scored); "Members of this team are able to bring up problems and tough
  issues"; "People on this team sometimes reject others for being different"; "It is safe to
  take a risk on this team"; "It is difficult to ask other members of this team for help"; "No
  one on this team would deliberately act in a way that undermines my efforts"; "Working with
  members of this team, my unique skills and talents are valued and utilized."
- **Sample and level.** "All members of the 53 teams in the sample (496 individuals) were
  administered a five-section survey"; "427 team members from 51 teams completed the surveys,
  an 86-percent response rate; of these 51 teams, 90 percent of members responded"; one
  manufacturer of office furniture (pseudonym "ODI"): "34 functional teams (in sales,
  manufacturing, and staff services such as information technology and accounting), nine
  self-managed teams (in manufacturing and sales), five cross-functional product development
  teams, and three cross-functional project teams". Group-level α = .82 for psychological
  safety; one-way ANOVA F(50, 427) = 6.98, p < .001, ICC = .39 — "It is particularly noteworthy
  that new measures such as team psychological safety and team learning behavior have high
  ICCs (.39 and .33, respectively)", against near-zero ICCs for the conceptually individual
  variables. Team-level correlations: psychological safety with team learning behavior .80,
  with team performance .72; with observer-rated learning .60 and observer-rated performance
  .47.
- **Model.** "As predicted, learning behavior mediates between team psychological safety and
  team performance"; the 51-team sample is a stated limit.

Evidence type: multimethod field study (interviews, survey, observer ratings); measured. No
software team is in the sample. Its reuse in software engineering: Lenberg and Feldt 2018
(below); Verwijs and Russo adapted a different five-item "Inquiry & Dialogue" scale rather
than Edmondson's (below); and a 2025 systematic review reports "the majority of studies
grounded in Edmondson's framework" without stating a count in its abstract
([Santana et al. 2025](https://arxiv.org/abs/2508.03369), abstract). No corpus note mentions
psychological safety or the scale.

### Google's Project Aristotle: what was and was not published

The re:Work guide "Understand team effectiveness" was read from Wayback captures of its eight
steps (2021–2022); the current `rework.withgoogle.com/intl/en/guides/understanding-team-effectiveness`
is listed in the site's sitemap but serves a JavaScript shell whose fetched HTML is a "404 /
Page Not Found" page, and the "collect data" step has no capture under its old path.

- **Sample and method** ([measure step](https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/measure-team-effectiveness/)):
  "the research team identified 180 teams to study (115 project teams in engineering and 65
  pods in sales) which included a mix of high- and low-performing teams"; "hundreds of
  double-blind interviews with leaders"; "existing survey data, including over 250 items from
  the annual employee engagement survey and gDNA, Google's longitudinal study on work and
  life". Sample items: "Group dynamics: I feel safe expressing divergent opinions to the team";
  "Personality traits: I see myself as someone who is a reliable worker (informed by the Big
  Five personality assessment)".
- **The criterion** ([define step](https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/define-effectiveness/)):
  leaders "realized that every suggested measure could be inherently flawed - more lines of
  code aren't necessarily a good thing and more bugs fixed means more bugs were initially
  created"; "the researchers measured team effectiveness in four different ways: Executive
  evaluation of the team; Team leader evaluation of the team; Team member evaluation of the
  team; Sales performance against quarterly quota."
- **The result** ([identify step](https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/identify-dynamics-of-effective-teams/)):
  "Using over 35 different statistical models on hundreds of variables", factors were kept if
  they "impacted multiple outcome metrics", "surfaced for different kinds of teams" and
  "showed consistent, robust statistical significance"; "In order of importance": psychological
  safety, dependability, structure and clarity, meaning, impact. Not significantly connected:
  colocation, consensus decision making, extroversion, individual performance, workload,
  seniority, team size, tenure.
- **The instrument as published** ([needs step](https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/help-teams-determine-their-needs/)):
  "they created a survey for teams to take and discuss amongst themselves. Survey items focused
  on the five effectiveness pillars and questions included: Psychological safety - 'If I make a
  mistake on our team, it is not held against me.' Dependability - 'When my teammates say
  they'll do something, they follow through with it.' Structure and Clarity - 'Our team has an
  effective decision-making process.' Meaning - 'The work I do for our team is meaningful to
  me.' Impact - 'I understand how our team's work contributes to the organization's goals.'";
  "team leads received aggregated and anonymized scores"; a "Team Effectiveness Discussion
  Guide" PDF is linked.
- **Not published**: the full item set, any coefficient, effect size, model specification,
  per-dynamic statistic, reliability, the split of results between engineering and sales
  teams, or a peer-reviewed paper. Evidence type: company account of an internal study.

### Instruments validated on software teams with more than 30 teams

| Instrument | What it measures | Teams (respondents) | Level and reliability | Read level |
| --- | --- | --- | --- | --- |
| Teamwork Quality, [Hoegl and Gemuenden 2001](https://doi.org/10.1287/orsc.12.4.435.10635) | Six facets: "communication, coordination, balance of member contributions, mutual support, effort, and cohesion" | 145 German software teams (575 members, leaders, managers) | Team ratings by three rater groups; "the magnitude of the relationship between TWQ and team performance varies by the perspective of the performance rater" | Abstract |
| Team Tacit Knowledge Measure, [Ryan and O'Connor 2009](https://doi.org/10.1016/j.jss.2008.05.037) | 14 bipolar situational-judgement items (for example "Clear goals ↔ Vague goals") scored as squared Euclidean distance from an 18-expert profile, aggregated to the team | 48 teams in 46 Irish and UK SMEs (181 respondents; mean team size 4.91; within-team response 81.86%) | rwg = .96; α = .71; r = .45 with quality of social interaction, r = .35 with effectiveness, ns with efficiency; "accounting for 8% of the variance over and above social interaction and explicit job knowledge" | Full text (DORAS author copy) |
| Lewis TMS scale plus quality of social interaction, [Ryan and O'Connor 2013](unfamiliar-code-and-shared-models.md#team-cognition-research) | TMS and interaction quality as predictors of the TTKM score | 48 teams, 181 people | TMS alone R² = .09; with interaction quality R² = .20 | Corpus (full text) |
| Dyadic shared-mental-model items, [Schmidt et al. 2014](unfamiliar-code-and-shared-models.md#team-cognition-research) | "have a similar understanding of our software architecture", "agree how well-crafted code looks like" (α = .86) | 81 Scrum teams (~490 engineers), one company | Pairing, review and tests predict SMM β = 0.58, R² = .06 | Corpus (full text) |
| Teamwork Quality on agile teams, [Lindsjørn et al. 2016](https://doi.org/10.1016/j.jss.2016.09.028) | TWQ against performance, learning and satisfaction | 71 agile teams in 26 companies (477 respondents) | SEM; "A positive effect ... when team members and team leaders rated team performance ... a negligible effect ... when product owners rated"; TWQ not higher than in traditional teams | Abstract (ScienceDirect PDF 403) |
| Psychological safety and norm clarity, [Lenberg and Feldt 2018](https://arxiv.org/abs/1802.01378) | Self-assessed team performance and job satisfaction | 38 teams in five organisations (N = 217) | Multiple regression; norm clarity "30% and 71% stronger" a predictor than psychological safety | Abstract |
| Scrum Team Survey, [Verwijs and Russo 2023](https://arxiv.org/abs/2105.12439) | 16 second-order themes as 7-point Likert scales; psychological safety (5 items, α = .862, adapted from the DLOQ "Inquiry & Dialogue" scale), shared goals (2, α = .924), concern for quality (2, α = .786), team morale (3), stakeholder satisfaction (4) | 1,978 Scrum teams (4,940 professionals), August 2020 – October 2021, via scrumteamsurvey.org | Members invited through a per-team link so results aggregate to the team; CB-SEM, CFI = 0.959, RMSEA = 0.038, SRMR = 0.035; the survey returned each team "an automatically generated and anonymized report" | Full text (arXiv) |

Individual-level instruments about teams, for contrast: Nguyen and Pham (2026) measure
"perceived shared mental models and team adaptability" from "252 software professionals in
Vietnam" with PROCESS mediation ([IJITPM 17(1)](https://doi.org/10.4018/ijitpm.410627),
abstract), and Edmondson's and Lewis's own samples are not software teams except Lewis's
Study 3 (27 technology-company teams). Verwijs and Russo's is the only instrument here whose
one item names shared understanding — "Members of this team have a shared understanding of
what quality means to them" — and it is about quality, not the code.

### Shared understanding of a codebase: what is and is not measured

Searched for an instrument that scores a team's shared model of its codebase (as opposed to
its task, its process, or "who knows what"). Nothing found. The nearest items and proxies,
with their level:

- **Self-report about code, individual level.** DX: "How often can you easily understand the
  code you work with?" (mean 3.827, SD 0.788; [track-measurement.md](track-measurement.md#self-report-and-survey-instruments));
  DORA core: "It's easy for me to find examples in our codebase" and "It's easy for us to
  change code maintained by other teams"; DORA 2025: "Understanding your team's codebase" as
  one of eight skills to rank; DORA 2024's "how much has your primary application or service
  been hindered by code complexity" ([track-measurement.md](track-measurement.md#self-report-and-survey-instruments)).
- **Self-report about agreement, dyadic.** Schmidt et al. 2014's "similar understanding of our
  software architecture" — an agreement rating between pairs, not a test of either party's
  model ([unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research)).
- **Structural-fact questionnaires, individual.** Fritz et al. 2007's questions about code
  elements, predicted by authorship and interaction
  ([unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research);
  [track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure)).
- **Footprint, repository level.** Truck factor and files "known" through review
  ([unfamiliar-code note](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss));
  Knowledge Islands, "a tool that visualizes the concentration of knowledge in a software
  repository using a state-of-the-art knowledge model ... calculation of the Truck Factor for
  all folders and source code files" ([Cury and Avelino 2024](https://arxiv.org/abs/2408.08733),
  abstract); ConceptRealm, an LDA model of "300k issues and 1.3M comments from 518 open-source
  projects" that "can represent the high-level domain knowledge within a team and can be
  utilized to predict the alignment of developers with issues", validated against one
  closed-source case, opening with "no established methods exist to measure how knowledge is
  distributed among development teams" ([Shafiq et al. 2024](https://arxiv.org/abs/2207.12851),
  abstract). All infer knowledge from authorship or text, none asks a question of a person.
- **Coordination need from code, repository level.** Socio-technical congruence measures the
  match between coordination requirements derived from file dependencies and actual
  communication; it is a coordination measure, not an understanding measure, and is documented
  in the [workspace-awareness note](workspace-awareness-and-coordination.md#cataldo-wagstrom-herbsleb-and-carley-2006-and-cataldo-and-herbsleb-2008-2013--socio-technical-congruence).

The unfamiliar-code note's dead end — "No pre-AI source found that measures a shared model of
a codebase directly; the instruments are dyadic agreement ratings, paired-comparison networks
on simulator tasks, structural-fact questionnaires (Fritz 2007), and authorship counts"
([unfamiliar-code note](unfamiliar-code-and-shared-models.md#dead-ends)) — is confirmed by
this pass for the pre-AI literature and extended: no AI-era instrument found measures it
either, and the AI-era surveys that reference the codebase do so with a single self-report
item or a skill ranking.

## AI-era surveys: what each asks, and at what level

### Industry surveys with published items

- **DORA 2024, 2025, and the adoption survey** — above. Items are scored per respondent about
  their service or team; the team-referenced AI items are "how much has your team relied on AI
  at work?", "how has AI impacted your team's productivity", the brown-bag frequency item, and
  "what percentage of your team's work is supported by AI?" (1,000 responses).
- **Stack Overflow 2025** — items and n (49,009, opt-in) in
  [track-measurement.md](track-measurement.md#self-report-and-survey-instruments); no team-level
  item was found there. The 2026 survey opened on 2026-06-23 with "The concern du jour now is,
  of course, AI—in particular, agents ... This year, we want to know where AI fits in the
  software development lifecycle, if it's affected your working life", and cites "Our recent
  survey on agents" that "found that agent usage has doubled since then"
  ([Stack Overflow blog](https://stackoverflow.blog/2026/06/23/the-2026-developer-survey-is-now-open-for-human-developers-only/),
  full text); `survey.stackoverflow.co/2026/` returned 404 on the research date, so the 2026
  instrument and results are not documented, and the agents survey was not located.
- **JetBrains 2025** — items, shares and the CC-BY raw-data package in
  [track-measurement.md](track-measurement.md#self-report-and-survey-instruments); no 2026
  edition was reachable (`devecosystem-2026.jetbrains.com` did not resolve).
- **Atlassian, State of Developer Experience 2025** ([PDF](https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf),
  full text): "We worked with Wakefield Research to run an online survey surveying a total of
  3,500 developers across the US, Australia, France, Germany, United Kingdom, and India",
  fielded 2025-03-13 to 2025-03-23, "1,750 respondents reported a title with a minimum
  seniority of software developer manager" and 1,750 below, recruited "through an email
  invitation"; margin "±1.66 percentage points for the Global Sample". Its AI construct is
  hours saved: "68% reporting saving more than 10 hours a week across all of their workflows"
  (30+ hours 3%, 21–30 hours 19%, 11–20 hours 46%, 4–10 hours 31%, less than 4 hours 1%), and
  "managers were aligned with their developers, reporting time savings on par with what their
  teams were sharing". The questionnaire is not published; a grep of the report for
  "understand" and "trust" finds only leadership items ("63% feel top leaders at their
  organization don't understand the challenges"), confirming the measurement note's statement
  that it "publishes no understanding or trust item". Evidence type: vendor survey, self-report,
  individual level.
- **GitHub 2024** (Wakefield, 2,000 enterprise respondents; questionnaire unpublished) — in
  [track-measurement.md](track-measurement.md#self-report-and-survey-instruments).

### Company and academic studies with an instrument

- **Butler, Jaffe, Ford and colleagues, "Dear Diary" (Microsoft)** ([arXiv:2410.18334](https://arxiv.org/abs/2410.18334),
  full text of the HTML version). Design: "surveys, a randomized controlled trial, and a three
  week diary study" at "a large multinational software company". Sample: 10,000 invited, "337
  people completed the survey but only 269 of them agreed to be in the study ... 228 people in
  the Intake Population ... a Final Population of 106." Items ("The full survey is available
  online"): self-view — "I am a highly trained individual", "I cannot be replaced by AI"; tool
  view — "AI coding tools are reliable", "AI coding tools generate correct code", "I trust AI
  coding tools", "I like AI coding tools". Results: "For the statement 'I like using AI coding
  tools,' the average rating rose from 2.72 before to 3.61 after, with p < 0.0001"; "There were
  no statistically significant changes in other variables, including how developers felt at
  work or in their level of trust for GenAI coding tools"; "having access to the Gen AI tool
  made no statistically significant difference to developer telemetry metrics". Level:
  individual; no team construct.
- **Choudhuri et al. 2025 (GitHub and Microsoft)** ([arXiv:2505.17418](https://arxiv.org/abs/2505.17418),
  abstract; journal extension of an ICSE 2025 paper): "a large-scale survey (N = 238)
  conducted at GitHub and Microsoft", PLS-SEM, trust driven by "system/output quality",
  "functional value" and "goal maintenance", adoption by trust plus "cognitive styles (i.e.,
  risk tolerance, technophilic motivations, computer self-efficacy)". Level: individual.
- **GitHub–Accenture RCT** ([GitHub blog](https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-in-the-enterprise-with-accenture/),
  full text): developers "randomly assigned to two groups"; a survey of Copilot users reports
  "90% of developers found they were more fulfilled with their job", "95% said they enjoyed
  coding more", "70% of developers also reported quite a bit less mental effort was expended on
  repetitive tasks", "91% of the developers reported that their teams had merged pull requests
  containing code suggested by GitHub Copilot". No n for the survey, no item wording, no
  team-level construct; the telemetry side of the trial is Cui et al., in
  [track-measurement.md](track-measurement.md#evaluation-designs). Evidence type: vendor
  account.
- **Paradis et al. 2024 (Google RCT, 96 engineers)** — in
  [track-measurement.md](track-measurement.md#evaluation-designs); no survey instrument
  documented there.
- **Stray et al. 2026 (NAV IT)** ([arXiv:2509.20353](https://arxiv.org/abs/2509.20353),
  abstract; HICSS-59): "26,317 unique non-merge commits from 703 ... repositories over a
  two-year period ... 25 Copilot users and 14 non-users", plus surveys on perceived
  productivity and 13 interviews; "We did not find any statistically significant changes in
  commit-based activity for Copilot users after they adopted the tool". Level: individual
  within one organisation.
- **Giray et al. 2025** ([arXiv:2512.23327](https://arxiv.org/abs/2512.23327), full text of
  the HTML version): questionnaire "available to participants from May to November 2025. We
  received 223 responses, of which 204 were used"; convenience, purposive and snowball
  sampling; "objective measurement of productivity and quality remains limited in practice";
  institutionalisation "with a strong focus on tool access and less emphasis on training and
  governance". Level: individual.
- **Felder et al. 2026** ([arXiv:2601.16700](https://arxiv.org/abs/2601.16700), abstract;
  FSE 2026): "18 exploratory interviews ... followed by a developer survey with 109
  participants" in Germany; "Limited awareness of the project context is identified as the
  most significant barrier". Level: individual.
- **Ziegler et al.'s Copilot items** — in
  [track-measurement.md](track-measurement.md#self-report-and-survey-instruments).

### Team cognition under AI: the one TMS-grounded study, and adjacent work

- **Annunziata, Choudhuri, Sarma, Catolino and Ferrucci, "When AI Joins the Team!"**
  ([arXiv:2608.03462](https://arxiv.org/abs/2608.03462), submitted 2026-08-04; full text of
  the HTML version). The instrument: "we validate instruments for Human–AI and Human–Human
  interaction along two TMS dimensions, Specialization and Coordination"; the Human–AI
  constructs (H_AI_Co, "workflow integration, adaptation to AI outputs, and effective task
  co-execution"; H_AI_Spec, "awareness of the specialization boundaries between human and AI
  knowledge") and Human–Human constructs (HH_Co, "frequency of communication and coordination
  interactions"; HH_Spec, "frequency of knowledge-sharing interactions") have "Items ...
  adapted from validated instruments grounded in Transactive Memory Systems theory (Huang and
  Hsieh, 2017) and contextualized to AI-assisted software development"; community-smell
  constructs were derived from a catalogue, validated by four experts, EFA and CFA; "All items
  were measured using 5-point Likert scales"; "The full questionnaire ... is reported in the
  online appendix". Sample: "A total of 152 software professionals ... a direct outreach
  campaign conducted via LinkedIn and professional networks open-source (source A, n = 51),
  and ... Prolific (source B, n = 101)", with the crowdsourced channel showing "a higher rate
  of missing data" (35.25% versus 11.84%) and "speeder" responses (16.7% versus 3%); most
  frequent experience band 1–3 years (41.4%). Results: H_AI_Spec → HH_Spec β = .252
  (p = .014), replicated at .259 and .253 across the three specialization models; the direct
  paths from H_AI_Spec to the smells were not significant; H_AI_Co → Communication
  Fragmentation β = −.406 (p = .001) while H_AI_Co → HH_Co was not (β = −.115, p = .463). The
  authors' reading: "In specialization work, AI is associated with higher knowledge-sharing
  peer interaction ... In coordination work, AI is directly associated with higher
  communication quality, complementing rather than replacing human interaction", with the
  caution that "treating AI as a first resort that replaces engaging with colleagues risks ...
  eroding the shared knowledge network that sustains team performance". Level: individual
  respondents reporting perceptions of their team; not team-aggregated; cross-sectional. This
  is the only study found that applies a TMS instrument to software teams using AI.
- **Hopf, Nahr, Staake and Lehner 2024, "The group mind of hybrid teams"**, *Journal of
  Information Technology* 40(1):9–34 ([doi:10.1177/02683962241296883](https://doi.org/10.1177/02683962241296883),
  abstract; Sage PDF 403): an abductive study of "a conversational intelligent agent (IA) and
  humans, that aims to improve health behavior or change personality traits", theorising a
  "Transactive Intelligent Memory System (TIMS)"; "whether individuals view IAs merely as
  external memory aids or as part of their teams' transactive memory is moderated by the
  tasks' complexity and knowledge intensity". Not a software team; no instrument stated in the
  abstract.
- **Alami, Paja and Tiwari 2026, "The psychological costs of AI adoption in software
  engineering"** ([arXiv:2609.03456](https://arxiv.org/abs/2609.03456), submitted
  2026-09-03; abstract): a case study "one year after the company launched its AI adoption",
  "semi-structured interviews (N = 21)", finding "accountability anxiety, craft identity
  disruption, meaning and satisfaction erosion, cognitive and workload intensification, and
  uncertainty distress". Qualitative; no instrument. The corpus already records Alami et al.
  2026 (n = 21) as the only developer study citing Braverman
  ([adjacent-literatures.md](adjacent-literatures.md#developer-studies-applying-these-frameworks));
  whether this is the same study or a second paper from the same site was not determined.
- **Human–AI team mental models outside code** are in
  [automation-as-a-team-player.md](automation-as-a-team-player.md#humanai-team-performance-and-mental-models).

### The level-of-analysis ledger

| Instrument | Construct | Scored at | Aggregation check | Used under AI adoption |
| --- | --- | --- | --- | --- |
| SPACE | five dimensions | individual / team or group / system (framework) | none (no items) | Framework only |
| DevEx in Action | flow, feedback loops, cognitive load; team outcomes = code quality, technical debt | individual (n = 219) | none | No AI item |
| DXI / Core 4 | 14 unpublished items; diffs per engineer "not at individual level" | individual, reported per team | not published | AI Measurement Framework separate ([track-measurement.md](track-measurement.md#self-report-and-survey-instruments)) |
| DORA five metrics | throughput and instability | per "primary application or service" | none | 2024 and 2025 models regress them on AI adoption ([review-capacity-and-volume.md](review-capacity-and-volume.md#survey-based-estimates)) |
| DORA team performance | five perceptual items | individual about team | none published | Yes, 2024 and 2025 |
| DORA AI adoption | reliance, trust, reflexive use; per-task reliance; team reliance; "% of team's work supported by AI" | individual; team-referenced | none | Is the AI measure |
| Lewis TMS | specialization, credibility, coordination | individual, aggregated with rwg | rwg ≥ .70 criterion | Adapted (Huang and Hsieh 2017 lineage) by Annunziata et al. 2026 at individual level |
| Edmondson | psychological safety | individual, aggregated | ICC .39, F-test | No AI study found |
| Aristotle | five dynamics | individual survey items; team-level modelling | not published | No |
| TWQ | six facets | individual, three rater groups | — (abstract) | No |
| TTKM | team tacit knowledge as distance from expert profile | individual, aggregated | rwg .96 | No |
| Scrum Team Survey | 16 themes incl. psychological safety, shared goals | individual, aggregated per team link | CB-SEM fit | No |
| Annunziata et al. | Human–AI and Human–Human specialization and coordination; community smells | individual (n = 152) | none | Yes |
| Dear Diary | tool beliefs, self-view, trust | individual (228 / 106) | — | Yes (RCT) |

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where the existing notes touch it |
| --- | --- | --- | --- |
| SPACE prescribes dimensions, levels, "at least three" metrics with one perceptual, team-level aggregate reporting; no items | [Forsgren et al. 2021](https://queue.acm.org/detail.cfm?id=3454124) | Framework | The isolation and anonymisation quotes in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments); the levels and example metrics: No counterpart |
| DevEx 2023 prescribes team-and-persona breakdown, construct-based items, benchmarks, transactional surveys | [Noda et al. 2023](https://queue.acm.org/detail.cfm?id=3595878) | Framework | Cognitive-load examples and the "poorly designed" warning in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments) |
| DevEx in Action: n = 219 of 2,213, PLS, team outcomes = code quality and technical debt, feedback loops affect team outcomes only, "50 percent less technical debt" | [Forsgren et al. 2024](https://queue.acm.org/detail.cfm?id=3639443) | Cross-sectional survey | The 42% headline and cognitive-load items in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments); the team-outcome operationalisation: No counterpart |
| DX Core 4's onboarding metric is "Time to 10th PR"; no codebase-knowledge metric | [dx-core-4.pdf](https://getdx.com/uploads/dx-core-4.pdf) | Vendor framework | [track-measurement.md](track-measurement.md#self-report-and-survey-instruments); [landscape-sweep.md](landscape-sweep.md#cluster-9--measurement-and-detection) |
| DORA's five metrics are survey items per application or service, "best suited for measuring one application or service at a time" | [core questions](https://dora.dev/research/core/questions/); [guide](https://dora.dev/guides/dora-metrics-four-keys/) | Questionnaire and guide text | Goodhart pitfall in [track-measurement.md](track-measurement.md#arguments-against-measuring); the 2024–2025 regressions in [review-capacity-and-volume.md](review-capacity-and-volume.md#survey-based-estimates); the item wording: No counterpart |
| DORA team definition ("shared work, not the org chart") and five team-performance items; team stability item | [2024](https://dora.dev/research/2024/questions/); [2025 questions](https://dora.dev/research/2025/questions/) | Questionnaire | No counterpart |
| DORA measures AI adoption by reliance (2024), reliance–trust–reflexive use (2025), team reliance, and "% of team's work supported by AI" (1,000 responses) | [2025 questions](https://dora.dev/research/2025/questions/); [adopt-gen-ai](https://dora.dev/insights/adopt-gen-ai/) | Questionnaire; model estimates | Reliance triad in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments) and [evidence-and-mechanisms.md](evidence-and-mechanisms.md#surveys-trust-and-verification-not-comprehension); team items and the 1,000-response survey: No counterpart |
| DORA 2025 asks "Understanding your team's codebase" as a skill rank, psychological ownership of code (5 items), brown-bag frequency, prompt storage location | [2025 questions](https://dora.dev/research/2025/questions/) | Questionnaire | The skills ranking is named in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments); ownership and prompt-storage items: No counterpart; ownership under delegation as a gap in [synthesis.md](synthesis.md#gaps-every-pass-left) |
| Lewis's 15-item TMS scale: three subscales, 124 + 64 + 27 teams, team-level α .84/.81/.83, r = .73 with team-rated performance | [Lewis 2003](https://doi.org/10.1037/0021-9010.88.4.587) | Scale validation | Used by Ryan and O'Connor 2013 in [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research); the instrument itself: No counterpart |
| Team-knowledge measurement is a choice of elicitation, team metric and aggregation | [Cooke et al. 2000](https://doi.org/10.1518/001872000779656561); [Mohammed et al. 2010](https://doi.org/10.1177/0149206309356804) | Methodological review (abstracts) | Mathieu's paired comparisons in [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research); Mohammed listed as not obtained in its [dead ends](unfamiliar-code-and-shared-models.md#dead-ends) |
| Edmondson's 7-item scale: 51 teams, α .82, ICC .39, learning behaviour mediates to performance | [Edmondson 1999](https://doi.org/10.2307/2666999) | Multimethod field study | No counterpart |
| Project Aristotle: 180 teams, four effectiveness measures, 35+ models, five dynamics, five sample items; no statistics published | [re:Work](https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/measure-team-effectiveness/) | Company account | No counterpart |
| TWQ validated on 145 and 71 software teams; rater perspective changes the effect | [Hoegl and Gemuenden 2001](https://doi.org/10.1287/orsc.12.4.435.10635); [Lindsjørn et al. 2016](https://doi.org/10.1016/j.jss.2016.09.028) | Survey with SEM (abstracts) | No counterpart |
| TTKM: expert-profile distance measure of team tacit knowledge, 48 teams, rwg .96, r = .35 with effectiveness | [Ryan and O'Connor 2009](https://doi.org/10.1016/j.jss.2008.05.037) | Scale validation | The 2013 follow-up in [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research); the measure: No counterpart |
| Scrum Team Survey: 1,978 teams, per-team aggregation, "shared understanding of what quality means" | [Verwijs and Russo 2023](https://arxiv.org/abs/2105.12439) | Survey with CB-SEM | Definition of Done as shared understanding in [flow-wip-limits-and-constraints.md](flow-wip-limits-and-constraints.md#definition-of-done-and-gates-as-shared-understanding); the instrument: No counterpart |
| Psychological safety and norm clarity on 38 software teams | [Lenberg and Feldt 2018](https://arxiv.org/abs/1802.01378) | Survey (abstract) | No counterpart |
| No instrument measures a team's shared model of its codebase; nearest are single self-report items, a dyadic agreement item, and footprint tools | this note; [Shafiq et al. 2024](https://arxiv.org/abs/2207.12851); [Cury and Avelino 2024](https://arxiv.org/abs/2408.08733) | Absence after bounded search | Confirms [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#dead-ends); footprint metrics in [track-measurement.md](track-measurement.md#proxies-and-telemetry) and [track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure) |
| The one TMS instrument applied to software teams using AI: 152 individuals, AI use in specialization work ↔ more peer knowledge sharing (β = .25), in coordination work ↔ less communication fragmentation (β = −.41) | [Annunziata et al. 2026](https://arxiv.org/abs/2608.03462) | Cross-sectional PLS-SEM | Single-human supervision of agent PRs in [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#bottom-line); human–AI team models in [automation-as-a-team-player.md](automation-as-a-team-player.md#humanai-team-performance-and-mental-models); the instrument: No counterpart |
| Dear Diary: 228 → 106, trust unchanged, liking 2.72 → 3.61, no telemetry effect; items published | [Butler et al. 2024](https://arxiv.org/abs/2410.18334) | RCT plus diary | No counterpart |
| Atlassian 2025: 3,500, hours-saved construct, no understanding or trust item, no questionnaire | [Atlassian PDF](https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf) | Vendor survey | [track-measurement.md](track-measurement.md#self-report-and-survey-instruments) (the absence); methodology and hours distribution: No counterpart |
| Stack Overflow 2026 opened 2026-06-23 with an agents focus; results unpublished | [Stack Overflow blog](https://stackoverflow.blog/2026/06/23/the-2026-developer-survey-is-now-open-for-human-developers-only/) | Announcement | 2025 items in [track-measurement.md](track-measurement.md#self-report-and-survey-instruments) |
| Every AI-era survey with a published instrument is scored at the individual | Butler 2024; Choudhuri 2025; Giray 2025; Felder 2026; Stray 2026; Annunziata 2026 | Surveys | Gap 6 in [synthesis.md](synthesis.md#gaps-every-pass-left) (no validated instrument beyond ~20 professionals) is about ownership, motivation and flow; team level: No counterpart |

"No counterpart" means no note in this directory addresses the point; it is a statement about
the notes, not about the wider literature.

## Corrections proposed

1. **unfamiliar-code-and-shared-models.md, Team cognition research**: "Ryan and O'Connor
   (2013), tacit knowledge in software teams. 48 teams from 46 Irish and UK SMEs, 181 people.
   Transactive memory (Lewis scale) and quality of social interaction both predicted team
   tacit knowledge" — not wrong, but the dependent variable's instrument is unnamed; it is the
   14-item Team Tacit Knowledge Measure scored as distance from an 18-expert profile, developed
   and validated on the same 48-team sample in
   [Ryan and O'Connor 2009](https://doi.org/10.1016/j.jss.2008.05.037) (rwg = .96, α = .71,
   r = .35 with effectiveness), so the 2013 result is a second analysis of one dataset rather
   than an independent sample; a pointer is proposed.
2. **synthesis.md, Gaps every pass left, item 6**: "No validated instrument for ownership,
   motivation, or flow under delegation beyond ~20 professionals" — qualified for ownership:
   DORA's 2025 questionnaire fields a five-item psychological-ownership-of-code scale ("I feel a
   very high degree of personal ownership for the code I write" ...) to nearly 5,000
   respondents ([2025 questions](https://dora.dev/research/2025/questions/)); whether the
   report analyses it against AI adoption is not established here, and the scale's validation
   is not published on the questions page, so the gap narrows from "no instrument" to "no
   published analysis of a fielded instrument".

## Dead ends

- **WebSearch** was used 8 times of the 15 allowed (queries listed in the report to the
  dispatching session). Semantic Scholar returned 429 on every search call after the first
  metadata lookup; OpenAlex full-text `search=` returned mostly irrelevant medical and ML
  papers for team-cognition queries and was useful only for DOI lookups and
  `title_and_abstract.search`; the Wayback availability API returned 429 intermittently and
  needed pauses between fetches.
- **ACM Queue images.** SPACE's figure 1 (the dimension-by-level grid of example metrics) and
  DevEx in Action's tables 1–3 (the instrument with means, SDs, loadings, CR and AVE) are
  images on `spawn-queue.acm.org` that return 403 directly and have no Wayback capture; the
  DX-hosted copy (`getdx.com/uploads/devex-in-action.pdf`) is 404 and the ACM DL PDF is 403.
  The item wording used here is the measurement note's transcription.
- **Closed or blocked**: Mohammed et al. 2010 (Sage; Penn State Pure has only metadata);
  Cooke et al. 2000 (Sage PDF 403; PubMed abstract used); Lewis 2003 at APA and at the live
  CiteSeerX path (a 2020 Wayback capture of the CiteSeerX download served the PDF);
  Edmondson 1999 at Harvard DASH's bitstream (405; the MIT course copy DASH links to was
  used); Lindsjørn et al. 2016 (ScienceDirect PDF 403); Hopf et al. 2024 (Sage 403);
  Salas et al. 2017's team-performance-measurement chapter at Clemson (TLS failure); the DORA
  2025 report PDF itself (read by the sibling note); Verwijs and Russo at the ACM DL (arXiv
  version used, which carries a placeholder volume line "Vol. 37, No. 4, Article 111" — the
  OpenAlex record gives TOSEM 32(3):1–51).
- **Google re:Work.** The current guide URL is in the site's sitemap but its fetched HTML is a
  404 shell (client-rendered); Wayback has the 2021–2022 steps except "collect data and
  measure effectiveness", which was renamed `measure-team-effectiveness` and was captured
  under that name. The "Team Effectiveness Discussion Guide" PDF and Google Doc were not
  fetched.
- **Not located**: the Stack Overflow "recent survey on agents" the June 2026 post refers to;
  the Stack Overflow 2026 results (404 on the research date); a JetBrains 2026 survey; a DORA
  2026 report; an Atlassian 2026 DevEx report (not searched for); Huang and Hsieh 2017, the
  TMS instrument Annunziata et al. adapted (not fetched); Annunziata et al.'s online appendix
  with the full questionnaire (not fetched); the Accenture survey's n and items; Yu and Petter
  2014's abstract (OpenAlex holds none); any study applying Edmondson's scale to software
  teams under AI adoption (the search found executive-opinion and consultancy pages only,
  none cited here); any team-aggregated (rwg or ICC) AI-adoption study of software teams.
- **Seed items not verified**: the seed's characterisation of Mohammed et al. 2010 as reviewing
  "similarity ratings, concept maps, Pathfinder, card sorts" was not read in the paper; no
  "Copilot in the enterprise" survey paper distinct from the Accenture blog (no instrument)
  and Dear Diary (instrument online) was identified.
- **Not searched**: team situation-awareness instruments; knowledge-sharing scales outside the
  TMS family; the healthcare and aviation team-cognition literature; Google's internal
  engineering-satisfaction survey ([track-measurement.md](track-measurement.md#dead-ends)).

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Alami, A., Paja, E., Tiwari, A. (2026). The psychological costs of artificial intelligence
  adoption in software engineering. arXiv:2609.03456. https://arxiv.org/abs/2609.03456
- Annunziata, G., Choudhuri, R., Sarma, A., Catolino, G., Ferrucci, F. (2026). When AI joins
  the team! A model of how AI adoption relates to social patterns in software engineering
  teams. arXiv:2608.03462. https://arxiv.org/abs/2608.03462
- Atlassian (2025). State of Developer Experience Report 2025.
  https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf
- Butler, J. L., et al. (2024). Dear Diary: A randomized controlled trial of Generative AI
  coding tools in the workplace. arXiv:2410.18334. https://arxiv.org/abs/2410.18334
- Choudhuri, R., Trinkenreich, B., Pandita, R., Kalliamvakou, E., Steinmacher, I., Gerosa,
  M., Sanchez, C., Sarma, A. (2025). What needs attention? Prioritizing drivers of
  developers' trust and adoption of generative AI. arXiv:2505.17418.
  https://arxiv.org/abs/2505.17418
- Cooke, N. J., Salas, E., Cannon-Bowers, J. A., Stout, R. J. (2000). Measuring team
  knowledge. *Human Factors* 42(1):151–173. doi:10.1518/001872000779656561
- Cury, O., Avelino, G. (2024). Knowledge Islands: Visualizing developers' knowledge
  concentration. arXiv:2408.08733. https://arxiv.org/abs/2408.08733
- DORA (2024–2026). Research questions: core, 2023, 2024, 2025; AI Capabilities Model
  questions; DORA's software delivery performance metrics (guide, updated 2026-01-05);
  Helping developers adopt generative AI (insight, 2025-01-31).
  https://dora.dev/research/core/questions/ ; https://dora.dev/research/2023/questions/ ;
  https://dora.dev/research/2024/questions/ ; https://dora.dev/research/2025/questions/ ;
  https://dora.dev/ai/capabilities-model/questions/ ;
  https://dora.dev/guides/dora-metrics-four-keys/ ; https://dora.dev/insights/adopt-gen-ai/
- DX (2024). DX Core 4. https://getdx.com/uploads/dx-core-4.pdf
- Edmondson, A. C. (1999). Psychological safety and learning behavior in work teams.
  *Administrative Science Quarterly* 44(2):350–383. doi:10.2307/2666999
- Felder, L., Eisenreich, T., Fischer, M., Wagner, S., Chen, C. (2026). Adoption of
  generative artificial intelligence in the German software engineering industry: An
  empirical study. FSE 2026. arXiv:2601.16700. https://arxiv.org/abs/2601.16700
- Forsgren, N., Storey, M.-A., Maddila, C., Zimmermann, T., Houck, B., Butler, J. (2021).
  The SPACE of developer productivity. *ACM Queue* 19(1). https://queue.acm.org/detail.cfm?id=3454124
- Forsgren, N., Noda, A., Storey, M.-A., Greiler, M. (2024). DevEx in action: A study of its
  tangible impacts. *ACM Queue* 22(1). https://queue.acm.org/detail.cfm?id=3639443
- GitHub (2024). Research: Quantifying GitHub Copilot's impact in the enterprise with
  Accenture. https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-in-the-enterprise-with-accenture/
- Giray, G., Demirörs, O., Kalinowski, M., Mendez, D. (2025). An empirical study of
  generative AI adoption in software engineering. arXiv:2512.23327.
  https://arxiv.org/abs/2512.23327
- Google re:Work (2016–2022). Guide: Understand team effectiveness.
  https://rework.withgoogle.com/guides/understanding-team-effectiveness/steps/introduction/
  (Wayback captures of the define, measure, identify and needs steps)
- Hoegl, M., Gemuenden, H. G. (2001). Teamwork quality and the success of innovative
  projects: A theoretical concept and empirical evidence. *Organization Science*
  12(4):435–449. doi:10.1287/orsc.12.4.435.10635
- Hopf, K., Nahr, N., Staake, T., Lehner, F. (2024). The group mind of hybrid teams with
  humans and intelligent agents in knowledge-intense work. *Journal of Information
  Technology* 40(1):9–34. doi:10.1177/02683962241296883
- Lenberg, P., Feldt, R. (2018). Psychological safety and norm clarity in software
  engineering teams. CHASE 2018, pp. 79–86. arXiv:1802.01378. https://arxiv.org/abs/1802.01378
- Lewis, K. (2003). Measuring transactive memory systems in the field: Scale development and
  validation. *Journal of Applied Psychology* 88(4):587–604. doi:10.1037/0021-9010.88.4.587
- Lindsjørn, Y., Sjøberg, D. I. K., Dingsøyr, T., Bergersen, G. R., Dybå, T. (2016). Teamwork
  quality and project success in software development: A survey of agile development teams.
  *Journal of Systems and Software* 122:274–286. doi:10.1016/j.jss.2016.09.028
- Mohammed, S., Ferzandi, L., Hamilton, K. (2010). Metaphor no more: A 15-year review of the
  team mental model construct. *Journal of Management* 36(4):876–910.
  doi:10.1177/0149206309356804
- Nguyen Thuy, A., Pham Thuy, N. (2026). Shared mental models, team adaptability, and agile
  project success. *International Journal of Information Technology Project Management*
  17(1):1–23. doi:10.4018/ijitpm.410627
- Noda, A., Storey, M.-A., Forsgren, N., Greiler, M. (2023). DevEx: What actually drives
  productivity. *ACM Queue* 21(2). https://queue.acm.org/detail.cfm?id=3595878
- Ryan, S., O'Connor, R. V. (2009). Development of a team measure for tacit knowledge in
  software development teams. *Journal of Systems and Software* 82(2):229–240.
  doi:10.1016/j.jss.2008.05.037 (author copy: https://doras.dcu.ie/16738/)
- Santana, B., Monte, L., Silva, B. S. de A., Carneiro, G., Freire, S., Santos, J. A. M.,
  Mendonça, M. (2025). Psychological safety in software workplaces: A systematic literature
  review. arXiv:2508.03369. https://arxiv.org/abs/2508.03369
- Shafiq, S., Mayr-Dorn, C., Mashkoor, A., Egyed, A. (2024). Balanced knowledge distribution
  among software development teams — observations from open- and closed-source software
  development. *Journal of Software: Evolution and Process*. arXiv:2207.12851.
  https://arxiv.org/abs/2207.12851
- Stack Overflow (2026). The 2026 Developer Survey is now open (for human developers only).
  https://stackoverflow.blog/2026/06/23/the-2026-developer-survey-is-now-open-for-human-developers-only/
- Stray, V., Brandtzæg, E. G., Wivestad, V. T., Barbala, A., Moe, N. B. (2026). Developer
  productivity with and without GitHub Copilot: A longitudinal mixed-methods case study.
  HICSS-59. arXiv:2509.20353. https://arxiv.org/abs/2509.20353
- Verwijs, C., Russo, D. (2023). A theory of Scrum team effectiveness. *ACM Transactions on
  Software Engineering and Methodology* 32(3):1–51. doi:10.1145/3571849. arXiv:2105.12439.
  https://arxiv.org/abs/2105.12439
