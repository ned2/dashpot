---
status: research
date: 2026-09-13
---

# "Understanding is the new bottleneck" (Geoffrey Litt, AI Engineer World's Fair 2026)

This note stands in for a talk the user remembers only vaguely as "Understanding is the New Bottleneck". A web search on the exact title returned one talk of that name plus several reactions to it; the talk's recording, official transcript page, speaker-written companion essay, and published skill were all located and read directly. Everything below is drawn from those primary sources unless marked otherwise. This is a landscape survey of what the talk says, not an assessment of fit for Dashpot.

## Source identification

**Speaker.** Geoffrey Litt, Design Engineer at Notion (previously Ink & Switch; PhD in HCI, MIT). Speaker page: <https://ai.engineer/speakers/geoffrey-litt>.

**Venue and date.** Design Engineering track, AI Engineer World's Fair, San Francisco. Litt opens the recording with "Thank you for coming to the Design Engineering track" (transcript at 0:00). The World's Fair 2026 ran June 29 – July 2, 2026 at Moscone West (<https://www.ai.engineer/worldsfair/2026>); the essay is dated July 2, 2026 and the recording was published July 10, 2026. The AI Engineer catalogue pages label the talk "AI Engineer World's Fair **2025**" (<https://ai.engineer/talks/WkBPX-oDMnA-understanding-is-the-new-bottleneck>, <https://ai.engineer/speakers/geoffrey-litt>); this appears to be a catalogue error, since the talk cites Storey's February 2026 post, describes a Notion feature that "launched this morning" whose release note is dated 2026-07-01, and Litt's own essay and newsletter say July 2026. Treat the year as 2026. (Settled 2026-09-13: the World's Fair 2026 schedule page, <https://ai.engineer/worldsfair/schedule>, lists "Understanding is the new bottleneck", Geoffrey Litt, Design Engineering track, Track 6, "Day 3 — Session Day 2", 10:45–11:05am, with a session id dated 2026-07-01.)

**Canonical URLs.**

- Recording: "Understanding is the new bottleneck — Geoffrey Litt, Notion", AI Engineer YouTube channel, published 2026-07-10, 19:33. <https://www.youtube.com/watch?v=WkBPX-oDMnA>
- Official talk page with corrected, timestamped transcript, chapter summaries, and a resources list: <https://ai.engineer/talks/WkBPX-oDMnA-understanding-is-the-new-bottleneck>
- Written companion essay by the speaker, with all 36 slides and four screen-recording videos: <https://www.geoffreylitt.com/2026/07/02/understanding-is-the-new-bottleneck>
- Newsletter issue (2026-07-04) carrying the essay plus context: <https://buttondown.com/geoffreylitt/archive/understanding-is-the-new-bottleneck/>
- Tweet thread version linked from the essay (not fetched; X returned HTTP 402): <https://x.com/geoffreylitt/status/2072522251300409556>
- The `/explain-diff` skill the talk presents (two files, HTML and Notion variants): <https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524>
- Slides: there is no separate slide deck; the essay embeds every slide as an image with descriptive alt text.

**Other candidates with the same title.** Eric J. Ma, "Understanding is the new bottleneck", newsletter essay, 2026-08-27 (<https://dspn.substack.com/p/understanding-is-the-new-bottleneck>). It is an essay, not a talk; it names Litt's talk as the source of the framing and restates his three techniques, adding a playable quiz. It is not what the user is looking for, but it is a reaction (see Related material). Several other 2026 blog posts reuse the phrase; all found were summaries of Litt's talk.

**Confidence.** High that this is the talk the user means: the title matches exactly, it is a 2026 AI-engineering conference talk, and the user's recollection of "PR-time activities" and "Anki-style quizzes on the codebase" maps directly onto the explainer-plus-quiz technique. One element of the user's recollection does not appear in the talk: an "explorable directory tree with directed questions and annotations". Nothing resembling a directory tree appears in the recording, the transcript, the essay, or the skill. The nearest items are the Prolog debugger micro-world (a timeline with self-annotations) and the migration "command center" (which shows file trees evolving). That element may come from another talk or be a conflation; see Dead ends and gaps.

## Outline of core ideas

### Problem framing

- **Opening claim.** "It is still important for people to understand how code works" — pitched as a "hot take" for an AI-engineering audience, with an audience poll showing near-universal agreement and Litt conceding selection bias (transcript 0:22–0:55).
- **Pressure.** Agents are "landing fifty thousand line PRs, and it is getting harder to keep up" (1:13). The figure is an illustration, not a measurement (the official page says so explicitly).
- **Reframing what "understanding" is for.** Litt says most people, including pro-understanding people, answer "why understand?" slightly wrongly (essay, "Why understand?").
  - *Understanding to verify*: checking the agent's work — matches the spec, does not take down production, is well-architected — which are all "thumbs up / thumbs down" decisions. Litt says this is what people mean by "code review is the new bottleneck" (2:53). Agents are getting better at these checks given a verification loop, and Litt welcomes that: "the role of humans in correctness checking is decreasing. And you know what? I actually don't hate that" (3:38).
  - *Understanding to participate*: "it's not just one loop" (4:15). A project is many iterative loops with the agent; what you learn in one loop is the foundation for the next idea. "When you have rich conceptual structures in your head that you can fluently recombine really fast without going out to ask some agent or some human how it works, that gives you the ability to fluidly take creative leaps, and that's the human part of the work" (4:50). This is the "real reason" understanding matters and "not something that we can just wash away with better agents" (5:08).
- **Name for the failure mode.** *Cognitive debt*, credited to Margaret-Anne Storey and Simon Willison (5:23). Like tech debt, "you might get away with it for a little bit, but at some point you get burned if your understanding degrades." The lived symptom: "You're vibe coding, things are going well, and then at some point you realize, 'Wait, I have no idea what's going on. I basically can't participate anymore'" (5:42). Slide 9 quotes Storey: "the humans involved may have simply lost the plot".
- **Method.** Treat understanding as a teaching problem and borrow from education: "this is not the first time that any human has asked this question. There is a field. It's called education" (6:25). The generative design question for any code change: "if you sent a team away for a year to come up with a personalized curriculum just to explain this one code change to you, what would that look like?" (7:07).
- **Larger point.** The closing section widens the claim from code to everything: "it's just important for humans to still understand how everything works" (17:16), tied to Alan Kay's 1972 vision of the personal computer as a medium that develops the person using it. "The point was always to augment, not just automate" (essay). "Not just taking ourselves out of loops, but actually putting ourselves more deeply in loops than we ever have before" (18:48).

### Evidence and anecdotes

The talk offers personal practice and anecdotes rather than studies:

- Litt uses `/explain-diff` "every day, and a lot of my coworkers do as well" (7:20). No adoption numbers or measured outcomes are given.
- The quiz was motivated by a specific failure: he sent a PR to a coworker believing he had read and understood it, "and she asked me the most basic question. And I was like, 'Oh, no. I don't know.' I clearly hadn't understood. I had fooled myself" (10:05–10:22). He reports the quiz "really is shocking the number of times this has caught me" (11:18).
- Building a Prolog interpreter "for my own learning" and finding Wikipedia-style descriptions of its mechanics hard until a visualisation made them click (12:38–12:56).
- Migrating his personal website between frameworks: a Claude-written migration script "seemed like it worked, and I read the script and I was like, 'Ah, I don't know'" (13:58).
- The printed-explainer habit: "I print these out and take them to the coffee shop sometimes and just read them" (9:50).

Everything above is verified against the transcript. The talk cites no controlled study of any technique.

### Proposal 1: Code explainer docs (`/explain-diff`)

**What it is.** A skill (Claude Code-style; "two versions… one that outputs HTML, one that outputs Notion", 11:49) that turns a code change into a structured explainer document. Published at <https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524>. The talk's worked example: a zen-garden drawing game whose perspective changed from top-down to isometric.

**When it runs.** On demand, after the agent finishes a change and before human review — "whenever an agent finishes some work, it's an opportunity for an explanation — an artifact" (essay). Litt's stated habit is to read the explainer before the raw diff: "I still read the code diff but I always read this first" (essay).

**Structure (from the talk; confirmed against the gist).** In this order:

1. *Background* — "We do not start with what happened in this change. It starts by teaching me, 'Hey, here's how this system works. Here's the game engine we're using. Here's the coordinate system. Here's the subsystems'" (7:56). Skippable or personalisable to what the reader already knows (8:17). The gist asks for a beginner-friendly deep explanation first, then narrowing to the changed components.
2. *Intuition before details* — state the goal ("make the garden feel three-dimensional using only 2D drawing tricks") and related concepts (what isometric projection is) before any code, "sort of as like a well-written commit message, a little deeper" (8:23–8:45). The gist asks for toy data and diagrams here.
3. *Interactive figures, where they earn their place* — e.g. dragging rocks around the garden while their coordinates and Z-layer painting order update (8:51). Delivered as an embedded HTML block in Notion or inline JS in the HTML variant.
4. *Literate code diff* — "we don't just throw a list of files in order… Give me prose. Explain it to me in the right order. Tell me before each file what's going on" (9:30–9:39). The gist itself says only "Group/order the changes in an understandable way" (corrected 2026-09-13: "ordered by execution or dependency flow rather than arbitrary file order" is from yudhiesh-oc's fork in the gist's comment thread, not from any of Litt's five revisions; see [track-hand-off-checks.md](track-hand-off-checks.md#litts-explain-diff-what-the-gist-actually-contains)).
5. *Quiz* — see Proposal 2.

**Other rules in the gist (re-verified 2026-09-13 against the gist's two files and five revisions via the GitHub Gists API).** "Broadly explore surrounding code" for the Background section; "Don't use ASCII diagrams. Always use simple HTML designs"; the HTML variant is "a single self-contained HTML file which includes CSS and JavaScript", saved outside the repo with a `YYYY-MM-DD-` date prefix, e.g. `/tmp/2026-01-12-explanation-<slug>.html`; the Notion variant creates the page with the Notion MCP tools; and write "with the clarity and flow of Martin Kleppmann". (Corrected 2026-09-13: an earlier draft of this paragraph also credited the gist with a five-step "narrative arc" workflow and a "strictly passive data" prompt-injection clause. Neither is in Litt's files: the workflow is yudhiesh-oc's fork (2026-07-15) and the passive-data clause is ehsan-ami's proposal (2026-07-17), both posted as comments on the gist; see [track-hand-off-checks.md](track-hand-off-checks.md#litts-explain-diff-what-the-gist-actually-contains).)

**Claimed effect.** Faster review than a raw diff; the reader is "led up to the point where I can even begin to understand" (8:07); the document is portable enough to print and read away from the IDE.

### Proposal 2: Quizzes as a speed regulator

**What it is.** A five-question, medium-difficulty interactive quiz at the bottom of every explainer, generated by the agent about the change (11:03).

**When it runs.** At the end of reading an explainer, gating hand-off: "my rule is I don't send code to others on my team to review unless I can pass the quiz about what my agents wrote" (11:03). The essay adds "and I do the same when reviewing others' code".

**Rationale.** Andy Matuschak's "books don't work" — "it's really easy to read a book and not realize you didn't understand it" (10:32) — and Matuschak and Nielsen's Quantum Country, which embeds spaced-repetition recall questions in an essay and emails you the questions later so "you cannot get through this essay without understanding it, or at least without remembering it" (10:43–10:52).

**Framing.** "I think of it as sort of a speed regulator. Everything AI is speed up, speed up, speed up… How do we make sure we're not just moving at the speed of correctness but also of understanding? And the quiz is that speed regulator" (11:27). The essay: "I mechanically ask 'do I actually understand?' so that I can remain a full creative participant."

**Quiz design rules.** (Corrected 2026-09-13.) Litt's gist specifies the quiz in one paragraph — five questions, "medium difficulty, difficult enough that you actually need to understand the substance of the PR to answer them, but not gotchas", interactive multiple choice with feedback on click (HTML) or toggle blocks with a ❌/✅ explanation per option (Notion) — and none of Litt's five revisions (the last on 2026-07-01) adds anti-guessing rules. The rules an earlier draft of this note attributed to the gist — randomise option order per question, balance correct-answer positions, keep options comparable in length, grammar, specificity, and confidence, distractors tied to a real misunderstanding, no single-phrase answers — are from yudhiesh-oc's rewritten skill posted as a comment on 2026-07-15, after commenters reported that the correct answer was usually the longest or the second option. The comment thread is summarised in [track-hand-off-checks.md](track-hand-off-checks.md#litts-explain-diff-what-the-gist-actually-contains).

**Scope note (inference).** Litt's quiz is a one-shot check at hand-off time; the spaced-repetition scheduling of Quantum Country is cited as inspiration but the talk does not describe re-quizzing later. The official page adds the caveat that "remembering an answer is not itself a guarantee of understanding or permanent retention."

### Proposal 3: Micro-worlds

**What it is.** Agent-built, ephemeral interactive environments in which the developer "inhabits" a system and builds intuition by manipulating it, after Seymour Papert's "Mathland" (12:06–12:25). Two worked examples:

- *Prolog interpreter debugger.* "I had Claude make me a microworld. This is a debugger, ephemeral UI that was built specifically to visualize the internal implementation of my programming language" (13:02). It shows program code, stack state, a timeline you scrub through step by step, and a commenting feature so he could "leave comments for myself on the timeline so I remember what I was thinking" (13:25). Its value went beyond the bugs fixed: "as I was fixing the bugs, I was getting a feel for the machine… if you just have an agent to go fix the bug, you don't get that peripheral vision. If you live in a microworld, you do" (13:36).
- *Migration "command center".* After a Claude-written migration script proved unreviewable, he asked Claude to "make me essentially a video game where I do the port myself": old site left, new site right, a Next button that runs and displays each step's commands, and file trees underneath showing files moving (14:10–14:26). "It's kind of like if I did it manually, but I'm just clicking a button. So I'm getting some of the benefit of doing it iteratively without the pain" (14:26–14:35).

**When it runs.** On demand, when a written explanation is insufficient or a change is hard to review by reading; the artefact is throwaway ("the point isn't building software to ship", 14:42).

**Claimed effect.** Intuitive, "deeper and richer than just a written document" understanding (1:55), plus peripheral understanding of the surrounding machine. Takeaway slide: "agents can write code to help us understand code" (14:42).

### Proposal 4: Shared spaces

**What it is.** Collaborative surfaces where a whole team, together with agents, builds shared mental models: shared vocabulary "for parts of a system… UI elements or concepts" is what lets a team "jam and have creative ideas together" (14:58–15:33). Two mechanisms described, both Notion features:

- *Multiplayer chat threads* with several humans and several agents, so that instead of each person talking to their own agent, "we're in a shared space. We can see each other's communication. It's kind of like going from one-on-one conversations to Slack channels" (15:38–16:09).
- *Commentable agent-written documents*: when Claude writes a plan into a collaborative page, a teammate can comment on the relevant passage and discuss it there, "not on my computer locally" (16:14–16:35). Litt notes Claude and Cursor can now run inside Notion (launched "last week" relative to the talk; Notion's 2026-07-01 release note documents "External Agents" and interactive HTML blocks: <https://www.notion.com/releases/2026-07-01>) and that his team "builds a lot of our code in Notion itself" for this reason (16:44).

**When it runs.** Continuously, as the medium for planning and discussion. The talk labels this section "quickly" and it is the least developed of the three.

### What the talk says does not work, or works only conditionally

- **Reading a raw diff top to bottom** is "the most naive explanation" (6:53) and "a pile of files edited in alphabetical order with no explanation" (essay); it is not rejected — Litt still reads the diff — but it is demoted to last.
- **Reading alone** does not guarantee understanding: "reading is hard, and I am lazy. People are lazy" (10:05). Hence the quiz.
- **Interactivity for its own sake**: "you have to be careful with interactivity. It can just be a crutch, and it can be kind of slop, to be honest. But used tastefully, it can provide an understanding that's hard to achieve with just static pictures" (9:16).
- **Delegating the fix entirely** loses "peripheral vision" of the system (13:36).
- **Verification alone as the reason to understand** is the "subtly wrong" framing (2:37); a human whose only role is thumbs-up/down will be automated out of that role and will have lost the ability to participate.
- **A working migration script** can be correct and still leave the human with no model of what happened (13:58).

## Sources the talk draws on

Verified as cited in the talk or the essay, with what the talk takes from each:

- Margaret-Anne Storey, "How Generative and Agentic AI Shift Concern from Technical Debt to Cognitive Debt", blog post, 2026-02-09. <https://margaretstorey.com/blog/2026/02/09/cognitive-debt/> — The term *cognitive debt* and the quoted line that "the humans involved may have simply lost the plot" (slide 9). Storey's post itself cites Naur's "programming as theory building", Brooks, Beck, and the Fowler/Thoughtworks Future of Software Engineering retreat, and proposes remedies (one person must understand each AI change before deployment; document why not just what; knowledge-sharing rituals; watch for warning signs of eroding shared understanding). Storey later formalised the idea as a "Triple Debt Model" (technical, cognitive, intent) in an arXiv paper: "From Technical Debt to Cognitive and Intent Debt: Rethinking Software Health in the Age of AI", 2026-03-23 (rev. 2026-04-06), <https://arxiv.org/abs/2603.22106> — not cited in the talk; noted as the formal successor.
- Simon Willison, "How Generative and Agentic AI Shift Concern from Technical Debt to Cognitive Debt", link post, 2026-02-15. <https://simonwillison.net/2026/Feb/15/cognitive-debt/> — Credited with popularising the term; Willison adds his own experience of losing his grasp of his projects' architecture when moving fast with agents. No remedies proposed.
- Andy Matuschak, "Why books don't work", 2019-05-11. <https://andymatuschak.org/books/> — The argument that reading produces a false feeling of understanding ("transmissionism"), motivating the quiz.
- Andy Matuschak and Michael Nielsen, "Quantum computing for the very curious" (Quantum Country). <https://quantum.country/qcvc> — The model of embedding recall questions in an explanatory essay with spaced-repetition follow-up emails; Litt borrows the embedded quiz, not the scheduling.
- Seymour Papert, *Mindstorms: Children, Computers, and Powerful Ideas* (1980), source of "Mathland" and the Logo Turtle. Free edition and context at MIT Media Lab: <https://mindstorms.media.mit.edu/> — The idea of learning by inhabiting an environment, and "the point isn't the robot, it's the kids that are changed" (12:25).
- Alan Kay, "A Personal Computer for Children of All Ages", Proceedings of the ACM National Conference, 1972, doi:10.1145/800193.1971922; readable copy at <https://mprove.de/visionreality/media/kay72.html> — The Dynabook image of two children editing a game's code to learn physics; the talk's closing frame that computing's original purpose was to "level us up as humans" (18:03).
- Litt's own `/explain-diff` skill, <https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524> — the artefact behind Proposals 1 and 2.
- Notion release notes 2026-07-01 (HTML blocks, External Agents), <https://www.notion.com/releases/2026-07-01> — the features behind the interactive figure and Proposal 4. Listed on the official talk page's resources, not cited by Litt verbally.

Not sourced: the "50,000-line PR" figure (illustrative, per the official page) and the astronaut meme slide (linked from the essay to <https://x.com/geoffreylitt/status/2071362040346955777>, not fetched).

## Related material

By the speaker, extending the thesis (all primary, listed as "Related reads" at the end of the essay):

- "Enough AI copilots! We need AI HUDs", 2025-07-27. <https://www.geoffreylitt.com/2025/07/27/enough-ai-copilots-we-need-ai-huds> — argues for non-copilot form factors "that more directly extend the human mind"; the micro-world idea is a HUD instance.
- "AI-generated tools can make programming more fun", 2024-12-22. <https://www.geoffreylitt.com/2024/12/22/making-programming-more-fun-with-an-ai-generated-debugger> — the original write-up of the Prolog debugger shown in the talk.
- "Code like a surgeon", 2025-10-24. <https://www.geoffreylitt.com/2025/10/24/code-like-a-surgeon> — delegate secondary grunt work to stay focused on the main thing; the "understand to participate" stance in a workflow framing.
- Newsletter issue, 2026-07-04. <https://buttondown.com/geoffreylitt/archive/understanding-is-the-new-bottleneck/> — adds that Litt co-hosts a podcast, *Small Talk*, with Max Schoening on AI and malleable software (episode "Is chat the final form of UX for AI?"), and notes companion World's Fair talks by Max Drake (agents in tldraw) and Charlie Holtz ("orchestras over factories"). Not fetched further.

Reactions and extensions by others:

- Eric J. Ma, "Understanding is the new bottleneck", newsletter, 2026-08-27. <https://dspn.substack.com/p/understanding-is-the-new-bottleneck> — restates Litt's three techniques, adds a playable quiz, and brings in Tim Schipper's critique of PR review. Primary for Ma's own take; secondary for Litt's.
- Storey's arXiv paper above is the strongest scholarly extension of the problem framing.
- Numerous 2026 summaries exist (sparsenotes.com, startuphub.ai, genai-playbook.com, braindetox.kr, daily.dev, videohighlight.com, youtubesummary.com). They were used only to locate the talk; none is cited for content here and none adds material beyond the recording.

## Dead ends and gaps

- **No separate slide deck.** Searched for "Understanding is the new bottleneck" slides/Speaker Deck/PDF; none published. The essay embeds all 36 slides as images with descriptive alt text, which is the best available substitute.
- **Tweet threads not fetched.** <https://x.com/geoffreylitt/status/2072522251300409556> (thread version of the talk) and <https://x.com/geoffreylitt/status/2071362040346955777> (meme slide) both return HTTP 402 to unauthenticated fetches; the Twitter oembed endpoint also returned nothing. The essay states the thread is the same content as the talk, so nothing is expected to be missing.
- **"Explorable directory tree with directed questions and annotations."** Not in this talk, its essay, its transcript, or the skill. Searched for 2026 talks combining "mental model", "codebase", "directory tree", "annotations", "quiz", "spaced repetition"/"Anki"; found nothing matching a talk. Adjacent tools surfaced only via secondary blogs (e.g. an open-source "Understand-Anything" code-knowledge-graph tool mentioned at <https://theroadtoenterprise.com/blog/onboarding-to-new-codebase-with-ai-tools>; secondary here, but since verified from its repository — an Egonex AI Claude Code plugin that builds a clickable knowledge graph with a directed Q&A panel and no human-annotation feature — in [track-explorable-maps.md](track-explorable-maps.md#agent-era-maps-and-wikis); updated 2026-09-13). The user may be conflating a second talk or a follow-up; a next pass could ask the user where they saw the tree or search the rest of the Design Engineering track at World's Fair 2026.
- **"Anki-style" recall.** The talk's quiz is a one-time gate at hand-off; spaced repetition appears only as Quantum Country inspiration. If the user recalls a genuinely spaced/scheduled codebase quiz, that is either an inference from the Quantum Country reference or from a different source.
- **Event year label.** The AI Engineer catalogue says "World's Fair 2025" on both the talk and speaker pages; every content signal says 2026 (see Source identification). Settled 2026-09-13 by the organisers' own 2026 schedule page, which lists the session on the second session day (2026-07-01); the catalogue label is the error.
- **No podcast or interview follow-ups found** specific to this talk; the *Small Talk* podcast is by the speaker but predates and is broader than the talk. No conference Q&A is in the recording.
- **No empirical evidence** for any technique beyond the speaker's own practice; the talk does not claim otherwise. Storey's blog post and arXiv paper are the nearest research-grade material on the problem side; nothing research-grade was found on the remedy side in this pass.
