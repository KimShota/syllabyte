# Spec: SyllaByte UI/UX implementation

Status: **settled spec** (grilling session 2026-10-04, 37 decisions). Decision numbers
(Q1–Q37) are kept inline in brackets so each rule can be traced to the session; §16 lists them.
Build in the phase order of §14. Phase 0 first.

> **Revised 2026-10-13 (`plan/per-ku-profiling-plan.md`, branch `per-ku-profiling`).** To follow the capstone proposal
> (§3.2), levels are measured **per Knowledge Unit** by a **computerized adaptive test** (2PL IRT, `catsim`), and
> **Week 7 is no longer part of the app**. Revised here: rules 1–4 of §2, §3.1, §3.1b, §3.8, §3.9, §3.10, §4.1–§4.4, §4.6,
> §5.1, §5.2, §6.1, §6.2, §7.2, §7.3 and §17. Decisions Q15, Q16, Q33, Q34 and Q36 are superseded (§16). Everything
> else stands. The per-KU plan is the source of truth for the assessment design (decisions D1–D18).

## 0. Context

Inputs: `SyllaByte UI Wireframes.pdf` (10 screens), `Syllabyte UI Literature Review.pdf`
(28 papers plus a traceability table), the capstone proposal, and the current repo.

**What the UI delivers:** the closed loop the literature review identifies as the novel
contribution: a baseline check → a level for every Knowledge Unit that the student can see and
correct → a playlist of tailored micro-videos with in-video checks → a short check before each
lecture that moves levels at lecture boundaries, with a card saying what changed and why. Every
override, skip, confidence rating and correction is research data for RQ1–RQ3, so instrumentation is
a core feature from Phase 0.

**Repo state (2026-10-04):** the file-based Week-1 pipeline (`scripts/generate_shorts.py`)
produces, per KU, `final.mp4` (9:16, 1080×1920, 60–90 s), `audio/captions.srt`, `script.json`
(segments → beats with `narration` + `visual` + `source_refs`), and per-segment timings in
`SegmentAudio`. Slide PNGs live in `runs/<id>/images/`. `assessment_agent` is empty. There is no
item bank, learner model, API or web app. Mongo/MinIO scaffolding exists in
`syllabyte_common/{db,storage}.py`. Node 24 + npm are installed.

**The wireframe PDF is the visual and copy-style spec.** Where this document changes a screen,
this document wins. The prototype's content is the **computational-ss** course (causal
inference), not Operating Systems [Q2].

---

## 1. Supplementary literature review (2023–2026 only)

These sources fill gaps the existing review leaves open. Only 2023–2026 work is used, matching
the existing review's window. They were read through search extracts and abstracts, because
publisher pages blocked full text. Check the numbers before citing them.

