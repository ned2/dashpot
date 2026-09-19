---
status: research
date: 2026-09-13
---

# Adjacent literatures: supervising automation, cognitive offloading, and motivation

Research date: 2026-09-13

The sibling notes lean on three literatures they never cite: human-factors research on
what happens to people who supervise automation, cognitive-psychology research on
offloading thinking to external tools, and the motivational account that Answer.AI attaches
to its "human is the agent" stance. This note documents each from primary sources — the
claim, the evidence and its setting, the stated limits — and then maps each claim to the
place in [evidence-and-mechanisms.md](evidence-and-mechanisms.md),
[answer-ai-sweep.md](answer-ai-sweep.md),
[track-in-loop-friction.md](track-in-loop-friction.md), and
[understanding-bottleneck-talk.md](understanding-bottleneck-talk.md) where the same claim
appears, or records that it has no counterpart. It is documentary: it does not evaluate fit
for Dashpot or any tool. Verification level is stated per source ("full text", "abstract",
"metadata"); numbers are quoted only where the text carrying them was read. Effect sizes
are reported as the sources state them, nulls included.

## Finding

The AI-coding discourse has independently rediscovered most of Bainbridge's 1983 ironies
without citing them: that the supervisor is left with the tasks the designer could not
automate, that monitoring reliable automation is a task humans do badly after about half an
hour, that skills and retrievable knowledge decay without use, and that the remedy is
regular manual practice. Human-factors research since then has measured the pieces —
complacency appears after roughly 20 minutes of constant-reliability automation under
multitask load (Parasuraman, Molloy and Singh 1993), automation bias produced 59% versus
97% event detection and a 35% accuracy rate on false prompts in a flight simulation
(Skitka, Mosier and Burdick 1999), a meta-analysis of 18 experiments found higher degrees
of automation improve routine performance while degrading failure performance and
situation awareness (Onnasch et al. 2014), a 10-minute return to manual control restored
failure detection (Parasuraman, Mouloua and Molloy 1996), and 126 airline pilots' fine-motor
tracking depended on recent practice more than on total experience (Haslbeck and Hoermann
2016, ηp² = .45) while 16 pilots' motor skills were intact and their cognitive
flight-management skills were not (Casner et al. 2014). Regulators drew the same
conclusions from AF447 and Asiana 214. The one measurement of AI-specific deskilling in a
profession is Budzyń et al. (2025): adenoma detection in non-AI colonoscopy fell from 28.4%
to 22.4% after three months of AI exposure (n = 1,443, observational) — the source behind
Kosmyna's "deskilling in 3 months" that the evidence note left unfollowed. The offloading
literature is narrower than its reputation: Sparrow et al.'s Google effect is a memory
result whose only replicated experiment failed to replicate (r = 0.05 pooled versus 0.37),
the GPS and calculator work measures skill and cognitive-map formation with small samples or
mixed direction, and the 2024–2026 AI studies that measure understanding rather than recall
(Bastani, Stadler, Fan) find task performance up and unassisted skill flat or down — the
pattern the evidence note already records for code; Gerlich (2025), the usual citation, is
a self-report correlation with no published critique found. The metacognitive strand
(Fisher, Goddu and Keil; Ward) is the strongest: search inflates self-assessed explanatory
knowledge (d = 0.43–0.63) without changing actual unaided performance. On motivation,
Ryan and Deci (2000) do state that controlling contexts make people "learn less effectively,
especially when learning requires conceptual, creative processing", which supports the
mechanism Howard invokes; but the "junk flow" term comes from a 2014 blog interview, not
from Csikszentmihalyi's published work, "dark flow" is Dixon et al.'s gambling construct
(correlational, r ≈ .5 with problem gambling and depression), and the analogy from
losses-disguised-as-wins to vibe coding is Rachel Thomas's own inference. Developer studies
applying these frameworks to AI tools are qualitative and small (Feng et al. 2026; Alami
et al. 2026, n = 21, the only one citing Braverman); nothing found measures motivation or
ownership under agentic delegation at scale.

## Supervising automation

### Bainbridge's ironies

