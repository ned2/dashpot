---
status: proposal
date: 2026-09-14
---

# Cognitive debt: analysis

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
candidates, their assumptions, and the tests are the next stage.

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
- **The default developer is one experienced person working from a
  terminal; the social form is a growth axis.** Every candidate is scored
  on what it becomes when a second person holds part of the model, because
  the evidence says the model was never held alone
  ([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model)).

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

Two facts about this layer matter for everything that follows. First,
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
([synthesis, gaps](synthesis.md#gaps-every-pass-left), item 5).

### Layer 2: what the evidence says a lifecycle needs

Stages no source places in a tool, or places only pre-AI, but which the
evidence marks as where the model is built, held, or lost:

| Stage | Why the evidence wants it | Nearest thing today |
| --- | --- | --- |
| **Task start: restate the problem** | Generation before exposure is the demanding end of the mechanism table; plan approval is the only task-start gate agents ship, and it is the one people reject (39% plan rejection versus 3% per permission) | Plan modes; AGENTS.md ([in-loop friction, Claude Code](track-in-loop-friction.md#claude-code)) |
| **In-loop step: promote, not accept** | The only tool inverting the authorship default is a notebook; no editor or agent CLI has ported it | Per-command permission gates ([in-loop friction, inversion](track-in-loop-friction.md#inversion-outside-notebooks)) |
| **Hand-off: explain it back** | The single causal result in the corpus: 61.5% versus 23.1% later unassisted repair, at d = 1.52 velocity cost | Nothing between "agent done" and "PR opened" ([hand-off checks, Sankaranarayanan](track-hand-off-checks.md#sankaranarayanan-2026-in-full)) |
| **Review as transfer** | Pre-AI, reviewing spread the files a developer "knows" by 66–150%; AI-era review telemetry runs the other way (approvals up, inline comments −22%) | Review decision glyph on a PR row ([unfamiliar code, practices](unfamiliar-code-and-shared-models.md#practices-that-transfer-the-model)) |
| **Return after absence** | Retention is unmeasured beyond one week; the human-factors literature found detection restored by a short return to manual control | Session activity age; fetch age ([adjacent literatures, aviation](adjacent-literatures.md#skill-fade-in-aviation)) |
| **Module revisit** | No tool connects a change to a review schedule; SRS on a repository has never been built | Integration facts per Branch ([durable model, scheduling](track-durable-model.md#who-has-connected-change-detection-to-review-scheduling)) |
| **Periodic: what did I lose** | Every measure in the corpus is a single session; the one deployed instrument is a self-report item | Nothing ([measurement, arguments against](track-measurement.md#arguments-against-measuring)) |
| **A person joining, or handing over** | The model was held by the team; onboarding's answer is mentor + small task + running it; no AI-era item touches this stage | Nothing ([unfamiliar code, convergence](unfamiliar-code-and-shared-models.md#what-the-newcomer-studies-converge-on)) |

### The map: lifecycle stage against demand

**O** = rests on an observed fact today; **N** = needs a new observation
(a person's act, a read, an explanation, a run, a schedule); **M** = would
mutate something and so must be a named command or an external gate
Dashpot observes. Cells name the kind of friction that could sit there,
not a candidate.

| Stage \ demands | Generate / write | Explain | Recall | Verify / approve | Read / navigate | Nothing (artifact) |
| --- | --- | --- | --- | --- | --- | --- |
| Issue declared | restate the problem before binding (N) | — | recall the last touch of the module (N) | — | — | Issue Profile (O) |
| Session / work starts | — | — | what changed since last run here (O for Git; N for "read") | — | — | skill-carried lifecycle instructions (O) |
| In-loop step | promote rather than accept (M: harness-side) | agent asks before proceeding (M: skill/hook) | — | permission gates (O via hooks, unmeasured) | — | curated dialog (N) |
| Hand-off (agent done, pre-PR) | write the PR description oneself (N) | explain it back, graded (N + M if gating) | quiz on the diff (N) | — | read-first viewer (N) | explainer artifact (N) |
| PR review / merge | — | reviewer explains a hunk (N; social) | — | review decision (O); read attestation per file (N) | `Viewed` state (N: not in the PR observation) | Agent Trace / provenance (N) |
| Integration / Cleanup | — | — | — | integration by reachability or content (O) | — | ADR / rationale written (N) |
| Return after absence | — | — | recall before re-reading (N) | — | what moved while away (O: Git facts; N: read) | — |
| Module revisit | — | — | scheduled retrieval, invalidated by change (N) | — | — | — |
| Periodic | — | — | sampled recall across the repository (N) | — | — | self-report instrument (N) |
| Person joining / handover | small first task (N) | teach-back to the newcomer (N; social) | — | pairing with the novice driving (N; social) | tour, map (N) | — |

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
   question worked.

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
   Dashpot observes rather than performs.

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

7. **Bring the instrument.** Nothing measures a codebase model over weeks;
   the one deployed instrument is a self-report item; Storey asks how to
   measure cognitive debt and Wheeler says the instrument does not exist
   ([measurement, arguments against](track-measurement.md#arguments-against-measuring);
   [synthesis, gaps](synthesis.md#gaps-every-pass-left), items 1 and 6).
   *Commits to:* every candidate carrying its own measure, however crude,
   because the alternative is shipping resistance with no way to know if
   it did anything. This goes beyond the evidence: the corpus also records
   the case against quantifying learning, and a Goodharted comprehension
   score is a documented harm in education.

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

9. **The model is held socially; solo is the floor.** Naur's theory is the
   team's; team cognition predicts performance (ρ = .38 over 65 studies);
   review spread what a developer knew by 66–150%; every AI-era remedy is
   for one person and the one longitudinal software-team study found models
   did not converge
   ([unfamiliar code, shared model](unfamiliar-code-and-shared-models.md#how-a-team-holds-a-shared-model)).
   *Commits to:* scoring each candidate on its social form — what it
   becomes when a reviewer, a newcomer, or a second agent holds part of the
   model — even though the first version is for one person.

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

## 4. Method for what follows

The next stage generates candidates per lifecycle stage and walks each
through a fixed set of lenses, so that candidates are comparable and the
reasons for a shortlist are legible:

- **Authorless code** — does it work when no one who could be asked wrote
  the code?
- **Grain** — what unit does it operate on: hunk, file, commit, PR, module,
  repository?
- **Demand** — which column of the demand axis, and what act is recorded?
- **Enforcement and relocation** — where on the enforcement axis, what it
  would take to move one step toward a default, and whose work it moves
  onto whom.
- **Verifiability** — how would we know it did anything (principle 7)?
- **Lifecycle hook** — observed today, new observation, or mutation; and
  through which channel (observation, hook publisher, skill, external
  gate).
- **Without AI** — is it still worth having on a human-authored branch?
- **Social form** — what it becomes with a second holder of the model.

Candidates that survive become a shortlist; each shortlisted candidate is
reduced to the assumptions it depends on and the cheapest test of each
assumption. The shortlist is then grilled — by the user, and by an
independent second opinion — before anything is proposed as a feature.
