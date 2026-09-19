---
status: research
date: 2026-09-15
---

# Apprenticeship under agents

Research date: 2026-09-15

This note documents what the sources say about the junior pipeline and learning-by-doing in
a software team when coding agents do the work juniors used to learn on: the pre-AI theory
of apprenticeship (legitimate peripheral participation, cognitive apprenticeship), the
labour-economics of who pays for training, the payroll and résumé datasets that measure
early-career hiring for software developers from 2022 to mid-2026, the usage telemetry that
splits Agent Sessions by user seniority, the experiments in which the least experienced
gained most, the parallel accounts from radiology residency and law, and the 2024–2026
practitioner essays and firm statements on hiring and supervising juniors. It is documentary:
it records what each source found, with its evidence type and limits, and maps each finding
to where the existing notes in this directory touch it. It does not evaluate fit for Dashpot
or any tool. Terminal citations are primary — the paper, the author's own page, the
publisher's page — and every figure is reported as the source states it, with the read level
marked per source ("full text", "abstract", "metadata", "secondary", "unverified"). Where an
earlier note already covers a source this note links to it rather than repeating it: the
trainee skill-fade literature (Beane 2019, Budzyń et al. 2025, Macnamara 2024) and Braverman's
deskilling are in
[adjacent-literatures.md](adjacent-literatures.md#skill-fade-in-medicine) and
[its labour-process section](adjacent-literatures.md#deskilling-as-a-labour-process-concept);
pre-AI mentoring and first-task evidence (Fagerholm, Labuschagne, Tan, Zhou and Mockus) is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#mentoring-and-first-task-evidence);
the computing-education studies of novices with generators (Kazemitabaar, Prather, Bastani)
are in [track-measurement.md](track-measurement.md#the-ai-and-comprehension-studies) and
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#ai-specific-evidence-20232026);
Anthropic's internal study and its Claude Code expertise report are summarised in
[literature-addendum.md](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026);
and Feng et al.'s "Evolving the Mentorship Pipeline" question is in
[track-in-loop-friction.md](track-in-loop-friction.md#open-questions-in-the-sources).

## Finding

The pre-AI account of how a junior becomes a competent engineer is apprenticeship: Lave and
Wenger's legitimate peripheral participation holds that "learning is fundamentally a social
process" in which newcomers do real but low-stakes work at the edge of a community of
practitioners ([Cambridge publisher page](https://www.cambridge.org/core/books/situated-learning/6915ABD21C8E4619F750A4D4ACA616CD),
publisher summary), and Collins, Brown and Newman's cognitive apprenticeship names the
mechanisms — modelling, coaching, scaffolding with "as much support as they need to carry out
the task, but no more", then fading — and observes that in a trade "well-executed skills
result in saleable products", which is what makes an apprentice worth keeping
([ED284181](https://files.eric.ed.gov/fulltext/ED284181.pdf), full text). Labour economists
formalise the same bargain: juniors pay for training by doing routine work whose value the
firm captures, so if agents "eliminate the junior work that once subsidized learning" the
firm loses its reason to train ([Garicano 2025](https://www.siliconcontinent.com/p/the-ai-becker-problem),
full text, argument); Garicano and Rayo's model makes a career viable only when a senior's
expertise leverage ratio exceeds e, below which "wholesale career collapse" follows
([CEPR DP20634](https://cepr.org/publications/dp20634), abstract); Ide shows entry-level
automation can lower growth even without lowering entry-level employment, by moving novices
away from the best experts ([arXiv:2507.16078](https://arxiv.org/abs/2507.16078), abstract);
and Singh's 2026 model turns on observability — "Seniors can no longer observe whether juniors
are learning or just prompting" ([SSRN 6779239](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6779239),
Crossref abstract). The measured hiring evidence is descriptive and contested: ADP payroll
records for 3.5–5 million workers a month show employment of software developers aged 22–25
"declined nearly 20% compared to its peak in late 2022" by September 2025, a 16% relative
decline in AI-exposed occupations after firm-time controls, and by June 2026 a 19% shortfall
for exposed 22–25-year-olds operating "primarily through reduced hiring of young workers
rather than increased separations" — presented by its authors as "early, descriptive
indicators … rather than causal estimates", attenuated by education controls and with some
divergence predating ChatGPT ([Canaries, November 2025 and August 2026 versions](https://digitaleconomy.stanford.edu/publications/canaries-in-the-coal-mine/),
full text); Lambert and Schindler's 243 million hires across four countries find generative-AI
and work-from-home exposure each predict a ~5 pp fall in the junior share of new hires when
estimated separately, but jointly "the GenAI coefficient attenuates sharply" while WFH remains
([Warwick WP 1615](https://warwick.ac.uk/fac/soc/economics/research/workingpapers/2026/twerp_1615_-_lambert.pdf),
full text); Humlum and Vestergaard find precise zeros for Danish workers
([NBER w33777](https://www.nber.org/papers/w33777), abstract); and the Yale Budget Lab finds
"no discernible disruption" 33 months after ChatGPT
([Budget Lab](https://budgetlab.yale.edu/research/evaluating-impact-ai-labor-market-current-state-affairs),
full text). Usage telemetry cuts the other way from the hiring story: in ~400,000 Claude Code
sessions a novice-rated session reaches verified success 15% of the time against 28–33% for
intermediate and above, novices abandon troubled sessions at 19% versus 5–7%, and "domain
expertise, and not coding proficiency, amplifies effective use"
([Anthropic, June 2026](https://www.anthropic.com/research/claude-code-expertise), page); at
Microsoft's early-2026 rollout IC2 and IC3 engineers had −13% and −14% odds of trying the
agent CLI against IC4 while IC5 had +22%, survey respondents doubted juniors who "don't know
what they don't know", yet "more junior ICs … experience a larger PR lift" once they adopt
([arXiv:2607.01418](https://arxiv.org/abs/2607.01418), HTML full text); and Anthropic's June
2026 survey of ~9,700 users finds 68% report learning more with AI while over a third put the
probability of a junior colleague losing their job in the next year above 60%, with the
authors noting "the data do not rule out skill erosion"
([Economic Index, June 2026](https://www.anthropic.com/research/economic-index-june-2026-report),
page). The counter-evidence that juniors gain most is real but pre-agentic and short-horizon:
Cui et al.'s three-firm RCT (n = 4,867) reports "less experienced developers had higher
adoption rates and greater productivity gains" ([SSRN 4945566](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4945566),
abstract), Brynjolfsson, Li and Raymond's 5,172 support agents improve most when least
experienced ([arXiv:2304.11771](https://arxiv.org/abs/2304.11771), abstract), and Dell'Acqua
et al.'s BCG consultants below the average performance threshold gained 43% against 17%
above it
([SSRN 4573321](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4573321), abstract) —
while Kellogg et al.'s qualitative study of 78 of the same consultants finds juniors "may fail
to be a source of expertise" for seniors on the technology
([SSRN 4857373](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4857373), abstract).
Radiology gives the sharpest experimental analogue: with a wrong AI suggestion inexperienced
readers' accuracy fell from 79.7% to 19.8% against 82.3% to 45.5% for the very experienced
([Dratsch et al. 2023](https://pubs.rsna.org/doi/10.1148/radiol.222176), abstract). Firm
practice diverges in the same months: IBM's CHRO says "we are tripling our entry-level
hiring, and yes, that is for software developers" ([Fortune](https://fortune.com/2026/02/13/tech-giant-ibm-tripling-gen-z-entry-level-hiring-according-to-chro-rewriting-jobs-ai-era/),
secondary), Amazon after outages requires "more senior engineers to sign off any AI-assisted
changes" by junior and mid-level engineers ([Ars Technica](https://arstechnica.com/ai/2026/03/after-outages-amazon-to-make-senior-engineers-sign-off-on-ai-assisted-changes/),
secondary), Applied Intuition keeps a no-AI phone screen and adds a two-hour AI-allowed
prototype ([Applied Intuition](https://www.appliedintuition.com/engineering-blog/hiring-engineers-age-of-agents),
full text), and a LeadDev practice account phases in "junior-only review steps" that a manager
withdraws once judgment is shown ([LeadDev](https://leaddev.com/career-development/junior-engineers-are-skipping-straight-to-architect-level-thinking),
full text) — all testimonial. No source measures a junior's skill acquisition under an agent
over more than a session, and no source studies the team-level transfer that apprenticeship
theory says the junior's routine work used to carry.

## Apprenticeship as the pre-AI theory of learning-by-doing

### Lave and Wenger — legitimate peripheral participation

Lave and Wenger, *Situated Learning: Legitimate Peripheral Participation* (Cambridge, 1991;
[doi:10.1017/CBO9780511815355](https://www.cambridge.org/core/books/situated-learning/6915ABD21C8E4619F750A4D4ACA616CD);
publisher summary only, see [Dead ends](#dead-ends)). The publisher's description states
the thesis: "learning is fundamentally a social process and not solely in the learner's
head", and that learners "inevitably participate in communities of practitioners", with
mastery requiring "newcomers to move toward full participation in the sociocultural
practices of a community". The five cases (Yucatec midwives, Vai and Gola tailors, naval
quartermasters, meat cutters, non-drinking alcoholics) are listed there; the tailor study is
Lave's earlier field work, which Collins, Brown and Newman summarise (below). Evidence type:
ethnographic argument. The concept is invoked once in the corpus already, through Johnson and
Senges's Google onboarding study
([unfamiliar code, Google's account](unfamiliar-code-and-shared-models.md#googles-account)).

### Collins, Brown and Newman — cognitive apprenticeship

Collins, Brown and Newman, "Cognitive Apprenticeship: Teaching the Craft of Reading, Writing,
and Mathematics", Technical Report 403, Center for the Study of Reading, January 1987
([ERIC ED284181](https://files.eric.ed.gov/fulltext/ED284181.pdf), full text; the 1989
Resnick-volume chapter is the usual citation). Points the later literature leans on:

- The method: "modelling", "coaching", "scaffolding" and "fading". "With successful
  scaffolding techniques, students get as much support as they need to carry out the task,
  but no more."
- Observation as the first stage: the apprentice watches the master and builds "a conceptual
  model of the target task" before attempting it; Lave's tailors sew from the inside out —
  finishing first, then cutting — so that early errors are cheap.
- The social embedding: "Apprenticeship derives many (cognitively important) characteristics
  from its embedding in a subculture in which most, if not all, members are visible
  participants in the target skills."
- The economic tie: "apprentices have natural opportunities to realize the value, in concrete
  economic terms, of their developing skill: Well-executed skills result in saleable
  products."
- The inefficiency they want to remove: "Letting the job demands select the tasks for
  students to practice is one of the great inefficiencies of traditional apprenticeship."

Evidence type: argument from cases; no measurement. The relevance to this note is that the
1987 text already separates the two things an agent changes at once — the task supply (what
the job demands, which the report calls inefficient but which supplies the practice) and the
saleable output (which justifies keeping the apprentice).

### Software as an apprenticeship industry — practitioner statements

Charity Majors, "Generative AI is not going to build your engineering team for you", Stack
Overflow blog, 10 June 2024 ([stackoverflow.blog](https://stackoverflow.blog/2024/06/10/generative-ai-is-not-going-to-build-your-engineering-team-for-you/),
full text). "Software is an apprenticeship industry"; "It takes a solid seven-plus years to
forge a competent software engineer"; the "Senior Software Engineer" title has become
"shorthand for engineers who can ship code and be a net positive in terms of productivity,
and I think that's a huge mistake"; a colleague's description of a generator as "an excitable
junior engineer who types really fast"; and "We need to stop cannibalizing our own future."
Evidence type: testimonial by a CTO. Written before agentic tools; it is the essay the 2025–26
"who trains the juniors" pieces below reply to.

### Proximity and the feedback channel

Emanuel, Harrington and Pallais, "The Power of Proximity to Coworkers: Training for Tomorrow
or Productivity Today?", NBER w31880 (2023; [nber.org](https://www.nber.org/papers/w31880),
abstract). Software engineers at a Fortune 500 firm whose campus has two buildings; "engineers
working in the same building as all their teammates received 22 percent more online feedback
than engineers with distant teammates"; "sitting together reduces engineers' programming
output, particularly for senior engineers"; proximity dampens short-run pay raises and
boosts long-run ones; the authors read this against "workers in their twenties who often need
mentorship". Evidence type: quasi-experimental (building assignment and office closure).
This is the closest measured statement of the cost of mentoring that the training bargain
below assumes: seniors give up output to train.
Aksoy, Bloom, Davis and Marino, "Remote Work, Employee Mix, and Performance", NBER w33851
(2025; [nber.org](https://www.nber.org/papers/w33851), abstract): at a Turkish call centre,
"fully remote employees with initial in-person training saw higher long-run remote
productivity and lower attrition rates". Both are pre-agent and concern remote work, not
automation, and the second is not software; they are cited here because
Lambert and Schindler (below) treat remote work as the rival explanation for the junior
decline.

## The economics of the training bargain

### Garicano — the "AI Becker problem" and the autonomy threshold

Luis Garicano, "The AI Becker problem", *Silicon Continent*, 23 July 2025
([siliconcontinent.com](https://www.siliconcontinent.com/p/the-ai-becker-problem), full
text; argument). Becker's training problem: general skills are paid for by the trainee,
historically by accepting low wages while doing routine work. "If AI eliminates the junior
work that once subsidized learning, it will devalue the currency workers have traditionally
used to pay for their training." The essay introduces an "autonomy threshold" (from ongoing
work with Jin Li and Yanhui Wu): the point at which a worker can be trusted to act without
review, which agents move upward, so the apprenticeship years produce less value to the firm
while lasting as long. Figures quoted in the essay: NY Fed data showing recent-graduate
unemployment "risen by 30 percent since the pandemic, compared with an 18 percent increase
among all workers", and a SignalFire chart (both secondary in the essay). The law example is
Allen & Overy's adoption of an OpenAI model; the consulting example is McKinsey's "Lilli".

### Garicano and Rayo — the expertise leverage ratio

Garicano and Rayo, "Training in the Age of AI: A Theory of Career Viability", CEPR DP20634,
10 September 2025, revised 2 March 2026 ([cepr.org](https://cepr.org/publications/dp20634),
abstract; paper paywalled, see [Dead ends](#dead-ends)). Canaries cites the earlier title
"…A Theory of Apprenticeship Viability". Abstract: "The expertise leverage ratio, measuring
the output of a fully-trained graduate relative to that of a novice who has just enough
knowledge to outperform AI, governs the overall impact of the technology"; "careers are
guaranteed viable … when this ratio is above a critical threshold, specifically Euler's
number e; in this case, training has a fixed duration and the training path is not at risk.
Below the threshold, the senior's saleable knowledge shrinks and training compresses; in this
case, advances in AI threaten wholesale career collapse." Evidence type: theory. The
abstract does not calibrate the ratio for any occupation.

### Ide — reallocation away from the best experts

Enrique Ide, "Automation, AI, and the Intergenerational Transmission of Knowledge"
(arXiv:2507.16078, v9;
[arXiv](https://arxiv.org/abs/2507.16078), abstract). "A task-based overlapping-generations
model in which novices acquire tacit knowledge by working alongside experts", where
"knowledge-transfer contracts are incomplete because tacit knowledge is embodied and
non-verifiable"; "improvements in entry-level automation increase output upon adoption but
can reduce growth and welfare, even without reducing entry-level employment. This occurs
when such improvements reallocate novices away from the most productive experts, slowing
the diffusion of best practices." Evidence type: theory. Canaries (November 2025) cites Ide
and Garicano and Rayo as the mechanisms it cannot test in payroll data.

### 2026 models: human-capital trap, moral hazard, apprenticeship externality

- Afrouzi, Blanco, Drenik and Hurst, "Automation, Learning, and Career Dynamics", NBER
  w35157 (April 2026;
  [nber.org](https://www.nber.org/papers/w35157), abstract): a continuous-time model in
  which "workers acquire skill through the tasks they perform"; economies with high
  learning capacity have two stationary equilibria, and "cheaper technology has opposite
  effects across the two: in the high-learning equilibrium, it raises welfare through the
  learning channel itself; in the low-learning equilibrium, it tips the economy into a
  human-capital trap." Theory.
- Preet Deep Singh, "Generative AI and the Collapse of Apprenticeship Labor Markets", SSRN
  6779239 (2026; Crossref abstract via
  [doi](https://doi.org/10.2139/ssrn.6779239)): apprenticeship as a moral-hazard contract;
  "Seniors can no longer observe whether juniors are learning or just prompting", so the
  contract that paid juniors for learning collapses even when learning is still possible.
  Theory. This is the one economic model whose mechanism is an observability loss rather
  than a task loss.
- Mustafa Seref Akin, "The Apprenticeship Externality: Generative AI, Entry-Level Work, and
  the Future Supply of Expertise", SSRN 6809082 (2026; [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6809082),
  abstract): an "apprenticeship externality" — a firm automating junior tasks does not
  internalise the lost training of workers who move on — with an over-automation region.
  Theory.

None of the four has data. They are recorded because the payroll papers cite them as the
mechanism behind the numbers below.

## Measured changes in junior developer employment

### Canaries in the coal mine — three vintages

Brynjolfsson, Chandar and Chen, "Canaries in the Coal Mine? Six Facts about the Recent
Employment Effects of Artificial Intelligence", Stanford Digital Economy Lab
([publication page](https://digitaleconomy.stanford.edu/publications/canaries-in-the-coal-mine/);
[November 2025 PDF](https://digitaleconomy.stanford.edu/wp-content/uploads/2025/08/Canaries_BrynjolfssonChandarChen.pdf)
and [August 2026 PDF](https://digitaleconomy.stanford.edu/wp-content/uploads/2026/08/Canaries_August2026.pdf),
both full text). Data: ADP payroll records; "records on 3.5 and 5 million workers each month"
after sample restrictions. Exposure: Anthropic Economic Index task usage mapped to
occupations, split into automative and augmentative use.

The figure that circulates — "13%" — is the August 2025 version's relative decline for
22–25-year-olds in exposed occupations with data through July 2025. The November 2025
version (data through September 2025) states: "Early-career workers (ages 22-25) in
AI-exposed occupations experienced 16% relative employment declines, controlling for
firm-level shocks, while employment for experienced workers remained stable", and for the
occupation this note concerns: "By September 2025, employment for software developers aged
22-25 declined nearly 20% compared to its peak in late 2022." The mechanism paragraph reads:
"AI may be automating the codifiable, checkable tasks that historically justified
entry-level headcount, while complementing the judgment-, client-, and process-intensive
tasks performed by experienced workers", with the footnote "Ironically, one of the practical
skills more likely to be learned on the job than in university computer science classes may
be how to use AI for software development."

The August 2026 revision (data through June 2026) restates six facts: no economy-wide
displacement; exposed 22–25-year-olds "now stands 19% below where it would be had it kept
pace with that of their less-exposed peers; experienced workers show no comparable gap"
(in levels, "fell about 11% between November 2022 and June 2026, while employment of the
same age group in the three least-exposed quintiles grew about 10%"); the divergence has
widened since August 2025; "It operates primarily through reduced hiring of young workers
rather than increased separations"; declines concentrate where usage substitutes for tasks;
and "Adjustment is occurring through employment rather than base compensation". The
robustness paragraph is explicit about limits: the pattern "persists when excluding
technology firms and computer occupations, when controlling for exposure to interest-rate
increases and for remote work", but "these patterns attenuate when controlling for
education, show some divergent trends predating generative AI, and are more pronounced in
the ADP analysis sample than in national survey benchmarks", and the authors "interpret these
facts as early, descriptive indicators — canaries in the coal mine — rather than causal
estimates". On software developers specifically the 2026 text notes an exception to flat
pay: compensation for 22–25-year-old developers "grew somewhat faster than for older workers
in the period after ChatGPT, though the gap shrinks toward the end of the sample", which
"may partly reflect composition effects if firms primarily contracted hiring of lower-paid
engineers". The 2026 version cites Lambert and Schindler and reports that controlling for
their remote-work measure does not remove the divergence in ADP data. Evidence type:
descriptive payroll panel; the authors' own label.

### Lambert and Schindler — remote work as the competing explanation

Lambert and Schindler, "The Broken Ladder: Remote Work, Generative AI and the Decline of
Early-Career Hiring", Warwick Economics Research Paper 1615 / CAGE 808, May 2026
([PDF](https://warwick.ac.uk/fac/soc/economics/research/workingpapers/2026/twerp_1615_-_lambert.pdf),
full text). "Two data sources spanning 243 million new hires and 407 million online job
postings, collected across the US, UK, Canada, and Australia during 2017-2025",
difference-in-differences at occupation, region and firm level. "When estimated separately, a
two-standard-deviation increase in GenAI and WFH exposure each predicts, by 2025, a fall of
around 5pp in the junior-share of new hires and around 3pp in the share of job ads requiring
limited experience." The two exposure measures "have a Spearman rank correlation of 0.77",
and software developers rank at the top of both. "Estimated jointly, the WFH effect remains,
while the GenAI coefficient attenuates sharply and is often statistically indistinguishable
from zero." Evidence type: descriptive difference-in-differences. The paper and Canaries 2026
read the same fact in different data and reach opposite attributions; both are recorded
without adjudication.

### Other datasets

- **Hosseini Maasoum and Lichtinger**, "Generative AI as Seniority-Biased Technological
  Change: Evidence from U.S. Résumé and Job Posting Data" (SSRN 5425555, 31 August 2025;
  [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5425555), abstract via
  Wayback): "U.S. résumé data covering 65 million workers at more than 280,000 firms",
  adoption identified from "GenAI integrator" job postings; "junior employment declines in
  adopting firms relative to non-adopters, while senior employment trends remain largely
  unchanged", "driven primarily by slower hiring rather than increased separations", and
  "GenAI-exposed tasks become increasingly less likely to appear in junior task bundles".
  The abstract gives no magnitude. Firm-level panel.
- **Frank, Sabet, Simon, Bana and Yu**, "AI-exposed jobs deteriorated before ChatGPT"
  (arXiv:2601.02554, 2026; [arXiv](https://arxiv.org/abs/2601.02554), abstract): AI-exposed jobs deteriorated from early 2022, before ChatGPT's release, which
  the authors take as evidence against a pure AI attribution. Descriptive.
- **Humlum and Vestergaard**, "Still Waters, Rapid Currents: Early Labor Market
  Transformation under Generative AI", NBER w33777 (2025;
  [nber.org](https://www.nber.org/papers/w33777), page and abstract; "previously circulated
  under the title 'Large Language Models, Small Labor Market Effects'"): two adoption
  surveys (late 2023 and 2024) "covering 11 exposed occupations (25,000 workers, 7,000
  workplaces), linked to matched employer-employee data in Denmark"; "we estimate precise
  zeros: AI chatbots have had no significant impact on earnings or recorded hours in any
  occupation, with confidence intervals ruling out effects larger than 1%"; average time
  savings of 3%. Survey linked to registers; not juniors specifically.
- **Yale Budget Lab**, "Evaluating the Impact of AI on the Labor Market: Current State of
  Affairs" ([budgetlab.yale.edu](https://budgetlab.yale.edu/research/evaluating-impact-ai-labor-market-current-state-affairs),
  full text, October 2025 update): "the broader labor market has not experienced a
  discernible disruption since ChatGPT's release 33 months ago"; the recent-graduate
  dissimilarity trend "may pre-date ChatGPT's release"; "measures of exposure, automation,
  and augmentation show no sign of being related to changes in employment or unemployment".
  Descriptive, CPS-based; the page itself notes the CPS's noisiness for young workers, and
  Canaries 2026 reports that the CPS holds only 23–48 young software developers a month.
- **Anthropic, "Labor market impacts"** (5 March 2026;
  [anthropic.com](https://www.anthropic.com/research/labor-market-impacts), page): the
  job-finding rate of 22–25-year-olds into exposed occupations fell about 14% relative to
  2022, described as "just barely statistically significant"; no unemployment effect;
  computer programmers among the most covered occupations (75% task coverage). Descriptive,
  CPS flows.
- **SignalFire, "State of Talent 2025"** ([signalfire.com](https://www.signalfire.com/blog/signalfire-state-of-talent-report-2025),
  page; LinkedIn-derived Beacon data): "Big Tech: New grads now account for just 7% of
  hires, with new hires down 25% from 2023 and over 50% from pre-pandemic levels in 2019";
  startups under 6%, down 11% from 2023 and over 30% from 2019; the Magnificent Seven's
  new-grad share roughly halved since 2022. Vendor analysis of a proprietary sample;
  methodology not published beyond the page.
- **NY Fed, "The Labor Market for Recent College Graduates"** ([newyorkfed.org](https://www.newyorkfed.org/research/college-labor-market),
  page): recent-graduate unemployment about 5.6% and underemployment 42% at the 2026 Q2
  reading. The 6.1% computer-science-major figure quoted in Voss's essay (below) was not
  found on the page as read and is marked unverified.

Taken together: two payroll/hiring panels (Canaries, Hosseini and Lichtinger) find a junior
decline at exposed occupations or adopting firms; one hiring panel (Lambert and Schindler)
finds the same decline but attributes it to remote work once both are entered; three
survey-based analyses (Humlum, Yale, Anthropic CPS) find small or null aggregate effects,
with Anthropic's finding a marginal effect specific to the 22–25 job-finding rate. None
observes what the remaining juniors do all day.

## What usage telemetry says about seniority

### Anthropic Economic Index — automation and augmentation

Anthropic's Economic Index reports classify conversations by the collaboration pattern
between user and model: "directive" and "feedback loop" count as automation, "task
iteration", "learning" and "validation" as augmentation. The reports read for this note:

- September 2025 ([report page](https://www.anthropic.com/research/anthropic-economic-index-september-2025-report)):
  coding is 36% of Claude.ai use; directive conversations rose from 27% to 39% since the
  first report; API traffic is 77% automation against about 50% on Claude.ai; the first
  report in which automation exceeds augmentation.
- January 2026 ([report page](https://www.anthropic.com/research/anthropic-economic-index-january-2026-report)):
  augmentation back to 52% on Claude.ai; directive fell 7 pp to 32%; API traffic 64%
  directive and about three-quarters automation; computer and mathematical tasks 36% of
  Claude.ai and 52% of API use; software-development requests reach the report's success
  criterion 61% of the time; the average education level implied by tasks is 13.8 years.
- March 2026, "Learning curves" ([report page](https://www.anthropic.com/research/economic-index-march-2026-report)):
  users with six or more months' tenure are less directive and "about 5 percentage" points
  more successful; "This pushes back against a hypothesis we made last year that automated
  use may be more typical of more experienced, sophisticated users; instead, we find that
  the most advanced users are more likely to iterate with Claude." Coding is migrating to
  the API (+14% API, −18% Claude.ai since August 2025).
- June 2026, "Cadences" ([report page](https://www.anthropic.com/research/economic-index-june-2026-report)):
  a linked survey of "about 9,700" users. "People with at least 15 years of experience put
  that share of tasks AI can do roughly 10 percentage points lower than those in their first
  year of work." "Respondents were especially worried about job loss for their junior
  colleagues, with over one third stating that the probability of a junior colleague losing
  their job in the next year was over 60%." "The majority of people also report learning
  more with AI (68%)", flat across automation share; "However, these are self-assessments,
  and skills can erode even as they become more valuable and as someone reports learning
  more, so the data do not rule out skill erosion."

Evidence type: platform telemetry and a self-selected linked survey; each page states its
own classifier definitions. Seniority is inferred from survey answers or tenure on the
platform, not from HR records.

### Claude Code and expertise

Anthropic, "Agentic coding and persistent returns to expertise", 16 June 2026
([research page](https://www.anthropic.com/research/claude-code-expertise), page; the
planning/execution split is already in
[literature-addendum.md](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026)).
Privacy-preserving analysis of "~400,000" Claude Code sessions from about 235,000 people,
with a classifier rating the user's apparent expertise. "A novice-rated session reaches our
strictest measure, verified success, 15% of the time and at least partial success 77% of the
time. A session rated intermediate or up reaches verified success 28-33% of the time and
partial success 91-92% of the time." "19% of sessions where the user appears to be a novice
end abandoned, against 5-7% for everyone else." "Among sessions that hit trouble, the share
that are verified successes rises from 4% for novice-rated sessions to 15% for expert-rated
ones." "We also see evidence that domain expertise, and not coding proficiency, amplifies
effective use of the tool." Software occupations reach verified success in about 30% of
sessions against 26% for other professions. Evidence type: telemetry with classifier-rated
expertise; no ground-truth seniority and no longitudinal measure of the same user.

### Microsoft's rollout — a seniority gradient in adoption and lift

Murphy-Hill, Butler and Savelieva, "Adoption and Impact of Command-Line AI Coding Agents: A
Study of Microsoft's Early 2026 Rollout of Claude Code and GitHub Copilot CLI"
(arXiv:2607.01418; [HTML](https://arxiv.org/html/2607.01418), full text). Career stage from
HR records, IC2–IC6 and M4–M6, IC4 as reference. "Junior ICs were less likely to try Copilot
CLI. IC2 and IC3 engineers had lower odds of trying it than a mid-level IC (−13% and −14%);
their retention markers were noisy, with only IC2's statistically significant." "IC5 and IC6
engineers had higher odds than a mid-level IC — about +22% for IC5 — but their retention
markers sat near zero." Adoption spread socially: skip-level peers' use raised the odds of
trying by +216%. On impact, "IC4 reference adopters experienced a +21.3% [+19.6%, +23.0%]
lift in the number of PRs they created", and "more junior ICs and more senior managers
experience a larger PR lift"; the headline is "roughly 24% more pull requests" with a 95%
CI of +14.5% to +33.7%. Survey text: one respondent was "less convinced that junior
developers (who 'don't know what they don't know') would be able to use them as
effectively"; another asked "what these tools mean for junior colleagues and how they can
develop a good 'sense' for code […] to know when [the] output is not optima[l]". Evidence
type: observational telemetry with HR seniority, four-month window; Pull Request counts
only, no skill or comprehension measure. The paper records both directions at once —
juniors adopt less and gain more Pull Requests per adopter.

## Counter-evidence: where the least experienced gained most

### Productivity experiments, 2023–2024

Each of the following found the largest gain for the least experienced. None used an
agentic tool, none ran longer than a few months, and none measured skill after the tool was
removed.

- Cui, Demirer, Jaffe, Musolff, Peng and Salz, "The Effects of Generative AI on High-Skilled
  Work: Evidence from Three Field Experiments with Software Developers" (SSRN 4945566;
  [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4945566), abstract; the
  26.08% headline and n = 4,867 are in
  [track-measurement.md](track-measurement.md#proxies-and-telemetry)): "Notably, less
  experienced developers had higher adoption rates and greater productivity gains." RCT at
  Microsoft, Accenture and a Fortune 100 firm; completed Pull Requests.
- Peng, Kalliamvakou, Cihon and Demirer, "The Impact of AI on Developer Productivity:
  Evidence from GitHub Copilot" (arXiv:2302.06590; [arXiv](https://arxiv.org/abs/2302.06590),
  abstract): the treatment group "completed the task 55.8% faster than the control group";
  "Observed heterogenous effects show promise for AI pair programmers to help people
  transition into software development careers". Controlled experiment (HTTP server in
  JavaScript); participant count not in the abstract.
- Brynjolfsson, Li and Raymond, "Generative AI at Work" (arXiv:2304.11771 v2;
  [arXiv](https://arxiv.org/abs/2304.11771), abstract): 5,172 customer-support agents,
  productivity "by 15% on average"; "Less experienced and lower-skilled workers improve both
  the speed and quality of their output while the most experienced and highest-skilled
  workers see small gains in speed and small declines in quality"; "AI assistance
  facilitates worker learning". Staggered rollout; not software.
- Dell'Acqua et al., "Navigating the Jagged Technological Frontier" (SSRN 4573321, 2023;
  [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4573321), abstract via Wayback):
  758 BCG consultants; "those below the average performance threshold increasing by 43% and
  those above increasing by 17% compared to their own scores" on tasks inside the frontier;
  19 percentage points less likely to be correct on the task outside it. RCT; the "cybernetic teammate" follow-up is in
  [automation-as-a-team-player.md](automation-as-a-team-player.md#ai-agents-as-teammates-in-field-experiments-outside-code).
- Choi, Monahan and Schwarcz, "Lawyering in the Age of Artificial Intelligence" (SSRN
  4626276; [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4626276), abstract
  via Wayback): RCT with law students and GPT-4; "access to GPT-4 only slightly and
  inconsistently improved the quality of participants' legal analysis but induced large and
  consistent increases in speed"; "where it was useful at all, the lowest-skilled
  participants saw the largest improvements"; time saved was "roughly the same amount…
  regardless of their baseline speed".

### Kellogg et al. — juniors as a source of expertise for seniors

Kellogg, Lifshitz-Assaf, Randazzo, Mollick, Dell'Acqua, McFowland, Candelon and Lakhani,
"Don't Expect Juniors to Teach Senior Professionals to Use Generative AI: Emerging
Technology Risks and Novice AI Risk Mitigation Tactics", HBS Working Paper 24-074, 3 June
2024 (SSRN 4857373;
[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4857373), abstract via Wayback).
"We interviewed 78 such junior consultants in July-August 2023" after the BCG experiment;
"such juniors may fail to be a source of expertise in the use of emerging technologies for
more senior professionals; instead, they may recommend three kinds of novice AI risk
mitigation tactics that: 1) are grounded in a lack of deep understanding of the emerging
technology's capabilities, 2) focus on change to human routines rather than system design,
and 3) focus on interventions at the project-level rather than system deployer- or
ecosystem-level." Qualitative;
consulting, not software. It is the one study in this set that asks whether the junior's
routine work still carries knowledge upward, and it answers no for this technology.

## Other trades

### Radiology residents

- Dratsch et al., "Automation Bias in Mammography: The Impact of Artificial Intelligence
  BI-RADS Suggestions on Reader Performance", *Radiology* 2023
  ([doi:10.1148/radiol.222176](https://pubs.rsna.org/doi/10.1148/radiol.222176), PubMed
  abstract): 27 radiologists read mammograms with correct or incorrect AI BI-RADS
  suggestions; with an incorrect suggestion inexperienced readers' accuracy fell from 79.7%
  to 19.8%, moderately experienced from 81.3% to 24.8%, very experienced from 82.3% to 45.5%;
  "inexperienced radiologists were significantly more likely to follow the suggestions of the
  purported AI when it incorrectly suggested a higher BI-RADS category". Crossover
  experiment; the accuracy numbers are as the abstract states them.
- Savardi et al., "Upskilling or deskilling? Measurable role of an AI-supported training for
  radiology residents: a lesson from the pandemic", *Insights into Imaging* 16(1):23, 2025
  ([doi:10.1186/s13244-024-01893-4](https://doi.org/10.1186/s13244-024-01893-4), abstract):
  eight residents scoring 150 chest radiographs under no-AI, on-demand and integrated-AI
  conditions; "Residents required AI in 70% of cases when left free to choose"; AI support
  "increased inter-rater agreement by 22%"; "Residents were resilient to AI errors above an
  acceptability threshold". Small prospective study; the authors frame it as balancing
  "educational benefits and deskilling risks".
- The corpus already holds Beane's shadow-learning ethnography of surgical residents and
  Budzyń's colonoscopy deskilling (28.4% to 22.4%), in
  [adjacent-literatures.md](adjacent-literatures.md#skill-fade-in-medicine); they are not
  repeated.

The radiology pattern — experience protects against following a wrong suggestion — is the
inverse of the productivity experiments above, and it is measured on the same kind of task
the agent-coding telemetry calls a "troubled session".

### Law

- LexisNexis UK, "AI as a thinking partner: training junior lawyers without weakening
  judgment", reporting its January 2026 survey of UK-based legal professionals
  ([lexisnexis.co.uk](https://www.lexisnexis.co.uk/blog/future-of-law/ai-as-a-thinking-partner-how-mid-law-firms-can-train-junior-lawyers-without-weakening-judgment),
  vendor blog; sample size not stated on the page): "72% of lawyers are concerned that
  junior lawyers using AI will struggle to develop deep legal reasoning and argumentation";
  "69% worry about verification and source-checking skills"; "Only 2% believe AI
  strengthens learning"; "52% of respondents supported verification exercises that require
  juniors to check AI outputs against authoritative sources". Vendor survey; the
  "verification exercise" is the legal profession's named replacement for document review.
- Choi, Monahan and Schwarcz (above) is the law RCT; Garicano's essay (above) uses Allen &
  Overy as its example of a firm whose junior work is the first automated.

## Practitioner accounts and firm practice, 2024–2026

All items in this section are testimonial or secondary unless marked otherwise.

### "Juniors can't code" and its replies

- Namanyay Goel, "New Junior Developers Can't Actually Code", 14 February 2025
  ([nmn.gl](https://nmn.gl/blog/ai-and-learning), full text; the page claims
  1,000,000 views): juniors ship working code but "when I dig deeper into their
  understanding of what they're shipping? That's where things get concerning"; "The
  foundational knowledge that used to come from struggling through problems is just…
  missing"; "We're trading deep understanding for quick fixes". Anecdotal; no counts.
- Can Elma, "AI makes seniors stronger", 21 September 2025
  ([canelma.com](https://canelma.com/engineering/ai-makes-seniors-stronger), full text):
  "AI was supposed to help juniors shine"; argues the gain accrues to whoever can already
  judge the output, since the model "possesses no internal mechanism to verify its own
  ignorance". Argument.
- Laurie Voss, "AI has torched the market for junior programmers", 4 July 2026
  ([seldo.com](https://seldo.com/posts/ai-has-torched-the-market-for-junior-programmers),
  full text): compiles Canaries ("a 16% relative employment decline for young workers in
  AI-exposed jobs"), BLS "computer programmer" employment −16% May 2024 to May 2025, and
  Indeed postings; "The market for young programmers has collapsed"; the training system
  was "apprenticeship inside employment" and has gone. Secondary compilation with argument.
- Francisco Trindade (VP Engineering, Braze), "The Kids Are Alright", 2 August 2026, and
  "The Kids Are Really Alright", 18 August 2026
  ([franciscotrindade.me](https://franciscotrindade.me/blog/the-kids-are-alright/)
  and [sequel](https://franciscotrindade.me/blog/the-kids-are-really-alright/), full
  text): replies to a CTO who said juniors "could be a liability, shipping changes that
  broke things"; the second post reports that "this summer, we assigned the problem to an
  intern" and "the intern led the development of this feature" that had been requested for
  years. Single case, testimonial.
- Be a Better Dev, "AI is Making Junior Devs Useless (Here's the Fix)", 1 March 2026
  ([beabetterdev.com](https://beabetterdev.com/2026/03/01/ai-is-making-junior-devs-useless/),
  full text; author identifies as a senior Amazon engineer): "That failure pattern
  recognition is what companies are actually paying for". Argument.
- Andrew Churchill (Workweave), "Hiring only senior engineers is the worst policy in the
  startup industry", 23 September 2025
  ([workweave.dev](https://workweave.dev/blog/hiring-only-senior-engineers-is-killing-companies),
  full text): "In the last 3 months, I've interviewed 134 engineers"; cites Shopify hiring
  25 interns in early 2025; describes an AI-allowed take-home followed by a walkthrough
  interview. Testimonial from a vendor.
- Justin Smestad, "If You Stop Hiring Juniors, Your Senior Engineers Own You", 26 April
  2026 ([evalcode.com](https://evalcode.com/posts/if-you-stop-hiring-juniors-your-seniors-own-you/), full text):
  "junior employees are salary insurance"; quotes Shopify: "We significantly expanded
  early-career hiring for 2026"; proposes a junior path built on reviewing agent output and
  tracing why a generated change is wrong. Argument with a secondary Shopify quote.

### Firms that changed junior practice

- **AWS.** Matt Garman, quoted by *The Register*, 21 August 2025
  ([theregister.com](https://www.theregister.com/2025/08/21/aws_ceo_entry_level_jobs_opinion/),
  secondary): replacing junior staff with AI is "the dumbest thing I've ever heard"; juniors
  are "probably the least expensive employees you have" and the most engaged with AI tools.
- **IBM.** CHRO Nickle LaMoreaux, quoted by *Fortune*, 13 February 2026
  ([fortune.com](https://fortune.com/2026/02/13/tech-giant-ibm-tripling-gen-z-entry-level-hiring-according-to-chro-rewriting-jobs-ai-era/),
  secondary): "We are tripling our entry-level hiring, and yes, that is for software
  developers and all these jobs we're being told AI can do"; the roles are described as
  rewritten around AI supervision. The same article notes layoffs announced the following
  week. No numbers behind "tripling" on the page.
- **Amazon.** *Ars Technica* citing the *Financial Times*, 10 March 2026
  ([arstechnica.com](https://arstechnica.com/ai/2026/03/after-outages-amazon-to-make-senior-engineers-sign-off-on-ai-assisted-changes/),
  secondary): after a 13-hour outage in which the Kiro agent chose to "delete and recreate
  the environment", "Junior and mid-level engineers will now require more senior engineers
  to sign off any AI-assisted changes". This is a seniority-gated review policy on Pull
  Requests, reported second-hand; the internal memo was not read.
- **Applied Intuition**, Kesav Viswanadha, "Hiring Engineers for the Age of Agents", 22 July 2026
  ([appliedintuition.com](https://www.appliedintuition.com/engineering-blog/hiring-engineers-age-of-agents), full
  text): "Keep our technical phone screen as is" (no AI); onsite adds a design round after
  which "the candidate gets two hours to build a working prototype of the system they just
  designed using any AI model they want"; a 30-candidate trial rated by 15 interviewers gave
  86%, 85%, 91% and 99% agreement on four survey items. Firm-published process with a small
  internal survey.
- **Shopify** appears only second-hand (Churchill: 25 interns in early 2025; Smestad:
  "significantly expanded early-career hiring for 2026"); no first-party Shopify page was
  found.
- **A LeadDev practice account**: Subathra Thanabalan, "Junior engineers are skipping straight to
  architect-level thinking", 25 August 2026
  ([leaddev.com](https://leaddev.com/career-development/junior-engineers-are-skipping-straight-to-architect-level-thinking),
  full text): phases the tool as tutor, then copilot, then accelerator; assigns a named
  mentor; "Once they consistently show solid judgment and stable quality on AI-assisted
  work, managers can phase out the extra junior-only review steps"; treats "engineering
  growth itself – learning, understanding, and judgment – as a primary metric, not just
  throughput, using humans as mentors and tooling as tutor". Single-author practice
  description; the corpus lists the related LeadDev talk "Guardrails, not gates" in
  [discourse-and-tooling-addendum.md](discourse-and-tooling-addendum.md#target-3-20252026-talks-beyond-litts).

### Roundtable and policy statements

Kang, Ray and Roychoudhury, "Skills for the future software profession: beyond agentic AI!"
(arXiv:2606.21894 v2, 23 June 2026; [arXiv](https://arxiv.org/abs/2606.21894), HTML full
text): a report on two 2026 round-tables in New York and Singapore whose recommendations
include "authorship policies that assign responsibility to human custodians" for
agent-written code; it cites Storey's cognitive-debt posts. Position paper; no data. It is the one source that ties the junior question to
authorship of agent output — who is the custodian of a change no person wrote.

## Computing-education and skill-acquisition evidence

The corpus already records the novice studies this section would otherwise repeat:
Kazemitabaar et al. 2023 (69 novices, retention one week later) and 2024, Prather's
"illusion of competence" and widening gap, and Bastani's 17% reduction in
[track-measurement.md](track-measurement.md#the-ai-and-comprehension-studies) and
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#ai-specific-evidence-20232026);
Gardella's "Fast and Forgettable" retest (N = 22, g = −1.13), Brender and Barth in
[literature-addendum.md](literature-addendum.md#target-5-retention-spacing-and-spaced-repetition-on-a-codebase);
Anthropic's internal study (n = 132 + 53) in
[literature-addendum.md](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026);
and the summary table in
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#summary-table). What that literature
has and this note's sources lack is a delayed skill measure; what this note's sources have
and that literature lacks is a workplace and a team. No source read for this note measures a
professional junior's skill acquisition under an agent across more than one session, and
none observes whether the senior who would have reviewed the junior's Pull Request now
reviews the agent's instead.

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where existing notes touch it |
|---|---|---|---|
| Learning is social participation at the periphery of a community of practice | Lave and Wenger 1991 (publisher summary) | Ethnographic argument | Johnson and Senges's LPP framing in [unfamiliar code, Google's account](unfamiliar-code-and-shared-models.md#googles-account) |
| Modelling, coaching, scaffolding "but no more", fading; saleable products justify the apprentice | Collins, Brown and Newman 1987 (full text) | Argument from cases | No counterpart |
| Seven-plus years to a competent engineer; generator as "excitable junior engineer who types really fast" | Majors 2024 (full text) | Testimonial | Howard's junior/senior/middle split in [answer-ai-sweep, core claims](answer-ai-sweep.md#core-claims) |
| Co-located engineers get 22% more code feedback; proximity trades senior output for junior pay growth | Emanuel, Harrington and Pallais 2023 (abstract) | Quasi-experimental telemetry | Mentoring cost in [unfamiliar code, mentoring evidence](unfamiliar-code-and-shared-models.md#mentoring-and-first-task-evidence) |
| Juniors pay for training with routine work; agents "devalue the currency" | Garicano 2025 (full text) | Argument | Braverman's separation of conception from execution in [adjacent, deskilling](adjacent-literatures.md#deskilling-as-a-labour-process-concept) |
| Career viable only above an expertise leverage ratio of e | Garicano and Rayo 2025/26 (abstract) | Theory | No counterpart |
| Entry-level automation can lower growth without lowering entry-level employment | Ide 2025 (abstract) | Theory | No counterpart |
| Seniors "can no longer observe whether juniors are learning or just prompting" | Singh 2026 (abstract) | Theory | Feng et al.'s mentorship-pipeline question in [in-loop friction, open questions](track-in-loop-friction.md#open-questions-in-the-sources) |
| Software developers 22–25 down "nearly 20%" from late-2022 peak; 16% relative decline; 19% shortfall by June 2026 via reduced hiring; descriptive, attenuates with education | Brynjolfsson, Chandar and Chen 2025/2026 (full text) | Descriptive payroll panel | No counterpart |
| Junior share of hires falls ~5 pp with either GenAI or WFH exposure; GenAI attenuates when jointly estimated | Lambert and Schindler 2026 (full text) | Descriptive DiD | No counterpart |
| Precise zeros in Denmark; no discernible disruption at 33 months; 14% job-finding drop "just barely" significant | Humlum and Vestergaard; Yale Budget Lab; Anthropic labour page | Survey/CPS descriptive | No counterpart |
| Directive use rose then fell; long-tenure users iterate more and succeed ~5 pp more; 68% report learning more, "do not rule out skill erosion" | Anthropic Economic Index Sept 2025, Jan, Mar, Jun 2026 (pages) | Platform telemetry and linked survey | No counterpart |
| Novice sessions 15% verified success vs 28–33%; 19% abandonment vs 5–7%; domain expertise, not coding proficiency | Anthropic Claude Code report 2026 (page) | Telemetry with classifier-rated expertise | Planning/execution split in [literature addendum, Target 1](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026) |
| IC2/IC3 −13%/−14% odds of trying vs IC4, IC5 +22%; juniors larger PR lift once adopted; "don't know what they don't know" | Murphy-Hill et al. 2026 (HTML full text) | Observational telemetry with HR seniority | 24% PR headline in [literature addendum, Target 1](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026) |
| Least experienced gained most in 2023–24 productivity experiments | Cui et al.; Peng et al.; Brynjolfsson, Li and Raymond; Dell'Acqua et al. 2023; Choi et al. (abstracts) | RCTs | Cui and Peng headlines in [measurement, proxies](track-measurement.md#proxies-and-telemetry); Dell'Acqua 2025 in [team player, field experiments](automation-as-a-team-player.md#ai-agents-as-teammates-in-field-experiments-outside-code) |
| Juniors "may fail to be a source of expertise" for seniors on generative AI | Kellogg et al. 2024 (abstract) | Qualitative, 78 interviews | No counterpart |
| Wrong AI suggestion drops inexperienced readers to 19.8% vs 45.5% for very experienced | Dratsch et al. 2023 (abstract) | Crossover experiment, n = 27 | Trainee skill fade in [adjacent, skill fade in medicine](adjacent-literatures.md#skill-fade-in-medicine) |
| 72% of lawyers fear juniors will not develop reasoning; verification exercises as the replacement task | LexisNexis UK 2026 (vendor page) | Vendor survey | No counterpart |
| Firms diverge: IBM triples entry-level hiring; Amazon gates junior AI-assisted changes behind senior sign-off; Applied Intuition keeps a no-AI screen and adds an AI prototype round | Fortune; Ars Technica; Applied Intuition blog | Secondary and firm-published | Seniority-gated review has no counterpart; LeadDev "Guardrails, not gates" listed in [discourse addendum, Target 3](discourse-and-tooling-addendum.md#target-3-20252026-talks-beyond-litts) |
| Junior-only review steps phased out once judgment is shown; humans as mentors, tooling as tutor | Thanabalan 2026 (full text) | Practice description | Stray's finding that stand-ups transfer more to juniors in [flow, the daily stand-up](flow-wip-limits-and-constraints.md#the-daily-stand-up) |
| No source measures junior skill acquisition under an agent beyond a session, or team-level transfer | This note's sweep | Absence | Gap 9 in [synthesis, gaps](synthesis.md#gaps-every-pass-left); Feng et al. in [in-loop friction, open questions](track-in-loop-friction.md#open-questions-in-the-sources) |

"No counterpart" means no note in this directory addresses the point; it is a statement
about the notes, not about the wider literature.

## Corrections proposed

(added 2026-09-20: every item below was applied inline at the target
sentence it names, marked `(corrected 2026-09-15: …)`, `(qualified 2026-09-15: …)`,
or `(added 2026-09-15: …)` there. The target's marker is the authoritative
copy; this list is the proposal as made and is not updated after it.)

1. **literature-addendum.md, Target 1**: "adopters 'merged roughly 24% more pull requests
   than they would have otherwise' (95% CI 14.5–33.7% per the search summary; not verified
   in the PDF)" — the interval is now verified: the arXiv HTML full text of 2607.01418
   states a lift "over the post-period [95% CI +14.5%, +33.7%]", and the abstract page was
   the read level at the time. The entry's read level can be raised from "abstract page
   read" to "HTML full text", and the sentence about the interval can drop "per the search
   summary; not verified in the PDF". The same source also carries the seniority gradient
   (IC2/IC3 −13%/−14% odds of trying; larger PR lift for junior ICs) recorded in this note,
   which the addendum's "No skill, comprehension or ownership measure" sentence does not
   contradict.

## Dead ends

- **Lave and Wenger 1991, full text.** Cambridge Core asset PDFs timed out (connection
  hung, HTTP 000); the Cambridge page yielded only the publisher summary; the Internet
  Archive item `situatedlearning0000lave` is lending-restricted (401 on the DjVu text,
  no JSON from the inside-search endpoint); Google Books API returned no preview. Read level
  is publisher summary plus Collins, Brown and Newman's account of Lave's tailor study.
- **Garicano and Rayo, CEPR DP20634.** Paper paywalled (£6); abstract only. The Canaries
  citation uses the earlier title "…A Theory of Apprenticeship Viability"; the current CEPR
  page gives "…A Theory of Career Viability", revised 2 March 2026.
- **SSRN direct fetch** returns "Content Blocked"/403 for every abstract page; the
  abstracts for 5425555, 4857373, 4573321 and 4626276 were read from Wayback Machine raw
  captures (`web.archive.org/web/2025id_/…`; 4573321 needed a 2024 capture). The SSRN URLs
  in the text are the terminal citations; the read is from the archived copy.
- **Hosseini Maasoum and Lichtinger.** Abstract only; the size of the junior decline at
  adopting firms is not in the abstract and is not reported here.
- **Singh 2026 and Akin 2026.** Crossref/SSRN abstracts only; neither full text was
  reachable.
- **Semantic Scholar, arXiv export API and OpenAlex** rate-limited or budget-exhausted
  during the sweep (429; OpenAlex "Insufficient budget… Resets at midnight UTC"); three
  WebSearch calls were used instead, and Crossref and PubMed E-utilities for metadata.
- **NY Fed computer-science-major unemployment (6.1%).** Quoted in Voss's essay; not found
  on the NY Fed page as read; marked unverified and not used as a figure.
- **Fortune IBM article.** The URL first found was truncated (404); the full URL was
  recovered from the Hacker News Algolia index (item 47009327). The article is the only
  source for "tripling" and gives no baseline.
- **Amazon senior sign-off policy.** Read only through Ars Technica's summary of the
  *Financial Times*; the FT article and the internal memo were not read.
- **Shopify junior hiring.** No first-party statement located; two practitioner essays quote
  it second-hand.
- **Anthropic Economic Index landing page** is script-rendered; report slugs were recovered
  from the page source. The September 2025 and January 2026 reports live under
  `/research/anthropic-economic-index-…`, the March and June 2026 reports under
  `/research/economic-index-…`.
- **Firm-published junior tracks.** Beyond Applied Intuition's hiring post and the LeadDev
  practice account, no engineering blog describing a redesigned junior onboarding
  programme under agents was found within the search budget (one WebSearch spent).
- **Junior skill-acquisition studies under agents, 2025–2026.** One WebSearch spent; nothing
  found that follows professional juniors across sessions with a skill measure. The
  computing-education studies in the corpus remain the only delayed-measure designs.
- **Law and document review.** One WebSearch spent; the LexisNexis vendor survey is the only
  source found that names the junior task replacement; its sample size is not on the page.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Afrouzi, H., Blanco, A., Drenik, G., Hurst, E. (2026). Automation, learning, and career dynamics. *NBER Working Paper* 35157. Abstract.
- Akin, M. S. (2026). The apprenticeship externality: generative AI, entry-level work, and the future supply of expertise. *SSRN* 6809082. Abstract.
- Aksoy, C. G., Bloom, N., Davis, S., Marino, V. (2025). Remote work, employee mix, and performance. *NBER Working Paper* 33851. Abstract.
- Anthropic (2025). Anthropic Economic Index, September 2025 report. Page.
- Anthropic (2026). Anthropic Economic Index, January 2026 report. Page.
- Anthropic (2026). Labor market impacts, 5 March 2026. Page.
- Anthropic (2026). Economic Index, March 2026 report ("Learning curves"). Page.
- Anthropic (2026). Economic Index, June 2026 report ("Cadences"). Page.
- Anthropic (2026). Agentic coding and persistent returns to expertise, 16 June 2026. Page.
- Applied Intuition, Viswanadha, K. (2026). Hiring engineers for the age of agents. Engineering blog, 22 July 2026. Full text.
- Ars Technica (2026). After outages, Amazon to make senior engineers sign off on AI-assisted changes, 10 March 2026. Secondary.
- Be a Better Dev (2026). AI is making junior devs useless (here's the fix), 1 March 2026. Full text.
- Brynjolfsson, E., Chandar, B., Chen, R. (2025, 2026). Canaries in the coal mine? Six facts about the recent employment effects of artificial intelligence. Stanford Digital Economy Lab; November 2025 and August 2026 versions. Full text.
- Brynjolfsson, E., Li, D., Raymond, L. (2023). Generative AI at work. arXiv:2304.11771 v2. Abstract.
- Choi, J. H., Monahan, A., Schwarcz, D. (2023). Lawyering in the age of artificial intelligence. *SSRN* 4626276. Abstract.
- Churchill, A. (2025). Hiring only senior engineers is the worst policy in the startup industry. Workweave blog, 23 September 2025. Full text.
- Collins, A., Brown, J. S., Newman, S. E. (1987). Cognitive apprenticeship: teaching the craft of reading, writing, and mathematics. Technical Report 403, Center for the Study of Reading; ERIC ED284181. Full text.
- Cui, Z. K., Demirer, M., Jaffe, S., Musolff, L., Peng, S., Salz, T. (2024). The effects of generative AI on high-skilled work: evidence from three field experiments with software developers. *SSRN* 4945566. Abstract.
- Dell'Acqua, F., et al. (2023). Navigating the jagged technological frontier. *SSRN* 4573321. Abstract.
- Dratsch, T., et al. (2023). Automation bias in mammography: the impact of artificial intelligence BI-RADS suggestions on reader performance. *Radiology* 307(4). doi:10.1148/radiol.222176. Abstract.
- Elma, C. (2025). AI makes seniors stronger, 21 September 2025. Full text.
- Emanuel, N., Harrington, E., Pallais, A. (2023). The power of proximity to coworkers. *NBER Working Paper* 31880. Abstract.
- Fortune (2026). IBM is tripling the number of Gen Z entry-level jobs, 13 February 2026. Secondary.
- Frank, M. R., Sabet, A. J., Simon, L., Bana, S. H., Yu, R. (2026). AI-exposed jobs deteriorated before ChatGPT. arXiv:2601.02554. Abstract.
- Garicano, L. (2025). The AI Becker problem. *Silicon Continent*, 23 July 2025. Full text.
- Garicano, L., Rayo, L. (2025, rev. 2026). Training in the age of AI: a theory of career viability. *CEPR Discussion Paper* 20634. Abstract.
- Goel, N. (2025). New junior developers can't actually code, 14 February 2025. Full text.
- Hosseini Maasoum, S. M., Lichtinger, G. (2025). Generative AI as seniority-biased technological change: evidence from U.S. résumé and job posting data. *SSRN* 5425555. Abstract.
- Humlum, A., Vestergaard, E. (2025). Still waters, rapid currents: early labor market transformation under generative AI. *NBER Working Paper* 33777. Abstract.
- Ide, E. (2025). Automation, AI, and the intergenerational transmission of knowledge. arXiv:2507.16078 v9. Abstract.
- Kang, S., Ray, B., Roychoudhury, A. (2026). Skills for the future software profession: beyond agentic AI! arXiv:2606.21894 v2. Full text (HTML).
- Kellogg, K. C., Lifshitz-Assaf, H., Randazzo, S., Mollick, E. R., Dell'Acqua, F., McFowland, E., Candelon, F., Lakhani, K. R. (2024). Don't expect juniors to teach senior professionals to use generative AI: emerging technology risks and novice AI risk mitigation tactics. *HBS Working Paper* 24-074; *SSRN* 4857373. Abstract.
- Lambert, T., Schindler, D. (2026). The broken ladder: remote work, generative AI and the decline of early-career hiring. *Warwick Economics Research Paper* 1615 / *CAGE* 808. Full text.
- Lave, J., Wenger, E. (1991). *Situated Learning: Legitimate Peripheral Participation*. Cambridge University Press. doi:10.1017/CBO9780511815355. Publisher summary.
- LexisNexis UK (2026). AI as a thinking partner: training junior lawyers without weakening judgment (January 2026 survey). Vendor page.
- Majors, C. (2024). Generative AI is not going to build your engineering team for you. Stack Overflow blog, 10 June 2024. Full text.
- Murphy-Hill, E., Butler, J., Savelieva, K. (2026). Adoption and impact of command-line AI coding agents: a study of Microsoft's early 2026 rollout of Claude Code and GitHub Copilot CLI. arXiv:2607.01418. Full text (HTML).
- New York Fed. The labor market for recent college graduates. Page.
- Peng, S., Kalliamvakou, E., Cihon, P., Demirer, M. (2023). The impact of AI on developer productivity: evidence from GitHub Copilot. arXiv:2302.06590. Abstract.
- Savardi, M., Signoroni, A., Benini, S., et al. (2025). Upskilling or deskilling? Measurable role of an AI-supported training for radiology residents: a lesson from the pandemic. *Insights into Imaging* 16(1):23. doi:10.1186/s13244-024-01893-4. Abstract.
- SignalFire (2025). State of Talent report 2025. Page.
- Singh, P. D. (2026). Generative AI and the collapse of apprenticeship labor markets. *SSRN* 6779239. Abstract (Crossref).
- Smestad, J. (2026). If you stop hiring juniors, your senior engineers own you. evalcode.com, 26 April 2026. Full text.
- Thanabalan, S. (2026). Junior engineers are skipping straight to architect-level thinking. LeadDev, 25 August 2026. Full text.
- The Register (2025). AWS CEO says using AI to replace junior staff is 'dumbest thing I've ever heard', 21 August 2025. Secondary.
- Trindade, F. (2026). The kids are alright, 2 August 2026; The kids are really alright, 18 August 2026. Full text.
- Voss, L. (2026). AI has torched the market for junior programmers. seldo.com, 4 July 2026. Full text.
- Yale Budget Lab (2025). Evaluating the impact of AI on the labor market: current state of affairs. Full text.
