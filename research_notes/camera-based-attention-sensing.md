# Camera-based attention sensing in SyllaByte

Date: 14 November 2026  
Status: Research synthesis and proposed future design. **Not built, and not part of the pilot.**  
Builds on: [Engagement measurement and personalized feedback](engagement-measurement-and-personalized-feedback.md) (section "Phone sensors and their limits") and the [implementation plan](../plan/engagement-feedback-implementation-plan.md) (section "Automatic feedback").

This note answers one question: if SyllaByte added front-camera sensing to its engagement feedback, what would it measure, how would the data be analysed, and what feedback would students get, when and how? Every design choice below cites the study it rests on. Where the evidence runs out, the note says so.

## Bottom line

Camera sensing is technically feasible on a phone and is not computationally prohibitive when processing stays on the device at a low frame rate. But camera-based detectors of mind wandering are only moderately accurate: F1 of about 0.39 to 0.59 against chance of about 0.24, and lower in live use than offline. The design therefore keeps the principle of the current system: **the camera decides when to ask, never what is true about the student.** A camera signal can trigger a question, a pause or a retrieval prompt, all of which are useful whatever the student's real state. It never produces a label such as "bored" or "disengaged".

The camera should be added only after a staged evaluation (data collection with thought probes, then a live accuracy check, then a comparison with the current non-camera rules), and only as a separate opt-in with its own consent.

## 1. What would be measured

All values are computed on the phone from the front camera, at a few frames per second, only while a video is playing. Each frame is discarded as soon as its features are extracted. Only derived numbers are kept.

| Measure | Definition | Evidence linking it to attention |
|---|---|---|
| Face present and head direction | Whether a face is visible; head yaw and pitch. A **look-away** is the face absent, or the head turned well away from the screen, for at least N seconds while the video plays | Gaze Tutor treated gaze leaving the screen as disengagement and responded by redirecting attention (D'Mello et al., 2012). Head pose is among the facial features that predicted mind wandering (Bosch & D'Mello, 2021) |
| Gaze on the video | A coarse estimate of whether the eyes are on the video area, plus fixation and saccade statistics per window | Gaze features detected mind wandering during learning in classrooms (Hutt et al., 2019) and during computerized reading (Faber et al., 2018). A plain webcam with WebGazer was accurate enough to predict task-unrelated thought and comprehension after one calibration (Hutt et al., 2024). Smartphone gaze reached about 0.6 to 1 degree of visual angle at 25 to 40 cm with calibration (Valliappan et al., 2020) |
| Blink rate | Blinks per minute per window | People blinked more during mind wandering while reading (Smilek et al., 2010). The study had 15 participants, so blink rate is only one model input, never a trigger on its own |
| Facial movement features | Action-unit intensities, used only as inputs to a model | A student-independent face-only detector found mind wandering during film comprehension (Stewart et al., 2017). Facial video predicted mind wandering during online lectures (Lee et al., 2022) |

**Not measured, deliberately:**

- **Pupil size.** The pupil responds mainly to light. A video's own brightness changes continuously, so luminance would swamp any effect of mental effort; ordinary front cameras without infrared add further noise (Mathôt, 2018).
- **Emotion labels** (bored, confused, frustrated). Facial movements do not map reliably onto specific emotions across contexts (Barrett et al., 2019). A 2026 review of engagement-prediction models found heavy reliance on facial information and limited generalization (Theophilus et al., 2026, cited in the parent note).
- **Raw video or images, and identity.** Nothing that identifies the student leaves the feature extractor.

## 2. How the data would be analysed

