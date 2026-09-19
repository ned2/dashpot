---
status: research
date: 2026-09-15
---

# Expert finding and transactive memory

Research date: 2026-09-15

This note documents what is known about how software teams find out who knows what, what
the transactive-memory (TMS) literature measured and how, whether the expertise-recommender
tools built for developers were ever evaluated on the people meant to use them, and what has
been measured about developers asking an AI assistant instead of a colleague. It is
documentary: it records what the sources found, with their evidence and limits, and maps each
finding to where the existing notes in this directory touch it. It does not evaluate fit for
Dashpot or any tool. Terminal citations are primary — the paper, the author's copy, the
vendor's own page — and every figure is reported as the source states it, with the sample and
the kind of evidence (measured, qualitative, testimonial, argument). Read level is marked per
source: "full text", "abstract", "metadata", "secondary"; anything recalled rather than read
is marked unverified. Where an earlier note already covers a source, this note links to it
rather than repeating it: Naur, DeChurch and Mesmer-Magnus, Ryan and O'Connor 2013 and the
Mockus and Herbsleb succession material are in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research);
the authorship-based expertise metrics (Expertise Browser as a metric, Fritz's
degree-of-knowledge, truck factor) are in
[track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure)
and [track-measurement.md](track-measurement.md#proxies-and-telemetry); the Lewis 2003 scale
items and the one TMS-instrument study of software teams using AI are in the sibling note
[team-level-measurement.md](team-level-measurement.md#team-cognition-instruments); the Google
effect is in
[adjacent-literatures.md](adjacent-literatures.md#memory-the-google-effect-and-its-replication);
harness transcript retention is in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance).
In this note "the who" means the person or thing a developer goes to for an answer, and the
agent-era question is what changes when that thing is an Agent Session transcript rather than
a person.

## Finding

Transactive memory was defined by Wegner as "a set of individual memory systems in combination
with the communication that takes place between individuals", in which "other people can be
locations of external storage for the individual" and knowledge responsibility is allocated
either by "personal expertise, or through the circumstantial knowledge responsibility" that
"the person who most recently encounters a domain of information" incurs ([Wegner 1987, full
text](https://web.archive.org/web/20041111092138id_/http://www.wjh.harvard.edu:80/~wegner/pdfs/Wegner%20Transactive%20Memory.pdf),
argument); the laboratory evidence is that natural couples agreed on who knew what in 5.52 of
7 categories against 4.04 for impromptu pairs (t(57) = 4.60, 59 couples) and that imposing an
expertise assignment on natural couples cut their recall from 31.40 to 23.75 items (t(55) =
2.90) (corrected 2026-09-15: in the Results of Wegner, Erber and Raymond 1991 the 31.40-versus-23.75 comparison is t(55) = 3.54, p < .001; t(55) = 2.90, p < .005 is natural couples with assignment (23.75) against impromptu couples with assignment (30.14)) ([Wegner, Erber and Raymond 1991, full text](https://web.archive.org/web/20051223234946id_/http://www.wjh.harvard.edu:80/~wegner/pdfs/Wegner,Erber,&Raymond1991.pdf),
measured). Two meta-analyses put the TMS–performance correlation at r = .44 [.36, .50] over
44 laboratory studies (103 effect sizes) but show it is r = .77 when the outcome is
self-reported and r = .38–.39 when observers or embedded metrics measure it ([Fausett et al.
2026, abstract](https://doi.org/10.1177/10464964261434540), measured), and find it moderated
by culture, volatility and diversity across 76 studies and 6,869 sampling units ([Bachrach et
al. 2019, abstract](https://doi.org/10.1037/apl0000329), measured). On software teams the
direct evidence is thin: 69 development teams where expertise coordination related to
performance "over and above" expertise presence and administrative coordination, with no
effect size in the abstract ([Faraj and Sproull 2000, abstract](https://doi.org/10.1287/mnsc.46.12.1554.12072),
measured); 139 ongoing teams in two Korean firms where IT support predicted TMS and TMS
predicted knowledge sharing and application ([Choi, Lee and Yoo 2010, abstract](https://doi.org/10.2307/25750708),
measured); 38 eight-week MBA virtual teams where early task communication built expertise
location and then mattered less ([Kanawattanachai and Yoo 2007, abstract](https://doi.org/10.2307/25148820),
measured); and the 48 Irish teams (qualified 2026-09-15: the corpus note records "48 teams from 46 Irish and UK SMEs, 181 people") already in the corpus where the Lewis scale alone explained
R² = .09 of team tacit knowledge ([unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research)).
How developers actually locate an expert was described from a five-month field study as
identification, selection and escalation ([McDonald and Ackerman 1998, full text](https://doi.org/10.1145/289444.289506),
qualitative), and the same site's "Line 10 Rule" — look in version control for "who last
modified the code and then approach that person for help", because "the person who last made
a change has the code 'freshest' in mind" and the rule is "good enough" ([McDonald and
Ackerman 2000, full text](https://web.archive.org/web/20030401080115id_/http://www.eecs.umich.edu:80/~ackerm/pub/00b30/cscw00.er.pdf),
qualitative) — is Wegner's circumstantial responsibility written into a work practice. The
recommenders built on that history were mostly evaluated offline: bug-triage precision of 57%
(Eclipse) and 64% (Firefox) ([Anvik, Hiew and Murphy 2006, abstract](https://doi.org/10.1145/1134285.1134336),
measured, no users), reviewer recommendation at 79% top-10 over 42,045 reviews ([Thongtanunam
et al. 2015, abstract](https://doi.org/10.1109/saner.2015.7081824), measured, no users); the
exceptions are the Expertise Browser's deployment logs from 75 hosts across four countries
with only qualitative feedback and the authors' own statement that their studies "do not
provide definitive evidence that EAs are a valid measure of expertise" ([Mockus and Herbsleb
2002, full text](http://herbsleb.org/web-pubs/pdfs/mockus-expertise-2002.pdf), measured usage,
qualitative feedback), IBM SmallBlue's 1,600 opt-ins and 150,000 indexed people in six months
where "searching for a person is not a daily activity" and "most users probably used the tool
just out of curiosity" ([Ackerman et al. 2013, full text](https://web.archive.org/web/20170814063447id_/http://web.eecs.umich.edu/~ackerm/pub/13a19/SharingKE_pre-press.pdf),
secondary for SmallBlue), and the one in-vivo evaluation of a deployed reviewer recommender
over 21,000 reviews at JetBrains, which found "no evidence" that recommendations influenced
reviewer choice because 63% of JetBrains and 92% of Microsoft respondents (n = 16 and 507)
already knew whom they would pick (qualified 2026-09-15: per section 6 of the preprint the 63% is JetBrains respondents answering "Always" (31% "Usually", one "Frequently"), while the 92% is Microsoft respondents answering "Always", "Usually" or "Frequently" combined; the two percentages are not the same threshold) ([Kovalenko et al. 2018, full text](https://doi.org/10.5281/zenodo.1404814),
measured and survey). The one measurement of colleague-asking under AI assistants is a survey
of 131 professional developers in which 66 (51%) "now ask GenAI for help with technical
aspects" instead of a teammate, 62% find it easier to ask GenAI "without fear of
embarrassment", 28% say interruptions from colleagues decreased against 32% who say they did
not, and preference splits by question: 71% would ask GenAI how to implement an algorithm but
65% would ask a colleague to clarify business logic and 50% would ask a teammate "how
something was done in the past" ([Salomon et al. 2026, full text](https://www.cs.ubc.ca/~rtholmes/papers/tse_2026_salomon.pdf),
survey, self-report); the public counterpart is a 25% fall in Stack Overflow activity within
six months of ChatGPT relative to Russian- and Chinese-language and mathematics forums
([del Rio-Chanona, Laurentsyeva and Wachs 2024, abstract](https://doi.org/10.1093/pnasnexus/pgae400),
measured difference-in-differences), and the Stack Exchange API on 2026-09-15 returns
1,854,952 surviving questions created in 2020 against 109,907 for 2025 (primary count,
deleted questions excluded) (qualified 2026-09-15: a re-query of the same API endpoint on the same day returned 1,855,058 and 109,776; the count is live and moves with deletions and undeletions). Nothing found measures a TMS whose "who" is an agent transcript:
the harness and vendor surfaces that make a transcript or repository-grounded assistant the
place to ask — a session picker that searches sessions by pull request URL or across "all
projects on this machine" and `claude -p --resume` to "ask an existing session a question"
([Claude Code docs, full text](https://code.claude.com/docs/en/sessions)), Copilot Chat that
"stores up to 100 of your most recent conversations" with messages "kept for 28 days"
([GitHub Docs, full text](https://docs.github.com/en/copilot/how-tos/chat-with-copilot/chat-in-github)),
and a vendor promising "Answers without interrupting teammates" ([Unblocked, vendor page](https://getunblocked.com/questions/),
testimonial) — are documented, while the TMS-with-AI research consists of two randomised
experiments on spillover from AI exposure into human–human shared language ([Riedl, Savage and
Zvelebilova, abstract](https://arxiv.org/abs/2407.17489)), a theorised "Transactive
Intelligent Memory System" from a health-behaviour chatbot ([Hopf et al. 2024, abstract](https://doi.org/10.1177/02683962241296883)),
a caregiver-network proposal with no results ([Kuznetsov, Chao and Dishop 2024, abstract](https://doi.org/10.1609/aaaiss.v4i1.31789)),
and the one 152-respondent TMS-instrument survey of software professionals using AI already in
the sibling note ([team-level-measurement.md](team-level-measurement.md#team-cognition-under-ai-the-one-tms-grounded-study-and-adjacent-work)).

## Transactive memory: the theory and the laboratory evidence

### Wegner 1987: the definition, and two ways responsibility is allocated

Daniel M. Wegner, "Transactive memory: A contemporary analysis of the group mind", in Mullen
and Goethals (eds), *Theories of Group Behavior*, Springer 1987, pp. 185–208
([doi:10.1007/978-1-4612-4634-3_9](https://doi.org/10.1007/978-1-4612-4634-3_9); full text
from the author's Harvard page in the Wayback Machine). Argument, illustrated with one couples
study; no new data.

- **Definition.** "A transactive memory system is a set of individual memory systems in
  combination with the communication that takes place between individuals." The mechanism is
  external storage: "Other people can be locations of external storage for the individual."
  What each person holds about the others is a directory of *labels* and *locations*, not the
  content; retrieval is "transactive" because it goes through the person who holds the item.
- **Two bases for who holds what.** Responsibility for a domain is assigned "either through
  personal expertise, or through the circumstantial knowledge responsibility" — and on the
  latter, "The person who most recently encounters a domain of information may also incur
  responsibility for it". Wegner adds that when neither expertise nor circumstantial
  responsibility is developed, "trouble may" follow in retrieval. This is the theoretical
  statement behind the "Line 10 Rule" recorded below: last-modifier-as-expert is
  circumstantial responsibility.
- **Differentiated versus integrated.** A group can hold the same items in many heads
  (integrated) or different items in different heads (differentiated); the differentiated
  structure gains capacity and loses redundancy.
- **On the communication channel.** Scaling the idea to an organisation, Wegner writes that
  "Unless all the members of the organization are connected with high-speed computer
  communications devices, however, the organization's encoding and retrieval processes will
  be sluggish indeed, resembling those of a brilliant slow person." This is the only passage
  in the chapter that anticipates technology as part of the system.
- **On dissolution.** "The loss of transactive memory feels like losing a part of one's own
  mind." The passage is about couples separating; it is the origin of the "loss of
  transactive memory" phrase that Storey's 2026 position paper reuses for teams
  ([track-measurement.md](track-measurement.md#position-papers-and-proposals)).

Evidence type: argument.

### Couples in the laboratory: Wegner, Erber and Raymond 1991; Hollingshead 1998

Wegner, Erber and Raymond, "Transactive memory in close relationships", *Journal of
Personality and Social Psychology* 61(6):923–929
([doi:10.1037/0022-3514.61.6.923](https://doi.org/10.1037/0022-3514.61.6.923); full text from
the author's page in the Wayback Machine). Laboratory experiment; 118 individuals in 59 dating
couples of at least three months, each pair tested either as the natural couple or re-paired
into an impromptu couple; half the pairs were given an explicit assignment of which member was
responsible for which categories, half were not.

- **Agreement on who knows what.** Natural couples agreed on which partner was the relative
  expert in 5.52 of 7 categories against 4.04 for impromptu pairs, t(57) = 4.60, p < .001.
- **Recall.** Without assignment, natural couples recalled 31.40 items against 27.64 for
  impromptu pairs, t(55) = 1.69, p < .05 one-tailed — the authors call this difference "not
  particularly robust". With an imposed assignment, natural couples fell to 23.75 while
  impromptu pairs rose to 30.14, t(55) = 2.90, p < .005; the interaction of relationship and
  assignment was F(1,55) = 10.00, p < .003. Impromptu pairs with and without assignment did
  not differ significantly (30.78 versus 25.43).
- **Reading.** An externally imposed directory helps strangers and hurts a pair that already
  has one; the existing tacit allocation is the thing being disrupted.

Evidence type: measured, laboratory, small n.

Hollingshead, "Retrieval processes in transactive memory systems", *JPSP* 74(3):659–671
([doi:10.1037/0022-3514.74.3.659](https://doi.org/10.1037/0022-3514.74.3.659); abstract only).
Dating couples working face-to-face outperformed strangers and outperformed couples working
through computer conferencing; the abstract attributes the gap to nonverbal and paralinguistic
cues that couples use to cue retrieval. Evidence type: measured, laboratory; n not in the
abstract.

### Training together: Liang, Moreland and Argote 1995 and its replication

Liang, Moreland and Argote, "Group versus individual training and group performance: The
mediating role of transactive memory", *Personality and Social Psychology Bulletin*
21(4):384–393 ([doi:10.1177/0146167295214009](https://doi.org/10.1177/0146167295214009);
abstract only). Three-person groups assembled transistor radios after being trained either
together or individually; group-trained groups recalled more of the procedure and made fewer
assembly errors, and the abstract states the effect operated "primarily by fostering the
development of transactive memory systems" as measured by observed specialisation,
coordination and trust. Evidence type: measured, laboratory; n not in the abstract.

Moreland and Myaskovsky, "Exploring the performance benefits of group training: Transactive
memory or improved communication?", *Organizational Behavior and Human Decision Processes*
82(1):117–133 ([doi:10.1006/obhd.2000.2891](https://doi.org/10.1006/obhd.2000.2891)).
Metadata only; no abstract was obtainable from Crossref, OpenAlex, Semantic Scholar or
PubMed. Secondary summaries in the corpus-adjacent reviews say it showed that giving
individually-trained groups information about each other's skills reproduced the group-training
benefit; unverified here.

## Measuring a transactive memory system

### The Lewis scale, and indicator versus structural measures

The fifteen items of the Lewis 2003 scale (specialization, credibility, coordination), its
three validation samples (124 laboratory teams, 64 MBA consulting teams, 27 teams from 11
technology companies) and its reliabilities are transcribed from the full text in the sibling
note [team-level-measurement.md](team-level-measurement.md#lewis-2003-the-transactive-memory-system-scale)
and are not repeated here. Only the abstract was reached from this note
([doi:10.1037/0021-9010.88.4.587](https://doi.org/10.1037/0021-9010.88.4.587)); the sibling
found a CiteSeerX copy in the Wayback Machine. Two things the sibling records matter for the
rest of this note: the scale is a *perception* measure answered by members and aggregated to
the team, and in the technology-company sample the specialization subscale "was not
significantly correlated with the performance variables".

Austin, "Transactive memory in organizational groups: The effects of content, consensus,
specialization, and accuracy on group performance", *Journal of Applied Psychology*
88(5):866–878 ([doi:10.1037/0021-9010.88.5.866](https://doi.org/10.1037/0021-9010.88.5.866);
abstract only). Studied "mature continuing groups" and operationalised TMS structurally as
knowledge stock plus specialization, consensus about who knows what, and the *accuracy* of
those beliefs; the composite related to goal attainment and external evaluations. Evidence
type: measured, field; n not in the abstract.

Kush and Argote, "Indicator vs. structural measure of transactive memory", INFORMS
Organization Science Winter Conference proposal, undated, four pages
([PDF](https://higherlogicdownload.s3.amazonaws.com/INFORMS/e2a17bc9-6cb2-4c0a-8ce8-03ff37e5bbb0/UploadedImages/OSWC/Kush%20%26%20Argote%20-%20Indicator%20vs%20Structural%20Measure%20of%20TMS%20-%20Proposal%20for%20OSWC.pdf);
full text; unpublished). 46 groups of four on a programming task and an innovation task;
Austin-style structural measures improved model fit over the Lewis indicator measure, and the
two were "reasonably correlated". Evidence type: measured, laboratory, unreviewed proposal.

Lewis and Herndon, "Transactive memory systems: Current issues and future research
directions", *Organization Science* 22(5):1254–1265
([doi:10.1287/orsc.1110.0647](https://doi.org/10.1287/orsc.1110.0647); abstract only). Argues
that the measures in use have drifted from the construct, that task type conditions what a
TMS does, and calls for "reconsidering the role of information technology in supporting
TMSs". Evidence type: argument.

Ren and Argote, "Transactive memory systems 1985–2010: An integrative framework of key
dimensions, antecedents, and consequences", *Academy of Management Annals* 5(1):189–229
([doi:10.5465/19416520.2011.590300](https://doi.org/10.5465/19416520.2011.590300); abstract
only). Reviews 76 papers, notes measurement inconsistency, and calls for research on TMS in
virtual teams and "at the organizational level facilitated with information technologies".
Evidence type: narrative review.

### The meta-analyses: an effect that depends on who measures the outcome

Bachrach, Lewis, Kim, Patel, Campion and Thatcher, "Transactive memory systems in context: A
meta-analytic examination of contextual factors in transactive memory systems development and
team performance", *Journal of Applied Psychology* 104(3):464–493
([doi:10.1037/apl0000329](https://doi.org/10.1037/apl0000329); abstract only). 76 studies,
6,869 "sampling units". The TMS–performance relationship is stronger under high power
distance and in-group collectivism; volatility, leadership and human capital relate positively
to TMS development; informational and gender diversity relate negatively. No pooled r in the
abstract. Evidence type: meta-analysis.

Fausett, Keebler, Lazzara, Gregory and Blickensderfer, "Measurement matters: A meta-analysis
of transactive memory systems and team performance in laboratory settings", *Small Group
Research* 2026 ([doi:10.1177/10464964261434540](https://doi.org/10.1177/10464964261434540);
erratum [doi:10.1177/10464964261462615](https://doi.org/10.1177/10464964261462615); abstract
from Crossref). 44 laboratory studies, 103 effect sizes; pooled r = .44, 95% CI [.36, .50];
when team performance was self-reported r = .77, when observer-rated r = .38, when taken
from embedded task metrics r = .39. Evidence type: meta-analysis. This is the number to hold
against any survey that measures both TMS and performance by asking the same people.

### Where the directory sits: Mell, van Knippenberg and van Ginkel 2014

Mell, van Knippenberg and van Ginkel, "The catalyst effect: The impact of transactive memory
system structure on team performance", *Academy of Management Journal* 57(4):1154–1173
([doi:10.5465/amj.2012.0589](https://doi.org/10.5465/amj.2012.0589); full text from the
Erasmus author manuscript). Laboratory; N = 112 three-person teams (372 Dutch students).
Manipulated whether metaknowledge about who knows what was *centralized* in one member or
*decentralized* across all three, crossed with how information was distributed. No main effect
of structure (F(1,108) = .13); an interaction with information distribution (F(1,108) = 4.48,
p < .05) such that centralized metaknowledge helped when information was distributed so that
the central member could act as a catalyst; centralized teams performed more retrieval acts
(F(1,55) = 6.49). Evidence type: measured, laboratory. The relevance here is that a single
member who knows who knows what — Mockus and Herbsleb's architect "clearinghouse"
([unfamiliar-code note](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss))
— is a structure with measured effects, not only a bottleneck.

## Transactive memory in software and virtual teams

- **Faraj and Sproull 2000, "Coordinating expertise in software development teams",
  *Management Science* 46(12):1554–1568**
  ([doi:10.1287/mnsc.46.12.1554.12072](https://doi.org/10.1287/mnsc.46.12.1554.12072);
  abstract only; INFORMS paywall). Cross-sectional field study of 69 software development
  teams; "expertise coordination" (knowing where expertise is located, where it is needed,
  and bringing it to bear) showed "a strong relationship with team performance ... over and
  above team input characteristics, presence of expertise, and administrative coordination".
  No coefficients in the abstract. Evidence type: measured, survey, cross-sectional. This is
  the most-cited software-specific TMS-family result and its size could not be read.
- **Ryan and O'Connor 2013** (48 teams, 181 people, Lewis TMS R² = .09 for team tacit
  knowledge, rising to .20 with quality of social interaction): in the
  [unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research).
- **Yoo and Kanawattanachai 2001, "Developments of transactive memory systems and collective
  mind in virtual teams", *International Journal of Organizational Analysis* 9(2):187–208**
  ([doi:10.1108/eb028933](https://doi.org/10.1108/eb028933); abstract only). 38 virtual teams
  of graduate management students at six universities in four countries over eight weeks;
  the effect of early communication volume on performance decreases as TMS and collective
  mind develop. Evidence type: measured, longitudinal, student teams.
- **Kanawattanachai and Yoo 2007, "The impact of knowledge coordination on virtual team
  performance over time", *MIS Quarterly* 31(4):783–808**
  ([doi:10.2307/25148820](https://doi.org/10.2307/25148820); abstract only). 38 MBA virtual
  teams, eight weeks: task-oriented communication forms expertise location and
  cognition-based trust early; later, task–knowledge coordination mediates the effect on
  performance and communication volume matters less. Evidence type: measured, longitudinal,
  student teams.
- **Choi, Lee and Yoo 2010, "The impact of information technology and transactive memory
  systems on knowledge sharing, application, and team performance: A field study", *MIS
  Quarterly* 34(4):855–870** ([doi:10.2307/25750708](https://doi.org/10.2307/25750708);
  abstract only). 139 ongoing teams, 743 individuals, two South Korean firms. IT support
  predicts TMS; TMS and IT predict knowledge sharing and application; the effect of sharing on
  performance is fully mediated by application. Evidence type: measured, survey, cross-sectional.
- **Oshri, van Fenema and Kotlarsky 2008, "Knowledge transfer in globally distributed teams:
  The role of transactive memory", *Information Systems Journal* 18(6):593–616**
  ([doi:10.1111/j.1365-2575.2007.00243.x](https://doi.org/10.1111/j.1365-2575.2007.00243.x);
  abstract only). Case study at Tata Consultancy Services; "directories" were maintained both
  codified (templates, standard documents) and personalized (teleconferences, site visits).
  Evidence type: qualitative case.
- **Mockus and Herbsleb 2002** on architects as "clearinghouses" for who-knows-what, the
  15-month learning curve and the satellite-site problem: in the
  [unfamiliar-code note](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss).
- **Metadata only** (title and venue confirmed; no abstract reached): Hsu, Shih, Chiang and
  Liu 2012, *International Journal of Project Management* 30(3):329–340
  ([doi:10.1016/j.ijproman.2011.08.003](https://doi.org/10.1016/j.ijproman.2011.08.003)),
  TMS and software project performance; Chen, Li, Clark and Dietrich 2013, *International
  Journal of Information Management* 33(3):553–563
  ([doi:10.1016/j.ijinfomgt.2013.01.008](https://doi.org/10.1016/j.ijinfomgt.2013.01.008));
  Lewis, Belliveau, Herndon and Keller 2007, *OBHDP* 103(2):159–178
  ([doi:10.1016/j.obhdp.2007.01.005](https://doi.org/10.1016/j.obhdp.2007.01.005)), on TMS
  and transfer to new tasks; Jackson and Klobas 2008, *Decision Support Systems* 44(2):409–424
  ([doi:10.1016/j.dss.2007.05.001](https://doi.org/10.1016/j.dss.2007.05.001)), TMS in
  software development.

Taken together: the software-team studies are surveys of perceived TMS with team-level n
between 38 and 139, mostly cross-sectional, and none reports an effect on a delivery metric
that was not itself self-reported. Fausett's moderator (self-report r = .77 versus embedded
metric r = .39) applies to all of them.

## How people find who knows what: the CSCW field studies

### McDonald and Ackerman 1998: identification, selection, escalation

McDonald and Ackerman, "Just talk to me: A field study of expertise location", *CSCW '98*
([doi:10.1145/289444.289506](https://doi.org/10.1145/289444.289506); full text from the
author's Michigan page, `eecs.umich.edu/~ackerm/pub/98b25/cscw98.expertise.pdf`, in the Wayback
Machine). Five-month field study at a medium-sized
medical software company ("MSC"); 37 formal and more than 50 informal interviews plus
observation. Expertise location decomposes into *identification* (who might know),
*selection* (which of them to ask, weighing load, approachability and past history) and
*escalation* (what to do when the first person cannot help). The paper's title is what
respondents did: ask. Evidence type: qualitative.

### McDonald and Ackerman 2000: the "Line 10 Rule"

McDonald and Ackerman, "Expertise Recommender: A flexible recommendation system and
architecture", *CSCW 2000* ([doi:10.1145/358916.358994](https://doi.org/10.1145/358916.358994);
full text from the same page in the Wayback Machine). The system encodes two heuristics
observed at MSC. The first, which "Developers called ... the 'Line 10 Rule'": "Given a
problem with a module a developer looks into the version control system to see who last
modified the code and then approaches that person for help. Developers say that this rule
works because the person who last made a change has the code 'freshest' in mind. The version
control system is not specifically designed to support this exact use. As a result, the rule
is not strictly followed, but most developers state that the heuristic is 'good enough' to
often get the help they need." The paper also records why the rule exists: "Developers at MSC
do not specialize in any part of the system" and turnover means "a developer being assigned
work in portions of the code where she has not worked before." The second heuristic mines
technical-support records for who has handled which customer problems. The paper states that
expertise-locating systems are "not designed to replace people who fill these key
organizational roles" and reports no user evaluation. Evidence type: qualitative (the rule);
system description (the tool).

### Ackerman, Dachtera, Pipek and Wulf 2013: what twenty years of expert finders found

Ackerman, Dachtera, Pipek and Wulf, "Sharing knowledge and expertise: The CSCW view of
knowledge management", *Computer Supported Cooperative Work* 22(4–6):531–573
([doi:10.1007/s10606-013-9192-8](https://doi.org/10.1007/s10606-013-9192-8); full text of the
pre-press copy in the Wayback Machine; the Springer page redirects to an identity provider).
Narrative review; the figures below are secondary through it.

- **Two generations.** Object-centric systems (repositories, Answer Garden) gave way to
  people-centric ones (expertise finders) because "the more difficult problem" was tacit
  knowledge held by people.
- **Accuracy has no ground truth.** "There is not any 'objective' truth and people's judgment
  on other's expertise" is the standard; Ackerman et al. 2002 found about 20 participants'
  pooled judgments as good as three "expertise concierges"; McDonald 2001 found participants'
  assessments "correct approximately 79% of the time (although the expertise concierges were
  better with 85%)".
- **Laboratory evaluations of Expertise Recommender** (McDonald 2001, 2003): users wanted
  ego-centred views of the social network around them rather than a global ranking.
- **Appropriation in the field.** Reichling and Wulf's Expert Finder at a national industry
  association was appropriated over months, with profiles read as job descriptions. IBM
  SmallBlue: "After six months, 1600 people had opted in and over 150,000 people were indexed
  in the system. In the interviews, most people stated that searching for a person is not a
  daily activity for them, and the search results were judged to be fairly accurate ... The
  log data revealed that while most users probably used the tool just out of curiosity, there
  were also some who used it again and again." The "social distance" display was judged useful
  for approaching strangers.
- **Selection from a list.** Shami et al. 2008 (below) found people prefer candidates with
  whom they share a social connection and that rank order drives choice; people two or three
  degrees away were more valuable than immediate contacts.
- **Old answers decay.** Lutters and Ackerman's Answer Garden follow-up found older records
  hard to recontextualise once their authors had "retired or moved on".

Evidence type: narrative review; the individual studies it summarises are qualitative or
small-n and are not independently read here.

### The developer-side information-need studies already in the corpus

Ko, DeLine and Venolia 2007 (coworkers as the most frequent source for several of the 21
information needs, and "what have my coworkers been doing" as a need in its own right) is in
[workspace-awareness-and-coordination.md](workspace-awareness-and-coordination.md#ko-deline-and-venolia-2007--information-needs-in-collocated-software-development-teams);
de Souza and Redmiles on newcomers inferring who the experts are from check-in emails is in
the [same note](workspace-awareness-and-coordination.md#de-souza-and-redmiles-2007-2011--the-awareness-network);
LaToza and Myers' finding that "ask an expert teammate" fails when the teammate has left, and
Maalej et al.'s 17 of 28 who prefer asking a colleague, are in the
[unfamiliar-code note](unfamiliar-code-and-shared-models.md#the-questions-comprehenders-ask);
Klein, Feltovich, Bradshaw and Woods on being "confused about who knows what" as a
common-ground breakdown is in
[handover-between-sessions-people-and-agents.md](handover-between-sessions-people-and-agents.md#klein-feltovich-bradshaw-and-woods-2005).

## Expertise recommenders: were they evaluated on the people meant to use them?

### Expertise Browser (Mockus and Herbsleb 2002)

Mockus and Herbsleb, "Expertise Browser: A quantitative approach to identifying expertise",
*ICSE 2002* ([doi:10.1145/581339.581401](https://doi.org/10.1145/581339.581401); full text
from the author's site). The metric ("experience atoms" from change history) and the authors'
own caution that their three validation studies "do not provide definitive evidence that EAs
are a valid measure of expertise" are in
[track-measurement.md](track-measurement.md#proxies-and-telemetry). What that note does not
carry is the human evaluation:

- **Motivation.** The tool was built as an alternative to "querying project architects",
  because at the studied site the architects were the "expertise experts" and the load on
  them was a problem, and because satellite sites could not walk down the hall.
- **Deployment.** Released to Project A in February 2000 and Project B in October 2000;
  usage logs from 94 hosts, 75 of them usable, across Germany, the UK, France and Ireland;
  the satellite sites were the most active users.
- **Evaluation on humans.** Qualitative feedback after training sessions — "Everyone
  indicated that the interface was fairly easy to understand" — and no measure of whether a
  question was answered faster, more often, or by a different person.

Evidence type: measured (usage logs), qualitative (feedback).

### Bug-triage and usage-expertise recommenders: offline precision

- Anvik, Hiew and Murphy, "Who should fix this bug?", *ICSE 2006*
  ([doi:10.1145/1134285.1134336](https://doi.org/10.1145/1134285.1134336); abstract only;
  ACM 403). Precision 57% on Eclipse and 64% on Firefox reports; "less positive" on gcc.
  Evaluated against historical assignments; no developers in the loop. Evidence type:
  measured, offline.
- Anvik and Murphy, "Reducing the effort of bug report triage: Recommenders for
  development-oriented decisions", *TOSEM* 20(3):1–35
  ([doi:10.1145/2000791.2000794](https://doi.org/10.1145/2000791.2000794); abstract only).
  Precision 70–98% over five open-source projects; no human evaluation stated. Evidence type:
  measured, offline.
- Minto and Murphy, "Recommending emergent teams", *MSR 2007*
  ([doi:10.1109/msr.2007.27](https://doi.org/10.1109/msr.2007.27); abstract only). Emergent
  Expertise Locator; higher precision and recall than the existing heuristic on historical
  data. Evidence type: measured, offline.
- Schuler and Zimmermann, "Mining usage expertise from version archives", *ICSM 2009*
  ([doi:10.1109/icsm.2009.5306386](https://doi.org/10.1109/icsm.2009.5306386); abstract only).
  Usage expertise (who *calls* a method) locates experts with accuracy comparable to
  implementation expertise on AspectJ and Eclipse; offline. The corpus cites the usage-expertise
  idea in [track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure).
- **Mozilla BugBug** (Castelluccio and Ledru, Mozilla Hacks, 2019-04-09; full text via the
  Wayback Machine of
  [hacks.mozilla.org](https://hacks.mozilla.org/2019/04/teaching-machines-to-triage-firefox-bugs/); the live page returned an HTML shell to a plain fetch).
  The deployed classifier assigns a *component*, not a person; at a 60% confidence threshold
  it reached more than 80% precision on December 2018–March 2019 validation data; deployed at
  the end of February 2019, about 350 bugs auto-triaged, with a median of two days (average
  nine, four without outliers) for a developer to act on an auto-triaged bug against about a
  week for manual assignment. Evidence type: measured, production, single project, vendor blog.

### Reviewer recommendation: offline, then in vivo

- Thongtanunam, Tantithamthavorn, Kula, Yoshida, Iida and Matsumoto, "Who should review my
  code?", *SANER 2015* ([doi:10.1109/saner.2015.7081824](https://doi.org/10.1109/saner.2015.7081824);
  abstract only). Across 42,045 reviews, reviews with a reviewer-assignment problem took 12
  days longer; RevFinder ranked a correct reviewer in the top 10 for 79% of reviews with median
  rank 4. Offline. Evidence type: measured, historical.
- Kovalenko, Tintarev, Pasynkov, Bird and Bacchelli, "Does reviewer recommendation help
  developers?", *IEEE Transactions on Software Engineering* (2018 preprint at
  [doi:10.5281/zenodo.1404814](https://doi.org/10.5281/zenodo.1404814); full text). The
  authors describe it as the first in-vivo evaluation. Over 21,000 code reviews at JetBrains
  with a deployed recommender in Upsource: "no evidence" that recommendations influenced
  reviewer choice (average MRR of the recommender about 0.64 regardless). Then four interviews
  and 16 survey responses at JetBrains (26% rate) and 507 valid responses at Microsoft (20%
  rate). At JetBrains 63% "Always" and 31% "Usually" know the reviewer before opening a review;
  at Microsoft 92% Always/Usually/Frequently. "In the survey at JetBrains, 69% of respondents
  reported that reviewer recommendation 'Never' helps them to find a reviewer. On the other
  hand, 19% of respondents reported that it 'Always' helped." "Most survey respondents (56% at
  Microsoft and 69% at JetBrains) find the recommendations more often relevant than not.
  However, reviewer recommendation features for reviewer selection were reported to be more
  often helpful than not by only 46% of respondents at Microsoft and by only 25% at
  JetBrains." The information needs respondents said they weigh when choosing: involvement,
  ownership and recent authorship of the changed code (82–91%), knowledge of dependent areas
  (79%), the candidate's current load only 32%; open answers named knowledge (about 30%),
  "none" (25%), seniority (23%) and being a stakeholder (22%). Evidence type: measured
  (deployment logs) and survey.

### Enterprise expert finders with users in the study

- Ehrlich and Shami, "Searching for expertise", *CHI 2008*
  ([doi:10.1145/1357054.1357224](https://doi.org/10.1145/1357054.1357224); abstract only). 75
  employees who were current users of an enterprise expertise locator; corporate directories
  and personal networks were the most-cited alternatives to the tool. Evidence type: survey.
- Shami, Ehrlich and Millen, "Pick me! Link selection in expertise search results", *CHI
  2008* ([doi:10.1145/1357054.1357223](https://doi.org/10.1145/1357054.1357223); abstract
  only). 67 employees in 21 countries; rank order and evidence of a social connection predict
  which result is selected. Evidence type: measured, user study.
- Balog, Fang, de Rijke, Serdyukov and Si, "Expertise retrieval", *Foundations and Trends in
  Information Retrieval* 6(2–3):127–256
  ([doi:10.1561/1500000024](https://doi.org/10.1561/1500000024); abstract only) and Yimam-Seid
  and Kobsa, "Expert-finding systems for organizations", *JOCEC* 13(1):1–24
  ([doi:10.1207/s15327744joce1301_1](https://doi.org/10.1207/s15327744joce1301_1); abstract
  only): the IR-side surveys, evaluated on TREC-style enterprise collections against relevance
  judgments rather than on askers.

### The evaluation ledger

| Tool or study | Population | What was measured on humans | Read level |
|---|---|---|---|
| Expertise Browser (2002) | 75 usable hosts, four countries | Usage logs; qualitative feedback after training | full text |
| Expertise Recommender (2000) | MSC developers | None in the paper; later lab studies (McDonald 2001, 2003) secondary via Ackerman 2013 | full text / secondary |
| SmallBlue (IBM) | 1,600 opt-ins, 150,000 indexed | Interviews and logs: "not a daily activity", "out of curiosity" | secondary |
| Ehrlich and Shami 2008; Shami et al. 2008 | 75; 67 employees | Survey; selection behaviour from a result list | abstract |
| Anvik 2006, 2011; Minto 2007; Schuler 2009 | Historical bug and change data | None | abstract |
| BugBug (2019) | One project, ~350 bugs | Time-to-first-action in production | full text (blog) |
| RevFinder (2015) | 42,045 historical reviews | None | abstract |
| Kovalenko et al. (2018) | 21,000 reviews; 16 + 507 respondents | Influence on choice (none found); perceived helpfulness | full text |

No study found measures whether an expertise recommender changed how quickly a question was
answered, whether it changed who was asked, or whether it changed a TMS measure on the team
that used it.

## The agent era

### Asking the AI instead of a colleague: what has been measured

- **Salomon, Koshchenko, Sergeyuk, Holmes, Murphy and Fritz 2026, "From disruptions to
  discussions: How GenAI is shaping human interactions in software development", *IEEE
  Transactions on Software Engineering* 52(7):2095–2110**
  ([doi:10.1109/TSE.2026.3655626](https://doi.org/10.1109/TSE.2026.3655626); full text from
  the [UBC author copy](https://www.cs.ubc.ca/~rtholmes/papers/tse_2026_salomon.pdf); dataset
  at [Zenodo 18100060](https://zenodo.org/records/18100060)). Two phases. Phase 1: 30
  industrial developers over 5–12 days each, 627 experience-sampling and 207 end-of-day
  responses, 22 interviewed. Phase 2: survey of 131 professional developers. The
  colleague-asking results, all from phase 2 and all self-report:
  - "Half of the developers (66 of 131, 51%) agreed or strongly agreed that they now ask
    GenAI for help with technical aspects" instead of a teammate; "62% also reported that it
    was easier to ask GenAI questions without fear of embarrassment."
  - "When asked whether overall interruptions from colleagues had decreased, 37 of 131 (28%)
    agreed or strongly agreed, 42 of 131 (32%) disagreed or strongly disagreed, and the
    largest group 52 of 131 (40%) remained neutral." Exploratory ordinal regression: team
    size, months of GenAI use, frequency and experience did not predict perceived reductions,
    but "developers in teams where GenAI was fully integrated into workflows were
    significantly more likely to report fewer interruptions than developers in other teams
    (p = .03)." 59% reported faster task completion.
  - Who-to-ask scenarios: "93 of 131 (71%) would consult GenAI when unsure how to implement
    an algorithm, 78 of 131 (60%) when decomposing a task into subtasks, and 77 of 131 (59%)
    when brainstorming implementation options. In contrast, colleagues were preferred for more
    socially and contextually grounded tasks: 66 of 131 (50%) would ask a teammate how
    something was done in the past, and 85 of 131 (65%) would consult a colleague to clarify
    business logic or requirements." Validating a solution before implementing: 47% GenAI, 40%
    colleague. The authors read this as "a division of labor".
  - "Approximately 52 of 131 (40%) of developers reported that they now collaborate more
    intentionally", and "96 of 131 (73%) of survey respondents emphasized that human
    collaboration continues to provide valuable alternative perspectives that GenAI cannot."
  - Phase-1 interview quote: "some people won't disturb for questions, that they can have
    the answer" from GenAI. Evidence type: measured (experience sampling), survey, qualitative;
    self-report throughout; cross-sectional.
- **Al Haque, Brown, LaToza and Johnson, "The evolution of information seeking in software
  development: Understanding the role and impact of AI assistants"** ([arXiv:2408.04032](https://arxiv.org/abs/2408.04032), FSE Companion 2025
  HumanAISE workshop; abstract and HTML). Survey n = 128 and 17 interviews; one interviewee
  (P13): "before going to my colleague or mentors for help, [I've been] using this [AI tool]";
  Stack Overflow was the most-cited non-AI resource. Evidence type: qualitative, survey.
- **Monteiro Ribeiro, Gama and Jackson, "A preliminary study on the impact of AI in the
  creativity and collaboration in software teams"**
  ([arXiv:2607.16744](https://arxiv.org/abs/2607.16744), SBES 2026; abstract and HTML). 13
  professionals at four companies; "developers increasingly consult AI instead of colleagues,
  weakening peer learning and mentoring"; P8: "Instead of asking my colleagues for advice, I
  end up asking the AI"; the authors describe a triadic developer–AI–colleague pattern.
  Evidence type: qualitative, small n.
- **Xiao, Hu, Whiting, Karunakaran, Shen and Cao, "Beyond the personal assistant: How
  expectations for enterprise AI in teamwork diverged as generative AI took shape,
  2023–2025"** ([arXiv:2509.10956](https://arxiv.org/abs/2509.10956); abstract only). 15
  practitioners interviewed in 2023, 10 re-interviewed in 2025; team-focused AI support was
  expected in 2023 and only personal assistants had arrived by 2025. Evidence type:
  qualitative, longitudinal.
- **Vella and Blincoe, "The impact of AI coding assistants on software engineering: A
  longitudinal study"** ([arXiv:2605.23135](https://arxiv.org/abs/2605.23135); abstract
  only). Matched samples of 158/101/95 developers; 82% report less time writing code;
  developer experience "worsened" rose from 14% to 27%. Nothing on colleague-asking in the
  abstract. Evidence type: survey.
- **Huang, Reyna, Lerner, Xia and Hempel, "Professional software developers don't vibe, they
  control: AI agent use for coding in 2025"** ([arXiv:2512.14012](https://arxiv.org/abs/2512.14012); abstract only).
  N = 13 observations and N = 99 survey on AI-assisted workflows; no colleague-asking figure
  in the abstract.
- **Annunziata, Choudhuri, Sarma, Catolino and Ferrucci 2026, "When AI joins the team!"**
  ([arXiv:2608.03462](https://arxiv.org/abs/2608.03462); abstract here; full text and the
  coefficients in the sibling
  [team-level-measurement.md](team-level-measurement.md#team-cognition-under-ai-the-one-tms-grounded-study-and-adjacent-work)).
  152 software professionals using AI tools, PLS-SEM on TMS-derived Human–AI and Human–Human
  specialization and coordination constructs; "In specialization work, AI is associated with
  higher knowledge-sharing peer interaction ... In coordination work, AI is directly
  associated with higher communication quality, complementing rather than replacing human
  interaction." Cross-sectional, individual-level self-report. This is the only study found
  that applies a TMS instrument to software teams using AI, and its direction (more
  human–human knowledge sharing with AI specialization awareness) runs against the
  Salomon/Monteiro Ribeiro direction (less asking of colleagues); the two measure different things
  (frequency of knowledge-sharing interaction versus whom one asks first).

### The public counterpart: question-asking on Stack Overflow

- **del Rio-Chanona, Laurentsyeva and Wachs 2024, "Large language models reduce public
  knowledge sharing on online Q&A platforms", *PNAS Nexus* 3(9)**
  ([doi:10.1093/pnasnexus/pgae400](https://doi.org/10.1093/pnasnexus/pgae400); abstract from
  Crossref; earlier version "Are large language models a threat to digital public goods?",
  [arXiv:2307.07367](https://arxiv.org/abs/2307.07367), which estimated a 16% fall in weekly
  posts). Difference-in-differences: a 25% decrease in Stack
  Overflow activity within six months of ChatGPT's release relative to Russian- and
  Chinese-language counterparts and mathematics forums, which the authors call a "lower
  bound"; no change in post quality; the decline spans all experience levels. Evidence type:
  measured, quasi-experimental.
- **Burtch, Lee and Chen 2024, "The consequences of generative AI for online knowledge
  communities", *Scientific Reports* 14**
  ([doi:10.1038/s41598-024-61221-0](https://doi.org/10.1038/s41598-024-61221-0); abstract
  only). October 2021 to March 2023: Stack Overflow visits and question volumes declined
  while Reddit developer communities did not; the decline was concentrated among newer users.
  Evidence type: measured, quasi-experimental.
- **Kabir, Udo-Imeh, Kou and Zhang, "Is Stack Overflow obsolete?"**
  ([arXiv:2308.02312](https://arxiv.org/abs/2308.02312), CHI 2024; abstract only). 517 Stack
  Overflow questions; 52% of ChatGPT answers contained incorrect information and 77% were
  verbose; users still preferred the ChatGPT answer 35% of the time and overlooked the
  misinformation 39% of the time. Evidence type: measured, offline plus user study.
- **Primary count.** The Stack Exchange API
  (`https://api.stackexchange.com/2.3/questions?fromdate=…&todate=…&site=stackoverflow&filter=total`,
  queried 2026-09-15, counting only questions that still exist — deleted questions are
  excluded, so earlier years are undercounted relative to what was asked): 2019 1,755,607;
  2020 1,854,952; 2021 1,534,749; 2022 1,335,589; 2023 788,282; 2024 398,628; 2025 109,907;
  2026 January–August 18,817 (qualified 2026-09-15: a re-query on the same day returned 1,855,058 for 2020 and 109,776 for 2025; the live count moves with deletions and undeletions). Evidence type: measured, primary, not corrected for deletion.

None of the Stack Overflow studies observes the workplace; they measure the public place
developers asked strangers. Whether the questions moved to an assistant, to colleagues, or were
not asked is not identified by any of them.

### The "who" as a transcript or a repository-grounded assistant

The surfaces that make an agent, or the record of one, the place to ask are documented by
their makers; no independent measurement of their use as expertise location was found.

- **Claude Code sessions** ([docs, full text](https://code.claude.com/docs/en/sessions)).
  The session picker's search mode: "`/` or any printable character ... Enter search mode
  and filter sessions. Paste a GitHub, GitHub Enterprise, GitLab, or Bitbucket pull or merge
  request URL to find the session that created it"; `Ctrl+A` to "Show sessions from all
  projects on this machine", `Ctrl+W` for all worktrees of the repository; `claude --from-pr
  <number>` "Opens the session picker filtered to sessions linked to that pull request". Each
  row "shows the session name if you set one, otherwise the AI-generated session title,
  conversation summary, or first prompt". Non-interactively: "Ask an existing session a
  question: pass a session ID to `claude -p --resume` to send a follow-up prompt, such as a
  summary request, and capture the structured response." Since v2.1.223 `claude --resume
  <session-id>` searches "every other project on this machine". All of this is per machine
  and per user: the directory of Agent Sessions is the developer's own, and the retention
  limit is the 30-day `cleanupPeriodDays` recorded in
  [track-rationale-as-artifact.md](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance).
  Evidence type: vendor documentation.
- **GitHub Copilot Chat in GitHub** ([docs, full text](https://docs.github.com/en/copilot/how-tos/chat-with-copilot/chat-in-github);
  [exploring a codebase](https://docs.github.com/en/copilot/tutorials/explore-a-codebase)).
  Questions can be asked from a repository page and are grounded in that repository's files;
  a conversation can continue alongside an agent session; "Copilot Chat stores up to 100 of
  your most recent conversations. Messages within each conversation are kept for 28 days
  before being permanently deleted." Evidence type: vendor documentation.
- **Unblocked** ([vendor pages](https://getunblocked.com/questions/)). Positioned explicitly
  against asking a person: "Answers without interrupting teammates"; "Free up senior
  engineers"; "Unblocked makes your team's technical knowledge accessible to everyone so
  senior engineers aren't answering the same questions all day"; example prompt "Who do I
  talk to about user metrics?" — an expertise-location query answered by an assistant. The
  performance figures on the page ("48%" fewer tokens, "2 hours and 5 minutes" saved) are a
  vendor's single-task comparison. Evidence type: testimonial.
- **DeepWiki and Sourcegraph Cody**, where the answer to a question about the code is a chat
  turn rather than a person, are in
  [track-explorable-maps.md](track-explorable-maps.md#agent-era-maps-and-wikis) and
  [track-explorable-maps.md](track-explorable-maps.md#code-navigation-platforms).

Three things follow from the sources rather than from this note's judgment. First, the Line 10
Rule's premise — the last modifier has the code "freshest" in mind — has, when the last
modifier is an Agent Run, no person to approach; the transcript is the only holder of that
circumstantial responsibility, and the harness surfaces above are what let a developer find it
(by Pull Request URL, by branch, by Worktree), on that developer's machine, within the
retention window. Second, Wegner's directory is of *labels and locations*, and the session
picker row (name, AI-generated title, summary, first prompt) is exactly a label for a location.
Third, the corpus already records that "nothing found measures whether shared transcripts are
later read"
([track-rationale-as-artifact.md](track-rationale-as-artifact.md#research-on-transcripts-and-prompts-as-documentation));
this pass found nothing to change that.

### Transactive memory research with an AI in the system

- **Riedl, Savage and Zvelebilova, "Cognitive spillover in human-AI teams"**
  ([arXiv:2407.17489](https://arxiv.org/abs/2407.17489), journal reference *ACM TOCHI* 2026;
  abstract only). Two randomised experiments: exposure to an AI teammate spills over into
  human–human interaction — shared language, attention, shared mental models and cohesion
  among the humans. Not a software task; n not in the abstract. Evidence type: measured,
  experimental.
- **Hopf, Nahr, Staake and Lehner 2024, "The group mind of hybrid teams with humans and
  intelligent agents in knowledge-intense work", *Journal of Information Technology*
  40(1):9–34** ([doi:10.1177/02683962241296883](https://doi.org/10.1177/02683962241296883);
  abstract from Crossref; Sage PDF blocked). Abductive study of a health-behaviour chatbot
  and its users; theorises a "Transactive Intelligent Memory System (TIMS)"; "hybrid teams of
  humans and IAs can realize joint systems of transactive memory"; whether people treat the
  agent "merely as external memory aids or as part of their teams' transactive memory is
  moderated by the tasks' complexity and knowledge intensity, as well as the IA's ability to
  complete the task". Evidence type: qualitative, theory-building, non-software.
- **Kuznetsov, Chao and Dishop 2024, "Transactive memory in caregiver networks using
  artificial intelligence"**, AAAI Spring Symposium
  ([doi:10.1609/aaaiss.v4i1.31789](https://doi.org/10.1609/aaaiss.v4i1.31789); abstract
  only). A proposal for an AI that holds the directory for a caregiver network; no results.
  Evidence type: proposal.
- **Peltokorpi and Hood, "Communication in theory and research on transactive memory systems",
  *Topics in Cognitive Science* 11(4):644–667**
  ([doi:10.1111/tops.12359](https://doi.org/10.1111/tops.12359); abstract only). Review of
  how communication is (under-)theorised in TMS work; relevant because a transcript is the
  communication made durable. Evidence type: narrative review.
- **Sparrow, Liu and Wegner 2011** on remembering where rather than what when a search
  engine is available, and its replication record, are in
  [adjacent-literatures.md](adjacent-literatures.md#memory-the-google-effect-and-its-replication);
  the Wegner of that paper is the Wegner of 1987, and "locations of external storage" is the
  same construct with a computer in the location slot.
- **Dell'Acqua et al.'s "cybernetic teammate"** field experiment (776 professionals) on AI
  substituting for a human teammate outside code is in
  [automation-as-a-team-player.md](automation-as-a-team-player.md#ai-agents-as-teammates-in-field-experiments-outside-code).

Gap 9 of the synthesis — "No source addresses code whose only author was never a person who
could be asked" ([synthesis.md](synthesis.md#gaps-every-pass-left)) — remains open after this
pass: the closest sources are Salomon's division-of-labour scenarios (which still assume a
teammate exists to be asked about "how something was done in the past") and Hopf's TIMS
theorising, neither of which observes a codebase.

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where the existing notes touch it |
|---|---|---|---|
| TMS is a directory of labels and locations; responsibility is allocated by expertise or by circumstantial (most-recent-encounter) responsibility | Wegner 1987 | Argument | [unfamiliar-code note, team cognition](unfamiliar-code-and-shared-models.md#team-cognition-research) names transactive memory as the compilational construct; the circumstantial basis has no counterpart |
| Imposed expertise assignment cuts natural couples' recall (31.40 → 23.75) and helps strangers | Wegner, Erber and Raymond 1991 | Measured, lab, 59 couples | No counterpart |
| Face-to-face couples outperform couples via computer conferencing at retrieval | Hollingshead 1998 | Measured, lab | [workspace-awareness note, Slack era](workspace-awareness-and-coordination.md#slack-era-20162025-where-knowledge-goes-to-die-and-the-trackers-counter-positioning) on channel effects, without the TMS framing |
| Group training improves recall and quality via TMS | Liang, Moreland and Argote 1995 | Measured, lab | [unfamiliar-code note, practices](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model) (pair, mob) without the TMS mechanism |
| Lewis scale: perception measure; specialization subscale uncorrelated with performance in technology teams | Lewis 2003 (via sibling) | Scale development, 3 samples | [team-level-measurement.md](team-level-measurement.md#lewis-2003-the-transactive-memory-system-scale) |
| TMS–performance r = .44 in labs; r = .77 self-report vs .38–.39 observed | Fausett et al. 2026 | Meta-analysis, 44 studies | [unfamiliar-code note](unfamiliar-code-and-shared-models.md#team-cognition-research) reports Ryan and O'Connor's self-report R² without this moderator; [team-level-measurement.md](team-level-measurement.md#the-level-of-analysis-ledger) on levels |
| TMS–performance moderated by culture, volatility, diversity | Bachrach et al. 2019 | Meta-analysis, 76 studies | No counterpart |
| Centralized metaknowledge helps only when information is distributed for a catalyst | Mell et al. 2014 | Measured, lab, 112 teams | [unfamiliar-code note, footprint](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss) (architects as clearinghouses) |
| Expertise coordination relates to software-team performance over and above expertise presence | Faraj and Sproull 2000 | Measured, 69 teams, cross-sectional | No counterpart |
| IT support → TMS → knowledge application → performance in 139 field teams | Choi, Lee and Yoo 2010 | Measured, survey | No counterpart |
| Early task communication builds expertise location in virtual teams, then matters less | Kanawattanachai and Yoo 2007; Yoo and Kanawattanachai 2001 | Measured, 38 student teams | [handover note](handover-between-sessions-people-and-agents.md#klein-feltovich-bradshaw-and-woods-2005) on common ground, without the time course |
| Expertise location = identification, selection, escalation | McDonald and Ackerman 1998 | Qualitative, 5-month field study | [unfamiliar-code note, questions](unfamiliar-code-and-shared-models.md#the-questions-comprehenders-ask) (asking a colleague as the preferred strategy) |
| "Line 10 Rule": ask whoever last modified the code; "good enough" | McDonald and Ackerman 2000 | Qualitative | [track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure) records authorship-based location as a metric, not as the practice it automates |
| Expert-finder accuracy has no objective truth; concierges 85% vs participants 79% | Ackerman et al. 2013 (secondary) | Narrative review | No counterpart |
| Expertise Browser was deployed to 75 hosts in four countries with qualitative feedback only | Mockus and Herbsleb 2002 | Measured usage, qualitative | [track-measurement.md](track-measurement.md#proxies-and-telemetry) carries the metric caveat, not the deployment |
| SmallBlue: "searching for a person is not a daily activity"; use "out of curiosity" | Ackerman et al. 2013 (secondary) | Interviews and logs | No counterpart |
| Bug-triage and reviewer recommenders evaluated offline (57–98% precision; 79% top-10) | Anvik 2006, 2011; Thongtanunam 2015 | Measured, historical | No counterpart |
| In-vivo: recommender did not influence reviewer choice; 63–92% already knew whom to ask | Kovalenko et al. 2018 | Measured, 21,000 reviews; 523 respondents | [unfamiliar-code note, practices](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model) on review as transfer, not on reviewer choice |
| BugBug: component assignment cut median time-to-action from ~a week to 2 days | Mozilla Hacks 2019 | Measured, production, one project | No counterpart |
| 51% now ask GenAI instead of a teammate; 62% less embarrassment; interruptions 28% down / 32% not | Salomon et al. 2026 | Survey, 131; self-report | [literature-addendum, target 1](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026) (Anthropic N = 132 survey) is the nearest; no counterpart on colleague-asking |
| Division of labour: GenAI for algorithms (71%), colleague for business logic (65%) and "how something was done in the past" (50%) | Salomon et al. 2026 | Survey, 131 | [unfamiliar-code note, questions](unfamiliar-code-and-shared-models.md#the-questions-comprehenders-ask) (rationale and history questions) |
| "Before going to my colleague ... using this AI tool"; "instead of asking my colleagues ... I end up asking the AI" | Al Haque et al. 2024; Monteiro Ribeiro et al. 2026 | Qualitative, 17 and 13 interviews | No counterpart |
| AI specialization awareness associated with more human–human knowledge sharing | Annunziata et al. 2026 | Survey, 152, PLS-SEM | [team-level-measurement.md](team-level-measurement.md#team-cognition-under-ai-the-one-tms-grounded-study-and-adjacent-work) |
| Stack Overflow activity down 25% within six months of ChatGPT (DiD); decline concentrated in newer users | del Rio-Chanona et al. 2024; Burtch et al. 2024 | Measured, quasi-experimental | [track-measurement.md, self-report](track-measurement.md#self-report-and-survey-instruments) (Stack Overflow survey) only |
| Surviving Stack Overflow questions: 1.85M (2020) → 110K (2025) | Stack Exchange API, 2026-09-15 | Measured, primary, deletion-biased | No counterpart |
| Session picker searches by PR URL, branch, worktree, all projects on this machine; `claude -p --resume` to "ask an existing session" | Claude Code docs | Vendor documentation | [track-rationale note, retention](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance) (30-day retention; session logs), not the search surface |
| Copilot Chat: 100 conversations, 28-day message retention; repository-grounded questions | GitHub Docs | Vendor documentation | [track-rationale note, retention](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance) (Copilot session logs) |
| "Answers without interrupting teammates"; "Who do I talk to about user metrics?" | Unblocked | Testimonial | [landscape-sweep, cluster 4](landscape-sweep.md#cluster-4--explorable-maps-and-explanation-on-demand) (explanation on demand) without the anti-interruption positioning |
| AI exposure spills over into human–human shared language and mental models | Riedl et al. (TOCHI 2026) | Measured, 2 experiments | [automation-as-a-team-player, field experiments](automation-as-a-team-player.md#ai-agents-as-teammates-in-field-experiments-outside-code) |
| TIMS: an agent can be a member of a TMS, moderated by task complexity and the agent's ability | Hopf et al. 2024 | Qualitative, theory-building | [team-level-measurement.md](team-level-measurement.md#team-cognition-under-ai-the-one-tms-grounded-study-and-adjacent-work) |
| No source measures a TMS whose "who" is an Agent Session transcript | This pass (absence) | — | [synthesis gap 9](synthesis.md#gaps-every-pass-left); [track-rationale note](track-rationale-as-artifact.md#research-on-transcripts-and-prompts-as-documentation) |

"No counterpart" means no note in this directory addresses the point; it is a statement about the notes, not about the wider literature.

## Dead ends

- Lewis 2003 full text: APA page paywalled; Academia.edu and ResearchGate copies behind
  Cloudflare "Just a moment" pages; the Carlson School PDF likewise. The sibling
  team-level-measurement note reached a CiteSeerX copy via the Wayback Machine; this note used
  the abstract and links to the sibling.
- Faraj and Sproull 2000: INFORMS paywall; abstract only, so no coefficient is reported here.
- Abstract only, publisher paywalls: Ren and Argote 2011, Lewis and Herndon 2011, Bachrach et
  al. 2019, Austin 2003, Liang et al. 1995, Hollingshead 1998, Kanawattanachai and Yoo 2007,
  Choi et al. 2010, Yoo and Kanawattanachai 2001, Oshri et al. 2008, Fausett et al. 2026.
- Metadata only (no abstract in Crossref, OpenAlex or Semantic Scholar; PubMed title search
  returned unrelated records and author search returned nothing): Moreland and Myaskovsky
  2000, Hsu et al. 2012, Chen et al. 2013, Lewis et al. 2007, Jackson and Klobas 2008, Nevo
  and Wand 2005 (*DSS* 39(4):549–562), Wegner 1995 (*Social Cognition* 13(3):319–339,
  "A computer network model of human transactive memory" —
  [doi:10.1521/soco.1995.13.3.319](https://doi.org/10.1521/soco.1995.13.3.319) — the paper
  most directly on point for a computer as TMS member, and not readable).
- ACM Digital Library returned 403 for Anvik 2006, Anvik and Murphy 2011, Ehrlich and Shami
  2008, Shami et al. 2008 and Minto and Murphy 2007; UBC author-copy paths returned 404.
- Ackerman et al. 2013: Springer page 303-redirects to an identity provider; the pre-press PDF
  in the Wayback Machine was used. Argote and Ren 2012 (*Journal of Management Studies*
  49(8):1375–1382): Carlson School PDF behind Cloudflare. Peltokorpi and Hood: Wiley
  `pdfdirect` returned an HTML shell.
- Salomon et al. 2026: the IEEE Xplore document page returned an empty body; the UBC author
  copy was used.
- The sentence attributed by IT Pro to a Microsoft Research report — that engineering managers
  "reported fewer interruptions within their teams, as developers relied less on colleagues
  for quick answers" — was not found in Microsoft's "Generative AI in Real-World Workplaces"
  (July 2024; full text via the Wayback Machine), whose only nearby sentence is that Copilot
  "can facilitate collaboration between colleagues". It may belong to the December 2023 "AI
  and Productivity Report"; not located and therefore not cited above.
- Tooling: OpenAlex daily budget exhausted mid-task; arXiv export API returned 503 (abs and
  HTML pages used instead); Semantic Scholar intermittently 429; Wayback `available` endpoint
  429 (CDX used); fatcat lookup timed out; hacks.mozilla.org and microsoft.com direct fetches
  returned HTML shells (Wayback copies used).
- No source was found that measures whether an expertise recommender changed the speed of
  getting an answer, whether shared agent transcripts are searched or read by anyone other
  than their author, or any TMS measure on a team whose code was written by an Agent Run.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.
- Ackerman, M. S., Dachtera, J., Pipek, V. and Wulf, V. (2013). Sharing knowledge and expertise: The CSCW view of knowledge management. *Computer Supported Cooperative Work* 22(4–6):531–573. doi:10.1007/s10606-013-9192-8
- Al Haque, E., Brown, C., LaToza, T. D. and Johnson, B. (2024). The evolution of information seeking in software development: Understanding the role and impact of AI assistants. arXiv:2408.04032
- Annunziata, S., Choudhuri, R., Sarma, A., Catolino, G. and Ferrucci, F. (2026). When AI joins the team! A model of how AI adoption relates to social patterns in software engineering teams. arXiv:2608.03462
- Anvik, J. and Murphy, G. C. (2011). Reducing the effort of bug report triage: Recommenders for development-oriented decisions. *ACM TOSEM* 20(3):1–35. doi:10.1145/2000791.2000794
- Anvik, J., Hiew, L. and Murphy, G. C. (2006). Who should fix this bug? *ICSE 2006*. doi:10.1145/1134285.1134336
- Austin, J. R. (2003). Transactive memory in organizational groups: The effects of content, consensus, specialization, and accuracy on group performance. *Journal of Applied Psychology* 88(5):866–878. doi:10.1037/0021-9010.88.5.866
- Bachrach, D. G., Lewis, K., Kim, Y., Patel, P. C., Campion, M. C. and Thatcher, S. M. B. (2019). Transactive memory systems in context: A meta-analytic examination of contextual factors in transactive memory systems development and team performance. *Journal of Applied Psychology* 104(3):464–493. doi:10.1037/apl0000329
- Balog, K., Fang, Y., de Rijke, M., Serdyukov, P. and Si, L. (2012). Expertise retrieval. *Foundations and Trends in Information Retrieval* 6(2–3):127–256. doi:10.1561/1500000024
- Burtch, G., Lee, D. and Chen, Z. (2024). The consequences of generative AI for online knowledge communities. *Scientific Reports* 14. doi:10.1038/s41598-024-61221-0
- Castelluccio, M. and Ledru, S. (2019). Teaching machines to triage Firefox bugs. Mozilla Hacks, 2019-04-09. https://hacks.mozilla.org/2019/04/teaching-machines-to-triage-firefox-bugs/ (read via the Wayback Machine)
- Chen, X., Li, X., Clark, J. G. and Dietrich, G. B. (2013). Knowledge sharing in open source software project teams: A transactive memory system perspective. *International Journal of Information Management* 33(3):553–563. doi:10.1016/j.ijinfomgt.2013.01.008
- Choi, S. Y., Lee, H. and Yoo, Y. (2010). The impact of information technology and transactive memory systems on knowledge sharing, application, and team performance: A field study. *MIS Quarterly* 34(4):855–870. doi:10.2307/25750708
- Claude Code documentation. Sessions. https://code.claude.com/docs/en/sessions
- del Rio-Chanona, M., Laurentsyeva, N. and Wachs, J. (2024). Large language models reduce public knowledge sharing on online Q&A platforms. *PNAS Nexus* 3(9). doi:10.1093/pnasnexus/pgae400; earlier version arXiv:2307.07367
- Ehrlich, K. and Shami, N. S. (2008). Searching for expertise. *CHI 2008*. doi:10.1145/1357054.1357224
- Faraj, S. and Sproull, L. (2000). Coordinating expertise in software development teams. *Management Science* 46(12):1554–1568. doi:10.1287/mnsc.46.12.1554.12072
- Fausett, C. M., Keebler, J. R., Lazzara, E. H., Gregory, M. E. and Blickensderfer, E. L. (2026). Measurement matters: A meta-analysis of transactive memory systems and team performance in laboratory settings. *Small Group Research*. doi:10.1177/10464964261434540 (erratum doi:10.1177/10464964261462615)
- GitHub Docs. Asking GitHub Copilot questions in GitHub. https://docs.github.com/en/copilot/how-tos/chat-with-copilot/chat-in-github; Using GitHub Copilot to explore a codebase. https://docs.github.com/en/copilot/tutorials/explore-a-codebase
- Hollingshead, A. B. (1998). Retrieval processes in transactive memory systems. *Journal of Personality and Social Psychology* 74(3):659–671. doi:10.1037/0022-3514.74.3.659
- Hopf, K., Nahr, N., Staake, T. and Lehner, F. (2024). The group mind of hybrid teams with humans and intelligent agents in knowledge-intense work. *Journal of Information Technology* 40(1):9–34. doi:10.1177/02683962241296883
- Hsu, J. S.-C., Shih, S.-P., Chiang, J. C. and Liu, J. Y.-C. (2012). The impact of transactive memory systems on IS development teams' coordination, communication, and performance. *International Journal of Project Management* 30(3):329–340. doi:10.1016/j.ijproman.2011.08.003
- Huang, R., Reyna, A., Lerner, S., Xia, H. and Hempel, B. (2025). Professional software developers don't vibe, they control: AI agent use for coding in 2025. arXiv:2512.14012
- Jackson, P. and Klobas, J. (2008). Transactive memory systems in organizations: Implications for knowledge directories. *Decision Support Systems* 44(2):409–424. doi:10.1016/j.dss.2007.05.001
- Jaffe, S., Shah, N. P., Butler, J., Farach, A., Cambon, A., Hecht, B., Schwarz, M. and Teevan, J. (eds) (2024). Generative AI in real-world workplaces: The second Microsoft report on AI and productivity research. Microsoft, July 2024 (read via the Wayback Machine; the live microsoft.com PDF URL returned an HTML shell).
- Kabir, S., Udo-Imeh, D. N., Kou, B. and Zhang, T. (2024). Is Stack Overflow obsolete? An empirical study of the characteristics of ChatGPT answers to Stack Overflow questions. *CHI 2024*. arXiv:2308.02312
- Kanawattanachai, P. and Yoo, Y. (2007). The impact of knowledge coordination on virtual team performance over time. *MIS Quarterly* 31(4):783–808. doi:10.2307/25148820
- Kovalenko, V., Tintarev, N., Pasynkov, E., Bird, C. and Bacchelli, A. (2018/2020). Does reviewer recommendation help developers? *IEEE Transactions on Software Engineering*. Preprint doi:10.5281/zenodo.1404814
- Kush, J. and Argote, L. (undated). Indicator vs. structural measure of transactive memory. INFORMS Organization Science Winter Conference proposal. https://higherlogicdownload.s3.amazonaws.com/INFORMS/e2a17bc9-6cb2-4c0a-8ce8-03ff37e5bbb0/UploadedImages/OSWC/Kush%20%26%20Argote%20-%20Indicator%20vs%20Structural%20Measure%20of%20TMS%20-%20Proposal%20for%20OSWC.pdf
- Kuznetsov, D., Chao, G. and Dishop, C. (2024). Transactive memory in caregiver networks using artificial intelligence. *Proceedings of the AAAI Symposium Series* 4(1). doi:10.1609/aaaiss.v4i1.31789
- Lewis, K. (2003). Measuring transactive memory systems in the field: Scale development and validation. *Journal of Applied Psychology* 88(4):587–604. doi:10.1037/0021-9010.88.4.587
- Lewis, K. and Herndon, B. (2011). Transactive memory systems: Current issues and future research directions. *Organization Science* 22(5):1254–1265. doi:10.1287/orsc.1110.0647
- Lewis, K., Belliveau, M., Herndon, B. and Keller, J. (2007). Group cognition, membership change, and performance: Investigating the benefits and detriments of collective knowledge. *Organizational Behavior and Human Decision Processes* 103(2):159–178. doi:10.1016/j.obhdp.2007.01.005
- Liang, D. W., Moreland, R. and Argote, L. (1995). Group versus individual training and group performance: The mediating role of transactive memory. *Personality and Social Psychology Bulletin* 21(4):384–393. doi:10.1177/0146167295214009
- McDonald, D. W. and Ackerman, M. S. (1998). Just talk to me: A field study of expertise location. *CSCW '98*. doi:10.1145/289444.289506 (author's copy at eecs.umich.edu/~ackerm/pub/98b25/cscw98.expertise.pdf, read via the Wayback Machine)
- McDonald, D. W. and Ackerman, M. S. (2000). Expertise Recommender: A flexible recommendation system and architecture. *CSCW 2000*. doi:10.1145/358916.358994. https://web.archive.org/web/20030401080115id_/http://www.eecs.umich.edu:80/~ackerm/pub/00b30/cscw00.er.pdf
- Mell, J. N., van Knippenberg, D. and van Ginkel, W. P. (2014). The catalyst effect: The impact of transactive memory system structure on team performance. *Academy of Management Journal* 57(4):1154–1173. doi:10.5465/amj.2012.0589
- Minto, S. and Murphy, G. C. (2007). Recommending emergent teams. *MSR 2007*. doi:10.1109/msr.2007.27
- Mockus, A. and Herbsleb, J. D. (2002). Expertise Browser: A quantitative approach to identifying expertise. *ICSE 2002*. doi:10.1145/581339.581401. http://herbsleb.org/web-pubs/pdfs/mockus-expertise-2002.pdf
- Monteiro Ribeiro, D., Gama, K. and Jackson, V. (2026). A preliminary study on the impact of AI in the creativity and collaboration in software teams. *SBES 2026*. arXiv:2607.16744
- Moreland, R. L. and Myaskovsky, L. (2000). Exploring the performance benefits of group training: Transactive memory or improved communication? *Organizational Behavior and Human Decision Processes* 82(1):117–133. doi:10.1006/obhd.2000.2891
- Oshri, I., van Fenema, P. and Kotlarsky, J. (2008). Knowledge transfer in globally distributed teams: The role of transactive memory. *Information Systems Journal* 18(6):593–616. doi:10.1111/j.1365-2575.2007.00243.x
- Peltokorpi, V. and Hood, A. C. (2019). Communication in theory and research on transactive memory systems: A literature review. *Topics in Cognitive Science* 11(4):644–667. doi:10.1111/tops.12359
- Ren, Y. and Argote, L. (2011). Transactive memory systems 1985–2010: An integrative framework of key dimensions, antecedents, and consequences. *Academy of Management Annals* 5(1):189–229. doi:10.5465/19416520.2011.590300
- Riedl, C., Savage, S. and Zvelebilova, J. (2026). Cognitive spillover in human-AI teams. *ACM Transactions on Computer-Human Interaction*. arXiv:2407.17489
- Salomon, L., Koshchenko, E., Sergeyuk, A., Holmes, R., Murphy, G. C. and Fritz, T. (2026). From disruptions to discussions: How GenAI is shaping human interactions in software development. *IEEE Transactions on Software Engineering* 52(7):2095–2110. doi:10.1109/TSE.2026.3655626. https://www.cs.ubc.ca/~rtholmes/papers/tse_2026_salomon.pdf; data https://zenodo.org/records/18100060
- Schuler, D. and Zimmermann, T. (2009). Mining usage expertise from version archives. *ICSM 2009*. doi:10.1109/icsm.2009.5306386
- Shami, N. S., Ehrlich, K. and Millen, D. R. (2008). Pick me! Link selection in expertise search results. *CHI 2008*. doi:10.1145/1357054.1357223
- Stack Exchange API (2026-09-15). `/2.3/questions?site=stackoverflow&filter=total` by creation-date window. https://api.stackexchange.com/2.3/questions
- Thongtanunam, P., Tantithamthavorn, C., Kula, R. G., Yoshida, N., Iida, H. and Matsumoto, K. (2015). Who should review my code? A file location-based code-reviewer recommendation approach for modern code review. *SANER 2015*. doi:10.1109/saner.2015.7081824
- Unblocked. Developer Q&A. https://getunblocked.com/questions/
- Vella, A. and Blincoe, K. (2026). The impact of AI coding assistants on software engineering: A longitudinal study. arXiv:2605.23135
- Wegner, D. M. (1987). Transactive memory: A contemporary analysis of the group mind. In B. Mullen and G. R. Goethals (eds), *Theories of Group Behavior*, Springer, 185–208. doi:10.1007/978-1-4612-4634-3_9. https://web.archive.org/web/20041111092138id_/http://www.wjh.harvard.edu:80/~wegner/pdfs/Wegner%20Transactive%20Memory.pdf
- Wegner, D. M. (1995). A computer network model of human transactive memory. *Social Cognition* 13(3):319–339. doi:10.1521/soco.1995.13.3.319
- Wegner, D. M., Erber, R. and Raymond, P. (1991). Transactive memory in close relationships. *Journal of Personality and Social Psychology* 61(6):923–929. doi:10.1037/0022-3514.61.6.923. https://web.archive.org/web/20051223234946id_/http://www.wjh.harvard.edu:80/~wegner/pdfs/Wegner,Erber,&Raymond1991.pdf
- Xiao, Q., Hu, X. E., Whiting, M. E., Karunakaran, A., Shen, H. and Cao, H. (2025). Beyond the personal assistant: How expectations for enterprise AI in teamwork diverged as generative AI took shape, 2023–2025. arXiv:2509.10956
- Yimam-Seid, D. and Kobsa, A. (2003). Expert-finding systems for organizations: Problem and domain analysis and the DEMOIR approach. *Journal of Organizational Computing and Electronic Commerce* 13(1):1–24. doi:10.1207/s15327744joce1301_1
- Yoo, Y. and Kanawattanachai, P. (2001). Developments of transactive memory systems and collective mind in virtual teams. *International Journal of Organizational Analysis* 9(2):187–208. doi:10.1108/eb028933
