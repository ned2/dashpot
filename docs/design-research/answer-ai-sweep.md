---
status: research
date: 2026-09-13
---

# Answer.AI sweep: keeping humans in understanding

A survey of Answer.AI's published thinking, and the public writing and talks of its team,
on the problem this research phase calls cognitive debt: as more authoring is delegated to
AI, the person loses the conceptual model of what was built. It covers the answer.ai and
fast.ai blogs, team members' own sites and recorded talks, and the tools the lab documents
as embodying its philosophy. solve.it's own site and product detail are left to the sibling
note; this note records where Answer.AI writing motivates or explains the thinking behind
that product. Citations are to primary sources only: the post, the tool's repo or docs, or
the recording of the speaker's own words (podcast recordings hosted by a third party are
marked "interview recording"). Status as observed on 2026-09-13.

## Finding

Answer.AI's position is a single, consistently stated thesis: understanding is built by
doing the work in small verifiable steps, and any tool that lets the human skip the steps
trades short-term output for long-term "understanding debt" (Howard, MLST interview; Whitaker,
Solveit launch). The thesis predates LLMs — it is fast.ai's 2016 "whole game" teaching
philosophy and nbdev's 2019 exploratory/literate programming rationale — and the lab has
re-applied it to AI-assisted work under the name *dialog engineering*, with George Pólya's
*How to Solve It* (1945) as the explicit frame. Its distinctive claims relative to the Phase A
notes are (a) a tool-design stance rather than a review-gate or quiz stance: the shared,
editable, live workspace where "the AI can see exactly what the human sees" and code is
never run until the human moves it, with default-off completions in a learning mode; (b) a
motivational rather than purely cognitive account — self-determination theory's autonomy
and mastery, and Csikszentmihalyi's "junk flow" — of why delegation erodes competence;
(c) an explicit, tested rejection of the autonomous-agent direction (the 20-task Devin
trial, "we've invested heavily in really pushing agentic AI to the limit"), tempered by
named exceptions where a fully-delegated task is accepted at the cost of "a piece of code
that no one understands"; and (d) an application of Naur's theory-building argument to code
complexity — "striving to understand is essentially a process of Theory-simplification".
Evidence the lab offers is almost entirely experiential and testimonial (a 1,000-person
preview cohort, "hundreds of testimonials", 3,000 beta testers, the lab's own throughput);
the only structured measurements are the Devin task log and the PyPI "where are the apps"
analysis, neither of which measures understanding. Nothing found in Answer.AI writing
proposes measuring, quizzing, or tracking what a developer understands of a codebase; the
one place the question of tracking arises (Rachel Thomas on learning dashboards) is
argued against.

## Core claims

1. **Small steps with verification at each step is how understanding is built.** "Instead of
   asking AI to generate hundreds of lines of code at once, you work together in small
   steps. You might write a line or two, then have the AI suggest the next piece … build
   something you truly understand." (Howard, [A New Chapter for fast.ai](https://www.answer.ai/posts/2024-11-07-solveit.html), 2024-11-07.)
   "We aim to write no more than a few lines of code at a time, with each piece giving some
   useful output that you can use to verify that you're on the right track." (Whitaker,
   [Launching Solveit](https://www.answer.ai/posts/2025-10-01-solveit-full.html), 2025-10-02.)
2. **Pólya's four stages are the frame, and each stage is where judgement is exercised.**
   Understand the problem; devise a plan; carry it out, verifying each step; look back.
   "When chatbots rush from your initial request to a finished answer, you skip the work
   through which you come to deeply understand the problem. Without having done this
   thinking, you cannot judge whether the solution is any good." (Thomas,
   [My friends all hate AI; I just joined an AI startup](https://www.fast.ai/posts/2026-08-18-returning-to-AI/), 2026-08-18;
   Whitaker, Solveit launch, "Inspiration from Polya".)
3. **Delegating the whole task yields understanding debt.** "If you didn't know the
   foundations of how to do it before, you don't now either. You've learned nothing. If you
   keep working this way, you build up more and more code you don't understand, creating
   technical and understanding debt that will eventually become crippling." (Whitaker,
   Solveit launch.) Howard on the MLST recording: "You're not paying attention and you get
   this delegation of competence and you get understanding debt" (host's phrasing, which
   Howard adopts) and "there is no methodology that works with vibe coding … software
   engineering is a study of creating non-trivial systems that can continually improve over
   time" ([SolveIt: The Thinking Developer's Environment](https://www.youtube.com/watch?v=DgPr3HVp0eg), Howard with Whitaker, 2025).
