---
status: research
date: 2026-09-13
---

# Solveit sweep

A single-product survey of Answer.AI's Solveit (spelled "SolveIt" on parts of its own site) as
it bears on keeping a person in understanding while working with AI. Primary sources are the
solve.it.com pages, the Answer.AI and fast.ai posts, the team's own talk and lesson recordings
(auto-captions read in full), the public repositories under the AnswerDotAI GitHub
organisation, and the team's own comments on Hacker News and X. Third-party write-ups appear
only under Reception and are labelled secondary. Sibling notes cover the Phase A
[landscape sweep](landscape-sweep.md) and the [evidence and mechanisms](evidence-and-mechanisms.md)
review; Answer.AI's broader philosophy is a sibling agent's remit and is cited here only where
Solveit material states it. Status is as observed on 2026-09-13. No fit-for-Dashpot judgement.

## Finding

Solveit is three things sold as one: a method (Pólya's four-step loop applied at the grain of
one or two lines of code with the output shown after each), a five-week fast.ai course that
teaches it, and a hosted notebook-plus-chat-plus-VPS platform built so that the method is the
path of least resistance. The mechanism it embodies is an *authorship-default inversion*: the
editor defaults to code the human writes, AI-suggested code is inert text until the human
extracts it, the "Learning" mode withholds autocomplete and answers with a question about the
user's background, and the prompt box does not reappear after an answer unless the user asks
for rapid chat. Understanding is meant to be built by generation (write it yourself), by
step-wise verification (run one to two lines, look), and by a norm — stop at any unfamiliar API
and read until you get it — that the tool supports but does not enforce. Relative to Phase A it
is new in four ways: it is the only item found that sits at task start and at every step of a
task rather than at commit, PR, or merge; it treats the editable dialog (notes, code, outputs,
AI turns) as the durable understanding artifact, where Phase A's provenance cluster keeps an
append-only trace; it inverts the default that every Cluster 1 and 7 item accepts (agent
writes, human is quizzed or handed a `TODO`); and it carries the same method into reading
papers and books with hand-off notes and Anki cards. It has no quiz, no mastery tracking, no
retention measurement, and no codebase-level model: the unit is a dialog, not a repository, and
the evidence for its claims is an end-of-course survey and 178 published testimonials.

## What it is

