---
status: proposal
date: 2026-09-16
---

# Design analysis

The evaluative counterpart to this directory's documentary corpus. The
[synthesis](synthesis.md) records what the sources found and leaves every
tension as the sources leave it; this document takes a position. It asks
one question the corpus deliberately did not: *given what was found, what
should Dashpot do?* — where "Dashpot" means the instrument for a
development lifecycle, not the terminal view that exists today. Nothing here
changes a research note; where the analysis leans on a finding, it cites
the note, and where it goes beyond the evidence it says so.

The document is being written in stages. This revision holds the thesis,
the lifecycle map, the principles, and the method for what follows; the
candidates, their assumptions, and the tests are in the
[candidates note](candidates.md), which applies §4's method.

Revised 2026-09-16 after the [thematic analysis](themes.md) of the whole
corpus, which tested this document's frame against blind clusterings of
every claim in the notes. The changes it asked for are marked where they
apply: six principles gain a clause, the map gains a cell and a
caveat, three of the four Phase C principles are marked as single-note,
and the method gains two lenses and widens one
([themes, what this changes](themes.md#8-what-this-changes-in-the-analysis)).

## 1. Thesis

**Dashpot is a tool for applying a flexible software development lifecycle
that leans heavily on AI and works without it.** Its current feature set is
one such lifecycle observed end to end: an Issue is declared, a session
binds to it, a Worktree is prepared, commits and pushes accumulate, a Pull
Request is reviewed, checked, and integrated, and the Branch and Worktree
are cleaned up. Every one of those is a stage a person or an agent passes
through, and Dashpot's contribution is to make the passage observable
without pretending to own it ([design](../design.md);
[domain language](../domain-language.md#observation)).

That lifecycle has a shape the chat-centric tools do not: **the work sits
above the session.** In a chat-centric tool the private conversation is
the unit of work and the identity of what was done; in Dashpot the Issue
holds intent and ownership, Git and the Pull Request hold the proposed
change and its history, checks hold the evidence, and the Agent Session
is an execution record bound to an Issue for a time and released. That is
the split Linear and GitHub have moved toward — the conversation demoted
from the identity of the work to a shared execution log attached to it —
and the one the first measurement of agentic pull requests says current
adoption lacks: one person both reviewed and modified the agent's
contribution in 78.9% of 25,264 agent PRs, and multi-human patterns were
11.3% ([chat-centric agents, bottom line](chat-centric-agents-vs-team-sdlc.md#bottom-line);
[chat-centric agents, synthesis](chat-centric-agents-vs-team-sdlc.md#synthesis)).
Dashpot's distinguishing strength, against those tools, is that it is
already built around the shared objects a team coordinates on. The feature
family designed here should sharpen that, not dilute it.

The namesake is the design brief. A dashpot resists motion in proportion
to velocity: it does not stop the piston, it slows it, and it slows a fast
stroke more than a slow one. That is exactly the shape the evidence asks
for. The loss the corpus documents is not that agents write code; it is
that they write it faster than a person's model of the system can follow,
and that reading and approving — the fast path — is the textbook condition
for believing one understands when one does not
([evidence, illusion of competence](evidence-and-mechanisms.md#illusion-of-competence-and-fluency);
[synthesis, finding](synthesis.md#finding)). Litt's own framing of his
quiz is "a speed regulator"
([talk, proposal 2](understanding-bottleneck-talk.md#proposal-2-quizzes-as-a-speed-regulator)).
The feature family this analysis is designing is therefore not "friction"
in general but *velocity-proportional* resistance placed at the lifecycle
stages where the model is most at risk — and a dashpot, unlike a brake, is
tuned rather than fixed.

Three commitments follow from the user's framing and are taken as given:

- **Friction attaches to lifecycle stages, not to a screen.** The current
  TUI is not a constraint on this design; whatever ships will be a
  significant extension or departure. The hooks that matter are the
  observation model — what Dashpot can see and record — and the lifecycle
  itself.
- **The lifecycle is expandable.** Stages the evidence says a lifecycle
  needs and Dashpot does not yet observe are a cost to be priced, not a
  reason to discard a candidate. Forcing new affordances into the
  entrypoints the current feature set happens to have would straitjacket
  the design.
- **It must work well for one person and for a team, and the social lens
  is a distinguishing principle, not a later extension.** The corpus's
  literature sweep found the model was never held alone — Naur's theory is
  the team's, and every practice that transferred it was social — and the
  AI-era shift it documents is from those social workflows to one person
  privately supervising an agent
  ([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model);
  [chat-centric agents, the tension](chat-centric-agents-vs-team-sdlc.md#the-tension-people-identify)).
  Dashpot's answer to that shift is the work-above-the-session shape
  above. So a candidate is not scored "solo first, social later": it is
  scored on whether it works for a person alone *and* on what it makes
  visible, shareable, or transferable beyond the session, and a candidate
  that only makes sense inside one person's session is suspect for the
  same reason a chat-centric tool is.

And one test, kept separate from the documentary work at the user's
request, runs through everything below: **does it work for code the person
did not write?** The pre-AI answer to unfamiliar code — a mentor, a small
task, and running it — assumes an author who can be asked. Agent-authored
code has no such author, and no source in the corpus addresses that case
([synthesis, gaps](synthesis.md#gaps-every-pass-left), item 9). A candidate
that only works when the person wrote the code is a candidate for a
problem Dashpot does not have.

## 2. The lifecycle, in two layers

The synthesis map's first axis — where the friction lives — was built from
the sources' own placements. For Dashpot the axis has to be replaced by the
lifecycle Dashpot can hook, so the map below is in two layers: the stages
Dashpot observes today, and the stages the evidence says a lifecycle needs.
Each stage is then laid against the demand axis, marking whether a friction
placed there would rest on an **observed** fact, would need a **new**
observation, or would **mutate** something — which under
[ADR 0008](../adr/0008-let-management-commands-mutate-on-explicit-invocation.md)
means a named command on explicit invocation, never a side effect of
observation.

### Layer 1: what Dashpot observes today

| Stage | What Dashpot sees | Who acts | Record kept |
| --- | --- | --- | --- |
| Issue declared | Issue Profile from the Issue Source; Linked Pull Requests | person | Query Pages, Resolved Issues (observed, not stored) |
| Session begins | Agent Session via harness lifecycle hooks; liveness; activity age | harness | Work Store record at the Worktree |
| Work starts | Issue Binding via `work start`; Agent Run at one Worktree | agent (main session only) | Work Store, versioned, Project-local |
| Worktree prepared | Issue Worktree by convention; dirty state; ahead/behind | person or agent | Observation Target (runtime only) |
| Commits and pushes | Branch refs, Remote-Tracking Branches, fetch age, integration by reachability or content | agent or person | none beyond Git |
| Pull Request opened | open / draft / closed / merged; review decision; checks and statuses; mergeability | person, reviewers, CI | none beyond GitHub |
| Work stops or relocates | `work stop`, `work relocate`, `SessionEnd`; Orphaned Agent Runs | agent | Work Store |
| Cleanup | Branch and Worktree removal on confirmed selection | person | none |

Three facts about this layer matter for everything that follows. First,
Dashpot already has two channels *into* the agent's loop, not merely a view
of its results: the lifecycle hook publisher registered in each harness,
and the model-invoked `dashpot-issue-work` skill that tells the agent how
to behave in this lifecycle
([agent sessions](../agent-sessions.md#agent-session-observation)). A
friction that must live inside the loop has somewhere to live. Second,
nothing Dashpot records today is about a *person's* act. The Work Store
records what an agent is bound to; the observation records what Git and
GitHub say. The corpus found that no tool anywhere records that a human
read an artifact, and Dashpot is no exception
([synthesis, gaps](synthesis.md#gaps-every-pass-left), item 5). Third,
by the CSCW definition Dashpot is a *workspace awareness* tool — the
up-to-the-moment understanding of who is acting, on what, where, with
their histories — and the awareness literature found no tool that treats
an automated actor as an awareness subject whose who/what/where must be
shown to people. Dashpot's Agent Run — a session, bound to an Issue, at a
Worktree, live or gone — is exactly that, which the awareness literature
says is instrumental: when the people whose work depends on each other's
know it, changes resolve faster and fail less
([awareness, finding](workspace-awareness-and-coordination.md#finding)).
Observability is the half of "automation as a team player" Dashpot has;
directability — re-directing the agent fluently — is the half it lacks,
and the hook and skill channels are where it could live
([team player, finding](automation-as-a-team-player.md#finding)).

### Layer 2: what the evidence says a lifecycle needs

Stages no source places in a tool, or places only pre-AI, but which the
evidence marks as where the model is built, held, or lost:

| Stage | Why the evidence wants it | Nearest thing today |
| --- | --- | --- |
| **Task start: restate the problem** | Generation before exposure is the demanding end of the mechanism table; plan approval is the only task-start gate agents ship, and it is the one people reject (39% plan rejection versus 3% per permission) | Plan modes; AGENTS.md ([in-loop friction, Claude Code](track-in-loop-friction.md#claude-code)) |
| **In-loop step: promote, not accept** | The only tool inverting the authorship default is a notebook; no editor or agent CLI has ported it | Per-command permission gates ([in-loop friction, inversion](track-in-loop-friction.md#inversion-outside-notebooks)) |
| **Hand-off: explain it back** | The single causal result in the corpus: 61.5% versus 23.1% later unassisted repair, at d = 1.52 velocity cost | Nothing between "agent done" and "PR opened" ([hand-off checks, Sankaranarayanan](track-hand-off-checks.md#sankaranarayanan-2026-in-full)) |
| **Review as transfer** | Pre-AI, reviewing spread the files a developer "knows" by 66–150%; AI-era review telemetry is disputed in direction (habituation in one study, scrutiny rising in another); batch size at review is the one place team friction meets comprehension evidence (59% versus 35% effectiveness for small versus large changes) | Review decision glyph on a PR row ([unfamiliar code, practices](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model); [flow, finding](flow-wip-limits-and-constraints.md#finding)) |
| **Arrival at review: rate and WIP** | Generation grows multiplicatively per developer, review linearly with headcount; no project sets a numeric limit beyond one three-PR rule; WIP limits are the team-level friction device with before–after evidence (lead time halved) and no comprehension measure | Open PR counts and Agent Runs per Worktree are observed but not bounded ([review capacity, finding](review-capacity-and-volume.md#finding); [flow, finding](flow-wip-limits-and-constraints.md#finding)) |
| **Session boundary: handover** | What is handed over is a state model plus a stance — belief, intent, expectation, contingency — and it is rebuilt by the receiver's questions; written-only handover failed in four of five investigated incidents; a structured protocol cut errors 23%; agent compaction keeps the artifact side and nobody measures what a person recovers from it | `work stop` / `work relocate` / `SessionEnd` end or move a run and record nothing about its state ([handover, finding](handover-between-sessions-people-and-agents.md#finding)) |
| **Return after absence** | Retention is unmeasured beyond one week; the human-factors literature found detection restored by a short return to manual control; programmers resume from cues, not memory (93% navigate before editing) | Session activity age; fetch age ([adjacent literatures, aviation](adjacent-literatures.md#skill-fade-in-aviation); [handover, finding](handover-between-sessions-people-and-agents.md#finding)) |
| **Integration order across parallel runs** | Conflict probability rose 5%→40% with concurrent changes at Uber; 79.4% of agent PRs are open concurrently and cross-agent pairs conflict 41.7%; no vendor states how many parallel runs is too many or in what order they land | Worktrees, Branches, and integration facts are observed; no count or order ([integration, finding](integration-frequency-and-parallel-branches.md#finding)) |
| **Module revisit** | No tool connects a change to a review schedule; SRS on a repository has never been built | Integration facts per Branch ([durable model, scheduling](track-durable-model.md#who-has-connected-change-detection-to-review-scheduling)) |
| **Periodic: what did I lose** | Every measure in the corpus is a single session; the one deployed instrument is a self-report item | Nothing ([measurement, arguments against](track-measurement.md#arguments-against-measuring)) |
| **A person joining, or handing over** | The model was held by the team; onboarding's answer is mentor + small task + running it; apprenticeship ran on the routine work agents now do, and "seniors can no longer observe whether juniors are learning or just prompting"; no AI-era item touches this stage | Nothing ([unfamiliar code, convergence](unfamiliar-code-and-shared-models.md#what-the-newcomer-studies-converge-on); [apprenticeship, finding](apprenticeship-under-agents.md#finding)) |
| **Who signs** | Every policy read places accountability for an agent change on a named person; ownership predicted quality at Microsoft; agent code is 15.8 points less likely to be modified later under an untested "no clear owner" hypothesis | Issue Binding names the session, not a person; PR author and reviewers are observed ([ownership, finding](ownership-and-accountability-for-delegated-work.md#finding)) |

### The map: lifecycle stage against demand

**O** = rests on an observed fact today; **N** = needs a new observation
(a person's act, a read, an explanation, a run, a schedule); **M** = would
mutate something and so must be a named command or an external gate
Dashpot observes. Cells name the kind of friction that could sit there,
not a candidate.

| Stage \ demands | Generate / write | Explain | Recall | Verify / approve | Read / navigate | Nothing (artifact) |
| --- | --- | --- | --- | --- | --- | --- |
| Issue declared | restate the problem before binding (N) | — | recall the last touch of the module (N) | — | — | Issue Profile (O; signal: Issue Source refresh) |
| Session / work starts | — | — | what changed since last run here (O for Git; N for "read") | — | — | skill-carried lifecycle instructions (O; signal: versioned with the repository) |
| In-loop step | promote rather than accept (M: harness-side) | agent asks before proceeding (M: skill/hook) | — | permission gates (O via hooks, unmeasured) | — | curated dialog (N; no change signal) |
| Hand-off (agent done, pre-PR) | write the PR description oneself (N) | explain it back, graded, diff hidden (N + M if gating) | quiz on the diff, diff hidden (N) | — | read-first viewer (N); ask a person (N; social) | explainer artifact (N; no change signal) |
| PR review / merge | — | reviewer explains a hunk (N; social) | — | review decision (O); read attestation per file (N) | `Viewed` state (N: not in the PR observation) | Agent Trace / provenance (N; signal: pinned to the commit, lost on rewrite) |
| Integration / Cleanup | — | — | — | integration by reachability or content (O); landing order across concurrent runs (N) | — | ADR / rationale written (N; signal: a scheduled staleness check or none) |
| Session boundary (stop, relocate, end) | state + stance handover written by the outgoing holder (N) | receiver asks before resuming (N) | — | — | what the run left undone (O: Work Store; N: state) | compaction summary (M: harness-side; consumed once, does not age) |
| Arrival at review | — | — | — | concurrent Agent Runs, open PRs, change size bounded per person (N; M if enforced) | — | — |
| Return after absence | — | — | recall before re-reading (N) | — | what moved while away (O: Git facts; N: read) | — |
| Module revisit | — | — | scheduled retrieval, invalidated by change (N) | — | — | — |
| Periodic | — | — | sampled recall across the repository (N) | — | — | self-report instrument (N) |
| Person joining / handover | small first task (N) | teach-back to the newcomer (N; social) | — | pairing with the novice driving (N; social) | tour, map (N; signal: pinned ref or none); ask a person (N; social) | — |

What the map shows, before any candidate is weighed:

- The **O** cells are all in the verify / artifact columns — the passive
  end of the demand axis, where the evidence is weakest or negative.
  Dashpot as it stands observes exactly the stages that do not build the
  model.
- The demanding columns are **N** almost everywhere. That is the price
  of the thesis: a person's act is a new kind of fact for Dashpot, and the
  first design decision is what such a fact is — who publishes it, where it
  is stored, whether it has identity — before which act to record.
- The **M** cells are few and they are all in-loop. Under ADR 0008 an
  in-loop friction is either a harness-side default Dashpot cannot set, or
  a behaviour the skill asks of the agent, or a hook that refuses. The
  channels exist; the policy of using them to slow an agent rather than
  observe it is new.
- Three whole rows — return after absence, module revisit, periodic —
  have no **O** at all, and they are the rows the retention gap sits in.
  They are also the rows that work identically without AI.
- The rows Phase C added — session boundary, arrival at review,
  integration order — are the team's rows, and they are where Dashpot's
  existing facts are densest: runs, worktrees, branches, open PRs,
  integration. The friction there is a *bound* (how many in flight, how
  large, in what order) rather than an act, which is the one kind of
  friction with team-level before–after evidence and the one kind a
  passive observer can show without performing.

Added 2026-09-16, from the [thematic analysis](themes.md):

- The **columns are a design choice, not a finding.** Of thirty-five
  robust blind groups only one concentrates on a demand value (explain);
  the notes cluster on lifecycle stage and on mechanism, not on what a
  device asks of a person. The columns remain the right way to compare
  candidates, but a candidate's evidence attaches to its mechanism, not
  to its column — a cell is not evidence for what sits in it.
- The **artifact column is stale by default.** Each artifact cell now
  names its change signal or says it has none (principle 6); the cells
  with none are the ones a candidate must couple or schedule.
- The **Issue declared row is the thinnest.** Task start places 89 of
  3,465 cards against review's 534: the corpus was collected around the
  loop, the hand-off, and review, and a candidate in the first row is a
  bet in the same sense as an in-loop one (principle 2).
- The **read-or-navigate column now separates asking from reading.**
  Who is asked — a person, a document, a model — is the team's directory
  in use or bypassed (principle 9), and an ask is an act Dashpot could
  record where a read is not.

## 3. Principles the evidence supports

Each principle is stated, then the evidence, then what it commits the
design to. A principle that goes beyond what was measured says so.

1. **Demand before display.** The mechanisms with meta-analytic support
   cluster at the demanding end — retrieval g ≈ 0.5–0.6, self-explanation
   g = 0.55, teaching g = 0.56, generation d = 0.40 — and verification
   behaviour, not exposure, predicted comprehension (r = 0.96)
   ([evidence, summary table](evidence-and-mechanisms.md#summary-table);
   [evidence, finding](evidence-and-mechanisms.md#finding)).
   *Commits to:* a friction that only shows the person something — a map,
   an explainer, a trace — is not a remedy by itself. Every candidate must
   name the act it asks for.

2. **The bookend is the one thing with causal support; the loop is the one
   thing nobody has built.** A teach-back gate at hand-off is the corpus's
   only randomised comprehension result; the in-loop authorship inversion
   exists in one notebook and has never been ported; no approval gate, plan
   mode, or learning mode has a measured comprehension effect
   ([hand-off checks, evidence](track-hand-off-checks.md#evidence);
   [in-loop friction, dead ends](track-in-loop-friction.md#dead-ends)).
   *Commits to:* a hand-off candidate can be justified from evidence; an
   in-loop candidate is a bet, and should be tested as one.

3. **Test the model, not the text.** Generated questions leak the answer
   from the diff unless prevented; 62% of rejected teach-back attempts were
   tautological; no tool checks whether its questions discriminate readers
   who understood from readers who skimmed
   ([hand-off checks, open questions](track-hand-off-checks.md#open-questions-in-the-sources)).
   The pre-AI comprehension literature's questions are about behaviour and
   structure — what happens if, where would you look, what depends on this
   ([unfamiliar code, questions](unfamiliar-code-and-shared-models.md#the-questions-comprehenders-ask)).
   *Commits to:* a question drawn from the repository's structure or from
   running the code, not from the diff's prose; and a way to tell whether a
   question worked. *Added 2026-09-16:* and a question answered with the
   answer off the screen. The feeling of understanding that fluent,
   answer-visible output produces exceeds the understanding held —
   judgments of learning inflate when the answer is present, 77% against
   39% failure once the assistant is removed, perceived against actual
   understanding correlating at .26 or less — and a retrieval attempt
   before the reveal is the one intervention with controlled evidence of
   closing that gap
   ([themes, the confidence gap](themes.md#53-the-confidence-gap)). A
   hand-off check that shows the diff while asking about it measures the
   text twice over.

4. **Defaults decide; practices fail; but only practices have shipped.**
   Answer.AI's claim is that willpower cannot hold against a tab key, and
   Solveit's own reported failure is students going too far too fast
   despite its defaults; every quiz, policy, and AI-free day in the
   landscape is a practice
   ([Answer.AI, core claims](answer-ai-sweep.md#core-claims);
   [Solveit, finding](solve-it-sweep.md#finding)).
   *Commits to:* stating, per candidate, where on the enforcement axis it
   sits and what would move it one step toward a default. For Dashpot the
   axis is not free: observation cannot gate, so a gate is a hook, a
   pre-commit check, a PR check, or an agent instruction — something
   Dashpot observes rather than performs. *Added 2026-09-16:* and
   defaults decay. Vigilance over reliable automation falls with
   exposure and load; 97% of permission prompts are approved and
   dangerous-command blocking falls from 17% to 5% after fifty prompts;
   within-reviewer approval rates rose over seven months while inline
   comments fell — though that dataset's direction is disputed and no
   comprehension gate has been watched for months either way
   ([themes, habituation](themes.md#52-habituation-of-repeated-friction)).
   A friction that repeats must be designed against its own habituation
   — varied, sampled, faded with competence (principle 10), or measured
   for persistence — and a candidate must say which.

5. **Friction belongs at boundaries.** Proactive interventions are welcomed
   at task boundaries (80–90% preference) and dismissed mid-task (62%);
   the pre-AI interruption literature says the same
   ([in-loop friction, interaction research](track-in-loop-friction.md#interaction-research-on-grain-and-turn-taking)).
   *Commits to:* the lifecycle stages Dashpot observes *are* boundaries —
   bind, hand off, open, review, integrate, return. That is the strongest
   reason to build this family in Dashpot rather than in an editor: the
   boundaries are already events.

6. **Record the act, not only the artifact.** The design-rationale
   literature measured capture cost as the constant that defeated it; no
   tool records that a person read a generated document; the only read
   attestation found anywhere is pre-AI
   ([rationale, capture cost](track-rationale-as-artifact.md#design-rationale-capture-cost-versus-use);
   [rationale, dead ends](track-rationale-as-artifact.md#dead-ends)).
   *Commits to:* whatever new observation the map's **N** cells need, it is
   an observation of a person's act — a read, an explanation, a run, a
   recall — with the same discipline as every other Dashpot fact: opaque
   identity, retained when a refresh fails, never inferred from a label.
   *Added 2026-09-16:* and an artifact is stale by default. A
   representation derived from the code — a document, a quiz item, a
   map, a provenance link — has no change signal from its referent, so
   it goes wrong silently unless something couples it to the code (a
   pinned ref, an executable check, an event feed) or re-verifies it on
   a schedule; the tools that do couple exist and the ones that do not
   are the ones people tolerate as "useful even if not up to date"
   ([themes, staleness](themes.md#51-staleness-without-a-trigger)).
   Every artifact cell on the map names its change signal or says it has
   none.

7. **Bring the instrument.** Nothing measures a codebase model over weeks;
   the one deployed instrument is a self-report item; Storey asks how to
   measure cognitive debt and Wheeler says the instrument does not exist
   ([measurement, arguments against](track-measurement.md#arguments-against-measuring);
   [synthesis, gaps](synthesis.md#gaps-every-pass-left), items 1 and 6).
   *Commits to:* every candidate carrying its own measure, however crude,
   because the alternative is shipping resistance with no way to know if
   it did anything. This goes beyond the evidence: the corpus also records
   the case against quantifying learning, and a Goodharted comprehension
   score is a documented harm in education. *Revised 2026-09-16:* "nothing
   measures" is true only as a conjunction. The instruments exist — a
   blackout or explain-back task scored against the code, comprehension
   time inferred from IDE logs, a verified-understanding score in CI —
   and the horizons have been reached in adjacent work; what no study has
   done is run one on a professional team, on a living codebase, for
   longer than a session, with a comprehension outcome. Meanwhile the
   frameworks in use score perception rather than the model held, at the
   individual rather than the team (transactive memory correlates with
   performance at .77 self-reported and .38 observed), and self-assessed
   understanding is not an instrument for this debt (principle 3)
   ([themes, the instruments](themes.md#56-the-instruments-in-use-cannot-see-the-debt)).
   The measure a candidate carries should therefore be one of those
   instruments, not a survey item, and where it concerns the team it
   should be scored by agreement across members, not by asking each one.

8. **Expect relocation, and show the bill.** Cowan: labour-saving
   technology relocated work onto one generalist and raised the standard;
   Bainbridge: the operator is left with the parts automation could not do,
   without the practice to do them; the corpus asserts both about AI coding
   without citing either, and the teach-back gate's velocity cost is
   d = 1.52 ([Cowan, finding](cowan-more-work-for-mother.md#finding);
   [adjacent literatures, finding](adjacent-literatures.md#finding)).
   *Commits to:* treating the cost of a friction as a first-class fact the
   person can see and tune — a dashpot has a damping coefficient — and to
   asking, of each candidate, whose work it relocates and onto whom.

9. **The model is held socially, and the work, not the session, is where
   it is held.** Naur's theory is the team's; team cognition predicts
   performance (ρ = .38 over 65 studies); review spread what a developer
   knew by 66–150%; every AI-era remedy is for one person; the one
   longitudinal software-team study found models did not converge; and
   the first measurement of agentic pull requests found one person
   privately supervising the agent in 88.7% of them
   ([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model);
   [chat-centric agents, single-developer orchestration](chat-centric-agents-vs-team-sdlc.md#single-developer-orchestration-is-not-team-level-engineering)).
   The products that resist the shift attach sessions to the team's
   existing work graph rather than making the session multiplayer
   ([chat-centric agents, two responses](chat-centric-agents-vs-team-sdlc.md#two-competing-responses)).
   *Commits to:* every candidate attaching what it records to the shared
   objects — the Issue, the Branch, the Pull Request, the module — and
   never only to a session; and being scored on what it makes visible to
   a reviewer, a newcomer, or a second agent as well as on what it does
   for one person. This is the principle that distinguishes the family
   from what a chat-centric tool could ship. *Added 2026-09-16:* the
   model is held socially *by asking*. Asking a colleague costs both
   parties, so people route around it to documents, tools, and now AI —
   Stack Overflow questions fell 25% in six months, 51% now ask a model
   instead of a teammate — and who is asked is the team's directory of
   who knows what in use or bypassed. That the cheapest answerer weakens
   the directory is an inference the corpus does not test; that an ask
   is an observable act, and the map's read-or-navigate column should
   distinguish "ask a person" from "read", follows from the evidence
   ([themes, question routing](themes.md#54-the-question-routing-economy)).

10. **Fade for the expert.** Expertise reversal makes worked examples
    redundant or harmful for experts; Sankaranarayanan names gating experts
    as the cost of his result and proposes adaptive fading no gate
    implements; comprehension time falls from 66% to 44% of the day with
    experience
    ([evidence, expertise reversal](evidence-and-mechanisms.md#worked-examples-and-the-expertise-reversal-effect);
    [hand-off checks, open questions](track-hand-off-checks.md#open-questions-in-the-sources)).
    *Commits to:* resistance proportional to what the person does not yet
    hold, not a flat gate; which requires some record of what they do hold
    — principle 6 again.

11. **It must be worth it without the agent.** The lifecycle Dashpot
    observes is the same whether a person or an agent authored the commits;
    the three lifecycle rows with no observed fact (return, revisit,
    periodic) are also the rows in which the AI is irrelevant
    ([map](#the-map-lifecycle-stage-against-demand)).
    *Commits to:* the AI-optional test — a candidate that would be pointless
    on a human-authored branch is suspect, because agent-authored code is
    the extreme case of unfamiliar code, not a different kind of thing.

The Phase C notes add four principles for the team's rows of the map
(added 2026-09-15). *Caveat, 2026-09-16:* the thematic analysis found
that the blind clusterings confirm the gaps and tensions behind
principles 12 to 14 by recovering one note's own structure — the
joint-activity, awareness, handover, batch-size, and integration groups
each draw 77% or more of their core from a single note — so those three
are consistent with the corpus rather than converged on by it, and a
candidate that depends on one of them needs a second source. The
review-capacity half of principle 14 and all of principle 15 are the
exceptions: the review-flooding, accountability, and authorship groups
are among the most evenly sourced robust groups in the corpus
([themes, confirmations](themes.md#4-robust-groups-that-confirm-the-frame)).

12. **Observable and directable, or not a teammate.** Two decades of
    joint-activity research give one answer to what automation needs to be
    a team player: people must see what it is doing and will do next, and
    be able to redirect it fluently — "strong, silent, difficult to direct"
    is the failure, not too much or too little autonomy — and every member
    must help control the cost of coordinating. The coding-agent
    measurements find 22.58% of misalignment episodes involve inaccurate
    self-report, and reviewers reward agent behaviours that reduce
    coordination cost
    ([team player, finding](automation-as-a-team-player.md#finding)).
    *Commits to:* Dashpot's observation model as the observability half —
    an Agent Run at a Worktree bound to an Issue is the who/what/where the
    awareness literature asks for and no tool shows for an automated actor
    ([awareness, finding](workspace-awareness-and-coordination.md#finding))
    — and to treating directability as the missing half: a friction on the
    agent must let the person redirect, not only watch, through the hook
    and skill channels that already exist.

13. **A handover is a state model and a stance, rebuilt by the receiver's
    questions.** Across mission control, nuclear plants, and hospitals the
    update that works is interactive and carries belief, intent,
    expectation, and contingency; written-only handover failed in four of
    five investigated incidents, a structured protocol cut errors 23%, and
    the sender's most important item was lost 60% of the time while
    senders believed it had arrived. Agent compaction keeps the artifact
    side only, and no one measures what a person recovers from it
    ([handover, finding](handover-between-sessions-people-and-agents.md#finding)).
    *Commits to:* the session boundary — `work stop`, relocation, session
    end, return after absence — as a lifecycle stage with its own friction:
    an outgoing statement of state and stance that the Work Store keeps,
    and a receiving step that asks before resuming rather than reads a
    summary. This is the one stage where the agent, not the person, is the
    outgoing holder.

14. **Bound the rate, not only the act.** Generation grows multiplicatively
    per developer and review linearly with headcount; no project sets a
    numeric limit beyond one three-PR rule; WIP limits are the team-level
    friction with before–after evidence, and batch size at review is the
    one place team friction meets comprehension evidence (59% versus 35%);
    conflict probability rose from 5% to 40% with concurrent changes, and
    79.4% of agent PRs are open concurrently with another
    ([review capacity, finding](review-capacity-and-volume.md#finding);
    [flow, finding](flow-wip-limits-and-constraints.md#finding);
    [integration, finding](integration-frequency-and-parallel-branches.md#finding)).
    *Commits to:* bounds — concurrent Agent Runs per person, open PRs
    awaiting a reviewer, change size, landing order — as first-class
    friction alongside the acts of principles 1–6. A bound is the one kind
    of friction a passive observer can show without performing, and the one
    the velocity-proportional reading of the namesake names most directly.
    Goes beyond the evidence: no source measures whether a bound changes
    what anyone understands.

15. **A named person signs.** Every policy, forge rule, and vendor term
    read places accountability for an agent-written change on a named
    person, none on the agent; ownership predicted quality at Microsoft
    more than any other metric; agent code is 15.8 points less likely to be
    modified later under an untested "no clear owner" hypothesis; and
    Nissenbaum's "many hands" barrier explains why a named signer can still
    fail ([ownership, finding](ownership-and-accountability-for-delegated-work.md#finding)).
    *Commits to:* every act Dashpot records under principle 6 attaching to
    a person's identity as well as to the shared object — an Issue Binding
    names a session; the accountable party is a person — and to the
    "who knows what" question having a person's name as its answer, not a
    transcript's
    ([expert finding, finding](expert-finding-and-transactive-memory.md#finding)).
    *Added 2026-09-16:* the name cannot be inferred from authorship.
    Every instrument that locates knowledge or assigns responsibility —
    blame, degree of knowledge, truck factor, ownership metrics, reviewer
    and expertise recommenders, the Line 10 rule, the DCO — infers
    understanding from authorship; the inference was weak before agents
    (degree of knowledge explains R² = .25 of self-rated knowledge;
    co-changer expert suggestion is right under half the time) and agent
    authorship breaks it across all of them at once
    ([themes, the authorship inference](themes.md#55-the-authorship-inference)).
    The person an act attaches to is whoever performed the act, recorded
    at the time — never whoever last touched the line.

## 4. Method for what follows

The [candidates note](candidates.md) generates candidates per lifecycle
stage and walks each through a fixed set of lenses, so that candidates are
comparable and the reasons for a shortlist are legible:

- **Authorless code** — does it work when no one who could be asked wrote
  the code? And does it lean on an authorship-derived proxy for
  understanding — blame, ownership, degree of knowledge, truck factor, a
  recommender? If so it fails the lens whether or not an agent wrote the
  code, because that inference was weak before agents and is now broken
  (principle 15).
- **Grain** — what unit does it operate on: hunk, file, commit, PR, module,
  repository?
- **Demand** — which column of the demand axis, and what act is recorded?
  The column classifies the candidate; it is not evidence for it
  (the map's caveat above).
- **Enforcement and relocation** — where on the enforcement axis, what it
  would take to move one step toward a default, and whose work it moves
  onto whom.
- **Decay** — what the device is at month six: varied, sampled, faded
  with competence, measured for persistence, or habituated to
  click-through (principle 4). No candidate can answer from evidence yet;
  the lens records what it would take to.
- **Verifiability** — how would we know it did anything (principle 7)?
  Named instrument and horizon, not a survey item; team measures scored
  by agreement, not by asking each member.
- **Evidence source** — of the claims a candidate rests on, which are
  vendor-run, single-session, or self-report? Those are the three ways
  the corpus's evidence fails to see the debt
  ([themes, the instruments](themes.md#56-the-instruments-in-use-cannot-see-the-debt)),
  and the two widest blind groups in the corpus — vendor against
  independent evidence, rigour against realism — had no frame element to
  sit under before this lens.
- **Lifecycle hook** — observed today, new observation, or mutation; and
  through which channel (observation, hook publisher, skill, external
  gate).
- **Without AI** — is it still worth having on a human-authored branch?
- **Coordination cost** — what the candidate makes observable and
  directable about the agent, and what it costs the team to coordinate
  (principle 12); for a bound, what it limits and who sets it (principle
  14).
- **Social form** — does it work for one person alone *and* for a team;
  what it attaches to (Issue, Branch, Pull Request, module — or only a
  session); and what it makes visible, shareable, or transferable to a
  reviewer, a newcomer, or a second agent.

Candidates that survive become a shortlist; each shortlisted candidate is
reduced to the assumptions it depends on and the cheapest test of each
assumption. The shortlist is then grilled — by the user, and by an
independent second opinion — before anything is proposed as a feature.
