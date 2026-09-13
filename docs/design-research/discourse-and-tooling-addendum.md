---
status: research
date: 2026-09-13
---

# Discourse and tooling addendum

This note is a documentary sweep of practitioner tooling and discourse on cognitive debt that the
thirteen earlier notes in this folder did not reach: more "prove you understand it" tools, company
policies and talks that name comprehension of agent-written code, 2026 essays outside the landscape
sweep's Cluster 8, provenance and attestation tooling since the Agent Trace RFC vanished, and the
state of solve.it-style defaults in editors and agent CLIs. It records what exists and what each
source says; it does not evaluate fit for Dashpot, rank, or recommend. Every claim carries its
primary source; figures (stars, dates, versions, view counts) were read on 2026-09-13 from the
GitHub API, the VS Code Marketplace, `yt-dlp` metadata, HN Algolia, and Lobsters, and are point
readings. Where a claim rests on a vendor's own page that is stated. Sections the earlier notes
already cover are pointed to rather than repeated.

## The gap

The earlier notes left the practitioner side explicitly open. The landscape sweep's
[dead ends](landscape-sweep.md#dead-ends) record "Company engineering blogs describing internal
comprehension-check rituals: none found" and "Conference talks on the theme other than Litt's: none
located by title", and its [areas the seeds missed](landscape-sweep.md#areas-the-seeds-missed)
list stops at the Cluster 8 essays. The hand-off note's
[dead ends](track-hand-off-checks.md#dead-ends) say the web budget ran out before "other PR-quiz
actions or apps beyond the three known" could be searched and that a GitHub search for "pr quiz"
"surfaced nothing new"; its [gate placement table](track-hand-off-checks.md#gate-placement-and-enforcement)
therefore covers dkamm PR Quiz, Revodata's quiz-gate, and Tidewave, with the measurement note's
[position papers](track-measurement.md#position-papers-and-proposals) adding sphinx-ci, PopPR,
VibeQuiz, PRep, and jeo-prd. The rationale note found the
[Agent Trace specification](track-rationale-as-artifact.md#the-agent-trace-specification) repository
gone and no shipped consumer among its backers, and asked
[who renders a trace for a human reader](track-rationale-as-artifact.md#who-renders-a-trace-for-a-human-reader).
The friction note's [inversion outside notebooks](track-in-loop-friction.md#inversion-outside-notebooks)
section and its [dead ends](track-in-loop-friction.md#dead-ends) found no editor with
manual-trigger-only completions by default and no tool that suppresses the agent's next step. The
talk note's [dead ends and gaps](understanding-bottleneck-talk.md#dead-ends-and-gaps) and the
Answer.AI sweep's [dead ends](answer-ai-sweep.md#dead-ends) leave the 2026 talk circuit and the
non-notebook product landscape unexamined. This addendum fills those six holes as far as one bounded
pass allows.

## Target 1: More "prove you understand it" tools

Every tool below is new relative to the earlier notes (checked against the union of URLs they cite).
Entries follow the format *type · who · what · mechanism · when it runs · status · evidence*.
"Storage" means what the tool persists about a human's answers; "none documented" means the README
read for this note describes none.

**diffquiz** — CLI (npm `diffquiz`, TypeScript, zero runtime dependencies, Node ≥ 22.18) · TYLDA
Solutions · "A 60-second quiz on your own diff before you open the PR"; 3–5 multiple-choice
questions tagged `[behavior]`, `[failure]`, etc., about the uncommitted or unpushed diff against
`merge-base(HEAD, origin/main)`; a wrong answer immediately shows the relevant lines and a
two-sentence explanation · *generates questions through whichever of the `claude` or `codex` CLIs
is installed, or a configured provider command* · run by hand before a PR; installing the Claude
Code plugin adds a `PreToolUse` hook that in "auto" mode defers `git push` / `gh pr create` until
the quiz is taken but "never block[s] it"; the README's roadmap lists an opt-in `pre-push` hook and
a GitHub Action posting a non-blocking comment · "**Not a gate.** Exit code is always 0 regardless
of score"; MIT; ★1; created 2026-09-02; pushed 2026-09-11; v0.2.0 (2026-09-11); storage none
documented · [repo](https://github.com/TYLDA-Solutions/diffquiz).

**AIditor: Code Review Quiz** — VS Code extension (`asabry.aiditor-vscode`) · Abdulrahman Sabry ·
quizzes the developer on `git diff --staged` (skipping trivial diffs) with multiple-choice and
LLM-graded free-text questions; default pass mark 75% · *uses the VS Code Language Model API or a
bring-your-own key for Anthropic, OpenAI, Google, or Groq; installs a real git `pre-commit` hook so
that commits from the terminal, the SCM view, or a GUI client are blocked until the quiz passes* ·
at commit · v1.0.6, updated 2026-09-07, 5 installs, MIT, no repository URL in the listing; storage:
webview only, none documented · [Marketplace listing](https://marketplace.visualstudio.com/items?itemName=asabry.aiditor-vscode).

**cognitive-debt (PrincessSats)** — Claude Code plugin built on hooks, zero dependencies ·
PrincessSats · tracks Claude-written code the user "never engaged with" as points owed (the README
shows `340/250 · level full`), accrues "interest", and issues one-question multiple-choice cards on
specific ranges such as `src/auth/session.py:40-118` · *at the "ultra" level it blocks commands
(`⨯ blocked — cognitive-debt (ultra)`) until a card is answered; levels are configurable* · during
the session, after each Claude edit · MIT; ★0; created 2026-08-06; pushed 2026-08-09; storage: a
local ledger of debt points (format not examined) · [repo](https://github.com/PrincessSats/cognitive-debt).

**quiz-me (runsagents)** — agent skill (`npx skills add runsagents/quiz-me`) · runsagents · reads
recent repository changes and asks eight questions of the "why is it built this way" and "what
breaks if X fails" kind, grades out of 8, and prompts a retake below 6/8 · *prompt-only; the model
both asks and grades* · after a change, on request · CC0; ★0; created 2026-07-13; pushed
2026-07-14; v1.0.0; storage none · cites Thariq Shihipar's field guide, the change-quiz skill, and
dkamm PR Quiz as prior art · [repo](https://github.com/runsagents/quiz-me).

**change-quiz (finding-unknowns-skills)** — skill in a skills collection · Neeeophytee · after a
session, builds a four-section report (Context / What changed / How it interacts / Intuition),
optionally as a single HTML page, ending in a 5–8 question quiz mixing recall and prediction;
"Pass = merge-ready"; after two failed rounds it recommends simplifying or splitting the change ·
*prompt-only, self-graded ("grade honestly")* · end of session · MIT; ★331; created 2026-07-05;
pushed 2026-09-09; storage none · [SKILL.md](https://github.com/Neeeophytee/finding-unknowns-skills/blob/main/skills/change-quiz/SKILL.md).

**quiz-me (emanzurv)** — Claude Code plugin ("The bouncer for your diff") · emanzurv · before
writing a fix, Claude asks the user for the root cause and the fix in a three-question round; "Nothing
gets written until you convince it you do" · *skill plus hooks; the gate is before generation, not
before merge* · at task start · MIT; Python; ★5; created 2026-08-10; pushed 2026-09-07; v0.8.2;
storage none documented · [repo](https://github.com/emanzurv/quiz-me-skill).

**okay** — set of Claude Code skills "for developers who type their own code" · rebeloper ·
`/okay:quiz-me` (live multiple-choice, hint and retry, "Never the answer"), `/okay:now-i-do-it`
(saves the current git diff as an answer key, reverts it, then paces a rebuild by hand),
`/okay:audit`, `/okay:explain`, `/okay:teach-me` · *"The AI does not write your code. You type every
line."* · on invocation · MIT; ★3; created 2026-09-02; pushed 2026-09-07; storage: markdown learning
workspace for `mentor-me` · [repo](https://github.com/rebeloper/okay).

**WHY** — Claude Code plugin "Combat cognitive debt from AI-assisted development" · jobrien874 ·
"questions/quizzes you on code you've accepted from Claude in Terminal", about "60 seconds" per
acceptance, questions "rooted in your specific code" · *prompt-only* · after accepting code · MIT;
v1.0.0; ★0; created 2026-04-11; pushed 2026-04-12; the README grounds the term in the 2025 MIT
Media Lab EEG study and repeats its "55% reduced neural connectivity" figure (the README's claim,
not verified here); the companion Medium article returned HTTP 403 · [repo](https://github.com/jobrien874/why-plugin).

**plum** — Go CLI, no dependencies · k3-mt · `plum run -- claude` wraps a session into a
`bundle.json`; `report`, `synth`, `trace` (an instrumented test run), `explore` (a code landscape
with "no score, no timer"), `export` (HTML), and `quiz`, which is offered "only after exploring" and
is "graded on real traces"; `claims verify` is meant for CI · *questions are grounded in recorded
execution traces rather than the diff text* · after a session · MIT; ★0; created 2026-08-20; pushed
2026-08-22; v0.2.6 (2026-08-22); languages Go, Python, JS/TS, dbt; storage: the bundle file ·
[repo](https://github.com/k3-mt/plum).

**opencode-sit** — OpenCode read-only agent ("Socratic Intelligent Tutor") · aemonge · viva, trace,
brain-dump, spot-the-gap, debug-prediction, and invariant modes with a hint ladder; a project-local
"mastery ledger" convention · *the agent definition denies edits and bash* · on invocation · MIT;
★0; created 2026-05-13; pushed 2026-05-22; storage: the ledger file · [repo](https://github.com/aemonge/opencode-sit).

**beanz** — Rust CLI, Homebrew tap · daveepope · scores "cognitive debt" per Claude Code session
from the session JSONL: code debt (files touched, complexity, context pressure, autonomy streaks,
"whether you're still asking questions") and artifact debt; `beanz watch` and `beanz score`, strict
and lenient profiles; the README suggests a CI gate over transcripts · *heuristic scoring of the
transcript, no quiz* · continuous or on demand · MIT; ★6; created 2026-07-03; pushed 2026-09-04;
v1.2.0 (2026-07-15); cites Trojer, Kosmyna, and He et al. (MSR 2026) · [repo](https://github.com/daveepope/beanz).

**thinking-cap** — OpenCode plugin · shreyas-makes · repository-local spaced repetition shown in a
terminal sidecar while the agent is busy; cards are extracted from transcripts by heuristics ·
*SQLite plus markdown* · while waiting on the agent · no license; ★1; created 2026-03-13; pushed
2026-03-15 · [repo](https://github.com/shreyas-makes/thinking-cap).

**llmwiki / Quiz_wiki** — local-first project wiki that "quizzes you back" · suwonleee · captures
Claude Code, Codex, and OpenCode sessions into a per-project markdown wiki with a spaced-repetition
quiz layer "on your own past decisions"; the README reports one developer's eleven weeks (19
repositories, 997 pages, measured 2026-08-21) and states these are not claims about teams ·
*hooks inject at most a few kilobytes of pointers per session; SQLite index over markdown* ·
continuous · Apache-2.0; ★14; created 2026-07-12; pushed 2026-09-06 · [repo](https://github.com/suwonleee/llmwiki).

**accountable-review** — Claude Code plugin, "Beta — early stages" · WyeWorks · the `review-map`
skill turns a PR into a published HTML "Review Map" organised by behaviour (Rails and Phoenix);
`setup-ci` produces one per review-ready PR; explicitly no verdict or score · *rendering for the
reviewer, not a quiz* · at PR time · MIT; ★0; created 2026-08-26; pushed 2026-09-11 ·
[repo](https://github.com/wyeworks/accountable-review).

**cognitive-debt-action** — GitHub Action · phoenix-assistant · a heuristic "orphaned AI code"
score per file: AI marker +30, no human comments +20, no tests +20, no TODO +15, no ADR +15;
threshold 50; opens issues; `fail-on-debt` input · *static heuristics, no model, no quiz* · on push
or PR · ★0; created 2026-05-03 · [repo](https://github.com/phoenix-assistant/cognitive-debt-action).

Also seen but not examined beyond their listings: yarikleto/claude-teacher-plugin (★8),
kesslernity/cognitive-debt-prevention-kit (★3, templates), EmanuelVogt/skills (★6),
luxsolari/three-axes-framework (v1.5.0, ★0), and XiaYiHann/socratic-agent (papers, not code).

**The prompt pattern behind several of these.** Thariq Shihipar's Anthropic post "A field guide to
Claude Fable 5: Finding your unknowns" (claude.com, 2026-07-06) gives the prompt "Give me a HTML
report on the changes … and a quiz at the bottom on the changes that I must pass" and states "I only
merge after I pass the quiz perfectly"; his examples page describes "A merge-readiness report on a
14-file diff that ends in a six-question quiz you must pass"
([post](https://claude.com/blog/a-field-guide-to-claude-fable-finding-your-unknowns),
[examples](https://thariqs.github.io/html-effectiveness/unknowns/)). The matching talk, "Field Guide
to Fable", AI Engineer World's Fair 2026, has a 9:08 chapter "Finding your unknowns" (uploaded
2026-07-06, 166,799 views, [recording](https://www.youtube.com/watch?v=9fubhllmsBU)). runsagents
quiz-me and change-quiz cite it as prior art.

## Target 2: Company engineering blogs and public RFCs

Said plainly: no company engineering blog or public RFC was found that describes an *internal
comprehension-check ritual* for AI-written code — a quiz, an explain-it-back step, or a recorded
attestation of understanding. What exists is policy language that names understanding as the
author's obligation, review policies that distinguish agent-authored PRs, and talks in which
companies describe adoption programmes. Searched: engineering-blog queries on "explain the
change" / "author must explain" / "we require" for agent PRs; GitLab, PostHog, and Sourcegraph
handbooks; "no AI code you can't explain" policies; onboarding-with-agents posts; Duolingo,
Automattic, and Umbraco follow-ups; the QCon London and San Francisco 2026 programmes.

- **PostHog** — three public, versioned documents. `AI_POLICY.md` (added 2026-04-14 in PR
  #54546, "require proof" 2026-04-23 in #56071) tells external contributors "You own what you
  submit. Understand your code, test it, and be ready to explain why it's correct and how it
  interacts with the rest of the system (without re-prompting an LLM)", requires proof (a demo or
  tests), requires disclosure of AI use, and blocks an account after two closures
  ([AI_POLICY.md](https://github.com/PostHog/posthog/blob/master/AI_POLICY.md)). The handbook page
  "How we review" (last changed 2026-09-09) says PRs "can be written by humans or by agents",
  "every PR needs a review before merging, and a human always merges"; human-authored PRs may be
  approved by "Stamphog, our AI approval agent" after deterministic checks and an LLM pass, while
  "Agent-authored PRs always require a human review since we want at least one human in the loop";
  reviews should "make sure more than one person understands important changes"; for quick reviews
  "Actually read the diff. Don't just hit approve"
  ([handbook](https://posthog.com/handbook/engineering/how-we-review),
  [source](https://github.com/PostHog/posthog.com/blob/master/contents/handbook/engineering/how-we-review.md)).
  Paul D'Ambra's blog post "10,000 PRs a month is easy" (2026-07-28) reports 1,441 PRs in January
  to 4,725 in June with 10% more engineers, says "20% of our PRs are approved by StampHog" for
  "about $300 per month in tokens", and lists the questions left to humans: "Do I understand this
  change?", "Does the author understand the change?", "Is this change safe?", "Is this change
  valuable?" ([post](https://posthog.com/blog/10k-prs-a-month)). None of the three describes how
  "does the author understand" is checked.
- **Duolingo** — no blog post found; the QCon London 2026 abstract for Sarah Deitke's "Teaching
  Engineers, Trusting AI: How Education Enabled Autonomous Code Review" describes scaling AI use
  "across 300+ engineers through intentional dogfooding programs, live training, office hours, and
  AI observability dashboards" and "Our AI-powered PR Risk Score and auto-approval system now safely
  approves 10% of pull requests and cuts developer wait times in half"
  ([abstract](https://qconlondon.com/presentation/mar2026/teaching-engineers-trusting-ai-how-education-enabled-autonomous-code-review)).
  Abstract only; no recording located.
- **Ona** — Benjamin Stark, "How auto-approving low-risk PRs with AI cut our lead time by 74%"
  (2026-04-09): six mechanical criteria (under 1,000 lines; no protobuf, database, infrastructure,
  auth, or audit changes), an agent evaluates every PR, "A human always clicks the merge button";
  median lead time 4.1 h to 1.1 h over a four-week window. The post contains nothing about humans
  understanding or explaining agent-written code ([story](https://ona.com/stories/auto-approving-low-risk-prs)).
- **GitHub (vendor guidance, not an internal ritual)** — Andrea Griffiths, "Agent pull requests are
  everywhere. Here's how to review them" (2026-05-07): a reviewer's checklist including "Require a
  new test that fails on the pre-change behavior. If the agent can't write a test that would have
  caught the bug it claims to fix, the fix is incomplete or the understanding is wrong"
  ([post](https://github.blog/ai-and-ml/generative-ai/agent-pull-requests-are-everywhere-heres-how-to-review-them/)).
- **Team programmes described only in talks** — Umbraco (Emma Burstow, NDC London, "Learning not
  leaning", mandatory Copilot-assisted sprints) and Automattic (Sanja Grbic, "500 people vibe-coded
  for 30 days", Radical Speed Month) are in Target 3; neither has a matching engineering-blog post
  that was found.
- **Practitioner discourse as a dataset** — Agarwal, Miller, Kästner, and Vasilescu, "3100
  Opinions on Code Review in an AI World" (arXiv 2607.07980, 2026-07-08) code 3,100 of 38,709
  collected documents and report that agent-authored PRs are reviewed less often and merged faster
  ([abstract](https://arxiv.org/abs/2607.07980)). Ehsani, Rawal, Cai, and Chatterjee, "Faster Code,
  Deeper Debt?" (arXiv 2606.14796, 2026-06-11) review 104 sources (31 formal, 73 grey) and name
  "fast-integration debt" and "provenance debt" among LLM-specific debts
  ([abstract](https://arxiv.org/abs/2606.14796)).
- **Vendor feature aimed at team onboarding** — Claude Code 2.1.101 (npm 2026-04-10) added
  `/team-onboarding`, which "generate[s] a teammate ramp-up guide from your local Claude Code usage"
  ([changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)).

## Target 3: 2025–2026 talks beyond Litt's

Unless marked "recording", outlines come from the official abstract or the video description and
chapter list; no recording was watched end to end. Upload dates and view counts are `yt-dlp`
readings on 2026-09-13.

**AI Engineer World's Fair 2026 (San Francisco, 29 June – 2 July).** The programme's `sessions.json`
(561 sessions) places Litt's "Understanding is the new bottleneck" on Day 3 at 10:45 in Track 6,
Design Engineering, with the abstract "it's not enough to just verify correctness -- you actually
need to understand the work they're doing" ([schedule](https://ai.engineer/worldsfair/schedule)).
Same track, same day: Maximillian Piras, "Mousepower: agents that can't be measured, can't be
managed" — "judgement is the new bottleneck … code generation becoming largely solved at the expense
of breaking code review" (abstract). Elsewhere in the programme:

- Alex Volkov (ThursdAI), "The Z/L Continuum: Should AI Engineers Still Read Code?", Leadership 2,
  Day 3; recording uploaded 2026-07-10, 4,609 views. Abstract: Zechner ("read every line") versus
  Lopopolo ("you don't even open the IDE anymore") as a five-stop spectrum, "your stop is per-task
  not per-person", and FOMAT ("Fear of Missing Agent Time") ([recording](https://www.youtube.com/watch?v=ZpK5PWX2YRM)).
- Keiji Kanazawa, "I Let Agents Refactor My Codebase for 3 Weeks. Then I Read the Code.",
  Leadership 2, Day 3, 14:25. Abstract: "Then I actually read what they'd built and couldn't explain
  my own system's contracts. The interfaces weren't wrong. They were plausible. Which is worse." He
  describes "building better specs and evals specifically so I can move back toward L". No
  recording located (abstract only, from `sessions.json`).
- Itamar Friedman (Qodo), "The Last Human Code Review", uploaded 2026-08-20, 3,403 views
  ([recording](https://www.youtube.com/watch?v=s-aixZYJG4c)); description only.
- Ankit Jain (Aviator), "How to Kill the Code Review", uploaded 2026-08-17, 8,045 views.
  Description: more than 30% of PRs merge without review; capture the agent session and turn
  decisions into acceptance criteria ([recording](https://www.youtube.com/watch?v=YgEv7IQzGdM)).
- Sachin Gupta (eBay), "ReviewDebt", uploaded 2026-07-12, 1,982 views; a deterministic PR
  review-burden score ([recording](https://www.youtube.com/watch?v=TJPInBjhE4Q)).
- Matt Dailey (Ref), "Velocity Sickness", Day 4, uploaded 2026-08-09, 8,043 views; the "decision
  layer" as a durable document, "agent bankruptcy" ([recording](https://www.youtube.com/watch?v=Kz4QJmNrVXU)).
- Vincent Koc, "Dark Factory: OpenClaw Ships Faster Than You Can Read the Diff", uploaded
  2026-06-05, 12,593 views ([recording](https://www.youtube.com/watch?v=pmoDeA3RBZY)).
- Zack Proser, "Your Attention Is the Bottleneck", uploaded 2026-06-11, 30,351 views
  ([recording](https://www.youtube.com/watch?v=so9l_MwS2yg)).
- Michal Cichra, "BDD, ADR, PRD, WTF", uploaded 2026-06-03, 29,706 views
  ([recording](https://www.youtube.com/watch?v=504PvfXou5Y)).
- Chris Noring (Microsoft), "From Writing Code to Designing Systems", uploaded 2026-07-11, 22,446
  views ([recording](https://www.youtube.com/watch?v=GdvKNwMcfd0)).
- Aditya Khandelwal (Amazon AGI Lab), "Agents, codebases, and teams", uploaded 2026-08-11
  ([recording](https://www.youtube.com/watch?v=aeTb5BdmTTc)).
- Sanja Grbic (Automattic), "500 people vibe-coded for 30 days" (Radical Speed Month), uploaded
  2026-07-07 ([recording](https://www.youtube.com/watch?v=UcYoMg-8-L8)).
- Thariq Shihipar (Anthropic), "Field Guide to Fable" — see Target 1.

**AI Engineer Europe 2026.** Mario Zechner, "Building pi in a World of Slop", uploaded 2026-04-16,
514,010 views; description calls it "a plea to slow the fuck down", chapter 13:58 "humans still the
bottleneck" ([recording](https://www.youtube.com/watch?v=RjfbvDXpFls)). Ryan Lopopolo (OpenAI),
"Harness Engineering", uploaded 2026-04-17, 230,526 views; the description links OpenAI's
"Harness engineering" post ([recording](https://www.youtube.com/watch?v=am_oeAoUhew),
[post](https://openai.com/index/harness-engineering/)). Volkov's and Kanazawa's World's Fair talks
above are framed as responses to these two.

**NDC.** NDC AI Oslo 2026: Stian Håklev, "What Actually Happens When You Give a Dev Team Claude Code
for a Day", uploaded 2026-06-30 — description mentions a PR walkthrough generator and semantic search
over 7,500 sessions, and names Osmani and Willison ([recording](https://www.youtube.com/watch?v=GqN13Y9k8HE));
Yngve Bakken Nilsen, "Where thinking stops", uploaded 2026-06-30
([recording](https://www.youtube.com/watch?v=ZpTl_uDoSsw)). NDC London: Emma Burstow, "Learning not
leaning", uploaded 2026-02-11 — the Umbraco team's experiments with mandatory Copilot-assisted
sprints ([recording](https://www.youtube.com/watch?v=xWf5eOKx87g)).

**QCon.** QCon London 2026 (March): Sarah Deitke (Duolingo), see Target 2; Phillip Mortimer (Carta),
"Complexity and Creativity in Software Engineering" — "Software complexity is scaling beyond the
limits of human comprehension" (blurb; page shows "No Video Available")
([schedule](https://qconlondon.com/schedule/mar2026)). QCon San Francisco 2026 (16–20 November,
upcoming): Margaret-Anne Storey, "Understanding as a Deliverable: How AI Changes What Healthy
Software Looks Like" — "three connected threats to software health: technical debt, cognitive debt,
and intent debt … practical ideas for measuring, managing, and reducing these forms of debt", in
the Engineering the Developer Experience track hosted by Ankit Jain
([abstract](https://qconsf.com/presentation/nov2026/understanding-deliverable-how-ai-changes-what-healthy-software-looks));
Omer van Kloeten (Forter), "You Can't Read the Code Anymore – Verifying Software in the Age of AI" —
"reviewing code you didn't write is much harder than writing it yourself … change what they review
by having the agent generate and maintain a runnable test for every behavior the service exposes"
([abstract](https://qconsf.com/presentation/nov2026/you-cant-read-code-anymore-verifying-software-age-ai));
Laurie Voss (Arize AI), "The Death of the Code Review" — the interview quotes "coders using LLM
assistance wrote more than 700% more code but released only 30% more actual software" (speaker's
figure, source not given on the page) ([abstract](https://qconsf.com/presentation/nov2026/death-code-review)).

**Others.** Matt Stauffer, "Building Software at the Edge of Your Understanding", Laracon US 2026,
uploaded 2026-08-09 — four guidelines in the description: reach from solid ground, don't stack
unknowns, use AI to build comprehension, own your failure path
([recording](https://www.youtube.com/watch?v=au9bIQsrh8k)). Margaret-Anne Storey: Waterloo
Distinguished Lecture, uploaded 2026-07-04 ([recording](https://www.youtube.com/watch?v=gmCqVgpN-m0));
Aviator HangarDX podcast with Ankit Jain, 2026-05-07 ([recording](https://www.youtube.com/watch?v=tIPbqipc88U)).
Luca Fossen (Waikato), "Comprehension Debt: How to Trust AI Agents", meetup upload 2026-08-03, 62
views ([recording](https://www.youtube.com/watch?v=3NbM9OOKdKE)). Jo Van Eyck, "5 tips to tackle
AI-induced cognitive debt", uploaded 2026-03-23; the description names a "learning-opportunities"
skill ([recording](https://www.youtube.com/watch?v=ov0-aDC5rBQ)). LeadDev 2026: "Guardrails, not
gates: Scaling juniors in the AI era", uploaded 2026-08-12, 705 views, empty description, speaker
not identified ([recording](https://www.youtube.com/watch?v=s0JljMZKruM)); "What to do when there's
too much code to review", uploaded 2026-06-14, 290 views ([recording](https://www.youtube.com/watch?v=0dbMKGS7uWk));
"The Shift's Big Interview #2: Thoughtworks CTO Rachel Laycock doesn't believe in code review",
uploaded 2026-06-10 ([recording](https://www.youtube.com/watch?v=zECLHcSnIoI),
[transcript post](https://leaddeveic.substack.com/p/big-interview-2-thoughtworks-cto)). GOTO 2026:
Scott Hanselman, "The EiC Problem: Junior Devs, AI Agents & the Missing Context Layer" — members-only
video, not viewable ([listing](https://www.youtube.com/watch?v=9-ajpf1wTRQ)). Kent Beck,
"Sustainable Augmented Development", YOW! 2025, uploaded 2026-06-30, 9,918 views — a 2025 talk on
keeping "genies" from leaving a mess, adjacent rather than on comprehension
([recording](https://www.youtube.com/watch?v=sMujMp4h_EY)).

## Target 4: 2026 essays and threads not in Cluster 8

All confirmed absent from the earlier notes' citations. Dates are the posts' own.

- Ganesh Pagade (Rockoder), "Cognitive Debt: When Velocity Exceeds Comprehension", 2026-02-17 —
  "Code has become cheaper to produce than to perceive"
  ([post](https://www.rockoder.com/beyondthecode/cognitive-debt-when-velocity-exceeds-comprehension/),
  [HN 507 points](https://news.ycombinator.com/item?id=47196582)).
- Margaret-Anne Storey, "What I'm Hearing About Cognitive Debt (So Far)", 2026-02-18 — a roundup
  naming Willison, Fowler, Khare, Yegge, Vella, and Würsch; practices heard: rigorous review,
  intent-capturing tests, continuously updated design docs
  ([post](https://margaretstorey.com/blog/2026/02/18/cognitive-debt-revisited/),
  [HN 224 points, 2026-05-05](https://news.ycombinator.com/item?id=48017298)).
- Martin Fowler, Fragments, 2026-04-02 — Storey's three debts, Shaw and Nave's "System 3" /
  cognitive surrender, Ajey Gore on verification
  ([post](https://martinfowler.com/fragments/2026-04-02.html),
  [HN 352 points](https://news.ycombinator.com/item?id=47865661)).
- Martin Trojer, "Cognitive debt is the real tax", 2026-04-12 — diagnosis only, no practices
  proposed ([post](https://martintrojer.github.io/post/2026-04-12-cognitive-debt-is-the-real-tax/)).
- Bryan Cantrill, "The peril of laziness lost", 2026-04-12
  ([post](https://bcantrill.dtrace.org/2026/04/12/the-peril-of-laziness-lost/),
  [HN 480 points](https://news.ycombinator.com/item?id=47743628),
  [Lobsters](https://lobste.rs/s/tmddcs/peril_laziness_lost)).
- Addy Osmani, "Comprehension Debt: The Hidden Cost of AI-Generated Code", republished on O'Reilly
  Radar 2026-04-13 (the addyosmani.com original is in Cluster 8)
  ([Radar](https://www.oreilly.com/radar/comprehension-debt-the-hidden-cost-of-ai-generated-code/)).
- Sean Goedecke, "In defense of not understanding your codebase", 2026-07-11 — "In sufficiently
  large codebases, everyone operates with an incorrect theory of the program"
  ([post](https://www.seangoedecke.com/in-defense-of-not-understanding-your-codebase/),
  [HN 22 points](https://news.ycombinator.com/item?id=48882777),
  [Lobsters](https://lobste.rs/s/elhi7o/defense_not_understanding_your_codebase)).
- antirez, "Control the ideas, not the code", 2026-07-13 — "Nobody should anymore look at this
  code, but only at the ideas the code contains", with stated doubt about juniors
  ([post](https://antirez.com/news/169), [HN 227 points, 189 comments](https://news.ycombinator.com/item?id=48891184),
  [Lobsters](https://lobste.rs/s/5t3wzn/control_ideas_not_code)).
- Amelia Wattenberger, "Code was our medium for thought", 2026-07-14 — "You can change the code
  faster than you can think about what to change … You've lost touch with your mental map of the
  codebase" ([post](https://wattenberger.com/thoughts/code-is-a-medium-for-thought/),
  [HN 7 points](https://news.ycombinator.com/item?id=48917501)).
- coles.codes, "Reviewing code you didn't write", 2026-07-22 — "Reviewing is how I stay a
  contributor to all that code … Skip the review and I'm not really involved in that code any more,
  just adjacent to it" ([post](https://coles.codes/posts/reviewing-code-you-didnt-write),
  [HN 16 points](https://news.ycombinator.com/item?id=49007149)).
- Cat Hicks, "We need more than a metaphor: here are testable diagnostics for comprehension debt",
  2026-07-28 — proposes an "Overproduction Pressure" measure; cites Sonar's survey figures (96%
  distrust, 48% verify) ([post](https://www.fightforthehuman.com/we-need-more-than-a-metaphor-here-are-testable-diagnostics-for-comprehension-debt/),
  [Lobsters](https://lobste.rs/s/l49j1h/we_need_more_than_metaphor_here_are),
  [HN 2 points](https://news.ycombinator.com/item?id=49133287)).
- Ankur Sethi, "Prevent cognitive debt by manually retyping LLM-generated code", 2026-08-02 —
  instructs the assistant to "show me every proposed edit in the chat so I can type it in manually";
  estimates "probably only 2x faster" than unassisted
  ([post](https://ankursethi.com/blog/prevent-cognitive-debt-by-manually-retyping-llm-generated-code/),
  [HN 545 points, 443 comments](https://news.ycombinator.com/item?id=49153374),
  [Lobsters](https://lobste.rs/s/ui2vor/prevent_cognitive_debt_by_manually)).
- typesanitizer, "Reviewing code is a skill", 2026-08-11 (author not named on the page)
  ([post](https://typesanitizer.com/blog/code-review.html), [HN](https://news.ycombinator.com/item?id=49254311)).
- Geoffrey Litt's "Understanding is the new bottleneck" reached HN on 2026-08-13 with 445 points;
  the thread URL is not in the earlier notes ([HN](https://news.ycombinator.com/item?id=49290299)).
- Nolan Lawson, "You can just choose how many bugs you want now", 2026-08-16 — "the finding of the
  bugs has become nearly free"; names Litt's explain-diff skill as part of his review routine
  ([post](https://nolanlawson.com/2026/08/16/you-can-just-choose-how-many-bugs-you-want-now/),
  [HN 4 points](https://news.ycombinator.com/item?id=49322664)).
- Tech Workers Coalition (techwerkers.nl), "A Manifesto for Responsible Agentic Coding", dated
  2026-08-01 on the page, on Lobsters 2026-08-25 — "Every line of production code must have been
  read and understood by a human. Engineers must be able to explain the code, debug it and modify it
  – even when Claude is down" ([manifesto](https://www.techwerkers.nl/en/posts/manifesto-responsible-agentic-coding/),
  [Lobsters](https://lobste.rs/s/voyeoa)).
- Threads without an article: Ask HN "Is understanding code becoming 'optional'?" (2026-01-30,
  [HN](https://news.ycombinator.com/item?id=46831133)); Ask HN "How do you capture WHY engineering
  decisions were made" (2026-03-13, [HN](https://news.ycombinator.com/item?id=47368874)); "Tell HN:
  Man, AI is killing my brain" (2026-08-27, 54 points, [HN](https://news.ycombinator.com/item?id=49468252));
  "I'm going back to coding by hand" (2026-09-09, 62 points, [HN](https://news.ycombinator.com/item?id=49622554));
  Lobsters "Surviving Code Reviews in the era of AI" (2026-09-04, 97 comments,
  [Lobsters](https://lobste.rs/s/7tpc5q/surviving_code_reviews_era_ai)). Not fetched for thesis:
  shiftmag's "CTOs Agree: Cognitive Debt Is the New Technical Debt" (2026-06-21, a roundup,
  [HN](https://news.ycombinator.com/item?id=48617323)); Show HN "Jacquard", a language "for
  AI-written, human-reviewed code" (2026-07-13, [HN](https://news.ycombinator.com/item?id=48894630)).

## Target 5: Provenance traces for readers and human attestation

**Agent Trace has no successor.** On 2026-09-13 `github.com/cursor/agent-trace` still returns 404
and agent-trace.dev still reads "Version 0.1.0 / Status RFC / Date January 2026" while linking the
dead repository ([site](https://agent-trace.dev/)). A GitHub name search found no renamed or
re-homed specification. The one live implementation is third-party:

**agent-trace-cli** — CLI · ujjalsharma100 · implements the Agent Trace spec as a deterministic
post-commit ledger in git notes (`refs/notes/agent-trace`), `agent-trace blame <file>` with a binary
AI / not-AI attribution, and a browser **file viewer** combining git blame with agent-trace blame ·
*git notes plus a local web view* · post-commit · ★10; created 2026-02-13; pushed 2026-07-25; site
cli.traceshub.com · [repo](https://github.com/ujjalsharma100/agent-trace-cli). This is the only
Agent-Trace-consuming reader UI found; none of the RFC's backers ship one.

**Human attestation.** One explicit design and one early implementation:

**VOUCH (Validated Ownership and Understanding of Code by Humans)** — essay and protocol · Manuel
Ibar · "Nobody Owns This Code" (repo, ★0, 2026-03-14) argues for *endorsement* as a unit distinct
from authorship, on two axes (provenance; comprehension: unknown / reviewed / endorsed), with
revocation on structural change, a `.vouchignore`, a heatmap, and thresholds (for example under 20%
endorsed in Tier-1 paths); it concedes "Endorsement is self-reported. There is no comprehension
quiz." Protocol v0.1 (`VOUCH-CLI.md`) defines an Endorsement Record `{version, commit, file_path,
endorser, timestamp, lines{endorsed, reviewed}, note}` stored in git notes under
`refs/notes/vouch-state`, and `vouch endorse / status / sync` · *git notes* · at review time ·
[essay repo](https://github.com/manuelibar/nobody-owns-this-code). **vouch** — Go/Cobra CLI ·
same author · `vouch init`, `vouch record endorsement --scope file#L44-L63`,
`vouch report --format porcelain`; bundled reviewer, teacher, and knowledge-transfer skills for
Codex · ★0; created and last pushed 2026-06-09; no license; no releases or tags ·
[repo](https://github.com/manuelibar/vouch).

**Repository-level attestation, not per-reader.** **AI Attestation** (Korext) — a CC0 YAML schema
(`.ai-attestation.yaml`) plus npm CLI (`init`, `scan`, `report`, `badge`, `hook install`) that
detects 19 AI tools from co-author trailers and commit patterns and asks, as one of its three
questions, "Has the AI generated code been reviewed or scanned?" — answered by the repository
owner, not per change · Apache-2.0 code; ★27; created 2026-04-16; pushed 2026-05-30 ·
[repo](https://github.com/Korext/ai-attestation). **Exceeds Ink** (commercial; vendor blog
2026-03-17) records "tool, model, session, interaction mode, and timestamp per line" in git notes
and proposes policies such as "requiring additional review on commits where agent mode produced more
than a specified percentage of the diff" — attribution, with review as a downstream policy
([vendor post](https://blog.exceeds.ai/analyze-git-commits-ai-code/)).

**Session transcripts as the trace a reader sees.**

- **ctx** — local search over coding-agent sessions · ctxrs · the paid "ctx pro" is described as
  "git blame, but for agent sessions", surfacing the transcript behind a line, file, commit, or PR ·
  Apache-2.0; ★1,106; created 2026-02-23; pushed 2026-09-13 · [repo](https://github.com/ctxrs/ctx),
  [Show HN 65 points](https://news.ycombinator.com/item?id=48763462).
- **agentlog** — session interchange spec 0.2.0 with converters for Claude Code, Codex, Cursor, and
  OpenCode · braintied · Apache-2.0; ★0; created 2026-03-30; pushed 2026-08-21 ·
  [repo](https://github.com/braintied/agentlog).
- **Haystack** (Show HN 2026-05-18, 45 points) triaged PRs into "safe to merge / needs fixes /
  needs human review" by reading "the diffs, the codebase, and the coding-agent conversation that
  produced the PR", showing the reviewer "the goal behind the PR, what design decisions the author
  made (informed by their coding-agent conversation), and how much the author did to verify" — a
  rendering of the agent conversation for the reader. The domain now redirects to haystack.sh, which
  describes a production-traffic replay QA product with no mention of PR triage
  ([Show HN](https://news.ycombinator.com/item?id=48182856), [current site](https://haystack.sh/)).
- **Stage** — PR reading app that splits changes into "chapters" · Stage Inc. · Team plan $30 per
  user per month; "Nothing is stored beyond the lifetime of a chapter generation"; comment threads
  only, no attestation state documented · [site](https://stagereview.app/),
  [Show HN 130 points](https://news.ycombinator.com/item?id=47796818); **stage-cli** reads AI
  changes locally, MIT, ★266, created 2026-04-26, pushed 2026-09-07
  ([repo](https://github.com/ReviewStage/stage-cli), [Show HN 46 points](https://news.ycombinator.com/item?id=48050732)).
- **revdiff** — TUI diff reviewer whose inline annotations are written to stdout for an agent to
  consume · umputun · MIT; ★858; created 2026-04-01; pushed 2026-09-10 ·
  [repo](https://github.com/umputun/revdiff).
- **beanz** and **plum** (Target 1) both read the session transcript; beanz scores it, plum turns
  it into an explorable bundle and a quiz.

**Studies.** No study was found that records a human's read of a specific generated artifact as an
attestation. The nearest is physiological: Burelli, Calefato, Grassi, Hristova, Novielli, Romano,
and Tell, "Using Biometrics to Understand AI-Assisted Coding Performance and its Perception" (arXiv
2606.20598, 2026-05-19; Stage 2 registered report under review at EMSE) — EEG, eye tracking,
electrodermal activity, and heart-rate variability in a two-site crossover; under AI assistance
"the EEG θ/α ratio was lower during the first task and the gaze blink rate was higher during the
second, both consistent with reduced cognitive engagement" ([abstract](https://arxiv.org/abs/2606.20598)).
The eye-tracking review study arXiv 2606.26505 is already in the earlier notes.

## Target 6: solve.it-style defaults outside notebooks

The friction note already tabulates approval modes for Claude Code, Codex CLI, Gemini CLI, Aider,
Amp, OpenCode, Cursor, Copilot, Junie, and Zed's tool permissions; this section records only what
bears on the three solve.it defaults — completions only on an explicit trigger, no automatic
follow-up after an agent step, and AI output inert until promoted — and what changed in 2026.

**Manual-trigger-only completions.**

- **copilot.lua (Neovim)** ships it as the default: `suggestion.auto_trigger = false` ("use the
  next, prev or accept keymap to trigger") and `nes.auto_trigger = false`, with a
  `toggle_auto_trigger` command · zbirenbaum; ★4,100; pushed 2026-09-12 ·
  [README](https://github.com/zbirenbaum/copilot.lua). It is a plugin default, not an editor default.
- **Zed edit prediction** has two modes, `eager` (default) and `subtle`, in which predictions "only
  appear inline when holding a modifier key (alt by default)"; `show_edit_predictions: false` hides
  them while the manual `editor::ShowEditPrediction` action still works
  ([docs](https://zed.dev/docs/ai/edit-prediction)). Opt-in, not default.
- **Visual Studio** added a manual-request-only option on 2025-08-21 (Simona Liao): "You can now
  disable automatic completions popping on and trigger them manually with keyboard shortcuts" (`Alt`
  + `,` / `Alt` + `.`), under Tools > Options > Text Editor > Code Completions in VS 2026; "The
  default experience is Automatically generate code completions in the Editor"
  ([post](https://devblogs.microsoft.com/visualstudio/better-control-over-your-copilot-code-suggestions/)).
- **VS Code Copilot**: the inline-suggestions page documents per-language `github.copilot.enable`,
  Snooze, next-edit-suggestion settings, and `editor.inlineSuggest.minShowDelay` (default 0); no
  manual-only mode ([docs](https://code.visualstudio.com/docs/copilot/ai-powered-suggestions)).
- **Cursor Tab**: Snooze, global disable, and per-extension disable; no explicit-keypress-only mode
  documented ([docs](https://cursor.com/docs/tab/overview)).
- **JetBrains AI Assistant**: automatic by default; manual invocation with Alt+Shift+\ ; no
  manual-only mode documented ([docs](https://www.jetbrains.com/help/ai-assistant/code-completion.html)).
- **Helix** has no first-party AI; the language servers that supply it are either archived
  (helix-gpt, ★696, archived, last push 2026-01-18: completions on trigger characters `{ ( space`
  by default with `ctrl+x` for manual, [README](https://github.com/leona/helix-gpt)), dormant
  (lsp-ai, ★3,207, last push 2025-01-07, [repo](https://github.com/SilasMarvin/lsp-ai)), or personal
  and auto-by-default (Hexai, 2026-07-09: "fires after a short idle debounce (`completion_debounce_ms`,
  800 ms)" on trigger characters, with `/disable` to pause, [post](https://foo.zone/gemfeed/2026-07-09-unveiling-hexai.html)).

**No automatic follow-up after an agent step.** Two 2026 Claude Code changes move in this
direction without reaching it: 2.1.200 (npm 2026-07-03) "Changed `AskUserQuestion` dialogs to no
longer auto-continue by default; opt into an idle timeout via `/config`" and "Changed the
'default' permission mode to 'Manual'"; 2.1.203 (2026-07-07) added a grey ⏸ badge for manual
mode; 2.1.218 (2026-07-22) made `/deep-research` start only when invoked manually
([changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)). These stop the
agent at a question or a permission, not after an arbitrary edit or command. OpenCode's permission
docs state "Most permissions default to `allow`" with only `doom_loop` and `external_directory`
defaulting to `ask` ([docs](https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/permissions.mdx)).
Junie's documentation says that "By default, Junie requests your permission to run suggested bash
commands, introduce changes, perform file operations, or use external tools", with "Brave Mode"
and an Action Allowlist as the ways to relax that ([docs](https://www.jetbrains.com/help/ai-assistant/junie-agent.html); the Junie plugin docs say the same of "Most terminal commands, code execution, and execution of MCP tools", [plugin docs](https://junie.jetbrains.com/docs/junie-ide-plugin.html)).
No tool documents suppressing the *next* agent action after a completed step; the 2026 changes are
all about the step before.

**Inert until promoted.** Nothing new. Ask/Chat modes remain the nearest; the `okay` skills and
Ankur Sethi's retyping practice (Targets 1 and 4) implement the inversion by convention, not by
product default. No 2026 announcement from any of the listed vendors describes a solve.it-style
default; the one search aimed at such announcements returned only the Visual Studio option above.

## Corrections proposed

None of the existing notes is edited here. Each item names the file, the exact sentence, and the
evidence.

- `landscape-sweep.md`, Dead ends: "Conference talks on the theme other than Litt's: none located
  by title." — Superseded. Target 3 lists talks located by title with recordings or official
  abstracts, among them Volkov's "The Z/L Continuum: Should AI Engineers Still Read Code?"
  ([recording](https://www.youtube.com/watch?v=ZpK5PWX2YRM)), Kanazawa's "I Let Agents Refactor My
  Codebase for 3 Weeks. Then I Read the Code." ([programme](https://ai.engineer/worldsfair/schedule)),
  Stauffer's "Building Software at the Edge of Your Understanding" ([recording](https://www.youtube.com/watch?v=au9bIQsrh8k)),
  Storey's forthcoming "Understanding as a Deliverable" ([abstract](https://qconsf.com/presentation/nov2026/understanding-deliverable-how-ai-changes-what-healthy-software-looks)),
  and van Kloeten's "You Can't Read the Code Anymore" ([abstract](https://qconsf.com/presentation/nov2026/you-cant-read-code-anymore-verifying-software-age-ai)).
- `landscape-sweep.md`, Dead ends: "Company engineering blogs describing internal
  comprehension-check rituals: none found; the practice literature is individual essays and OSS
  policies." — Still true for *rituals*, but the qualifier should note that PostHog's blog names
  "Does the author understand the change?" as a human review question
  ([post](https://posthog.com/blog/10k-prs-a-month)) and its handbook distinguishes agent-authored
  PRs, which "always require a human review" ([handbook](https://posthog.com/handbook/engineering/how-we-review)).
- `track-hand-off-checks.md`, Dead ends: "Searches that therefore could not be run: … other
  PR-quiz actions or apps beyond the three known." and "a GitHub repository search for 'pr quiz',
  'quiz pull request', 'explain-diff', and 'teach-back code' surfaced nothing new beyond generic
  study skills." — Superseded by Target 1: diffquiz ([repo](https://github.com/TYLDA-Solutions/diffquiz)),
  AIditor ([listing](https://marketplace.visualstudio.com/items?itemName=asabry.aiditor-vscode)),
  PrincessSats/cognitive-debt ([repo](https://github.com/PrincessSats/cognitive-debt)), plum
  ([repo](https://github.com/k3-mt/plum)), and the skills listed there. Several were created after
  the search terms would have found them (diffquiz 2026-09-02; AIditor updated 2026-09-07), so the
  sentence was accurate when written and is now stale.
- `track-in-loop-friction.md`, Inversion outside notebooks: "No editor was found whose default is
  manual-trigger-only completions." and Dead ends: "No editor found with manual-trigger-only
  completions as default; only Copilot's disable/snooze and GitHub's learner guidance." — Needs
  qualification rather than reversal: copilot.lua, the most-used Neovim Copilot plugin, defaults to
  `suggestion.auto_trigger = false` ([README](https://github.com/zbirenbaum/copilot.lua)); Zed's
  `subtle` mode and Visual Studio's manual-request option exist but are opt-in
  ([Zed docs](https://zed.dev/docs/ai/edit-prediction),
  [Visual Studio blog](https://devblogs.microsoft.com/visualstudio/better-control-over-your-copilot-code-suggestions/)).
  "No editor" remains true; "no editor or plugin" would not.
- `track-in-loop-friction.md`, Inversion outside notebooks: "No tool documentation found describes
  suppressing the agent's next step after a command or edit" — Still true, but the note should record
  the nearest 2026 change: Claude Code 2.1.200's `AskUserQuestion` dialogs "no longer auto-continue
  by default" ([changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)).
- `track-rationale-as-artifact.md`, The Agent Trace specification: "No shipped Agent-Trace-consuming
  UI was found in any backer's docs." — True of backers; a third-party consumer with a file viewer
  exists, agent-trace-cli ([repo](https://github.com/ujjalsharma100/agent-trace-cli)).

## Dead ends

- Amp: `ampcode.com/manual/permissions` and `/manual/tools` redirect to a sign-in wall; the public
  `/manual` landing page has no permission text. Nothing new on Amp could be verified.
- Kanazawa's World's Fair talk: no recording found on the AI Engineer channel or by search; abstract
  only.
- YOW!: the `@YOW_Conf` handle returns 404; YOW! recordings live on the GOTO Conferences channel,
  whose latest 300 uploads contain no 2026 YOW! talk on the theme.
- Hanselman's GOTO 2026 talk is a members-only video; no abstract text retrievable.
- The WHY plugin's companion Medium article returns HTTP 403; the repository README was used instead.
- geminicli.com documentation URLs return 404; the raw GitHub `docs/cli/*.md` files were used
  (already reflected in the friction note's coverage).
- The O'Reilly Radar page returns "Access Denied" to direct fetches; a rendered fetch identified it
  as Osmani's republished essay.
- haystackeditor.com now redirects to haystack.sh, a different product; the PR-triage description
  survives only in the Show HN text.
- AIditor lists no repository, so its source, licence file, and storage could not be read.
- The LeadDev "Guardrails, not gates" upload has an empty description; speaker not identified.
- QCon presentation pages do not carry session dates; conference dates come from the schedule
  pages (London March 2026; San Francisco 16–20 November 2026).
- Agent Trace successor: none by GitHub name search ("agent-trace", "agent trace spec"); the
  agent-trace.dev page is unchanged since the rationale note.
- Not searched in this pass: PyCon US, JSConf, RustConf, and Local-first 2026 programmes; SpecStory
  and Cursor Blame for 2026 changes; a study that logs which lines of a generated diff a reviewer
  actually viewed (the GitHub "viewed" checkbox as data) — no such study surfaced in the one search
  aimed at it.
- Lobsters: the site search returns story titles without ids; ids were recovered by a second query
  per title, so a few threads (typesanitizer, Wattenberger) have HN links only.
- WebSearch calls used: 19 of the 90 allotted; the remainder of the discovery ran on the GitHub API,
  HN Algolia, Lobsters, `yt-dlp`, programme JSON, and direct page fetches.

## References

Tools (Target 1): [diffquiz](https://github.com/TYLDA-Solutions/diffquiz) ·
[AIditor](https://marketplace.visualstudio.com/items?itemName=asabry.aiditor-vscode) ·
[PrincessSats/cognitive-debt](https://github.com/PrincessSats/cognitive-debt) ·
[runsagents/quiz-me](https://github.com/runsagents/quiz-me) ·
[change-quiz](https://github.com/Neeeophytee/finding-unknowns-skills/blob/main/skills/change-quiz/SKILL.md) ·
[emanzurv/quiz-me-skill](https://github.com/emanzurv/quiz-me-skill) ·
[rebeloper/okay](https://github.com/rebeloper/okay) · [why-plugin](https://github.com/jobrien874/why-plugin) ·
[plum](https://github.com/k3-mt/plum) · [opencode-sit](https://github.com/aemonge/opencode-sit) ·
[beanz](https://github.com/daveepope/beanz) · [thinking-cap](https://github.com/shreyas-makes/thinking-cap) ·
[llmwiki](https://github.com/suwonleee/llmwiki) · [accountable-review](https://github.com/wyeworks/accountable-review) ·
[cognitive-debt-action](https://github.com/phoenix-assistant/cognitive-debt-action) ·
[Shihipar, field guide](https://claude.com/blog/a-field-guide-to-claude-fable-finding-your-unknowns) ·
[Shihipar, examples](https://thariqs.github.io/html-effectiveness/unknowns/) ·
[Shihipar, talk](https://www.youtube.com/watch?v=9fubhllmsBU).

Companies (Target 2): [PostHog AI_POLICY.md](https://github.com/PostHog/posthog/blob/master/AI_POLICY.md) ·
[PostHog, How we review](https://posthog.com/handbook/engineering/how-we-review) ·
[PostHog, 10,000 PRs a month](https://posthog.com/blog/10k-prs-a-month) ·
[Duolingo at QCon London 2026](https://qconlondon.com/presentation/mar2026/teaching-engineers-trusting-ai-how-education-enabled-autonomous-code-review) ·
[Ona, auto-approving low-risk PRs](https://ona.com/stories/auto-approving-low-risk-prs) ·
[GitHub Blog, reviewing agent PRs](https://github.blog/ai-and-ml/generative-ai/agent-pull-requests-are-everywhere-heres-how-to-review-them/) ·
[arXiv 2607.07980](https://arxiv.org/abs/2607.07980) · [arXiv 2606.14796](https://arxiv.org/abs/2606.14796) ·
[Claude Code changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md).

Talks (Target 3): [AIE World's Fair schedule](https://ai.engineer/worldsfair/schedule) ·
[Volkov](https://www.youtube.com/watch?v=ZpK5PWX2YRM) · [Friedman](https://www.youtube.com/watch?v=s-aixZYJG4c) ·
[Jain](https://www.youtube.com/watch?v=YgEv7IQzGdM) · [Gupta](https://www.youtube.com/watch?v=TJPInBjhE4Q) ·
[Dailey](https://www.youtube.com/watch?v=Kz4QJmNrVXU) · [Koc](https://www.youtube.com/watch?v=pmoDeA3RBZY) ·
[Proser](https://www.youtube.com/watch?v=so9l_MwS2yg) · [Cichra](https://www.youtube.com/watch?v=504PvfXou5Y) ·
[Noring](https://www.youtube.com/watch?v=GdvKNwMcfd0) · [Khandelwal](https://www.youtube.com/watch?v=aeTb5BdmTTc) ·
[Grbic](https://www.youtube.com/watch?v=UcYoMg-8-L8) · [Zechner](https://www.youtube.com/watch?v=RjfbvDXpFls) ·
[Lopopolo](https://www.youtube.com/watch?v=am_oeAoUhew) · [OpenAI, Harness engineering](https://openai.com/index/harness-engineering/) ·
[Håklev](https://www.youtube.com/watch?v=GqN13Y9k8HE) · [Bakken Nilsen](https://www.youtube.com/watch?v=ZpTl_uDoSsw) ·
[Burstow](https://www.youtube.com/watch?v=xWf5eOKx87g) · [QCon London 2026 schedule](https://qconlondon.com/schedule/mar2026) ·
[Storey, QCon SF](https://qconsf.com/presentation/nov2026/understanding-deliverable-how-ai-changes-what-healthy-software-looks) ·
[van Kloeten, QCon SF](https://qconsf.com/presentation/nov2026/you-cant-read-code-anymore-verifying-software-age-ai) ·
[Voss, QCon SF](https://qconsf.com/presentation/nov2026/death-code-review) ·
[Stauffer](https://www.youtube.com/watch?v=au9bIQsrh8k) · [Storey, Waterloo](https://www.youtube.com/watch?v=gmCqVgpN-m0) ·
[Storey, HangarDX](https://www.youtube.com/watch?v=tIPbqipc88U) · [Fossen](https://www.youtube.com/watch?v=3NbM9OOKdKE) ·
[Van Eyck](https://www.youtube.com/watch?v=ov0-aDC5rBQ) · [LeadDev, Guardrails not gates](https://www.youtube.com/watch?v=s0JljMZKruM) ·
[LeadDev, too much code to review](https://www.youtube.com/watch?v=0dbMKGS7uWk) ·
[LeadDev, Laycock interview](https://www.youtube.com/watch?v=zECLHcSnIoI) ·
[Hanselman (members-only)](https://www.youtube.com/watch?v=9-ajpf1wTRQ) · [Beck, YOW! 2025](https://www.youtube.com/watch?v=sMujMp4h_EY).

Essays (Target 4): [Pagade](https://www.rockoder.com/beyondthecode/cognitive-debt-when-velocity-exceeds-comprehension/) ·
[Storey, revisited](https://margaretstorey.com/blog/2026/02/18/cognitive-debt-revisited/) ·
[Fowler, fragments](https://martinfowler.com/fragments/2026-04-02.html) ·
[Trojer](https://martintrojer.github.io/post/2026-04-12-cognitive-debt-is-the-real-tax/) ·
[Cantrill](https://bcantrill.dtrace.org/2026/04/12/the-peril-of-laziness-lost/) ·
[Osmani on Radar](https://www.oreilly.com/radar/comprehension-debt-the-hidden-cost-of-ai-generated-code/) ·
[Goedecke](https://www.seangoedecke.com/in-defense-of-not-understanding-your-codebase/) ·
[antirez](https://antirez.com/news/169) · [Wattenberger](https://wattenberger.com/thoughts/code-is-a-medium-for-thought/) ·
[coles.codes](https://coles.codes/posts/reviewing-code-you-didnt-write) ·
[Hicks](https://www.fightforthehuman.com/we-need-more-than-a-metaphor-here-are-testable-diagnostics-for-comprehension-debt/) ·
[Sethi](https://ankursethi.com/blog/prevent-cognitive-debt-by-manually-retyping-llm-generated-code/) ·
[typesanitizer](https://typesanitizer.com/blog/code-review.html) · [Litt on HN](https://news.ycombinator.com/item?id=49290299) ·
[Lawson](https://nolanlawson.com/2026/08/16/you-can-just-choose-how-many-bugs-you-want-now/) ·
[Tech Workers Coalition manifesto](https://www.techwerkers.nl/en/posts/manifesto-responsible-agentic-coding/).

Provenance and attestation (Target 5): [agent-trace.dev](https://agent-trace.dev/) ·
[agent-trace-cli](https://github.com/ujjalsharma100/agent-trace-cli) ·
[Nobody Owns This Code (VOUCH)](https://github.com/manuelibar/nobody-owns-this-code) ·
[vouch](https://github.com/manuelibar/vouch) · [AI Attestation](https://github.com/Korext/ai-attestation) ·
[Exceeds Ink post](https://blog.exceeds.ai/analyze-git-commits-ai-code/) · [ctx](https://github.com/ctxrs/ctx) ·
[agentlog](https://github.com/braintied/agentlog) · [Haystack Show HN](https://news.ycombinator.com/item?id=48182856) ·
[Stage](https://stagereview.app/) · [stage-cli](https://github.com/ReviewStage/stage-cli) ·
[revdiff](https://github.com/umputun/revdiff) · [arXiv 2606.20598](https://arxiv.org/abs/2606.20598).

Defaults (Target 6): [copilot.lua](https://github.com/zbirenbaum/copilot.lua) ·
[Zed edit prediction](https://zed.dev/docs/ai/edit-prediction) ·
[Visual Studio blog](https://devblogs.microsoft.com/visualstudio/better-control-over-your-copilot-code-suggestions/) ·
[VS Code inline suggestions](https://code.visualstudio.com/docs/copilot/ai-powered-suggestions) ·
[Cursor Tab](https://cursor.com/docs/tab/overview) · [JetBrains AI Assistant completion](https://www.jetbrains.com/help/ai-assistant/code-completion.html) ·
[helix-gpt](https://github.com/leona/helix-gpt) · [lsp-ai](https://github.com/SilasMarvin/lsp-ai) ·
[Hexai](https://foo.zone/gemfeed/2026-07-09-unveiling-hexai.html) ·
[OpenCode permissions](https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/permissions.mdx) ·
[Junie in AI Assistant docs](https://www.jetbrains.com/help/ai-assistant/junie-agent.html) · [Junie IDE plugin docs](https://junie.jetbrains.com/docs/junie-ide-plugin.html) ·
[Claude Code changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md).
