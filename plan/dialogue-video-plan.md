# Dialogue videos: two characters, Gen-Z voice (built 2026-11-04)

An opt-in video style (`--style dialogue`) modelled on the two-character "brainrot" reel format, without the
gameplay background. Two characters talk one KU through at one student's level.
- **Peter** is the explainer.
- **Stewie** is a peer who is learning the idea.

Monologue videos are unchanged and stay the default.

## Pedagogy (sources: `research_notes/dialogue-framework.md`)

- **Video level:** the CLT-bLM four-phase cycle, as in every SyllaByte video.
- **Inside each phase:** the five-step tutoring frame (Graesser, Person & Magliano 1995): question → the peer's
  answer → the explainer's feedback → building the answer together → checking understanding. The student watches
  it as a vicarious tutorial dialogue.
- **Deep questions:** the peer's questions must be deep-level questions (why / how / what if / compare). Craig et
  al. (2006) found that these questions drive the vicarious-learning gain, more than the dialogue format itself.
- **Misconception:** the first deliver segment always contains one. The peer voices it, and the explainer's next
  line refutes it **with an explanation** (Kendeou et al. 2014: the explanation is the active ingredient).
- **Predict line:** one line asks the viewer to pause and predict (Chi et al. 2008 support learners becoming
  constructive observers).
- **Recap:** the peer restates the idea at the end and the explainer sharpens it, as step 5 of the frame.
- **Slang** is delivery, not content (personalization principle; seductive details):
  - only phrases from a reviewed list (`slang.json`), about one per 2–3 lines;
  - never in a definition, formula, objective or recap line, and never in place of a course term;
  - never mocking a wrong answer.
- **Captions** are burned in, 2–4 words at a time, timed to the spoken words. Colour-key terms are drawn in their
  diagram colour (signalling). Captions show exactly the words spoken, which also helps viewers whose first
  language isn't English.

## Format
- **Layout:** Manim animation in the top 70% (4.5 × 5.6 units). The bottom 30% holds the speaking character,
  alone, on their side of the screen, with captions on the other side.
- **Voices:** Kokoro stock voices, `am_michael` for Peter and `bm_george` for Stewie. Not imitations of the
  actors.
- **Length:** 150–250 words, about 70–100 s.

## Where it lives
| Part | File |
|---|---|
| Schema | `syllabyte_common/models.py`: `DialogueBeat` (speaker, step, misconception), `DialogueScript`, `load_script` |
| Cast | `syllabyte_common/cast.py`, `media/characters/cast.json` (gitignored) |
| Prompt | `script_generation_agent/prompts.py`: `dialogue_system_prompt`, `dialogue_critique_system_prompt` |
| Checker | `script_generation_agent/script_writer.py`: `validate_dialogue` |
| Slang | `script_generation_agent/slang.json`, `slang.py` |
| Voices + word timings | `animation_agent/tts.py` |
| 70% frame | `animation_agent/frame.py`, `manim_config.py`, `manim_prompt.py`, `layout.py`, `layout_audit.py` |
| Band | `animation_agent/dialogue_band.py` |
| Pipeline | `scripts/generate_shorts.py` (`make_ku_video(style=)`), `scripts/video_jobs.py --style dialogue` |
| App | `captions_burned_in` on the video, `speaker` on transcript rows; the player hides its caption overlay |

## Deviations from the proposal (state them in the report)
1. **Narration:** two voices instead of one narrator. The proposal describes single-narrator TTS; its future
   work mentions the professor's own voice.
2. **Length:** dialogue videos run up to about 100 s, against the proposal's 60–90 s.
3. **Subjects:** CS and mathematics only, against the proposal's general STEM framing. The reason: Manim draws
   these subjects accurately.
4. **Characters:** the images are copyrighted placeholders (Family Guy) for local testing. Before any use in the
   study or in published demos, clear them with the advisor and the IRB, or replace them with original characters
   (`cast.json` swaps them in one file).
5. **Limitation of the framework:** the five-step frame comes from live, adaptive tutoring. Here it is scripted
   and watched, as in the vicarious-learning studies. Adaptation comes from the student's measured level (L1–L3),
   not from live replies.
