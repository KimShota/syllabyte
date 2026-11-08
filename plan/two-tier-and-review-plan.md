# Two-tier checks, misconception videos and spaced review: design plan

Status: proposal, 2026-11-08. Nothing built. Several items change the research design and need advisor sign-off
(marked **[sign-off]**).

## 0. Decisions already made (user, 2026-11-08)

- D1. The in-video check is **two-tier**: a multiple-choice answer, then a written reason.
- D2. The **multiple-choice answer adjusts the KU level**. The **written reason is used only to find misconceptions**.
- D3. A misconception found in the reason triggers a **refutation video** for that misconception. It is made in the
  background while the student watches the next topic's video.
- D4. Videos are cached **per (KU, misconception)**, not per student.
- D5. If the misconception survives the video, **keep generating** until the student gets it (see §4.4 for a cap).
- D6. Remove the "prove it" question and the "I already know this" skip. The mobile app has neither already; the
  leftovers are in core, server, web and `assessment_agent/video_app_data.py`.
- Refutation script template: prediction prompt, name the wrong idea once, contradiction (shown), causal explanation
  (most of the time), contrasting case, follow-up check with confidence.

## 1. What the literature says, and what it means for SyllaByte

| Finding | Source | Design consequence |
|---|---|---|
| Practice testing beats restudy (g ≈ 0.50–0.70). Mixed-format practice tests worked best; whether MCQ or short answer is better is contested. | Rowland 2014; Adesope et al. 2017 | Mix formats in review; don't rely on one. |
| Effortful retrieval (recall) gives larger testing benefits than recognition (MCQ). | Rowland 2014 | Move from MCQ toward short constructed answers as the KU matures. |
| Testing effects transfer (d ≈ 0.40), more so with application-style practice and elaborated feedback. | Pan & Rickard 2018 | Later reviews should ask application/transfer questions, not repeat the original question. |
| Application quizzes helped both definition and application exam items; definition quizzes did not help application. | McDaniel et al. 2013 | Don't stay at recall tier. Once the level allows, review with application items. |
| Fact quizzes didn't build higher-order performance; higher-order and **mixed** quizzes did, mixed best. | Agarwal 2019 | Mix recall and higher-order items within a review session. |
| MCQ lures can be learned as facts. Feedback removes this negative effect. | Butler & Roediger 2008 | Every review answer gets feedback: correct answer + explanation. Never withhold it. |
| High-confidence errors are corrected **more** readily after feedback (hypercorrection). | Butterfield & Metcalfe 2001; replications | Ask confidence. A confident wrong answer is the moment to show the refutation, and it is a strong misconception flag. |
| Two-tier tests (answer + reason) diagnose misconceptions; they can't separate a misconception from not knowing, so three/four-tier versions add confidence. | Treagust 1988; Tsui & Treagust 2009; Caleon & Subramaniam 2010 | Two-tier + one confidence rating (three-tier). "Wrong + guessing" = gap; "wrong + sure" = misconception. |
| Videos that state and refute misconceptions (refutation or student–tutor dialogue) roughly doubled learning gains over plain exposition (d ≈ 0.8, n = 364). | Muller et al. 2008 | Supports the refutation template, and fits the existing dialogue video format. |
| Learned science **suppresses** intuitive misconceptions but doesn't erase them; they persist in adults. | Shtulman & Valcarcel 2012 | A fixed misconception must be **re-probed at later reviews**, not marked resolved after one right answer. |
| Spaced retrieval beats massed (g = 0.74); **expanding vs uniform gaps: no reliable difference** (g = 0.03). | Latimier et al. 2021 | Spacing matters; the exact expanding pattern doesn't. Use simple expanding gaps, don't over-engineer. |
| The best review gap depends on how long you need to remember: roughly 10–20% of the time until the test. | Cepeda et al. 2008 | Fit gaps to the exam dates in the syllabus. |
| Practising to a criterion, then relearning across spaced sessions (successive relearning), boosted course exam scores (d ≈ 0.5–1.1). | Rawson & Dunlosky 2011, 2013; Janes et al. 2020 | A KU stays in review until it is answered correctly in several spaced sessions. |
| Personalized review scheduling beat a one-size-fits-all spaced schedule by 10% at semester end. | Lindsey et al. 2014 | Per-student, per-KU scheduling is worth it, and fits the per-KU level we already have. |
| Interleaving helps most when categories look similar but must be told apart. | Brunmair & Richter 2019 | Mix KUs in a review session, and add "which method applies?" questions for look-alike KUs (e.g. Dijkstra vs Bellman-Ford). |
| Students who don't master a skill quickly are unlikely to master it with more of the same practice ("wheel-spinning"). | Beck & Gong 2013 | Cap the misconception-video loop; switch to a different kind of help after the cap. |
| Algorithms and data structures have documented, recurring misconceptions; some were found only by asking students to explain. | Danielsiek et al. 2012; Paul & Vahrenhold 2013 | Seed the misconception catalog from the literature and from MCQ wrong options, and grow it from written reasons. |
| LLMs can detect gaps/misconceptions in student explanations (GPT-4 best of those tested). They are weaker on short answers and on right-answer-wrong-reason cases. | arXiv 2501.10365; arXiv 2605.23925; Eedi arXiv 2602.02414 | Classify against a known list, quote evidence, allow "can't tell", and audit by hand. |

