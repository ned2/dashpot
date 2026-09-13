---
status: living
date: 2026-09-13
---

# Cognitive debt: research index

Breadth-first research into *cognitive debt* — the loss of a developer's
conceptual model of a codebase as agents author more of it — and into the
ideas, evidence, and tooling that engage with keeping or rebuilding that
model. This is the exploration phase of a design effort; nothing here
assesses fit for Dashpot or for any particular flavour of agentic
engineering. Each note is a dated `research` document: true as of its date,
corrections marked inline as `(corrected 2026-09-13: …)`, and every claim
cited to a primary source, with dead ends recorded so a later pass does not
repeat them. Notes cite one another with relative links rather than
repeating material.

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
