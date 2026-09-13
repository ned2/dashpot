---
status: research
date: 2026-09-13
---

# Cognitive-debt landscape sweep

A broad, shallow map of proposals, prototypes, practices, and shipping tools that engage with
building, maintaining, testing, or protecting a developer's understanding of a codebase while
coding agents do more of the authoring. Sibling notes cover Geoffrey Litt's "Understanding is
the New Bottleneck" talk and the academic evidence; this note only points at those where a
tool or practice is the item. Each entry is characterised briefly and cited to a primary
source (repo, docs, announcement, or original essay). No ranking and no fit-for-Dashpot
judgement; clusters are emergent. Status is as observed on 2026-09-13.

Entry format: **Name** — type · who · what · *mechanism* · when it runs · status · evidence.

## Emergent clusters

Nine clusters emerged. The seed areas mapped onto six of them; three (provenance and intent
capture, merge-policy gates, and review-first diff tooling) were not in the seeds and are
called out under "Areas the seeds missed".

1. **Retrieval practice and Socratic tutoring inside the agent loop** (11 items) — quizzes,
   spaced repetition, teach-back and "you write this part" modes bolted onto Claude Code,
   Codex, Cursor and MCP. Mostly community skills from 2026, one first-party output style,
   one learning-science-authored skill with real adoption. Per-module mastery tracking exists
   only as a per-user learning journal.
2. **Merge-time understanding gates** (10 items) — PR quizzes that block merge, open-source
   AI policies that require the submitter to explain every line, and essays reframing review
   around the author's ability to explain. The seed's "quiz the author bot" exists in three
   independent implementations.
3. **Diff-comprehension aids** (8 items) — walkthroughs, sequence diagrams, literate diffs and
   review-first viewers that restructure a changeset for a reader rather than a merger.
4. **Explorable maps and explanation on demand** (15 items) — the largest and most commercial
   cluster: repo wikis, task-specific codemaps, guided tours, repo maps, codebase Q&A, and the
   built-in "explain" / "ask" modes of every major assistant. Several 2023-era entrants have
   been acquired, sunset, or refocused on enterprise.
5. **Agent-maintained living artifacts** (8 items) — docs, wikis, steering files and ADRs that
   an agent regenerates or is instructed to keep current. Understanding is a side effect of
   the artifact existing, not something the tool checks.
6. **Provenance and intent capture** (7 items, seeds missed) — attaching the agent's
   conversation, reasoning and rejected alternatives to commits and lines so that "why" can be
   recovered later. Includes an open spec with vendor backing.
7. **Friction and metacognitive checkpoints** (7 items) — modes that pause execution, hand a
   piece of the work back to the human, or interpose a review step between agent and git;
   plus AI-free-day practices from community discourse.
8. **Discourse and framing** (13 items) — the essays, radar entries, and threads that named the
   problem (cognitive, comprehension, knowledge, intent debt) and the rituals they propose.
9. **Measurement and detection** (6 items) — mostly position papers and perception surveys;
   no shipping tool measures comprehension directly.

Seed areas that turned out thin: Anki-style spaced repetition *on a codebase* (only generic
flashcard skills and one codebase tutor with SRS scheduling); Parsons-problem generation from a
real codebase (education-only); comprehension telemetry (none).

## Cluster 1 — Retrieval practice and Socratic tutoring in the agent loop

- **learn-codebase** — prototype skill · ktaletsk · <https://github.com/ktaletsk/learn-codebase>
  · "The anti-vibe-coding skill": a Socratic tutor that teaches a codebase by asking the
  learner to predict before revealing, with active-recall quizzes and a persistent learning
  journal rating each topic Confused / Learning / Confident. · *quiz, spaced repetition,
  mastery journal* · on demand, session-spanning · active (55 stars, 14 commits) · no usage
  evidence.
