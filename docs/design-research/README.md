---
status: living
date: 2026-09-16
---

# Design research

The research and analysis behind Dashpot's direction. Three themes run
through it: *cognitive debt* — the loss of a developer's conceptual model
of a codebase as agents author more of it — and the ideas, evidence, and
tooling that engage with keeping or rebuilding that model; the intentional
friction that keeps it, and where in a development lifecycle it belongs;
and the shift from understanding held by a team, in the work, to
understanding held by one person, in a session. The research notes are the
exploration phase of a design effort and assess no fit for Dashpot or for
any particular flavour of agentic engineering; only the
[analysis](analysis.md) takes a position. Each research note is a dated
`research` document: true as of its date,
corrections marked inline as `(corrected 2026-09-13: …)`, and every claim
cited to a primary source, with dead ends recorded so a later pass does not
repeat them. Notes cite one another with relative links rather than
repeating material.

## How this was produced

This is agent-driven research and summarisation, not directly
human-authored research. The questions, the scope of each pass, the
corrections to apply, and the framing of the analysis were set by a
person; the searching, reading, and writing were done by coding agents
(Claude Code sessions dispatching background research agents), with a
later agent pass verifying claims against primary sources and marking
corrections inline. Read every claim as a machine summary of a cited
source: the citation is the authority, and a claim without one should be
treated as unverified. The [synthesis](synthesis.md#provenance-of-this-corpus) records the
provenance of each pass.

## Phase A: seed inputs

- [The talk](understanding-bottleneck-talk.md) — Geoffrey Litt's
  *Understanding is the new bottleneck* (AI Engineer World's Fair 2026):
  source identification, an outline of its four proposals, and the sources
  it draws on.
- [Evidence and mechanisms](evidence-and-mechanisms.md) — what is lost
  (Naur, program-comprehension research, the AI-specific studies) and the
  learning-science mechanisms with evidence, ending in a
  mechanism-by-evidence table.
- [Landscape sweep](landscape-sweep.md) — a broad, shallow catalogue of
  tools, prototypes, proposals, practices, and discourse in nine emergent
  clusters, with the areas the seeds missed.
- [Answer.AI sweep](answer-ai-sweep.md) — Answer.AI's and fast.ai's thesis
  that understanding is built in small verifiable steps, its fifteen core
  claims, and the tools that embody it.
- [Solveit sweep](solve-it-sweep.md) — the product, its method, and the
  mechanics that invert the authorship default.

## Phase B: one deep pass per feature idea

- [In-loop friction](track-in-loop-friction.md) — friction inside the
  loop: step gates, pacing, generation-first interaction, and the
  authorship inversion outside notebooks.
- [Hand-off comprehension checks](track-hand-off-checks.md) — explainers,
  quizzes, teach-back gates, and diff-comprehension aids at commit, review,
  and merge.
- [A durable model over time](track-durable-model.md) — retrieval practice
  and spaced repetition on a living repository, and the invalidation
  problem.
- [Explorable maps and micro-worlds](track-explorable-maps.md) — code maps,
  tours, node-scoped questions, and agent-built environments for inhabiting
  a system.
- [Rationale as artifact](track-rationale-as-artifact.md) — living
  documentation, provenance capture, the dialog as artifact, and shared
  spaces.
- [Knowing it works](track-measurement.md) — instruments, proxies, survey
  items, metric proposals, and the arguments against measuring.

## Gap pass

- [Adjacent literatures](adjacent-literatures.md) — supervising automation
  (Bainbridge's ironies and what was measured since), cognitive offloading,
  and the motivational account.
- [Unfamiliar code and shared models](unfamiliar-code-and-shared-models.md)
  — the pre-AI research and practice on building a model of code one did not
  write, and on how a team holds a shared model.
- [Cowan, *More Work for Mother*](cowan-more-work-for-mother.md) — Ruth
  Schwartz Cowan's thesis that household technology relocated work rather
  than removing it, its evidence status, and where the corpus asserts the
  same pattern about AI coding without citing her.
- [Literature addendum](literature-addendum.md) — the 2025–2026 studies the
  earlier passes could not search for: professionals' comprehension and
  ownership, teach-back and LLM-graded explanations, evaluations of
  generated wikis and tours, approval gates and learning modes, retention,
  and motivation under delegation.
- [Discourse and tooling addendum](discourse-and-tooling-addendum.md) — the
  practitioner sweep the earlier passes could not reach: further PR-quiz and
  "prove you understand it" tools, company policies, 2025–2026 conference
  talks, 2026 essays and threads, provenance and attestation tooling, and
  manual-trigger defaults in editors and agent CLIs.

## The team lens

- [Chat-centric agents versus team development](chat-centric-agents-vs-team-sdlc.md)
  — who is writing about the mismatch between a private session as the
  unit of work and a team's shared Issues, Branches, Pull Requests, and
  review: Linear's and GitHub's issue-centric responses, the first
  measurement of single-human supervision of agent pull requests (78.9%),
  and the pre-agent history of the same fault line. Researched separately
  from the passes above; it supplies the individual-against-team tension
  with an AI-era measurement the corpus lacked.

## Phase C: the lifecycle and the team

Researched separately on 2026-09-15 to balance a corpus skewed toward one
person keeping a model of code an agent wrote: these notes take the team and
the lifecycle as their unit, and the work rather than the session. Each ends
in a mapping of its findings to where the earlier notes touch them, and each
is documentary — the [analysis](analysis.md) remains the only note that
takes a position.

- [Workspace awareness and coordination](workspace-awareness-and-coordination.md)
  — the CSCW definitions of awareness (who, what, where, and their
  histories), the coordination requirements awareness serves (Conway's law
  tests, socio-technical congruence, the awareness network), how the
  developer awareness tools were evaluated, what awareness information
  people measurably use, three generations of the chat-versus-tracker
  argument, and bots as awareness participants.
- [Flow, WIP limits and constraints](flow-wip-limits-and-constraints.md) —
  WIP limits, pull, batch size, the Theory of Constraints, the Definition of
  Done and stage gates as their own texts state them and as software teams
  measured them; batch size at review as the one place WIP meets
  comprehension evidence; and the stand-up and retrospective as knowledge
  transfer.
- [Handover between sessions, people, and agents](handover-between-sessions-people-and-agents.md)
  — what shift handover in mission control, nuclear plants, and hospitals
  transfers and loses (I-PASS's 23% fewer errors; the sender's most
  important item lost 60% of the time), interruption and resumption as
  handover to one's later self, common ground with a machine, and what
  agent-era compaction and handoff artifacts keep and drop.
- [Automation as a team player](automation-as-a-team-player.md) — the
  joint-activity strand's requirements (observability, directability,
  common ground, the ten challenges), coordination cost as measured in
  human–autonomy teaming, and the 2019–2026 AI-teammate and coding-agent
  studies that restate those requirements without citing them.
- [Review capacity and volume](review-capacity-and-volume.md) — reviewer
  hours before agents, arrival rates and review latencies since, curl's
  security-triage record, what project policies actually enforce (no
  numeric rate limit found beyond one three-PR rule), tooling sold as
  capacity, and the Jevons and rebound framing.
- [Ownership and accountability for delegated work](ownership-and-accountability-for-delegated-work.md)
  — the ownership–quality evidence and its replications, who signs for an
  agent change (the DCO, the kernel's rule, forge mechanics, vendor terms),
  licence positions on certifying agent output, and the first measurements
  of ownership feeling and modification survival under AI authorship.
- [Expert finding and transactive memory](expert-finding-and-transactive-memory.md)
  — Wegner's transactive memory and its meta-analyses, how developers
  locate an expert, whether expertise recommenders were evaluated on
  people, and the one survey of developers asking an AI instead of a
  colleague.
- [Apprenticeship under agents](apprenticeship-under-agents.md) —
  legitimate peripheral participation and cognitive apprenticeship, the
  economics of who pays for training, the contested payroll evidence on
  junior developer hiring, seniority in usage telemetry, the counter-evidence
  that the least experienced gain most, and firms' divergent practice.
- [Integration frequency and parallel branches](integration-frequency-and-parallel-branches.md)
  — pre-agent conflict rates (one in six to one in three), branch structure
  and quality, the frequency prescriptions and their evidence, merge queues
  as integration devices, what agent vendors say about worktree counts and
  landing order, and the first conflict measurements on agent-authored
  branches.
- [Team-level measurement](team-level-measurement.md) — SPACE, DevEx, and
  DORA as instruments and at what level they score, the team-cognition
  scales and how many teams validated them, the AI-era surveys' actual
  items, and the finding that nothing measures a team's shared model of its
  codebase.

## Synthesis and analysis

- [Synthesis](synthesis.md) — the documentary reading of the whole corpus:
  the loss as the sources define it, a three-axis map (where the friction
  lives × what it demands × how it is enforced) with evidence levels, the
  tensions the sources leave unresolved, and the gaps every pass left.
- [Analysis](analysis.md) — the evaluative counterpart, and the only note
  here that takes a position: Dashpot as an instrument for a flexible,
  AI-heavy but AI-optional lifecycle; the lifecycle in two layers against
  the demand axis; the principles the evidence supports; and the method
  for the candidates that follow. Revised after the themes note, whose
  changes are marked in place.
- [Thematic analysis: plan](thematic-analysis-plan.md) — the method for
  clustering the ideas across the whole corpus before candidates are
  drawn: a claim inventory, replicated blind clusterings by mechanism and
  by tension, a framed placement of every card, a mechanical clustering,
  and a reconciliation that separates the themes the frame already names
  from the cross-cutting ones it scatters.
- [Claim inventory](claim-inventory.md) — the plan's first deliverable:
  every research note decomposed into atomic idea cards (3,931 across the
  27 notes, one file per note under `claim-inventory/`), each in the
  note's own terms with its figures verbatim and a link to the section it
  was read from; extracted blind to the frame and sample-verified. Cite
  by card id.
- [Themes](themes.md) — the plan's second deliverable and the plan's
  result: the link-graph baseline, four blind clusterings and their
  agreement, the framed placement of every card, the robust groups
  sorted into confirmations of the frame and the themes the frame
  scatters, the connections the corpus does not draw, the fate of the
  held-out priors, and what all of it changes in the analysis.
- [Candidates](candidates.md) — the analysis's candidate stage: 91
  candidates across the map's twelve stages, each walked through the
  eleven lenses with a verdict on record; the 47 survivors reduced to
  twelve families, each with the assumptions it depends on and the
  cheapest test of each; the cross-cutting assumptions; and a sequence,
  pending the grilling the analysis calls for.

## Reading order

The evidence note and the landscape sweep are the shared vocabulary; the
track notes assume both. The gap notes are best read after the tracks, since
each ends in a mapping of its claims to where the tracks touch them. The
synthesis assumes all of them; the analysis assumes the synthesis. The
Phase C notes assume the team lens and the unfamiliar-code note, and can
be read in any order after those; the synthesis summarises them in its
own dated section and the analysis draws on them for the team's rows of
its map and its last four principles. The themes note assumes the
synthesis and the analysis, since it tests their frame; the claim
inventory is a reference, cited by card id, not a note to read through.
