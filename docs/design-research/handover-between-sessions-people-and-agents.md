---
status: research
date: 2026-09-15
---

# Handover between sessions, people, and agents

Research date: 2026-09-15

This note documents what the handover literature says about a boundary at which one holder of
work state gives way to another: what must be transferred, what is measured to be lost, and what
a written artifact can and cannot carry. It reads three bodies of material side by side. The
first is the high-consequence shift-handover work (space shuttle mission control, nuclear power,
railroad and ambulance dispatch, UK process industry), where the handoff is a studied unit of
work with observed strategies and named incidents. The second is the hospital handoff literature,
which is the only place the failure rate of a handover has been measured before and after a
protocol was imposed. The third is the interruption and resumption research on information
workers and programmers, which treats the boundary as a handover from a person to the same
person later, and which the agent-era material re-enacts at the boundary between one Agent
Session and the next. The agent-era practices themselves (Claude Code compaction and resume,
Anthropic's context-engineering and multi-agent accounts, the OpenAI Agents SDK handoff, Codex
`resume` and `/compact`, Beads, Agent Handoff, the practitioner "intentional compaction"
workflows) are documented from their own pages, together with the 2026 studies of what
summarisation loses. It is documentary: it records what the sources found, with their evidence
and limits, and maps each finding to where the existing notes in this directory touch it. It
does not evaluate fit for Dashpot or any tool. Terminal citations are primary — the paper, the
author's copy, the vendor's own documentation page — and every figure is reported as the source
states it, with the sample and the kind of evidence (measured, qualitative, testimonial,
argument). Items read only as abstract or metadata are marked; anything recalled rather than
read is marked unverified. Where an earlier note already covers a source, this note links to it
rather than repeating it: Naur on what a document cannot carry and the team-cognition and
succession literature are in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model),
the supervisory-control and situation-awareness literature (Bainbridge, Parasuraman, Sheridan,
Endsley, adaptive automation, skill fade) is in
[adjacent-literatures.md](adjacent-literatures.md#supervising-automation), the interruption-cost
figures already cited are in
[track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking),
transcript retention and provenance are in
[track-rationale-as-artifact.md](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance),
and the positioning of Beads, Agent Handoff, and Git-as-memory is in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#a-transcript-is-local-interaction-state-not-durable-team-state).

## Finding

Across every setting in which handover has been observed, the thing transferred is not a list
of facts but a state model plus a stance: what the outgoing holder believes the situation is,
what they were about to do, what they expect to happen, and how they would react if it does not.
Patterson, Roth, Woods, Chow and Gomes catalogued 21 strategies from 422 hours of observation in
mission control, nuclear plants, railroad dispatch and ambulance dispatch and found the update
was in every case interactive, verbal and face-to-face, with the outgoing controller's stance
toward plan changes given in every mission-control handoff observed, and 8 of 75 incoming
questions in the 16 NASA handoffs serving to detect errors in the outgoing holder's model
([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026), full text, measured
observation). The costs of a missed update they enumerate are all model costs — an incorrect or
incomplete state model, being unprepared for the consequences of prior events, failing to
anticipate, dropping or reworking activity in progress, an unwarranted shift in goals or
priorities ([Patterson and Woods 2001](https://doi.org/10.1023/A:1012705926828), abstract plus
the 2004 paper's summary). Lardner's HSE review of five investigated incidents at or after shift
change (Sellafield 1983, Piper Alpha, Windscale, two others) finds that "in four of the five
incidents, communication by written means failed as the intended message was misunderstood or
simply not communicated", that all five involved planned maintenance, and that in sixteen taped
nuclear-reprocessing handovers all six misunderstandings were repaired only because the incoming
"victim" asked for confirmation
([Lardner 1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf),
full text, incident analysis plus observation). The hospital work supplies the numbers: purely
verbal transfer retained 2.5% of simulated patient data after five cycles, verbal plus
note-taking 85.5%, a printed sheet 99% ([Bhabra et al. 2007](https://doi.org/10.1308/003588407X168352),
abstract, measured, n=12 simulated patients); the sender's single most important item failed to
reach the receiver 60% of the time while senders believed it had ([Chang et al.
2010](https://doi.org/10.1542/peds.2009-0351), abstract, measured, 52 interview pairs (qualified 2026-09-15: the abstract, Results, says "We conducted 52 interviews, which constituted 59% of eligible interviews. Seventy-two patients were discussed"; it does not state the number of sender–receiver pairs)); and the
structured I-PASS bundle reduced medical errors 23% and preventable adverse events 30% across
10,740 admissions at nine hospitals with no change in oral-handoff duration ([Starmer et al.
2014](https://doi.org/10.1056/NEJMsa1405556), abstract, measured, verified against the seed's
"23%"). What is written down survives; what is written down is also what the writer thought
mattered at the time, and Cohen, Hilligoss and Kajdacsy-Balla Amaral's "a handoff is not a
telegram" argues that the receiver's questions, not the sender's summary, are where the model is
actually reconstructed ([Cohen et al. 2012](https://doi.org/10.1186/cc10536), full text,
argument with cited measures). The interruption literature makes the same point about the
handover from a person to their later self: programmers resumed editing within a minute in only
10% of 10,000 sessions, navigated before editing in 93%, and restored global position, goal,
plan and context in that order from cues rather than from memory ([Parnin and Rugaber
2011](https://doi.org/10.1007/s11219-010-9104-9), full text, measured), while 27% of
interrupted information-worker tasks were not resumed within two hours ([Iqbal and Horvitz
2007](https://doi.org/10.1145/1240624.1240730), full text, measured, 27 users, 2,267 hours).
Klein, Feltovich, Bradshaw and Woods hold that common-ground breakdown is inevitable, that "no
amount of procedure or documentation can totally prevent them", and that no automation "today or
on the horizon" can enter the Basic Compact fully — a "basic coordinative asymmetry" that makes
handover to a machine a one-sided transfer unless the machine can signal its status and take
direction ([Klein et al. 2005](https://ihmc.us/users/jbradshaw/publications/Common_Ground_Single.pdf),
full text, argument). The agent-era practices re-implement the artifact side of this record and
say so: Claude Code compaction keeps "your requests and intent, key technical concepts, files
examined or modified with important code snippets, errors and how they were fixed, pending
tasks, and current work", re-reads up to five recently modified files, and warns that "detailed
instructions from early in the conversation may be lost" and that "full tool outputs and
intermediate reasoning are gone" ([Claude Code, Context window](https://code.claude.com/docs/en/context-window),
full text, vendor documentation); Anthropic's engineering account concedes that "overly
aggressive compaction can result in the loss of subtle but critical context whose importance
only becomes apparent later" ([Anthropic 2025a](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents));
the OpenAI Agents SDK hands the entire prior history to the receiving agent by default and lets
an `input_filter` strip it ([OpenAI Agents SDK, Handoffs](https://openai.github.io/openai-agents-python/handoffs/));
Agent Handoff's snapshot schema (primary outcome, smallest acceptance proof, execution envelope,
next direct outcome step) is a handoff form with the receiver's cross-check replaced by a
required "acceptance proof" ([Agent Handoff standard](https://github.com/artyomboyko/Agent_Handoff/blob/main/AGENT_HANDOFF_STANDARD.md));
and the 2026 compaction studies measure what the summariser drops: peak tokens fall 26–54% but
the compactor "is fundamentally unaware of precisely what information the agent will need
later", retained information "fluctuate[s] substantially from run to run", and compression
"can weaken the influence of recent interactions, increasing blocked actions, repeated
exploration, and instability across runs" ([ACON](https://arxiv.org/abs/2510.00615),
[Slipstream](https://arxiv.org/abs/2605.08580), [Parallel Context
Compaction](https://arxiv.org/abs/2605.23296), [TRACE](https://arxiv.org/abs/2608.06503),
abstracts, measured on benchmarks). No source in either literature measures what a human reader
recovers from an agent's compaction summary or handoff snapshot; that boundary is documented by
its designers and by benchmark accuracy, not by the receiver's questions.

## What must be transferred: the high-consequence handover studies

### Patterson, Roth, Woods, Chow and Gomes 2004 — 21 strategies in four settings

Read level: full text (author-archive PDF at
[interruptions.net](http://interruptions.net/literature/Patterson-IntJQualHealthCare04.pdf);
publisher's copy at [doi:10.1093/intqhc/mzh026](https://doi.org/10.1093/intqhc/mzh026) returned
403). Evidence type: measured observation, secondary analysis of data collected for other
purposes, which the authors flag as a limit.

The study's sample table gives 67 hours of observation at NASA Johnson Space Center (16
shift-change handoffs, five personnel, typical update 10 minutes), 177 hours at two Canadian
nuclear plants (27 personnel interviewed, seven shift-change handoffs observed with 15 personnel,
10–15 minutes), 60 hours of US railroad dispatch (multiple break handoffs on 11 shifts, 22
personnel, 1–5 minutes), and 118 hours of Toronto ambulance dispatch (5–10 minutes). The 21
strategies were derived from the earlier mission-control study and from comparing medical and
non-medical handoffs; 19 of the 21 were observed in at least one setting, and the two not
observed were readback (strategy 7) and delivering the update in the same order every time
(strategy 10) ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)).

The strategies, in the paper's grouping, are:

- interactive, verbal, face-to-face update with questioning; additional updates from
  colleagues; limiting interruptions during the update; topics initiated by the incoming as well
  as the outgoing; limiting operator actions during the update;
- including in the update the outgoing team's stance toward changes to plans and contingencies
  — given in every observed shuttle mission-control handoff, illustrated by an APU
  hydraulic-leak case in which the outgoing controller told the incoming what the team intended
  to do if the leak rate changed; readback; the outgoing writing a one-paragraph summary of the
  shift in the handwritten log before the update; the incoming assessing current status before
  the update ("walk the board" at the nuclear plants); same order every time; the incoming
  scanning historical data (log entries) before or after; reviewing automated logs;
- daily 15-minute updates for on-call staff; the outgoing having held the position; the incoming
  receiving primary access to the tools and paperwork; handwritten annotations kept alongside
  the official record (at the railroad, a meal-break form whose content "was not considered
  critical enough to be maintained in the 'official record'"); unambiguous transfer of
  responsibility (the seat, the headphone jack — nuclear staff reported it is "almost insulting"
  to plug in before the update is complete); the outgoing remaining responsible until the update
  is done; overhearing others' updates; a one-hour overlap at mission control in which the
  outgoing oversees the incoming; and delaying transfer during critical activity (once, at
  mission control, for several hours during an undiagnosed APU anomaly)
  ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)).

Two observations bear on what an artifact carries. First, the incoming person's questions had an
error-detection function: of 75 questions asked by incoming controllers during the 16 NASA
handoffs, eight were asked to detect errors ("Do you know that for sure?"), which the authors
attribute to the incoming holder's "fresh perspective". Second, what is said depends on what the
displays already show. Ambulance dispatchers did not convey unit locations because the GPS map
showed them, only the map's inaccuracies; the authors note that health care lacks "at a glance"
displays of status and therefore has to convey more verbally
([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)).

### Patterson and Woods 2001 — the mission-control update and the seven costs

Read level: abstract ([PubMed 12269342](https://pubmed.ncbi.nlm.nih.gov/12269342/)) and secondary
via the 2004 paper; the Springer full text at
[doi:10.1023/A:1012705926828](https://doi.org/10.1023/A:1012705926828) was not fetched (HTML
landing page; PDF 403). An earlier HFES conference version exists at
[doi:10.1177/107118139704100155](https://doi.org/10.1177/107118139704100155) (metadata only).
Evidence type: qualitative observation of 16 shift changes during the STS-76 mission.

The abstract states that the observations show "the importance of prior knowledge in the
updates" and that "missing updates can leave flight controllers vulnerable to being unprepared"
([Patterson and Woods 2001](https://pubmed.ncbi.nlm.nih.gov/12269342/)). The 2004 paper reports
from it the seven costs incurred when an incoming controller fails to be told, forgets, or
misunderstands an item: (1) an incorrect or incomplete model of the system's state, (2) being
unaware of significant data or events, (3) being unprepared to deal with the impacts of
previous events, (4) failing to anticipate future events, (5) lacking knowledge needed to
perform tasks safely, (6) dropping or reworking activities that were in progress or that the
team had agreed to do, and (7) an unwarranted shift in goals, decisions, priorities or plans
([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026), citing Patterson and Woods
2001). All seven are properties of the receiver's model, not of the artifact.

### Lardner 1996 — the HSE review and incidents at changeover

Read level: full text of the 19-page report, recovered from the Internet Archive
([oto96003.pdf, 2008 capture](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf));
the live HSE URL returns 404 and the National Archives mirror 405. Evidence type: literature
review and incident analysis, with a small number of empirical studies summarised.

Lardner defines shift changeover as three phases — preparation by the outgoing person, the
handover exchange itself, and cross-checking by the incoming person as they take over — and
draws from communication theory that redundancy through more than one channel, two-way
feedback, and face-to-face exchange are the conditions under which misunderstandings are
detected; that misunderstandings are "an inevitable feature" of communication and most likely
when the two parties' mental models differ widely (deviations from normal working, maintenance,
lengthy absence, an experienced person handing to an inexperienced one); that the key
information should be specified and irrelevant information excluded; and that natural language
is ambiguous and over-confidence in having been understood is common ([Lardner
1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf)).

The incident section cites a MHIDAS query finding three major accidents at or after shift
changeover, with 20 fatalities, 35 injuries and £46 million of damage, and analyses five
published investigations: the Sellafield beach contamination of 1983, where a log entry carried
forward across shifts changed from "ejections from HASW" to "ex HASW washout" and tank contents
were described by origin rather than nature; Piper Alpha, where the Cullen inquiry found that
the removal of a pressure safety valve and the fitting of a blind flange were not communicated at
handover, that there were no written handover procedures and the content of the notepad was at
the operator's discretion; the Sutherland fatality of 1987; the Windscale vitrification-plant
shield-door incident, in which a temporary override was not carried forward across four shifts;
and an offshore valve injury where a message was not passed at handover. The review's summary is
that all five involved planned maintenance and that "in four of the five incidents,
communication by written means failed as the intended message was misunderstood or simply not
communicated" ([Lardner
1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf)).

The empirical studies it summarises: a nuclear-reprocessing observation in which sixteen taped
handovers and their logs yielded six misunderstandings, four safety-related, most arising during
discussion of deviations from normal working, and "on each occasion the misunderstanding was
identified and repaired by the potential 'victim'" asking for confirmation, clarification and
repetition; handovers after a ten-day rest were longer, added a historical summary, and the
incoming person read back through the logs afterwards; a 12-hour versus 8-hour shift comparison
in which 80% of reactor operators found handover easier on 12-hour shifts because they received
it from the person they had briefed, while seven-day absences were harder; a survey of 19
chemical plants and 50 interviewees in which fitters and managers disagreed about whether
permits-to-work were renewed at shift change; and a UK oil-refinery intervention that analysed
each post's information needs, designed structured log books from them and trained behaviours,
affecting 315 personnel in 63 posts, after which 70 interviewees (21%) reported that
three-quarters found the structured logs beneficial and over half thought handovers themselves
had improved ([Lardner
1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf),
testimonial evaluation). The nursing studies it cites found taped reports inadequate for
intensive and coronary care and that a computer-generated report eliminated the transcription of
unchanged information.

The HSE's current topic page keeps the three elements and the same principles — face-to-face,
two-way, verbal and written, "based on an analysis of the information needs of incoming staff",
and "given as much time as necessary" — and cites Sellafield and Piper Alpha as the incidents
behind them ([HSE, Shift handover](https://www.hse.gov.uk/humanfactors/topics/shift-handover.htm),
full text, guidance). Its audit methodology (Keil Centre, 2006) reports that around half of the
delegates at its seminars knew of incidents in their own organisations attributable to handover
failure and names the same high-risk handovers: after a lengthy absence, between experienced and
inexperienced staff, and during plant upset (metadata via the topic page; the PDF was not read).

### What the written record could and could not carry

The pattern across these sources is consistent enough to state without interpretation. The
written log carried state (what is out of service, what override is in force) when it was
structured around the incoming person's information needs, and failed when the entry was
transcribed by hand across shifts (Sellafield), left to the writer's discretion (Piper Alpha),
or not carried forward at all (Windscale) ([Lardner
1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf)).
What the log did not carry, and what every observed high-consequence handoff conveyed verbally,
was the stance — how the outgoing team intended to react to contingencies — and the
error-detecting questions of the incoming holder ([Patterson et al.
2004](https://doi.org/10.1093/intqhc/mzh026)). Patterson and colleagues note that the written
summary and the verbal update were used together: the one-paragraph log summary was written
before the update and the incoming controller scanned the log before or after it, so the
artifact bounded the conversation rather than replacing it.

## Measured handover failure rates in hospitals

### Retention experiments: verbal, notes, printed

Read level: abstracts. Evidence type: measured, simulated.

Pothier, Monteiro, Mooktiar and Shaw had nurses hand over twelve simulated patients through five
successive cycles. Purely verbal handover lost all data after three cycles; verbal with
note-taking transferred 31% correctly after five cycles; a typed sheet plus verbal handover
showed minimal loss ([Pothier et al. 2005](https://doi.org/10.12968/bjon.2005.14.20.20053)).
Bhabra, Mackeith, Monteiro and Pothier repeated the design with senior house officers handing
over one-to-one: 2.5% of information retained after five verbal-only cycles, 85.5% with verbal
plus note-taking, 99% with a printed handout; the authors call the scenario artificial and note
that the handout "relies on … being regularly updated" ([Bhabra et al.
2007](https://doi.org/10.1308/003588407X168352)). Both studies measure fact retention across
repeated relays rather than the outcome of any single handoff.

### Omissions and the egocentric sender

Read level: abstracts. Evidence type: measured, observational.

Arora, Johnson, Lovinger, Humphrey and Meltzer interviewed 26 interns about 82 patients and
collected 25 incidents plus 21 "worst events"; omitted content (medications, active problems,
pending tests) and failure-prone processes (lack of face-to-face communication) led to
uncertainty and repeated tests; interns wanted a face-to-face verbal exchange reviewing
anticipated issues plus a legible, updated written sheet ([Arora et al.
2005](https://doi.org/10.1136/qshc.2005.015107)). Horwitz and colleagues audiotaped 88 sign-out
sessions on eight teams over twelve days (503 patient sign-outs, 319 unique patient-days) and
verified 24 sign-out-related problems: five delays including one ICU transfer, four near
misses, fifteen inefficiencies; omissions were of clinical condition, recent or scheduled
events, tasks to be done, anticipatory guidance, and "a specific plan of action and rationale
for assigned tasks" ([Horwitz et al. 2008](https://doi.org/10.1001/archinte.168.16.1755)).
Chang, Arora, Lev-Ari, D'Arcy and Keysar interviewed both parties to 52 handoffs covering 72
patients: the sender's single most important piece of information was not successfully
communicated 60% of the time although the sender believed it had been; the two parties disagreed
on the rationale 60% of the time; to-do items were communicated in 65% of cases, anticipatory
guidance in 69%, knowledge items in 38%; peer quality ratings were nonetheless high, which the
authors read as egocentric overestimation of one's own communication ([Chang et al.
2010](https://doi.org/10.1542/peds.2009-0351)).

### Structured protocols: SBAR and I-PASS

Read level: I-PASS 2012 full text ([PMC9923540](https://pmc.ncbi.nlm.nih.gov/articles/PMC9923540/));
the 2013 and 2014 trials and the SBAR papers as abstracts. Evidence type: measured
before-and-after for the trials; case study for SBAR.

SBAR — Situation, Background, Assessment, Recommendation — is presented by Haig, Sutton and
Whittington through a single case (an INR/warfarin call), pocket cards, and the observation that
nurses hesitated to give the "recommendation" step ([Haig et al. 2006](https://doi.org/10.1016/s1553-7250(06)32022-3)).
Leonard, Graham and Bonacum's paper on standardised communication was read as abstract only; the
Navy-submarine origin often attributed to SBAR and the "over 70% of sentinel events involve
communication" figure were not verified in this pass and are marked unverified
([Leonard et al. 2004](https://doi.org/10.1136/qshc.2004.010033), abstract; PMC full text not
served). Müller and colleagues' systematic review of SBAR found eight before-after and three
controlled studies; of 26 outcomes eight improved significantly, eleven were described as
improved without statistical test, six were unchanged, and they rate the evidence "moderate",
strongest for telephone communication, with "a lack of high-quality research" ([Müller et al.
2018](https://doi.org/10.1136/bmjopen-2018-022202)).

I-PASS was designed from what was most often absent in existing handoffs. Starmer and
colleagues describe the elements — Illness severity, Patient summary, Action list, Situation
awareness and contingency planning, Synthesis by receiver — and say they chose illness
severity, contingency planning and read-back because those were the items most often missing; a
Riesenberg review of handoff mnemonics had found 24 mnemonics in 46 articles, and a SIGNOUT pilot found the majority
of verbal handoffs did not adhere to the mnemonic ([Starmer et al. 2012](https://doi.org/10.1542/peds.2011-2966),
full text). The single-site trial at Boston Children's (1,255 admissions, 84 residents) reduced
medical errors from 33.8 to 18.3 per 100 admissions and preventable adverse events from 3.3 to
1.5, with omissions reduced in 11 of 14 categories on the unit that had a computerised handoff
tool and 2 of 14 on the unit without ([Starmer et al. 2013](https://doi.org/10.1001/jama.2013.281961)).
The nine-hospital study of 10,740 admissions reduced medical errors 23% (24.5 to 18.8 per 100
admissions, P<0.001) and preventable adverse events 30% (4.7 to 3.3, P<0.001), left
nonpreventable events unchanged (3.0 versus 2.8, P=0.79), was significant at six of the nine
sites, increased the inclusion of all nine written and five oral key elements (P<0.001 for each),
and did not change the oral handoff's duration (2.4 versus 2.5 minutes per patient) ([Starmer et
al. 2014](https://doi.org/10.1056/NEJMsa1405556)). The seed's "23% fewer medical errors" is
confirmed by the abstract.

### The critiques: what "standardise" does not settle

Read level: abstracts for Cohen and Hilligoss and for Riesenberg; full text for the 2012 Critical
Care commentary (Europe PMC XML for [PMC3396216](https://europepmc.org/article/PMC/PMC3396216)).
Evidence type: literature review and argument.

Cohen and Hilligoss reviewed the handoff literature to July 2008 and drew four conclusions: the
concept of a handoff is poorly delimited; "standardise" is unclear as a prescription; handoffs
serve functions beyond safety whose trade-offs are unanalysed; and standardisation had not been
shown to yield marked gains in measured outcomes ([Cohen and Hilligoss 2010](https://doi.org/10.1136/qshc.2009.033480)).
Riesenberg, Leitzsch, Massucci and colleagues screened 2,590 records to 46 articles (1987–June
2008) and catalogued 91 barriers and 140 strategies; of 18 research articles only six included any
effectiveness measure, a "paucity of evidence" ([Riesenberg et al. 2009](https://doi.org/10.1097/ACM.0b013e3181bf51a6)).
Cohen, Hilligoss and Kajdacsy-Balla Amaral's "A handoff is not a telegram" argues that the
one-way transmission model hampers improvement; they list five kinds of content (background,
course, to-dos, uncertainty, anticipation), note that "as electronic records … make the basic
data ever more widely accessible, these data become less crucial in a handoff", and cite that in
the majority of handoffs the incoming clinician asked no questions, that important information
was omitted or corrupted in more than 20% of sequential handoffs, that physicians agreed on the
main problem in fewer than half of emergency-department-to-ward handoffs, a twofold increase in
preventable adverse events under cross-cover, handoffs implicated in 28% of surgical errors and
20–24% of malpractice claims, and a team-mental-model meta-analysis attributing up to 30% of
performance variance to shared models — while noting that differing models can be safer when
the diagnosis is unclear ([Cohen et al. 2012](https://doi.org/10.1186/cc10536); the figures are
the commentary's citations of other studies and are reported here as secondary). Randell, Wilson
and Woodward's observation of 15 medical and 33 nursing handovers at three sites found the
verbal report "practically focused" and concluded that technology should support rather than
replace the verbal exchange ([Randell et al. 2011](https://doi.org/10.1016/j.ijmedinf.2011.08.006),
abstract, qualitative).

## Interruption and resumption: handover to one's later self

The interruption literature treats the boundary as a self-handover. It is documented here because
the agent-era session boundary is closer to it than to a shift change: the "receiver" has the
same tools and files but a different memory state.
[track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)
already cites Mark, Gudith and Klocke 2008 and the two Parnin and Rugaber 2011 percentages; this
section adds the mechanism papers and the framework of what is restored.

### Memory for goals and resumption lag

Read level: abstracts (Altmann and Trafton 2002; Trafton et al. 2003) and abstract plus
introduction (Monk et al. 2008), all from author-archive PDFs at interruptions.net. Evidence
type: laboratory measurement.

Altmann and Trafton's memory-for-goals model treats a suspended goal as a memory trace subject to
decay and interference, retrievable only if it was strengthened before suspension and if a cue
is present at resumption ([Altmann and Trafton 2002](https://doi.org/10.1207/s15516709cog2601_2)).
Trafton, Altmann, Brock and Mintz showed that an eight-second warning before an interruption (an
"interruption lag") let participants prepare and resume faster, and that without the warning
resumption improved with practice ([Trafton et al. 2003](https://doi.org/10.1016/S1071-5819(03)00023-5)).
Monk, Trafton and Boehm-Davis found that longer and more demanding interruptions produced longer
resumption lags, that the decay occurred within the first minute, that rehearsal mitigated it,
and report a resumption lag of about 1,548 ms against a 949 ms baseline in their first experiment
([Monk et al. 2008](https://doi.org/10.1037/a0014402)). The unit here is seconds, not the
minutes of the field studies; the relevance is the mechanism — the goal must be re-activated by a
cue, and the cue can be prepared before the boundary.

### Information workers: Mark 2005 and Iqbal and Horvitz 2007

Read level: full text (author-archive PDFs). Evidence type: measured field observation and
instrumented logging.

Mark, Gonzalez and Harris shadowed 24 information workers (seven managers, nine analysts, eight
developers) for more than 700 hours: 57% of working spheres were interrupted; the average time
in a working sphere before switching was 11 minutes 4 seconds; 77.2% of interrupted work was
resumed the same day, after 25 minutes 26 seconds on average (standard deviation 54 minutes 48
seconds) and 2.26 intervening working spheres; 90.1% of resumptions were self-initiated. They
cite O'Conaill and Froehlich's finding that 41% of interrupted tasks were never resumed and give
a blinking-cursor left in a document as an example of a self-placed resumption cue ([Mark et al.
2005](https://doi.org/10.1145/1054972.1055017)). Iqbal and Horvitz logged 27 Microsoft
developers, researchers and managers for two weeks (2,267 hours, 974 sessions): 40.8% of email
alerts were answered immediately and 59.2% after an average 7 minutes 32 seconds; users left
about three windows suspended; the return to any suspended application took 9 minutes 33
seconds after an email diversion and the "resumption phase" — the time to return to the same
task state — 16 minutes 33 seconds; 27% of alerts diverted the user for more than two hours
from the prior active windows; and interviewees described "preparing" before switching (saving,
copying, stabilising state) so that the task could be resumed ([Iqbal and Horvitz
2007](https://doi.org/10.1145/1240624.1240730)). The 27% figure is stated by the authors as
"27% of task suspensions resulted in more than two hours of time until resumption" and attributed
to "loss of context".

### Programmers: Parnin and DeLine 2010, Parnin and Rugaber 2011 and 2012

Read level: full text for the CHI 2010 and Software Quality Journal papers (author copies at
[chrisparnin.me](https://chrisparnin.me/pdf/parnin-sqj11.pdf)); abstract and introduction for the
ICPC 2012 paper. Evidence type: survey, instrumented logging, and a small laboratory study.

Parnin and DeLine surveyed 371 Microsoft programmers (of 2,000 invited) on how they suspend and
resume. Note-taking was "by far the most prevalent practice": 36% wrote a physical note before
suspending, 58% relied on a mental note, and 50% left a reminder cue in the environment (a text
selection, an open window); notes lived in physical media (47%), electronic files (40%), the
task database (16%) and email (15%). Only 11% said their task descriptions were well defined;
58% said the purpose was clear but the plan was not, and 55% described their tasks as broad.
On resuming, programmers re-read notes and the task description, navigated the source, and looked
for recent changes. In the laboratory study, 15 professional programmers (14 usable) were
interrupted 15 seconds after a substantive edit; those given two cues — a degree-of-interest
tree view and a content timeline — had "twice the success rate" of those with notes alone
(chi-square, p<0.1), and the notes-only group made more errors and re-located more; one
participant who resumed from notes alone forgot to reconnect an event handler. The paper cites
van Solingen's estimate of roughly an hour a day spent on interruptions with 15 minutes to
recover, O'Conaill and Froehlich's 40% of interrupted tasks never resumed, and Czerwinski's
finding that interrupted tasks took twice as long ([Parnin and DeLine 2010](https://doi.org/10.1145/1753326.1753342),
measured; the cited figures secondary).

Parnin and Rugaber's instrumented study of 10,000 sessions from 86 programmers plus a 414-response
survey found that the "edit lag" (time from session start to first edit) was under a minute in
only 10% of sessions and over 30 minutes in about 30%; only 7% of sessions involved no navigation
before editing; programmers viewed task information in 9% of sessions and in 75% of those the
edit lag exceeded 30 minutes; and the revision history was consulted during the edit lag in only
4%. Their framework distinguishes what is restored: global restoration (return to the last place,
navigate to remember), goal restoration (review the task assignment, execute the program, restore
from a task breakdown), plan restoration (review the source-change history or diffs, search for
prospective notes, TODOs or deliberately left compile errors), and context restoration; what needs
to be restored "depends on the breakpoint" at which the interruption fell ([Parnin and Rugaber
2011](https://doi.org/10.1007/s11219-010-9104-9)). The ICPC 2012 paper frames these as memory
failures of different types — prospective, episodic, associative, conceptual — and repeats that an
interruption "makes tasks take twice as long" with "twice as many errors", that a programmer's
day fragments into 15–30-minute sessions, and that the first 15–30 minutes of a longer session go
to recovery ([Parnin and Rugaber 2012](https://chrisparnin.me/pdf/infoneeds.pdf), abstract and
introduction; the doubling figures are the paper's citations, secondary). Earlier work on
programmers' information needs and the strategies they use in unfamiliar code is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#the-questions-comprehenders-ask).

## Common ground and handover to a machine

### Klein, Feltovich, Bradshaw and Woods 2005

Read level: full text of the authors' preprint dated June 2004
([Common_Ground_Single.pdf](https://ihmc.us/users/jbradshaw/publications/Common_Ground_Single.pdf));
the published chapter in Rouse and Boff's *Organizational Simulation* (Wiley) was not read.
Evidence type: argument, with illustrative cases.

The chapter defines joint activity through a Basic Compact — an agreement to work toward
coordination, to signal deviation, and to repair breakdowns — and interpredictability as its
product. Common ground is lost, the authors say, when parties lack experience together, see
different data, receive directives without the rationale, do not know each other's stance, lose a
communication channel, or are confused about who knows what. "We assert that, no matter how much
care is taken, breakdowns in common ground are inevitable: no amount of procedure or
documentation can totally prevent them"; the practical baseline is detecting and repairing
breakdowns, "not attempting to document all assumptions and duplicate the contents of each
person's mind". The Fundamental Common Ground Breakdown is the case in which party A assumes B
knows X, B does not, and the divergence grows until a coordination surprise reveals it ([Klein et
al. 2005](https://ihmc.us/users/jbradshaw/publications/Common_Ground_Single.pdf)).

The section on automation is the closest the literature read here comes to "handover to a
machine". "No form of automation today or on the horizon is capable of entering fully into the
rich forms of Basic Compact that are used among people. Thus, agents cannot be full-fledged
members of human-agent teams in the same sense that other people are — a basic coordinative
asymmetry between people and automata." The authors state three requirements for an agent to
partake even partially: to act predictably and be directable (citing Christoffersen and Woods
2002), to signal its status and intentions, and to interpret the signals of others ([Klein et al.
2005](https://ihmc.us/users/jbradshaw/publications/Common_Ground_Single.pdf)). The related
supervisory-control literature, including Bainbridge's point that the state model needed for
takeover takes time to build, is documented in
[adjacent-literatures.md](adjacent-literatures.md#bainbridges-ironies) and is not repeated
here. Naur's argument that a document cannot carry the theory a team holds is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#naur-1985-the-team-as-the-theorys-holder).

## Agent-era handoff practices: what they transfer and what they drop

This section records the practices from their own pages. Read level is full text of the vendor
or project documentation in every case; evidence type is vendor or practitioner description
unless a measurement is named.

### Claude Code: compaction, rewind, resume, subagents

The Claude Code documentation describes three boundaries within one Agent Session and one
between sessions. Compaction is the in-session boundary. The context-window page's timeline
states what the automatic pass keeps: "The summary keeps: your requests and intent, key technical
concepts, files examined or modified with important code snippets, errors and how they were
fixed, pending tasks, and current work. It replaces the verbatim conversation: full tool outputs
and intermediate reasoning are gone." Its "What survives compaction" table lists what is
re-injected from disk rather than summarised — the system prompt, project-root CLAUDE.md and
unscoped rules, auto memory, the plan written in plan mode — and what is recovered by re-reading:
"up to five" files Claude read or edited, "most recently modified first", with files over 5,000
tokens returned as a path reference; invoked skill bodies are re-injected "capped at 5,000 tokens
per skill and 25,000 tokens total; oldest dropped first"; path-scoped rules and nested CLAUDE.md
files are "summarized away with everything else" and reload only when a matching file is read;
background commands and subagents keep running; and SessionStart hooks matching the `compact`
source run again ([Claude Code, Context window](https://code.claude.com/docs/en/context-window)).
The overview page says the pass "clears older tool outputs first, then summarizes the
conversation if needed. Your requests and key code snippets are preserved; detailed instructions
from early in the conversation may be lost. Put persistent rules in CLAUDE.md rather than relying
on conversation history" ([Claude Code, How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)).
`/compact [instructions]` lets the person say what to keep ("The summary keeps what you choose
instead of what the automatic pass guesses is important"); `/autocompact <tokens>` moves the
threshold; `/rewind` offers "Summarize from here" and "Summarize up to here", after which "a
**Summarized conversation** marker appears in the conversation where the compressed messages
were"; `/clear` is recommended "when switching to unrelated work" because "old conversation
crowds out the files you need next" ([Claude Code, Context window](https://code.claude.com/docs/en/context-window);
[Claude Code, Checkpointing](https://code.claude.com/docs/en/checkpointing)). The costs page
documents a "Compact instructions" section of CLAUDE.md as the standing version of the same
control ([Claude Code, Costs](https://code.claude.com/docs/en/costs)).

The between-session boundary is `claude --continue`, `--resume`, `/resume` (alias `/continue`),
which restore a transcript rather than a summary, and `/clear` or a fresh session, which restore
nothing except what is on disk ([Claude Code, Commands](https://code.claude.com/docs/en/commands)).
The best-practices page's advice for long work is to move the transfer into an artifact: "Once the
spec is complete, start a fresh session to execute it. The new session has clean context focused
entirely on implementation, and you have a written spec to reference"; and "After two failed
corrections, `/clear` and write a better initial prompt incorporating what you learned"
([Claude Code, Best practices](https://code.claude.com/docs/en/best-practices)). The same page
describes the reviewer subagent boundary as a deliberate loss: a reviewer "in a fresh subagent
context sees only the diff and the criteria you give it, not the reasoning that produced the
change". The subagent page describes the general form: a subagent has its own context window,
returns only a final summary to the parent, may be forked to inherit the whole conversation, may
be nested three deep, and its transcript is deleted after `cleanupPeriodDays` (30 days by
default) ([Claude Code, Subagents](https://code.claude.com/docs/en/sub-agents)). What is
documented at each of these boundaries is the mechanism; no page reports a measurement of what a
person or the next session recovers from the summary.

### Anthropic's context-engineering and multi-agent accounts

Anthropic's engineering post frames context as a finite "attention budget" subject to "context
rot" and names three techniques for long-horizon work. Compaction "summarize[s] its contents and
reinitiate[s] a new context window with the summary"; the Claude Code implementation "preserv[es]
architectural decisions, unresolved bugs, and implementation details while discarding redundant
tool outputs or messages", then continues "plus the five most recently accessed files". The
post's own limit statement is that "overly aggressive compaction can result in the loss of subtle
but critical context whose importance only becomes apparent later", and its advice is to tune for
recall first and precision second, with tool-result clearing as the lightest form. Structured
note-taking (a NOTES.md, a to-do list; the Pokémon example of tallies persisting across resets)
is the second technique, and sub-agents returning "a condensed, distilled summary (often
1,000–2,000 tokens)" the third; the post assigns compaction to extended back-and-forth,
note-taking to milestone-structured work, and multi-agent architectures to parallel research
([Anthropic 2025a](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents),
published 29 September 2025, full text, vendor argument).

The multi-agent research post describes the handoff from a lead agent to subagents and back. The
lead saves its plan to memory "since if the context window exceeds 200,000 tokens it will be
truncated"; each subagent brief needs "an objective, an output format, guidance on the tools and
sources to use, and clear task boundaries", and vague briefs produced duplicated work; agents
"summarize completed work phases and store essential information in external memory" before
proceeding, and "spawn fresh subagents with clean contexts while maintaining continuity through
careful handoffs"; subagents write outputs to the filesystem and pass "lightweight references" to
avoid the "game of telephone"; and the system resumes from checkpoints on error rather than
restarting. The measured claim is that the multi-agent system outperformed a single Opus 4 agent
by 90.2% on an internal evaluation, with token usage explaining 80% of variance on BrowseComp
([Anthropic 2025b](https://www.anthropic.com/engineering/multi-agent-research-system),
published 13 June 2025, full text, vendor measurement on an internal benchmark).

### OpenAI Agents SDK handoffs and Codex

The OpenAI Agents SDK names the transfer between agents a handoff and implements it as a tool
(`transfer_to_<agent>`). Its default is total: "When a handoff occurs, it's as though the new
agent takes over the conversation, and gets to see the entire previous conversation history." An
`input_filter` receives a `HandoffInputData` (input history, pre-handoff items, new items, run
context) and can drop parts — `handoff_filters.remove_all_tools` strips tool calls — and an
opt-in beta `nest_handoff_history` replaces the raw history with summary segments. A handoff may
carry small model-generated metadata (`input_type`: a reason, a priority, a summary), a
`RECOMMENDED_PROMPT_PREFIX` explains the mechanism to the model, handoffs stay within a single
run, and `Agent.as_tool` calls a specialist without transferring the conversation ([OpenAI Agents
SDK, Handoffs](https://openai.github.io/openai-agents-python/handoffs/), full text, vendor
documentation). The SDK's default is therefore the opposite of Claude Code's subagent default:
everything transferred unless filtered, versus a summary transferred unless forked.

Codex's command reference documents `/compact` as "Summarize the visible chat to free tokens …
Codex replaces earlier turns with a concise summary, freeing context while keeping critical
details", `/delete` as "Permanently delete the current session … Remove the transcript and
descendant sessions", and `codex resume`, `codex fork` and `codex archive` as the between-session
operations, with `/init` generating an AGENTS.md scaffold ([Codex, Commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
full page text). The Codex pages on memories and AGENTS.md could not be located by URL (see
[Dead ends](#dead-ends)). The positioning of Codex projects, chats and worktrees is already
recorded in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#openaicodex-specific-signs-of-the-same-fault-line).

### Practitioner protocols: Beads, Agent Handoff, HumanLayer, Manus

Beads describes itself as "persistent, structured memory for coding agents" that "replaces messy
markdown plans with a dependency-aware graph", stored in Dolt with hash-based issue IDs. Its
session-boundary operations are `bd prime`, which prints workflow context and persistent
memories at the start of an Agent Session, `bd remember "<insight>"`, which stores a memory, and
`bd ready`, `bd show`, `bd update --claim`, `bd close` for the work graph; its "Compaction:
Semantic 'memory decay' summarizes old closed tasks to save context window". Its recommended
AGENTS.md snippet tells the agent not to create MEMORY.md files or markdown TODO lists ([Beads
README](https://github.com/steveyegge/beads/blob/main/README.md), full text, practitioner
documentation). What it transfers at the boundary is the graph and the memories; what it drops is
the transcript, by design, and Yegge's essay on why is already summarised in
[chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#a-transcript-is-local-interaction-state-not-durable-team-state).

Agent Handoff is the most explicit handoff form in the agent-era material. Its standard (v1.5.1)
locates truth in three places — GitHub for work, Git for code, a repository-local `ai/` directory
for compact memory — and treats `ai/handoffs/` as "short snapshots of agent runs". A new run
starts by reading the standard, the protocol, the related Issue and Pull Request, the branch, the
recent commits, and the relevant handoffs, and claims the work before touching code. A handoff is
written "only at a legitimate outcome boundary, blocker, interruption, or transfer", and staging
one is appropriate only when the primary outcome advanced, an acceptance proof completed, a
verified out-of-envelope blocker appeared, or the run was genuinely interrupted or transferred;
two consecutive supporting-only updates are flagged as progress stalled. The snapshot schema
carries frontmatter (run, agent, agent id, branch, issue, PR, base and implementation commits,
status, relevance, supersedes) and the sections Primary outcome, Smallest acceptance proof,
Reason for the change, What changed, Validation, Scope preserved, Risks, Next direct outcome
step, and Links; an INDEX table lists eight snapshots between 2026-06-29 and 2026-07-27 with
Date, Updated, Run, Issue, PR, Branch, Status, Relevance, Summary, File and Supersedes columns.
The protocol's stated rationale for its review contract is that "a bare defect statement could
require another agent to reconstruct reproduction, contract, invariants, scope, and proof from
chat history" ([Agent Handoff standard](https://github.com/artyomboyko/Agent_Handoff/blob/main/AGENT_HANDOFF_STANDARD.md);
[Agent Handoff protocol](https://github.com/artyomboyko/Agent_Handoff/blob/main/ai/HANDOFF_PROTOCOL.md);
[handoffs INDEX](https://github.com/artyomboyko/Agent_Handoff/blob/main/ai/handoffs/INDEX.md),
full text, a single project's practice, no measurement). Set against the shift-handover form, the
snapshot carries state, next step and a proof of progress; it does not carry the outgoing agent's
stance toward contingencies, and the receiver's cross-check is the acceptance proof rather than a
question.

HumanLayer's "Advanced Context Engineering for Coding Agents" names the practice "intentional
compaction": as context fills, "pause your work and start over with a fresh context window" after
a prompt such as "Write everything we did so far to progress.md, ensure to note the end goal, the
approach we're taking, the steps we've done so far, and the current failure we're working on";
commit messages can serve the same purpose. Its ordering of harms is "Incorrect Information,
Missing Information, Too much Noise", its workflow keeps context utilisation "in the 40%-60%
range" through research, plan and implement phases whose outputs are files reviewed by a person,
and its stated reason for reviewing those files is leverage ("a bad line of research … could land
you with thousands of bad lines of code"). The evidence offered is testimonial: a two-person,
seven-hour session that shipped 35k lines, and a failed attempt whose research "didn't go deep
enough through the dependency tree" ([Horthy 2025](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md),
full text, practitioner testimonial). Manus's account of its own agent describes a `todo.md`
rewritten step by step as "a deliberate mechanism to manipulate attention", "reciting its
objectives into the end of the context" to counter "lost-in-the-middle" drift over tasks of
around 50 tool calls, argues that "any irreversible compression carries risk" because "you can't
reliably predict which observation might become critical ten steps later", and so keeps
compression "restorable" and treats the file system as "the ultimate context" ([Ji
2025](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus),
published 18 July 2025, full text, vendor argument). Chroma's "Context Rot" report, which the
Anthropic post's vocabulary draws on, evaluates 18 models and finds performance "grows
increasingly unreliable as input length grows", with consistent degradation when irrelevant
context is added to inputs the models handle correctly when focused ([Hong, Troynikov and Huber
2025](https://research.trychroma.com/context-rot), 14 July 2025, full text, measured on
synthetic tasks).

### Studies of what compaction loses

Read level: arXiv abstracts, plus the HTML full text of TRACE. Evidence type: measured on
agent benchmarks; none involves a human receiver.

ACON (Agent Context Optimization) learns compression guidelines from failure analysis of cases
where the agent succeeds with full context and fails with compressed context; it reports peak
token use reduced 26–54% with task performance largely preserved and up to a 46% improvement for
small models distilled from it ([Kang et al. 2025, arXiv:2510.00615](https://arxiv.org/abs/2510.00615),
accepted at ICML 2026). Slipstream states the problem of the summariser's ignorance directly: "the
compactor … is fundamentally unaware of precisely what information the agent will need later",
and compaction errors "silently propagate through coherent but incorrect behavior"; it validates
an asynchronous compaction against the agent's continued reasoning and reports accuracy gains of
up to 8.8 percentage points on SWE-bench Verified and BrowseComp with 39.7% lower latency
([arXiv:2605.08580](https://arxiv.org/abs/2605.08580)). Parallel Context Compaction states that
"summarization is inherently lossy", that "prompt instructions are largely ignored" by the
summariser, and that retained information "fluctuate[s] substantially from run to run", across
8B–120B backbones on HotpotQA and LoCoMo ([arXiv:2605.23296](https://arxiv.org/abs/2605.23296)).
ARC replaces summarisation with an append-only, ID-addressable log in which citations stand in
for observations, and reports needle-in-a-haystack retrieval of 99.40% against 88.12% for a
summarising baseline ([arXiv:2607.25066](https://arxiv.org/abs/2607.25066)). CompactionRL trains
the agent to compact its own context and reports SWE-bench Verified 66.8% (+7.0 points) and
Terminal-Bench 2.0 24.5% (+3.1) for GLM-4.5-Air ([arXiv:2607.05378](https://arxiv.org/abs/2607.05378)).
TRACE's preliminary empirical study, on AppWorld where previously observed information "remains
recoverable after compaction", finds that "compression can weaken the influence of recent
interactions, increasing blocked actions, repeated exploration, and instability across runs";
that mean pass rate declines as the context budget shrinks; that the advantage of summarisation
over first-in-first-out truncation "appears only under severe compression"; and that both remain
below full-context performance ([Min et al. 2026, arXiv:2608.06503](https://arxiv.org/abs/2608.06503),
HTML full text). The common finding is that the loss is real, that it is not the loss of facts
(which the agent can re-fetch) but of the actionability of recent state, and that its size
varies from run to run — the machine analogue of Lardner's "over-confidence in having been
understood".

## The two literatures side by side

This section places the documented items next to each other; it draws no conclusion about any
tool.

| Handover element | Human handover source | Agent-era counterpart |
| --- | --- | --- |
| State summary prepared by the outgoing holder before the exchange | One-paragraph log summary written before the update ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)); structured log book designed from the incoming post's information needs ([Lardner 1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf)) | Compaction summary ("requests and intent … pending tasks, and current work") ([Claude Code, Context window](https://code.claude.com/docs/en/context-window)); `progress.md` ([Horthy 2025](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md)); handoff snapshot ([Agent Handoff standard](https://github.com/artyomboyko/Agent_Handoff/blob/main/AGENT_HANDOFF_STANDARD.md)) |
| Stance toward contingencies | Given in every observed mission-control handoff ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)); "Situation awareness and contingency planning" in I-PASS ([Starmer et al. 2012](https://doi.org/10.1542/peds.2011-2966)) | Not a named field in any documented schema; "Risks" and "Next direct outcome step" in Agent Handoff are the nearest ([Agent Handoff standard](https://github.com/artyomboyko/Agent_Handoff/blob/main/AGENT_HANDOFF_STANDARD.md)) |
| Receiver's cross-check | Incoming "walks the board", reads logs, asks error-detecting questions ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)); "Synthesis by receiver" ([Starmer et al. 2012](https://doi.org/10.1542/peds.2011-2966)); repair by the "victim" ([Lardner 1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf)) | Re-reading five recently modified files ([Claude Code, Context window](https://code.claude.com/docs/en/context-window)); `bd prime` ([Beads README](https://github.com/steveyegge/beads/blob/main/README.md)); reading Issue, PR, branch, commits, handoffs at run start ([Agent Handoff protocol](https://github.com/artyomboyko/Agent_Handoff/blob/main/ai/HANDOFF_PROTOCOL.md)) |
| Redundant channels | Verbal and written together, never written alone ([Lardner 1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf)) | Summary plus re-injected CLAUDE.md, memory, plan, files ([Claude Code, Context window](https://code.claude.com/docs/en/context-window)); summary plus filesystem ([Anthropic 2025b](https://www.anthropic.com/engineering/multi-agent-research-system); [Ji 2025](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)) |
| What the record was not trusted to carry | Handwritten annotations "not considered critical enough … for the 'official record'" ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)) | "Detailed instructions from early in the conversation may be lost"; "intermediate reasoning are gone" ([Claude Code, How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works); [Context window](https://code.claude.com/docs/en/context-window)) |
| Measured loss | 2.5% retained after five verbal cycles ([Bhabra et al. 2007](https://doi.org/10.1308/003588407X168352)); most important item lost 60% ([Chang et al. 2010](https://doi.org/10.1542/peds.2009-0351)); −23% errors with I-PASS ([Starmer et al. 2014](https://doi.org/10.1056/NEJMsa1405556)) | Run-to-run fluctuation in retained information ([arXiv:2605.23296](https://arxiv.org/abs/2605.23296)); blocked actions and repeated exploration after compression ([arXiv:2608.06503](https://arxiv.org/abs/2608.06503)); no human-receiver measurement found |
| Timing of the boundary | Delayed during critical activity ([Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026)); an eight-second warning improves resumption ([Trafton et al. 2003](https://doi.org/10.1016/S1071-5819(03)00023-5)) | `/compact` before a long new task, `/autocompact` threshold, fresh session once the spec is complete ([Claude Code, Context window](https://code.claude.com/docs/en/context-window); [Best practices](https://code.claude.com/docs/en/best-practices)); handoff "only at a legitimate outcome boundary" ([Agent Handoff protocol](https://github.com/artyomboyko/Agent_Handoff/blob/main/ai/HANDOFF_PROTOCOL.md)) |

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where the existing notes touch it |
| --- | --- | --- | --- |
| The update conveys a state model and a stance; every observed high-consequence handoff was interactive and verbal, and the incoming holder's questions detect errors | [Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026) | Measured observation, 422 h | No counterpart |
| Missing updates cost the receiver's model in seven ways, from an incomplete state model to an unwarranted shift in goals | [Patterson and Woods 2001](https://doi.org/10.1023/A:1012705926828) | Qualitative, 16 shift changes | No counterpart |
| In four of five investigated incidents at changeover, written-only communication failed; all six taped misunderstandings were repaired by the incoming person's questions | [Lardner 1996](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf) | Incident analysis; observation | No counterpart |
| Verbal-only relay retains 2.5% after five cycles; a printed sheet 99% | [Bhabra et al. 2007](https://doi.org/10.1308/003588407X168352) | Measured, simulated | No counterpart |
| The sender's most important item fails to arrive 60% of the time while the sender believes it did | [Chang et al. 2010](https://doi.org/10.1542/peds.2009-0351) | Measured, 52 pairs | No counterpart |
| A structured bundle cut medical errors 23% and preventable adverse events 30% without lengthening the oral handoff | [Starmer et al. 2014](https://doi.org/10.1056/NEJMsa1405556) | Measured, 10,740 admissions | No counterpart |
| Standardisation is under-specified and its outcome evidence thin; a handoff is co-constructed, not transmitted | [Cohen and Hilligoss 2010](https://doi.org/10.1136/qshc.2009.033480); [Cohen et al. 2012](https://doi.org/10.1186/cc10536) | Review; argument | No counterpart |
| Programmers resume by restoring position, goal, plan and context from cues; edit lag under a minute in 10% of sessions | [Parnin and Rugaber 2011](https://doi.org/10.1007/s11219-010-9104-9) | Measured, 10,000 sessions | [track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking) cites the two percentages |
| Notes are the most prevalent suspension practice; environment cues doubled resumption success over notes alone in a small lab study | [Parnin and DeLine 2010](https://doi.org/10.1145/1753326.1753342) | Survey n=371; lab n=14 | No counterpart |
| 27% of interruptions diverted workers for more than two hours; resumption phase about 16 minutes | [Iqbal and Horvitz 2007](https://doi.org/10.1145/1240624.1240730) | Measured, 27 users | No counterpart |
| 57% of working spheres interrupted; resumption after 25 minutes on average | [Mark et al. 2005](https://doi.org/10.1145/1054972.1055017) | Measured, 24 workers | [track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking) cites Mark 2008, not 2005 |
| A suspended goal needs strengthening before, and a cue at, resumption | [Altmann and Trafton 2002](https://doi.org/10.1207/s15516709cog2601_2) | Model; lab | No counterpart |
| Common-ground breakdown is inevitable and documentation cannot prevent it; automation cannot fully enter the Basic Compact | [Klein et al. 2005](https://ihmc.us/users/jbradshaw/publications/Common_Ground_Single.pdf) | Argument | [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research) on shared models; [adjacent-literatures.md](adjacent-literatures.md#bainbridges-ironies) on takeover |
| Compaction keeps intent, concepts, files, errors, pending tasks; drops tool outputs, reasoning, early instructions; re-reads five files | [Claude Code, Context window](https://code.claude.com/docs/en/context-window) | Vendor documentation | [track-rationale-as-artifact.md](track-rationale-as-artifact.md#solveits-curated-dialog-versus-the-append-only-trace) mentions `/rewind` summarise; [track-in-loop-friction.md](track-in-loop-friction.md#claude-code) on modes |
| A fresh session with a written spec, and a reviewer subagent that sees only the diff, are recommended losses | [Claude Code, Best practices](https://code.claude.com/docs/en/best-practices) | Vendor guidance | No counterpart |
| Compaction can lose "subtle but critical context whose importance only becomes apparent later"; note-taking and sub-agent summaries are the alternatives | [Anthropic 2025a](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Vendor argument | No counterpart |
| A subagent brief needs objective, output format, tool guidance and boundaries; outputs go to the filesystem to avoid the "game of telephone" | [Anthropic 2025b](https://www.anthropic.com/engineering/multi-agent-research-system) | Vendor measurement, internal | No counterpart |
| The SDK handoff transfers the entire history by default; filters remove parts | [OpenAI Agents SDK, Handoffs](https://openai.github.io/openai-agents-python/handoffs/) | Vendor documentation | No counterpart |
| Codex `/compact` replaces earlier turns with a summary; `/delete` removes transcript and descendants | [Codex, Commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli) | Vendor documentation | [track-rationale-as-artifact.md](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance) on `codex resume` |
| Beads transfers a graph and memories, compacts closed tasks, and drops the transcript | [Beads README](https://github.com/steveyegge/beads/blob/main/README.md) | Practitioner documentation | [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#a-transcript-is-local-interaction-state-not-durable-team-state) |
| Agent Handoff's snapshot carries outcome, proof, envelope and next step, written only at an outcome boundary | [Agent Handoff standard](https://github.com/artyomboyko/Agent_Handoff/blob/main/AGENT_HANDOFF_STANDARD.md) | Practitioner documentation | [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#a-transcript-is-local-interaction-state-not-durable-team-state) at positioning level |
| "Intentional compaction" writes goal, approach, steps and current failure to a file before a fresh context | [Horthy 2025](https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md) | Practitioner testimonial | No counterpart |
| Irreversible compression is risky because the critical observation cannot be predicted; recitation of the plan counters drift | [Ji 2025](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | Vendor argument | No counterpart |
| The summariser cannot know what will be needed; retained content varies run to run; compression weakens recent state | [arXiv:2605.08580](https://arxiv.org/abs/2605.08580); [arXiv:2605.23296](https://arxiv.org/abs/2605.23296); [arXiv:2608.06503](https://arxiv.org/abs/2608.06503) | Measured, benchmarks | No counterpart |
| Model performance degrades non-uniformly as input length grows | [Hong et al. 2025](https://research.trychroma.com/context-rot) | Measured, 18 models | No counterpart |
| Transcripts are retained 30 days and deleted; provenance is what the commit carries | [Claude Code, Subagents](https://code.claude.com/docs/en/sub-agents) | Vendor documentation | [track-rationale-as-artifact.md](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance) |
| Reading-workflow hand-off notes appended per chapter as a session-continuity artifact | [solve-it-sweep.md](solve-it-sweep.md#the-method) | Secondary (existing note) | [solve-it-sweep.md](solve-it-sweep.md#the-method) |

"No counterpart" means no note in this directory addresses the point; it is a statement about
the notes, not about the wider literature.

## Dead ends

- [Patterson and Woods 2001](https://doi.org/10.1023/A:1012705926828) full text: the Springer DOI
  resolved to an HTML landing page and the PDF returned 403; ResearchGate was not tried. Read as
  abstract via PubMed and as reported in the 2004 paper.
- [Patterson et al. 2004](https://doi.org/10.1093/intqhc/mzh026) at the publisher: 403; the
  author-archive PDF at interruptions.net was used instead.
- [Cohen and Hilligoss 2010](https://doi.org/10.1136/qshc.2009.033480) full text: BMJ returned
  403; abstract reconstructed from OpenAlex.
- [Leonard, Graham and Bonacum 2004](https://doi.org/10.1136/qshc.2004.010033): the PMC article
  page shows only the abstract, the PMC PDF URL returned HTML, and the Europe PMC full-text XML
  for PMC1765783 was empty. The SBAR origin story and the sentinel-event percentage remain
  unverified.
- [HSE OTO 96 003](https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf):
  the live hse.gov.uk URL returns 404 and the National Archives mirror 405; a 2015 Wayback
  capture was a truncated zero-page PDF; the 2008 capture was complete.
- The HSE "Improving communication at shift handover" audit PDF (Keil Centre, 2006) was not
  read; its figures are taken from the topic page's description.
- Semantic Scholar's API returned 429 on first use and was abandoned for OpenAlex and Crossref;
  the arXiv export API returned "Rate exceeded" and arXiv abstract pages were used instead.
- BMC's site for *Critical Care* served a JavaScript challenge; the full text of Cohen et al. 2012
  came from Europe PMC instead.
- Codex documentation pages on memories and AGENTS.md: learn.chatgpt.com is a JavaScript
  application and every guessed path returned 404; only the command reference was captured.
- HumanLayer's blog URL for "Advanced Context Engineering" returned 404 and the short link
  redirects to a YouTube recording; the essay was read from the project's GitHub repository.
- No study was found that measures what a human reader recovers from an agent's compaction
  summary, handoff snapshot or `progress.md`; the compaction studies measure agent benchmark
  accuracy only. Two WebSearch queries were used in this pass; all other lookups were fetches.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Altmann, E. M. and Trafton, J. G. (2002). Memory for goals: an activation-based model.
  *Cognitive Science* 26(1):39–83. doi:10.1207/s15516709cog2601_2.
- Anthropic (2025a). Effective context engineering for AI agents. Anthropic Engineering, 29
  September 2025. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic (2025b). How we built our multi-agent research system. Anthropic Engineering, 13
  June 2025. https://www.anthropic.com/engineering/multi-agent-research-system
- Anthropic (2026). Claude Code documentation: Context window; How Claude Code works; Best
  practices; Commands; Subagents; Checkpointing; Costs. https://code.claude.com/docs/en/context-window
  and sibling pages, read 2026-09-15.
- Arora, V., Johnson, J., Lovinger, D., Humphrey, H. J. and Meltzer, D. O. (2005). Communication
  failures in patient sign-out and suggestions for improvement: a critical incident analysis.
  *Quality and Safety in Health Care* 14(6):401–407. doi:10.1136/qshc.2005.015107.
- Bhabra, G., Mackeith, S., Monteiro, P. and Pothier, D. D. (2007). An experimental comparison of
  handover methods. *Annals of the Royal College of Surgeons of England* 89(3):298–300.
  doi:10.1308/003588407X168352.
- Boyko, A. (2026). Agent Handoff: standard v1.5.1, `ai/HANDOFF_PROTOCOL.md`, `ai/handoffs/INDEX.md`.
  https://github.com/artyomboyko/Agent_Handoff
- Chang, V. Y., Arora, V. M., Lev-Ari, S., D'Arcy, M. and Keysar, B. (2010). Interns overestimate
  the effectiveness of their hand-off communication. *Pediatrics* 125(3):491–496.
  doi:10.1542/peds.2009-0351.
- Chen, Z., Pan, R., Dai, Y. et al. (2026). Slipstream: trajectory-grounded compaction validation
  for long-horizon agents. arXiv:2605.08580. https://arxiv.org/abs/2605.08580
- Cim, M., Topcu, B., Das, C. et al. (2026). Parallel context compaction for long-horizon LLM
  agent serving. arXiv:2605.23296. https://arxiv.org/abs/2605.23296
- Cohen, M. D. and Hilligoss, P. B. (2010). The published literature on handoffs in hospitals:
  deficiencies identified in an extensive review. *Quality and Safety in Health Care*
  19(6):493–497. doi:10.1136/qshc.2009.033480.
- Cohen, M. D., Hilligoss, B. and Kajdacsy-Balla Amaral, A. C. (2012). A handoff is not a
  telegram: an understanding of the patient is co-constructed. *Critical Care* 16(1):303.
  doi:10.1186/cc10536.
- Dang, T., Ichikawa, Y., Fatima, S. et al. (2026). Addressable recall compaction for long
  context-window control in AI agents. arXiv:2607.25066. https://arxiv.org/abs/2607.25066
- Haig, K. M., Sutton, S. and Whittington, J. (2006). SBAR: a shared mental model for improving
  communication between clinicians. *Joint Commission Journal on Quality and Patient Safety*
  32(3):167–175. doi:10.1016/s1553-7250(06)32022-3.
- Health and Safety Executive (n.d.). Shift handover. Human factors topics.
  https://www.hse.gov.uk/humanfactors/topics/shift-handover.htm
- Hong, K., Troynikov, A. and Huber, J. (2025). Context rot: how increasing input tokens impacts
  LLM performance. Chroma Technical Report, 14 July 2025. https://research.trychroma.com/context-rot
- Horthy, D. (2025). Advanced context engineering for coding agents. HumanLayer, GitHub.
  https://github.com/humanlayer/advanced-context-engineering-for-coding-agents/blob/main/ace-fca.md
- Horwitz, L. I., Moin, T., Krumholz, H. M., Wang, L. and Bradley, E. H. (2008). Consequences of
  inadequate sign-out for patient care. *Archives of Internal Medicine* 168(16):1755.
  doi:10.1001/archinte.168.16.1755.
- Iqbal, S. T. and Horvitz, E. (2007). Disruption and recovery of computing tasks: field study,
  analysis, and directions. *Proceedings of CHI 2007*, 677–686. doi:10.1145/1240624.1240730.
- Ji, Y. (2025). Context engineering for AI agents: lessons from building Manus. Manus blog, 18
  July 2025. https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- Kang, M., Chen, W.-N., Han, D. et al. (2025). ACON: optimizing context compression for
  long-horizon LLM agents. arXiv:2510.00615. https://arxiv.org/abs/2510.00615
- Klein, G., Feltovich, P. J., Bradshaw, J. M. and Woods, D. D. (2005). Common ground and
  coordination in joint activity. In Rouse, W. B. and Boff, K. R. (eds), *Organizational
  Simulation*, Wiley. Preprint: https://ihmc.us/users/jbradshaw/publications/Common_Ground_Single.pdf
- Lardner, R. (1996). Effective shift handover: a literature review. HSE Offshore Technology
  Report OTO 96 003. https://web.archive.org/web/20080727070021id_/http://www.hse.gov.uk/research/otopdf/1996/oto96003.pdf
- Leonard, M., Graham, S. and Bonacum, D. (2004). The human factor: the critical importance of
  effective teamwork and communication in providing safe care. *Quality and Safety in Health
  Care* 13(suppl 1):i85–i90. doi:10.1136/qshc.2004.010033.
- Li, Y., Hou, Z., Jing, Y. et al. (2026). CompactionRL: reinforcement learning with context
  compaction for long-horizon agents. arXiv:2607.05378. https://arxiv.org/abs/2607.05378
- Mark, G., Gonzalez, V. M. and Harris, J. (2005). No task left behind? Examining the nature of
  fragmented work. *Proceedings of CHI 2005*, 321–330. doi:10.1145/1054972.1055017.
- Min, G., Wu, L., Darbari, M. et al. (2026). Toward reliable context compression for
  long-horizon agents: an empirical study of execution instability (TRACE). arXiv:2608.06503. https://arxiv.org/abs/2608.06503
- Monk, C. A., Trafton, J. G. and Boehm-Davis, D. A. (2008). The effect of interruption duration
  and demand on resuming suspended goals. *Journal of Experimental Psychology: Applied*
  14(4):299–313. doi:10.1037/a0014402.
- Müller, M., Jürgens, J., Redaèlli, M., Klingberg, K., Hautz, W. E. and Stock, S. (2018). Impact
  of the communication and patient hand-off tool SBAR on patient safety: a systematic review.
  *BMJ Open* 8(8):e022202. doi:10.1136/bmjopen-2018-022202.
- OpenAI (2026). Agents SDK: Handoffs. https://openai.github.io/openai-agents-python/handoffs/
- OpenAI (2026). Codex: Commands (CLI). https://learn.chatgpt.com/docs/developer-commands?surface=cli
- Parnin, C. and DeLine, R. (2010). Evaluating cues for resuming interrupted programming tasks.
  *Proceedings of CHI 2010*, 93–102. doi:10.1145/1753326.1753342.
- Parnin, C. and Rugaber, S. (2011). Resumption strategies for interrupted programming tasks.
  *Software Quality Journal* 19(1):5–34. doi:10.1007/s11219-010-9104-9.
- Parnin, C. and Rugaber, S. (2012). Programmer information needs after memory failure.
  *Proceedings of ICPC 2012*. https://chrisparnin.me/pdf/infoneeds.pdf
- Patterson, E. S. and Woods, D. D. (2001). Shift changes, updates, and the on-call architecture
  in space shuttle mission control. *Computer Supported Cooperative Work* 10(3–4):317–346.
  doi:10.1023/A:1012705926828.
- Patterson, E. S., Roth, E. M., Woods, D. D., Chow, R. and Gomes, J. O. (2004). Handoff
  strategies in settings with high consequences for failure: lessons for health care operations.
  *International Journal for Quality in Health Care* 16(2):125–132. doi:10.1093/intqhc/mzh026.
- Pothier, D., Monteiro, P., Mooktiar, M. and Shaw, A. (2005). Pilot study to show the loss of
  important data in nursing handover. *British Journal of Nursing* 14(20):1090–1093.
  doi:10.12968/bjon.2005.14.20.20053.
- Randell, R., Wilson, S. and Woodward, P. (2011). The importance of the verbal shift handover
  report: a multi-site case study. *International Journal of Medical Informatics*
  80(11):803–812. doi:10.1016/j.ijmedinf.2011.08.006.
- Riesenberg, L. A., Leitzsch, J., Massucci, J. L., Jaeger, J., Rosenfeld, J. C., Patow, C.,
  Padmore, J. S. and Karpovich, K. P. (2009). Residents' and attending physicians' handoffs: a
  systematic review of the literature. *Academic Medicine* 84(12):1775–1787.
  doi:10.1097/ACM.0b013e3181bf51a6.
- Starmer, A. J., Spector, N. D., Srivastava, R., Allen, A. D., Landrigan, C. P. and Sectish, T.
  C. (2012). I-PASS, a mnemonic to standardize verbal handoffs. *Pediatrics* 129(2):201–204.
  doi:10.1542/peds.2011-2966.
- Starmer, A. J. et al. (2013). Rates of medical errors and preventable adverse events among
  hospitalized children following implementation of a resident handoff bundle. *JAMA*
  310(21):2262–2270. doi:10.1001/jama.2013.281961.
- Starmer, A. J. et al. (2014). Changes in medical errors after implementation of a handoff
  program. *New England Journal of Medicine* 371(19):1803–1812. doi:10.1056/NEJMsa1405556.
- Trafton, J. G., Altmann, E. M., Brock, D. P. and Mintz, F. E. (2003). Preparing to resume an
  interrupted task: effects of prospective goal encoding and retrospective rehearsal.
  *International Journal of Human-Computer Studies* 58(5):583–603.
  doi:10.1016/S1071-5819(03)00023-5.
- Yegge, S. (2026). Beads README. https://github.com/steveyegge/beads/blob/main/README.md
