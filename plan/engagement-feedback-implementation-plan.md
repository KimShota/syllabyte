# Engagement measurement and personalized feedback implementation plan

Date: 14 November 2026  
Status: Proposed implementation, informed by repository inspection  
Primary surface: Expo mobile app  
Research basis: [Literature review and feature design](../research_notes/engagement-measurement-and-personalized-feedback.md)

## Implementation status (14 November 2026, branch engagement-measurement, uncommitted)

The first milestone (end of this plan) is built for the mobile feed: watch → answer and confidence → optional reflection (difficulty, attention) → one evidence-linked card → replay or continue → session reflection page after the last video.

- Core: `logic/playback.ts` (PlaybackMeter, interval union), `learning.ts` (types, `learningFeedback` rules v1), `api/learning.ts` (`recordLearningPlayback`, `postLearningCheckIn`, `recordLearningFeedbackAction`, `getLearningReflection`). Completion is 90% unique coverage of one source; real and stand-in ("demo") playback never add up. Checkpoint answers carry an `attemptId` and are idempotent. Calibration block 1 states counts only. Replay alone no longer queues a refresher.
- Playback saves use `mutateQuietly` (store) and are exempt from the remote client's refetch, so screens don't refetch every 5 s; the server runner saves on quiet changes too. Screens are woken when a save completes a video or a page stops playing.
- Mobile: `usePlayback` feeds the meter (also from the stand-in clock), `useLearningPlayback` saves every 5 s and on leaving, `QuickCheck` retries without duplicating, `LearningFeedback` is an optional check-in after a checkpoint. The session reflection is no longer a page: see "Automatic feedback" below.
- Tests: `packages/core/tests/learning.test.ts`, plus an HTTP test in `apps/server/tests/rpc.test.ts`.

### Automatic feedback (built 14 November 2026)

Students never open a reflection page; the app decides when to offer support, in the sense of a just-in-time adaptive intervention (Nahum-Shani et al., 2018): decision points, tailoring variables, intervention options, rules, and "no prompt" as the default. Policy `drift-1` in `packages/core/src/logic/engagementDrift.ts`; every number is a pilot starting point, versioned in the data.

| Decision point | Rule | What the student sees |
|---|---|---|
| Moving to the next video | Drift: 3 videos in a row left before half-way, or two of {2 such videos, 2 absences of 15 s+ within 10 min, 2 of the last 3 checks wrong}. Only evidence since the last prompt counts; at most 2 per session, 5 min apart | The observation in plain words ("You moved on early from the last 3 videos"), "where was your attention?" (on the videos / something else / familiar / searching; Seli et al., 2016). Drifted or familiar: recall the last video really watched, then compare with its key points (`claims`; Szpunar et al., 2013) → continue / rewatch it / take a break |
| Returning to the app after 60 s to 10 min, partway through a video | Welcome back, at most 2 per session | "Welcome back. You were 0:45 into X." Recall the last idea, then compare with the key points up to there → continue / replay from that point |
| Returning after 10 min or more | The session ends (reason `gap`); a new one starts | The ended session's reflection |
| Leaving the feed | The session ends (reason `left`) | The reflection, as a sheet over whatever screen comes next |
| Next app open after closing it | Sessions idle for 10 min end when the app next asks (`getPendingReflection`) | The latest ended session's reflection ("Your last session") |
| Feed open, app in front, video paused for any length of time | Keep-alive about once a minute (`keepLearningSessionOpen`), so the session never ends as idle; if it ended anyway (no keep-alive got through for 10 min), the feed starts a new session | Nothing until they leave |

The reflection is one observation and one next step, and only when there is something to say (an answer, a finished video, or a reported drift). Observation priority: certain + wrong, wrong, right while unsure (2+), drift, all right, finished. Shown once; dismissing it also clears older ones. The swipe-to reflection page is removed.