Note: some numbers above come from abstracts or secondary summaries. Check them against the papers before they go in the
thesis.

## 2. The two-tier check (immediately after the video)

Screen order: question → choose answer → "Why?" (one or two sentences) → confidence (Sure / Guessing) → feedback.

The reason is asked **after** the answer and **before** feedback. That way the student explains their own choice, not
the feedback.

| Answer | Reason | What it means | What happens |
|---|---|---|---|
| right | right | knows it | nothing extra |
| right | misconception | right for the wrong reason | refutation video (the MCQ alone would have missed this) |
| wrong | right | slip | feedback only |
| wrong | misconception | misconception | refutation video |
| wrong | unclear / blank | gap, not diagnosable | feedback + the KU's next review comes sooner |

Level (D2): only the MCQ answer goes into the IRT estimate. Confidence goes to calibration as today.

Mobile cost: typing on a phone is the biggest risk to completion (H2). Keep the reason box short, give a sentence
starter ("Because…"), and allow skipping the reason (logged as skipped, treated as "unclear").

## 3. Misconception catalog and diagnosis

- **Catalog per KU:** a list of misconceptions, each with an id, one-sentence statement (the exact wording used in the
  video's step 2), and source: `distractor`, `literature` or `student`. Seeded at bank time from the MCQ wrong options
  (the bank prompt already writes them as misconceptions) and from the literature for known DSA topics.
- **Classifier:** an LLM gets the KU, the item, the chosen option and the reason. It returns one of:
  - `correct`
  - `known:<id>` plus a verbatim quote from the reason as evidence
  - `new` plus a proposed one-sentence statement
  - `unclear`
- **New misconceptions** go into the catalog as `student`, pending. A pending entry needs either 2 students or a
  researcher's approval before a video is made for it. This stops one odd answer from triggering a video.
- **Audit:** a researcher labels a random sample of about 10–20% of reasons. Report agreement (Cohen's κ) with the
  classifier. This is a study result in its own right.

## 4. Misconception videos

### 4.1 Script

Use the refutation template from §0, about 60–90 s. Step 2 uses the catalog's exact wording. Steps 3–4 use the
existing trace templates, so the moment the wrong idea breaks is shown, not told. The dialogue format (one character
holds the misconception, the other resolves it) matches the "dialogue" condition in Muller et al. 2008.

### 4.2 When it plays

- The video is generated in the background after the check. The feed shows the next topic's video meanwhile.
- **Exception:** if the next topic depends on the misunderstood one (the KU graph has the edge), the misconception
  video goes **before** it once ready. The feed shows a short "making a video about this" card if it isn't ready.

### 4.3 After the video

The student answers a **new** two-tier item aimed at the same misconception, with confidence. This is the
follow-up check in the template's step 6. It is graded by the same rules as §2.

### 4.4 If it survives (D5)

The video doesn't re-play. The next attempt is a different explanation, generated with a different angle:
1. Attempt 1: the refutation template, the catalog's main example.
2. Attempt 2: a different example and representation, e.g. a worked trace step by step, or a concrete
   counter-example the student predicts.
3. Attempt 3: the contrasting-case structure. Side by side, one case where the wrong idea happens to work and one
   where it fails.

Each attempt is cached as (KU, misconception, attempt n) and shared across students. The second student with the
same surviving misconception gets attempt 2 instantly.

**Cap at 3 attempts (recommended; departs from "until they get it").** Wheel-spinning research says more of the same
kind of help rarely works once early attempts fail. After 3 attempts:
- stop generating,
- show the KU's slides and the item explanation,
- suggest office hours,
- mark the misconception `unresolved` for the student and flag it for the researcher,
- put the KU into review at the shortest gap.

The unresolved rate is a useful study outcome.

### 4.5 Resolved

A misconception is **resolved** when a follow-up check (§4.3) is right with a correct reason **and** a later delayed
review (§5) is also right. Until then it stays "fixing". Because misconceptions persist under the surface (Shtulman &
Valcarcel 2012), resolved misconceptions are still probed in later reviews (§5.3).

## 5. Spaced review: what questions to ask

### 5.1 Schedule (per student, per KU)

- **Steps:** about 1 day, 3 days, 7 days, 21 days, then every ~5 weeks.
- **Right answer:** advance one step.
- **Wrong answer:** go back one step.
- **Confident wrong answer, or a misconception in the reason:** back to step 1 (and §4 runs).
- **Exam compression:** when an exam is coming, cap the gap at about 20% of the days left until it (Cepeda et al.
  2008). Every KU on the exam gets at least one review in the final week. This needs exam dates from the syllabus, and
  the syllabus extraction doesn't capture them yet.
- **Load:** at most about 5 review questions a day, about 3 minutes, shown as one review card on the home screen.
  Order: overdue first, then "fixing" misconceptions, then the rest. Spread over visits like today's next-session cap
  of 2 per visit.

The exact expanding pattern doesn't matter much (Latimier et al. 2021). Keep the rule simple and spend effort on the
questions.

### 5.2 Question format by KU kind

Each KU gets a `kind` at extraction:

| KU kind | Example | Format | Grading |
|---|---|---|---|
| procedural | trace Dijkstra; compute a hash slot; heap after 3 inserts | **short answer**: a number, an expression, or a sequence (tap-to-order) | exact match, no LLM |
| conceptual | why Dijkstra fails on negative edges; what a hash function guarantees | MCQ with misconception distractors | answer key |
| reasoning | which data structure suits this case and why | **two-tier**: MCQ + written reason | MCQ scores; reason → diagnosis |

### 5.3 Question type by review step

| Step | Purpose | Question |
|---|---|---|
| Check (in video) | diagnose | two-tier MCQ + reason + confidence (§2) |
| Review 1 (~1 day) | quick diagnosis, retrieval | two-tier MCQ, **new item**, at the KU's level tier |
| Review 2 (~3 days) | effortful retrieval | short answer for procedural KUs; MCQ + reason for the others |
| Review 3 (~7 days) | application / transfer | a new scenario: same idea, different data or context |
| Review 4+ (21 days on) | durable knowledge, discrimination | mixed and interleaved across KUs; "which method applies?" items for look-alike KUs |
| Any step, if the KU ever had a misconception | relapse check | a probe aimed at that misconception (its distractor present, reason asked) |

**Rules for every review question:**
- **A new item each time.** Never the same question twice. This avoids memorizing the answer and keeps the
  level estimate clean.
- **Tier follows the current level:** Level 1 basic (recall/understand), Level 2 applied, Level 3 advanced
  (analyze/evaluate).
- **Feedback always:** the correct answer plus an explanation. For a confident wrong answer, show the misconception's
  statement and why it fails (hypercorrection).
- **Confidence on every item.**
- **What counts for the level:** MCQ answers and exactly graded short answers. **Never** LLM-graded text (D2,
  extended to short answers that have an exact key).

## 6. Data model sketch

- **`KuEntry`:** add `kind: "procedural" | "conceptual" | "reasoning"` and `misconceptions: MisconceptionRef[]`.
- **`Item`:**
  - add `format: "mcq" | "two_tier" | "short_answer"` and `targets_misconception: string | null`
  - short answers carry `answer_key` (normalized string or ordered list)
  - context `"review"` and `"misconception_check"` are added; `"prove_it"` is removed (D6)
- **`ResponseRecord`:** add `reason_text`, `reason_skipped`, `diagnosis` (`correct | known:<id> | new | unclear`),
  `diagnosis_evidence`.
- **`ReviewTask`:** generalizes `NextSessionTask` (per KU, not per video): `ku_id`, `step`, `due_at`, `item_id`,
  `result`.
- **`StudentMisconception`:** `ku_id`, `misconception_id`, `state: fixing | resolved | unresolved`, `attempts`,
  `video_ids`.
- **Server video job kind:** `misconception`, keyed (ku_id, misconception_id, attempt). The cache is shared across
  students.
- **`EVIDENCE_CONTEXTS`:** becomes `assessment`, `checkpoint`, `review`, `misconception_check` (MCQ / exact answers only).

## 7. Study design implications **[sign-off]**

1. **Condition A changes.** It is now videos **plus** two-tier diagnosis, refutation videos and spaced retrieval.
   Condition B (business as usual) gets none of that. H1 then tests the whole SyllaByte system, not the videos alone.
   That is a defensible framing, but it must be said that way.
2. **Retention test contamination.** The proposal's retention quiz (after each module and again two weeks later;
   `retention_delay_days: 14`) must use items **never** shown in checks or reviews. Otherwise it measures review
   practice on the same questions.
3. **Personalization unit.** The proposal personalizes by KU level. Misconception-targeted videos are a new kind of
   personalization: add it to the methods and give the diagnosis audit (§3) as its validation.
4. **H2 engagement.** Written reasons and review cards add work. Log reason-skip rate and review completion
   separately from video completion.
5. **New measures this enables:** misconception incidence per KU, resolution rate per attempt, relapse rate at later
   reviews, and classifier agreement with human labels.

## 8. Cost

- **Misconception video:** about $0.27 each, from the 17-video S1–S5 run. One per (KU, misconception, attempt), shared
  by everyone. Suppose 5 misconceptions per KU are seen and the mean is 1.5 attempts: about $2 per KU across the whole
  cohort.
- **Review items:** generated ahead of time per KU × tier × format, like the item bank. Small text calls.
- **Diagnosis:** one short LLM call per written reason.

## 9. Build order (proposal)

1. **R0.** Remove "prove it" and the skip (D6).
2. **R1.** KU `kind` at extraction; misconception catalog seeded from wrong options and literature.
3. **R2.** Two-tier check on mobile: reason box + confidence. Reasons logged, no diagnosis yet. This alone already
   gives research data.
4. **R3.** Diagnosis classifier + researcher audit view (label a sample, compute κ).
5. **R4.** Misconception video generation (refutation template, dialogue style), cache, feed placement, follow-up
   check, attempt loop with cap.
6. **R5.** Review scheduler + review card on mobile. It replaces the next-day question, which mobile never showed.
7. **R6.** Review item generation by format and step: short-answer exact grading, application items, interleaved
   discrimination items, misconception probes.
8. **R7.** Exam dates from the syllabus; exam compression.

## 10. Open questions

- Q1. Cap the misconception loop at 3 attempts, or truly unlimited (D5)?
- Q2. Does a right MCQ answer with a misconception in the reason still count as **right** for the level? D2 says yes
  (MCQ only). It's worth confirming.
- Q3. Do exactly graded short answers count toward the level?
- Q4. Which course(s) does the pilot use? The misconception catalog needs literature seeds per course.

## References

- Adesope, O. O., Trevisan, D. A., & Sundararajan, N. (2017). Rethinking the use of tests: A meta-analysis of
  practice testing. *Review of Educational Research, 87*(3), 659–701.
- Agarwal, P. K. (2019). Retrieval practice & Bloom's taxonomy: Do students need fact knowledge before higher order
  learning? *Journal of Educational Psychology, 111*(2), 189–209.
- Beck, J. E., & Gong, Y. (2013). Wheel-spinning: Students who fail to master a skill. *AIED 2013*, LNCS 7926,
  431–440.
- Brunmair, M., & Richter, T. (2019). Similarity matters: A meta-analysis of interleaved learning and its moderators.
  *Psychological Bulletin, 145*(11), 1029–1052.
- Butler, A. C., & Roediger, H. L. (2008). Feedback enhances the positive effects and reduces the negative effects of
  multiple-choice testing. *Memory & Cognition, 36*(3), 604–616.
- Butterfield, B., & Metcalfe, J. (2001). Errors committed with high confidence are hypercorrected. *JEP: LMC,
  27*(6), 1491–1494.
- Caleon, I. S., & Subramaniam, R. (2010). Do students know what they know and what they don't know? Using a
  four-tier diagnostic test to assess the nature of students' alternative conceptions. *Research in Science Education,
  40*(3), 313–337.
- Cepeda, N. J., Vul, E., Rohrer, D., Wixted, J. T., & Pashler, H. (2008). Spacing effects in learning: A temporal
  ridgeline of optimal retention. *Psychological Science, 19*(11), 1095–1102.
- Danielsiek, H., Paul, W., & Vahrenhold, J. (2012). Detecting and understanding students' misconceptions related to
  algorithms and data structures. *SIGCSE '12*, 21–26.
- Janes, J. L., Dunlosky, J., Rawson, K. A., & Jasnow, A. (2020). Successive relearning improves performance on a
  high-stakes exam in a difficult biopsychology course. *Applied Cognitive Psychology, 34*(5), 1118–1132.
- Latimier, A., Peyre, H., & Ramus, F. (2021). A meta-analytic review of the benefit of spacing out retrieval
  practice episodes on retention. *Educational Psychology Review, 33*, 959–987.
- Lindsey, R. V., Shroyer, J. D., Pashler, H., & Mozer, M. C. (2014). Improving students' long-term knowledge
  retention through personalized review. *Psychological Science, 25*(3), 639–647.
- McDaniel, M. A., Thomas, R. C., Agarwal, P. K., McDermott, K. B., & Roediger, H. L. (2013). Quizzing in
  middle-school science: Successful transfer performance on classroom exams. *Applied Cognitive Psychology, 27*,
  360–372.
- Muller, D. A., Bewes, J., Sharma, M. D., & Reimann, P. (2008). Saying the wrong thing: Improving learning with
  multimedia by including misconceptions. *Journal of Computer Assisted Learning, 24*(2), 144–155.
- Pan, S. C., & Rickard, T. C. (2018). Transfer of test-enhanced learning: Meta-analytic review and synthesis.
  *Psychological Bulletin, 144*(7), 710–756.
- Paul, W., & Vahrenhold, J. (2013). Hunting high and low: Instruments to detect misconceptions related to algorithms
  and data structures. *SIGCSE '13*, 29–34.
- Rawson, K. A., & Dunlosky, J. (2011). Optimizing schedules of retrieval practice for durable and efficient learning.
  *JEP: General, 140*(3), 283–302.
- Rowland, C. A. (2014). The effect of testing versus restudy on retention: A meta-analytic review of the testing
  effect. *Psychological Bulletin, 140*(6), 1432–1463.
- Shtulman, A., & Valcarcel, J. (2012). Scientific knowledge suppresses but does not supplant earlier intuitions.
  *Cognition, 124*(2), 209–215.
- Treagust, D. F. (1988). Development and use of diagnostic tests to evaluate students' misconceptions in science.
  *International Journal of Science Education, 10*(2), 159–169.
- Tsui, C.-Y., & Treagust, D. F. (2009). Evaluating secondary students' scientific reasoning in genetics using a
  two-tier diagnostic instrument. *International Journal of Science Education, 32*(8), 1073–1098.
- LLM misconception detection: "Can LLMs identify gaps and misconceptions in students' code explanations?"
  (arXiv:2501.10365); "The correct answer trap" (arXiv:2605.23925); Eedi misconception diagnosis from dialogue
  (arXiv:2602.02414).