**Naming and lineage.** The name comes from George Pólya's *How to Solve It* (1945); the site's
epigraphs are Pólya's "There is a grain of discovery in the solution of any problem" and "It
is not enough to understand the solution of a problem; you must also understand how it was
found" ([solve.it.com](https://solve.it.com/)). Jeremy Howard first named the course and the
"dialogue engineering" idea on Latent Space in August 2024, when the platform was still called
"AI Magic": "we might launch AI magic via a course called how to solve it with code"
([YouTube, 1:02:52](https://www.youtube.com/watch?v=qO-YqJm0Q1U)). The coding practice is the
one fast.ai has taught since before LLMs — exploratory, literate notebooks packaged with nbdev
— with the AI added to the same surface ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).

**Three parts.** Howard's own framing in the October 2025 forum email is "a course, a
software platform, a community, and ongoing R&D" ([fast.ai, 2025-10-15](https://www.fast.ai/posts/2025-10-15-solveit2.html)).
On Hacker News he answered "is it a chat tool or a class?" with "It's both! ... a course, plus
access to the platform" ([HN, jph00](https://news.ycombinator.com/item?id=45456056)) and
"The course is about a methodology, not a product" ([HN, jph00](https://news.ycombinator.com/item?id=45456043)).

**Timeline.**

- 2024-11-07: fast.ai joins Answer.AI; beta course "How To Solve It With Code" announced,
  starting 2024-11-26, led by Howard, Johno Whitaker and Audrey Roy Greenfeld; the platform
  "solveit" is introduced as "the first tool specifically designed for Dialog Engineering"
  ([Answer.AI, 2024-11-07](https://www.answer.ai/posts/2024-11-07-solveit.html)). Signups
  closed after one day with 1,000 students ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).
  A December 2024 Answer.AI post says "our community of over 2,000 students in our solveit
  course" ([nbsanity post](https://www.answer.ai/posts/2024-12-13-nbsanity.html)); the
  discrepancy is not resolved in any source found.
- 2025-08-15: platform and method demonstrated at length with Hamel Husain
  ([YouTube](https://www.youtube.com/watch?v=DgPr3HVp0eg)).
- 2025-10-02: public launch post; signups open until 2025-10-20; five-week, ten-lesson course
  starting 2025-10-20 ([Answer.AI](https://www.answer.ai/posts/2025-10-01-solveit-full.html));
  Product Hunt launch 2025-10-03 ([Product Hunt](https://www.producthunt.com/products/solveit));
  Latent Space episode the same day ([YouTube](https://www.youtube.com/watch?v=01ybLOH1fnU)).
- 2025-10-17 and 2025-11-07: the platform tour video and its written version, the only
  feature-level documentation found in public ([fast.ai](https://www.fast.ai/posts/2025-11-07-solveit-features.html)).
- 2026-01-20: two Lesson 9 excerpts (close reading of a book and of a paper) published free
  ([fast.ai, 2026-01-21](https://www.fast.ai/posts/2026-01-21-reading-LLMs/)).
- 2026-06-04: Howard's AI Engineer Melbourne keynote: "strictly speaking Solveit at the moment
  ... has been beta tested for the last two years by 3,000 people" and a conference code "before
  it's officially released" ([YouTube, 33:07](https://www.youtube.com/watch?v=SUZwYV5JYBM)).
- 2026-06-11: Eric Ries on HN: "once we re-open the solveit course ... stay tuned"
  ([HN, eries](https://news.ycombinator.com/item?id=48486758)).
- 2026-08-18: Rachel Thomas returns to Answer.AI to work on AI in education, describing
  Solveit as "a tool where people can directly edit the AI's responses and decide for
  themselves what to do next" ([fast.ai](https://www.fast.ai/posts/2026-08-18-returning-to-AI/)).
- 2026-08-19: an Answer.AI post describes Solveit's billing after "launch day": credits only,
  charged for "LLM usage, cpu, disk, memory and bandwidth", card saved at signup, manual or
  automatic top-up ([Answer.AI](https://www.answer.ai/posts/2026-08-19-llms-code-simpler.html)).
  The date of that launch, and whether it was public or to alumni, is unsourced.

**Status as of 2026-09-13.** The site banner reads "Signups are currently closed"
([solve.it.com](https://solve.it.com/)); a forum user reported the same on 2026-05-06
([forums.fast.ai](https://forums.fast.ai/t/about-the-solveit-category/122445)); the
`solveit_demos` README (updated 2026-03-31) says "Solveit is currently only available via the
ongoing course ... Stay tuned for eventual release" ([GitHub](https://github.com/AnswerDotAI/solveit_demos)).
The platform has never been purchasable on its own: "You can't purchase access to the platform
directly" ([HN, jph00, 2025-10-04](https://news.ycombinator.com/item?id=45475755)).

**Pricing.** The site lists the course at $500 with 30 days of platform access "with no quotas",
then $10/month ([solve.it.com](https://solve.it.com/)); at the October 2025 launch Howard
confirmed a $400 figure quoted by a commenter ("The 400 includes platform access from signup
until a few weeks after course finishes. No quota") ([HN](https://news.ycombinator.com/item?id=45475755)),
so the price appears to have risen after launch (unsourced). Full refund "any time until 2
weeks into the course" ([fast.ai, 2025-10-15](https://www.fast.ai/posts/2025-10-15-solveit2.html)).
By August 2026 the model is usage credits, not a subscription (above).

**Who it is for.** "designed mainly for experienced coders, AI practitioners, and data
scientists" ([fast.ai, 2025-10-15](https://www.fast.ai/posts/2025-10-15-solveit2.html));
"You should feel at least somewhat comfortable writing code ... somewhat familiar with Python"
and "the most successful students were those that wanted to understand their code, not just
copy-paste" ([solve.it.com](https://solve.it.com/)). Howard's own segmentation: "best honestly
for people who are really new to programming or to people that have over 20 years experience
... for people with a medium amount of experience, it can feel almost confronting ... either you
need to be very junior or very senior or very open-minded" ([YouTube, 1:30:44](https://www.youtube.com/watch?v=DgPr3HVp0eg)).
Preview attendees included "a professor of English, high school students, physicists and
astronomers" ([solve.it.com](https://solve.it.com/)).

**Team.** Jeremy Howard and Johno Whitaker teach; Eric Ries teaches writing and startup
lessons and used the platform to write *Incorruptible* ([solve.it.com](https://solve.it.com/);
[Product Hunt review](https://www.producthunt.com/products/solveit)); Kerem Turgutlu wrote
the features guide and the tokenizer article ([fast.ai](https://www.fast.ai/posts/2025-11-07-solveit-features.html));
Rens Dimmendaal was a student and then joined Answer.AI ([archived post](https://web.archive.org/web/2025/https://rensdimmendaal.com/posts/solveit-course-key-take-aways));
Pol Alvarez Vecino works on billing ([Answer.AI, 2026-08-19](https://www.answer.ai/posts/2026-08-19-llms-code-simpler.html));
Audrey Roy Greenfeld co-led the 2024 cohort ([Answer.AI, 2024-11-07](https://www.answer.ai/posts/2024-11-07-solveit.html)).
Answer.AI is a public benefit corporation; Howard: "Our job is actually to maximize human
flourishing by taking advantage of AI" ([YouTube, 53:52](https://www.youtube.com/watch?v=01ybLOH1fnU)).

## The method

**Pólya's loop, stated.** "Understand the Problem: identify what you're being asked to do;
restate the problem. Devise a Plan: draw on similar problems; break down into manageable
parts; consider working backward; simplify the problem. Carry Out the Plan: verify each step.
Look Back and Reflect: consider alternatives; extract lessons learned"
([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)). Howard
maps the same loop to the OODA loop, Toyota's line iteration, and the Lean Startup
([YouTube, 12:37](https://www.youtube.com/watch?v=DgPr3HVp0eg)); the site calls Lean Startup
and the Solveit method "two sides of the same coin: shorten feedback loops & learn fast"
([solve.it.com](https://solve.it.com/)). Whitaker: the loop applies "fractally ... from the
one-week scale to the like 10-second scale" ([YouTube, 17:45](https://www.youtube.com/watch?v=DgPr3HVp0eg)).

**The grain: one to two lines, then look.** "We write 1-2 lines of code at a time, and then
immediately show the result of those steps. Once we have a series of steps that solve a part
of our problem, we package them up into a function" ([solve.it.com](https://solve.it.com/)).
The launch post walks an Advent of Code sub-task in exactly this way (split, inspect; first
element, inspect; sort, inspect; then a function) and notes "as your skill increases you can
tailor the level of granularity" ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).
Howard calls it "our strongest theme in the solve it course ... after every one to two lines of
code output the result" and adds the sample-first rule: "x equals sample zero ... do everything
end to end on x" before scaling up ([YouTube, 40:15](https://www.youtube.com/watch?v=DgPr3HVp0eg)).

**Who writes.** The AI is optional: the course "shows how to use AI in small doses to help
learn as you build, but doesn't rely on AI at all — you can totally avoid AI if you prefer"
([HN, jph00](https://news.ycombinator.com/item?id=45457494)); "the first example shown doesn't
use AI at all. The AI is an optional helper" ([HN, jph00](https://news.ycombinator.com/item?id=45456309)).
Howard on his own use: "It doesn't write my code for me, or my prose, or my devops scripts,
but it's part of the process of me learning as I write them" ([HN, jph00](https://news.ycombinator.com/item?id=45456413)),
and on the launch email: "I didn't use any AI to actually *write* the email ... since I want to
use my own brain" ([fast.ai, 2025-10-15](https://www.fast.ai/posts/2025-10-15-solveit2.html)).
Ries's rule: "never ask the AI to make an artifact for you. Instead, ask it to teach you how to
make the same artifact ... making sure you've mastered each step before moving on to the next
... this is a go slow to go fast kind of situation" ([HN, eries, 2026-06-11](https://news.ycombinator.com/item?id=48485022)).
The delegation that remains is boilerplate the person already understands: Whitaker hands off
"save that to JSON and load it again" but "if it was my first time ever, I'd probably be saying
like, 'Hey, how should I save this?'" ([YouTube, 42:13](https://www.youtube.com/watch?v=DgPr3HVp0eg)).

**The stop rule.** "anytime an AI shows you a function, a library or an API you're not very
familiar with, you should stop and you should go and read the documentation for it. You should
then go back to solve it and say, 'Oh, I want to learn all about this.' And then you should try
running a few different inputs, see the outputs ... And only then should you allow yourself to
move on" ([YouTube, 43:02](https://www.youtube.com/watch?v=DgPr3HVp0eg)). The launch post's
"Learning Trajectory" section: "when the AI suggests something you don't know, it is important
not to skip it and move on ... the evidence of that side-quest can be collapsed below a heading
(for later ref) or deleted" ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).
In the keynote: "don't move on when you're learning a new thing or working on something until
you get it" ([YouTube, 24:56](https://www.youtube.com/watch?v=SUZwYV5JYBM)).

**Dialog engineering.** Defined in 2024 as "Instead of asking AI to generate hundreds of lines
of code at once, you work together in small steps. You might write a line or two, then have
the AI suggest the next piece" ([Answer.AI, 2024-11-07](https://www.answer.ai/posts/2024-11-07-solveit.html)).
In 2025 the emphasis is context hygiene with an autoregressive rationale: "once an AI sees some
mistakes in a chat, the most likely next tokens are going to be mistakes as well ... every time
you are correcting the AI, you are making it more likely for the AI to give bad responses";
therefore edit or remove mistakes, "even edit past AI responses, to steer it", hide messages,
pin messages, so that "AI work sessions ... improve as time goes on, rather than degrading"
([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)). Howard:
"context editing (you can — and should — directly edit AI responses instead of tell the AI it's
wrong)" ([HN, jph00](https://news.ycombinator.com/item?id=45456928)). The same discipline is
claimed to serve the human: "keeping things tidy, using (collapsible) headings ... writing
notes on what you're doing or aiming for, and even past questions+answers with the AI all make
it a pleasure to pick back up old work" ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).

**Shared context.** "the AI should be able to see everything exactly as the human does, and vice
versa, and both human and AI must be able to use the same tools"
([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)); "No
separate instruction files, no context windows that don't match your actual workspace"
([fast.ai, 2025-10-30](https://www.fast.ai/posts/2025-10-30-build-to-last.html)).

**Deliberate practice framing.** "This is all hard work. It's like exercise, or practicing a
musical instrument. And like any pursuit of mastery, I don't know that it's for everyone"
([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)). "You
can't expect to feel like you're in zen ... If you're feeling like that, then you're not in
deliberate practice mode. So ... you can't ask the AI to read the problem for you" — read it,
restate it, then ask the AI "does that look right? Did I miss anything?"
([YouTube, 13:50](https://www.youtube.com/watch?v=DgPr3HVp0eg)). The keynote grounds the same
claim in self-determination theory (autonomy, mastery) and Csikszentmihalyi's "junk flow",
citing Rachel Thomas's dark-flow essay ([YouTube, 2:22–10:03](https://www.youtube.com/watch?v=SUZwYV5JYBM)).

**How it differs from agent workflows, in the team's words.** "This is basically the opposite of
where the rest of the world seems to be heading, towards huge complex artifacts implemented by
AI. The software being developed for this world encourages zero learning, zero craftsmanship,
and zero human agency" ([solve.it.com](https://solve.it.com/)). "If you're familiar with
something like Claude Code or Codex, you might be saying, 'Oh, the unit of operation is 10,000
lines of code within a half an hour execution loop.' This is very much about like one or two
lines at a time" ([YouTube, 11:24](https://www.youtube.com/watch?v=bxDDLMe6KuU)). "rather than
the computer being the agent ... you're the human agent" ([YouTube, 10:09](https://www.youtube.com/watch?v=DgPr3HVp0eg));
"the human is the agent driving the process end to end" ([YouTube, 3:05](https://www.youtube.com/watch?v=01ybLOH1fnU)). On the
cost of going the other way: "If you didn't know the foundations of how to do it before, you
don't now either ... you build up more and more code you don't understand, creating technical
and understanding debt that will eventually become crippling"
([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)). Ries on the
felt hazard: "it's just extremely easy to get into this kind of like soporific state where the
AI is doing the thinking for you and you start to think that all the information that it's
generating for you is like an asset rather than a liability" ([YouTube, 38:00](https://www.youtube.com/watch?v=01ybLOH1fnU)).
The team does not reject agentic steps outright: tools, web search, file tools "that power
Claude Code-style agents", and a `spawn_agent` sub-agent exist (below), and Howard says "we've
invested heavily in really pushing agentic AI to the limit ... discovered some small limited
areas where that approach can be useful" ([YouTube, 10:57](https://www.youtube.com/watch?v=DgPr3HVp0eg)).

## Product mechanics

Source for this section unless noted: the written platform guide
([fast.ai, 2025-11-07](https://www.fast.ai/posts/2025-11-07-solveit-features.html)), the tour
video it transcribes ([YouTube](https://www.youtube.com/watch?v=bxDDLMe6KuU)), the "Welcome To
Solveit" onboarding dialog ([GitHub](https://github.com/AnswerDotAI/solveit_demos)), and the
`dialoghelper` reference ([docs](https://answerdotai.github.io/dialoghelper/core.html)). No
public docs site exists (see Dead ends).

**Surface.** A *dialog* is a linear document of messages of three kinds — *note* (markdown),
*code* (Python, run in a persistent per-dialog kernel, output shown beneath), *prompt* (to the
AI) — plus a rarely used *raw* type; "a conversation between three parties: you and yourself
(notes), you and the computer (code), and you and the AI (prompts)." Dialogs are `.ipynb` files
on an *instance*, a persistent Linux VPS with terminal, git, secrets, file upload, and a public
URL that exposes whatever listens on port 8000. The editor is Monaco, deliberately "fairly
small and down at the bottom [which] emphasizes that this is a REPL/dialog, optimised for
building small, understandable pieces" ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).
Howard's inventory of what the platform combines: ChatGPT, Jupyter + nbdev, bits of
VS Code/Cursor, a VPS, Claude Code's tools, a persistent terminal; plus "any Python function
can be instantly used as an AI tool", live variables referenced into context, metaprogramming
of the dialog, context editing, and collaborative editing ([HN, jph00](https://news.ycombinator.com/item?id=45456928)).

**What the AI sees.** The AI sees every message above the prompt, including code outputs and
pasted images, unless hidden; it does not read ahead ("the golden rule ... it only sees what's
before it", [YouTube, 31:38](https://www.youtube.com/watch?v=bxDDLMe6KuU)). When the dialog
exceeds the context limit, messages are discarded from the top; `H` hides a message from the
AI while keeping it visible to the person; `P` pins a message so it is always sent (pinned
messages are omitted from exports). Every message and every collapsed section shows a token
count. Live variables can be referenced with `` $`name` ``; markdown images are invisible to
the AI unless suffixed `#ai`. A forum thread shows the "sees what you see" phrase confused at
least one student about whether it meant the viewport or the document
([forums.fast.ai](https://forums.fast.ai/t/platform-context-sent-on-each-request-to-the-llm/122584)).

**Editable history.** Any message, including an AI response, can be edited (`n` on a prompt
edits its reply), deleted, cut, copied, pasted, or moved; undo is per message; the AI "always
sees the current state of your dialog, not the edit history." Rachel Thomas: "Its design treats
AI as fallible and keeps the human in control" ([fast.ai, 2026-08-18](https://www.fast.ai/posts/2026-08-18-returning-to-AI/)).

**Features that deliberately slow or gate the AI** (each named as intentional in the launch post
or guide):

- *Default Code toggle* (on by default): after the AI answers a prompt, the next message the
  user creates is a code message. "You're encouraged to implement what you learned rather than
  immediately asking another question." "We're trying to encourage people ... just to write your
  own code rather than have the AI do it for you" ([YouTube, 20:39](https://www.youtube.com/watch?v=bxDDLMe6KuU)).
- *No automatic follow-up prompt*: `Cmd+Enter` submits and does not open a new prompt box;
  "The default behavior encourages you to think about the response or run some code before
  asking the next question." `Alt+Enter` opts into ChatGPT-style rapid chat.
- *Suggested code is inert*: "AI outputs code in fenced blocks, but these are not added to your
  code or run until you choose to do so ... this extra step encourages you to read + refactor
  before mindlessly running" ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).
  `W` extracts fenced blocks into runnable code messages; the onboarding dialog says "We
  encourage you to review code from the AI to understand it for yourself."
- *Learning mode*: "assumes you're trying to learn. The AI asks about your background before
  answering, breaks down explanations, and encourages understanding"; it "will gently guide you
  to writing small steps rather than providing a big chunk of code, unless you really
  specifically ask." Implemented as a different prompt "as well as adding some hidden extra fake
  'chat history' to steer the answer style" (onboarding dialog). Howard reports drifting back to
  it: "the more I use AI, the more I realize actually I need to be pushed to not use AI too much"
  ([YouTube, 34:18](https://www.youtube.com/watch?v=bxDDLMe6KuU)).
- *Ghost text withheld in Learning mode*: inline completions "don't show unless you trigger
  them with a keyboard shortcut" (`⌥+.`). "when you're learning, you should write code
  yourself rather than accept suggestions." Howard: ghost text "is not just distracting, it's
  encouraging you to turn your brain off" ([YouTube, 39:19](https://www.youtube.com/watch?v=bxDDLMe6KuU)).
- *Concise* and *Standard* modes exist for when "you know what you want"; *Super Completions*
  (larger model, bigger chunks) and *Super Edits* (Cursor `Cmd+K`-style) exist with the
  guide's caveat repeated three times: "Writing code yourself builds understanding." The tour
  adds: "if you're clicking this button, it's a bit of a bad sign" ([YouTube, 1:28:20](https://www.youtube.com/watch?v=DgPr3HVp0eg)).
- *Explicit tool grants*: a Python function becomes a tool only when the user writes
  `` &`name` `` in a message; "For security, users grant access explicitly to the model"
  ([Answer.AI, 2026-01-20](https://www.answer.ai/posts/2026-01-20-toolcalling.html)). Built-ins
  are `read_url` and web search; `dialoghelper` adds message-editing and file tools "that
  power Claude Code-style agents" behind a wrench toggle; long tool results are truncated and
  not kept in context. A `spawn_agent` tool "Spawn[s] a subagent to complete a task defined by
  prompt" ([dialoghelper docs](https://answerdotai.github.io/dialoghelper/core.html)); Howard
  used it in the keynote to reproduce a paper's method ([YouTube, 25:46](https://www.youtube.com/watch?v=SUZwYV5JYBM)).

**Features for verifying and re-entering understanding.**

- *Symbol Browser*: a live outline of headings, variables (with current values) and functions,
  cleared on kernel restart — "easy to trace back through your work and understand the current
  state of your Python environment."
- *Restart and run all*: "develop and iterate freely, then restart the kernel and run all cells
  top-to-bottom to make sure everything works in sequence."
- *Collapsible headed sections* with token counts; the recommended way to park a side-quest.
- *Export to module* (`E` marks a cell, nbdev `#| export` style): a dialog named `utils`
  becomes `utils.py`, importable in other dialogs. Ries: "That file is now an importable Python
  module ... I wrote it myself and I understand every line of it. But also, I had a lot of help
  in making it" ([YouTube, 41:10–43:04](https://www.youtube.com/watch?v=01ybLOH1fnU)).
- *Dialog duplication* as templates and as branches for alternatives; *bookmarks 1–9* on
  messages ([dialoghelper docs](https://answerdotai.github.io/dialoghelper/core.html)).
- *Sharing*: gist, `.ipynb`, `.md`, full-script `.py`, a read-only published page, a "blog
  view", import of published dialogs by URL, and by 2026 public fork links on `share.solveit.pub`
  ("Click to run and edit this dialog", [example](https://share.solveit.pub/d/2ec584e79ecd9aed714c438d43f48f8e))
  and a `solveblog` package that serves dialogs as posts ([GitHub](https://github.com/AnswerDotAI/solveblog)).
  Howard on the keynote dialogs: "don't just read it, right? Open it, ask questions ... and then
  write some code" ([YouTube, 33:56](https://www.youtube.com/watch?v=SUZwYV5JYBM)).
- *Real-time collaboration* on one dialog; *screenshot into prompt* (`Cmd+Shift+,`); *pop-out*
  output windows.

**The reading workflow (Lesson 9).** The same method applied to text: convert PDF to markdown;
generate chapter summaries as context; instruct the AI not to spoil; ask questions while
reading the full text; at each chapter end "generate overviews of the conversation between the
reader and the LLM to share as further context for the next chapter"; "Optional: have the LLM
ask questions to check the reader's understanding"; "Optional: create Anki cards within reading
dialogs using fastanki" ([fast.ai, 2026-01-21](https://www.fast.ai/posts/2026-01-21-reading-LLMs/)).
The recording shows the hand-off notes being appended and re-used ("add more handoff notes ...
change the two chapters to be the next one and the previous one ... and start reading again",
[YouTube, 37:43–39:00](https://www.youtube.com/watch?v=zIqLuuyxgE4)). Supporting code is public:
`fastanki` reads and writes Anki collections and syncs to AnkiWeb
([GitHub](https://github.com/AnswerDotAI/fastanki)); `solveit-reader` is a Chrome extension
that imports a page into a dialog as a note ([GitHub](https://github.com/AnswerDotAI/solveit-reader)).
The post's own caveat: "The SolveIt PDF-to-markdown and Anki integration tools currently
require coding ability to set up."

**What is absent.** No quiz, exercise, or reflection prompt is built into the coding surface;
the only understanding check found is the optional one in the reading process. No progress or
mastery tracking; no retention feature beyond the Anki export; no repository-level view (the
unit is a dialog and its instance). The course's own evaluation is community feedback: asked
about evals, Whitaker answered "the evals is kind of like us and this community"
([YouTube, 1:29:32](https://www.youtube.com/watch?v=DgPr3HVp0eg)). Models: "We're using
anthropic models. But we're not just using system prompts" ([YouTube, 19:02](https://www.youtube.com/watch?v=01ybLOH1fnU));
a `REASONING_EFFORT` secret sets thinking depth (onboarding dialog).

## External material (catalogue)

Team-authored, in date order. Each entry says what it adds beyond the site.

- 2024-08-16 · Latent Space, "Answer.ai & AI Magic with Jeremy Howard" ·
  <https://www.youtube.com/watch?v=qO-YqJm0Q1U> · First public naming of "dialogue
  engineering" and the course title; the platform is then "AI Magic", built on Claudette and
  Cosette; the stated audience is "this whole generation of people who are learning to code
  with and because of ChatGPT" (from 1:00:10).
- 2024-11-07 · Answer.AI/fast.ai, "A New Chapter for fast.ai: How To Solve It With Code" ·
  <https://www.answer.ai/posts/2024-11-07-solveit.html> · Announcement; the "line or two, then
  the AI suggests the next piece" definition; "not for you if you believe AI can already replace
  programmers"; the post itself was written by dialog engineering from a Hamel Husain interview.
- 2024-11-07 · "How To Solve It With Code — Overview" (Howard, Whitaker) ·
  <https://www.youtube.com/watch?v=YKeXxj4geRo> · The "wall" problem for LLM-first coders; "it's
  going to take a little bit of unlearning"; originally twice-weekly for eight weeks; beta.
- 2024-11-07 · "background on the course; a discussion with Jeremy and Hamel" ·
  <https://www.youtube.com/watch?v=e9tL_Eg3fpM> · Source interview for the announcement post.
- 2024-12-23/24 · Audrey Roy Greenfeld, "SolveIt-style exploration" notebooks on `execnb` ·
  <https://audrey.feldroy.com/> · A co-lead applying "the SolveIt process in a Jupyter notebook
  to learn new things" outside the platform.
- 2025-08-15 · Hamel Husain with Howard and Whitaker, "SolveIt: The Thinking Developer's
  Environment" · <https://www.youtube.com/watch?v=DgPr3HVp0eg> · The fullest method statement:
  Pólya/OODA/Toyota/Lean equivalence, the fractal loop, deliberate practice, the one-to-two-line
  rule with sample-first, the stop-at-unfamiliar-API rule, editing an AI response to set style,
  the audience segmentation, the "no evals but the community" answer, and Ries's observation
  that no successful company he has seen was built by vibe coding (8:55).
- 2025-10-02 · Answer.AI, "Launching Solveit, the antidote to AI fatigue" (Whitaker) ·
  <https://www.answer.ai/posts/2025-10-01-solveit-full.html> · The canonical method and
  design-intent text used throughout this note.
- 2025-10-02 · Latent Space, "The antidote to AI fatigue — Answer.ai Solveit" (Howard, Ries,
  Whitaker) · <https://www.youtube.com/watch?v=01ybLOH1fnU> · Live demo of editing an answer,
  Learning mode with thinking, one-keystroke code extraction; Ries's chapter-by-chapter
  book workflow with briefing notes and test-reader comments; module composability; the
  Karpathy video-to-article challenge done "line by line ... way slower than just saying like
  press a single button"; the platform is "hosted on a new horizontally scalable multi-server
  platform we built ... entirely using Solveit."
- 2025-10-02 · Whitaker, "What is Solveit? Showing some recent use cases" ·
  <https://www.youtube.com/watch?v=m-GOZSi2R_Q> · Scraping, model poking, recreational maths;
  "once that course is complete hopefully we'll be opening up ... pay as you go subscriptions."
- 2025-10-02 · Hacker News launch thread, team comments ·
  <https://news.ycombinator.com/item?id=45455719> · Howard's component inventory of the
  platform, the "optional AI" clarification, the multiple-testimonials-per-person explanation
  (multiple survey questions), and Whitaker: "the method requires some discipline and
  'unlearning'. It's very hard to show someone an AI tool and not have them treat it just like
  ChatGPT" ([comment](https://news.ycombinator.com/item?id=45456310)).
- 2025-10-13 · Answer.AI, "How I created a book chapter from video transcripts with SolveIt"
  (Turgutlu) · <https://www.answer.ai/posts/2025-10-13-video-to-doc.html> · A worked
  non-coding use: "It took longer than one-shotting the whole thing, but I ended up with
  something I fully understand, and it was still faster than writing it from scratch."
- 2025-10-15 · fast.ai, "How to Solve it With Code course now available" (Howard) ·
  <https://www.fast.ai/posts/2025-10-15-solveit2.html> · "I do not want to create more 'agentic
  AI' – I want humans to have agency, not computers!"; the four-part structure; refund policy.
- 2025-10-16 · Howard on X ·
  <https://x.com/jeremyphoward/status/1978953446662295575> · On the tokenizer article: "made
  by a human deeply engaged in the lesson, with AI help. So it was 10x faster than doing it
  manually, but the result is similar to fully manual."
- 2025-10-17 · "A Tour of the Solveit Platform" (Howard, Whitaker) ·
  <https://www.youtube.com/watch?v=bxDDLMe6KuU> · Feature walkthrough; the source of the
  written guide; mode demonstrations and the ghost-text rationale.
- 2025-10-30 · fast.ai, "Build to Last" (Howard with Chris Lattner) ·
  <https://www.fast.ai/posts/2025-10-30-build-to-last.html> and
  <https://www.youtube.com/watch?v=WJS2YDZO-vc> · The "AI sees what the human sees" principle;
  Lattner's summary of the approach: "instead of bringing in a junior engineer that can just
  crank out code, you're bringing in a senior expert ... somebody that can actually help you
  make better code and teach you things."
- 2025-11-07 · fast.ai, "A Guide to Solveit Features" (Turgutlu) ·
  <https://www.fast.ai/posts/2025-11-07-solveit-features.html> · The only feature reference.
- 2026-01-20 · "The Best Way to Read a Book (That Nobody's Doing)" (Howard, Ries) ·
  <https://www.youtube.com/watch?v=zIqLuuyxgE4> · Lesson 9 excerpt: context set-up, hierarchical
  summaries, curiosity-driven rabbit holes, skeptical verification, hand-off notes for session
  continuity; Howard cites Wozniak's incremental reading as an influence (14:52).
- 2026-01-20 · "How to Actually Understand Dense Machine Learning Papers" (Whitaker) ·
  <https://www.youtube.com/watch?v=U5akUYqCqnA> · Lesson 9 excerpt: LeJEPA paper; set up
  context, summaries, run the paper's code, explore the repo with file tools, build a minimal
  interactive demo "to develop intuition."
- 2026-01-21 · fast.ai, "How To Use AI for the Ancient Art of Close Reading" (Rachel Thomas) ·
  <https://www.fast.ai/posts/2026-01-21-reading-LLMs/> · The seven-step reading process, the
  Anki integration, and the "clunky ... require coding ability" caveat.
- 2026-01-20 · Answer.AI, "Tool calling" (on hallucinated tool calls inside Solveit) ·
  <https://www.answer.ai/posts/2026-01-20-toolcalling.html> · Confirms explicit per-user tool
  grants and the single default tool `read_url`.
- 2026-04-10 · Howard on X · <https://x.com/jeremyphoward/status/2042440101788279094> · "We've
  spent 2 years building a solution that's working well for us — co-writing software side by
  side the AI in an notebook-ish environment. We call it the 'solveit method'."
- 2026-06-04 · Howard, AI Engineer Melbourne keynote, "Growing on Purpose: The Work That Makes
  You" · <https://www.youtube.com/watch?v=SUZwYV5JYBM> · Self-determination theory and
  dark flow as the rationale; "the people getting you to use AI don't care about your autonomy
  and mastery. They care about your outputs"; Sutherland, Engelbart, Iverson, Victor, Lattner as
  the lineage; three worked dialogs (reading the RLM paper and re-implementing it, rebuilding a
  CSS framework from a blog post, writing the talk); "this whole talk was written in Solveit —
  created none of the narrative, none of the slides"; beta status and conference code.
- 2026-06-10/11 · Eric Ries, HN AMA comments ·
  <https://news.ycombinator.com/item?id=48480371>, <https://news.ycombinator.com/item?id=48485022>
  · "explicitly designed for human-in-the-loop creation of artifacts and the development of
  human skills even while you use AI. Otherwise, it's likely that LLMs will cause your own
  skills to atrophy"; the "teach me to make the artifact" rule; re-opening "stay tuned."
- 2026-08-18 · fast.ai, "My friends all hate AI; I just joined an AI startup" (Rachel Thomas)
  · <https://www.fast.ai/posts/2026-08-18-returning-to-AI/> · "SolveIt is explicitly designed to
  be the opposite of an overly 'helpful' chatbot."
- 2026-08-19 · Answer.AI, "Why LLMs can't make your code simpler" (Alvarez Vecino) ·
  <https://www.answer.ai/posts/2026-08-19-llms-code-simpler.html> · Naur's theory-building
  applied by a team member; a public fork-able close-reading dialog of Naur; billing design.
- Repositories · `dialoghelper` (tools; changelog to 0.2.43, 2026-09) ·
  <https://github.com/AnswerDotAI/dialoghelper>; `solveit_demos` (onboarding and example
  dialogs, "nuggets", instant-dialog URLs) · <https://github.com/AnswerDotAI/solveit_demos>;
  `solveit_client` (programmatic dialog API) · <https://github.com/AnswerDotAI/solveit_client>;
  `fastanki`, `solveit-reader`, `solveblog`, `solvecdp`, `fastcdp-chrome` (browser bridge).
- Course material · Ten recorded lessons (2025 cohort) plus sixteen from the 2024 preview are
  behind enrolment; only the two Lesson 9 excerpts above and the 2024 overview are public. The
  fast.ai "Let's Build the GPT Tokenizer" article
  (<https://www.fast.ai/posts/2025-10-16-karpathy-tokenizers.html>) is a public artifact made
  with the method.

## Claims and evidence

**Claims made.**

- Understanding: the result is "working code that you understand. Code you can modify, extend,
  and maintain. Code that becomes part of your expanding skill set rather than a black box
  you're afraid to touch" ([fast.ai, 2025-11-07](https://www.fast.ai/posts/2025-11-07-solveit-features.html)).
- Learning compounding: "your own skills develop even faster than AI improves"
  ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).
- Productivity: "This method may sometimes be slower initially, but produces something more
  valuable" (same guide); "10x faster than doing it manually, but the result is similar to
  fully manual" ([X, 2025-10-16](https://x.com/jeremyphoward/status/1978953446662295575)); "go
  slow to go fast" ([HN, eries](https://news.ycombinator.com/item?id=48485022)); Answer.AI's
  own output with 12 people is offered as the existence proof ("When people ask how we
  accomplish so much with such a small team, this is the answer",
  [Answer.AI, 2024-11-07](https://www.answer.ai/posts/2024-11-07-solveit.html)).
- Model behaviour: dialogs "improve as time goes on, rather than degrading"; small batches
  "make the LLMs much more intelligent" ([YouTube, 2:51](https://www.youtube.com/watch?v=DgPr3HVp0eg)).
- Well-being: "at the end of every day, I feel honestly energized, excited"
  ([YouTube, 32:43](https://www.youtube.com/watch?v=SUZwYV5JYBM)); "changed our lives at
  Answer.AI, and hundreds of our users say the same thing"
  ([Answer.AI, 2025-10-02](https://www.answer.ai/posts/2025-10-01-solveit-full.html)).

**Evidence offered.**

- Testimonials: 178 on the site from the ~1,000-person preview cohort
  ([solve.it.com/testimonials](https://solve.it.com/testimonials)), collected by an
  end-of-course survey with several questions, which is why one person appears several times
  ([HN, jph00](https://news.ycombinator.com/item?id=45461980)). Themes: "I do have
  problem-solving skills"; "it's hard to see that going slower is making you faster"; "if you
  suppress the urge to move faster than you can, you will also understand what you build"; a
  job-interview anecdote ("methodically tested code along the way"). Self-selected, self-report,
  no comparison group, no delayed measure.
- Artifacts: a community project showcase built by a student
  ([showcase](https://solveit-project-showcase.pla.sh/)); the tokenizer article; Ries's book;
  Answer.AI's own products. These show output, not comprehension.
- Argument from literature: the keynote's SDT, behavioural activation, and flow citations
  are general psychology, not studies of Solveit; the launch post's autoregression argument is a
  mechanism claim without a reported test.
- No controlled measurement of learning, retention, or comprehension was found in any
  source, and the team says its evaluation is qualitative community feedback
  ([YouTube, 1:29:32](https://www.youtube.com/watch?v=DgPr3HVp0eg)). Whitaker's reported
  failure mode is itself informal evidence that the method is hard to hold: "The most common
  failure mode that students fall into in our course is actually trying to go way too far, way
  too fast with AI" ([YouTube, 16:58](https://www.youtube.com/watch?v=DgPr3HVp0eg)).

## Reception (secondary)

Labelled secondary; useful for what the product feels like in use, not for its claims.

- **Hacker News launch thread** (2025-10-02, 111 points, 102 comments,
  <https://news.ycombinator.com/item?id=45455719>). Non-alumni were confused about what was
  being sold ("I have no idea what it is ... What is the value add?"; "a sales pitch for a coding
  course for would-be vibe coders, with AI training wheels"), sceptical of price and of a course
  being needed to learn a tool, and after watching the video summarised it as "basically a
  'Jupyter notebook' type of app where you can type code and chat with the AI ... I'm not sure
  it's 'revolutionary'". Several questioned the testimonials' authenticity (many quotes per
  person). Alumni replied in numbers (Ries acknowledged they came from the course Discord and
  denied astroturfing): "It's really hard to not to try to vomit out solutions and to go about
  something in a methodical way ... It takes a lot of practice"; "a programming environment for
  AI assisted literate programming ... an intelligent notebook"; "it can take more steps and
  iterations than other tools, that is part of the difference."
- **Chris Thomas, "The Human is the Agent"** (2025-09-24,
  <https://christhomas.co.uk/blog/2025/09/24/the-human-is-the-agent-how-solveit-changed-my-programming-journey-after-25-years/>).
  A 25-year programmer from the first cohort: building "piece by piece, with me understanding
  each component"; "I find myself initially pausing to carefully consider my prompts ... to
  front-load the context and clearly specify my end goals"; editing AI output as the key
  feature. Linked from the site and the HN thread by the team.
- **Chris Thomas, "Why I love SolveIt"** (2026-06-03,
  <https://microblog.christhomas.co.uk/blog/why-i-love-solveit>). Describes Learning mode as
  "training wheels with resistance. It drags you back, forces you to think about what you are
  doing ... As the dialog grows, the resistance fades"; reports model switching within a
  dialog (2026); describes a close-reading loop over video lectures with Anki cards generated
  "from my specific confusions" — "The friction is the learning." Linked from fast.ai's August
  2026 post.
- **Rens Dimmendaal, "The Solveit approach turns frustrating AI conversations into learning
  experiences"** (2025-08-25, archived at
  <https://web.archive.org/web/2025/https://rensdimmendaal.com/posts/solveit-course-key-take-aways>).
  Written as a student before joining Answer.AI. Frames the method as three counters to three
  LLM properties: RLHF over-eagerness → small steps and clarifying questions; autoregression →
  edit and prefill responses; flawed training data → include relevant context. Shows a
  side-by-side of Claude's wall of code versus Solveit asking about prior experience first.
- **Aditya Kabra, "How I Built Solveit Project Showcase"**
  (<https://himalayanhacker.substack.com/p/how-i-built-solve-it-project-showcase>). A student
  cataloguing "200+ community projects" from 4,500 Discord messages; useful as a count of
  output, not comprehension.
- **fast.ai forum** (<https://forums.fast.ai/t/platform-context-sent-on-each-request-to-the-llm/122584>).
  One student's uncertainty about what "the AI can see what you can see" means in practice.

## Mapping to the Phase A landscape

Clusters are those in the landscape sweep's [Emergent clusters](landscape-sweep.md#emergent-clusters);
mechanisms are those in the evidence note's [Summary table](evidence-and-mechanisms.md#summary-table).

**Cluster 7, friction and metacognitive checkpoints.** Solveit is a friction design at the finest
grain found: Default Code, the withheld follow-up prompt, inert fenced blocks, and suppressed
ghost text act on every turn, and the method's "understand, restate, plan" step acts at task
start. The sweep's [Observations for the deep pass](landscape-sweep.md#observations-for-the-deep-pass)
recorded that in Cluster 7 "no item sits at task start"; Solveit fills that point, and also
the mid-task point, but not commit, PR, or merge, where Phase A's gates live. Its pause is
structural (the default action is authoring) rather than a checkpoint that interrupts an agent,
which distinguishes it from Covate's quiz-blocking and from Cursor's plan-then-apply in
[Cluster 7](landscape-sweep.md#cluster-7--friction-and-metacognitive-checkpoints).

**Cluster 1, retrieval practice and Socratic tutoring.** Learning mode is a Socratic tutor of the
kind [Cluster 1](landscape-sweep.md#cluster-1--retrieval-practice-and-socratic-tutoring-in-the-agent-loop)
catalogues (background question first, small steps, feedback), but the polarity differs from
the Claude Code Learning style's `TODO(human)`: there the agent writes and hands back a piece;
here the person writes and asks for a piece. No quiz, spaced repetition, or mastery journal
exists on the coding side; the optional "have the LLM ask questions to check the reader's
understanding" and the Anki export apply to reading, so the sweep's finding that spaced
repetition "on a codebase" is thin stands.

**Cluster 5 and Cluster 6, living artifacts and provenance.** The dialog is both: notes, code,
outputs, and AI turns in one file, exportable and forkable, offered as the reason "old work" is
easy to pick back up, and as an nbdev-style literate source of modules. Unlike the
[provenance cluster](landscape-sweep.md#cluster-6--provenance-and-intent-capture-seeds-missed),
which keeps the agent's raw trace, Solveit's record is curated by editing and deletion; what
survives is what the person decided was worth keeping, and the hand-off notes in the reading
workflow are an explicit session-continuity artifact. Whether anyone other than the author
reads a dialog is, as with Cluster 5, not checked by the tool.

**Cluster 4, explanation on demand.** Ask-about-anything-visible is the same affordance as the
"explain" modes in [Cluster 4](landscape-sweep.md#cluster-4--explorable-maps-and-explanation-on-demand),
scoped to a dialog rather than a repository; there is no map of a codebase.

**Cluster 8, discourse.** Whitaker's "technical and understanding debt" (2025-10-02), Thomas's
dark flow (already in [Cluster 8](landscape-sweep.md#cluster-8--discourse-and-framing)), and
Alvarez Vecino's Naur reading (2026-08-19) place Answer.AI in the same framing as the essays
there; the Naur argument itself is covered in the evidence note's
[Naur section](evidence-and-mechanisms.md#naur-the-theory-is-not-in-the-text).

**Cluster 9, measurement.** Nothing; consistent with the sweep's finding that no shipping tool
measures comprehension.

**Mechanisms.** *Generation effect*: the default-code and inert-suggestion design makes the
person produce the next line before any AI version is on screen, the closest shipping
instance found of the evidence note's "write the expected ... before seeing the agent's"
sketch; the withheld ghost text is generation-before-reveal at the token level. *Step-wise
engagement* (which the evidence note lists as having direct computing-education support): the
one-to-two-lines-then-output rule is that mechanism as a norm. *Self-explanation and
elaborative interrogation*: restating the problem, writing notes, and the stop rule are
prescribed but rely on discipline; no prompt asks for an explanation before proceeding.
*Desirable difficulty and expertise reversal*: the Learning/Concise/Standard switch is a manual
expertise-reversal control, and the team's own account (experienced users "still got to use
learning mode") is the fluency illusion the evidence note describes. *Spaced repetition*:
present only for reading, via Anki. *Reading and approving*: the fenced-block gate forces a read
before a run but is still reading; the method's answer is that the person should mostly not be
approving AI code at all.

**What is new relative to Phase A.**

1. An environment whose *default* is human authorship with AI output inert until promoted —
   every Phase A item in Clusters 1 and 7 accepts agent authorship and adds a check.
2. Placement at task start and at every step, the workflow point the sweep found empty.
3. The editable, curated dialog as the understanding artifact, versus append-only traces.
4. The same method carried into reading books and papers with hand-off notes and retrieval,
   the one place Solveit operationalises retrieval and spacing.
5. An explicit stop-at-unfamiliar-API rule stated as a norm of the practice.
6. Enforcement by course, community, and habit rather than by tooling; the team's own
   reported failure mode is students abandoning the method for speed.

**What Solveit does not cover, in Phase A terms.** Nothing at the repository or team scale (a
dialog is one person's working document); nothing at hand-off between people beyond sharing a
dialog; no measurement; no check that the look-back step happened; no mechanism for the case
Phase A centres on, where an agent has already written the code and the person must recover a
model of it.

## Dead ends

- No public documentation site: `docs.solve.it.com` returns HTTP 525; `/docs`, `/pricing`,
  `/faq`, `/course`, `/changelog` on solve.it.com return 404; the in-app `solveit_docs` tool
  ("Full reference documentation for Solveit") is available only inside a dialog. The fast.ai
  features guide and the tour video are the only public reference.
- No public changelog for the platform; only `dialoghelper`'s release notes.
- Course content: the ten 2025 lessons and sixteen 2024 preview lessons are behind enrolment;
  the Discord is private. Only the two Lesson 9 excerpts and the 2024 overview are public.
- Current status: the exact date and scope of the 2026 "launch" implied by the August 2026
  billing post, and whether a subscription or credit price is published anywhere, could not be
  sourced; the site says signups are closed. A Product Hunt "June 17th, 2026" date surfaced by
  search belongs to a different product built with Solveit, not to Solveit.
- Cohort size is stated as 1,000 (2025 posts), "over 2,000" (December 2024 post), and "3,000
  people" (June 2026 keynote); not reconciled.
- Price is $500 on the site and $400 in the team's October 2025 HN reply; not reconciled.
- Latent Space's own show-notes page for the October 2025 episode was not located; the YouTube
  recording was used.
- Reddit: searches returned no thread about Solveit and reddit.com blocked direct queries.
- No talk, post, or podcast about Solveit by Isaac Flath or Daniel Roy Greenfeld was found;
  Audrey Roy Greenfeld appears only as a 2024 course lead and in two "SolveIt-style" notebooks.
- Rens Dimmendaal's post is linked from solve.it.com but its URL now returns 404; the Internet
  Archive copy was used.
- The X threads linked from the launch were read through the syndication endpoint; replies in
  those threads were not retrieved.
- YouTube transcripts are auto-generated captions; timestamps are approximate and quoted
  wording may differ slightly from speech.