Playback saves, absences, prompts and prompt responses are quiet writes (no refetch). Writes nobody waits on (prompt answers and actions, absences, ending a session, dismissing a reflection, a page's last playback save) go through a stored outbox on the phone (`apps/mobile/src/state/outbox.ts`): network and server failures are retried with backoff and on returning to the app, refused writes are dropped, at most 200 are kept, and sign-out clears it. All of them are idempotent on the server (absences carry the phone's id). This is not yet the research event queue of phase 1. A decision point waits for the page left behind to finish saving (`apps/mobile/src/components/player/learningSync.ts`), so the server decides on everything the student did.

### Misconception clips (in progress, branch misconception-videos)

When a checkpoint answer is wrong and the student chose "Certain" (no hint), a short clip is made on demand that addresses that misconception: the peer voices the wrong idea, the explainer shows why it fails and what is right (refutation: Schroeder & Kucera, 2022, g = 0.41; in video: Muller et al., 2008; high-confidence errors are the most correctable: Metcalfe, 2017; wrong + certain signals a misconception rather than a gap: Hasan et al., 1999).

- **Generated on demand, cached per misconception.** The key is the question plus the wrong option chosen. The first student who makes that mistake triggers a `misconception` job; later students with the same mistake get the cached clip at once. Cost grows with the misconceptions students actually show.
- **The immediate correction stays.** The checkpoint card still shows the right answer, the explanation and the "certain but wrong" card at once; the clip is a deeper follow-up.
- **Shown when ready, never mid-video.** The video pipeline makes a video in about 1 to 1.5 minutes. The app checks for ready clips; when one is ready it pops up at once, unless a video is playing, in which case it waits until that video ends (or the student moves on). Options: watch now or later; "later" offers it again at the next chance.
- **A follow-up question** from the clip's own generated questions, after watching, records whether the correction worked.
- **Quality:** no human sees a clip before its first viewing, so it goes through the pipeline's own checks against the slides; a failed job leaves the student with the existing replay and explanation. Cached clips are flagged for expert review afterwards.

The API names differ from the "Proposed API operations" table below. Research events (phase 1, in part): each phone event carries `event_id` and `occurred_at`, made when it happened; the queue (`createEventQueue`) keeps events in storage until the server acknowledges their ids, retries with a growing delay, and keeps at most 500 (overflow counted); the server stores an event once per id, sets `received_at`, times the event by its age on the phone's clock (`sent_at - occurred_at`, so a wrong phone clock cancels out; an impossible age is flagged `clock_anomaly`), marks events from older phones `legacy`, refuses events over 4 KB, and stores phone events only while consent is "research", checked on arrival, so a packet after withdrawal restores nothing. Events the server logs inside API calls still follow the demo `flags.log_declined` switch (on by default), so decliners' API events are stored, though the research export leaves them out: a decision for the study protocol. Not built yet: sequence numbers and session ids on every event, later retrieval and future-learning judgments in the feed (phase 5), research exports and feature flags (phase 6). Native playback callbacks have not yet been exercised on a device.

## Objective and scope

Add an engagement-support feature to SyllaByte that observes learning behavior, collects occasional brief reports, and provides evidence-linked feedback with an immediate learning action. Help students recognize attention lapses, conceptual difficulty, and mismatches between confidence and understanding.

The broader research question remains whether the entire personalized video-learning system improves engagement and learning. This plan implements one component of that system; expert and user study protocols are separate work.

The first release includes reliable playback observations, short check-ins, three feedback paths, session reflection, and later retrieval. It uses transparent rules and course-grounded content. Camera sensing, ambient audio, device-wide tracking, a global engagement score, and LLM classification of students' mental states are outside this release.

Retrieval, explanation, and metacognitive prompting have research support. The exact trigger combinations, thresholds, wording, and interface below are proposed design choices. Pilot and version them rather than presenting them as scientifically established cutoffs.

## Current implementation and gaps