| Source | Finding | What it changes |
|---|---|---|
| [In-lecture quizzes improve online learning (Communications Psychology, 2025)](https://www.nature.com/articles/s44271-025-00234-5) | Quiz questions interpolated in an online lecture improved learning for university and community-college students. Preliminary evidence they may narrow an achievement gap | Backs the in-video checkpoint (§3.4) |
| [Active learning strategies in video learning: meta-analysis (Educational Research Review, 2025)](https://www.sciencedirect.com/science/article/abs/pii/S1747938X25000454) | 54 studies, 74% from 2019–2025. Embedded questions were the most-studied strategy (46%) | Checkpoints are the right first feature. Effect size not in the extract; read before citing |
| [Zheng et al. 2024 (Active Learning in Higher Education)](https://journals.sagepub.com/doi/abs/10.1177/14697874221126920) | N = 121. Segmentation, and segmentation + self-explanation, beat continuous video. The combination beat continuous video overall after controlling for prior knowledge | Pause at a segment boundary, resume only on **Continue**, and pair it with a self-explanation prompt at the end (§3.7) |
| [Wang & Xu 2024 (Education and Information Technologies)](https://link.springer.com/article/10.1007/s10639-024-12806-9); [2025 self-explanation meta-analysis (EPR)](https://link.springer.com/article/10.1007/s10648-025-10001-x) | N = 143. Scaffolded self-explanation prompts improved learning and reduced cognitive load. Fill-in-the-blank did best | Screen 7 uses a **sentence frame** (§3.7) |
| [Pan & Carpenter 2023 (EPR)](https://link.springer.com/article/10.1007/s10648-023-09814-5); [Pretesting in the classroom (2023)](https://link.springer.com/article/10.1007/s10648-023-09805-6); [Placement matters (PB&R, 2023)](https://link.springer.com/article/10.3758/s13423-023-02274-6) | Pretests improve later learning of pretested content, and can narrow attention to it | Onboarding shows answers and explanations on review. Items are spread across topics (§3.2) |
| [Conditions for effective learning without upfront instruction (EPR, 2025)](https://link.springer.com/article/10.1007/s10648-025-10103-6) | Practice with feedback can reduce overconfidence compared with passive instruction | With Wagner 2026 (existing review), backs the **next-session check** (§3.3.3) |
| [Tharumalingam et al. 2025, playback-speed meta-analysis (EPR)](https://link.springer.com/article/10.1007/s10648-025-10003-9) | 24 studies, 110 effect sizes. Small cost up to 1.5×, significant near 2× | Speed capped at 1.5×, logged per view (§3.4) |
| ["Don't know" option and guessing rate (J Autism Dev Disord, 2024)](https://link.springer.com/article/10.1007/s10803-024-06452-w) | A "don't know" option introduced systematic error: guessing tendency was the strongest predictor of measured knowledge, and it hides partial knowledge | "Not sure" is missing evidence, never wrong. Dropped where a confidence row exists (§2) |
| [Planning promotes studying (Contemporary Educational Psychology, 2025)](https://www.sciencedirect.com/science/article/pii/S0361476X25000876) | N = 357. Planning prompts worked only when plans were good | Week 7 offers concrete slots plus real reminders (§3.9) |
| [WCAG 2.2 (W3C, 2023)](https://dequeuniversity.com/resources/wcag-2.2/) | 2.5.8 targets ≥ 24×24 px; 2.5.7 non-drag alternative; 2.4.11 focus not obscured | Move up/down buttons, sheets that never hide focus, captions/transcript/keyboard from day one |
| 9:16 vs 16:9 for learning | No peer-reviewed comparison found (2023–2026) | Vertical is a design choice to test; device and orientation are logged |

---

## 2. Global product rules

These apply on every screen. Claude Code should treat them as invariants and test them.

1. **Per-KU levels (1–3) drive which video version a student gets.** A topic is a lecture. The overall level is only a summary (per-KU plan D2, D6; supersedes Q15).
2. **Levels change only at a lecture boundary (the end of a check before a lecture) or by student correction** (per-KU plan D11; supersedes Q33). Answers in between update the estimate behind the scenes but never a level the student sees.
3. **"Not sure yet" is missing evidence, never a wrong answer** [Q5]. It appears in the baseline, the checks before a lecture and prove-it. It **does not** appear in in-video checks (the "Guessing" confidence covers it) or retention quizzes.
4. **Every "because…" string a student sees is built from a template over stored data, never written freely by an LLM** (screens 1-result, 2, 5, 8, the "What changed and why" card). Numbers in reason text must equal the stored counts. Tests assert this.
5. **Nothing overlays the video**, including captions [Q3, Q17].
6. **No autoplay, no infinite feed, no streaks, points, leaderboards, or peer comparison.** Students only see their own history.
7. **When evidence is mixed or missing, default to more support** (lower level, more help).
8. **Every user action in §6.2's event list is logged** through the typed API client, in every phase [Q20].
9. **Wrong answers use amber, never red** [Q10]. Copy keeps the "not graded" tone.
10. **Accessibility:** WCAG 2.2 AA; tap targets ≥ 44 px tall; every drag has a button alternative; `prefers-reduced-motion` respected for UI transitions.

---

## 3. Screen specs

Screen numbers match the wireframe PDF. New screens have letter suffixes.

### 3.0 First run: Welcome (0a) → Consent (0b) [Q18]
- **0a Welcome:** "SyllaByte makes short animated videos from your course's own slides, tuned to what you already know." Three bullets: *The videos are AI-made, and you can always see the source.* · *Nothing here is graded.* · *You can correct anything we guess about you.* Button **Get started**.
- **0b Consent:** a summary card (what's collected: answers, confidence, skips, watch events, notes; who sees it; how to withdraw), a **Read the full consent form** link (renders `apps/web/content/consent.md`, marked `TODO: replace with IRB-approved text`), and two equal-weight buttons: **I agree to take part** / **Use SyllaByte without research data**.
  - Decliners get full access, but no events or responses are stored for research (§6.3).
- Shown on first login only (Phase 1+). In Phase 0 the app starts here, and Reset demo returns here.
- Phase 3: the server assigns condition A/B **after** consent. Decliners get condition A with no research logging (confirm with IRB, §15).
- Next: screen 1.

### 3.1 Baseline check (screen 1) [Q4, Q5; per-KU plan D8, D9]
- Layout as wireframed:
  - Back button and **Pick my own level** link at the top.
  - Eyebrow `{COURSE} · START`, title "A quick check, no grade".
  - Subtitle "{n} questions, about {m} minutes. It only tunes your videos. 'Not sure' is a fine answer." and the line
    "Each question adapts to your last answer, so you can't go back."
  - n-segment progress bar, "Question i of n".
  - Question card with the lecture as eyebrow, stem, 3 options + dashed **Not sure yet**.
  - "After question n" info card. **Back** (first question only) / **Next**.
- **A fixed-length adaptive sitting** (`cat_week0_length` 16, capped by `cat_items_per_topic` 4 × the first
  `cat_week0_lectures` 4 lectures; 12 on the 3-lecture dev course), interleaved lecture by lecture. Each question is the most
  informative unseen item of its lecture at the current ability estimate (§4.1). No confidence row. Next is enabled once an
  option is selected; nothing is preselected. A choice can change until **Next**, then it is locked: **there is no going
  back**, and **Back** and the top arrow exist on the first question only. Closing the tab resumes on the same question.
- **Pick my own level:** works at any point. A sheet with the three level cards (§3.12 descriptions) sets **every KU**.
  Answers given so far are kept as evidence, and the level source is `student`.

### 3.1b Start result (new) [Q15 revised]
- "We suggest **Level N · {name}** overall", then **one card per lecture** (title, a bar, "{k} concepts at Level L · …"), each
  opening into its concepts (a card per KU: `LevelBar`, level, templated reason, **Change**).
- A lecture the baseline did not cover starts from the ability pooled over the answers so far ("We have not asked about
  “{lecture}” yet…"); with no answer anywhere it is a dashed **Not covered yet** card at Level 1.
- **Review my answers:** each item with the student's answer, the correct answer and a one-line explanation (pretesting benefit).
- Actions: **Keep these levels** (primary) · **Change a concept** (opens §3.12) · **Pick one level for everything**.
- Next: Playlist.

### 3.2 Playlist (screen 2) [Q12, Q13, Q22, Q27, Q31]
Top to bottom:
1. **Study tasks card** (only when a task is due; condition A/B; §3.18).
2. **Check card** (the check before the upcoming lecture, when due; §3.9), and the **What changed and why** card (§3.10) after a lecture boundary moved levels.
3. **Next-session cards** (max 2 per visit, one at a time; §3.3.3).
4. Header: eyebrow `{COURSE} · LEVEL {overall}`, title "Your playlist", subtitle "{n} videos, about {m} minutes. Play them in any order."
5. **Why this order** card: templated text (§4.3), or "You set this order" after a manual reorder. **Change order** link.
6. Video cards (`VideoCard`): poster thumbnail with play icon, title, "{duration} · Lecture {n}", tag (*Fills a gap* amber / *Refresher* violet / *New for you* teal / *You added* neutral), review-status badge if not `unreviewed` (§3.15), ⋮ menu. The current or next video gets a primary border.
   - If a card plays a fallback level version, it also shows "Level 2 version · Level 3 coming soon".
7. **Skipped (n)** collapsed group. Skipped cards stay playable.
8. Footer: "Done so far: {n} videos" · **Watch again** (list of watched videos).
- When every video is watched: "That's this week's playlist." with Watch again. No autoplay.
- **⋮ menu:** Skip · Move up · Move down · View in course map.
- **Skip:** the card moves to the Skipped group, and the toast "Skipped '{title}'. **Say why** · **Undo**" appears. It shows for 8 s, paused while focused or hovered. Say why opens screen 3.
- **Change order:** edit mode with ↑/↓ on each card (plus drag on desktop), **Done**, and **Reset to suggested order**. A manual order persists until reset or the next rebuild.
- **Empty states [Q31]:** "Your Lecture {n} videos are being made. Ready by {date}." with Watch again + Course map links. No spinner.
- Bottom tabs on mobile: **Playlist · My levels · Course**. A left sidebar on desktop.

### 3.3 Skip reason sheet (screen 3) and prove-it (3b) [Q12]
- **Screen 3** as wireframed: a bottom sheet over the video card.
  - Eyebrow "SKIPPED · OPTIONAL", title "Why skip this one?", subtitle "Your reason tunes your playlist and your next check-in. It never affects a grade."
  - Options: *I already know this* / *It looks too hard right now* / *No time today* / *Not relevant to my course* / dashed *Rather not say*.
  - Info card about "I already know this". **Undo skip** / **Save reason**.
  - Also reachable later from a skipped card.
- **3b Prove-it** (after saving "I already know this"): "Want to show it? One question." **Try it** / **No thanks**.
  - The item comes from the bank (`context: prove_it`) and allows "Not sure yet".
  - **Pass:** "Nice, we'll leave this one out." The video stays skipped, and the topic is marked known for that video only. **No level change** [Q33].
  - **Fail or Not sure:** "No problem, it's back in your playlist." with a **Keep it skipped** link.

#### 3.3.3 Next-session check card (new) [Q13]
- Eligible: a watched video whose next-session item hasn't been answered, on the **first visit ≥ 12 h after watching**. Oldest first, **max 2 per visit**, one card shown at a time. **Expires after 7 days** unanswered.
- Card: "Yesterday: {title}. You said **{Yes/Maybe/No}**. Try one question?" → **Try it** / **Not now**.
- Inline item (no "Not sure", no confidence), then a result with explanation and "You said {JOL} · Result: {right/not quite}".
- A wrong answer tags that video's topic as a gap and queues a refresher (§4.3). It doesn't change the level.
- Also queued for: a checkpoint answered right with "Guessing" [Q10].

### 3.4 Player (screen 4) [Q3, Q4, Q10, Q17, Q21]
**Layout:**
- **Mobile:** a header with back ‹, eyebrow "VIDEO n OF m", title, **AI-made** chip and ⓘ button. Below it the **Tailored for Level N · {k} changes · See how** chip (teal; opens screen 5).
- Then the video (9:16, centered, `max-height: 62svh`), the caption band **below** the video, then the scrubber (with a checkpoint tick) and time, then the control row **CC · 1x · Transcript · Notes**, then the state panel.
- **Desktop ≥ 1024 px:** video left, header and state panel right. Sheets become right-side panels.

**One panel at a time below the controls:**

| Video state | Panel |
|---|---|
| Not started | Poster + large play button (never autoplays) |
| Playing / paused by user | Nothing beyond controls |
| At checkpoint | Quick check (video paused) |
| Ended | Navigate to screen 7 |

**Quick check (checkpoint):**
- **Exactly one per video**, at `checkpoint.t` = end of the main *deliver* segment [D5/Q29].
- Pauses the video on `timeupdate` when `t ≥ checkpoint.t`. Eyebrow "VIDEO PAUSED · QUICK CHECK", then the stem and 3 options (**no "Not sure"**).
- Selecting an option slides in "How sure?" **Guessing · Pretty sure · Certain**.
  - Changing the answer keeps the confidence.
  - The reveal fires automatically once both are set (no Submit button).
- **Show a hint** (Level 2) is available until the reveal. At Level 1 the hint is shown inline from the start. At Level 3 there is no hint [Q29]. Hint use is logged.
- **Skip this check:** resume with nothing revealed (logged).
- **Result:**
  - **Correct:** "Right" + explanation + **Continue video**.
  - **Wrong:** "Not quite" + correct answer highlighted + explanation + **Rewatch this part** (seeks to the start of the segment just watched and plays) and **Continue video**.
  - **Correct + Guessing:** an extra line, "You got it, but you said you were guessing. We'll check this again tomorrow." (queues a next-session item).
- A rewatch never re-triggers the same check in that view.

**Controls:**
- **CC:** captions are on by default, and the choice is remembered globally (also in Course → settings). Implementation: `<track kind="captions" src=captions.vtt>` in `mode="hidden"`, with cues rendered by the app via `cuechange` into a band below the video. White on dark translucent, 16–18 px.
- **Speed:** cycles 1× → 1.25× → 1.5× → 0.75× → 1×. The label shows the current speed.
- **Transcript sheet:** narration sentences interleaved with *[Visual: …]* lines from `Beat.visual`. The current sentence is highlighted, and tapping a sentence seeks there.
- **Notes sheet:** opening it pauses the video. A text box. Each saved note is stamped with the video time (tap to seek). Notes are private, listed per video in the Course map, and included in Download my data.
- **Keyboard:** Space/K play-pause · ←/→ ±5 s · C captions · T transcript · N notes · Esc closes sheet.

**ⓘ About this video sheet:**
- Source line: "Made from: Slides {deck} · slides {list}".
- AI disclosure: "The animation is AI-generated from these slides."
- Review status badge (§3.15).
- **Check the claims in this video** (→ screen 6) · **Report an error** (→ §3.15) · **Skip video** (skips, returns to Playlist, same toast as §3.2).

### 3.5 Tailoring receipt (screen 5) [Q14, Q29, Q31]
- A sheet as wireframed: eyebrow "HOW THIS VIDEO WAS TAILORED", title "{title}, for Level N", subtitle "Made from your {topic} level and your last answers. You can undo any of it."
- One row per `TailoringDecision` (§7.5): tag **Left out** / **Added** / **Set to** + what. The reason line comes from a template over the student's evidence, or "Standard for Level N" when there's no evidence.
- Footer copy: "When your answers are mixed, we lean toward including more help, not less."
- If a fallback version is playing: an extra row, "Level {n} version · Level {m} coming soon".
- **Show the full version ({duration})** → plays the Level 1 version (Phase 0: same file, with a "Prototype: only one version exists yet" note [Q2]) · **Back to the video** · **This level is wrong for me** (→ §3.12).

### 3.6 Claim check (screen 6) [Q11]
- Header badge = review status. Eyebrow "{TITLE} · {n} CLAIMS", title **"Check it against the slides"**, subtitle "The video is AI-made. Open the slide behind any claim and tell us if it does not match."
- **Claim card:** claim text, source line "Slides · slide {n}", **View slide**, and verdict buttons **Matches** / **Does not match**. "Does not match" opens an optional one-line note.
- **View slide sheet:** the slide PNG (pinch-zoom), its extracted text below for screen readers, and a **Play this part** mini-player underneath that plays only that claim's segment of the AI video.
- Info card "What happens to a report": "It goes to your instructor with the claim and the slide. Until it is checked, the video shows a note that a student flagged it."
- A mismatch verdict sets the variant to `flagged` (§3.15).

### 3.7 Before you move on (screen 7) [Q13]
- A header with **Replay** and "VIDEO n OF m · DONE", eyebrow `{TITLE}`, title "Before you move on", subtitle "Videos feel clearer than they are. A quick guess about tomorrow helps you spot what to revisit."
- In order:
  1. "Without looking back, could you explain {topic} to a classmate tomorrow?" **Yes · Maybe · No**.
  2. **OPTIONAL · Say it in one sentence:** a sentence frame with blanks (e.g. "Randomization makes the groups ___, so the difference in means equals ___."), plus a **Write it my own way** toggle for free text. "Your sentence stays private. It helps us pick tomorrow's question."
  3. "This video was **Too easy · Just right · Too hard**".
  4. **Tomorrow** info card (teal): "We will ask 1 question on this video. Your guess and your answer will show side by side under My levels."
- Nothing is required. **Next video: {title}** opens the next player paused on its poster. After the last video, the button reads **Back to playlist**. **Skip this** leaves without saving.

### 3.8 My levels (screen 8) [Q14, Q30, Q33, Q35]
- Eyebrow `{COURSE} · MY LEVELS`, title "What your videos are based on", subtitle "This is our best guess, not a grade. If a level looks wrong, correct it."
- **Overall card** (dark): "OVERALL START LEVEL · Level N · {name}". "Levels update after your check for “{lecture}”." while one is due, else "Levels update after each lecture's check. Videos already made keep the level they were made at."
- **The "What changed and why" card** (§3.10), when a lecture boundary moved levels. **Do the check for “{lecture}”** when one is due.
- **One section per lecture, one card per concept (KU):** name, `LevelBar`, level, templated reason, and **Correct this** (→ §3.12).
  - If the student set the level: "Set by you" + **Use suggested level**.
  - If the video was made at another level: "Its video was made at Level a. You are now Level b, so new videos on it use Level b."
  - Dashed **Not checked yet** cards use **Set it myself**.
- **Calibration block 1: "How sure you were, and how often you were right."**
  - Source: checkpoint answers with confidence. Correct-after-hint counts as right.
  - Rows Certain / Pretty sure / Guessing with bars, "x of y".
  - Hidden until ≥ 5 rated answers ("We'll show this after 5 quick checks").
  - Sentence by pattern: Certain accuracy ≤ Pretty sure → "Your 'Certain' answers were right {a} times in {b}, no better than 'Pretty sure'." · Guessing accuracy < 0.5 → "Your guesses were honest: you were usually wrong when you said so." · otherwise → "Your confidence matches your results well."
- **Calibration block 2: "Your guess vs the next day."**
  - The last 5 pairs: "{title} · You said **Maybe** · Next day: **right**".
  - A summary after ≥ 3 pairs: "When you said *Yes*, you got the next-day question right {a} of {b} times."
  - Hidden until ≥ 1 pair.
- **You, since your first check:** a list of level changes from the student's own history (“Selection bias formula” went from Level 2 to Level 1 at your “Randomization” check), or "No changes yet."
- Footer: **Download my data** · **Reset my model** (§3.19).

### 3.9 The check before a lecture (replaces Week 7 invite and re-check) [per-KU plan D8, D9]
- **When it is due:** before the upcoming lecture's videos, from the lecture week after the baseline (the baseline already covers a lecture it
  asked about in the same week). It appears as a card at the top of the Playlist: eyebrow "Before “{lecture}”", "A quick check before this
  lecture.", "{n} questions, about {m} minutes… Not graded.", **Start the check** (or **Continue the check**) and **Not now**.
- **The sitting** (`/check?l=N`): eyebrow `{COURSE} · LECTURE N CHECK`, title "A quick check before this lecture", same layout, same rules as
  §3.1 (adaptive, no going back, "Not sure yet" allowed, close **×** to leave and resume later). `cat_prelecture_new` (4) questions on the
  lecture and `cat_prelecture_review` (2) from earlier lectures, chosen from the earlier lecture whose ability is least certain. The order is
  new, new, review, new, new, review. The last button reads **Start the lecture**.
- **Not now:** skips it. Nothing changes and the card goes away for that lecture.
- **At the end:** the levels the answers support are published and the playlist is rebuilt (§3.10, §4.3). A level the student set is not overwritten.
- There is no scheduling, calendar file or reminder: the check is short and sits where the student already is.

### 3.10 What changed and why (replaces Week 7 results) [per-KU plan D11]
- A card on the Playlist and My levels after a lecture boundary moved any level: eyebrow "What changed and why", "Your levels moved after the
  “{lecture}” check.", then one line per KU that moved: "{KU}: Level a → b. {r} of {n} right on “{lecture}” so far. Your next videos on it will use
  Level b." (a template over the stored counts), and the line "Videos already made keep the level they were made at. You can correct any level yourself."
- **Got it** dismisses it for good; **See my levels** (Playlist only). Nothing needs deciding: there are no proposals, accept/keep/dispute
  buttons, or undo window. The student's lever is **Correct this** (§3.8, §3.12), which applies at once, is logged as the student's choice and can be undone.

### 3.11 Course tab (new) [Q8]
- **Course map:** grouped by lecture → topic → videos (`VideoCard`) with status *Watched* / *In playlist* / *Skipped* / *Not made yet* (dashed, no play, "Expected by {date}" or "Coming soon").
  - Each available video has **Add to my playlist**, which adds it with the tag *You added* (logged).
  - The student's notes are listed under each video.
- **Course info & settings** (collapsed, at the bottom):
  - Syllabus summary and lecture schedule; what "AI-made" means.
  - Captions default; the weekly email toggle (§9.4).
  - Consent and data: view consent, **Withdraw from research** (§3.19).
  - Sign out.

### 3.12 Change level sheet (new, shared) [Q14]
- Opened from **Correct this** / **Set it myself** (screen 8), **This level is wrong for me** (screen 5), and Change a topic (§3.1b).
- Content:
  - Topic, plus the current level with its reason.
  - Three choice cards, each with a one-line description of what changes in the videos:
    - **Level 1 · Foundations:** "More steps, hints and a recap."
    - **Level 2 · Core:** "Key steps, hints if you ask."
    - **Level 3 · Advanced:** "Skips the basics, adds a 'what if'."
  - Optional reason chips: *Videos feel too easy* · *Videos feel too hard* · *I learned this elsewhere* · *Other* (+ one-line note).
  - **Save level**, then a toast "{Topic} set to Level N by you. Your playlist will update. **Undo**".
- Effects: level `source = student`, and the topic's playlist entries swap to that level's versions. A check never silently overwrites a level the student set (§3.9); only its suggestion moves.

### 3.13 Instructor review queue (new, Phase 2) [Q25]
- Desktop-first, `instructor` role.
- **`/instructor`:** a table of all variants (topic, level, lecture, status, open reports, mismatch count). Filter by status and lecture. Sorted by open reports first, then unreviewed.
- **`/instructor/videos/[id]`:** player on the left; tabs on the right:
  - **Claims:** slide, verdict counts, student notes.
  - **Reports:** category, time (click to seek), note.
  - **Script:** read-only narration + visuals per segment.
- Actions:
  - **Approve:** status becomes `approved`, and open reports are resolved.
  - **Hide:** status becomes `hidden`, with an optional student-facing message.
  - **Request fix:** the video stays `flagged`, and a note goes to the author. A new version uploaded for the same KU + level replaces the old one automatically, and its status resets to `unreviewed`.
- Each report: **Resolve** with *fixed / not an error / duplicate*.
- A daily email digest to the instructor when new reports arrive. No student emails about outcomes. No in-browser script editing or regeneration.
- `researcher` role: the same views read-only, plus the export (§3.19).

### 3.14 Control condition B shell (new, Phase 3) [Q26]
- The same sign-in, consent and visual design. One tab, **Course materials**: lecture recordings by lecture (slide decks until recordings exist), with a plain player (same CC/speed/keyboard, no checkpoints, transcript only if one exists).
- The **Study tasks card** at the top. Same retention quizzes. No levels, playlist, checkpoints, AI videos or My levels.
- Event logging is the same as in condition A.

### 3.15 Error report and review status [Q21]
- **Report sheet** (from ⓘ):
  - "What's wrong?" chips: *A fact is wrong* · *The picture doesn't match what's said* · *Captions or audio are off* · *Text is cut off or overlaps* · *Something else*.
  - The video time is attached automatically ("at 0:42", editable). An optional note.
  - **Send report**, then "Thanks. Your instructor will see this with the clip."
  - *A fact is wrong* also offers a link to screen 6.
- **Badges** (player header, ⓘ sheet, video cards):

| Status | Badge | When |
|---|---|---|
| `unreviewed` | "Not yet reviewed by your instructor" (neutral outline) | default |
| `flagged` | "A student flagged part of this video · being checked" (amber) | ≥ 1 open report or mismatch verdict |
| `approved` | "Reviewed by your instructor" (teal) | instructor approved |
| `hidden` | removed from playlists and map. If already listed: "This video was taken down for fixes" | instructor hid it |

- Unreviewed videos are **shown with the label, not blocked**. Flags apply course-wide (variants are shared) and are anonymous.

### 3.16 Missing, empty, error and offline states [Q31]
- **Missing level version:** fall back toward more support: L3 → L2 → L1; L2 → L1; L1 → L2 only as a last resort. The card and receipt say "Level {n} version · Level {m} coming soon".
- **No version at all:** excluded from the playlist; *Not made yet* in the Course map.
- **Load errors:** an inline "Couldn't load this. **Try again**". The player shows the poster + "Video didn't load · **Try again**".
- **Offline:** responses and events are queued in IndexedDB and flushed in order on reconnect. The UI never blocks on a failed event post.
- New or replacement videos appear on the next load. No push notifications.

### 3.17 Hidden demo menu (Phase 0 only) [Q6, Q13, Q20]
- Opens with `?demo=1` or a 1-second long-press on the course eyebrow. Hidden in Phase 1+ builds unless `NEXT_PUBLIC_DEMO=1`.
- Items:
  - **Participant code** (e.g. `P03`, stamped on every event).
  - **Reset demo** (clears all state and the log, returns to Welcome).
  - **Jump to screen…:** Welcome, Baseline check, Start result, Playlist, Player (each video), Receipt, Claim check, Before you move on, My levels, Course, Check due, Lecture 3 check quiz, Levels changed, My levels (mid-course student), Empty playlist; tools: Simulate next day, Simulate next week.
  - **Simulate next day** (+24 h on the mock clock).
  - **Download session log (JSON)**.
  - **Open `/debug/events`** (a live event timeline).

### 3.18 Study tasks and retention quizzes (Phase 3) [Q27, Q28]
- **Study tasks card:** "{Task} · ~{min} min · due {day}". Shown at the top of Playlist (A) or Course materials (B), above next-session cards.
- **Questionnaires** (NASA-TLX, SUS, UEQ-S, Likert efficacy, trust scale) open in **Qualtrics** in a new tab, with an anonymous `pid` query parameter.
- **Retention quizzes (in-app):**
  - Triggered at module end and again 14 days later. **Due within 3 days**; a missed quiz expires and is recorded as missing.
  - Onboarding layout, one item per screen, Back allowed, a review step, then **Submit**.
  - **No "Not sure", no confidence, no per-item feedback, no score.** End screen: "Thanks, your answers are saved for the study. They don't affect your levels or grade."
  - Items are instructor-written or approved, identical across conditions, never shown elsewhere, and stored in `study_responses`. They **never feed the learner model**.
  - Course config `reveal_retention_scores_after_week_14` defaults to false.

### 3.19 Download, reset, withdraw, export [Q30]
- **Download my data:** generates a ZIP immediately with `profile.json` (levels + history + sources), `responses.csv`, `events.csv`, `notes.md`, `self_explanations.md`, and a plain-language `README.txt`.
- **Reset my model:** a confirm sheet: "This clears your levels and rebuilds your playlist from scratch. Your watch history, notes and study answers stay. You'll retake the 8-question check. We keep a copy for the study unless you withdraw." → **Reset and retake the check** / **Cancel**. The old model is archived with `reset_at`, not deleted.
- **Withdraw from research** (Course → settings): stops research logging from that moment. An optional **Also delete my past research data** deletes events and study responses, and the deletion is recorded.
- **Researcher export** (`/research/export`, researcher role):
  - CSV + Parquet per collection: participants (pseudonymous ID, condition, consent flags), events, responses, level snapshots (Week 0/7/14), proposals, skips, claim reports, plus a data dictionary.
  - No names or emails. The ID → email key file downloads only after a second confirmation.

---

## 4. Logic (`packages/assessment_agent/`)

All thresholds live in the course config (§5.2). The engine of record is Python (`assessment_agent`, on `catsim`); in Phase 0 a TypeScript port of §4.1 and §4.3 runs inside the mock, and a parity test replays golden sessions recorded from the Python engine and fails on any difference in the item chosen or in ability (per-KU plan D3).

### 4.1 Levels from adaptive tests [Q15 revised; per-KU plan D1–D10]
- **A topic is a lecture; one ability (θ) per topic**, from a 2PL CAT (`catsim`): start θ 0, next item = the most informative unseen item (ties go to
  the earlier item in the pool), θ by bounded maximum likelihood with Dodd's heuristic for an all-correct / all-wrong pattern.
- **Item bank:** 3 items per KU, one per Bloom tier (basic = Remember/Understand, applied = Apply/Analyze, advanced = Evaluate/Create), generated per
  course upload (§7.3). Difficulty β = tier offset (−1 / 0 / +1) + 0.5 × the LLM's single rating of the KU; discrimination α = 1.0 until post-pilot calibration.
- **Evidence for a lecture's θ:** its assessment items and its videos' quick-check, next-day and prove-it items (latest answer per item). A hinted
  answer counts as the same item made easier (β − `irt_hint_beta_shift`); "Not sure" counts toward a sitting's length and for nothing in the estimate.
- **KU level (tier rule):** Level 3 if θ ≥ β of the KU's advanced item; Level 2 if θ ≥ β of its applied item; else Level 1. A lecture answered entirely
  "Not sure" is Level 1. A lecture not asked about yet borrows the θ pooled over every answer so far (provisional); with none it is "not checked".
- **Overall level** = median of the KU levels, rounded down.
- Reason templates, for example:
  - "From your {n} answers on “{lecture}” ({r} right), you are likely to handle this concept's applied questions but not yet its advanced ones, so we use medium pacing."
  - "You chose 'Not sure' on all {n} questions on “{lecture}”, so videos start from the basics with more hints."
  - "We have not asked about “{lecture}” yet. From your {n} answers so far ({r} right) and how hard this concept is, we start you at Level {l}. We will check it before that lecture."
- **Sittings:** the Week 0 baseline and the check before each lecture are fixed-length (§3.1, §3.9); items answered in any sitting are never asked again.
- **When a level changes:** only at a lecture boundary (the end of a baseline or pre-lecture check), when it is published and the playlist is rebuilt (§3.10).

### 4.2 Video version selection
- KU level → `VideoVariant(ku, level)`, with the §3.16 fallback. A video is made once, at the KU's level when first needed, and never remade; the app records the level it was made at (per-KU plan D15).

### 4.3 Playlist builder [Q22; per-KU plan D13, D14]
- **Eligible:** KUs mapped to the upcoming lecture plus the previous two (from the lecture schedule, §5.2), minus hidden variants, minus videos skipped as known after a passed prove-it.
- **Tags:**
  - *gap:* the video's KU is at Level 1.
  - *new:* upcoming lecture, not yet watched (or started and left early, to pick up again).
  - *refresher:* watched, and (the KU is at Level 1, or the checkpoint or next-session item was missed, or it was watched `refresher_replay_count` times). Only added after every gap and new entry is watched or skipped.
  - *you_added:* via the Course map.
- **Order:** gaps → new → refreshers → you_added (appended). Inside a group a KU's **prerequisites come first** (the Knowledge Unit Graph), then the upcoming lecture's gaps, then earlier slides. A video stopped before `refresher_dropoff_fraction` of it goes to the very top, ahead of the cap, once 30 minutes have passed.
- **Cap:** 6 videos or 600 s total, whichever comes first. Overflow stays reachable in the Course map.
- **Rebuild:** at the baseline, at the end of each pre-lecture check, and at the start of each lecture week. A manual order persists until reset or the next rebuild. A level correction does not rebuild.
- **Why this order template:** "Lecture {n} is next{, and your levels show {gap_KUs} as gaps}. We put those first, then new videos from Lecture {n}{, then a short refresher}.{ You stopped “{video}” partway, so it is back at the top.}{ “{A}” comes first because “{B}” builds on it.}" Engagement (drop-off, replays) only changes what is delivered, never a level (D13).

### 4.4 Week 7 proposals: removed [Q34 superseded]
- There is no Week 7 in the app. Its job (re-measuring and updating levels) is done continuously: each check before a lecture adds review
  questions from earlier lectures, and quick-check, next-day and prove-it answers feed their lecture's ability. The pilot's midterm
  *measurement* (retention quiz, NASA-TLX, SUS, Likert, trust scale, focus groups) is a study-protocol item (roadmap: study instruments), not a level update.
- **Needs the advisor's sign-off** (OSF pre-registration not yet filed): H3 and the profile-shift heatmap change from "recalibration after the
  Week 7 reassessment vs a static profile" to "continuous per-lecture adaptation vs a static Week 0 profile".

### 4.5 Next-session scheduling [Q13]
- Covered in §3.3.3.

### 4.6 Ability and item parameters [Q36 superseded]
- θ is no longer log-only: it sets levels (§4.1). It is **never shown to students**.
- Item parameters before the pilot are priors: β from the LLM's KU rating plus the tier offset, α fixed at 1.0. Stated limitations: standard error
  stays about one logit at these test lengths, so sittings have a fixed length rather than a precision target; Dodd's heuristic is not a
  maximum-likelihood estimate and can place "all correct" below "all but one correct" on a narrow pool.
- After the pilot: calibrate β and α on real responses and report agreement with the priors.

---

## 5. Data and configuration

### 5.1 Models (`syllabyte_common/learner.py`, Pydantic; TS types mirror them)
| Model | Key fields |
|---|---|
| `Course` | id, name, display_eyebrow, semester_start, config (§5.2), lectures `[{n, date, deck, slide_range, ku_ids}]`, kus (each with `bloom_level` and `prerequisites`; the graph is validated as a DAG) |
| `Topic` | id (`lecture-<n>`), title, ku_ids, first_lecture (a topic is a lecture) |
| `Item` | id, ku_id, topic_id, context (`assessment`/`checkpoint`/`next_session`/`prove_it`/`retention`), tier (`basic`/`applied`/`advanced` on bank items), stem, options, correct_index, allows_not_sure, explanation, hint, difficulty_prior (β), discrimination (α, 1.0), source_refs |
| `Response` | id, student_id, item_id, choice (`int` \| `"not_sure"`), confidence (`guess`/`pretty`/`certain` \| null), hint_used, latency_ms, context, variant_id?, at |
| `KuLevel` | student_id, ku_id, level, source (`model`/`student`), suggested_level, reason, not_checked, provisional, history `[{level, source, at, cause}]` (cause: `baseline`/`lecture_check`/`student`/`use_suggested`/`pick_all`/`reset`) |
| `Sitting` | student_id, id (`week0` / `lecture-<n>`), answered_ids, started_at, finished_at, skipped, week |
| `LevelUpdate` | per lecture boundary: ku_id, from, to, direction, reason (the "What changed and why" rows), seen |
| `Progress` | student_id, video_id, max_t, duration_s, last_at (drives drop-off, D13) |
| `MadeLevel` | student_id, ku_id, level the KU's video was made at (a video is made once, D15) |
| `VideoVariant` | id, ku_id, level, version, video_url, vtt_url, poster_url, duration_s, lecture_n, checkpoint `{t, item_id}`, next_session_item_id, prove_it_item_id, sentence_frame `{template, blanks}`, segments `[{phase, start, end}]`, claims `[{idx, text, segment_idx, slide_refs, lecture_clip?}]`, tailoring `[{kind: left_out/added/set_to, what, dimension}]`, transcript `[{t, narration, visual}]`, review_status, expected_by? |
| `PlaylistEntry` | student_id, variant_id, position, tag (`gap`/`new`/`refresher`/`you_added`), state (`todo`/`watched`/`skipped`), skip_reason?, manual_order, week |
| `NextSessionTask` | student_id, variant_id, item_id, jol (`yes`/`maybe`/`no` \| null), due_after, expires_at, done |
| `ClaimVerdict` | student_id, variant_id, claim_idx, verdict (`matches`/`mismatch`), note |
| `Report` | student_id, variant_id, category, video_t, note, status (`open`/`resolved`), resolution |
| `Note` | student_id, variant_id, video_t, text, at |
| `SelfExplanation` | student_id, variant_id, mode (`frame`/`free`), blanks?, text |
| `StudyTask` / `StudyResponse` | retention quizzes and Qualtrics links; separate collection |
| `Participant` | student_id, pseudonym, condition (`A`/`B`), consent_research, withdrawn_at?, email_weekly |
| `Event` | `{actor: pid, verb, object: {type, id}, result?, context: {screen, device, orientation, condition, participant_code?}, timestamp}` |

### 5.2 Course config (`course.json`)
`semester_start`, `playlist_max_videos: 6`, `playlist_max_seconds: 600`, `next_session_min_hours: 12`, `next_session_max_per_visit: 2`,
`next_session_expiry_days: 7`, `retention_due_days: 3`, `retention_delay_days: 14`, `reveal_retention_scores_after_week_14: false`,
`lectures` (schedule, entered by hand today, from ingestion later), and the adaptive-assessment settings (design choices, to be tuned by
simulation before the pilot): `cat_start_theta: 0`, `cat_items_per_topic: 4`, `cat_week0_length: 16`, `cat_week0_lectures: 4`,
`cat_prelecture_new: 4`, `cat_prelecture_review: 2`, `irt_hint_beta_shift: 1.0`, `refresher_dropoff_fraction: 0.6`, `refresher_replay_count: 3`.
The Week 7 settings (`recheck_*`) are gone.

---

## 6. API and events

### 6.1 Endpoints (FastAPI, all under `/api`; the Phase 0 mock implements the same contract)
| Area | Endpoints |
|---|---|
| Auth | `POST /auth/request-link`, `GET /auth/callback`, `POST /auth/logout`, `GET /me` |
| First run | `POST /consent`, `POST /withdraw` |
| Sittings | `GET /sittings/{id}` (the question it is on), `POST /sittings/{id}/answer` (locks it), `POST /sittings/{id}/finish` (publishes levels), `POST /sittings/{id}/skip`, `GET /start-result`, `POST /levels/accept`, `POST /levels/pick-all` |
| Levels | `GET /levels` (by lecture), `POST /levels/{ku}/correct`, `POST /levels/{ku}/use-suggested`, `GET /calibration`, `GET /level-updates`, `POST /level-updates/{id}/dismiss`, `GET /history` |
| Playlist | `GET /playlist`, `POST /playlist/reorder`, `POST /playlist/reset-order`, `POST /playlist/{entry}/skip`, `POST /playlist/{entry}/undo`, `POST /playlist/{entry}/skip-reason`, `GET /next-session`, `POST /next-session/{task}/answer` |
| Course | `GET /course`, `GET /course/map`, `POST /course/videos/{variant}/add` |
| Player | `GET /variants/{id}`, `POST /responses` (checkpoint, prove-it), `POST /progress`, `POST /jol`, `POST /self-explanation`, `POST /notes`, `GET /notes` |
| Trust | `POST /claims/{variant}/{idx}/verdict`, `POST /reports` |
| Study | `GET /study/tasks`, `GET /study/retention/{task}`, `POST /study/retention/{task}` |
| Data | `GET /me/export` (ZIP), `POST /me/reset` |
| Events | `POST /events` (batch) |
| Instructor | `GET /instructor/variants`, `GET /instructor/variants/{id}`, `POST /instructor/variants/{id}/review`, `POST /instructor/reports/{id}/resolve` |
| Research | `GET /research/export/{collection}`, `GET /research/key` (second confirmation) |
| Admin | `POST /admin/variants` (pipeline registers an uploaded variant), `POST /admin/allowlist` (CSV) |

### 6.2 Event vocabulary [Q20]
`consent_given, cat_answered, cat_finished, level_suggested, levels_updated, level_kept, level_corrected, playlist_viewed,
reordered, skipped, skip_reason, undo, prove_it_result, video_play, video_pause, video_seek,
video_ended, speed_changed, captions_toggled, transcript_opened, note_saved, checkpoint_shown,
checkpoint_answered, checkpoint_skipped, hint_used, rewatch_part, receipt_opened,
full_version_requested, about_opened, claim_slide_viewed, claim_verdict, error_reported,
difficulty_rated, jol_answered, self_explanation_saved, next_session_answered, course_video_added,
data_downloaded, model_reset`

### 6.3 Logging rules
- Every event carries device type, orientation, screen and condition.
- If `consent_research = false` or the student has withdrawn, events are used only for app function and **not stored** in the research event log.
- Phase 0: events go to localStorage, stamped with the participant code.

---

## 7. Pipeline additions

### 7.1 UI manifest per video (do first)
`<ku>/ui_manifest.json` (shape = `VideoVariant`), built without an LLM:
- duration, a poster frame (ffmpeg at 25%), and `captions.vtt` converted from the SRT;
- segment times from `SegmentAudio`; `checkpoint.t` = `srt_end` of the main *deliver* segment;
- claims (one per *deliver*/*end* segment: narration + `source_refs`);
- a transcript from beats (`narration` + `visual`).

### 7.2 Generated items per KU
One LLM call per KU, grounded in the cited slides and checked by the existing critic, produces:
- the checkpoint item (3 options, no "Not sure", explanation, hint);
- the next-session item;
- the prove-it item ("Not sure" allowed);
- the sentence frame;
- `difficulty_prior` for each item (the LLM's estimate; for the adaptive bank see §7.3).

### 7.3 Item bank (per KU, for the adaptive tests)
Three items per KU, one per Bloom tier (basic, applied, advanced), written from the KU's own slides by one LLM call and checked by the existing critic
(`scripts/build_item_bank.py`, rules in `assessment_agent/bank.py`). The LLM rates the KU once; the item difficulty is derived (§4.1). Every stem must end
in a question, answers are rotated over A/B/C by course position, and the bank is validated (three tiers per KU, tier-ordered difficulties). A sample is
validated by hand for the pilot course (at least 2 items per lecture), reading `_bank-review.md`. Retention items are written or approved by the
instructor, separately. The old per-topic onboarding and re-check items are retired.

### 7.4 Per-level variants [Q29]
Add `level: 1|2|3` to `build_script_prompt`. Three versions per KU, not one per student.

| Dimension | Level 1 · Foundations | Level 2 · Core | Level 3 · Advanced |
|---|---|---|---|
| Prerequisite recap | 1 recap segment | 1 sentence in *prepare* | none |
| Worked example | full, step by step | one, key steps | none; one "why/what if" contrast |
| On-screen supports | labels on all elements, step callouts, end recap card | labels on key elements, short recap line | minimal labels, no recap |
| Bloom target | remember / understand | apply / analyze | analyze / evaluate |
| Narration pace | ~140 wpm | ~155 wpm | ~165 wpm |
| Checkpoint hint | shown inline | "Show a hint" button | none |
| Length | ≤ 90 s | ~75 s | ~60 s |

**All versions share the same claims, facts and slide refs.** Levels change support and depth only. Pace and length are tunable starting values.

### 7.5 Tailoring decisions
The script writer emits `TailoringDecision[]` by comparing each version with Level 1 along the §7.4 dimensions, so the receipt can only list real differences. The *why* text is filled in per student by the API (§2 rule 4).

### 7.6 Upload and registration
Generation stays off-server (laptop or lab DGX). The pipeline uploads assets + manifest to S3 and calls `POST /admin/variants`. A new version for the same KU + level replaces the old one and resets its status to `unreviewed`.

Burned-in captions stay out (Week-1 scope change). The UI renders the sidecar VTT.

---

## 8. Design system [Q19]

- **Fonts:** Manrope (700 titles, 600 buttons, 400/500 body) + JetBrains Mono (eyebrows, metadata), loaded via `next/font/google`.
- **Mobile type scale:** title 32/38 · card title 20/26 · body 17/24 · eyebrow 13 mono uppercase +0.08em · meta 14 mono.
- **Colors (estimated from the PDF):** `--ink #151B33`, `--bg #F2F3F7`, `--surface #FFFFFF`, `--border #DADCE5`, `--primary #5B3FD6`, `--primary-tint #ECE8FC`. Tags: gap `#FBE7CC/#8A4B0F`, refresher `#E9E5FB/#4B32B8`, new `#D8F1EE/#0F6B5F`. Any pair below 4.5:1 in axe is darkened. If the exact wireframe values arrive, replace these.
- **Shape:** cards radius 20, 1 px `--border`, no shadow · buttons 56 px tall, radius 16 · selected = 2 px primary border + primary-tint fill · "Not sure" = 1.5 px dashed border.
- **Light mode only** through Phase 2. Dark mode is optional in Phase 3.
- **Breakpoints:** < 768 px is the wireframe layout. ≥ 1024 px: left sidebar nav, content max-width 720 px, two-column player, sheets become right-side panels.
- **Components:** `ChoiceCard`, `SegmentedRow`, `Tag`, `StatusBadge`, `InfoCard`, `BottomSheet` (Radix Dialog; drag handle + close button), `LevelBar`, `ProposalCard`, `VideoCard`, `VideoPlayer` (with `CaptionBand`, `PlayerControls`, `CheckpointPanel`), `TranscriptSheet`, `NotesSheet`, `ChangeLevelSheet`, `ReportSheet`, `PrimaryBar`, `UndoToast`, `StudyTaskCard`, `NextSessionCard`.
- **Copy rules:** plain language, the "not graded" framing, every model claim paired with a reason and a way to correct it.

---

## 9. Architecture and infrastructure

### 9.1 Layout
```
apps/web/                         Next.js App Router, TypeScript strict, Tailwind, Radix (student + instructor UI)
  content/consent.md              placeholder consent text
  fixtures/                       generated + hand-written fixture JSON (Phase 0)
  public/fixtures/                media copied from runs/dev (gitignored)
packages/api/syllabyte_api/       FastAPI (added to root pyproject hatch packages)
packages/assessment_agent/        levels, playlist, proposals, Rasch, item bank loader
packages/common/syllabyte_common/ learner.py models, db.py, storage.py
scripts/build_ui_fixtures.py      fixture generator (Phase 0; seed of §7.1–7.2)
```

### 9.2 Stack conventions
- `apps/web` is a standalone npm project. Phase 0 uses `output: "export"`; Phase 2+ runs as a Node server.
- The typed API client (`apps/web/lib/api/`) is the only way components talk to data [Q6].
  - Phase 0: an in-browser mock backed by fixtures + localStorage.
  - Phase 1+: real fetch calls.
  - Phase 0 types are hand-written. From Phase 1, TS types are generated from FastAPI's OpenAPI schema (`openapi-typescript`) and must match.
- Video: native `<video>` + custom controls. No player library.
- Python deps added: `fastapi`, `uvicorn`, `resend`, `girth`.

### 9.3 Auth (Phase 1+) [Q23]
- Magic link via **Resend**. Single-use links, 15 min expiry.
- A **per-course allowlist** (CSV of email + role `student`/`instructor`/`researcher`). Non-allowlisted emails see "This email isn't enrolled in a SyllaByte course".
- Session: a 30-day rolling httpOnly SameSite=Lax cookie.
- `DEV_LOGIN=1` lets you pick a seeded user.
- Users are keyed by email (NYU SSO can be added later).

### 9.4 Email [Q32]
Plain text + one link. No images, tracking pixels or open tracking. One-tap unsubscribe in every email.
- Sign-in links.
- Study task due dates.
- **Weekly "Your playlist is ready"** at the start of each lecture week ("{n} videos, about {m} minutes, for Lecture {k}"). Condition B: "This week's lecture materials are up." Same timing in both conditions. On by default, with a toggle in settings.
- Instructor: a daily digest of new reports.
- **No nudges.**

### 9.5 Deployment (Phase 2+) [Q24]
- One ~$12–15/month VM running Docker Compose: Next.js, FastAPI, Mongo and **Caddy** (auto-HTTPS; same domain, `/api/*` → FastAPI).
- Media in **S3** via presigned URLs.
- A nightly `mongodump` to S3.

---

## 10. Phase 0 prototype details [Q2, Q6, Q7, Q9, Q37]

- **Content:** the computational-ss course. The 20 KUs are grouped into ~4 topics by the generator. There are 4 real videos (`runs/dev`: potential outcomes, selection-bias formula, coin-toss worked example, reading a difference table), one version each, labelled Level 2.
- **Lecture schedule fixture:** 4 invented lectures, from slide ranges of the single deck. The 4 videos are spread across them.
- **`scripts/build_ui_fixtures.py`:**
  - From `runs/dev`: the lecture topics, per-video checkpoint/next-session/prove-it items, sentence frames and tailoring decisions (§7.2, via `llm.py` + critic); the per-KU adaptive bank is built separately (§7.3).
  - Without an LLM: the manifests of §7.1.
  - Writes `apps/web/fixtures/*.json`. **The author reviews every item before a session.**
- **Persona fixture (hand-written):** levels, calibration history and a lecture boundary that tell one coherent story, built by running the real API with a backdated clock. It must include ≥ 1 gap KU, ≥ 1 skippable video, ≥ 1 level up and ≥ 1 level down on the "What changed and why" card, ≥ 5 rated checkpoint answers and ≥ 3 JOL/next-day pairs.
- **Commands:**
  - `npm run fixtures` copies media from `runs/dev/` into `apps/web/public/fixtures/` (gitignored).
  - `npm run dev -- --hostname 0.0.0.0` serves phones on the same Wi-Fi.
  - `npm run build` produces a static `out/`.
  - Local by default; hosting waits for the professor's OK.
- **Usability round 1 tasks** (think-aloud, 5 students):
  1. Complete onboarding; say what level you got and why.
  2. Which video should you watch first, and why is it first?
  3. Play video 1 and answer the quick check.
  4. What's different about this video for you?
  5. Is this claim correct? How would you check?
  6. Skip a video you think you know.
  7. Correct a level you disagree with.
  8. (via Jump "Levels changed") Read the "What changed and why" card and correct one level.
- **Per session, record:** task success (yes / with help / no), time on task, the event log, SUS, and 3 debrief questions (most confusing moment; what felt trustworthy; what you'd change).

---

## 11. Accessibility checklist
- WCAG 2.2 AA; axe on every route in CI.
- Keyboard-only path through every flow. Focus is trapped in sheets and returned on close. Focused items are never hidden behind the bottom nav or sheets.
- Captions are on by default; a described transcript; every slide image has its extracted text.
- Reduced motion respected; no information conveyed by color alone (tags and badges have text).

## 12. Verification
- **Unit (pytest + Vitest):**
  - §4.1 rules, overall median, §4.3 tags, order, cap and first-pass refresher rule, §4.4 thresholds and clamp, §3.3.3 timing (12 h / 2 per visit / 7-day expiry), §3.16 fallback.
  - **Every reason template renders numbers equal to the stored evidence.**
  - `srt → vtt` conversion.
- **Component:** every component state (selected, not-sure, disabled, fallback, flagged).
- **E2E (Playwright; 390×844 and 1280×800):**
  - Welcome → consent → onboarding → result → playlist → play to checkpoint → answer → confidence → auto-reveal → wrong → rewatch → continue → screen 7 → Simulate next day → next-session card.
  - Skip → reason → prove-it pass/fail → undo.
  - Change order + reset.
  - Change level from all 3 entry points.
  - Claim check → view slide → mismatch → badge turns flagged.
  - The check before a lecture: due → adaptive questions → levels published → "What changed and why" → dismissed.
  - Each flow asserts the expected events (§6.2).
- **Accessibility:** `@axe-core/playwright` on every route. A manual VoiceOver pass on the sheets and player.
- **Research data:** after an E2E run, the export has one row per response with confidence, context and timestamps (enough for RQ2 and RQ3).

---

## 13. Schedule

| Phase | Dates | Scope |
|---|---|---|
| **0 Prototype** | Oct 5–18 | `apps/web` scaffold, design system, all screens §3.0–3.12 + §3.15–3.17 on the mock, fixture generator §10, manifests §7.1, event log + demo menu, usability round 1 |
| **1 Backend + onboarding** | Oct 19 – Nov 8 | FastAPI, `learner.py`, Mongo, auth (§9.3), event ingest + offline queue, `assessment_agent` §4.1–4.3 + Rasch §4.6, item bank §7.3; wire §3.0–3.3, §3.8, §3.11, §3.12 to the API; OpenAPI type generation |
| **2 Player loop + trust** | Nov 9 – Nov 29 | Wire §3.4–3.7, §3.15; per-level variants §7.4–7.5, items §7.2, upload §7.6; instructor queue §3.13; deploy §9.5; usability round 2 (SUS + UEQ-S + NASA-TLX dry run) |
| **3 Pilot hardening** | Dec 1 – Dec 20 | email §9.4; condition B §3.14; study tasks + retention §3.18; data §3.19; accessibility audit; error/offline tests; freeze for January |

## 14. Build order inside Phase 0
1. Scaffold `apps/web`, tokens and fonts, base components (§8).
2. Typed API client + mock, event logger, demo menu.
3. `scripts/build_ui_fixtures.py`, `npm run fixtures`, author review of the items.
4. Screens in flow order: 0a/0b → 1 → 1b → 2 → 4 (+ CC/transcript/notes/ⓘ) → 5 → 6 → 7 → 3/3b → 3.3.3 → 8 → 3.12 → 11 → 9/9b → 10/10b → 3.15/3.16.
5. Playwright E2E + axe for the Phase 0 flows; a desktop layout pass.

## 15. Open items outside the code
1. **Professor:** may course slides and videos be hosted on a server? (needed before Phase 2)
2. **IRB:** do research decliners get condition A (assumed)? Final consent text.
3. **Proposal wording:** §4.1, the control group uses a minimal SyllaByte shell (not the LMS) [Q26]. The CAT/IRT section: levels come from transparent rules; IRT fitted on pilot data evaluates them [Q36].
4. **NYU IT:** SSO and a possible university VM (both optional).
5. **Exact fonts and hex values** from the wireframe tool, if available (§8 uses estimates).
6. **Traceability table:** add the new design choices (12 h / 2 per visit / 7-day next-session rules, playlist cap, the adaptive-assessment settings, speed cap, sentence frame, the calibration blocks).

## 16. Decision index
Q1 phasing (§13–14) · Q2 course content (§0, §10) · Q3 9:16 layout (§3.4) · Q4 confidence order (§3.4) ·
Q5 "Not sure" (§2) · Q6 mock data layer (§9.2) · Q7 fixture generator (§10) · Q8 Course tab (§3.11) ·
Q9 local prototype (§10) · Q10 check result (§3.4) · Q11 slide evidence (§3.6) · Q12 skip/reorder
(§3.2–3.3) · Q13 end of video + next-session (§3.7, §3.3.3) · Q14 change level (§3.12) · Q15 levels +
result (§3.1b, §4.1) · Q16 Week 7 (§3.9–3.10) · Q17 captions/transcript/notes (§3.4) · Q18 first run
(§3.0) · Q19 design system (§8) · Q20 event log (§6.2, §3.17) · Q21 reports + badges (§3.15) · Q22
playlist (§4.3) · Q23 auth (§9.3) · Q24 deployment (§9.5) · Q25 instructor queue (§3.13) · Q26
condition B (§3.14) · Q27 study instruments (§3.18) · Q28 retention quizzes (§3.18) · Q29 level
versions (§7.4) · Q30 data rights (§3.19) · Q31 missing/error states (§3.16) · Q32 email (§9.4) · Q33
level stability (§2) · Q34 Week 7 rule (§4.4) · Q35 calibration (§3.8) · Q36 Rasch (§4.6) · Q37
usability tasks (§10)

**Superseded 2026-10-13** (see `plan/per-ku-profiling-plan.md`): Q15 (levels are per KU, §3.1b, §4.1), Q16 (no Week 7; §3.9–3.10 are now the
check before a lecture and "What changed and why"), Q33 (levels change at lecture boundaries, §2 rule 2), Q34 (§4.4 removed), Q36 (§4.6).

## 17. Implementation status (2026-10-13)

**Phase 0 is built** in `apps/web` (see its README for commands). It covers §3.0–3.12, §3.15, §3.16 (except the
IndexedDB offline queue, which only matters once there is a network), and §3.17, plus the fixture generator
(`scripts/build_ui_fixtures.py`), the UI manifest builder (`animation_agent/ui_manifest.py`) and the learner models
(`syllabyte_common/learner.py`). Checks: 69 unit tests, 106 Playwright tests at 390×844 and 1280×800, axe (WCAG 2.2 AA)
clean on every route and sheet, TypeScript and ESLint clean.

**Revised 2026-10-13 on branch `per-ku-profiling`:** the assessment moved to per-KU levels from adaptive tests (§4.1), Week 7 was removed (§3.9–3.10, §4.4),
and the app was rewired: 186 unit tests, 75 Python tests, 98 Playwright tests and axe clean. The Python CAT engine and its TypeScript port agree to 1e-11 on
140 recorded steps; the 60-item bank for the dev course is generated locally (gitignored). The statements below about Week 7 describe the earlier build.

**Not built yet:** Phase 1 (FastAPI, Mongo, magic-link auth, event ingest, offline queue), Phase 2 (per-level video
variants, instructor queue, deployment), Phase 3 (§3.14 control shell, §3.18 study tasks, ZIP export, weekly email,
researcher export). The Phase 0 "Study tasks" card and "Withdraw / Reset" flows are minimal versions.

**Where the build departs from, or interprets, this spec**
- *Week 7 minimum answers (§4.4).* "Needs ≥3 answered" is applied to the score rules; the "more than half Not sure" rule
  needs ≥3 *presented* (answered + Not sure). Read literally, that rule could never fire.
- *Hints and half credit (§4.4, §3.4).* A hint that was visible when the student answered counts as used, so a Level 1
  student, who sees the hint inline, earns half credit on checkpoint answers.
- *Short titles.* Cards, headers and receipts use a hand-written `short_title` per KU (in `build_ui_fixtures.py`); the
  full KU title appears in "About this video" and the transcript.
- *Reason text quotes topic titles* (`questions on “Causal questions”`) instead of appending a noun, which broke on titles
  that already end in "questions".
- *Answer positions* in generated items are rotated A/B/C deterministically after generation, because the model favoured
  some slots (all four prove-it keys were option C).
- *Nothing is drawn over the video, including the start button:* the large play control sits under the video.
- *The player's own seeks are not logged.* Landing on the checkpoint after an overshoot would otherwise add a `video_seek`
  the student never made.
- *Persistence flushes on page hide,* so a tap followed by a quick navigation can't lose the last change.
- *Test builds* (`NEXT_PUBLIC_TEST_WEBM=1`) list a small WebM before the MP4 and preload it whole, because Playwright's
  Chromium has no H.264 decoder and seeks poorly in progressively loaded files. Production is unaffected.

**Before the first usability session**
1. Re-render the fixture videos with the current pipeline: two of the four show an unrelated plot and clipped titles
   (older pipeline output), which would contaminate the claim-check and trust tasks.
2. Read `apps/web/fixtures/_review.md` end to end (26 items, 12 claims, 4 sentence frames). The critic passed everything,
   but a quiz error in a think-aloud session derails it.
3. Replace `content/consent.md` with the IRB-approved text.
4. Add the new design choices to the traceability table (the 12 h / 2-per-visit / 7-day rules, playlist cap, speed cap,
   sentence frame, calibration blocks, and the adaptive-assessment settings of §5.2 with the tier offsets and fixed α; see
   `plan/per-ku-profiling-plan.md`).