- **Learning Opportunities** — shipping skill · Dr Cat Hicks and Dr Michael Mullarkey ·
  <https://github.com/DrCatHicks/learning-opportunities> · Claude Code / Codex skill that,
  after significant architectural work, offers an optional 10–15 minute exercise built on
  prediction–observation–reflection, generation before viewing, retrieval practice and
  teach-back, using semi-worked examples from the user's own project; suppresses itself after
  one decline. · *retrieval practice, generation, spaced repetition* · triggered after new
  files, schema changes, refactors · active (2.4k stars, CC-BY-4.0) · explicitly grounded in
  learning-science literature (generation effect, fluency illusion, spacing); no outcome data.
  (Clarified 2026-09-13: "spaced repetition" here means the skill cites the spacing effect and
  runs a "retrieval check-in" at the start of a returning session; it schedules no reviews and
  keeps no journal or mastery record — the per-user journal above is learn-codebase's only, as
  confirmed from both repositories in
  [track-durable-model.md](track-durable-model.md#mastery-and-coverage-models).)
- **socratic-skills (quiz-me / guide-me)** — prototype skill · Rod BV ·
  <https://github.com/rodbv/socratic-skills> · `quiz-me` reads a diff, spec or plan and asks
  questions one at a time with Socratic follow-ups; `guide-me` walks the user through
  implementing a spec themselves and checks the diff. · *quiz on diffs, guided
  implementation* · before commit, on demand · active but small (16 stars).
- **Covate (MCP Creator Growth)** — prototype MCP server · SunflowersLwtech ·
  <https://github.com/SunflowersLwtech/covate> · `learning_session` tool opens a quiz card in
  a local web UI and blocks the agent until the developer completes the card or a timeout
  (default 600 s) elapses, at any score; the score is saved locally and deliberately not
  returned to the agent, and the questions are supplied by the calling agent (the server's own
  fallback is a generic template per change type) (corrected 2026-09-13 from "blocks … until the
  developer passes it", per `src/covate/server.py`; see
  [track-hand-off-checks.md](track-hand-off-checks.md#dead-ends)). · *quiz as blocking
  checkpoint inside the agent loop* · during agent run, on "quiz me" · early-stage
  (tool-definition quality rated C on Glama).
- **Claude Code Learning and Explanatory output styles** — shipping feature · Anthropic ·
  <https://code.claude.com/docs/en/output-styles> · Explanatory interleaves "Insights" about
  implementation choices and codebase patterns; Learning additionally leaves `TODO(human)`
  markers for the user to implement small strategic pieces and gives feedback. · *explanation
  interleaved with work; hand-back of authorship* · every turn while selected · active, built
  in (the `/output-style` command was removed in v2.1.91; set via `/config`) · no published
  outcome data.
- **claude-tutor** — prototype plugin · kirilxd · <https://github.com/kirilxd/claude-tutor> ·
  Generic learning plans with adaptive quizzes and SM-2 spaced repetition inside Claude Code;
  topic-agnostic, not codebase-aware. · *quiz, SRS* · on demand · active · included as the
  nearest shipping "Anki inside the harness".
- **Study-skills / Anki-generator skills** — prototype skills · jacquardlabs and others ·
  <https://github.com/jacquardlabs/study-skills> · Flashcard and quiz generators for Claude
  Code that can take code as input but do not model a codebase. · *flashcards* · on demand ·
  active · no codebase-specific evidence.
- **Embedded spaced-repetition quizzes in explainers** — prototype practice · Geoffrey Litt ·
  <https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck> · Explainer
  documents end with interactive quiz questions, after Quantum Country
  (<https://quantum.country>). · *quiz embedded in living doc* · on reading · prototype.
- **Playable comprehension quiz on the essay itself** — practice · Eric J. Ma ·
  <https://dspn.substack.com/p/understanding-is-the-new-bottleneck> · Post on the same theme
  ships its own quiz so the reader tests rather than witnesses understanding. · *quiz* ·
  on reading · one-off.
- **Inquisitive code editor** — research prototype (pre-agent precedent) · Austin Henley et
  al., ICSE-SEET 2021 · <https://arxiv.org/abs/2102.06098> · Editor periodically asks the
  programmer questions about their program's behaviour, generates explanations from actual
  behaviour, and inserts tests to prevent recurrence. · *periodic quiz on own code* ·
  continuous · Atom plugins, informal surveys only · cited on HN as prior art for pr-quiz.
- **Code-generation-based grading of Explain-in-Plain-English** — research method · Smith and
  Zilles (ITiCSE 2024) · <https://zilles.cs.illinois.edu/papers/smith_eipe_cgbg_ITiCSE_2024.pdf>
  · A student explains code in prose; an LLM regenerates code from the explanation; unit tests
  check equivalence. Explanation quality becomes machine-checkable. · *explain-it-back verified
  by regeneration* · assessment time · education research, not productised.

## Cluster 2 — Merge-time understanding gates

- **PR Quiz (dkamm)** — shipping GitHub Action · dkamm · <https://github.com/dkamm/pr-quiz> ·
  Generates a quiz from the PR diff (OpenAI structured output, default o4-mini) and blocks
  merge until passed; configurable attempts (3), time limit (10 min), min lines changed (100),
  file exclusions; runs a temporary web server tunnelled via ngrok; triggers only after
  approval. Framed explicitly as "how do we make sure we understand what [AI agents] write?"
  · *quiz as merge gate* · PR time · active-ish (209 stars, low recent activity) · Show HN
  discussion at <https://news.ycombinator.com/item?id=44726672> (privacy, circumvention, and
  "works for human PRs too" themes).
- **pr-quiz (Revodata)** — shipping tool · revodatanl ·
  <https://github.com/revodatanl/pr-quiz> · Databricks job reads the diff, writes a question
  pool sized to the reviewable part (skips lockfiles, minified, vendored), samples fresh
  questions per attempt, and unlocks merge via a branch-protection status check only on a
  100% score for that commit. · *quiz as merge gate* · PR open · active (40 commits).
- **pr-quiz (Tidewave)** — prototype · Tidewave AI · <https://github.com/tidewave-ai/pr-quiz>
  · MCP App that shows two unlabelled implementations side by side, asks the user to pick the
  better and justify it, then reveals which came from the PR and discusses trade-offs.
  · *comparative judgement instead of recall* · on demand · self-described "vibe-coded"
  exploration of MCP Apps (25 stars).
- **LLVM AI Tool Use Policy** — practice · LLVM project ·
  <https://llvm.org/docs/AIToolPolicy.html> · Contributors must read and review all
  LLM-generated content before asking others to review it and "be able to answer questions
  about their work during review"; the contributor is always the author. · *explain-on-demand
  as policy gate* · PR time · adopted · cited widely as the reference policy.
- **BeeWare AI policy** — practice · BeeWare ·
  <https://beeware.org/contributing/guide/policies/ai-policy/> · "You must fully understand
  every line of code in the submission. You must be able to fully explain your implementation
  during the review process"; doubt closes the PR. · *explain-on-demand gate* · PR time ·
  adopted 2026-04-24.
- **Mastodon AI policy** — practice · Mastodon ·
  <https://github.com/mastodon/.github/blob/main/AI_POLICY.md> · Same "understand every line
  and explain the why" clause. · *explain-on-demand gate* · PR time · adopted.
- **Landscape of AI policies in popular OSS projects** — study · Hora, Robbes, Zacchiroli
  (2026-09-07) · <https://arxiv.org/abs/2609.07542> · 281 policies: 83.3% permit AI, 48.8%
  require disclosure, 67.3% require high human involvement, 43.4% assign accountability; ten
  "anti-slop" countermeasures catalogued. · *policy survey* · — · preprint · gives the base
  rate for explain-it-back clauses.
- **"Code review assumes an author"** — essay · Raed (2026-06-01) ·
  <https://blog.raed.dev/posts/ai-code-review> · A PR is not ready until the human can state
  its intent, the invariants it touches, and the evidence it is safe; producing that
  explanation is what returns ownership. · *explain-before-review* · PR time · essay.
- **Simon Willison's golden rule** — practice · Simon Willison (2025-03-19) ·
  <https://simonwillison.net/2025/Mar/19/vibe-coding/> · Won't commit code he "couldn't
  explain exactly what it does to somebody else"; the line between vibe coding and software
  development. · *explain-it-back as personal commit gate* · commit time · widely quoted.
- **GitHub "Review AI-generated code" tutorial** — vendor guidance · GitHub ·
  <https://docs.github.com/en/copilot/tutorials/review-ai-generated-code> · Eight-step
  checklist (right problem, architecture fit, hidden assumptions, human-judgement decisions)
  pointing at Copilot review, test-generation and self-review agents; no comprehension check
  on the author. · *checklist* · PR time · shipping docs.

## Cluster 3 — Diff-comprehension aids

- **CodeRabbit walkthrough and sequence diagrams** — shipping · CodeRabbit ·
  <https://docs.coderabbit.ai/pr-reviews/walkthroughs> · Top-of-PR comment with grouped
  file-change table in plain language, plus Mermaid sequence diagrams for PRs that change
  component interactions; sections individually toggleable. · *AI walkthrough, diagram* ·
  PR open · active.
- **Sourcery reviewer's guide** — shipping · Sourcery ·
  <https://docs.sourcery.ai/reviews/anatomy-of-a-review/> · Summary of purpose and risk in
  the description, a reviewer's guide mapping the change set file by file with how to verify,
  sequence diagrams on by default. · *AI walkthrough* · PR open · active.
- **GitHub Copilot PR summaries and "explore pull requests"** — shipping · GitHub ·
  <https://docs.github.com/en/copilot/how-tos/copilot-on-github/copilot-for-github-tasks/create-a-pr-summary>
  and <https://docs.github.com/en/copilot/tutorials/explore-pull-requests> · Summarise a PR,
  narrate its commits and unresolved feedback, explain a file's changes or selected lines, and
  ask a Copilot-authored PR about its own decisions. · *explanation on demand over a diff* ·
  PR time · active.
- **GitHub Next "Copilot for Pull Requests"** — concluded experiment · GitHub Next ·
  <https://githubnext.com/projects/copilot-for-pull-requests/> · `copilot:walkthrough` marker
  expanded into a linked list of changes. · *AI walkthrough* · PR time · technical preview
  ended 2023-12-15; ideas folded into Copilot.
- **"Explain This Pull Request" feature request** — proposal · GitHub community discussion
  (2026-07-12) · <https://github.com/orgs/community/discussions/201713> · Asks for pre-review
  summaries with breaking changes, risk areas and role-specific views; commenters note partial
  overlap with Copilot summaries. · *AI walkthrough* · PR time · no GitHub response.
- **/explain-diff and literate diffs** — prototype · Geoffrey Litt ·
  <https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524> · Skill that turns
  a diff into a structured explainer (HTML or Notion variants; corrected 2026-09-13, no Markdown
  variant exists) ordered as prose with background, intuition, embedded snippets and interactive
  figures, instead of alphabetical file order; the gist's own ordering rule is only "Group/order
  the changes in an understandable way" — flow ordering and quiz anti-leak rules are in
  commenters' forks (see [track-hand-off-checks.md](track-hand-off-checks.md#litts-explain-diff-what-the-gist-actually-contains)).
  · *literate diff* · on demand · gist (1,139 stars, 157 forks, 23 comments on 2026-09-13).
- **Hunk** — shipping tool · Modem (modem-dev) · <https://github.com/modem-dev/hunk> ·
  Review-first terminal diff viewer for agent-authored changesets: whole-changeset reading
  order, watch mode, inline AI/agent notes beside hunks, positioned as a gate between the
  agent and git. · *review-first viewer, friction* · after agent run, before commit · active
  (9.2k stars, 872 commits).
- **git-narrate / correlated PR narratives** — prototype · arsyadal ·
  <https://dev.to/arsyadal/how-we-correlated-llm-tool-calls-with-git-diff-hunks-to-automate-pr-narratives-289j>
  · Parses the agent transcript and matches each modified hunk to the prompt or reasoning
  that caused it, producing a narrative PR description. · *diff annotated with intent* ·
  PR time · write-up only; overlaps Cluster 6.

## Cluster 4 — Explorable maps and explanation on demand

- **Windsurf Codemaps** — shipping · Cognition (2025-11-04) ·
  <https://cognition.com/blog/codemaps> · Task-specific, AI-annotated structured maps of a
  repo (entry points, call paths, trace guides, node diagrams) generated by SWE-1.5 or
  Sonnet 4.5; referenced in agent prompts via `@{codemap}`. Stated aim is to turn engineers'
  brains "ON rather than OFF"; cites onboarding-cost sources, no internal benchmarks.
  · *task-scoped map* · on demand · active.
- **DeepWiki / Devin Wiki** — shipping · Cognition (public 2025-05-05) ·
  <https://github.com/CognitionAI/deepwiki> and <https://docs.devin.ai/work-with-devin/deepwiki>
  · Auto-generated wiki with Mermaid architecture and data-flow diagrams, source links and
  "Ask Devin" Q&A; 50k+ public repos pre-indexed; private repos via Devin; configured with
  `.devin/wiki.json`. · *generated wiki, Q&A* · continuous · active.
- **Google Code Wiki** — shipping preview · Google (2025-11-13) ·
  <https://developers.googleblog.com/introducing-code-wiki-accelerating-your-code-understanding/>
  · Regenerates a structured wiki with architecture, class and sequence diagrams after each
  change; Gemini chat grounded in the wiki; public repos free; Gemini CLI extension for
  private repos on waitlist. · *generated wiki, Q&A* · continuous · public preview.
- **Mutable.ai Auto Wiki** — shipping (2024) · Mutable.ai ·
  <https://blog.mutable.ai/p/auto-wiki-v2> · Wikipedia-style articles with citations to
  lines and diagrams, refreshed per commit / monthly. · *generated wiki* · continuous ·
  status unclear in 2026; earliest of the wiki generators.
- **CodeTour** — shipping (pre-agent) · Microsoft / vsls-contrib ·
  <https://github.com/microsoft/codetour> · Record and play back step-by-step guided tours
  of a codebase inside VS Code; tours checked into the repo. · *authored tour* · onboarding ·
  maintained.
- **Tour de Code AI** — prototype · Saurabh Yergattikar ·
  <https://github.com/Tour-de-Code-AI/Tour-de-Code-AI> · Fork of CodeTour that generates
  narrative tours from a Repomix dump via an LLM, ordered by entry points. · *generated tour*
  · on demand · small (18 stars).
- **Aider repo map** — shipping (agent-facing) · Paul Gauthier ·
  <https://aider.chat/docs/repomap.html> · Tree-sitter symbol graph ranked by PageRank to
  fit a token budget; built for the model, but readable by humans and re-implemented as an
  MCP server (<https://github.com/pdavis68/RepoMapper>). · *ranked structural map* ·
  continuous · active.
- **Sourcegraph Cody** — shipping (enterprise only) · Sourcegraph ·
  <https://sourcegraph.com/docs/cody> · Chat-based explanations over local and remote
  codebases, marketed for onboarding; Free and Pro tiers ended 2025-07-23
  (<https://sourcegraph.com/blog/changes-to-cody-free-pro-and-enterprise-starter-plans>),
  individuals pointed to Amp. · *Q&A over code* · on demand · enterprise-only.
- **Greptile** — shipping · Greptile · <https://www.greptile.com> · Semantic graph of the
  repo powering PR review and a query API. · *Q&A over graph* · PR time and on demand ·
  active.
- **Unblocked** — shipping · Unblocked · <https://docs.getunblocked.com/what-is-unblocked>
  · Connects code, tickets, chat and docs into a context engine for asking questions about
  the codebase and feeding agents; Series A 2026. · *Q&A over code plus history* · on demand
  · active.
- **Kognita** — shipping · Kognita · <https://www.kognita.co/blog/ai-coding-bus-factor-problem>
  · Managed semantic index of conventions and cross-service relationships, framed as
  countering knowledge concentrating in one engineer's AI setup. · *queryable index* ·
  continuous · promotional, undated.
- **CodeSee** — sunset · CodeSee → GitKraken · <https://www.codesee.io> · Automated
  codebase maps; company announced shutdown 2024-02-22, acquired by GitKraken 2024-05-14.
  · *generated map* · — · absorbed.
- **bloop** — open source, commercial site inactive · BloopAI ·
  <https://github.com/BloopAI/bloop> · Natural-language code search and chat. · *Q&A* ·
  on demand · self-host only.
- **Onboard AI** — early entrant (2023) · <https://www.producthunt.com/products/onboard-ai>
  · "ChatGPT with all the context for your repo"; later product pages under the same name
  are unrelated. · *Q&A* · onboarding · status unclear.
- **Built-in explain / ask modes** — shipping · Cursor Ask mode
  (<https://cursor.com/help/ai-features/ask-mode>, read-only exploration, docs recommend
  planning in Ask before Agent); JetBrains AI Assistant Explain code
  (<https://www.jetbrains.com/help/ai-assistant/explain-code-with-ai.html>); GitHub Copilot
  `/explain`. · *explanation on demand* · on demand · active · none check that the
  explanation was absorbed.

## Cluster 5 — Agent-maintained living artifacts

- **Swimm** — shipping · Swimm · <https://docs.swimm.io/> · Code-coupled docs with smart
  tokens; Auto-sync detects when referenced code changed and proposes updates; surfaced in
  IDEs as you navigate; now positioned as an assistant for "big, complex codebases".
  · *living doc* · continuous · active.
- **Kiro steering files and agent hooks** — shipping · AWS Kiro ·
  <https://kiro.dev/docs/steering/> and
  <https://kiro.dev/blog/how-i-stopped-worrying-about-readme-files/> (2025-10-09) · Steering
  files hold architecture and conventions and can link live workspace files; hooks re-run an
  agent to refresh README/API docs on save, with a warning about over-broad patterns.
  · *living doc, spec* · on file events · active; Kiro replaces Amazon Q Developer.
- **Amazon Q Developer `/doc`** — sunset · AWS ·
  <https://docs.aws.amazon.com/en_us/amazonq/latest/qdeveloper-ug/generate-docs.html> ·
  Generates and updates READMEs and infra diagrams. End of support 2027-04-30, new signups
  blocked from 2026-05-15
  (<https://aws.amazon.com/blogs/devops/amazon-q-developer-end-of-support-announcement/>).
  · *generated doc* · on demand · being retired.
- **AGENTS.md convention** — practice · agents.md · <https://agents.md> · "README for
  agents" carrying conventions and commands; used as the anchor for pointing agents at ADRs.
  · *ambient context doc* · every session · widespread (60k+ projects claimed on the site).
- **record-architecture-decisions skill** — prototype · Eric Clemmons ·
  <https://gist.github.com/ericclemmons/96cc6c774e2062e6660f1acb97506940> · Skill instructing
  the agent to write an ADR whenever it makes an architectural change, referenced from
  AGENTS.md. · *agent-written ADR* · at change time · gist.
- **Cursor rules / Continue rules** — shipping · Cursor, Continue ·
  <https://cursor.com/docs/context/rules> · Persistent instruction files; used in practice as
  the place architecture summaries live. · *ambient context doc* · every session · active.
- **DeepWiki and Google Code Wiki** — see Cluster 4; both regenerate on change and are the
  clearest shipping "living architecture doc" generators.
- **Maintainability sensors for coding agents** — essay with prototypes · Birgitta Böckeler,
  Thoughtworks (2026-05-27) · <https://martinfowler.com/articles/sensors-for-coding-agents.html>
  · "Guides" (markdown for agents) and "sensors" (lint, coupling analyser, mutation testing)
  keep the *agent's* output maintainable; a human-facing coupling visualisation was tried and
  found tedious. · *agent-side feedback; human view secondary* · continuous · essay.

## Cluster 6 — Provenance and intent capture (seeds missed)

- **Agent Trace** — open specification · Cursor (<https://agent-trace.dev/>, RFC 0.1.0,
  January 2026, authored by Lee Robinson), endorsed on 2026-01-29 by Cognition alongside
  Cloudflare, Vercel, git-ai, Google Jules, Amp, OpenCode (corrected 2026-09-13: Cognition's
  post is an endorsement, not the spec's origin) · <https://cognition.com/blog/agent-trace> ·
  Attributes each change to the conversation and line ranges that produced it via a URL to
  externally stored context; aim is a "living record of decision traces" so code stays
  legible. · *intent provenance* · at commit · spec site live, but the canonical repository
  `github.com/cursor/agent-trace` returns 404 with no redirect (its last commit, 2026-02-06, is
  visible only through forks; it disappeared between 2026-06-30 and 2026-08-15) and no backer
  documents emitting or consuming it; see
  [track-rationale-as-artifact.md](track-rationale-as-artifact.md#the-agent-trace-specification).
- **git-ai** — shipping · git-ai-project · <https://github.com/git-ai-project/git-ai> · Git
  extension linking every AI-written line to agent, model and prompt; `git ai blame`.
  · *line-level provenance* · continuous · active.
- **Commit Context** — shipping feature · AgentsRoom · <https://agentsroom.dev/features/commit-context>
  · Attaches the redacted agent conversation to each commit as an unlisted gist linked from
  the message; 14 agent CLIs. · *conversation-per-commit* · at commit · enabled by default in
  the app.
- **gitwhy** — prototype · mehrtam · <https://github.com/mehrtam/gitwhy> · Links Claude Code
  and Codex session transcripts to commits by file overlap, time window and visible commit
  commands; emits an HTML report and a `GITWHY.md` memory file; notes Claude Code's 30-day
  transcript deletion. · *session-to-commit linking* · after the fact · small (6 stars).
- **blameprompt / ai-blame / code-provenance** — prototypes ·
  <https://github.com/Ekaanth/blameprompt>, <https://github.com/ai4curation/ai-blame>,
  <https://github.com/QAInsights/code-provenance> · Variants of "git blame for prompts".
  · *provenance* · continuous · small.
- **"Agent sessions are the real commit messages"** — essay · Blake Crosley ·
  <https://blakecrosley.com/blog/session-is-the-commit-message> · Argues the transcript holds
  the design reasoning the diff discards. · *framing* · — · essay.
- **TraceVault** — named in VirtusLab's essay (Cluster 8) as capturing conversations, tool
  calls and reasoning tied to commits; no primary repo or product page found.

## Cluster 7 — Friction and metacognitive checkpoints

- **Claude Code Learning style `TODO(human)`** — see Cluster 1; the only first-party mode
  that hands authorship back mid-task.
- **Covate quiz-blocking** — see Cluster 1; blocks the agent until the card is completed or
  times out (not until a pass mark), not the merge.
- **Hunk as agent-to-git gate** — see Cluster 3.
- **Vibe Check MCP** — shipping MCP server · PV-Bhat ·
  <https://github.com/PV-Bhat/vibe-check-mcp-server> · Metacognitive questions and a pause
  layer aimed at the *agent's* tunnel vision; claims +27% success and −41% harmful actions.
  Included because it is the agent-side mirror of human checkpoints. · *agent metacognition*
  · during run · active.
- **Cursor Ask and Plan modes** — shipping · Cursor · <https://cursor.com/help/ai-features/ask-mode>
  · Read-only Ask, and Plan mode that produces a plan and clarifying questions before
  execution; docs recommend Ask-then-Agent. · *plan before apply* · per task · active.
- **Command-center UI for migrations** — prototype · Geoffrey Litt (see Cluster 3 source) ·
  Game-like interface that performs a migration step by step with visible effects, so the
  human stays in the loop at a coarser grain than the diff. · *step-wise visibility* · on
  demand · prototype.
- **AI-free days ("Rawdog Thursdays"), plan-before-execute, adversarial sub-agent review** —
  practices · Ask HN "How do we stop vibe coding?" ·
  <https://news.ycombinator.com/item?id=49033388> · Community-proposed rituals: a weekly
  no-AI day, mandatory plans for approval, humans own architecture while agents implement
  functions, deliberate hand-coding in hard domains. · *scheduled abstinence, plan gate* ·
  weekly / per task · discourse only.

## Cluster 8 — Discourse and framing

- **Thoughtworks Technology Radar: "Codebase cognitive debt"** — radar entry · Thoughtworks
  Vol. 34, April 2026 · <https://www.thoughtworks.com/radar/techniques/codebase-cognitive-debt>
  · Defines the gap between implementation and shared understanding; "proceed with caution";
  names feedback sensors, tracking team cognitive load, and architectural fitness functions.
- **"How Generative and Agentic AI Shift Concern from Technical Debt to Cognitive Debt"** —
  essay · Margaret-Anne Storey (2026-02-09) · <https://margaretstorey.com/blog/2026/02/09/cognitive-debt/>
  · Naur's "program as theory"; practices: at least one human fully understands each AI
  change, document why, periodic rebuild-understanding checkpoints. Republished at DX
  (2026-04-22) with warning signs (fear of change, tribal knowledge, black-box perception):
  <https://getdx.com/blog/cognitive-debt-the-hidden-risk-in-ai-driven-software-development/>.
- **"From Technical Debt to Cognitive and Intent Debt"** — paper · Storey (ACM Queue; arXiv
  2026-03-23) · <https://arxiv.org/abs/2603.22106> · Triple-debt model adding intent debt
  (missing externalised goals and rationale); suggests onboarding-time tracking, knowledge
  concentration metrics and intent-vs-behaviour audits.
- **"Comprehension Debt"** — essay · Addy Osmani (2026-03-14) ·
  <https://addyosmani.com/blog/comprehension-debt/> · Speed asymmetry between generation and
  understanding; be explicit about intent before code is written; system-level mental models
  over line-by-line review; no specific tools.
- **"Cognitive debt: the code nobody understands"** — essay · VirtusLab (2026-04-10) ·
  <https://virtuslab.com/blog/ai/cognitive-debt-the-code-nobody-understands> · Design
  review before generation, reviewer rotation, ask reviewers to explain purpose not judge
  correctness, atomic changes, and measurement ideas (comprehension test scores, feedback-loop
  speed).
- **"AI coding creates two kinds of debt"** — article · LeadDev ·
  <https://leaddev.com/ai/ai-coding-creates-two-kinds-of-debt-youre-only-measuring-one> ·
  Management-audience framing; cites Anthropic's 17% comprehension gap.
- **"Understanding is the new bottleneck"** — talk and post · Geoffrey Litt (2026-07-02) ·
  <https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck> · Covered by a
  sibling note; its artefacts appear in Clusters 1, 3 and 7.
- **"Understanding is the new bottleneck"** — essay · Eric J. Ma (2026-08-27) ·
  <https://dspn.substack.com/p/understanding-is-the-new-bottleneck> · Literate explainers,
  quizzes, micro-worlds; "if you approve a PR you couldn't have written and can't fully
  explain, you didn't review it. You witnessed it."
- **"Breaking the spell of vibe coding"** — essay · Rachel Thomas, fast.ai (2026-01-28) ·
  <https://www.fast.ai/posts/2026-01-28-dark-flow/> · "Dark flow": productivity feeling
  without growth; no tooling proposed. HN discussion
  (<https://news.ycombinator.com/item?id=47006615>) adds spec-first, allowlists, mandatory
  comprehension in review.
- **"Not all AI-assisted programming is vibe coding"** — essay · Simon Willison (2025-03-19)
  · see Cluster 2.
- **"Agents That Teach"** — position paper · Mehra et al., ASE 2026 NIER ·
  <https://arxiv.org/abs/2607.06101> · "Knowledge Debt" as developer-level technical debt;
  six design principles; SHIELD multi-agent system surfaces out-of-band learning moments from
  the agent's own reasoning; no evaluation.
- **Anthropic "How AI assistance impacts the formation of coding skills"** — study
  (2026-01) · <https://www.anthropic.com/research/AI-assistance-coding-skills> · RCT, 52
  engineers, 17% lower quiz scores with AI; concept-question users scored well, delegators
  poorly; calls for "intentional design choices that ensure engineers continue to learn".
  Detail belongs to the academic sibling; listed because it is the vendor-published trigger
  most tools in Cluster 1 cite.
- **Ask HN threads** — discourse · <https://news.ycombinator.com/item?id=49033388> (stop vibe
  coding), <https://news.ycombinator.com/item?id=44726672> (PR quiz), Auto Wiki Show HN
  <https://news.ycombinator.com/item?id=38915999>.

## Cluster 9 — Measurement and detection

- **"The Substrate Collapse"** — position paper · Brett Wheeler (2026-06-18) ·
  <https://arxiv.org/abs/2606.20882> · Truck factor and Degree-of-Authorship measure
  authorship, which no longer implies comprehension; calls for instruments grounded in
  evidence of comprehension and predicts incident-resolution failures where authorship
  metrics look healthy. Construction left open.
- **"Impact of Generative AI on Code Expertise Models"** — study ·
  <https://arxiv.org/pdf/2507.08160> · Degree of Knowledge (authorship plus interest) under
  AI authorship. Academic sibling covers.
- **DX AI Measurement Framework** — shipping survey metric · DX ·
  <https://getdx.com/research/measuring-ai-code-assistants-and-agents/> · "Code
  maintainability" is a perception item (developers rate how easy code is to understand and
  modify); the closest shipping proxy for comprehension. · *perception survey* · periodic.
- **Thoughtworks "tracking team cognitive load"** — technique named in the radar entry;
  no tool.
- **Kognita** — commercial framing of knowledge concentration; see Cluster 4.
- **git-ai attribution share** — proxy; percentage of AI-written lines per file, not
  comprehension. See Cluster 6.

## Areas the seeds missed

- **Provenance and intent capture** (Cluster 6): an open spec with multi-vendor backing and
  half a dozen tools treat the agent transcript as the durable record of "why". The seeds
  framed living docs as prose; this cluster keeps the raw reasoning instead.
- **Open-source AI policies as understanding gates** (Cluster 2): "understand every line and
  explain it in review" is now boilerplate in project policies, with a 281-policy survey
  giving base rates. This is the most widely adopted explain-it-back mechanism found, and it
  is enforced socially, not by tooling.
- **Review-first terminal diff viewers** (Hunk): a large-adoption tool whose premise is that
  reading should be separated from editing and interposed before commit.
- **Explain-it-back verified by regeneration** (CGBG): a mechanism from CS education that
  makes a prose explanation machine-checkable by regenerating code from it.
- **Learning-science-authored skills** (Learning Opportunities): the one item with an explicit
  cognitive-science basis and notable adoption; its self-suppression rule is a design answer to
  friction fatigue.
- **Agent-side metacognition** (Vibe Check): the same pause-and-question pattern applied to
  the agent, with claimed effect sizes; a mirror for human-side designs.
- **Commit-time as distinct from PR-time**: Willison's rule, gitwhy, Commit Context and
  socratic `quiz-me` all attach to the commit, not the PR.
- **Scheduled abstinence** (AI-free days) as a ritual, present only in discourse.

## Dead ends

- Anki-style spaced repetition *over a codebase*: only generic flashcard/quiz skills and
  learn-codebase's SRS scheduling; no tool builds a deck from a repository's structure.
- Per-module mastery tracking: only learn-codebase's per-user journal; nothing team-level.
- Comprehension telemetry: no shipping tool measures understanding; the nearest are a
  perception survey item (DX) and authorship proxies (git-ai).
- Parsons-problem or question generation from a *real* codebase: CodeTailor and EiPE work
  target course material only.
- Company engineering blogs describing internal comprehension-check rituals: none found;
  the practice literature is individual essays and OSS policies. (qualified 2026-09-13: still
  no ritual with enforcement detail, but PostHog's blog names "Does the author understand the
  change?" as a human review question and its handbook requires human review of agent-authored
  PRs; see the [discourse and tooling addendum](discourse-and-tooling-addendum.md#corrections-proposed).)
- Conference talks on the theme other than Litt's: none located by title. (corrected
  2026-09-13: the later sweep located about twenty-five, among them Volkov's "The Z/L
  Continuum", Kanazawa's "I Let Agents Refactor My Codebase for 3 Weeks", Stauffer's
  "Building Software at the Edge of Your Understanding", and Storey's forthcoming
  "Understanding as a Deliverable"; see the
  [discourse and tooling addendum](discourse-and-tooling-addendum.md#corrections-proposed).)
- TraceVault: named in one essay, no primary source.
- Copilot Workspace: could not confirm status from GitHub Next's page; Copilot for Pull
  Requests is confirmed concluded (2023-12).
- Sourcegraph Cody, CodeSee, Onboard AI, bloop, Mutable Auto Wiki: the 2023 onboarding
  cohort is sunset, acquired, enterprise-only, or unclear.
- GitHub's response to the "Explain this PR" request: none.

## Observations for the deep pass

Cluster 1 (retrieval practice): how do the skills decide *what* to quiz (diff, plan, module,
whole repo), and what evidence exists that generated questions test the model rather than the
text; how Learning Opportunities' trigger and self-suppression rules behave in long sessions;
whether any skill's journal survives across worktrees or machines.

Cluster 2 (gates): PR Quiz's default trigger is post-approval, so what it gates is the merger
not the reviewer; Revodata gates on 100% for a commit, so how re-pushes interact; how OSS
policies are actually enforced in review threads (the Hora survey's "countermeasures" list).

Cluster 3 (diff aids): whether walkthroughs are read (CodeRabbit and Sourcery expose toggles
but no read metrics); how Hunk's inline agent notes are produced and whether they are stored.

Cluster 4 (maps): Codemaps is task-scoped and ephemeral, Code Wiki and DeepWiki are
repo-scoped and regenerated; which of them persist a human's annotations; what happened to
Mutable Auto Wiki.

Cluster 5 (living artifacts): Kiro hooks and Swimm both regenerate on file events; what
prevents regeneration from silently rewriting the human's intent; whether any artifact records
that a human read it.

Cluster 6 (provenance): Agent Trace's actual adoption among its listed backers; how Claude
Code's 30-day transcript deletion interacts with commit-linking; whether any tool renders a
trace for a *reader* rather than for an agent.

Cluster 7 (friction): Covate blocks the agent (until completion, not a pass), Hunk sits before commit, PR Quiz before merge;
no item sits at task start; Vibe Check's claimed effects come from the project's own
case studies.

Cluster 9 (measurement): every proposal is a position paper; the DX item is the only deployed
instrument and it is self-report.