| Area | Existing implementation | Required work |
|---|---|---|
| Mobile player | [usePlayback.ts](../apps/mobile/src/components/player/usePlayback.ts) uses expo-video and a synthetic playback clock when there is no video file | Capture actual playback intervals and transitions; identify real versus synthetic media; separate requested play state from observed playback |
| Completion | [PlayerPage.tsx](../apps/mobile/src/components/player/PlayerPage.tsx) calls markWatched after position reaches 90 percent of duration | Compute unique coverage; seeking alone must not satisfy the threshold |
| Event meanings | [mock.ts](../packages/core/src/api/mock.ts) emits video_ended from markWatched | Separate actual player end from crossing the coverage threshold; version the changed meaning |
| Confidence | [QuickCheck.tsx](../apps/mobile/src/components/player/QuickCheck.tsx) collects answer then confidence before showing the result | Reuse the sequence; add attempt identity, robust submission state, feedback evidence, and timing |
| Self-reports and recall | Core API supports difficulty, future-learning judgments, explanations, calibration, and next-session tasks | These methods are not currently referenced by the inspected mobile source; add the intended mobile surfaces rather than assuming they are already exposed |
| Event delivery | [remote.ts](../packages/core/src/api/remote.ts) batches UI events in memory with bounded retries | Persist a bounded queue; preserve occurrence time; acknowledge and deduplicate events |
| Event ingestion | [events.ts](../packages/core/src/events.ts) sends UI events without client event IDs or occurrence timestamps; [runner.ts](../apps/server/src/runner.ts) recreates events when received | Retain occurrence time and identity, add receipt time, validate payloads, and preserve account/course scope |
| Session lifecycle | [app.ts](../apps/mobile/src/state/app.ts) starts a new visit on return from background | Introduce a learning-session identifier independent of visit so brief interruptions do not reset feedback limits |
| Replay logic | [engagement.ts](../packages/core/src/logic/engagement.ts) and [playlist.ts](../packages/core/src/logic/playlist.ts) use repeated views to help flag refresher content | Remove replay alone as evidence that material was not understood |
| Calibration | [calibration.ts](../packages/core/src/logic/calibration.ts) can default to saying confidence matches results well | Replace unsupported conclusions with descriptive counts and insufficient-evidence states |
| Persistence | [state.ts](../apps/server/src/state.ts) splits profile and course documents | Store learning sessions and support decisions by course; keep preferences at profile level; migrate old state with defaults |
| Research export | [app.ts](../apps/server/src/app.ts) exposes questionnaire CSV; allStates selects one course per student | Add a dedicated, authorized engagement export covering the intended courses and retaining event and decision provenance |

