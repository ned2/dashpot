---
status: research
date: 2026-09-15
---

# Workspace awareness and coordination

Research date: 2026-09-15

This note documents what the CSCW and software-engineering literature says about
awareness — knowing who is working on what, where, and in what state — and about the
coordination requirements that awareness serves. It covers the framework papers (Dourish
and Bellotti 1992; Gutwin and Greenberg 2002), the awareness tools built for developers and
how they were evaluated (Palantír, FASTDash, Jazz dashboards and feeds, GitHub's activity
feeds), the coordination-requirements strand (Conway's law and its empirical tests, Kraut and
Streeter, Herbsleb and Mockus, Cataldo's socio-technical congruence, de Souza's awareness
network), the studies that measured which awareness information developers actually seek,
the previous round of the "chat versus the work item" argument (IRC versus mailing list in
open source, ChatOps, Slack versus the tracker), and the awareness work that treats an
automated actor as a participant. It is documentary: it records what the sources found, with
their evidence and limits, and maps each finding to where the existing notes in this
directory touch it. It does not evaluate fit for Dashpot or any tool. Terminal citations are
primary — the paper, the author's copy, a Wayback capture of the author's copy, the vendor's
own page — and every figure is reported as the source states it. Items read only as abstract
or metadata are marked; anything recalled rather than read is marked unverified. Where an
earlier note already covers a source, this note links to it rather than repeating it: the
issue-tracker-as-knowledge-repository study and the current issue-centric agent surfaces are
in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#this-predates-coding-agents),
team cognition and presence awareness (Espinosa et al. 2007, abstract only) are in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research),
ownership footprints and expertise location are in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss)
and
[track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure),
and the situation-awareness literature from human factors (Endsley) is in
[adjacent-literatures.md](adjacent-literatures.md#situation-awareness-and-the-out-of-the-loop-problem).

## Finding

The literature defines awareness as "an understanding of the activities of others, which
provides a context for your own activity" (Dourish and Bellotti 1992) and, for shared
workspaces, as "the up-to-the-moment understanding of another person's interaction with a
shared workspace" (Gutwin and Greenberg 2002), whose elements are who (presence, identity,
authorship), what (action, intention, artifact) and where (location, gaze, view, reach) in the
present, plus their histories in the past — with the future deliberately excluded because it
"involves inference, extrapolation, and prediction". Awareness is treated as instrumental: the
coordination strand shows that communication need follows the technical dependency structure
(Conway 1968; Herbsleb and Grinter 1999; MacCormack, Rusnak and Baldwin), that informal
interpersonal contact is what handles uncertainty and "other project members" are the help
source developers use and value most (Kraut and Streeter 1995), that coordination requirements
are volatile week to week and that when the people who need to talk actually do, modification
requests resolve faster and fail less (Cataldo et al. 2006; Cataldo and Herbsleb 2013:
structural congruence from minimum to maximum cut the estimated failure probability by 18.6 per
cent in one project and 7.6 per cent in another), that distributed work took roughly 2.5 times
as long largely because more people had to be found and involved (Herbsleb and Mockus 2003),
and that the set of people a developer must be aware of — the "awareness network" — is fluid
and is misidentified in both directions (de Souza and Redmiles 2007, 2011). What developers
actually seek is measured in a few places: "What have my coworkers been doing?" was the second
most frequently sought information need in Ko, DeLine and Venolia 2007 (17 developers, 334
instances), obtained overwhelmingly from coworkers and email rather than tools, and rated
unimportant on a survey precisely because it was so readily obtained; the FASTDash survey of 90
Microsoft employees put work-item assignments, bug descriptions and the checked-out/edited
state of the shared code base at the top, and a six-person field deployment raised
situation-awareness ratings and communication about status; Treude and Storey's Jazz study
found dashboards used for pull-mode high-level overview by roughly half of respondents and
feeds used as a small-scale inbox for "What should I do next?", with 26 of 32 saying dashboard
information would not alter their practice. Tool papers (Palantír, FASTDash, Jazz, GitHub
feeds) mostly report design plus small studies; the controlled evidence that awareness tooling
changes outcomes is two laboratory experiments (Palantír, TSE 2012, abstract only) and a
six-person pre/post field study (FASTDash). The chat-versus-durable-channel argument recurs
across three generations with the same shape: open-source developers in 2004 kept technical
discussion off IRC because it is "not archived" and "siphoned off" from the list, posting
summaries back; Bertram et al. 2010 found collocated teams pasting IM excerpts into the issue
tracker and preferring its comment history because IM was interrupting and the case was
"persistent, asynchronous, and oftentimes multicast"; GitHub's 2011–2013 ChatOps testimony
claimed the chat room made deploys and branch state visible to everyone ("Everyone sees all of
that happen on their first day"), while a 2016 survey respondent said "If Slack is taken out …
We're blind", and the 2019–2025 discourse has settled on "Slack is where knowledge/context goes
to die" with vendors positioning the tracker as where "context stays attached to the work".
Bots as participants are studied as noise sources and as conduits (Wessel et al. 2018: 26 per
cent of 351 projects used bots, no consistent before/after difference; Storey and Zagalsky
2016: bots "help team members know when commits were made, which tests and services failed, and
when other services or builds are deployed"); no source found treats an automated actor as an
awareness *subject* whose who/what/where must be displayed to humans, which is the gap the
corpus's Claude Code session-registry issues sit in.

## What awareness is: the CSCW frameworks

### Dourish and Bellotti 1992 — "Awareness and coordination in shared workspaces"

Read in full (author's copy). CSCW '92, pp. 107–114.

The paper's definition is the one the later literature repeats: awareness "is an understanding
of the activities of others, which provides a context for your own activity". The context is
used "to ensure that individual contributions are relevant to the group's activity as a
whole, and to evaluate individual actions with respect to group goals and progress".

The analytical contribution is a classification of how collaborative writing systems provide
awareness, illustrated with three systems:

- **Informational** mechanisms: explicit exchange of information about activity, such as
  RCS-style edit logs or "who is editing what" annotations. The cost falls on the provider,
  who must decide what is relevant to whom (the paper cites Grudin's observation that
  groupware fails when the people who do the work are not the people who benefit), and the
  sender presupposes relevance and controls delivery.
- **Role restrictive** mechanisms: roles (author, commenter, reader) constrain what each
  participant can do and thereby imply what they are doing.
- **Shared feedback**: awareness information is generated passively as a by-product of
  working in a shared space, so no one has to decide to send it.

The empirical basis is the ShrEdit study conducted with the Olsons: groups of three designers
solving a 90-minute design problem in a shared editor, with video analysis of four groups.
The observation reported is that groups "continually moved between concurrent, but more or
less independent, work … to very tightly focused group consideration", which the authors take
as evidence that awareness support must serve both loosely and tightly coupled work without
the participants having to declare which mode they are in. The paper coins "semi-synchronous"
for systems whose participants work at the same time but not in lockstep. Evidence type:
qualitative observation of four small groups plus an argument from system analysis.

Source: <https://www.dourish.com/publications/1992/cscw92-awareness.pdf>.

### Gutwin and Greenberg 2002 — "A descriptive framework of workspace awareness for real-time groupware"

Read in full (author's copy via Wayback). *Computer Supported Cooperative Work* 11(3):411–446,
doi:10.1023/A:1021271517844.

The definition: "We define workspace awareness as the up-to-the-moment understanding of
another person's interaction with a shared workspace." The framework has three parts.

**Elements** (Table 1, present; Table 2, past). Present: *who* — presence ("Is anyone in the
workspace?"), identity ("Who is participating?"), authorship ("Who is doing that?"); *what* —
action ("What are they doing?"), intention ("What goal is that action part of?"), artifact
("What object are they working on?"); *where* — location, gaze, view, reach. Past: action
history ("How did that operation happen?"), artifact history ("How did this artifact come to
be in this state?"), event history ("When did that event happen?"), and presence, location and
action history ("Who was here, and when? Where has a person been? What has a person been
doing?"). The future is left out on purpose: knowledge of the present and past "can be based
on perceptual information, whereas belief about the future involves inference, extrapolation,
and prediction".

**Mechanisms** by which people maintain awareness in a physical shared workspace:
*consequential communication* (watching bodies at work), *feedthrough* (seeing artifacts
change), and *intentional communication* (talk and gesture). The design problem for
groupware is that the first two come for free physically and must be reconstructed in a
distributed tool.

**Activities** that awareness serves: management of coupling (deciding when to work
together and when apart — the same observation as Dourish and Bellotti's ShrEdit groups),
simplification of communication (deixis, "this one here"), coordination of action,
anticipation, and assistance.

The paper is a conceptual framework built from prior literature and the authors' own
observational studies (summarised in an appendix); it reports no new experiment. Evidence
type: argument organising qualitative observation.

Source:
<https://web.archive.org/web/20060618211403id_/http://hci.usask.ca/publications/2002/awareness-jcscw.pdf>.

### Steinmacher, Chaves and Gerosa 2013 — awareness support in distributed software development

Abstract only (Springer page via a 2019 Wayback capture; full text paywalled). *Computer
Supported Cooperative Work* 22(2–3):113–158, doi:10.1007/s10606-012-9164-4.

A systematic mapping of awareness support in distributed software development. From the
abstract: 1,967 papers were screened and 91 were found to present awareness support; 71 of
those were published between 2006 and 2010. The papers were classified by the 3C
collaboration model (communication, coordination, cooperation) and by Gutwin and Greenberg's
framework. Coordination was the most-supported dimension and communication the least, and
the workspace-awareness elements (who/what/where) were the ones most often supported. The
abstract is cited here to show that the Gutwin framework became the standard classification
for developer-awareness tools; nothing further from the body is claimed.

Source: <https://doi.org/10.1007/s10606-012-9164-4> (abstract; paywalled).

### Treude and Figueira Filho 2019 — the awareness kinds applied to developers

Read in full (open-access book chapter). In Sadowski and Zimmermann (eds.), *Rethinking
Productivity in Software Engineering*, ch. 15, doi:10.1007/978-1-4842-4221-6_15.

The chapter restates the Dourish and Bellotti definition and distinguishes context awareness
(the state of a shared task, "the progress of a development team toward the next release"),
social awareness (others' roles and contributions) and workspace awareness (the Gutwin
definition). Its illustrative questions range from "What is the overall status of the
project? What are the current bottlenecks?" to "Who else is working on the same file right
now and has uncommitted changes? Who is affected by the source code I am writing at the
moment?". The chapter's own study reports developer interviews in which participants said
no single metric captures output, that measures can be gamed, and that what they want
surfaced is deviation from expectation (a scenario question about what changed since
Monday). Evidence type: qualitative interviews reported without counts in the chapter.

Source: <https://doi.org/10.1007/978-1-4842-4221-6_15>.

## Coordination requirements: what awareness is for

### Conway 1968 and the mirroring evidence

**Conway 1968**, read in full (author's page). *Datamation* April 1968. The thesis:
"organizations which design systems … are constrained to produce designs which are copies of
the communication structures of these organizations". The argument is that every interface
in a design corresponds to a communication path that existed (or did not) between the groups
that designed either side, and that the number of possible communication paths grows as
roughly half the square of the number of people, so a design effort "should be organized
according to the need for communication". Evidence type: argument from cases.

**Herbsleb and Grinter 1999**, read in full (author's copy). *IEEE Software*, September/October
1999, "Architectures, coordination, and distance: Conway's law and beyond". Two rounds of
interviews at Lucent (10 and 8) on a product developed across UK and German sites. The
finding is that the three formal coordination mechanisms — architecture, plans and process —
work only "as far as our ability to see into the future"; the unanticipated is handled by
unplanned contact, and across sites "there were no chance discussions", so contradictory
assumptions between sites went undetected. The authors describe collocated developers as able
to initiate communication easily "because they know who is around and if they are
available" — presence and availability awareness stated as the enabling condition for the
informal mechanism. Evidence type: qualitative interviews.

Source: <https://herbsleb.org/web-pubs/pdfs/herbsleb-architectures-1999.pdf>.

**MacCormack, Rusnak and Baldwin**, read in full as HBS Working Paper 08-039 (published as
"Exploring the duality between product and organizational architectures", *Research Policy*
2012). Five matched pairs of open-source and commercial products (Linux kernel versus Solaris
and XNU, MySQL versus a commercial database, and others), comparing dependency structure with
design-structure matrices. In every pair the product built by the loosely coupled
(open-source) organisation was more modular, with propagation cost differing by up to a
factor of eight. Evidence type: measured, five pairs, observational.

Source:
<https://www.hbs.edu/ris/Publication%20Files/08-039_1861e507-1dc1-4602-85b8-90d71559d85b.pdf>.

### Kraut and Streeter 1995 — "Coordination in software development"

Read from a scanned copy via Wayback (poor OCR; pages 4, 7, 8 and 9 read as images).
*Communications of the ACM* 38(3):69–81, doi:10.1145/203330.203345.

A survey study at a large telecommunications firm: 563 individuals across 65 projects and
150 supervisory groups, from 750 surveyed (88 per cent return). The instrument asked how much
each coordination technique was used and how valuable it was, and related coordination to
outcomes. Three results are relevant here. First, in the regressions of Table 2 (N = 65
projects), informal interpersonal procedures (unscheduled meetings, discussion with peers)
were judged more valuable when project certainty was low (β = .46 for certainty, p < .05, on
value) and during planning (.28), while formal impersonal procedures (documents, schedules,
error tracking) were used more on larger projects (.32) and valued more when certainty was
high (.39); the text adds that techniques "judged to be statistically significantly less
valuable than predicted by their use tended to be formal coordination techniques" such as
code inspections and status reviews. Second, Figure 2 places "other project members" as by
far the most used and most valued source of help, with electronic bulletin boards the least
used and least valued; the authors write that "software engineers overwhelmingly get their
information from other people, and the ease of getting the information is a critical
determinant". Third, Table 3 reports that coordination success correlated 0.61 with client
satisfaction (18 projects with both measures, p < .01) and 0.13 with managers' evaluations.
The paper's argument is that formal procedures scale with project size but do not handle
uncertainty, which informal interpersonal contact does, and that the latter is what breaks
down as projects grow. Evidence type: measured survey, cross-sectional, pages 4, 7, 8 and 9
read as images.

Source:
<https://web.archive.org/web/20160910203218id_/http://kraut.hciresearch.org/sites/kraut.hciresearch.org/files/articles/kraut95-CoordiantionInSoftwareDevelopment.pdf>.

### Herbsleb and Mockus 2003 — "An empirical study of speed and communication in globally distributed software development"

Read in full (author's copy). *IEEE Transactions on Software Engineering* 29(6):481–494.

Modification requests (MRs) at Lucent that required work at more than one site took about
two and a half times as long as single-site MRs: department A, 5 days single-site versus 12.7
days distributed; department B, 7 versus 18 (p < 0.001; replication set of 4,974 MRs). The
mechanism the models support is that distributed MRs involved more people, and the delay
tracks the number of people rather than distance directly. Surveys (98 of 117 responding)
measured the communication network: developers reported a mean of 16.0 weekly contacts at
their own site versus 4.9 at the remote site, and agreed more strongly with "I lose time
trying to figure out who to contact regarding …" for remote colleagues (t = 4.44,
p < .0001). Section 4.2.4, "Awareness", names presence awareness through instant messaging
and shared calendars as the mechanism by which collocated developers know when a colleague
is reachable. Evidence type: measured, archival plus survey.

Source: <https://herbsleb.org/web-pubs/pdfs/Herbsleb-Empirical-2003.pdf>.

### Cataldo, Wagstrom, Herbsleb and Carley 2006, and Cataldo and Herbsleb 2008, 2013 — socio-technical congruence

**Cataldo, Wagstrom, Herbsleb and Carley 2006**, "Identification of coordination
requirements", read in full (author's copy). CSCW 2006. The data: 114 developers in 8 teams
across 3 laboratories at a data-storage company, about three years and four releases, with
the MR as the unit of work. The method derives a *coordination requirements* matrix from
which files each MR touched and which developers touched them, then measures *congruence* as
the fraction of those requirements met by an actual communication or structural link: team
structure, geography, MR-comment interaction, and IRC. Results: coordination requirements are
volatile from week to week; all four congruence measures significantly reduce MR resolution
time in the OLS models (Table 2); structural congruence decays across releases while
communication-based congruence rises; higher performers had higher congruence. The
implications section proposes that an IDE could use the congruence measures "to recommend a
dynamic 'buddy list' every time particular parts of the software are" being modified, citing
TUKAN and Palantír as existing awareness tools. Coding reliability: two raters, 97.5 per cent
agreement. Evidence type: measured, one company.

**Cataldo, Herbsleb and Carley 2008**, "Socio-technical congruence: a framework for
assessing the impact of technical and work dependencies on software development
productivity", read in full (author's copy). ESEM 2008. Same project, 39 months. Logical
(co-change) dependencies predicted coordination needs better than syntactic call and data
dependencies. Evidence type: measured.

**Cataldo and Herbsleb 2013**, "Coordination breakdowns and their impact on development
productivity and software failures", read in full (author's copy). *IEEE TSE* 39(3):343–360.
Project A is the earlier data (114 developers, 8,257 MRs; 2,375 with IRC data); Project B is
an embedded system with 380 developers in 37 teams and 9,074 files. Moving structural
congruence from its minimum to its maximum reduced the estimated failure probability of an MR
by 18.6 per cent in A and 7.6 per cent in B; IRC and MR congruence were also significant for
failure proneness; congruence was the second most important factor for resolution time in A
and third in B. New coordination needs — pairs of people who had never needed to coordinate
before — exceeded 30 per cent of requirements in some months. Coding agreement 98.2 per
cent. Evidence type: measured, two projects, observational.

Sources: <https://herbsleb.org/web-pubs/pdfs/cataldo-identification-2006.pdf>,
<https://herbsleb.org/web-pubs/pdfs/cataldo-socio-2008.pdf>,
<https://herbsleb.org/web-pubs/pdfs/Cataldo-Coordination-2013.pdf>.

### de Souza and Redmiles 2007, 2011 — the awareness network

**de Souza and Redmiles 2007**, "The awareness network: to whom should I display my
actions? And, whose actions should I monitor?", read in full (ECSCW 2007 proceedings via
Wayback), pp. 99–117, doi:10.1007/978-1-84800-031-5_6. Two ethnographies. Alpha: a nine-year
old system, 34 developers, non-modular, problem-report based, with mandatory check-in emails;
8 weeks of observation and 8 interviews. Beta: a nine-month old system, 57 developers in 5
sub-teams, API-based; 11 weeks and 15 interviews of 35–90 minutes. The term "awareness
network" names the set of people whose actions a developer must monitor and to whom the
developer must display their own actions. Findings: the network is fluid, changing with the
task and the code touched; developers misidentified it in both directions, so that
notifications went to people who did not need them (overflow) and did not reach people who
did (missing notifications), and both caused delays; newcomers in Alpha used the check-in
emails to infer who the experts on a part of the code were; in Beta, architecture (API)
knowledge reduced the size of the network a developer needed to track.

**de Souza and Redmiles 2011**, "The awareness network, to whom should I display my actions?
And, whose actions should I monitor?", abstract only (OpenAlex). *IEEE TSE* 37(3):325–340,
doi:10.1109/TSE.2011.19. Extends the analysis to three teams with the same conclusions.

Evidence type: qualitative ethnography with interview counts.

Source: <https://web.archive.org/web/20110515023002id_/http://www.ecscw.org/2007/06%20paper%20100%20Desouza.pdf>.

## Awareness tools for developers and how they were evaluated

### Palantír (Sarma, Noroozi and van der Hoek 2003; Sarma, Redmiles and van der Hoek 2012)

**Sarma, Noroozi and van der Hoek 2003**, "Palantír: raising awareness among configuration
management workspaces", read in full (author's copy via Wayback). ICSE 2003, pp. 444–454,
doi:10.1109/ICSE.2003.1201222. The framing is that workspace isolation "is both good and
bad": good because developers work without interference, bad because "not knowing which
artifacts are changing in parallel regularly leads to problems when changes are promoted".
Palantír "inverts information flow from pull to push": instead of learning about others'
changes only at check-in or check-out, developers continuously see which developers are
changing which artifacts, with a severity measure of how much has changed, and the tool
distinguishes direct conflicts (same artifact) from indirect (dependent artifacts). The 2003
paper is a design paper with no evaluation.

**Sarma, Redmiles and van der Hoek 2012**, "Palantír: early detection of development
conflicts arising from parallel code changes", abstract only. *IEEE TSE* 38(4):889–908,
doi:10.1109/TSE.2011.64. Two laboratory experiments; participants with Palantír detected and
resolved more conflicts, earlier, and checked in fewer unresolved conflicts, at what the
abstract calls reasonable overhead. Full text not reached (see Dead ends).

Evidence type: design (2003); measured laboratory experiment (2012, abstract only).

Source (2003):
<https://web.archive.org/web/20070208130645id_/http://www.ics.uci.edu/~asarma/papers/icse2003-final.pdf>.

### FASTDash (Biehl, Czerwinski, Smith and Robertson 2007)

Read in full (Microsoft Research copy). CHI 2007, pp. 1313–1322, doi:10.1145/1240624.1240823.

Formative work: a survey of 90 Microsoft employees (over 30 questions) and 13 one-hour
interviews. The awareness items most sought were work items (task assignments), bug
descriptions, and the status of the shared code base — which files were checked out or being
edited; the key items were reported to change daily or hourly. FASTDash is a large-display
visualisation of the source tree annotated with who has which files checked out, who is
editing, and conflicts.

Summative work: a pre/post field study with six colocated programmers on one team, 610
observation minutes without the display and 443 with it, over four days. The Situation
Awareness Rating Technique (SART) was completed pre and post by four of the six; Division of
Attention fell by 30 per cent (p = 0.059) and Instability of the Situation fell by over 30
per cent (pre μ = 3.0, post μ = 2.0, z = −2.0, p = 0.046). Coded communication rose: a 58 per
cent increase in instruction/orientation communications, 15 per cent in
information/bottleneck, and 33 per cent in status communications. Whiteboard and sticky-note
use fell (the paper's Figure 8 says creations "were down 250%"). The team kept the display
after the study. Evidence type: measured, six participants, no control group; the survey is
self-report.

Source: <https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/chi2007-fastdash.pdf>.

### Jazz: Frost 2007, and Treude and Storey 2010 — dashboards and feeds

**Frost 2007**, "Jazz and the eclipse way of collaboration", abstract only (OpenAlex). *IEEE
Software* 24(6):114–117, doi:10.1109/MS.2007.170. Jazz is described as a platform for making
"teams and teams of teams more productive" by integrating work items, source control, builds
and team awareness in one server. Cited here as the primary description of the platform the
next paper studied.

**Treude and Storey 2010**, "Awareness 2.0: staying aware of projects, developers and tasks
using dashboards and feeds", read in full (author's copy). ICSE 2010, doi:10.1145/1806799.1806854.

Setting: IBM's Jazz development, a detailed case of a team of about 150 developers plus four
other component teams. Data: 311 dashboards containing 2,975 viewlets (2 project-level, 72
team-level, 237 individual dashboards), nine interviews, and a survey with 119 responses (21
from the detailed case at 14 per cent response, 98 from other teams at 9 per cent; 76
contributors, 28 component leads, 9 development managers, 6 project administrators).

Findings on use:

- 36 of the 74 who answered the question use dashboards; 38 do not. Only 26 could recall
  when they last looked at one. "High-level overview" was named 14 times in the survey and in
  six of nine interviews as the purpose; 19 of 35 use dashboards for navigation to work
  items. Use is constant across release phases for 25 of 36.
- Feeds "track work at a small scale" and serve as an inbox for "What should I do next?",
  replacing work-item email notifications.
- Asked whether they would alter their work practices because of dashboard information, 26
  of 32 said no. Dashboards were nonetheless used for comparison between teams ("Just knowing
  that you're not the component that's on the critical path for number of bugs remaining")
  and participants described adding caveats so that long bars are not misread: "Just because
  one team has a lot more defects than another that doesn't necessarily mean that the
  quality of that component is any worse."
- Push versus pull: none of the respondents found dashboards distracting, because they are
  outside the client and consulted deliberately; 6 of 40 found feed notifications irrelevant.

Evidence type: measured (artifact counts), self-report survey, qualitative interviews; one
company.

**Storey and Treude 2019**, "Software engineering dashboards: types, risks, and future",
read in full (open-access chapter, doi:10.1007/978-1-4842-4221-6_16). Lists the risks of
dashboards as argument: they favour numbers over text, may omit relevant context, often do
not explain what they show, and invite Goodhart's-law gaming when a displayed measure
becomes a target. Evidence type: argument drawing on the 2010 study.

Sources: <https://ctreude.ca/pdf/2010-awareness-20-staying-aware-of.pdf>;
<https://doi.org/10.1007/978-1-4842-4221-6_16>.

### GitHub's activity feeds as social transparency (Dabbish, Stuart, Tsay and Herbsleb 2012)

Read in full (author's copy). "Social coding in GitHub: transparency and collaboration in an
open software repository", CSCW 2012.

Twenty-four semi-structured interviews, sampling both peripheral users and heavy users of
projects with more than 80 watchers. GitHub's news feed shows follow, watch, commit, issue,
pull-request and comment events. The paper's claim is that visibility of these events lets
users make inferences from four sets of cues (about people, projects, commits, and
discussion) and supports five activities: managing incoming contributions, identifying user
needs from forks, managing dependencies by watching the commit events and releases of
upstream projects, learning, and reputation. The awareness use is direct: "Commit activity in
the feeds shows that the project is alive" (P16). Evidence type: qualitative interviews.

Source: <https://herbsleb.org/web-pubs/pdfs/dabbish-social-2012.pdf>.

## What awareness information people actually use

### Ko, DeLine and Venolia 2007 — "Information needs in collocated software development teams"

Read in full (author's copy; pages 3 and 7 read as rendered images because the text layer
dropped digits). ICSE 2007, pp. 344–353.

Seventeen developers at Microsoft observed for roughly 90-minute sessions each; 334
information-seeking instances coded into 21 information needs. The need labelled a2, "What
have my coworkers been doing?", was the second most frequently sought and the second most
frequently acquired. Its sources, by count: coworker 20, email 13, tool 4, bug alert 4,
instant message 2 — that is, mostly people and mail, not tooling. A separate survey (42
responses of 550 invited) asked developers to rate the needs: only 17 per cent rated a2
important, 10 per cent said it was unavailable and 10 per cent said it was inaccurate. The
authors' interpretation: "coworker awareness is so frequently sought and successfully
obtained that developers do not think about it". Other measurements: developers were blocked
a median of four times per session, and task switches occurred about every five minutes.
Evidence type: measured observation plus self-report survey; one company; the corpus already
cites this paper for unanswered "why" questions in
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of).

Source: <https://faculty.washington.edu/ajko/papers/Ko2007InformationNeeds.pdf>.

### Gutwin, Penner and Schneider 2004 — group awareness in distributed open-source development

Read in full (author's copy via Wayback). CSCW 2004, pp. 72–81, doi:10.1145/1031607.1031621.

Fourteen interviews (nine NetBSD, four Apache httpd, one Subversion). Awareness of who is
working on what was maintained mainly through mailing lists and text chat, by a practice the
authors call overhearing: developers read lists they are not addressed on to keep a picture
of activity, and the projects' "making it public" culture treats posting to the list as the
norm. Table 2 lists the mechanisms: mailing lists, chat, commit messages, the maintainer
field in files, the repository itself, issue trackers (which the authors note "may remove
communication from other lists"), asking senior developers, and documentation. Two wishes
were recorded: a searchable archive spanning ten or more years, and an automatically updated
picture of who works where. Evidence type: qualitative interviews. The IRC-versus-list
findings are in the next section.

Source:
<https://web.archive.org/web/20060618211526id_/http://hci.usask.ca/publications/2004/awareness-cscw04.pdf>.

### Lin, Zagalsky, Storey and Serebrenik 2016, and Storey et al. 2017 — where awareness comes from now

**Lin, Zagalsky, Storey and Serebrenik 2016**, "Why developers are slacking off:
understanding how software teams use Slack", read in full (author's copy via Wayback). CSCW
2016 Companion, pp. 333–336, doi:10.1145/2818052.2869117. Two surveys, 53 and 51 responses
(the second sent to 650 forkers of hubot-slack), 104 in total. Bots for development and
deployment support were the most-mentioned use (55 mentions). The quote reported for
dependence: "If Slack is taken out, it's just like turning our lights off. We're blind."
Evidence type: self-report survey, small.

**Storey, Zagalsky, Figueira Filho, Singer and German 2017**, "How social and communication
channels shape and challenge a participatory culture in software development", read in full
(author's copy). *IEEE TSE* 43(2):185–204. A survey of 1,449 GitHub users, mean 11.7
channels each. Code hosting and project-coordination tools were the channels cited for group
awareness; private and public chat were rated most important by about 15 per cent (sixth and
ninth in the ranking), microblogs by about 20 per cent (fifth). The fragmentation finding is
stated as a challenge: "Important communications get lost … Companies such as Slack are
attempting to solve this problem". Evidence type: self-report survey, large.

Sources: <https://web.archive.org/web/20240422032939id_/http://chisel.cs.uvic.ca/pubs/lin-CSCW2016.pdf>
(Wayback capture of the CHISEL group's copy);
<https://web.archive.org/web/20240424025500id_/http://chisel.cs.uvic.ca/pubs/storey-TOSE2017.pdf>.

## Chat versus the durable channel: three generations of the same argument

### Open source, 2004: IRC versus the mailing list

Gutwin, Penner and Schneider 2004 (above) recorded the first version. Chat was where
developers overheard each other in real time, but interviewees kept technical decisions off
it: chat is "not archived" and discussion there is "siphoned off" from the mailing list; a
NetBSD interviewee said it is "bad style to have technical discussions there, since it is no
public service and not documented later". The practice that reconciled the two was posting a
summary of a chat discussion back to the list. Evidence type: qualitative interviews.

### Collocated commercial teams, 2010: IM versus the issue tracker

Bertram, Voida, Greenberg and Walker 2010, "Communication, collaboration, and bugs: the social
nature of issue tracking in small, collocated teams", read in full (author's copy; the corpus
already cites it in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#this-predates-coding-agents)).
CSCW 2010. Fifteen participants across four North American teams, questionnaire plus
semi-structured interview, grounded-theory analysis. The details relevant here go beyond the
"knowledge repository" summary the corpus already carries: participants copied "portions of
instant messenger conversations or email threads, summaries of face-to-face meetings, and
even self-reflective notes" into the issue; the comment history was "often favored over other
channels, such as instant messaging, that were viewed to be more interrupting for less urgent
and timely messages", because IM systems "alert, flash, and otherwise grab their users'
attention", so "the case itself served as a persistent, asynchronous, and oftentimes
multicast communication channel"; and "each issue was treated much like a threaded chat room
conversation in which the comment history formed the body of the conversation and the issue
itself provided the topic". A participant on the comment history: "You can just see a history
and figure out what the decision pattern was … Just having this record is invaluable" (P04).
Evidence type: qualitative interviews, four teams.

Source: <https://amy.voida.com/wp-content/uploads/2013/04/issueTracking-cscw10.pdf>.

### ChatOps, 2011–2013: putting the work into the chat room

**GitHub, "Say hello to Hubot"**, 25 October 2011, read in full (GitHub blog). Announces the
open-sourcing of Hubot, GitHub's Campfire bot, which "ships our code" and is the "interface
to our CI server", and is described as "part of our culture". Evidence type: vendor
announcement.

**Newland 2013, "ChatOps at GitHub"**, slide deck of 7 February 2013, read in full
(Speaker Deck). The abstract claims that running operations through Hubot in chat "increased
our awareness of what other GitHubbers are working on and the speed at which new team
members learn common practices". Slides: "Everyone sees all of that happen on their first
day"; "Everyone is pairing all of the time"; "Teaching by doing … by making things visible"
(attributed to @rtomayko); and a slide headed "THINGS I HAVEN'T ASKED RECENTLY" listing
"how's that deploy going? are you deploying that or should I? is that branch green?" The
awareness claim is that automation actions issued in a shared room make the *state* of
deploys and branches visible as a side effect of doing the work — Dourish and Bellotti's
shared feedback and Gutwin's feedthrough, produced by an automated actor. Evidence type:
testimonial, no measurement.

Sources: <https://github.blog/news-insights/say-hello-to-hubot/>;
<https://speakerdeck.com/jnewland/chatops-at-github>.

### Slack era, 2016–2025: "where knowledge goes to die" and the tracker's counter-positioning

**The phrase.** A Hacker News Algolia search found "Slack is where documentation goes to
die" on 2019-09-18 (item 21001771), "Slack is where data goes to die" on 2022-07-15 (item
32106823) and "Discord is where knowledge goes to die" on 2023-06-14 (items 36327251 and
36328986). The origin of the exact wording "Slack is where knowledge goes to die" was not
found (one WebSearch spent; see Dead ends). Evidence type: discourse, dated by forum
timestamps.

**Atlassian Community, "Slack is where context goes to die"** (Evan Fishman, 6 August 2025),
read in full. States the working mantra "Slack is where the conversation takes place,
Confluence is where it is documented". Evidence type: practitioner post on a vendor forum.

**Slack, "Prevent brain drain"** (Slack blog, knowledge management), read in full; date not
extracted from the page. Claims "workers spend 33% of their time searching for information,
according to Slack's Workforce Lab" and recommends "Work 'out loud' by defaulting to
channels". Evidence type: vendor marketing citing its own survey; the 33 per cent figure is
not traceable to a method on the page.

**Jira Cloud for Slack** (Slack app directory listing), read in full. Positions the tracker as
the durable side: "Jira is where people and AI agents come together …"; "Keep comments in
sync by pushing Slack conversations to Jira comments, so conversation context stays attached
to the work"; and offers to "hand it off to an agent". **GitHub for Slack** (integration
README and product page), read in full: "full visibility into your GitHub projects right in
Slack channels" via subscriptions and notifications. Both vendors thus sell the same
reconciliation the 2004 open-source developers did by hand — chat for the live exchange,
with a copy pushed to the durable object — and both now name an agent as a party to the
hand-off. Evidence type: vendor positioning.

**Alkadhi, Lata, Guzman and Bruegge 2017**, "Rationale in development chat messages: an
exploratory study", read in full (arXiv). MSR 2017, pp. 436–446, doi:10.1109/MSR.2017.43.
8,702 HipChat messages from three student teams of eight to nine; 9 per cent of messages
contained rationale, and for 48 per cent of the issues discussed the chat contained the
complete rationale. Cited here as the one measurement found of how much decision content
actually lives in chat. Evidence type: measured, student teams.

Sources: <https://hn.algolia.com/api/v1/search?query=%22where%20knowledge%20goes%20to%20die%22>
(items 21001771, 32106823, 36327251, 36328986);
<https://community.atlassian.com/forums/Teamwork-Lab-Improving-our-ways/Slack-is-where-context-goes-to-die/td-p/3084304>;
<https://slack.com/blog/productivity/knowledge-management-in-slack>;
<https://slack.com/apps/A2RPP3NFR-jira-cloud>; <https://github.com/integrations/slack>;
<https://arxiv.org/pdf/1704.08500>.

## An automated actor as a participant

### Storey and Zagalsky 2016 — "Disrupting developer productivity one bot at a time"

Read in full (author's copy via Wayback). FSE 2016 Visions and Reflections, pp. 928–931,
doi:10.1145/2950290.2983989.

A position paper. Bots "serve as a conduit or an interface between users and services,
typically through a conversational user interface", in pull mode, push mode or both. Under
"Support team cognition" the paper quotes Poppendieck's "team with the most situational
awareness wins" and observes that "Many Bots already help team members know when commits
were made, which tests and services failed, and when other services or builds are deployed".
The reflective half lists possible harms: bots "may cause team members to spend less time
together, reducing the chances for serendipitous learning and discovery"; bots used to avoid
interruptions "may bring other interruptions or distractions that are not as obvious
initially"; and generated documentation may not be read or trusted once known to be
generated. Bots are called "new virtual team members" but are analysed as channels through
which humans become aware of systems, not as actors whose own activity must be made visible.
Evidence type: argument.

Source: <https://web.archive.org/web/20220709205452id_/http://chisel.cs.uvic.ca/pubs/storey-FSE-VaR2016.pdf>.

### Wessel et al. 2018, 2021, and the "quality gatekeepers" study

**Wessel, de Souza, Steinmacher, Wiese, Polato, Chaves and Gerosa 2018**, "The power of
bots: characterizing and understanding bots in open source software projects", abstract only
(Crossref). *PACM HCI* 2(CSCW), doi:10.1145/3274451. Of 351 projects studied, 93 (26 per
cent) used bots; 228 people surveyed; no consistent, significant before/after difference in
activity indicators after bot adoption. **Wessel, Wiese, Steinmacher and Gerosa 2021**,
"Don't disturb me: challenges of interacting with software bots on open source software
projects", abstract only, doi:10.1145/3476042: 21 interviews; noise — bots producing more
notifications than value — is the central challenge. **Wessel et al., "Quality
gatekeepers"**, abstract only (arXiv:2103.13547): a regression-discontinuity design on 1,194
projects plus 12 interviews; bot adoption increased merged pull requests and decreased
communication on them. Evidence type: measured (2018, gatekeepers), qualitative (2021);
abstracts only.

Sources: <https://doi.org/10.1145/3274451>; <https://doi.org/10.1145/3476042>;
<https://arxiv.org/abs/2103.13547>.

### Erlenhov, Gomes de Oliveira Neto and Leitner 2020 — personas of bot users

Abstract only (arXiv:2005.13969). FSE 2020, "An empirical study of bots in software
development: characteristics and challenges from a practitioner's perspective". 21
interviews and 111 survey responses; three personas of developers by their expectations of
bots; noise and trust are the challenges named. Evidence type: qualitative plus survey;
abstract only.

Source: <https://arxiv.org/abs/2005.13969>.

### Treude and Poskitt 2024, and Rooijendijk, Treude and Wessel 2026

**Treude and Poskitt 2024**, "Bot-driven development: from simple automation to autonomous
software development bots", read in full (arXiv:2411.16100). A position paper proposing that
bots move from responders to drivers of development, with the human as navigator; it does not
report data on what such a bot's activity would need to make visible.

**Rooijendijk, Treude and Wessel 2026**, registered report (arXiv:2606.28125), read in full.
Proposes a study of 33,078 agent-authored pull requests across 2,807 repositories
(AIDev-pop); tangential to awareness, cited only as evidence that the agent-authored PR is
now a measurable unit. Evidence type: protocol, no results yet.

Sources: <https://arxiv.org/abs/2411.16100>; <https://arxiv.org/abs/2606.28125>.

### What the bot literature does and does not treat

Across Storey and Zagalsky, Wessel and Erlenhov, the automated actor appears in two roles:
as a *channel* (it tells humans about builds, deploys, and commits — Gutwin's feedthrough
delivered by push) and as a *noise source* (its notifications compete with human ones for
attention). The Gutwin present-tense elements — is the actor present, what artifact is it on,
what is it doing, what is its intention — are applied by these papers to human participants
only. The ChatOps testimony is the closest to treating the bot's own actions as awareness
content ("is that branch green?" answered by seeing the bot act), but that is because the bot
executed a human's command in a shared room; the human's intention was already visible. No
source found in this pass presents a study of humans maintaining awareness of an autonomous
actor's who/what/where in a codebase.

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where the existing notes touch it |
| --- | --- | --- | --- |
| Awareness is "an understanding of the activities of others, which provides a context for your own activity"; mechanisms are informational, role-restrictive, and shared feedback; groups move continually between loose and tight coupling | Dourish and Bellotti 1992 (full text) | Qualitative observation of four groups; argument | No counterpart |
| Workspace awareness is "up-to-the-moment understanding of another person's interaction with a shared workspace"; elements are who/what/where in present and past; the future is excluded as inference | Gutwin and Greenberg 2002 (full text) | Framework from prior observation | [adjacent-literatures.md, situation awareness](adjacent-literatures.md#situation-awareness-and-the-out-of-the-loop-problem) carries the human-factors analogue (Endsley); no CSCW counterpart |
| Ninety-one awareness-support papers classified by the Gutwin framework; coordination most supported, communication least | Steinmacher, Chaves and Gerosa 2013 (abstract) | Systematic mapping | No counterpart |
| Design mirrors communication structure; formal coordination reaches only as far as foresight; collocated developers "know who is around and if they are available" | Conway 1968; Herbsleb and Grinter 1999; MacCormack et al. (all full text) | Argument; interviews; measured five pairs | No counterpart |
| Informal interpersonal coordination is valued most under uncertainty and formal techniques are valued less than their use predicts; "other project members" are the top help source; coordination success correlates 0.61 with client satisfaction | Kraut and Streeter 1995 (scan, pages read as images) | Measured survey, 563 respondents | No counterpart |
| Distributed MRs take about 2.5× longer because more people are involved; "I lose time trying to figure out who to contact"; presence awareness via IM and calendars | Herbsleb and Mockus 2003 (full text) | Measured archival plus survey | [unfamiliar-code-and-shared-models.md, team cognition](unfamiliar-code-and-shared-models.md#team-cognition-research) cites the Espinosa et al. 2007 abstract on presence awareness |
| Coordination requirements are volatile; congruence between them and actual communication cuts resolution time and failure probability (18.6 per cent and 7.6 per cent); a dynamic "buddy list" is proposed | Cataldo et al. 2006; Cataldo and Herbsleb 2013 (full text) | Measured, two projects | No counterpart |
| The awareness network is fluid and misidentified in both directions; newcomers infer experts from check-in emails | de Souza and Redmiles 2007 (full text), 2011 (abstract) | Ethnography | [unfamiliar-code-and-shared-models.md, knowledge as footprint](unfamiliar-code-and-shared-models.md#knowledge-as-footprint-ownership-succession-loss) covers expertise inferred from authorship; the network concept has no counterpart |
| Push-mode awareness of parallel changes; two laboratory experiments showed earlier conflict detection | Sarma et al. 2003 (full text); Sarma, Redmiles and van der Hoek 2012 (abstract) | Design; laboratory experiment | No counterpart |
| Developers most want work-item assignments, bug descriptions, and checked-out/edited file state; a six-person deployment raised SART ratings and status communication | Biehl et al. 2007 (full text) | Survey of 90; pre/post field study of six | No counterpart |
| Dashboards give pull-mode high-level overview and are not found distracting; feeds are a small-scale inbox; 26 of 32 would not change practice | Treude and Storey 2010 (full text) | Artifact counts, survey of 119, nine interviews | [chat-centric-agents-vs-team-sdlc.md, attach sessions to the work graph](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph) discusses issue-centric agent surfaces without the dashboard-versus-feed distinction |
| Dashboards favour numbers over text, omit context, do not explain, and invite gaming | Storey and Treude 2019 (full text) | Argument | [track-measurement.md, arguments against measuring](track-measurement.md#arguments-against-measuring) |
| GitHub feeds let users infer project liveness, dependencies, and needs from visible events | Dabbish et al. 2012 (full text) | 24 interviews | No counterpart |
| "What have my coworkers been doing?" is the second most sought need, obtained from coworkers and email, and rated unimportant because it is so easily obtained | Ko, DeLine and Venolia 2007 (full text) | Measured observation, 17 developers; survey of 42 | [evidence-and-mechanisms.md, program comprehension](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of) cites the same paper for "why" questions only |
| Open-source awareness is maintained by overhearing on lists and chat; technical decisions are kept off unarchived chat and summarised back to the list | Gutwin, Penner and Schneider 2004 (full text) | 14 interviews | [chat-centric-agents-vs-team-sdlc.md, transcript is local state](chat-centric-agents-vs-team-sdlc.md#a-transcript-is-local-interaction-state-not-durable-team-state) states the same point for agent transcripts |
| Collocated teams pasted IM into the issue and preferred its comment history because IM interrupts; each issue is "a threaded chat room" with the issue as topic | Bertram et al. 2010 (full text) | 15 participants, four teams | [chat-centric-agents-vs-team-sdlc.md, this predates coding agents](chat-centric-agents-vs-team-sdlc.md#this-predates-coding-agents) cites the knowledge-repository finding |
| ChatOps claimed shared-room automation raised awareness of what others are working on ("is that branch green?") | GitHub 2011; Newland 2013 | Testimonial | [track-rationale-as-artifact.md, multiplayer threads](track-rationale-as-artifact.md#multiplayer-human-plus-agent-threads-elsewhere) covers the agent-era shared-room products |
| "If Slack is taken out … We're blind"; chat rated most important by about 15 per cent; fragmentation is the stated challenge | Lin et al. 2016; Storey et al. 2017 (full text) | Surveys of 104 and 1,449 | [understanding-bottleneck-talk.md, shared spaces](understanding-bottleneck-talk.md#proposal-4-shared-spaces) records Litt's "one-on-one conversations to Slack channels" |
| "Slack is where context goes to die"; trackers position themselves as where "context stays attached to the work" and name an agent as a hand-off party | Atlassian Community 2025; Slack app listing; GitHub for Slack | Discourse; vendor positioning | [chat-centric-agents-vs-team-sdlc.md, attach sessions](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph) covers Linear and GitHub agent surfaces |
| 9 per cent of chat messages carry rationale; 48 per cent of issues have complete rationale in chat | Alkadhi et al. 2017 (full text) | Measured, student teams | [track-rationale-as-artifact.md, capture cost versus use](track-rationale-as-artifact.md#design-rationale-capture-cost-versus-use) |
| Bots are conduits that tell humans about commits, failed tests, and deploys; possible harms are less serendipitous learning and new interruptions | Storey and Zagalsky 2016 (full text) | Argument | No counterpart |
| 26 per cent of 351 projects used bots with no consistent activity change; noise is the central complaint; bots raise merged PRs and lower communication | Wessel et al. 2018, 2021, gatekeepers (abstracts) | Measured; interviews | No counterpart |
| No source studies humans maintaining awareness of an autonomous actor's who/what/where | This pass | Absence | [chat-centric-agents-vs-team-sdlc.md, make the session multiplayer](chat-centric-agents-vs-team-sdlc.md#1-make-the-session-multiplayer) records the Claude Code issues asking for a registry of live sessions |

"No counterpart" means no note in this directory addresses the point; it is a statement about
the notes, not about the wider literature.

## Dead ends

- Sarma, Redmiles and van der Hoek 2012 (Palantír, TSE) full text: the UNL Digital Commons
  copy returns a Cloudflare "Just a moment" challenge; IEEE Xplore returns an empty 202;
  dl.acm.org returns 403; CiteSeerX's current URLs return 404. Abstract via OpenAlex only.
- de Souza and Redmiles 2011 (TSE) full text not reached; abstract via OpenAlex.
- Steinmacher, Chaves and Gerosa 2013 full text: Springer redirects to an identity-provider
  page; abstract taken from a 2019 Wayback capture of the article page.
- Frost 2007 (IEEE Software) full text not reached; abstract via OpenAlex.
- Wessel et al. 2018 full text: dl.acm.org 403; abstract via Crossref. Wessel et al. 2021 and
  the "quality gatekeepers" paper read as abstracts only.
- Erlenhov, Gomes de Oliveira Neto and Leitner 2020: abstract only; the FSE PDF was not
  fetched.
- Colfer and Baldwin, "The mirroring hypothesis: theory, evidence and exceptions", HBS
  Working Paper 16-124: the HBS PDF returns 403. The mirroring evidence is cited from
  MacCormack, Rusnak and Baldwin instead.
- hci.usask.ca and the GroupLab publication URLs for the Gutwin papers return 404; both were
  recovered through the Wayback CDX index.
- Kraut and Streeter 1995 exists online only as a poor scan (568 words of OCR); pages were
  rendered and read as images, so only the pages named above were read.
- Ko, DeLine and Venolia 2007: the text layer drops digits; the two tables were read as
  rendered images.
- Semantic Scholar returned 429 intermittently; OpenAlex free-text search was noisy and only
  direct DOI lookups were used.
- The origin of the exact phrase "Slack is where knowledge goes to die" was not found; the
  earliest dated variants located are the 2019, 2022 and 2023 Hacker News items above. One
  WebSearch was used for this (`"Slack is where knowledge goes to die"`).
- The Slack "Prevent brain drain" page carries no visible publication date; the 33 per cent
  figure is attributed to Slack's Workforce Lab without a method.
- Downloaded but not read for this note: Sarma et al. 2009 (Tesseract), Dabbish et al. 2013
  (leveraging transparency), Marlow, Dabbish and Herbsleb 2013 (impression formation),
  Espinosa et al. 2002 (shared mental models), Herbsleb, Mockus, Finholt and Grinter 2000
  (distance), Herbsleb and Grinter 1999 (splitting the organization), Grinter, Herbsleb and
  Perry 1999 (geography of coordination), Cataldo et al. 2008 (communication patterns).

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Alkadhi, R., Lata, T., Guzman, E., Bruegge, B. (2017). Rationale in development chat
  messages: an exploratory study. MSR 2017, 436–446, doi:10.1109/MSR.2017.43. Full text
  (arXiv 1704.08500).
- Atlassian Community (Fishman, E.), 6 August 2025. Slack is where context goes to die. Full
  text.
- Bertram, D., Voida, A., Greenberg, S., Walker, R. (2010). Communication, collaboration, and
  bugs: the social nature of issue tracking in small, collocated teams. CSCW 2010. Full text
  (author's copy).
- Biehl, J. T., Czerwinski, M., Smith, G., Robertson, G. G. (2007). FASTDash: a visual
  dashboard for fostering awareness in software teams. CHI 2007, 1313–1322,
  doi:10.1145/1240624.1240823. Full text (Microsoft Research copy).
- Cataldo, M., Wagstrom, P. A., Herbsleb, J. D., Carley, K. M. (2006). Identification of
  coordination requirements: implications for the design of collaboration and awareness
  tools. CSCW 2006. Full text (author's copy).
- Cataldo, M., Herbsleb, J. D., Carley, K. M. (2008). Socio-technical congruence: a framework
  for assessing the impact of technical and work dependencies on software development
  productivity. ESEM 2008. Full text (author's copy).
- Cataldo, M., Herbsleb, J. D. (2013). Coordination breakdowns and their impact on
  development productivity and software failures. *IEEE TSE* 39(3):343–360. Full text
  (author's copy).
- Conway, M. E. (1968). How do committees invent? *Datamation*, April 1968. Full text (author's
  page, reprinted by permission).
- Dabbish, L., Stuart, C., Tsay, J., Herbsleb, J. (2012). Social coding in GitHub:
  transparency and collaboration in an open software repository. CSCW 2012. Full text
  (author's copy).
- de Souza, C. R. B., Redmiles, D. F. (2007). The awareness network: to whom should I display
  my actions? And, whose actions should I monitor? ECSCW 2007, 99–117,
  doi:10.1007/978-1-84800-031-5_6. Full text (Wayback capture of the proceedings PDF).
- de Souza, C. R. B., Redmiles, D. F. (2011). The awareness network, to whom should I display
  my actions? And, whose actions should I monitor? *IEEE TSE* 37(3):325–340,
  doi:10.1109/TSE.2011.19. Abstract only.
- Dourish, P., Bellotti, V. (1992). Awareness and coordination in shared workspaces. CSCW
  '92, 107–114. Full text (author's copy).
- Erlenhov, L., Gomes de Oliveira Neto, F., Leitner, P. (2020). An empirical study of bots in
  software development: characteristics and challenges from a practitioner's perspective. FSE
  2020, arXiv:2005.13969. Abstract only.
- Frost, R. (2007). Jazz and the Eclipse way of collaboration. *IEEE Software* 24(6):114–117,
  doi:10.1109/MS.2007.170. Abstract only.
- GitHub (2011). Say hello to Hubot. GitHub blog, 25 October 2011. Full text.
- GitHub. GitHub for Slack (integration README and product page). Full text.
- Gutwin, C., Greenberg, S. (2002). A descriptive framework of workspace awareness for
  real-time groupware. *Computer Supported Cooperative Work* 11(3):411–446,
  doi:10.1023/A:1021271517844. Full text (Wayback capture of the author's copy).
- Gutwin, C., Penner, R., Schneider, K. (2004). Group awareness in distributed software
  development. CSCW 2004, 72–81, doi:10.1145/1031607.1031621. Full text (Wayback capture of
  the author's copy).
- Hacker News (Algolia search), items 21001771 (2019), 32106823 (2022), 36327251 and 36328986
  (2023). Discourse; dated by forum timestamps.
- Herbsleb, J. D., Grinter, R. E. (1999). Architectures, coordination, and distance: Conway's
  law and beyond. *IEEE Software*, September/October 1999. Full text (author's copy).
- Herbsleb, J. D., Mockus, A. (2003). An empirical study of speed and communication in
  globally distributed software development. *IEEE TSE* 29(6):481–494. Full text (author's
  copy).
- Ko, A. J., DeLine, R., Venolia, G. (2007). Information needs in collocated software
  development teams. ICSE 2007, 344–353. Full text (author's copy; two pages read as images).
- Kraut, R. E., Streeter, L. A. (1995). Coordination in software development. *CACM*
  38(3):69–81, doi:10.1145/203330.203345. Scanned copy via Wayback; pages 4, 7, 8 and 9 read
  as images.
- Lin, B., Zagalsky, A., Storey, M.-A., Serebrenik, A. (2016). Why developers are slacking
  off: understanding how software teams use Slack. CSCW 2016 Companion, 333–336,
  doi:10.1145/2818052.2869117. Full text (Wayback capture of the CHISEL group's copy).
- MacCormack, A., Rusnak, J., Baldwin, C. Y. Exploring the duality between product and
  organizational architectures: a test of the "mirroring" hypothesis. HBS Working Paper
  08-039; published in *Research Policy* 41(8), 2012. Full text (working paper).
- Newland, J. (2013). ChatOps at GitHub. Slide deck, 7 February 2013, Speaker Deck. Full text
  of slides.
- Rooijendijk, R., Treude, C., Wessel, M. (2026). Registered report, arXiv:2606.28125. Full
  text.
- Sarma, A., Noroozi, Z., van der Hoek, A. (2003). Palantír: raising awareness among
  configuration management workspaces. ICSE 2003, 444–454, doi:10.1109/ICSE.2003.1201222.
  Full text (Wayback capture of the author's copy).
- Sarma, A., Redmiles, D. F., van der Hoek, A. (2012). Palantír: early detection of
  development conflicts arising from parallel code changes. *IEEE TSE* 38(4):889–908,
  doi:10.1109/TSE.2011.64. Abstract only.
- Slack. Jira Cloud for Slack (app directory listing); Prevent brain drain (Slack blog).
  Full text; vendor.
- Steinmacher, I., Chaves, A. P., Gerosa, M. A. (2013). Awareness support in distributed
  software development: a systematic review and mapping of the literature. *Computer
  Supported Cooperative Work* 22(2–3):113–158, doi:10.1007/s10606-012-9164-4. Abstract only.
- Storey, M.-A., Treude, C. (2019). Software engineering dashboards: types, risks, and
  future. In Sadowski, C., Zimmermann, T. (eds.), *Rethinking Productivity in Software
  Engineering*, ch. 16, doi:10.1007/978-1-4842-4221-6_16. Full text.
- Storey, M.-A., Zagalsky, A. (2016). Disrupting developer productivity one bot at a time.
  FSE 2016 Visions and Reflections, 928–931, doi:10.1145/2950290.2983989. Full text (Wayback
  capture of the CHISEL group's copy).
- Storey, M.-A., Zagalsky, A., Figueira Filho, F., Singer, L., German, D. M. (2017). How
  social and communication channels shape and challenge a participatory culture in software
  development. *IEEE TSE* 43(2):185–204. Full text (author's copy).
- Treude, C., Figueira Filho, F. (2019). How team awareness influences perceptions of
  developer productivity. In Sadowski, C., Zimmermann, T. (eds.), *Rethinking Productivity
  in Software Engineering*, ch. 15, doi:10.1007/978-1-4842-4221-6_15. Full text.
- Treude, C., Poskitt, C. M. (2024). Bot-driven development: from simple automation to
  autonomous software development bots. arXiv:2411.16100. Full text.
- Treude, C., Storey, M.-A. (2010). Awareness 2.0: staying aware of projects, developers and
  tasks using dashboards and feeds. ICSE 2010, doi:10.1145/1806799.1806854. Full text
  (author's copy).
- Wessel, M., de Souza, B. M., Steinmacher, I., Wiese, I. S., Polato, I., Chaves, A. P.,
  Gerosa, M. A. (2018). The power of bots: characterizing and understanding bots in open
  source software projects. *PACM HCI* 2(CSCW), doi:10.1145/3274451. Abstract only.
- Wessel, M., Wiese, I., Steinmacher, I., Gerosa, M. A. (2021). Don't disturb me: challenges
  of interacting with software bots on open source software projects. *PACM HCI* 5(CSCW2),
  doi:10.1145/3476042. Abstract only.
- Wessel, M., et al. Quality gatekeepers: investigating the effects of code review bots on
  pull request activities. arXiv:2103.13547. Abstract only.
