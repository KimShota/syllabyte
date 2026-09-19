"""
Shared Pydantic schemas used across every stage of the Week-1 pipeline:

    ingest -> extract_kus -> write_script (+critique) -> tts -> animate -> assemble

Every stage reads/writes these types to/from JSON under runs/<run_id>/, so the
CLI can resume from any stage (see run_store.py).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
VisualKind = Literal["title", "bullets", "equation", "plot", "diagram", "code", "compare"]


class VisualSpec(BaseModel):
    kind: VisualKind
    # Free-form payload interpreted by animation_agent.manim_prompt /
    # animation_agent.templates depending on `kind`. Kept loose here so the
    # script-writing LLM call isn't constrained to a rigid per-kind schema;
    # manim_codegen.py and templates.py validate the fields they need.
    title: str | None = None
    bullets: list[str] | None = None
    equation_latex: str | None = None
    plot_description: str | None = None
    diagram_description: str | None = None
    code_snippet: str | None = None
    compare_left: str | None = None
    compare_right: str | None = None


class Segment(BaseModel):
    phase: Phase
    narration: str
    visual: VisualSpec
    source_refs: list[SlideRef] = Field(default_factory=list, min_length=1)


class Script(BaseModel):
    ku_id: str
    title: str
    segments: list[Segment]

    @property
    def word_count(self) -> int:
        return sum(len(seg.narration.split()) for seg in self.segments)

    @property
    def full_narration(self) -> str:
        return " ".join(seg.narration for seg in self.segments)


class CritiqueScore(BaseModel):
    pedagogical_coherence: int = Field(ge=0, le=10)
    conceptual_accuracy: int = Field(ge=0, le=10)
    learner_appropriateness: int = Field(ge=0, le=10)
    issues: list[str] = Field(default_factory=list)

    @property
    def min_score(self) -> int:
        return min(
            self.pedagogical_coherence,
            self.conceptual_accuracy,
            self.learner_appropriateness,
        )


class CritiqueResult(BaseModel):
    ku_id: str
    rounds: list[CritiqueScore] = Field(default_factory=list)
    passed: bool = False


# --------------------------------------------------------------------------
# Stage 4/5 — TTS + Animation
# --------------------------------------------------------------------------

RenderTier = Literal["llm_first_try", "llm_repaired", "llm_regenerated", "template_fallback"]


class SegmentAudio(BaseModel):
    segment_index: int
    wav_path: str
    duration_seconds: float
    srt_start: float
    srt_end: float


class RenderResult(BaseModel):
    segment_index: int
    tier: RenderTier
    attempts: int
    render_seconds: float
    video_path: str | None = None
    error: str | None = None


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
