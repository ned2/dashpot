---
status: research
date: 2026-09-13
---

# Unfamiliar code and shared models

Research date: 2026-09-13

This note documents the pre-AI literature and practice on two questions the AI-era
cognitive-debt material takes for granted: how a person builds a model of code they did not
write (onboarding, legacy code, reverse engineering, code reading), and how a team holds a
model in common (Naur's theory-holding team, ubiquitous language, shared and transactive
mental models, ownership and truck factor, pair, mob, inspection and review as transfer). It
is documentary: it records what the sources found, with their evidence and limits, and maps
each finding to where the existing notes in this directory touch it. It does not evaluate fit
for Dashpot or any tool. Terminal citations are primary — the paper, the author's copy, the
book's own sample or reference text — and every figure is reported as the source states it.
Items read only as abstract or metadata are marked; anything recalled rather than read is
marked unverified. Where an earlier note already covers a source, this note links to it rather
than repeating it: the Naur summary and classic comprehension models are in
[evidence-and-mechanisms.md](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of),
the tool-evaluation studies (Storey 2000, Ko 2006, Lawrance 2010, Roehm 2012 in brief) in
[track-explorable-maps.md](track-explorable-maps.md#evidence), the documentation-staleness
surveys in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#documentation-use-and-staleness),
and the authorship-based knowledge metrics (Expertise Browser, degree-of-knowledge, truck
factor, Jabrayilzade) in
[track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure)
and [track-measurement.md](track-measurement.md#proxies-and-telemetry).

## Finding

The pre-AI literature answers "how do you build a model of code you did not write" with one
consistent observation across four decades and three research traditions: the model is built
socially and by doing, not by reading. Every onboarding study that watched real newcomers —
Sim and Holt's four compiler-team immigrants (1998), Begel and Simon's eight Microsoft hires
(2008), Dagenais et al.'s eighteen IBM project-joiners (2010), Ju et al.'s 32 Microsoft
movers (2021) — found the same sequence: get the thing to build and run, take a small
isolated task, ask a person as soon as reading stalls, and accept that a working model of a
large system takes months (six to twelve by the compiler team's estimate, "around six months"
in Google's own account, roughly 15 months to full productivity in Mockus and Herbsleb's
learning-curve data). Professionals in the field studies "try to avoid comprehension whenever
possible", trust code over documentation (21 of 28 observed developers), prefer asking a
colleague to reading (17 of 28), take transient notes that are never archived, and use no
dedicated comprehension tool in any of 28 observed sessions (Maalej et al. 2014); logged over
3,148 working hours they spend 58% of their time comprehending, falling from 66% for
developers with under three years' experience to 44% for those with more than five (Xia et
al. 2018). The question catalogues that mark what a comprehender is trying to find out —
Sillito's 44 questions from newcomers and professionals, LaToza and Myers' 94 hard-to-answer
questions from 179 Microsoft developers — put rationale ("Why was it done this way?", 42
reports, the largest category) and intent at the top and note that the usual answer, "ask an
expert teammate", fails "when the teammate has left the company". The literature's methods
for building a model without an author to ask — Feathers' characterisation tests and scratch
refactoring, Biggerstaff's design recovery, Rugaber's synchronized refinement, Hermans' and
the Code Reading Club's structured reading, Spinellis' code reading — are practitioner or
research proposals whose only evaluations are of navigation aids on the program layer, not of
whether a situation model or rationale is recovered. On the second question, how a team holds
a shared model, Naur's 1985 text (read here from a primary reprint) locates the theory in the
team and states that revival "merely from the documentation, is strictly impossible"; his
Case 1 shows a documented compiler degraded within ten years of losing its authors' advice.
Evans' own pattern summary makes the team's spoken language the model's carrier and treats
knowledge leaking when people move on as the default condition of projects. Team-cognition
research supports the general claim (DeChurch and Mesmer-Magnus 2010: team cognition
correlates ρ = .38 with performance over 65 studies, strongest for project teams and for
distributed "who knows what" knowledge, ρ = .62 with process), while the one longitudinal
software-team study found mental models did not converge over time as role differentiation
reduced interaction (Levesque et al. 2001, abstract only). The practices that measurably
spread the model are review and pairing: peer review raised the number of files a median
developer "knows" by 66% to 150% across five Microsoft and Google products (Rigby and Bird
2013); pair programming with a novice driving transfers detail at the cost of speed (Plonka
et al. 2015, six observed teaching strategies); Fagan's 1976 inspection process listed
"education" as an explicit objective of its overview and preparation stages and was used as
the formal event for transferring code between programmers. What departure costs is
measured only by footprint: 16% of 1,932 popular GitHub projects lost all their truck-factor
developers and 41% of those survived (Avelino et al. 2019); Avaya and Chrome abandoned a
median of ~130 files per quarter, with the largest losses where a file had no co-change
successor (Rigby et al. 2016). Nothing in this literature measures the model itself; the
instruments are questionnaires about structural facts (Fritz et al. 2007), dyadic
agreement ratings, or authorship counts, and the AI-era notes inherit that gap. The
correspondence that matters for the AI-era reading is exact in one place and absent in
another: the newcomer who joins a team whose authors left, the maintainer of a "dead"
program, and the reviewer of a colleague's change are the pre-AI figures closest to a
developer receiving agent-written code, and the literature says they succeed through a
mentor, a small task, and running the code — not through a document; but no pre-AI source
addresses the case where the code's only author was never a person who could be asked,
and no AI-era note found in this directory addresses onboarding, mentoring, or team-level
model sharing at all.

## Onboarding and newcomers

Each entry: design and sample, what newcomers did to build a model, what helped or
hindered, how it was measured, access level.

### Sim and Holt 1998 — "The ramp-up problem"

Exploratory multi-case study of four "software immigrants" joining one team maintaining a
roughly fifteen-year-old compiler (~250,000 lines, ~1,000 files, twelve major releases, team
growing from ~10 to ~20) at "a very large computer company". Structured tape-recorded
interviews February–June 1997: two newcomers every three weeks for four months from
arrival, two others once at seven and eight months. Senior developers estimated "six to
twelve months for a new team member to become fully productive". Seven patterns, in the
authors' words: "Mentoring is an effective, though inefficient, way to teach immigrants about
the software system" (mentors spent "many hours a day" for about two weeks, tapering to "a
short question every two days or so" by four months); "Lack of documentation forces
software immigrants to rely on mentors" ("Most people operate under the assumption that there
are no documents, so you shouldn't try asking for one"); administrative and environment
frustration dominated ("in no case did they describe [comprehending the system] as
frustrating. In contrast, frustration was a word that every respondent used with respect to at
least one system administration task"); first tasks came at two to four weeks and were
mentor-screened and isolated ("modifying, maybe three or four files ... It allowed me to gain
familiarity with at least those four files"); mentors passed on low-level, immediately useful
information rather than design concepts; and "Programmers who prefer to use bottom-up
comprehension approaches have a smoother naturalization" — the three who read source and
profiled one subsystem at a time settled faster than the one who wanted a top-down view
first. At four months one newcomer summarised the model reached: "I can read the code and
understand it. ... I know where to look for problems, and that's half the battle and I know
who to consult, when I don't." A pilot course built from two hours of videotaped senior talks
plus the Software Bookshelf architecture tool was judged by its three participants not
"directly applicable" four months later, though they "often thought about the concepts".
Measures: interview coding across seventeen variables and a cross-case matrix; no
comprehension test. Sim, S. E. and Holt, R. C. *ICSE 1998*,
[doi:10.1109/ICSE.1998.671389](https://doi.org/10.1109/ICSE.1998.671389); full text read
from a course copy at
[users.ece.utexas.edu](http://users.ece.utexas.edu/~perry/education/382v-s08/papers/sim98.pdf).

### Begel and Simon 2008 — "Novice software developers, all over again" and "Struggles of new college graduates"

Direct-observation case study of eight new Microsoft developers (hired one to seven months
earlier, minimal industry experience), each shadowed for 6–11 hours over two two-week
periods with a month between, plus daily video-diary answers to scaffolded questions; 85
observation hours in total; grounded-theory coding of task and subtask. What they did:
communication dominated most subjects' time; reading documentation "in a variety of sources"
came next for several and was described as "a result of flailing in other efforts"; all were
observed reproducing bugs; they navigated and searched code "a process often difficult for
them to effectively manage", copied code from the team codebase and MSDN samples, and added
comments to code they were only reading. Newcomers in the ICER paper's scenarios "read
through code in the product that is similar to the new feature to copy from" and "ask
questions of co-workers to understand the source code and the root cause of the bug". What
helped: asking people ("You can figure out something in five minutes by asking someone
instead of spending a day of looking through code and design docs"), peer mentoring between
two simultaneous hires, mentors who modelled behaviour rather than pointing at documents.
What hindered: fear that asking reveals ignorance, an official mentor who was "quite busy ...
often simply pointed Subject V at resources and documentation – sometimes incorrectly so",
and not recognising being stuck — the SIGCSE paper lists "I know when I am stuck" as a
misconception ("contrary to explicit observations ... NSDs almost always waste time, effort,
and money by flailing") alongside "If there was only more documentation" (more experienced
hires "desired information on people, i.e. who to go talk to"). Retrospective: "Many of the new
hires ... wished they had taken more time in the first few months to simply learn the system in
breadth and depth, rather than jumping straight into a project." Several were told "you are on
your own here" with respect to documentation because the original developers had left.
Measures: coded observation time per category, diary transcripts, exit interviews; five of
eight said at the end they could mentor a newcomer "only in the 'getting started' tasks".
Begel, A. and Simon, B. *ICER 2008*,
[doi:10.1145/1404520.1404522](https://doi.org/10.1145/1404520.1404522), author copy at
[microsoft.com](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icer-begel-2008.pdf);
*SIGCSE 2008*, [doi:10.1145/1352135.1352218](https://doi.org/10.1145/1352135.1352218),
author copy at
[microsoft.com](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/sigcse-begel-2008.pdf).
Both read in full.

### Dagenais, Ossher, Bellamy, Robillard and de Vries 2010 — "Moving into a new software project landscape"

Grounded-theory study of eighteen newcomers on eighteen IBM projects (team sizes 4–80,
joined one to twelve months earlier; sample skews to experienced developers joining ongoing
projects because brand-new hires and brand-new projects proved unsuitable), with a sketch
task, a one-hour interview, and seven validation re-interviews. Newcomers learned
architecture "only through exploration, i.e., questions, technical meetings and
experimentation"; low-level design and runtime behaviour were "often the least documented"
and were reached by "technical questions, actively search[ing] for code examples, and ...
trial and error"; design rationale came from questions and, where issue-tracking was strict,
from bug reports; they followed "trails" ("seeing the bugs that are closed so you can see the
corresponding changes ... that gives you an easy start to find out where are things located"),
copied and modified examples, and documented their own steps for the next person. Three
theory factors: *early experimentation* ("being able to compile your sources to run the
product ... from that point on, you can easily try to change things yourself"; one newcomer
committed a fix on day one, another in week one; the experimentation phase "rarely lasted
more than two weeks"); *internalizing structures and cultures* (tacit knowledge; "I think I
know, maybe five percent of the product ... when I have a bug, I know where to look and what
to do"); and *progress validation* (daily scrums "ensured that newcomers would not stay stuck
on a problem for more than a day"; code review gives "pointers and hints"). In teams without
validation, newcomers "would typically stay stuck on a problem for a few hours to a few days".
An architecture overview on day one "didn't really hit home until later"; environment-setup
waits ranged "from one week to two months"; the assistance and mentoring culture was "the
most influential [feature] in how pleasant and efficient ... the integration experience was".
Twelve of eighteen integrations were judged efficient and pleasant. Contrasts Sim and Holt:
the successful order was overview of structures, then low-level tasks. Measured by interview
coding and sketch content; no comprehension test. *ICSE 2010*,
[doi:10.1145/1806799.1806842](https://doi.org/10.1145/1806799.1806842); author copy at
[cs.mcgill.ca](http://www.cs.mcgill.ca/~martin/papers/icse2010.pdf), read in full.

### Ju, Sajnani, Kelly and Herzig 2021 — "A case study of onboarding in software teams: tasks and strategies"

Microsoft, two divisions: interviews with 32 developers who had joined a new team within
three months (22 transfers, 10 new hires) and 15 managers; constructivist grounded theory
over 61 task items; triangulating surveys of 189 developers (11.6% response) and 37
managers (4.9%). "Out of 61 task items, 41 (67%) led to learning." Knowledge channels:
task-related documentation (developers "seek answers from documentations before asking ...
frustrated when documentation cannot provide answers"), mentors or buddies (18 had one, 14
found them helpful; "new members can ask mentors 'dumb' questions freely"), technical
meetings. Fourteen developers said "learn the task's big picture first". Manager strategies:
Simple-to-Complex (12 managers, 14 developers; one manager's timeline — week 1 simple bugs
and configuration, weeks 2–4 small bugs to "get oriented in the codebase", three to nine
months to expert in one domain), Priority-First (2 managers, 12 developers, 8 of whom found
tasks "challenging"), Exploration-Based (6 developers, two of whom had not yet delivered when
interviewed). Ten managers treated *independence* as the onboarding end-point. Survey
agreement: documentation 90%, safe-to-ask environment 98%, frequent delivery builds
confidence 88%, frequent one-to-ones recommended by 95% of managers. Measured by
interview coding and Likert agreement. *ICSE 2021*,
[doi:10.1109/ICSE43902.2021.00063](https://doi.org/10.1109/ICSE43902.2021.00063); preprint
[arXiv:2103.05055](https://arxiv.org/abs/2103.05055), read in full. (The DOI in the task
brief, ...00036, resolves to an unrelated paper.)

### Rodeghero, Zimmermann, Houck and Ford 2021 — remote onboarding

Survey of 1,000 US Microsoft hires who started January–June 2020; 267 responses (26.7%),
eight confirmatory interviews. 61.9% said their challenges were pandemic-specific. Themes:
asking for help ("I don't like asking small, half-thought out questions virtually"), no channel
"where a new hire can at least watch and learn", documentation as "both an information glut
and an indexing dearth", environment setup ("close to 2 weeks ... there should have been a
stackoverflow sort of internal tool"). 67.7% were assigned a mentor; 58.1% had daily
one-to-ones. Recommendations: "Assign a simple first task", "Provide up-to-date
documentation", "Assign an onboarding buddy" separate from a technical mentor.
*ICSE-SEIP 2021*,
[doi:10.1109/ICSE-SEIP52600.2021.00013](https://doi.org/10.1109/ICSE-SEIP52600.2021.00013);
preprint [arXiv:2011.08130](https://arxiv.org/abs/2011.08130), read in full.

### Steinmacher et al. — newcomer barriers in open source

- **Systematic review (IST 2015).** 20 primary studies from 291 candidates; 15 barriers in
  five categories (social interaction, previous knowledge, finding a way to start,
  documentation, technical hurdles). "The most evidenced barriers are related to
  socialization, appearing in 75% (15 out of 20) of the studies." On finding a way to start,
  the review cites von Krogh et al.: "in 56.7% of the cases members of the community
  encouraged the new participants to find some part of the software architecture to work on
  ... In only 16.7% of the cases new participants were both encouraged to join and given
  specific technical tasks"; newcomers "tend to work more easily on new modules than on
  older ones"; and Midha et al. on 450 SourceForge projects: "cognitive [code] complexity has
  a strong negative influence on the number of contributions from new developers". The
  authors note "a lack of in-depth studies on technical issues, such as code issues".
  Steinmacher, Silva, Gerosa and Redmiles, *IST* 59:67–85,
  [doi:10.1016/j.infsof.2014.11.001](https://doi.org/10.1016/j.infsof.2014.11.001); author
  copy at [igor.pro.br](https://igor.pro.br/publications/journals-infsof-SteinmacherSGR15.pdf),
  read in full.
- **Social barriers (CSCW 2015).** Four sources — the review, nine students contributing for
  a course, a 24-answer questionnaire, and 36 interviews across 14 projects (11 experienced
  members, 16 successful newcomers, 6 dropouts, 3 in progress). Model of 58 barriers, 45
  technical ("running or developing environments' domain technologies and concepts,
  documentation, and source-code") and 13 social; counts per source, for example "Finding a
  mentor (3-3-2-5, 7 projects)". Cites Jensen et al.: "None of the newbies who failed to
  receive a reply within 24 hours of posting their first question were still posting."
  Steinmacher, Conte, Gerosa and Redmiles, *CSCW 2015*,
  [doi:10.1145/2675133.2675215](https://doi.org/10.1145/2675133.2675215); author copy at
  [igor.pro.br](https://igor.pro.br/publications/conf-cscw-SteinmacherCGR15.pdf), read in full.
- **FLOSScoach portal (ICSE 2016).** 65 undergraduates over two iterations, one month to make
  a code contribution to LibreOffice, JabRef, Amarok, Empathy, Vim or Audacity; matched then
  alternated assignment to portal or control; 46 analysed (control 19 of 34 = 56% completed;
  portal 24 of 31 = 77%). Control diaries showed "uncertainty and doubt on how to start
  (evidenced in 12 out of 19 diaries)"; one student cloned the wrong repository for about a
  third of his time. Portal users "felt more comfortable and were aware of the expected
  steps", but "Technical: barriers are still there, in both cases" — "difficulty understanding
  the architecture/code structure, understanding the code, problems finding the correct
  artifact to fix an issue, and ... local environment setup hurdles ... (in 32 out of 46)".
  Self-efficacy fell significantly in the control group (Wilcoxon p = 0.005) and not in the
  portal group; post-study portal > control (p = 0.013). Steinmacher, Conte, Treude and
  Gerosa, *ICSE 2016*,
  [doi:10.1145/2884781.2884806](https://doi.org/10.1145/2884781.2884806); author copy at
  [igor.pro.br](https://igor.pro.br/publications/conf-icse-SteinmacherCTG16.pdf), read in full.

### Mentoring and first-task evidence

- **Fagerholm, Sanchez Guinea, Münch and Borenstein (ESEM 2014).** A Facebook-sponsored
  programme: about 120 students on nine open-source projects with a three-day kick-off
  hackathon where mentors gave "familiarisation with the code base, tools, and procedures",
  then distributed teams of 4–8 with a project mentor and small initial tasks. Supported
  developers versus a random sample of unsupported peripheral developers over 16 weeks:
  weekly contribution speed t = 7.38 (critical 2.12 at 5%); total commits "about three times
  larger" (Kotlin 11 vs 5, Phabricator 26 vs 11, Rails 40 vs 17, Socket.IO 21 vs 9).
  [doi:10.1145/2652524.2652540](https://doi.org/10.1145/2652524.2652540); open copy at
  [hdl.handle.net/10138/153194](http://hdl.handle.net/10138/153194), read in full. (The brief's
  DOI resolves to a different paper.) The 2013 preliminary analysis (20 mentored vs 20
  random, 12 weeks: commits 64 vs 19, pull requests 111 vs 37)
  [arXiv:1311.1334](https://arxiv.org/abs/1311.1334), read in full.
- **Labuschagne and Holmes (MSR 2015), "Do onboarding programs work?"** Mozilla Bugzilla
  2001–2014 (395,347 bugs). Entrants via Good First Bug (75), mentored bugs (193), both
  (220), no programme (3,070); success = a non-obsolete patch on a FIXED bug. First-attempt
  success: mentored 80.1%, mentored and GFB 85.7%, GFB-only 67.1%; "fewer than 15% of
  participants make 10 or more contributions while more than 20% of non-participants" —
  programme entrants "half as likely to transition into long-term community members".
  Survey respondents (11 of 35) said mentorship "certainly helped me not get lost" and that
  "at first, it felt really odd to contribute by changing a single line of code".
  [doi:10.1109/MSR.2015.45](https://doi.org/10.1109/MSR.2015.45); author copy at
  [cs.ubc.ca](https://www.cs.ubc.ca/~rtholmes/papers/msr_2015_labuschagne.pdf), read in full.
- **Zhou and Mockus (ICSE 2012).** Gnome and Mozilla issue trackers; long-term contributor =
  stays three years and is productive. "Only 2.12% of Gnome and 0.90% of Mozilla joiners
  become LTCs"; more than 70% are one-time contributors; starting by commenting rather than
  reporting, or getting one reported issue fixed, "more than double their odds"; too-rapid
  responses reduced the odds by 28% (Mozilla) and 39% (Gnome).
  [doi:10.1109/ICSE.2012.6227164](https://doi.org/10.1109/ICSE.2012.6227164); author copy at
  [mockus.org](https://mockus.org/papers/willingness.pdf), read in full.
- **Canfora, Di Penta, Oliveto and Panichella (FSE 2012), "Who is going to mentor
  newcomers?"** Not obtained; the extended version in Panichella's 2014 thesis (ch. 7) reports
  top-1 mentor-recommendation correctness "above 80% except for Python ... 65%, and ...
  FreeBSD ... 30%" and that mentored newcomers had "at least, three time more chances to
  become LCTs". [doi:10.1145/2393596.2393647](https://doi.org/10.1145/2393596.2393647);
  thesis at [spanichella.github.io](https://spanichella.github.io/img/1_PhD-thesis.pdf).
  Figures are the thesis's, not the paper's.
- **Tan, Zhou and Sun (ESEC/FSE 2020), "A first look at good first issues on GitHub"**,
  [doi:10.1145/3368089.3409746](https://doi.org/10.1145/3368089.3409746), metadata only. The
  ICSE 2023 follow-up analysed 48,402 GFIs from 964 repositories: "~70% of GFIs have expert
  participation, with each GFI usually having one expert who makes two comments. Half of GFIs
  will receive their first expert comment within 8.5 hours"; "expert involvement positively
  correlates with newcomers' successful contributions but negatively correlates with
  newcomers' retention" ([arXiv:2302.05058](https://arxiv.org/abs/2302.05058), abstract;
  [doi:10.1109/ICSE48619.2023.00064](https://doi.org/10.1109/ICSE48619.2023.00064)).

### Google's account

Johnson and Senges (2010) interviewed 24 Google stakeholders on the onboarding programme
and report "legitimate peripheral participation" and peer learning; abstract only
([doi:10.1108/13665621011028620](https://doi.org/10.1108/13665621011028620)). The
practitioner account in *Software Engineering at Google* (ch. 3, Chen and Barolak; ch. 9,
Manshreck and Sadowski) states: "We tell Nooglers that ramping up can take around six
months"; the mentor is a volunteer "not on the same team as the mentee", "a safety net to
talk to if the mentee doesn't know whom else to ask"; "One of the biggest mistakes that
beginners make is not to ask for help when they're stuck"; readability began when "Craig
Silverstein (employee ID #3) would sit down in person with every new hire and do a
line-by-line 'readability review' of their first major code commit", and "Every changelist (CL)
requires readability approval"; "around 20% of Google engineers are participating in the
readability process at any given time" and "Around 1 to 2% ... are readability reviewers";
internal studies (no figures published) found CLs by authors with readability "take
statistically significantly less time to review and submit". Ch. 9: "Many engineers at
Google 'meet' other engineers first through their code reviews!"
([abseil.io ch. 3](https://abseil.io/resources/swe-book/html/ch03.html),
[ch. 9](https://abseil.io/resources/swe-book/html/ch09.html)). This is a company's own
description, not a study.

### What the newcomer studies converge on

Across the observational studies the model-building acts are the same: build and run the
system; take a small, isolated, mentor-screened task; read code adjacent to the task and copy
from it; run the debugger to see runtime behaviour; follow closed bugs to their changes; and
ask a person the moment reading stalls. Documentation is consulted first and found outdated,
scattered, or absent; the stated wish of experienced newcomers is for information about
people, not documents. Nothing in these studies measures the model directly: the outcomes
are time to first task or commit, contribution counts, retention, self-efficacy, and
interview self-report.

## Comprehension strategies and practice

### Strategies

- **Systematic versus as-needed (Littman, Pinto, Letovsky and Soloway 1987).** *J. Systems
  and Software* 7(4):341–355,
  [doi:10.1016/0164-1212(87)90033-1](https://doi.org/10.1016/0164-1212(87)90033-1);
  metadata only. As summarised in Storey, Wong and Müller (2000), which was read: "Littman et
  al. observed that programmers use either a systematic approach, reading the code in detail
  and tracing through control and data flow, or they use an as-needed approach, focusing
  only on the code related to the task at hand"; the systematic strategy "is less feasible for
  larger programs", the as-needed strategy is "more commonly used" but "more mistakes could
  occur since important interactions" may be missed. The specific result usually attributed to
  the paper — that systematic readers built causal models and succeeded at the modification
  while as-needed readers missed a delocalised interaction — was not read here and is
  unverified.
- **Integrated metamodel in the field (von Mayrhauser and Vans 1996).** *IEEE TSE*
  22(6):424–437, [doi:10.1109/32.508315](https://doi.org/10.1109/32.508315); metadata only
  (the brief's DOI ...508313 is a different paper). Storey et al. 2000: "they observed that
  some programmers frequently switched between all three of these models ... understanding
  is built concurrently at several levels of abstractions by freely switching between the
  three comprehension strategies." The 1995 *IEEE Computer* statement is in the evidence
  note.
- **Concept location (Rajlich and Wilde 2002).** *IWPC 2002*,
  [doi:10.1109/WPC.2002.1021348](https://doi.org/10.1109/WPC.2002.1021348); metadata only.
  Maalej et al. quote it: "regularities in the design, and especially in the naming of functions
  and data, may greatly facilitate concept location."
- **Corritore and Wiedenbeck 2001** on procedural versus object-oriented programmers'
  strategy shifts, *IJHCS* 54(1):1–23,
  [doi:10.1006/ijhc.2000.0423](https://doi.org/10.1006/ijhc.2000.0423); metadata only, not
  summarised here.
- **Program comprehension as fact finding (LaToza, Garlan, Herbsleb and Myers 2007).** Lab
  study: thirteen developers (0 to 10.5 years' industry experience; three "experts", ten
  "novices") worked three hours understanding the design of jEdit (54,720 non-comment
  lines). Participants "spent their time seeking, learning, critiquing, explaining, proposing,
  and implementing facts about the code such as 'getFoldLevel has effects'"; facts "served
  numerous roles, such as suggesting changes, constraining changes, and predicting the amount
  of additional investigation necessary". "Experts talked about code in terms of abstractions
  such as 'caching' while novices more often described code statement by statement"; "the
  experts explained the root cause of the design problem and made changes to address it,
  while novice changes addressed only the symptoms"; "Experts did not read more methods but
  also did not visit some methods novices wasted time understanding." One minute in, an expert
  said "this is just updating a cache"; after 51 minutes and "over 12 minutes staring at
  getFoldLevel", a novice "was still stuck at the statement level, never describing it as
  caching". *ESEC/FSE 2007*,
  [doi:10.1145/1287624.1287675](https://doi.org/10.1145/1287624.1287675); open copy at
  [figshare](https://figshare.com/articles/journal_contribution/Program_Comprehension_as_Fact_Finding/6470342),
  read in full.

### The questions comprehenders ask

**Sillito, Murphy and De Volder (FSE 2006).** Two qualitative studies: nine graduate students
in pairs, twelve 45-minute sessions on real ArgoUML issues (~60 KLOC), all newcomers to the
code; and sixteen industrial programmers in fifteen ~30-minute think-aloud sessions on their
own non-trivial change tasks in their normal tools, code bases from ~20,000 to over a
million lines. Framing: "Considering a code base as a graph of entities ... to answer any given
question requires considering some subgraph of the system." The 44 questions, in the
paper's four categories:

- *Finding initial focus points* (1–5): Which type represents this domain concept or this UI
  element or action? Where in the code is the text in this error message or UI element?
  Where is there any code involved in the implementation of this behavior? Is there a
  precedent or exemplar for this? Is there an entity named something like this in that unit?
- *Building on those points* (6–20): What are the parts of this type? Which types is this
  type a part of? Where does this type fit in the type hierarchy? Does this type have any
  siblings in the type hierarchy? Where is this field declared in the type hierarchy? Who
  implements this interface or these abstract methods? Where is this method called or type
  referenced? When during the execution is this method called? Where are instances of this
  class created? Where is this variable or data structure being accessed? What data can we
  access from this object? What does the declaration or definition of this look like? What
  are the arguments to this function? What are the values of these arguments at runtime?
  What data is being modified in this code?
- *Understanding a subgraph* (21–33): How are instances of these types created and
  assembled? How are these types or objects related? How is this feature or concern
  implemented? What in this structure distinguishes these cases? What is the behavior these
  types provide together and how is it distributed over the types? What is the "correct" way
  to use or access this data structure? How does this data structure look at runtime? How
  can data be passed to (or accessed at) this point in the code? How is control getting (from
  here to) here? Why isn't control reaching this point in the code? Which execution path is
  being taken in this case? Under what circumstances is this method called or exception
  thrown? What parts of this data structure are accessed in this code?
- *Questions over groups of subgraphs* (34–44): How does the system behavior vary over
  these types or cases? What are the differences between these files or types? What is the
  difference between these similar parts of the code? What is the mapping between these UI
  types and these model types? Where should this branch be inserted or how should this case
  be handled? Where in the UI should this functionality be added? To move this feature into
  this code what else needs to be moved? How can we know this object has been created and
  initialized correctly? What will be (or has been) the direct impact of this change? What
  will be the total impact of this change? Will this completely solve the problem or provide
  the enhancement?

Newcomers (study 1) accounted for 75%, 67% and 67% of the category 1–3 occurrences
against 25%, 33% and 33% from the professionals on their own code; category 4 split 48% to
52%. The tool finding: "Results were presented by tools in isolation as largely
undifferentiated and unconnected lists with no support for building towards an answer to a
participant's question." [doi:10.1145/1181775.1181779](https://doi.org/10.1145/1181775.1181779);
author copy via the Wayback Machine at
[pages.cpsc.ucalgary.ca](http://web.archive.org/web/20150914160324/http://pages.cpsc.ucalgary.ca/~sillito/work/fse2006.pdf),
read in full. The *IEEE TSE* 2008 version
([doi:10.1109/TSE.2008.26](https://doi.org/10.1109/TSE.2008.26)) was not obtained.

**LaToza and Myers (PLATEAU 2010), "Hard-to-answer questions about code."** A free-response
item in a survey of about 2,000 randomly sampled Microsoft developers (469 responded; 179
answered the free-response item — 149 individual contributors, 22 leads, 8 architects;
median ten years' experience, median one year on the current codebase; 68% agreed they were
"very familiar with my current codebase"). 371 questions clustered into 21 categories and
94 distinct questions over three topics — changes, properties of elements, relationships
between elements. The five most reported categories: Rationale (42 reports: "Why was it done
this way?" 14, "Why wasn't it done this other way?" 15, "Was this intentional, accidental, or a
hack?" 9, "How did this ever work?" 4); Intent and implementation (32: "What is the intent of
this code?" 12, "What does this do in this case?" 16, "How does it implement this behavior?"
4); Debugging (26); Refactoring (25: "How can I refactor this without breaking existing
users?" 9); History (23: "When, how, by whom, and why was this code changed or inserted?"
13). Other categories: Implications of a change (21), Testing (20), Implementing (19),
Control flow (19), Contracts (17), Teammates (16: "Who is the owner or expert for this
code?" 3; "How do I convince my teammates to do this the 'right way'?" 12), Performance
(16), Policies (15: "What is the policy for doing this?" 10), Type relationships (15), Data
flow (14), Location (13), Architecture (11), Building and branching (11), Concurrency (9),
Dependencies (5), Method properties (2). On rationale: "Despite their prevalence, effective
support for answering rationale questions remains an open problem. A popular strategy – ask
an expert teammate – interrupts the teammate, interrupts the question asker when the
teammate is unavailable, and does not work when the teammate has left the company."
"Comments might also help, but require future questions to be anticipated, the comments to
be correctly updated, and the author to make the time investment." "Many questions were
highly focused around specific hypotheses, situations, or proposals relevant to the
developer's current task and mental model of the code." Limits stated: one organisation;
self-report "subject to biases in perception of difficulty and what developers are able to
recall". [doi:10.1145/1937117.1937125](https://doi.org/10.1145/1937117.1937125); author copy
hosted by the workshop at
[ecs.victoria.ac.nz](http://ecs.victoria.ac.nz/twiki/pub/Events/PLATEAU/2010Program/plateau10-latoza.pdf),
linked from the CMU NatProg publications page; read in full.

### Comprehension in industrial practice

**Maalej, Tiarks, Roehm and Koschke (TOSEM 2014), "On the comprehension of program
comprehension"**, which contains and corrects the ICSE 2012 study ("The original version of
this paper [Roehm et al. 2012] included a mistake, which is corrected in this version").
28 think-aloud observation sessions with professional developers from seven companies
(2011) plus contextual interviews, and a 2009 survey with 1,477 complete responses (86% with
three or more years' experience). Observed strategies, with participant and company counts
of 28 and 7: employ a recurring, structured comprehension strategy depending on context
(26/7); follow a problem–solution–test work pattern (18/5); interact with the UI to test
expected behaviour (17/5); debug to elicit runtime information (16/5); "Clone to avoid
comprehension and minimize effort" (14/6 — "I do not know whether it is used otherwise";
one participant commented code out and let compiler warnings show what to restore rather
than "understand how each method works"); identify a starting point and filter irrelevant
code from experience (11/5); establish and test hypotheses (9/5); "Take notes to reflect
mental model and record knowledge" (9/4 — "This externalized knowledge is only used
personally. It is neither archived nor reused"); "Dedicated program comprehension tools are
not used" (28/7); "Source code is more trusted than documentation" (21/6 — "technical
documentation covers only 10 % of the application"; "you cannot trust the documentation");
"Communication is preferred over documentation" (17/5 — "much easier to go next door and
ask a colleague"); standards facilitate (12/6); cryptic names hamper (10/6); "Rationale and
intended usage is important, but rare information" (10/5 — "we did not observe a single
participant documenting rationale for own code"). Survey: over 83% often or usually hit
problems from lack of information about "what is the program supposed to do" or "whether a
component provides a certain functionality"; 81% consult other people often or usually;
web search "as popular as people"; wikis "remain unpopular with 'never' as mode". The
authors' summary: "developers try to avoid comprehension whenever possible ... focusing
rather on the expected output of the main development task"; comprehension "is rather
considered as a necessary step to accomplish different maintenance tasks rather than a goal
by [itself]". [doi:10.1145/2622669](https://doi.org/10.1145/2622669); author preprint via the
Wayback Machine at
[mast.informatik.uni-hamburg.de](http://web.archive.org/web/20200710070655/https://mast.informatik.uni-hamburg.de/wp-content/uploads/2014/06/TOSEM-Maalej-Comprehension-PrePrint2.pdf),
read in full. Roehm et al. *ICSE 2012*,
[doi:10.1109/ICSE.2012.6227188](https://doi.org/10.1109/ICSE.2012.6227188), was not obtained
as its own text; its abstract-level findings are in the explorable-maps note.

**Xia, Bao, Lo, Xing, Hassan and Li (TSE 2018), "Measuring program comprehension."**
Whole-desktop activity logging (IDEs, browsers, document editors) at two Chinese
outsourcing companies: seven projects, 78 professional developers, 3,148 working hours;
200 long comprehension sessions replayed and coded (Fleiss κ = 0.78); ten interviews.
Comprehension time is "inspection activities such as inspecting console and breakpoint
within the IDE, or reading through a piece of code (identified by e.g., detecting mouse
drifting actions)"; navigation is counted separately ("readers can simply sum up navigation
and comprehension time if they consider navigation as part of comprehension"). Result: "on
average developers spend 58 percent of their time on program comprehension activities" —
57.62% comprehension, 23.96% navigation, 13.40% other, 5.02% editing, ranging 51.80% to
64.05% across projects. Experience effect: 66.37% (under three years), 55.97% (three to
five), 44.43% (over five), one-way ANOVA p < 2.2e-16. Browser-based comprehension was 27%
of time, "more than the total percentage of time spent on program comprehension activities
that are performed within IDEs and document editors". Root causes of long sessions: no or
insufficient comments (all ten interviewees; in 30 sessions developers added comments
afterwards), meaningless names, large classes and methods, inconsistent style (21% of the
200 sessions), inheritance hierarchies, search-result browsing, absent or ambiguous
documents, finding documents, unfamiliar business logic. "Without comments, developers have
to look at the code and use bottom-up comprehension." Limits: Windows-only logging; the
published text is internally inconsistent about "5" versus "7" projects in one passage.
[doi:10.1109/TSE.2017.2734091](https://doi.org/10.1109/TSE.2017.2734091); author copy at
[xin-xia.github.io](https://xin-xia.github.io/publication/TSE17.pdf), read in full. The 70%
figure often cited alongside it is Minelli, Mocci and Lanza (ICPC 2015): 18 Pharo developers,
about 740 sessions, 200 hours, where "understanding" is inferred from every inter-event pause
longer than one second plus inspection and mouse drifting — "an explicit assumption that we
made" — giving 69.85% on average, per-developer 40% to 94%
([doi:10.1109/ICPC.2015.12](https://doi.org/10.1109/ICPC.2015.12); author copy at
[inf.usi.ch](https://www.inf.usi.ch/faculty/lanza/PUBS/P/Mine2015b.pdf), read in full).

### Expert models

Petre and Blackwell (1999) had ten experts ("ten or more years ... acknowledged by their peers
as expert") think aloud during design and surveyed 227 LabVIEW users. All experts described
"a sort of dynamic mental simulation, a 'machine in the mind'", with common properties:
stoppably dynamic; focal attention ("I don't need to think about that; it's enough to know it's
over there"); adjustable granularity; provisional and incomplete (signalled by "absence,
fuzziness, partial shading"); and "the name business" ("absolutely necessary to understand
things"). *IJHCS* 51(1):7–30,
[doi:10.1006/ijhc.1999.0267](https://doi.org/10.1006/ijhc.1999.0267); author copy at
[cl.cam.ac.uk](http://www.cl.cam.ac.uk/~afb21/publications/IJHCS.pdf), read in full. Petre's
2009 synthesis of expert-team observation states that developers want visualisation for
"comprehension (particularly comprehension of inherited code), debugging, and design
reasoning", that "Experts want to see software visualized in context – not just what the
code does, but what it means", and that "Automatic generation from code is inherently
unlikely to produce conceptual visualizations because the code does not contain information
about intentions and principles"; her experts "typically produce their own software rather
than working with legacy systems". *ESEC/FSE 2009*,
[doi:10.1145/1595696.1595731](https://doi.org/10.1145/1595696.1595731); author copy via
the Wayback Machine at
[oro.open.ac.uk](http://web.archive.org/web/2015/http://oro.open.ac.uk/25994/1/p233-petre.pdf),
read in full. "UML in practice" (ICSE 2013,
[doi:10.1109/ICSE.2013.6606618](https://doi.org/10.1109/ICSE.2013.6606618)) was metadata
only; *Software Designers in Action* (2013) documents three professional pairs designing a
greenfield traffic simulator, so it is not a source on comprehending existing systems.

### Reading methods

- **Hermans, *The Programmer's Brain* (Manning 2021).** Verified from the free chapter and
  the published section outline: three kinds of confusion — "Lack of knowledge", "Lack of
  information", "Lack of processing power" — mapped to long-term, short-term and working
  memory ("Not knowing the meaning of a domain concept is a different sort of confusion than
  trying to read a complicated algorithm step by step"); chunking and "Expert programmers
  can remember code better than beginners" (ch. 2); reducing cognitive load with refactoring,
  code synonyms and memory aids such as a dependency graph and a state table (ch. 4);
  "Text knowledge vs. plan knowledge", "Different stages of program understanding", and
  text-comprehension strategies applied to code beginning with "Activating prior knowledge"
  (ch. 5); five programming activities — searching, comprehension, transcription,
  incrementation, exploration — in ch. 11, where comprehension is "you read and execute code
  to gain an understanding of its functionality" and the 58% figure is cited; and ch. 13 "How
  to onboard new developers": "Limit tasks to one programming activity", "Support the memory
  of the onboardee", "Read code together". Manning livebook
  ([manning.com](https://livebook.manning.com/book/the-programmers-brain/chapter-1/)) and
  the publisher's excerpt of ch. 11. Section bodies beyond ch. 1 were not read; the
  beacon-and-schema treatment and the full strategy list are unverified here.
- **Code Reading Club.** "A bit like a book club, and a bit like an escape room"; "experienced
  developers know that their work invariably involves reading more code than writing it, but
  little attention is paid to reading technique"; "inspired by research and teaching exercises
  designed by Felienne Hermans". Session structure, each step done independently then
  together: *first glance* (one minute: "note down the first thing that catches your eye ...
  then the second"; discussion steered "back to individual details, rather than summaries";
  reflect on "what kind of knowledge you used"); *syntax knowledge*; *code structure* ("circle
  all variables in red ... link ... their uses"; methods in blue; instantiations in green; "How does
  the data flow through the code?"); *content* — list identifier names, or *a random line*
  ("What is the main idea of this line? What lines does it relate to and why?"); *identify most
  important lines* (five each, then "Agree on less than 8"); *summary* ("write down the
  essence of the code in a few sentences", then compare strategies — "method names,
  documentation, variable names, prior knowledge of system"). A second session on the same
  code adds central thematic and programming concepts, "The decisions made in the code",
  their consequences, and "The 'why' of the decisions". The starter kit's first session is 75
  minutes on a Signal-iOS file revealed only at the end. Stated evidence: none — "In our
  experience, it does not matter all that much what code you pick"; "one of the most
  important things people gain from the reading club is realising that people do not all
  comprehend and create code in the same way." [codereading.club](https://codereading.club)
  and the exercises repository
  [github.com/CodeReadingClubs/Resources](https://github.com/CodeReadingClubs/Resources),
  read in full.
- **Spinellis, *Code Reading* (Addison-Wesley 2003).** "My goal was to provide background
  knowledge and techniques for reading code written by others"; "the first one to
  exclusively deal with code reading as a distinct activity"; "40% to 70% of the effort that
  goes into a software system is expended after the system is first written"; "Code reading is
  in many cases a bottom-up activity"; the maxims include "Documentation often mirrors and
  therefore reveals the underlying system structure". Organised by language constructs, then
  large-project mechanics, architecture, tools (grep, diff, the compiler as a reading tool),
  and a worked "attack plan". Book site and sample chapter at
  [spinellis.gr/codereading](https://www.spinellis.gr/codereading/), read; body not read.
- **Feathers, *Working Effectively with Legacy Code* (Prentice Hall 2004).** Verified from
  the publisher's sample chapters 1 and 4: "Understanding is the key thing that we need to
  make changes safely"; "in the good ones, you feel pretty calm after you've done that
  learning ... In poorly structured code, the move from figuring things out to making changes
  feels like jumping off a cliff to avoid a tiger"; "A seam is a place where you can alter
  behavior in your program without editing in that place", each with "an enabling point".
  The chapter titles "I Don't Understand the Code Well Enough To Change It" (16) and "My
  Application Has No Structure" (17) are verified from the table of contents. Their
  techniques — characterisation tests (assert what the code actually does, discovered by
  letting a wrong assertion fail), notes and sketching, listing markup, scratch refactoring
  (refactor to understand, then discard), effect sketches, "telling the story of the system",
  naked CRC, conversation scrutiny (compare how the team talks about the system with the
  code) — are recalled, not read here, and unverified. InformIT samples
  [ch. 4](https://www.informit.com/content/images/0131177052/samplechapter/0131177052_ch04.pdf)
  and [ch. 1](https://www.informit.com/content/images/0131177052/samplechapter/0131177052_ch01.pdf).

### Reverse engineering and design recovery

- **Chikofsky and Cross (1990).** *IEEE Software* 7(1):13–17,
  [doi:10.1109/52.43044](https://doi.org/10.1109/52.43044); not obtained. Its definition is
  quoted identically by two primary sources that were read (Müller et al. 2000; Rugaber
  1995): "Reverse engineering is the process of analyzing a subject system to identify the
  system's components and their interrelationships and create representations of the system
  in another form or at a higher level of abstraction." The companion definitions
  (redocumentation, design recovery, restructuring, reengineering) are recalled and
  unverified.
- **Biggerstaff (1989), "Design recovery for maintenance and reuse."** "Design recovery
  recreates design abstractions from a combination of code, existing design documentation (if
  available), personal experience, and general knowledge about problem and application
  domains"; it "must reproduce all of the information required for a person to fully
  understand what a program does, how it does it, why it does it, and so forth"; "A system
  expert provides one of the most effective ways to recover the design of a foreign system by
  answering questions, shifting attention quickly to germane areas of the program,
  interpreting code segments in human (informal) terms"; "Expectations derived from
  organizational conventions are powerful and efficient mechanisms"; "the degree of
  automation is unlikely to ever go beyond the notion of an assistant." *IEEE Computer*
  22(7):36–49, [doi:10.1109/2.30731](https://doi.org/10.1109/2.30731); OCR'd scan via the
  Wayback Machine, read in full.
- **Rugaber (1995, 2000).** "Program comprehension is the process of acquiring knowledge
  about a computer program ... today program comprehension is largely a manual task"; cites
  Fjeldstad and Hamlen's finding that "47% and 62% of time spent on actual enhancement and
  correction tasks, respectively, are devoted to comprehension activities"; names five gaps
  (application domain and language; machine and design; intended and deteriorated
  structure; hierarchical programs and associational cognition; bottom-up analysis and
  top-down synthesis). The 2000 paper: "As currently practiced, program understanding
  consists mainly of code reading. The few automated understanding tools that are actually
  used in industry provide helpful but relatively shallow information ... adequate to answer
  questions concerning implementation details, so called what questions. They are severely
  limited, however, when trying to relate a system to its purpose or requirements, the why
  questions." Encyclopedia draft and *Annals of Software Engineering* 9:143–192,
  [doi:10.1023/A:1018976708691](https://doi.org/10.1023/A:1018976708691); author PostScript
  from the Georgia Tech reverse-engineering repository via the Wayback Machine, both read.
- **Müller, Jahnke, Smith, Storey, Tilley and Wong (2000), "Reverse engineering: a roadmap."**
  "Over time, memories fade, people leave, documents decay, and complexity increases.
  Consequently, an understanding gap arises between known, useful information and the
  required information needed to enable software change." Three categories of technique:
  "unaided browsing" ("limitations based on the amount of information that a software
  engineer may be able to keep track of in his or her head"), "leveraging corporate knowledge
  and experience" ("through mentoring or by conducting informal interviews with personnel
  ... They carry important information in their heads about design decisions, major changes
  over time, and troublesome subsystems"), and computer-aided reverse engineering.
  "Continuous program understanding": mappings between application and implementation
  domains "must be made explicit, recorded, reused, and updated continuously." On
  evaluation: "since there is no agreed-upon definition or test of understanding, it is
  difficult to claim that program comprehension has been improved when program
  comprehension itself cannot be measured." "In corporate settings, reverse engineering tools
  still have a long way to go before becoming an effective and integral part of the standard
  toolset." *ICSE Future of SE*,
  [doi:10.1145/336512.336526](https://doi.org/10.1145/336512.336526); copy at
  [cs.ucl.ac.uk](http://www.cs.ucl.ac.uk/staff/A.Finkelstein/fose/finalmuller.pdf), read in full.
- **The Rigi lineage.** Müller and Klashinsky, "Rigi: a system for programming-in-the-large",
  *ICSE 1988* ([doi:10.1109/ICSE.1988.93690](https://doi.org/10.1109/ICSE.1988.93690);
  metadata only — the brief's DOI is a different paper); Kienle and Müller, "Rigi — An
  environment for software reverse engineering, exploration, visualization, and
  redocumentation", *Sci. Comput. Program.* 75(4):247–263 (2010),
  [doi:10.1016/j.scico.2009.10.007](https://doi.org/10.1016/j.scico.2009.10.007); metadata
  only. The authors' own evaluation (Storey, Wong and Müller 2000; Rigi, SHriMP and SNiFF+
  with 30 students on a 1,700-line C program) and its "enhance or ease the programmer's
  preferred strategies" conclusion are in
  [track-explorable-maps.md](track-explorable-maps.md#evidence); that paper also records
  "the majority of these tools have not been adopted by industrial maintainers"
  ([doi:10.1016/s0167-6423(99)00036-2](https://doi.org/10.1016/s0167-6423(99)00036-2);
  author copy via the Wayback Machine, read in full).

## How a team holds a shared model

### Naur 1985: the team as the theory's holder

Read here from the full reprint of the 1985 article in Cockburn's *Agile Software
Development: The Cooperative Game* (2nd ed., 2006, Appendix B), which reproduces Naur's
text as reprinted in *Computing: A Human Activity* (1992); original: *Microprocessing and
Microprogramming* 15(5):253–261,
[doi:10.1016/0165-6074(85)90032-8](https://doi.org/10.1016/0165-6074(85)90032-8); reprint
PDF at [gwern.net](https://gwern.net/doc/cs/algorithm/1985-naur.pdf). The evidence note
summarises the theory-building argument; the passages on the team are these.

*The cases.* Case 1: group B, extending group A's compiler with "full documentation, including
annotated program texts and much additional written design discussion, and also personal
advice", submitted designs that group A "found ... to make no use of the facilities that were
not only inherent in the structure of the existing compiler but were discussed at length in
its documentation, and to be based instead on additions to that structure in the form of
patches that effectively destroyed its power and simplicity. The members of group A were
able to spot these cases instantly." Naur's conclusion: "the full program text and additional
documentation is insufficient in conveying to even the highly motivated group B the deeper
insight into the design, that theory which is immediately present to the members of group
A." Ten years on, after other programmers had taken the compiler over "without guidance
from group A", "the original powerful structure was still visible, but made entirely
ineffective by amorphous additions of many different kinds." Case 2: the producer's
installation and fault-finding programmers for a 200,000-line real-time system "rely almost
exclusively on their ready knowledge of the system and the annotated program text, and are
unable to conceive of any kind of additional documentation that would be useful to them",
while customer groups with the same documentation "regularly encounter difficulties that
upon consultation with the producer's installation and fault finding programmer are traced
to inadequate understanding of the existing documentation, but which can be cleared up
easily".

*Life, death and revival.* "The building of the program is the same as the building of the
theory of it by and in the team of programmers. During the program life a programmer team
possessing its theory remains in active control of the program, and in particular retains
control over all modifications. The death of a program happens when the programmer team
possessing its theory is dissolved. A dead program may continue to be used for execution in a
computer and to produce useful results. The actual state of death becomes visible when
demands for modifications of the program cannot be intelligently answered. Revival of a
program is the rebuilding of its theory by a new programmer team." On succession: "For a
new programmer to come to possess an existing theory of a program it is insufficient that he
or she has the opportunity to become familiar with the program text and other
documentation. What is required is that the new programmer has the opportunity to work in
close contact with the programmers who already possess the theory, so as to be able to
become familiar with the place of the program in the wider context of the relevant real
world situations and so as to acquire the knowledge of how the program works and how
unusual program reactions and program modifications are handled within the program
theory." The education is of knowledge-how, "such as writing and playing a music
instrument. The most important educational activity is the student's doing the relevant
things under suitable supervision and guidance", including "discussions of the relation
between the program and the relevant aspects and activities of the real world". On revival:
"program revival, that is reestablishing the theory of a program merely from the
documentation, is strictly impossible"; it "should only be attempted in exceptional situations
and with full awareness that it is at best costly, and may lead to a revived theory that differs
from the one originally had by the program authors and so may contain discrepancies with the
program text"; "the existing program text should be discarded and the new-formed
programmer team should be given the opportunity to solve the given problem afresh", which
"is more likely to produce a viable program than program revival, and at no higher, and
possibly lower, cost", because "building a theory to fit and support an existing program text
is a difficult, frustrating, and time consuming activity." Naur adds that "Similar problems
are likely to arise even when a program is kept continuously alive by an evolving team of
programmers ... particularly as the team is being kept operational by inevitable replacements
of the individual members." On status: "the notion of the programmer as an easily
replaceable component in the program production activity has to be abandoned."

This is argument from two cases the author witnessed or was told of; Naur says so ("the
experience is my own or has been communicated to me by persons having firsthand contact").

### Evans: ubiquitous language and knowledge that leaks

Chapter 2 of *Domain-Driven Design* (Addison-Wesley 2003) was not obtained as text; its
section list — Ubiquitous Language, Modeling Out Loud, One Team One Language, Documents and
Diagrams, Written Design Documents, Executable Bedrock, Explanatory Models — is verified from
the publisher's sample pages. Evans' own *Domain-Driven Design Reference* (2015, CC BY 4.0),
which restates the book's patterns, is quoted instead. Definition: a ubiquitous language is "A
language structured around the domain model and used by all team members within a bounded
context to connect all the activities of the team with the software." The problem: "Domain
experts use their jargon while technical team members have their own language tuned for
discussing the domain in terms of design. The terminology of day-to-day discussions is
disconnected from the terminology embedded in the code (ultimately the most important
product of a software project). And even the same person uses different language in speech
and in writing, so that the most incisive expressions of the domain often emerge in a
transient form that is never captured in the code or even in writing." The pattern: "Use the
model as the backbone of a language. Commit the team to exercising that language
relentlessly in all communication within the team and in the code. Within a bounded
context, use the same language in diagrams, writing, and especially speech. Recognize that a
change in the language is a change to the model." Continuous Integration: "When a number of
people are working in the same bounded context, there is a strong tendency for the model to
fragment. The bigger the team, the bigger the problem, but as few as three or four people can
encounter serious problems"; therefore "Relentlessly exercise the ubiquitous language to
hammer out a shared view of the model as the concepts evolve in different people's heads."
Hands-on Modelers: "the knowledge and skills of experienced designers won't be transferred
to other developers if the division of labor prevents the kind of collaboration that conveys
the subtleties of coding a model-driven design"; "Any technical person contributing to the
model must spend some time touching the code" ([DDD Reference
PDF](https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf),
read in full). The book's chapter 1 (publisher sample chapter, read in full) states the
knowledge-loss premise: "all projects leak knowledge. People who have learned something move
on. Reorganization scatters the team, and the knowledge is fragmented again. Crucial
subsystems are outsourced in such a way that code is delivered but knowledge isn't. And with
typical design approaches, the code and documents don't express this hard-earned knowledge
in a usable form, so when the oral tradition is interrupted for any reason, the knowledge is
lost"; and the remedy is a "stable core of people" who grow knowledge "consciously,
practicing continuous learning"
([ptgmedia.pearsoncmg.com ch. 1](https://ptgmedia.pearsoncmg.com/images/0321125215/samplechapter/evansch01.pdf)).
Fowler's foreword, in the same sample: "The greatest value of a domain model is that it
provides a ubiquitous language that ties domain experts and technologists together." All of
this is practitioner argument; no evaluation is offered. The rationale note's use of Evans
via arc42, Cucumber and Contextive is in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#shared-vocabulary-as-the-theorys-carrier).

### Team cognition research

- **Shared mental models (Cannon-Bowers, Salas and Converse 1993).** Book chapter in
  Castellan (ed.), *Individual and Group Decision Making* (Erlbaum); not obtained. The four
  content domains are confirmed in DeChurch and Mesmer-Magnus 2010: "technology or
  equipment, job or task, team interaction, and team".
- **Mathieu, Heffner, Goodwin, Salas and Cannon-Bowers (2000).** 56 undergraduate dyads on
  a PC flight-combat simulation; task- and team-based mental models measured by "individually
  completed paired-comparisons matrices analyzed using a network-based algorithm"; "both
  shared-team- and task-based mental models related positively to subsequent team process
  and performance", with process fully mediating. *J. Applied Psychology* 85(2):273–283,
  [doi:10.1037/0021-9010.85.2.273](https://doi.org/10.1037/0021-9010.85.2.273); abstract
  only.
- **DeChurch and Mesmer-Magnus (2010) meta-analysis.** 231 correlations from 65 studies,
  3,738 groups. Team cognition and behavioural process ρ = .43 (k = 37); cognition and
  performance ρ = .38 (k = 60, N = 3,512); cognition added ΔR² = .068 over cohesion and
  process. Compilational (transactive memory, "who knows what") versus compositional
  (shared mental model) emergence: cognition–process .62 versus .29, cognition–performance
  .44 versus .32; similarity versus accuracy of shared models made no material difference
  (performance .30 versus .34); effects were strongest for project teams (.52 compositional,
  .54 compilational): "the effects of cognition on performance are actually stronger for
  project teams." "in cross-functional teams ... it is likely less relevant ... that team members
  know everything similarly (congruence) than that team members know their own areas of
  expertise as well as whom to consult for everything else (compilation)." *J. Applied
  Psychology* 95(1):32–53, [doi:10.1037/a0017328](https://doi.org/10.1037/a0017328); read in
  full.
- **Levesque, Wilson and Wholey (2001).** Software development project teams followed over
  time: "Contrary to predictions, team members' mental models about the group's work and
  each other's expertise did not become more similar over time. Structural equation
  modelling revealed that as role differentiation increased in these teams, it led to a
  decrease in interaction and a corresponding decline in shared mental models." *J.
  Organizational Behavior* 22(2):135–144,
  [doi:10.1002/job.87](https://doi.org/10.1002/job.87); abstract only (Wiley 403; no open
  copy). Design details (student teams, number of timepoints) are unverified.
- **Schmidt, Kude, Heinzl and Mithas (ICIS 2014).** 81 co-located Scrum teams (~490
  engineers) at one enterprise-software company; shared mental models measured by dyadic
  agreement items ("The two of us ... have a similar understanding of our software
  architecture"; "agree how well-crafted code looks like"; α = .86). Use of pair programming,
  code review and automated tests predicted shared mental models (β = 0.58, p < .05, R² =
  .06) and backup behaviour (β = 0.75); "These mental models are made explicit by writing
  test cases and then shared in the team's 'test suite'." AIS eLibrary, no DOI; read in full.
  (Yu and Petter 2014, *IST* 56(8):911–921,
  [doi:10.1016/j.infsof.2014.02.010](https://doi.org/10.1016/j.infsof.2014.02.010), on agile
  practices and shared mental models, was metadata only.)
- **Ryan and O'Connor (2013), tacit knowledge in software teams.** 48 teams from 46 Irish
  and UK SMEs, 181 people. Transactive memory (Lewis scale) and quality of social interaction
  both predicted team tacit knowledge (TMS alone R² = .09; adding quality of interaction β =
  .43, R² = .20; quantity of interaction ns); "team tacit knowledge is acquired and shared
  directly through good quality social interactions and through the development of a TMS
  with quality of social interaction playing a greater role than transactive memory." *IST*
  55(9):1614–1624, [doi:10.1016/j.infsof.2013.02.013](https://doi.org/10.1016/j.infsof.2013.02.013);
  author manuscript, read in full.
- **Espinosa, Slaughter, Kraut and Herbsleb (2007).** Distributed software teams: "shared
  task knowledge is more important for coordination among collocated members" and
  geographic distance "is mitigated by shared knowledge of the team and presence awareness"
  (*JMIS* 24(1), [doi:10.2753/MIS0742-1222240104](https://doi.org/10.2753/MIS0742-1222240104));
  "the benefit of team familiarity for team performance is enhanced when team coordination is
  more challenging — i.e., when teams are larger or geographically dispersed", and task and
  team familiarity "are more substitutive than complementary" (*Organization Science*
  18(4):613–630, [doi:10.1287/orsc.1070.0297](https://doi.org/10.1287/orsc.1070.0297)).
  Both abstract only.

### Knowledge as footprint: ownership, succession, loss

The authorship-based estimators (Expertise Browser, degree-of-knowledge, truck factor,
Jabrayilzade's decay) are documented in
[track-durable-model.md](track-durable-model.md#expertise-location-tied-to-repository-structure)
and [track-measurement.md](track-measurement.md#proxies-and-telemetry); this section adds
what those papers say about knowledge itself and what happens when it leaves.

- **Fritz, Murphy and Hill (2007), "Does a programmer's activity indicate knowledge of
  code?"** Nineteen professional Java programmers at IBM, Mylyn interaction logs over five
  weeks, questionnaires of eighteen auto-generated structural questions about elements with
  high and low degree-of-interest. Elements with high interaction were answered more
  correctly (p = 0.0016) but "We did not find any evidence that the frequency or recency of
  activity alone with an element indicated knowledge"; "All subjects stated that he or she
  knows more about elements he or she authored"; one subject: "global knowledge of the
  system is maintained over a longer period of time but the specifics of each method
  implementation deteriorates quite quickly." *ESEC/FSE 2007*,
  [doi:10.1145/1287624.1287673](https://doi.org/10.1145/1287624.1287673); author copy via
  the Wayback Machine, read in full. Fritz et al. 2010 add that "developers had suggested
  three months as a lower bound for the period of time in which one still has knowledge
  about code after authoring it" and that of 45 elements a developer had interacted with,
  "only 12 (27%) also had at least one first authorship or delivery event in the previous three
  months" ([doi:10.1145/1806799.1806856](https://doi.org/10.1145/1806799.1806856); author
  copy, read in full). These questionnaires are the only pre-AI instrument found that tests a
  developer's knowledge of specific code directly.
- **Bird et al. (2011).** The knowledge interpretation behind the defect result: "The set of
  developers that contribute to a component implicitly form a team that has shared knowledge
  regarding the semantics and design of the component. If a member of this team devotes little
  attention to the team and/or the component, they may not acquire the knowledge required to
  make changes to the component without error." In Vista "52% of the binaries had minor
  contributors who were major contributors to other binaries that the original had a
  dependency with" versus 24% expected by chance. Recommendations: extra review of minor
  contributors' changes by major contributors; "Microsoft employs strong ownership
  practices" is stated as a limit. [doi:10.1145/2025113.2025119](https://doi.org/10.1145/2025113.2025119);
  read in full. **Greiler, Herzig and Czerwonka (2015)** replicated at file and directory level
  across Office, Exchange and Windows (directory-level Spearman with bugs: proportion of
  minor contributors .51–.69) and found strong ownership *discouraged* in Office; their
  interviews distinguish intentional collaborative ownership from unintentional
  non-ownership, and they quote Mockus: "developers go to great lengths to create and
  maintain rich mental models of code that are rarely permanently recorded"; an owner is
  "aware of changes to the artifact for example via code reviewing practices", not the sole
  editor. *MSR 2015*, [doi:10.1109/MSR.2015.8](https://doi.org/10.1109/MSR.2015.8); author
  copy, read in full.
- **Mockus and Herbsleb (2002), Expertise Browser.** Beyond the experience-atom metric
  documented in the durable-model note: the motivating finding that project architects "had
  become clearinghouses" for who-knows-what questions; a learning curve for 50 joiners of
  "approximately 15 months" to full productivity; and, in deployment, satellite sites searching
  product-to-people while established sites searched people-to-product. *ICSE 2002*,
  [doi:10.1145/581339.581401](https://doi.org/10.1145/581339.581401); accepted draft via
  the Wayback Machine, read in full.
- **Mockus (2009), "Succession."** Mentor–follower transfer of file ownership at Avaya,
  validated on ten known pairs: "what matters most is who owns the file, not which files a
  developer spends most of their time changing." On 1,012 followers across 13 products,
  offshoring succession "roughly halves the productivity ratio" (e^−0.63, CI [0.42, 0.67]);
  the ratio falls with the number of followers per mentor — "Mentors appear to have trouble
  transfering their expertise to a large number of followers." *ICSE 2009*,
  [doi:10.1109/ICSE.2009.5070509](https://doi.org/10.1109/ICSE.2009.5070509); author copy
  at [mockus.org](https://mockus.org/), read in full.
- **Rigby, Zhu, Donadelli and Mockus (2016), turnover-induced knowledge loss.** Avaya
  (>5M SLOC, eight quarters) and Chrome (3M LOC, seventeen quarters): a file is "abandoned"
  when ≥90% of its blame lines belong to departed developers; per-quarter losses had means
  of 209 and 194 files (medians 130 and 132), with 95th-percentile expected shortfalls of 797
  and 709 ("only 4% of total number of files" for Chrome). Successors: 56% (Avaya) and 77%
  (Chrome) of abandoned files had a co-change successor; suggesting the file's top five
  co-changers as experts was correct 48% and 34% of the time; "large losses occur because a
  developer hoards a file and does not have any potential successors"; "only 16% of files are
  adopted by newcommers in their first quarter." "Individuals who create software transfer
  their, often tacit knowledge, into the inner workings of the system making it difficult for
  others to maintain." *ICSE 2016*,
  [doi:10.1145/2884781.2884851](https://doi.org/10.1145/2884781.2884851); read in full.
- **Avelino et al. (2016, 2019).** The 2016 truck-factor paper's survey of 67 systems: 84%
  at least partially agreed the algorithm's authors were the main ones; respondents named
  documentation (36 mentions), an active community (15), tests (10), legibility (10) and
  comments (7) as what attenuates a low truck factor; a libgdx maintainer: "the truck factor
  is mostly concerned with institutional memory getting lost. No automatic system can
  account for this lost, unless all project communication is public"; a Clojure maintainer:
  "if the code is old enough, even the original author will have to approach it with
  essentially fresh eyes." [arXiv:1604.06766](https://arxiv.org/abs/1604.06766), read in
  full. The 2019 abandonment study of 1,932 popular GitHub projects: 57% had truck factor 1;
  all truck-factor developers detached in 315 projects (16%), 66% of those with truck factor
  1; 128 of 315 (41%) survived by attracting a new truck-factor developer, in 86% of cases
  only one, 52% from old contributors and 41% from newcomers; surviving projects had a
  median 505 commits after detachment versus 126 for the rest. Survey of 33 new
  truck-factor developers: 77% at least partially aware of the risk; motivation "Because I was
  using the project" (53%); helped by "Friendly and active owners/members" (41%); barriers
  "lack of time" (26%) and "lack of access to main repository" (19%). *ESEM 2019*,
  [arXiv:1906.08058](https://arxiv.org/abs/1906.08058), read in full.
- **Jabrayilzade et al. (2022), "Bus factor in practice."** 269 engineers: 63% "worked in the
  past year on a project they felt had high risk of bus factor reaching zero"; 76% believe
  knowledge decays, median halving time four months; a departed engineer "usually provides
  answers with a high level of abstraction, while low-level abstraction is required";
  practices named include "organizing talks by key developers, doing code reviews, or
  including team into making decisions", rotation, and hiring for redundancy. *ICSE-SEIP
  2022*, [arXiv:2202.01523](https://arxiv.org/abs/2202.01523), read in full; the knowledge
  channel ranking is in the measurement note.

### Practices that transfer the model

**Pair programming.**

- Williams, Kessler, Cunningham and Jeffries (2000): 41 senior students, 13 solo versus 28
  paired, four assignments; pairs passed more tests (73.4/86.4, 78.1/88.6, 70.4/87.1,
  78.1/94.4, p < 0.01), took 60% more programmer-hours on the first assignment "decreased
  dramatically to a minimum of 15%", and "individual workers asked two or three times more
  technical questions than did collaborative workers." On knowledge: "By pairing regularly
  with all members of the group, an individual programmer maintains sufficient general
  awareness to substitute for a missing partner at a moment's notice"; "a side effect of pair
  programming is a high order of staff cross training." *IEEE Software* 17(4):19–25,
  [doi:10.1109/52.854064](https://doi.org/10.1109/52.854064); author copy via the Wayback
  Machine, read in full.
- Plonka, Sharp, van der Linden and Dittrich (2015): about 37 hours of video of 21 pairing
  sessions with 31 developers at four German agile companies; interaction analysis of five
  expert–novice exemplars. Six teaching strategies — "indirect hints, pointing out problems,
  gradually adding information, giving clear instructions, explanation, and verbalisation" —
  the first four when the novice drives, the last two when the expert drives; "In none of the
  sessions did the expert explicitly encourage the novice to articulate their knowledge";
  "letting the novice drive can be useful to ensure that detailed knowledge is transferred.
  However, it also means that the process of solving the task at hand might be slower";
  tasks "are typically chosen according to agile prioritisation which considers business
  value, not educational progression"; learning was not measured. Cites Williams for a
  reduction of mentoring time "from 37% of a developer's time to 26%" and time to
  independent productivity "from 27 to 12 days" (second-hand). *IJHCS* 73:66–78,
  [doi:10.1016/j.ijhcs.2014.09.001](https://doi.org/10.1016/j.ijhcs.2014.09.001); accepted
  manuscript, read in full.
- Arisholm, Gallis, Dybå and Sjøberg (2007): 295 professional Java consultants (99
  individuals, 98 pairs) from 29 companies, one day each; "do not support the hypotheses that
  pair programming in general reduces the time required to solve the tasks correctly or
  increases the proportion of correct solutions"; "a significant 84 percent increase in
  effort"; on the more complex system pairs had "a 48 percent increase in the proportion of
  correct solutions", mainly for juniors. *IEEE TSE* 33(2),
  [doi:10.1109/TSE.2007.17](https://doi.org/10.1109/TSE.2007.17); abstract only. Hannay,
  Dybå, Arisholm and Sjøberg's meta-analysis (*IST* 51(7):1110–1122, 2009,
  [doi:10.1016/j.infsof.2009.02.001](https://doi.org/10.1016/j.infsof.2009.02.001)) was
  metadata only; its effect sizes are not reported here.

**Mob or ensemble programming**, as its practitioners document it.

- Zuill's Agile 2014 experience report (Hunter Industries): the practice began at a
  project restart where "A few of the team members and a contractor had previously worked on
  this project, but the rest of the team had not", and the team "felt we were rapidly improving
  our ability to communicate well, increase our knowledge, and find better solutions. We were
  gaining a deep and shared understanding of the project and the technologies involved."
  Falco's rule — "for an idea to go from your head into the computer it MUST go through
  someone else's hands" — with rotation every fifteen minutes; "This solves some of the
  common silo problems which occur when there is only one person who is a point of contact";
  "Everything from keyboard shortcuts and programming language features to design patterns
  and business concepts are exposed and shared across the team." The productivity claim
  ("approximately 10 times the number of projects delivered") is explicitly hedged: "we do
  not claim that this would be repeatable in any other environment."
  [agilealliance.org PDF](https://www.agilealliance.org/wp-content/uploads/2015/12/ExperienceReport.2014.Zuill_.pdf),
  read in full; Zuill's site posts ("we transfer knowledge quickly througout the team"; "the
  group memory of the team allows us to quickly locate the previous situation") at
  [mobprogramming.org](https://mobprogramming.org/).
- Falco, "Llewellyn's strong-style pairing" (2014): "the expert almost always is in the
  navigator position having everything go through the novice. This is a very intense way of
  immersion learning"; "If the thinking is happening in the same person that is typing then
  they usually are not talking ... By making the navigator speak out loud, you help to ensure
  that everyone is on the same page."
  [llewellynfalco.blogspot.com](https://llewellynfalco.blogspot.com/2014/06/llewellyns-strong-style-pairing.html),
  read in full.
- Buchan and Pearl (EASE 2018): one nine-person team over eighteen months plus a survey of
  82 practitioners. "Code ownership moved from individual ownership to the team ownership
  ... 'our' code"; "it is now difficult to distinguish who wrote a particular piece of code";
  "all the developers are comfortable and capable of working in both the front end and back
  end ... the risk of knowledge being lost if a team member leaves is lowered"; 89% of survey
  respondents named "learning from others" as a benefit; an expert driving too long makes
  others "passive spectators". [doi:10.1145/3210459.3210482](https://doi.org/10.1145/3210459.3210482);
  [arXiv:1907.11352](https://arxiv.org/abs/1907.11352), read in full. Wilson (XP 2015)
  adopted "Mob Fridays" for re-architecting "old and business critical" code "because we
  wanted as many eyes on what we were doing as possible"
  ([doi:10.1007/978-3-319-18612-2_33](https://doi.org/10.1007/978-3-319-18612-2_33); first
  two pages only). Shiraishi et al.'s 2019 systematic review found "only ten papers"
  ([doi:10.1109/COMPSAC.2019.10276](https://doi.org/10.1109/COMPSAC.2019.10276); abstract).

**Inspection and review as comprehension devices.**

- Fagan (1976). The inspection process's stated objectives table lists Overview as
  "Communication education" and Preparation as "Education" alongside Inspection's "Find
  errors"; in the overview "The designer first describes the overall area being addressed and
  then the specific area he has designed in detail — logic, paths, dependencies, etc."; in
  the inspection a reader "is expected to paraphrase the design as expressed by the designer."
  The knowledge passage: "The overview, preparation, and inspection sequence of the
  operations of the inspection process give the inspection participants a high degree of
  product knowledge in a very short time. This important side benefit results in the
  participants being able to handle later development and testing with more certainty and
  less false starts." And: "an inspection is frequently a required event where responsibility
  for design or code is being transferred from one programmer to another. The complete
  inspection team is convened for such an inspection ... Usually the side benefit of finding
  errors more than justifies the transfer inspection." Error-finding figures: 23% coding
  productivity increase; inspected code had "38 percent less errors than the walk-through
  sample". *IBM Systems Journal* 15(3):182–211,
  [doi:10.1147/sj.153.0182](https://doi.org/10.1147/sj.153.0182); read from an image-only
  scan of the 1999 reprint, about half the pages.
- Bacchelli and Bird (ICSE 2013), modern code review at Microsoft: 17 developers observed,
  873 programmers and 165 managers surveyed. Knowledge transfer was the first motivation
  for 8% of programmers, second for 14%, third for 16%; "All the interviewees but one
  motivated their code reviews also from a learning — or knowledge transfer — perspective";
  a senior developer: "If you do a code review and did not learn anything about the area ...
  then that was not as good code review as it could have been"; managers spoke of "grooming
  'backup developers' for areas where knowledge is too concentrated on one or two expert
  developers". Understanding is the reviewer's main challenge: 91% said unfamiliar files take
  longer; only 14% of review comments concerned defects. "if the author of a change is the
  only expert, she has no potential reviewers."
  [doi:10.1109/ICSE.2013.6606617](https://doi.org/10.1109/ICSE.2013.6606617); open copy
  via ZORA, read in full.
- Rigby and Bird (ESEC/FSE 2013), convergent practices across AMD, Bing, SQL Server,
  Office, Android and Chrome OS: median two active reviewers; the knowledge measure (files
  a developer modified or reviewed) rose with review by 44% in Chrome (24 to 43 files),
  100% Bing, 122% Office, 150% SQL Server, 66% Android — "conducting peer review increases
  the number of distinct files a developer knows about by 66% to 150%"; the authors note
  that before this "we are unaware of any empirical studies that measure this phenomenon."
  [doi:10.1145/2491411.2491444](https://doi.org/10.1145/2491411.2491444); author copy, read
  in full.
- Sadowski, Söderberg, Church, Sipko and Bacchelli (ICSE-SEIP 2018), Google: "the main
  impetus behind the introduction of code review was to force developers to write code that
  other developers could understand; this was deemed important since code must act as a
  teacher for future developers", and review "would ensure that more than one person would be
  familiar with each piece of code, thus increasing the chances of knowledge staying within
  the company." Median one reviewer, median 24 lines, median latency under four hours; "Every
  change must be either authored or reviewed by someone with a readability certification";
  developers in their first year "typically have more than twice as many comments per
  change". [doi:10.1145/3183519.3183525](https://doi.org/10.1145/3183519.3183525); author
  copy via the Wayback Machine, read in full.
- Rituals such as brown-bag talks, architecture review boards and design reviews: no
  primary empirical source was located beyond Jabrayilzade's practitioner list ("organizing
  talks by key developers"); Yourdon's *Structured Walkthroughs* was not obtained.

## Documentation and tooling for newcomers

Only what the explorable-maps and rationale notes do not already hold. The survey evidence
that documentation is outdated yet still used (Forward and Lethbridge; Lethbridge, Singer and
Forward; Aghajani et al.) is in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#documentation-use-and-staleness);
pre-agent comprehension tools with persistent notes (Sourcetrail, Understand, CodeCompass) and
the authored-tour lineage (CodeTour, Swimm) are in
[track-explorable-maps.md](track-explorable-maps.md#pre-agent-comprehension-tools-structure-with-in-some-cases-persistent-human-notes)
and [its tours section](track-explorable-maps.md#guided-tours-and-onboarding-narratives). The
additional pre-AI evidence:

- The newcomer studies above agree on what newcomers want from documents: a way to get the
  system to build and run, a map of who owns what, and worked examples to copy — Dagenais'
  participants used closed bugs as "trails" and documented their own steps for the next
  arrival; Ju's developers went to documentation first and were "frustrated when
  documentation cannot provide answers"; Rodeghero's hires described "an information glut and
  an indexing dearth"; Begel and Simon's more experienced hires "desired information on
  people". The field observations add that developers trust code over documents (21 of 28)
  and that rationale is "important, but rare information" (Maalej et al. 2014, above).
- The only controlled newcomer-tooling evaluation found is FLOSScoach (above): a portal
  organised by barrier raised task completion from 56% to 77% of students and protected
  self-efficacy, while technical comprehension barriers were "still there, in both cases".
- Sim and Holt's pilot onboarding course (videotaped senior talks plus the Software
  Bookshelf) was not found "directly applicable" four months later; the participants had
  wanted "more information on the overall system architecture and main data structures".
- Google's readability programme is the one documented practice that certifies a person's
  familiarity with a codebase's conventions rather than documenting the codebase; its
  reported effect (faster review and submission for certified authors) is an internal, unpublished
  analysis.
- Fritz et al.'s 2010 case study is the one attempt found to use a knowledge model for
  onboarding: "Only 2 of the 60 (3%) elements" it recommended "were considered ... helpful for
  a newcomer" ([doi:10.1145/1806799.1806856](https://doi.org/10.1145/1806799.1806856)).
- Good-first-issue labelling is the open-source analogue of the mentor-screened first task;
  the 2023 analysis above found expert involvement raised newcomers' success and lowered
  retention, and Labuschagne and Holmes found Good First Bug entrants succeeded less often on
  their first attempt (67.1%) than mentored entrants (80.1%).

## Mapping to the existing notes

| Pre-AI finding | Primary source | Evidence type | Where the AI-era notes touch it |
| --- | --- | --- | --- |
| The theory lives in the team; a program dies when the team dissolves; revival from documents is "strictly impossible"; newcomers acquire it by working "in close contact" with holders | Naur 1985 (reprint read) | Argument from two cases | [evidence note](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text); [rationale note](track-rationale-as-artifact.md#shared-vocabulary-as-the-theorys-carrier); [Answer.AI](answer-ai-sweep.md#finding) applies Naur to complexity |
| Full documentation plus text did not stop a motivated second team from patching around a design its authors could see "instantly" | Naur 1985, Case 1 | Case | [rationale note, capture cost versus use](track-rationale-as-artifact.md#design-rationale-capture-cost-versus-use) (rationale read by humans) |
| The team's spoken language is the model's carrier; "all projects leak knowledge" when people move on | Evans 2003 ch. 1; DDD Reference 2015 | Practitioner argument | [rationale note, shared vocabulary](track-rationale-as-artifact.md#shared-vocabulary-as-the-theorys-carrier) |
| Newcomers build the model by building and running, a small isolated task, reading adjacent code, debugging, and asking; six to twelve months to productivity | Sim and Holt 1998; Begel and Simon 2008; Dagenais 2010; Ju 2021 | Observation and interview | [explorable-maps tours](track-explorable-maps.md#guided-tours-and-onboarding-narratives) (agent-generated onboarding tours, unevaluated); otherwise no counterpart |
| Mentoring is effective but costs the mentor hours a day for weeks; asking beats reading; "I know when I am stuck" is a misconception | Sim and Holt 1998; Begel and Simon 2008 | Observation | [hand-off checks, teach-back](track-hand-off-checks.md#explain-it-back-and-teach-back) (a gate that asks the human to explain, no mentor); no counterpart for mentoring |
| Mentored newcomers contribute about three times more and are more likely to stay; task recommendation alone helps less | Fagerholm 2014; Labuschagne and Holmes 2015; Tan 2023 | Quasi-experiment and mining | No counterpart |
| Systematic reading builds a stronger model than as-needed reading but does not scale; experts switch between domain, program and situation models | Littman 1987 (via Storey 2000); von Mayrhauser and Vans 1996 | Lab observation (metadata only here) | [evidence note, comprehension](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of); [Solveit's](solve-it-sweep.md#the-method) small-step re-derivation is a systematic strategy at the line grain |
| Comprehension is fact finding; experts speak in abstractions ("caching") and fix root causes, novices stay at the statement level | LaToza et al. 2007 | Lab study, n=13 | [measurement note, classic instruments](track-measurement.md#classic-comprehension-instruments) (EiPE rubrics score exactly this level shift) |
| 44 questions over a code graph; newcomers ask the focus-finding questions three times as often as owners | Sillito 2006 | Qualitative, 27 sessions | [explorable-maps, directed questions](track-explorable-maps.md#directed-questions-on-a-node) |
| Rationale and intent are the hardest questions; "ask an expert teammate" fails when the teammate has left | LaToza and Myers 2010 | Survey, n=179 | [rationale note](track-rationale-as-artifact.md#design-rationale-capture-cost-versus-use); [evidence note](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of) |
| Professionals avoid comprehension, trust code over documents, prefer asking, take transient notes, use no comprehension tools | Maalej 2014 | Field observation, n=28; survey, n=1,477 | [explorable-maps evidence](track-explorable-maps.md#evidence) (Roehm abstract); [rationale note, staleness](track-rationale-as-artifact.md#documentation-use-and-staleness) |
| 58% of time is comprehension, falling with experience; 27% happens in the browser | Xia 2018; Minelli 2015 | Telemetry, 78 developers | [measurement note, proxies](track-measurement.md#proxies-and-telemetry) uses telemetry for AI share, not comprehension time |
| Structured group reading: first glance, structure marking, important lines, summary, then decisions and their "why" | Code Reading Club; Hermans 2021 | Practice, no evaluation | [evidence note, computing education](evidence-and-mechanisms.md#computing-education-evidence-on-reading-code); [Solveit](solve-it-sweep.md#finding) reads in small steps but alone; no counterpart for group reading |
| Legacy-code techniques: characterisation tests, scratch refactoring, seams | Feathers 2004 (chs. 1, 4 read) | Practitioner method | No counterpart |
| Design recovery needs domain knowledge and a system expert; automation "unlikely to ever go beyond the notion of an assistant"; tools answer what, not why | Biggerstaff 1989; Rugaber 2000; Müller 2000 | Argument and tool experience | [explorable-maps, agent-era maps and wikis](track-explorable-maps.md#evidence) (generated wikis unevaluated on humans) |
| Comprehension "cannot be measured", so tool improvement cannot be claimed | Müller 2000 | Position | [measurement note](track-measurement.md#classic-comprehension-instruments) |
| Team cognition predicts process and performance; distributed "who knows what" matters more than identical models; strongest in project teams | DeChurch and Mesmer-Magnus 2010 | Meta-analysis, k=65 | No counterpart |
| Software teams' mental models did not converge over time; role differentiation cut interaction | Levesque 2001 | Longitudinal, abstract only | [rationale note](track-rationale-as-artifact.md#shared-vocabulary-as-the-theorys-carrier) |
| Agile quality practices (pairing, review, tests) predict shared mental models | Schmidt 2014 | Survey, 81 teams | No counterpart |
| Tacit team knowledge comes from quality of interaction more than from transactive memory | Ryan and O'Connor 2013 | Survey, 48 teams | [rationale note, multiplayer threads](track-rationale-as-artifact.md#multiplayer-human-plus-agent-threads-elsewhere) (shared threads, no measure of interaction quality) |
| Authorship and interaction predict answers to questions about code; method-level detail decays in months, global knowledge persists | Fritz 2007, 2010 | Field study with questionnaire | [durable-model note](track-durable-model.md#expertise-location-tied-to-repository-structure); [measurement note](track-measurement.md#proxies-and-telemetry) |
| Minor contributors form a team without shared knowledge; strong ownership can block transfer | Bird 2011; Greiler 2015 | Mining plus interviews | [evidence note](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of); [measurement note](track-measurement.md#proxies-and-telemetry) |
| Succession halves a follower's productivity; mentors cannot transfer to many followers | Mockus 2009 | Mining, 1,012 followers | No counterpart |
| Departure abandons ~130 files a quarter; losses concentrate where there is no co-change successor; 16% of projects lose all truck-factor developers and 41% of those survive | Rigby 2016; Avelino 2019 | Mining | [measurement note](track-measurement.md#proxies-and-telemetry) (truck factor and AI share); [evidence note dead ends](evidence-and-mechanisms.md#dead-ends-and-gaps) |
| Pairing cross-trains; a novice driving transfers detail more slowly; six teaching strategies; no measured learning | Williams 2000; Plonka 2015; Arisholm 2007 | Experiment and video analysis | [in-loop friction](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking) cites AI pairing analogies; no counterpart for human pairing as transfer |
| Mob programming makes ownership collective and reduces loss on departure; 89% cite learning | Zuill 2014; Buchan and Pearl 2018 | Experience report and survey | No counterpart |
| Inspection educates its participants and is the formal event for transferring code; review spreads files known by 66–150% | Fagan 1976; Rigby and Bird 2013; Bacchelli and Bird 2013; Sadowski 2018 | Process data and survey | [hand-off checks, gate placement](track-hand-off-checks.md#gate-placement-and-enforcement) (review-time gates); [evidence note, reading and approving](evidence-and-mechanisms.md#does-reading-and-approving-build-understanding) |
| Good-first-issue labelling and newcomer portals raise completion but leave code-comprehension barriers in place | Steinmacher 2016; Labuschagne 2015; Tan 2023 | Controlled and mining | No counterpart |

"No counterpart" means no AI-era note in this directory addresses the point; it is a
statement about the notes, not about the wider literature.

## Dead ends

- **Discovery.** WebSearch was unavailable by instruction; OpenAlex refused every call after
  the first two ("Insufficient budget ... Resets at midnight UTC"); Semantic Scholar elides
  abstracts for IEEE and ACM records and rate-limited after about twenty calls; the arXiv
  export API returned 503; CORE returned empty bodies or 429; scholar.archive.org and
  DuckDuckGo present bot challenges; the Wayback Machine rate-limited intermittently.
  Crossref, publisher sample pages, author sites, Wayback captures of author sites, figshare,
  Helda and HAL were the working routes.
- **Naur.** The gwern-hosted reprint is Cockburn's appendix reproduction, not a scan of the
  1985 journal pages; wording was checked against the *Computing: A Human Activity* text it
  reproduces only insofar as Cockburn's preface says so. Page numbers in the original journal
  were not verified.
- **Evans chapter 2** was not read as text; O'Reilly (403), InformIT's article listing, and
  the publisher's sample pages (which hold the table of contents, foreword and chapter 1 only)
  were tried. The DDD Reference is Evans' own restatement and was used instead.
- **LaToza and Myers 2010** was obtained (workshop-hosted author copy); the CMU NatProg
  paths guessed in earlier passes are 404.
- **Not obtained as full text**: Littman et al. 1987; von Mayrhauser and Vans 1993–1998
  (no author copies in the Wayback Machine); Roehm et al. ICSE 2012 as its own text (covered
  by the TOSEM 2014 version that subsumes and corrects it); Sillito et al. TSE 2008 (UBC
  cIRcle blocks scripted fetches); Chikofsky and Cross 1990 (definition verified only through
  quotation in Müller 2000 and Rugaber 1995); Corritore and Wiedenbeck 2001; Rajlich and
  Wilde 2002; Müller and Klashinsky 1988; Kienle and Müller 2010; Petre 2013 "UML in
  practice" (ORO 403); Levesque et al. 2001 (Wiley 403); Mathieu et al. 2000; Mohammed et
  al. 2010; Cannon-Bowers et al. 1993 (book chapter); Yu and Petter 2014; Hannay et al.
  2009 (no abstract retrievable anywhere reached); Arisholm et al. 2007 (abstract only);
  Espinosa et al. 2007 (both papers, abstract only); Fritz et al. 2014 TOSEM; Canfora et al.
  FSE 2012 (rcost.unisannio.it unreachable; thesis chapter substituted); Johnson and Senges
  2010 (Emerald 403); Fagerholm et al. *IEEE Software* 2014; Tan et al. 2020 (metadata);
  Robillard and DeLine 2011 on API learning obstacles (McGill 403); Wilson 2015 beyond page
  320; Shiraishi et al. 2019 body; Yourdon *Structured Walkthroughs*; Zuill and Meadows'
  book; Hermans' chapters beyond the free chapter 1 and section headings; Feathers' chapters
  13, 16 and 17 (only chapters 1 and 4 are published as samples); Spinellis' body beyond the
  sample chapter; Petre and van der Hoek 2013 (established from the workshop site to be a
  greenfield design corpus).
- **Fagan 1976** exists reachable only as an image scan of the 1999 reprint; about half the
  pages were read visually, and the summary pages were not.
- **Wrong DOIs in the task brief**, corrected above: Ju 2021, Johnson and Senges 2010,
  Fagerholm ESEM (2014, not 2013), von Mayrhauser and Vans 1996, Müller and Klashinsky
  1988, Greiler 2015, Mockus "Succession" (ICSE 2009), Wilson 2015, Ryan and O'Connor 2013.
- **No primary empirical source** was found for brown-bag talks, architecture review boards
  or design reviews as comprehension devices; the Google engineering book is a company
  account, and Jabrayilzade's respondents' practices are self-report.
- **No pre-AI source found** that measures a shared model of a codebase directly; the
  instruments are dyadic agreement ratings, paired-comparison networks on simulator tasks,
  structural-fact questionnaires (Fritz 2007), and authorship counts.
- **mobprogramming.org** blocks non-default user agents and no longer hosts the Agile 2014
  report; the Agile Alliance copy was used. igorsteinmacher.com no longer resolves; papers
  are at igor.pro.br. Sillito's Calgary homepage is 404; only the Wayback copy of the FSE
  paper survives.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Arisholm, E., Gallis, H., Dybå, T., Sjøberg, D. I. K. (2007). Evaluating pair programming
  with respect to system complexity and programmer expertise. *IEEE TSE* 33(2).
  doi:10.1109/TSE.2007.17.
- Avelino, G., Passos, L., Hora, A., Valente, M. T. (2016). A novel approach for estimating
  truck factors. *ICPC 2016*. doi:10.1109/ICPC.2016.7503718; arXiv:1604.06766.
- Avelino, G., Constantinou, E., Valente, M. T., Serebrenik, A. (2019). On the abandonment
  and survival of open source projects. *ESEM 2019*. arXiv:1906.08058.
- Bacchelli, A., Bird, C. (2013). Expectations, outcomes, and challenges of modern code
  review. *ICSE 2013*. doi:10.1109/ICSE.2013.6606617.
- Begel, A., Simon, B. (2008). Novice software developers, all over again. *ICER 2008*.
  doi:10.1145/1404520.1404522.
- Begel, A., Simon, B. (2008). Struggles of new college graduates in their first software
  development job. *SIGCSE 2008*. doi:10.1145/1352135.1352218.
- Biggerstaff, T. J. (1989). Design recovery for maintenance and reuse. *IEEE Computer*
  22(7):36–49. doi:10.1109/2.30731.
- Bird, C., Nagappan, N., Murphy, B., Gall, H., Devanbu, P. (2011). Don't touch my code!
  *ESEC/FSE 2011*. doi:10.1145/2025113.2025119.
- Buchan, J., Pearl, M. (2018). Leveraging the mob mentality: an experience report on mob
  programming. *EASE 2018*. doi:10.1145/3210459.3210482; arXiv:1907.11352.
- Canfora, G., Di Penta, M., Oliveto, R., Panichella, S. (2012). Who is going to mentor
  newcomers in open source projects? *FSE 2012*. doi:10.1145/2393596.2393647.
- Chen, N., Barolak, M. (2020). Knowledge sharing. In *Software Engineering at Google*
  (O'Reilly), ch. 3. abseil.io/resources/swe-book/html/ch03.html.
- Chikofsky, E. J., Cross, J. H. (1990). Reverse engineering and design recovery: a taxonomy.
  *IEEE Software* 7(1):13–17. doi:10.1109/52.43044.
- Code Reading Club. codereading.club; github.com/CodeReadingClubs/Resources.
- Corritore, C. L., Wiedenbeck, S. (2001). An exploratory study of program comprehension
  strategies of procedural and object-oriented programmers. *IJHCS* 54(1):1–23.
  doi:10.1006/ijhc.2000.0423.
- Dagenais, B., Ossher, H., Bellamy, R. K. E., Robillard, M. P., de Vries, J. P. (2010).
  Moving into a new software project landscape. *ICSE 2010*. doi:10.1145/1806799.1806842.
- DeChurch, L. A., Mesmer-Magnus, J. R. (2010). The cognitive underpinnings of effective
  teamwork: a meta-analysis. *J. Applied Psychology* 95(1):32–53. doi:10.1037/a0017328.
- Espinosa, J. A., Slaughter, S. A., Kraut, R. E., Herbsleb, J. D. (2007). Team knowledge and
  coordination in geographically distributed software development. *JMIS* 24(1):135–169.
  doi:10.2753/MIS0742-1222240104.
- Espinosa, J. A., Slaughter, S. A., Kraut, R. E., Herbsleb, J. D. (2007). Familiarity,
  complexity, and team performance in geographically distributed software development.
  *Organization Science* 18(4):613–630. doi:10.1287/orsc.1070.0297.
- Evans, E. (2003). *Domain-Driven Design: Tackling Complexity in the Heart of Software*.
  Addison-Wesley. ISBN 0-321-12521-5. Chapter 1 sample:
  ptgmedia.pearsoncmg.com/images/0321125215/samplechapter/evansch01.pdf.
- Evans, E. (2015). *Domain-Driven Design Reference: Definitions and Pattern Summaries*.
  Domain Language, Inc. CC BY 4.0.
  domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf.
- Fagan, M. E. (1976). Design and code inspections to reduce errors in program development.
  *IBM Systems Journal* 15(3):182–211. doi:10.1147/sj.153.0182.
- Fagerholm, F., Sanchez Guinea, A., Münch, J., Borenstein, J. (2014). The role of mentoring
  and project characteristics for onboarding in open source software projects. *ESEM 2014*.
  doi:10.1145/2652524.2652540.
- Falco, L. (2014). Llewellyn's strong-style pairing.
  llewellynfalco.blogspot.com/2014/06/llewellyns-strong-style-pairing.html.
- Feathers, M. (2004). *Working Effectively with Legacy Code*. Prentice Hall. ISBN
  0-13-117705-2.
- Fritz, T., Murphy, G. C., Hill, E. (2007). Does a programmer's activity indicate knowledge
  of code? *ESEC/FSE 2007*. doi:10.1145/1287624.1287673.
- Fritz, T., Ou, J., Murphy, G. C., Murphy-Hill, E. (2010). A degree-of-knowledge model to
  capture source code familiarity. *ICSE 2010*. doi:10.1145/1806799.1806856.
- Greiler, M., Herzig, K., Czerwonka, J. (2015). Code ownership and software quality: a
  replication study. *MSR 2015*. doi:10.1109/MSR.2015.8.
- Hannay, J. E., Dybå, T., Arisholm, E., Sjøberg, D. I. K. (2009). The effectiveness of pair
  programming: a meta-analysis. *IST* 51(7):1110–1122. doi:10.1016/j.infsof.2009.02.001.
- Hermans, F. (2021). *The Programmer's Brain*. Manning. ISBN 978-1-61729-867-7.
- Jabrayilzade, E., Evtikhiev, M., Tüzün, E., Kovalenko, V. (2022). Bus factor in practice.
  *ICSE-SEIP 2022*. doi:10.1145/3510457.3513082; arXiv:2202.01523.
- Johnson, M., Senges, M. (2010). Learning to be a programmer in a complex organization.
  *J. Workplace Learning* 22(3):180–194. doi:10.1108/13665621011028620.
- Ju, A., Sajnani, H., Kelly, S., Herzig, K. (2021). A case study of onboarding in software
  teams: tasks and strategies. *ICSE 2021*. doi:10.1109/ICSE43902.2021.00063;
  arXiv:2103.05055.
- Labuschagne, A., Holmes, R. (2015). Do onboarding programs work? *MSR 2015*.
  doi:10.1109/MSR.2015.45.
- LaToza, T. D., Garlan, D., Herbsleb, J. D., Myers, B. A. (2007). Program comprehension as
  fact finding. *ESEC/FSE 2007*. doi:10.1145/1287624.1287675.
- LaToza, T. D., Myers, B. A. (2010). Hard-to-answer questions about code. *PLATEAU 2010*.
  doi:10.1145/1937117.1937125.
- Levesque, L. L., Wilson, J. M., Wholey, D. R. (2001). Cognitive divergence and shared mental
  models in software development project teams. *J. Organizational Behavior* 22(2):135–144.
  doi:10.1002/job.87.
- Littman, D. C., Pinto, J., Letovsky, S., Soloway, E. (1987). Mental models and software
  maintenance. *J. Systems and Software* 7(4):341–355. doi:10.1016/0164-1212(87)90033-1.
- Maalej, W., Tiarks, R., Roehm, T., Koschke, R. (2014). On the comprehension of program
  comprehension. *ACM TOSEM* 23(4), art. 31. doi:10.1145/2622669.
- Manshreck, T., Sadowski, C. (2020). Code review. In *Software Engineering at Google*
  (O'Reilly), ch. 9. abseil.io/resources/swe-book/html/ch09.html.
- Mathieu, J. E., Heffner, T. S., Goodwin, G. F., Salas, E., Cannon-Bowers, J. A. (2000). The
  influence of shared mental models on team process and performance. *J. Applied
  Psychology* 85(2):273–283. doi:10.1037/0021-9010.85.2.273.
- Minelli, R., Mocci, A., Lanza, M. (2015). I know what you did last summer. *ICPC 2015*.
  doi:10.1109/ICPC.2015.12.
- Mockus, A. (2009). Succession: measuring transfer of code and knowledge between
  developers. *ICSE 2009*. doi:10.1109/ICSE.2009.5070509.
- Mockus, A., Herbsleb, J. D. (2002). Expertise Browser: a quantitative approach to
  identifying expertise. *ICSE 2002*. doi:10.1145/581339.581401.
- Müller, H. A., Jahnke, J. H., Smith, D. B., Storey, M.-A., Tilley, S. R., Wong, K. (2000).
  Reverse engineering: a roadmap. *ICSE Future of Software Engineering*.
  doi:10.1145/336512.336526.
- Müller, H. A., Klashinsky, K. (1988). Rigi: a system for programming-in-the-large. *ICSE
  1988*. doi:10.1109/ICSE.1988.93690.
- Naur, P. (1985). Programming as theory building. *Microprocessing and Microprogramming*
  15(5):253–261. doi:10.1016/0165-6074(85)90032-8. Reprinted in *Computing: A Human
  Activity* (ACM Press, 1992) and in Cockburn, *Agile Software Development: The Cooperative
  Game* (2nd ed., Addison-Wesley, 2006), Appendix B.
- Petre, M. (2009). Insights from expert software design practice. *ESEC/FSE 2009*.
  doi:10.1145/1595696.1595731.
- Petre, M., Blackwell, A. F. (1999). Mental imagery in program design and visual
  programming. *IJHCS* 51(1):7–30. doi:10.1006/ijhc.1999.0267.
- Plonka, L., Sharp, H., van der Linden, J., Dittrich, Y. (2015). Knowledge transfer in pair
  programming: an in-depth analysis. *IJHCS* 73:66–78. doi:10.1016/j.ijhcs.2014.09.001.
- Rajlich, V., Wilde, N. (2002). The role of concepts in program comprehension. *IWPC
  2002*. doi:10.1109/WPC.2002.1021348.
- Rigby, P. C., Bird, C. (2013). Convergent contemporary software peer review practices.
  *ESEC/FSE 2013*. doi:10.1145/2491411.2491444.
- Rigby, P. C., Zhu, Y. C., Donadelli, S. M., Mockus, A. (2016). Quantifying and mitigating
  turnover-induced knowledge loss. *ICSE 2016*. doi:10.1145/2884781.2884851.
- Rodeghero, P., Zimmermann, T., Houck, B., Ford, D. (2021). Please turn your cameras on:
  remote onboarding of software developers during a pandemic. *ICSE-SEIP 2021*.
  doi:10.1109/ICSE-SEIP52600.2021.00013; arXiv:2011.08130.
- Rugaber, S. (1995). Program comprehension. Draft for *Encyclopedia of Computer Science and
  Technology* (Marcel Dekker). cc.gatech.edu/reverse/repository/encyc.ps (Wayback).
- Rugaber, S. (2000). The use of domain knowledge in program understanding. *Annals of
  Software Engineering* 9:143–192. doi:10.1023/A:1018976708691.
- Ryan, S., O'Connor, R. V. (2013). Acquiring and sharing tacit knowledge in software
  development teams. *IST* 55(9):1614–1624. doi:10.1016/j.infsof.2013.02.013.
- Sadowski, C., Söderberg, E., Church, L., Sipko, M., Bacchelli, A. (2018). Modern code
  review: a case study at Google. *ICSE-SEIP 2018*. doi:10.1145/3183519.3183525.
- Schmidt, C. T., Kude, T., Heinzl, A., Mithas, S. (2014). How agile practices influence the
  performance of software development teams: the role of shared mental models and backup.
  *ICIS 2014*. AIS eLibrary.
- Sillito, J., Murphy, G. C., De Volder, K. (2006). Questions programmers ask during software
  evolution tasks. *FSE 2006*. doi:10.1145/1181775.1181779. Journal version: *IEEE TSE*
  34(4):434–451 (2008). doi:10.1109/TSE.2008.26.
- Sim, S. E., Holt, R. C. (1998). The ramp-up problem in software projects: a case study of
  how software immigrants naturalize. *ICSE 1998*. doi:10.1109/ICSE.1998.671389.
- Spinellis, D. (2003). *Code Reading: The Open Source Perspective*. Addison-Wesley. ISBN
  0-201-79940-5. spinellis.gr/codereading.
- Steinmacher, I., Silva, M. A. G., Gerosa, M. A., Redmiles, D. F. (2015). A systematic
  literature review on the barriers faced by newcomers to open source software projects.
  *IST* 59:67–85. doi:10.1016/j.infsof.2014.11.001.
- Steinmacher, I., Conte, T., Gerosa, M. A., Redmiles, D. (2015). Social barriers faced by
  newcomers placing their first contribution in open source software projects. *CSCW 2015*.
  doi:10.1145/2675133.2675215.
- Steinmacher, I., Conte, T. U., Treude, C., Gerosa, M. A. (2016). Overcoming open source
  project entry barriers with a portal for newcomers. *ICSE 2016*.
  doi:10.1145/2884781.2884806.
- Storey, M.-A. D., Wong, K., Müller, H. A. (2000). How do program understanding tools
  affect how programmers understand programs? *Science of Computer Programming*
  36(2–3):183–207. doi:10.1016/S0167-6423(99)00036-2.
- Tan, X., Zhou, M., Sun, Z. (2020). A first look at good first issues on GitHub. *ESEC/FSE
  2020*. doi:10.1145/3368089.3409746. Follow-up: Tan et al. (2023). Is it enough to
  recommend tasks to newcomers? *ICSE 2023*. doi:10.1109/ICSE48619.2023.00064;
  arXiv:2302.05058.
- von Mayrhauser, A., Vans, A. M. (1996). Identification of dynamic comprehension processes
  during large scale maintenance. *IEEE TSE* 22(6):424–437. doi:10.1109/32.508315.
- Williams, L., Kessler, R. R., Cunningham, W., Jeffries, R. (2000). Strengthening the case
  for pair programming. *IEEE Software* 17(4):19–25. doi:10.1109/52.854064.
- Wilson, A. (2015). Mob programming — what works, what doesn't. *XP 2015*, LNBIP 212.
  doi:10.1007/978-3-319-18612-2_33.
- Xia, X., Bao, L., Lo, D., Xing, Z., Hassan, A. E., Li, S. (2018). Measuring program
  comprehension: a large-scale field study with professionals. *IEEE TSE* 44(10):951–976.
  doi:10.1109/TSE.2017.2734091.
- Zhou, M., Mockus, A. (2012). What make long term contributors: willingness and opportunity
  in OSS community. *ICSE 2012*. doi:10.1109/ICSE.2012.6227164.
- Zuill, W. (2014). Mob programming — a whole team approach. Agile 2014 experience report.
  agilealliance.org/wp-content/uploads/2015/12/ExperienceReport.2014.Zuill_.pdf.