1. **On-device feature extraction.** Google's face mesh and iris model track iris and pupil landmarks from a single RGB camera in real time, at over 50 frames per second on modern phones (Ablavatski et al., 2020; MediaPipe Iris). On iPhones, Apple's Vision and ARKit face tracking are the equivalent (ARKit gaze needs a TrueDepth camera). Features are summarised over short windows of video, for example 10 to 30 seconds, as in the detection studies above.
2. **Ground truth from thought probes.** Occasionally during a video, the app asks "Just before this, where was your attention?" Probe-caught mind wandering is the standard label in this literature; Weinstein (2018) reviews the many probe formats. The existing drift question already separates deliberate from unintended mind wandering (Seli et al., 2016). Probe answers become the training labels.
3. **A student-independent model.** Train a classifier on probe-labelled windows and evaluate it on held-out students (leave-one-student-out), as Hutt et al. (2019), Faber et al. (2018) and Stewart et al. (2017) did. Report F1 and AUC against the chance baseline given the base rate of mind wandering. Choose the decision threshold for a low false-alarm rate, because every false alarm interrupts a student who was paying attention.
4. **Expect lower accuracy in live use.** Hutt et al. (2019) reported F1 of 0.59 offline but 0.40 live, with chance at 0.24. Stewart et al. (2017) reported F1 of 0.39 for face-only detection. The model output is therefore treated as a probability, not a fact.
5. **Fuse with the signals the app already has.** In lecture-video viewing, eye tracking and face video were each more predictive than physiology, and combining them worked best (Bühler et al., 2024). In classrooms, multimodal fusion helped only in limited circumstances (Hutt et al., 2019). So the camera probability enters the existing drift rule (`packages/core/src/logic/engagementDrift.ts`) as **one more signal**, alongside early leaves, absences and checkpoint errors, and its added value is tested rather than assumed.
6. **Missing data means no prompt.** No face, poor lighting or an unusual phone angle produces no prompt and is recorded as missing, never as disengagement. Faber et al. (2018) found that predicting probabilistically for windows with poor or missing gaze beat discarding them for measurement; for **triggering feedback** this design is more conservative and simply does not act.

## 3. What feedback, when and how

| Situation | When | What the student sees | Evidence |
|---|---|---|---|
| Look-away: face absent or head turned away for at least N seconds while the video plays | Immediately | The video pauses at the same place: "Paused while you looked away." Options: resume, or replay the last 15 seconds | Gaze Tutor's gaze-reactive dialogue redirected attention and improved learning on deep-reasoning questions, with little effect on motivation (D'Mello et al., 2012). The message only describes what happened and keeps the student's place |
| Likely mind wandering: model probability above threshold **and** at least one other drift signal | At the end of the current segment of the video, never mid-sentence | "In one sentence, what did this part show?" Then the video's own key point (its `claims`). If the answer did not match, replay the segment | Eye-Mind Reader asked students to self-explain after detected mind wandering and prompted re-reading when the explanation was weak; comprehension was better a week later, though not immediately (Mills et al., 2021). Gaze-based attention-aware interventions re-engaged high-school students in classrooms; learning was not tested (Hutt et al., 2021). Short retrieval tests between segments reduce mind wandering and improve learning (Szpunar et al., 2013) |
| Repeated over a session | In the automatic session-end reflection | Only what the camera directly observed, for example "The video was paused 4 times while you looked away." Never an inferred state | The existing rule of describing what happened rather than judging the student (Barrett et al., 2019) |

The existing safeguards from the automatic-feedback design apply unchanged: at most 2 automatic prompts of each kind per session, at least 5 minutes apart, every step skippable, and only evidence gathered since the previous prompt counts, so a dismissed prompt is not repeated for the same reason. The idea of a learning technology that senses and responds to attention in real time is set out by D'Mello (2016).

## 4. Consent and privacy

- **A separate opt-in** for the camera, with the app fully usable without it, a visible indicator while it is on, and an off switch available at any time.
- **An amendment to the study's ethics approval**, since continuous face capture is biometric processing.
- **On-device processing only**; raw video is never stored or transmitted; only the derived features in section 1 are kept, under the same consent rules as other research telemetry.
- Camera-based monitoring of students raises documented concerns about surveillance, privacy, autonomy and trust (Coghlan et al., 2021, on online exam proctoring). These are design requirements, not afterthoughts: the camera must serve the student's learning, never grading or compliance.

