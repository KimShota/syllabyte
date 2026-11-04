# Dialogue script framework: sources checked (2026-11-04)

The dialogue style (`Script.style = "dialogue"`) keeps CLT-bLM as the video-level structure. Inside each phase,
the two characters follow the five-step tutoring frame, delivered as vicarious tutorial dialogue with
deep-level reasoning questions and explanation-based refutation of misconceptions.

Checked against abstracts and citing papers, not the full texts. Read the PDFs linked below before quoting
effect sizes or sample sizes in the report.

## Five-step tutoring frame
Graesser, A. C., Person, N. K., & Magliano, J. P. (1995). Collaborative dialogue patterns in naturalistic
one-to-one tutoring. *Applied Cognitive Psychology, 9*, 495–522.
PDF: https://talkbank.org/class/access/0docs/graesser1995.pdf

- Naturalistic tutoring by unskilled tutors (graduate students tutoring research methods, high-school students
  tutoring 7th-grade algebra).
- Pervasive pattern: (1) tutor asks a question, (2) student answers, (3) tutor gives short feedback on the
  answer's quality, (4) tutor and student collaboratively improve the answer, (5) tutor assesses the student's
  understanding.
- Some papers credit the frame to Graesser & Person (1994). Cite the 1995 paper, which describes it.
- Our adaptation: step 5 is done by the peer restating the idea (the explainer confirms), so the viewer sees
  understanding being checked rather than asked "do you understand?".

## Deep-level reasoning questions in vicarious learning
Craig, S. D., Sullins, J., Witherspoon, A., & Gholson, B. (2006). The deep-level-reasoning-question effect:
The role of dialogue and deep-level-reasoning questions during vicarious learning. *Cognition and
Instruction, 24*(4), 565–591. doi:10.1207/s1532690xci2404_4

- Compared interactive AutoTutor tutoring with vicarious conditions (watching), including dialogue with deep
  questions.
- Deep questions drove the gains; follow-ups found the effect holds when the questions are embedded in
  monologue too. So **the questions matter more than the two-voice format** — the checker requires the
  peer's questions to be deep types, not filler.
- Replicated with 8th–11th graders in computer literacy and Newtonian physics (Gholson et al., 2009,
  *Instructional Science*, doi:10.1007/s11251-008-9069-2).

Deep question types used in the prompt (Graesser & Person question taxonomy): why (causal antecedent / goal),
how (procedural / enablement), what-if (consequence), compare.

## Observing dialogue vs. observing monologue
Chi, M. T. H., Roy, M., & Hausmann, R. G. M. (2008). Observing tutorial dialogues collaboratively: Insights
about human tutoring effectiveness from vicarious learning. *Cognitive Science, 32*(2), 301–341.
doi:10.1080/03640210701863396

- Students who observed tutoring dialogues collaboratively learned physics problem solving as well as the
  tutees themselves.
- Tutoring worked when tutees constructed knowledge (alone or with the tutor), not when the tutor just
  conveyed it. Supports making the peer construct (wrong answer → improved answer → restatement) rather than
  only asking, and the "pause, guess first" prompt to make the viewer active.
- Caveat for the report: their observers watched in pairs. Our viewers watch alone.

## Refutation with explanation
Kendeou, P., & O'Brien, E. J. (2014). The Knowledge Revision Components (KReC) framework: Processes and
mechanisms. In D. N. Rapp & J. L. G. Braasch (Eds.), *Processing inaccurate information* (pp. 353–377).
MIT Press.

Kendeou, P., Walsh, E. K., Smith, E. R., & O'Brien, E. J. (2014). Knowledge revision processes in
refutation texts. *Discourse Processes, 51*(5–6), 374–397. doi:10.1080/0163853X.2014.913961

- KReC: the misconception and the correct idea are co-activated; revision needs the new information to be
  integrated and to compete with the old.
- Experiments: refutation **plus explanation** reduced the old belief's interference; the explanation was the
  key component (explanation alone was about as effective as refutation + explanation).
- Our rule: every correction says what is wrong and explains why the right idea holds, in the explainer's
  very next line. "Nah, that's wrong" alone is rejected by the checker and the critic.

## Limitation to state in the report
The five-step frame describes live, adaptive tutoring. SyllaByte uses it as a scripted dialogue the student
watches, as the vicarious-learning studies did; adaptation comes from the student's measured level (L1–L3),
not from live replies.
