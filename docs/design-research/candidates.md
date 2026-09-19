---
status: proposal
date: 2026-09-17
---

# Design candidates

The candidate stage the [analysis](analysis.md#4-method-for-what-follows)
calls for. The analysis fixed the thesis, the lifecycle map, fifteen
principles, and eleven lenses; this note generates candidates per lifecycle
stage, walks each through the lenses, and reduces the survivors to the
assumptions they depend on and the cheapest test of each. Nothing here is a
feature proposal: the shortlist is grilled — by the user and by an
independent second opinion — before anything is proposed.

## Method

**Stages.** The twelve rows of the analysis's
[map](analysis.md#the-map-lifecycle-stage-against-demand), with a short code
used in candidate ids:

| Code | Stage | Map row |
| --- | --- | --- |
| IS | Issue declared | Issue declared |
| ST | Session or work starts | Session / work starts |
| IL | In-loop step | In-loop step |
| HO | Hand-off, agent done and before the Pull Request | Hand-off (agent done, pre-PR) |
| RV | Pull Request review and merge | PR review / merge |
| IN | Integration and Cleanup | Integration / Cleanup |
| SB | Session boundary: stop, relocate, end | Session boundary |
| AR | Arrival at review: rate and WIP | Arrival at review |
| RT | Return after absence | Return after absence |
| MR | Module revisit | Module revisit |
| PD | Periodic | Periodic |
| JN | A person joining, or handing over | Person joining / handover |

**Generation.** Wide, then narrow. Each stage gets five to eight candidates
drafted from the corpus, including the obvious ones the map's cells name, so
that a rejection is on record with its reason rather than implied by
absence. Drafting was delegated to four agents, one per group of three
stages, each given the analysis, the [themes](themes.md), the domain language, the
current observation model, and the claim inventory, and asked to ground
every mechanism and every figure in a card id and to take no position. The
lens walk and the verdicts are the session's, and every card id a verdict
leans on was checked against the inventory.

**The card.** One per candidate, in this order, so that candidates are
comparable line by line:

- **Stage and cell** — the map row and demand column, with the map's
  O / N / M mark.
- **What it is** — what happens, who performs it, when it fires, and the
  act it asks of a person (principle 1). A candidate that asks for no act
  says so.
- **Mechanism and evidence** — the mechanism it rests on, the cards that
  carry it, and the evidence level of the best card.
- **Nearest existing thing** — the tool, practice, or proposal in the corpus
  closest to it, by card id, and how the candidate differs.
- Then the eleven lenses of the
  [method](analysis.md#4-method-for-what-follows), one line each:
  authorless code; grain; demand; enforcement and relocation; decay;
  verifiability; evidence source; lifecycle hook; without AI; coordination
  cost; social form.
- **Verdict** — *shortlist*, *hold*, or *reject*, with the lens that
  decided it. A *hold* is a candidate that fails no lens but depends on
  another candidate or on the person's-act record (principle 6) landing
  first.

**Shortlist.** A candidate survives if it names an act or a bound
(principle 1 or 14), passes the authorless-code lens, attaches to a shared
object rather than only a session (principle 9), is worth having on a
human-authored branch (principle 11), and carries an instrument (principle
7). Each survivor is then reduced to the assumptions it depends on and the
cheapest test of each assumption, in the final section.

## Candidates by stage

### Issue declared (IS)

#### IS-1 Restate the Issue before binding
- **Stage and cell**: Issue declared / Explain — "restate the problem before binding" (N).
- **What it is**: Before `work start`, the person writes, in their own words, what the Issue asks and what done looks like, then asks the agent "did I miss anything?". The restatement is posted as a comment on the Issue (the shared object at the Issue Source), so it precedes the Issue Binding rather than following it. The act is generative: the person produces the restatement before the agent produces a plan.
- **Mechanism and evidence**: Pólya's "understand the problem" step (N02:4) and solve.it's read-restate-ask sequence (N17:40); restating is a practice, not a tool feature, in the Answer.AI corpus (N02:130). Kazemitabaar's most effective technique was the learner stating what must happen next before code is revealed (N08:59, C). Generation effect d=0.40 (N08:88, C), reversing when generation fails (N08:89). Best card: C.
- **Nearest existing thing**: emanzurv quiz-me asks root cause and fix in a three-question round before writing a fix, at task start (N07:8); Cursor Plan mode produces the plan and clarifying questions before execution (N13:79). Both have the agent generate; this has the person generate and the agent check.
- **Authorless code**: Independent of who wrote existing code; the object is the Issue text and the person's model of the change.
- **Grain**: Issue.
- **Demand**: Explain/generate, before any agent output is shown.
- **Enforcement and relocation**: Skill step in `dashpot-issue-work` before `work start` (SKILL.md); the bill is one comment per Issue; can relocate to a one-line paraphrase (N11:57: most verbal handoffs did not adhere to the mnemonic).
- **Decay**: The comment goes stale as the Issue evolves; the practice decays by habituation — no card measures restatement fatigue.
- **Verifiability**: The agent's "did I miss anything?" checks the restatement against the Issue; nothing checks it against code. No card on scoring a restatement.
- **Evidence source**: Issue Source (the comment); Dashpot's Issue Profile refresh observes that a comment exists, not its content.
- **Lifecycle hook**: `issue show` → restate → `work start` (SKILL.md order).
- **Without AI**: Yes; Pólya predates AI (N02:4).
- **Coordination cost**: Communication overhead of one comment (N04:27); none for others unless they read it.
- **Social form**: The binder alone, visible to the team.
- **Verdict**: *Shortlist, paired with HO-3.* A generative act with C-level support, on the Issue, worth having without an agent, at the thinnest row of the map (principle 2 makes it a bet). Alone it lacks an instrument: nothing scores a restatement, and the agent's "did I miss anything?" checks it against the Issue text the person just read (principle 3). Paired with HO-3 — the person's own Pull Request description at hand-off — it gains one: the person's account at both ends of the Issue, compared for what changed in their model between binding and hand-off.

#### IS-2 Recall the module's last touch before binding
- **Stage and cell**: Issue declared / Recall — "recall the last touch of the module" (N).
- **What it is**: When the Issue names or implies modules, the person states from memory who or what last changed them, when, and why, before the agent shows `git log`. The comparison is then shown. Asked once per Issue Binding.
- **Mechanism and evidence**: Retrieval practice applied to a codebase — state from memory which module owns state or why a boundary exists before opening the file (N08:75); retrieval must succeed or be followed by feedback and learners do not choose it spontaneously (N08:74, C); retrieval before reveal is the remedy for the illusion of competence (N08:115, C). Programmers resuming look for recent changes (N11:83) but consulted revision history in only 4% of edit lags (N11:87, M). Best card: C.
- **Nearest existing thing**: Agent Handoff's run start reads Issue, PR, branch and recent commits before touching code (N11:127) — a read, not a recall; `bd prime` prints context at session start (N11:124).
- **Authorless code**: Authorship no longer implies comprehension (N08:22; N13:95), so the recall is of the change and its reason, not of a name in blame.
- **Grain**: Module.
- **Demand**: Recall, answer hidden.
- **Enforcement and relocation**: Skill step; relocates to "don't know" answers — Karpicke's condition is that retrieval be followed by feedback (N08:74), so a miss still yields the log.
- **Decay**: Items are invalidated by every edit (N08:84); the question is regenerated per binding so it does not go stale.
- **Verifiability**: Checked against Git history; the "why" is checked only if a commit message or Issue carries it (N08:20: why-questions most often unanswered).
- **Evidence source**: Git (the answer); no channel records the person's guess unless the skill writes it to the Issue.
- **Lifecycle hook**: Between `issue show` and `work start`.
- **Without AI**: Yes; the mechanism is pre-AI (N08:69–N08:74).
- **Coordination cost**: None beyond the binder's time (N11:86: edit lag already exceeds 30 minutes in ~30% of sessions).
- **Social form**: Individual.
- **Verdict**: *Shortlist.* A recall with the answer hidden, scored by Git itself, needing no judge; independent of who wrote the code because it asks for the change and its reason, not a name; pre-AI mechanism, so it holds on a human-authored branch. The miss is the instrument (principle 7) and the miss rate per person per module is the record principle 10's fading needs. Attaches to the Issue if the skill posts the guess; without that it is session-only, so the post is part of the candidate. Same device as ST-1 and the return-after-absence row (RT): one mechanism, three firing points.

#### IS-3 Commentable plan on the Issue before binding
- **Stage and cell**: Issue declared / Verify-approve (N; the map has no cell for team plan review at this row).
- **What it is**: The agent drafts a plan as a comment on the Issue; a second named person comments or objects before the binder runs `work start`. The act asked of the binder is to wait; the act asked of the second person is to read and comment.
- **Mechanism and evidence**: Litt's one concrete mechanism — agent plans in a collaborative Notion page, commentable by the team immediately (N24:144; N25:41). Goal negotiation and incremental collaborative planning are challenges 7–8 (N04:43, N04:44, A). Plans are rejected 39% of the time versus 3% for permissions (N22:38; N14:71, vendor telemetry). The only controlled plan-mode study found similar outcomes, less refinement, no comprehension measure (N14:77, C). HumanLayer's leverage argument: a bad plan lands thousands of bad lines (N11:135, T). Best card: C, but not on comprehension.
- **Nearest existing thing**: Notion External Agents assign tasks from shared boards (N24:146); Linear sessions start from the Issue with context attached (N05:34). Neither requires a second person's comment.
- **Authorless code**: Applies regardless of prior authorship.
- **Grain**: Plan.
- **Demand**: Read and verify, on the reviewer.
- **Enforcement and relocation**: Skill instruction or Issue Source convention; relocates to rubber-stamp comments — N11:66 reports incoming clinicians asked no questions in most handoffs.
- **Decay**: The plan comment goes stale as work diverges; no change signal.
- **Verifiability**: A comment exists or not; whether it engaged the plan is unmeasured (N14:5).
- **Evidence source**: Issue Source comment; Dashpot's Issue Profile refresh.
- **Lifecycle hook**: Before `work start`.
- **Without AI**: Yes — design review before generation is proposed pre-agent (N13:86).
- **Coordination cost**: Synchronisation overhead: the binder waits on another person (N04:27).
- **Social form**: Pair or team; a named person comments.
- **Verdict**: *Hold*, on verifiability and on demand. The plan is the agent's; the binder's act is to wait and the second person's is to read, and a comment's existence does not show engagement (N14:5, N11:66). It is the team-shaped form of task start and the nearest thing to Linear's model in the corpus, so it is held rather than rejected: it becomes a shortlist candidate if the second person's comment is an *ask* or a *prediction* (IS-4, IL-8's form) rather than a read, which gives it an act and an instrument.

#### IS-4 Name the person to ask before binding
- **Stage and cell**: Issue declared / Explain–Recall (N).
- **What it is**: If the Issue touches a module the binder has not changed, the skill asks the binder to name a person who holds that module's theory and to ask them one question before `work start`. The name and answer go on the Issue.
- **Mechanism and evidence**: Rationale is socially held and recovered by interrupting teammates (N08:19, Q; N08:26); Naur's remedy is contact with theory-holders (N08:8, A). Common ground is repaired by asking, not documenting (N04:30; N11:93). Cataldo proposes a dynamic buddy list when particular parts are modified (N27:43, M). Best card: Q.
- **Nearest existing thing**: Kognita's knowledge-concentration index (N13:54, promotional); Linear's assignee-stays-responsible rule (N15:13) names who is responsible, not whom to ask.
- **Authorless code**: Cuts against blame-derived ownership (N08:21 vs N08:22): the person is named by the binder, not inferred from Git.
- **Grain**: Module.
- **Demand**: Explain (by the holder) and read (by the binder).
- **Enforcement and relocation**: Skill step; relocates to naming oneself; the bill is one interruption (N27:71: developers blocked a median of four times per session).
- **Decay**: Names go stale with team change (N08:6); refreshed per Issue.
- **Verifiability**: Whether a question was asked is visible; whether it built a model is not — no card.
- **Evidence source**: Issue Source comment.
- **Lifecycle hook**: Before `work start`.
- **Without AI**: Yes (N08:19 predates AI).
- **Coordination cost**: Communication and synchronisation overhead on the holder (N04:27); no measurement for humans with coding agents (N04:149).
- **Social form**: Pair; named person.
- **Verdict**: *Shortlist.* The one candidate at this row that records an ask (principle 9's routing corollary) with a person's name declared, not inferred (principle 15 and the widened authorless-code lens). The instrument is the ask itself: who was asked about which module, over time, is the team's directory made observable, which no locating instrument in the corpus does without the authorship inference. Cost is one interruption on the holder; the bill is visible. Pre-AI mechanism. Depends on ST-6's person identity.

#### IS-5 A WIP bound on Issue Bindings
- **Stage and cell**: Issue declared / Nothing-artifact (a bound, principle 14).
- **What it is**: A person may hold at most N active Issue Bindings (Agent Runs with `work start` and no `work stop`); the skill reports the count from the Work Store at `work show` and instructs the agent to refuse a new binding above the bound. Asks the person to finish or stop before starting.
- **Mechanism and evidence**: Kanban pull — an item starts only when a WIP slot is free and item age begins at Issue declared (N10:135; N10:136); DORA small batches under a week (N10:73). Coordination costs outweigh freshness (N04:28, A). Per-prompt fan-out is ~10 actions (N14:34, M). No card measures a WIP bound's effect on comprehension (N10:95). Best card: M.
- **Nearest existing thing**: Kanban WIP limits (N10:135); Anthropic's worktree-per-task with non-overlap assumed (N12:68).
- **Authorless code**: Neutral.
- **Grain**: Issue.
- **Demand**: Nothing asked at the step; a bound on starting.
- **Enforcement and relocation**: Skill instruction; ADR 0008 — Dashpot observes the Work Store and refuses nothing. Relocates to `work stop` then immediate restart, or to work outside a binding.
- **Decay**: A bound is a default (principle 4); no card on WIP-limit decay.
- **Verifiability**: The count is checkable from the Work Store (`.dashpot/state/work/`, agent-sessions.md).
- **Evidence source**: Work Store; Dashpot Agent Run observation.
- **Lifecycle hook**: `work show` before `work start`.
- **Without AI**: Yes — WIP limits are pre-AI.
- **Coordination cost**: Reduces the number of threads a person tracks (N04:54).
- **Social form**: Individual bound, visible to the team in Dashpot.
- **Verdict**: *Shortlist, folded into the AR bound family.* A bound (principle 14) resting on an observed fact — the Work Store already counts Agent Runs per person — which makes it the cheapest bound Dashpot could show. Principle 14 is single-note, but the WIP evidence here comes from N10 with N04 beside it, so it has its second source. Without AI the Work Store records nothing, so its AI-optional form is the open-PR bound at AR; the two are one candidate with two counters.

#### IS-6 Issue Profile shows binding age and last act
- **Stage and cell**: Issue declared / Nothing-artifact — Issue Profile (O; signal: Issue Source refresh).
- **What it is**: Dashpot's Issue Profile displays, per Issue, when the Issue Binding was made, by which Agent Session Identity, and the last observed lifecycle event. It asks no act; it is a display.
- **Mechanism and evidence**: Observability — status and knowledge made observable (N04:61; N04:16, A); data availability does not equal informativeness (N04:17). Linear nests session status under the Issue and keeps the human assignee responsible (N05:3; N05:33, T); GitHub shows agent sessions beneath assignees (N05:4). Best card: T.
- **Nearest existing thing**: Linear coding sessions (N05:34); Dashpot's own Issue Profile and Work Store (domain-language.md).
- **Authorless code**: Neutral; displays binding, not authorship.
- **Grain**: Issue.
- **Demand**: None — display before demand (principle 1 names this as the failure mode).
- **Enforcement and relocation**: Nothing to enforce; nothing relocates.
- **Decay**: Refreshed on Issue Source refresh and hook events; a display habituates (N04:34: nuisance signals get removed).
- **Verifiability**: The display is checkable against the Work Store; no act to verify.
- **Evidence source**: Work Store and hook publisher (agent-sessions.md).
- **Lifecycle hook**: Issue Source refresh; SessionStart/SessionEnd.
- **Without AI**: The binding exists only when an Agent Session opts in; without AI there is nothing to show.
- **Coordination cost**: Lowers diagnosis overhead for others (N04:27).
- **Social form**: Team display.
- **Verdict**: *Reject*, on demand. It asks no act (principle 1). It is a display improvement to the Issue Profile and belongs on the ordinary backlog as the observability half of principle 12; it is not a member of this family.

#### IS-7 Issue quiz before binding
- **Stage and cell**: Issue declared / Verify-approve (N).
- **What it is**: The agent generates three questions from the Issue text and the person answers them before `work start`. Included as the obvious quiz form at this row.
- **Mechanism and evidence**: emanzurv quiz-me's three-question round before a fix (N07:8, T); retrieval and testing effects (N08:69; N08:71, C). But the questions are generated from and graded against the Issue text, which the person has just read — the foresight-bias condition (N08:111; N08:113). N13:116 leaves open whether generated questions test the model rather than the text. Best card: C, for the mechanism, not this application.
- **Nearest existing thing**: N07:8; Covate blocks the agent until a card is completed at any score (N13:16).
- **Authorless code**: Neutral — the object is the Issue, not code.
- **Grain**: Issue.
- **Demand**: Recognise/recall, answer visible in the Issue.
- **Enforcement and relocation**: Skill step; relocates to re-reading the Issue while answering.
- **Decay**: Habituation to quizzes: Learning Opportunities self-suppresses after one decline (N13:13); gates dismissed 62% mid-task (N22:104).
- **Verifiability**: The model both asks and grades (N07:6 pattern); no judge–human agreement figure for such gates (N14:51).
- **Evidence source**: None in Dashpot's channels unless the skill posts the result to the Issue.
- **Lifecycle hook**: Before `work start`.
- **Without AI**: The quiz needs a generator; without AI it would be hand-written — no card.
- **Coordination cost**: None.
- **Social form**: Individual.
- **Verdict**: *Reject*, on verifiability. The questions are drawn from and graded against the Issue text with that text on screen: the confidence-gap condition (principle 3, N08:111). IS-1 and IS-2 are the answer-hidden forms at this row.

### Session or work starts (ST)

#### ST-1 What changed here since your last run
- **Stage and cell**: Session/work starts / Recall — "what changed since last run here" (O for Git; N for "read").
- **What it is**: At `work show` or `work start`, the skill has the agent find the person's previous Agent Run on this Issue (Work Store) and ask the person to say what they expect to have changed in the Worktree and Branch since then; then the diff and commits since that run are shown. Asks a recall before a read.
- **Mechanism and evidence**: On resuming, programmers re-read notes, navigate, and look for recent changes (N11:83, M); edit lag exceeded 30 minutes in ~30% of sessions and only 4% consulted revision history (N11:86; N11:87, M). Plan restoration uses diffs and change history (N11:88). Retrieval before reveal (N08:115, C). Handovers after a ten-day rest were longer and added history (N11:33). Best card: C.
- **Nearest existing thing**: Agent Handoff's run-start reading list (N11:127); Claude Code re-reads up to five files after compaction (N11:99). Both read; neither asks first.
- **Authorless code**: Applies to changes by anyone — other people, other Agent Runs, the person's own.
- **Grain**: Branch/Worktree since a run.
- **Demand**: Recall then read.
- **Enforcement and relocation**: Skill step; relocates to skipping the guess — the diff is shown anyway.
- **Decay**: Regenerated per session; cannot go stale.
- **Verifiability**: The guess is checked against Git.
- **Evidence source**: Git plus Work Store (previous run's timestamps).
- **Lifecycle hook**: SessionStart hook or `work show` step (agent-sessions.md; SKILL.md).
- **Without AI**: Yes — the recall and the diff exist without an agent.
- **Coordination cost**: None; it is a self-handover (N11:70).
- **Social form**: Individual.
- **Verdict**: *Shortlist.* A recall before a read, scored against Git, regenerated per session so it cannot go stale, pre-AI, and a self-handover that needs no second person. It is IS-2's mechanism fired at a different boundary, and the same device the return-after-absence row (RT) names; the three firing points are one candidate whose test is whether the guess-then-diff changes what a person can later say about the Branch.

#### ST-2 The skill carries the stage's acts
- **Stage and cell**: Session/work starts / Nothing-artifact — skill-carried lifecycle instructions (O; signal: versioned with repository).
- **What it is**: The acts of IS and ST candidates live in `dashpot-issue-work` and AGENTS.md, versioned and reviewed like code, installed by `dashpot integrate <harness>` (SKILL.md). It asks no act of its own; it is the carrier.
- **Mechanism and evidence**: AGENTS.md is a human-written README for agents used by 60k+ projects (N13:62; N24:45, T); adding agent instructions appears in 2.1% of OSS AI policies (N21:149, M). Böckeler separates guides (Markdown for the agent) from sensors (automated feedback) and deletes guides once sensors are trusted (N24:63; N24:64, T). Skill bodies are re-injected after compaction, capped at 5,000 tokens each (N11:99). Best card: T.
- **Nearest existing thing**: The learning-output-style plugin's SessionStart hook injecting 5–10 lines of instruction (N22:45; N22:46); Beads' AGENTS.md snippet (N11:125).
- **Authorless code**: Neutral.
- **Grain**: Repository.
- **Demand**: None.
- **Enforcement and relocation**: The skill is an instruction the model may not follow; Tang et al. find Developer Constraint Violation in 38.33% of misalignment episodes (N04:117, M).
- **Decay**: A guide decays when no sensor checks it (N24:64); versioning shows change, not adherence.
- **Verifiability**: Whether the skill ran is not observed — Dashpot's hooks report lifecycle events only (agent-sessions.md); no card.
- **Evidence source**: Git history of the skill file.
- **Lifecycle hook**: SessionStart (skill injection) and every skill step.
- **Without AI**: The skill exists only for agents; the practices it carries may not.
- **Coordination cost**: Team agreement on the skill text.
- **Social form**: Team, via review of the skill.
- **Verdict**: *Reject as a candidate; recorded as a shared assumption.* It asks no act; it is the carrier every skill-step candidate rides on. What it exposes is the assumption they all share and none can verify today: that the skill ran and the step was performed. Dashpot's hooks see lifecycle events, not skill steps, and constraint violation runs at 38% of misalignment episodes (N04:117). Every skill-carried candidate's cheapest test starts with an observable trace that the step happened.

#### ST-3 Start in plan mode by default
- **Stage and cell**: Session/work starts / Verify-approve (O in the harness; M for the default).
- **What it is**: The repository sets the harness's default permission mode to plan (`defaultMode: plan`, N22:33) so every Agent Session begins by producing a plan the person approves before edits. The act is reading and approving or rejecting a plan.
- **Mechanism and evidence**: Plans are rejected far more than permissions — 39% vs 3% (N22:38; N14:71, vendor telemetry). Cursor's docs recommend Ask-then-Agent (N13:79; N13:58). The one controlled plan-mode study found similar outcomes, less refinement, better tool perception, no comprehension measure (N14:77, C). Sheridan–Verplank levels 5–7 by another name (N01:71). Best card: C.
- **Nearest existing thing**: Cursor Plan mode (N13:79); HumanLayer's research-plan-implement with files reviewed by a person (N11:134).
- **Authorless code**: Neutral.
- **Grain**: Plan.
- **Demand**: Read and approve.
- **Enforcement and relocation**: Harness setting versioned in the repository (`.claude/settings.json` per N24:72) — ADR 0008: external to Dashpot. Relocates to approving plans reflexively; the 39% rejection rate is the current evidence against.
- **Decay**: A default holds until a person changes it; 25% of sessions start in bypass mode (N14:73).
- **Verifiability**: Approval is recorded by the harness, not checked for understanding (N14:5).
- **Evidence source**: Harness; Dashpot does not see plan approval.
- **Lifecycle hook**: SessionStart.
- **Without AI**: No plan mode without an agent, though written plans predate it.
- **Coordination cost**: Redirection overhead paid up front (N04:27).
- **Social form**: Individual.
- **Verdict**: *Reject*, on lifecycle hook and without-AI. A harness default Dashpot neither sets nor observes, with no comprehension effect measured for any plan gate (N14:77, gap G2), and nothing to approve on a human-authored branch. Principle 2: an in-loop bet, and not one this family can place.

#### ST-4 Record the stance at start
- **Stage and cell**: Session/work starts / Explain (N).
- **What it is**: At `work start` the person writes two lines on the Issue: the approach they intend and the condition under which they would stop or change course. The next holder — a later session or another person — reads it first.
- **Mechanism and evidence**: What transfers at handover is a state model plus a stance (N11:1, A); the outgoing team's stance toward contingencies was given in every observed mission-control handoff (N11:10, M) and is not a named field in any documented agent schema (N11:148). The sender's most important item fails to arrive 60% of the time while the sender believes it did (N11:50, M). Best card: M.
- **Nearest existing thing**: Agent Handoff's "Risks" and "Next direct outcome step" fields (N11:129; N11:132); HumanLayer's `progress.md` (N11:133). Both are written at the end; this is written at the start.
- **Authorless code**: Neutral.
- **Grain**: Issue/session.
- **Demand**: Explain.
- **Enforcement and relocation**: Skill step; relocates to boilerplate — Chang et al. found parties disagreed on rationale 60% of the time despite high self-ratings (N11:52).
- **Decay**: Stale once the approach changes; the Issue thread shows the sequence.
- **Verifiability**: Whether the stated stop condition was honoured is checkable at `work stop`; no card.
- **Evidence source**: Issue Source comment.
- **Lifecycle hook**: `work start`.
- **Without AI**: Yes (N11:10 is pre-AI).
- **Coordination cost**: One comment; lowers diagnosis overhead for the next holder (N04:27).
- **Social form**: Individual, for the next holder.
- **Verdict**: *Hold, merged into SB's handover.* Passes demand, authorless, without-AI, and attaches to the Issue; but its evidence is one note (N11) and principle 13 is single-note, so it needs a second source, and its instrument — was the stop condition honoured at `work stop` — only exists once the session-boundary statement exists. Stance at start and state-and-stance at stop are the two ends of one candidate.

#### ST-5 Ask the person's familiarity, then fade
- **Stage and cell**: Session/work starts / Explain (N).
- **What it is**: At start the agent asks how well the person knows the modules the Issue touches, and the skill scales the in-loop asks (IL-5, IL-8) accordingly — fewer for a holder of the theory, more for a newcomer. The act is a self-rating.
- **Mechanism and evidence**: Expertise reversal — guidance that helps novices becomes redundant or harmful for experts (N08:102, C; N08:103); agent output as worked example for the unfamiliar, generation-first for the theory-holder (N08:104). Solve.it's Learning mode asks background (N17:60, T). METR's slowdown was largest on familiar code (N08:36). Self-ratings are miscalibrated (N08:114). Best card: C.
- **Nearest existing thing**: Solve.it Learning mode (N17:60); learn-codebase's Confused/Learning/Confident journal (N13:12).
- **Authorless code**: Familiarity is asked, not inferred from authorship.
- **Grain**: Module.
- **Demand**: Explain (self-report).
- **Enforcement and relocation**: Skill instruction; relocates to claiming expertise to skip asks — foresight bias (N08:111).
- **Decay**: A rating per session; no stored profile unless written.
- **Verifiability**: Unverifiable at the time; IL acts later test it.
- **Evidence source**: None in Dashpot channels; the skill could post to the Issue.
- **Lifecycle hook**: `work start`.
- **Without AI**: No agent, no ask; the fade principle applies to any onboarding.
- **Coordination cost**: None.
- **Social form**: Individual.
- **Verdict**: *Hold*, on verifiability. Fading is right (principle 10) but a self-rating is the wrong input: self-assessed understanding correlates with held understanding at .26 or less (principle 3, principle 7), and the relocation is to claim expertise and skip. Fading should be driven by the recorded misses of IS-2 and ST-1 rather than by asking. Held until an act record exists to fade against.

#### ST-6 A named person signs the binding
- **Stage and cell**: Session/work starts / Verify-approve (O: `work start`).
- **What it is**: `work start` is preceded by the person confirming, by name, that they hold this Issue for this Agent Run; the skill posts "held by <person>" on the Issue. The Agent Session Identity is the harness's; the signature is a person's.
- **Mechanism and evidence**: Linear keeps a human assignee responsible when delegating to an agent (N05:33; N15:13, T) and is the only tracker documentation found that does (N15:14). Accountability lowers the autonomy developers accept (N14:20, T; N15:100). Unambiguous transfer of responsibility — the seat, the headphone jack (N11:14, M). Best card: T.
- **Nearest existing thing**: Linear assignee rule (N15:13); the Work Store's Issue Binding (domain-language.md) — whether it records a person's name: no card.
- **Authorless code**: Directly addresses it — responsibility is declared, not read from `git blame` (N08:22).
- **Grain**: Issue.
- **Demand**: Verify/approve (a signature).
- **Enforcement and relocation**: Skill step; relocates to an agent posting the name unattended — the hook cannot distinguish.
- **Decay**: A signature per binding; stale if the Issue is handed over without a new one.
- **Verifiability**: The comment's author at the Issue Source is checkable.
- **Evidence source**: Issue Source; Work Store for the binding.
- **Lifecycle hook**: `work start`.
- **Without AI**: Yes — assignment predates agents.
- **Coordination cost**: None.
- **Social form**: Named person.
- **Verdict**: *Shortlist.* The prerequisite for the whole family: every act principle 6 records needs a person to attach to, the Issue Binding today names an Agent Run, and principle 15 is among the best-sourced in the corpus. The act is a signature; the instrument is the comment's author at the Issue Source, or a person field in the Work Store record. Cheap, pre-AI, and it fixes what Linear's model gets right that Dashpot's Issue Binding does not.

#### ST-7 Inject a generated codebase summary at SessionStart
- **Stage and cell**: Session/work starts / Read-navigate (N).
- **What it is**: A SessionStart hook injects a generated wiki or onboarding summary of the modules the Issue touches, for the person and agent to read. Asks no act.
- **Mechanism and evidence**: DeepWiki and Google Code Wiki regenerate on change (N13:45; N13:46, T); `/team-onboarding` generates a ramp-up guide (N07:31, T); the learning-output-style plugin injects via SessionStart (N22:45). No human evaluation of any generated wiki was found (N14:56); LLM evaluation of tours was unreliable (N14:53, Q); the one human quiz on generated tours scored 57% vs 83% for expert-guided (N14:55, C, n=5). Understanding is a side effect of the artifact existing, not checked (N13:6). Best card: C, small n.
- **Nearest existing thing**: DeepWiki (N13:45); Codemaps as task-scoped snapshot (N20:6; N13:43).
- **Authorless code**: Neutral.
- **Grain**: Module.
- **Demand**: Read, nothing asked before display (principle 1).
- **Enforcement and relocation**: Hook; nothing relocates because nothing is asked.
- **Decay**: Regenerated content can rewrite a human's intent silently (N13:120); whether it is read is unknown (N13:118).
- **Verifiability**: Reading is not verified (N07:102: no study logs which lines a reviewer viewed).
- **Evidence source**: Hook publisher sees SessionStart only.
- **Lifecycle hook**: SessionStart.
- **Without AI**: The summary needs a generator.
- **Coordination cost**: None.
- **Social form**: Individual.
- **Verdict**: *Reject*, on demand and decay. No act, an uncoupled generated artifact ([themes 5.1](themes.md#51-staleness-without-a-trigger)), and no human evaluation of any generated wiki (gap G3).

### In-loop step (IL)

#### IL-1 Promote rather than accept
- **Stage and cell**: In-loop step / Generate — "promote rather than accept" (M: harness-side).
- **What it is**: Agent-produced code is inert until the person promotes it into the Worktree; nothing lands by default. The act is a promotion per hunk or per step.
- **Mechanism and evidence**: Solve.it's Default Code toggle and inert code that a keypress extracts (N17:57; N17:59, T); copilot.lua ships manual-trigger-only completions as its plugin default (N07:84); no editor default and no vendor announcement of a solve.it-style default (N07:95; N07:94). Ward's writing-first or 25-second delay eliminated knowledge misattribution (N01:92, C). Retyping LLM code, ~2× faster only (N07:63, T). Best card: C.
- **Nearest existing thing**: Cursor Ask mode (N13:58); Hunk as an agent-to-git gate before commit (N13:41). Hunk gates the commit; this gates the Worktree.
- **Authorless code**: Neutral.
- **Grain**: Hunk or step (N22:91 names five grains).
- **Demand**: Verify then generate the promotion.
- **Enforcement and relocation**: Harness or plugin default (E1) — ADR 0008: Dashpot cannot supply it; the hook publisher's PostToolUse covers only EnterWorktree/ExitWorktree (agent-sessions.md). Relocates to promote-all after habituation (N14:72: blocking of dangerous commands fell from 17% to 5% after 50 prompts).
- **Decay**: Defaults decay (N14:70: auto mode is now the default; N14:73: 25% of sessions start in bypass).
- **Verifiability**: A promotion is an act, not evidence of a model; no study measures understanding as a function of hunk approval (N14:5).
- **Evidence source**: Harness; none in Dashpot.
- **Lifecycle hook**: Every edit.
- **Without AI**: Nothing to promote without an agent.
- **Coordination cost**: None; individual redirection overhead.
- **Social form**: Individual.
- **Verdict**: *Reject*, on lifecycle hook and without-AI. The authorship inversion is the loop's one unbuilt idea (principle 2), but it is a harness-side default Dashpot cannot set or observe, and there is nothing to promote without an agent. Recorded as a harness gap, not a Dashpot candidate.

#### IL-2 The agent asks before proceeding
- **Stage and cell**: In-loop step / Explain–Verify — "agent asks before proceeding" (M: skill/hook).
- **What it is**: At step boundaries the skill instructs the agent to stop and ask one question — "did I miss anything?" or a goal-negotiation question — and not auto-continue. The act is an answer.
- **Mechanism and evidence**: Claude Code 2.1.200 made AskUserQuestion not auto-continue (N22:129; N07:91, T). Goal negotiation is challenge 7 (N04:43, A); notify-before-proceeding is an OPD requirement (N04:63). Zhou et al.: 81% preferred intermediate confirmation (N14:76, C, not coding). Kuo: 52% engaged at boundaries, 62% dismissed mid-task (N22:104). Against: asking one who cannot judge yields an illusion of control (N02:26). Incoming controllers' questions detected errors (N11:16, M). Best card: C.
- **Nearest existing thing**: AskUserQuestion default (N07:91); Vibe Check's agent-side pause (N13:78, claimed effects).
- **Authorless code**: Neutral.
- **Grain**: Step.
- **Demand**: Explain/verify, framed by the agent.
- **Enforcement and relocation**: Skill instruction; a Stop hook can block continuation (N22:39). Relocates to "yes" — N01:64 collects the "clicking through" sources.
- **Decay**: Habituation (N14:72); no card on question fatigue specifically.
- **Verifiability**: The answer is checked by nothing; N22:137 and N22:146: no comprehension measure of gates.
- **Evidence source**: Harness transcript, deleted after 30 days (N11:108); Dashpot sees Stop events only.
- **Lifecycle hook**: Stop / step boundary.
- **Without AI**: No agent, no asker.
- **Coordination cost**: Communication overhead per step (N04:27; N04:112: 20% of agent steps went to communication).
- **Social form**: Individual.
- **Verdict**: *Reject*, on without-AI and social form. The directability half of principle 12 belongs in the skill's design and in the harness's AskUserQuestion default; as a friction it is unverifiable, individual, and mid-task, where 62% dismiss (principle 5).

#### IL-3 Permission gates on named actions
- **Stage and cell**: In-loop step / Verify-approve — "permission gates" (O via hooks, unmeasured).
- **What it is**: A PreToolUse hook returns `ask` for a short list of named actions (push, migration, deletion) and `allow` otherwise, so the gate fires rarely enough to be read. The act is a decision per named action.
- **Mechanism and evidence**: PreToolUse permissionDecision allow/deny/ask (N22:39, T). Telemetry: 97% approval, 3% per-permission rejection, 17%→5% blocking after 50 prompts, 62% used bypass or don't-ask-again (N14:71–N14:73, M). OpenCode defaults to ask only for doom_loop and external_directory (N07:92). Complacency after ~20 minutes under constant-reliability automation (N01:20, C); a 10-minute return to manual restored detection (N01:43). Best card: C, non-code.
- **Nearest existing thing**: Junie's ask-by-default with an allowlist (N07:93); Claude Code's Manual default (N07:91).
- **Authorless code**: Neutral.
- **Grain**: Command.
- **Demand**: Verify.
- **Enforcement and relocation**: Hook in the repository (ADR 0008: a hook, not Dashpot). Relocates to allow-rules — 49.5% of users created a Bash allow-rule (N14:73).
- **Decay**: The clearest measured decay in the corpus (N14:72).
- **Verifiability**: Approval is not comprehension (N14:74); the dead end stands (N14:69).
- **Evidence source**: Harness hook log; Dashpot's hook publisher does not subscribe to PreToolUse (agent-sessions.md).
- **Lifecycle hook**: PreToolUse.
- **Without AI**: Pre-commit and branch protection are the pre-AI forms.
- **Coordination cost**: None.
- **Social form**: Individual; the list is a team artifact.
- **Verdict**: *Reject*, on decay. The clearest measured habituation in the corpus (17% to 5% blocking after fifty prompts, N14:72), approval is not comprehension, and Dashpot does not subscribe to PreToolUse.

#### IL-4 Curated dialog as the record
- **Stage and cell**: In-loop step / Nothing-artifact — "curated dialog" (N; no change signal).
- **What it is**: The person edits, hides, pins and deletes messages in the working dialog so the transcript becomes a curated account of the change rather than an append-only log. The act is editing.
- **Mechanism and evidence**: Solve.it's H/P/E keys and editable messages (N24:126; N17:35; N17:36, T); dialog engineering (N02:10); Zed's editable text threads were removed on 2026-03-31 (N24:128); gptel keeps editable conversations in-file (N24:129). The dialog is provenance not attached to git (N02:129). gIBIS: capture overhead in the moment is prohibitive (N24:9, Q); "the capture problem is the spectre" (N24:13). Best card: T.
- **Nearest existing thing**: Solve.it (N24:126); Commit Context attaching the redacted conversation to commits (N13:70).
- **Authorless code**: Neutral.
- **Grain**: Session.
- **Demand**: Generate (editing).
- **Enforcement and relocation**: Harness feature (E1); relocates to not curating (N24:13: no immediate value).
- **Decay**: Transcripts deleted after 30 days (N13:71; N11:108); nothing signals a stale dialog.
- **Verifiability**: No card on measuring a curated dialog's value to a reader (N11:181).
- **Evidence source**: Harness store; not Git, not Issue Source.
- **Lifecycle hook**: Throughout the session.
- **Without AI**: There is no dialog without an agent.
- **Coordination cost**: None unless shared.
- **Social form**: Individual.
- **Verdict**: *Reject*, on social form and lifecycle hook. Session-only by construction, deleted after thirty days, nothing without an agent: the chat-centric shape the thesis argues against.

#### IL-5 TODO(human) hand-back
- **Stage and cell**: In-loop step / Generate (N; O as a Claude Code output style).
- **What it is**: The agent leaves a bounded, strategic piece of the change as `TODO(human)` for the person to write, then reviews it. The act is writing code.
- **Mechanism and evidence**: Claude Code Learning style leaves `TODO(human)` markers, the only first-party mode handing authorship back mid-task (N13:17; N13:75; N22:10, T); the plugin's README states learning-by-doing with no evaluation (N14:84). Generation effect (N08:88, C); generation must be of the target from an actionable cue and reverses when it fails (N08:89). Expertise reversal (N08:102). Best card: C.
- **Nearest existing thing**: okay's /now-i-do-it saving the diff as answer key and pacing a rebuild (N07:9); Cocoa's step assignment (N22:107).
- **Authorless code**: The person authors the strategic part; the rest stays agent-written.
- **Grain**: Function/hunk.
- **Demand**: Generate.
- **Enforcement and relocation**: Output style or skill (E2/E3); relocates to asking the agent to fill the TODO — no hook detects who typed.
- **Decay**: Style selection persists per config (N13:17); adherence unmeasured.
- **Verifiability**: The person's piece must pass the tests; whether it was theirs is unverifiable.
- **Evidence source**: Git shows the hunk; authorship of a hunk within an agent-driven commit: no card.
- **Lifecycle hook**: Mid-task.
- **Without AI**: Without an agent all code is hand-written.
- **Coordination cost**: None.
- **Social form**: Individual.
- **Verdict**: *Reject*, on without-AI and verifiability. The generation effect is real, but on a human-authored branch every hunk is already the person's, and inside an agent-driven commit nothing shows who typed the hunk. An in-loop bet (principle 2) with no instrument.

#### IL-6 Small test-bounded steps
- **Stage and cell**: In-loop step / Nothing-artifact (a bound, principle 14; M via Stop hook).
- **What it is**: The agent works in diffs small enough to read, each closed by a passing test; a Stop hook blocks the turn until tests are green. The act is reading a bounded diff.
- **Mechanism and evidence**: Feng et al.'s small reviewable diffs and three non-negotiables (N22:105; N22:106); Stop hook as deterministic gate, override after 8 blocks (N22:40, T). Larger changes are less likely to merge after controls (N04:107, M); DORA small batches (N10:73). Risk: developers use test results as guarantees of correctness (N14:79, Q). Best card: M.
- **Nearest existing thing**: Böckeler's sensors (N24:63); Ona's under-1,000-lines criterion (N07:26).
- **Authorless code**: Neutral.
- **Grain**: Step/diff.
- **Demand**: Read.
- **Enforcement and relocation**: Stop hook and skill (ADR 0008); relocates to trivial tests or the 8-block override (N22:40).
- **Decay**: Hooks hold; the size norm is social.
- **Verifiability**: Test pass is checkable; reading is not.
- **Evidence source**: Stop events reach Dashpot's hook publisher (agent-sessions.md); test results reach CI.
- **Lifecycle hook**: Stop.
- **Without AI**: Yes — small batches and TDD predate agents.
- **Coordination cost**: Reviewer burden falls (N08:127: review bounded by working memory).
- **Social form**: Individual, norm held by the team.
- **Verdict**: *Shortlist as a size bound, folded into the AR bound family.* The act asked — read a bounded diff — is thin, but the bound is the thing: change size is observable on the Branch today, batch size at review is the one place team friction meets comprehension evidence (59% against 35%), and small batches predate agents. The Stop-hook enforcement is harness-side and out of scope; the observed size against a bound is Dashpot's.

#### IL-7 Explain before the agent proceeds
- **Stage and cell**: In-loop step / Explain (M: skill or plugin gate).
- **What it is**: Before the agent continues past a step, the person types why the step is correct and what it depends on; an LLM judge scores it against a rubric and the agent proceeds only on a pass. The act is a teach-back.
- **Mechanism and evidence**: Sankaranarayanan's Explanation Gate: blackout failure 77% unrestricted vs 39% with the gate, n=78 (N08:53, C); GPT-4o judge, SOLO rubric, pass ≥3, no judge–human agreement (N23:15); epistemic debt 69.3 vs 27.6 vs −4.0 (N23:134). Self-explanation g=0.55 (N08:93, C), must ask for mechanism not paraphrase (N08:95). Best card: C.
- **Nearest existing thing**: PrincessSats cognitive-debt blocking commands until a card is answered (N07:5); Covate blocking until completion at any score (N13:16). Hawthorne effect, novices only (N08:54).
- **Authorless code**: Applies to any change.
- **Grain**: Step.
- **Demand**: Explain, answer hidden.
- **Enforcement and relocation**: Plugin or hook (ADR 0008); relocates to paraphrase the judge accepts (N08:56: poor explanations raised confidence).
- **Decay**: Mid-task gates dismissed 62% (N22:104).
- **Verifiability**: Scored, with no agreement statistic (N14:51).
- **Evidence source**: Plugin ledger (N07:5); not Dashpot.
- **Lifecycle hook**: Step boundary.
- **Without AI**: Yes — teach-back is pre-AI (N08:106).
- **Coordination cost**: None.
- **Social form**: Individual.
- **Verdict**: *Hold, relocated to HO.* The corpus's strongest C-level card (N08:53) is this mechanism, but fired mid-task, where 62% dismiss and the individual pays per step, and outside every Dashpot channel. Principle 5 places it at the hand-off boundary, where HO's explain-back is the same mechanism with the diff hidden; the in-loop firing point is rejected, the mechanism is not.

#### IL-8 Predict the test before it runs
- **Stage and cell**: In-loop step / Verify (N).
- **What it is**: Before the agent runs a test or command, the person states the expected outcome; the result is then shown against the prediction.
- **Mechanism and evidence**: Predicting a test's outcome before running it (N08:90); friction that forces prediction before the answer is shown (N08:87); the in-loop note found no predict-then-run tool (N22:125). learn-codebase asks the learner to predict before revealing (N13:12); opencode-sit has a debug-prediction mode (N07:12). Retrieval before reveal (N08:115, C). Best card: C.
- **Nearest existing thing**: opencode-sit (N07:12); the Inquisitive code editor asking about program behaviour (N13:22; N19:21).
- **Authorless code**: Applies regardless of authorship.
- **Grain**: Command.
- **Demand**: Verify by prediction, answer hidden.
- **Enforcement and relocation**: Skill instruction or PreToolUse hook on test commands (ADR 0008); relocates to "pass" every time.
- **Decay**: Per-command asks habituate fastest (N14:72).
- **Verifiability**: The prediction is scored by the run itself — no judge.
- **Evidence source**: Harness; a hook could log prediction and outcome; not Dashpot.
- **Lifecycle hook**: PreToolUse on test/run commands.
- **Without AI**: Yes.
- **Coordination cost**: None.
- **Social form**: Individual.
- **Verdict**: *Hold*, on social form. The cleanest instrument at this row — the run scores the prediction, no judge — pre-AI and answer-hidden, but per-command asks habituate fastest and the record lives in a PreToolUse hook Dashpot does not see, attached to nothing shared. Held for a form that fires once per test run at a boundary and posts prediction and outcome to the Branch or Issue.

### Hand-off, agent done and before the Pull Request (HO)

#### HO-1 Explain it back with the diff hidden

- **Stage and cell**: HO; the map's "explain it back, graded, diff hidden" cell (N; M if it gates the push or the `work stop`).
- **What it is**: After the Agent Run's last edit and before a Pull Request exists, the person writes or speaks, with the diff off screen, what the change does, why it is correct, and what it depends on; the explanation is scored against the code, not against the agent's prose. The act is the person's own generated explanation (principles 1, 3, 7).
- **Mechanism and evidence**: Self-explanation asking for mechanism rather than paraphrase, g = 0.55 over 69 effects (N08:93, N08:95); retrieval before reveal as the remedy for foresight bias when the answer is on screen (N08:111, N08:115). The one direct test on code: Sankaranarayanan's three-arm study, n = 78, where a teach-back Explanation Gate cut failure on a 30-minute no-AI repair task from 77% to 39% while both AI arms beat manual on output (N08:53, N21:159–175); the gate cost a median 14.2 minutes, 62% of first explanations were judged tautological, and 72% of participants called it annoying while 64% credited it (N21:159–175). Best evidence level C, novices only, no judge–human agreement reported (N08:54, N14:51).
- **Nearest existing thing**: VibeCheck: ≥ 2 lines / 50 characters, SOLO ≥ 3, GPT-4o judge, bypass detection (N21:22–24, N21:83–86); Willison's rule of not committing what he could not explain to somebody else (N13:33). The candidate differs by scoring against the code (N21:25/26, CGBG κ = .58) and by recording that the act happened on a shared object rather than in the session.
- **Authorless code**: Passes: the explainer is the named person handing off, whoever or whatever wrote the lines (N15:45, N13:32).
- **Grain**: Change (the whole Branch diff); nothing in the corpus does it at module grain (N21:235).
- **Demand**: Generated explanation with the answer off screen (D3 with a D1 constraint); the highest-demand cell in the hand-off row.
- **Enforcement and relocation**: As a skill instruction before `work stop` it is unenforced (N21:158; agent instructions appear in 2.1% of policies, N21:149); a Stop hook can block the turn until it passes, with an override after eight blocks (N22:40). Expected relocation: pasting the question to the agent, which is how HN readers said they would beat dkamm's quiz (N21:109), and Revodata's own threat model calls its gate "a review aid, not a secret exam" (N21:62).
- **Decay**: Expertise reversal: the gate helped novices and is predicted to become redundant or irritating for experts (N21:172, N08:102), so the corpus itself proposes fading (N21:174, N21:246).
- **Verifiability**: A text can be produced by a model; "text artifacts cannot prove a human privately understands code" (N23:93); judge reliability on developer explanations is unmeasured (N21:247, N14:51).
- **Evidence source**: C (N08:53), single study, students.
- **Lifecycle hook**: A `dashpot-issue-work` step before `work stop`; or a Stop-hook gate. Dashpot would observe a record of the act, not perform it (ADR 0008).
- **Without AI**: Yes: Fagan's inspection has the reader paraphrase the design (N26:189) and Willison's rule predates agents (N13:33).
- **Coordination cost**: None if a judge grades; a person grading costs the time the mentoring studies price in hours a day (N26:8).
- **Social form**: Solo with an instrument; becomes social if the explanation is posted where a reviewer reads it (N08:126).
- **Verdict**: *Shortlist, head of the explain-back family.* The bookend principle 2 says is the one thing with causal support: a generated explanation with the diff off screen (principle 3's operational form), scored against the code, recorded on the Issue or Pull Request rather than in the session. Its known costs are the ones to test — a median of 14 minutes, 62% tautological first attempts, expertise reversal — and the record it leaves is what PD-8 re-tests and what MR-2's fading reads. Its one unverifiable assumption is that the explanation is the person's and not pasted from the agent; the corpus says no text can prove that, so the family relies on the answer-hidden condition and on RT-7's blackout task to catch the gap, not on provenance.

#### HO-2 Quiz on the diff with the diff hidden

- **Stage and cell**: HO; the map's "quiz on the diff, diff hidden" cell (N).
- **What it is**: Before the Pull Request, the person answers a small set of questions generated from the change — which module owns the new state, what breaks if X fails, what a call returns on the edge case — with the diff closed. Items are drawn from the code's structure, not from a prose summary. The act is recall.
- **Mechanism and evidence**: Retrieval practice, g ≈ 0.50–0.61, stronger for recall than recognition and needing feedback (N08:71, N08:72, N08:74); conditions that mimic the test reduce the illusion of competence (N08:112). The tools are self-checked and unevaluated: Litt's five MCQs (N21:4/5, N21:27–32, N25:27), diffquiz's 3–5 questions in 60 seconds, never blocking (N07:3), quiz-me's eight questions with a retake below 6/8 (N07:6), change-quiz's 5–8 questions and "two failed rounds means split" (N07:7), socratic quiz-me (N13:15). Generated MCQs leak: the correct answer was usually the longest or the second option (N21:34/38, N25:31); 4.9% of GPT-4 items had multiple correct answers and 4.0% answer-revealing distractors (N23:140); no item-response validation exists on developer answers (N23:142).
- **Nearest existing thing**: Litt's `/explain-diff` quiz (N23:88), which persists nothing and sits below a prose explainer, so the diff is on screen; the candidate closes the diff and keeps a record.
- **Authorless code**: Passes: it tests the person's model, not the author's identity.
- **Grain**: Change; the malav2110 fork adds file:line anchors re-read at PR head (N21:47/48).
- **Demand**: Recall (D4); recognition if multiple choice, which the retrieval literature rates weaker (N08:71).
- **Enforcement and relocation**: Unenforced as a skill; AIditor installs a real pre-commit hook that blocks below 75% (N07:4). Relocation: quiz the agent (N21:109); answer by re-opening the diff, which nothing detects.
- **Decay**: One-shot at hand-off, never re-asked (N25:32, N19:20); nothing survives across Worktrees (N21:244).
- **Verifiability**: A pass is recordable; whether it discriminates skimmers is unknown (N21:239); the same model asks and grades (N07:6).
- **Evidence source**: T for every tool; C only for the retrieval mechanism on non-code material (N08:69).
- **Lifecycle hook**: Skill step before the push; a record in the Work Store or on the Issue is the observable.
- **Without AI**: Yes; PopPR's regex question bank runs on any diff (N23:144).
- **Coordination cost**: None.
- **Social form**: Solo; Litt's rule extends it to reviewing others' code (N25:28).
- **Verdict**: *Hold, folded into HO-1 as its cheaper option.* Recognition is weaker than recall, generated items leak, and the same model asks and grades; HO-1 dominates it on every lens but cost. Held for the case where a judge for HO-1 proves too expensive or too lenient, with the requirement that items be drawn from structure and the diff be closed.

#### HO-3 Write the Pull Request description yourself

- **Stage and cell**: HO; the map's "write the PR description oneself" cell (N).
- **What it is**: The person, not the agent, writes the Pull Request body: intent, the invariants touched, what was verified and how. The agent's summary is not offered as a draft. The act is generation of the rationale from memory (principles 1, 6).
- **Mechanism and evidence**: Generation effect, d = 0.40 over 445 effects, holding when the target is generated from an actionable cue (N08:88, N08:89). Policy precedent: OSS policies that say write PR descriptions yourself (N21:136), the kernel's requirement that the submitter understand and defend the change (N15:45), Raed's "a PR is not ready until the human can state its intent, the invariants it touches, and the evidence it is safe" (N13:32). The counter-evidence is on the generated side: Copilot-for-PRs descriptions cut review time 19.3 hours and raised merge odds 1.57× across 18,256 PRs, correlational, no comprehension measure (N14:60, N14:109); when people edited them the commonest edit was deletion (22.9%) and intent was added in 12.8% (N14:61). Reviewers get rationale from the author rather than the code (N08:126).
- **Nearest existing thing**: git-narrate, which matches hunks to transcript prompts and writes the PR body for you (N21:211–213, N13:42); the candidate is its inverse.
- **Authorless code**: Passes: the description's author is a named person regardless of who wrote the lines.
- **Grain**: Change.
- **Demand**: Written rationale (D2).
- **Enforcement and relocation**: A PR template or a skill instruction, unenforced (N21:158); docs-as-code teams block merge on missing documentation (N24:29). Relocation: paste the agent's summary; the capture cost is the design-rationale field's forty-year spectre (N24:9, N24:13), lack of time the top barrier at 60.5% (N24:166).
- **Decay**: Templates fill with boilerplate; ADR authors omitted the section they feared being criticised for (N24:26).
- **Verifiability**: Provenance of prose is undetectable (N23:93); Dashpot observes PR state, not the body's authorship.
- **Evidence source**: C for the mechanism (N08:88), T for the policies, M against (N14:60).
- **Lifecycle hook**: The skill's "follow the repository workflow" step; the PR body is a GitHub field a new observation could read.
- **Without AI**: Yes; it is the pre-agent norm.
- **Coordination cost**: Saves the reviewer's, per the author-as-source finding (N08:126).
- **Social form**: Dyadic: written for the reviewer; commentable on the shared object.
- **Verdict**: *Shortlist, paired with IS-1.* The pre-agent norm restated: the person writes the Pull Request body from memory — intent, invariants, what was verified. Alone its verifiability is weak, since prose provenance is undetectable and generated descriptions measurably speed review. Paired with IS-1's restatement at binding it becomes an instrument: the person's own account at both ends of the Issue, compared for what changed in their model. The counter-evidence (N14:60) is about reviewer speed, not the author's understanding, and the analysis has already chosen which of those Dashpot is for.

#### HO-4 Read-first viewer with a record of hunks visited

- **Stage and cell**: HO; the map's "read-first viewer" cell (N).
- **What it is**: Before commit or PR, the person reads the whole changeset in an ordered viewer that records which hunks were opened; the record travels with the Branch. The act is reading, plus the viewer's ordering.
- **Mechanism and evidence**: LLVM's rule: read and review all generated content before asking others to review it (N21:134, N13:28); PostHog's "actually read the diff" (N07:22). Hunk (9,245 stars) offers whole-changeset reading order, sidecar notes and a review-triage that marks visited hunks, but the marks are session-local and it blocks no commit (N21:202–210, N13:41). Ordering by flow rather than alphabetical file order is the consistent recommendation (N21:199–201, N25:43). Against: reading confers the program model at best (N08:129), the diff on screen is the foresight-bias condition (N08:114), and METR's developers, 75% of whom reported reading every line, still misjudged their speed by 39 points (N08:37, N08:35).
- **Nearest existing thing**: Hunk (N21:202); the candidate adds persistence of the visited set beyond the session.
- **Authorless code**: Passes: the reader is named; what was read is code, not authorship.
- **Grain**: Hunk.
- **Demand**: Reading (D6), the lowest demand that still asks an act.
- **Enforcement and relocation**: None in Hunk (N21:210); a pre-commit check could refuse unvisited hunks. Relocation: scroll through without reading — nothing distinguishes it (N21:239).
- **Decay**: Habituation is the known failure of read-and-approve: approvals rose 30.1%→36.8% and inline comments fell 22% as reviewers habituated to agent PRs (N21:220–222).
- **Verifiability**: Visited ≠ read; no metric of reading exists in any tool (N21:192/196/217, N13:118).
- **Evidence source**: T (tools, policies); Q against (N08:124).
- **Lifecycle hook**: Between the agent's last edit and `git commit`; Dashpot could observe a visited-set file in the Work Store.
- **Without AI**: Yes, though the reviewer already reads; the value is on one's own Branch.
- **Coordination cost**: None.
- **Social form**: Solo.
- **Verdict**: *Reject*, on verifiability. Visited is not read, nothing distinguishes a scroll from a reading, and reading with the diff on screen is the confidence-gap condition. The ordering-by-flow idea survives as how HO-1's reveal is shown afterwards.

#### HO-5 Ask a named person before opening the Pull Request

- **Stage and cell**: HO; the map's "ask a person" cell (N, social).
- **What it is**: Before the PR, the person walks the change through with a colleague — five minutes, voice or thread — and records who was asked on the Issue or in the PR body. The act is the conversation; the record names the second person (principles 9, 15).
- **Mechanism and evidence**: Asking beats reading across four decades of newcomer studies: five minutes by asking versus a day in code and docs (N26:18), communication preferred over documentation by 17 of 28 professionals (N26:87), 81% consult other people (N26:90). Handover research finds the model is reconstructed by the receiver's questions, not the sender's summary (N11:3); 8 of 75 incoming controllers' questions were error-detecting (N11:16); the sender's most important item failed to transfer 60% of the time while the sender believed it had (N11:50). Review is where engineers meet (N26:56) and spreads files known by 66–150% (N26:196).
- **Nearest existing thing**: Fagan's transfer inspection, "frequently a required event where responsibility for design or code is being transferred" (N26:191); pairing as cross-training (N26:175/176). Differs by being a lightweight pre-PR consult with a named record.
- **Authorless code**: Passes: two named people, neither inferred from authorship.
- **Grain**: Change.
- **Demand**: Ask (D7) with spoken explanation (D3); the protégé effect, g = 0.56 for teaching after preparing (N08:108).
- **Enforcement and relocation**: Unenforced by tooling; a PR check could require a named consult. Relocation: name someone who was not really asked; ask the agent instead (N21:109).
- **Decay**: Fear that asking reveals ignorance (N26:19); newcomers unanswered within 24 hours stopped posting (N26:41).
- **Verifiability**: The name is verifiable; the conversation is not.
- **Evidence source**: Q (N26:18, N26:87), M (N11:50).
- **Lifecycle hook**: A skill instruction before "open the PR"; the record on the Issue (Issue Source) or PR body is observable.
- **Without AI**: Yes; it is how models were always built (N26:1, N26:57).
- **Coordination cost**: The highest in the row: it interrupts the teammate and fails when the teammate is unavailable or gone (N26:77); delay tracks the number of people (N27:37).
- **Social form**: Dyadic by construction.
- **Verdict**: *Shortlist, folded into the ask family.* The pre-PR consult with a named second person, recorded on the Issue or in the PR body: the ask family's hand-off firing point, with the highest coordination cost in the row and the protégé effect behind it. The name is verifiable; the conversation is not, and the family accepts that.

#### HO-6 Explainer artifact with a change signal

- **Stage and cell**: HO; the map's "explainer artifact" cell (N; no change signal in any existing tool).
- **What it is**: When the Agent Run finishes, an explainer packet (background, intuition, ordered literate diff) is generated; it is anchored to file:line at the Branch head and marked outdated when those lines change. The person reads it first. It asks no act beyond reading.
- **Mechanism and evidence**: Litt reads the explainer before the diff, every day, as do coworkers; no outcomes measured (N25:14, N25:20, N24:133); background first, intuition before detail (N25:21/22). Human evaluation of generated tours: 26 developers preferred tours that scaled detail and avoided restating code, while LLM judgments of tour quality were unreliable (N14:52/53); LACY's expert-guided tours scored 83% vs 57% on a quiz, n = 5 (N14:55). Nothing asks whether a walkthrough reader understood the change (N14:64); CodeRabbit and Sourcery expose no read metric (N21:192/196, N23:87). Poor explanations lowered accuracy while raising confidence (N08:56). Code carries no intentions to generate from (N26:100).
- **Nearest existing thing**: `/explain-diff` (N25:20, N13:40) with malav2110's file:line anchors re-read at PR head (N21:47/48); Swimm's outdated flag that blocks a PR check until a human reselects the snippet is the only change signal in the corpus (N24:39).
- **Authorless code**: Passes trivially, since it asks nothing of anyone.
- **Grain**: Change, with file:line anchors.
- **Demand**: Reading (D6); principle 1 (demand before display) is the lens this candidate is expected to fail.
- **Enforcement and relocation**: None; Litt's own gate is the quiz, not the packet (N25:28).
- **Decay**: Stale by default: not retained, versioned or re-read after the review it was written for (N24:135, N24:201); the change signal only says it is stale.
- **Verifiability**: No tool records that a human read a generated artifact (N24:53, N07:82).
- **Evidence source**: T (N25:14); Q for tours (N14:52).
- **Lifecycle hook**: Generated at the agent's Stop; stored outside the repository in Litt's variant (N25:25).
- **Without AI**: The artifact needs a generator; a human explainer is the PR description (HO-3).
- **Coordination cost**: None; Notion embedding makes it commentable (N24:134).
- **Social form**: Solo reading; shareable.
- **Verdict**: *Reject*, on demand. The expected failure: an artifact that asks nothing, even with the change signal that makes it honest about being stale. Litt's own gate is his quiz, not his packet.

#### HO-7 The agent asks two questions before `work stop`

- **Stage and cell**: HO; between "explain back" and "quiz" (N; carried by the skill).
- **What it is**: The `dashpot-issue-work` skill instructs the agent, after its last edit and before it may run `work stop`, to ask the person two questions about the change — one on mechanism, one on what breaks — and to wait; no grading, no score returned to the agent. The act is answering a questioning agent.
- **Mechanism and evidence**: Teaching to a questioning audience beats preparing to teach, g = 0.56 vs 0.35 (N08:108, N08:109, N08:110). Learning Opportunities offers a 10–15 minute exercise after a commit via a PostToolUse hook, two offers per session, self-suppressing, 2,418 stars, no outcome data and no mastery record (N21:20/21, N21:76–82, N19:19, N19:132, N13:13). Covate blocks the agent until completion and does not return the score to it (N21:18/19). Interventions at workflow boundaries got 52% engagement while mid-task ones were dismissed 62% of the time (N22:104). Agents misreport completion in 22.58% of misalignment cases (N04:117), which a question at the end can catch.
- **Nearest existing thing**: Learning Opportunities (N19:19); the candidate is smaller, un-scored, and placed at the hand-off boundary rather than after each commit.
- **Authorless code**: Passes: the person answering is named by the Agent Session Identity.
- **Grain**: Change.
- **Demand**: Spoken/typed explanation (D3), unscored.
- **Enforcement and relocation**: A skill instruction, which nothing enforces (N21:149); a Stop hook could hold the turn (N22:40). Relocation: type "yes" — the decline path Learning Opportunities self-suppresses on (N19:19).
- **Decay**: Habituation is the vendor's own finding for prompts: 97% of permission prompts approved, dangerous-command blocking falling from 17% to 5% after 50 prompts (N14:71, N14:72).
- **Verifiability**: Only that a question was asked and something typed.
- **Evidence source**: C for the protégé effect off code (N08:108); T for the tools.
- **Lifecycle hook**: The skill's finish step, immediately before `work stop`; the Stop hook is the enforcing variant.
- **Without AI**: No: there is no questioner without the agent.
- **Coordination cost**: None.
- **Social form**: Solo with a simulated audience (N08:109).
- **Verdict**: *Reject*, on without-AI and verifiability. No questioner without the agent, no score, and "yes" is the relocation. HO-1 is the scored form at the same boundary; the directability point belongs to the skill's design.

#### HO-8 Blackout repair on the Branch

- **Stage and cell**: HO; the map's instrument row rather than a named cell (N; M if it gates).
- **What it is**: Before the PR, the person makes one small change on the Branch — fix a failing test a reviewer or script seeds, or re-implement one reverted hunk — with the agent off. The act is doing, and the instrument is whether the repair lands (principle 7).
- **Mechanism and evidence**: The 30-minute no-AI blackout maintenance task is the outcome measure in the one gate study, where repair succeeded for 69.2% manual, 23.1% unrestricted-AI and 61.5% gated participants (N21:159–175, N08:53). Newcomers built models by running and changing code, committing a fix on day one (N26:26, N26:57); Pennington's situation model predicted modification performance (N08:16). Regulated industries' forced manual friction preserved engagement in Shukla and Sharma's interviews (N14:29). okay's `now-i-do-it` saves the diff as an answer key, reverts it and paces a rebuild by hand (N07:9); Sethi retypes every edit at "probably only 2×" speed (N07:63).
- **Nearest existing thing**: `now-i-do-it` (N07:9); the candidate scopes it to one hunk and records the outcome.
- **Authorless code**: Passes: whoever repairs is named.
- **Grain**: Hunk within a change.
- **Demand**: Generation (D1), the highest column.
- **Enforcement and relocation**: Seeded test as a local check; unenforceable that the agent stayed off. Relocation: run the agent anyway.
- **Decay**: Expertise reversal predicts it wastes experts' time on familiar code (N08:103, N08:105).
- **Verifiability**: The repair is in git; who typed it is not.
- **Evidence source**: C (N08:53), novices, one task.
- **Lifecycle hook**: Between the agent's Stop and the push; the seeded failure is a pre-commit or local check.
- **Without AI**: Yes as a self-test; pointless on code you typed.
- **Coordination cost**: None unless a reviewer seeds the failure.
- **Social form**: Solo.
- **Verdict**: *Shortlist, folded into RT-7 as the instrument family's hand-off firing point.* The blackout repair is the study's own outcome measure, and at hand-off it doubles as a check on HO-1. Expensive, and pointless on code the person typed, so it is sampled and it lives with RT-7 rather than as a gate.

### Pull Request review and merge (RV)

#### RV-1 The reviewer explains a hunk back to the author

- **Stage and cell**: RV; the map's "reviewer explains a hunk" cell (N, social).
- **What it is**: For each hunk the reviewer approves, they write in the thread what it does and why it is safe, in their own words, before marking it; the author confirms or corrects. The act is the reviewer's explanation, recorded on the Pull Request.
- **Mechanism and evidence**: Fagan's inspection has a reader paraphrase the design and lists education among its objectives (N26:189, N26:190); VirtusLab proposes asking reviewers to explain purpose rather than judge correctness (N13:86); Ma: "if you approve a PR you couldn't have written and can't fully explain, you didn't review it. You witnessed it" (N13:89). Understanding is the reviewer's main challenge — 91% say unfamiliar files take longer, 14% of comments concern defects (N26:195); review transfers knowledge as a by-product of effortful understanding, not of approval (N08:124), and spreads files known by 66–150% (N26:196). Per-reviewer load already doubled under agent PRs, 2.09× (N21:225).
- **Nearest existing thing**: Review comments as they exist (observed as review decision); no tool records what reviewers ask (N21:187/188).
- **Authorless code**: Passes: the reviewer is a named person; the author may be an Agent Run.
- **Grain**: Hunk.
- **Demand**: Written explanation (D3).
- **Enforcement and relocation**: Social; a PR check could require one explanation comment per file. Relocation: ask a review bot to write it — reviews of agent PRs are already largely by agents (N14:63).
- **Decay**: Habituation on agent PRs: approvals up, comments down 22% (N21:220–222); direction disputed (N06:65).
- **Verifiability**: The comment is verifiable as an act; its provenance is not (N23:93).
- **Evidence source**: M (N26:196), Q (N08:124), A for the proposal.
- **Lifecycle hook**: PR review comments, a GitHub field beside the review decision Dashpot already observes.
- **Without AI**: Yes; it is Fagan (N26:189) and Google's stated purpose of review (N26:197).
- **Coordination cost**: Doubles review time per the effort figures (N16:11, N21:225).
- **Social form**: Dyadic on the shared object.
- **Verdict**: *Shortlist, the explain-back family's review firing point, paired with RV-2.* Fagan's reader paraphrasing the design, written into the PR thread per hunk: a social act on the shared object, pre-AI, with review's 66–150% knowledge spread as its mechanism and the doubling of per-reviewer load as its bill. JN-8 folds in here as the newcomer's firing point. Its decay is the disputed habituation dataset, which AR-4 is held to measure.

#### RV-2 The author answers a question in-thread before approval counts

- **Stage and cell**: RV; the explain-on-demand clause of the OSS policies (N; M if a check requires it).
- **What it is**: A reviewer asks one question about the change; the author answers in the PR thread without re-prompting an agent; approval is withheld until an answer exists. The act is the author's answer to a person's question (principle 9).
- **Mechanism and evidence**: LLVM: contributors must "be able to answer questions about their work during review" (N13:28, N21:134); BeeWare: "You must be able to fully explain your implementation during the review process", doubt closes the PR (N13:29); Mastodon likewise (N13:30); the kernel's maintainer "may ask the submitter to explain" (N15:46); PostHog: explain "without re-prompting an LLM" (N07:21). Of 281 policies 67.3% require high human involvement and 43.4% assign accountability, none enforced by tooling (N21:140–147, N21:158, N13:31). Reviewers obtain rationale from the author (N08:126). The receiver's question is where the model is reconstructed (N11:3).
- **Nearest existing thing**: The BeeWare clause (N13:29); the candidate makes the question a required event rather than a right.
- **Authorless code**: Passes only if the author is a person; for an Agent Run's PR the answerer must be the named custodian (N03:103/104, N15:1).
- **Grain**: Change or hunk, as asked.
- **Demand**: Explanation on demand (D3).
- **Enforcement and relocation**: Policy today; a required "question answered" status is M. Relocation: paste the question to the agent — PostHog's clause exists because this is expected (N07:21), and none of its documents says how "does the author understand" is checked (N07:24).
- **Decay**: Questions get perfunctory; the majority of incoming clinicians asked no questions at handoff (N11:66).
- **Verifiability**: The answer is on record; its authorship is not.
- **Evidence source**: T (policies); M for the base rate (N13:31).
- **Lifecycle hook**: PR comments plus review decision (O); a check (M).
- **Without AI**: Yes; the clause predates agents in spirit (N15:46).
- **Coordination cost**: One question and one answer per PR; asynchronous.
- **Social form**: Dyadic; visible to the team.
- **Verdict**: *Shortlist, paired with RV-1.* The ask family on the Pull Request: a reviewer's question, the author's answer without re-prompting an agent, approval withheld until it exists. Two thirds of contribution policies already claim this right and none enforces it; making the question a required event is the one-step-toward-default. For an Agent Run's PR the answerer is the named custodian (RV-6), which is why the two families meet here.

#### RV-3 Read attestation per file

- **Stage and cell**: RV; the map's "read attestation per file" cell (N).
- **What it is**: A named person records, per file at a commit, "I read this" or "I endorse this", stored with the Branch (git notes) or on the PR, revocable, invalidated when the file changes. The act is the attestation.
- **Mechanism and evidence**: VOUCH defines an Endorsement Record {commit, file_path, endorser, lines endorsed/reviewed} under `refs/notes/vouch-state`, with comprehension as unknown / reviewed / endorsed, revocation and thresholds such as under 20% endorsed in Tier-1 paths; endorsement is self-reported (N07:72–74). cdebt flags files with no verified owner `[DARK]` and gates CI (N19:12). Google's freshness date is a human `reviewed` attestation with a three-month reminder (N24:35); AWS's ADR review records who was present at a 10–15 minute read (N24:22/23). No study records a human's read of a generated artifact as attestation (N07:82, N24:204); Agent Trace and git-ai have no human-reviewed field (N23:76/77).
- **Nearest existing thing**: VOUCH (N07:72); the candidate differs by being observed by Dashpot beside the PR and invalidated on change.
- **Authorless code**: Passes: endorsement is "a unit distinct from authorship" (N07:72).
- **Grain**: File, with line ranges.
- **Demand**: Reading plus a signed claim (D6/D5).
- **Enforcement and relocation**: A threshold check is M (N07:72); otherwise a glyph. Relocation: tick without reading — the kernel's Assisted-by trailer is likewise unenforced (N16:73).
- **Decay**: Built in: revocation and per-commit pinning (N07:73); three-month freshness (N24:35).
- **Verifiability**: Self-report; hasty review is detectable only by rate, faster than 200 lines per hour (N23:85, N16:11).
- **Evidence source**: T only; no evaluation of any attestation tool.
- **Lifecycle hook**: Notes pushed with the Branch, read at Remote Fetch; or a PR comment.
- **Without AI**: Yes; Google's `reviewed` date is pre-AI (N24:35).
- **Coordination cost**: None beyond the read.
- **Social form**: Individual record, team-visible heatmap (N07:72).
- **Verdict**: *Hold, on verifiability; becomes MR-2 at review if it carries a question.* VOUCH's endorsement as "a unit distinct from authorship", pinned per commit and revoked on change, is the right shape and the coupling principle 6 asks for; but a tick is self-report, and no attestation tool has been evaluated. Held until the attestation carries a hidden-answer item, at which point it is the verified-at-ref family's review firing point.

#### RV-4 GitHub Viewed state as a glyph

- **Stage and cell**: RV; the map's "Viewed state" cell (N).
- **What it is**: Dashpot reads the reviewer's own per-file Viewed checkbox state on a Linked Pull Request and shows files unviewed at approval time. It asks no act beyond the tick GitHub already offers.
- **Mechanism and evidence**: The checkbox collapses a file, is unmarked if the file changes, and GraphQL exposes `viewerViewedState` with mark/unmark mutations; only the viewer's own state is exposed and nothing about time or attention is recorded (N23:83). No study uses it as data (N07:102). Walkthrough tools expose toggles but no read metric (N13:118, N23:87); vendor review-time products measure windows, not reading (N23:84).
- **Nearest existing thing**: The checkbox itself (N23:83); the candidate only surfaces it beside the review decision.
- **Authorless code**: Passes: it is the reader's state.
- **Grain**: File.
- **Demand**: A tick (D5 at most); expected to fail principle 1.
- **Enforcement and relocation**: None possible from the outside: the state is private to the viewer (N23:83). Relocation: tick all.
- **Decay**: Reset on file change (N23:83); otherwise habituates like any checkbox (N14:71).
- **Verifiability**: Viewed ≠ read; unmeasurable (N07:102).
- **Evidence source**: T (docs); no card on effect — the lens would need a study correlating Viewed marks with a comprehension test.
- **Lifecycle hook**: A new GitHub query beside the review-decision observation; only the current user's own state.
- **Without AI**: Yes.
- **Coordination cost**: None.
- **Social form**: Solo; invisible to others by API design (N23:83), the lens it is expected to fail.
- **Verdict**: *Reject*, on social form and demand. The state is private to the viewer by API design, and a tick is not a reading.

#### RV-5 Agent Trace or session provenance shown at review

- **Stage and cell**: RV; the map's "Agent Trace / provenance" cell (N; pinned to a commit, lost on rewrite).
- **What it is**: Each line's producing conversation or model is recorded at commit and rendered in the PR; the reviewer can open the transcript behind a hunk. It asks no act of anyone.
- **Mechanism and evidence**: Agent Trace 0.1.0 records per-file conversations with contributor type human/ai/mixed/unknown and a URL by reference (N24:67–69); its canonical repository returned 404 by 2026-09-13, dormant since 2026-02-06, with no backer emitting or consuming it (N24:73, N24:76, N24:81, N13:68) and one third-party reader (N07:71). git-ai keeps attestations in `refs/notes/ai` and puts the agent in the blame column (N24:83–85); Entire adds a checkpoint trailer (N24:86); Agent Blame paints gutter markers on GitHub PRs (N24:90). Pointers into Claude Code transcripts dereference to nothing after 30 days (N24:102, N24:110); rebases and merges are left to implementations (N24:71); force pushes during review lower merge likelihood (N04:106). Nothing measures whether a transcript is later read (N24:142). Wheeler: AI severs the inference from authorship to comprehension (N08:22).
- **Nearest existing thing**: Agent Blame (N24:90); Copilot's session-log link per commit (N24:108).
- **Authorless code**: Expected to fail: it names the producer, and no format has a human-reviewed field (N23:77, N23:76).
- **Grain**: Line range.
- **Demand**: None (D8).
- **Enforcement and relocation**: Hooks write it automatically (N24:72); nothing to relocate.
- **Decay**: Rewrite loses the pin (N24:71); the URL decays with the vendor store (N24:111).
- **Verifiability**: The trace is verifiable; understanding is not in it.
- **Evidence source**: T; M for adoption (N24:77).
- **Lifecycle hook**: Commit; Dashpot would read notes at Remote Fetch.
- **Without AI**: No; there is nothing to trace.
- **Coordination cost**: None.
- **Social form**: Broadcast, unread (N24:142).
- **Verdict**: *Reject*, on authorless code and demand. It names the producer, has no human-reviewed field, decays with the vendor store, and no one reads it. SB-1's handover is the legitimate record of what a run did; provenance to a transcript is not.

#### RV-6 A named custodian signs the merge

- **Stage and cell**: RV; the accountability cell beside "review decision" (O for merged state; N for the signer).
- **What it is**: An Agent Run's Pull Request merges only when a named person, distinct from any bot approval and recorded as the merger, signs it; approval by the agent's principal does not count as review. The act is signing (principle 15).
- **Mechanism and evidence**: Kernel: agents MUST NOT add Signed-off-by; the human submitter must understand and defend the change (N15:42, N15:45). Copilot's cloud agent authors the commit with the task starter as co-author; the starter's approval does not count (N15:52, N15:55, N15:56). PostHog: a human always merges, agent PRs always get human review (N07:22); Ona: a human clicks merge (N07:26/27); Amazon requires senior sign-off on AI-assisted junior changes after a 13-hour outage (N03:100). Linear's assignee stays responsible (N15:13/14). In 78.9% of agentic PRs one person both reviewed and modified the contribution (N16:16–19, N05:6). Accountability lowered the odds of letting AI produce artefacts, OR 0.82 (N14:20). What "full responsibility" obliges is undefined (N15:135) and no measure of the accountable reviewer exists (N15:134).
- **Nearest existing thing**: GitLab's composite identity attributing the MR to the human who triggered the flow (N24:113).
- **Authorless code**: Passes by construction: the signer is named, not inferred (N15:1).
- **Grain**: Change.
- **Demand**: Approval as a signed claim (D5).
- **Enforcement and relocation**: Branch protection can require a human reviewer distinct from the author; the kernel's rule is unenforced (N16:73). Relocation: rubber-stamp — the 97% approval figure (N14:71).
- **Decay**: Habituation (N21:220–222); "performative" review in Agarwal's data (N16:44–53).
- **Verifiability**: Merger identity is a GitHub field; understanding is not.
- **Evidence source**: T (policies), M (N16:16–19).
- **Lifecycle hook**: PR merged state (O) plus merged-by (N).
- **Without AI**: Yes; it is the DCO.
- **Coordination cost**: Second person per PR.
- **Social form**: Dyadic, public.
- **Verdict**: *Shortlist, folded into the named-person family with ST-6 and IN-4.* One candidate, three signatures: the person who holds the Issue at binding, the person who signs the integration, the person who merges, distinct from the agent's principal. The merger's identity is a GitHub field; what the signature obliges is undefined in every policy read, so the family pairs each signature with a sampled act from the explain-back family rather than trusting the click.

#### RV-7 Post-approval quiz that gates the merger

- **Stage and cell**: RV; the map's quiz cell moved to merge time (M: a required status check).
- **What it is**: After approval, a quiz generated from the diff must be passed before the merge button unlocks; the taker is whoever merges. The act is recall at merge.
- **Mechanism and evidence**: dkamm's PR Quiz: triggers after approval, 100-line threshold, 3 attempts, 10 minutes, anonymous URL, 209 stars (N21:6–8, N21:50–55, N13:24). Revodata: a required `quiz-gate` status, N = ceil(lines/40 × difficulty), 100% to pass, re-push resets, and a threat model admitting the status is forgeable and the quiz is "a review aid, not a secret exam" (N21:9–11, N21:56–63, N21:111–116, N13:26). sphinx-ci: 10 questions, 70%, 3 attempts (N23:143). Show HN raised privacy, circumvention and "works for human PRs too" (N13:25, N21:109). Open questions the note itself lists: who is gated (N21:240), re-push durability (N21:241). No SE-specific harm from a knowledge gate is documented (N23:157).
- **Nearest existing thing**: Revodata pr-quiz (N21:9); the candidate is that, observed as a check Dashpot already reads.
- **Authorless code**: Passes: the merger is quizzed.
- **Grain**: Change.
- **Demand**: Recall, usually recognition (D4).
- **Enforcement and relocation**: Enforced by branch protection; relocation to the agent is the expected bill (N21:109), and 78.9% of the time the merger is the same person who reviewed and edited (N16:16–19), so the gate lands on the author.
- **Decay**: Item leakage (N21:34/38); generated items unvalidated (N23:142).
- **Verifiability**: A pass is on record; the status is forgeable (N21:111–116).
- **Evidence source**: T; no outcome data for any PR-quiz tool.
- **Lifecycle hook**: PR checks/statuses (O); Dashpot shows the pending check.
- **Without AI**: Yes, the HN point (N13:25).
- **Coordination cost**: Adds minutes to merge per PR.
- **Social form**: Solo at the shared object.
- **Verdict**: *Reject*, on relocation and decay. The gate lands on the author 78.9% of the time, the status is forgeable, the items leak, and merge is the wrong boundary: the person's model matters before the Pull Request, not after approval. HO-1 is the evidenced form.

#### RV-8 Reviewer assignment inferred from ownership

- **Stage and cell**: RV; reviewer selection beside "review decision" (O for CODEOWNERS requests; N if inferred).
- **What it is**: The reviewer is chosen by who authored or co-changed the touched files, or by a declared CODEOWNERS map. It asks no act.
- **Mechanism and evidence**: RevFinder ranked a correct reviewer in the top 10 for 79% of 42,045 reviews, offline (N09:60); in vivo at JetBrains over 21,000 reviews showed no evidence recommendations influenced choice, and 69% said recommendation never helps (N09:61, N09:63). Reviewers weigh ownership and recent authorship 82–91%, load only 32% (N09:64). Suggesting the top five co-changers as successors was correct under half the time (N26:167). CODEOWNERS is a glob-to-handle map with no estimation and no decay (N19:151, N15:8–12). Ownership metrics predicted defects at Microsoft under strong ownership (N23:60, N15:16–36), but AI severs authorship from comprehension (N08:22, N15:41/45).
- **Nearest existing thing**: CODEOWNERS (N19:151).
- **Authorless code**: Inferred variants fail: when the last modifier is an Agent Run there is no person to approach (N09:100); the declared map passes because it names people (N15:12).
- **Grain**: File.
- **Demand**: None (D8).
- **Enforcement and relocation**: Auto-request is enforceable; nothing to relocate.
- **Decay**: Method-level knowledge decays in months (N26:157, N26:173); CODEOWNERS has no decay (N19:151).
- **Verifiability**: Assignment verifiable; expertise not.
- **Evidence source**: M (N09:60/61).
- **Lifecycle hook**: PR review-request observation.
- **Without AI**: Yes.
- **Coordination cost**: Reviewer-assignment problems added 12 days (N09:60).
- **Social form**: Routing, not conversation.
- **Verdict**: *Reject*, on authorless code. The inferred variant has no one to recommend when the last modifier is an Agent Run and did not change anyone's choice in vivo; the declared CODEOWNERS map passes the lens but asks nothing.

### Integration and Cleanup (IN)

#### IN-1 Landing order across concurrent Agent Runs

- **Stage and cell**: Integration / Cleanup; verify / approve; "landing order across concurrent runs" (N).
- **What it is**: Dashpot shows, for the Branches whose Worktrees hold or held Agent Runs, a proposed landing order derived from which Branches touch the same files against the Integration Branch, and marks pairs that would conflict. A person confirms or reorders; the order is advisory, and a merge queue or the person's merge sequence performs it. The act asked is a verify: approve the order before the first Pull Request lands.
- **Mechanism and evidence**: Conflict probability rises with concurrent potentially-conflicting changes, 5% to 40% (N12:57, M, a slide without n); 79.4% of agent Pull Requests are open concurrently with another (N12:89, M) and replayed cross-agent pairs conflict 41.7% against 19.8% intra-agent (N12:91, M). Ordering devices exist pre-agent: bors priority markers (N12:53), Rust rollup tags (N12:55), GitHub merge queue FIFO (N12:56), Cassandra's disjoint-footprint scheduling by retrospective simulation (N12:19, N12:51). No vendor page states an order for parallel worktree Branches (N12:66, N12:117). Best card M, observational.
- **Nearest existing thing**: bors and rollups order by reviewer-set priority (N12:53, N12:55); this candidate orders by observed file overlap across live Worktrees, before any Pull Request is queued, and shows the order rather than executing it.
- **Authorless code**: Works: overlap is a Git fact, not an authorship proxy. Cautions: developer-named conflict indicators did not predict conflicts (N12:25) and 42% of agent conflict signals are structural add/add or modify/delete (N12:101, N12:92), which a file-overlap heuristic under-counts.
- **Grain**: Branch, with file-level overlap as the ordering key.
- **Demand**: Verify / approve; the act recorded is the person's confirmation of an order.
- **Enforcement and relocation**: Advisory display (E1 default of the view); one step toward a gate is a merge-queue priority the person sets from it (N12:56). Relocates sequencing work from the integrator's head onto a shown list; adds nothing to the agent.
- **Decay**: A repeating confirm is the click-through shape (N22:38: 97% of prompts approved). It would need sampling: confirm only when overlap is non-empty.
- **Verifiability**: Textual conflict rate per landing before and after, replayed with `git merge-tree` as Xu et al. did (N12:91); horizon a release. No comprehension measure attaches (N12:99).
- **Evidence source**: Uber's curve is vendor-run with no n (N12:57, N12:98); the agent replays are independent but textual-only lower bounds (N12:94).
- **Lifecycle hook**: New observation: file footprints of Branches relative to the Integration Branch (Git, cheap). Channel: observation; the mutation stays with the merge queue or the person.
- **Without AI**: Yes; parallel human Branches conflict at 17%–19% (N12:11) and a third of clean merges hide build or test failure (N12:12).
- **Coordination cost**: Makes visible which Agent Runs are on a collision course and lets the person direct which lands first (principle 12 has one note behind it; second source here is the pre-agent conflict literature N12:10, N12:14). A bound on order, set by the person.
- **Social form**: Team-first; attaches to Branches and the Integration Branch. Alone it degenerates to a self-conflict list, which GitButler names as the worktree cost (N12:77).
- **Verdict**: *Shortlist, in the bound family.* A bound on order, principle 14's third kind, derived from Git facts Dashpot can observe cheaply and shown rather than performed; team-first; pre-agent conflict rates give it its without-AI case; the instrument is textual conflict rate per landing replayed with `git merge-tree`, which the agent studies already used. Principle 14 is single-note but the agent replays (N12:91) and the pre-agent conflict literature are its second source here. The confirm must fire only when overlap is non-empty, or it is the 97%-approved prompt.

#### IN-2 Same-file parallel change shown across Worktrees

- **Stage and cell**: Integration / Cleanup; read / navigate (no cell today) and verify; a push-mode awareness fact rather than an act.
- **What it is**: While two or more Worktrees have uncommitted or unpushed changes to the same file, Dashpot's Worktrees pane marks both rows with the overlap and its severity (direct: same file; indirect: dependent file). Nothing is asked of anyone; the row exists. It fires continuously from Repository State.
- **Mechanism and evidence**: Palantír inverts pull to push and distinguishes direct from indirect conflicts (N27:53); in two laboratory experiments participants with it detected and resolved more conflicts, earlier, and checked in fewer unresolved (N27:55, C). Crystal speculatively merges every pair (N12:48); WeCode detected 28 of 28 indirect conflicts before check-in against 0 of 28 for repository-only detection (N12:50, C). Lack of awareness "occurs more frequently than merge conflicts and is more harmful" (N12:22, T). FASTDash's six-person field study raised SART ratings (N27:58, M, no control).
- **Nearest existing thing**: Palantír (N27:53); the difference is that the parallel workspaces are Worktrees on one machine, some driven by agents, and Dashpot already lists them.
- **Authorless code**: Works; overlap is observed, not inferred from who wrote what.
- **Grain**: File, summarised to Worktree and Branch rows.
- **Demand**: Nothing / artifact — a display. Names no act, which principle 1 marks against it unless paired with IN-1's confirm.
- **Enforcement and relocation**: E1 tool default. Relocates nothing; the cost is a Git diff-stat per refresh.
- **Decay**: An always-on marker habituates like any status glyph; awareness displays are event-fed by construction and do not go stale (N27:67 is the corpus's example), but attention to them does. No card measures a marker's attention over months.
- **Verifiability**: Unresolved conflicts checked in per week (Palantír's outcome, N27:55); conflict persistence mean 10 days, median 1.6 (N12:14) as the baseline. No comprehension instrument.
- **Evidence source**: Two lab experiments and a six-person field study (N27:2); independent, single-session.
- **Lifecycle hook**: New observation: per-Worktree changed-file sets (Git status and unpushed commits); channel: observation only.
- **Without AI**: Yes; it is the pre-agent awareness problem verbatim (N27:54).
- **Coordination cost**: Observability of what each Agent Run is touching now, the who/what/where the awareness literature says no tool shows for an automated actor. Costs nothing to the agent; adds a glyph to the person.
- **Social form**: Team-first; attaches to Worktrees and Branches. Solo, it shows the person's own parallel runs colliding, which the vendor advice assumes away (N12:68).
- **Verdict**: *Shortlist, folded into IN-1 as its observation.* It asks no act, so it is not a friction; but it is the fact IN-1 orders by, and the one awareness display in the corpus with controlled evidence of catching conflicts earlier (N27:55, N12:50). Dashpot already lists the Worktrees; the per-Worktree changed-file set is the missing observation, and it is the who/what/where for an automated actor that principle 12 says no tool shows.

#### IN-3 ADR written at integration with a staleness check

- **Stage and cell**: Integration / Cleanup; nothing / artifact; "ADR / rationale written (N; signal: a scheduled staleness check or none)".
- **What it is**: When a Pull Request that chose among alternatives integrates, a person writes or confirms a one-page decision record under `docs/adr/`, and the record carries a check that runs on a schedule or on change to the files it names. The act asked is a write (or a confirm of an agent's draft); the record's status flips to stale when its check fails.
- **Mechanism and evidence**: Nygard's template and its length-as-currency rule (N24:17, N24:18, A); adoption is low, about half of ADR repositories hold one to five records (N24:172, M); capture cost is the constant — gIBIS's "prohibitive" overhead (N24:9, Q), 60.5% cite lack of time (N24:166, M). Use: rationale questions answered by the record 41% of the time (N24:162, Q); one of two systems showed significant change-impact improvement with a rationale document (N24:168, C). Staleness machinery: adr-kit's pre-commit rule check, daily drift check and bi-weekly audit (N24:60, T); Swimm blocks the PR check until a moved snippet is reselected (N24:39); Henderson's after-action review about a month after implementation (N24:28). "Useful even if not up to date" scores 3.96 of 5 (N24:176). Best card C (N24:168), mixed.
- **Nearest existing thing**: adr-kit (N24:60) is the only ADR skill with staleness machinery; every agent ADR skill requires a human confirmation before writing except Clemmons', where a merged ADR is accepted (N24:56, N24:62). The candidate adds Dashpot observing the record's check state beside the Branch it came from.
- **Authorless code**: Works: the record names the decision, not the author. It is the one artifact the corpus says a future agent reads as much as a person (N24:62).
- **Grain**: Pull Request to module; the record is per decision.
- **Demand**: Generate / write, or verify if an agent drafts (N24:57, N24:58). Recorded act: the write or the confirm, by a named person.
- **Enforcement and relocation**: E3 practice today; one step toward a gate is docs-as-code blocking merge without the record (N24:29) or adr-kit's pre-commit (N24:60). Relocates the writing onto the integrator at the busiest moment (N24:25).
- **Decay**: Half of the Winery MADRs omitted the Pros and Cons out of fear of criticism (N24:26); records thin out under repetition. The staleness check is what does not decay; the writing does. Would need a count of records per month and their length over six months.
- **Verifiability**: Fraction of records whose check has failed and been repaired; later Karsenty-style question-answer rate (N24:162). Horizon months. No study measures whether an agent-written ADR is later read or kept current (N24:188).
- **Evidence source**: Pre-AI surveys and one small controlled experiment; the agent-era ADR skills carry no evidence (N24:184 is automated metrics only).
- **Lifecycle hook**: New observation: presence and check state of a record linked to the Pull Request (a path in the repository plus a CI status, both observable). The gate is a pre-commit or PR check, external to Dashpot.
- **Without AI**: Yes; ADRs predate agents and the Thoughtworks Radar carried them at Adopt in 2017 (N24:21).
- **Coordination cost**: The record is the "reason for the change" a successor otherwise reconstructs from chat history (N11:131); low coordination cost, one page.
- **Social form**: Attaches to the repository and module; recording decisions was found to be a two-or-more-person activity where systematic (N24:173). Works alone as a note to one's future self.
- **Verdict**: *Shortlist.* The one artifact candidate that names its change signal, which principle 6's staleness clause requires: the writing decays, the check does not. A write by a named person, pre-AI, attached to the repository and the module, with a C-level card on change-impact (N24:168) and a known killer in capture cost. Dashpot's part is observing the record's check state beside the Branch it came from; the gate is a pre-commit or PR check. The cheapest test is whether records get written at all when the skill drafts and a person confirms.

#### IN-4 A named person signs the integration

- **Stage and cell**: Integration / Cleanup; verify / approve; overlaps the "who signs" layer-2 stage the map lists but does not row.
- **What it is**: Integration of a Branch that carried an Agent Run is shown as unsigned until a person records, in a place Dashpot observes, that they can defend the change: a `Signed-off-by` trailer on the squash commit, a Pull Request approval by someone other than the Agent Session's initiator, or a review state. The act asked is a verify by a person whose name attaches to the Pull Request.
- **Mechanism and evidence**: Every policy read places accountability on a named person, none on the agent (N15:1, A); the kernel forbids agents adding sign-off and makes the submitter responsible for reviewing all generated code (N15:42, policy), and asks contributors to "understand and be able to defend everything you submit" (N15:45). GitHub's allocation is the inverse and requires a second write-access human (N15:56). Linear keeps the human assignee responsible (N05:33). 78.9% of agentic Pull Requests had one person both review and modify (N05:6, M). Best card M for the pattern; the effect of a signature on anything is unmeasured.
- **Nearest existing thing**: The DCO sign-off (N15:38) and Cilium's AI Influence Level disclosure (N15:49); the difference is Dashpot showing the signature's presence per integrated Branch rather than a project enforcing it in text.
- **Authorless code**: This is the case it exists for; the signer is recorded at the time of signing, never inferred from blame (principle 15). Passes unless the signer is picked by an ownership recommender, which it must not be.
- **Grain**: Pull Request / squash commit.
- **Demand**: Verify / approve; the recorded act is a signature by a named person.
- **Enforcement and relocation**: E4 socially today (N15:67); E5 via a DCO check or a required-reviewers rule, both PR checks Dashpot observes. Relocates accountability explicitly onto one person, the "many hands" problem principle 15 names.
- **Decay**: A signature is the canonical click-through; approvals of agent PRs rose within-reviewer over seven months while inline comments fell (N21:220, N21:221), though that dataset's direction is disputed (N06:65). It would need the signature paired with a sampled defend-it check.
- **Verifiability**: Share of integrated Branches with a named signer; later modification rate of signed against unsigned agent changes, against the untested "no clear owner" hypothesis the analysis cites. No comprehension instrument in the signature itself.
- **Evidence source**: Policy texts and one large observational PR study (N05:6); no vendor telemetry.
- **Lifecycle hook**: Observed today in part (PR author, reviewers, review decision); new observation for commit trailers on the Integration Branch.
- **Without AI**: Yes; the DCO predates agents (N15:38), and Ts'o notes the same problems exist without tools (N15:47).
- **Coordination cost**: Names who the team asks about the change; a second human reviewer is a real cost the kernel and GitHub both accept (N15:56).
- **Social form**: Team-first; attaches to the Pull Request. Alone, the signer is the person, which records nothing new but keeps the habit.
- **Verdict**: *Shortlist, folded into the named-person family with ST-6.* ST-6 signs the binding; this signs the integration. Half of it is observed today (PR author, reviewers, review decision), the trailer on the Integration Branch is new, and principle 15 is among the best-sourced in the corpus. A signature is the canonical click-through, so the family pairs it with a sampled defend-it check from the review stage.

#### IN-5 Branch age at landing shown against a team bound

- **Stage and cell**: Integration / Cleanup; verify / approve; a bound rather than an act (principle 14).
- **What it is**: Each Branches row shows how long the Branch has diverged from the Integration Branch and how far behind it is, coloured against a team-set bound (a day, a couple of days). The act asked is none; the row is the fact, and a Pull Request check may refuse a Branch past the bound.
- **Mechanism and evidence**: Continuous Integration's daily merge (N12:40), trunk-based development's couple of days (N12:43), DORA's under-a-day and fewer than three active Branches (N12:45, T) and hours-versus-days (N12:46, T) are prescriptions resting on argument and cross-sectional self-report, not on the conflict measurements (N12:1, N12:47). Measured: conflicts persisted a mean of 10 days, median 1.6 (N12:14, M); resolution took 22.93 days on average in Perl (N12:17, M); Branch activity raised post-release failures up to 59% (N12:36, M). Best card M, observational.
- **Nearest existing thing**: DORA's branch-lifetime guidance (N12:46); Dashpot already observes ahead/behind and fetch age. The candidate adds the bound and the colour.
- **Authorless code**: Works; age is a Git fact.
- **Grain**: Branch.
- **Demand**: Nothing / verify: a bound the person reads. Records no act.
- **Enforcement and relocation**: E1 display; E5 if a PR check refuses stale Branches. Relocates rebasing work onto whoever holds the Branch — often the agent, via the skill's rebase authority.
- **Decay**: A colour habituates; the bound itself does not decay. Persistence would be measured as Branch-age distribution over months.
- **Verifiability**: Median Branch age at landing and conflict rate per landing; the Sjøberg WIP study shape (lead time halved, N10:31) applied to Branch age. No comprehension measure exists for any bound (N10:162).
- **Evidence source**: DORA is vendor-adjacent self-report (N12:47); the persistence figures are independent mining.
- **Lifecycle hook**: Observed today (ahead/behind, Remote-Tracking Branch age); the bound is configuration.
- **Without AI**: Yes; every source here is pre-agent.
- **Coordination cost**: A bound the team sets; makes visible which Agent Runs are drifting from trunk. Costs the team the agreement on the number.
- **Social form**: Team-first; attaches to Branches. Solo it is a personal nag with the same Git facts.
- **Verdict**: *Shortlist, folded into the bound family.* Ahead/behind and fetch age are observed today; the bound and the colour are configuration. No comprehension measure exists for any bound, which principle 14 accepts and states. Its evidence for the number is prescription and self-report, so the bound is the team's to set and Dashpot's to show.

#### IN-6 Cleanup preview shows what the last Agent Run left behind

- **Stage and cell**: Integration / Cleanup; read / navigate (no cell) leading to verify; Cleanup is M and stays a confirmed selection.
- **What it is**: The Cleanup preview for a Worktree or Branch lists, beside integration and recovery facts, whether the Worktree's last Agent Run ended with a `work stop`, an Orphaned Agent Run, or a lost `SessionEnd`; whether a handover record (SB-1) exists for it; and any unintegrated content. The act asked is the existing confirmation, now made against those facts.
- **Mechanism and evidence**: Vendors remove worktrees on exit or by sweep: Claude Code's exit prompt deletes "the worktree, its branch and all the work" (N12:61, T); Codex keeps 15 and snapshots before deleting (N12:73); Cursor sweeps every six hours (N12:69). Agent Handoff writes a snapshot "only at a legitimate outcome boundary, blocker, interruption, or transfer" (N11:128). The shift literature's costs of a missed update are the receiver's, not the artifact's (N11:19, N11:20). Best card T.
- **Nearest existing thing**: Codex's snapshot-before-delete (N12:73); the difference is that Dashpot never deletes on its own and only shows the person what a confirmed removal would discard.
- **Authorless code**: Works; the facts are Work Store and Git state.
- **Grain**: Worktree and Branch.
- **Demand**: Read then verify; records the confirmation, which Cleanup already does.
- **Enforcement and relocation**: E1 within the existing confirm dialog. Relocates nothing new.
- **Decay**: Cleanup is infrequent, so habituation is low; the risk is the preview growing until it is skimmed.
- **Verifiability**: Count of Cleanups that removed a Worktree with an Orphaned Agent Run or no handover, before and after. No comprehension instrument.
- **Evidence source**: Vendor documentation of deletion behaviour; no study.
- **Lifecycle hook**: Observed today (Orphaned Agent Runs, integration by content); new observation for the handover record's existence.
- **Without AI**: Partly; a human-only Worktree has no Agent Run, but unintegrated content and a dirty tree still show.
- **Coordination cost**: Low; it is one more block in a dialog the person already reads.
- **Social form**: Attaches to Worktree and Branch; on a shared machine it tells the person whose run they are about to discard.
- **Verdict**: *Reject as a candidate; recorded for the backlog.* It asks no new act — the confirm exists — and is an improvement to the Cleanup preview that becomes possible once SB-1's record exists. Worth doing; not a member of this family.

#### IN-7 Integrator recommended from ownership metrics (expected to fail a lens)

- **Stage and cell**: Integration / Cleanup; verify / approve.
- **What it is**: Dashpot suggests who should land or sign a Branch by computing degree-of-knowledge or truck-factor weights over the files it touches, from Git history. The act asked is the suggested person's approval.
- **Mechanism and evidence**: DOK regresses first authorship, deliveries, acceptances and interaction, R² = 0.25 on 246 self-ratings (N23:66, M; N19:126); truck factor reuses the DOA weights and 65% of 133 systems have TF ≤ 2 (N19:148); top-five co-changer expert suggestion was right 48% and 34% of the time (N26:167, M); footprint tools infer knowledge from authorship and none asks a person (N18:95, A).
- **Nearest existing thing**: Reviewer and expertise recommenders (N26:167); the candidate is the same inference applied at landing.
- **Authorless code**: Fails: the inference was weak before agents and agent authorship breaks it across all such instruments (principle 15; N18:95). On an agent-authored Branch the "owner" is the session's initiator by construction.
- **Grain**: File to Branch.
- **Demand**: Verify / approve.
- **Enforcement and relocation**: E1 suggestion; relocates review onto whoever authored most, which is the agent's operator.
- **Decay**: The weights drift toward whoever accepts the most agent output.
- **Verifiability**: Agreement with developer-named owners was 55% (N23:66); a Dashpot version would be scored the same way.
- **Evidence source**: Independent but pre-agent and self-report-anchored.
- **Lifecycle hook**: Observed today (Git history); observation channel.
- **Without AI**: Works as well as it ever did, which is under half.
- **Coordination cost**: Low; a name in a row.
- **Social form**: Attaches to Branch and person; the person named is not necessarily the one who understands. On record so the rejection is explicit.
- **Verdict**: *Reject*, on authorless code. The recommender at landing: on an agent-authored Branch the "owner" it computes is the session's initiator by construction.

### Session boundary: stop, relocate, end (SB)

#### SB-1 State-and-stance handover kept by the Work Store

- **Stage and cell**: Session boundary; generate / write; "state + stance handover written by the outgoing holder (N)".
- **What it is**: Before `work stop`, `work relocate`, or a planned session end, the outgoing holder — usually the agent, under the `dashpot-issue-work` skill's finish step — writes a short structured record the Work Store keeps beside the Agent Run: current state, next direct step, what the holder believes, intends, expects to happen, and what it would do if it did not. The person is asked for nothing at write time; SB-2 is the receiving act.
- **Mechanism and evidence**: What transfers is a state model plus a stance (N11:1, A); stance toward contingencies was given in every observed mission-control handoff (N11:10, M) and is not a named field in any documented agent schema (N11:148). Written-only communication failed in four of five investigated incidents (N11:31, Q); a structured log built from the incoming person's information needs carried state where discretionary notes did not (N11:40, N11:36). I-PASS cut medical errors 23% and preventable adverse events 30% over 10,740 admissions without lengthening the handoff (N11:59, N11:60, M). For an agent successor, context-bearing handoffs cut median events 20–59% (N04:114, M). Nothing measures what a person recovers (N11:181). Best card M.
- **Nearest existing thing**: Agent Handoff's snapshot schema (N11:129) and HumanLayer's `progress.md` (N11:133); both carry state, next step and proof, not stance (N11:132). Dashpot's Relocation Intent already records a target at the boundary and nothing about state.
- **Authorless code**: Works: the record is about the run, not about who wrote the code; the agent as outgoing holder is exactly the authorless case.
- **Grain**: Agent Run, hence Issue and Worktree.
- **Demand**: Generate / write by the outgoing holder; the recorded act is the record's existence and author (agent or person).
- **Enforcement and relocation**: E2 via the skill's instruction; one step toward default is the hook publisher refusing to reconcile a `work stop` with no record. Relocates writing onto the agent; reading onto the receiver.
- **Decay**: Agents fill schemas reliably but the content thins: Chang found to-dos communicated 65% and knowledge items 38% (N11:51). Would need the record's field completeness tracked per month, and the skill varying its prompts.
- **Verifiability**: Receiver's questions per handover (SB-2) and the Chang instrument: do sender and receiver agree on the most important item (60% did not, N11:50). Horizon weeks.
- **Evidence source**: Medical and mission-control field studies (independent, non-software); agent-successor benchmark (single-session, agent receiver).
- **Lifecycle hook**: Mutation of the Work Store by a named command the session runs; observation shows it; channel: skill plus `work stop` / `relocate`. Depends on principle 13, single-note; second source is the agent-successor measurement (N04:114) and the Iqbal "preparing before switching" practice (N11:80).
- **Without AI**: Yes, as the pre-suspension note 36% of programmers already write (N11:81), given a place to keep it.
- **Coordination cost**: Makes the agent's belief and intent observable (challenge 5, N04:41) at the one moment it stops; costs one write per boundary.
- **Social form**: Attaches to the Issue via the Agent Run; visible to a second agent, a reviewer, or the person resuming. Solo it is a self-handover (N11:70).
- **Verdict**: *Shortlist, head of the handover family, as a pair with SB-2.* The agent is the outgoing holder, which is the authorless case exactly; the Work Store already sits at the boundary and records a target and nothing about state; the structured-record evidence is M-level and from three domains, with N04:114 as the second source principle 13's single-note caveat requires. It asks the person for nothing, so its act is SB-2's and the two are one candidate. ST-4's stance at start and RT-4's cue at stop are fields of this record.

#### SB-2 The receiver asks before resuming

- **Stage and cell**: Session boundary; explain; "receiver asks before resuming (N)".
- **What it is**: Before an Agent Run resumes — a resumed Codex turn, a session re-entering a Worktree, or a person taking over — the receiver poses questions against the handover (SB-1) and the Worktree, and the outgoing record or the person answers; the skill's resume step runs this before `work start` or continuation, and the questions and answers are appended to the record. The act asked is an ask, by an agent or a person.
- **Mechanism and evidence**: "A handoff is not a telegram": the receiver's questions are where the model is reconstructed (N11:3, N11:63, A); 8 of 75 incoming questions at NASA were asked to detect errors (N11:16, M); all six taped misunderstandings were repaired by the incoming person asking (N11:32, M); in the majority of medical handoffs the incoming clinician asked no questions (N11:66, M). Klein: breakdowns are inevitable and the baseline is detecting and repairing them, not documenting everything (N11:93, A). Best card M.
- **Nearest existing thing**: Agent Handoff's receiver cross-check is the acceptance proof, not a question (N11:132); `bd prime` and Claude Code's re-read of five files are reads, not asks (N11:149). The candidate makes the question the step.
- **Authorless code**: Works: the questions are about state and stance, and a run can be asked about them whoever wrote the code.
- **Grain**: Agent Run / Issue.
- **Demand**: Explain (the answerer) and read-or-navigate's "ask" (the receiver); the recorded act is the question list.
- **Enforcement and relocation**: E2 skill instruction; a hook could refuse `work start` at a Worktree with an unanswered handover, one step toward E5. Relocates a few minutes onto the receiver; for a person receiving from an agent it is the mission-control ten-minute update (N11:6).
- **Decay**: Nurses hesitated to give the "recommendation" step (N11:53); readback was one of two strategies never observed (N11:8). Would need a fixed minimum of one error-detecting question, varied by the skill.
- **Verifiability**: Rate at which a question changes the next step (the "fresh perspective" catch, N11:16); Chang's agreement instrument (N11:50). Horizon weeks.
- **Evidence source**: Field observation in non-software domains; no software measurement (N11:181).
- **Lifecycle hook**: New observation (an ask is an act); channel: skill, with the record written through the Work Store. Depends on principle 13; second source is Lardner's communication-theory argument (N11:22) and the routing theme's "ask is observable" (N09:76 for the AI-as-answerer context).
- **Without AI**: Yes; it is the shift-change update between two people.
- **Coordination cost**: This is the coordination cost, made explicit and bounded; it is also the redirect point principle 12 wants.
- **Social form**: Attaches to the Issue; the question list is what a reviewer or newcomer reads instead of a transcript.
- **Verdict**: *Shortlist, paired with SB-1.* The receiving act: a question before resuming, by an agent or a person, appended to the record. The ask is the act principles 9 and 13 both name, and the instrument is Chang's agreement test — do sender and receiver name the same most important item — plus the rate at which a question changes the next step. Its decay is the medical finding that most incoming clinicians asked nothing, so the skill must require one error-detecting question.

#### SB-3 The undone list, reconciled against observed facts

- **Stage and cell**: Session boundary; read / navigate; "what the run left undone (O: Work Store; N: state)".
- **What it is**: At `work stop` or `SessionEnd`, the Work Store records the run's own list of what it did not finish, and Dashpot checks each item against what it observes: uncommitted changes, unpushed commits, an open Pull Request with failing checks, an Issue still open. Disagreements — the run says done, Git says dirty — are shown as a Diagnostic. The act asked of a person is to read the reconciled list; of the agent, to write it.
- **Mechanism and evidence**: Omissions at sign-out were of tasks to be done and "a specific plan of action and rationale" (N11:49, M); to-do items were communicated 65% of the time (N11:51). Inaccurate self-reporting — claiming success or completion prematurely — is 22.58% of agent misalignment episodes and rising (N04:117, N04:119, M). Agent Handoff's "Next direct outcome step" and progress-stalled rule (N11:128, N11:129). Beads keeps the graph and drops the transcript (N11:125). Best card M.
- **Nearest existing thing**: Dashpot's Orphaned Agent Run diagnostic, which says a run was left, not what it left; Manus's recited `todo.md` (N11:137). The reconciliation against Git is the new part.
- **Authorless code**: Works; the check is against repository facts.
- **Grain**: Agent Run, Worktree, Pull Request.
- **Demand**: Read for the person; write for the agent; recorded act: the list and its reconciliation.
- **Enforcement and relocation**: E1 for the check (observation), E2 for the list (skill). The skill's finish rule already waits for CI green; this adds the record when it does not. Relocates nothing onto the person beyond a read.
- **Decay**: A reconciled Diagnostic does not habituate the way a confirm does; it fires only on disagreement, which is the sampled shape.
- **Verifiability**: Share of stops whose self-report disagreed with Git; that is a direct measure of N04:117 on this lifecycle. Horizon weeks.
- **Evidence source**: Medical field study and one large observational agent dataset (N04:117).
- **Lifecycle hook**: Observed today (Work Store, Git dirty state, PR checks) plus a new Work Store field; channel: `work stop` and the hook publisher's `SessionEnd`.
- **Without AI**: Yes; a person's `work stop` benefits the same.
- **Coordination cost**: Observability of the gap between the agent's claim and the repository, which 91.49% of resolutions otherwise need explicit user correction to find (N04:118).
- **Social form**: Attaches to Issue and Pull Request; a second agent or a reviewer sees the same list.
- **Verdict**: *Shortlist, the handover family's verification and the cheapest candidate in the stage.* Almost entirely observed facts — Work Store, dirty state, unpushed commits, PR checks — against the run's own claim of what it left, firing only on disagreement, which is the sampled shape principle 4 wants. It measures inaccurate agent self-report (N04:117) directly on this lifecycle, and a person's `work stop` benefits the same.

#### SB-4 Stop only at an outcome boundary, and show a dirty end

- **Stage and cell**: Session boundary; verify (no cell); a bound on when the boundary may fall.
- **What it is**: The skill instructs the agent to end or relocate a run only at an outcome boundary — commits landed, checks reported, or a blocker stated — and Dashpot marks a `SessionEnd` that arrives with a dirty Worktree or unpushed commits as a mid-activity end. The person is asked to verify such an end before treating the Worktree as quiet.
- **Mechanism and evidence**: Transfer is delayed during critical activity, once for several hours (N11:15, M); an eight-second interruption lag improved resumption (N11:72, C); the goal must be strengthened before suspension (N11:71, C). Agent Handoff writes only at a legitimate boundary (N11:128); vendors advise `/compact` before a long new task and a fresh session once the spec is complete (N11:153, N11:106). Iqbal's workers "prepared" state before switching (N11:80). Best card C, laboratory seconds.
- **Nearest existing thing**: The skill's finish step (stop after CI green); Agent Handoff's boundary rule (N11:128). The addition is the observed mid-activity end.
- **Authorless code**: Works; dirty state is a Git fact.
- **Grain**: Agent Run and Worktree.
- **Demand**: Verify; the recorded act is the person's acknowledgement of a mid-activity end.
- **Enforcement and relocation**: E2 (skill) for the agent; E1 (Diagnostic) for the person. Relocates the tidy-up onto the agent before it stops.
- **Decay**: The Diagnostic fires only on dirty ends; the skill instruction is the part that can be ignored under pressure. No card read here measures adherence to a stop rule over months; it would need stops with a dirty tree counted per month.
- **Verifiability**: Share of session ends with a dirty Worktree, over months; resumption time at the next session (edit lag, N11:86) as the outcome.
- **Evidence source**: Lab interruption studies (independent, seconds-scale, N11:74) and vendor practice pages.
- **Lifecycle hook**: Observed today (`SessionEnd`, dirty state); channel: hook publisher and skill.
- **Without AI**: Yes; the blinking cursor and the deliberate compile error are human practices (N11:77, N11:88).
- **Coordination cost**: Predictability: the team can know a quiet Worktree is quiet.
- **Social form**: Attaches to Worktree; on record for whoever enters next.
- **Verdict**: *Shortlist, folded into SB-3.* A `SessionEnd` with a dirty Worktree is one of SB-3's disagreements; the skill's "stop at an outcome boundary" is the instruction that reduces them. The lab evidence is seconds-scale and the field evidence is vendor practice, so it adds a rule to SB-3 rather than a candidate.

#### SB-5 Compaction as an observed boundary with a handover first

- **Stage and cell**: Session boundary; nothing / artifact; "compaction summary (M: harness-side; consumed once, does not age)".
- **What it is**: The hook publisher observes the harness's compaction event (Claude Code re-runs `SessionStart` hooks with the `compact` source, N11:100) and the skill asks the agent to write the SB-1 handover before an intentional `/compact` or `/clear`. Dashpot shows compactions on the Sessions row as boundaries within a session. The person is asked nothing; the agent is asked to write.
- **Mechanism and evidence**: Compaction keeps intent, files, errors and pending tasks and drops tool outputs and reasoning (N11:97); "detailed instructions from early in the conversation may be lost" (N11:101); the compactor "is fundamentally unaware of precisely what information the agent will need later" and errors "silently propagate through coherent but incorrect behavior" (N11:141, M); retained content fluctuates run to run (N11:142, M); the loss is of the actionability of recent state (N11:146, A). `/compact [instructions]` and a CLAUDE.md compact-instructions section exist (N11:102, N11:104); intentional compaction writes goal, approach, steps and current failure to a file first (N11:133, T). Best card M, agent benchmarks.
- **Nearest existing thing**: HumanLayer's intentional compaction (N11:133); the difference is that the boundary becomes an event Dashpot sees and the record lands in the Work Store rather than a loose file.
- **Authorless code**: Works.
- **Grain**: Agent Session, sub-turn.
- **Demand**: Artifact; the agent writes, no person acts. Fails principle 1 on its own; it exists to feed SB-1 and SB-2.
- **Enforcement and relocation**: M harness-side for the compaction itself; E2 skill for the write; the observation is E1. Relocates nothing onto the person.
- **Decay**: Compaction summaries are consumed once and do not age (the map's note); the handover written before them can go unread, which SB-2 addresses.
- **Verifiability**: Number of compactions per run and whether the next turn's actions repeat exploration (blocked actions and repeated exploration after compression, N11:145). Horizon a session.
- **Evidence source**: Vendor documentation and independent agent benchmarks; single-session; no human measure (N11:109).
- **Lifecycle hook**: New observation via the existing hook publisher (a `SessionStart` with `compact` source); channel: hook publisher and skill.
- **Without AI**: No; compaction is an agent-only event. The candidate exists for the agent side of principle 13.
- **Coordination cost**: Makes an invisible internal event observable to the team watching the Sessions pane.
- **Social form**: Attaches to the session first; through SB-1 to the Issue.
- **Verdict**: *Hold*, on without-AI and demand. Compaction is an agent-only event and the candidate asks nothing of a person; it exists to trigger SB-1's write before the harness forgets. Held as an SB-1 trigger, observable today through the hook publisher's compact-source `SessionStart`.

#### SB-6 The handover posted to the Issue, not only the Work Store

- **Stage and cell**: Session boundary; generate / write; the shared-object variant of SB-1.
- **What it is**: The SB-1 record, or a digest of it, is posted as a comment on the Issue (or the open Pull Request) at `work stop`, so that the handover lives where the team reads and outlives the Worktree and the transcript. The act asked of the agent is the post; of a person, none.
- **Mechanism and evidence**: Issue comment history was favoured over instant messaging as a persistent, asynchronous, multicast channel and "just having this record of the decision pattern is invaluable" (N27:81, N27:82, Q). Linear's session "belongs to the organisation" and its review sits beside the issue (N05:3, N05:35, T); a Codex report proposes explicit handoff artifacts owned by the project rather than implicit transcript sharing (N05:43); Agent Handoff keeps `ai/handoffs/` in the repository (N11:126); a preprint proposes binding retained memory to Git so it inherits review and history (N05:18). Transcripts are deleted after 30 days (N11:108, N11:179). Best card Q.
- **Nearest existing thing**: Agent Handoff's repository-local `ai/handoffs/` (N11:126); the difference is the Issue Source as the home, which Dashpot already observes.
- **Authorless code**: Works.
- **Grain**: Issue and Pull Request.
- **Demand**: Write (agent); the recorded act is the comment, attributable to the session's initiator.
- **Enforcement and relocation**: E2 skill; one step toward default is a hook that posts the digest itself, which is a mutation Dashpot would have to name (ADR 0008) — priced as a new named command, not observation.
- **Decay**: Comment noise: bots producing more notifications than value is the central complaint about bots (N27:98). Would need one digest per stop, never per turn.
- **Verifiability**: Whether the next Agent Run's first read (N11:127 pattern) hits the comment; whether a reviewer cites it. Horizon weeks.
- **Evidence source**: Qualitative field studies and vendor product design; no measurement.
- **Lifecycle hook**: Mutation of the Issue Source by the session (or a new named command); observed afterwards as an Issue fact.
- **Without AI**: Yes; a person's stop note on the Issue is ordinary practice.
- **Coordination cost**: Low per post; the Issue is already the multicast channel.
- **Social form**: Team-first by construction; the record is readable by anyone the Issue is visible to, including a second agent.
- **Verdict**: *Shortlist, folded into SB-1 as the question of where the record lives.* Principle 9 says attach to the shared object, not only a session; the Work Store is Project-local and dies with the checkout's state, and the Issue is where the team reads. But posting is a mutation of the Issue Source and under ADR 0008 must be a named command, never a hook side effect. Work Store, Issue comment, or both is a decision for the grilling, not a lens.

#### SB-7 The transcript as the handover (expected to fail a lens)

- **Stage and cell**: Session boundary; nothing / artifact.
- **What it is**: Keep the full conversation, or its compaction summary, as the handover: the next session resumes from it (`--resume`, N11:105) and a person is pointed at it on return. No act is asked.
- **Mechanism and evidence**: The OpenAI Agents SDK's default handoff transfers the entire history (N11:119, T); Claude Code's resume restores a transcript rather than a summary (N11:105); provenance tooling keeps the raw agent transcript as the record of why (N24:4; Agent Trace, N13:67). Against: context rot degrades performance as input grows (N11:139, M); the receiver's model is rebuilt by questions, not by the sender's summary (N11:3); the CLI transcript is "ephemeral interactions lost in a terminal's scroll-back buffer" (N04:104); the Agent Trace repository is gone with no consumer (N13:68, N07:70).
- **Nearest existing thing**: Every harness's resume; this is the status quo named as a candidate.
- **Authorless code**: Indifferent.
- **Grain**: Session only.
- **Demand**: Nothing; no act. Fails principle 1.
- **Enforcement and relocation**: E1 default of every harness; relocates reading onto the receiver in full.
- **Decay**: Deleted at 30 days (N11:108).
- **Verifiability**: None proposed; the corpus has no measure of what a person recovers from a transcript (N11:181).
- **Evidence source**: Vendor defaults.
- **Lifecycle hook**: Observed only as a session; attaches to no shared object.
- **Without AI**: Meaningless; a human session has no transcript.
- **Coordination cost**: High for a reader; none for the writer.
- **Social form**: Session-only, the chat-centric shape the thesis argues against (N05:2). On record so the rejection is explicit.
- **Verdict**: *Reject*, on demand and social form. The status quo named: session-only, deleted at thirty days, no act, meaningless without an agent. The chat-centric shape the thesis argues against.

### Arrival at review: rate and WIP (AR)

#### AR-1 A bound on open Pull Requests awaiting review, per person

- **Stage and cell**: AR; the map's "open PRs bounded per person" cell (N; M if enforced).
- **What it is**: Dashpot shows, per person, the count of open Linked Pull Requests with no review decision against a configured bound; the Glyph goes red above it. No act is required to see it (principle 14); the act it invites is not opening another.
- **Mechanism and evidence**: Kanban's WIP limit is a count constraint on items in progress, with age, throughput and cycle time as its metrics and nothing on understanding (N10:3–8); WIP limits halved lead time from 12 to 5 days at one company without a control (N10:30–36) and cut it 37% in another (N10:37–43). kilocode caps contributors at three open PRs (N16:84); 3 of 188 policies limit PRs, 1.6% (N16:69, N21:147). Google's baseline is a median 3 changes authored and 4 reviewed per developer-week, 3.2 hours of review (N16:2/3/5). PostHog went from 1,441 to 4,725 PRs a month with 10% more engineers (N07:23); adopters merged roughly 24% more PRs (N14:23). Merge queues have no reviewer-load setting (N16:98). No study links WIP to comprehension (N10:54, N10:162).
- **Nearest existing thing**: kilocode's three-PR rule (N16:84); DORA's fewer than three active branches (N12:45).
- **Authorless code**: Passes: counted per named person opening PRs.
- **Grain**: Person × PR.
- **Demand**: None on display; a bound, not an act.
- **Enforcement and relocation**: Observed only, or a skill instruction refusing to open a fourth (M). Relocation: batch into one large PR — the size lens (AR-3).
- **Decay**: Thresholds get dropped, as Rust/LLVM dropped a line threshold (N16:83).
- **Verifiability**: A count; exact.
- **Evidence source**: M/Q for lead time (N10:30–36); none for comprehension — the lens would need a WIP-varied study with a comprehension outcome (N10:54).
- **Lifecycle hook**: PR state and review decision are already observed; the per-person count is derived.
- **Without AI**: Yes; it is Kanban.
- **Coordination cost**: It is a coordination device.
- **Social form**: Team-visible board.
- **Verdict**: *Shortlist, head of the bound family.* Open Pull Requests without a review decision per person, against a bound: observed today, exact, pre-AI, team-visible, with the only before–after evidence any team-level friction has. No study links WIP to comprehension, which principle 14 states and accepts. The family's other members — IS-5/AR-2's runs per person, IL-6/AR-3's change size, IN-1's landing order, IN-5's Branch age, AR-5's queue age — are the same display with different counters.

#### AR-2 A bound on concurrent Agent Runs per person

- **Stage and cell**: AR; the map's "concurrent Agent Runs bounded per person" cell (N; M if `work start` refuses).
- **What it is**: Dashpot shows the number of live Agent Runs per person across Worktrees, from the Work Store, against a bound. No act; a red Glyph.
- **Mechanism and evidence**: Cursor: "run as many agents as you want in parallel" (N12:71). Cross-agent PR pairs conflicted 41.7% versus 19.8% intra-agent (N12:91); agent PRs conflicted 27.67% at closure (N12:83). DORA: fewer than three active branches (N12:45); trunk-based: one developer per branch (N12:43). People make about 70% of planning decisions but only 20% of execution decisions, each prompt triggering around 10 actions (N14:34); more than half of Anthropic staff can fully delegate only 0–20% of their work (N14:33). Kanban's constraint (N10:3–8); context-switching cost is asserted without citation in the WIP literature (N10:10). Naur: the agent's session held the mapping and ends (N08:9). No card measures concurrent agent runs against understanding; principle 14's single-note caveat applies.
- **Nearest existing thing**: Kanban WIP (N10:3–8) applied to Agent Runs; nothing in the corpus does this.
- **Authorless code**: Passes: the bound is on the person.
- **Grain**: Person × Agent Run.
- **Demand**: None.
- **Enforcement and relocation**: `work start` could refuse above the bound (M, a named command, ADR 0008). Relocation: run agents outside the Issue Binding, which Dashpot sees only as live sessions.
- **Decay**: Bounds drift upward with familiarity; no card.
- **Verifiability**: Exact count from `.dashpot/state/`.
- **Evidence source**: M for conflicts (N12:91), T for vendor stance; none for comprehension — the lens would need a study varying concurrent runs and testing the person.
- **Lifecycle hook**: Work Store plus SessionStart/SessionEnd hooks (observed today).
- **Without AI**: No; Agent Runs are the unit.
- **Coordination cost**: None.
- **Social form**: Team-visible.
- **Verdict**: *Shortlist, folded into the bound family with IS-5.* The same bound seen at arrival rather than at binding; the Work Store already counts it. Its evidence is conflict mining and vendor stance, and it fails without-AI on its own, which is why it is one counter on AR-1's board rather than a candidate.

#### AR-3 A bound on change size at PR open

- **Stage and cell**: AR; the map's "change size bounded per person" cell (N; M as a PR check).
- **What it is**: Lines and files changed on a Linked Pull Request are shown against a bound; above it the Glyph asks for a split. No act to see it.
- **Mechanism and evidence**: Useful review comments fall with file count and reviews turn cursory (N10:61/63); Cohen: 200–400 lines and 400 lines per hour (N10:64–69); Google's guidance marks 100 and 1,000 lines (N10:70/71); Microsoft developers "struggle with large reviews" (N16:9). Larger changes are less likely to merge after controlling for agent and engagement (N04:107); conflict rate rises from about 9.9% at 2-line churn to nearly 30% at 25 lines (N12:87). Faros reports PR size up 154% among AI-heavy teams (N16:26–33, N23:86). Rust/LLVM dropped a 150-line threshold (N16:83); docusaurus requires prior communication above 1k lines (N16:86); Ona auto-approves under 1,000 lines (N07:26); dkamm quizzes above 100 (N21:53). Review performance is bounded by working memory (N08:127). Litt's fifty-thousand-line PRs are illustration, not measurement (N25:7).
- **Nearest existing thing**: docusaurus's 1k-line rule (N16:86).
- **Authorless code**: Passes.
- **Grain**: Change.
- **Demand**: None; the split it invites is an act.
- **Enforcement and relocation**: PR check (M). Relocation: many small PRs (AR-1's bill) or vendored/minified padding, which Revodata's pool excludes (N13:26).
- **Decay**: Thresholds dropped (N16:83).
- **Verifiability**: Exact.
- **Evidence source**: M (N10:61/63, N04:107).
- **Lifecycle hook**: PR observation; additions/deletions are GitHub fields (new).
- **Without AI**: Yes; pre-AI review guidance.
- **Coordination cost**: Splits multiply review events.
- **Social form**: Team-visible.
- **Verdict**: *Shortlist, folded into the bound family with IL-6.* Change size at PR open against a bound, with the best comprehension-adjacent evidence any bound has (59% against 35% review effectiveness). Additions and deletions are a GitHub field Dashpot does not yet read.

#### AR-4 Review rate flag: lines per hour of review

- **Stage and cell**: AR; rate beside "review decision" (N).
- **What it is**: For each review decision, Dashpot derives lines changed over time from review request to decision and flags reviews faster than a bound. No act.
- **Mechanism and evidence**: McIntosh's "hastily reviewed" metric: approved faster than 200 lines per hour, framed as process quality (N23:85); Cohen's 400 lines per hour (N10:66); Google's 200 lines per hour effort rule of thumb (N16:11). No dataset records effort per change (N16:10, N16:54, N16:127). Review latency rose 3.5× while comments fell under agent PRs (N21:220–222); Agarwal's later data reverses the direction (N16:53, N06:65); Faros: time in review up 441.5% (N06:65). Vendor products measure windows, not reading (N23:84).
- **Nearest existing thing**: McIntosh et al.'s metric (N23:85).
- **Authorless code**: Passes.
- **Grain**: Change × reviewer.
- **Demand**: None; expected to fail principle 1.
- **Enforcement and relocation**: Glyph only. Relocation: leave the tab open.
- **Decay**: None in the measure.
- **Verifiability**: Time is exact; reading is not inferable (N23:84).
- **Evidence source**: M (N23:85).
- **Lifecycle hook**: Review decision (O) plus timestamps (new field).
- **Without AI**: Yes.
- **Coordination cost**: None.
- **Social form**: Individual, visible.
- **Verdict**: *Hold, as the review family's decay instrument.* No act, so not a friction; but lines per hour of review is the one measure in the corpus that would show whether RV-1 and RV-6 habituate, and the direction of the existing data is disputed. Held as the instrument principle 4's decay clause asks for, not as a candidate.

#### AR-5 Review-queue age

- **Stage and cell**: AR; the map's arrival row as a flow metric (N).
- **What it is**: Dashpot shows each Linked Pull Request's age since review was requested, and the oldest per reviewer. No act.
- **Mechanism and evidence**: Work item age is one of Kanban's four flow metrics (N10:6). Receiving at least one review is the strongest correlate of merging (N04:106); most AI-generated PRs receive no review, and reviews they get are largely by agents (N14:63); the no-review share of merged agentic PRs fell from over 50% to about 12% as time-to-merge lengthened from about 20 minutes to 2–3 hours (N16:44–53, N06:65); unreviewed merges up 31.3% at Faros (N16:26–33). Google's median latency is under four hours at 24 lines (N26:198). Pickup and review time are vendor staples (N23:84). Reviewer-assignment problems added 12 days (N09:60).
- **Nearest existing thing**: LinearB's Pickup Time (N23:84).
- **Authorless code**: Passes.
- **Grain**: PR.
- **Demand**: None.
- **Enforcement and relocation**: Glyph; vitest's auto-close after 3 days (N21:154) is the enforced variant.
- **Decay**: None.
- **Verifiability**: Exact.
- **Evidence source**: M (N04:106).
- **Lifecycle hook**: PR observation plus review-requested timestamp.
- **Without AI**: Yes.
- **Coordination cost**: None.
- **Social form**: Team-visible.
- **Verdict**: *Shortlist, folded into AR-1.* Queue age is the second flow metric on the same board, and the finding that most agent PRs receive no review is what it makes visible.

#### AR-6 Hard stop on agent-authored arrivals

- **Stage and cell**: AR; the extreme of the bound cell (M, external policy or bot).
- **What it is**: The project closes or refuses agent-authored PRs, or auto-closes stale ones; Dashpot shows the closed state. No act of understanding.
- **Mechanism and evidence**: pocketbase stopped accepting AI contributions (N16:85); vitest auto-closes after 3 days (N16:87, N21:154); bans (N16:70–72); curl's maintainers' account of AI-report load (N16:55–68). Stage gates carry no comprehension content (N10:94/95). Volume rebounds with capacity, Jevons (N16:104–107). Most AI PRs get no review anyway (N14:63).
- **Nearest existing thing**: vitest's auto-close (N21:154).
- **Authorless code**: Fails the test the other way: it acts on inferred authorship, which disclosure policies leave unenforced (N16:73, N24:114).
- **Grain**: PR.
- **Demand**: None.
- **Enforcement and relocation**: Fully enforced; relocation: strip the trailer (N16:73).
- **Decay**: Policies revisited (N16:83).
- **Verifiability**: Exact.
- **Evidence source**: T.
- **Lifecycle hook**: PR closed state (O).
- **Without AI**: No; it targets agent output.
- **Coordination cost**: Saves reviewer time; loses contributions.
- **Social form**: Project rule.
- **Verdict**: *Reject*, on without-AI and authorless code. It acts on inferred authorship, which disclosure policies leave unenforced, and it saves reviewers by refusing the work rather than by anyone understanding it.

#### AR-7 Definition of Done ticked before requesting review

- **Stage and cell**: AR; the arrival gate as a shared-understanding checklist (N; M as a PR template check).
- **What it is**: Before requesting review the author ticks a short team-agreed list — tests run locally, invariants named, one thing the reviewer should look at — in the PR body. The act is ticking against a shared definition.
- **Mechanism and evidence**: Definition of Done is the shared-understanding device: 93% found it valuable, yet 70% or more report differing understandings (N10:29, N10:85–93). I-PASS chose illness severity, contingency and read-back because those were most often missing, cut medical errors 23% across nine hospitals, and did not lengthen the handoff (N11:56, N11:59, N11:60); a SIGNOUT pilot found most handoffs did not adhere to the mnemonic (N11:57). Review checklists: higher cognitive load led to better performance (N23:116). GitHub's eight-step review checklist has no comprehension check on the author (N13:34). MADR's Confirmation section says how, not who (N24:20). PostHog: "You own what you submit" (N07:21).
- **Nearest existing thing**: PR templates; PostHog's AI_POLICY (N07:21).
- **Authorless code**: Passes: the ticker is named.
- **Grain**: Change.
- **Demand**: Approval of one's own claims (D5).
- **Enforcement and relocation**: Template check (M). Relocation: tick all — 97% approval, 17%→5% blocking (N14:71/72).
- **Decay**: Checkbox habituation; the DoD's differing understandings (N10:85–93).
- **Verifiability**: Ticks verifiable, claims not.
- **Evidence source**: M (N11:59) off code; Q for DoD.
- **Lifecycle hook**: PR body at open; a check.
- **Without AI**: Yes.
- **Coordination cost**: Agreeing the list once.
- **Social form**: Team-agreed, individually performed.
- **Verdict**: *Hold, folded into HO-3 as a template shape.* Ticks habituate and claims are unverifiable, but "one thing the reviewer should look at" is a generative item, and I-PASS's lesson is that the fields chosen are the ones most often missing. Held as the structure HO-3's description could take.

#### AR-8 A named reviewer with capacity before the PR opens

- **Stage and cell**: AR; arrival as a handoff to a named person (N).
- **What it is**: No PR is opened without naming a reviewer whose open-review count is under their bound; Dashpot shows each reviewer's load. The act is naming a person who agreed.
- **Mechanism and evidence**: At JetBrains 63% always know the reviewer before opening a review; at Microsoft 92% always, usually or frequently (N09:62); load is weighed by only 32% when choosing (N09:64). Reviewer-assignment problems added 12 days over 42,045 reviews (N09:60). CODEOWNERS auto-requests owners with no capacity notion (N19:151); merge queues have none (N16:98). Google reviews have a median of one reviewer (N26:198). Delay tracks the number of people (N27:37). Handover research: unambiguous transfer of responsibility, the outgoing remaining responsible until the update is done (N11:14).
- **Nearest existing thing**: CODEOWNERS (N19:151) plus a WIP limit (N10:3–8).
- **Authorless code**: Passes: two named people.
- **Grain**: PR × reviewer.
- **Demand**: Ask (D7).
- **Enforcement and relocation**: Required-reviewer branch protection (M). Relocation: name the least busy, not the knowing.
- **Decay**: Load bounds drift; no card.
- **Verifiability**: Name and count exact.
- **Evidence source**: M (N09:60/62).
- **Lifecycle hook**: PR review-request observation plus a per-reviewer count.
- **Without AI**: Yes.
- **Coordination cost**: One negotiation per PR.
- **Social form**: Dyadic, team-visible.
- **Verdict**: *Shortlist.* Where the ask family and the bound family meet: no Pull Request opens without a named reviewer who agreed and whose load is under their bound. M-level evidence that assignment problems cost twelve days, pre-AI, dyadic and team-visible, and the arrival row's one act. The relocation — name the least busy rather than the knowing — is the ask family's standing risk and is the reason PD-5's ledger records who was asked.

### Return after absence (RT)

#### RT-1 Recall before re-reading at return

- **Stage and cell**: Return after absence; recall; "recall before re-reading (N)".
- **What it is**: When a person returns to a Worktree after an absence Dashpot can see (session activity age, or no session at that Worktree for longer than a threshold), the skill or a `SessionStart` hook asks two or three questions about the modules the last run touched — which module owns this state, what invariant this function keeps, why this boundary exists — to be answered from memory before any file is opened, then checked against the code. The act asked is a recall with the answer off the screen.
- **Mechanism and evidence**: Retrieval practice g = 0.50 over 159 effects (N08:71, C) and g = 0.61 (N08:72); the benefit appears at delays, not immediately, and learners do not choose it spontaneously (N08:74, C); retrieval before reveal is the documented remedy for the illusion of competence (N08:115, N08:112, C). The codebase application is stated as a practice: state from memory before opening the file, scheduled after a delay from the change (N08:75). Handovers after a ten-day rest were longer and the incoming person read back through the logs afterwards (N11:33, M); after lengthy absence is a named high-risk handover (N11:39). Two months later students could not recall more than two or three identifiers from their own code (N14:87, M). Best card C.
- **Nearest existing thing**: codequiz's confidence-banded review schedule (N19:8) and Learning Opportunities' retrieval check-in at session start (N19:19); neither is triggered by observed absence at a Worktree, and cdebt's grading of own-words answers against the code (N19:11) is the scoring shape.
- **Authorless code**: Works if questions are about structure and behaviour (N26:70, N26:71 question types), not "what did you write".
- **Grain**: Module, chosen from the last run's touched files.
- **Demand**: Recall; recorded act: the answers and their score, by a named person.
- **Enforcement and relocation**: E2 (skill or hook prompt); one step toward default is the hook refusing to place the session until answered, which is a gate Dashpot observes rather than performs. Relocates a few minutes onto the returning person, at a boundary (N22:104: 52% engagement at boundaries against 62% dismissed mid-task).
- **Decay**: Varied items and fading with a good score (principle 10) are the designed answers; no card measures a recall gate over months (N21:174 names longitudinal retention as future work).
- **Verifiability**: The score itself, over weeks, is the instrument principle 7 asks for, scored against the code not the person.
- **Evidence source**: Independent laboratory meta-analyses on declarative material; the transfer to a codebase is untested (N19:42).
- **Lifecycle hook**: Observed trigger (activity age); new observation of the act; channel: skill or `SessionStart` hook.
- **Without AI**: Yes; it is the row the analysis marks as identical without AI.
- **Coordination cost**: None on the agent; on the person, the minutes.
- **Social form**: Attaches to module and person; the scores, aggregated by agreement across members (N18:57), are a team measure.
- **Verdict**: *Shortlist, folded into the verified-at-ref family as its return firing point.* Structural questions about the modules the last run touched, answered from memory and scored against the code, are MR-2's re-verification items asked because of absence rather than change. Same store, same instrument, same fading.

#### RT-2 What moved while away, since your last touch

- **Stage and cell**: Return after absence; read / navigate; "what moved while away (O: Git facts; N: read)".
- **What it is**: On return, Dashpot shows a digest keyed to the person's last activity at the Worktree: commits on the Integration Branch, Branches integrated or removed, Pull Requests merged, Worktrees created, Agent Runs started and ended, with the files those changes touched that the person's last run also touched. The act asked is a read, recorded when the digest is dismissed as read.
- **Mechanism and evidence**: Programmers resume by re-reading notes and looking for recent changes (N11:83, M) yet consult revision history during the edit lag in only 4% of sessions (N11:87, M); what developers want surfaced is deviation from expectation, "what changed since Monday" (N27:23, Q); "What have my coworkers been doing?" was the second most sought information need, from coworkers 20 times to tools 4 (N27:69, M); GitHub's event feed lets users infer liveness and dependencies (N27:67, N27:68, Q); dashboards changed practice for 6 of 32 (N27:64, T). Best card M.
- **Nearest existing thing**: GitHub's activity feed (N27:67) and Jazz feeds as an inbox (N27:63); the difference is the anchor on the person's own last touch and on the files their run held.
- **Authorless code**: Works; the digest is Git and Work Store facts.
- **Grain**: Repository, filtered to the Worktree and its files.
- **Demand**: Read; the recorded act is a read attestation, which no tool records today (N24:53).
- **Enforcement and relocation**: E1 display; relocates nothing.
- **Decay**: Feeds are ignored as noise (N27:65, N27:98); a digest that only appears after absence is sampled by construction.
- **Verifiability**: Edit lag at the first session after return (N11:86 baseline: over 30 minutes in about 30% of sessions); no comprehension measure.
- **Evidence source**: Field observation, independent, pre-agent.
- **Lifecycle hook**: Observed today (Git, Work Store, activity age); new observation for the read.
- **Without AI**: Yes.
- **Coordination cost**: Observability of what the other Agent Runs did while the person was away.
- **Social form**: Attaches to Repository and Worktree; solo it is a personal changelog.
- **Verdict**: *Shortlist, folded into the recall-before-reveal family.* The digest is the reveal half of ST-1's guess-then-diff; alone it is a read, and no tool records a read. Anchoring on the person's last touch and the files their run held is what makes the reveal checkable against the guess.

#### RT-3 A hand-driven stint after supervised absence

- **Stage and cell**: Return after absence; generate / write (no cell today); the human-factors "short return to manual control".
- **What it is**: After a stretch in which every commit at a Worktree arrived during a live Agent Run, the skill asks that the next small task be done by the person with the agent withheld — the Learning style's `TODO(human)` shape (N22:10) applied at return — and Dashpot records that a stint happened. The act asked is a write.
- **Mechanism and evidence**: Bainbridge's remedy is hands-on control for a short period in each shift (N01:13, A); following a ten-minute return to manual control, adaptive groups detected significantly more automation failures in later blocks (N01:43, C); skills decay with disuse (N01:33, N01:4); recent flight practice predicted manual performance more than total experience (N01:47, M). AI-free days exist only in discourse (N13:108); no counterpart to the manual-return result was found in the AI-coding notes (N01:72, N01:163). Best card C, laboratory.
- **Nearest existing thing**: Claude Code's Learning output style withholding 5–10 lines (N22:10, N22:46), which is mid-task and not default; the candidate moves it to the return boundary.
- **Authorless code**: Works; the task is chosen from the returning person's own Worktree, not from who wrote what. Caveat: "arrived during a live Agent Run" is a session fact, not blame, but inferring that a commit was agent-written from it is still an inference and must be stated as such.
- **Grain**: Task, within a Worktree.
- **Demand**: Generate / write; the recorded act is the stint (commit made with no live Agent Session at the Worktree, or a skill-recorded stint).
- **Enforcement and relocation**: E3 practice via skill text; a step toward default is a hook refusing agent edits for the first N minutes after return, a heavy gate. Relocates real work onto the person, the Cowan shape (N01:193).
- **Decay**: The stint is easy to skip under deadline; no card read here measures adherence. Would need a count of stints per return over months.
- **Verifiability**: Failure detection is the aviation outcome (N01:43); the software analogue is the blackout task (N08:53) run after stints against without.
- **Evidence source**: Independent laboratory and regulator data in aviation (N01:48); nothing in software (N01:199).
- **Lifecycle hook**: Observed trigger (runs per Worktree over time); new observation for the stint; channel: skill.
- **Without AI**: No; on a human-authored Branch every stint is a stint. On record for that reason.
- **Coordination cost**: Slows one Worktree for one task; nothing on the team.
- **Social form**: Person-first; attaches to Worktree. Makes visible to the team that someone can still work the module by hand.
- **Verdict**: *Hold, folded with PD-3.* The manual-return result is C-level and the software analogue is unbuilt, but on a human-authored Branch every stint is a stint, so it fails the AI-optional test the same way PD-3 does. One "agent-free stint" candidate, held for teams that want it, with the observable being a commit with no live Agent Session at the Worktree.

#### RT-4 Resumption cue prepared at stop, surfaced at return

- **Stage and cell**: Return after absence; recall via cue; the return side of SB-1.
- **What it is**: At `work stop`, the outgoing holder leaves a positional cue — the file and line to reopen, the failing test to run, the deliberately left TODO — recorded in the Work Store; at return Dashpot shows it on the Worktree row and the skill opens the session there. The act asked at return is none beyond following the cue; the recall it triggers is the mechanism.
- **Mechanism and evidence**: A suspended goal is retrievable only if strengthened before suspension and cued at resumption (N11:71, C); 50% of programmers left a reminder cue in the environment and 36% a physical note (N11:81, M); those given an environment cue view had twice the resumption success of notes alone (N11:84, C, p < 0.1, n = 14); plan restoration uses TODOs and deliberately left compile errors (N11:88); the blinking cursor is a self-placed cue (N11:77). Best card C, small.
- **Nearest existing thing**: Claude Code re-reading the five most recently modified files after compaction (N11:99); the candidate records the cue explicitly rather than reconstructing it from recency.
- **Authorless code**: Works.
- **Grain**: File and line within a Worktree.
- **Demand**: Recall by cue; recorded act: the cue's placement (outgoing) and its use (return, if the first edit lands there).
- **Enforcement and relocation**: E2 skill; relocates a line of writing onto the outgoing holder.
- **Decay**: Cues that are always the same location stop being read; the cue should be the run's actual stopping point, which varies by construction.
- **Verifiability**: Edit lag and navigation count before the first edit (N11:86: 93% navigate before editing); horizon per return.
- **Evidence source**: One small lab study and a survey, independent, pre-agent.
- **Lifecycle hook**: Work Store field written at `work stop`; observed at return; channel: skill and observation.
- **Without AI**: Yes; it formalises what 50% already do.
- **Coordination cost**: Nil.
- **Social form**: Attaches to Worktree; a second person or agent entering sees where the last holder stopped.
- **Verdict**: *Shortlist, folded into the handover family as a field of SB-1.* The cue at stop is what half of programmers already leave; recording it in the Work Store and opening the resumed session there is cheap, pre-AI, and has a small C-level card. Its instrument, navigation before the first edit, is observable from the harness rather than from Dashpot.

#### RT-5 Re-verify held items whose referent changed while away

- **Stage and cell**: Return after absence; recall; the coupled form of RT-1 and the return-time instance of the module-revisit row's "invalidated by change".
- **What it is**: Items a person has previously answered (RT-1 scores) are re-asked at return only when the code they refer to changed during the absence, or when the spacing schedule is due; an item whose referent changed is marked stale and reworded or dropped rather than re-asked as if true. The act asked is a recall on stale items.
- **Mechanism and evidence**: No scheduler models the answer changing (N19:85); Anki decouples content edits from memory state (N19:56); hashcards resets progress when the card's text changes (N19:39); Orbit records provenance and leaves judgement to the author (N19:74, N19:75). Coupling exists elsewhere: doctests fail a build on drift (N19:107); CodeTour pins to a ref and a CI watcher detects drift (N20:44); 74.6% of outdated comments are detectable from code-change features (N19:116). The spacing effect is among the most replicated but validated on flashcard logs, not structures (N08:82). Best card T for the mechanism; C for spacing.
- **Nearest existing thing**: codequiz's per-module confidence bands (N19:8) with no change trigger; cdebt's re-grade on demand (N19:13). The change trigger is what neither has (N19:89).
- **Authorless code**: Works; the referent is a path or symbol.
- **Grain**: Item, pinned to a module or symbol.
- **Demand**: Recall; recorded act: the answer and the item's stale/fresh state.
- **Enforcement and relocation**: E2; relocates item maintenance onto whoever wrote the item, which is the SM-2 rewrite problem (N19:46, N19:50).
- **Decay**: This is the anti-decay device: items vary as the code varies; the leech rule (N19:52) drops items that never stick.
- **Verifiability**: Retrievability over weeks per FSRS (N19:59) restricted to items whose referent is unchanged, against changed; horizon months. This is the retention study the corpus lacks (N19:42).
- **Evidence source**: Tool behaviour and laboratory spacing effects; no professional-team study.
- **Lifecycle hook**: New observation (items and answers) plus an observed change signal (Git diff against pinned refs); channel: skill and observation.
- **Without AI**: Yes.
- **Coordination cost**: None on the agent.
- **Social form**: Attaches to module; shared items scored across members are the team's model by agreement (N18:57).
- **Verdict**: *Shortlist, folded into the verified-at-ref family.* The coupled form of RT-1 and the change trigger neither codequiz nor cdebt has: items re-asked when their referent changed or the schedule is due, stale items reworded or dropped. This is MR-2 with MR-1's schedule as an option, and its verifiability line is the retention study the corpus lacks.

#### RT-6 Who touched it while you were away — a person to ask

- **Stage and cell**: Return after absence; read / navigate, "ask a person" as the map now separates it.
- **What it is**: The RT-2 digest names, for each module the returning person's run held, which sessions and which people acted on it during the absence, and offers the ask as the recorded act: the person marks that they asked, and whom (a person, a document, a model). It does not rank people by knowledge.
- **Mechanism and evidence**: Coordination requirements are volatile week to week and congruence with actual communication cut resolution time (N27:42, N27:45, M); a dynamic buddy list is proposed "every time particular parts of the software are being modified" (N27:43); asking took five minutes against a day of reading (N26:18, Q); 51% now ask generative AI instead of a teammate (N09:76, T); Stack Overflow activity fell 25% in six months (N09:88, M). Awareness's past-tense elements include who was here and when (N27:14). Best card M.
- **Nearest existing thing**: Cataldo's dynamic buddy list (N27:43) and expertise recommenders; the difference is presence-based (who acted, observed) rather than knowledge-inferred, and the ask recorded.
- **Authorless code**: Partly: "who acted" is an awareness fact and passes; presenting it as "who knows" is the authorship inference the widened lens fails (N26:167: co-changer suggestion right under half the time). The card must stay at "acted".
- **Grain**: Module, person, session.
- **Demand**: Read-or-navigate, "ask"; the recorded act is the ask and its target.
- **Enforcement and relocation**: E1 display plus E3 practice; relocates an interruption onto the asked colleague (N26:77).
- **Decay**: Asks fall to the cheapest answerer over time ([themes 5.4](themes.md#54-the-question-routing-economy), inference); the record would show the drift.
- **Verifiability**: Ratio of asks to people against asks to models per return, over months — the directory-in-use measure G15 lacks.
- **Evidence source**: Independent field mining (Cataldo) and self-report surveys (N09:76).
- **Lifecycle hook**: Observed (sessions per Worktree and Branch over time) plus a new observation of the ask.
- **Without AI**: Yes.
- **Coordination cost**: An ask costs both parties; that is the point being measured.
- **Social form**: Team-only; alone there is no one to ask, and the card degenerates to RT-2.
- **Verdict**: *Shortlist, folded into the ask family with IS-4 and JN-5.* Who *acted* on the module during the absence is an awareness fact and passes; presenting it as who *knows* would be the authorship inference, and the card holds the line. The ask and its target — a person, a document, a model — recorded per return is the directory-in-use measure the themes ask for.

#### RT-7 A blackout task on return, as the instrument itself

- **Stage and cell**: Return after absence; explain / verify; the measurement candidate the row otherwise lacks.
- **What it is**: Periodically at return — sampled, not every time — the person performs a short repair task on their own Worktree with the agent disabled: a scripted regression is applied to code the last run produced and the person must find and fix it. Dashpot records the outcome against the Worktree and module. The act asked is a repair.
- **Mechanism and evidence**: The one causal result in the corpus: a 30-minute no-AI blackout maintenance task after a 90-minute build; failure 77% for unrestricted AI against 39% behind an explanation gate (N08:53, C; N23:13); the regression was "a structural regression of the participant's own existing code" applied by git patch (N21:163). The productivity RCTs measured speed only (N23:159). Detection of automation failures was the aviation outcome restored by a manual stint (N01:43). Best card C, single session.
- **Nearest existing thing**: Sankaranarayanan's Phase 2 protocol (N21:163), public replication package (N21:159); the candidate runs it on a living Worktree at return instead of a fixed app.
- **Authorless code**: This is its purpose: the code was produced by the run, and the question is whether the person can repair it unaided.
- **Grain**: Module, within a Worktree.
- **Demand**: Verify by doing; recorded act: pass or fail, time, by a named person.
- **Enforcement and relocation**: E2 opt-in; relocates half an hour onto the person per sampled return, the largest cost in this group.
- **Decay**: Sampled by design; the task varies with the code. Whether people keep opting in is the open question.
- **Verifiability**: It is the instrument principle 7 names: a blackout task scored against the code, repeated over weeks. Horizon months.
- **Evidence source**: One independent randomised study, single session, novice sample (N21:159 is a Learning at Scale paper).
- **Lifecycle hook**: New observation; channel: skill (to apply the patch and disable the agent) and observation (to record). The patch is a mutation of the Worktree the person invokes.
- **Without AI**: Yes as a self-test; the contrast that gives it meaning is agent-produced code.
- **Coordination cost**: None on the team; the agent is off for the duration.
- **Social form**: Attaches to module and person; pass rates by agreement across members would be a team measure. Alone it is the one number the corpus says nobody has.
- **Verdict**: *Shortlist, as the family's individual instrument.* The blackout task is the instrument principle 7 names, sampled at return on the person's own Worktree, scored by whether they can repair what the run produced without it. The cost is half an hour per sampled return, the largest in the group, and the evidence is one randomised study on novices; whether people keep opting in is the question to grill. With PD-4 as the team instrument and PD-8 as the persistence instrument, it completes the measurement set.

### Module revisit (MR)

#### MR-1 Scheduled retrieval invalidated by change

- **Stage and cell**: Module revisit / Recall — "scheduled retrieval, invalidated by change (N)".
- **What it is**: Each module a person has verified (by an explain-back, a quiz answer, or a signed review) becomes a retrieval item with an expanding interval; a merged change to that module's files invalidates the item and resets it regardless of schedule. The act asked is a recall, answer hidden, when the item is due or invalidated, surfaced when the person next binds an Issue whose Worktree touches the module.
- **Mechanism and evidence**: Retrieval practice (g≈0.50–0.61, N19:1; N08:72 g=0.61) and spacing (N08:76–77, optimal gap roughly 10–20% of the retention interval) are the best-replicated effects in the corpus; the schedulers are SM-2 (N19:45–46, N08:79) and FSRS at 90% retention (N19:57–65, N08:80). None models the answer changing (N19:85, N19:89, N19:103; N08:83–84); Wozniak dates items and leaves invalidation to the human (N19:26, N19:48, N19:50). Hashcards resets identity on content hash (N19:39); Swimm's snippet-bound verification fails a check on drift (N19:104–106). Best evidence: controlled, on flashcards, never on an evolving codebase (N19:1, N14:94).
- **Nearest existing thing**: codequiz — top-level directory as module key, confidence-driven schedule, no change detection (N19:4–10); cdebt's debt(file) formula with fresh/aging/stale weights, re-graded on demand only (N19:11–13, N23:92). Differs by taking the invalidation signal from integration facts rather than from a manual re-grade.
- **Authorless code**: Items are the person's own verified answers scored against code; no blame or ownership input. Works whether an Agent Run or a person wrote the module.
- **Grain**: Module (directory or path set), with invalidation at file grain.
- **Demand**: Recall; the recorded act is the answer and its score.
- **Enforcement and relocation**: Optional prompt at `work start`; one step toward default is a skill instruction that asks the recall before the agent proceeds. The work moves onto the person who verified the module.
- **Decay**: Wozniak says programming items lose applicability in 1–3 years (N19:26); FSRS assumes stable items (N19:57–65). To answer at month six the item log would need due, answered, invalidated counts and an interval-vs-miss curve (Khan moves mastery down on misses, N19:143).
- **Verifiability**: Delayed recall rate on items after invalidation versus without, at four to eight weeks; Quantum Country's 54 days per question after six repetitions gives a horizon (N19:176).
- **Evidence source**: Independent and controlled for retrieval and spacing; no test of items whose answer changes (N19:179); the codebase tools are unevaluated repositories (N19:16, N14:89–93).
- **Lifecycle hook**: New observation (item store keyed to module and commit) plus an existing observation (integration per Branch); prompt via the skill or SessionStart hook. No mutation.
- **Without AI**: Yes; the mechanism predates agents and the invalidation is any merged change.
- **Coordination cost**: Nothing about the agent is made observable; cost is the person's recall minutes and an item store per Repository.
- **Social form**: One person; attaches to module and commit, shareable as "verified at ref X by person Y" to a reviewer or newcomer.
- **Verdict**: *Hold*, on mechanism and dependency. Spacing and retrieval are the best-replicated effects in the corpus, but no scheduler models an answer that changes (N19:85, N19:103) and the spacing evidence is on stable items only, so the schedule half is a bet. It also needs items to schedule, which only exist once a person's verified answers are recorded. MR-2 is the same coupling without the scheduler and rests on observed integration facts; MR-1 becomes a shortlist candidate once MR-2's item store exists and a miss curve shows that spacing adds anything to change-triggered invalidation.

#### MR-2 Change-triggered re-verification, unscheduled

- **Stage and cell**: Module revisit / Recall (N), the event-driven half of the cell without spacing.
- **What it is**: A module carries a per-person "verified at ref" mark. When integration facts show the module changed since that ref, the mark is shown as unverified the next time this person's Worktree touches the module, and the act asked is to re-verify: read the delta and re-answer one question about the module, answer hidden.
- **Mechanism and evidence**: Knowledge-base verifiers — Guru, Notion, Slab — pair a named verifier with a 30- or 90-day expiry and unverify on edit by a non-verifier (N19:120–124); Google's freshness dates and "Last reviewed by" byline (N19:114–115, N24:35). Swimm marks a doc "outdated" and blocks the PR check until a human reselects the snippet (N24:39). DOK lowers a person's knowledge when others change the file (N19:126–127, N19:146). GitHub's "Viewed" checkbox is unmarked on change (N23:83). 74.6% of outdated comments are detectable (N19:116). Best evidence: vendor mechanics and one detection study; no comprehension outcome.
- **Nearest existing thing**: Guru-style verifier expiry (N19:120–124) applied to code rather than a doc; differs from MR-1 by having no schedule.
- **Authorless code**: The verified mark belongs to a reader, not an author; works on agent-written modules.
- **Grain**: File set of a module; trigger at commit grain.
- **Demand**: Recall (or Verify if the re-verification is a read attestation only); recorded act is the re-verification with ref.
- **Enforcement and relocation**: Optional; a step toward default is a PR check that a changed module has at least one non-author re-verification. Moves reading onto whoever last verified.
- **Decay**: Risk of click-through habituation as with "Viewed" (N23:83; [themes 5.2](themes.md#52-habituation-of-repeated-friction)). Month six: ratio of re-verifications that include an answer to bare clicks.
- **Verifiability**: Hidden-answer question at re-verification scored against the diff (N23:39–45 rubric); horizon one release.
- **Evidence source**: Vendor mechanics (N19:120–124, N24:39); no independent study that a verifier mark changes a reader's model (N24:188).
- **Lifecycle hook**: New observation (verified-at-ref per person per module) derived from existing Branch and PR observation; surfaced via skill or SessionStart. No mutation.
- **Without AI**: Yes; colleagues' edits invalidate equally.
- **Coordination cost**: Makes "who last verified this module and at what ref" observable to the team; cost is one re-verification per changed module per verifier.
- **Social form**: Team-facing; attaches to module and Pull Request; a newcomer can see which modules nobody has re-verified since a change.
- **Verdict**: *Shortlist.* The cheapest instance of principle 6's coupling clause: a per-person "verified at ref" mark on a module, unverified when integration facts Dashpot already observes show the module changed, with a hidden-answer re-verification as the act. It records what a person holds, which principle 10's fading needs and no other candidate supplies; it works for agent-written modules because the mark belongs to a reader; colleagues' edits invalidate equally, so it holds without AI; and the instrument is the ratio of re-verifications with an answer to bare clicks, which is also its decay measure. Depends on ST-6's person identity. Head of the *verified-at-ref* family, with MR-1, PD-1 and MR-5 as extensions.

#### MR-3 Explain-back on revisit, scored against the code

- **Stage and cell**: Module revisit / Explain (the map leaves this cell empty; widened candidate).
- **What it is**: When a person's Worktree touches a module they have not worked in for a set period, they write a short explanation of what the module does and why before anyone edits it; the explanation is scored against the code, with the code hidden while writing.
- **Mechanism and evidence**: Explain-in-plain-English is the closest instrument (N23:2); SOLO-style rubrics reach Spearman 0.817–0.936 between raters and an autograder 87–89% agreement (N23:39–45); Shen and Tamkin's 14-item IRT quiz (N23:3–5) and Sankaranarayanan's blackout task (N23:13–16) are the two AI-era instruments. cdebt scores generic answers at 0 (N19:12). Experts explain in abstractions while novices stay at the statement level (N26:65, N26:213), which is what an EiPE rubric scores. Best evidence: validated rubrics on course-sized programs only (N19:167).
- **Nearest existing thing**: The hand-off cell "explain it back, graded, diff hidden"; learn-codebase's journal of Confused/Learning/Confident (N19:14–15, N13:12). Differs by firing on revisit after absence from the module, not after an agent run.
- **Authorless code**: Scored against code, not against an author; passes.
- **Grain**: Module.
- **Demand**: Explain; recorded act is the explanation and score.
- **Enforcement and relocation**: Optional; a skill instruction could ask for it before `work start` proceeds. Work stays with the person editing.
- **Decay**: Principle 10 says fade for the expert; the period-since-touch threshold is the fade knob. Month six needs the distribution of scores by time-since-touch.
- **Verifiability**: Rubric score over time per module; a within-person trend at three months.
- **Evidence source**: Rubric validity independent (N23:39–45); no professional-codebase study (N14:2).
- **Lifecycle hook**: New observation (explanation record); prompt through the skill. No mutation.
- **Without AI**: Yes.
- **Coordination cost**: Nothing about the agent; a few minutes per revisit.
- **Social form**: One person; the explanation attaches to the module and is readable by a newcomer as a dated account (N26:84 records that such notes are otherwise never reused).
- **Verdict**: *Shortlist, folded into the explain-back family.* The hand-off cell's mechanism fired at revisit after absence from the module, code hidden while writing, scored by a rubric with independent validity (N23:39–45). The time-since-touch threshold is the fade knob principle 10 asks for. One mechanism, several firing points: HO's explain-back, this, JN-2, JN-6.

#### MR-4 Recall the last integration before reading it

- **Stage and cell**: Module revisit / Recall (N), using an existing observation.
- **What it is**: Before the person opens the module, Dashpot asks them to state what the last change to it did (hidden), then shows the integration fact — Branch, Pull Request, date — it already observes. The answer is kept if the person chooses.
- **Mechanism and evidence**: Method-level specifics decay in months while global knowledge persists (N26:156–157; three-month lower bound); knowledge halves in about four to five months by developer estimate (N26:173, N23:72). Diff-time quizzes exist but persist nothing (N19:20). Storage versus retrieval strength (N19:187) and hypercorrection (N19:184) suggest a confident wrong recall followed by the fact is the strongest correction. Best evidence: laboratory memory research; the codebase link is by analogy.
- **Nearest existing thing**: The map's "recall the last touch of the module (N)" at Issue declared and "what changed since last run here (O for Git)" at Session/work starts. Differs by placing the recall at the module, not the Issue or session.
- **Authorless code**: Recalls the integration event, not its author; works for Agent Run changes.
- **Grain**: Module; the fact is at Pull Request grain.
- **Demand**: Recall; recorded act optional.
- **Enforcement and relocation**: Optional display; a step toward default is the skill asking before `work start`. Nothing moves onto another person.
- **Decay**: Habituation if the fact is shown without the recall; principle 4 asks for sampling. Month six: fraction of prompts answered before reveal.
- **Verifiability**: Hit rate of recall versus fact, per module, per person, over weeks.
- **Evidence source**: Independent laboratory memory work; nothing on code (N08:145).
- **Lifecycle hook**: Observed today (integration facts per Branch); the recall is a new observation. No mutation.
- **Without AI**: Yes.
- **Coordination cost**: Low; nothing about the agent.
- **Social form**: One person; attaches to module and Pull Request.
- **Verdict**: *Shortlist, folded into the recall-before-reveal family.* IS-2 and ST-1's device fired at the module rather than the Issue or session, against an integration fact Dashpot observes today. The hit rate per module per person over weeks is the instrument. Nothing here is new beyond the firing point, which is why it folds.

#### MR-5 Date-stamped module note, confirmed or struck at revisit

- **Stage and cell**: Module revisit / Nothing (artifact), with an act attached at revisit.
- **What it is**: A person leaves a short dated note on a module; at revisit the note is shown with its date and the commits since, and the act is to confirm, amend, or strike it. Struck notes are kept as history.
- **Mechanism and evidence**: Wozniak's rule 19 date-stamps items whose truth changes (N19:48); Google's freshness metadata reminds after three months (N19:114–115, N24:35) and Google concedes measurement tools "have still not caught up" (N24:36). ADR superseding keeps the old record (N19:119, N24:19, N24:24). Developers take notes reflecting their model but never archive or reuse them (N26:84). 68% of professionals say documentation is always outdated (N24:175), yet out-of-date documents remain useful (N24:178–179). Best evidence: surveys and vendor practice.
- **Nearest existing thing**: Swimm's code-coupled docs (N13:59, N24:38) and Google freshness dates (N24:35). Differs by making the note a per-person act at revisit rather than a CI re-sync.
- **Authorless code**: A reader's note; no authorship inference.
- **Grain**: Module.
- **Demand**: Nothing (artifact) until revisit, then Verify (confirm or strike).
- **Enforcement and relocation**: Optional; could be a PR check that touched modules carry no stale unconfirmed notes. Moves confirmation onto the reviser.
- **Decay**: Stale by default by date (principle 6); month six needs confirmed/struck/ignored counts.
- **Verifiability**: Weak alone — a confirmed note shows reading, not understanding; would need pairing with MR-3's explain-back.
- **Evidence source**: Self-report surveys (N24:175–179), vendor mechanics; no study that a note improves a later reader's model (N24:188).
- **Lifecycle hook**: New observation (dated note store per module). No mutation.
- **Without AI**: Yes.
- **Coordination cost**: Low; notes visible to the team.
- **Social form**: Team; attaches to module; a newcomer reads the dated history.
- **Verdict**: *Hold*, on verifiability. A confirmed note shows reading, not understanding, and the surveys that support it are self-report. It is the artifact side of MR-2 — the mark with a sentence attached — and is held as an option on that candidate rather than a candidate of its own.

#### MR-6 Revisit ordered by authorship-derived knowledge decay

- **Stage and cell**: Module revisit / Recall (N) — expected to fail the authorless-code lens; recorded so the rejection is on record.
- **What it is**: Modules are ranked for revisit by an authorship metric: degree of knowledge decayed by others' commits, blame share held by departed people, or truck-factor risk. The person is prompted to revisit the highest-ranked module.
- **Mechanism and evidence**: DOK combines first authorship, deliveries and acceptances and lowers knowledge when others change the file (N19:126–127); explained R²=0.25 and 55% owner agreement (N23:66). Knowledge is estimated to halve in about five months and commits give MRR .560 (N23:72). Files are "abandoned" at ≥90% blame by departed developers, about 130 a quarter (N26:166); co-change successor suggestions are correct under half the time (N26:167). CodeScene sells knowledge metrics with invalidation by departure (N19:149–150). Cury and Avelino discount GenAI lines and 86 of 120 truck factors fall (N23:73).
- **Nearest existing thing**: CodeScene knowledge maps (N19:149–150); Expertise Browser (N19:145, N09:51–54).
- **Authorless code**: Fails: when the last modifier is an Agent Run there is no person to whom the metric assigns knowledge (N09:100); Wheeler severs authorship from comprehension and predicts incident failures the metric cannot see (N19:152, N23:74, N08:23); the tools' own authors report no definitive validity (N23:64, N09:54).
- **Grain**: File and module.
- **Demand**: Recall, with the choice of module made by the metric.
- **Enforcement and relocation**: Advisory ranking; a default would make the metric a gate.
- **Decay**: The metric decays by design (N23:72) but never measures recall.
- **Verifiability**: Would need to show the ranking predicts recall failure better than time-since-touch; no card tests this.
- **Evidence source**: Mining studies with weak validity (N23:59–66); vendor dashboards.
- **Lifecycle hook**: Computable from Git today; a new derived observation.
- **Without AI**: The metric predates agents and was weak then (N23:59–63).
- **Coordination cost**: Low.
- **Social form**: Team dashboard; attaches to file; infers rather than records who knows what (principle 15).
- **Verdict**: *Reject*, on authorless code. An authorship-derived proxy for understanding (principle 15, [themes 5.5](themes.md#55-the-authorship-inference)): when the last modifier is an Agent Run the metric has no one to assign knowledge to, and its validity was R² = .25 before any agent wrote code. The rejection the widened lens needed on record.

#### MR-7 Interleaved retrieval across parallel modules

- **Stage and cell**: Module revisit / Recall (N), a variant of MR-1.
- **What it is**: Due items from two or more modules with parallel responsibilities (two adapters, two state machines) are mixed rather than blocked, so the person must discriminate which module a fact belongs to.
- **Mechanism and evidence**: Interleaving g=0.42 over 238 effects, larger for confusable categories, null for expository text and reversed for word lists (N08:98–99); the corpus's own application note says mixing unrelated files has no support (N08:100). Best evidence: meta-analysis outside code.
- **Nearest existing thing**: MR-1; no codebase tool interleaves (N13:11).
- **Authorless code**: As MR-1; passes.
- **Grain**: Module pairs.
- **Demand**: Recall.
- **Enforcement and relocation**: Optional.
- **Decay**: As MR-1.
- **Verifiability**: Discrimination accuracy between the paired modules at delay.
- **Evidence source**: Independent; the null on text material is the closest analogue to code (N08:98).
- **Lifecycle hook**: As MR-1.
- **Without AI**: Yes.
- **Coordination cost**: Low.
- **Social form**: One person.
- **Verdict**: *Reject*, on evidence source. The interleaving effect is null on expository text and reversed for word lists, and the corpus's own application note says mixing unrelated files has no support (N08:98–100). A variant of MR-1 with less behind it.

#### MR-8 Characterisation test written before reading

- **Stage and cell**: Module revisit / Verify (widened; the map's Verify cell in this row is empty).
- **What it is**: At revisit the person writes a predicted behaviour of the module as an executable test before reading the code, then runs it. A failing prediction is the signal; the test and outcome are kept against the commit.
- **Mechanism and evidence**: Feathers' characterisation tests for code not understood well enough to change (N26:112, N26:219 — recalled, not read, in the source note); learn-codebase's "predict before revealing" (N13:12); mental models made explicit in test cases and shared in the suite (N26:150; 81 teams, β=0.58). Experts establish and test hypotheses (N26:83). Best evidence: practitioner method plus a survey correlation.
- **Nearest existing thing**: cdebt's re-grade on demand (N19:13); differs by using the test runner as the grader.
- **Authorless code**: Scored by running the code; passes.
- **Grain**: Module or function.
- **Demand**: Verify; recorded act is the prediction and outcome.
- **Enforcement and relocation**: Optional; could be a skill step before agent edits.
- **Decay**: No card; would need prediction accuracy over time per module.
- **Verifiability**: Prediction pass rate before reading, at delay.
- **Evidence source**: Practitioner text, no evaluation (N26:112).
- **Lifecycle hook**: New observation (prediction record); the test lives in the Repository.
- **Without AI**: Yes, and it yields a test either way.
- **Coordination cost**: Adds test files the team maintains.
- **Social form**: One person or pair; attaches to module and commit; shareable as tests.
- **Verdict**: *Shortlist, head of the prediction family.* The boundary form IL-8 was held for: a prediction made before reading, scored by the test runner with no judge, kept in the Repository as a test so the record is the artifact and cannot go stale. Pre-AI and it yields a test either way. Its evidence is practitioner text, and two of its cards are marked in the inventory as recalled rather than read, so the candidate is a bet on a mechanism with C-level support elsewhere (prediction before reveal, N08:115) and a form no source has evaluated.

### Periodic (PD)

#### PD-1 Sampled recall across the repository

- **Stage and cell**: Periodic / Recall — "sampled recall across the repository (N)".
- **What it is**: On a cadence, a small random sample of retrieval items is drawn across the Repository's modules, weighted toward recently integrated Branches, and posed with answers hidden. Sampling replaces a full schedule so no item becomes routine.
- **Mechanism and evidence**: Three successful recalls then three relearnings is the durable-learning criterion (N19:174); Quantum Country's delay experiment moved recall from 91% to 87% (N19:176). Retrieval must succeed or be followed by feedback, and learners do not choose it spontaneously (N08:74). Nothing tests items whose answers change (N19:179) or spacing on a living repository (N14:6, N14:94). Best evidence: controlled, on prose and flashcards.
- **Nearest existing thing**: sphinx-ci's 10-question 70% gate (N23:143–145) and codequiz (N19:4–10); N21:235 records that no tool takes a module or the whole repository as quiz subject.
- **Authorless code**: Items scored against code; passes.
- **Grain**: Repository, sampled at module grain.
- **Demand**: Recall; recorded act is the answer set.
- **Enforcement and relocation**: Optional cadence; a step toward default is a scheduled job or SessionStart prompt.
- **Decay**: Sampling is the anti-habituation design (principle 4); month six needs answer rate and score by module age.
- **Verifiability**: Recall accuracy on sampled items at four and eight weeks, per module.
- **Evidence source**: Independent controlled work outside code; LLM item generation shows 4.9%/4.0% flaw rates and no IRT on developer responses (N23:140–142).
- **Lifecycle hook**: New observation; prompt via skill or hook. No mutation.
- **Without AI**: Yes.
- **Coordination cost**: Person-minutes per cadence.
- **Social form**: One person; the team form is PD-4.
- **Verdict**: *Shortlist, folded into the verified-at-ref family.* Sampling is the anti-habituation design principle 4 asks for, applied to MR-2's item store on a cadence. It has no items of its own; it is how the family fires when nothing has changed.

#### PD-2 Self-report instrument on a cadence

- **Stage and cell**: Periodic / Nothing (artifact) — "self-report instrument (N)".
- **What it is**: A short questionnaire on a cadence — "How often can you easily understand the code you work with?" plus reliance items — aggregated per team. No act on code is asked.
- **Mechanism and evidence**: DXI's 14 items include that understanding item, mean 3.827 (N23:96–99); DORA reliance items (N23:101–104); SPACE aggregates anonymised to the team (N23:107); DX's "code maintainability" perception item is the closest shipping proxy (N13:97). No item asks "do you understand the AI code" (N23:119). Self-report misperceives its own usage against logs (N23:105); 68% report learning more with AI while skills may erode (N03:62). Learning Opportunities ships a pre/post team survey with advice not to run significance tests on six people (N21:82). Best evidence: large vendor surveys.
- **Nearest existing thing**: DXI (N23:96–99). Differs only by cadence and by display beside Repository facts.
- **Authorless code**: Neutral; asks a person about their own state.
- **Grain**: Person and team.
- **Demand**: Nothing; no act on code is recorded.
- **Enforcement and relocation**: Optional; surveys are already periodic in DX and DORA practice.
- **Decay**: Survey fatigue; no card on cadence effects.
- **Verifiability**: Principle 7 asks for team measures scored by agreement, not survey; TMS–performance is r=.77 when self-reported versus .39 by embedded metrics (N09:23–24).
- **Evidence source**: Self-report throughout (N23:96–111).
- **Lifecycle hook**: New observation, outside Dashpot's Git and session channels.
- **Without AI**: Yes.
- **Coordination cost**: Low.
- **Social form**: Team aggregate; attaches to nothing in the Repository.
- **Verdict**: *Reject*, on verifiability. Principle 7's revision says this directly: self-assessed understanding is not an instrument for this debt, and the team measure is scored by agreement, not by asking each member. PD-4 is the form that passes.

#### PD-3 Periodic blackout task scored against the code

- **Stage and cell**: Periodic / Generate (widened) — a scheduled exercise without the agent.
- **What it is**: On a cadence the person takes a small sampled change in a module they recently shipped with an agent and completes it on a Branch with no Agent Run bound; the result is scored by tests and review. Dashpot can observe whether an Agent Run was bound to the Branch; whether the person worked alone is not observable.
- **Mechanism and evidence**: Sankaranarayanan's 30-minute blackout with a logic bomb (N23:13–16); Bainbridge's remedy of hands-on control for a short period each shift (N01:13); FAA findings and recommendations on maintaining manual flight skill (N01:48, N01:51, N01:53); "Rawdog Thursdays" as discourse (N13:81); Storey's periodic rebuild-understanding checkpoints (N13:83). Best evidence: one three-arm student experiment (N23:13–16).
- **Nearest existing thing**: The hand-off blackout (N23:13–16) moved to a cadence.
- **Authorless code**: Scored by code; passes.
- **Grain**: Module task, Branch.
- **Demand**: Generate; recorded act is the Branch and its Pull Request.
- **Enforcement and relocation**: Optional ritual; a bound (principle 14) could be "one agent-free Branch per person per sprint", set by the team.
- **Decay**: Compliance drift; month six needs the count of agent-free Branches per person.
- **Verifiability**: Task success and time relative to the agent-assisted baseline; N23:159–163 shows single-session RCTs measure speed only.
- **Evidence source**: One student experiment, aviation policy, discourse.
- **Lifecycle hook**: Observed today in part (Agent Run bound or not to a Branch); scheduling is new. No mutation.
- **Without AI**: The exercise has meaning only where an agent is in normal use.
- **Coordination cost**: Slower work for one task per person per cadence.
- **Social form**: One person; visible to the team as Branch history.
- **Verdict**: *Hold*, on without-AI. The one exercise aimed squarely at the debt — the blackout task moved to a cadence — with a bound form Dashpot could show today (an agent-free Branch is a Branch with no Agent Run bound). But it has meaning only where an agent is in normal use, its evidence is one student experiment, and whether the person worked alone is unobservable. Held for the team that wants it; not shortlisted on the AI-optional test.

#### PD-4 Within-team agreement measure of the shared model

- **Stage and cell**: Periodic / Recall (N), team form.
- **What it is**: On a cadence each member answers the same sampled structural questions about the Repository and names whom they would ask about each sampled module. Scoring is by agreement among members and against the code, not by asking each member how well the team understands.
- **Mechanism and evidence**: Lewis's 15-item TMS scale needs rwg≥.70 to aggregate (N18:48–58, N09:16–17); Austin's structural measure scores consensus and accuracy of who-knows-what beliefs (N09:18–19); Mathieu's paired-comparison matrices (N18:59–63, N26:145); Schmidt's dyadic agreement items across 81 Scrum teams (N18:78–88, N26:150); compilational (who-knows-what) cognition outperforms compositional (N26:147). No instrument scores a team's shared model of a codebase (N18:89, N18:97, N26:3, N26:236); Fritz's questionnaires are the only direct test of code knowledge (N26:158, N23:65). Best evidence: meta-analytic on simulator teams (N26:146).
- **Nearest existing thing**: Scrum Team Survey per-team link (N18:78–88); Knowledge Islands and ConceptRealm infer from authorship instead (N18:93–95).
- **Authorless code**: Asks people and scores against code; passes.
- **Grain**: Repository, sampled modules.
- **Demand**: Recall.
- **Enforcement and relocation**: Optional ritual.
- **Decay**: Software teams' models did not converge over time (N26:149, N24:160); month six needs the agreement series.
- **Verifiability**: Agreement index and accuracy per cadence; the instrument is itself the verification (principle 7).
- **Evidence source**: Independent; self-report inflation applies to the perception scales, not to the agreement score (N09:23–24, N09:34).
- **Lifecycle hook**: New observation outside Git.
- **Without AI**: Yes.
- **Coordination cost**: A team session per cadence.
- **Social form**: Team only; attaches to Repository and modules.
- **Verdict**: *Shortlist, as the family's team instrument.* The instrument principle 7 names: the same sampled structural questions to every member, scored by agreement among them and against the code, with "whom would you ask" alongside so the directory is measured rather than inferred. Independent meta-analytic evidence on other kinds of team; nothing on a codebase, which is the gap it would close. Dashpot's part is the question sample against the Repository and the score series, not the ritual.

#### PD-5 Team directory recorded from acts, not inferred from authorship

- **Stage and cell**: Periodic / Nothing (artifact), with entries created only by acts.
- **What it is**: A who-knows-what directory whose entries are written only by recorded acts — a scored explain-back on a module (MR-3), an answered ask (JN-5), a signed transfer walkthrough (JN-6), a named review. Entries carry name, module, ref and date; nothing is derived from blame.
- **Mechanism and evidence**: Wegner's directory is labels and locations, not content (N09:1–2); responsibility is assigned by expertise or by most-recent encounter (N09:3), the latter being the Line 10 Rule (N09:4, N09:36). Expert-finder accuracy has no objective truth (N09:40). An imposed directory helps strangers and hurts pairs that already have one (N09:11–12). Information about each other's skills reproduced the group-training benefit (N09:15, unverified). 63–92% of reviewers already know whom to ask (N09:62). Experienced newcomers want information about people (N26:20, N26:58). Best evidence: laboratory couples and one field study.
- **Nearest existing thing**: Expertise Recommender (N09:38), CODEOWNERS (N19:151), Kognita (N13:54). Differs by recording acts, per principle 15.
- **Authorless code**: Passes by construction; the holder of an agent-written module is whoever verified it.
- **Grain**: Module.
- **Demand**: Nothing; entries come from other candidates' acts.
- **Enforcement and relocation**: None; a gate could require one named entry per module before merge.
- **Decay**: Entries are dated and invalidated by change (MR-2); month six needs stale-entry share.
- **Verifiability**: Whether asks routed by the directory are answered faster; N09:74 records that no such study exists.
- **Evidence source**: Independent but old; the AI-era transcript "who" is vendor-documented only (N09:93).
- **Lifecycle hook**: New observation composed from others; no mutation.
- **Without AI**: Yes.
- **Coordination cost**: Makes who-verified-what observable; low.
- **Social form**: Team; attaches to module.
- **Verdict**: *Shortlist, as the family's ledger.* It asks no act, so it is not a friction; it is the record every act candidate writes to — IS-4 and JN-5's asks, MR-2's marks, JN-6's signatures, named reviews — keyed by module, ref, date and a person's declared name. Principle 15's "who knows what" answered by acts, never by blame. Listed on the shortlist because the family does not cohere without it, and because it is the thing a chat-centric tool cannot have.

#### PD-6 Periodic rebuild-understanding session with a walked-module record

- **Stage and cell**: Periodic / Explain (widened; social).
- **What it is**: A recurring team session (code reading club, brown bag, mob Friday) in which one member walks a module for the others; the record is which modules were walked, when, by whom, against which ref.
- **Mechanism and evidence**: Code Reading Club's structured session, no evidence claimed (N26:105–108); mob Fridays on critical legacy code (N26:187); talks by key developers after departures (N26:174); Storey's periodic checkpoints (N13:83). Fagan's overview stage is education (N26:189–190). No primary source evaluates brown bags or design reviews (N26:199, N26:235); no stand-up or retrospective study measures a model change (N10:112, N10:117, N10:119). Best evidence: practitioner reports.
- **Nearest existing thing**: Code Reading Club (N26:105). Differs by keeping the walked-module record pinned to a ref.
- **Authorless code**: Anyone can walk an agent-written module; passes.
- **Grain**: Module.
- **Demand**: Explain; recorded act is the walk.
- **Enforcement and relocation**: Optional ritual.
- **Decay**: Rituals drift to status reporting (N10:99, N10:109); month six needs attendance and coverage.
- **Verifiability**: Pair with PD-4 agreement before and after walked modules.
- **Evidence source**: Practitioner and discourse only.
- **Lifecycle hook**: New observation (walk record).
- **Without AI**: Yes.
- **Coordination cost**: A team hour per cadence.
- **Social form**: Team only; attaches to module and ref.
- **Verdict**: *Hold*, on verifiability and evidence source. Practitioner reports only, and its instrument is PD-4 run before and after. The walked-module record pinned to a ref is a cheap ledger entry once PD-5 exists; held as an option on it.

#### PD-7 Knowledge-concentration and truck-factor dashboard

- **Stage and cell**: Periodic / Nothing (artifact) — expected to fail the authorless-code lens; recorded for the rejection.
- **What it is**: A periodic view of truck factor, ownership concentration and abandoned-file share per module, computed from blame, with agent-written lines discounted.
- **Mechanism and evidence**: Truck factor with k=0.75, m=3.293; 65% of 133 systems have TF≤2 (N19:148); 57% of 1,932 popular projects have TF 1 and 41% survive losing all TF developers (N26:171); Bird's Minor contributors below 5% (N23:59–63); Storey's knowledge-concentration metrics (N23:127–130). Cury and Avelino discount GenAI lines (N23:73). A libgdx maintainer: the truck factor is about institutional memory that no automatic system can account for (N26:170).
- **Nearest existing thing**: CodeScene (N19:149–150); cognitive-debt-action's orphaned-AI-code heuristic (N07:17).
- **Authorless code**: Fails: an authorship-derived proxy for understanding (principle 15); Wheeler's invalid class (N23:74, N23:127–130).
- **Grain**: File and Repository.
- **Demand**: Nothing.
- **Enforcement and relocation**: Dashboard only.
- **Decay**: Not applicable; no act.
- **Verifiability**: Would need Wheeler's prediction tested (N08:23); no card.
- **Evidence source**: Mining studies; vendor.
- **Lifecycle hook**: Derived from Git; new observation.
- **Without AI**: Predates agents.
- **Coordination cost**: Low.
- **Social form**: Team dashboard; infers.
- **Verdict**: *Reject*, on authorless code. As MR-6, at repository grain.

#### PD-8 Delayed re-test of hand-off items

- **Stage and cell**: Periodic / Recall (N), as the row's instrument.
- **What it is**: Items answered at hand-off (the diff quiz or explain-back) are re-posed to the same person at one and four weeks without the diff, so the row measures persistence rather than a single session.
- **Mechanism and evidence**: Every RCT in the corpus is single-session and measures speed; Kazemitabaar's one-week follow-up and Bastani's 17% drop are the longest (N23:159–163); no retention study exceeds a week under AI assistance (N14:1, N14:94). Testing beats restudy at two days and a week, not at five minutes (N08:69); Moulton's distributed-practice RCT on 38 residents (N19:170). WWC single-case standards give a small-n design (N23:168).
- **Nearest existing thing**: Learning Opportunities' MEASURE-THIS pre/post survey (N19:19, N21:82). Differs by re-testing items against code.
- **Authorless code**: Passes.
- **Grain**: Pull Request items.
- **Demand**: Recall.
- **Enforcement and relocation**: Optional.
- **Decay**: This is the decay measurement.
- **Verifiability**: Retention curve per person; horizon four weeks.
- **Evidence source**: Independent memory research; nothing on professional code.
- **Lifecycle hook**: New observation built on the hand-off record.
- **Without AI**: Yes.
- **Coordination cost**: Low.
- **Social form**: One person; attaches to Pull Request.
- **Verdict**: *Shortlist, as the hand-off family's persistence instrument.* Re-posing hand-off items at one and four weeks with the diff hidden is the horizon principle 7 asks for and no study has run on professionals. It exists only once HO's explain-back or quiz records items; it is the cheapest way to know whether that candidate did anything past the session.

### A person joining, or handing over (JN)

#### JN-1 Small first task, isolated and mentor-screened

- **Stage and cell**: Person joining / Generate — "small first task (N)".
- **What it is**: The newcomer's first Issue is a screened change touching three or four files, done by the newcomer; Dashpot shows the Issue Binding, Worktree, Branch and Pull Request and whether an Agent Run was bound.
- **Mechanism and evidence**: First tasks at two to four weeks, three or four files (N26:11); one newcomer committed on day one (N26:26); Simple-to-Complex strategy with weeks 2–4 on small bugs (N26:33); 41 of 61 task items led to learning (N26:31). Mentored entrants succeed first time 80.1% against 67.1% for Good First Bug only (N26:47); expert involvement raises success and lowers retention (N26:52); mentored newcomers commit about three times more over 16 weeks (N26:45). Choosing manual pain during onboarding as an appropriation practice (N14:30). Best evidence: mining and multi-case studies; no comprehension measure (N26:59).
- **Nearest existing thing**: Good-first-issue labels (N26:205). Differs by binding to an Issue and Worktree the team can watch.
- **Authorless code**: The task is on whatever code exists; passes.
- **Grain**: Issue and Pull Request.
- **Demand**: Generate; recorded act is the Pull Request.
- **Enforcement and relocation**: Optional; screening is the mentor's work (N26:8).
- **Decay**: Not applicable after the first weeks.
- **Verifiability**: Time to first and tenth Pull Request (N18:11, N18:13, N18:25) measure time, not model; a rubric on the first PR description would be the instrument.
- **Evidence source**: Independent field studies.
- **Lifecycle hook**: Observed today (Issue Binding, Branch, PR, Agent Run).
- **Without AI**: Yes.
- **Coordination cost**: Mentor's screening hours.
- **Social form**: Person with mentor; attaches to Issue.
- **Verdict**: *Hold*, on verifiability. The best-evidenced onboarding practice in the corpus, and Dashpot already observes everything it needs — the Issue Binding, the Branch, the Pull Request, and whether an Agent Run was bound. But its measures are time to first and tenth Pull Request, which score speed, not the model. Held as the setting in which JN-2 and JN-8 fire, not a friction of its own.

#### JN-2 Teach-back to the newcomer

- **Stage and cell**: Person joining / Explain — "teach-back to the newcomer (N; social)".
- **What it is**: An incumbent explains a module to the newcomer, then the newcomer explains it back; the newcomer's questions and the explain-back are recorded against the module. Two acts, both named.
- **Mechanism and evidence**: Teaching after preparing gives g=0.56 over 28 studies (N08:108, N08:110). In no observed pairing did the expert encourage the novice to articulate knowledge (N26:178). Fagan's inspection has a reader paraphrase the design (N26:189). Naur: the theory is acquired in close contact with holders (N26:132–133, N08:8). Newcomers ask focus-finding questions three times as often as owners (N26:72). Five of eight new hires could mentor only in getting-started tasks (N26:22). Best evidence: meta-analysis outside code.
- **Nearest existing thing**: The hand-off cell "explain it back, graded"; LACY's expert-guided tours scored 83% versus 57% for AI-only on a ten-question quiz, n=5 (N14:55, N20:123).
- **Authorless code**: The incumbent need not be the author; passes, with the caveat that someone must hold a model to teach it (N26:5).
- **Grain**: Module.
- **Demand**: Explain.
- **Enforcement and relocation**: Optional; the incumbent gives up output to train (N03:12–14).
- **Decay**: Not applicable after onboarding; the record persists.
- **Verifiability**: EiPE rubric on the explain-back (N23:39–45).
- **Evidence source**: Independent; no software study of teach-back on production code (N14:2).
- **Lifecycle hook**: New observation.
- **Without AI**: Yes.
- **Coordination cost**: Two people, an hour per module.
- **Social form**: Team; attaches to module; the recorded explain-back is readable by the next newcomer.
- **Verdict**: *Shortlist, folded into the explain-back family.* Two named acts on one module, the newcomer's explain-back scored by rubric, the record readable by the next newcomer. Teaching's g = 0.56 is independent and outside code; the software finding is that in no observed pairing did the expert ask the novice to articulate anything (N26:178), which is what this candidate changes.

#### JN-3 Pairing with the novice driving

- **Stage and cell**: Person joining / Verify — "pairing with the novice driving (N; social)".
- **What it is**: The newcomer drives — keyboard, or the agent's prompt — while an incumbent navigates aloud on a bound Issue; the Branch carries both names. Beyond one Agent Session and two committers nothing about the pairing is observable.
- **Mechanism and evidence**: Four of six teaching strategies occur when the novice drives (N26:177); letting the novice drive transfers detail but is slower and learning was not measured (N26:178); strong-style pairing routes everything through the novice (N26:184). Mentoring fell from 37% to 26% of time and time to productivity from 27 to 12 days (N26:179, second-hand). Arisholm found no time or correctness gain and 84% more effort (N26:180). Pairing, review and tests predict shared mental models (N26:150). A Copilot partner lowered demand and valence against a human partner (N14:38). Best evidence: one controlled experiment with 295 consultants (N26:180).
- **Nearest existing thing**: Mob programming (N26:181–186). Differs by dyad and by the novice's hands.
- **Authorless code**: Passes.
- **Grain**: Issue and Branch.
- **Demand**: Verify (the navigator verifies in real time).
- **Enforcement and relocation**: Optional; moves the incumbent's output onto training (N03:13).
- **Decay**: Fades as competence grows (principle 10); no card.
- **Verifiability**: No card measures learning from pairing (N26:178); would need a delayed explain-back.
- **Evidence source**: Independent; direction contested (N26:175 versus N26:180).
- **Lifecycle hook**: Observed only as committers on a Branch; a "paired" mark would be a new observation.
- **Without AI**: Yes.
- **Coordination cost**: Two people per task.
- **Social form**: Dyad; attaches to Branch.
- **Verdict**: *Hold*, on verifiability. The direction of the pairing evidence is contested and no study measures learning from it; the only observable is two committers on a Branch. Held for the delayed explain-back that would make it measurable.

#### JN-4 Tour or map pinned to a ref

- **Stage and cell**: Person joining / Read-navigate — "tour, map (N; signal: pinned ref or none)".
- **What it is**: A checked-in tour or map whose steps reference files at a ref; Dashpot shows the tour's ref against the current Branch head so a newcomer sees how stale it is before following it. Reading is not recorded unless the newcomer marks steps.
- **Mechanism and evidence**: CodeTour stores `.tours/` JSON pinned to a ref or regex, and CodeTour Watch flags drift in CI (N20:43–45); Swimm Playlists record reader position (N20:49); no tour records understanding (N20:53). Developers preferred tours scaled to code length and trusted human-seeming text more; LLM judging of tours was unreliable (N14:52–53). Generated wikis regenerate on change with no human evaluation (N20:6–10, N24:43–44, N14:56). Sim and Holt's course was not applicable at four months (N26:15); a day-one architecture overview did not hit home (N26:29); newcomers want build-and-run, who owns what, and worked examples (N26:200). Best evidence: 26-developer preference study (N14:52).
- **Nearest existing thing**: CodeTour (N13:48); `/team-onboarding` generates a ramp-up guide from local usage (N07:31).
- **Authorless code**: A tour can be written by any reader; passes, though generated tours inherit unverified accuracy (N20:22).
- **Grain**: Repository, steps at file grain.
- **Demand**: Read; no act unless steps are marked.
- **Enforcement and relocation**: Optional; a PR check could fail a tour whose refs drifted (N20:45).
- **Decay**: Stale by default; the pinned ref is the signal.
- **Verifiability**: Only LACY's quiz exists (N14:55); a tour would need a paired question per step.
- **Evidence source**: Vendor and small studies; 68.79% LLM-judged accuracy without humans (N20:22).
- **Lifecycle hook**: New observation (tour ref versus Branch head) from existing Git observation.
- **Without AI**: Yes.
- **Coordination cost**: Someone maintains the tour.
- **Social form**: Team artifact; attaches to Repository and ref.
- **Verdict**: *Hold*, on demand. A pinned tour's ref against the Branch head is a real, cheap coupling signal (principle 6) and Dashpot could show it today from Git facts; but following a tour is a read, and reading is not recorded. Becomes a shortlist candidate if each step carries a hidden-answer question, at which point it is a verified-at-ref item store with a route through it.

#### JN-5 Ask a person, recorded as an act

- **Stage and cell**: Person joining / Read-navigate — "ask a person (N; social)".
- **What it is**: The newcomer asks a named person about a module; the ask and answer are recorded against the module and Issue, so the routing act is observable and the answer reusable. When the last change was an Agent Run, the record points at the Agent Session transcript as the holder.
- **Mechanism and evidence**: Asking resolves in five minutes what reading takes a day (N26:18); fear that asking reveals ignorance (N26:19); 17 of 28 professionals prefer asking a colleague (N26:87, N09:49) and 81% consult people (N26:90). First questions unanswered within 24 hours end participation (N26:41). 51% now ask GenAI instead of a teammate and 62% find it less embarrassing (N09:76); "ask an expert teammate" fails when the teammate has left (N26:77, N09:48). Wegner's directory is labels and locations (N09:2); the session picker row is such a label and retention is 30 days (N09:94–96, N09:100–101). Best evidence: observational field studies.
- **Nearest existing thing**: Unblocked, positioned against interrupting teammates (N09:98); Answer Garden's old answers decayed once authors left (N09:45).
- **Authorless code**: Passes when a person holds a model; when none does, the record points at a transcript, which no study shows is read (N09:102, N09:132).
- **Grain**: Module and Issue.
- **Demand**: Read; the recorded act is the ask.
- **Enforcement and relocation**: Optional; moves interruption onto the answerer (N26:77).
- **Decay**: Answers age as Answer Garden's did (N09:45); pair with MR-2 invalidation.
- **Verifiability**: Time to answer and re-ask rate; N09:74 records no study of a routing tool changing either.
- **Evidence source**: Independent field studies; AI-era figures are self-report (N09:75).
- **Lifecycle hook**: New observation; Issue comments are outside Dashpot's current channels.
- **Without AI**: Yes.
- **Coordination cost**: The answerer's interruption; makes the question-routing economy visible ([themes 5.4](themes.md#54-the-question-routing-economy)).
- **Social form**: Team; attaches to Issue and module.
- **Verdict**: *Shortlist, folded into the ask family with IS-4.* The same act at a different boundary: the ask and its answer recorded against module and Issue. Where the last change was an Agent Run the record points at a transcript that no study shows anyone reads (N09:102), which the card states and which is the family's open question.

#### JN-6 Transfer walkthrough signed by both names

- **Stage and cell**: Person handing over / Explain (widened; social).
- **What it is**: When a person leaves a module or Project they walk the receiver through it; the receiver's questions drive the session; both sign the record against the modules and ref. Dashpot lists held modules with no signed receiver.
- **Mechanism and evidence**: Fagan convened a full inspection when responsibility for code transferred (N26:191); departed engineers answer at too high an abstraction (N26:174); succession roughly halves the follower's productivity and mentors cannot transfer to many followers (N26:165); about 130 files a quarter are abandoned and co-change successors are correct under half the time (N26:166–167). Revival from documents alone is strictly impossible (N26:134). AWS's ADR review is the one pre-AI process recording who was present at a reading (N24:22–23). Best evidence: mining studies plus practitioner accounts.
- **Nearest existing thing**: The session-boundary handover cell (state plus stance); Jabrayilzade's practices list (N26:174).
- **Authorless code**: The leaver need not be the author; if no one holds the module there is nothing to hand over (N26:5).
- **Grain**: Module set.
- **Demand**: Explain.
- **Enforcement and relocation**: Optional; a bound could be "no departure without signed receivers for held modules".
- **Decay**: A signed record is dated and invalidated by change (MR-2).
- **Verifiability**: Receiver's explain-back at four weeks (the JN-2 instrument).
- **Evidence source**: Independent mining; no evaluation of walkthroughs.
- **Lifecycle hook**: New observation.
- **Without AI**: Yes.
- **Coordination cost**: Hours per module for two people.
- **Social form**: Team; attaches to module and ref; feeds PD-5.
- **Verdict**: *Shortlist, in the explain-back family, with a display of its own.* The receiver's questions drive the walkthrough (principle 13's interactive form, here with a second source in N26), both names sign, and Dashpot lists held modules with no signed receiver — a bound-like view built from the ledger. Instrument is the receiver's explain-back at four weeks.

#### JN-7 Mentor or reviewer recommender from authorship

- **Stage and cell**: Person joining / Read-navigate (N) — expected to fail the authorless-code lens; recorded for the rejection.
- **What it is**: The newcomer is pointed to a mentor or reviewer by blame, commit history, or CODEOWNERS globs.
- **Mechanism and evidence**: Canfora's mentor recommender reached top-1 above 80% except Python and FreeBSD (N26:51); RevFinder ranked a correct reviewer in the top 10 for 79% offline (N09:60); in vivo at JetBrains the recommender showed no influence on choice, MRR about 0.64 regardless, and 63–92% already knew the reviewer (N09:61–63). The Line 10 Rule is circumstantial responsibility (N09:4, N09:36); Expertise Browser's authors report no definitive validity (N09:54); CODEOWNERS is a glob map (N19:151); top-five co-changers were correct 48% and 34% (N26:167).
- **Nearest existing thing**: Expertise Recommender (N09:38); CODEOWNERS (N19:151).
- **Authorless code**: Fails: when the last modifier is an Agent Run there is no person to approach (N09:100); the proxy was weak before agents (N23:59–66, N19:152).
- **Grain**: File.
- **Demand**: Read.
- **Enforcement and relocation**: Advisory.
- **Decay**: Not applicable.
- **Verifiability**: No study measures a recommender changing who was asked or how fast (N09:74).
- **Evidence source**: Offline precision (N09:55–60); one in-vivo null (N09:61).
- **Lifecycle hook**: Derived from Git.
- **Without AI**: Weak then too.
- **Coordination cost**: Low.
- **Social form**: Infers rather than records.
- **Verdict**: *Reject*, on authorless code. The in-vivo null at JetBrains (N09:61) shows the recommender did not change who was asked even before agents; with an Agent Run as last modifier it has no one to recommend.

#### JN-8 Newcomer as first reviewer of the agent's change

- **Stage and cell**: Person joining / Verify (widened) — the junior task rebuilt as verification.
- **What it is**: The newcomer's early work includes being first named reviewer of Pull Requests whose Branch had an Agent Run bound, tracing why a change is right or wrong before a senior signs; Dashpot shows the review decision and the bound run.
- **Mechanism and evidence**: The legal profession names verification exercises as the junior task replacement (N03:87–88); a proposed junior path is reviewing agent output and tracing why it is wrong (N03:97); Amazon requires senior sign-off on junior AI-assisted changes after a 13-hour outage (N03:100); junior-only review steps are phased out once judgment is shown (N03:102). Seniors can no longer observe whether juniors are learning or prompting (N03:26–27). Review spreads files known by 66–150% (N26:196); unfamiliar files take longer for 91% of reviewers (N26:195). No source observes whether the senior now reviews the agent instead of the junior (N03:107). Best evidence: practitioner policy; no skill measure.
- **Nearest existing thing**: Google's readability review of a new hire's first commit (N26:55, N26:203); Fagan's overview as education (N26:189).
- **Authorless code**: Built for agent-written changes; passes.
- **Grain**: Pull Request.
- **Demand**: Verify; recorded act is the review.
- **Enforcement and relocation**: A PR check can require the newcomer's review before merge; moves first review onto the newcomer and sign-off onto the senior.
- **Decay**: Fades by policy once judgment is shown (N03:102); month six needs review-comment substance over time.
- **Verifiability**: Reviewer explains a hunk (the review-row cell) scored by rubric; time-to-tenth-PR as a coarse companion (N18:25).
- **Evidence source**: Vendor survey and policy reports (N03:87, N03:100).
- **Lifecycle hook**: Observed today (review decision, Agent Run on Branch); the role assignment is Repository policy.
- **Without AI**: The reviewed change could be human-authored; the role still trains.
- **Coordination cost**: Adds a review step; makes the agent's output the newcomer's first object of study.
- **Social form**: Team; attaches to Pull Request.
- **Verdict**: *Shortlist, folded into RV-1 as its newcomer firing point.* Its own evidence is policy only, but the act it asks — the newcomer traces why the agent's change is right or wrong as first reviewer — is RV-1's reviewer-explains-a-hunk, and review's knowledge spread is the mechanism onboarding needs. Fades by policy once judgment is shown, which is principle 10 done socially.

## What the walk showed

Ninety-one candidates across twelve stages: 47 shortlisted, 18 held, 26
rejected. The numbers overstate the shortlist, because most shortlisted
candidates are one mechanism fired at different boundaries and fold into
a head; reduced, the shortlist is twelve families, below. Three things
the walk itself showed:

- **The in-loop row is empty.** All eight IL candidates were rejected or
  held: harness-side defaults Dashpot cannot set or see, mid-task
  firing where 62% dismiss, nothing on a human-authored branch, and the
  clearest measured decay in the corpus. Principle 2 predicted this;
  the one mechanism with causal support at that row (IL-7) survives by
  relocating to the hand-off boundary.
- **The authorless-code lens did its work.** Seven rejections turned on
  it — every candidate that inferred knowledge, ownership, or a
  reviewer from authorship, plus provenance-to-transcript and the hard
  stop on agent-authored arrivals. None had a second defence.
- **The families converge on one new fact.** Every shortlisted act
  needs the same record the analysis named as the first design
  decision: a person's act as a Dashpot fact, with a declared name, an
  act kind, a shared object at a ref, a time, and an outcome. The
  ledger (PD-5) is that record; the named-person family (ST-6) is its
  identity; everything else writes to it or reads from it.

Rejections by deciding lens: authorless code 7; demand (no act) 6;
without-AI or lifecycle hook 6; verifiability 4; decay 2; evidence
source 1.

## The shortlist, as families

Each family names its head, the candidates that fold into it, the
assumptions it depends on, and the cheapest test of each assumption. An
assumption marked *shared* appears in the cross-cutting list at the end
and is not repeated.

### F1. A named person signs

**Head** ST-6; folds IN-4, RV-6. A person's declared name at three
signatures — holding the Issue at binding, signing the integration,
merging distinct from the agent's principal — recorded where Dashpot
observes: the Work Store, the Issue Source, the Pull Request.

- *The Issue Binding can carry a person as well as a session.* Test: add
  a person field to the Work Store record and have the skill ask for it
  at `work start`; count bindings with and without a name over two
  weeks.
- *A signature obliges something.* No policy read defines what; the
  family pairs each signature with a sampled act from F4. Test: for a
  sample of signed integrations, ask the signer one F4 question a week
  later; the pass rate is what the signature was worth.
- *The name is declared, never inferred.* Test: grep the implementation
  for any use of blame, ownership, or CODEOWNERS as a default; there
  must be none.

### F2. The ledger of acts

**Head** PD-5. Not a friction; the record the other families write.
Entries keyed by module, ref, date, act kind, declared person, outcome.

- *A person's act is a fact Dashpot can hold with its usual discipline*
  — opaque identity, retained when a refresh fails, never inferred from a
  label (principle 6). Test: write the Pydantic model and the storage
  seam before any act is recorded; the review of that model is the test.
- *Where it lives is decidable.* Project-local Work Store, the Issue
  Source, or the repository (git notes); each has a different lifetime
  and audience, and posting to the Issue Source is a mutation under
  ADR 0008. Test: the grilling; then one entry kind written to each
  home for a fortnight, and a count of who read it where.
- *Entries stay honest as code changes.* Test: every entry carries a
  ref; F7's invalidation is the proof that the ref is read.

### F3. Recall before reveal

**Head** IS-2; folds ST-1, MR-4, RT-2. State from memory what changed —
in the module at binding, in the Branch since your last run, at the
module on revisit, in the repository on return — then see the Git facts.
Scored by Git, no judge, regenerated per firing so it cannot go stale.

- *A recall before a diff changes what a person can later say about the
  Branch.* Test: F12's persistence re-test on a sample of guessed against
  unguessed sessions, four weeks out.
- *People answer rather than skip.* Test: the skill records "don't know"
  separately from a guess; the ratio over a month is the engagement
  figure, and Karpicke's condition (feedback after a miss) is met by the
  reveal itself.
- *The guess is posted, not kept in the session.* Shared.

### F4. Explain it back, answer hidden

**Head** HO-1; folds MR-3, JN-2, JN-6, RV-1 with RV-2, JN-8; IL-7
relocated here; HO-2 held as the cheaper option. A generated explanation
with the code off screen, scored against the code by a rubric, at
hand-off, revisit, joining, handover, and review (reviewer explains a
hunk; author answers a question). The one mechanism with a causal result
on code.

- *The result transfers from novices on a fixed app to professionals on
  a living repository.* Untested anywhere (gap G1). Test: F12's
  persistence re-test and F11's blackout task on hand-offs with and
  without an explanation, on this repository, for a quarter.
- *A judge can score developer explanations reliably.* No judge–human
  agreement figure exists for a code gate. Test: two people and the
  judge score the same twenty explanations blind; κ below .6 means a
  person grades until it improves.
- *The explanation is the person's, not pasted from the agent.* No text
  proves this (N23:93). The family does not try; it relies on the
  answer-hidden condition and on F11 catching the gap. Test: F11's pass
  rate against F4's score; divergence is the paste rate.
- *Expertise reversal is handled by fading.* Test: the threshold is F7's
  record of what the person holds; watch whether experts' time per
  explanation falls to the median of 14 minutes or below within a month,
  and whether they opt out.
- *At review, doubling the reviewer's load is accepted.* Test: RV-1 on
  one hunk per Pull Request, not every hunk, for a month; measure
  comments per PR against the habituation baseline (F12's decay
  instrument).

### F5. Restate at both ends

**Head** IS-1 with HO-3; AR-7 held as the template shape. The person's
own account of the Issue at binding and of the change in the Pull
Request body at hand-off, compared.

- *The comparison is an instrument.* Untested. Test: for ten Issues,
  have a second person read both accounts blind and say whether the
  second shows a model the first lacked; agreement between two readers
  is the instrument's reliability.
- *People write rather than paste.* Shared with F4's third assumption.
- *Task start is worth a bet.* The thinnest row of the map. Test: the
  restatement costs one comment; if F5's instrument shows nothing after
  twenty Issues, drop IS-1 and keep HO-3 as the norm it already is.

### F6. Ask a person, recorded

**Head** IS-4; folds HO-5, JN-5, RT-6; RV-2 shared with F4; AR-8 shared
with F10. An ask, by a named person of a named person, about a module,
recorded on the Issue or Pull Request with its target — a person, a
document, a model. The directory in use, made observable ([themes 5.4](themes.md#54-the-question-routing-economy)).

- *Who is asked is a fact people will record.* Test: the skill offers
  the record at the binding, hand-off, and return boundaries for a
  month; count asks recorded against Pull Requests opened.
- *Recording asks does not chill them.* Fear of revealing ignorance is a
  documented cost (N26:19). Test: asks per person per week before and
  after the record exists.
- *When the last modifier was an Agent Run, the record points at
  something useful.* The card says a transcript; no study shows one is
  read (N09:102). Test: for those cases, record whether the asker
  opened the transcript, the handover (F9), or a person, and what
  answered the question.
- *"Who acted" is never presented as "who knows".* Test: as F1's third.

### F7. Verified at ref, invalidated by change

**Head** MR-2; folds RT-1, RT-5, PD-1; MR-1, MR-5, RV-3, JN-4 held as
extensions. A per-person mark on a module with a hidden-answer item,
unverified when integration facts Dashpot already observes show the
module changed, re-asked on change, on return, or by sample.

- *A hidden-answer item about a module can be written and scored against
  the code.* Test: write ten items for ten modules of this repository
  by hand and have three people answer them blind; items that
  discriminate people who worked in the module from those who did not
  are the item format.
- *Change-triggered invalidation is enough without a spaced schedule.*
  MR-1 held on this. Test: after a quarter, plot miss rate against
  time-since-verification for unchanged modules; a rising curve is the
  case for adding MR-1.
- *The ratio of answered re-verifications to bare marks stays above
  click-through.* This is the family's decay instrument. Test: report it
  monthly; below one in two, the item is being skipped and F7 has become
  RV-4.
- *This record is what F4's fading reads.* Shared.

### F8. Predict as a test

**Head** MR-8; IL-8 held for the boundary form. A prediction about a
module's behaviour written as an executable test before reading, run,
and kept in the repository so the record is the artifact.

- *People will write a test before reading unfamiliar code.* Practitioner
  method only, and two of its cards are marked recalled, not read.
  Test: the skill offers it at revisit for a month; count predictions
  written, and the failing-prediction rate, which is the signal.
- *The test is worth keeping regardless.* Test: whether the
  characterisation tests written this way survive a quarter in the
  suite.

### F9. Handover: state and stance

**Head** SB-1 with SB-2; folds SB-3 (with SB-4), RT-4, ST-4; SB-6 is the
question of where it lives; SB-5 held as its trigger. The outgoing
holder — usually the agent — writes state, next step, belief, intent,
expectation, contingency, and the cue to resume at, before `work stop`,
relocation, or a planned end; the receiver asks one question before
resuming; Dashpot reconciles the run's own undone list against Git and
Pull Request facts and shows only the disagreements.

- *An agent will fill the record and a person will read it.* The
  schema-filling half is likely (agents fill schemas); the reading half
  is the medical finding that most incoming clinicians asked nothing.
  Test: count handovers written against stops for a month, and
  questions asked against handovers read.
- *Sender and receiver agree on the most important item.* Chang's 60%
  disagreement is the baseline. Test: for ten handovers, ask each side
  blind; the agreement rate is the instrument.
- *The reconciliation catches real disagreements.* Test: SB-3 alone,
  first: the share of stops whose self-report disagrees with Git, on
  this repository, for a month. It rests on observed facts and needs
  nothing else built, so it is the cheapest test in the shortlist.
- *Principle 13 has a second source.* N04:114 and N11:80 are named; the
  test is whether the grilling accepts them.
- *Where the record lives is decided.* Shared with F2.

### F10. Bounds

**Head** AR-1; folds IS-5 with AR-2, IL-6 with AR-3, IN-1 with IN-2,
IN-5, AR-5; AR-8 shared with F6. One board: open Pull Requests without a
review decision per person, live Agent Runs per person, change size at
open, Branch age against trunk, queue age, and a landing order across
concurrent Worktrees derived from file overlap — each against a bound
the team sets and Dashpot shows, never enforces.

- *A bound changes behaviour when it is only shown.* The WIP evidence
  is before–after with enforcement; a shown bound is untested. Test:
  AR-1 and AR-3 as glyphs for a month; median open PRs and PR size per
  person before and after.
- *A bound changes what anyone understands.* No source says so
  (principle 14 states this). Test: F12's team instrument before and
  after the board exists; if agreement does not move, the family is a
  flow tool, which is still worth having, and says so.
- *File overlap predicts conflict well enough to order by.* Developer-
  named indicators did not (N12:25) and 42% of agent conflicts are
  structural. Test: replay landing orders with `git merge-tree` on this
  repository's history; the overlap heuristic's hit rate is the number.
- *The confirm on landing order does not habituate.* Test: it fires only
  when overlap is non-empty; count fires per week and confirms without
  reorder.

### F11. Coupled rationale

**Head** IN-3. A decision record written or confirmed by a named person
when a Pull Request that chose among alternatives integrates, carrying a
check that runs on change to the files it names; Dashpot shows the
check's state beside the Branch. The one artifact candidate that names
its change signal.

- *Records get written when the skill drafts and a person confirms.*
  Capture cost is the field's forty-year failure. Test: count records
  per integrating PR that chose among alternatives, for a quarter; half
  of ADR repositories hold one to five records, so below that rate the
  candidate has the field's problem.
- *The check catches staleness before a reader does.* Test: fraction of
  records whose check failed and was repaired, against records a reader
  reported wrong.

### F12. The instruments

**Heads** RT-7 with HO-8 (the individual instrument), PD-4 (the team
instrument), PD-8 (the persistence instrument); AR-4 held as the decay
instrument for review. Not frictions: the measures every family above
names as its test. A sampled blackout repair on the person's own
Worktree with the agent off; the same structural questions to every
member scored by agreement and against the code, with "whom would you
ask" alongside; hand-off items re-posed at one and four weeks, diff
hidden; lines per hour of review as the habituation series.

- *People opt in to a half-hour blackout at return.* The largest cost on
  the shortlist. Test: offer it sampled at one return in five for a
  month; the opt-in rate decides whether it is an instrument or a
  study.
- *Agreement across members is computable for a codebase.* Never done
  (gap G15). Test: PD-4 once, by hand, with this team: ten questions,
  every member, one hour; the agreement index either exists or does
  not.
- *Four weeks is a horizon people tolerate.* Test: PD-8 on the first ten
  hand-off items; completion rate at one week and four.
- *The instruments are not Goodharted.* The corpus's documented harm is
  educational. Test: none of the instruments' scores appears in a
  performance review; state this in the design and check it in the
  grilling.

## Cross-cutting assumptions

Shared by several families; each is a single point of failure for the
shortlist and belongs at the top of the grilling.

1. **The skill step ran.** Every skill-carried act assumes the agent
   performed it, and Dashpot's hooks see lifecycle events, not skill
   steps; constraint violation runs at 38% of misalignment episodes
   (N04:117). Cheapest test: the skill writes a one-line trace to the
   Work Store at each step it performs; the count of traces against
   `work start` events is the adherence figure.
2. **A person's act can be a Dashpot fact.** The analysis's first design
   decision, made concrete by F1 and F2. Cheapest test: the model and
   seam review.
3. **Where the record lives.** Work Store, Issue Source, or repository;
   lifetime, audience, and ADR 0008 all differ. A grilling question, not
   a lens.
4. **Text provenance is unverifiable.** No explanation, restatement, or
   description proves a person wrote it. The shortlist relies on
   answer-hidden conditions and on F12's blackout task, never on
   provenance.
5. **No comprehension gate has been watched for months.** Every decay
   line above is a design answer to an unmeasured question; F12's decay
   instrument and F7's ratio are the first measurements.
6. **The rejected rows are not forgotten.** IS-6 and IN-6 are backlog
   items, not family members; IL-1 is a harness gap to raise upstream;
   PD-3 with RT-3 is the agent-free stint a team may still choose.

## Sequence, if the grilling holds

The families order themselves by dependency and by cost of the cheapest
test, not by evidence strength:

1. F1 and F2 first, because every other family writes to them; their
   tests are a model review and a fortnight of counts.
2. SB-3 (F9's reconciliation) next, because it rests entirely on facts
   Dashpot already observes and measures agent self-report directly.
3. F3 and F10's glyphs, because they need no judge and no new act
   store beyond F2.
4. F7 and F4, which need the item format and the judge reliability
   tests before they are more than a bet.
5. F12 throughout, since without it nothing above can be said to have
   done anything.

The grilling — by the user, then an independent second opinion — comes
before any of this, and the analysis's method says so.