## 5. Staged evaluation

1. **Data collection only.** Thought probes plus camera features, with no camera-triggered feedback. Build and evaluate the model offline (section 2).
2. **Live detection check.** Live accuracy; false-alarm rate, measured by students answering "I was on the video" after a camera-triggered prompt; share of time with missing data; battery and heat on target phones.
3. **Incremental value.** Compare the drift rule with and without camera input: whether help comes earlier, the share of false prompts, recall or quiz results, and burden. This is the comparison the parent note already recommends ("compare a model using behavior and check-ins with the same model plus camera features").

Camera-triggered feedback should reach students only after stages 1 and 2 show acceptable accuracy and burden on the target phones.

## 6. Engineering cost

- **Not possible in Expo Go.** It needs a development build with a camera frame-processing library and a face-tracking model (MediaPipe Face Landmarker and Iris on Android; Vision or ARKit on iOS).
- **Battery and heat** from running the camera alongside video decoding for a whole session. No figures are available for SyllaByte's case; this must be measured on the target phones.
- **Device coverage.** Lower-end Android phones may not sustain the frame rate; ARKit gaze needs an iPhone with a TrueDepth camera.
- **Data model.** New per-window feature records, a camera-consent flag, and a policy version, following the same quiet-save, outbox and consent-gated research-event paths as the existing engagement data.

## 7. Where the evidence runs out

- **No study found tested this on phones during short educational videos.** The evidence comes from laptop webcams and eye trackers, in labs and classrooms, during reading, film and lecture video. Zhao et al. (2017) found webcam-based detection during MOOC lecture videos feasible, but with 13 participants.
- **Detection accuracy is modest**, with F1 of about 0.39 to 0.59 against chance of about 0.24, and it drops in live use.
- **Evidence that camera-triggered feedback improves learning is limited:** delayed comprehension in Mills et al. (2021) and deep-reasoning questions in D'Mello et al. (2012). Hutt et al. (2021) measured attention only.
- **Blink evidence rests on a small sample** (15 participants in Smilek et al., 2010).
- **Smartphone gaze accuracy.** Valliappan et al. (2020) reported 0.6 to 1 degree at 25 to 40 cm with calibration and favourable conditions. The parent note quotes a 0.46 cm figure from the same paper; check that figure against the full text before citing it.

## Sources

Verified for this note on 14 November 2026 (bibliographic details and main findings; full texts were not all read):