Bainbridge, "Ironies of automation", *Automatica* 19(6):775–779 (1983),
[doi:10.1016/0005-1098(83)90046-8](https://doi.org/10.1016/0005-1098(83)90046-8);
full text read from an
[author-page scan](https://ckrybus.com/static/papers/Bainbridge_1983_Automatica.pdf).
A five-page essay on process control with flight-deck examples; it cites secondary studies
(Edwards and Lees 1974; Mackworth 1950; Duncan and Shepherd 1975; Ephrath and Young 1981)
and no original data. Its claims, in the paper's order:

- *The residue.* "The designer who tries to eliminate the operator still leaves the
  operator to do the tasks which the designer cannot think how to automate … the operator
  can be left with an arbitrary collection of tasks, and little thought may have been given
  to providing support for them."
- *Manual skill decays.* "Physical skills deteriorate when they are not used, particularly
  the refinements of gain and timing. This means that a formerly experienced operator who
  has been monitoring an automated process may now be an inexperienced one." Because
  take-over happens when something is wrong, "the operator needs to be more rather than
  less skilled, and less rather than more loaded, than average."
- *Cognitive skill decays.* "Efficient retrieval of knowledge from long-term memory
  depends on frequency of use (consider any subject which you passed an examination in at
  school and have not thought about since)", and such knowledge "develops only through use
  and feedback about its effectiveness"; classroom knowledge without practice "will not be
  within a framework which makes it meaningful". Present systems are "riding on" former
  manual operators' skills "which later generations of operators cannot be expected to
  have."
- *Working storage.* The operator's model of current state "takes time to build up";
  manual operators arrive "quarter to half an hour before they are due to take over
  control", so the supervisor who must act quickly "can only do so on the basis of minimum
  information".
- *Monitoring is a poor human task.* "It is impossible for even a highly motivated human
  being to maintain effective visual attention towards a source of information on which
  very little happens, for more than about half an hour"; the operator "will not monitor
  the automatics effectively if they have been operating acceptably for a long period";
  logging does not help because "people can write down numbers without noticing what they
  are." And: "the automatic control system has been put in because it can do the job better
  than the operator, but yet the operator is being asked to monitor that it is working
  effectively" — where the computer decides faster than a human can check, the human can
  only judge at a meta-level whether decisions are "acceptable", and "the human monitor has
  been given an impossible task."
- *Deskilling and attitude.* A job "reduced to monitoring" is "very boring but very
  responsible, yet there is no opportunity to acquire or maintain the qualities required to
  handle the responsibility"; "if the job is 'deskilled' by being reduced to monitoring,
  this is difficult for the individuals involved to come to terms with." Cited support:
  Ekkers et al. (1979) correlations of process controllability and a "rich pattern of
  activities" with feeling of achievement.
- *The paradox and the remedy.* "By automating the process the human operator is given a
  task which is only possible for someone who is in on-line control." Solutions: "allow
  the operator to use hands-on control for a short period in each shift. If this suggestion
  is laughable then simulator practice must be provided"; "accurate fast reactions can only
  be learned on a high fidelity simulator"; training must cover "general strategies rather
  than specific responses" because unknown faults cannot be simulated. Following computer
  advice leaves the operator "getting no practice in being 'intelligent'", and "by taking
  away the easy parts of his task, automation can make the difficult parts of the human
  operator's task more difficult." Final irony: "it is the most successful automated
  systems, with rare need for manual intervention, which may need the greatest investment
  in human operator training."

Limits: none stated; the paper is argument, and Bainbridge notes that error data are
"difficult to interpret" and unpublished. Two retrospectives confirm the argument's
standing without adding measurement: Baxter, Rooksby, Wang and Khajeh-Hosseini, "The
ironies of automation: still going strong at 30?", *ECCE 2012*, 65–71,
[doi:10.1145/2448136.2448149](https://doi.org/10.1145/2448136.2448149) (full text, author
copy), which extends the ironies to cloud computing — customers who lost data in the 2011
EC2 outage "had either lost, or never had expertise in system administration" — and states
the limit that "the work relies on published or reported cases"; and Strauch, "Ironies of
automation: still unresolved after all these years", *IEEE THMS* 48(5):419–433 (2018),
[doi:10.1109/THMS.2017.2732506](https://doi.org/10.1109/THMS.2017.2732506) (abstract
only).

### Use, misuse, disuse, abuse: complacency and automation bias

- Parasuraman and Riley, "Humans and automation: use, misuse, disuse, abuse", *Human
  Factors* 39(2):230–253 (1997),
  [doi:10.1518/001872097778543886](https://doi.org/10.1518/001872097778543886); abstract
  only. Claim: "Misuse refers to over reliance on automation, which can result in failures
  of monitoring or decision biases. Factors affecting the monitoring of automation include
  workload, automation reliability and consistency, and the saliency of automation state
  indicators." Disuse is neglect "commonly caused by alarms that activate falsely"; abuse
  is "the automation of functions by designers and implementation by managers without due
  regard for the consequences for human performance", which "tends to define the
  operator's roles as by-products of the automation." Review; no numbers in the abstract.
- Parasuraman, Molloy and Singh, "Performance consequences of automation-induced
  'complacency'", *International Journal of Aviation Psychology* 3(1):1–23 (1993),
  [doi:10.1207/s15327108ijap0301_1](https://doi.org/10.1207/s15327108ijap0301_1); abstract
  only. Forty subjects, four 30-minute sessions of a PC flight simulation with manual
  tracking and fuel management plus an automated system-monitoring task. "Operator detection
  of automation failures was substantially worse for constant-reliability than for
  variable-reliability automation after about 20 min under automation control"; "when
  system monitoring was the only task, detection was very efficient and was unaffected by
  variations in automation reliability." Detection percentages not verified.
- Skitka, Mosier and Burdick, "Does automation bias decision-making?", *IJHCS*
  51(5):991–1006 (1999),
  [doi:10.1006/ijhc.1999.0252](https://doi.org/10.1006/ijhc.1999.0252); full text (author
  copy). Eighty undergraduates, eight simulated flights, an automated monitoring aid that
  was "94% reliable". Omission errors: automated condition "missed more of these events
  (M = 2.44 or a 59% accuracy rate) than those in the non-automated condition (M = 0.18 or
  a 97% accuracy rate), F(1,62) = 44.32, p < 0.05". Commission errors: "an average
  accuracy rate of 35%. Only one participant made no commission errors; 23.1% of the
  participants made commission errors on all six events." Stated limits: generalisation
  "to aviation or other complex real-life decision-making settings remains an open
  question"; the task "cannot capture … the psychological mindset of experienced pilots".
- Parasuraman and Manzey, "Complacency and bias in human use of automation: an
  attentional integration", *Human Factors* 52(3):381–410 (2010),
  [doi:10.1177/0018720810376055](https://doi.org/10.1177/0018720810376055); abstract only.
  Review conclusions: complacency "occurs under conditions of multiple-task load", "is
  found in both naive and expert participants and cannot be overcome with simple
  practice"; automation bias "results in making both omission and commission errors when
  decision aids are imperfect", "cannot be prevented by training or instructions, and can
  affect decision making in individuals as well as in teams."
- Wickens, Clegg, Vieane and Sebok, "Complacency and automation bias in the use of
  imperfect automation", *Human Factors* 57(5):728–739 (2015),
  [doi:10.1177/0018720815581940](https://doi.org/10.1177/0018720815581940); abstract only.
  An experiment, not a meta-analysis: process-control simulation with a decision aid made
  dependable over several trials, then an unexpected error in which the aid was either
  "gone" or "wrong". "The aid failure degraded all three variables, but 'automation wrong'
  had a much greater effect on accuracy, reflecting the automation bias, than did
  'automation gone,' reflecting the impact of complacency." n not verified.
- Lee and See, "Trust in automation: designing for appropriate reliance", *Human Factors*
  46(1):50–80 (2004),
  [doi:10.1518/hfes.46.1.50_30392](https://doi.org/10.1518/hfes.46.1.50_30392); full text
  (author preprint). Conceptual: "Calibration refers to the correspondence between a
  person's trust in the automation and the automation's capabilities … Overtrust is poor
  calibration in which trust exceeds system capabilities"; "trust guides reliance when
  complexity and unanticipated situations make a complete understanding of the automation
  impractical." No data.

### Levels of automation and supervisory control

- Sheridan and Verplank, *Human and Computer Control of Undersea Teleoperators*, MIT
  Man-Machine Systems Laboratory technical report (1978), DTIC ADA057655; full text from an
  [archive.org mirror](https://archive.org/download/DTIC_ADA057655/DTIC_ADA057655.pdf).
  Defines supervisory control as "a hierarchical control scheme whereby a … device having
  sensors, actuators and a computer, and capable of autonomous decision making and control
  over short periods and restricted conditions, is remotely monitored and intermittently
  operated directly or reprogrammed by a person." Table 8.2 gives the ten-level scale for
  "a single elemental decisive step": 1 human does the whole job up to implementation;
  2 computer determines options; 3 suggests one; 4 "computer selects action and human may
  or may not do it"; 5 "computer selects action and implements it if human approves";
  6 "computer selects action, informs human in plenty of time to stop it"; 7 "does whole
  job and necessarily tells human what it did"; 8 tells only if asked; 9 tells if it
  decides to; 10 "does whole job if it decides it should be done, and if so tells human,
  if it decides he should be told." Sheridan, *Telerobotics, Automation, and Human
  Supervisory Control* (MIT Press, 1992), metadata only.
- Parasuraman, Sheridan and Wickens, "A model for types and levels of human interaction
  with automation", *IEEE Trans. SMC–A* 30(3):286–297 (2000),
  [doi:10.1109/3468.844354](https://doi.org/10.1109/3468.844354); full text (archived
  course copy). Four function classes — "information acquisition; information analysis;
  decision and action selection; action implementation" — each automatable at a level from
  1 to 10. The *primary* evaluative criteria are "mental workload, situation awareness,
  complacency, and skill degradation"; the secondary criteria are automation reliability
  and the costs of decision consequences. On skill: "if the decision-making function is
  consistently performed by automation, there will come a time when the human operator
  will not be as skilled in performing that function … forgetting and skill decay occur
  with disuse." Complacency is "greatest when the operator is engaged in multiple tasks
  and less apparent when monitoring the automated system is the only task". Stated
  limits: the model "is almost certainly a gross simplification"; whether unreliability
  effects apply equally to all stages "needs further examination".
- Onnasch, Wickens, Li and Manzey, "Human performance consequences of stages and levels
  of automation: an integrated meta-analysis", *Human Factors* 56(3):476–488 (2014),
  [doi:10.1177/0018720813501549](https://doi.org/10.1177/0018720813501549); abstract only.
  Eighteen experiments; effects "summarized by level of statistical significance", not
  pooled. "(a) a clear automation benefit for routine system performance with increasing
  DOA, (b) a similar but weaker pattern for workload when automation functioned properly,
  and (c) a negative impact of higher DOA on failure system performance and SA"; negative
  consequences "seem to be most likely when DOA moved across a critical boundary, which was
  identified between automation supporting information analysis and automation supporting
  action selection."
- Norman, "The 'problem' with automation: inappropriate feedback and interaction, not
  'over-automation'", *Phil. Trans. R. Soc. B* 327(1241):585–593 (1990),
  [doi:10.1098/rstb.1990.0101](https://doi.org/10.1098/rstb.1990.0101); full text (NASA
  NTRS preprint). Counter-position by case analysis: "the problem is not the presence of
  automation, but rather its inappropriate design … there is inadequate feedback and
  interaction with the humans who must control the overall conduct of the task"; current
  automation "is at an intermediate level of intelligence, powerful enough to take over
  control … but not powerful enough to handle all abnormalities", so it "should either be
  made less intelligent or more so". No data.

### Situation awareness and the out-of-the-loop problem

- Endsley, "Toward a theory of situation awareness in dynamic systems", *Human Factors*
  37(1):32–64 (1995),
  [doi:10.1518/001872095779049543](https://doi.org/10.1518/001872095779049543); definition
  read from a scanned copy. "Situation awareness is the perception of the elements in the
  environment within a volume of time and space, the comprehension of their meaning, and
  the projection of their status in the near future" — Levels 1, 2 and 3. Theory paper.
- Endsley and Kiris, "The out-of-the-loop performance problem and level of control in
  automation", *Human Factors* 37(2):381–394 (1995),
  [doi:10.1518/001872095779064555](https://doi.org/10.1518/001872095779064555); abstract
  only. Navigation task with an expert system: "low SA corresponded with out-of-the-loop
  performance decrements in decision time following a failure of the expert system. Level
  of operator control in interacting with automation is a major factor in moderating this
  loss of SA … the shift from active to passive processing was most likely responsible for
  decreased SA under automated conditions." n, levels and takeover times not verified.
- Endsley, "From here to autonomy: lessons learned from human–automation research",
  *Human Factors* 59(1):5–27 (2017),
  [doi:10.1177/0018720816681350](https://doi.org/10.1177/0018720816681350); abstract only.
  "An automation conundrum exists in which as more autonomy is added to a system, and its
  reliability and robustness increase, the lower the situation awareness of human operators
  and the less likely that they will be able to take over manual control when needed." The
  lessons list was not reached.
- Kaber and Endsley, "The effects of level of automation and adaptive automation on human
  performance, situation awareness and workload in a dynamic control task", *Theoretical
  Issues in Ergonomics Science* 5(2):113–153 (2004),
  [doi:10.1080/1463922021000054335](https://doi.org/10.1080/1463922021000054335); full text
  (author preview copy). Thirty students, five levels of automation crossed with four
  adaptive-automation cycle times in a multitask simulation. LOA affected target collapses,
  F(4,25) = 31.11, p < 0.0001, and Level 2 SA, F(4,25) = 5.68, p = 0.0021, with
  comprehension highest at intermediate levels and "substantially lower SA" under batch
  processing and supervisory control; "low-level automation produced superior performance
  and intermediate LOAs facilitated higher SA, but this was not associated with improved
  performance or reduced workload." Stated limits: "not intended to generate results or
  design guidelines for a specific domain"; generalisation "to more realistic tasks" needs
  further research.

### Adaptive automation

Parasuraman, Mouloua and Molloy, "Effects of adaptive task allocation on monitoring of
automated systems", *Human Factors* 38(4):665–679 (1996),
[doi:10.1518/001872096778827279](https://doi.org/10.1518/001872096778827279); abstract
only. Three 30-minute sessions of engine-status monitoring under automation with tracking
and fuel management; in the adaptive groups the monitoring task was handed back to the
human for 10 minutes mid-session. "All groups had low probabilities of detection of
automation failures for the first 40 min spent with automation. However, following the
10-min intervening period of human control, both adaptive groups detected significantly
more automation failures during the subsequent blocks under automation control." n and
rates not verified. This is the experimental form of Bainbridge's "hands-on control for a
short period in each shift".

### Skill fade in aviation

- Casner, Geven, Recker and Schooler, "The retention of manual flying skills in the
  automated cockpit", *Human Factors* 56(8):1506–1516 (2014),
  [doi:10.1177/0018720814535628](https://doi.org/10.1177/0018720814535628); abstract only.
  Sixteen airline pilots in a 747-400 simulator across levels of automation. "We found
  pilots' instrument scanning and manual control skills to be mostly intact, even when
  pilots reported that they were infrequently practiced. However, when pilots were asked to
  manually perform the cognitive tasks needed for manual flight (e.g., tracking the
  aircraft's position without the use of a map display, deciding which navigational steps
  come next, recognizing instrument system failures), we observed more frequent and
  significant problems", and those problems "were associated with measures of how often
  pilots engaged in task-unrelated thought when cockpit automation was used." Effect sizes
  not in the abstract.
- Haslbeck and Hoermann, "Flying the needles: flight deck automation erodes fine-motor
  flying skills among airline pilots", *Human Factors* 58(4):533–545 (2016),
  [doi:10.1177/0018720816640394](https://doi.org/10.1177/0018720816640394); full text (DLR
  self-archived manuscript). 126 randomly selected pilots of one airline, long-haul versus
  short-haul fleet crossed with rank, flying a raw-data ILS approach in Level-D
  simulators. Fleet effect V = .45, F(2,121) = 48.90, p < .001, ηp² = .45; rank effect
  ηp² = .08. "Recent flight practice is a significantly stronger predictor for fine-motor
  flying performance than the time period since flight school or even the total or
  type-specific flight experience." Stated limits: one airline; one manoeuvre; aircraft
  type is a latent confound.
- FAA PARC/CAST Flight Deck Automation Working Group, *Operational Use of Flight Path
  Management Systems* (final report, 5 September 2013),
  [faa.gov PDF](https://www.faa.gov/sites/faa.gov/files/aircraft/air_cert/design_approvals/human_factors/OUFPMS_Report.pdf);
  full text. Data: 26 accidents and 20 major incidents since 1996, over 1,000 ASRS
  reports (734 coded), LOSA observations on 9,155 flights, interviews. Finding 2:
  "Vulnerabilities were identified in pilot knowledge and skills for manual flight
  operations, including … appropriate manual handling after transition from automated
  control … definition, development, and retention of such skills." Finding 4: "Pilots
  sometimes rely too much on automated systems and may be reluctant to intervene;
  Autoflight mode confusion errors continue to occur." Mode selection errors "were cited in
  27% of the accidents reviewed". The report records that operators and trainers "expressed
  uncertainty as to how these skills may decay". Recommendation 1: standards "for
  maintaining and improving knowledge and skills for manual flight operations".
  Finding 23 states the data-source limits (ASRS is self-reported; frequencies are not
  rates).
- FAA SAFO 13002, *Manual Flight Operations* (4 January 2013), and SAFO 17007, *Manual
  Flight Operations Proficiency* (4 May 2017), full text at
  [SAFO13002](https://www.faa.gov/sites/faa.gov/files/other_visit/aviation_industry/airline_operators/airline_safety/SAFO13002.pdf)
  and
  [SAFO17007](https://www.faa.gov/sites/faa.gov/files/other_visit/aviation_industry/airline_operators/airline_safety/SAFO17007.pdf).
  SAFO 13002: "A recent analysis of flight operations data … identified an increase in
  manual handling errors"; "continuous use of autoflight systems could lead to degradation
  of the pilot's ability to quickly recover the aircraft from an undesired state." SAFO
  17007: "manual flight is the foundation upon which other technical flying skills are
  built … while recognizing that manual flight operations involve more than motor skills."
- BEA, *Final Report* on AF447 (July 2012),
  [bea.aero PDF](https://bea.aero/fileadmin/documents/docspa/2009/f-cp090601.en/pdf/f-cp090601.en.pdf);
  full text, targeted reading. Findings: "The copilots had not undertaken any in-flight
  training, at high altitude, for the 'vol avec IAS douteuse' procedure or on manual
  aeroplane handling"; "in less than one minute after autopilot disconnection, the
  aeroplane exited its flight envelope following inappropriate pilot inputs." Contributing
  causes include "the absence of any training, at high altitude, in manual aeroplane
  handling" and "poor management of the startle effect"; "the crew, progressively becoming
  de-structured, likely never understood that it was faced with a 'simple' loss of three
  sources of airspeed information." Recommendation: "specific and regular exercises
  dedicated to manual aircraft handling of approach to stall and stall recovery, including
  at high altitude."
- NTSB, *Descent Below Visual Glidepath and Impact With Seawall, Asiana Airlines Flight
  214*, AAR-14/01 (2014),
  [ntsb.gov PDF](https://www.ntsb.gov/investigations/AccidentReports/Reports/AAR1401.pdf);
  full text, targeted. Probable cause names "the flight crew's inadequate monitoring of
  airspeed"; contributing factors include "the complexities of the autothrottle and
  autopilot flight director systems that were inadequately described in Boeing's
  documentation and Asiana's pilot training, which increased the likelihood of mode error".
  Finding 8: insufficient monitoring "likely resulted from expectancy, increased workload,
  fatigue, and automation reliance." Finding 10: the pilot flying "had an inaccurate
  understanding of how the autopilot flight director system and autothrottle interacted".
  The analysis cites Parasuraman and Manzey (2010) on complacency under high trust.

### Skill fade in medicine

- Beane, "Shadow learning: building robotic surgical skill when approved means fail",
  *Administrative Science Quarterly* 64(1):87–123 (2019),
  [doi:10.1177/0001839217751692](https://doi.org/10.1177/0001839217751692); abstract only.
  "A two-year, five-sited, comparative ethnographic study of learning in robotic and
  traditional surgical practice, and a blinded interview-based study of surgical learning
  practices at 13 top-tier teaching hospitals"; "the radically different practice of robotic
  surgery greatly limited trainees' role in the work, making approved methods ineffective",
  so that "only a minority of robotic surgical trainees" reached competence, via
  "premature specialization", "abstract rehearsal", and "undersupervised struggle".
  Qualitative; counts not verified.
- Budzyń et al., "Endoscopist deskilling risk after exposure to artificial intelligence in
  colonoscopy: a multicentre, observational study", *Lancet Gastroenterology & Hepatology*
  10(10):896–903 (2025),
  [doi:10.1016/S2468-1253(25)00133-5](https://doi.org/10.1016/S2468-1253(25)00133-5);
  abstract via PubMed (PMID 40816301). Retrospective before–after at four Polish centres:
  "1443 patients underwent non-AI assisted colonoscopy before (n=795) and after (n=648) the
  introduction of AI … The ADR of standard colonoscopy decreased significantly from 28·4%
  (226 of 795) before to 22·4% (145 of 648) after exposure to AI, corresponding with an
  absolute difference of -6·0% (95% CI -10·5 to -1·6; p=0·0089)"; adjusted odds ratio for
  AI exposure 0·69 (0·53–0·89). Limits section not reached; the design is observational and
  a correction (10(11):e12) exists whose content was not reached. This is reference [130] in
  Kosmyna et al., the "deskilling happening in 3 months" the evidence note lists as
  unfollowed ([dead ends](evidence-and-mechanisms.md#dead-ends-and-gaps)).
- Macnamara et al., "Does using artificial intelligence assistance accelerate skill decay
  and hinder skill development without performers' awareness?", *Cognitive Research:
  Principles and Implications* 9:46 (2024),
  [doi:10.1186/s41235-024-00572-8](https://doi.org/10.1186/s41235-024-00572-8); full text.
  A perspective, not a study: "no experiments were conducted." It predicts, from the
  aviation literature above, that "high performance is observed in the AI-assisted group,
  but the limits on learning remain hidden until AI assistance is removed", and states that
  "to our awareness, no research has been conducted on AI assistants' effects on the user's
  skill."

### What the AI-coding sources already say, and what they do not

Implicit counterparts, by claim:

- *Monitoring degrades with reliability and time* — Claude Code's own guidance that "after
  the tenth approval you're clicking through rather than reviewing" and Codex's naming of
  step-watching as a mistake
  ([in-loop friction, Arguments and evidence](track-in-loop-friction.md#arguments-and-evidence));
  Sarkar and Drosos's "material disengagement" and Kuo et al.'s 62% dismissal of mid-task
  interventions
  ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026);
  [in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)).
- *Automation bias and overtrust* — Kaufman et al.'s 49% accuracy on incorrect assertions
  with unchanged confidence, Perry et al.'s more-confident-and-less-secure participants, and
  Lee et al.'s finding that confidence in GenAI predicts less critical thinking
  ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)).
  Trust calibration in Lee and See's sense is what the DORA "verification tax" and Stack
  Overflow trust figures describe
  ([evidence, surveys](evidence-and-mechanisms.md#surveys-trust-and-verification-not-comprehension)).
- *Out-of-the-loop loss of situation awareness* — Litt's "peripheral vision" lost when the
  fix is delegated
  ([talk note, Proposal 3](understanding-bottleneck-talk.md#proposal-3-micro-worlds)), his
  framing of the debate as "taking ourselves out of the loop"
  ([talk note, Problem framing](understanding-bottleneck-talk.md#problem-framing)), Howard's
  "I wasn't really in control" after the GPT-5.3 Pro fix
  ([Answer.AI, Core claims](answer-ai-sweep.md#core-claims)), and Storey's "lost the plot"
  ([evidence, practitioner framings](evidence-and-mechanisms.md#practitioner-framings-argument-not-evidence)).
- *Skills and knowledge decay without use; practice is the remedy* — Answer.AI claims 3, 8
  and 14 and Thomas's "skills atrophy when you stop using them"
  ([Answer.AI, Core claims](answer-ai-sweep.md#core-claims);
  [Answer.AI, Team writing](answer-ai-sweep.md#team-writing-and-talks)), the latter stated
  without a source.
- *Feedback and display design rather than less automation* (Norman; Weiser's cockpit) —
  Litt's HUD essay, which argues the aviation analogy directly and cites Heer's "Agency plus
  automation" ([talk note, Related material](understanding-bottleneck-talk.md#related-material)).
- *The impossible meta-level check* — Litt's "understanding to verify" is a thumbs-up role
  that agents will take over
  ([talk note, Problem framing](understanding-bottleneck-talk.md#problem-framing)).
- *Levels of automation* — the mode tables (Always Ask, Agent Decides, Autopilot, plan
  approval) are Sheridan–Verplank levels 5–7 by another name
  ([in-loop friction, Existing modes and tools](track-in-loop-friction.md#existing-modes-and-tools)),
  though no source cites the scale.

No counterpart found: the adaptive-automation result that a short return to manual control
restores failure detection (the landscape sweep's AI-free days are the nearest artefact, with
no measurement); Onnasch et al.'s boundary between automating analysis and automating
action selection; the automation conundrum as a stated relation between reliability and
awareness; Bainbridge's "working storage" claim that a supervisor's state model takes time
to rebuild before safe takeover; her final irony that the most reliable automation needs the
most training; the dissociation between preserved motor skill and lost cognitive skill
(Casner); and the "deskilled job" attitude effect, which the notes touch only through Feng
et al.'s juniors ([in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)).

### Cowan's ironies of household technology

A third pattern beside Bainbridge's residue and Braverman's separation of conception from
execution: Ruth Schwartz Cowan, *More Work for Mother: The Ironies of Household Technology
from the Open Hearth to the Microwave* (Basic Books, 1983), argues that "labour-saving"
household technology did not reduce housework but relocated it — removing the tasks men,
children and servants had done and leaving the whole job with one unpaid person — while the
standard the work was held to rose to absorb the saving, so that the housewife of 1950
produced "singlehandedly what her counterpart of 1850 needed a staff of three or four to
produce" (p. 100). Her 1987 "consumption junction" adds that what a technology saves must be
judged from the point of view of the person doing the work. It was published the same year
as Bainbridge's essay, defines irony the same way, and neither cites the other: Bainbridge's
reference list was read and contains no Cowan, and no occurrence of "Bainbridge" surfaced in
a full-text search of Cowan's book. The time-use evidence that tests the thesis, its
disputes (Mokyr, Gershuny and Robinson, Greenwood et al., Ramey), and its mapping to the
notes' verification-time and throughput claims are in
[Cowan's ironies of household technology](cowan-more-work-for-mother.md).

## Cognitive offloading

### Memory: the Google effect and its replication

Sparrow, Liu and Wegner, "Google effects on memory: cognitive consequences of having
information at our fingertips", *Science* 333(6043):776–778 (2011),
[doi:10.1126/science.1207745](https://doi.org/10.1126/science.1207745); full text (archived
author copy). Four experiments on students. Experiment 1 (n = 69): colour-naming of
computer words was slower than general words after hard trivia questions (M = 712 versus
591 ms, t(68) = 3.26, p < .003). Experiment 2 (about 60, between subjects): recall of typed
trivia statements was lower when told they were saved (M = .22) than erased (M = .31),
omnibus F(3,56) = 2.80, p < .05; an explicit instruction to remember had no effect.
Experiment 3 (n = 28): recognition was best for erased statements (.93 versus .88 and .85,
F(1,27) = 4.01, p < .03). Experiment 4 (about 33): folder locations were recalled better
than the statements themselves (.49 versus .23, t(31) = 6.70, p < .001). Stated limits:
Experiment 4's folder recall was cued while statement recall was not, and it "could not be
counterbalanced"; the authors call it "preliminary". Measure: recall and recognition only.
Replication: Camerer et al., *Nature Human Behaviour* 2(9):637–644 (2018),
[doi:10.1038/s41562-018-0399-z](https://doi.org/10.1038/s41562-018-0399-z), full text and
supplement, attempted only Experiment 1: original r = 0.368 (n = 69, which the paper had
reported as 46); replication r = 0.110, p = 0.265 (n = 104), pooled r = 0.050, p = 0.449
(n = 234), classified as not replicating; the original authors did not respond and Wegner
had died. Experiments 2–4 were not tested.

Storm and Stone, "Saving-enhanced memory", *Psychological Science* 26(2):182–188 (2015),
[doi:10.1177/0956797614559285](https://doi.org/10.1177/0956797614559285); abstract only.
"Saving one file before studying a new file significantly improved memory for the contents
of the new file … this effect was not observed when the saving process was deemed unreliable
or when the contents of the to-be-saved file were not substantial enough to interfere."
Three experiments; n and statistics not reached. Memory only.

Grinschgl, Papenmeier and Meyerhoff, "Consequences of cognitive offloading: boosting
performance but diminishing memory", *QJEP* 74(9):1477–1496 (2021),
[doi:10.1177/17470218211008060](https://doi.org/10.1177/17470218211008060); full text
(PMC). Three preregistered experiments, N = 172 each, pattern-copy task with a model window
that can be reopened. Without a lockout, participants reopened the model more (η²p = .25),
finished faster (η²p = .06), and remembered less of what they copied (identity η²p = .04,
bindings η²p = .04); forced maximal offloading with no warned test produced the worst
memory. Stated limit: lockout time itself may contribute. Memory only; the authors frame the
cost with desirable difficulties.

### Offloading as a metacognitive strategy

Risko and Gilbert, "Cognitive offloading", *Trends in Cognitive Sciences* 20(9):676–688
(2016), [doi:10.1016/j.tics.2016.07.002](https://doi.org/10.1016/j.tics.2016.07.002); full
text (author copy). Defines offloading as "the use of physical action to alter the
information processing requirements of a task so as to reduce cognitive demand". The
framework: offloading follows "a metacognitive evaluation of the available options" shaped
by beliefs and felt effort; using either strategy feeds back on those evaluations, which
"predicts a type of self-reinforcing pattern that will produce a drift away from reliance on
internal capabilities when situated in an environment with effective cognitive
technologies." Evidence of superfluous offloading: people wrote items down "about 40% of the
time when they were required to remember only two items" and "erroneously judged that
offloading would improve their performance." On learning: "any benefit of offloading will be
contingent on the fact that the demand being offloaded is unnecessary with respect to the
learning goal." Stated limit: "Understanding the long-term cognitive consequences of this
drift represents an important area of future research." On understanding versus memory:
the review says offloading "could also qualitatively change the processes involved in
thinking, communicating, and learning" but reports no direct evidence.

### Self-assessed knowledge

- Fisher, Goddu and Keil, "Searching for explanations: how the Internet inflates
  estimates of internal knowledge", *JEP: General* 144(3):674–687 (2015),
  [doi:10.1037/xge0000070](https://doi.org/10.1037/xge0000070); full text (archived author
  manuscript). Nine Mechanical Turk experiments (n = 138–302 each). After searching the
  Internet for explanations, participants rated their ability to explain *unrelated* topics
  higher: Experiment 1a M = 3.61 versus 3.07, t(195) = 3.24, p = .001, d = 0.50; with time,
  content and autonomy equated, d = 0.63; on a brain-image scale, d = 0.43; the effect
  persisted when searches failed and "is driven by querying Internet search engines".
  Stated limit: the sample "presumably use Internet search engines frequently". Measures
  metacognition — self-assessed explanatory understanding — not understanding or memory.
- Ward, "People mistake the internet's knowledge for their own", *PNAS*
  118(43):e2105061118 (2021),
  [doi:10.1073/pnas.2105061118](https://doi.org/10.1073/pnas.2105061118); full text (PMC).
  Eight experiments, n = 1,917. Google users predicted higher future unaided knowledge
  (F(1,157) = 13.73, p < 0.001) while actual unaided performance did not differ
  (F(1,157) = 2.25, p = 0.136); writing one's own answer first, or a 25-second delay
  before results, eliminated the misattribution; Google users attributed answers to
  themselves more than Wikipedia users did (F(1,154) = 8.17, p = 0.005). Metacognitive; a
  null on actual knowledge.

### Navigation

- Dahmani and Bohbot, "Habitual use of GPS negatively impacts spatial memory during
  self-guided navigation", *Scientific Reports* 10:6310 (2020),
  [doi:10.1038/s41598-020-62877-0](https://doi.org/10.1038/s41598-020-62877-0); full text.
  Fifty regular drivers; virtual-maze strategy and probe errors. Cross-sectional
  correlations were small: lifetime GPS hours with first-probe error r = −0.22 (BCa 95% CI
  [−0.41, −0.01]); GPS reliance with probe errors r = −0.25 [−0.44, −0.03]; landmarks
  noticed r = −0.26 [−0.42, −0.09]. In 13 participants retested after about three years,
  GPS hours since baseline correlated with decline in probe performance r = −0.68
  [−0.91, −0.10] and with map-drawing decline r = −0.52. No association with self-reported
  sense of direction (r = 0.07), which the authors use to argue direction of cause. Stated
  limits: "the longitudinal sample was small"; replication needed. Measures cognitive-map
  formation and learning rate — closer to understanding of a space than to item recall.
- Ishikawa, Fujiwara, Imai and Okabe, "Wayfinding with a GPS-based mobile navigation
  system: a comparison with maps and direct experience", *Journal of Environmental
  Psychology* 28(1):74–82 (2008),
  [doi:10.1016/j.jenvp.2007.09.002](https://doi.org/10.1016/j.jenvp.2007.09.002); abstract
  only. Six walked routes, three media. "GPS users traveled longer distances and made more
  stops … traveled more slowly, made larger direction errors, drew sketch maps with poorer
  topological accuracy, and rated wayfinding tasks as more difficult than direct-experience
  participants." n not verified. Measures configurational knowledge.

### Calculators

- Hembree and Dessart, "Effects of hand-held calculators in precollege mathematics
  education: a meta-analysis", *JRME* 17(2):83–99 (1986),
  [doi:10.2307/749255](https://doi.org/10.2307/749255); abstract only. Seventy-nine
  reports. "At all grades but Grade 4, a use of calculators in concert with traditional
  mathematics instruction apparently improves the average student's basic skills with paper
  and pencil, both in working exercises and in problem solving. Sustained calculator use in
  Grade 4 appears to hinder the development of basic skills in average students." Numeric
  effect sizes not reached.
- Ellington, "A meta-analysis of the effects of calculators on students' achievement and
  attitude levels in precollege mathematics classes", *JRME* 34(5):433–463 (2003),
  [doi:10.2307/30034795](https://doi.org/10.2307/30034795); abstract only. Fifty-four
  studies. "Students' operational skills and problem-solving skills improved when
  calculators were an integral part of testing and instruction. The results for both skill
  types were mixed when calculators were not part of assessment, but in all cases,
  calculator use did not hinder the development of mathematical skills." Stated limit:
  "further research is needed in the retention of mathematics skills after instruction and
  transfer of skills." Both meta-analyses measure paper-and-pencil skill, not memory, and
  both are null-to-positive.

### The extended mind as counter-position

Clark and Chalmers, "The extended mind", *Analysis* 58(1):7–19 (1998),
[doi:10.1093/analys/58.1.7](https://doi.org/10.1093/analys/58.1.7); full text
([author copy](http://consc.net/papers/extended.html)). The parity principle: "If, as we
confront some task, a part of the world functions as a process which, were it done in the
head, we would have no hesitation in recognizing as part of the cognitive process, then that
part of the world is (so we claim) part of the cognitive process." Otto's notebook counts as
memory because "the notebook is a constant in Otto's life", "the information in the
notebook is directly available without difficulty", "upon retrieving information from the
notebook he automatically endorses it", and it "has been consciously endorsed at some point
in the past" — the fourth criterion "is arguable". Philosophical; no empirical claim about
memory versus understanding.

### AI and critical thinking, 2024–2026

- Gerlich, "AI tools in society: impacts on cognitive offloading and the future of critical
  thinking", *Societies* 15(1):6 (2025),
  [doi:10.3390/soc15010006](https://doi.org/10.3390/soc15010006); full text. n = 666 UK
  respondents by convenience sampling plus 50 interviews; "critical thinking" is eight
  self-report habit items modelled on the HCTA, which was not administered. AI use
  correlated with offloading r = 0.72 and with critical thinking r = −0.68; offloading with
  critical thinking r = −0.75; mediation indirect b = −0.25, direct b = −0.17; younger
  respondents used AI more and scored lower. Author's stated limits: "reliance on
  self-reported measures and the potential for sample bias". Internal inconsistency: "deep
  thinking activities" are described as positive but carry β = −0.36. Critiques: a screen of
  about 1,000 citing works and Crossref found none; the only notice is the author's own
  correction (*Societies* 15(9):252, a duplicated table, "conclusions unaffected"). No
  performance measure of understanding or memory.
- Bastani et al., "Generative AI without guardrails can harm learning: evidence from high
  school mathematics", *PNAS* 122(26):e2422633122 (2025),
  [doi:10.1073/pnas.2422633122](https://doi.org/10.1073/pnas.2422633122); full text.
  Preregistered cluster RCT, about 50 classes and nearly 1,000 students in one Turkish high
  school, four sessions. On assisted practice, GPT Base +0.137 and GPT Tutor +0.361
  normalised grades over a control mean of 0.284 ("48% and 127%"); on the unassisted exam,
  GPT Base −0.054 (SE 0.022, p < 0.05, "17% reduction") and GPT Tutor −0.004 (n.s.). GPT
  Base's answers were correct "only 51% of the time"; the mechanism analysis favours
  "crutch" use; students "did not perceive that they performed worse or learned less".
  Stated limits: one topic, one school, Fall 2023, short-term outcomes. Measures transfer
  to conceptually similar unassisted problems — skill, not recall.
- Stadler, Bannert and Sailer, "Cognitive ease at a cost: LLMs reduce mental effort but
  compromise depth in student scientific inquiry", *Computers in Human Behavior*
  160:108386 (2024),
  [doi:10.1016/j.chb.2024.108386](https://doi.org/10.1016/j.chb.2024.108386); full text.
  Ninety-one students randomised to ChatGPT-3.5 or Google for a 20-minute inquiry. Germane
  load lower with the LLM (4.79 versus 3.14, η² = 0.27); quality of justifications lower
  (1.20 versus 1.87 relevant arguments, F = 11.18, p = 0.001, η² = 0.11); recommendation
  homogeneity unchanged (p = 0.411). Stated limits: no think-aloud; small student sample;
  forced duration. Measures depth of reasoning — understanding, not recall.
- Fan et al., "Beware of metacognitive laziness: effects of generative artificial
  intelligence on learning motivation, processes, and performance", *BJET* 56(2):489–530
  (2025), [doi:10.1111/bjet.13544](https://doi.org/10.1111/bjet.13544); full text of the
  arXiv preprint (2412.09315). 117 students randomised to ChatGPT-4, a human expert, a
  checklist, or control on one reading–writing task. Essay improvement favoured ChatGPT
  (F = 4.549, p = 0.005, η² = 0.108); knowledge gain (post-test F = 0.913, p = 0.438) and
  transfer (F = 0.019, p = 0.996) showed no differences; intrinsic-motivation subscales
  showed no differences. Stated limits: duration, sample, 70% female, no follow-up.
  Separates performance from knowledge and transfer: the former rose, the latter did not.
- Zindulka, Goller, Fernandes, Welsch and Buschek, "The AI memory gap: users misremember
  what they created with AI or without", *CHI 2026*,
  [arXiv:2509.11851](https://arxiv.org/abs/2509.11851); abstract. Preregistered, 184
  participants; one week later "the odds of correct attribution dropped, with the steepest
  decline in mixed human-AI workflows". Source memory only. This is reference [131] in
  Kosmyna et al.
- Barcaui, "ChatGPT as a cognitive crutch: evidence from a randomized controlled trial on
  knowledge retention", *Social Sciences & Humanities Open* 12:102287 (2025),
  [doi:10.1016/j.ssaho.2025.102287](https://doi.org/10.1016/j.ssaho.2025.102287);
  abstract. n = 120 undergraduates; surprise test 45 days later, 57.5% versus 68.5%
  correct, t(83) = −3.19, p = .002, d = 0.68. Retention only.
- Also seen but not read: Liu et al., "AI assistance reduces persistence and hurts
  independent performance", [arXiv:2604.04721](https://arxiv.org/abs/2604.04721) (RCTs,
  N = 1,222); Gerlich, "From offloading to engagement", *Data* 10(11):172 (2025),
  [doi:10.3390/data10110172](https://doi.org/10.3390/data10110172) (n = 150, structured
  prompting improved expert-rated reasoning). Shen and Tamkin (2026), Kosmyna et al.
  (2025) and Lee et al. (2025) are in the
  [evidence note](evidence-and-mechanisms.md#ai-specific-evidence-20232026).

### Memory versus understanding across the offloading sources

Sparrow, Storm and Stone, Grinschgl, Zindulka and Barcaui measure recall, recognition or
source memory and say nothing about understanding. Fisher and Ward measure *self-assessed*
understanding and find it inflated with actual unaided knowledge unchanged. Dahmani,
Ishikawa, Hembree, Ellington, Bastani, Stadler and Fan measure a skill or a reasoning
outcome; of these, the calculator meta-analyses are null-to-positive when the tool is also
present at test, and the AI studies find assisted performance up with unassisted skill flat
(Fan, GPT Tutor) or down (GPT Base, Stadler). Risko and Gilbert's condition — offloading is
benign only when "the demand being offloaded is unnecessary with respect to the learning
goal" — is the one general statement in the literature that distinguishes the two.

## The motivational account

### Self-determination theory

- Deci and Ryan, *Intrinsic Motivation and Self-Determination in Human Behavior* (Plenum,
  1985), [doi:10.1007/978-1-4899-2271-7](https://doi.org/10.1007/978-1-4899-2271-7);
  metadata only. Chapters 3–4 present cognitive evaluation theory; the three-need
  formulation below is cited to the 2000 review rather than to the book's pages, which were
  not read.
- Ryan and Deci, "Self-determination theory and the facilitation of intrinsic motivation,
  social development, and well-being", *American Psychologist* 55(1):68–78 (2000),
  [doi:10.1037/0003-066X.55.1.68](https://doi.org/10.1037/0003-066X.55.1.68); full text
  ([author copy](https://selfdeterminationtheory.org/SDT/documents/2000_RyanDeci_SDT.pdf)).
  "The findings have led to the postulate of three innate psychological needs —
  competence, autonomy, and relatedness — which when satisfied yield enhanced
  self-motivation and mental health and when thwarted lead to diminished motivation and
  well-being." Cognitive evaluation theory: "optimal challenges, effectance-promoting
  feedback, and freedom from demeaning evaluations were all found to facilitate intrinsic
  motivation"; "feelings of competence will not enhance intrinsic motivation unless
  accompanied by a sense of autonomy"; "not only tangible rewards but also threats,
  deadlines, directives, pressured evaluations, and imposed goals diminish intrinsic
  motivation"; and, on learning, "students taught with a more controlling approach not only
  lose initiative but learn less effectively, especially when learning requires conceptual,
  creative processing". Stated limit: CET "applies only to activities that hold intrinsic
  interest"; the relatedness link is "distal". Evidence: a narrative review of laboratory
  experiments and field studies.
- Deci, Koestner and Ryan, "A meta-analytic review of experiments examining the effects of
  extrinsic rewards on intrinsic motivation", *Psychological Bulletin* 125(6):627–668
  (1999), [doi:10.1037/0033-2909.125.6.627](https://doi.org/10.1037/0033-2909.125.6.627);
  full text (teaching copy). 128 studies. Expected tangible rewards undermined free-choice
  intrinsic motivation, composite d = −0.36 (CI −0.42 to −0.30; 92 studies); by
  contingency, d = −0.40, −0.36, −0.28; unexpected rewards d = 0.01; positive feedback
  enhanced free-choice behaviour d = 0.33 (college students d = 0.43, children d = 0.11,
  n.s.). Stated limits: uninteresting tasks excluded from primary analyses; single-session
  laboratory studies; heterogeneity (Q(91) = 224.85).

### Flow and its dark side

- Csikszentmihalyi, *Flow: The Psychology of Optimal Experience* (Harper & Row, 1990);
  quotations checked against a digitised copy on archive.org (identifier
  `flow-the-psychology-of-optimal-experience`). The definition Thomas and Howard quote is
  verbatim from the chapter "The Conditions of Flow": "a sense that one's skills are
  adequate to cope with the challenges at hand, in a goal-directed, rule-bound action system
  that provides clear clues as to how well one is performing." The challenge–skill diagram
  (the tennis player who is bored when skill exceeds challenge and anxious when challenge
  exceeds skill) is in the same chapter. On gambling: "gamblers who enjoy games of hazard
  are subjectively convinced that their skills do play a major role in the outcome …
  Roulette players develop elaborate systems to predict the turn of the wheel"; and "almost
  any enjoyable activity can become addictive, in the sense that instead of being a
  conscious choice, it becomes a necessity that interferes with other activities … the self
  becomes captive of a certain kind of order." The term "junk flow" does not occur in the
  book. Evidence base: interviews and the Experience Sampling Method, described in the
  book's notes; Nakamura and Csikszentmihalyi, "The concept of flow", in *Handbook of
  Positive Psychology* (Oxford, 2002), 89–105,
  [doi:10.1093/oso/9780195135336.003.0007](https://doi.org/10.1093/oso/9780195135336.003.0007),
  abstract only.
- "Junk flow": the only source located is a blog-hosted 2014 interview
  ([alearningaday.blog](https://alearningaday.blog/2014/04/21/prof-mihaly-csikszentmihalyi-on-flow-intrinsic-motivation-and-happiness/)),
  quoting Csikszentmihalyi: "Junk flow is when you are actually becoming addicted to a
  superficial experience that may be flow at the beginning, but after a while becomes
  something that you become addicted to instead of something that makes you grow." No
  published Csikszentmihalyi text using the term was found.
- "Dark flow": Dixon, Stange, Larche, Graydon, Fugelsang and Harrigan, "Dark flow,
  depression and multiline slot machine play", *Journal of Gambling Studies* 34:73–84
  (2018), [doi:10.1007/s10899-017-9695-1](https://doi.org/10.1007/s10899-017-9695-1); full
  text (PMC). The term is "a contraction of 'the dark side of flow'" from Partington,
  Partington and Olivier (2009) on big-wave surfing. 153 casino slot players; dark flow
  correlated with problem-gambling severity r(134) = .572 and with depression r(134) = .51
  (both p < .001); losses disguised as wins "were treated similarly to small wins" on the
  arousal measure. Limits: correlational; sample oversampled for problem gamblers. Dixon,
  Harrigan, Sandhu, Collins and Fugelsang, "Losses disguised as wins in modern multi-line
  video slot machines", *Addiction* 105(10):1819–1824 (2010),
  [doi:10.1111/j.1360-0443.2010.03050.x](https://doi.org/10.1111/j.1360-0443.2010.03050.x);
  abstract: 40 novices; "SCR amplitudes were similar for wins and LDWs — both were
  significantly larger than for regular losses."
- "Illusion of control": Langer, *JPSP* 32(2):311–328 (1975),
  [doi:10.1037/0022-3514.32.2.311](https://doi.org/10.1037/0022-3514.32.2.311); metadata
  only. Howard uses the phrase as "what psychologists call an illusion of control" without
  citation; Csikszentmihalyi's gambling passage above describes the same phenomenon without
  the term.

### Answer.AI's claim reconstructed from its sources

The claim as stated: delegation erodes autonomy and mastery, and agentic coding can induce
a gambling-like "junk flow" ([Answer.AI, claim 13](answer-ai-sweep.md#core-claims)). Its
sources, from the keynote transcript
([Growing on Purpose](https://www.youtube.com/watch?v=SUZwYV5JYBM), auto-captions) and
Thomas's post ([Breaking the spell of vibe coding](https://www.fast.ai/posts/2026-01-28-dark-flow/)):

- Howard reads the opening two paragraphs of Ryan and Deci (2000) — "the fullest
  representations of humanity show people to be curious, vital, and self-motivated … Yet it
  is also clear that the human spirit can be diminished or crushed" — and calls it "a review
  paper at the end of 30 years of research representing hundreds and hundreds of
  experiments". That is the paper's own framing. *Supported.*
- He lists "autonomy, mastery, relatedness and purpose", noting purpose is his own
  addition; "mastery" is Pink's word for SDT's competence. He states that authentic
  motivation yields "more interest, excitement, and confidence … enhanced performance and
  persistence and creativity … vitality, self-esteem, and general well-being", which
  paraphrases Ryan and Deci's summary of intrinsic-motivation outcomes. *Supported as
  paraphrase.*
- He quotes the *Flow* definition verbatim. *Supported.*
- He attributes "junk flow or dark flow" to Csikszentmihalyi. "Dark flow" is Dixon et
  al.'s; "junk flow" is from the 2014 interview. *Conflated attribution.*
- Thomas's post cites Dixon et al. (2018) for the physiological similarity of LDWs and wins
  and for the dark-flow construct, the 2014 interview for "junk flow", *Flow* for the
  definition and the roulette sentence, and METR for the perception gap; it splices two
  separate interview passages into one quotation. It cites no SDT source, and the words
  autonomy, mastery and competence do not occur in it. The mapping of LDWs to "the signs of
  how hard the AI coding agent is working and the quantities of code produced", and the
  claims that vibe coding "does not provide clear clues of how well one is performing",
  that "the match between challenge level and skill level is murky", and that it "provides a
  false sense of control", are her own inference by analogy; no gambling or flow study of
  developers is cited. *Team inference.*
- Howard's "the agent asking you … distributed system or green threads … decays your
  autonomy" and "the people getting you to use AI don't care about your autonomy and
  mastery. They care about your outputs" are his own applications. The nearest SDT support
  is the 2000 review's statement that "directives, pressured evaluations, and imposed
  goals" undermine intrinsic motivation and that controlling contexts impair conceptual
  learning; the reward meta-analysis (d = −0.36 for expected tangible rewards) is the
  closest evidence for "they care about your outputs". Neither is cited. *Team inference
  with adjacent support.*
- "Behavioural activation" as the depression-side evidence is asserted without a source
  and was not followed here. *Unsourced.*
- Ronacher's "the dopamine hit from working with these agents is so very real" is quoted
  accurately from
  [agent psychosis](https://lucumr.pocoo.org/2026/1/18/agent-psychosis/) (2026-01-18).
  *Testimonial.*

### Developer studies applying these frameworks

- Graziotin, Wang and Abrahamsson, "Happy software developers solve problems better",
  *PeerJ* 2:e289 (2014), [doi:10.7717/peerj.289](https://doi.org/10.7717/peerj.289); full
  text. Forty-two CS students split on affect balance; the positive group scored higher on
  an analytic (Tower of London) task, t(33.45) = −2.82, p = 0.008, d = −0.91, with no
  difference on creativity. Limit: students only. Graziotin, Fagerholm, Wang and
  Abrahamsson, "What happens when software developers are (un)happy", *JSS* 140:32–47
  (2018), [doi:10.1016/j.jss.2018.02.041](https://doi.org/10.1016/j.jss.2018.02.041); full
  text (arXiv). 317 questionnaire respondents; top consequences of unhappiness include
  "lower motivation" (21), "low focus" (16) and "broken flow" (5); of happiness, "high
  motivation" (42) and "sustained flow" (12). Pre-AI; self-report.
- Barke, James and Polikarpova, "Grounded Copilot", *PACMPL* 7(OOPSLA1):85 (2023),
  [doi:10.1145/3586030](https://doi.org/10.1145/3586030); full text (arXiv). Twenty
  participants; acceleration versus exploration modes
  ([in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)).
  On understanding, a participant: "my actual understanding of [the library] is not better
  but I was able to use them effectively"; the multi-suggestion pane "added to their
  cognitive load"; "first-time users were sometimes over-reliant on Copilot". Limits: 20
  participants skewed to academia, assigned tasks.
- Liang, Yang and Myers, "A large-scale survey on the usability of AI programming
  assistants", *ICSE 2024*,
  [doi:10.1145/3597503.3608128](https://doi.org/10.1145/3597503.3608128); full text
  (arXiv). 410 developers. Reasons for non-use: output not meeting requirements (54%) and
  "difficulty controlling the model" (48%); "not understanding generated code" was rated
  unimportant by 76%, and only 5.6% often had trouble understanding generated code. Limits:
  January 2023 sample of enthusiasts recruited from GitHub. The finding cuts against the
  premise: developers did not report comprehension as a felt problem.
- Kalliamvakou, GitHub blog (2022),
  [github.blog](https://github.blog/news-insights/research/research-quantifying-github-copilots-impact-on-developer-productivity-and-happiness/);
  vendor research. Over 2,000 technical-preview users: 73% "stay in the flow", 87%
  "preserve mental effort during repetitive tasks"; a 95-developer experiment (Peng et al.,
  [arXiv:2302.06590](https://arxiv.org/abs/2302.06590)): 55.8% faster (CI 21–89%),
  completion-rate difference not significant.
- Feng, Yun and Wang, "From junior to senior: allocating agency and navigating
  professional growth in agentic AI-mediated software engineering", *CHI 2026*,
  [doi:10.1145/3772318.3791642](https://doi.org/10.1145/3772318.3791642); full text (author
  PDF). Five seniors (ACTA and Delphi), ten juniors on a debugging task, five blind
  reviewers, summer 2025. "Juniors reported that authorship without understanding
  undermined fulfillment and ownership, while shaping the intent and using AI as labor —
  not judgment — restored achievement." Does not cite SDT, Csikszentmihalyi or Braverman.
  Limit: groups "cannot be directly compared".
- Alami, Paja and Tiwari, "The psychological costs of artificial intelligence adoption in
  software engineering", [arXiv:2609.03456](https://arxiv.org/abs/2609.03456) (2026); full
  text. One company, 21 interviews: "accountability anxiety, craft identity disruption,
  meaning and satisfaction erosion, cognitive and workload intensification, and uncertainty
  distress"; interpreted through SDT and citing Braverman. Single-site qualitative.
- Hicks, Lee and Foster-Marks, "The new developer: AI skill threat, identity change &
  developer thriving in the transition to AI-assisted software development", PsyArXiv
  (2024), [doi:10.31234/osf.io/2gej5](https://doi.org/10.31234/osf.io/2gej5); abstract.
  Survey of "3000+ software engineers and developers"; "AI Skill Threat" — fear that
  current skills will become obsolete — is higher where "innate brilliance" beliefs
  prevail and lower where learning cultures and belonging are reported. Cited by Storey
  ([evidence, practitioner framings](evidence-and-mechanisms.md#practitioner-framings-argument-not-evidence)).
  Preprint; self-report.
- Chi, Rietsche, Göldi, Ungar and Guntuku, "Optimized but unowned",
  [arXiv:2605.12344](https://arxiv.org/abs/2605.12344) (2026); abstract. Not developers:
  preregistered, N = 470, LLM-generated goals lowered psychological ownership (d = 1.38),
  which mediated every downstream motivational outcome. The cleanest ownership mechanism
  found, in a non-code task.
- Valovy, "Human-AI programming role optimization: developing a personality-driven
  self-determination framework", PhD dissertation,
  [arXiv:2511.00417](https://arxiv.org/abs/2511.00417) (2025); abstract. 200 experimental
  participants and 46 interviews; the only explicitly SDT-framed empirical work on
  AI-assisted programming found; results ("23% average motivation increases") are from the
  abstract only.
- Also seen, abstracts only: Andriotte and Ribeiro,
  [arXiv:2607.24606](https://arxiv.org/abs/2607.24606) (13 juniors; an "autonomy paradox":
  more capable, less ownership); Li et al., "Vibe coding in product teams",
  [arXiv:2509.10652](https://arxiv.org/abs/2509.10652) (22 interviews; deskilling and
  ownership); Sergeyuk et al., *IST* (2025),
  [doi:10.1016/j.infsof.2024.107610](https://doi.org/10.1016/j.infsof.2024.107610)
  (481 programmers; which activities they want to delegate).

### Deskilling as a labour-process concept

Braverman, *Labor and Monopoly Capital: The Degradation of Work in the Twentieth Century*
(Monthly Review Press, 1974); metadata only. The thesis, paraphrased and unverified against
the pages: scientific management separates the conception of work from its execution,
appropriating craft knowledge so that labour is cheapened and deskilled. In the AI-coding
discourse the word "deskilling" is used by Kosmyna et al. (citing Budzyń), Thomas ("skills
atrophy"), Li et al. (2025) and Chalkidis and Søgaard ("Brainrot",
[arXiv:2605.03512](https://arxiv.org/abs/2605.03512)); only Alami et al. (2026) cites
Braverman. Bainbridge herself used "deskilled" in 1983 for the job "reduced to
monitoring". None of the sibling notes invokes Braverman.

## Mapping to the existing notes

| Claim from the adjacent literature | Primary source | Setting and evidence type | Where the same claim appears |
| --- | --- | --- | --- |
| The supervisor is left with the tasks the designer could not automate, unsupported | Bainbridge 1983 | Process control; essay | Litt's "understanding to verify" as a residual thumbs-up role ([talk, Problem framing](understanding-bottleneck-talk.md#problem-framing)) |
| Manual and cognitive skills decay without use; knowledge retrieval depends on frequency of use | Bainbridge 1983; PSW 2000 | Essay; model paper | Answer.AI claims 3, 14 ([Core claims](answer-ai-sweep.md#core-claims)); Thomas "skills atrophy" ([Team writing](answer-ai-sweep.md#team-writing-and-talks)); retrieval practice ([evidence, summary table](evidence-and-mechanisms.md#summary-table)) |
| Monitoring reliable automation fails after about 20–30 minutes; worse under multitask load | Bainbridge 1983; Parasuraman et al. 1993 (n = 40) | Vigilance; PC flight simulation | "After the tenth approval you're clicking through" ([in-loop friction, Arguments and evidence](track-in-loop-friction.md#arguments-and-evidence)) |
| Automation bias: omission and commission errors with imperfect aids, confidence intact | Skitka et al. 1999 (n = 80); Parasuraman & Manzey 2010 | Simulated flights; review | Kaufman et al. 2026; Perry et al. 2023 ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| Reliance should be calibrated to capability; overtrust is miscalibration | Lee & See 2004 | Conceptual review | Trust gap and verification tax ([evidence, surveys](evidence-and-mechanisms.md#surveys-trust-and-verification-not-comprehension)); Lee et al. 2025 confidence result ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| Ten levels of automation from human-does-all to computer-decides-and-may-not-tell | Sheridan & Verplank 1978; PSW 2000 | Taxonomy | Permission-mode tables, uncited ([in-loop friction, Existing modes and tools](track-in-loop-friction.md#existing-modes-and-tools)) |
| Higher automation improves routine performance and degrades failure performance and SA; the break is between automating analysis and automating action selection | Onnasch et al. 2014 | Meta-analysis of 18 experiments | No counterpart |
| Passive processing lowers situation awareness; takeover after failure is slower | Endsley & Kiris 1995; Kaber & Endsley 2004 (n = 30) | Lab tasks | Litt's "peripheral vision" ([talk, Proposal 3](understanding-bottleneck-talk.md#proposal-3-micro-worlds)); Howard's "I wasn't really in control" ([Core claims](answer-ai-sweep.md#core-claims)); Sarkar's "material disengagement" ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| Automation conundrum: reliability up, awareness down | Endsley 2017 | Review | No counterpart as a stated relation |
| A short return to manual control restores failure detection | Parasuraman, Mouloua & Molloy 1996 | Lab; adaptive automation | No counterpart (AI-free days are an artefact without measurement, [landscape sweep, Cluster 7](landscape-sweep.md#cluster-7--friction-and-metacognitive-checkpoints)) |
| The state model needed for takeover takes time to build ("working storage") | Bainbridge 1983 | Essay | No counterpart |
| The most reliable automation needs the most training | Bainbridge 1983 | Essay | No counterpart |
| Feedback and display design, not less automation, is the fix | Norman 1990; Weiser via Litt | Case analysis; essay | Litt's HUD essay ([talk, Related material](understanding-bottleneck-talk.md#related-material)) |
| Motor skill survives infrequent practice; cognitive flight-management skill does not | Casner et al. 2014 (n = 16) | 747 simulator | No counterpart |
| Fine-motor skill tracks recent practice, not total experience | Haslbeck & Hoermann 2016 (n = 126) | A320/A340 simulators | Answer.AI claim 8 "don't move on until you get it" is practice-adjacent ([Core claims](answer-ai-sweep.md#core-claims)); no measurement |
| Regulators: manual-skill vulnerability, mode confusion, over-reliance | FAA 2013; SAFO 13002/17007; BEA 2012; NTSB 2014 | Accident and incident data | No counterpart |
| Trainees lose practice when the machine does the work; only a minority reach competence | Beane 2019 | Ethnography, 5 sites + 13 hospitals | Feng et al.'s mentorship-pipeline question ([in-loop friction, Open questions](track-in-loop-friction.md#open-questions-in-the-sources)); Howard's junior/senior/middle split ([Core claims](answer-ai-sweep.md#core-claims)) |
| Three months of AI exposure lowered unassisted detection from 28.4% to 22.4% | Budzyń et al. 2025 (n = 1,443) | Observational before–after | Kosmyna's unfollowed [130] ([evidence, dead ends](evidence-and-mechanisms.md#dead-ends-and-gaps)) |
| Deskilled monitoring jobs damage status and satisfaction | Bainbridge 1983 §1.2; Braverman 1974 | Essay; labour theory | Feng et al.'s juniors' ownership loss ([in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)); no Braverman |
| Expecting information to be saved lowers recall of it | Sparrow et al. 2011 (Exp. 2–3, n ≈ 28–60) | Lab; Exp. 1 failed replication | No counterpart |
| Saving one item frees memory for the next, only if saving is reliable | Storm & Stone 2015 | Lab | No counterpart |
| Offloading raises performance and lowers memory for the offloaded content | Grinschgl et al. 2021 (N = 172 × 3) | Preregistered lab | Qiao et al.: performance up, comprehension flat ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| Offloading is a metacognitive choice that drifts self-reinforcingly toward the tool | Risko & Gilbert 2016 | Review | Answer.AI claim 7 on defaults over willpower and claim 14 on bifurcation ([Core claims](answer-ai-sweep.md#core-claims)); Storey's offloading/surrender distinction ([evidence, practitioner framings](evidence-and-mechanisms.md#practitioner-framings-argument-not-evidence)) |
| Searching inflates self-assessed explanatory knowledge; actual unaided knowledge unchanged | Fisher et al. 2015 (d = 0.43–0.63); Ward 2021 (n = 1,917) | Online experiments | Illusion of competence; METR perception gap; Kaufman's intact confidence ([evidence, illusion of competence](evidence-and-mechanisms.md#illusion-of-competence-and-fluency)) |
| Habitual GPS use correlates with poorer cognitive-map formation | Dahmani & Bohbot 2020 (n = 50; 13 longitudinal); Ishikawa 2008 | Virtual mazes; walked routes | Naur's theory not in the text, as the analogue of a map ([evidence, Naur](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text)); no measurement |
| Calculators do not hinder skill when integrated in instruction and testing (Grade 4 aside) | Hembree & Dessart 1986 (79 reports); Ellington 2003 (54 studies) | Meta-analyses | No counterpart; the AI-coding sources assume harm |
| A reliably available, automatically endorsed external store is part of the mind | Clark & Chalmers 1998 | Philosophy | No counterpart; Litt's "extend the human mind" HUD language is the nearest phrase ([talk, Related material](understanding-bottleneck-talk.md#related-material)) |
| Unguarded AI raises assisted practice and lowers unassisted exam; students do not notice | Bastani et al. 2025 (~1,000 students) | Cluster RCT | Shen & Tamkin; Sankaranarayanan's gate; Maier meta-analysis ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| LLM use lowers germane load and argument quality | Stadler et al. 2024 (n = 91) | RCT | Lee et al. 2025 self-report is the nearest ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| AI improves the artefact, not knowledge or transfer; motivation unchanged | Fan et al. 2025 (n = 117) | RCT | Maier et al. productivity g = 0.33, learning n.s. ([evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)) |
| AI use correlates with lower self-reported critical thinking | Gerlich 2025 (n = 666) | Cross-sectional survey | No counterpart |
| People misremember whether they or the AI produced content | Zindulka et al. 2026 (n = 184) | Preregistered experiment | Ownership dead end ([evidence, dead ends](evidence-and-mechanisms.md#dead-ends-and-gaps)) |
| Competence, autonomy, relatedness; controlling contexts impair conceptual learning | Ryan & Deci 2000 | Narrative review | Answer.AI claim 13 ([Core claims](answer-ai-sweep.md#core-claims)), cited by Howard |
| Expected tangible rewards undermine intrinsic motivation, d = −0.36 | Deci, Koestner & Ryan 1999 | Meta-analysis, 128 studies | Howard's "they care about your outputs", uncited ([Core claims](answer-ai-sweep.md#core-claims)) |
| Flow requires challenge–skill balance, clear goals, immediate feedback; flow activities can become addictive | Csikszentmihalyi 1990 | Interviews, ESM | Answer.AI claim 13; Thomas's dark-flow post ([Evidence offered](answer-ai-sweep.md#evidence-offered)) |
| Dark flow correlates with problem gambling and depression; LDWs arouse like wins | Dixon et al. 2018 (n = 153); Dixon et al. 2010 (n = 40) | Correlational; psychophysiology | Thomas's post, cited; the vibe-coding analogy is hers ([Evidence offered](answer-ai-sweep.md#evidence-offered)) |
| Authorship without understanding undermines ownership and fulfilment | Feng et al. 2026 (5 + 10 + 5) | Qualitative | Feng's agency practices ([in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)); the ownership finding is not quoted there |
| Developers do not report understanding generated code as a felt problem (5.6%) | Liang et al. 2024 (n = 410) | Survey | Liang's control finding ([in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)); the comprehension item has no counterpart |
| AI skill threat is moderated by learning culture and belonging | Hicks et al. 2024 (3,000+) | Survey preprint | No counterpart beyond Storey's citation |
| Conception separated from execution deskills labour | Braverman 1974 | Labour theory | No counterpart |
| "Labour-saving" technology relocates work rather than removing it; the whole job returns to one person (added 2026-09-13) | Cowan 1976; Cowan 1983, p. 100 | Social history; time-budget studies | Vella and Blincoe's shift "from creation to verification" ([literature addendum, Target 1](literature-addendum.md#target-1-comprehension-ownership-and-skill-studies-of-professionals-20252026)); CUPS 22.4% verifying and METR's no time saved ([in-loop friction, Interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking); [evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026)); see [Cowan note, mapping](cowan-more-work-for-mother.md#mapping-to-the-existing-notes) |
| The standard rises to absorb the saving ("spotless shirts") (added 2026-09-13) | Cowan 1983, p. 216; Mokyr 2000 (germ theory as the rival mechanism) | Social history; economic history | Throughput only: PostHog's 1,441→4,725 PRs a month ([discourse addendum, Target 2](discourse-and-tooling-addendum.md#target-2-company-engineering-blogs-and-public-rfcs)); review scrutiny falls rather than rises ([hand-off checks, Evidence](track-hand-off-checks.md#evidence)); no counterpart for a rising standard of understanding |
| What a technology saves is decided at the point of use, from the consumer's point of view (added 2026-09-13) | Cowan 1987 | Sociology of technology; proposal | No counterpart as a method; Answer.AI's defaults-over-willpower claim is the nearest ([Core claims](answer-ai-sweep.md#core-claims)) |

## Dead ends

- Search tooling: WebSearch was unavailable throughout. OpenAlex exhausted its daily
  budget partway (429 "insufficient budget", resets at midnight UTC), Semantic Scholar and
  the arXiv API rate-limited, and Google Books' API quota was exhausted; Sage, ScienceDirect,
  Wiley, Lancet, IEEE, MDPI (mdpi.com, not its CDN), Springer, PeerJ, APA PsycNet and MIT
  Press returned 403 or bot challenges to curl and WebFetch. Full texts were reached through
  author pages, PMC, NTRS, DLR, LMU and UCL repositories, archive.org and the Wayback
  Machine; the sections above name which. The 2023–2026 developer-study list is from arXiv
  HTML search and Crossref only and is not exhaustive.
- Abstract-only, with numbers unverified: Parasuraman and Riley 1997; Parasuraman, Molloy
  and Singh 1993 (detection percentages); Endsley and Kiris 1995 (n, levels, takeover
  times); Endsley 2017 (lessons list); Parasuraman and Manzey 2010; Onnasch et al. 2014;
  Wickens et al. 2015 (n); Parasuraman, Mouloua and Molloy 1996 (n, rates); Casner et al.
  2014 (effect sizes); Beane 2019 (counts); Budzyń et al. 2025 (limitations section and
  the 10(11):e12 correction); Strauch 2018; Storm and Stone 2015; Ishikawa et al. 2008 (n);
  Hembree and Dessart 1986 and Ellington 2003 (numeric effect sizes — not to be cited from
  memory); Nakamura and Csikszentmihalyi 2002 (conditions wording); Dixon et al. 2010;
  Valovy 2025; Chi et al. 2026; Zindulka et al. 2026; Barcaui 2025.
- Metadata only: Deci and Ryan 1985 (the three-need wording and the
  controlling/informational distinction were not checked against the pages); Sheridan
  1992; Csikszentmihalyi 1975; Langer 1975 (abstract page would not render); Braverman
  1974.
- Corrections to the brief's own framing found on reading: Parasuraman, Sheridan and
  Wickens list workload, SA, complacency and skill degradation as *primary* criteria;
  Wickens et al. 2015 is an experiment, not a meta-analysis; Macnamara et al. 2024 is a
  perspective with no data; the DOI usually given for Parasuraman, Mouloua and Molloy 1996
  (10.1177/001872089606380410) does not resolve — the registered DOI is
  10.1518/001872096778827279; Clark and Chalmers' author copy gives pages 10–23 while
  Crossref gives 7–19.
- "Junk flow": no published Csikszentmihalyi source; only the 2014 blog interview. Howard's
  attribution of "dark flow" to Csikszentmihalyi is not supported.
- "Behavioural activation" as cited in the keynote: no source given; not followed.
- Gerlich 2025 critiques: none found among about 1,000 citing works or by Crossref title
  search; only the author's correction.
- Sparrow et al. Experiments 2–4 have no located replication attempt; the Social Sciences
  Replication Project site was unreachable (DNS failure), so replication details come from
  the Camerer et al. supplement.
- Feng et al. 2026 was read from the author PDF; the ACM landing page was not fetched (403)
  (corrected 2026-09-13: the preprint is <https://arxiv.org/abs/2602.00496>, "To appear in
  CHI'26"; see the [literature addendum](literature-addendum.md#corrections-proposed)). Koshchenko et al. (FSE 2026, "Configurable AI coding assistants … for
  developers who like to be in control") and Le (2025, IGI chapter on deskilling) exist as
  metadata only.
- No study found that measures situation awareness, complacency, or skill decay in
  developers supervising coding agents in the human-factors sense; no study found that
  measures motivation, ownership or flow under agentic delegation with more than ~20
  professionals; no offloading study found that measures understanding of a codebase.
- The Howard keynote was read from YouTube auto-captions; speaker names ("Ammon", "Armen")
  were resolved to Ronacher by the quoted text; timestamps were not extracted.

## References

Primary sources, alphabetical. DOIs and URLs above are the terminal citations.

- Alami, A., Paja, A., Tiwari, M. (2026). The psychological costs of artificial intelligence adoption in software engineering. arXiv:2609.03456.
- Bainbridge, L. (1983). Ironies of automation. *Automatica* 19(6):775–779. doi:10.1016/0005-1098(83)90046-8.
- Barcaui, A. (2025). ChatGPT as a cognitive crutch. *Social Sciences & Humanities Open* 12:102287. doi:10.1016/j.ssaho.2025.102287.
- Barke, S., James, M. B., Polikarpova, N. (2023). Grounded Copilot. *PACMPL* 7(OOPSLA1):85. doi:10.1145/3586030.
- Bastani, H., Bastani, O., Sungu, A., Ge, H., Kabakcı, Ö., Mariman, R. (2025). Generative AI without guardrails can harm learning. *PNAS* 122(26):e2422633122. doi:10.1073/pnas.2422633122.
- Baxter, G., Rooksby, J., Wang, Y., Khajeh-Hosseini, A. (2012). The ironies of automation: still going strong at 30? *ECCE 2012*, 65–71. doi:10.1145/2448136.2448149.
- BEA (2012). Final report on the accident on 1st June 2009 to the Airbus A330-203 registered F-GZCP operated by Air France flight AF 447. https://bea.aero/fileadmin/documents/docspa/2009/f-cp090601.en/pdf/f-cp090601.en.pdf
- Beane, M. (2019). Shadow learning. *Administrative Science Quarterly* 64(1):87–123. doi:10.1177/0001839217751692.
- Braverman, H. (1974). *Labor and Monopoly Capital*. Monthly Review Press.
- Budzyń, K., et al. (2025). Endoscopist deskilling risk after exposure to artificial intelligence in colonoscopy. *Lancet Gastroenterology & Hepatology* 10(10):896–903. doi:10.1016/S2468-1253(25)00133-5.
- Camerer, C. F., et al. (2018). Evaluating the replicability of social science experiments in Nature and Science between 2010 and 2015. *Nature Human Behaviour* 2(9):637–644. doi:10.1038/s41562-018-0399-z.
- Casner, S. M., Geven, R. W., Recker, M. P., Schooler, J. W. (2014). The retention of manual flying skills in the automated cockpit. *Human Factors* 56(8):1506–1516. doi:10.1177/0018720814535628.
- Chalkidis, I., Søgaard, A. (2026). Brainrot: deskilling and addiction are overlooked AI risks. arXiv:2605.03512.
- Chi, Y., Rietsche, R., Göldi, A., Ungar, L., Guntuku, S. C. (2026). Optimized but unowned. arXiv:2605.12344.
- Clark, A., Chalmers, D. (1998). The extended mind. *Analysis* 58(1):7–19. doi:10.1093/analys/58.1.7.
- Csikszentmihalyi, M. (1990). *Flow: The Psychology of Optimal Experience*. Harper & Row.
- Dahmani, L., Bohbot, V. D. (2020). Habitual use of GPS negatively impacts spatial memory during self-guided navigation. *Scientific Reports* 10:6310. doi:10.1038/s41598-020-62877-0.
- Deci, E. L., Koestner, R., Ryan, R. M. (1999). A meta-analytic review of experiments examining the effects of extrinsic rewards on intrinsic motivation. *Psychological Bulletin* 125(6):627–668. doi:10.1037/0033-2909.125.6.627.
- Deci, E. L., Ryan, R. M. (1985). *Intrinsic Motivation and Self-Determination in Human Behavior*. Plenum. doi:10.1007/978-1-4899-2271-7.
- Dixon, M. J., Harrigan, K. A., Sandhu, R., Collins, K., Fugelsang, J. A. (2010). Losses disguised as wins in modern multi-line video slot machines. *Addiction* 105(10):1819–1824. doi:10.1111/j.1360-0443.2010.03050.x.
- Dixon, M. J., Stange, M., Larche, C. J., Graydon, C., Fugelsang, J. A., Harrigan, K. A. (2018). Dark flow, depression and multiline slot machine play. *Journal of Gambling Studies* 34:73–84. doi:10.1007/s10899-017-9695-1.
- Ellington, A. J. (2003). A meta-analysis of the effects of calculators on students' achievement and attitude levels in precollege mathematics classes. *JRME* 34(5):433–463. doi:10.2307/30034795.
- Endsley, M. R. (1995). Toward a theory of situation awareness in dynamic systems. *Human Factors* 37(1):32–64. doi:10.1518/001872095779049543.
- Endsley, M. R. (2017). From here to autonomy. *Human Factors* 59(1):5–27. doi:10.1177/0018720816681350.
- Endsley, M. R., Kiris, E. O. (1995). The out-of-the-loop performance problem and level of control in automation. *Human Factors* 37(2):381–394. doi:10.1518/001872095779064555.
- FAA (2013). SAFO 13002, Manual Flight Operations. FAA (2017). SAFO 17007, Manual Flight Operations Proficiency.
- FAA PARC/CAST Flight Deck Automation Working Group (2013). *Operational Use of Flight Path Management Systems*. https://www.faa.gov/sites/faa.gov/files/aircraft/air_cert/design_approvals/human_factors/OUFPMS_Report.pdf
- Fan, Y., et al. (2025). Beware of metacognitive laziness. *BJET* 56(2):489–530. doi:10.1111/bjet.13544.
- Feng, K. J. K., Yun, B., Wang, X. (2026). From junior to senior. *CHI 2026*. doi:10.1145/3772318.3791642.
- Fisher, M., Goddu, M. K., Keil, F. C. (2015). Searching for explanations. *JEP: General* 144(3):674–687. doi:10.1037/xge0000070.
- Gerlich, M. (2025). AI tools in society. *Societies* 15(1):6. doi:10.3390/soc15010006. Correction: *Societies* 15(9):252. doi:10.3390/soc15090252.
- Graziotin, D., Fagerholm, F., Wang, X., Abrahamsson, P. (2018). What happens when software developers are (un)happy. *JSS* 140:32–47. doi:10.1016/j.jss.2018.02.041.
- Graziotin, D., Wang, X., Abrahamsson, P. (2014). Happy software developers solve problems better. *PeerJ* 2:e289. doi:10.7717/peerj.289.
- Grinschgl, S., Papenmeier, F., Meyerhoff, H. S. (2021). Consequences of cognitive offloading. *QJEP* 74(9):1477–1496. doi:10.1177/17470218211008060.
- Haslbeck, A., Hoermann, H.-J. (2016). Flying the needles. *Human Factors* 58(4):533–545. doi:10.1177/0018720816640394.
- Heer, J. (2019). Agency plus automation. *PNAS* 116(6):1844–1850. doi:10.1073/pnas.1807184115.
- Hembree, R., Dessart, D. J. (1986). Effects of hand-held calculators in precollege mathematics education. *JRME* 17(2):83–99. doi:10.2307/749255.
- Hicks, C. M., Lee, C. S., Foster-Marks, K. (2024). The new developer. PsyArXiv. doi:10.31234/osf.io/2gej5.
- Howard, J. (2026). Growing on Purpose: The Work That Makes You. AI Engineer Melbourne keynote. https://www.youtube.com/watch?v=SUZwYV5JYBM
- Ishikawa, T., Fujiwara, H., Imai, O., Okabe, A. (2008). Wayfinding with a GPS-based mobile navigation system. *Journal of Environmental Psychology* 28(1):74–82. doi:10.1016/j.jenvp.2007.09.002.
- Kaber, D. B., Endsley, M. R. (2004). The effects of level of automation and adaptive automation on human performance, situation awareness and workload in a dynamic control task. *Theoretical Issues in Ergonomics Science* 5(2):113–153. doi:10.1080/1463922021000054335.
- Kalliamvakou, E. (2022). Research: quantifying GitHub Copilot's impact on developer productivity and happiness. GitHub blog. Peng, S., Kalliamvakou, E., Cihon, P., Demirer, M. (2023). arXiv:2302.06590.
- Langer, E. J. (1975). The illusion of control. *JPSP* 32(2):311–328. doi:10.1037/0022-3514.32.2.311.
- Lee, J. D., See, K. A. (2004). Trust in automation. *Human Factors* 46(1):50–80. doi:10.1518/hfes.46.1.50_30392.
- Liang, J. T., Yang, C., Myers, B. A. (2024). A large-scale survey on the usability of AI programming assistants. *ICSE 2024*. doi:10.1145/3597503.3608128.
- Litt, G. (2025). Enough AI copilots! We need AI HUDs. https://www.geoffreylitt.com/2025/07/27/enough-ai-copilots-we-need-ai-huds
- Macnamara, B. N., et al. (2024). Does using artificial intelligence assistance accelerate skill decay and hinder skill development without performers' awareness? *Cognitive Research: Principles and Implications* 9:46. doi:10.1186/s41235-024-00572-8.
- Nakamura, J., Csikszentmihalyi, M. (2002). The concept of flow. In *Handbook of Positive Psychology*, Oxford, 89–105. doi:10.1093/oso/9780195135336.003.0007.
- Norman, D. A. (1990). The 'problem' with automation. *Phil. Trans. R. Soc. B* 327(1241):585–593. doi:10.1098/rstb.1990.0101.
- NTSB (2014). *Descent Below Visual Glidepath and Impact With Seawall, Asiana Airlines Flight 214*. AAR-14/01. https://www.ntsb.gov/investigations/AccidentReports/Reports/AAR1401.pdf
- Onnasch, L., Wickens, C. D., Li, H., Manzey, D. (2014). Human performance consequences of stages and levels of automation. *Human Factors* 56(3):476–488. doi:10.1177/0018720813501549.
- Parasuraman, R., Manzey, D. H. (2010). Complacency and bias in human use of automation. *Human Factors* 52(3):381–410. doi:10.1177/0018720810376055.
- Parasuraman, R., Molloy, R., Singh, I. L. (1993). Performance consequences of automation-induced 'complacency'. *International Journal of Aviation Psychology* 3(1):1–23. doi:10.1207/s15327108ijap0301_1.
- Parasuraman, R., Mouloua, M., Molloy, R. (1996). Effects of adaptive task allocation on monitoring of automated systems. *Human Factors* 38(4):665–679. doi:10.1518/001872096778827279.
- Parasuraman, R., Riley, V. (1997). Humans and automation: use, misuse, disuse, abuse. *Human Factors* 39(2):230–253. doi:10.1518/001872097778543886.
- Parasuraman, R., Sheridan, T. B., Wickens, C. D. (2000). A model for types and levels of human interaction with automation. *IEEE Trans. SMC–A* 30(3):286–297. doi:10.1109/3468.844354.
- Risko, E. F., Gilbert, S. J. (2016). Cognitive offloading. *Trends in Cognitive Sciences* 20(9):676–688. doi:10.1016/j.tics.2016.07.002.
- Ronacher, A. (2026). Agent psychosis. https://lucumr.pocoo.org/2026/1/18/agent-psychosis/
- Ryan, R. M., Deci, E. L. (2000). Self-determination theory and the facilitation of intrinsic motivation, social development, and well-being. *American Psychologist* 55(1):68–78. doi:10.1037/0003-066X.55.1.68.
- Sheridan, T. B. (1992). *Telerobotics, Automation, and Human Supervisory Control*. MIT Press.
- Sheridan, T. B., Verplank, W. L. (1978). *Human and Computer Control of Undersea Teleoperators*. MIT Man-Machine Systems Laboratory; DTIC ADA057655.
- Skitka, L. J., Mosier, K. L., Burdick, M. (1999). Does automation bias decision-making? *IJHCS* 51(5):991–1006. doi:10.1006/ijhc.1999.0252.
- Sparrow, B., Liu, J., Wegner, D. M. (2011). Google effects on memory. *Science* 333(6043):776–778. doi:10.1126/science.1207745.
- Stadler, M., Bannert, M., Sailer, M. (2024). Cognitive ease at a cost. *Computers in Human Behavior* 160:108386. doi:10.1016/j.chb.2024.108386.
- Storm, B. C., Stone, S. M. (2015). Saving-enhanced memory. *Psychological Science* 26(2):182–188. doi:10.1177/0956797614559285.
- Strauch, B. (2018). Ironies of automation: still unresolved after all these years. *IEEE THMS* 48(5):419–433. doi:10.1109/THMS.2017.2732506.
- Thomas, R. (2026). Breaking the spell of vibe coding. https://www.fast.ai/posts/2026-01-28-dark-flow/
- Valovy, M. (2025). Human-AI programming role optimization. arXiv:2511.00417.
- Ward, A. F. (2021). People mistake the internet's knowledge for their own. *PNAS* 118(43):e2105061118. doi:10.1073/pnas.2105061118.
- Wickens, C. D., Clegg, B. A., Vieane, A. Z., Sebok, A. L. (2015). Complacency and automation bias in the use of imperfect automation. *Human Factors* 57(5):728–739. doi:10.1177/0018720815581940.
- Zindulka, T., Goller, S., Fernandes, D., Welsch, R., Buschek, D. (2026). The AI memory gap. *CHI 2026*. arXiv:2509.11851.
