---
status: research
date: 2026-09-13
---

# Track: a durable model of the codebase over time

Research date: 2026-09-13

This note is the Phase B deep pass on one feature idea from the cognitive-debt
research phase: retrieval practice and spaced repetition applied to a living
repository, with per-module or per-concept mastery, and the problem that code
changes invalidate what was learned. It is documentary. It records what
exists, what each source claims, and where the sources stop; it does not rank,
recommend, or judge fit for Dashpot or any workflow. Terminal citations are
primary — the repository, manual, paper, or author's own post — and claims
that could not be verified against a primary source are marked. Phase A is
cited by relative link rather than repeated. Three parallel research agents
supplied catalogue sweeps; every claim taken from them that carries weight
was re-read against its source before inclusion, and two agent claims that did
not survive that check are recorded under Dead ends.

## The idea

Phase A established the object at risk — a layered mental model whose
situation and rationale layers are expensive to build and largely undocumented
([evidence-and-mechanisms.md, "Program comprehension"](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of))
— and the two mechanisms with the strongest support for retaining declarative
knowledge: retrieval practice (g≈0.50–0.61) and spacing, both established on
discrete, stable items and neither tested on a real, evolving codebase
([evidence-and-mechanisms.md, "Retrieval practice"](evidence-and-mechanisms.md#retrieval-practice-testing-effect),
["Spaced repetition and its schedulers"](evidence-and-mechanisms.md#spaced-repetition-and-its-schedulers)).
The landscape sweep found no tool that builds a spaced-repetition deck from a
repository, per-module mastery only as one skill's per-user journal, and
Litt's quiz as a one-shot gate at hand-off with Quantum Country cited as
inspiration but not as mechanism
([landscape-sweep.md, "Dead ends"](landscape-sweep.md#dead-ends);
[understanding-bottleneck-talk.md, "Proposal 2"](understanding-bottleneck-talk.md#proposal-2-quizzes-as-a-speed-regulator)).
Solveit applies Anki to reading, not to code
([solve-it-sweep.md, "Product mechanics"](solve-it-sweep.md#product-mechanics)).
The idea under examination is therefore: items about a codebase, generated
from it, scheduled by a spacing algorithm, tracked per unit of the repository,
and kept truthful as the repository changes. This pass asks what each of
those parts already looks like in the sources.

## Prior attempts

Each entry: what the items are, how they are generated, how they are
scheduled, whether they survive the source changing, maturity, primary URL.
Phase A's Cluster 1 is the baseline
([landscape-sweep.md](landscape-sweep.md#cluster-1--retrieval-practice-and-socratic-tutoring-in-the-agent-loop));
entries already there are kept short except where this pass read the source
more closely. Repository metadata is from the GitHub API on 2026-09-13.

### Items generated from a repository, diff, or PR

- **codequiz** (nessielabs; "Duolingo for your codebase — a Claude Code
  skill that quizzes you on your own code with XP, spaced repetition, and
  mastery tracking";
  [github.com/nessielabs/codequiz](https://github.com/nessielabs/codequiz);
  13 stars, created and last pushed 2026-03-21). The one tool found that keys
  mastery to repository structure and schedules reviews from it. Items: three
  question types the agent composes after reading source — "Explain This
  (easiest) — preferred for Novice modules," "What Happens When (medium),"
  "Connect the Dots (hardest) — preferred for Proficient modules." Unit:
  "use the top-level directory as the module key (e.g., `src/auth`,
  `src/api`, `lib/workers`). Do NOT use sub-paths … This prevents state
  fragmentation across sessions." State: per user, per repository, in
  `~/.codequiz/$REPO_SLUG/mastery.json`, saved "after EVERY question."
  Mastery: a confidence score per module updated by rule — "Correct:
  confidence += 0.15 (capped at 1.0); Partially correct: += 0.05; Incorrect:
  −= 0.1 (floored at 0.0); Spot-check pass: += 0.2; Spot-check fail: −=
  0.15" — with levels Novice 0.0–0.29, Familiar 0.3–0.59, Proficient
  0.6–0.84, Expert 0.85–1.0. Scheduling: "Confidence < 0.3: next_review =
  tomorrow; 0.3–0.59: 3 days from now; 0.6–0.84: 7 days from now; ≥ 0.85: 14
  days from now"; modules at ≥ 0.85 with a future `next_review` are excluded
  from a session; a user can say "Quiz me on this again later" to force
  `next_review` to tomorrow. Survival of source change: not addressed — the
  skill reads the current code when it composes a question, but nothing
  reads commits, hashes, or diffs, and confidence does not decay with time
  or edits; the only "git" calls locate the repository root and update the
  skill itself. Evidence: none
  ([SKILL.md](https://github.com/nessielabs/codequiz/blob/main/SKILL.md)).
- **comprehension-debt / `cdebt`** (RonaldSit;
  [github.com/RonaldSit/comprehension-debt](https://github.com/RonaldSit/comprehension-debt);
  0 stars, created and last pushed 2026-06-10). Not spaced repetition but a
  per-file verified-understanding score: "debt(file) = difficulty × exposure
  × (1 − verified understanding)"; `cdebt repay` "drafts an ADR + 3 questions
  about YOUR file"; `cdebt confirm . thefile.py -i` — "answer in your own
  words; answers get graded against the code"; "Generic AI-pasted answers
  score 0 (they never name the file's actual identifiers — that's their
  tell)"; `cdebt reverify .` re-grades "the whole corpus with today's
  grader"; files with no verified owner are flagged `[DARK]`; a CI gate
  blocks PRs. Unit: file. Invalidation: re-grading on demand; no time or
  edit trigger documented
  ([README](https://github.com/RonaldSit/comprehension-debt/blob/main/README.md)).
- **learn-codebase** (Konstantin Taletskiy;
  [github.com/ktaletsk/learn-codebase](https://github.com/ktaletsk/learn-codebase);
  55 stars, last push 2026-06-15). Items: Socratic questions the agent
  composes about the project during a tutoring session. Scheduling: a fixed
  ladder in SKILL.md — "1st success → review in 1 day; 2nd success → review
  in 3 days; 3rd success → review in 1 week; 4th success → review in 2 weeks;
  5th success → likely in long-term memory" — logged as dated checklist
  lines ("Auth middleware (review by: 2026-01-25) - 2nd review") in a
  per-project `.claude/learning-journal.md` copied from a bundled template.
  Mastery: a "Concept Mastery Map" with "Confused: Cannot explain or apply,"
  "Learning: Partial understanding, making connections, has questions,"
  "Confident: Can explain to others, can apply in new situations," plus a
  per-concept hint count. Unit: a concept named in prose ("JWT validation"),
  not a path. Survival of source change: not addressed; no reference to
  commits, hashes, or versions. The README's acknowledgments cite "Spaced
  repetition research (SM-2 algorithm concepts)"; the ladder is not SM-2
  ([SKILL.md](https://github.com/ktaletsk/learn-codebase/blob/main/SKILL.md),
  [JOURNAL-TEMPLATE.md](https://github.com/ktaletsk/learn-codebase/blob/main/JOURNAL-TEMPLATE.md)).
- **Doculearn** (williamai_, Show HN 2025-12-27, 1 point). "It watches your
  GitHub activity and automatically generates flashcards from YOUR code …
  actual flashcards about the authentication middleware you merged
  yesterday"; "When you push code, Doculearn: Generates spaced-repetition
  flashcards from your commits." Algorithm unnamed; change handling not
  addressed beyond new pushes producing new cards. Dead: doculearnapp.com
  refused connections on 2026-09-13
  ([news.ycombinator.com/item?id=46400512](https://news.ycombinator.com/item?id=46400512)).
  The only commit-driven flashcard generator found, and it did not survive.
- **exbrain.app** (Show HN 2019-05-27, 2 points): "breaking the code into
  flash cards and allow you to add an explanation for each method … uses
  spaced repetition"; Python only; prototype; site unreachable
  ([news.ycombinator.com/item?id=20024179](https://news.ycombinator.com/item?id=20024179)).
  **code-flashcards** (ToneyAlexander, 0 stars, two commits 2023-11-03):
  "generate flashcards from code to quiz yourself on repos"; no scheduling
  documented; dead (agent sweep).
- **Learning Opportunities** (Hicks and Mullarkey;
  [github.com/DrCatHicks/learning-opportunities](https://github.com/DrCatHicks/learning-opportunities);
  2,418 stars, CC-BY-4.0, last push 2026-08-19). Items: a 10–15 minute
  exercise offered after "Creating new files or modules; Database schema
  changes; Architectural decisions or refactors; Implementing unfamiliar
  patterns"; "Always ask before starting." Scheduling: none; the only
  time-sensitive element is a "Retrieval check-in (for returning sessions)"
  — "At the start of a new session on an ongoing project: Pause: 'Quick
  check—what do you remember about how [previous component] handles
  [scenario]?'" Self-suppression: "User declined an exercise offer this
  session; User has already completed 2 exercises this session." The skill
  keeps no journal, rating, or mastery record; see
  [Mastery and coverage models](#mastery-and-coverage-models), which corrects
  the task brief on this point
  ([SKILL.md](https://github.com/DrCatHicks/learning-opportunities/blob/main/learning-opportunities/skills/learning-opportunities/SKILL.md)).
- **Diff-time quizzes** — Covate `learning_session`, socratic-skills
  `quiz-me`, pr-quiz (209 stars), Litt's `/explain-diff` — generate items
  from the current diff, ask once, and do not persist them; Covate's README
  lists spaced repetition under an unbuilt "v2.0" and says "Not built yet,
  so not promised"; pr-quiz's README contains no scheduling
  ([landscape-sweep.md, Cluster 2](landscape-sweep.md#cluster-2--merge-time-understanding-gates);
  [understanding-bottleneck-talk.md](understanding-bottleneck-talk.md#proposal-2-quizzes-as-a-speed-regulator);
  [github.com/SunflowersLwtech/covate](https://github.com/SunflowersLwtech/covate);
  [github.com/dkamm/pr-quiz](https://github.com/dkamm/pr-quiz)).
- **Inquisitive code editor** (Henley et al., ICSE-SEET 2021,
  [arXiv:2102.06098](https://arxiv.org/abs/2102.06098)): questions about the
  behaviour of the programmer's own program, generated by analysis, surfaced
  as "a green question mark … much like a syntax error," periodic rather than
  spaced; no stored item to invalidate; Atom-plugin prototype with informal
  surveys (Phase A).
- **Repository sweep.** GitHub, PyPI, npm, and Hacker News searches for
  "flashcards from code," "anki codebase," "anki from git repo," "flashcards
  from commits," "anki from pull requests," "anki from documentation,"
  "spaced repetition codebase," and "srs code comprehension" returned only
  text-to-Anki converters, language vocabulary decks, Anki MCP servers, and
  the entries above. No shipping tool builds review items from a
  repository's structure, commits, or PRs (agent sweep; consistent with
  [landscape-sweep.md, "Dead ends"](landscape-sweep.md#dead-ends)).

### Items about programming languages and APIs

- **Wozniak, "Spaced repetition to increase programmer productivity"**
  (*Informatyka* 1993, revised 1998;
  [super-memory.com/articles/programming.htm](https://super-memory.com/articles/programming.htm)).
  The earliest and only source found that quantifies item attrition for
  programming knowledge. Items: "Elements of the language; syntax and use"
  and "Practical tips, observations, and experimental findings not included
  in the documentation (these should be collected by the programmer in the
  course of the programming practice) … compiler bugs, freaks of the
  operating system, frequently encountered traps." Selection: a
  "memorization criterion" TG > TL, time gained from not consulting an
  external reference against time lost to training. Attrition: "the
  knowledge of a programmer must constantly be turned over, with a large
  proportion of items losing their applicability in a period of time as
  short as 1-3 years"; his Pascal collection went from 800 Turbo Pascal 3
  items in 1987 to 40 in 1993 as the language moved through five versions,
  while the collection grew to 4,000 items.
- **Execute Program** (Gary Bernhardt;
  [executeprogram.com](https://www.executeprogram.com/)). Items:
  hand-authored interactive code examples (TypeScript, SQL, JavaScript,
  regular expressions, Python, concurrency); the learner answers by typing
  what the code evaluates to. Bernhardt's own description: "it's a spaced
  repetition system with exponential review intervals, similar to those used
  for language learning in e.g. WaniKani and Anki. But it also has a lot of
  fine-grained knowledge of its own course structure, so it can use reviews
  to intelligently unlock different lessons depending on how the user
  performed on their reviews"; "When you start a course, you get 5 lessons
  on the first day, then it stops you … On the next day, you get some brief
  reviews of yesterday's lessons, then a few new lessons"; "Execute Program
  is very intentionally non-bingeable"
  ([news.ycombinator.com/item?id=26349754](https://news.ycombinator.com/item?id=26349754)).
  Scheduling (verified 2026-09-13 from the site's own "Spaced Repetition" page, recovered from
  the client bundle — see [Execute Program (Bernhardt)](#execute-program-bernhardt)):
  exponential delays with base e, "four delay levels" of 2 days, 1 week, 3 weeks and 2 months,
  so a punctual learner "will completely finish an item's reviews after 90 days (2+7+21+60)"
  after five reviews; a "zeroth" 1-day level is shown only after "giving up" on a review; a wrong answer
  halves the item's level ("a middle ground" between reset and step-down); the earlier schedule
  was 1, 4, 16 and 64 days, dropped because "the 1-day review was too soon after the initial
  lesson". Survival of course revision: not addressed in any retrieved source.
  Commercial, launched 2019, live in 2026.
- **Fata** (Djoumé, Show HN 2026-06-11, 124 points;
  [fata.dev](https://fata.dev)). "Spaced repetition to fight skill rot from
  AI coding": "short daily spaced-repetition sessions for programming skills
  (Rust, CSS, React, Python, TypeScript, Architecture)"; "most content is
  now AI-generated. It takes about 3000 LLM calls to generate a course, and
  every code samples goes through compilation, linting, unit testing, AI and
  a final manual review." Items are course questions, not the user's code;
  algorithm unnamed; no retention data
  ([news.ycombinator.com/item?id=48489163](https://news.ycombinator.com/item?id=48489163)).
  The motivation is the cognitive-debt framing; the mechanism is a
  language-course SRS.
- **Quantum Country** (Matuschak and Nielsen;
  [quantum.country](https://quantum.country/),
  [numinous.productions/ttft](https://numinous.productions/ttft/)):
  112 hand-written prompts in a ~4-hour essay; schedule and data under
  [Scheduling algorithms](#scheduling-algorithms-and-their-assumptions) and
  [Evidence](#evidence). The essay's own caution on programming: "it's no
  good (but surprisingly common) for someone to memorize lots of details of
  a programming language they plan to use for just one small project."
- **Orbit** (Matuschak;
  [github.com/andymatuschak/orbit](https://github.com/andymatuschak/orbit);
  1,831 stars, last push 2024-10-14): author-embedded prompts on web pages
  and Markdown notes; scheduler and identity model under
  [Scheduling algorithms](#scheduling-algorithms-and-their-assumptions) and
  [Item invalidation and drift](#item-invalidation-and-drift).
- **Personal Anki practice on APIs and code.** Nielsen's "Augmenting
  Long-term Memory": items are "atomic" ("How to create a soft link from
  linkname to filename?" → "ln -s filename linkname"); the appendix "Using
  Anki to learn APIs" advises cards only "in tandem with serious work on your
  project" and adds, "I find it surprisingly helpful to Ankify the APIs for
  code I've personally written, if they're likely to be useful in the future.
  Just because I wrote something doesn't mean I'll remember it in future!";
  he wishes for "a memory system that integrates into my actual working
  environment … it could query me on Unix commands, while placing me at an
  actual command line"
  ([augmentingcognition.com/ltm.html](http://augmentingcognition.com/ltm.html)).
  Sivers, on a year of Anki for a programming language: "Every command,
  every parameter, every function"; "First, learn! Flash cards are for
  remembering what you've learned"; nothing on cards going out of date
  ([sivers.org/srs](https://sivers.org/srs)). Codecademy's "personalized
  practice packs" use "a modified version of the Leitner system" and track
  "individual facts you encounter … based on your chronological, correctness,
  and completeness data"
  ([codecademy.com/article/spaced-repetition](https://www.codecademy.com/article/spaced-repetition)).
  Exercism, Brilliant, Khan Academy: no programming-content review mechanics
  found; Duolingo's published model concerns language (agent sweep).
- **Adjacent: problem-set SRS.** Lanki (Show HN 2024, 206 points) and
  several SM-2 wrappers schedule LeetCode-style problems by self-rated
  difficulty and elapsed time; the item is a problem, not a codebase (agent
  sweep, not verified individually).
- **Design precedent: content-addressed cards.** Hashcards (Borretti;
  [github.com/eudoxia0/hashcards](https://github.com/eudoxia0/hashcards)):
  "cards are identified by the hash of their text. This means a card's
  progress is reset when the card is edited"; FSRS scheduling; the SQLite
  schema keys reviews on `card_hash`. The same identity strategy as Orbit's
  embedded prompts, stated as a feature.

### Items from reading, exported to Anki

- **fastanki** (Answer.AI;
  [github.com/AnswerDotAI/fastanki](https://github.com/AnswerDotAI/fastanki);
  30 stars, last push 2026-09-09) "reads and writes Anki's collection format
  and speaks the AnkiWeb sync protocol directly, in Python"; it creates and
  finds notes and cards and syncs them; it has no scheduler and no notion of
  a changing source. Its use in Solveit is for papers and books
  ([solve-it-sweep.md](solve-it-sweep.md#product-mechanics)).
- **Skill-Anything** (329 stars) turns "any source (PDF, video, web, audio,
  text)" into "25-50 spaced-repetition cards" with a `review` CLI; not
  code-specific; algorithm unnamed (agent sweep).

### Research on SRS for programming

No study found applies spaced retrieval to comprehension of a specific
codebase or to API knowledge in professionals. The nearest, all on course
material: YeckehZaare, Aronoff, and Grot, SIGCSE 2022, retrieval-based
teaching in introductory programming that incentivised spacing over more
days with higher course grades
([doi:10.1145/3478431.3499408](https://doi.org/10.1145/3478431.3499408);
record confirmed, abstract not retrieved); Elhayany and Meinel 2025, a
GPT-based generator of retrieval items for introductory programming whose
pilot reported "challenges in difficulty calibration and the accuracy of
AI-generated feedback, particularly in code-focused tasks"
([doi:10.1109/democon65705.2025.11282675](https://doi.org/10.1109/democon65705.2025.11282675);
agent-reported); and the Parsons and EiPE literature in Phase A.

## Scheduling algorithms and their assumptions

Each scheduler is described from its owner's document, then what that document
says, or implies by omission, about an item whose ground truth changes.

### SM-2 (SuperMemo, 1987)

Wozniak's account of SM-2, adapted from his 1990 master's thesis, states the
algorithm in seven steps, the first of which is a formulation rule, not a
scheduling rule: "Split the knowledge into smallest possible items." Every
item starts with an E-Factor of 2.5; intervals are I(1)=1, I(2)=6,
I(n)=I(n−1)·EF; after each repetition the user grades recall 0–5 and the
E-Factor is updated by EF' = EF + (0.1 − (5−q)(0.08 + (5−q)·0.02)), floored
at 1.3; a grade below 3 restarts the item's intervals "as if the item was
memorized anew" without changing the E-Factor
([super-memory.com/english/ol/sm2.htm](https://super-memory.com/english/ol/sm2.htm)).
Two statements bear on item semantics. The floor exists because items that
kept falling below 1.3 "always seemed to have inherent flaws in their
formulation (usually they did not conform to the minimum information
principle)," so the floor "provided an indicator of items that should be
reformulated" — the scheduler's only signal about an item is a difficulty
statistic, and the response is manual rewriting. And the program was built to
"apply the optimization procedures to smallest possible items" and
"differentiate between the items on the base of their different difficulty":
each item carries its own state and is scheduled independently.

Wozniak's "Twenty rules of formulating knowledge" is the one owner document
in this set that addresses changing ground truth. Rule 19, "Provide date
stamping": "Knowledge can be relatively stable (basic math, anatomy,
taxonomy, physical geography, etc.) and highly volatile (economic indicators,
high-tech knowledge, personal statistics, etc.). It is important that you
provide your items with time stamping or other tags indicating the degree of
obsolescence. … When learning software applications, it is enough you stamp
the item with the software version. Once you have newer figures you can
update your items. Unfortunately, in most cases you will have to re-memorize
knowledge that became outdated." Rule 18, "Provide sources": sources "help
you manage the learning process, updating your knowledge, judging its
reliability, or importance" and "should accompany your items but should not
be part of the learned knowledge." Rules 11 ("Combat interference") and 13
("Refer to other memories") acknowledge that items interact in memory even
though the scheduler treats them independently
([supermemo.com, twenty rules](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge)).
The invalidation mechanism is human: a version tag, a source pointer, and a
manual edit-or-relearn when the person notices the drift.

### Anki (legacy scheduler and FSRS)

Anki's legacy scheduler is SM-2-derived: "Starting ease … defaults to 2.50,"
an interval modifier, an easy bonus (default 1.30), a lapse "New interval"
multiplier whose default 0.00 resets the delay to zero, and a leech rule —
"When this counter reaches 8, Anki tags the note as a leech and suspends the
card" — whose remedies are to rewrite, delete, or suspend, because leeches
arise from "too much information," "trying to memorize something without
fully understanding it," or interference
([deck-options](https://docs.ankiweb.net/deck-options.html),
[leeches](https://docs.ankiweb.net/leeches.html)). The card is the
scheduling unit and the note the content unit: "Anki takes care of creating
the cards for you, and updating them if you make any edits in the future"
([getting-started](https://docs.ankiweb.net/getting-started.html)). The
manual never states an effect of editing on scheduling; it says so only by
implication — importing "notes … updated in place" preserves "the existing
scheduling information on all their cards"
([importing/text-files](https://docs.ankiweb.net/importing/text-files.html)),
changing note type leaves scheduling "not affected," and Reset "Move[s]
currently selected cards to the end of the new queue. The existing review
history is preserved"
([browsing](https://docs.ankiweb.net/browsing.html)). A forum moderator
states the rule plainly: "anything that doesn't cause cards to be created or
deleted – won't impact scheduling"
([forums.ankiweb.net/t/50066](https://forums.ankiweb.net/t/editing-cards-and-impact-on-scheduling/50066);
not an owner document). Content and memory state are decoupled by design: a
changed fact keeps the old fact's interval unless a person resets it.

FSRS, in Anki since 23.10, is documented in the manual and the project wiki.
The manual: "Choose a value of desired retention: the proportion of cards
recalled successfully when they are due. … The default is 90% … Above 90% the
workload increases very quickly, and above 97% the workload can be
overwhelming"; "The FSRS optimizer uses machine learning to learn your memory
patterns and find parameters that best fit your review history"; "FSRS can
adapt to almost any habit, except for one: pressing 'Hard' instead of 'Again'
when you forget the information. When you press 'Hard', FSRS assumes you have
recalled the information correctly"; where history is missing "it will assume
that when you did those old reviews, you remembered 90% of the material"; and
"Reschedule cards on change" is off by default so that "future reviews will
use the new scheduling, but there will be no immediate change to your
workload"
([deck-options](https://docs.ankiweb.net/deck-options.html)). The wiki
defines the memory state as retrievability, "the probability that the person
can successfully recall a particular piece of information at a given moment";
stability, "the time, in days, required for R to decrease from 100% to 90%";
and difficulty, "the inherent complexity of a particular information … how
difficult it is to increase memory stability after a review," and states
that FSRS "springs from DHP model, which is based on the 'Three Component
Model of Memory'"
([ABC of FSRS](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/ABC-of-FSRS)).
The algorithm page gives retrievability as R(t,S) = 0.9^(t/S) in v3, a power
law R(t,S) = (1 + t/(9S))^−1 from v4, (1 + FACTOR·t/S)^DECAY with DECAY = −0.5
and FACTOR = 19/81 in FSRS-4.5, and a trainable decay −w20 in FSRS-6 (21
parameters); post-lapse stability S'_f = w11·D^−w12·((S+1)^w13 − 1)·e^(w14(1−R));
difficulty mean-reverts after every review
([The Algorithm](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm)).
Papers: Ye, Su, and Cao, KDD 2022,
[doi:10.1145/3534678.3539081](https://doi.org/10.1145/3534678.3539081); Su et
al., IEEE TKDE 2023,
[doi:10.1109/TKDE.2023.3251721](https://doi.org/10.1109/TKDE.2023.3251721)
(records confirmed; full texts not retrieved). The benchmark evaluates
schedulers on about 727 million reviews from 10,000 Anki users (349.9 million
after filtering) by log loss, binned RMSE, and AUC, removing filtered-deck
reviews and manual due-date changes and handling same-day reviews separately;
recurrent networks and FSRS variants lead, HLR and an SM-2 equivalent trail
([srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark)).

What FSRS assumes, read from these documents: the memory state (D, S, R)
belongs to one card, changes only at reviews, and is inferred from that card's
grade history plus population parameters; a grade reports recall, never the
item's truth; the benchmark's ground truth is the next grade. Nothing in the
manual, wiki, or benchmark mentions a card whose content changed between
reviews; the only content-level signals are difficulty and the leech counter,
both of which would read a changed fact as a hard fact.

### Orbit (Matuschak)

Orbit's scheduler is one file. Defaults: `intervalGrowthFactor: 2.3` and an
`initialReviewInterval` of five days. On Remembered (or Skipped) the next
interval is max(initial, floor(actualElapsed × 2.3)), using the interval that
actually elapsed rather than the scheduled one; on Forgotten the interval is
divided by 2.3, floored at the initial interval, and the prompt is re-queued
in about ten minutes; a jitter of up to ten minutes prevents fixed ordering.
A source comment records the design stance: "if they do an early review, and
forget, should we 'penalize' them? In principle, they've demonstrated that
they aren't able to retain the detail across that span. … But in practice, I
suspect this would mostly be annoying"
([spacedRepetitionScheduler.ts](https://github.com/andymatuschak/orbit/blob/master/packages/core/src/schedulers/spacedRepetitionScheduler.ts)).
Quantum Country's published schedule has the same shape: "in-text," then "five
days, if the user remembers the answer … from five days to two weeks, then a
month, and so on. After just five successful reviews the interval is at four
months. If the user doesn't remember at any point, the time interval drops
down one level, e.g., from two weeks to five days"; the first interval was
raised to five days late in the essay's life, "For most of Quantum Country's
history the review schedule was more conservative"
([numinous.productions/ttft](https://numinous.productions/ttft/)).
Matuschak's working notes, from "a couple years of data," conclude that
letting forgotten prompts step back rather than reset was "pretty clearly a
mistake," that "recall rates fall with each repetition since the lapse," and
that a constant 2.3 factor "is too large for prompts that have been
forgotten"; a proposed fix reduces ease by 25% per lapse and recovers it at
0.2 per success
([forgotten prompts, next day](https://notes.andymatuschak.org/zVdX3T4ZCsgeHa3nsd5sKZD);
[smaller future intervals](https://notes.andymatuschak.org/zWCjuY1mFfjVkj5D58Mpte8)).
Orbit's docs scope the scheduler: "The current prompt type is meant for
memory practice. The existing prompt interface and scheduler are tuned to
questions which help people remember and internalize what they read"
([docs.withorbit.com](https://docs.withorbit.com/); agent-reported).

Orbit's data model is the one scheduler here with an explicit notion of an
item's source. A task has a `spec` (content), a `provenance` — an
`identifier` "representing a source which tasks might share," optional `url`,
`title`, `containerTitle`, and W3C-annotation-style `selectors` (range, text
position, text quote, XPath) locating the prompt in its source — and
per-component scheduling state; events include `TaskUpdateSpecEvent`,
`TaskUpdateProvenanceEvent`, and `TaskUpdateDeleted`, and the spec-update
reducer is `{ ...oldSnapshot, spec: event.spec }`, replacing content and
leaving scheduling untouched
([task.ts](https://github.com/andymatuschak/orbit/blob/master/packages/core/src/entities/task.ts),
[event.ts](https://github.com/andymatuschak/orbit/blob/master/packages/core/src/event.ts),
[taskReducers.ts](https://github.com/andymatuschak/orbit/blob/master/packages/core/src/eventReducers/taskReducers.ts)).
How that interacts with prompt identity is under
[Item invalidation and drift](#item-invalidation-and-drift).

### Execute Program (Bernhardt)

Execute Program's explanatory pages are client-rendered and return no text
to a non-browser fetch of the HTML, but the page copy is compiled into the
lazy-loaded chunk `dist/spaced-repetition-BPEUNIC4.js` referenced from the
app bundle, from which the rules were read on 2026-09-13
([executeprogram.com/spaced-repetition](https://www.executeprogram.com/spaced-repetition)):
"Our reviews come in four delay levels … subjectively aligned to day/week/month
boundaries: 2 days, 1 week, 3 weeks, and 2 months. If you're punctual and do
your reviews as soon as they become available, and you succeed at all of them,
then you'll completely finish an item's reviews after 90 days (2+7+21+60). You
only did five reviews of that item"; "There's also a "zeroth" level with a
1-day delay, but you'll only see that if you choose to "give up" on a review";
there is no level 5 because "by
that point you're either using the tool that you learned in a real system, or
else you've abandoned it"; on a wrong answer "we halve the item's level"; the
page's appendix gives the generating function `2.718 ** (level - 1)` days,
rounded "to 2, 7, 14, and 60 days" (the prose says 3 weeks; the page is
internally inconsistent on the third interval), replacing "an earlier version
of this system [that] used 1, 4, 16, and 64 days"; lessons unlock from the
dependency graph "combined with your review performance"; answers are checked
automatically and "some common mistakes like syntax errors" are not penalised
(added 2026-09-13; the section previously relied on secondary sources only).
The rules were earlier recorded from Bernhardt's own HN description (above,
under Prior attempts) and from Matuschak's first-hand notes on the product,
which agree with the page: "Lessons don't unlock until you've successfully
reviewed their prerequisites"; "Lessons assume solid recall of prior
material"; missed answers "don't penalize the student unless they 'give
up'"; the progress mechanics "emphasize completing new lessons over
increasing recall duration"; prompts act "both as application prompts and
recall prompts"; the system "doesn't have non-executable prompts"
([notes.andymatuschak.org/z2LGZ8…](https://notes.andymatuschak.org/z2LGZ8cXBcQMP7YuAHbeVyCSLZoiMXvQNKCok)).
A user report describes a fourth success at day 64 after which an item is not
shown again and notes that "related reviews all come on the same day, which
makes them artificially easy"
([mike.place/2020/executeprogram](https://mike.place/2020/executeprogram/);
secondary — its day-64 fourth success matches the earlier 1/4/16/64 schedule
the page describes). The interval table is now from the primary page (above).

### Shared assumptions, as stated or implied

- Atomicity: SM-2's first step is to split knowledge into the smallest
  possible items; Matuschak's guide asks for "focused" and "precise" prompts;
  FSRS attaches one (D, S, R) state to one card.
- Stability of ground truth: no scheduler document models the answer
  changing. SM-2's guide treats it as a formulation problem (date-stamp,
  source, edit, "re-memorize"); Anki decouples content edits from memory
  state; Orbit records provenance and allows spec replacement but leaves the
  judgement to the author.
- Discreteness and re-testability: every scheduler learns only from a
  per-review grade on a re-askable prompt; the FSRS benchmark's ground truth
  is the next grade.
- Independence: each item is scheduled from its own history. Wozniak's rules
  on interference, Anki's sibling burying, and the Bjork lab's
  retrieval-induced forgetting all acknowledge that memories interact; the
  schedulers model none of it beyond burying siblings.
- Retention as objective: Anki/FSRS target a recall probability at due time;
  Orbit and the ttft essay measure demonstrated retention. Matuschak's note
  "Conceptual information may have much slower optimal spaced repetition
  schedules" observes that "almost all the prior literature on the spacing
  effect and on naturalistic applications" concerns declarative items such
  as definitions and word pairs, and that Quantum Country's interconnected
  conceptual material shows slower forgetting than that literature
  ([notes.andymatuschak.org](https://notes.andymatuschak.org/Conceptual_information_may_have_much_slower_optimal_spaced_repetition_schedules)).

## Item invalidation and drift

Three families of mechanism exist for a learned or written fact ceasing to
hold: identity rules in SRS tools, verification of documentation against
code, and expiry in knowledge bases. No source found connects any of them to
review scheduling.

### SRS tools: what an edit does

- **Anki**: identity is the note/card ID; edits are invisible to the
  scheduler (above). Suspend hides a card "until they are manually
  unsuspended"; flags add "a colored marker"; Reset preserves history
  ([studying](https://docs.ankiweb.net/studying.html),
  [browsing](https://docs.ankiweb.net/browsing.html)).
- **SuperMemo**: rule 19 date-stamping and "re-memorize" (above); Forget
  "removes the displayed element from the learning process and puts it at
  the end of the pending queue, whereas Dismiss completely removes it"
  ([supermemopedia](https://supermemopedia.com/wiki/Use_Forget,_not_Dismiss,_on_items_that_you_will_want_to_learn_in_the_future);
  agent-reported; help.supermemo.org returned 403).
- **RemNote** is the one vendor document that names content change as a
  reset trigger: "If you make major changes to the content of a card, the
  previous scheduling history may no longer give an accurate picture of how
  well you know the card. You can reset the card to start it over"; reset is
  manual, and "The previous entries are retained for analytics purposes"
  ([help.remnote.com](https://help.remnote.com/en/articles/7230389-resetting-flashcard-scheduling)).
- **Mochi**: history per card, manual reset, archive keeps "content,
  metadata, and history"; editing not addressed
  ([mochi.cards/docs/cards](https://mochi.cards/docs/cards/); agent-reported).
- **Obsidian Spaced Repetition** stores schedule state "in an HTML comment
  for that card … `<!--SR:!2024-08-16,51,230-->` … on the line following the
  card text"; identity is therefore positional — editing the text leaves the
  schedule, deleting the comment makes the card new
  ([data-storage.md](https://github.com/st3v3nmw/obsidian-spaced-repetition/blob/main/docs/docs/en/data-storage.md)).
- **Orbit** has two identity paths. Embedded prompts: "We generate consistent
  IDs for embedded attachments and tasks based on their content (URL and
  TaskSpec JSON data). With this strategy, a user can read an article on
  multiple machines without acquiring duplicate prompts" —
  `generateTaskIDForSpec` is a UUIDv5 over the stably-serialised spec, so an
  author's edit yields a new task and orphans readers' state on the old one
  ([extractItems.ts](https://github.com/andymatuschak/orbit/blob/master/packages/web-component/src/extractItems.ts)).
  Markdown-note ingestion: item identifier is `this._hasher.hash(spec)`; the
  ingester diffs a source's items by identifier, treating an edited prompt
  as a delete plus a new task, and comments: "if you add the prompt back,
  it'll end up creating a new Task in the database. In the future we should
  consider just marking the deleted task as undeleted in those cases, to
  preserve continuous review history"; provenance updates are a `TODO`
  ([MarkdownInterpreter.ts](https://github.com/andymatuschak/orbit/blob/master/packages/interpreter/src/interpreters/markdown/MarkdownInterpreter.ts),
  [ingest.ts](https://github.com/andymatuschak/orbit/blob/master/packages/ingester/src/ingest.ts)).
  Matuschak states the consequence for his own notes: "if you modify a
  prompt's text, it will be treated as a new prompt, and your review history
  won't be ported from the old prompt. That's because this system's based on
  dumb plaintext files, which don't have enough semantic structure to
  unambiguously specify whether a given modification represents a new prompt
  or a modification of an old one. Fixing this would require introducing
  heuristics or extra identifying markup"
  ([My implementation of a personal mnemonic medium](https://notes.andymatuschak.org/My_implementation_of_a_personal_mnemonic_medium)).
  Hashcards makes the same choice explicit: "a card's progress is reset when
  the card is edited"
  ([github.com/eudoxia0/hashcards](https://github.com/eudoxia0/hashcards)).
- **Matuschak's prompt guide**, "Revising prompts over time": "Problems may
  become apparent only upon review, and sometimes only once a prompt's
  repetition interval has grown to many months. Prompt-writing involves long
  feedback loops"; "most spaced repetition interfaces treat each prompt as a
  sovereign unit, which makes this kind of high-level revision difficult";
  "most of the time the correct way to revise such prompts is to delete
  them." No section addresses prompts becoming factually false
  ([andymatuschak.org/prompts](https://andymatuschak.org/prompts/)).

The pattern across SRS tools: identity is either opaque (Anki, Mochi,
RemNote; edit keeps state, reset is manual) or content-derived (Orbit,
Hashcards, Matuschak's notes; edit resets state by construction). Neither
detects that the world changed; both wait for the author to change the text.

### Documentation verified against code

- **Swimm** binds documentation to source by path, line, and token:
  `<SwmSnippet path="/src/Polly/Policy.HandleSyntax.cs" line="10">` wraps
  the literal code lines in a `.sw.md` file
  ([swimmio/DEMO-Polly](https://github.com/swimmio/DEMO-Polly/blob/main/.swm/overview-of-the-policy-class.0o2qm.sw.md)).
  On change: "If Auto-sync decides that a change is impactful enough that
  Swimm oversight is needed … The Swimm verification check will fail.
  Depending on your configuration, this means it will block the commit or
  pull request until the issue is fixed, or it will open an issue that needs
  to be resolved within a certain time frame. Any affected documentation
  will be marked as potentially out of date and you will be notified"
  ([docs.swimm.io, Auto-sync](https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/));
  the verify action requires `fetch-depth: 0` because "pulling the commits
  history is required for the verification to function properly"
  ([swimm-verify-action](https://github.com/swimmio/swimm-verify-action)).
  This is the most developed change-detection mechanism found: unit = snippet
  or token, detection = git history plus content match, outcome = a failing
  check and an "out of date" mark. It is attached to a document, never to a
  person's memory.
- **Doctests** make the example the unit and execution the check. Python:
  doctest "executes those sessions to verify that they work exactly as
  shown" and is "serious about requiring exact matches in expected output"
  ([docs.python.org](https://docs.python.org/3/library/doctest.html)); Rust:
  "This makes sure that examples within your documentation are up to date
  and working," with `ignore`, `no_run`, `should_panic`, `compile_fail`
  escapes ([rustdoc](https://doc.rust-lang.org/rustdoc/write-documentation/documentation-tests.html));
  Go: "Having executable documentation for a package guarantees that the
  information will not go out of date as the API changes"
  ([go.dev/blog/examples](https://go.dev/blog/examples)); Elixir doctests
  are "not recommended when your code examples contain side effects"
  ([ExUnit.DocTest](https://ex-unit.hexdocs.pm/ExUnit.DocTest.html);
  agent-reported).
- **Docs as Tests** (Silva): "a strategy that keeps your docs in sync with
  your product. It's a way to test your docs, just like engineers test their
  code" ([docsastests.com](https://www.docsastests.com/)); Doc Detective
  "scans commands, code blocks, and examples" and "continuously verifies them
  by running real checks against real systems"
  ([docs.doc-detective.com](https://docs.doc-detective.com/)).
- **Include and snippet tools** re-read a line range or marker at build time
  and fail only when the marker vanishes: Sphinx `literalinclude` with
  `:lines:`, `:start-after:`, `:pyobject:`
  ([sphinx-doc.org](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html));
  pymdownx Snippets with `check_paths` to "Make the build fail if a snippet
  can't be found"
  ([pymdown-extensions](https://facelessuser.github.io/pymdown-extensions/extensions/snippets/));
  cog's `--check`, "Check that the files would not change if run again," and
  `-c` checksums "to protect it against accidental change"
  ([cog.readthedocs.io](https://cog.readthedocs.io/en/latest/running.html));
  embedme's `--verify`
  ([github.com/zakhenry/embedme](https://github.com/zakhenry/embedme)).
  Sphinx's `versionadded` / `versionchanged` / `deprecated` directives are
  manual version-stamping of the kind Wozniak's rule 19 prescribes.
- **Literate programming**: Knuth's WEB generates program and documentation
  "from the same source, so they are consistent with each other"; change
  files are content-matched, and "An error message is given if the m lines
  replaced did not match x1 … xm perfectly"
  ([knuthweb.pdf](http://www.literateprogramming.com/knuthweb.pdf);
  agent-reported). Org-babel's `:comments link` and `org-babel-detangle`
  propagate edits back by link comments; no staleness detection
  ([orgmode.org](https://orgmode.org/manual/Extracting-Source-Code.html)).
- **Freshness dates**: "At Google, we often attach 'freshness dates' to
  documentation. Such documents note the last time a document was reviewed,
  and metadata in the documentation set will send email reminders when the
  document hasn't been touched in, for example, three months"; a byline of
  "Last reviewed by…" "led to increased adoption"
  ([Software Engineering at Google, ch. 10](https://abseil.io/resources/swe-book/html/ch10.html)).
  This is a time-based re-verification schedule on a document, with a
  person, not a memory model, as the thing that decays.

### Comment and decision staleness

Comment–code inconsistency detection is a research line with just-in-time
variants: Liu et al. 2018 detect "the comments that should be changed during
code changes" from 64 features of code before and after, with "74.6% of
outdated comments" detected
([doi:10.1109/compsac.2018.00028](https://doi.org/10.1109/compsac.2018.00028));
CUP (ASE 2020) generates "a new comment based on its corresponding old
comment and code change" from 108K co-change samples
([doi:10.1145/3324884.3416581](https://doi.org/10.1145/3324884.3416581));
Panthaplackel et al. (AAAI 2021) "detect whether a comment becomes
inconsistent as a result of changes to the corresponding body of code …
before they are committed"
([doi:10.1609/aaai.v35i1.16119](https://doi.org/10.1609/aaai.v35i1.16119))
(all agent-reported from abstracts). For decisions, Nygard's ADR statuses
carry obsolescence explicitly: "If a later ADR changes or reverses a
decision, it may be marked as 'deprecated' or 'superseded' with a reference
to its replacement"; "we will keep the old one around, but mark it as
superseded"
([cognitect.com](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions);
MADR status line at [adr.github.io/madr](https://adr.github.io/madr/)).

### Knowledge bases with expiring verification

Guru: "Every Guru Card has a designated verifier"; a "Verification/Expiration
date – when the Card will become unverified"; intervals "every 30 days, 90
days, or 'Does not expire'"; "If someone edits a Card but is not the named
verifier … the Card will become unverified and trigger a verification
request"
([help.getguru.com](https://help.getguru.com/docs/verifying-and-unverifying-cards)).
Notion: a page owner can "verify the page until a specific time or
indefinitely"; "Once verification expires, page owners will be notified to
re-verify the page"
([notion.com/help](https://www.notion.com/help/wikis-and-verified-pages);
agent-reported). Slab: verifiers "choose the frequency of review"; on expiry
"the banner will turn yellow"; "if any edits have been made to the post since
the last verification, the changes will be highlighted"
([help.slab.com](https://help.slab.com/en/articles/4136379-post-verification);
agent-reported). These are re-verification schedules with a fixed interval
and an edit trigger, applied to a document and its owner.

### Who has connected change detection to review scheduling

No one found. The closest sources model the *decay of a person's knowledge of
code* rather than the scheduling of its review:

- Fritz, Ou, Murphy, and Murphy-Hill's degree-of-knowledge model (ICSE 2010)
  combines authorship and interaction: DOK = 3.293 + 1.098·FA + 0.164·DL −
  0.321·ln(1+AC) + 0.19·ln(1+DOI), where FA is first authorship, DL the
  developer's deliveries, AC "acceptances, representing changes to the
  element not completed by D," and DOI a Mylyn degree-of-interest that
  "rises with each interaction the developer has with the element and
  decays as the programmer interacts with other elements"
  ([icse10_dok_web.pdf](https://www.cs.ubc.ca/~fritz/papers/icse10_dok_web.pdf)).
  Others' changes lower one's knowledge logarithmically; decay is driven by
  interaction, not the clock; nothing is scheduled. Detail under
  [Mastery and coverage models](#mastery-and-coverage-models).
- Krüger, Wiemann, Fenske, Saake, and Leich, "Do you remember this source
  code?" (ICSE 2018): a survey of 60 open-source developers against their
  version-control data; "forgetting is an important factor when considering
  familiarity and program comprehension of developers. We find that a
  forgetting curve is partly applicable for software development,
  investigate three factors - the number of edits, ratio of owned code, and
  tracking behavior - that can impact familiarity with code, and derive a
  general memory strength for our participants"
  ([doi:10.1145/3180155.3180215](https://doi.org/10.1145/3180155.3180215);
  abstract via OpenAlex). Follow-ups on recency and frequency of interaction
  and on activity breaks are agent-reported
  ([arXiv:2204.07669](https://arxiv.org/abs/2204.07669),
  [arXiv:2305.00760](https://arxiv.org/abs/2305.00760)); none proposes
  scheduling.
- Wozniak's programming article (1993) is the only SRS source that measures
  attrition of programming items and states the consequence: items lose
  applicability within 1–3 years and must be turned over (above).

## Mastery and coverage models

For each: unit tracked, how mastery is estimated, whether it is tied to
repository structure, and whether it decays or is invalidated.

### Agent skills

- **Learning Opportunities** keeps no mastery record. A research agent read
  the whole repository and its 64-commit history: the word "journal" occurs
  only in citation titles; the only persisted state is the auto-plugin's
  per-session offer counter ("Stop after 2 offers per session"; a
  post-tool-use hook that fires after a `git commit` and injects "consider
  whether this is a good moment to offer a learning exercise … If they
  decline, note it — no more offers this session") and `orient`'s generated
  `orientation.md` (purpose, pipeline stages, key files, core concepts,
  gotchas, "Suggested exercise sequence"), written "to the project level."
  Difficulty adjusts qualitatively ("if they're nailing predictions,
  increase complexity; if they're struggling, narrow scope"). The learning
  science cited spans Bjork, Dunlosky, Kornell, Roediger and Karpicke,
  Rohrer and Taylor, Soderstrom and Bjork, Sweller and Cooper, Kalyuga, and
  the authors' own AI Skill Threat work; PRINCIPLES.md's "Spacing Effect"
  section applies it as "Retrieval check-ins at the start of sessions. Return
  to the same learning area at multiple times during a project." Outcome
  claims: none for the skill; MEASURE-THIS.md supplies a pre/post survey and
  warns "Absence of measurable change is not evidence of absence of impact"
  ([SKILL.md](https://github.com/DrCatHicks/learning-opportunities/blob/main/learning-opportunities/skills/learning-opportunities/SKILL.md),
  [post-tool-use.sh](https://github.com/DrCatHicks/learning-opportunities/blob/main/learning-opportunities-auto/hooks/post-tool-use.sh),
  [MEASURE-THIS.md](https://github.com/DrCatHicks/learning-opportunities/blob/main/learning-opportunities/docs/MEASURE-THIS.md)).
  Phase A's landscape entry attributes "spaced repetition" to this skill and
  its Dead ends attribute the per-user journal to learn-codebase; the task
  brief for this pass conflated the two. The journal is learn-codebase's.
- **learn-codebase**: unit = named concept; estimate = the tutoring model's
  reading of answers plus hint count; per-project journal; fixed review
  ladder; no decay or edit trigger (above).
- **codequiz**: unit = top-level directory; estimate = rule-updated
  confidence from graded answers; per-user-per-repo JSON; interval by
  confidence band; no decay or edit trigger (above).
- **cdebt**: unit = file; estimate = graded free-text explanation; no decay
  documented (above).

### Knowledge tracing

- **Bayesian Knowledge Tracing** (Corbett and Anderson 1995, *UMUAI*
  4:253–278, [doi:10.1007/BF01099821](https://doi.org/10.1007/BF01099821);
  author PDF at
  [act-r.psy.cmu.edu](http://act-r.psy.cmu.edu/wordpress/wp-content/uploads/2012/12/893CorbettAnderson1995.pdf),
  scanned; quotations read from page images by a research agent). Unit: a
  production rule in the ACT-R "ideal student model" — "ACT-R assumes that
  procedural knowledge can be represented as a set of independent production
  rules." "Knowledge tracing assumes a two-state learning model. Each coding
  rule is either in the learned state or in the unlearned state. … There is
  no forgetting; rules do not make the transition in the other direction."
  Four parameters per rule — initial learning, acquisition, guess, slip —
  "estimated empirically for each rule"; mastery is "a knowledge probability
  of 0.95." Items are binary, independent, and never forgotten.
- **Deep Knowledge Tracing** (Piech et al. 2015,
  [arXiv:1506.05908](https://arxiv.org/abs/1506.05908)) characterises BKT
  as assuming "that once a skill is learned it is never forgotten" and that
  "the meaning of the hidden variables and their mappings onto exercises can
  be ambiguous, rarely meeting the model's expectation of a single concept
  per exercise"; its input is a one-hot (exercise, correct) tuple and it "does
  not need expert annotations"; forgetting is not modelled explicitly
  (agent-verified from the PDF).
- **Knowledge component** (LearnLab): "a description of a mental structure
  or process that a learner uses, alone or in combination with other
  knowledge components, to accomplish steps in a task or a problem … a
  generalization of everyday terms like concept, principle, fact, or skill"
  ([learnlab.org wiki](https://learnlab.org/wiki/index.php?title=Knowledge_component)).
- **Half-life regression** (Settles and Meeder, ACL 2016,
  [aclanthology.org/P16-1174](https://aclanthology.org/P16-1174.pdf)):
  "the Ebbinghaus model, also known as the forgetting curve," p = 2^(−Δ/h),
  with half-life ĥ = 2^(Θ·x) fitted from per-(student, lexeme) counters of
  exposures, correct, and incorrect recalls plus per-lexeme difficulty
  indicators; "reducing error by 45%+ compared to several baselines." Items
  are words; each trace is fitted independently.
- **Khan Academy mastery levels** are per skill (an exercise): Attempted
  (<70%), Familiar (70–99%), Proficient (100%, or Familiar plus correct
  answers on a mixed-skill assessment), Mastered (Proficient plus correct on
  a Mastery Challenge); levels move down on misses, so invalidation is
  performance-triggered, not time-triggered
  ([support.khanacademy.org, article 5548760867853](https://support.khanacademy.org/hc/en-us/articles/5548760867853);
  agent-read via the Zendesk API; the page returns 403 to a plain fetch).

What this family assumes: a fixed inventory of items, each mapped to
exercises, with mastery a monotone or slowly-decaying function of
performance. None models the item itself changing.

### Expertise location tied to repository structure

- **Expertise Browser** (Mockus and Herbsleb, ICSE 2002): "The simplest unit
  of experience that could be observed in projects using change management
  systems is the atomic change (delta)"; experience "in a file, module, or
  area of functionality" is a count of such atoms; "One can also identify
  current experience, by restricting domain experience to a specified
  (recent) period of time" — windowing, not decay
  ([mockus-expertise-2002.pdf](https://herbsleb.org/web-pubs/pdfs/mockus-expertise-2002.pdf)).
- **Degree-of-knowledge** (Fritz et al.): unit = source-code element;
  estimate = the DOK regression above, with first authorship the strongest
  term, others' acceptances negative, and interaction-driven DOI; the ICSE
  2010 case study recommends "changes of interest" to a developer when the
  changed elements carry positive DOK — a change-to-attention link without a
  schedule
  ([icse10_dok_web.pdf](https://www.cs.ubc.ca/~fritz/papers/icse10_dok_web.pdf);
  TOSEM 2014 extension
  [doi:10.1145/2512207](https://doi.org/10.1145/2512207), abstract only).
- **Usage expertise** (Schuler and Zimmermann, MSR 2008): unit = method;
  "Developers also accumulate expertise by calling (using) methods"; no decay
  ([schuler-msr-2008.pdf](https://thomas-zimmermann.com/publications/files/schuler-msr-2008.pdf)).
- **Truck factor** (Avelino et al., ICPC 2016): reuses the DOA weights
  ("k = 0.75 and m = 3.293"); "65% [of 133 GitHub systems] have TF ≤ 2"
  ([arXiv:1604.06766](https://arxiv.org/abs/1604.06766)).
- **CodeScene**: "The knowledge metrics are based on the amount of code each
  developer has contributed. CodeScene looks at the deep history of each
  file … Even if one developer completely rewrites a piece of code, its
  original author will still retain some knowledge in that area"; "Code
  familiarity describes how much of the codebase is known by the current
  team"; "Knowledge islands … known only by a single developer"; "Knowledge
  loss represents code that is written by a developer who is no longer part
  of your organization"
  ([codescene.io docs](https://codescene.io/docs/guides/social/knowledge-distribution.html)).
  Unit = file/module; invalidation by marking a developer as departed.
- **CODEOWNERS**: "Code owners are automatically requested for review when
  someone opens a pull request that modifies code that they own"; a declared
  glob-to-handle map; no estimation, no decay
  ([docs.github.com](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)).
- **Wheeler 2026** argues the whole family "rest[s] on one inference — that
  authoring a region of code is evidence of understanding it" and that "AI
  code generation severs that inference at its root"
  ([arXiv:2606.20882](https://arxiv.org/abs/2606.20882); position paper, in
  Phase A).

Across this family the unit is a repository element and the estimator is
authorship or interaction; the only tool that estimates from demonstrated
understanding rather than footprint is cdebt, and the only one that both
estimates from answers and schedules by repository unit is codequiz.

## What would be retrieved

The evidence note characterises the object at risk as a layered model whose
program layer is recoverable from text, whose situation layer (world mapping,
function, data flow) is what modification depends on, and whose rationale is
largely undocumented and socially held
([evidence-and-mechanisms.md](evidence-and-mechanisms.md#program-comprehension-what-a-mental-model-of-code-consists-of));
Naur adds the world-to-code mapping, the justification for each part, and the
capacity to answer a modification demand
([evidence-and-mechanisms.md, "Naur"](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text)).
The sources below turn that content into question types.

**Empirical question catalogues.** Sillito, Murphy, and De Volder observed
newcomers on a ~20,000-line code base and industrial programmers on their own
code and catalogued "44 different kinds of questions asked by our
participants" in four categories: finding initial focus points ("Which type
represents this domain concept or this UI element?", "Is there a precedent or
exemplar for this?"); building on those points ("Where is this method called
or type referenced?", "What are the arguments to this function?");
understanding a subgraph ("How are these types or objects related?
(whole-part)", "How is this feature or concern … implemented?", "How is
control getting (from here to) here?", "What is the 'correct' way to use or
access this data structure?"); and questions over groups of subgraphs ("How
does the system behavior vary over these types or cases?", "What will be the
total impact of this change?"). Participants also asked for the reasoning
behind a decomposition ("why they're doing that")
(FSE 2006, [doi:10.1145/1181775.1181779](https://doi.org/10.1145/1181775.1181779);
author PDF at
[cs.ubc.ca](https://www.cs.ubc.ca/~murphy/papers/other/asking-answering-fse06.pdf);
extended in *IEEE TSE* 34(4):434–451, 2008,
[doi:10.1109/TSE.2008.26](https://doi.org/10.1109/TSE.2008.26)). Letovsky's
"why", "how", and "what" conjectures and the LaToza, Venolia, DeLine and Ko
et al. findings that rationale is the need most often unmet are in Phase A.
LaToza and Myers' "Hard-to-answer questions about code" (PLATEAU 2010,
[doi:10.1145/1937117.1937125](https://doi.org/10.1145/1937117.1937125); PDF
at [plateau10-latoza.pdf](https://ecs.victoria.ac.nz/twiki/pub/Events/PLATEAU/2010Program/plateau10-latoza.pdf),
linked from Brad Myers' publication list) is the direct follow-up on which
questions are hardest: 179 respondents reported 371 questions, clustered into
21 categories and 94 distinct questions, and "the most frequently reported
categories dealt with intent and rationale – what does this code do, what is
it intended to do, and why was it done this way?" (updated 2026-09-13; the
full text was previously unretrievable — see
[track-explorable-maps.md](track-explorable-maps.md#evidence) for the entry).

**Rationale as a first-class record.** Nygard: "One of the hardest things to
track during the life of a project is the motivation behind certain
decisions"; without it a newcomer can only "Blindly accept the decision" or
"Blindly change it"; an ADR has Title, Context ("the forces at play"),
Decision, Status, Consequences, and a superseded record stays because "It's
still relevant to know that it *was* the decision, but is *no longer* the
decision"
([cognitect.com](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)).
The ADR is a rationale item with an explicit obsolescence state — the
property no card scheduler has. cdebt's `repay` generates an ADR draft plus
three questions per file, the one tool found that pairs the two.

**Question types from the prompt-writing literature.** Matuschak's guide
lists five properties of a retrieval prompt — focused, precise, "consistent"
(the same answer over time, to avoid interference), "tractable" ("You should
strive to write prompts which you can almost always answer correctly"), and
"effortful" — and a taxonomy by knowledge type: factual (facts, closed and
open lists, cues), procedural (keywords for verbs, conditions, and timing),
and conceptual through five lenses: attributes and tendencies, similarities
and differences, parts and wholes, causes and effects, significance and
implications; plus "salience prompts" and creative prompts ("give an answer
you haven't given before"). The guide "contains no discussion of learning
codebases, APIs, or programming"
([andymatuschak.org/prompts](https://andymatuschak.org/prompts/)). Read
against the comprehension literature, the conceptual lenses map onto the
situation and rationale layers (parts/wholes ↔ decomposition; causes/effects
↔ data and control flow; significance ↔ why it is here), and "consistent" is
the property a changing codebase breaks.

**Question types in the shipping skills.** codequiz's three types — "Explain
This," "What Happens When," "Connect the Dots" — correspond to EiPE purpose
questions, tracing, and subgraph questions; learn-codebase's QUESTION-PATTERNS
are "Prediction," "Trace," "Design Reasoning," "Comparison," "Error
Prediction" (agent-reported from the repository); Learning Opportunities'
elaborative interrogation asks "Why did we structure it this way rather than
[alternative]?" and "How would this behave differently if [condition
changed]?"; cdebt grades a free-text explanation by whether it names "the
file's actual identifiers." None of the four documents a mapping from the
comprehension literature; the correspondence is this note's observation.

**Computing-education instruments.** EiPE purpose questions, tracing, and
Parsons problems are the validated instruments for the program and situation
layers; Smith and Zilles' code-generation-based grading makes an EiPE answer
machine-checkable by regenerating code from it
([evidence-and-mechanisms.md](evidence-and-mechanisms.md#computing-education-evidence-on-reading-code);
[landscape-sweep.md](landscape-sweep.md#cluster-1--retrieval-practice-and-socratic-tutoring-in-the-agent-loop)).
All were validated on course-sized programs; none was found applied to a
repository a person maintains.

**Wozniak's selection rule.** The 1993 article's memorization criterion — an
item is worth learning when time gained by not looking it up exceeds time
lost to reviewing it — and its inventory of what programmers should hold
("tips, observations, and experimental findings not included in the
documentation") is the only source that states a selection criterion for
programming items
([programming.htm](https://super-memory.com/articles/programming.htm)).
Nielsen's version is "only Ankify material I know I'll need repeatedly"
([ltm.html](http://augmentingcognition.com/ltm.html)).

## Evidence

Phase A established the mechanism base: retrieval practice g≈0.50–0.61,
spacing meta-analytic, both on declarative or problem-solving material, with
no study on retaining a model of an evolving codebase
([evidence-and-mechanisms.md, "Summary table"](evidence-and-mechanisms.md#summary-table)).
This section adds what the sources say about spacing and retrieval on
procedural and conceptual knowledge, naturalistic data from embedded SRS,
and knowledge that changes.

**Spacing on procedural and applied knowledge (for).**

- Moulton et al., *Annals of Surgery* 244(3):400–409 (2006): 38 junior
  surgical residents randomised to massed (one day) or distributed (weekly)
  practice of microvascular anastomosis with equal practice time; "the
  distributed group performed significantly better on the retention test in
  most outcome measures … [and] also outperformed the massed group on the
  live rat anastomosis in all expert-based measures"
  ([doi:10.1097/01.sla.0000234808.85789.6a](https://doi.org/10.1097/01.sla.0000234808.85789.6a);
  abstract via PubMed 16926566).
- Kerfoot et al., *Medical Education* 41:23–31 (2007): randomised trial of
  "spaced education," "weekly e-mailed case scenarios and clinical
  questions," on retention by third-year medical students
  ([doi:10.1111/j.1365-2929.2006.02644.x](https://doi.org/10.1111/j.1365-2929.2006.02644.x);
  record and abstract via Crossref; results not extracted).
- Rohrer and Taylor: distributed practice improved retention of mathematics
  and shuffling problem types improved learning (*Applied Cognitive
  Psychology* 20:1209–1224, 2006,
  [doi:10.1002/acp.1266](https://doi.org/10.1002/acp.1266); *Instructional
  Science* 35:481–498, 2007,
  [doi:10.1007/s11251-007-9015-8](https://doi.org/10.1007/s11251-007-9015-8);
  records confirmed only).
- Kornell and Bjork, *Psychological Science* 19(6):585–592 (2008), inductive
  category learning: "we expected spacing to hamper induction … Surprisingly,
  induction profited from spacing"
  ([doi:10.1111/j.1467-9280.2008.02127.x](https://doi.org/10.1111/j.1467-9280.2008.02127.x)).
- Rawson and Dunlosky, *JEP: General* 140(3):283–302 (2011): 533 students,
  conceptual material, over 100,000 hand-scored recall responses;
  "Relearning had pronounced effects on long-term retention with a relatively
  minimal cost"; prescription: "practice recalling concepts to an initial
  criterion of 3 correct recalls and then to relearn them 3 times at widely
  spaced intervals"
  ([doi:10.1037/a0023956](https://doi.org/10.1037/a0023956); abstract via
  PubMed 21707204).
- Computing education: YeckehZaare et al. (SIGCSE 2022) and Moraes et al.
  (2023) report grade gains from spaced retrieval quizzes in CS1
  ([doi:10.1145/3478431.3499408](https://doi.org/10.1145/3478431.3499408),
  [doi:10.1145/3629296.3629362](https://doi.org/10.1145/3629296.3629362);
  agent-reported; abstracts not retrieved here).

**Naturalistic data from embedded SRS (for, observational).** The ttft essay
reports that after six repetitions "most users are up around 6,000 days of
demonstrated retention. That means an average of about 6,000 / 112 ~ 54 days
per question," for "about 95 minutes of total review time" against a
four-hour read; in a two-week delayed-review experiment "accuracy dropped
from 91% (upon the initial read) to 87% (after two weeks)" for delayed users
while reviewers improved; the authors add that "memory is not an end-goal in
itself" and that memory systems "don't make it easy to decide what to
memorize"
([numinous.productions/ttft](https://numinous.productions/ttft/)). Orbit's
multi-year data concern lapse handling, not content change
([notes.andymatuschak.org](https://notes.andymatuschak.org/zVdX3T4ZCsgeHa3nsd5sKZD)).
Nielsen reports a personal collection whose "average interval between
reviews is currently 1.2 years, and rising" at "15 to 20 minutes per day"
([ltm.html](http://augmentingcognition.com/ltm.html); agent-quoted).

**Retrieval and knowledge that changes.** No source tests spaced retrieval on
items whose correct answer changes between reviews. The nearest laboratory
literature is on interference and updating:

- Barnes and Underwood, *J. Exp. Psychol.* 58(2):97–105 (1959), the A–B, A–C
  paradigm: learning a new response to an old cue impairs the old association
  ([doi:10.1037/h0047507](https://doi.org/10.1037/h0047507); record only).
- Potts and Shanks, *JEP: LMC* 38(6):1780–1785 (2012): English–Swahili pairs,
  then English–Finnish pairs "sharing the same cues"; "List 2 learning
  disrupted List 1 memory when there was no reminder test, but reminder
  testing immunized the memory against interference"
  ([doi:10.1037/a0028218](https://doi.org/10.1037/a0028218); abstract via
  PubMed 22686838). Read literally for a codebase: retrieving the old fact
  protects the old fact, the wrong direction once the fact has changed.
- Pastötter and Bäuml, *Frontiers in Psychology* 5:286 (2014), review of the
  forward effect of testing: "recall testing of previously studied
  information can enhance learning of subsequently presented new
  information," observed "for both veridical information and
  misinformation"
  ([doi:10.3389/fpsyg.2014.00286](https://doi.org/10.3389/fpsyg.2014.00286)).
- Butterfield and Metcalfe, *JEP: LMC* 27(6):1491–1494 (2001): "highly
  confident errors were the most likely to be corrected in a subsequent
  retest" — hypercorrection, the one result found in which discovering that a
  confidently held answer is wrong aids updating
  ([doi:10.1037/0278-7393.27.6.1491](https://doi.org/10.1037/0278-7393.27.6.1491);
  abstract via PubMed 11713883).
- Lewandowsky, Ecker, Seifert, Schwarz, and Cook, *PSPI* 13(3):106–131
  (2012), the continued influence of corrected misinformation
  ([doi:10.1177/1529100612451018](https://doi.org/10.1177/1529100612451018);
  record confirmed, full text 403).
- Anderson, Bjork, and Bjork, *JEP: LMC* 20(5):1063–1087 (1994),
  retrieval-induced forgetting: "the impaired access to non-retrieved items
  that share a cue with retrieved items" when "those associates compete
  during the retrieval attempt"
  ([doi:10.1037/0278-7393.20.5.1063](https://doi.org/10.1037/0278-7393.20.5.1063);
  [bjorklab.psych.ucla.edu/research](https://bjorklab.psych.ucla.edu/research/)).
  The same page states the New Theory of Disuse: storage strength, "how well
  learned something is," versus retrieval strength, "how accessible … at any
  given moment," with "the more RS that information has, the smaller the
  boost in SS as a consequence of restudy" (Bjork and Bjork 1992,
  [lab PDF](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/07/RBjork_EBjork_1992.pdf),
  scanned, not text-extracted).
- Krüger et al. (ICSE 2018), above: "a forgetting curve is partly applicable
  for software development," with edits, owned-code ratio, and tracking
  behaviour as factors — the one empirical study of forgetting code
  ([doi:10.1145/3180155.3180215](https://doi.org/10.1145/3180155.3180215)).

**Against, or limiting.**

- Matuschak's reading of the literature: nearly all spacing evidence is on
  declarative items; conceptual, interconnected material may need different
  schedules
  ([notes.andymatuschak.org](https://notes.andymatuschak.org/Conceptual_information_may_have_much_slower_optimal_spaced_repetition_schedules)).
- The FSRS benchmark's leaders are fitted to Anki review logs and evaluated
  on next-grade prediction; nothing in the corpus represents an item whose
  answer changed
  ([srs-benchmark](https://github.com/open-spaced-repetition/srs-benchmark)).
- Wozniak: for volatile knowledge "in most cases you will have to re-memorize
  knowledge that became outdated"
  ([twenty rules](https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge));
  programming items lose applicability within 1–3 years
  ([programming.htm](https://super-memory.com/articles/programming.htm)).
- Nielsen: cards "disconnected from my other interests" become "rather stale"
  within months; cards for an API no longer in use are deleted "when they
  come up"; the ttft essay warns against memorising a language "for just one
  small project"
  ([ltm.html](http://augmentingcognition.com/ltm.html),
  [ttft](https://numinous.productions/ttft/)).
- Litt's official talk page: "remembering an answer is not itself a guarantee
  of understanding or permanent retention"
  ([understanding-bottleneck-talk.md](understanding-bottleneck-talk.md#proposal-2-quizzes-as-a-speed-regulator)).
- Elhayany and Meinel's pilot of LLM-generated retrieval items reported
  "challenges in difficulty calibration and the accuracy of AI-generated
  feedback, particularly in code-focused tasks"
  ([doi:10.1109/democon65705.2025.11282675](https://doi.org/10.1109/democon65705.2025.11282675);
  agent-reported).

## Open questions in the sources

Stated by the sources themselves, not by this note.

- Matuschak: whether conceptual material follows the declarative spacing
  literature at all
  ([conceptual schedules](https://notes.andymatuschak.org/Conceptual_information_may_have_much_slower_optimal_spaced_repetition_schedules));
  how to handle "subsequent lapses beyond the first"
  ([next-day review](https://notes.andymatuschak.org/zVdX3T4ZCsgeHa3nsd5sKZD));
  how to revise prompts when "most spaced repetition interfaces treat each
  prompt as a sovereign unit"
  ([prompts](https://andymatuschak.org/prompts/)); and, for plaintext
  identity, "heuristics or extra identifying markup" to tell a modified prompt
  from a new one
  ([personal mnemonic medium](https://notes.andymatuschak.org/My_implementation_of_a_personal_mnemonic_medium)).
- Orbit's ingester: whether to mark deleted tasks as undeleted "to preserve
  continuous review history"; provenance updates are an open `TODO`
  ([ingest.ts](https://github.com/andymatuschak/orbit/blob/master/packages/ingester/src/ingest.ts)).
- Nielsen and Matuschak: "Memory systems don't make it easy to decide what to
  memorize"; whether recall translates into "creative problem-solving,
  problem-finding" ([ttft](https://numinous.productions/ttft/)). Nielsen:
  "it'd be good to better understand when the transfer [from declarative to
  procedural] works and when it doesn't"
  ([ltm.html](http://augmentingcognition.com/ltm.html)).
- Anki/FSRS: how to choose desired retention given the workload curve; the
  manual removed "Compute minimum recommended retention" in 25.07
  ([deck-options](https://docs.ankiweb.net/deck-options.html)).
- Krüger et al.: which forgetting curve applies to code and how edits,
  ownership, and tracking combine; their follow-ups are registered studies
  ([doi:10.1145/3180155.3180215](https://doi.org/10.1145/3180155.3180215)).
- Wheeler: whether authorship-derived metrics with low comprehension will
  show incident-resolution failures the metric cannot predict — a stated
  falsifiable prediction ([arXiv:2606.20882](https://arxiv.org/abs/2606.20882)).
- Learning Opportunities: how to measure effect; MEASURE-THIS.md says a flat
  survey result is not evidence of no effect
  ([MEASURE-THIS.md](https://github.com/DrCatHicks/learning-opportunities/blob/main/learning-opportunities/docs/MEASURE-THIS.md)).
- Wozniak (1993): how to keep turning over programming knowledge whose
  applicability lasts 1–3 years; he offers date-stamping and re-memorising,
  not a mechanism
  ([programming.htm](https://super-memory.com/articles/programming.htm)).

## Dead ends

- **Execute Program's own pages** (`/spaced-repetition`, `/why-ep`, FAQ,
  blog, and Wayback copies) are client-rendered; every non-browser fetch of
  the HTML returned only the page title. Resolved 2026-09-13: the page text is
  in the site's lazy-loaded JS chunk (`/dist/spaced-repetition-*.js`, linked
  from `/dist/app.*.js`), from which the interval table was verified (see
  [Execute Program (Bernhardt)](#execute-program-bernhardt)).
- **LaToza and Myers 2010**: ACM DL returned 403; the NatProg paper index
  has no copy; the file at the guessed name was a different paper. Resolved
  2026-09-13: Brad Myers' résumé publication list links the workshop's own
  copy at
  <https://ecs.victoria.ac.nz/twiki/pub/Events/PLATEAU/2010Program/plateau10-latoza.pdf>
  (six pages), from which the figures above were verified.
- **Bjork and Bjork 1992** and **Corbett and Anderson 1995**: author-hosted
  PDFs are scans without a text layer; quotations are from the lab's research
  page and from an agent's reading of page images respectively.
- **Fritz et al. TOSEM 2014** full text: not obtainable (ACM 403, no OA
  copy; re-checked 2026-09-13 — Unpaywall reports no open location, Fritz's
  UBC page lists it only as "submitted for ACM TOSEM (invited paper)", the
  UZH pages 404, and ZORA sits behind a bot challenge). The ICSE 2010 paper
  on the author's site — the full ten-page paper, not a two-page summary
  (corrected 2026-09-13) — supplied the formula, re-verified against its
  text.
- **Anki FSRS page** at `docs.ankiweb.net/fsrs.html` is 404; FSRS material is
  in `deck-options.html`. The original `fsrs4anki` wiki page redirects to the
  `awesome-fsrs` wiki.
- **SuperMemo Guru** and **help.supermemo.org** returned Cloudflare
  challenges; the SM-2 text and twenty rules were read from super-memory.com
  and supermemo.com. SuperMemo's behaviour on editing an item's content
  versus its interval is unverified.
- **Jack Kinsella's "Janki method"**: the original URL now serves unrelated
  UX content; Wayback returned only its shell. An agent's report that
  Kinsella and Sivers recommend deleting outdated cards was checked and is
  not supported by either page; Sivers' post says nothing on staleness, and
  Kinsella's could not be read.
- **Nielsen on codebases**: an agent's quotation "I've used Anki … to help me
  learn a new codebase quickly" does not appear in the essay; the verified
  passages are the API appendix and the "code I've personally written" line
  above.
- **Learning Opportunities' "journal"**: does not exist in any of the
  repository's 64 commits; the attribute belongs to learn-codebase.
- **Doculearn, exbrain.app, memorific.com, code-flashcards**: dead or empty.
  Doculearn was the only commit-driven flashcard generator found.
- **Orbit's docs** say nothing about prompt identity or author edits;
  behaviour was read from source. `docs.withorbit.com/embedding` is 404.
- **Swimm's blog post on Auto-sync** returned 403 here; its mechanism is
  cited from the docs page and the public demo repository instead.
- **Khan Academy's 2014 mastery post** was not located; the 2011 Hu post and
  current help articles were used (agent). The help centre returns 403 to a
  plain fetch.
- **Web search budget** for this session was exhausted early; discovery then
  relied on the GitHub API, HN Algolia, Crossref, OpenAlex, PubMed E-utilities,
  and direct fetches. Semantic Scholar rate-limited every query.
- **No source** connects git-diff or hash invalidation to a review schedule;
  no controlled study applies spaced retrieval to a real codebase; no
  "Anki for your codebase" tool exists by that or any name on GitHub, PyPI,
  or npm.

## References

Primary sources cited above, grouped. Phase A notes:
[understanding-bottleneck-talk.md](understanding-bottleneck-talk.md),
[evidence-and-mechanisms.md](evidence-and-mechanisms.md),
[landscape-sweep.md](landscape-sweep.md),
[answer-ai-sweep.md](answer-ai-sweep.md),
[solve-it-sweep.md](solve-it-sweep.md).

Schedulers and formulation guides: Wozniak, SM-2,
<https://super-memory.com/english/ol/sm2.htm>; Wozniak, Twenty rules,
<https://www.supermemo.com/en/blog/twenty-rules-of-formulating-knowledge>;
Wozniak, Spaced repetition to increase programmer productivity,
<https://super-memory.com/articles/programming.htm>; Anki manual,
<https://docs.ankiweb.net/deck-options.html>,
<https://docs.ankiweb.net/leeches.html>,
<https://docs.ankiweb.net/browsing.html>,
<https://docs.ankiweb.net/getting-started.html>,
<https://docs.ankiweb.net/importing/text-files.html>; FSRS wiki,
<https://github.com/open-spaced-repetition/awesome-fsrs/wiki/ABC-of-FSRS>,
<https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm>;
srs-benchmark, <https://github.com/open-spaced-repetition/srs-benchmark>;
Ye, Su, Cao 2022, <https://doi.org/10.1145/3534678.3539081>; Su et al. 2023,
<https://doi.org/10.1109/TKDE.2023.3251721>; Orbit,
<https://github.com/andymatuschak/orbit>; Matuschak notes,
<https://notes.andymatuschak.org/zVdX3T4ZCsgeHa3nsd5sKZD>,
<https://notes.andymatuschak.org/zWCjuY1mFfjVkj5D58Mpte8>,
<https://notes.andymatuschak.org/Conceptual_information_may_have_much_slower_optimal_spaced_repetition_schedules>,
<https://notes.andymatuschak.org/My_implementation_of_a_personal_mnemonic_medium>,
<https://notes.andymatuschak.org/z2LGZ8cXBcQMP7YuAHbeVyCSLZoiMXvQNKCok>;
Matuschak, How to write good prompts, <https://andymatuschak.org/prompts/>;
Matuschak and Nielsen, ttft, <https://numinous.productions/ttft/>; Nielsen,
Augmenting Long-term Memory, <http://augmentingcognition.com/ltm.html>;
Bernhardt on Execute Program, <https://news.ycombinator.com/item?id=26349754>;
Hashcards, <https://github.com/eudoxia0/hashcards>; RemNote,
<https://help.remnote.com/en/articles/7230389-resetting-flashcard-scheduling>;
Obsidian Spaced Repetition,
<https://github.com/st3v3nmw/obsidian-spaced-repetition/blob/main/docs/docs/en/data-storage.md>.

Tools on code: codequiz, <https://github.com/nessielabs/codequiz>;
comprehension-debt, <https://github.com/RonaldSit/comprehension-debt>;
learn-codebase, <https://github.com/ktaletsk/learn-codebase>; Learning
Opportunities, <https://github.com/DrCatHicks/learning-opportunities>;
Covate, <https://github.com/SunflowersLwtech/covate>; pr-quiz,
<https://github.com/dkamm/pr-quiz>; Doculearn,
<https://news.ycombinator.com/item?id=46400512>; exbrain,
<https://news.ycombinator.com/item?id=20024179>; Fata,
<https://news.ycombinator.com/item?id=48489163>; fastanki,
<https://github.com/AnswerDotAI/fastanki>; Sivers, <https://sivers.org/srs>;
Codecademy, <https://www.codecademy.com/article/spaced-repetition>; Henley et
al. 2021, <https://arxiv.org/abs/2102.06098>.

Invalidation and verification: Swimm,
<https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/>,
<https://github.com/swimmio/DEMO-Polly/blob/main/.swm/overview-of-the-policy-class.0o2qm.sw.md>,
<https://github.com/swimmio/swimm-verify-action>; Python doctest,
<https://docs.python.org/3/library/doctest.html>; rustdoc,
<https://doc.rust-lang.org/rustdoc/write-documentation/documentation-tests.html>;
Go examples, <https://go.dev/blog/examples>; Docs as Tests,
<https://www.docsastests.com/>; Doc Detective, <https://docs.doc-detective.com/>;
Sphinx, <https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html>;
cog, <https://cog.readthedocs.io/en/latest/running.html>; embedme,
<https://github.com/zakhenry/embedme>; Knuth, WEB,
<http://www.literateprogramming.com/knuthweb.pdf>; Org-babel,
<https://orgmode.org/manual/Extracting-Source-Code.html>; Software Engineering
at Google ch. 10, <https://abseil.io/resources/swe-book/html/ch10.html>;
Nygard, ADRs, <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>;
MADR, <https://adr.github.io/madr/>; Guru,
<https://help.getguru.com/docs/verifying-and-unverifying-cards>; Notion,
<https://www.notion.com/help/wikis-and-verified-pages>; Slab,
<https://help.slab.com/en/articles/4136379-post-verification>; Liu et al.
2018, <https://doi.org/10.1109/compsac.2018.00028>; CUP,
<https://doi.org/10.1145/3324884.3416581>; Panthaplackel et al. 2021,
<https://doi.org/10.1609/aaai.v35i1.16119>.

Mastery and expertise: Corbett and Anderson 1995,
<https://doi.org/10.1007/BF01099821>; Piech et al. 2015,
<https://arxiv.org/abs/1506.05908>; LearnLab knowledge component,
<https://learnlab.org/wiki/index.php?title=Knowledge_component>; Settles and
Meeder 2016, <https://aclanthology.org/P16-1174.pdf>; Khan Academy mastery
levels, <https://support.khanacademy.org/hc/en-us/articles/5548760867853>;
Mockus and Herbsleb 2002,
<https://herbsleb.org/web-pubs/pdfs/mockus-expertise-2002.pdf>; Fritz et al.
2010, <https://www.cs.ubc.ca/~fritz/papers/icse10_dok_web.pdf>; Fritz et al.
2014, <https://doi.org/10.1145/2512207>; Schuler and Zimmermann 2008,
<https://thomas-zimmermann.com/publications/files/schuler-msr-2008.pdf>;
Avelino et al. 2016, <https://arxiv.org/abs/1604.06766>; CodeScene,
<https://codescene.io/docs/guides/social/knowledge-distribution.html>;
CODEOWNERS,
<https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners>;
Krüger et al. 2018, <https://doi.org/10.1145/3180155.3180215>; Wheeler 2026,
<https://arxiv.org/abs/2606.20882>.

Comprehension questions and evidence: Sillito, Murphy, De Volder 2006,
<https://doi.org/10.1145/1181775.1181779>,
<https://www.cs.ubc.ca/~murphy/papers/other/asking-answering-fse06.pdf>;
Sillito et al. 2008, <https://doi.org/10.1109/TSE.2008.26>; LaToza and Myers
2010, <https://doi.org/10.1145/1937117.1937125>; Moulton et al. 2006,
<https://doi.org/10.1097/01.sla.0000234808.85789.6a>; Kerfoot et al. 2007,
<https://doi.org/10.1111/j.1365-2929.2006.02644.x>; Rohrer and Taylor 2006,
<https://doi.org/10.1002/acp.1266>; Rohrer and Taylor 2007,
<https://doi.org/10.1007/s11251-007-9015-8>; Kornell and Bjork 2008,
<https://doi.org/10.1111/j.1467-9280.2008.02127.x>; Rawson and Dunlosky 2011,
<https://doi.org/10.1037/a0023956>; YeckehZaare et al. 2022,
<https://doi.org/10.1145/3478431.3499408>; Moraes et al. 2023,
<https://doi.org/10.1145/3629296.3629362>; Elhayany and Meinel 2025,
<https://doi.org/10.1109/democon65705.2025.11282675>; Barnes and Underwood
1959, <https://doi.org/10.1037/h0047507>; Potts and Shanks 2012,
<https://doi.org/10.1037/a0028218>; Pastötter and Bäuml 2014,
<https://doi.org/10.3389/fpsyg.2014.00286>; Butterfield and Metcalfe 2001,
<https://doi.org/10.1037/0278-7393.27.6.1491>; Lewandowsky et al. 2012,
<https://doi.org/10.1177/1529100612451018>; Anderson, Bjork, Bjork 1994,
<https://doi.org/10.1037/0278-7393.20.5.1063>; Bjork lab,
<https://bjorklab.psych.ucla.edu/research/>.
