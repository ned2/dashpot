---
status: research
date: 2026-09-16
---

<!-- The frame handed to the placement agent after the blind runs, as used on 2026-09-16; the frontmatter above and this comment are the only additions. -->

# The frame

## Three index themes

- T1 **Cognitive debt** — the loss of a developer's conceptual model of a codebase as agents author more of it, and the ideas, evidence, and tooling for keeping or rebuilding that model.
- T2 **The friction that keeps understanding** — intentional friction and where in a development lifecycle it belongs.
- T3 **Work above the session** — the shift from understanding held by a team, in the work, to understanding held by one person, in a session.

## Three axes

**Where the friction lives** (W): W1 task start; W2 inside the loop (each step); W3 hand-off (agent done, before commit or review); W4 review and merge; W5 continuous (scheduled, independent of any task); W6 onboarding and team (a person joining, or a model shared).

**What it demands of the person** (D): D1 generate or predict before seeing; D2 write; D3 explain (teach-back); D4 recall (retrieval); D5 verify or approve; D6 read; D7 navigate or ask; D8 nothing (the artifact exists).

**How it is enforced** (E): E1 a tool default; E2 an opt-in mode; E3 a personal practice; E4 a policy enforced socially; E5 a gate enforced by tooling.

## Tensions

- X1 Speed against understanding
- X2 Text against model (questions test the diff's text, not the model)
- X3 Expert against novice (expertise reversal)
- X4 Default against practice (willpower fails; defaults)
- X5 Artifact against act (docs outdated yet useful; the act of writing vs the artifact)
- X6 Measure against Goodhart
- X7 Interrupt against flow
- X8 Saved against relocated (work eliminated vs work moved to someone else)
- X9 Individual against team (every AI-era remedy is for one person)
- X10 Session against work graph (make the session multiplayer, or attach it to the issue and branch)
- X11 Rate against capacity (generation multiplicative, review linear)
- X12 A named person against many hands (every policy names one signer; barriers to accountability)

## Gaps (what no source does)

- G1 No study measures retention of a codebase model over weeks under agentic work
- G2 No study measures the comprehension effect of any approval gate or plan approval
- G3 No human evaluation of any generated wiki, map, or walkthrough
- G4 No tool connects code change to review scheduling; no spaced retrieval on a repository
- G5 No tool records that a person read a generated artifact
- G6 No validated instrument for ownership, motivation, or flow under delegation
- G7 No company describes an internal comprehension ritual with enforcement
- G8 No editor or agent CLI ships a manual-trigger-only or generate-first default
- G9 No source addresses code whose only author was never a person who could explain it
- G10 No AI-coding source cites the human-factors literature it restates
- G11 No source treats an automated actor as an awareness subject
- G12 No source measures what a human recovers from an agent's compaction summary or handoff artifact
- G13 No source measures the coordination cost a coding agent imposes on a human team
- G14 No before-and-after measure of reviewer hours per change
- G15 No instrument measures a team's shared model of its codebase
- G16 No source measures conflict or quality as a function of concurrent agent runs on one repository
- G17 No source measures whether a WIP limit or batch rule changes what a team member understands
