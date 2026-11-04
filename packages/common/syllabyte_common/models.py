"""
Shared Pydantic schemas used across every stage of the Week-1 pipeline:

    ingest -> extract_kus -> write_script (+critique) -> tts -> animate -> assemble

Every stage reads/writes these types to/from JSON under runs/<run_id>/, so the
CLI can resume from any stage (see run_store.py).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------
# Stage 1 — Ingestion (syllabus + slide decks -> CourseCorpus)
# --------------------------------------------------------------------------


class Slide(BaseModel):
    deck_name: str
    slide_number: int  # 1-indexed
    text: str
    notes: str = ""
    image_path: str | None = None  # PNG rendered from the slide, if available


class SlideDeck(BaseModel):
    name: str
    source_path: str
    slides: list[Slide] = Field(default_factory=list)
    has_images: bool = False  # False when parsed from a PPTX with no LibreOffice available


class CourseCorpus(BaseModel):
    course_name: str
    syllabus_path: str
    syllabus_text: str
    decks: list[SlideDeck] = Field(default_factory=list)

    def slide_by_ref(self, deck_name: str, slide_number: int) -> Slide | None:
        for deck in self.decks:
            if deck.name == deck_name:
                for slide in deck.slides:
                    if slide.slide_number == slide_number:
                        return slide
        return None


# --------------------------------------------------------------------------
# Stage 2 — Curriculum Alignment (Knowledge Unit extraction)
# --------------------------------------------------------------------------

BloomLevel = Literal[
    "remember", "understand", "apply", "analyze", "evaluate", "create"
]


class SlideRef(BaseModel):
    deck_name: str
    slide_number: int


class KnowledgeUnit(BaseModel):
    id: str  # short slug, e.g. "ku-gradient-descent"
    title: str
    summary: str
    bloom_level: BloomLevel
    cognitive_load: Literal["low", "medium", "high"]
    prerequisites: list[str] = Field(default_factory=list)  # other KU ids
    source_refs: list[SlideRef] = Field(default_factory=list)
    visual_idea: str  # 1-sentence idea for how this KU could be visualized
    short_worthiness: int = Field(ge=1, le=5)
    short_worthiness_reason: str


class KUList(BaseModel):
    knowledge_units: list[KnowledgeUnit]


# --------------------------------------------------------------------------
# Stage 3 — Script Generation
# --------------------------------------------------------------------------

Phase = Literal["prepare", "initiate", "deliver", "end"]


class Beat(BaseModel):
    """One spoken sentence paired with the one visual action shown while it
    is spoken — Code2Video's lecture_lines[i] <-> animations[i] pairing
    (github.com/showlab/Code2Video). Each beat is synthesized to its own
    audio clip (tts.py), and the scene pads each beat's animations to that
    clip's exact end time (layout.GridLayoutScene.end_beat), so visual N is
    on screen while sentence N is being said."""
    narration: str
    visual: str


class Segment(BaseModel):
    phase: Phase
    beats: list[Beat] = Field(min_length=1)
    source_refs: list[SlideRef] = Field(default_factory=list, min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy(cls, data: Any) -> Any:
        """Loads pre-beat script.json files (one `narration` paragraph + a
        `visual.animation_steps` list with no per-sentence pairing) as a
        single beat, so old runs still load in report.py."""
        if isinstance(data, dict) and "beats" not in data and "narration" in data:
            data = dict(data)
            steps = (data.pop("visual", None) or {}).get("animation_steps", [])
            data["beats"] = [{"narration": data.pop("narration"), "visual": "; ".join(steps)}]
        return data

    @property
    def narration(self) -> str:
        return " ".join(beat.narration for beat in self.beats)


# Manim colour constants that read well on the black background (no dark _D/_E shades). WHITE stays for neutral text.
KeyColour = Literal["BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PURPLE", "TEAL", "PINK", "GOLD"]


class TermColour(BaseModel):
    """One thing the video shows repeatedly (a group, a quantity) and the one colour it has in every segment."""

    term: str
    colour: KeyColour


class Script(BaseModel):
    ku_id: str
    title: str
    segments: list[Segment]
    # The video's colour key: every segment's animation is written separately, so without it the same thing can change
    # colour between segments (plan/per-student-video-plan.md). Empty for scripts written before it existed.
    colour_key: list[TermColour] = Field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(len(seg.narration.split()) for seg in self.segments)

    @property
    def full_narration(self) -> str:
        return " ".join(seg.narration for seg in self.segments)


# --------------------------------------------------------------------------
# Dialogue scripts (research_notes/dialogue-framework.md)
#
# Two characters talk the idea through: an explainer and a peer who is learning it, like the viewer. Inside each
# CLT-bLM phase the beats follow the five-step tutoring frame (Graesser, Person & Magliano 1995): question ->
# the peer's answer -> the explainer's feedback -> building the answer together -> checking understanding. These
# are subclasses, so the monologue schema the writer fills in is unchanged, and every stage that takes a Script
# takes a DialogueScript too.
# --------------------------------------------------------------------------

Speaker = Literal["explainer", "peer"]

# question:  a deep question (why / how / what-if / compare) about the idea
# answer:    the peer's first answer: partial, or a misconception (then `misconception` is true)
# feedback:  the explainer says what is right or wrong in the answer and explains why
# build:     the two work toward the full answer, one step per beat
# predict:   a line to the viewer: guess before the answer is shown
# check:     the peer restates the idea in their own words; the explainer confirms or sharpens it
# objective: the explainer states what the viewer will be able to do (the initiate phase)
TutorStep = Literal["question", "answer", "feedback", "build", "predict", "check", "objective"]


class DialogueBeat(Beat):
    speaker: Speaker
    step: TutorStep
    # True when this line voices a wrong idea. The explainer's next line corrects it, with the reason.
    misconception: bool


class DialogueSegment(Segment):
    beats: list[DialogueBeat] = Field(min_length=1)


class DialogueScript(Script):
    segments: list[DialogueSegment]
    style: Literal["dialogue"]


# A dialogue whose lines are drawn with the visual template library (plan/visual-template-library-plan.md):
# each beat also lists the template calls that draw it (animation_agent/visuals). Subclasses again, so the
# schema the writer fills in without templates is unchanged.


class TemplatedDialogueBeat(DialogueBeat):
    # Calls on the visual templates that draw this line, e.g. 'arr.bisect_check(target=9)'. [] keeps the
    # picture as it is. A segment whose beats all have [] is drawn by LLM-written code from `visual`, as before.
    draw: list[str]


class TemplatedDialogueSegment(DialogueSegment):
    beats: list[TemplatedDialogueBeat] = Field(min_length=1)
    # How the segment is drawn: "templates" (its calls, after what earlier segments left on screen) or "code"
    # (LLM-written Manim from each beat's `visual`). None in scripts written before storyboards: templates when
    # any beat has calls.
    drawn: Literal["templates", "code"] | None = None

    @property
    def drawn_by(self) -> str:
        return self.drawn or ("templates" if any(b.draw for b in self.beats) else "code")


class TemplatedDialogueScript(DialogueScript):
    segments: list[TemplatedDialogueSegment]
    visuals: Literal["templates"]


def load_script(json_text: str) -> Script:
    """A script.json as the class it was written as: a DialogueScript when it says so, else a Script."""
    import json

    data = json.loads(json_text)
    schema: type[Script] = Script
    if isinstance(data, dict) and data.get("style") == "dialogue":
        schema = TemplatedDialogueScript if data.get("visuals") == "templates" else DialogueScript
    return schema.model_validate(data)


# The part of the 9:16 frame Manim draws: all of it, or the top 70% when a dialogue band sits underneath.
FrameName = Literal["full", "dialogue"]


class RenderBeat(Beat):
    # A line's template calls (TemplatedDialogueBeat.draw), kept for the renderer; [] for scripts without them.
    draw: list[str] = Field(default_factory=list)


class RenderSegment(Segment):
    """A segment as the animation stage sees it: with the video's colour key, so every codegen and repair prompt
    carries it and a changed key invalidates the segment's render cache, and with the frame it is drawn in."""

    beats: list[RenderBeat] = Field(min_length=1)
    colour_key: list[TermColour] = Field(default_factory=list)
    frame: FrameName = "full"
    # Drawn from template calls (TemplatedDialogueSegment.drawn_by), after replaying `carried`: every call of the
    # template segments before it, so the picture continues from where the last segment ended.
    templates: bool = False
    carried: list[str] = Field(default_factory=list)


