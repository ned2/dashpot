---
status: research
date: 2026-09-15
---

# Automation as a team player

Research date: 2026-09-15

This note documents what the joint-activity and human–autonomy-teaming strand of human
factors says about automation as a teammate — common ground, observability, directability,
predictability, and the cost of coordinating with a machine agent — and how the AI-teammate
literature of 2019–2026, including the coding-agent studies of 2025–2026, relates to it. It
extends the [supervising-automation section of the adjacent-literatures note](adjacent-literatures.md#supervising-automation),
which already covers Bainbridge's ironies, complacency and automation bias, levels of
automation, situation awareness, adaptive automation and skill fade; those are linked, not
repeated. It is documentary: it records what the sources say, with evidence type and size, and
maps each finding to where the existing notes in this directory touch it. It does not evaluate
fit for Dashpot or any tool. Terminal citations are primary and every figure is reported as
the source states it. Read level is marked per source: "full text", "abstract", "metadata",
"secondary"; anything recalled rather than read is marked "unverified". Where an earlier note
already covers a source, this note links to it: DeChurch and Mesmer-Magnus's meta-analysis is in
[unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#team-cognition-research),
the 1-to-N versus N-to-N distinction and Raida and Hou's single-human supervision figure are
in [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#single-developer-orchestration-is-not-team-level-engineering),
and the AI-pairing analogies are in
[track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking).

## Finding

The joint-activity strand answers "what does automation need in order to be a teammate" with
one argument, restated across a decade of position papers and grounded in aviation field
studies: automation fails as a team player not because it has too much or too little
autonomy but because it is "strong, silent, difficult to direct" — so the design target is
coordination, not a level of automation. Christoffersen and Woods (2002) state the two
requirements as observability ("users need to be able to see what the automated agents are
doing and what they will do next relative to the state of the process") and directability
("re-direct machine activities fluently"), and warn that "data availability does not equal
informativeness" ([full text](https://web.archive.org/web/20220125021917id_/http://csel.eng.ohio-state.edu/productions/xcta/downloads/automation_team_players.pdf)).
Klein, Woods, Bradshaw, Hoffman and Feltovich (2004) expand these into four requirements of
joint activity — a Basic Compact, mutual predictability, mutual directability, and common
ground — and ten challenges, the tenth being that "all team members must help control the
costs of coordinated activity" ([full text](https://web.archive.org/web/2024id_/https://www.jeffreymbradshaw.net/publications/17._Team_Players.pdf_1.pdf)).
The chapter behind that piece (Klein, Feltovich, Bradshaw and Woods 2005) defines coordination
cost as "the burden on joint action participants that is due to choreographing their efforts",
names four overheads — synchronization, communication, redirection, diagnosis — asserts that
"no amount of procedure or documentation can totally prevent" common-ground breakdowns, and
grounds the automation case in Sarter and Woods' full-mission A-320 simulation, where 4 of 18
experienced pilots never noticed the automation dropping altitude constraints and 12 of the 14
who noticed could not recover in time ([chapter preprint](https://web.archive.org/web/2024id_/https://www.jeffreymbradshaw.net/publications/Common_Ground_Single.pdf);
[Sarter and Woods 2000, abstract](https://doi.org/10.1518/001872000779698178)). Johnson et al.
(2014) turn the challenges into a design method — observability, predictability and
directability (OPD) requirements read off an interdependence-analysis table — and report the
one worked case with numbers: the winning DARPA Virtual Robotics Challenge entry (26 teams)
ran an average of 10 scripts per hose-task run, only 50% without intervention, with 9 pauses
and 7 operator corrections per run, and recovered from all 8 of 50 script failures because
every scripted step was observable, predictable and directable ([full text](https://repository.tudelft.nl/record/uuid:35cfe91a-bd59-427d-89a9-e2019f9b0c28)).
Bradshaw, Hoffman, Johnson and Woods (2013) list seven myths of autonomy, of which the sixth —
machines as "simple substitutes (or multipliers) of human capability" — is the substitution
myth, and tabulate the putative benefit "frees up limited attention" against the observed
"creates more threads to track … with coordination costs, continuously" ([full text](https://web.archive.org/web/20260511062134id_/https://www.jeffreymbradshaw.net/publications/IS-28-03-HCC_1.pdf)).
The human–autonomy-teaming (HAT) literature that followed measured the coordination cost the
strand predicted, but only in simulation: O'Neill et al.'s review of 76 empirical HAT studies
found every one simulation-based, 57 military or emergency, and human–human teams "generally
had better outcomes" than HATs ([PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC9284085/));
McNeese et al. (2018; 3 configurations × 10 three-person teams) found synthetic-teammate teams
matched all-human teams at mission level but processed targets less efficiently
([abstract](https://doi.org/10.1177/0018720817743223)), and Demir et al. (2019) traced this to
the synthetic teammate pulling information rather than pushing it, producing "very stable and
rigid coordination" ([full text](https://www.frontiersin.org/articles/10.3389/fcomm.2019.00050/pdf)).
The AI-teammate literature of 2019–2026 restates the strand's requirements in its own
vocabulary without citing it: Bansal et al. (2019; 25 crowdworkers per condition) find team
performance depends on the human's mental model of the AI's error boundary
([full text](https://ojs.aaai.org/index.php/HCOMP/article/download/5285/5137)); Amershi et al.
(2019; 49 practitioners × 20 products) list "make clear why the system did what it did",
"support efficient correction" and "notify users about changes" among 18 guidelines
([full text](https://web.archive.org/web/20250130135417id_/https://www.microsoft.com/en-us/research/uploads/prod/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf));
Weisz et al. (2024) add "design for co-creation" and "use friction to avoid overreliance"
([HTML](https://arxiv.org/html/2401.14484)); none cites Klein, Woods or Bradshaw. Field
experiments with generative-AI teammates outside code find AI reshaping teamwork rather than
joining it: with 776 P&G professionals, individuals with AI matched teams without AI
([abstract](https://doi.org/10.3386/w33641)); with 2,234 participants, human–AI pairs sent 25%
more task-oriented and 18% fewer interpersonal messages and delegated 17% more
([abstract](https://arxiv.org/abs/2503.18238)). For coding agents the only coordination-cost
measurements are on agent–agent or agent–successor pairs, or on the reviewer side: CooperBench
(652 tasks) finds two agents coordinating lose on average 41% of solo success (qualified 2026-09-15: 41% is the pooled Solo-capability loss in the HTML results table, "pooled retention 0.59"; the abstract states the headline as "on average 30% lower success rates when working together"), 20% of steps
going to communication ([HTML](https://arxiv.org/html/2601.13295)); Handoff Debt (75 tasks, 724
takeover runs per model) finds a successor agent given the predecessor's trace or notes needs
20–59% fewer events and 42–63% fewer prompt tokens than one given the repository alone
([abstract](https://arxiv.org/abs/2606.02875)); Nachuma and Zibran (33,596 agent PRs) find
reviewer engagement the strongest correlate of merge and force-pushes during review penalised,
concluding that "reviewers reward agent behaviors that reduce coordination cost and penalize
those that disrupt shared understanding" ([HTML](https://arxiv.org/html/2602.19441)); and Tang
et al. (20,574 sessions) find "inaccurate self-reporting" in 22.58% of misalignment episodes and
rising in share — the observability failure the strand named "strong silent automation"
([HTML](https://arxiv.org/html/2605.29442)). No source found measures the coordination cost a
coding agent imposes on a human team, as opposed to on one developer or one reviewer.

## The joint-activity strand, 1995–2014

### Automation surprises and mode awareness

- **Sarter, Woods and Billings, "Automation surprises"**, *Handbook of Human Factors and
  Ergonomics*, 2nd ed., Salvendy (ed.), Wiley 1997; read in full from the Ohio State
  preprint ([Wayback](https://web.archive.org/web/20260205021152id_/http://csel.eng.ohio-state.edu/productions/xcta/downloads/automation_surprises.pdf)).
  The chapter defines mode awareness as "the ability of a supervisor to track and to
  anticipate the behavior of automated systems", and automation surprises as what
  "breakdowns in mode awareness result in". It reports that Wiener's 1989 survey of B-757
  pilots found "about 55% of all respondents said that they were still being surprised by the
  automation after more than one year of line experience", that Sarter and Woods (1992)
  "replicated Wiener's results" at a different airline on the B737-300/400, and that in a
  later simulator study pilots "were overconfident and miscalibrated about how well they
  understood the Flight Management System" — "the number and severity of pilots' problems
  during the simulated flight was higher than was to be expected from the survey" (survey and
  simulation; n not stated in the chapter). Its design conclusion, attributed to Billings
  (1991), is that "as long as human operators bear ultimate responsibility for operational
  goals, they must be in command", so "the automation must be observable, and it needs to act
  in predictable ways". The epigraph — "The road to technology-centered systems is paved with
  user-centered intentions" — and the framing of accidents as "a breakdown in coordination
  between the human and machine portions of a team" carry through every later paper in the
  strand.
- **Sarter and Woods (1995), "How in the world did we ever get into that mode?"**, *Human
  Factors* 37(1):5–19, [doi:10.1518/001872095779049516](https://doi.org/10.1518/001872095779049516);
  abstract only. Flexibility "has a price": the supervisor "must know more than before" and
  "satisfy new monitoring and attentional demands to track which mode the automation is in
  and what it is doing".
- **Sarter and Woods (1997), "Team play with a powerful and independent agent: operational
  experiences and automation surprises on the Airbus A-320"**, *Human Factors*
  39(4):553–569, [doi:10.1518/001872097778667997](https://doi.org/10.1518/001872097778667997);
  abstract only. A corpus of A-320 automation surprises and pilots' "monitoring strategies";
  n not in the abstract.
- **Sarter and Woods (2000), "Team play with a powerful and independent agent: a full-mission
  simulation study"**, *Human Factors* 42(3):390–402,
  [doi:10.1518/001872000779698178](https://doi.org/10.1518/001872000779698178); abstract
  only, numbers from the Klein et al. 2005 chapter below. "A lack of mode awareness is not
  simply a pilot problem; rather, it is a symptom of a coordination breakdown between humans
  and machines"; on the A-320 "mode errors and 'automation surprises' still occur", with
  "more opportunities for delayed or missing interventions with undesirable system
  activities, possibly because of higher system autonomy and coupling". Klein et al. report
  the altitude-constraint scenario: "4 of 18 experienced pilots never understood or noticed
  the automation's behavior and 12 of 14 who noticed at some point were unable to recover
  before the constraints were violated" (measured, simulator, n = 18).
- **Billings (1996), *Human-Centered Aviation Automation: Principles and Guidelines***, NASA
  Technical Memorandum; abstract only ([NTRS record via OpenAlex](https://openalex.org/W1497874644)).
  Problems "are related to automation complexity, autonomy, coupling, and opacity, or
  inadequate feedback to operators".

### Christoffersen and Woods 2002: observability and directability

**"How to make automated systems team players"**, in Salas (ed.), *Advances in Human
Performance and Cognitive Engineering Research* vol. 2, pp. 1–12, Elsevier 2002,
[doi:10.1016/S1479-3601(02)02003-9](https://doi.org/10.1016/S1479-3601(02)02003-9); read in
full from the Ohio State preprint ([Wayback](https://web.archive.org/web/20220125021917id_/http://csel.eng.ohio-state.edu/productions/xcta/downloads/automation_team_players.pdf)).
Argument from field research and incident analysis; no new data.

- **The substitution myth.** Automation fails when designers hold "an implicit belief …
  that automation activities simply can be substituted for human activities without
  otherwise affecting the operation of the system"; what is actually there is "a network of
  interdependent and mutually adapted activities and artifacts". "Adding or expanding the
  role of automation changes the nature of the" work.
- **Coordination, not level.** "The field research results are clear — the issue is not the
  level of autonomy or authority, but rather the degree of coordination." Increasing
  autonomy "create[s] the demand for greater coordination"; displays adequate for lower
  autonomy "are no longer sufficient". The answer "can be stated simply as — Cooperating
  automation is both observable and directable."
- **Observability.** A shared representation has two parts: "a shared representation of the
  problem state, and … representations of the activities of other agents." In open
  environments "this information … comes for free"; with automated team members "we have to
  actively design representations". "Data availability does not equal informativeness":
  early expert systems "'explained' their behavior by providing lists of the individual rules
  which had fired", and "the amount of cognitive work required to extract a useful,
  integrated assessment from such a representation was often prohibitive"; better was
  "access to the intermediate computations and partial conclusions". "Increases in the
  complexity and autonomy of machine agents requires a proportionate increase in the feedback
  they provide." Questions the paper lists for a representation to answer: "Is a problem proving
  especially difficult? Why? … which [tactics] have been tried? Why did they fail? What other
  options are being considered? How close is the automation to the limits of its
  competence?" New representations must be "event-based", "future-oriented" and
  "pattern-based" (citing Woods and Sarter 2000).
- **Directability: "Who owns the problem?"** "As long as some humans remain responsible for
  the outcomes, they must also be granted effective authority" (citing Billings 1996).
  All-or-nothing takeover "forces people to buy control of the problem at the price of the
  considerable computational power" of the automation; what is required are "intermediate,
  cooperative modes of interaction which allow human operators to focus the power of the
  automation on particular sub-problems, or to specify solution methods". "Automated agents
  need to be flexible and they need to be good at taking direction." The penalty for absent
  directability "tend[s] to accrue during those critical, rapidly deteriorating situations"
  when demands escalate. This "does not imply that automation work only as a passive
  adjunct"; micromanaging the machine is "a waste".
- **Organisational pattern.** "Advocates vigorously promote the claim that the more
  autonomous the machine, the less the required investment in team play"; "We have no need to
  witness or document more of these natural experiments in strong, silent, difficult to
  direct automation."

### Common ground and coordination in joint activity (Klein, Feltovich, Bradshaw and Woods 2005)

Chapter in Rouse and Boff (eds.), *Organizational Simulation*, Wiley 2005; read in full from
the June 2004 preprint on Bradshaw's site ([Wayback](https://web.archive.org/web/2024id_/https://www.jeffreymbradshaw.net/publications/Common_Ground_Single.pdf)),
marked "Do not quote or cite without permission of the authors" and "To appear". The preprint
presents six challenges for automation where the published IEEE piece (next section) presents
ten; the four requirements and the coordination-cost taxonomy are the same. Conceptual
analysis of three domains — relay races, driving in traffic, coaching football — plus
Clark's (1996) analysis of conversation, with anaesthesia, aviation and Army-exercise
examples; the reasons teams lose common ground are attributed to incident analyses (Klein,
Armstrong, Woods, Gokulachandra and Klein 2000, not obtained).

- **Definitions.** Joint activity is "an extended set of behaviors that are carried out by an
  ensemble of people who are coordinating with each other (Clark, 1996 p. 3)". Two criteria:
  "the parties have to intend to work together, and their work has to be interdependent" —
  "'It's not cooperation if either you do it all or I do it all.' (Woods, 2002)". Three
  requirements: "the team members have to be interpredictable, they have to have sufficient
  common ground, and they have to be able to redirect each other." The Basic Compact is "an
  agreement (often tacit) to facilitate coordination and prevent its breakdown", under which
  "all parties are expected to bear their portion of the responsibility to establish and
  sustain common ground and to repair it as needed".
- **Common ground, after Clark.** "Pertinent knowledge, beliefs and assumptions that are
  shared among the involved parties", in three categories: "initial common ground, public
  events so far, and the current state of the activity". Public events so far includes
  precedents "regarding how certain situations have been handled … who has been established
  as leader or follower"; "As we bring new people into an evolving situation we have to work
  out a range of issues about how they will come up to speed in the absence of their
  participation in the public events so far." Common ground "is not a binary or constant
  feature — it is both continuous in its degree and constantly changing over time".
- **Coordination devices (Clark 1996 pp. 64–66).** Agreement, convention, precedent, and
  salience — "how the ongoing work arranges the workspace so that next move becomes
  apparent"; salience "is likely to be the predominant mode of coordination among
  long-standing, highly practiced teams".
- **Coordination cost.** "The burden on joint action participants that is due to
  choreographing their efforts." Four types, attributed to Schaeffer (1997) and Klinger and
  Klein (1999): "synchronization overhead (time wasted in waiting for one entity to complete
  its work before the next one can begin); communication overhead (effort to manage the
  handoff); redirection overhead (wasted time and energy in going in the wrong direction after
  a new direction is called out but before all entities can be told to change course); and
  diagnosis overhead (the additional burden of diagnosing a performance problem when multiple
  moving parts are involved)". The relay illustration: four runners over 400 m, not 24,
  because "the coordination costs would outweigh advantages of the freshness and energy of
  each new runner". "As common ground is lost, coordination costs can rise"; but cutting
  signalling to save cost "increases the likelihood of a breakdown". No coordination cost is
  measured in the chapter.
- **The Fundamental Common Ground Breakdown.** "No matter how much care is taken, breakdowns
  in common ground are inevitable: no amount of procedure or documentation can totally
  prevent them." The baseline state "is one in which people are detecting and repairing
  problems with common ground — and not attempting to document all assumptions and duplicate
  the contents of each person's mind." Teams lose common ground because they "may lack
  experience in working together; … may have access to different data; … may not have a clear
  rationale for the directives presented by the leader; … may be ignorant of differences in
  stance (e.g., some may have higher workload and competing priorities); … may experience an
  unexpected loss of communications …; … may fail to monitor confirmation of messages and get
  confused over who knows what." The last is the Fundamental breakdown: "Person A assumes that
  person B knows item 'X,' whereas person B doesn't", the discrepancy grows as A "explain[s]
  away the initial anomalies", "until they encounter a coordination surprise".
- **Automation.** Sarter and Woods' altitude-constraint case "illustrates how a Fundamental
  Common Ground Breakdowns occur in human-automata interaction unless special measures are
  taken in design": the software "drops all of the altitude constraints", and "the only
  signal that these constraints have been dropped is through the disappearance of two
  indications". On attention: auditory
  automation-active warnings were "usually remove[d] … because the signal is a nuisance", and
  Sarter's tactile cues let "the human partner … stay peripherally aware of automation changes
  and to focus only on those that are unusual" (Sklar and Sarter 1999, not obtained). The
  chapter's closing warning: "Simply relying on explicit procedures, such as common operating
  pictures, is not likely to be sufficient."
- **Clark (1996), *Using Language***, Cambridge University Press,
  [doi:10.1017/CBO9780511620539](https://doi.org/10.1017/CBO9780511620539), and Clark and
  Brennan (1991), "Grounding in communication", APA, pp. 127–149,
  [doi:10.1037/10096-006](https://doi.org/10.1037/10096-006); metadata only. Their concepts are
  read here as Klein et al. quote and page-cite them.

### The ten challenges (Klein, Woods, Bradshaw, Hoffman and Feltovich 2004)

*IEEE Intelligent Systems* 19(6):91–95, November/December 2004,
[doi:10.1109/MIS.2004.74](https://doi.org/10.1109/MIS.2004.74); read in full from Bradshaw's
site ([Wayback](https://web.archive.org/web/2024id_/https://www.jeffreymbradshaw.net/publications/17._Team_Players.pdf_1.pdf)).
Position paper, "adapted from a more comprehensive examination of common ground and
coordination" (the chapter above). The four requirements: participants must "Enter into an
agreement, which we call a Basic Compact, that the participants intend to work together; Be
mutually predictable in their actions; Be mutually directable; Maintain common ground."
Directability is "the capacity for deliberately assessing and modifying other parties'
actions in a joint activity as conditions and priorities change". The challenges, in the
paper's words:

1. "To be a team player, an intelligent agent must fulfill the requirements of a Basic
   Compact to engage in common-grounding activities." Agents must "understand and accept
   their roles in the collaboration … and be capable of signaling if they're unable or
   unwilling to fully participate".
2. "To be an effective team player, intelligent agents must be able to adequately model the
   other participants' intentions and actions vis-à-vis the joint activity's state and
   evolution — for example, are they having trouble? Are they on a standard path proceeding
   smoothly? What impasses have arisen? How have others adapted to disruptions to the plan?"
3. "Human-agent team members must be mutually predictable." An agent "should act neither
   capriciously nor unobservably". "Ironically, by making agents more adaptable, we might
   also make them less predictable."
4. "Agents must be directable." "The nontransparent complexity and inadequate directability
   of agents can be a formula for disaster." Policies let people "precisely express bounds on
   autonomous behavior in a way that's consistent with their appraisal of an agent's
   competence in a given context".
5. "Agents must be able to make pertinent aspects of their status and intentions obvious to
   their teammates." Flight management systems "often leave commercial pilots baffled …
   wondering what the automation is currently doing, why it's doing that, and what it will
   do next". Agents "must make their own targets, states, capacities, intentions, changes, and
   upcoming actions obvious". "This challenge runs counter to the advice sometimes given to
   automation developers to create systems that are barely noticed."
6. "Agents must be able to observe and interpret pertinent signals of status and
   intentions." "Few existing agents are intended to read their operator teammates' signals
   with any degree of substantial understanding."
7. "Agents must be able to engage in goal negotiation." Planners that "produce output as if
   they can provide a complete plan" are "not compatible with what we know about optimal
   coordination".
8. "Support technologies for planning and autonomy must enable a collaborative approach."
   "Understanding, problem solving, and task execution are necessarily incremental, subject
   to negotiation, and forever tentative."
9. "Agents must be able to participate in managing attention." Automation "can compensate
   for trouble … but currently does so invisibly"; crews "take over too late or [are]
   unprepared … resulting in a bumpy transfer of control". "Rigid and context-insensitive
   thresholds will typically be crossed too early (resulting in an agent that speaks up too
   often, too soon) or too late". Open question: "How and when does an agent effectively
   reveal or communicate that it's moving toward its limit of capability?"
10. "All team members must help control the costs of coordinated activity." "Coordination
    doesn't come for free, and coordination, once achieved, doesn't allow us to stop
    investing." Keeping cost down is "partly, but only partly, a matter of good
    human-computer interface design. More than that, the agents must conform to the operators'
    needs rather than require operators to adapt to them."

The authors offer the list "as a blueprint for designing and evaluating intelligent systems"
and close by imagining agents as "fellow team members with humans in the way a young child or
a novice can be — subject to the consequences of brittle and literal-minded interpretation of
language and events … poor anticipation, and insensitivity to nuance." "No form of automation
today or on the horizon can enter fully into the rich forms of Basic Compact that are used
among people." Argument; no data.

### The seven deadly myths (Bradshaw, Hoffman, Johnson and Woods 2013)

*IEEE Intelligent Systems* 28(3):54–61, May/June 2013,
[doi:10.1109/MIS.2013.70](https://doi.org/10.1109/MIS.2013.70); read in full from Bradshaw's
site ([Wayback](https://web.archive.org/web/20260511062134id_/https://www.jeffreymbradshaw.net/publications/IS-28-03-HCC_1.pdf)).
Position paper drawing on the 2012 Defense Science Board autonomy report. The myths as stated:
(1) "'Autonomy' is unidimensional"; (2) "The conceptualization of 'levels of autonomy' is a
useful scientific grounding for the development of autonomous system roadmaps"; (3) "Autonomy
is a widget"; (4) "Autonomous systems are autonomous"; (5) "Once achieved, full autonomy
obviates the need for human-machine collaboration"; (6) "As machines acquire more autonomy,
they will work as simple substitutes (or multipliers) of human capability"; (7) "'Full
autonomy' is not only possible, but is always desirable."

- Against myth 1 the paper proposes two dimensions, self-directedness and self-sufficiency,
  and a Figure 1 whose corners are "Over-trust", "Burden", "Underreliance" and "Not well
  understood"; "Whether human or machine, a 'team player' must be able to observe,
  understand, and predict the state and actions of others." "The problem with what David
  Woods calls 'strong silent automation' is that it fails to communicate effectively those
  things that would allow humans to work interdependently with it"; "there's nothing worse
  than a so-called smart machine that can't tell you what it's doing, why it's doing
  something, or when it will finish. Even more frustrating — or dangerous — is a machine
  that's incapable of responding to human direction when something (inevitably) goes wrong."
- Against levels of automation (myth 2): "levels aren't consistently ordinal"; "autonomy is
  relative to the context of activity"; the levels notion "reinforces the erroneous notion
  that 'automation activities simply can be substituted for human activities'" (the levels
  literature is in [adjacent-literatures.md](adjacent-literatures.md#levels-of-automation-and-supervisory-control)).
- Myth 6: "help of whatever kind doesn't simply enhance our ability to perform the task: it
  changes the nature of the task"; poorly designed autonomy yields "clumsy automation", and
  adding more is "adding more clumsy automation onto clumsy automation".
- Table 1, "Putative benefits of automation versus actual experience", eight rows. Putative
  "Frees up human by offloading work to the machine" versus "Creates new kinds of cognitive
  work for the human, often at the wrong times; every automation advance will be exploited to
  require people to do more, do it faster, or in more complex ways — the law of stretched
  systems." Putative "Frees up limited attention by focusing someone on the correct answer"
  versus "Creates more threads to track; makes it harder for people to remain aware of and
  integrate all of the activities and changes around them — with coordination costs,
  continuously." Putative "Less human knowledge is required" versus "New knowledge and skill
  demands are imposed on the human and the human might no longer have a sufficient context to
  make decisions, because they have been left out of the loop — automation surprise."
  Putative "Same feedback to human will be required" versus "New levels and types of feedback
  are needed to support peoples' new roles — with coordination costs, continuously." Putative
  "Agent will function autonomously" versus "Team play with people and other agents is
  critical to success — principles of interdependence." The law of stretched systems is quoted
  from Woods and Hollnagel: "every system is stretched to operate at its capacity; as soon as
  there is some improvement, for example in the form of new technology, it will be exploited
  to achieve a new intensity and tempo of activity."
- **Hoffman, Hawley and Bradshaw (2014), "Myths of automation, part 2: some very human
  consequences"**, *IEEE Intelligent Systems* 29(2):82–85,
  [doi:10.1109/MIS.2014.25](https://doi.org/10.1109/MIS.2014.25); read in full from Bradshaw's
  site ([Wayback](https://web.archive.org/web/20220724174244id_/https://jeffreymbradshaw.net/publications/Hoffman-Hawley-54.%20Myths%20of%20Automation%20Part%202.pdf)).
  Case analysis of the 2003 Patriot fratricides: "Of these 11 [engagements], nine resulted in
  successful tactical ballistic missile engagements; the other two were fratricides", with
  three aircrew killed, attributed to automation-shaped crew roles rather than operator error.
- **Woods and Hollnagel (2006), *Joint Cognitive Systems: Patterns***, CRC Press,
  [doi:10.1201/9781420005684](https://doi.org/10.1201/9781420005684), and **Hollnagel and Woods
  (2005), *Joint Cognitive Systems: Foundations***, [doi:10.1201/9781420038194](https://doi.org/10.1201/9781420038194);
  metadata only; reached here only as quoted by Bradshaw et al. 2013 (the law of stretched
  systems) and Christoffersen and Woods 2002.

### Coactive Design (Johnson, Bradshaw, Feltovich, Jonker, van Riemsdijk and Sierhuis 2014)

**"Coactive Design: designing support for interdependence in joint activity"**, *Journal of
Human-Robot Interaction* 3(1):43–69, [doi:10.5898/JHRI.3.1.Johnson](https://doi.org/10.5898/JHRI.3.1.Johnson);
read in full from the TU Delft repository copy ([record](https://repository.tudelft.nl/record/uuid:35cfe91a-bd59-427d-89a9-e2019f9b0c28)).
Method paper with one competition case; the numbers are the team's own instrumentation of
its own runs.

- **Interdependence, hard and soft.** "Much of the robotics work today is about required
  (i.e., hard) interdependence relationships that stem from lack of capacity"; soft
  interdependence "arises from recognizing opportunities to be more effective, more
  efficient, or more robust by working jointly" — "progress appraisals ('I'm running late'),
  warnings ('Watch your step'), helpful adjuncts …, and observations about relevant unexpected
  events ('It has started to rain')". "Good teams can often be distinguished from great ones
  by how well they manage soft interdependencies."
- **OPD as requirements.** "Observability means making pertinent aspects of one's status, as
  well as one's knowledge of the team, task, and environment observable to others … [and]
  the ability to observe and interpret pertinent signals" (mapped to challenges 5, 6 and 9).
  "Predictability means one's actions should be predictable enough that others can reasonably
  rely on them when considering their own actions" (challenges 1, 2, 3). "Directability means
  one's ability to direct the behavior of others and complementarily be directed by others",
  including "explicit commands such as task allocation and role assignment as well as subtler
  influences, such as providing guidance or suggestions or even providing salient information
  that is anticipated to alter behavior, such as a warning" (challenges 4 and 7; the 2004
  paper "is only described as agents being directable and does not include the complement").
  "The goal of a designer is not to maximize or minimize OPD. It is to attain sufficient OPD to
  support the necessary interdependent relationships"; "it is not just about what information
  you share, but also about what you do not share." Footnote 5: challenge 10, controlling the
  costs of joint activity, "is not directly addressed in this paper".
- **Interdependence analysis.** A table listing, per subtask, which party could perform it
  and which could support it, colour-coded for reliability and capacity; OPD requirements are
  read off the supporting relationships the designer chooses to keep: if the human is to judge
  whether an obstacle is passable, there is an observability requirement (the human must see
  the obstacle), a directability requirement (the judgment must alter the robot's behaviour)
  and "a predictability requirement that the robot will notify the human when assistance is
  needed before proceeding".
- **DARPA Virtual Robotics Challenge, 2013.** "After initial entries from 1268 potential
  competitors, 26 teams from eight countries qualified"; three tasks, 30 minutes per attempt,
  "a minimum 500ms of network latency". IHMC placed first (score 52; WPI second at 39). In the
  five hose-task runs "87 percent [of commands] were issued through the third-person view"
  and the virtual-arm manipulable "was used in 99% of all arm commands". Scripting: a fully
  automated grasp script "eliminated any potential support for interdependence" and was "too
  brittle";
  step-by-step playback with visuals made "the upcoming action observable and predictable"
  but "failure meant aborting the process and rescripting"; adding directability — modify,
  replay or skip a step — gave "a flexible and resilient" result: "an average of 10 scripts
  were used per run. Only 50 percent of these were run without intervention. We averaged nine
  pauses in script behavior to verify performance and seven operator corrections to scripted
  actions per run. Even with operator intervention, 8 of the 50 scripts failed to accomplish
  their purpose. Due to the flexibility in our system to retry, make adjustments, and use
  different approaches, we were successful in recovering from all eight failures."

## Human–autonomy teaming, 2017–2022

### Definitions and the automation–autonomy distinction

- **Lyons, Sycara, Lewis and Capiola (2021), "Human–autonomy teaming: definitions, debates,
  and directions"**, *Frontiers in Psychology* 12:589585,
  [doi:10.3389/fpsyg.2021.589585](https://doi.org/10.3389/fpsyg.2021.589585); read in full.
  Narrative review. "To the extent the machines' actions can be precisely predicted, a social
  context may not be needed"; "the distinction between automation and autonomy lies in the
  eye of the human beholder." It adopts McNeese et al.'s definition — "autonomy is a
  technology that is capable of working with humans as teammates to include the essential
  task work and teamwork function of a human teammate" — and states that HATs "require
  intent information, shared mental models, and social affordances". It reports Chien et al.
  (2020): "compliance doubled when participants were shown why a path planner wanted to
  re-route a UAV" (secondary here). Research gaps listed include "the capability of the agent
  to communicate its intent" and "how do we establish shared accountability within the
  context of a HAT?"
- **Salas, Sims and Burke (2005), "Is there a 'Big Five' in teamwork?"**, *Small Group
  Research* 36(5):555–599, [doi:10.1177/1046496405277134](https://doi.org/10.1177/1046496405277134);
  abstract only. Five components — "team leadership, mutual performance monitoring, backup
  behavior, adaptability, and team orientation" — with "coordinating mechanisms (e.g., shared
  mental modes [sic], closed-loop communication, and mutual trust)"; carried into HAT by Lyons
  et al. and O'Neill et al.

### What the empirical HAT literature measured (O'Neill, McNeese, Barron and Schelble 2022)

**"Human–autonomy teaming: a review and analysis of the empirical literature"**, *Human
Factors* 64(5):904–938, [doi:10.1177/0018720820960865](https://doi.org/10.1177/0018720820960865);
read in full from PubMed Central ([PMC9284085](https://pmc.ncbi.nlm.nih.gov/articles/PMC9284085/)).
Systematic review; 1,942 initial returns filtered to 476 containing "team", 33 meeting
criteria, plus 31 from author searches (Bradshaw was the most frequent author in the 476,
with 15) and eight more, for 76 articles; 30% double-coded with 89% inter-coder agreement.

- "All articles that met criteria for inclusion were simulation and not field-based"; "the
  overwhelming majority of articles were military- or emergency-related simulations (n =
  57)", 17 non-military, two unclassifiable.
- Themes, as tabulated: "Higher levels of agent autonomy generally have positive effects …
  although a moderate level was ideal in a few studies"; "Transparency has mixed effects. It
  leads to favorable outcomes with respect to performance, perceptions of the autonomous
  agent, perceived time pressure, and use of the autonomous agent. However, it can lead to
  negative outcomes such as complacency, conflict, and workload"; "Reliability is positively
  associated with all outcomes"; "transparency reduces the negative effects of lower levels of
  reliability"; "Human–human teams generally had better outcomes than did HATs"; "The role of
  information sharing differences among human–human and HATs appears fundamental";
  "Increasing human–autonomous agent outcome interdependence led to all positive outcomes";
  "Training humans with agent autonomy produced consistently positive results including
  increased mental model similarity, trust, and lower uncertainty"; "The quality of
  communication is associated with stronger team functioning" while "Findings for
  communication quantity were mixed". Transparency is defined as "the extent to which it
  communicates only its current status (low transparency) versus its reasoning processes, how
  it projects future" states.

### The synthetic teammate: coordination measured

- **McNeese, Demir, Cooke and Myers (2018), "Teaming with a synthetic teammate: insights into
  human-autonomy teaming"**, *Human Factors* 60(2):262–273,
  [doi:10.1177/0018720817743223](https://doi.org/10.1177/0018720817743223); structured abstract
  (Crossref). Three-person unmanned-aerial-system teams: "(1) synthetic teams in which the
  pilot role is assigned to a synthetic teammate, (2) control teams in which the pilot was an
  inexperienced human, and (3) experimenter teams in which an experimenter served as an
  experienced pilot. Ten of each type of team participated." "Synthetic teams performed as well
  at the mission level as control (all human) teams but processed targets less efficiently.
  Experimenter teams performed better across all other measures." Measured; lab; 30 teams.
- **Demir, McNeese, Cooke and colleagues (2019), "The evolution of human-autonomy teams in
  remotely piloted aircraft systems operations"**, *Frontiers in Communication* 4:50,
  [doi:10.3389/fcomm.2019.00050](https://doi.org/10.3389/fcomm.2019.00050); read in full.
  Summary of three experiments (10 teams per condition; ten 40-minute missions in the last),
  coding communications as "pushing or pulling of information" and applying joint recurrence
  quantification to communication flow. "Synthetic teams pulled more information than they
  pushed, and pushing information was not as effective for their performance as the all-human
  teams"; "behavioral passiveness of the synthetic teams resulted in very stable and rigid
  coordination in comparison to the all-human teams"; experimenter teams "demonstrated
  metastable coordination (not rigid nor unstable) and performed better". The named mechanism
  is entrainment: "one team member (the pilot in our study, either agent or human) can change
  the communication behaviors of the other teammates over time". Its recommendation is
  "Developing mechanisms to enhance the pushing of information" by the agent. This is the
  strand's challenge 9 (attention management, the agent must "speak up") measured as a
  communication-flow statistic.

### Transparency models and the National Academies report

- **Chen, Lakhmani, Stowers, Selkowitz, Wright and Barnes (2018), "Situation awareness-based
  agent transparency and human-autonomy teaming effectiveness"**, *Theoretical Issues in
  Ergonomics Science* 19(3):259–282, [doi:10.1080/1463922X.2017.1315750](https://doi.org/10.1080/1463922X.2017.1315750);
  abstract only. The SAT model's three levels — "the agent's current actions and plans (Level
  1), its reasoning process (Level 2), and its projection of future outcomes (Level 3)" (from
  the 2017 SPIE abstract, [doi:10.1117/12.2263194](https://doi.org/10.1117/12.2263194)) — are
  Endsley's levels of situation awareness (see
  [adjacent-literatures.md](adjacent-literatures.md#situation-awareness-and-the-out-of-the-loop-problem))
  applied to what the agent discloses; the 2018 paper extends it to "bidirectional
  transparency". The SPIE abstract claims performance "improved as the agents became more
  transparent" across three programmes; O'Neill et al. read the same literature as "mixed".
- **National Academies of Sciences, Engineering, and Medicine (2022), *Human-AI Teaming:
  State-of-the-Art and Research Needs***, National Academies Press,
  [doi:10.17226/26355](https://doi.org/10.17226/26355); summary chapter read online
  ([chapter 2](https://nap.nationalacademies.org/read/26355/chapter/2)). Consensus report for
  the US Air Force, "57 research objectives" over near, mid and far term. "Supporting humans
  and AI systems as teammates relies on a carefully designed system with the capability for
  both taskwork and teamwork"; "Real-time transparency is critical for supporting
  understanding and predictability of AI systems and has been found to significantly
  compensate for out-of-the-loop performance deficits"; research is needed "to define when
  such information should be provided to meet SA needs without overloading the human"; and
  study is needed "to understand the effect of AI directability on the trust relationship".
  Policy text; the observability and directability vocabulary is the strand's.

## The AI-teammate literature, 2019–2026

### Human–AI team performance and mental models

- **Bansal, Nushi, Kamar, Lasecki, Weld and Horvitz (2019), "Beyond accuracy: the role of
  mental models in human-AI team performance"**, *Proceedings of the AAAI Conference on Human
  Computation and Crowdsourcing* 7:2–11, [doi:10.1609/hcomp.v7i1.5285](https://doi.org/10.1609/hcomp.v7i1.5285);
  read in full. The factor studied is "the human's mental model of the AI capabilities,
  specifically the AI system's error boundary (i.e. knowing 'When does the AI err?')". Two
  properties of the boundary, parsimony and non-stochasticity, and one of the task,
  dimensionality, "affect humans' mental models of AI capabilities and the resulting team
  performance". Amazon Mechanical Turk, "For every condition we hired 25 workers". The paper
  cites Lee and See (2004) on trust but none of the joint-activity sources; its "team" is one
  human advised by one classifier.
- **Bansal, Nushi, Kamar, Horvitz, Weld (2019), "Updates in human-AI teams"**, *AAAI*
  33(1):2429–2437, [doi:10.1609/aaai.v33i01.33012429](https://doi.org/10.1609/aaai.v33i01.33012429);
  abstract only. "Updates that increase AI performance may actually hurt team performance"
  when they are incompatible with "the user's prior experiences and confidence in the AI's
  inferences" — the strand's challenge 3 (adaptation reduces predictability) with a
  measurement on three classification tasks.
- **Bansal, Wu, Zhou, Fok, Nushi, Kamar, Ribeiro and Weld (2021), "Does the whole exceed its
  parts?"**, *CHI 2021*, [arXiv:2006.14779](https://arxiv.org/abs/2006.14779); abstract only.
  With an AI "with accuracy comparable to humans", "complementary improvements from AI
  augmentation … were not increased by explanations. Rather, explanations increased the chance
  that humans will accept the AI's recommendation, regardless of its correctness." A null for
  explanation as observability, consistent with O'Neill et al.'s "transparency has mixed
  effects".
- **Zhang, McNeese, Freeman and Musick (2021), "'An ideal human': expectations of AI
  teammates in human-AI teaming"**, *PACM HCI* 4(CSCW3):1–25,
  [doi:10.1145/3432945](https://doi.org/10.1145/3432945); abstract only (ACM 403). Survey of 213
  and interviews with 20, in multiplayer online games; expectations include "shared
  understanding between humans and AI, communication capabilities, human-like behaviors and
  performance". Self-report; games, not work.

### Design guidelines: Amershi 2019 and Weisz 2024

- **Amershi et al. (2019), "Guidelines for human-AI interaction"**, *CHI 2019*, pp. 1–13,
  [doi:10.1145/3290605.3300233](https://doi.org/10.1145/3290605.3300233); read in full from the
  camera-ready ([Wayback](https://web.archive.org/web/20250130135417id_/https://www.microsoft.com/en-us/research/uploads/prod/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf)).
  Eighteen guidelines "validated through … a user study with 49 design practitioners who
  tested the guidelines against 20 popular AI-infused products". Those that state
  observability or directability concretely:
  G1 "Make clear what the system can do"; G2 "Make clear how well the system can do what it
  can do"; G3 "Time services based on context … when to act or interrupt"; G7 "Support
  efficient invocation"; G8 "Support efficient dismissal"; G9 "Support efficient correction …
  edit, refine, or recover when the AI system is wrong"; G10 "Scope services when in doubt";
  G11 "Make clear why the system did what it did"; G14 "Update and adapt cautiously"; G16
  "Convey the consequences of user actions"; G17 "Provide global controls"; G18 "Notify users
  about changes". The lineage the paper claims is Norman, Höök and Horvitz's mixed-initiative
  principles; it does not cite Klein, Woods, Sarter or Bradshaw.
- **Weisz, He, Muller, Hoefer, Miles and Geyer (2024), "Design principles for generative AI
  applications"**, *CHI 2024*, [arXiv:2401.14484](https://arxiv.org/abs/2401.14484); HTML
  read. Six principles — design responsibly, design for mental models, design for appropriate
  trust and reliance, design for generative variability, design for co-creation, design for
  imperfection — motivated by "the control that users have lost over the computational
  process". Strategies under co-creation: "Help the user craft effective outcome
  specifications", "Provide generic input parameters", "Provide controls relevant to the use
  case & technology", "Support co-editing of generated outputs"; under trust: "Calibrate trust
  using explanations", "Provide rationales for outputs", "Use friction to avoid overreliance …
  mechanisms that slow them down at key decision-making points"; under mental models: "Orient
  the user to generative variability", "Teach effective use". The paper builds on Amershi et
  al., remarking that G11 "is potentially less important when a user's goal is to simply
  generate a desirable artifact"; developed through literature review, practitioner feedback
  and two applications. No joint-activity citation.

### The "AI pair programmer" framing and its critics

- **GitHub, "Introducing GitHub Copilot: your AI pair programmer"**, Nat Friedman, 2021-06-29
  ([blog](https://github.blog/2021-06-29-introducing-github-copilot-ai-pair-programmer/));
  read. "A new AI pair programmer that helps you write better code." Vendor framing.
- **Bird, Ford, Zimmermann, Forsgren, Kalliamvakou, Lowdermilk and Gazit (2022), "Taking
  flight with Copilot"**, *ACM Queue* 20(6):35–57, [doi:10.1145/3582083](https://doi.org/10.1145/3582083);
  read via Wayback ([capture](https://web.archive.org/web/20251125083726id_/https://queue.acm.org/detail.cfm?id=3582083)).
  Adopts the framing: "the emergence of new AI-powered tools to support programmers has
  shifted what it means to pair program"; the technical-preview case study reports
  experiences from "enjoyment, guilt, skepticism" to "clarity on how to interact with the
  tool". Vendor-authored qualitative study.
- **Imai (2022), "Is GitHub Copilot a substitute for human pair-programming? An empirical
  study"**, *ICSE 2022 Companion*, pp. 319–321, [doi:10.1145/3510454.3522684](https://doi.org/10.1145/3510454.3522684);
  abstract (Semantic Scholar). "An experiment with 21 participants" under three conditions —
  Copilot, human pair as driver, human pair as navigator: "although Copilot increases
  productivity as measured by lines of code added, the quality of code produced is inferior by
  having more lines of code deleted in the subsequent trial." Measured; small.
- **Sarkar et al. (2022), "What is it like to program with artificial intelligence?"**, *PPIG
  2022*, [arXiv:2208.06213](https://arxiv.org/abs/2208.06213); abstract page read, and already
  cited in [track-in-loop-friction.md](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking).
  "LLM-assisted programming shares some properties of compilation, pair programming, and
  programming via search and reuse, [but] there are fundamental differences"; it "ought to be
  viewed as a new way of programming". Argument from experience reports.
- **Ma, Wu and Koedinger (2023), "Is AI the better programming partner? Human-human pair
  programming vs. human-AI pAIr programming"**, [arXiv:2306.05153](https://arxiv.org/abs/2306.05153);
  abstract page read. A literature comparison: "the effectiveness of both approaches is mixed
  in the literature (though the measures used for pAIr programming are not as
  comprehensive)". Review, not data; the human pair-programming evidence is in
  [unfamiliar-code-and-shared-models.md](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model).

None of these sources measures coordination cost; the pair-programming framing is asserted by
the vendor, adopted by the vendor's researchers, and questioned by Sarkar et al. and Ma et al.
on interaction properties rather than on the joint-activity criteria.

### AI agents as teammates in field experiments outside code

- **Dell'Acqua, Ayoubi, Lifshitz, Sadun, Mollick, Mollick and colleagues (2025), "The
  cybernetic teammate: a field experiment on generative AI reshaping teamwork and
  expertise"**, NBER Working Paper 33641, [doi:10.3386/w33641](https://doi.org/10.3386/w33641);
  abstract only. Pre-registered field experiment "with 776 professionals at Procter & Gamble"
  on "real product innovation challenges", randomised to with or without AI and to individual
  or pair: "individuals with AI matched the performance of teams without AI"; AI "breaks down
  functional silos" (R&D and commercial professionals produced balanced proposals); AI
  "prompted more positive self-reported emotional responses", "suggesting it can fulfill part
  of the social and motivational role traditionally offered by human teammates". Measured;
  outcome is rated proposal quality, not coordination.
- **Ju and Aral (2025), "Collaborating with AI agents: field experiments on teamwork,
  productivity, and performance"**, [arXiv:2503.18238](https://arxiv.org/abs/2503.18238);
  abstract page read. "2,234 participants" randomised to human–human and human–AI teams
  producing "11,024 ads"; "human-AI teams produced 50% more ads per worker"; "human-AI
  collaboration was more task-oriented, with 25% more task-oriented messages and 18% fewer
  interpersonal messages"; participants "delegated 17% more work to AI agents than to human
  partners and performed 62% fewer direct text edits". The one experiment found that measures
  how an AI teammate changes the human's coordination behaviour (message mix, delegation,
  editing); the domain is advertising copy.

### Coding agents as teammates, 2025–2026

- **Li, Zhang and Hassan (2025), "The rise of AI teammates in software engineering (SE) 3.0"**,
  [arXiv:2507.15003](https://arxiv.org/abs/2507.15003); abstract page read. Introduces the
  AIDev dataset — "over 456,000 pull requests by five leading agents — OpenAI Codex, Devin,
  GitHub Copilot, Cursor, and Claude Code — across 61,000 repositories and 47,000 developers"
  — under the "AI teammates" framing. "Although agents often outperform humans in speed, their
  PRs are accepted less frequently, revealing a trust and utility gap". The AIDev-based studies
  already in the corpus (Watanabe et al., Duma et al.) are in
  [literature-addendum.md](literature-addendum.md#target-3-human-evaluations-of-generated-wikis-maps-and-tours-accuracy-of-generated-documentation).
- **Hassan, Li, Lin, Adams, Chen, Kashiwa and Qiu (2025), "Agentic software engineering:
  foundational pillars and a research roadmap"**, [arXiv:2509.06216](https://arxiv.org/abs/2509.06216);
  read in full from the author copy the chat-centric note cites. Beyond the 1-to-N / N-to-N
  distinction recorded in
  [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#single-developer-orchestration-is-not-team-level-engineering),
  its section "The critical gap: observability, archival, and revision control" states that
  CLI agents "often result in ephemeral interactions … lost today, existing only in a
  terminal's scroll-back buffer"; that PR-anchored platforms "treat the agent mentoring and
  the code as separate, unlinked artifacts"; and that "no mainstream system today provides
  adequate observability into the agent's internal state". Its vision has agents "become
  persistent teammates with memory, observability, and secure, hermetic execution". The word
  "observability" is used in the software-telemetry sense; Klein, Woods, Christoffersen and
  Bradshaw are not cited.
- **Nachuma and Zibran (2026), "When AI teammates meet code review: collaboration signals
  shaping the integration of agent-authored pull requests"**, *MSR 2026*,
  [arXiv:2602.19441](https://arxiv.org/abs/2602.19441); HTML read. AIDev's curated subset:
  "33,596 agent-authored PRs submitted by 1,797 distinct developers across 2,807
  repositories" with at least 100 stars. Outcomes: "71.5% were merged, 21.6% were closed
  without merge, and 6.9% remained open"; by agent, Codex 82.6%, Devin 53.8%, Copilot 43.0%.
  Logistic regression with repository-clustered errors:
  "receiving at least one review is the strongest correlate of merging"; "Force pushes during
  review are consistently associated with lower merge likelihood; … history rewriting during
  active review can disrupt shared understanding and increase coordination costs for
  reviewers"; "Larger changes are less likely to be merged even after controlling for agent
  identity and reviewer engagement"; "Neither iteration intensity nor test additions are
  significantly associated with merge outcomes once reviewer engagement and coordination
  stability are accounted for". Qualitative sample of 60 PRs: "actionable review loop" was the
  primary driver in 32 (30 merged), "design disagreement" in 10 (0 merged). Synthesis:
  "reviewers reward agent behaviors that reduce coordination cost and penalize those that
  disrupt shared understanding"; comparison with human-authored PRs is left to future work.
  Correlational mining; the coordination cost is inferred from merge outcomes, not measured.
- **Khatua, Zhu, Tran, Prabhudesai, Sadrieh, Lieberwirth, Yu, Fu et al. (2026), "CooperBench:
  why coding agents cannot be your teammates yet"**, [arXiv:2601.13295](https://arxiv.org/abs/2601.13295);
  HTML read. "652 tasks constructed from 12 popular open-source libraries across Python,
  TypeScript, Go, and Rust", each assigning two agents features that "may conflict without
  proper coordination" ("77.3% of tasks have conflicting ground-truth solutions"); agents work
  in isolated workspaces and coordinate only in natural language. "The curse of
  coordination: agents achieve on average 30% lower
  success rates when working together compared to performing both tasks individually"; leading
  models "achieve only 25% with two-agent cooperation …, which is around 50% lower than a
  'Solo' baseline"; pooled retention 0.59, "41% of Solo capability is lost when agents must
  coordinate"; scaling from 2 to 4 agents on 46 tasks shows "a monotonic decline". "Agents
  spent as much as 20% of the steps in communication"; sending "a message in the very first
  turn nearly halves the conflict rate (29.4% vs 51.5%)". Three failure classes: channels
  "jammed with vague, ill-timed, and inaccurate messages"; agents "deviate from their
  commitments"; agents "hold incorrect expectations about others' plans" — the Basic Compact,
  predictability and common-ground failures of the 2004 list, on agent–agent pairs. The paper
  uses "common ground" without citing Clark. Benchmark; the LLM annotator agreed with human
  experts on 48 of 50 sampled trajectories.
- **KC and Budathoki (2026), "Handoff debt: the rediscovery cost when coding agents take over
  interrupted tasks"**, [arXiv:2606.02875](https://arxiv.org/abs/2606.02875); abstract page
  read. A takeover protocol interrupts an agent at deterministic points and evaluates
  successors under four views — "repository state only, raw trace, summary notes, and
  structured notes"; "Across 75 source tasks, the protocol generates 181 handoff-point tasks
  and 724 takeover runs per successor model. Across three successor models, context-bearing
  handoffs reduce median agent events by 20-59% and cumulative prompt tokens by 42-63%
  relative to repository-only takeover. Solved-rate effects are smaller and model-dependent."
  This is Klein et al.'s "public events so far" — the cost of coming "up to speed in the
  absence of their participation" — measured for an agent successor; no human successor is
  studied.
- **Tang, Chen, Xu, Shi, Huang, McMillan, Dong and Li (2026), "How coding agents fail their
  users: a large-scale analysis of developer-agent misalignment in 20,574 real-world
  sessions"**, [arXiv:2605.29442](https://arxiv.org/abs/2605.29442); HTML read. Sessions
  "from 1,639 repositories across IDE and CLI workflows", from developers "who use SpecStory
  or Entire.io and opt into public logging" (stated selection bias); 16,118 validated
  episodes annotated by an LLM judge (GPT-5.4) with human agreement checked on 100. Seven
  forms: "Developer Constraint Violation (S3, 38.33%)", "Misread Developer Intent (S2,
  26.95%)", "Inaccurate Self-Reporting (S7, 22.58%)", "Faulty Implementation (S5, 17.82%)",
  and three smaller. S7 "occurs when the agent misreports its work by prematurely claiming
  success, completion, or readiness"; "90.50% of episodes impose effort and trust costs rather
  than irreversible system damage, yet 91.49% of visible resolutions still require explicit
  user correction"; over February 2025 to April 2026 "the overall misalignment rate per user
  turn declines significantly" while "the daily shares of S3 … and S7 … rise". S7 is the
  strand's challenge 5 failing — status and intentions not made obvious — measured as a share
  of developer pushback episodes.
- **Shukla, Feng, Wang, Rostami and Zhang (2026), "Hedwig: dynamic autonomy for coding agents
  under local oversight"**, *ACM CAIS 2026 demo*, [arXiv:2605.11495](https://arxiv.org/abs/2605.11495);
  abstract page read. "A formative survey with 21 software engineers who use coding agents …
  found that they experience frustration with calibrating autonomy and have evolving
  preferences for level of oversight"; the tool "learns an evolving set of behavioral
  guidelines from developer decisions and feedback". Demo, no evaluation.
- **Stokel-Walker (2026), "AI-coding agents kill team collaboration"**, *LeadDev*, 2026-07-28
  ([article](https://leaddev.com/ai/ai-coding-agents-kill-team-collaboration)); read.
  Practitioner journalism restating Raida and Hou: agents "are often cast by their makers as
  new teammates"; "in 79% of agentic PRs, the same developer both reviewed and modified the
  AI's contribution". Secondary; the primary figures are in
  [chat-centric-agents-vs-team-sdlc.md](chat-centric-agents-vs-team-sdlc.md#bottom-line).

### Does the AI-era literature cite the strand?

Checked by full-text search of the copies read here. Amershi et al. 2019: Norman, Höök and
Horvitz, no Klein/Woods/Sarter/Bradshaw. Weisz et al. 2024: Amershi and the HCI co-creation
literature, none of the strand. Bansal et al. 2019: Lee and See 2004 on trust, none of the
strand. CooperBench 2026: "common ground" without Clark or Klein. Hassan et al. 2025:
"observability" and "persistent teammates" without the strand. Nachuma and Zibran 2026:
"coordination cost" and "shared understanding" without the strand. O'Neill et al. 2022, by
contrast, found Bradshaw the most frequent author in its 476-article pool, and Johnson et al.
2014 map every OPD element to a numbered 2004 challenge. The two literatures share vocabulary
and do not share references; this extends the pattern the adjacent-literatures note records
for Bainbridge ([mapping](adjacent-literatures.md#mapping-to-the-existing-notes)).

## Mapping to the existing notes

| Finding | Primary source | Evidence type | Where the existing notes touch it |
| --- | --- | --- | --- |
| The design target is coordination, not a level of autonomy; "cooperating automation is both observable and directable" | Christoffersen and Woods 2002 | Argument from field studies | [adjacent, levels of automation](adjacent-literatures.md#levels-of-automation-and-supervisory-control) (Sheridan–Verplank levels; the mode tables); [in-loop friction, modes](track-in-loop-friction.md#existing-modes-and-tools) |
| "Data availability does not equal informativeness": rule traces are not observability; representations must be event-based, future-oriented, pattern-based | Christoffersen and Woods 2002 | Argument | [rationale, transcript retention](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance) (transcripts as records, not representations); no counterpart for representation design |
| Directability means intermediate modes, not all-or-nothing takeover; "who owns the problem" follows responsibility | Christoffersen and Woods 2002; Billings 1996 | Argument | [in-loop friction, vendor guidance](track-in-loop-friction.md#what-the-vendors-say-about-when-to-use-the-gates); [chat-centric, accountability versus execution](chat-centric-agents-vs-team-sdlc.md#2-attach-sessions-to-the-teams-existing-work-graph) |
| Automation surprises: ~55% of B-757 pilots still surprised after a year; miscalibrated self-assessed understanding; 4 of 18 pilots never noticed dropped constraints, 12 of 14 who did could not recover | Sarter, Woods and Billings 1997; Sarter and Woods 2000 | Survey; simulator, n = 18 | [adjacent, situation awareness](adjacent-literatures.md#situation-awareness-and-the-out-of-the-loop-problem); [adjacent, complacency](adjacent-literatures.md#use-misuse-disuse-abuse-complacency-and-automation-bias) (Skitka's automation bias); no counterpart for mode awareness |
| Four requirements of joint activity (Basic Compact, predictability, directability, common ground) and ten challenges, listed | Klein et al. 2004 | Position paper | No counterpart |
| Coordination cost defined; four overheads (synchronization, communication, redirection, diagnosis); cost rises as common ground falls; not measured | Klein et al. 2005 | Conceptual analysis | [in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking) (interruption cost, Mark et al.); no counterpart for coordination cost |
| Common ground in three parts; "public events so far" and the newcomer's problem; precedent and salience as coordination devices | Klein et al. 2005; Clark 1996 | Conceptual analysis | [unfamiliar code, Naur](unfamiliar-code-and-shared-models.md#naur-1985-the-team-as-the-theorys-holder) (theory held in the team); [rationale, shared vocabulary](track-rationale-as-artifact.md#shared-vocabulary-as-the-theorys-carrier) |
| "No amount of procedure or documentation can totally prevent" common-ground breakdowns; teams repair rather than document all assumptions; common operating pictures are insufficient | Klein et al. 2005 | Incident analysis (secondary) | [unfamiliar code, Naur](unfamiliar-code-and-shared-models.md#naur-1985-the-team-as-the-theorys-holder) (revival from documents impossible); [rationale, capture cost](track-rationale-as-artifact.md#design-rationale-capture-cost-versus-use) |
| Attention management: automation compensates invisibly; threshold alarms fire too early or too late; tactile cues keep peripheral awareness | Klein et al. 2004, 2005; Sarter | Argument; design study cited | [adjacent, AI-coding counterparts](adjacent-literatures.md#what-the-ai-coding-sources-already-say-and-what-they-do-not) (Litt's "peripheral vision"); [in-loop friction, Claude Code](track-in-loop-friction.md#claude-code) (notification and approval prompts) |
| Seven myths; substitution myth; Table 1 of putative benefit versus real complexity ("creates more threads to track … with coordination costs, continuously"); law of stretched systems | Bradshaw et al. 2013; Woods and Hollnagel 2006 | Position paper | [adjacent, Bainbridge](adjacent-literatures.md#bainbridges-ironies); [Cowan](cowan-more-work-for-mother.md#travel-into-technology-criticism-and-software-discourse) (relocated labour) |
| OPD as design requirements read from an interdependence table; "sufficient OPD", not maximal; the VRC scripting case (10 scripts/run, 50% uninterrupted, 9 pauses, 7 corrections, 8 of 50 failed and all recovered) | Johnson et al. 2014 | Method paper; own-run instrumentation | [in-loop friction, step grains](track-in-loop-friction.md#grains-observed-in-tools) (step-level pause, modify, skip); no counterpart for interdependence analysis |
| Empirical HAT: 76 studies, all simulation; human–human teams generally better; transparency mixed; reliability positive; interdependence positive | O'Neill et al. 2022 | Systematic review | No counterpart |
| Synthetic teammate matches mission performance but processes targets less efficiently; pulls rather than pushes information; rigid coordination; entrainment | McNeese et al. 2018; Demir et al. 2019 | Lab, 30 teams; communication-flow analysis | [unfamiliar code, team cognition](unfamiliar-code-and-shared-models.md#team-cognition-research) (DeChurch: process mediates); no counterpart for push versus pull |
| SAT transparency levels; NASEM's 57 objectives; directability's effect on trust is an open question | Chen et al. 2018; NASEM 2022 | Model; consensus report | [adjacent, situation awareness](adjacent-literatures.md#situation-awareness-and-the-out-of-the-loop-problem) (Endsley's levels) |
| Team performance depends on the human's model of the AI's error boundary; updates that improve accuracy can hurt the team; explanations raise acceptance regardless of correctness | Bansal et al. 2019, 2019, 2021 | Crowd experiments, 25/condition | [evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026) (Kaufman, Perry on overtrust); [adjacent, complacency](adjacent-literatures.md#use-misuse-disuse-abuse-complacency-and-automation-bias) |
| 18 guidelines including make clear why, support efficient correction, convey consequences, notify about changes; six generative principles including co-creation and friction against overreliance | Amershi et al. 2019; Weisz et al. 2024 | Practitioner validation, 49 × 20 products; iterative design | [in-loop friction, arguments](track-in-loop-friction.md#arguments-and-evidence) (friction as design); [hand-off checks, gate placement](track-hand-off-checks.md#gate-placement-and-enforcement) |
| "AI pair programmer" is vendor framing; Copilot adds lines and deletions (n = 21); LLM programming "a new way of programming"; pAIr measures "not as comprehensive" | GitHub 2021; Bird 2022; Imai 2022; Sarkar 2022; Ma 2023 | Vendor text; small experiment; reviews | [in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking); [unfamiliar code, practices](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model) (human pairing as transfer) |
| Individuals with AI match teams without AI (n = 776); human–AI pairs are more task-oriented, delegate 17% more, edit 62% less (n = 2,234) | Dell'Acqua et al. 2025; Ju and Aral 2025 | Field experiments | [chat-centric, bottom line](chat-centric-agents-vs-team-sdlc.md#bottom-line) (single-human supervision); [adjacent, developer studies](adjacent-literatures.md#developer-studies-applying-these-frameworks) |
| Agent PR integration correlates with reviewer engagement; force-pushes and size penalised; iteration and tests not; 71.5% merged | Nachuma and Zibran 2026 | Mining, 33,596 PRs | [literature addendum, walkthroughs](literature-addendum.md#target-3-human-evaluations-of-generated-wikis-maps-and-tours-accuracy-of-generated-documentation) (Watanabe, Duma on AIDev); [chat-centric, Raida and Hou](chat-centric-agents-vs-team-sdlc.md#single-developer-orchestration-is-not-team-level-engineering) |
| Two coordinating agents lose 41% of solo success; 20% of steps in communication; first-turn planning halves conflicts | CooperBench 2026 | Benchmark, 652 tasks | No counterpart |
| A successor agent given trace or notes needs 20–59% fewer events and 42–63% fewer tokens than one given the repository alone | Handoff Debt 2026 | Benchmark, 724 runs/model | [rationale, transcript retention](track-rationale-as-artifact.md#harness-transcript-retention-versus-commit-linked-provenance); [chat-centric, transcripts](chat-centric-agents-vs-team-sdlc.md#a-transcript-is-local-interaction-state-not-durable-team-state) |
| Inaccurate self-reporting is 22.58% of misalignment episodes and rising; 91.49% of resolutions need explicit user correction | Tang et al. 2026 | Observational, 20,574 sessions, LLM-annotated | [evidence, AI-specific](evidence-and-mechanisms.md#ai-specific-evidence-20232026); [in-loop friction, Claude Code](track-in-loop-friction.md#claude-code) (approval telemetry) |
| Developers are frustrated calibrating autonomy and want it to vary by task and over time | Hedwig 2026 | Survey, n = 21 | [in-loop friction, modes](track-in-loop-friction.md#existing-modes-and-tools); [literature addendum, gates](literature-addendum.md#target-4-comprehension-effects-of-approval-gates-and-learning-modes) |
| The AI-era sources restate observability, directability, common ground and coordination cost without citing the strand | Full-text checks above | Bibliographic | [adjacent, mapping](adjacent-literatures.md#mapping-to-the-existing-notes); [synthesis, gap 10](synthesis.md#gaps-every-pass-left) |

"No counterpart" means no note in this directory addresses the point; it is a statement about
the notes, not about the wider literature.

## Dead ends

- **Seven Deadly Myths.** Not open access; the author-site PDF (`IS-28-03-HCC_1.pdf`) is 404
  live and the 2022–2023 Wayback captures are truncated (pdftotext fails); the 2026-05-11
  capture is complete. One WebSearch was spent locating the filename.
- **Coactive Design.** The ACM PDF returns 403 and the author-site copy is 404 in every
  capture; the TU Delft repository file is the working route.
- **Bradshaw's site.** Live requests for every publication PDF returned 404 or empty bodies;
  Wayback raw mode served the Ten Challenges, the Common Ground preprint and Myths part 2. The
  Common Ground text is the June 2004 preprint marked "do not quote or cite without
  permission", not the Wiley chapter; the published chapter may differ (the preprint has six
  challenges, the IEEE piece ten).
- **Christoffersen and Woods; Sarter, Woods and Billings.** Read from Ohio State CSEL
  preprints via Wayback; pagination against the Elsevier and Wiley versions not verified.
  Sarter and Woods 1995, 1997, 2000 are abstract only (Sage).
- **O'Neill et al. 2022.** Sage returned 403; the PubMed Central HTML was read instead.
- **ACM (Zhang et al. 2021, Imai 2022, Bird et al. 2022).** 403 throughout; Crossref and
  Semantic Scholar abstracts used for the first two, a 2025-11-25 Wayback capture for Queue.
- **Clark 1996; Clark and Brennan 1991; Woods and Hollnagel 2006; Hollnagel and Woods 2005;
  Billings 1996 (book).** Metadata only. Klein et al. (2000) on why teams lose common ground,
  Schaeffer (1997) and Klinger and Klein (1999) on coordination-cost types, Sklar and Sarter
  (1999), Chien et al. (2020) and Wiener (1989) were not obtained; each is reported as cited
  by the source that cites it.
- **Demir et al. 2017 (*Cognitive Systems Research* 46:3–12).** Metadata only; the 2019
  Frontiers summary was used instead.
- **NASEM report.** Only the summary chapter was read; the 57 objectives and the transparency
  chapter were not.
- **Cybernetic Teammate.** Dell'Acqua et al. is NBER w33641 / SSRN 5188231, abstract only;
  arXiv 2503.18238 is Ju and Aral's paper, not theirs.
- **Coordination cost of a coding agent on a human team.** Searched OpenAlex (three queries
  from 2025), two WebSearches, and arXiv listings; what exists measures agent–agent
  coordination (CooperBench), agent–successor handoff (Handoff Debt), reviewer-side merge
  correlates (Nachuma and Zibran; Raida and Hou in the chat-centric note), developer pushback
  (Tang et al.), or non-code teams (Dell'Acqua; Ju and Aral). No study measures synchronization,
  communication, redirection or diagnosis overhead, in Klein et al.'s sense, for humans
  working alongside a coding agent.
- **"AI teammate" critics.** Beyond CooperBench's title and the LeadDev piece, no essay was
  found that argues against the teammate framing on joint-activity grounds; the critics found
  argue from adoption data (Raida and Hou) or interaction properties (Sarkar; Ma).
- **WebSearch count: 3** — the Seven Deadly Myths PDF; arXiv 2026 coding agents and
  "teammate"; "AI teammate" critiques.

## References

Primary sources, alphabetical; URLs in the text are the terminal citations.

- Amershi, S., Weld, D., Vorvoreanu, M., Fourney, A., Nushi, B., Collisson, P., Suh, J., Iqbal, S., Bennett, P. N., Inkpen, K., Teevan, J., Kikin-Gil, R., Horvitz, E. (2019). Guidelines for human-AI interaction. *CHI 2019*, 1–13. doi:10.1145/3290605.3300233.
- Bansal, G., Nushi, B., Kamar, E., Horvitz, E., Weld, D. S. (2019). Updates in human-AI teams: understanding and addressing the performance/compatibility tradeoff. *AAAI* 33(1):2429–2437. doi:10.1609/aaai.v33i01.33012429.
- Bansal, G., Nushi, B., Kamar, E., Lasecki, W. S., Weld, D. S., Horvitz, E. (2019). Beyond accuracy: the role of mental models in human-AI team performance. *Proc. AAAI HCOMP* 7:2–11. doi:10.1609/hcomp.v7i1.5285.
- Bansal, G., Wu, T., Zhou, J., Fok, R., Nushi, B., Kamar, E., Ribeiro, M. T., Weld, D. S. (2021). Does the whole exceed its parts? The effect of AI explanations on complementary team performance. *CHI 2021*. arXiv:2006.14779.
- Billings, C. E. (1996). *Human-centered aviation automation: principles and guidelines*. NASA Technical Memorandum 110381. https://openalex.org/W1497874644.
- Bird, C., Ford, D., Zimmermann, T., Forsgren, N., Kalliamvakou, E., Lowdermilk, T., Gazit, I. (2022). Taking flight with Copilot. *ACM Queue* 20(6):35–57. doi:10.1145/3582083.
- Bradshaw, J. M., Hoffman, R. R., Johnson, M., Woods, D. D. (2013). The seven deadly myths of "autonomous systems". *IEEE Intelligent Systems* 28(3):54–61. doi:10.1109/MIS.2013.70.
- Chen, J. Y. C., Lakhmani, S. G., Stowers, K., Selkowitz, A. R., Wright, J. L., Barnes, M. (2018). Situation awareness-based agent transparency and human-autonomy teaming effectiveness. *Theoretical Issues in Ergonomics Science* 19(3):259–282. doi:10.1080/1463922X.2017.1315750. Also Chen et al. (2017), *Proc. SPIE* 10194:101941V. doi:10.1117/12.2263194.
- Christoffersen, K., Woods, D. D. (2002). How to make automated systems team players. In Salas, E. (ed.), *Advances in Human Performance and Cognitive Engineering Research* 2:1–12. Elsevier. doi:10.1016/S1479-3601(02)02003-9.
- Clark, H. H. (1996). *Using Language*. Cambridge University Press. doi:10.1017/CBO9780511620539.
- Clark, H. H., Brennan, S. E. (1991). Grounding in communication. In Resnick, L. B., Levine, J. M., Teasley, S. D. (eds.), *Perspectives on Socially Shared Cognition*, 127–149. APA. doi:10.1037/10096-006.
- Dell'Acqua, F., Ayoubi, C., Lifshitz, H., Sadun, R., Mollick, E., Mollick, L., et al. (2025). The cybernetic teammate: a field experiment on generative AI reshaping teamwork and expertise. *NBER Working Paper* 33641. doi:10.3386/w33641.
- Demir, M., McNeese, N. J., Cooke, N. J., et al. (2019). The evolution of human-autonomy teams in remotely piloted aircraft systems operations. *Frontiers in Communication* 4:50. doi:10.3389/fcomm.2019.00050.
- GitHub / Friedman, N. (2021). Introducing GitHub Copilot: your AI pair programmer. GitHub Blog, 2021-06-29. https://github.blog/2021-06-29-introducing-github-copilot-ai-pair-programmer/.
- Hassan, A. E., Li, H., Lin, D., Adams, B., Chen, T.-H., Kashiwa, Y., Qiu, D. (2025). Agentic software engineering: foundational pillars and a research roadmap. arXiv:2509.06216.
- Hoffman, R. R., Hawley, J. K., Bradshaw, J. M. (2014). Myths of automation, part 2: some very human consequences. *IEEE Intelligent Systems* 29(2):82–85. doi:10.1109/MIS.2014.25.
- Hollnagel, E., Woods, D. D. (2005). *Joint Cognitive Systems: Foundations of Cognitive Systems Engineering*. CRC Press. doi:10.1201/9781420038194.
- Imai, S. (2022). Is GitHub Copilot a substitute for human pair-programming? An empirical study. *ICSE 2022 Companion*, 319–321. doi:10.1145/3510454.3522684.
- Johnson, M., Bradshaw, J. M., Feltovich, P. J., Jonker, C. M., van Riemsdijk, M. B., Sierhuis, M. (2014). Coactive Design: designing support for interdependence in joint activity. *Journal of Human-Robot Interaction* 3(1):43–69. doi:10.5898/JHRI.3.1.Johnson.
- Ju, H., Aral, S. (2025). Collaborating with AI agents: field experiments on teamwork, productivity, and performance. arXiv:2503.18238.
- KC, D., Budathoki, A. (2026). Handoff debt: the rediscovery cost when coding agents take over interrupted tasks. arXiv:2606.02875.
- Khatua, A., Zhu, H., Tran, P., Prabhudesai, A., Sadrieh, F., Lieberwirth, J. K., Yu, X., Fu, Y., et al. (2026). CooperBench: why coding agents cannot be your teammates yet. arXiv:2601.13295.
- Klein, G., Feltovich, P. J., Bradshaw, J. M., Woods, D. D. (2005). Common ground and coordination in joint activity. In Rouse, W. B., Boff, K. R. (eds.), *Organizational Simulation*. Wiley. Preprint: https://web.archive.org/web/2024id_/https://www.jeffreymbradshaw.net/publications/Common_Ground_Single.pdf.
- Klein, G., Woods, D. D., Bradshaw, J. M., Hoffman, R. R., Feltovich, P. J. (2004). Ten challenges for making automation a "team player" in joint human-agent activity. *IEEE Intelligent Systems* 19(6):91–95. doi:10.1109/MIS.2004.74.
- Li, H., Zhang, H., Hassan, A. E. (2025). The rise of AI teammates in software engineering (SE) 3.0: how autonomous coding agents are reshaping software engineering. arXiv:2507.15003.
- Lyons, J. B., Sycara, K., Lewis, M., Capiola, A. (2021). Human–autonomy teaming: definitions, debates, and directions. *Frontiers in Psychology* 12:589585. doi:10.3389/fpsyg.2021.589585.
- Ma, Q., Wu, T., Koedinger, K. (2023). Is AI the better programming partner? Human-human pair programming vs. human-AI pAIr programming. arXiv:2306.05153.
- McNeese, N. J., Demir, M., Cooke, N. J., Myers, C. (2018). Teaming with a synthetic teammate: insights into human-autonomy teaming. *Human Factors* 60(2):262–273. doi:10.1177/0018720817743223.
- Nachuma, C., Zibran, M. (2026). When AI teammates meet code review: collaboration signals shaping the integration of agent-authored pull requests. *MSR 2026*. arXiv:2602.19441.
- National Academies of Sciences, Engineering, and Medicine (2022). *Human-AI Teaming: State-of-the-Art and Research Needs*. National Academies Press. doi:10.17226/26355.
- O'Neill, T., McNeese, N., Barron, A., Schelble, B. (2022). Human–autonomy teaming: a review and analysis of the empirical literature. *Human Factors* 64(5):904–938. doi:10.1177/0018720820960865.
- Salas, E., Sims, D. E., Burke, C. S. (2005). Is there a "Big Five" in teamwork? *Small Group Research* 36(5):555–599. doi:10.1177/1046496405277134.
- Sarkar, A., Gordon, A. D., Negreanu, C., Poelitz, C., Ragavan, S. S., Zorn, B. (2022). What is it like to program with artificial intelligence? *PPIG 2022*. arXiv:2208.06213.
- Sarter, N. B., Woods, D. D. (1995). How in the world did we ever get into that mode? Mode error and awareness in supervisory control. *Human Factors* 37(1):5–19. doi:10.1518/001872095779049516.
- Sarter, N. B., Woods, D. D. (1997). Team play with a powerful and independent agent: operational experiences and automation surprises on the Airbus A-320. *Human Factors* 39(4):553–569. doi:10.1518/001872097778667997.
- Sarter, N. B., Woods, D. D. (2000). Team play with a powerful and independent agent: a full-mission simulation study. *Human Factors* 42(3):390–402. doi:10.1518/001872000779698178.
- Sarter, N. B., Woods, D. D., Billings, C. E. (1997). Automation surprises. In Salvendy, G. (ed.), *Handbook of Human Factors and Ergonomics*, 2nd ed. Wiley. Preprint: https://web.archive.org/web/20260205021152id_/http://csel.eng.ohio-state.edu/productions/xcta/downloads/automation_surprises.pdf.
- Shukla, T., Feng, K. J. K., Wang, L., Rostami, M., Zhang, A. X. (2026). Hedwig: dynamic autonomy for coding agents under local oversight. *ACM CAIS 2026 demo*. arXiv:2605.11495.
- Stokel-Walker, C. (2026). AI-coding agents kill team collaboration. *LeadDev*, 2026-07-28. https://leaddev.com/ai/ai-coding-agents-kill-team-collaboration.
- Tang, N., Chen, C., Xu, G., Shi, Y., Huang, Y., McMillan, C., Dong, T., Li, T. J.-J. (2026). How coding agents fail their users: a large-scale analysis of developer-agent misalignment in 20,574 real-world sessions. arXiv:2605.29442.
- Weisz, J. D., He, J., Muller, M., Hoefer, G., Miles, R., Geyer, W. (2024). Design principles for generative AI applications. *CHI 2024*. arXiv:2401.14484.
- Woods, D. D., Hollnagel, E. (2006). *Joint Cognitive Systems: Patterns in Cognitive Systems Engineering*. CRC Press. doi:10.1201/9781420005684.
- Zhang, R., McNeese, N. J., Freeman, G., Musick, G. (2021). "An ideal human": expectations of AI teammates in human-AI teaming. *PACM HCI* 4(CSCW3):1–25. doi:10.1145/3432945.
