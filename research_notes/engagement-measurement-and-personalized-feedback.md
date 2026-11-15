# Measuring engagement and providing personalized feedback in SyllaByte

Date: 14 November 2026  
Population: Undergraduate students using the SyllaByte phone app and watching educational videos inside it  
Status: Research synthesis and proposed engagement-support feature design, with evaluation context

Implementation: [Phased engineering plan with file mappings and acceptance checks](../plan/engagement-feedback-implementation-plan.md).

The immediate design task is to measure how students engage while using SyllaByte and watching its videos, then use those observations to give personalized feedback that supports self-awareness, engagement, and learning. The app should help students notice a specific pattern, understand its possible significance, choose an appropriate action, and check the result.

The overarching research question remains: **Does the entire personalized video-learning system improve undergraduate students' engagement and learning?** An expert study will assess video quality and a user study will assess engagement, usability, learning outcomes, and related experiences. These studies evaluate the system; the measurement and feedback features described here are part of the experience students receive. Self-awareness is an explicit design goal of this feature, even if it is a secondary outcome in the broader study.

The recommended first version combines automatic playback and app-activity logging, occasional short check-ins, and evidence from learning responses and confidence. Camera sensing is optional later work. More screen time, more taps, or greater video completion alone would not establish success.

## Recommended engagement support feature

The student experience should follow this sequence:

> Observe a relevant pattern → clarify ambiguity when necessary → explain the evidence briefly → offer an immediately available action → revisit the result

For example, after repeated viewing of a binary-search explanation, the app can offer a question about the stopping condition. If the student answers incorrectly and says the explanation was difficult, offer a simpler trace or an alternative explanation. If the student answers correctly with a sound reason, offer a new application. Replaying alone does not distinguish these cases.

### Collect three complementary kinds of evidence

| Evidence source | Concrete data | Student effort | Role in feedback |
|---|---|---|---|
| Automatic app observations | Playback intervals, replays, seeks, speed, app activity changes, attempts, optional activity choices | No additional response | Locate a potentially useful moment for support and describe behavior |
| Brief check-ins | Attention at a sampled moment, interest, perceived difficulty, reason for an interruption or replay | One short response at selected moments | Clarify experiences the phone cannot directly observe |
| Learning and monitoring evidence | Answers, explanations, assistance used, confidence before feedback, later recall | Embedded in meaningful learning tasks | Identify what support to offer and help students recognize their understanding |

The system should use these inputs jointly. Learning performance is evidence about understanding, not a direct engagement label. Self-reports are evidence about the student's reported experience, not objective continuous attention readings. The later literature sections explain these distinctions and their empirical basis.

### Connect each measurement to a student benefit

The following operational rules are proposed product behavior. Thresholds and prompt frequency require piloting. Every offer can be skipped, and a dismissed offer should not immediately reappear.

| Situation and evidence | When to respond | Feedback shown to the student | Action available in the app | What the student can learn about themselves |
|---|---|---|---|---|
| Repeated viewing of one concept, followed by an error and reported difficulty | At the next video boundary or after the response | You revisited this step, and the stopping condition is still unclear. A smaller example may help. | Open a worked trace, show a prerequisite explanation, or choose another explanation | Which specific concept needs support and which explanation helps |
| Repeated viewing followed by a correct explanation | After the response | You revisited the example and explained the key step correctly. Try applying it to a new case. | Open a transfer question or continue | Rewatching can be a productive study choice rather than a sign of failure |
| Student reports thoughts unrelated to the task | After the check-in | You said your attention drifted. Choose a short recap, a question about the last idea, or a pause. | Replay the relevant segment, retrieve the main idea, or save the place and pause | Notice attention lapses and practice choosing a recovery strategy |
| App interruptions with an unclear cause | On return, only when useful | Welcome back. Were you checking course material, interrupted, or taking a break? | Resume without answering; optionally identify the reason | Recognize interruptions without being mislabeled |
| Student confirms repeated unwanted interruptions | At the end of the activity | You said interruptions made this session harder. Try one short study block with fewer interruptions next time. | Set a small session goal; optionally choose a reminder | Recognize environmental conditions worth changing |
| Incorrect answer with high confidence | Immediately after answer feedback | You were certain, but this case uses a different stopping rule. Compare the two cases, then explain the difference. | Open a side-by-side example and answer a new question | Identify a specific mismatch between confidence and understanding |
| Correct reasoning with low confidence across multiple opportunities | Session reflection | You solved these examples correctly even when unsure. Review which steps you can already justify. | Review successful reasoning and try another example | Recognize evidence of competence without unsupported reassurance |
| Reported boredom with successful application | Between videos | These examples seem familiar, and you handled the application question. Try a more challenging case or move on. | Choose a harder activity or skip familiar material when appropriate | Distinguish lack of challenge from lack of ability |
| Reported difficulty or frustration with unresolved errors | After an unsuccessful attempt | Let's work through the first step together. You can then try the next one. | Open a hint, a worked first step, an alternative explanation, or pause | Recognize when to seek support and change strategy |
| Strong immediate familiarity but weak delayed recall | During later review | This felt clear last time, but recalling it was harder today. Try remembering the steps before replaying. | Attempt retrieval, reveal a cue, then review | Distinguish recognizing an explanation from being able to recall it |

Do not infer boredom from skipping, distraction from backgrounding, or confusion from replay alone. These observations can justify an optional clarification or learning check. Confirmed reports and task evidence determine the more specific response.

### Deliver feedback at three useful times

During learning, use a small contextual card at a natural boundary. It should show one observation and one main action, with an alternative and a way to continue. The proposed default is to offer assistance rather than automatically changing playback speed, lowering the student's level, or stopping the video. Adapt ability estimates through the existing assessment logic rather than behavioral engagement signals.

At the end of a session, show a short reflection linking the student's goal, demonstrated understanding, and one next action. For example:

> You wanted to understand binary search. You explained how the interval shrinks, but the stopping condition needs another check. You chose a worked example today. Next time, begin with a new trace problem.

Do not claim that the worked example caused improvement just because a later answer was correct. Report the sequence of events and use independent later questions to check whether understanding persists.

After several sessions, offer a personal pattern with its supporting observations, not a fixed learner label. For example:

> You reported interruptions in three recent sessions. Would you like to try a shorter planned session and compare how it feels?

Only show such a message when those observations exist. If reporting performance differences between sessions, account for topic difficulty and assistance, show sample sizes, and describe associations tentatively. Use the student's own relevant history rather than class rankings.

### Make personalization explainable and actionable

Each recommendation should depend on the current concept, the student's response and confidence, relevant recent behavior, and their chosen goal or preference. Students who show the same replay behavior can receive different support because their understanding differs.

Select a specific action before generating its wording. A rule can select the relevant worked example, prerequisite video, retrieval question, or challenge. An LLM may phrase an explanation using approved course material, but should not invent a reason the student was distracted or a learning pattern absent from the data.

