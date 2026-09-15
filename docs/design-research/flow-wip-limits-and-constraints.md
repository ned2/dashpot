---
status: research
date: 2026-09-15
---

# Flow, WIP limits and constraints

Research date: 2026-09-15

This note documents what the process literature already holds on team-level friction devices —
work-in-progress (WIP) limits, pull, batch size, the Theory of Constraints, the Definition of
Done, stage gates — and which agile ceremonies the studies of them find to function as
knowledge transfer. It is documentary: it records what each source claims, what evidence stands
behind the claim, and with what sample, and maps each finding to where the existing notes in
this directory touch it. It does not evaluate fit for Dashpot or any tool. Terminal citations
are primary — the guide, the paper, the author's own copy, the vendor's own report — and every
figure is reported as the source states it, with its evidence type marked (measured,
qualitative, testimonial, argument). Read level is marked per source: "full text" where the
whole document was read, "abstract", "metadata", or "secondary" where only another source's
restatement was reachable; anything recalled rather than read is marked unverified. Two things
the note looks for specifically: sources that connect WIP limits or batch size to
*comprehension, review load, or knowledge sharing* rather than to throughput, and the point in
each process book where a claim rests on queueing theory by analogy rather than on measurement
in software teams. Where an earlier note already covers a source, this note links to it rather
than repeating it: review as transfer, pairing, mob programming and inspection are in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model),
the code-review comprehension studies in
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding),
the AI-era reviewer-load numbers in
[track-hand-off-checks.md](track-hand-off-checks.md#evidence), the resumption-cost work of
Parnin and Rugaber in
[track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking),
and the review-speed and PR-size telemetry in
[track-measurement.md](track-measurement.md#proxies-and-telemetry).

## Finding

The process literature's team-level friction devices divide cleanly by the kind of evidence
behind them. WIP limits and pull are defined by the practice texts as a constraint on the count
of started-but-unfinished items ("must explicitly control the number of work items in a
workflow from started to finished", [Kanban Guide 2025](https://kanbanguides.org/the-kanban-guide/2025.5/),
full text) and are justified there by queueing theory named as analogy ("Kanban draws on
established flow theory, including ... queuing theory (batch size and queue size)", same page)
and by a human-factors claim about context switching stated without a citation
([Kanban University guide](https://kanban.university/kanban-guide/), full text); the measured
software evidence for them is two single-company before–after studies — Sjøberg, Johnsen and
Solberg's >12,000 work items at one ~100-developer company where replacing Scrum with
Kanban-with-a-WIP-limit roughly halved lead time and raised PBI productivity 21% while bug
productivity fell 11% (measured, no control group,
[IEEE Software 2012](https://www.mn.uio.no/ifi/personer/vit/dagsj/sjoberg.johnsen.solberg.ieee.sw.pdf),
full text), and Middleton and Joyce's nine-person BBC Worldwide team where over 12 months lead
time fell 37% (22.8 to 14.4 days), its variance 47%, and customer-reported defects 24%
(measured, one team, [IEEE TEM 2012](https://doi.org/10.1109/tem.2010.2081675), full text) —
and three systematic reviews that found 19, 23 and 20 primary studies respectively, mostly
single-case, none a controlled experiment, in which "improved communication and coordination"
and "promoting a culture of continuous learning" appear as reported benefits but as
practitioner perception, not as a measured comprehension or knowledge outcome (Ahmad, Markkula
and Oivo 2013, abstract; [Ahmad, Dennehy, Conboy and Oivo 2018](https://doi.org/10.1016/j.jss.2017.11.045),
full text, 23 papers, 16 single-case, learning cited by 6; [dos Santos et al. 2018](https://doi.org/10.1186/s40411-018-0057-1),
full text, 20 studies, "absence of negative results reported"). The one place WIP and
comprehension meet with software measurement is *batch size at review*: Baum, Schneider and
Bacchelli's confirmatory experiment (n = 50, 46 professionals, median 84 minutes) found review
effectiveness 59% for small versus 35% for large changes and 15.65 versus 9.47 defects per hour,
one seeded defect found in 38 of 50 small reviews (76%) versus 9 of 25 large (36%), all
significant after Bonferroni–Holm correction (measured, [EMSE 2019](https://doi.org/10.1007/s10664-018-9676-8),
full text); Bosu, Greiler and Bird's ~1.5 million comments across five Microsoft projects show
useful-comment density falling as the file count of a change rises (measured, observational,
[MSR 2015](https://doi.org/10.1109/msr.2015.21), full text); and SmartBear's vendor study of
2,500 Cisco reviews over 3.2 million lines by 50 developers reports defect density trailing off
above about 200 lines and reviewers faster than 400 lines/hour finding fewer defects, on the
stated assumption that true defect density is constant across change sizes (measured,
vendor-reported, [Cohen 2006](https://web.archive.org/web/20101009071211id_/http://smartbear.com:80/code-collaborator/docs/book/code-review-cisco-case-study.pdf),
full text). The batch-size argument in Reinertsen's *Flow* is explicitly not a collection of
company studies ("It is not a collection of company stories") and its figures — 98.5% average
utilisation, 2% of developers measuring queues, 3% trying to reduce batch size — come from
uncounted "precourse surveys" of his own course attendees (argument plus unsized testimonial,
[chapter 1](http://celeritaspublishing.com/wp-content/uploads/2013/07/ReinertsenFLOWChap1.pdf),
full text); DORA's small-batches capability rests on a >4,600-respondent 2016 survey model in
which small batches loaded with flow visibility and predicted IT performance, and on the 2017
survey (3,200 respondents) in which the same authors "flipped the model and found that IT
performance predicts lean product management practices", settling on a reciprocal model
(measured self-report, [2016](https://dora.dev/research/2016/2016-state-of-devops-report.pdf),
[2017](https://dora.dev/research/2017/2017-state-of-devops-report.pdf), full text). The
Theory of Constraints reaches software only as method text and a manufacturing meta-analysis
that "found no reports of failures" (Mabin and Balderstone 2003, abstract), and Stage-Gate as
Cooper's own articles and Griffin's 1997 PDMA survey (abstracts). The Definition of Done is
defined by the [Scrum Guide 2020](https://scrumguides.org/scrum-guide.html) as creating
"transparency by providing everyone a shared understanding of what work was completed" (full
text); its only sizeable empirical study is Kopczyńska et al.'s survey of 137 practitioners, of
whom 93% rated the DoD at least valuable, whose DoD items were most often about tests (29),
code review (15), acceptance criteria (15) and documentation (12), and 70% or more of whose
projects reported "some team members had different understanding of DoD" (measured self-report,
[arXiv:2208.04003](https://arxiv.org/abs/2208.04003), full text). Of the ceremonies, the daily
stand-up is the one with direct knowledge-transfer evidence and it is mixed: Stray, Sjøberg and
Dybå's grounded theory (12 teams, 3 companies, 60 interviews, 79 observed meetings) names
"information sharing" and "team awareness" as the most-cited benefits, finds that low knowledge
redundancy makes members uninterested in each other's reports (twelve interviewees), and
measured meetings shortening from 27 to 19 minutes when a reporting manager left (measured plus
qualitative, [JSS 2016](https://doi.org/10.1016/j.jss.2016.01.004), full text); their 2020
observation of 102 meetings across 15 teams found only 34% of meeting time spent on the three
questions and 31% on problem-focused discussion, with juniors more positive than seniors
(measured, [IEEE Software 2020](https://arxiv.org/abs/1808.07650), full text); and a 221-person
survey found 44.7% of attendees positive, 36.6% negative, the positive group significantly
younger (29.6 vs 33.5 years, p = 0.008) (measured self-report,
[XP 2017](https://doi.org/10.1007/978-3-319-57633-6_20), full text). Retrospectives have no
learning-outcome evidence at all by their own researchers' account — "We do not know of studies
investigating the learning effect of retrospectives" ([Dingsøyr et al. 2018](https://doi.org/10.1007/978-3-319-91602-6_13),
full text; 109 issues and 36 action items from one team's reports (corrected 2026-09-15: the minutes are from two of the programme's four teams over seven iterations, per the paper's section 3 and Table 1 caption "In total 109 issues were recorded during seven iterations for two teams" and "the two teams identified 36 action items")) — and Andriyani, Hoda and
Amor's 16 interviews across four teams found one team never reaching the reconstructing level
of reflection and a member reporting "200 action points ... not a single one followed up"
(qualitative, [XP 2017](https://doi.org/10.1007/978-3-319-57633-6_1), full text). No source
found measures whether a WIP limit, a batch-size rule or a gate changes what a team member
*understands* of code; the connection is inferred in every case from review effectiveness,
meeting content, or self-reported benefit.

## The devices as their own texts state them

### Kanban: visualise, limit WIP, pull

The [Kanban Guide](https://kanbanguides.org/the-kanban-guide/2025.5/) (Coleman and Vacanti,
May 2025 revision; full text) makes an explicit "Definition of Workflow" the basis of the
method ("The explicit shared understanding of flow among Kanban system members within their
context is called a Definition of Workflow"), requires that members "must explicitly control
the number of work items in a workflow from started to finished", and claims for that control
that it "helps flow and often improves the Kanban system members' collective focus, commitment,
and collaboration" — a claim stated without evidence. Four flow metrics are mandatory (WIP,
throughput, work item age, cycle time), each defined as a count or an elapsed time. The
theory section names the justification as borrowed: "Kanban draws on established flow theory,
including but not limited to systems thinking, lean principles, queuing theory (batch size and
queue size), variation, and quality control." Nothing in the guide concerns what a member
knows or understands beyond the shared definition of the workflow itself.

Kanban University's [Official Guide to the Kanban Method](https://kanban.university/kanban-guide/)
(full text; authored by Susanne and Andreas Bartel with Kanban University, based on Anderson
2010) lists six practices — visualise, limit work in progress, manage flow, make policies
explicit, implement feedback loops, improve collaboratively — and motivates the WIP limit by a
human-factors claim: limiting WIP avoids "context switching that can drastically reduce the
effectiveness of workers". No citation accompanies the claim. Anderson's 2010 book itself was
not readable (the archive.org lending copy returned 401/403; see Dead ends), so the practice is
documented here from the two guides that descend from it.

### Reinertsen's flow principles

Reinertsen's *The Principles of Product Development Flow* (2009) is the source most process
texts cite for the batch-size and queue arguments. Only chapter 1 was readable
([publisher PDF](http://celeritaspublishing.com/wp-content/uploads/2013/07/ReinertsenFLOWChap1.pdf),
full text). It states the book's form plainly: 175 principles in eight themes — economics,
queues, variability, batch size, WIP constraints, cadence and synchronisation, fast feedback,
decentralised control — and "It is not a collection of company stories." The figures the
chapter uses to motivate the problem are from "precourse surveys" of the author's course
attendees, with no n given: 98.5% average utilisation targeted, 2% of product developers
measuring queues, 15% knowing their cost of delay, 3% trying to reduce batch size, 65% wanting
to eliminate variability, 95% beginning design before requirements are fully known. The chapter
asserts a "critical relation between batch size and feedback speed" as principle, not as a
measured result. Two blog posts extend the argument: "The Four Impostors" (2013-02-01,
[reinertsenassociates.com](https://reinertsenassociates.com/the-four-impostors-success-failure-knowledge-creation-and-learning/),
full text) treats small batches through an information-theory analogy (a lottery example) and
states that "learning and knowledge sometimes have economic value; but this value does not
arise simply because learning and knowledge are intrinsically 'good'" — knowledge is valued
only as it changes decisions; and "Is One-Piece Flow the Lower Limit for Product Developers"
([reinertsenassociates.com](https://reinertsenassociates.com/is-one-piece-flow-the-lower-limit-for-product-developers/),
full text) argues that batches below one item are possible in development because an item can
be split. Both are argument. Little's law itself, which the process books invoke, is a result
about steady-state queues: Little 1961 (*Operations Research* 9(3):383–387,
[doi:10.1287/opre.9.3.383](https://doi.org/10.1287/opre.9.3.383), metadata) and Little's own
2011 fiftieth-anniversary review ([doi:10.1287/opre.1110.0940](https://doi.org/10.1287/opre.1110.0940),
abstract), neither of which concerns software or people.

### Lean software development

Poppendieck's "Lean Programming" (*Software Development Magazine*, May/June 2001; full text via
the [Wayback copy of poppendieck.com](https://web.archive.org/web/20010408070557id_/http://www.poppendieck.com:80/lean.htm))
is the earliest statement of the lean transfer and is explicit about its method: "Lean
Manufacturing rules have been tested and proven" and are carried over to software as ten rules,
of which the one bearing on this note is "Minimize Inventory (Minimize Intermediate
Artifacts)" — requirements and design documents are inventory in the manufacturing sense, so
their reduction is argued from the manufacturing analogy, with Frailey cited for small batches.
The later seven principles of *Lean Software Development* (2003), including "amplify learning",
were reachable only as Ahmad et al. 2018's restatement (secondary); the book itself was not
readable (Dead ends). No measurement of software teams appears in the 2001 article.

### Theory of Constraints

The Goldratt Institute's white paper "The Theory of Constraints and its Thinking Processes"
(©2001–2009; full text via the [Wayback copy](https://web.archive.org/web/20110813080003id_/http://www.goldratt.com:80/pdfs/toctpwp.pdf))
states the five focusing steps verbatim — identify the constraint; decide how to exploit it;
subordinate and synchronise everything else to that decision; elevate the constraint; if a
constraint has been broken, go back to step one — and cites Mabin and Balderstone's review for
mean improvements. Mabin and Balderstone's meta-analysis (*IJOPM* 23(6):568–595,
[doi:10.1108/01443570310476636](https://doi.org/10.1108/01443570310476636), abstract) covers
"over 80" published TOC applications, mainly manufacturing, and reports that it "found no
reports of failures" — a statement the abstract itself flags as a publication-bias concern. No
software-team measurement of TOC was found (Dead ends). Goldratt's own books were not readable.
The device therefore enters software as method text: a rule for where to place a limit
(at the constraint) rather than evidence about what the limit does to the people at it.

### Stage-Gate

Cooper's "Stage-gate systems: a new tool for managing new products" (*Business Horizons*
33(3):44–54, 1990, [doi:10.1016/0007-6813(90)90040-I](https://doi.org/10.1016/0007-6813(90)90040-I))
was reachable only as metadata (paywalled; 1,828 citations counted by OpenAlex). Cooper's
2008 update (*JPIM* 25(3):213–232, [doi:10.1111/j.1540-5885.2008.00296.x](https://doi.org/10.1111/j.1540-5885.2008.00296.x),
abstract) argues for "gates with teeth" and against overbureaucratising the process. Griffin's
PDMA best-practices survey (*JPIM* 14(6):429–458, 1997,
[doi:10.1111/1540-5885.1460429](https://doi.org/10.1111/1540-5885.1460429), abstract) reports
that more than half of responding firms used a cross-functional stage-gate process and more than
a third had no formal process. Cooper and Sommer's agile–stage-gate hybrid (*Industrial
Marketing Management* 59:167–180, 2016, metadata) was not read. The stage-gate literature is
new-product management, not software teams; it is recorded here because "gate" in the AI-era
material (see [track-hand-off-checks.md](track-hand-off-checks.md#gate-placement-and-enforcement))
borrows its vocabulary.

### Scrum's Daily Scrum, Sprint Retrospective and Definition of Done

The [Scrum Guide 2020](https://scrumguides.org/scrum-guide.html) (Schwaber and Sutherland;
full text) defines the three ceremonies this note examines. The Daily Scrum's purpose is "to
inspect progress toward the Sprint Goal ... improve communications, identify impediments,
promote quick decision-making, and consequently eliminate the need for other meetings". The
Sprint Retrospective's purpose is "to plan ways to increase quality and effectiveness"; the
team "inspects how the last Sprint went with regards to individuals, interactions, processes,
tools, and their Definition of Done". The Definition of Done "creates transparency by
providing everyone a shared understanding of what work was completed as part of the
Increment". All three are practice text; the guide cites nothing.

## WIP limits and pull: what was measured

### Sjøberg, Johnsen and Solberg 2012

"Quantifying the Effect of Using Kanban versus Scrum: A Case Study" (*IEEE Software* 29(5):47–53,
[doi:10.1109/ms.2012.110](https://doi.org/10.1109/ms.2012.110); full text from the
[author's copy](https://www.mn.uio.no/ifi/personer/vit/dagsj/sjoberg.johnsen.solberg.ieee.sw.pdf))
analysed "more than 12,000 work items" from 2009–2011 at Software Innovation (about 100
developers, 330 employees), which used Scrum from 2007 to autumn 2010 and then Kanban with a
WIP limit. Measured: lead time "almost halved" (bugs from 12 to 5 days; after adjusting for
churn, 58% reduction for bugs and 40% for product backlog items); weighted bugs down 10% (1,774
to 1,591 per quarter); productivity up 21% for PBIs and down 11% for bugs on the authors'
second productivity measure; raw items per person, bugs 15.3 to 12.1 and PBIs 5.9 to 10.2;
developers plus testers grew from 40 to 48 and project managers fell from 4 to 3. The authors
caution that Kanban succeeded Scrum in time, so there is no control, and that the 2010 Scrum
lead time was already at the later Kanban level. The paper reports nothing about knowledge or
comprehension; its variables are lead time, quality and productivity. Read level: full text.

### Middleton and Joyce 2012

"Lean Software Management: BBC Worldwide Case Study" (*IEEE Transactions on Engineering
Management* 59(1):20–32, [doi:10.1109/tem.2010.2081675](https://doi.org/10.1109/tem.2010.2081675);
full text via the Wayback copy of the Queen's University Belfast repository PDF) followed a
nine-person team through 2009. Measured over 12 months: lead time "reduced by 37% or 8.4 days
from 22.8 to 14.4 working days"; lead-time variance "reduced by 47% from 70.7 to 37.3";
development time for smaller features "declined by 73% from 9.2 to 2.5 working days"; releases
from 2 to 16 per month; customer-reported defects down 24% (2.9 to 2.2 per week). WIP limits
were set from staffing constraints (fewer QA and business-analyst staff than developers). The
paper's one comprehension claim is qualitative and stated through Little's law by analogy:
"Using short-cycle times and the kanban boards to reduce WIP did accelerate the software
development team's learning ... The learning curve was increased by the effect of Little's Law
[32], which facilitates learning by shorter cycle times and the transparency resulting from
reduced WIP." Little's law is introduced as "a basic manufacturing principle" and the authors
write that "Given the nature of software, the precise unit size and the value of the output
cannot be measured exactly, but Little's Law appears to be working." On the stand-up: "The
social value of the daily standup also cannot be underestimated. The requirement to daily share
the progress of your work with your peers was a powerful motivator and source of discipline"
(testimonial). Read level: full text.

### The systematic reviews

Ahmad, Markkula and Oivo, "Kanban in software development: A systematic literature review"
(SEAA 2013, [doi:10.1109/seaa.2013.28](https://doi.org/10.1109/seaa.2013.28); abstract via
OpenAlex) screened 492 papers to 19 primary studies and lists as reported benefits improved
lead time, quality, "communication and coordination", consistency of delivery and fewer customer
defects, and as challenges lack of knowledge and training and organisational issues. Full text
was not reached.

Ahmad, Dennehy, Conboy and Oivo, "Kanban in software engineering: A systematic mapping study"
(*JSS* 137:96–113, 2018, [doi:10.1016/j.jss.2017.11.045](https://doi.org/10.1016/j.jss.2017.11.045);
full text via the Wayback copy of the University of Oulu repository PDF) screened 382 to 23
primary papers from 2006–2016 plus 23 experience reports. Of the primary studies 20 are case
studies, 16 of them single-case; controlled experiments were excluded by the search's own
result (none found); the two simulation studies (Anderson et al. 2011; Concas et al. 2013)
were excluded; no study scored full marks on the Dybå–Dingsøyr quality criteria. Benefits by
count of studies reporting them: visibility and transparency 16, control of tasks 12,
identification of impediments 10, improved workflow 7, communication and collaboration 7,
motivation 6, "promoting a culture of continuous learning" 6. The recommended practices
include "Enforce WIP limit strictly, it will help team members to focus." Each benefit is a
practitioner-reported outcome counted across studies, not a measured effect size. The paper
restates Poppendieck's seven lean principles including "amplify learning" — the only route by
which that text was reachable here. Read level: full text.

dos Santos, Beltrão, de Souza and Travassos, "On the benefits and challenges of using kanban in
software engineering: a structured synthesis study" (*JSERD* 6:13, 2018,
[doi:10.1186/s40411-018-0057-1](https://doi.org/10.1186/s40411-018-0057-1); full text)
synthesised 20 primary studies with a belief-weighted method: highest belief in work visibility
(84%), control of activities (83%), flow of work (77%), and time-to-market. The authors record
the "absence of negative results reported in the technical literature", which they treat as a
limitation of the evidence base. Read level: full text.

Ahmad et al.'s HICSS 2016 interview study ([doi:10.1109/hicss.2016.670](https://doi.org/10.1109/hicss.2016.670),
abstract) covers 17 interviews in two Finnish maintenance teams moving from Scrum to Kanban;
no numbers were readable.

### What the Kanban evidence says about comprehension and knowledge sharing

Reading the three reviews and two case studies together: every study measures lead time,
throughput, defects or delivery variance; where communication, collaboration or learning
appear they are counted as benefits *reported* by the studied teams (Ahmad 2018: 7 and 6
studies of 23) or asserted by analogy (Middleton and Joyce's Little's-law sentence). No primary
study in the three reviews' inclusion sets is described as measuring what a team member knows
or can explain before and after a WIP limit. The Kanban Guide's own claim — that WIP control
"often improves ... collective focus, commitment, and collaboration" — is uncited in the guide
and unmeasured in the reviews.

## Batch size and review load

### Baum, Schneider and Bacchelli 2019 — change size in a controlled experiment

"Associating working memory capacity and code change ordering with code review performance"
(*Empirical Software Engineering* 24(4):1762–1798,
[doi:10.1007/s10664-018-9676-8](https://doi.org/10.1007/s10664-018-9676-8); full text via the
Wayback copy of the Zurich Open Repository PDF). The corpus already cites this paper for its
working-memory result
([evidence-and-mechanisms.md](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding));
what that note does not carry is the change-size comparison, which is the paper's strongest
effect. Design: confirmatory controlled experiment, 50 participants (46 professionals), median
84 minutes of review; two small change reviews and one large. Measured: "the mean review
effectiveness is 59% for the small reviews and 35% for the large reviews. The mean review
efficiency is 15.65 defects/hour for the small reviews and 9.47 defects/hour for the large
reviews"; a specific seeded defect was found "in 38 of 50 occasions (detection probability:
76%)" as a small review versus "9 of 25 times (detection probability: 36%)" as a large one; all
three differences significant after Bonferroni–Holm correction. Working memory was moderately
associated with finding delocalised defects only; the change-ordering hypothesis was
inconclusive. The related-work section summarises the practice it tests: MacLeod et al. 2017's
"aim for small incremental changes" and Rigby et al. 2014's finding that churn lengthens the
review interval (secondary through Baum). Read level: full text.

### Bosu, Greiler and Bird 2015 — useful-comment density falls with file count

"Characteristics of useful code reviews: an empirical study at Microsoft" (MSR 2015,
[doi:10.1109/msr.2015.21](https://doi.org/10.1109/msr.2015.21); full text via the Wayback copy
of the Microsoft Research PDF). A classifier of comment usefulness was applied to "∼1.5 million
code review comments from five Microsoft projects". Measured, observational: "the more files
that are in a change, the lower the proportion of comments in the code review that will be of
value to the author of the change" (their Figure 8 trendline), which the authors say "supports
Rigby's recommendation for smaller changesets"; and a reviewer's proportion of useful comments
"increases dramatically in the first year that he or she is at Microsoft but tends to plateau
afterwards". The explanation offered is the developers' own: "if there are more files to
review, then a thorough review takes more time and effort. As a result, reviewers may opt for
cursory review of large changesets" (qualitative). Read level: full text.

### SmartBear's Cisco study 2006 — 200 lines and 400 lines per hour

"Code Review at Cisco Systems" (Cohen, in SmartBear's *Best Kept Secrets of Peer Code Review*,
2006; full text via the [Wayback copy](https://web.archive.org/web/20101009071211id_/http://smartbear.com:80/code-collaborator/docs/book/code-review-cisco-case-study.pdf)).
A vendor study by the maker of the tool used: "2500 reviews of 3.2 million lines of code written
by 50 developers" over ten months (July 2005 to May 2006). Measured: "61% of the reviews
uncovered no defects"; "Anything below 200 lines produces a relatively high rate of defects,
often several times the average. After that the results trail off considerably; no review
larger than 250 lines produced more than 37 defects per 1000 lines of code"; "Reviewers slower
than 400 lines per hour were above average" in defect density found. The chapter's own
footnote states the assumption the size result depends on: "we're tacitly assuming that true
defect density is constant over both large and small code changes." The 60-minute fatigue
figure ("after 60 minutes reviewers 'wear out'") is cited there from other inspection
literature, not measured at Cisco. The widely quoted "200–400 lines" review rule descends from
this chapter. Read level: full text.

### Google's "Small CLs" — practice text

Google's engineering-practices page [Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html)
(full text) gives the reasons for small changes as "Reviewed more quickly", "Reviewed more
thoroughly", less likely to introduce bugs, easier to merge and to roll back, and sizes them:
"100 lines is usually a reasonable size for a CL, and 1000 lines is usually too large", with a
200-line change across 50 files also called too large. The page states the reviewer's position
directly — "the reviewer often has no context" — and is argument from practice; it cites no
study. Sadowski et al.'s Google review study, which the corpus already summarises
([evidence-and-mechanisms.md](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding)),
supplies the practice's scale (about nine million changes, most with one reviewer).

### Reinertsen and DORA on batch size — argument and survey

Reinertsen's batch-size principles (above) are argument by queueing theory with course-survey
figures of unstated n. DORA's [Working in small batches](https://dora.dev/capabilities/working-in-small-batches/)
capability page (full text) describes the practice — batches completable in under a week,
MVPs, splitting features — and its pitfalls, and cites the 2016, 2017 and 2023 reports without
reproducing statistics. The [2016 State of DevOps Report](https://dora.dev/research/2016/2016-state-of-devops-report.pdf)
(full text; "more than 4,600" respondents) modelled lean product management as three constructs
— working in small batches "that can be completed in less than a week", understanding and
visibility of the flow of work, and customer feedback — and found them predictive of IT
performance and of lower deployment pain by partial-least-squares structural equation
modelling (SmartPLS 3.2.0); the report notes that small batches and flow visibility
"statistically load together". The [2017 report](https://dora.dev/research/2017/2017-state-of-devops-report.pdf)
(full text; 3,200 respondents) reverses the arrow: "This year, we flipped the model and found
that IT performance predicts lean product management practices", and the authors adopt a
reciprocal model. Both are cross-sectional self-report surveys; neither measures comprehension,
review load or knowledge sharing. The corpus's treatment of DORA's later instruments is in
[track-measurement.md](track-measurement.md#self-report-and-survey-instruments).

## Multitasking and interruption: the WIP argument's human-factors leg

The Kanban University guide's "context switching" sentence is the point where the WIP argument
leaves queueing theory for psychology. The software studies that measure switching are
observational and concern productivity, not understanding. Vasilescu et al., "The sky is not
the limit: multitasking across GitHub projects" (ICSE 2016,
[doi:10.1145/2884781.2884875](https://doi.org/10.1145/2884781.2884875); abstract) found that
developers who focus on few projects per day are more productive and that excessive switching
lowers productivity (measured from GitHub activity). Tregubov, Boehm, Rodchenko and Lane,
"Impact of task switching and work interruptions on software development processes" (ICSSP
2017, [doi:10.1145/3084100.3084116](https://doi.org/10.1145/3084100.3084116); abstract via
OpenAlex) measured in an educational setting that developers on two or more projects spend on
average 17% of effort on cross-project interruptions, that Weinberg's often-quoted heuristic
overestimates the loss, and that the correlation between number of projects and effort is weak.
Shakeri Hossein Abad et al., "Task interruption in software development projects" (EASE 2018,
[arXiv:1805.05508](https://arxiv.org/abs/1805.05508); full text) analysed 4,910 tasks of 17
professional developers plus a 132-response survey and found self-interruptions more
disruptive than external ones; it cites Parnin and Rugaber's 10,000-session study for the
15–30 minutes needed to reconstruct context, which the corpus already holds
([track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)).
Sedano, Ralph and Péraire, "Software development waste" (ICSE 2017,
[doi:10.1109/icse.2017.20](https://doi.org/10.1109/icse.2017.20); abstract via OpenAlex;
full text closed) is the one lean-derived taxonomy grounded in observation — two years and five
months of participant observation across eight Pivotal projects with 33 interviews — and its
nine wastes include "extraneous cognitive load", "waiting/multitasking", "knowledge loss" and
"ineffective communication"; the abstract gives no counts. Stray et al. 2016 use the same
resumption-cost literature to explain why a stand-up scheduled mid-flow is experienced as an
interruption (full text; see the stand-up section). None of these sources measures what is
understood after a switch; they measure time, effort, or throughput.

## Definition of Done and gates as shared understanding

The Scrum Guide's sentence — the DoD "creates transparency by providing everyone a shared
understanding of what work was completed" — is the one place in the practice texts where a
friction device is defined *as* a shared-understanding device rather than as a flow device.
Silva et al., "A systematic review on the use of Definition of Done on agile software
development projects" (EASE 2017, [doi:10.1145/3084226.3084262](https://doi.org/10.1145/3084226.3084262))
was reachable only as a truncated abstract ("little is known of its actual use in Agile teams";
OpenAlex and Semantic Scholar both elide the rest) and as Kopczyńska et al.'s restatement
(secondary): 8 relevant studies, DoD items defined at up to four levels (story, sprint, release,
project), four primary studies mentioning benefits, and the conclusion that "there is a need for
more and better empirical studies documenting and evaluating the use of the DoD".

Kopczyńska, Ochodek, Piechowiak and Nawrocki, "On the benefits and problems related to using
Definition of Done — a survey study" (*JSS* 2022, [doi:10.1016/j.jss.2022.111479](https://doi.org/10.1016/j.jss.2022.111479);
full text of the [arXiv preprint](https://arxiv.org/abs/2208.04003)) is the sizeable empirical
source. Sample: 137 complete responses (139 incomplete), practitioners from over 20 countries.
Measured self-report: 93% (128) rated using a DoD "Rather valuable" or "Definitely valuable"
and 64% (88) definitely valuable; the top benefits by percentage of projects reporting them
were "Help to make work items complete" (93%), "Help to assure quality of product" (92%),
"Help to ensure that the activities other than coding were executed (e.g., code review, manual
testing, build)" (90%), "Help to ensure that all quality gates are passed" (90%), and "Help to
keep product releasable" (86%); "Promotion on the meaning of 'complete' work between
stakeholders" 79%; "Help to make team members aware of the current status of the project" 66%;
"Help to keep the documentation up-to-date" 56%. DoD items shared by respondents were "most
frequently about tests (29 items), code review (15), acceptance criteria (15), and
documentation (12)". The five most frequent problems — difficult or time-consuming to
implement items, "Some team members had different understanding of DoD", difficult to verify,
difficulty defining a universal DoD, imprecise items — "were reported to appear in 70% or more
of the projects"; unclear, missing or unverifiable items in over 60%; an undocumented DoD,
incorrect items and infeasible items in more than 45%. Among 31 respondents describing projects
without a DoD, "Lack of shared understanding what done means" (6) and "Misunderstandings" (5)
head the team-level consequences. Six respondents said DoD problems were solved in team
interaction such as retrospectives, after which items "started to have shared understanding".
The survey measures perception; no comprehension outcome is tested. Read level: full text.

Stage gates as Cooper defines them (above) are decision points with deliverables and criteria,
and Cooper 2008's argument for "gates with teeth" concerns whether projects are actually killed,
not what anyone learns. The corpus's own treatment of AI-era approval gates and where they are
placed is in [track-hand-off-checks.md](track-hand-off-checks.md#gate-placement-and-enforcement);
its finding that no source measures the comprehension effect of an approval gate
([synthesis.md](synthesis.md#gaps-every-pass-left), item 2) is unchanged by anything found here:
the stage-gate and DoD literature measures adoption and perceived value.

## Ceremonies as knowledge transfer

### The daily stand-up

Stray, Sjøberg and Dybå, "The daily stand-up meeting: a grounded theory study" (*JSS*
114:101–124, 2016, [doi:10.1016/j.jss.2016.01.004](https://doi.org/10.1016/j.jss.2016.01.004);
full text via the Wayback copy of the BIBSYS Brage PDF). Method: grounded theory across twelve
teams in three companies in Malaysia, Norway, Poland and the United Kingdom; 60 interviews; 79
observed meetings. Findings: the positive categories are information sharing and discussing
and solving problems, the negative are status reporting to a manager and meetings held too
often or too long; "team awareness" — "an understanding of the activities of others" — is the
most-mentioned benefit. Two explanations are offered as propositions: "A low level of knowledge
redundancy in the team negatively affects the DSMs; participants are uninterested in what
others are doing because it does not concern them" (twelve interviewees "stated that they were
not interested in what others were doing"; the authors connect this to Levesque et al. 2001,
which the corpus holds in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research)),
and "A low level of self-management makes it easy for authoritative managers to use the
meeting to obtain status information". One measured before–after: when a reporting project
manager left one team, meeting duration fell from 27 minutes (median 28) to 19 (median 17);
sit-down meetings "lasted 63% longer than the stand-up meetings" (12 versus 19 minutes on
average). The paper's definition sets the meeting's "primary purpose" as "to make team members
obtain a shared understanding of the current activities of other team members", and its
guideline table lists "Improve communication, knowledge sharing and team orientation" among
benefits and "Interruption of workflow" among pitfalls, citing the resumption-cost literature
(fifteen minutes or more to make the first edit after an interruption). Adoption context:
VersionOne's 2013 survey put the stand-up at 85% of agile organisations (secondary through
Stray). Read level: full text.

Stray, Moe and Bergersen, "Are daily stand-up meetings valuable? A survey of developers in
software teams" (XP 2017, LNBIP 283:274–281,
[doi:10.1007/978-3-319-57633-6_20](https://doi.org/10.1007/978-3-319-57633-6_20); full text,
open access). Sample: 221 responses, 165 recruited from a programming forum, 96.8% male, mean
age 31. Measured self-report: the stand-up "was used by 87%" of agile-team respondents and by
35.4% of those in non-agile teams; 70.6% attend; among attendees the mean value rating was 3.1
on a five-point scale, with 44.7% positive, 36.6% negative and 18.7% neutral; those positive
were "significantly younger (p = 0.008, positive: M = 29.6 years, n = 49; negative: M = 33.5
years, n = 42)" and attended fewer meetings per day; teams of twelve or more were the most
negative; those negative rated their own skills higher than their peers'. Read level: full text.

Stray, Moe and Sjøberg, "Daily stand-up meetings: start breaking the rules" (*IEEE Software*
37(3):70–77, 2020, [doi:10.1109/ms.2018.2875988](https://doi.org/10.1109/ms.2018.2875988);
full text of the [arXiv copy](https://arxiv.org/abs/1808.07650)). Method: 102 observed
meetings and 60 interviews across 15 teams in five countries. Measured: "only 34% of the
meeting was spent on answering the three questions"; 31% on "elaborating problem issues,
discussing" — problem-focused communication; "juniors were more satisfied with the meetings
than seniors", seniors often perceiving the meetings as giving them little; larger teams
drifted toward reporting meetings. The paper's problem list includes "Productivity is reduced
because the day is broken into slots". Read level: full text.

The corpus already carries the newcomer angle: Dagenais et al. 2010 found daily scrums
"ensured that newcomers would not stay stuck ... more than a day"
([unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#dagenais-ossher-bellamy-robillard-and-de-vries-2010--moving-into-a-new-software-project-landscape)),
and Middleton and Joyce's "powerful motivator and source of discipline" (above) is the case
study's testimonial. Together the stand-up evidence says: the meeting transfers awareness of
*what others are doing*, transfers more to juniors than to seniors, transfers less where
members' work does not overlap, and costs a mid-day interruption; no study measures a change
in any member's model of the code.

### Retrospectives and postmortems

Dingsøyr, "Postmortem reviews: purpose and approaches in software engineering" (*IST*
47(5):293–303, 2005, [doi:10.1016/j.infsof.2004.08.008](https://doi.org/10.1016/j.infsof.2004.08.008);
full text via the Wayback copy of the author's preprint) frames the postmortem as knowledge
sharing and records, from the literature it reviews, that only about one project in five
receives a post-project review, that Keegan and Turner found no company satisfied with its
practice, and that written postmortem reports are often not used afterwards (secondary through
Dingsøyr). Read level: full text.

Bjørnson, Wang and Arisholm, "Improving the effectiveness of root cause analysis in post mortem
analysis: a controlled experiment" (*IST* 51(1):150–161, 2009,
[doi:10.1016/j.infsof.2008.02.003](https://doi.org/10.1016/j.infsof.2008.02.003); abstract) —
a controlled experiment in which a modified postmortem method with individual participation
and less structured diagrams identified root causes more effectively than the standard
fishbone method. The abstract read gives no n or effect size (see Dead ends). Read level:
abstract.

Andriyani, Hoda and Amor, "Reflection in agile retrospectives" (XP 2017, LNBIP 283:3–19,
[doi:10.1007/978-3-319-57633-6_1](https://doi.org/10.1007/978-3-319-57633-6_1); full text,
open access). Method: 16 interviews across four teams plus observation. Qualitative: three
levels of reflection (reporting and responding, relating and reasoning, reconstructing); one
team, "Team Neptune", did not reach the reconstructing level; a participant: "You could make
200 action points ... not a single one followed up"; the authors conclude that teams "may not
achieve all levels" of reflection simply by holding retrospectives. Read level: full text.

Dingsøyr, Mikalsen, Solem and Vestues, "Learning in the large — an exploratory study of
retrospectives in large-scale agile development" (XP 2018, LNBIP 314:191–198,
[doi:10.1007/978-3-319-91602-6_13](https://doi.org/10.1007/978-3-319-91602-6_13); full text,
open access). Data: retrospective reports from one large programme, 109 issues and 36 action
items. The authors state the evidence gap directly: "We do not know of studies investigating the
learning effect of retrospectives", and conclude the retrospectives studied "do not seem to
facilitate 'deep' learning (double loop)". Read level: full text.

Przybyłek, Albecka, Springer and Kowalski, "Game-based Sprint retrospectives: multiple action
research" (*Empirical Software Engineering* 2021,
[doi:10.1007/s10664-021-10043-z](https://doi.org/10.1007/s10664-021-10043-z); abstract) —
action research in six teams on games as retrospective formats; abstract only, no numbers
recorded.

The retrospective literature therefore contains process-improvement and engagement evidence,
one controlled experiment on root-cause method, and by its own authors' statement no
measurement of what participants learn. The corpus's treatment of pairing, mob programming,
inspection and review as the practices with transfer evidence is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model)
and is not repeated here.

## Argument, analogy or measurement: a ledger

| Claim | Where stated | Evidence type | Sample | Measured in software teams? |
| --- | --- | --- | --- | --- |
| Limiting WIP shortens lead time (Little's law) | Kanban Guide 2025; Middleton and Joyce 2012 | Argument by queueing theory; one case study | 1 team of 9 (Middleton) | Yes, before–after, one team |
| Kanban with WIP limit outperforms Scrum on lead time and productivity | Sjøberg et al. 2012 | Measured, no control | >12,000 work items, ~100 developers, one company | Yes, successive periods |
| Kanban improves communication, collaboration, learning | Ahmad 2013 (19 studies); Ahmad 2018 (23; 7 and 6 studies) ; dos Santos 2018 (20) | Practitioner-reported benefit counted across case studies | Mostly single-case; no controlled experiment | Reported, not measured |
| WIP control improves "collective focus, commitment, and collaboration" | Kanban Guide 2025 | Argument (uncited) | — | No |
| WIP limits avoid context switching that "drastically" reduces effectiveness | Kanban University guide | Argument (uncited) | — | Switching cost measured elsewhere: Tregubov 17% effort; Vasilescu GitHub |
| Small batches speed feedback | Reinertsen 2009 ch. 1; blog posts | Argument; course-survey figures of unstated n | — | No |
| Small batches predict IT performance | DORA 2016 | Survey PLS-SEM | >4,600 | Self-report; 2017 finds the reverse direction, reciprocal model adopted (3,200) |
| Small changes are reviewed more effectively | Baum et al. 2019 | Controlled experiment | n = 50 (46 professionals) | Yes: 59% vs 35% effectiveness; 76% vs 36% detection |
| Larger changes get fewer useful comments | Bosu et al. 2015 | Observational | ~1.5M comments, 5 projects | Yes, trend |
| Defect density falls above ~200 lines; >400 lines/hour is too fast | Cohen 2006 (SmartBear) | Vendor observational; assumes constant true density | 2,500 reviews, 50 developers | Yes, one site, vendor |
| 100 lines reasonable, 1,000 too large | Google Small CLs | Practice text | — | No |
| Minimise intermediate artifacts (inventory) | Poppendieck 2001 | Argument by manufacturing analogy | — | No |
| Five focusing steps; TOC "no reports of failures" | Goldratt Institute; Mabin and Balderstone 2003 | Method text; meta-analysis of >80 applications | Manufacturing | No |
| Stage gates with deliverables and criteria | Cooper 1990/2008; Griffin 1997 | Method text; adoption survey | PDMA firms | No (new-product management) |
| DoD creates shared understanding of "done" | Scrum Guide 2020; Kopczyńska 2022 | Practice text; survey | 137 | Perceived value 93%; "different understanding" in ≥70% of projects |
| Stand-up shares information and builds team awareness | Stray 2016, 2020; Middleton 2012 | Grounded theory; observation; testimonial | 12 teams/79 meetings; 15 teams/102 meetings | Yes: meeting content (34%/31%); duration 27→19 min |
| Stand-ups are valued | Stray 2017 | Survey | 221 | 44.7% positive, 36.6% negative |
| Retrospectives produce learning | Dingsøyr 2018; Andriyani 2017 | Authors state no learning study exists; qualitative | 109 issues/36 actions; 16 interviews | No |
| Modified root-cause method finds more causes | Bjørnson 2009 | Controlled experiment | Not readable | Yes (abstract) |

## Where each device sits in the lifecycle

Placed against the stages the corpus uses ([analysis.md](analysis.md#2-the-lifecycle-in-two-layers)),
as the sources themselves locate the device; the rightmost column is the evidence about
comprehension or knowledge sharing at that point, which in most cells is none.

| Stage | Device in the process literature | Source | What is measured there about understanding |
| --- | --- | --- | --- |
| Issue declared | Pull: an item is started only when a WIP slot is free; Definition of Workflow states the "started" point | Kanban Guide 2025 | Nothing; item age begins |
| Session begins / Work starts | WIP limit on started items; TOC "subordinate" to the constraint | Kanban Guide 2025; Goldratt Institute | Nothing; Kanban University's context-switching claim is uncited |
| Worktree prepared | Batch-size decision — how much one Issue carries | Reinertsen 2009; Google Small CLs | Nothing measured at this point |
| Commits and pushes | Batch size becomes change size | Google Small CLs ("100 lines ... reasonable") | None here; effect appears at review |
| Pull Request opened | Change size determines review effectiveness and comment usefulness; DoD items "code review" (15 of the items shared) and "documentation" (12) attach here | Baum 2019; Bosu 2015; Cohen 2006; Kopczyńska 2022 | Review effectiveness 59% vs 35%; detection 76% vs 36%; usefulness density falls with file count |
| Review / merge | Gate: DoD satisfied; stage gate "with teeth" | Scrum Guide 2020; Cooper 2008 | Perceived value only (93% at least valuable) |
| Daily, across stages | Daily stand-up: awareness of others' current activities | Stray 2016, 2020; Middleton 2012 | Meeting content shares; 34% on the three questions; juniors gain more |
| Per iteration | Retrospective: process reflection; DoD revision | Scrum Guide 2020; Andriyani 2017; Dingsøyr 2018 | No learning-effect study exists (Dingsøyr 2018) |
| Cleanup | Postmortem after project end | Dingsøyr 2005 | One in five projects reviewed; reports often unused |

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where the existing notes touch it |
| --- | --- | --- | --- |
| WIP limits are defined as a count constraint, justified by queueing theory named as analogy, with an uncited collaboration claim | [Kanban Guide 2025](https://kanbanguides.org/the-kanban-guide/2025.5/) | Practice text | No counterpart |
| Kanban WIP limit at one company halved lead time; productivity +21% PBIs, −11% bugs; no control | [Sjøberg et al. 2012](https://www.mn.uio.no/ifi/personer/vit/dagsj/sjoberg.johnsen.solberg.ieee.sw.pdf) | Measured, before–after | No counterpart |
| One team's WIP reduction cut lead time 37% and variance 47%; "accelerated learning" asserted through Little's law | [Middleton and Joyce 2012](https://doi.org/10.1109/tem.2010.2081675) | Measured plus qualitative | No counterpart |
| Kanban reviews: 19/23/20 primary studies, mostly single-case, no controlled experiment; learning and communication are reported benefits | [Ahmad et al. 2018](https://doi.org/10.1016/j.jss.2017.11.045); [dos Santos et al. 2018](https://doi.org/10.1186/s40411-018-0057-1) | Systematic review / mapping | No counterpart |
| Small changes reviewed at 59% vs 35% effectiveness; n = 50 | [Baum et al. 2019](https://doi.org/10.1007/s10664-018-9676-8) | Controlled experiment | Working-memory result only: [evidence-and-mechanisms.md](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding) |
| Useful-comment density falls with file count; ~1.5M comments | [Bosu et al. 2015](https://doi.org/10.1109/msr.2015.21) | Observational | No counterpart |
| Defect density falls above ~200 lines; 400 lines/hour ceiling; vendor study assuming constant density | [Cohen 2006](https://web.archive.org/web/20101009071211id_/http://smartbear.com:80/code-collaborator/docs/book/code-review-cisco-case-study.pdf) | Vendor observational | McIntosh's 200-lines-per-hour "hastily reviewed" metric: [track-measurement.md](track-measurement.md#proxies-and-telemetry) |
| Reviewer load doubles under agent throughput; PR size +154% | corpus sources | Measured | [track-hand-off-checks.md](track-hand-off-checks.md#evidence); [track-measurement.md](track-measurement.md#proxies-and-telemetry) |
| Small-batch argument rests on queueing analogy and unsized course surveys | [Reinertsen 2009 ch. 1](http://celeritaspublishing.com/wp-content/uploads/2013/07/ReinertsenFLOWChap1.pdf) | Argument | No counterpart |
| Small batches predict IT performance (2016); direction reversed and reciprocal model adopted (2017) | [DORA 2016](https://dora.dev/research/2016/2016-state-of-devops-report.pdf); [DORA 2017](https://dora.dev/research/2017/2017-state-of-devops-report.pdf) | Survey SEM | DORA's later instruments: [track-measurement.md](track-measurement.md#self-report-and-survey-instruments) |
| Cross-project interruptions cost 17% of effort; self-interruptions most disruptive | [Tregubov et al. 2017](https://doi.org/10.1145/3084100.3084116); [Shakeri Hossein Abad et al. 2018](https://arxiv.org/abs/1805.05508) | Measured | Resumption cost: [track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking) |
| Lean wastes observed at Pivotal include extraneous cognitive load and knowledge loss | [Sedano et al. 2017](https://doi.org/10.1109/icse.2017.20) | Qualitative (abstract) | No counterpart |
| TOC enters software as method text; meta-analysis found no failures | Goldratt Institute; [Mabin and Balderstone 2003](https://doi.org/10.1108/01443570310476636) | Method text; meta-analysis | No counterpart |
| Stage gates are decision points; "gates with teeth" | [Cooper 2008](https://doi.org/10.1111/j.1540-5885.2008.00296.x); [Griffin 1997](https://doi.org/10.1111/1540-5885.1460429) | Method text; survey | Gate vocabulary in AI-era tools: [track-hand-off-checks.md](track-hand-off-checks.md#gate-placement-and-enforcement) |
| DoD defined as a shared-understanding device; 93% value it; "different understanding" in ≥70% of projects | [Scrum Guide 2020](https://scrumguides.org/scrum-guide.html); [Kopczyńska et al. 2022](https://arxiv.org/abs/2208.04003) | Practice text; survey n = 137 | No counterpart |
| No source measures the comprehension effect of an approval gate | corpus | Gap | [synthesis.md](synthesis.md#gaps-every-pass-left), item 2 — unchanged |
| Stand-up transfers awareness; low knowledge redundancy makes members uninterested; manager departure cut meeting 27→19 min | [Stray et al. 2016](https://doi.org/10.1016/j.jss.2016.01.004) | Grounded theory plus measurement | Levesque non-convergence: [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research); newcomers: [Dagenais 2010](unfamiliar-code-and-shared-models.md#dagenais-ossher-bellamy-robillard-and-de-vries-2010--moving-into-a-new-software-project-landscape) |
| 34% of stand-up time on the three questions; juniors more positive | [Stray et al. 2020](https://arxiv.org/abs/1808.07650) | Observation, 102 meetings | No counterpart |
| 44.7% positive, 36.6% negative; positive group younger | [Stray et al. 2017](https://doi.org/10.1007/978-3-319-57633-6_20) | Survey n = 221 | No counterpart |
| Retrospectives: no learning-effect study exists; shallow reflection; action points not followed up | [Dingsøyr et al. 2018](https://doi.org/10.1007/978-3-319-91602-6_13); [Andriyani et al. 2017](https://doi.org/10.1007/978-3-319-57633-6_1) | Authors' statement; qualitative | No counterpart |
| Postmortems held for one in five projects; reports unused | [Dingsøyr 2005](https://doi.org/10.1016/j.infsof.2004.08.008) | Review (secondary figures) | No counterpart |
| Pairing, mob, inspection and review as the practices with transfer evidence | corpus sources | Measured | [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model) |

"No counterpart" means no note in this directory addresses the point; it is a statement about
the notes, not about the wider literature.

## Dead ends

- **Anderson 2010, *Kanban: Successful Evolutionary Change for Your Technology Business*;
  Poppendieck and Poppendieck 2003, *Lean Software Development*; Reinertsen 2009 beyond
  chapter 1; Goldratt's *The Goal* and *Critical Chain*.** archive.org lending copies returned
  401/403 on text access; Google Books API returned quota 0 (429). Documented from the guides,
  chapter 1, the Goldratt Institute paper and Ahmad 2018's restatement instead.
- **Cooper 1990, *Business Horizons*.** Paywalled at Elsevier; no repository copy found by
  OpenAlex (oa_status closed). Metadata only.
- **Ahmad, Markkula and Oivo 2013 (SEAA).** IEEE paywall; abstract via OpenAlex. Full text not
  reached; primary-study list taken from the 2018 mapping study instead.
- **Silva et al. 2017 (EASE) DoD systematic review.** ACM paywall; OpenAlex and Semantic
  Scholar carry only the first sentences of the abstract ("elided by the publisher"); Wayback
  has no capture of the ACM page. Counts (2,326 screened, 8 included, four DoD levels) are from
  Kopczyńska et al.'s restatement and a search-engine snippet — secondary.
- **Sedano, Ralph and Péraire 2017 (ICSE).** Closed at IEEE; OpenAlex finds no repository
  copy; Crossref and Wayback CDX found no preprint. Abstract only.
- **Bjørnson, Wang and Arisholm 2009.** Abstract read on a SINTEF publications page which now
  redirects to a not-found page; the ScienceDirect DOI landing page returns a bot-check
  redirect to curl; OpenAlex carries no abstract. No n or effect size recorded.
- **Mabin and Balderstone 2003; Cooper 2008; Griffin 1997; Cooper and Sommer 2016; Little
  1961.** Publisher pages (Emerald, Wiley, INFORMS) readable only as abstract or metadata via
  Crossref/OpenAlex.
- **Semantic Scholar API.** 429 rate limits and elided abstracts for IEEE, ACM and Elsevier
  items; replaced by OpenAlex abstract reconstruction and Crossref.
- **NVA (nva.sikt.no) file download for Stray 2016** returned "Missing Authentication
  Token"; the BIBSYS Brage PDF was recovered through the Wayback CDX index with the
  `?sequence=1` capture.
- **Direct downloads from Queen's University Belfast Pure, the Oulu repository, ZORA, and
  Microsoft Research** returned Cloudflare or HTML challenge pages to curl; each was read
  through a Wayback `id_` raw capture instead. reinertsenassociates.com's TLS certificate had
  expired and was fetched with certificate checking off.
- **A software-team measurement of the Theory of Constraints** (five focusing steps applied to a
  development team with before–after data) was not found in Crossref or OpenAlex searches;
  the TOC evidence located is manufacturing.
- **Any study measuring comprehension, retention or knowledge distribution before and after
  introducing a WIP limit or a batch-size rule** was not found. Searches on OpenAlex and
  Crossref for "work in progress limit" with "knowledge sharing", "comprehension" or
  "onboarding" returned the Kanban reviews above and nothing narrower.
- **The brief's pointer to an existing Kanban or WIP-limit mention in
  literature-addendum.md** did not resolve: `grep -n -i "kanban\|WIP"` over the directory finds
  no "kanban" and the only "WIP" hit is the word "Swipe" (literature-addendum.md, line 626).
  Recorded here as a dead end, not a correction, since no sentence in that note makes the
  claim.
- **VersionOne 2013 State of Agile survey** (85% stand-up adoption) was not fetched; the
  figure is as Stray et al. 2016 cite it.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Ahmad, M. O., Dennehy, D., Conboy, K., Oivo, M. (2018). Kanban in software engineering: A
  systematic mapping study. *Journal of Systems and Software* 137:96–113.
  doi:10.1016/j.jss.2017.11.045
- Ahmad, M. O., Markkula, J., Oivo, M. (2013). Kanban in software development: A systematic
  literature review. *39th Euromicro Conference on Software Engineering and Advanced
  Applications (SEAA)*. doi:10.1109/seaa.2013.28
- Ahmad, M. O., Kuvaja, P., Oivo, M., Markkula, J. (2016). Transition of Software Maintenance
  Teams from Scrum to Kanban. *HICSS 2016*, pp. 5427–5436. doi:10.1109/hicss.2016.670
- Andriyani, Y., Hoda, R., Amor, R. (2017). Reflection in agile retrospectives. *XP 2017*,
  LNBIP 283:3–19. doi:10.1007/978-3-319-57633-6_1
- Bartel, S., Bartel, A., Kanban University. The Official Guide to the Kanban Method.
  https://kanban.university/kanban-guide/
- Baum, T., Schneider, K., Bacchelli, A. (2019). Associating working memory capacity and code
  change ordering with code review performance. *Empirical Software Engineering*
  24(4):1762–1798. doi:10.1007/s10664-018-9676-8
- Bjørnson, F. O., Wang, A. I., Arisholm, E. (2009). Improving the effectiveness of root cause
  analysis in post mortem analysis: A controlled experiment. *Information and Software
  Technology* 51(1):150–161. doi:10.1016/j.infsof.2008.02.003
- Bosu, A., Greiler, M., Bird, C. (2015). Characteristics of useful code reviews: An empirical
  study at Microsoft. *MSR 2015*. doi:10.1109/msr.2015.21
- Cohen, J. (2006). Code Review at Cisco Systems. In *Best Kept Secrets of Peer Code Review*,
  SmartBear Software.
  https://web.archive.org/web/20101009071211id_/http://smartbear.com:80/code-collaborator/docs/book/code-review-cisco-case-study.pdf
- Coleman, J., Vacanti, D. (2025). The Kanban Guide (May 2025).
  https://kanbanguides.org/the-kanban-guide/2025.5/
- Cooper, R. G. (1990). Stage-gate systems: A new tool for managing new products. *Business
  Horizons* 33(3):44–54. doi:10.1016/0007-6813(90)90040-I
- Cooper, R. G. (2008). Perspective: The Stage-Gate idea-to-launch process — update, what's
  new, and NexGen systems. *Journal of Product Innovation Management* 25(3):213–232.
  doi:10.1111/j.1540-5885.2008.00296.x
- Cooper, R. G., Sommer, A. F. (2016). The Agile–Stage-Gate hybrid model. *Industrial
  Marketing Management* 59:167–180. doi:10.1016/j.indmarman.2016.10.006
- Dingsøyr, T. (2005). Postmortem reviews: Purpose and approaches in software engineering.
  *Information and Software Technology* 47(5):293–303. doi:10.1016/j.infsof.2004.08.008
- Dingsøyr, T., Mikalsen, M., Solem, A., Vestues, K. (2018). Learning in the large — an
  exploratory study of retrospectives in large-scale agile development. *XP 2018*, LNBIP
  314:191–198. doi:10.1007/978-3-319-91602-6_13
- DORA (2016). 2016 State of DevOps Report. Puppet and DORA.
  https://dora.dev/research/2016/2016-state-of-devops-report.pdf
- DORA (2017). 2017 State of DevOps Report. Puppet and DORA.
  https://dora.dev/research/2017/2017-state-of-devops-report.pdf
- DORA. Working in small batches. https://dora.dev/capabilities/working-in-small-batches/
- dos Santos, P. S. M., Beltrão, A. C., de Souza, B. P., Travassos, G. H. (2018). On the
  benefits and challenges of using kanban in software engineering: a structured synthesis
  study. *Journal of Software Engineering Research and Development* 6:13.
  doi:10.1186/s40411-018-0057-1
- Goldratt Institute (2009). The Theory of Constraints and its Thinking Processes.
  https://web.archive.org/web/20110813080003id_/http://www.goldratt.com:80/pdfs/toctpwp.pdf
- Google. Small CLs. *Google Engineering Practices*.
  https://google.github.io/eng-practices/review/developer/small-cls.html
- Griffin, A. (1997). PDMA research on new product development practices: Updating trends
  and benchmarking best practices. *Journal of Product Innovation Management* 14(6):429–458.
  doi:10.1111/1540-5885.1460429
- Kopczyńska, S., Ochodek, M., Piechowiak, J., Nawrocki, J. (2022). On the benefits and
  problems related to using Definition of Done — A survey study. *Journal of Systems and
  Software* 193:111479. doi:10.1016/j.jss.2022.111479; arXiv:2208.04003
- Little, J. D. C. (1961). A proof for the queuing formula: L = λW. *Operations Research*
  9(3):383–387. doi:10.1287/opre.9.3.383
- Little, J. D. C. (2011). Little's Law as viewed on its 50th anniversary. *Operations
  Research* 59(3):536–549. doi:10.1287/opre.1110.0940
- Mabin, V. J., Balderstone, S. J. (2003). The performance of the theory of constraints
  methodology. *International Journal of Operations & Production Management* 23(6):568–595.
  doi:10.1108/01443570310476636
- Middleton, P., Joyce, D. (2012). Lean Software Management: BBC Worldwide Case Study. *IEEE
  Transactions on Engineering Management* 59(1):20–32. doi:10.1109/tem.2010.2081675
- Poppendieck, M. (2001). Lean Programming. *Software Development Magazine*, May/June 2001.
  https://web.archive.org/web/20010408070557id_/http://www.poppendieck.com:80/lean.htm
- Przybyłek, A., Albecka, M., Springer, O., Kowalski, W. (2021). Game-based Sprint
  retrospectives: multiple action research. *Empirical Software Engineering* 27:1.
  doi:10.1007/s10664-021-10043-z
- Reinertsen, D. G. (2009). *The Principles of Product Development Flow: Second Generation
  Lean Product Development*, chapter 1. Celeritas Publishing.
  http://celeritaspublishing.com/wp-content/uploads/2013/07/ReinertsenFLOWChap1.pdf
- Reinertsen, D. G. (2013). The Four Impostors: Success, Failure, Knowledge Creation, and
  Learning.
  https://reinertsenassociates.com/the-four-impostors-success-failure-knowledge-creation-and-learning/
- Reinertsen, D. G. Is One-Piece Flow the Lower Limit for Product Developers?
  https://reinertsenassociates.com/is-one-piece-flow-the-lower-limit-for-product-developers/
- Schwaber, K., Sutherland, J. (2020). The Scrum Guide. https://scrumguides.org/scrum-guide.html
- Sedano, T., Ralph, P., Péraire, C. (2017). Software Development Waste. *ICSE 2017*.
  doi:10.1109/icse.2017.20
- Shakeri Hossein Abad, Z., Karras, O., Schneider, K., Barker, K., Bauer, M. (2018). Task
  interruption in software development projects: What makes some interruptions more
  disruptive than others? *EASE 2018*. doi:10.1145/3210459.3210471; arXiv:1805.05508
- Silva, A., Araújo, T., Nunes, J., Perkusich, M., Dilorenzo, E., Almeida, H., Perkusich, A.
  (2017). A systematic review on the use of Definition of Done on agile software development
  projects. *EASE 2017*. doi:10.1145/3084226.3084262
- Sjøberg, D. I. K., Johnsen, A., Solberg, J. (2012). Quantifying the Effect of Using Kanban
  versus Scrum: A Case Study. *IEEE Software* 29(5):47–53. doi:10.1109/ms.2012.110.
  https://www.mn.uio.no/ifi/personer/vit/dagsj/sjoberg.johnsen.solberg.ieee.sw.pdf
- Stray, V., Moe, N. B., Bergersen, G. R. (2017). Are daily stand-up meetings valuable? A
  survey of developers in software teams. *XP 2017*, LNBIP 283:274–281.
  doi:10.1007/978-3-319-57633-6_20
- Stray, V., Moe, N. B., Sjøberg, D. I. K. (2020). Daily Stand-Up Meetings: Start Breaking
  the Rules. *IEEE Software* 37(3):70–77. doi:10.1109/ms.2018.2875988; arXiv:1808.07650
- Stray, V., Sjøberg, D. I. K., Dybå, T. (2016). The daily stand-up meeting: A grounded theory
  study. *Journal of Systems and Software* 114:101–124. doi:10.1016/j.jss.2016.01.004
- Tregubov, A., Boehm, B., Rodchenko, N., Lane, J. A. (2017). Impact of task switching and
  work interruptions on software development processes. *ICSSP 2017*.
  doi:10.1145/3084100.3084116
- Vasilescu, B., Blincoe, K., Xuan, Q., Casalnuovo, C., Damian, D., Devanbu, P., Filkov, V.
  (2016). The sky is not the limit: Multitasking across GitHub projects. *ICSE 2016*.
  doi:10.1145/2884781.2884875