1. Bosch, N., and D'Mello, S. K. (2021). Automatic detection of mind wandering from video in the lab and in the classroom. *IEEE Transactions on Affective Computing*, 12(4), 974–988. https://doi.org/10.1109/TAFFC.2019.2908837 ([dblp](https://dblp.uni-trier.de/rec/journals/taffco/BoschD21.html))
2. Hutt, S., Krasich, K., Mills, C., Bosch, N., White, S., Brockmole, J. R., and D'Mello, S. K. (2019). Automated gaze-based mind wandering detection during computerized learning in classrooms. *User Modeling and User-Adapted Interaction*, 29(4), 821–867. https://doi.org/10.1007/s11257-019-09228-5
3. Hutt, S., Krasich, K., Brockmole, J. R., and D'Mello, S. K. (2021). Breaking out of the lab: Mitigating mind wandering with gaze-based attention-aware technology in classrooms. *CHI 2021*. [Author copy](https://par.nsf.gov/servlets/purl/10284389)
4. D'Mello, S., Olney, A., Williams, C., and Hays, P. (2012). Gaze tutor: A gaze-reactive intelligent tutoring system. *International Journal of Human-Computer Studies*, 70(5), 377–398. https://doi.org/10.1016/j.ijhcs.2012.01.004
5. Stewart, A., Bosch, N., Chen, H., Donnelly, P. J., and D'Mello, S. K. (2017). Face forward: Detecting mind wandering from video during narrative film comprehension. *AIED 2017*, LNCS 10331, 359–370. https://doi.org/10.1007/978-3-319-61425-0_30
6. Smilek, D., Carriere, J. S. A., and Cheyne, J. A. (2010). Out of mind, out of sight: Eye blinking as indicator and embodiment of mind wandering. *Psychological Science*. https://doi.org/10.1177/0956797610368063
7. Mathôt, S. (2018). Pupillometry: Psychology, physiology, and function. *Journal of Cognition*, 1(1). https://doi.org/10.5334/joc.18
8. Hutt, S., Wong, A., Papoutsaki, A., Baker, R. S., Gold, J. I., and Mills, C. (2024). Webcam-based eye tracking to detect mind wandering and comprehension errors. *Behavior Research Methods*, 56(1), 1–17. https://doi.org/10.3758/s13428-022-02040-x
9. Mills, C., Gregg, J., Bixler, R., and D'Mello, S. K. (2021). Eye-Mind reader: An intelligent reading interface that promotes long-term comprehension by detecting and responding to mind wandering. *Human–Computer Interaction*, 36(4). https://doi.org/10.1080/07370024.2020.1716762
10. Faber, M., Bixler, R., and D'Mello, S. K. (2018). An automated behavioral measure of mind wandering during computerized reading. *Behavior Research Methods*, 50(1), 134–150. https://doi.org/10.3758/s13428-017-0857-y
11. Ablavatski, A., et al. (2020). Real-time pupil tracking from monocular video for digital puppetry. Google Research preprint. [arXiv:2006.11341](https://arxiv.org/abs/2006.11341); [MediaPipe Iris](https://research.google/blog/mediapipe-iris-real-time-iris-tracking-depth-estimation/)
12. Valliappan, N., et al. (2020). Accelerating eye movement research via accurate and affordable smartphone eye tracking. *Nature Communications*, 11, 4553. https://doi.org/10.1038/s41467-020-18360-5
13. D'Mello, S. K. (2016). Giving eyesight to the blind: Towards attention-aware AIED. *International Journal of Artificial Intelligence in Education*, 26(2), 645–659. https://doi.org/10.1007/s40593-016-0104-1
14. Weinstein, Y. (2018). Mind-wandering, how do I measure thee with probes? Let me count the ways. *Behavior Research Methods*, 50(2), 642–661. https://doi.org/10.3758/s13428-017-0891-9
15. Lee, T., et al. (2022). Predicting mind-wandering with facial videos in online lectures. *CVPR Workshops 2022*. [Open access](https://openaccess.thecvf.com/content/CVPR2022W/CVPM/html/Lee_Predicting_Mind-Wandering_With_Facial_Videos_in_Online_Lectures_CVPRW_2022_paper.html)
16. Bühler, B., et al. (2024). Detecting aware and unaware mind wandering during lecture viewing (eye tracking, facial video and physiological signals; N = 87). *ICMI 2024*. [Record](https://portal.fis.tum.de/en/publications/detecting-aware-and-unaware-mind-wandering-during-lecture-viewing/)
17. Zhao, Y., et al. (2017). Webcam-based versus eye-tracker mind-wandering detection while watching MOOC lecture videos (N = 13). *EC-TEL 2017*. [PDF](https://chauff.github.io/documents/publications/ectel2017-zhao.pdf)
18. Coghlan, S., Miller, T., and Paterson, J. (2021). Good proctor or "Big Brother"? Ethics of online exam supervision technologies. *Philosophy & Technology*, 34(4), 1581–1606. https://doi.org/10.1007/s13347-021-00476-1

Cited from the parent note: Barrett et al. (2019), Seli et al. (2016), Szpunar et al. (2013), Theophilus et al. (2026), Krafka et al. (2016); see its Sources list.