class CritiqueScore(BaseModel):
    pedagogical_coherence: int = Field(ge=0, le=10)
    conceptual_accuracy: int = Field(ge=0, le=10)
    learner_appropriateness: int = Field(ge=0, le=10)
    # None only for critiques written before this dimension existed.
    visual_alignment: int | None = Field(default=None, ge=0, le=10)
    issues: list[str] = Field(default_factory=list)

    @property
    def min_score(self) -> int:
        scores = [
            self.pedagogical_coherence,
            self.conceptual_accuracy,
            self.learner_appropriateness,
        ]
        if self.visual_alignment is not None:
            scores.append(self.visual_alignment)
        return min(scores)


class CritiqueResult(BaseModel):
    ku_id: str
    rounds: list[CritiqueScore] = Field(default_factory=list)
    passed: bool = False


# --------------------------------------------------------------------------
# Stage 4/5 — TTS + Animation
# --------------------------------------------------------------------------

# spec_template: drawn from the script's template calls (animation_agent/visuals), no LLM code.
RenderTier = Literal["spec_template", "llm_first_try", "llm_repaired", "llm_regenerated", "template_fallback"]


class WordTiming(BaseModel):
    word: str
    start: float
    end: float


class SegmentAudio(BaseModel):
    segment_index: int
    wav_path: str
    duration_seconds: float
    srt_start: float
    srt_end: float
    # Per-beat durations (sum == duration_seconds); empty for pre-beat runs.
    beat_durations: list[float] = Field(default_factory=list)
    # Per beat, each spoken word with its start and end in seconds from the start of that beat (the burned-in
    # captions of dialogue videos follow them). Empty when the backend gives no word timings.
    beat_words: list[list[WordTiming]] = Field(default_factory=list)


