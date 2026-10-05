"""
Learner-facing models for the student UI (see plan/ui-ux-implementation-plan.md §5).

Phase 0 uses these to validate the fixture JSON that `scripts/build_ui_fixtures.py`
writes into apps/web/fixtures/. From Phase 1 the FastAPI layer serves the same
shapes. The TypeScript mirrors live in apps/web/lib/types.ts — keep both in sync.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from syllabyte_common.models import SlideRef

Level = Literal[1, 2, 3]
ItemContext = Literal[
    "onboarding", "checkpoint", "recheck", "next_session", "prove_it", "retention"
]
ReviewStatus = Literal["unreviewed", "approved", "flagged", "hidden"]
TailoringKind = Literal["left_out", "added", "set_to"]
Phase = Literal["prepare", "initiate", "deliver", "end"]


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------


class MCQ(BaseModel):
    """What the LLM writes. The generator adds id / context / refs around it."""

    stem: str
    options: list[str] = Field(min_length=3, max_length=3)
    correct_index: int = Field(ge=0, le=2)
    explanation: str  # one or two sentences, shown after the answer
    hint: str | None = None  # a nudge that does not give the answer away
    difficulty_prior: float = Field(default=0.0, ge=-3, le=3)  # logit scale, 0 = medium


class Item(BaseModel):
    id: str
    ku_id: str | None = None
    topic_id: str
    context: ItemContext
    stem: str
    options: list[str] = Field(min_length=3, max_length=4)
    correct_index: int
    allows_not_sure: bool
    explanation: str
    hint: str | None = None
    difficulty_prior: float = 0.0
    source_refs: list[SlideRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _index_in_range(self) -> "Item":
        if not 0 <= self.correct_index < len(self.options):
            raise ValueError(f"item {self.id}: correct_index out of range")
        return self


# --------------------------------------------------------------------------
# Course structure
# --------------------------------------------------------------------------


class Topic(BaseModel):
    id: str
    title: str
    blurb: str
    ku_ids: list[str]
    first_lecture: int


class Lecture(BaseModel):
    n: int
    title: str
    week: int
    slide_start: int
    slide_end: int


class KuEntry(BaseModel):
    """A Knowledge Unit as the Course map lists it. `video_id` is None while no
    video exists ("Not made yet")."""

    id: str
    title: str
    short_title: str
    topic_id: str
    lecture_n: int
    video_id: str | None = None


class CourseConfig(BaseModel):
    recheck_week: int = 7
    recheck_skip_until_week: int = 9
    recheck_up_threshold: float = 0.8
    recheck_down_threshold: float = 0.4
    recheck_min_answers: int = 3
    playlist_max_videos: int = 6
    playlist_max_seconds: int = 600
    next_session_min_hours: int = 12
    next_session_max_per_visit: int = 2
    next_session_expiry_days: int = 7
    retention_due_days: int = 3
    retention_delay_days: int = 14
    reveal_retention_scores_after_week_14: bool = False
    # Phase 0 only: the fixture has 3 lectures, so pin "the upcoming lecture"
    # instead of deriving it from the clock.
    upcoming_lecture_override: int | None = None


class Course(BaseModel):
    id: str
    code: str
    name: str
    eyebrow: str
    syllabus_summary: str
    config: CourseConfig
    topics: list[Topic]
    lectures: list[Lecture]
    kus: list[KuEntry]


# --------------------------------------------------------------------------
# Videos
# --------------------------------------------------------------------------


class SegmentSpan(BaseModel):
    phase: Phase
    start: float
    end: float


class Checkpoint(BaseModel):
    t: float  # the video pauses here
    rewatch_from: float  # "Rewatch this part" seeks here
    item_id: str


class Claim(BaseModel):
    idx: int
    text: str
    segment_idx: int
    slide_refs: list[SlideRef]
    lecture_clip: str | None = None  # filled once lecture transcription exists


class TailoringSkeleton(BaseModel):
    """What differs at a level. The *why* sentence is filled in per student at
    runtime from their own answers (plan §2 rule 4), never written here."""

    kind: TailoringKind
    what: str
    dimension: Literal["recap", "example", "support"]
    evidence_topic_id: str | None = None


class SentenceFrame(BaseModel):
    template: str  # blanks written as ___
    answers: list[str]  # one model answer per blank, for the author's reference


class TranscriptRow(BaseModel):
    t: float
    narration: str
    visual: str | None = None


class VideoFixture(BaseModel):
    id: str  # == ku_id in Phase 0
    ku_id: str
    title: str
    short_title: str  # what cards, headers and receipts show; the full title is in "About this video"
    topic_id: str
    lecture_n: int
    file_level: Level = 2  # the only version that exists in Phase 0
    duration_s: float
    # Repo-relative source files; `npm run fixtures` copies them to public/.
    video_src: str
    poster_src: str
    vtt_src: str
    video_url: str
    poster_url: str
    vtt_url: str
    segments: list[SegmentSpan]
    checkpoint: Checkpoint
    next_session_item_id: str
    prove_it_item_id: str
    sentence_frame: SentenceFrame
    claims: list[Claim]
    tailoring: dict[str, list[TailoringSkeleton]]  # keys "1" | "2" | "3"
    transcript: list[TranscriptRow]
    source_slides: list[int]
    prerequisite_titles: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = "unreviewed"