Maintain two histories: what evidence supported the recommendation, and what the student actually did. Record whether the offer was shown, accepted, skipped, attempted, and followed by new evidence. Acceptance alone does not mean the advice helped. An optional later question such as "Did that explanation help?" captures perceived usefulness alongside performance.

### Build the first version in this order

1. Capture dependable playback, concept, app-activity, and response events, including assistance and confidence timing.
2. Add a small set of optional attention, interest, and difficulty check-ins, plus a reason question only when behavior is ambiguous and clarification is useful.
3. Implement three complete feedback paths: confirmed difficulty, confidence–performance mismatch, and student-reported attention drift. Include productive-review handling so replay never automatically becomes a negative judgment.
4. Add a short session reflection and later retrieval linked to the same concepts.
5. Add personal patterns only after there is enough comparable history. Consider camera sensing only if it improves useful decisions beyond these inputs.

The immediate deliverable is a working measurement-to-feedback specification and one complete student experience. The expert and user studies remain the later means of evaluating the whole system.

## Scope and evidence standards

This is a targeted narrative literature review covering engagement theory, online and video learning, self-regulated learning, metacognition, feedback, learning analytics, and smartphone sensing. The search included foundational research and recent publications available through November 2026. Search topics included multidimensional student engagement, video clickstreams, mind-wandering and retrieval tests, metacognitive prompts, confidence calibration, dashboard effectiveness, smartphone gaze estimation, and automated engagement detection.

Priority was given to original studies, systematic reviews, meta-analyses, author or institutional copies of papers, and official platform documentation. The review is not an exhaustive systematic review: there was no registered search protocol, complete database export, duplicate screening, or formal risk-of-bias assessment. Sources were inspected through accessible full texts, publisher abstracts, and publication records; access depth varied. The bibliography provides direct links for further reading.

Evidence is interpreted at its actual scope:

- A randomized intervention study can support a causal claim about the intervention and setting it tested.
- An observational association can identify a useful pattern but cannot establish why it occurred.
- A sensor validation study can establish measurement performance under its tested conditions without validating an educational interpretation.
- A framework can guide design without proving that a particular app implementation works.
- A result from desktop learning, text comprehension, or mobile health requires validation before being generalized to undergraduate micro-video learning.

The proposed rules, prompt frequencies, interface examples, and roadmap below are design choices to test. They are not validated engagement instruments or universally optimal thresholds.

## What engagement means in this project