class RenderResult(BaseModel):
    segment_index: int
    tier: RenderTier
    attempts: int
    render_seconds: float
    video_path: str | None = None
    error: str | None = None
    # Visual Critic (Code2Video-inspired grid-anchored layout pass, run once
    # after any successful LLM-tier render — see animation_agent/visual_critic.py).
    visual_repair_applied: bool = False
    visual_issues_remaining: list[str] = Field(default_factory=list)
    # Plugin names (`module.Name`, see animation_agent/plugins.py) the final scene imports, and
    # every one any attempt imported: which plugins get used, and which keep failing.
    plugins_used: list[str] = Field(default_factory=list)
    plugins_tried: list[str] = Field(default_factory=list)
    # Why a segment with template calls was drawn by LLM code instead (its calls failed to render).
    spec_fallback_reason: str | None = None


# Thin list wrappers so scripts/generate_shorts.py can round-trip
# per-segment lists through RunDir.save_json/load_json (which take a single
# BaseModel) without reaching for a separate TypeAdapter call site.
class SegmentAudioList(BaseModel):
    items: list[SegmentAudio]


class RenderResultList(BaseModel):
    items: list[RenderResult]


# --------------------------------------------------------------------------
# Stage 7 — Run manifest (cost / time accounting for the report)
# --------------------------------------------------------------------------


class LLMCallRecord(BaseModel):
    stage: str  # e.g. "extract_kus", "write_script", "critique", "manim_codegen"
    ku_id: str | None = None
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    wall_seconds: float = 0.0


class RunManifest(BaseModel):
    run_id: str
    course_name: str | None = None
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)

    def total_cost_usd(self, price_per_mtok: dict[str, tuple[float, float]]) -> float:
        """price_per_mtok maps model -> (input_$_per_mtok, output_$_per_mtok)."""
        total = 0.0
        for call in self.llm_calls:
            in_price, out_price = price_per_mtok.get(call.model, (0.0, 0.0))
            total += (call.input_tokens / 1_000_000) * in_price
            total += (call.output_tokens / 1_000_000) * out_price
            # Cache reads are ~10% of input price; cache writes ~1.25x.
            total += (call.cache_read_tokens / 1_000_000) * in_price * 0.1
            total += (call.cache_creation_tokens / 1_000_000) * in_price * 1.25
        return total
