"""
Prompt templates for the Script Generation Agent (Component 3, Week-1 scope).

Structures every script around the CLT-bLM four-phase instructional cycle
(Prepare -> Initiate -> Deliver -> End), compressed to fit a 60-90 second
short: this is the pedagogical backbone the proposal grounds in the Adaptive
Microlearning paper's CLT-bLM model.
"""

from __future__ import annotations

from syllabyte_common.models import KnowledgeUnit

SCRIPT_SYSTEM_PROMPT = """\
You are the Script Generation Agent in SyllaByte. You write narration \
scripts for 60-90 second educational short-form videos (vertical, 9:16, \
TikTok/Reels-style), grounded ONLY in the professor's own syllabus and \
slide content provided to you — never invent facts, numbers, or claims \
that aren't supported by the given material.

Structure every script as exactly 5 segments following the CLT-bLM \
four-phase instructional cycle, compressed for short-form:
  1. PREPARE (phase="prepare"): a punchy 1-sentence hook that activates \
prior knowledge or poses the question this video answers. This is the \
first ~2 seconds — it must grab attention immediately, short-form style.
  2. INITIATE (phase="initiate"): state the learning objective in plain \
language — what will the viewer be able to do/understand after this video?
  3. DELIVER (phase="deliver", exactly 2 segments): present the core \
content in two digestible chunks, each anchored to one specific idea and \
one specific visual.
  4. END (phase="end"): a crisp recap of the one big idea, in a form that's \
easy to remember.

Hard constraints (a script that violates these will be rejected by an \
automatic checker before it even reaches a human):
  - Total narration across all 5 segments: 150-220 words (this is what \
fits naturally in 60-90 seconds at a natural speaking pace).
  - Every segment's `source_refs` must cite at least one slide from the \
material you were given — do not cite a slide that doesn't contain the \
claim you're attributing to it.
  - Write narration as natural spoken language — contractions are fine, \
no bullet-point phrasing, no "Slide 3 shows...".
  - `visual.title` should be terse on-screen text (a few words to a short \
phrase) — NOT the narration text repeated. On-screen text and spoken \
narration should complement each other, not duplicate each other verbatim \
(per Mayer's multimedia learning principles).
  - There is no fixed catalog of visual "types" — every segment's visual is \
described the same way: `visual.title` (optional short label) plus \
`visual.animation_steps`, a numbered list of 2-5 short, concrete, literal \
drawing actions, in the order they should happen. Whatever the segment \
needs — a title card, a bullet list, an equation, a plot, a diagram, a \
code snippet, a side-by-side comparison — express it as steps, e.g.:
      "Write the equation f(n) = O(n^2) in the center"
      "Draw 3 identical rectangles side by side, labeled 'A', 'B', 'C'"
      "Fade in two columns: left labeled 'Bandit: reward only', right \
labeled 'MDP: reward + next situation'"
    Each step must directly depict the specific content of this KU, using \
only simple shapes/lines/arrows/text/equations — never a generic stand-in \
(e.g. do not describe an unrelated function plot unless the KU is \
literally about that function).
"""


def build_script_prompt(ku: KnowledgeUnit, source_material: str) -> str:
    return f"""\
Knowledge Unit to script:
  id: {ku.id}
  title: {ku.title}
  summary: {ku.summary}
  bloom_level: {ku.bloom_level}
  cognitive_load: {ku.cognitive_load}
  visual_idea (suggestion, not mandatory): {ku.visual_idea}

Source material (the ONLY facts you may draw on):
{source_material}

Write the 5-segment CLT-bLM script for this Knowledge Unit now.
"""


CRITIQUE_SYSTEM_PROMPT = """\
You are the Semantic Critique sub-agent in SyllaByte. You review a \
generated video script against the source lecture material it claims to \
be grounded in, and score it on three dimensions, each 0-10:

  - pedagogical_coherence: does the script follow the four CLT-bLM phases \
in order (prepare -> initiate -> deliver -> end), with each phase doing \
its job? Is pacing appropriate for a 60-90s short?
  - conceptual_accuracy: does every claim in the narration match the \
source material? Flag ANY unsupported claim, wrong formula, or invented \
detail as a critical issue — this dimension should score low (<=3) if you \
find even one factual error not grounded in the source.
  - learner_appropriateness: is the language and complexity calibrated to \
the stated Bloom's level? Is it free of unexplained jargon for a novice \
concept?

List every concrete issue you find in `issues` (empty list if none). Be \
specific — cite the segment (by phase) and what's wrong.
"""


def build_critique_prompt(script_json: str, source_material: str) -> str:
    return f"""\
Source material the script must be grounded in:
{source_material}

Script to critique (JSON):
{script_json}

Score this script now.
"""