The app uses Expo SDK 58. Implementation must use the matching [expo-video documentation](https://docs.expo.dev/versions/v58.0.0/sdk/video/) and installed types. App focus behavior must follow [React Native AppState documentation](https://reactnative.dev/docs/appstate). No new native dependency is planned.

## Student experience

1. The student starts or resumes a learning session. Playback and learning events are recorded without additional taps.
2. The existing checkpoint collects an answer and confidence. Ordinary correctness feedback appears as it does now.
3. At a suitable boundary, an optional brief check-in can clarify difficulty or attention. It never competes with an open checkpoint.
4. One contextual feedback card gives the observation, a short interpretation within the evidence, an available action, and Continue or Not now.
5. At the end of the feed, a reflection summarizes demonstrated understanding and one chosen next action. Leaving early saves a summary for later access without blocking navigation.
6. An eligible later-retrieval card checks the relevant concept and, if collected, compares the earlier future-learning judgment with the new result.

Preserve the existing mandatory checkpoint policy for this feature's initial integration. New engagement check-ins and support offers are optional. Changing checkpoint requirements would be a separate product/protocol change.

## Proposed measurement contract

### Learning session

A learning session starts when a real learning activity begins, not when an off-screen feed item mounts. It has an ID independent of login session and visit, and is scoped to a user and course. Brief backgrounding closes active intervals but retains the learning session. An explicit finish, course change, or a sufficiently long gap closes it.

Proposed pilot gap: 10 minutes without a learning activity. Store this in versioned policy configuration. It defines a session boundary, not a psychological attention threshold. On process restart, recover persisted state and either resume or finalize it using the same rule; never invent activity during the missing interval.

Keep durations for video playback, questions, check-ins, and other learning screens separate. Label foreground exposure as such; do not call it focused time.

### Event envelope

Extend the existing event channel with:

- event_id: generated once at occurrence and stable across retries.
- schema_version and policy_version where relevant.
- occurred_at: device wall time for sequencing across sessions.
- received_at: server receipt time, assigned by the server.
- session_id and playback_instance_id where applicable.
- sequence and elapsed_ms from a monotonic clock within a playback/session instance.
- course_id, knowledge-unit ID, video/content version, item ID, and served level where applicable.
- source: real playback, synthetic demo, or legacy event.
- event-specific payload, with explicit reasons for system-triggered transitions.

The server supplies authenticated identity and study condition; do not trust client claims for either. Validate course membership and object ownership. Never silently reassign a delayed event to a different active course. Record clock anomalies and use elapsed time for durations; an incorrect device wall clock must not create negative viewing durations.

Legacy events lacking these fields remain readable, marked as legacy. Do not fabricate precise historical coverage or attention from them.

### Playback observations

Observe play, pause, seek, rate change, end, readiness/loading changes, page visibility, route focus, and app activity. Use actual media progress and status; neither a requested play state nor ready status alone proves content advanced.

Build intervals while the relevant page is active and visible, the route is focused, playback is actually advancing, and no blocking overlay obscures the content. Close or split intervals at seeks, pauses, rate changes, checkpoints, app-state changes, source changes, and unmount. Native status updates and progress stalls should prevent counting buffering. Unsupported or ambiguous periods are unknown, not assumed playback.

Use the existing player updates locally; do not upload every 250 ms tick. Aggregate interval observations, persist at boundaries and a bounded checkpoint interval, and batch transport. A proposed local persistence interval is 5 seconds; record truncation if a crash loses an unfinished tail.

Derived quantities:

- Unique coverage = length of the union of observed content intervals / video duration.
- Content exposure = summed traversed content seconds, including replay.
- Elapsed playback = observed wall duration, which differs from content exposure at non-default speeds.
- Replay exposure = content traversed again after an earlier observed exposure.
- Backward seek count = navigation behavior, distinct from actually replaying that content.
- Resume position = last known position, separate from maximum reached position and coverage.

Persist interval unions so revisits can contribute to coverage without double-counting. Keep coverage per content version. Preserve the current 90 percent completion threshold initially, but apply it to unique coverage and record the policy version. Actual player end has its own event. Define a completed viewing instance so duplicate events and repeated crossings do not inflate views or create duplicate recall tasks.

If background audio or picture-in-picture is supported, classify it separately. Exclude synthetic demo playback from research aggregates. A lack of touches during video playback is not inactivity.

### Student reports

Add a versioned check-in record: ID, session, concept/video, prompt type, shown time, answered time, response or explicit skip, and trigger source.

| Type | Proposed prompt and options | Use |
|---|---|---|
| Attention | Just before this prompt, what were you thinking about? Video / Thinking through the idea / Something unrelated / Something around me / Skip | Offer a recovery choice when unrelated thoughts are reported |
| Difficulty | How did that explanation feel? Easy / Manageable / Difficult / Skip | Combine with task evidence before recommending support |
| Interest | How interested were you in this example? Low / Somewhat / Very / Skip | Secondary descriptive input; challenge adaptation can follow later |
| Interruption reason | Were you checking course material, interrupted, or taking a break? Include Resume without answering | Clarify a relevant interruption without guessing its cause |

Map difficulty to the existing Difficulty type where semantics match. Retain timestamped records; the existing latest-value map is insufficient for session histories. Do not silently overwrite the meaning of legacy values.

Proposed pilot budget: at most two automatic engagement check-ins and two automatic support offers per learning session; no more than one automatic check-in per video; at least five minutes between automatic check-ins. Inline correctness feedback and voluntary requests for help are separate. Prioritize a relevant difficulty check after an error over routine interest sampling. Store actual shown and skipped events and keep the budget across brief backgrounding.

These limits are engineering starting points to reduce burden, not literature-derived optima. An attention response obtained after a long delay describes the moment asked about; never backfill it as continuous attention for the preceding session.

## Feedback rules and available actions

Implement a pure rule function in a proposed core module, taking a typed evidence snapshot and returning a decision or no decision. Do not label a student globally engaged or disengaged.

| Rule | Required evidence | Example wording | Initial executable action |
|---|---|---|---|
| confidence_mismatch | Current incorrect answer with confidence recorded as certain before revelation | You were certain about this answer. Compare your reasoning with the explanation, then revisit the key step. | Show the existing item explanation and replay from checkpoint.rewatch_from |
| difficulty_support | Incorrect response plus a difficult rating for the same concept and current session | You said this explanation was difficult, and this question needs another check. Review the example one step at a time. | Open a verified source explanation or replay the mapped segment; offer a hint only when available |
| attention_recovery | Explicit report of unrelated thoughts or environmental distraction | You said your attention drifted. Choose a recap, a question, or a pause. | Replay the mapped segment; offer an available non-repeated item; or pause and preserve the place |
| review_acknowledgment | Observed replay plus a correct response | You revisited the example and answered this question correctly. Continue or try another example. | Continue; offer another item only if available |
| no_decision | Replay alone, missing responses, conflicting timing, or insufficient evidence | No psychological interpretation | Continue normally; optional check-in if budget allows |

Do not call a correct multiple-choice answer a correct explanation or proof of mastery. Identify a particular misconception only when the answer/explanation content supports it. If both difficulty_support and confidence_mismatch apply, show one combined card with both observations, not two alerts. Following an attention-recovery choice, wait for the next learning boundary before offering academic remediation.

Initially use existing item explanations and mapped replay locations. A promise of a simpler generated video, new worked trace, prerequisite resource, or alternate question requires an actual available resource. Resolve action targets before showing the card. If no fresh item exists, offer replay and continue; never relabel a previously revealed answer as a new mastery check.

Later extensions can add low-interest-plus-success challenges and longer-term calibration patterns. They are not prerequisites for the three initial feedback paths.

### Decision and action lifecycle

Persist a decision ID, rule/version, evidence IDs, evidence summary, available actions and targets, creation time, and status. Separate generated, shown, accepted, dismissed, action started, action completed, expired, and follow-up observed.

A button tap records acceptance. Completion comes from the destination action: for example, the target segment actually played or a new question was submitted. Opening the destination is not completion. A dismissed decision is not reoffered for the same evidence. New evidence can produce a new decision subject to the session budget.

Do not display stale feedback after a concept or source version changes. Link any later result to its evidence and assistance, and report the sequence without claiming the advice caused improvement.

## Shared logic storage and API

### Proposed modules

- packages/core/src/logic/playbackCoverage.ts: interval merging and exposure derivation.
- packages/core/src/logic/learningSession.ts: session lifecycle and prompt budgets.
- packages/core/src/logic/engagementFeedback.ts: decision rules and evidence selection.
- packages/core/src/logic/sessionReflection.ts: factual session summary.
- packages/core/src/content/engagementFeedback.ts: versioned prompts and message templates.
- apps/mobile/src/state/engagement.ts: player observations, session coordination, durable local records, and sync.
- apps/mobile/src/components/player/EngagementCheckIn.tsx and EngagementFeedbackCard.tsx: optional student interactions.
- apps/mobile/src/components/SessionReflection.tsx and NextSessionReview.tsx: session and later-review surfaces.

These paths are proposed new files. Keep platform APIs in mobile, pure calculations in core, and authenticated persistence in the server.

### State model

Add a versioned per-course engagement branch to DemoState containing sessions, aggregate coverage, check-ins, feedback decisions, action records, and reflection references. Keep global enable/snooze preferences at profile level. Update freshState, local hydration, server default merging, export, and deletion paths. Inspect nested defaults explicitly; a shallow object merge does not migrate a partially populated new branch.

Operational personalization must not depend on the research-event array, which is suppressed for research decliners. Store the minimal functional state needed to provide support separately from consent-gated research telemetry. Preserve the ability to learn without research participation. Reuse existing data-rights behavior and document what happens when support is disabled, research consent is withdrawn, or account data is deleted.

### Proposed API operations

Extend the existing shared Api and mockApi, which also execute on the server, rather than introducing a separate service:

| Proposed operation | Responsibility |
|---|---|
| submitEngagementContext(input) | Validate and idempotently save new session observations/check-ins, then evaluate a boundary using persisted response evidence |
| respondToEngagementFeedback(input) | Record a decision action or dismissal once and return the valid action target |
| getSessionReflection(sessionId) | Return evidence-backed summary and next action without creating new decisions |
| finishLearningSession(input) | Finalize the session once and save a reflection reference |

Inputs include expected course and stable command IDs. Extend checkpoint submission with a stable attempt/command ID and recorded confidence timing so retrying a request cannot duplicate an answer or recommendation. Existing next-session and difficulty APIs can be extended/reused rather than duplicated.

Boundary evaluation must not depend on an asynchronous analytics batch happening to arrive first. submitEngagementContext includes the bounded new operational observations and commits them before evaluating rules. Research telemetry mirrors these observations through the consent-gated channel. Reference the same IDs to avoid double ingestion. Server-side task correctness comes from trusted item data and saved responses, not a client-supplied correct flag.

For per-course RPCs, check expected course against the loaded course and reject a mismatch explicitly; the client must not retry an old operation into the new course. Course-tagged telemetry and background session finalization need an authorized persistence path for the originating course. Implement this alongside server course loading, not by changing an event label after writing state into the wrong document.

The mobile client may calculate provisional exposure locally. Use the same core rules for local demo mode and server-backed mode. In remote mode, no new server-backed learning action is reported as saved until acknowledged. Persist pending telemetry/context safely, show an honest retry state when needed, and leave playback/navigation usable. This release does not require making the entire remote learning API offline-capable.

### Reliable delivery

Extend createEventQueue with a storage adapter so core remains platform-independent; use AsyncStorage on mobile. Scope queued data to authenticated account and consent generation. Persist before transmission, retain unacknowledged events, retry with bounded backoff, and acknowledge IDs rather than assuming an accepted count identifies every event.

Deduplicate ingestion with a persisted uniqueness mechanism, such as a table keyed by user and event ID written in the same transaction as event persistence. Bound storage and surface overflow or truncation as data-quality information. Sign-out clears or securely detaches the current user's queue; withdrawal clears queued research data and the server checks current consent so late packets cannot restore deleted research records.

Validate event types and payload sizes in the existing /api/events route. Legacy clients can retain their old contract temporarily, but must not enter the new high-quality measurement cohort without the required event schema.

## Mobile integration

Use VideoFeed as the coordinator for the active concept, learning session, and natural boundaries. Feed visibility alone is insufficient: include route focus and app activity. Ensure mounted neighboring pages cannot emit active exposure or prompts.

Extend QuickCheck's result area with the relevant feedback card rather than stacking a second modal. Persist the submitted answer and confidence together, disable changes while submission is pending, and provide a retry path that retains the same attempt ID. The current sent ref prevents repeated submissions but needs explicit handling when a request fails.

Show a difficulty check in the result/transition area when useful, attention at selected natural boundaries, and other check-ins within the shared budget. New overlays must close playback intervals, report their own cause, and restore the correct playback state. A pause caused by the app's checkpoint is not a student interruption.

Use the existing VideoFeed end slot for session reflection. Add access to the latest reflection from an appropriate existing course/home surface so leaving a feed early does not lose it. Do not require a new dashboard tab for the first release.

Wire existing getNextSession and answerNextSession logic to a mobile review card. Add an optional future-learning judgment after the relevant video completion, ensuring a task exists before associating the judgment. Keep the current scheduling configuration initially. Link concept, video/content version, actual follow-up delay, assistance, and response. Avoid showing the answer before the recall attempt.

## Phased delivery and acceptance checks

| Phase | Deliverable | Acceptance checks |
|---|---|---|
| 1. Contracts and reliable state | Event envelope, session model, operational/research separation, storage migration, idempotency and transport | Retried packets/commands create one record; occurrence time survives delayed upload; old states load; accounts/courses remain isolated; withdrawal blocks late research packets |
| 2. Accurate observations | Playback interval tracking, coverage, lifecycle causes, completion semantics | Seeking to the end does not complete a video; replay does not double unique coverage; 2× changes elapsed time correctly; buffering/background/hidden pages do not count as foreground exposure; synthetic media is excluded |
| 3. Check-ins and confidence | Optional reports, prompt budget, robust checkpoint submission, calibration correction | No new prompt blocks learning; budgets survive brief backgrounding; confidence precedes revelation; failure/retry does not duplicate a response; missing evidence yields no confident interpretation |
| 4. Feedback and actions | Three initial paths plus productive-review handling, templates, decisions and action lifecycle | Each card references real evidence; no broken/imaginary action; replay alone causes no remediation; only one applicable card appears; dismissals stick; engagement never changes ability directly |
| 5. Reflection and recall | Session summary, later access, optional future judgment, next-session review | Summary counts match saved records; actual delay is available; unavailable recall items are handled honestly; reused questions are identified; no unsupported mastery/calibration claims |
| 6. Exports and pilot readiness | Authorized engagement exports, feature/policy version flags, mobile validation, complete sample session | A consenting test participant's full observation→feedback→action→follow-up path can be reconstructed; decliners are excluded from research exports; iOS and Android flows pass |

Phases 1–4 form the first useful vertical slice. Phases 5–6 make the feature suitable for the intended pilot. Avoid starting the main user study with partially instrumented behavior whose event meaning changes mid-study.

## Research export and policy controls

Provide researcher-only exports for sessions/coverage, check-ins, feedback/action histories, and confidence/follow-up links. Include pseudonymous participant, condition, course, source IDs, actual served level, occurrence/receipt times, schema/policy/content versions, missingness, and synthetic/legacy flags. Keep open-text explanations out of default telemetry exports unless intentionally included under the study's data design.

Export all relevant authorized course documents; the existing allStates helper alone selects one active/recent course and is insufficient for complete multi-course histories. Extend the student's own data download and deletion paths to cover the new records too.

Use feature flags for collection and support display and a separately versioned prompt-sampling policy. This allows the wider user-study condition to control which features are delivered. Do not create a new feedback-only experiment or assign new conditions in this implementation.

## Verification plan

Add meaningful tests for interval unions and seek discontinuities, session boundaries and cooldowns, rule conflicts and insufficient evidence, retries and duplicate commands, cross-account/course isolation, old-state migrations, and consent/deletion behavior. Cover API persistence and response provenance with server tests, not only snapshots of message strings.

For modified packages, run the established scripts:

- packages/core: npm run typecheck and npm test.
- apps/server: npm run typecheck and npm test.
- apps/mobile: npm run lint, npm run typecheck, and npm test.

Also typecheck the web consumer after shared Api/type changes and run relevant existing tests. Exercise actual devices or emulators for player callbacks, route transitions, app backgrounding, Android notification-drawer focus, buffering, and overlay interaction; pure unit tests cannot establish native playback behavior.

Use a scripted session with known playback intervals, one confident error, one difficult rating, one attention-drift report, a dismissed offer, a completed action, a temporary connection failure, and a later recall response. Inspect both the student display and exported rows. Keep the test participant and synthetic data distinguishable from study participants.

## First implementation milestone

Start with the data/session contract and playback measurement fixes, then deliver this sequence for one real video:

> Watch → answer and confidence → optional difficulty report → one evidence-linked card → working replay/explanation action → saved reflection

This verifies the central behavior before adding broader personal patterns. Exact UI copy and budgets can then be refined through a short undergraduate usability pilot, while the broader expert and user studies retain their whole-system purpose.