Fredricks, Blumenfeld, and Paris distinguish behavioral, emotional, and cognitive engagement. Their review supports treating engagement as a multidimensional construct. A more recent review of 159 higher-education learning-analytics studies found that observable behavior, including clicks and task duration, still dominates measurement, while relatively few studies address multiple dimensions. [Fredricks et al., 2004](https://doi.org/10.3102/00346543074001059); [Bergdahl et al., 2024](https://doi.org/10.1186/s41239-024-00493-y).

| Construct | Research question | Suitable evidence in SyllaByte |
|---|---|---|
| Behavioral engagement | Is the student participating and persisting? | Questions attempted, returning after interruptions, resuming activities, video exposure |
| Cognitive engagement | How is the student processing the material? | Explanations, predictions, connections, revisions to reasoning, strategy changes |
| Emotional engagement | How does the student experience the activity? | Reports of interest, boredom, confusion, and frustration |
| Attention | Where is attention directed at sampled moments? | Occasional thought probes and contextual behavioral indicators |
| Self-regulation and self-awareness | Can the student recognize understanding and adjust studying? | Confidence versus performance, planning, reflection, and strategy selection |

Attention and self-regulation are related processes, not interchangeable synonyms for the engagement dimensions. Keep them separate in the data model and outcome analysis.

Students should also be able to request a different explanation, identify an unclear point, and choose an application problem. These are opportunities for agentic engagement: constructively influencing the instruction received. [Reeve & Tseng, 2011](https://doi.org/10.1016/j.cedpsych.2011.05.002).

A student can watch silently and reason deeply. Another can tap frequently without processing the content. Confusion may accompany serious cognitive effort, and replaying may reflect effective review. This is why no single behavioral count should be treated as a complete engagement measure.

## Evidence most relevant to feedback design

| Study | Design and main finding | Implication and boundary |
|---|---|---|
| Guo, Kim, and Rubin, 2014 | Observational analysis of 6.9 million video-watching sessions. Video length and production features were associated with watching behavior and assessment attempts. | Collect playback data and investigate content design. The measured behaviors do not establish comprehension or a universal ideal video length. [Paper](https://juhokim.com/files/LAS2014-Engagement.pdf) |
| Szpunar, Khan, and Schacter, 2013 | Two experiments found that interpolated memory tests reduced reported mind-wandering and improved online-lecture learning. | Insert retrieval opportunities at meaningful boundaries. The study does not establish an optimal frequency for short phone videos. [Paper](https://doi.org/10.1073/pnas.1221764110) |
| Chi and Wylie, 2014 | ICAP distinguishes passive reception, active manipulation, constructive generation, and substantive interaction. | Explanations and predictions provide richer evidence than tapping alone. Watching characters converse is not automatically interactive engagement by the viewer. [Paper](https://doi.org/10.1080/00461520.2014.965823) |
| Bisra et al., 2018 | Meta-analysis of 69 effect sizes from 64 research reports found an average effect of self-explanation prompts on learning of g = 0.55. | Occasionally ask why a step works or how concepts connect. This does not validate automatic scoring of student explanations. [Paper](https://doi.org/10.1007/s10648-018-9434-x) |
| Guo, 2022 | Meta-analysis found effects of metacognitive prompts on self-regulated learning activities of g = 0.50 and learning outcomes of g = 0.40. Effects varied with specificity, adaptability, and feedback. | Use task-specific prompts that lead to an action. Avoid assuming every reflection prompt is equally effective. [Paper](https://doi.org/10.1111/jcal.12650) |
| Wisniewski, Zierer, and Hattie, 2020 | Meta-analysis of 435 studies involving over 61,000 participants found an average feedback effect of d = 0.48, with substantial variation. Information content mattered. | Give useful information about the task and strategy. Cognitive benefits cannot be assumed to imply equal motivational or behavioral benefits. [Paper](https://doi.org/10.3389/fpsyg.2019.03087) |
| Kizilcec, Pérez-Sanagustín, and Maldonado, 2016 | Randomized MOOC experiment with 653 learners found that study-strategy recommendations did not improve persistence or achievement despite favorable helpfulness ratings. | Helpful-sounding advice is insufficient. The studied one-time recommendation intervention does not establish that ongoing adaptive support also fails. [Paper](https://rene.kizilcec.com/wp-content/uploads/2016/02/kizilcec2016recommending.pdf) |
| Kizilcec, Pérez-Sanagustín, and Maldonado, 2017 | Observational study of 4,831 learners across six MOOCs linked planning and goal setting with personal goal attainment; stronger self-regulation was associated with revisiting materials. | Interpret replay alongside understanding and goals. Associations do not prove that increasing replays causes improvement. [Paper](https://www.rene.kizilcec.com/wp-content/uploads/2016/11/kizilcec2017srl.pdf) |
| Kaliisa et al., 2024 | Review of 38 dashboard studies found limited convincing evidence of achievement benefits and recurring self-selection and sample-size limitations. Participation findings were more promising. | Displaying analytics is not sufficient evidence of educational benefit. [Paper](https://doi.org/10.1145/3636555.3636884) |
| Giorgashvili et al., 2025 | Analysis of 1,251 reflections from 417 students found that personalized dashboard feedback influenced what learners intended to change. | Feedback can direct reflection. The analyzed intentions do not establish subsequent behavior change or learning improvement. [Paper](https://doi.org/10.1111/jcal.70073) |
| Gestiardi and Yuniawatika, 2026 | Journal pre-proof pooling 21 controlled dashboard studies reported a small student-facing effect, g approximately 0.29, with substantial heterogeneity. Pooled effects for log-based engagement, self-reported self-regulation, and motivation were not significant. | Treat dashboard benefits as dependent on implementation and outcome. The findings neither guarantee benefit nor establish that dashboards never help. [Paper](https://doi.org/10.1016/j.iheduc.2026.101119) |

These effect sizes concern different interventions, populations, and outcomes. They are not directly comparable estimates of SyllaByte's likely impact. They motivate the system's learning and feedback components; the user study evaluates their combined implementation with the personalized videos.

## Measurements to implement in the phone app

The table below operationalizes the literature for SyllaByte. It separates directly logged events from interpretations that need corroboration.

| Measurement | Collection method | Useful interpretation | Main limitation |
|---|---|---|---|
| Video exposure | Playback intervals, position, speed, buffering, and app state | Which content played under which conditions | Playback does not establish attention |
| Unique content coverage | Union of content intervals actually played divided by video duration | Proportion of distinct content exposed | Seeking to the end must not count as watching all intervening content |
| Pauses and replays | Pause times, backward seeks, repeated segments | Where students stop or revisit | Could indicate review, confusion, note-taking, or interruption |
| Session interruptions | App activity transitions and return times | When app activity was interrupted | Does not identify the cause or whether studying continued elsewhere |
| Participation and persistence | Attempts, voluntary retries, resuming after an error or interruption | Observable involvement | More attempts can reflect persistence, difficulty, or interface problems |
| Generative activity | Explanations, predictions, examples, conceptual connections | Evidence of reasoning and processing | Evaluate substance rather than length, speed, or number of taps |
| Current attention | Occasional thought probes | Reported attention at sampled moments | Reports are imperfect and the probe can change attention |
| Interest and difficulty | Separate brief ratings after selected activities | Subjective learning experience | Interest, effort, difficulty, and disengagement are different constructs |
| Confidence calibration | Confidence before correctness feedback, paired with answer outcome | Recognition of certainty and uncertainty | Requires consistent timing, adequate observations, and attention to item difficulty |
| Retention and transfer | Later recall and novel application questions | Persistence and application of learning | These are outcomes, not direct engagement measures |
| Planning and regulation | Goals, intended duration, strategy choices, follow-through | Deliberate management of studying | Revising a plan can be appropriate |
| Feedback uptake | Recommendation shown, selected, attempted, dismissed, and subsequent outcome | Whether feedback leads to action | Selection alone does not establish usefulness |

### Playback and interruption definitions

Maintain separate quantities for elapsed session time, elapsed playback time, content seconds played, and unique coverage. At 2× speed, content time advances faster than elapsed time; replay increases exposure without necessarily increasing unique coverage. Exclude buffering from playback exposure. Record whether playback happened while the app was active, and handle supported audio or picture-in-picture use explicitly rather than assuming all background time is disengagement.

Define sessions and interruptions before analysis. A timeout is a technical definition, not a psychological threshold. For example, the current 30-minute grace period in the engagement logic is an application heuristic, not a validated point at which a student becomes disengaged.

No-touch intervals should not automatically be classified as inactivity during video watching. Likewise, leaving the app is not evidence of opening social media. React Native documents app-state and focus events that can also occur during system interactions; on Android, the notification drawer can trigger blur without changing AppState. [React Native documentation](https://reactnative.dev/docs/appstate.html).

### Attention and experience check-ins

An initial thought probe could ask:

> Just before this prompt, what were you thinking about?
>
> The video / Thinking through the idea / Something unrelated / Something around me / Prefer not to answer

Distinguishing reflection about the idea from unrelated thoughts reduces the risk of interpreting productive thinking as disengagement. Research also distinguishes intentional and unintentional mind-wandering, which can relate differently to motivation and retention. [Seli et al., 2016](https://pubmed.ncbi.nlm.nih.gov/26585116/).

Use separate prompts for interest and difficulty when relevant:

- How interested were you in this example?
- How difficult was that?
- Are you feeling stuck?

These are proposed study-specific items. Do not describe them as a validated scale. Pilot comprehension, response burden, missingness, and whether students distinguish the response options. Do not administer every item after every video by default.

Confusion should lead to a check for support needs, not an automatic disengagement label. Research suggests confusion can benefit learning when it is appropriately regulated and resolved. [D'Mello et al., 2014](https://doi.org/10.1016/j.learninstruc.2012.05.003).

### Learning activities

Use a mix of retrieval, prediction, and explanation:

- Recall: state the stopping condition without replaying the clip.
- Prediction: choose the next step in a new example.
- Explanation: explain why that step follows.
- Transfer: apply the concept to a structurally different problem.

The activity attempted and the quality of the response are different variables. An inaccurate but thoughtful explanation may reflect engagement while revealing a misconception. A correct multiple-choice answer may reflect prior knowledge or guessing. Record assistance and attempt history to interpret both appropriately.

## Phone sensors and their limits

| Signal | Feasible observation | Recommended role |
|---|---|---|
| Front-camera gaze or head orientation | Approximate gaze direction, orientation, face presence | Optional later extension after validation on target phones and conditions |
| Facial movements | Observable facial features or model-generated expression labels | Do not use as the primary measure of boredom, confusion, or engagement |
| Accelerometer and gyroscope | Device movement and orientation | Context only; movement has no unique engagement meaning |
| Microphone | An explicitly recorded explanation; potentially environmental audio | Prefer deliberate voice responses if needed; omit ambient recording from the initial design |
| Heart rate and related physiology | Signals obtained through suitable sensing methods or additional wearables | Outside the initial phone-only implementation; not specific to engagement |
| Location and daily routines | Broader patterns in context and behavior | Low priority for feedback during in-app video learning |

Krafka et al. demonstrated gaze estimation using commodity phones and tablets. Valliappan et al. subsequently reported approximately 0.46 cm gaze error with calibration and favorable viewing conditions, while documenting reduced performance as head pose and distance changed. These studies validate gaze estimation under their conditions; they do not establish that looking toward a screen means understanding the content. [Krafka et al., 2016](https://openaccess.thecvf.com/content_cvpr_2016/html/Krafka_Eye_Tracking_for_CVPR_2016_paper.html); [Valliappan et al., 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7486382/).

Facial emotion inference introduces an additional validity problem. A major review challenges the assumption that facial movements map reliably to specific emotions across contexts. A neutral expression cannot simply be translated into boredom. [Barrett et al., 2019](https://pubmed.ncbi.nlm.nih.gov/31313636/).

A 2026 systematic review of 42 engagement-prediction studies identified heavy dependence on facial information and limited model generalization. DAiSEE, a widely used dataset, contains observer-assigned affective labels. Predicting such labels does not establish direct measurement of internal attention or understanding. [Theophilus et al., 2026](https://doi.org/10.1007/s44163-026-01761-8); [DAiSEE documentation](https://people.iith.ac.in/vineethnb/resources/daisee/index.html).

StudentLife followed 48 college students over ten weeks and found associations between smartphone-derived behavior and educational or wellbeing outcomes. It supports the feasibility of broader sensing research, but it did not establish a moment-to-moment video-engagement detector. [Wang et al., 2014](https://users.ece.utexas.edu/~ethomaz/courses/asr/papers/health/student-life.pdf).

A detailed, evidence-based design for camera sensing (what to measure, how to analyse it, what feedback to give and when, consent, and a staged evaluation) is in [Camera-based attention sensing](camera-based-attention-sensing.md).

If camera sensing is added, compare a model using behavior and check-ins with the same model plus camera features. Measure incremental decision quality, false alerts, missingness, and burden. Treat failed tracking as missing data, not disengagement. Keep learning available without camera participation and specify what data is retained.

### Watching inside the app versus other apps

The core study does not require device-wide tracking. Your own video player and app lifecycle provide the relevant basic events. A supported embedded YouTube player can expose player states and playback position through its API, but that does not grant access to videos watched in the separate YouTube app. [YouTube IFrame Player API](https://developers.google.com/youtube/iframe_api_reference).

Android usage statistics require special access. Apple's Screen Time technologies involve authorization and entitlements. These capabilities have platform-specific limits and should not be assumed to provide detailed educational-video interactions in other apps. [Android UsageStatsManager](https://developer.android.com/reference/android/app/usage/UsageStatsManager); [Apple Family Controls entitlement](https://developer.apple.com/documentation/FamilyControls/requesting-the-family-controls-entitlement).

## Personalized feedback rules

Feedback should connect an observation with a cautious interpretation and a student-controlled action:

> What happened → what it may mean → one useful option → a later check of whether it helped

This draws on feedback theory's emphasis on goals, progress, and next steps, and on self-regulated learning models that connect planning, monitoring, control, and reflection. [Hattie & Timperley, 2007](https://doi.org/10.3102/003465430298487); [Panadero, 2017](https://doi.org/10.3389/fpsyg.2017.00422).

The following are proposed rules and example messages. Exact triggers need piloting.

| Evidence | Example feedback | Intended next action |
|---|---|---|
| Replay plus incorrect answer and reported difficulty | You revisited the recursion example and missed the stopping-condition question. Try tracing one smaller example step by step. | Work through a targeted example |
| Replay plus accurate explanation | You revisited the example and explained the stopping condition correctly. Try a new case to check whether it transfers. | Attempt an application problem |
| High confidence plus incorrect answer | You were confident about this answer. The missing distinction is between X and Y. Try explaining that difference before the next question. | Examine a misconception and revise reasoning |
| Low confidence across several correct answers | You answered these application questions correctly even when unsure. Compare your reasoning with the worked explanation. | Recognize evidence of competence |
| Reported unrelated thoughts | Would you like to pause for a moment or answer a quick question about the last idea? | Choose a recovery action |
| High reported difficulty and persistent errors | Let's work through the first step together, then you can try the next one. | Use partial support and continue actively |
| Low interest with demonstrated understanding | You're handling these examples accurately. Choose a harder application or move to the next concept. | Adjust challenge or progress |
| Interrupted session with student-confirmed distraction | You said notifications interrupted this session. For the next video, you could try a short uninterrupted study block. | Test a contextual change |
| High immediate confidence with weak later recall | This felt clear yesterday, but today's recall was harder. Try recalling the steps before replaying the explanation. | Use retrieval before rewatching |

Practice testing and distributed practice have substantial support in the broader learning-science literature. Their inclusion is justified, while the appropriate schedule for SyllaByte's content remains an implementation question. [Dunlosky et al., 2013](https://pubmed.ncbi.nlm.nih.gov/26173288/).

Let students correct ambiguous interpretations. For example: "You paused several times. Were you taking notes, thinking, interrupted, or doing something else?" The answer adds context and creates an opportunity to reflect.

Do not produce a stable trait judgment from a small number of observations. Use wording such as "In these questions" rather than "You are overconfident." Missing reports and rejected suggestions must remain legitimate responses.

## Confidence calibration and self-awareness

Collect answer confidence after the student chooses an answer and before correctness feedback. Record whether the response was assisted and whether confidence was collected before or after that assistance.

An understandable display is:

> Of the 12 answers you marked certain, 8 were correct.

A judgment about future learning is different:

> How likely are you to explain this idea tomorrow without the video?

Pair that judgment with a later retrieval task. This separates recognizing current correctness from recognizing durable understanding. A meta-analysis on metacomprehension found poor monitoring of text comprehension and benefits from interventions; extending those findings to micro-videos is a hypothesis to test. [Yang et al., 2022](https://doi.org/10.3102/00346543221094083).

For the initial interface, retain descriptive counts by confidence category and show sample sizes. Do not map "certain," "pretty sure," and "guessing" to invented probabilities. If a research protocol uses explicit probability estimates, prespecify suitable calibration and discrimination measures. A single signed average confidence-minus-accuracy value can hide opposite errors that cancel out; it is insufficient on its own.

An initial reflection display should include:

- Understanding: concepts demonstrated on questions and explanations.
- Confidence: where confidence and correctness agree or diverge.
- Study patterns: replay, interruptions, and chosen strategies.
- Next experiment: one strategy the student elects to try.

Avoid an overall engagement percentage without a validated measurement model. Multiple interpretable indicators better support discussion of conflicting evidence. A student can reasonably report strong concentration while still misunderstanding the content.

## Feedback timing and delivery

| Time | Interaction | Purpose |
|---|---|---|
| Before the session | A small goal and optional time/context check | Establish what the learner intends to accomplish |
| At a natural boundary | Retrieval, explanation, or a relevant check-in | Support processing and gather useful evidence |
| After the session | A short reflection and one main recommendation | Connect observations with a next action |
| At a later review | Recall or application and comparison with an earlier judgment | Check retention and monitoring accuracy |

For micro-videos, the gap between videos is a practical initial location for prompts. Test a limited number of check-ins and one main recommendation per session, with skip and snooze options. These are starting choices, not evidence-based universal frequencies.

The just-in-time adaptive intervention framework helps specify decision points, tailoring variables, intervention options, and rules, including when to provide no intervention. Its foundational context is mobile health, so its role here is a design framework, not proof of educational efficacy. [Nahum-Shani et al., 2018](https://pubmed.ncbi.nlm.nih.gov/27663578/).

Feedback can itself interrupt learning. Experimental work found that receiving phone notifications impaired performance on an attention task even without interacting with the phone. That was not a video-learning trial, but it supports testing notification burden instead of assuming more prompts are beneficial. [Stothart et al., 2015](https://carystothart.com/publications/attentional-cost-cell-phone-notification/).

Compare a learner primarily with their own relevant history, accounting for topic, task difficulty, and assistance. Do not automatically rank students by watch time or replay count. Patterns such as "you recall more after short sessions" should remain tentative observational findings unless experimentally tested.

## Initial decision system and data design

Start with transparent rules that combine evidence:

- Replay alone: offer an optional understanding check.
- Replay, confusion, and an error: offer a targeted worked example.
- Replay and accurate reasoning: offer application practice.
- Low interest and demonstrated understanding: offer challenge or progression.
- Missing, conflicting, or sparse evidence: show descriptive information or no recommendation.

If an LLM is used, a suitable initial role is generating wording or a course-grounded explanation after the rule has selected the action. Retain the evidence and rule version behind each recommendation. Validate automated evaluation of explanations against human scoring before using it as a research measure.

An implementation specification should identify these event groups without assuming that their exact names already exist in the application:

| Event group | Essential information |
|---|---|
| Session and context | Session identifier, course, start/end, app activity state, timestamps, technical interruption information |
| Playback | Video and knowledge-unit identifiers, content version, position, speed, interval boundaries, buffering and visibility context |
| Learning response | Item and version, selected answer or explanation, attempt, correctness or rubric result, assistance |
| Confidence | Confidence value and scale version, timing relative to answer, assistance, and feedback |
| Check-in | Prompt version, trigger or sampling reason, response, skipped status, timestamp |
| Feedback | Rule and message version, evidence used, option shown, selected or dismissed, subsequent action |
| Follow-up | Related concept and prior session, delay, question, response, assistance, and outcome |

Use pseudonymous research identifiers and preserve the app's consent and withdrawal behavior. Distinguish technical missingness from deliberate skips. Record enough timing information to align events and handle offline uploads without interpreting upload time as learning time.

Before collecting research data, define which data support ordinary personalization and which are collected for the study. For optional sensing, document the purpose, retained representation, and deletion behavior. The initial system can avoid raw camera and ambient audio collection entirely.

## Evaluation of measurement quality

Triangulate behavior with sampled attention reports, explanation quality, and independent learning checks. None is a perfect ground truth for every engagement dimension. Observer judgments measure visible behavior; self-reports measure reported experience; performance measures what a student can demonstrate.

Study disagreements rather than forcing every signal into one label. For example, frequent replay plus strong transfer may indicate a productive strategy. Low reported attention plus a correct easy question may reflect prior knowledge rather than successful learning during the video.

If building a predictive model:

- Separate training and evaluation by student, not randomly by event or video frame.
- Test on unseen content and devices where feasible.
- Compare with simple baselines and models using fewer inputs.
- Report class balance, false alerts, uncertainty, and missingness alongside aggregate performance.
- For cameras, evaluate relevant lighting, pose, glasses, device, and participant conditions.
- Validate the target label itself; strong prediction of a weak label does not solve construct validity.

Distinguish a measurement model's ability to predict an attention report from the causal benefit of acting on that prediction. Those require separate evaluation.

## Evaluation of the whole personalized video learning system

The confirmed overarching question is:

> Does the entire personalized video-learning system improve student engagement and learning?

Use two complementary studies with distinct evidence and units of analysis:

| Study | Question | Evidence and unit of analysis |
|---|---|---|
| Expert study | Are the generated videos accurate, instructionally appropriate, clear, and suitable for their intended learners? | Expert ratings and error annotations for sampled videos, knowledge units, and target learner levels |
| User study | Does using the complete system improve undergraduate engagement and learning relative to the selected baseline, and how usable is it? | Student assessments, comparable engagement measures, app behavior, questionnaires, and interviews |

The protocols below are proposals within that confirmed structure. Expert-rated motivational appeal is not a measurement of actual student engagement, and students liking a video does not establish its factual accuracy.

### Expert study of video quality

Recruit subject-matter experts to assess correctness and curriculum alignment, and reviewers with instructional or multimedia-design expertise where available. Record their expertise and any involvement in developing SyllaByte. Give reviewers the source slides, learning objective, intended learner profile, and target level alongside each video. They need that context to judge suitability.

The Learning Object Review Instrument provides a useful starting framework, including content quality, learning-goal alignment, feedback and adaptation, presentation, and accessibility. The rubric below adapts relevant ideas to generated videos; it is a proposed study-specific rubric, not an unchanged validated LORI scale. [Leacock & Nesbit, 2007](https://www.sfu.ca/~jcnesbit/articles/leacocknesbit2007.htm).

| Proposed dimension | What experts examine | Evidence to record |
|---|---|---|
| Factual and conceptual accuracy | Definitions, reasoning, calculations, examples, and conclusions | Error description, severity, and timestamp |
| Source fidelity and objective alignment | Consistency with course materials and coverage of the intended objective | Unsupported claims, omissions, and alignment rating |
| Instructional clarity | Logical sequence, explanation of steps, examples, and misconception handling | Anchored rating and specific confusing passages |
| Suitability for the target level | Assumed prerequisites, complexity, scaffolding, and challenge | Fit to the supplied learner profile; comparison across versions of the same concept |
| Visual and audio quality | Diagram correctness, legibility on a phone, synchronization, narration, and captions | Rating and timestamped presentation defects |
| Pacing and information density | Time to process concepts and amount of information presented | Overloaded or unnecessarily slow segments |
| Accessibility | Readable text, usable captions, contrast, and reliance on color or sound alone | Observable barriers; do not infer full accessibility from expert ratings alone |
| Anticipated motivational appeal | Relevance, examples, and presentation likely to sustain interest | Expert expectation, reported separately from student engagement |

Use dimension-specific anchors, such as 1 to 5, plus comments and a separate critical-error flag. A visually polished video with a serious conceptual error must not receive an acceptable quality judgment merely because other ratings average out the problem. Define acceptance and revision criteria before the main ratings.

Sample across knowledge units, subject difficulty, target levels, and output types actually used by the system. Include matched level variants for selected concepts so reviewers can judge whether adaptation changes the explanation appropriately. Specify the sampling frame, pipeline version, and whether the target is first-pass generation quality or quality of the final videos delivered to students. Retain rejection and repair information when reporting pipeline performance rather than selecting only showcase outputs.

Have multiple experts independently rate overlapping videos, ideally every sampled video where workload permits. Calibrate the rubric on separate examples, then preserve independent ratings before any reconciliation discussion. Randomize presentation order and conceal irrelevant generation labels where feasible; retain the target learner description because it is needed for the judgment.

Report ratings by dimension, critical-error frequency, disagreements, and uncertainty. Select an inter-rater agreement statistic suited to the scale and assignment design. If using an intraclass correlation coefficient for suitable quantitative scores, specify its model, single- versus average-rater type, and agreement definition, and report confidence intervals. [Koo & Li, 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4913118/); [2017 correction](https://pmc.ncbi.nlm.nih.gov/articles/PMC5731844/).

Separate formative review used to improve videos from the final expert evaluation. Version any repaired videos and identify which version students receive. If outputs are generated during the user study, retain their versions and specify how they relate to the expert-reviewed sample; a rating of one frozen video does not cover every future generated output.

### User study of engagement usability and learning

The intervention is SyllaByte as delivered: personalized videos, navigation and sequencing, learning activities, and any engagement feedback included in the study version. Document that package and record the recommendations and video versions each student receives.

A comparison group is needed for a persuasive claim that the system improves outcomes relative to an alternative. The existing slide-viewer plan is a candidate, not a newly finalized choice. The meaning of the result depends on the selected baseline:

| Candidate comparator | What the comparison estimates |
|---|---|
| Existing course slides or usual study resources | Benefit of the complete SyllaByte experience relative to the selected usual resource |
| A fixed nonpersonalized video-learning experience | Benefit of the complete SyllaByte experience relative to that specified video baseline; attribution depends on all differences between conditions |

The whole-system question allows the intervention to include learning activities and support that the baseline lacks. Those differences are part of the treatment package. Keep learning objectives, source scope, research assessments, and scheduled study opportunities comparable, and record actual study time. Decide whether the intended question concerns learning within a fixed time budget or effectiveness under natural use. Do not automatically adjust away extra study time if it is a pathway through which the system works.

Random assignment is recommended where feasible. A parallel-group design avoids exposing the same student to the same content twice. If logistics require a within-student design, use different but matched topics, counterbalance condition and order, and account for topic differences and carryover. A single-group usability study can establish feasibility and describe experience but cannot by itself establish comparative effectiveness.

Use common research measures where possible, with condition-specific behavior as supporting evidence. Video completion and reaching the last slide are different observations, even when both are expressed as percentages. More taps or more completed in-app questions in a condition offering more opportunities is not an independent demonstration of higher engagement.

| Outcome | Proposed evidence | Role and interpretation |
|---|---|---|
| Engagement | Comparable engagement self-reports, sampled attention or interest, and meaningful participation | Central outcome; prespecify dimensions and a main measure |
| Learning | Baseline knowledge, common immediate assessments, delayed retention, and transfer | Central outcome; keep outcome items separate from adaptive practice |
| Usability | Existing SUS questionnaire, task completion, navigation errors, and interviews | Student experience of the app; distinguish from instructional quality |
| Workload and experience | Existing Raw NASA-TLX, perceived learning, pacing, trust where applicable, and open comments | Explain the experience; workload is not itself engagement and perceived learning is not tested learning |
| Self-awareness | Confidence versus correctness on common questions and identification of knowledge gaps | Secondary outcome or exploratory explanatory process |
| Feature use | Video exposure, replay, level changes, feedback uptake, and study time | Describe implementation and possible mechanisms; observational associations do not isolate component effects |

An initial schedule is baseline assessment, learning sessions with light measurement, immediate post-module assessment, delayed retention and transfer, and a concluding questionnaire or interview. The repository already proposes immediate and two-week delayed module quizzes; confirm that interval against the actual study schedule. Record actual delays and exposure to other course materials between tests.

Use research attention probes on a comparable sampling schedule across conditions. Event-triggered probes disproportionately sample suspected problems and should not be naively compared with uniformly sampled probes. Separate intervention prompts from outcome measurements where feasible.

Prespecify one main engagement measure and one main learning measure, together with how the two central outcomes will be tested and interpreted. Treat usability and other measures according to a declared secondary-outcome plan. Do not select confidence calibration as the primary endpoint merely because it is useful for the feedback component.

Determine sample size from the chosen design, meaningful effect, anticipated attrition, and intended analysis. More events per student do not substitute for independent participants. Account for baseline knowledge, repeated observations, and topic differences as appropriate. Prespecify missing-data handling, assistance rules, exclusions, and uncertainty reporting. Analyze randomized assignment as the main comparison; usage-based analyses can be supplementary and are vulnerable to self-selection.

The resulting claim is about the whole system relative to its baseline. Isolating personalization, video style, or engagement feedback would require an additional component comparison, which is optional future work rather than a prerequisite for this capstone evaluation.

## Existing questionnaires and study design

The repository's [study instruments plan](../plan/study-instruments-plan.md) already specifies demographics, Raw NASA-TLX, SUS, learning-efficacy items, and trust items. These address different aspects of the experience. They should not automatically be treated as substitutes for momentary attention or confidence calibration, and this research note does not replace their planned administration.

The Online Student Engagement scale is a candidate for course-level engagement assessment. It was developed for online courses, so its fit for short individual video sessions requires consideration and any adaptation needs piloting. The User Engagement Scale concerns engagement with a digital experience and should not be interpreted as a direct learning measure. [Dixson, 2015](https://olj.onlinelearningconsortium.org/index.php/olj/article/view/561); [O'Brien et al., 2018](https://pure.york.ac.uk/portal/en/publications/a-practical-approach-to-measuring-user-engagement-with-the-refine/).

The existing [Condition B plan](../plan/condition-b-plan.md) concerns a slide-viewer control and is marked as parked pending study-design decisions. Such a comparator can fit the confirmed whole-system question. Finalize the baseline and measurement equivalence with the advisor; the present clarification does not by itself settle that choice. Preserve the existing A/B labels until the protocol is finalized. Feedback remains part of the intervention rather than a separate main experiment.

## Implications for the current implementation

This review identifies changes to consider; it does not implement them.

| Existing component | Relevant behavior | Recommended follow-up |
|---|---|---|
| [Engagement logic](../packages/core/src/logic/engagement.ts) | Separates engagement adjustments from ability estimates; repeated views trigger a refresher under the assumption that material did not stick | Preserve the separation from ability. Combine replay with understanding and reported difficulty before recommending remediation |
| [Early drop-off logic](../packages/core/src/logic/engagement.ts) | Uses maximum reached playback position and a grace period | Audit coverage tracking. Maximum position alone does not establish unique exposure |
| [Confidence feedback](../packages/core/src/logic/calibration.ts) | Can default to saying confidence matches results well when no other rule fires | Use descriptive counts and insufficient-evidence wording instead of unsupported reassurance |
| [Confidence feedback](../packages/core/src/logic/calibration.ts) | Includes correct answers after hints | Record assistance and confidence timing; compare like with like in calibration analysis |
| [Next-day judgments](../packages/core/src/logic/calibration.ts) | Pairs a future-learning judgment with a later result | Retain this useful foundation, show sample size and actual delay, and avoid stable conclusions from a few pairs |
| [Event infrastructure](../packages/core/src/events.ts) | Shared event vocabulary and sink across app layers | Extend the existing mechanism; verify mobile capture, persistence, export, timing, and consent behavior end to end |

Existing code structure is a starting point, not proof that every proposed event is already collected correctly in production.

## What to do next

### First build the engagement support feature

The immediate priority is the feature design above: agree on the observable events and check-in wording, connect them to specific learning actions, and implement an end-to-end session. The study protocols below should evaluate that experience rather than displace the feature work. Start with the three feedback paths described above and verify the data and student-facing interpretation for each.

### Specify the two study protocols

The research question and two-study structure are established. The next advisor discussion should resolve the remaining design choices:

1. Which baseline will the user study compare with the complete SyllaByte system?
2. Which engagement measure and learning measure will be the main outcomes, and when will they be collected?
3. Which videos, knowledge units, and learner levels will experts evaluate, and which expertise is required?
4. What recruitment, study duration, assignment method, and delayed-testing schedule are feasible?

The output should be an expert-study protocol and a user-study protocol, each with a clear unit of analysis, sampling plan, measures, and interpretation of results. No separate feedback-effectiveness experiment is required.

### Prepare the expert review materials

Build the rubric with explicit anchors, timestamped comments, and critical-error flags. Prepare source slides, learning objectives, and target learner profiles. Choose a representative video sample and matched level variants, record generation versions, and plan overlapping independent ratings.

Pilot the rubric on a small set of separate examples. Revise ambiguous criteria before the main ratings. Specify the agreement analysis and distinguish formative corrections from the final evaluation. If reviewed videos change, retain the earlier version and document what changed.

The output should be a review packet and rating form that experts can use consistently.

### Prepare the user study measures and comparison experience

Map each central outcome to a specific measure and time point. Use common learning assessments aligned with the course objectives, including delayed retention and transfer. Pilot question difficulty and avoid reusing adaptive practice items as the sole outcome test.

Retain the existing usability, workload, and other relevant questionnaires with their intended interpretations. Select or adapt engagement items carefully and pilot their wording. Define comparable attention-probe schedules and behavioral denominators across conditions. Decide how outside study and delayed-test timing will be recorded.

Finalize and implement the comparison experience. Keep its research assessment schedule aligned with SyllaByte's while preserving the actual instructional differences that define the whole-system comparison.

The output should be an outcome matrix, instrument set, assessment schedule, and usable comparator.

### Finish the study version of the whole system

Ensure that the student can complete the intended journey:

> Baseline assessment → personalized video learning → learning activities and feedback → immediate assessment → delayed retention and transfer

Verify video delivery, adaptation, playback logging, check-ins, confidence timing, feedback decisions, and questionnaire collection. Correct unsupported calibration reassurance and distinguish productive replay from confirmed difficulty. These improvements strengthen the intervention without turning feedback into the main research question.

Preserve identifiers for videos, learner levels, items, assistance, feedback rules, and versions. Check that both study conditions export complete, interpretable data and that consent and withdrawal behavior work across the full collection path.

The output should be a versioned system and comparator that support a complete participant session and research export.

### Pilot both study procedures

Use a formative expert pilot to check the rubric and review burden. Use a formative undergraduate pilot to check navigation, task understanding, prompt burden, assessment timing, and follow-up feasibility. These pilots refine procedures rather than establish effectiveness.

Inspect missing events, misunderstood items, inappropriate feedback, technical problems, and late retention responses. Define feasibility criteria with the study team before the pilot and document changes afterward.

The output should be revised protocols, stable instrumentation, and a realistic estimate of participant and expert workload.

### Finalize and conduct the main studies

Finalize recruitment, power or precision planning, consent materials, and analysis plans through the applicable university study process. Use expert findings to resolve serious content problems before affected videos reach students, while documenting which version the expert study evaluated and which students receive.

Freeze or version the pipeline and intervention policy for the user study. Conduct the planned comparative evaluation and report engagement, learning, usability, and other outcomes separately, including uncertainty and null findings. Relate expert quality findings to the user experience where appropriate without treating expert scores as proof of student benefit.

### Reserve component comparisons and extra sensing for later work

If the whole system shows promise, later studies can isolate personalization, feedback, or video style. Camera sensing can also be tested for added value beyond app logs, brief reports, and learning responses. These extensions are not prerequisites for the confirmed expert and user studies.

## Sources

The links below identify the literature used in this synthesis. In-text citations place evidence beside the claims it supports; these entries provide a consolidated reading list.

1. Fredricks, J. A., Blumenfeld, P. C., and Paris, A. H. (2004). [School Engagement: Potential of the Concept, State of the Evidence](https://doi.org/10.3102/00346543074001059). *Review of Educational Research*. Foundational multidimensional engagement review.
2. Bergdahl, N., Bond, M., Sjöberg, J., Dougherty, M., and Oxley, E. (2024). [Unpacking student engagement in higher education learning analytics: a systematic review](https://doi.org/10.1186/s41239-024-00493-y). *International Journal of Educational Technology in Higher Education*. Review of engagement constructs and measures.
3. Reeve, J., and Tseng, C.-M. (2011). [Agency as a fourth aspect of students' engagement during learning activities](https://doi.org/10.1016/j.cedpsych.2011.05.002). *Contemporary Educational Psychology*. Agentic engagement.
4. Guo, P. J., Kim, J., and Rubin, R. (2014). [How Video Production Affects Student Engagement: An Empirical Study of MOOC Videos](https://juhokim.com/files/LAS2014-Engagement.pdf). *ACM Learning at Scale*. Large observational video study.
5. Szpunar, K. K., Khan, N. Y., and Schacter, D. L. (2013). [Interpolated memory tests reduce mind wandering and improve learning of online lectures](https://doi.org/10.1073/pnas.1221764110). *PNAS*. Experimental retrieval intervention.
6. Chi, M. T. H., and Wylie, R. (2014). [The ICAP Framework: Linking Cognitive Engagement to Active Learning Outcomes](https://doi.org/10.1080/00461520.2014.965823). *Educational Psychologist*. Cognitive engagement framework.
7. Bisra, K., Liu, Q., Nesbit, J. C., Salimi, F., and Winne, P. H. (2018). [Inducing Self-Explanation: a Meta-Analysis](https://doi.org/10.1007/s10648-018-9434-x). *Educational Psychology Review*. Learning effects of explanation prompts.
8. Guo, L. (2022). [Using metacognitive prompts to enhance self-regulated learning and learning outcomes](https://doi.org/10.1111/jcal.12650). *Journal of Computer Assisted Learning*. Meta-analysis of experimental studies in computer-based environments.
9. Wisniewski, B., Zierer, K., and Hattie, J. (2020). [The Power of Feedback Revisited: A Meta-Analysis of Educational Feedback Research](https://doi.org/10.3389/fpsyg.2019.03087). *Frontiers in Psychology*. Feedback effectiveness and heterogeneity.
10. Kizilcec, R. F., Pérez-Sanagustín, M., and Maldonado, J. J. (2016). [Recommending Self-Regulated Learning Strategies Does Not Improve Performance in a MOOC](https://rene.kizilcec.com/wp-content/uploads/2016/02/kizilcec2016recommending.pdf). *ACM Learning at Scale*. Randomized study with null persistence and achievement findings.
11. Kizilcec, R. F., Pérez-Sanagustín, M., and Maldonado, J. J. (2017). [Self-regulated learning strategies predict learner behavior and goal attainment in Massive Open Online Courses](https://www.rene.kizilcec.com/wp-content/uploads/2016/11/kizilcec2017srl.pdf). *Computers & Education*. Observational evidence about study strategies.
12. Kaliisa, R., Misiejuk, K., López-Pernas, S., Khalil, M., and Saqr, M. (2024). [Have Learning Analytics Dashboards Lived Up to the Hype?](https://doi.org/10.1145/3636555.3636884). *ACM Learning Analytics and Knowledge*. Systematic review of dashboard impacts.
13. Giorgashvili, T., et al. (2025). [From Reflection to Action: A Controlled Field Study on How Learners Interpret and Respond to Feedback in Learning Analytics Dashboards](https://doi.org/10.1111/jcal.70073). *Journal of Computer Assisted Learning*. Analysis of learner reflection and intended changes.
14. Gestiardi, R., and Yuniawatika (2026). [Learning analytics dashboards in Internet-enabled higher education: A meta-analysis of effects on student outcomes, self-regulated learning, and engagement](https://doi.org/10.1016/j.iheduc.2026.101119). *The Internet and Higher Education*. Journal pre-proof available online 7 October 2026.
15. Seli, P., Wammes, J. D., Risko, E. F., and Smilek, D. (2016). [On the relation between motivation and retention in educational contexts: The role of intentional and unintentional mind wandering](https://pubmed.ncbi.nlm.nih.gov/26585116/). *Psychonomic Bulletin & Review*. Distinctions in mind-wandering during learning.
16. D'Mello, S., Lehman, B., Pekrun, R., and Graesser, A. (2014). [Confusion can be beneficial for learning](https://doi.org/10.1016/j.learninstruc.2012.05.003). *Learning and Instruction*. Confusion and its regulation.
17. Krafka, K., et al. (2016). [Eye Tracking for Everyone](https://openaccess.thecvf.com/content_cvpr_2016/html/Krafka_Eye_Tracking_for_CVPR_2016_paper.html). *CVPR*. Commodity-device gaze estimation.
18. Valliappan, N., et al. (2020). [Accelerating eye movement research via accurate and affordable smartphone eye tracking](https://pmc.ncbi.nlm.nih.gov/articles/PMC7486382/). *Nature Communications*. Smartphone gaze validation and operating conditions.
19. Barrett, L. F., Adolphs, R., Marsella, S., Martinez, A. M., and Pollak, S. D. (2019). [Emotional Expressions Reconsidered: Challenges to Inferring Emotion From Human Facial Movements](https://pubmed.ncbi.nlm.nih.gov/31313636/). *Psychological Science in the Public Interest*. Limits of facial emotion inference.
20. Theophilus, G., Eke, C. I., Agushaka, J. O., and Liman, M. M. (2026). [A systematic review of deep learning techniques for learners' engagement prediction in electronic learning systems](https://doi.org/10.1007/s44163-026-01761-8). *Discover Artificial Intelligence*. Engagement-prediction approaches and generalization limitations.
21. DAiSEE project. [Dataset for Affective States in E-Environments](https://people.iith.ac.in/vineethnb/resources/daisee/index.html). Dataset documentation and annotation description.
22. Wang, R., et al. (2014). [StudentLife: Assessing Mental Health, Academic Performance and Behavioral Trends of College Students using Smartphones](https://users.ece.utexas.edu/~ethomaz/courses/asr/papers/health/student-life.pdf). *UbiComp*. Longitudinal smartphone sensing.
23. Hattie, J., and Timperley, H. (2007). [The Power of Feedback](https://doi.org/10.3102/003465430298487). *Review of Educational Research*. Feedback theory and evidence.
24. Panadero, E. (2017). [A Review of Self-regulated Learning: Six Models and Four Directions for Research](https://doi.org/10.3389/fpsyg.2017.00422). *Frontiers in Psychology*. Planning, monitoring, and reflection frameworks.
25. Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., and Willingham, D. T. (2013). [Improving Students' Learning With Effective Learning Techniques](https://pubmed.ncbi.nlm.nih.gov/26173288/). *Psychological Science in the Public Interest*. Review of study strategies, including retrieval and distributed practice.
26. Yang, C., Zhao, W., Yuan, B., Luo, L., and Shanks, D. R. (2023; first published online 2022). [Mind the Gap Between Comprehension and Metacomprehension: Meta-Analysis of Metacomprehension Accuracy and Intervention Effectiveness](https://doi.org/10.3102/00346543221094083). *Review of Educational Research*. Text-comprehension monitoring and intervention evidence.
27. Nahum-Shani, I., et al. (2018). [Just-in-Time Adaptive Interventions in Mobile Health: Key Components and Design Principles for Ongoing Health Behavior Support](https://pubmed.ncbi.nlm.nih.gov/27663578/). *Annals of Behavioral Medicine*. Adaptive intervention design framework.
28. Stothart, C., Mitchum, A., and Yehnert, C. (2015). [The attentional cost of receiving a cell phone notification](https://carystothart.com/publications/attentional-cost-cell-phone-notification/). *Journal of Experimental Psychology: Human Perception and Performance*. Experimental evidence on notification interruption.
29. Dixson, M. D. (2015). [Measuring Student Engagement in the Online Course: The Online Student Engagement Scale](https://olj.onlinelearningconsortium.org/index.php/olj/article/view/561). *Online Learning*. Course-level engagement instrument.
30. O'Brien, H. L., Cairns, P., and Hall, M. (2018). [A practical approach to measuring user engagement with the refined user engagement scale and new UES short form](https://pure.york.ac.uk/portal/en/publications/a-practical-approach-to-measuring-user-engagement-with-the-refine/). *International Journal of Human-Computer Studies*. Digital user-experience engagement instrument.
31. React Native. [AppState](https://reactnative.dev/docs/appstate.html). Official documentation for app state and focus events.
32. Google. [YouTube IFrame Player API](https://developers.google.com/youtube/iframe_api_reference). Official documentation for embedded playback events and state.
33. Android Developers. [UsageStatsManager](https://developer.android.com/reference/android/app/usage/UsageStatsManager). Official documentation for device usage statistics and access requirements.
34. Apple Developer. [Requesting the Family Controls entitlement](https://developer.apple.com/documentation/FamilyControls/requesting-the-family-controls-entitlement). Official documentation for Screen Time-related distribution capability.
35. Leacock, T. L., and Nesbit, J. C. (2007). [A Framework for Evaluating the Quality of Multimedia Learning Resources](https://www.sfu.ca/~jcnesbit/articles/leacocknesbit2007.htm). *Educational Technology and Society*. LORI framework for expert evaluation of learning resources.
36. Koo, T. K., and Li, M. Y. (2016). [A Guideline of Selecting and Reporting Intraclass Correlation Coefficients for Reliability Research](https://pmc.ncbi.nlm.nih.gov/articles/PMC4913118/). *Journal of Chiropractic Medicine*. Selection and reporting of ICC forms; see the [2017 correction](https://pmc.ncbi.nlm.nih.gov/articles/PMC5731844/) to Table 3.
