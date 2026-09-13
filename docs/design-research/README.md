---
status: living
date: 2026-09-13
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

## Synthesis and analysis

- [Synthesis](synthesis.md) — the documentary reading of the whole corpus:
  the loss as the sources define it, a three-axis map (where the friction
  lives × what it demands × how it is enforced) with evidence levels, the
  tensions the sources leave unresolved, and the gaps every pass left.
- [Analysis](analysis.md) — the evaluative counterpart, and the only note
  here that takes a position: Dashpot as an instrument for a flexible,
  AI-heavy but AI-optional lifecycle; the lifecycle in two layers against
  the demand axis; the principles the evidence supports; and the method
  for the candidates that follow.

## Reading order

The evidence note and the landscape sweep are the shared vocabulary; the
track notes assume both. The gap notes are best read after the tracks, since
each ends in a mapping of its claims to where the tracks touch them. The
synthesis assumes all of them; the analysis assumes the synthesis.