4. **The human is the agent; the computer is not.** "I do not want to create more 'agentic
   AI' – I want humans to have agency, not computers!" (Howard,
   [How to Solve it With Code course now available](https://www.fast.ai/posts/2025-10-15-solveit2.html), 2025-10-15.)
   "A system where rather than the computer being the agent … you're the human agent. And
   the whole system is designed to make you more competent every day that you use it."
   (Howard, Thinking Developer's Environment recording.)
5. **Shared context: the AI sees exactly what the human sees, and both use the same tools.**
   "The AI should be able to see everything exactly as the human does, and vice versa, and
   both human and AI must be able to use the same tools." (Whitaker, Solveit launch.) "No
   separate instruction files, no context windows that don't match your actual workspace."
   (Howard, [Build to last](https://www.fast.ai/posts/2025-10-30-build-to-last.html), 2025-10-30.)
   The same principle motivates ShellSage: "maintaining shared context … both human and AI
   can see and understand the same complete context, right where the work is happening."
   (Cooper, [ShellSage](https://www.answer.ai/posts/2024-12-05-introducing-shell-sage.html), 2024-12-05.)
6. **Dialog engineering: the human curates the AI's context by editing the dialog.** Because
   auto-regressive models continue the pattern of their context, mistakes left in the
   transcript beget more mistakes; the remedy is to edit, hide, pin and delete messages so
   "AI work sessions … improve as time goes on, rather than degrading" (Whitaker, Solveit
   launch, "Dialog Engineering Keeps Context Useful"). Howard first described it in
   August 2024: "crafting a dialogue, you know, where the outcome of the dialogue is the
   artifacts that you want … I use it to kind of like craft the thought process before I
   generate the code." ([Latent Space interview recording](https://www.latent.space/p/answerai), 2024-08-16.)
   Ries: "the human always decides what's important. The human is in control of the
   context." ([Mixergy interview recording](https://mixergy.com/interviews/eric-ries-why-anthropic-won-and-how-to-build-incurruptible-companies/), 2026-05-30.)
7. **Tool defaults, not willpower, must make the understanding path the easy path.** "It's not
   enough to expect to rely on willpower to like not hit tab lots of times because every time
   you do it's using up your energy … we try to make it that the natural easy comfortable
   flow is the one that is going to produce high quality work and high quality learnings."
   (Howard, Thinking Developer's Environment recording.) "If a tool is not making it the
   natural way for a human to become more knowledgeable … that's a tool problem."
   ([MLST interview recording](https://www.youtube.com/watch?v=dHBEQ-Ryo24), 2026-03-03.)
   Concretely: AI output "is not added to your code or run until you choose to do so";
   Learning mode suppresses ghost-text completion unless triggered (Whitaker, Solveit launch,
   "Building an App for Collaboration not Replacement"; Howard,
   [A Guide to Solveit Features](https://www.fast.ai/posts/2025-11-07-solveit-features.html), 2025-11-07).
8. **Don't move on until you get it.** "When the AI suggests something you don't know, it is
   important not to skip it and move on – otherwise that new piece will never be something
   you learn!" (Whitaker, Solveit launch, "Learning Trajectory"). "I always tell people, don't
   move on when you're learning a new thing or working on something until you get it."
   (Howard, [Growing on Purpose keynote](https://www.youtube.com/watch?v=SUZwYV5JYBM), AI Engineer Melbourne, June 2026.)
9. **AI as senior advisor, not junior code-generator.** "Instead of bringing in a junior
   engineer that can just crank out code, you're bringing in a senior expert … somebody that
   can actually help you make better code and teach you things." (Howard quoting his framing
   to Lattner, Build to last.) The lab's earlier characterisation of autonomous agents is the
   opposite: Devin produced "code soup" and "spaghetti code that was way more confusing to
   read through than if I'd written it from scratch" ([A Month With Devin](https://www.answer.ai/posts/2025-01-08-devin.html), 2025-01-08).
10. **Naur applied: the complexity that matters is Theory complexity, which is not in the
    code.** "The complexity of your code really depends on a lot of factors that have NOTHING
    to do with code and that information is NOT in the code … Striving to understand is
    essentially a process of Theory-simplification." (Alvarez Vecino,
    [Why LLMs can't make your code simpler](https://www.answer.ai/posts/2026-08-19-llms-code-simpler.html), 2026-08-19.)
11. **Literate and exploratory programming: save the exploration so understanding transfers.**
    "The very process of exploration is valuable in itself, and that this process should be
    saved so that other programmers (including yourself in six months time) can see what
    happened and learn by example." (Howard, [nbdev](https://www.fast.ai/posts/2019-11-27-nbdev.html), 2019-11-27.)
    Knuth's "moral commitment" never to write an illiterate program is adopted verbatim for
    Claudette ([A new kind of literate program](https://www.answer.ai/posts/2024-06-23-claudette-src.html), 2024-06-23).
12. **Simplicity that fits in a head is a design goal.** "It will be easier to understand,
    easier to use, easier to hold in your head and in your hand." (Gallagher,
    [Introducing fastmigrate](https://www.answer.ai/posts/2025-06-13-fastmigrate.html), 2025-06-13.)
    "Focusing on one task and bringing as much of the code as possible into a single notebook
    or python file … forcing you to read the important bits." (Whitaker,
    [High-surface-area problems](https://www.answer.ai/posts/2024-04-12-tips.html), 2024-04-12.)
13. **Delegation erodes motivation, not only knowledge.** Howard's keynote grounds the
    argument in self-determination theory (autonomy, mastery) and Csikszentmihalyi's flow:
    "AI is neither good nor bad for you for your psyche. But warning, the people getting you
    to use AI don't care about your autonomy and mastery. They care about your outputs."
    The agent asking "distributed system or green threads?" to someone who cannot judge is
    an "illusion of control" that "decays your autonomy" (Growing on Purpose keynote). Thomas
    names the same pattern "dark flow" ([Breaking the spell of vibe coding](https://www.fast.ai/posts/2026-01-28-dark-flow/), 2026-01-28; already in Phase A).
14. **A bifurcation is coming between those who use AI to learn and those who use it to
    avoid learning.** "People who use AI the wrong way are going to get worse and worse. And
    the people who use it to learn more and learn faster are going to outpace the speed of
    growth of AI capabilities." (Howard, Build to last.) "If I was a between two and 20 years
    of experience developer, I would be asking that question of myself a lot because
    otherwise you might be in the process of making yourself obsolete." (MLST recording.)
15. **Against quantifying learning.** Asked for "a dashboard to track what my child is
    learning", Howard: "I actively do not want that." Thomas: "many AI education approaches
    are exacerbating the problems created by the tyranny of metrics: doubling down on trying
    to quantify everything, working only with discrete decomposable units."
    ([I Don't Want a Learning Dashboard for My Child](https://www.fast.ai/posts/2026-02-17-education/), 2026-02-17.)

**Where the team endorses the agentic direction.** Howard, MLST recording: after weeks of
failing to understand a 5,000-line ipykernel regression, GPT-5.3 Pro fixed it in two hours;
"it wasn't at all fun … I wasn't really in control", and the result is "a piece of code that
no one understands. Am I going to bet my company's product on it? … I don't know." He
frames the beneficiaries of current agents as "really junior people who can't code at all"
and "really experienced people like me or like Chris Lattner", with "people in the middle"
at risk. Whitaker's own site celebrates vibe coding for "throwaway weekend projects" and
"pieces of software I want to exist" that he does not want to carefully code
([Vibe Coding Wins](https://johnowhitaker.dev/posts/vc_wins.html), 2025-07-24;
[Vibe Coding and V-Plotters](https://johnowhitaker.dev/essays/vibe_coding.html), 2025-02-03),
and argues that for some projects "the idea is the software" and implementation can be
regenerated ([The Idea Is The Software](https://johnowhitaker.dev/essays/distributables.html), 2026-02-23).
Solveit itself exposes sub-agents and tool loops for "'agentic' actions" inside a dialog
(Solveit launch; keynote demo). Lattner's endorsed uses: "amazing for learning a codebase
you're not familiar with … getting us out of writing boilerplate" (Build to last).

## Answer.AI posts

Of 49 posts in the site's sitemap, these engage the topic. Author and date are from the post.

- **A new old kind of R&D lab** — Jeremy Howard, 2023-12-12 ·
  <https://www.answer.ai/posts/2023-12-12-launch.html> · Founding essay. States the shared
  method of Howard and Ries: "solve smaller easier problems in simple ways first, and create
  a ladder where each rung is a useful step of itself." Claims a "single generalist with a
  strong understanding of the foundations" plus AI tools can solve problems in unfamiliar
  stacks. No Pólya, Papert, or Bell Labs reference (Edison's Invention Lab is the model).
- **Lessons from history's greatest R&D labs** — Eric Gilliam (guest), 2024-01-26 ·
  <https://www.answer.ai/posts/2024-01-26-freaktakes-lessons.html> · Edison "nothing was
  settled until he proved it for himself at the lab bench"; hands-on iteration over theory.
  Organisational, not developer-level; included for the lineage of the "prove it yourself"
  stance.
- **A few tips for working on high-surface-area problems** — Johno Whitaker, 2024-04-12 ·
  <https://www.answer.ai/posts/2024-04-12-tips.html> · Pre-Solveit statement of the method:
  start with a minimal example and build up; instrument everything; explain the problem to
  someone (rubber-duck); refactor repeatedly into one notebook "forcing you to read the
  important bits". Notes that intermediate exploration is usually lost: "we usually see just
  the final (working) version rather than all the intermediate pieces."
- **Introducing Claudette** — Jeremy Howard, 2024-06-21 ·
  <https://www.answer.ai/posts/2024-06-21-claudette.html> · Library announcement whose
  closing section states the literate-programming commitment: the source is a rendered
  notebook that "teaches how and why the code is written the way it is."
- **A new kind of literate program – Claudette** — Jeremy Howard, 2024-06-23 ·
  <https://www.answer.ai/posts/2024-06-23-claudette-src.html> · Knuth's call to "concentrate
  rather on explaining to human beings what we want a computer to do"; launches the public
  "dev chats" series ([playlist](https://www.youtube.com/watch?v=p_8Zk6HUCV8&list=PLfYUBJiXbdtSPnX9IeYmwqTGBlkhAweAT))
  so that "you can quickly build a deep understanding of the code, and explore how it works
  by interacting with it directly."
- **FastHTML** — Jeremy Howard, 2024-08-03 · <https://www.answer.ai/posts/2024-08-03-fasthtml.html>
  · "The best way to create a big complex application is to first create a small simple
  application, and then add to it in small steps." Scale-down as a design requirement.
- **/llms.txt** — Jeremy Howard, 2024-09-03 · <https://www.answer.ai/posts/2024-09-03-llmstxt.html>
  · "Site authors know best" and curate what an LLM should read; a human-authored context
  map rather than a crawl. See Tools.
- **A New Chapter for fast.ai: How To Solve It With Code** — Jeremy Howard, 2024-11-07 ·
  <https://www.answer.ai/posts/2024-11-07-solveit.html> · Names *Dialog Engineering* and
  describes the "hit a wall" pattern: an app in 15 minutes, then "you need to make changes,
  add features, fix bugs. The magic starts to fade." Explicit exclusion: "this isn't for you
  if you believe AI can already replace programmers entirely." Course led by Howard,
  Whitaker and Audrey Roy Greenfeld. Companion video:
  [background discussion with Hamel Husain](https://www.youtube.com/watch?v=e9tL_Eg3fpM).
- **ShellSage – Your AI Bash Buddy** — Nathan Cooper, 2024-12-05 ·
  <https://www.answer.ai/posts/2024-12-05-introducing-shell-sage.html> · Terminal assistant
  that reads tmux scrollback so the model shares the human's context; "designed to teach
  rather than just tell" (explains what, why the flags, variations). Certificate-transparency
  anecdote as the model of "augmenting human intuition" rather than solving for the human.
- **ShellSage Loves iTerm** — Alexis Gallagher, 2024-12-10 ·
  <https://www.answer.ai/posts/2024-12-10-shellsage-loves-iterm.html> · Setup note; restates
  that tmux "sitting in between is what allows it to see your incoming commands, and their
  output, and make that context available to an AI."
- **nbsanity** — Hamel Husain, 2024-12-13 · <https://www.answer.ai/posts/2024-12-13-nbsanity.html>
  · "At fastai, we've long believed that Jupyter Notebooks are an excellent medium for
  technical writing, combining live code, visualizations, and narrative text."
- **Thoughts On A Month With Devin** — Hamel Husain, Isaac Flath, Johno Whitaker, 2025-01-08 ·
  <https://www.answer.ai/posts/2025-01-08-devin.html> · 20 tasks: 3 successes, 14 failures,
  3 inconclusive; no predictable pattern. "Workflows where developers drive more (like
  Cursor) avoid most issues"; "for now, we're sticking with tools that let us drive the
  development process." Flath: "I would have been better off starting from scratch and going
  step by step."
- **GPU Programming from Scratch** — Sarah Pan, 2025-03-17 ·
  <https://www.answer.ai/posts/2025-03-17-gpu-programming-scratch.html> · A learner's
  account; cites fast.ai's top-down approach and "iterate fast". Education, not AI-assisted
  coding.
- **Introducing fastmigrate** — Alexis Gallagher, 2025-06-13 ·
  <https://www.answer.ai/posts/2025-06-13-fastmigrate.html> · "Easier to hold in your head
  and in your hand"; the sharp-knife-versus-food-processor argument for tools whose
  behaviour a person can fully model.
- **The Stripe Experience You Deserve** — Nathan Cooper, 2025-07-23 ·
  <https://www.answer.ai/posts/2025-07-23-faststripe.html> · Docs-in-the-editor so that
  exploration does not require "context switching, which is a developer's worst friend."
- **Cachy** — Tommy, 2025-10-01 · <https://www.answer.ai/posts/2025-10-01-cachy.html> ·
  "We build most of our software in notebooks"; non-deterministic outputs "add significant
  bloat to notebook diffs which makes code review more difficult." Review of notebook diffs
  is a live concern.
- **Launching Solveit, the antidote to AI fatigue** — Johno Whitaker (tl;dr by Howard),
  2025-10-02 · <https://www.answer.ai/posts/2025-10-01-solveit-full.html> · The fullest
  statement of the method: Pólya's four steps; the worked Advent-of-Code example; fast
  feedback loops (Lean Startup, Kaggle evals); shared context; dialog engineering; the
  design choices that make hands-off generation "intentionally hard"; the learning
  trajectory; "Mastery Requires Deliberate Practice". Howard's tl;dr: "basically the opposite
  of 'vibe coding'; it's all about small steps, deep understanding, and deep reflection."
- **How I Created the Karpathy Tokenizers Book Chapter** — Kerem Turgutlu, 2025-10-13 ·
  <https://www.answer.ai/posts/2025-10-13-video-to-doc.html> · Non-code application. One-
  shotting the conversion "is very similar to asking AI to write a whole program for you –
  you don't build a deep understanding, have control over it or learn anything." Working
  piece by piece "took longer than one-shotting … but I ended up with something I fully
  understand, and it was still faster than writing it from scratch." Clarifying questions
  asked along the way became content "I actually understood because I had asked the
  questions myself."
- **The unauthorized tool call problem** — Piotr Czapla, 2026-02-18 ·
  <https://www.answer.ai/posts/2026-01-20-toolcalling.html> · Security, not understanding;
  relevant only for "I've learned to stay away from massive AI frameworks that try to
  abstract away complexity without providing auditable, flexible code."
- **So where are all the AI apps?** — Alexis Gallagher and Rens Dimmendaal, 2026-03-12 ·
  <https://www.answer.ai/posts/2026-03-12-so-where-are-all-the-ai-apps.html> · PyPI
  package-creation and release-frequency analysis: no aggregate productivity inflection
  after ChatGPT; a >2x release-frequency jump concentrated in popular AI-related packages.
  Evidence against the productivity premise, not about understanding. Code and data at
  <https://github.com/AnswerDotAI/pypi-analysis>.
- **Why LLMs can't make your code simpler** — Pol Alvarez Vecino, 2026-08-19 ·
  <https://www.answer.ai/posts/2026-08-19-llms-code-simpler.html> · Naur's "Programming as
  Theory Building" applied to LLM output: complexity metrics (LoC, cyclomatic, Halstead)
  cannot capture Theory complexity; the Solveit billing case, where the team declined an
  LLM's proposal to reinstate a managed-subscription path in order to keep a Theory that fits
  in one sentence; "in the process of understanding and simplifying … we learned something
  valuable beyond the product we built."

Not engaged (judged from title and skim): the FSDP/QLoRA, ColBERT, ModernBERT, rerankers,
synthetic-data, cold-compress, gpu.cpp, WebGPU Puzzles, MonsterUI, flexicache, concurrency,
readbench, transformers-as-matchers, HTMX interview, policy (SB-1047, AI definition, OpenAI
contract), life-sciences, and audience-building posts. The site's mission line: "a new kind
of AI R&D lab which creates practical end-user products based on foundational research
breakthroughs" (<https://www.answer.ai/overview.html>).

## Team writing and talks

**Jeremy Howard.**
- [Providing a Good Education in Deep Learning](https://www.fast.ai/posts/2016-10-08-teaching-philosophy.html)
  (with Rachel Thomas, 2016-10-08): the "whole game" (Perkins), top-down, examples-first,
  "if you truly understand something, you can explain it in an accessible way"; spaced
  repetition named as an evidence-backed technique the course structure dovetails with.
- [nbdev: use Jupyter Notebooks for everything](https://www.fast.ai/posts/2019-11-27-nbdev.html)
  (2019-11-27): exploratory programming as "a scientist's journal"; lineage to Knuth's
  literate programming and Bret Victor's "programming system for understanding programs".
- [I Like Notebooks](https://www.youtube.com/watch?v=9Q6sLbz37gk) (JupyterCon 2020,
  Howard's channel): the rebuttal to Joel Grus; notebooks as the literate/exploratory
  environment. Revisited in the MLST recording: "all software developers should be using
  exploratory based programming to deepen their understanding of what they're working with so
  that they end up with a really strong mental model of the system."
- [Latent Space: AI Magic](https://www.latent.space/p/answerai) (interview recording,
  2024-08-16): first public description of dialog engineering, then internally called "AI
  Magic"; "craft the thought process before I generate the code."
- [Build to Last](https://www.fast.ai/posts/2025-10-30-build-to-last.html)
  (2025-10-30; [recording](https://www.youtube.com/watch?v=bxDDLMe6KuU) of the 2025-10-05
  conversation): the concern stated in Howard's own voice ("developers abandoning the very
  practices that lead to understanding, mastery, and software that lasts"; "it's like a
  gambling machine … pull the lever again"); Lattner's PR anecdote ("if you're delegating
  knowledge to an AI, and you're just reviewing the code without thinking about what you want
  to achieve, I think that's very, very concerning"); tight iteration loops and a live
  workspace as the precondition for craftsmanship with AI; "a third participant in this
  dialogue"; the bifurcation claim.
- [How to Solve it With Code course now available](https://www.fast.ai/posts/2025-10-15-solveit2.html)
  (2025-10-15): "I want humans to have agency, not computers"; CJ Reynolds quote on losing
  "the little wins"; the four-part structure (course, platform, community, R&D).
- [A Guide to Solveit Features](https://www.fast.ai/posts/2025-11-07-solveit-features.html)
  (2025-11-07): the problem statement ("you get code you don't understand, and when you need
  to modify it … you're stuck"); a dialog as "a conversation between three parties: you and
  yourself (notes), you and the computer (code), and you and the AI (prompts)"; Learning
  mode hides ghost text because "when you're learning, you should write code yourself";
  "Writing code yourself builds understanding" repeated at each AI-generation feature.
  Feature detail is the sibling note's territory.
- [SolveIt: The Thinking Developer's Environment](https://www.youtube.com/watch?v=DgPr3HVp0eg)
  (with Johno Whitaker, on Hamel Husain's channel, 2025): "no methodology of software
  engineering … works with vibe coding"; "we've invested heavily in really pushing agentic
  AI to the limit … discovered some small limited areas where that approach can be useful";
  Ries "has not seen any [startups] which have been built through vibe coding"; "most of us
  … have independently discovered that when we're using stuff like cursor and relying on tab
  completion … it's damaging our ability to do high quality work over an extended period";
  the willpower argument for defaults; "I spend at least half an hour a day doing deliberate
  practice."
- [The Dangerous Illusion of AI Coding?](https://www.youtube.com/watch?v=dHBEQ-Ryo24)
  (MLST interview recording, 2026-03-03): "LLMs cosplay understanding"; AI coding "is like a
  slot machine in that you have an illusion of control"; the ipykernel episode (above);
  prompting-framework skill "is not reusable knowledge, it's ephemeral"; the junior/senior/
  middle split; the evaluation critique ("so many models and tools expressly are being
  evaluated on can I give it a complete piece of work … versus have you evaluated whether a
  human comes out the other end with a deep understanding").
- [Growing on Purpose: The Work That Makes You](https://www.youtube.com/watch?v=SUZwYV5JYBM)
  (AI Engineer Melbourne keynote, June 2026, Howard's channel): self-determination theory
  (autonomy, mastery, relatedness, purpose); behavioural activation; flow vs junk flow;
  Armin Ronacher's "decoupled from any external validation"; a community member's 200k-line
  vibe-coded product where "the pace we've moved at has slowed down as models get better";
  the augmentation lineage (Sutherland, Engelbart, Iverson, Victor, Lattner); demos of
  reading a paper and a blog post by rebuilding their contents; "this whole talk was written
  in Solveit … [it] created none of the narrative, none of the slides."
- [The Best Way to Read a Book (That Nobody's Doing)](https://www.youtube.com/watch?v=zIqLuuyxgE4)
  (Howard's channel, course lesson excerpt): close reading of Ries's manuscript; linked from
  Thomas's close-reading post below.

**Rachel Thomas** (fast.ai co-founder; rejoined Answer.AI 2026).
- [Breaking the spell of vibe coding](https://www.fast.ai/posts/2026-01-28-dark-flow/)
  (2026-01-28): already catalogued in the Phase A
  [discourse cluster](landscape-sweep.md#cluster-8--discourse-and-framing); the source of the
  gambling/junk-flow framing Howard's keynote and the MLST recording reuse.
- [How To Use AI for the Ancient Art of Close Reading](https://www.fast.ai/posts/2026-01-21-reading-LLMs/)
  (2026-01-21): a seven-step reading process (chapter summaries as context; no spoilers;
  per-chapter dialog overviews carried forward; "optional: have the LLM ask questions to
  check the reader's understanding"; Anki cards via fastanki); Whitaker on preparing the
  workspace: "that little investment up front makes it a very different tool."
- [I Don't Want a Learning Dashboard for My Child](https://www.fast.ai/posts/2026-02-17-education/)
  (2026-02-17): against learning dashboards and "discrete decomposable units"; not about
  code but the only Answer.AI text on tracking understanding.
- [My friends all hate AI; I just joined an AI startup](https://www.fast.ai/posts/2026-08-18-returning-to-AI/) (2026-08-18):
  "people of all ages are outsourcing their thinking to AI. However, skills atrophy when you
  stop using them"; Solveit's design "treats AI as fallible and keeps the human in control";
  "explicitly designed to be the opposite of an overly 'helpful' chatbot."

**Eric Ries** (co-founder).
- [The AI platform I use every day](https://news.theleanstartup.com/p/the-ai-platform-i-use-everyday-4211)
  (2025-10-14): "the current trend of ever more powerful models generating ever larger blocks
  of code feels unsustainable"; quotes a 25-year-experience participant: "maintaining human
  agency, working in comprehensible increments and building genuine understanding at each
  step … a partnership model that builds competence over time rather than creating
  dependence."
- [Mixergy interview recording](https://mixergy.com/interviews/eric-ries-why-anthropic-won-and-how-to-build-incurruptible-companies/)
  (2026-05-30): wrote *Incorruptible* in Solveit; "AI did not write the prose for me"; "with
  Claude Code, with CoWork … there's a huge amount of work happening behind the scenes that
  you can't see. Here, the human always decides what's important."
- The launch post quotes Ries on development informing research; the Solveit launch credits
  him with the fast-feedback principle (Lean Startup). No Ries text on code understanding as
  such was found.

**Johno Whitaker** (Answer.AI; on sabbatical as of 2026-08).
- [3 Modes of Making with AI](https://johnowhitaker.dev/essays/3_modes.html) (2024-11-08):
  slot machine → iterative refinement → co-creation, ordered by human agency; co-creation is
  "writing code a few lines at a time, getting AI help with syntax and brainstorming but also
  understanding the parts myself."
- [AI Outputs as Junk Food](https://johnowhitaker.dev/essays/junk_food.html) (2024-12-02):
  preference-optimised outputs (verbosity, more code, flattery) as "eye-candy"; "this won't
  make you a better programmer in the long term."
- [Vibe Coding and V-Plotters](https://johnowhitaker.dev/essays/vibe_coding.html)
  (2025-02-03): "keep in mind the value of wasting an hour or two trying to do things the
  human way."
- [My Thoughts on the Future of "AI"](https://johnowhitaker.dev/essays/future-ai.html)
  (2025-03-18): names skill atrophy among present dangers.
- [What Is Solveit?](https://johnowhitaker.dev/posts/solveit.html) (2025-09-12): draft of
  the launch post.
- [The Idea Is The Software](https://johnowhitaker.dev/essays/distributables.html)
  (2026-02-23) and [Quo Vadis?](https://johnowhitaker.dev/essays/quo_vadis.html)
  (2026-08-24): the counter-current within the team — "software skills may have a limited
  remaining shelf life"; Solveit was "a fantastic tool for coding with AI in 2024, or
  learning to code with AI in 2025."
- Talk: [Agents at Work 9: AI Agents from First Principles](https://www.youtube.com/watch?v=ZIZCfVZg91A)
  (third-party channel; not transcribed here).

**Alexis Gallagher.** fastmigrate and ShellSage posts above; the PyPI analysis. No personal
site writing on the topic found.

**Hamel Husain** (co-author on Answer.AI posts). [Innovating on Software Development](https://www.youtube.com/watch?v=rX1yGxJijsI)
(AI Council channel) is the literate-programming talk the Claudette posts cite; the Devin
post's "there is more opportunity to nudge things in the right direction more incrementally"
in Cursor versus Devin.

**Nathan Cooper.** ShellSage and FastStripe posts above; "designing for collaboration rather
than automation."

**Kerem Turgutlu.** Tokenizers book-chapter post above.

**Isaac Flath.** Co-author of the Devin post. His own newsletter
([The SpecFlow Process](https://elite-ai-assisted-coding.dev/p/the-specflow-process-for-using-ai),
2025-11-02) moves toward structured agent workflows — a Plan/Implement/Reflect process with
a `decisions.md` capturing "the why behind the code" — and by 2026 the newsletter's framing
is an "agentic software factory" (Eleanor Berger, 2026-08-24, not Flath). Neither mentions
Solveit or Answer.AI.

**Pol Alvarez Vecino.** Naur post above.

**Not found**: writing on this topic by Benjamin Warner, Austin Huang, Audrey Roy Greenfeld,
Daniel Roy Greenfeld (his Answer.AI post is on flexicache), Rens Dimmendaal beyond the PyPI
post, or Piotr Czapla beyond the tool-call post.

## Tools embodying the philosophy

Each entry: what it is · the principle it embodies as its own documentation states it ·
source.

- **nbdev** — package, tests and docs authored in notebooks · "Traditional programming
  environments throw away the result of your exploration in REPLs or notebooks. nbdev makes
  exploration an integral part of your workflow"; tests are the exploration, docs are the
  narrative · <https://nbdev.fast.ai/>; rationale in the
  [2019 launch post](https://www.fast.ai/posts/2019-11-27-nbdev.html). Note: every nbdev
  project now emits `.md` twins of its doc pages for LLM ingestion (llms.txt post).
- **Claudette** (and Cosette) — thin wrappers over the Anthropic/OpenAI SDKs · the first
  "literate nbdev" project: "even if you've never used the Anthropic Python SDK or Claude
  API before, you should be able to read the source code"; `Chat` keeps a stateful dialog
  and `toolloop` runs an agent loop, both from a notebook · <https://claudette.answer.ai/>;
  [announcement](https://www.answer.ai/posts/2024-06-21-claudette.html).
- **fastcore `docments`** — parameter comments as documentation · used so a plain Python
  function with commented parameters becomes a tool definition; the human-readable
  annotation is the machine-readable schema · referenced in the Claudette announcement;
  docs at <https://fastcore.fast.ai/docments.html>.
- **llms.txt** — a proposal for a curated, human-authored map of what an LLM should read
  about a site · "site authors know best, and can provide a list of content that an LLM
  should use"; Markdown chosen because "we expect many of these files to be read by language
  models and agents" yet stay human-readable; the `llms_txt2ctx` tool expands it into a
  context file · <https://llmstxt.org/>; [post](https://www.answer.ai/posts/2024-09-03-llmstxt.html).
  FastHTML's docs are the reference implementation.
- **contextkit** — `read_*` helpers that pull URLs, files, repos, PDFs and transcripts into
  LLM context · described only as "useful LLM contexts ready to be used in AIMagic" (the
  pre-release name for Solveit); the README carries no design statement about the human,
  so the principle is inferred only from its use inside dialog engineering ·
  <https://github.com/AnswerDotAI/contextkit>.
- **ShellSage** — terminal assistant reading tmux history · shared context "right where
  the work is happening"; "teach rather than just tell"; commands are explained and
  extracted, not executed, unless the user opts in · <https://github.com/AnswerDotAI/shell_sage>;
  [post](https://www.answer.ai/posts/2024-12-05-introducing-shell-sage.html). Howard: "about
  100 lines of code … by the next day, all of us were using it constantly" (Build to last).
- **fastlite / fastmigrate / faststripe** — small libraries for SQLite, migrations and Stripe ·
  the "sharp knife" principle: few commands, "easier to hold in your head"; fastlite adds
  notebook auto-complete and SQL-transparent objects so the database is explored a step at a
  time · <https://github.com/AnswerDotAI/fastlite>;
  [fastmigrate post](https://www.answer.ai/posts/2025-06-13-fastmigrate.html);
  [faststripe post](https://www.answer.ai/posts/2025-07-23-faststripe.html).
- **fastanki** — read/write Anki collections and sync to AnkiWeb from code · lets a reading
  dialog emit spaced-repetition cards; the docs state capability, not pedagogy; the rationale
  is in Thomas's close-reading post · <https://answerdotai.github.io/fastanki/>.
- **dialoghelper** — functions the AI can call to add, update and reorganise messages in a
  Solveit dialog · makes the dialog itself the artefact both parties edit; the README is
  terse, the behaviour is documented in the Tokenizers post and the features guide ·
  <https://github.com/AnswerDotAI/dialoghelper>.
- **nbsanity** and **cachy** — render notebooks as pages; cache LLM calls to keep notebook
  diffs reviewable · the notebook as the unit of technical communication and review ·
  [nbsanity](https://www.answer.ai/posts/2024-12-13-nbsanity.html);
  [cachy](https://www.answer.ai/posts/2025-10-01-cachy.html).
- **Solveit** — the platform · left to the sibling note. The design principles Answer.AI
  writing gives for it: three message types in one workspace; output not run until moved;
  Learning mode suppresses completions; hide/pin/edit for context; symbol browser of live
  kernel state; sub-agents and Python-functions-as-tools available but not the default path
  (Solveit launch; features guide; [platform tour](https://www.youtube.com/watch?v=bxDDLMe6KuU)).

## Evidence offered

Evidence, in the sense of a measurement or a structured record:

- **Devin trial** — 20 tasks over a month, 3/14/3 success/failure/inconclusive, task table
  in the appendix; measures task completion and code quality by the team's judgement, not
  understanding ([Devin post](https://www.answer.ai/posts/2025-01-08-devin.html)).
- **PyPI analysis** — package creation and release frequency by cohort and AI-relatedness,
  code published; measures output, not understanding
  ([post](https://www.answer.ai/posts/2026-03-12-so-where-are-all-the-ai-apps.html)).
- **Cohort and usage figures** — 1,000-person preview course that filled in a day; "hundreds
  of testimonials"; "3,000 people" in beta over two years; "a few hundred" showcase
  projects (Solveit launch; solveit2 email; keynote). Self-reported and uncontrolled.
- **Cited external research** — self-determination theory review paper and flow research
  (keynote); Csikszentmihalyi and gambling "loss disguised as a win" studies (dark flow post,
  already in Phase A); Perkins's *Making Learning Whole* and spaced-repetition literature
  (2016 teaching philosophy); Naur 1985 (Alvarez Vecino). The Anthropic skill-formation
  study is raised by the MLST host, not by Howard, and is already in the Phase A
  [AI-specific evidence](evidence-and-mechanisms.md#ai-specific-evidence-20232026).

Argument and reported experience, not evidence: the lab's own throughput ("when people ask
how we accomplish so much with such a small team, this is the answer"); Ries's claim not to
have seen a vibe-coded startup; Lattner's PR anecdote; Howard's ipykernel episode; the
200k-line community anecdote; Ronacher's and Reynolds's quotes; Turgutlu's "still faster
than writing it from scratch"; the "we've independently discovered tab completion damages
our ability" claim; the bifurcation prediction. No Answer.AI text reports a comparison of
understanding between people who worked the Solveit way and people who did not, and the
close-reading post's "have the LLM ask questions to check the reader's understanding" is
marked optional and unevaluated.

## Mapping to the Phase A landscape

- **Cluster 1, retrieval practice and Socratic tutoring** ([landscape](landscape-sweep.md#cluster-1--retrieval-practice-and-socratic-tutoring-in-the-agent-loop)):
  Solveit's Learning mode ("asks about your background before answering, breaks down
  explanations") is a first-party analogue of the Claude Code Learning style; the close-
  reading post's optional comprehension questions and fastanki cards are the only Answer.AI
  items in this cluster, and they target reading, not code. The Phase A observation that
  Anki-style repetition on a codebase is thin holds here too.
- **Cluster 2, merge-time gates** ([landscape](landscape-sweep.md#cluster-2--merge-time-understanding-gates)):
  nothing. Answer.AI's gate is at generation time (output not run until moved), not at
  merge. Lattner's "we also do code review, which is a very important thing" is the only
  mention.
- **Cluster 3, diff-comprehension aids** ([landscape](landscape-sweep.md#cluster-3--diff-comprehension-aids)):
  the literate-nbdev source and cachy's concern for reviewable notebook diffs are adjacent;
  no walkthrough or literate-diff tool.
- **Cluster 4, explorable maps** ([landscape](landscape-sweep.md#cluster-4--explorable-maps-and-explanation-on-demand)):
  llms.txt is a human-curated map for the model rather than for the human; the symbol
  browser of live kernel state is a map of the session, not the repo. Lattner endorses
  AI for "discovery" of unfamiliar codebases.
- **Cluster 5, living artifacts** ([landscape](landscape-sweep.md#cluster-5--agent-maintained-living-artifacts)):
  nbdev's docs-from-source and the dialog-as-artefact idea (Whitaker's tips post: notebooks
  save "the progression as you verify things a few lines at a time") are human-maintained
  living artefacts; the agent edits them only through dialoghelper under the human's eye.
- **Cluster 6, provenance and intent** ([landscape](landscape-sweep.md#cluster-6--provenance-and-intent-capture-seeds-missed)):
  the Solveit dialog is itself a provenance record ("the evidence of that side-quest can be
  collapsed below a heading"); Flath's `decisions.md` is a provenance practice. Neither is
  attached to git.
- **Cluster 7, friction and checkpoints** ([landscape](landscape-sweep.md#cluster-7--friction-and-metacognitive-checkpoints)):
  the closest fit. Answer.AI's friction is designed into defaults (fenced output, hidden
  ghost text, small editor at the bottom) and justified by the willpower argument; Phase A
  noted no item "sits at task start" — Pólya's "understand the problem; restate it" is a
  task-start checkpoint, but as a practice, not a tool feature.
- **Cluster 8, discourse** ([landscape](landscape-sweep.md#cluster-8--discourse-and-framing)):
  Thomas's dark-flow essay is already there; Howard's keynote, the Lattner interview, the
  MLST recording and the Naur post extend it with "understanding debt", the SDT framing, and
  Theory-simplification.
- **Cluster 9, measurement** ([landscape](landscape-sweep.md#cluster-9--measurement-and-detection)):
  nothing, and the education post argues against it.
- **Evidence note** ([Naur](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text);
  [generation effect](evidence-and-mechanisms.md#generation-effect);
  [desirable difficulties](evidence-and-mechanisms.md#desirable-difficulties);
  [illusion of competence](evidence-and-mechanisms.md#illusion-of-competence-and-fluency)):
  the Answer.AI method is, in the evidence note's terms, generation-first with immediate
  feedback and deliberate difficulty, and its "illusion of control" language is the
  motivational cousin of the illusion of competence. The team does not cite this literature;
  the correspondence is this note's, not theirs.

**New relative to Phase A.** (1) Understanding as a *tool-design* problem solved by defaults
and a shared live workspace, with an explicit argument that willpower-based practices fail;
(2) dialog engineering — the human curating the model's context as the mechanism that keeps
both parties' understanding aligned; (3) the self-determination-theory account (autonomy,
mastery, illusion of control) alongside the cognitive one; (4) Naur's Theory as the
complexity metric that LLM-written code cannot optimise, with a documented case of declining
an LLM's proposal to preserve a one-sentence Theory; (5) the junior/senior/middle split as a
statement of who agents help and who they harm; (6) the "hit a wall" account of when
cognitive debt comes due (change, feature, bug); (7) a founder-level, tested rejection of
autonomous agents from a lab that builds AI products, paired with a candid record of the
exception. None of these is a mechanism for a codebase the human did not build in dialog;
Answer.AI's answer to inherited or agent-written code is to rebuild understanding by
re-deriving it in small steps (the keynote's RLM and Tailwind demos).

## Dead ends

- No Answer.AI or fast.ai text titled or themed "Programming should be …"; the "AI Magic"
  name appears only as Solveit's pre-release name (Latent Space; contextkit README).
- The "How to Solve It With Code" lesson pages live on solve.it.com, not on fast.ai or
  course.fast.ai; course.fast.ai still describes the deep-learning course. Lesson content is
  the sibling note's territory; only the two lesson-9 excerpts on Howard's channel and the
  Hamel-hosted session were used here.
- No Ries text on code understanding as such; his writing on Solveit concerns prose.
- No personal-site writing on the topic by Gallagher, Warner, Huang, Cooper, Turgutlu, or
  either Roy Greenfeld. The Greenfelds are named as course staff only.
- Flath's newsletter posts do not mention Solveit or Answer.AI; his later position is
  represented only by the SpecFlow post.
- The Chris Thomas post "The Human is the Agent" linked from Thomas's return post is a
  user's account, not a team source, and was not used.
- The MAD podcast (2025-05), Unsupervised Learning ep. 34 (2024), and the MLST Patreon
  "extended version" were not transcribed; the public MLST episode was used instead.
- Neither the contextkit nor the dialoghelper README states a design principle; their
  principles are documented only in the posts that use them.
- Nothing found in Answer.AI writing on measuring or tracking a developer's understanding
  of a codebase, on quizzing at review or merge time, or on AI-free periods.
