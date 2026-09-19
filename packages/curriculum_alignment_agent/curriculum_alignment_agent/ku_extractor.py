"""
Knowledge Unit (KU) extraction — Component 1 (Curriculum Alignment Agent),
Week-1 scope.

One Claude call per slide deck: the syllabus text (for course-level context)
plus the *entire deck as a PDF document block* (so the model sees diagrams,
equations, and layout — not just a text dump) produces a KUList. Each KU
must be scoped to a single 60-90s short and must cite the slide(s) it came
from — that's the grounding contract the rest of the pipeline relies on.

Note: this only works for decks parsed from (or converted to) a PDF, since
the model needs the actual deck file, not just extracted text. A PPTX deck
with no LibreOffice available still gets a KU pass using its extracted text
via corpus.syllabus_text-style context (see `_deck_text_only_prompt`), just
without the visual grounding a PDF document block provides.
"""

from __future__ import annotations

from pathlib import Path

from syllabyte_common.llm import DEFAULT_MODEL, pdf_block, structured, text_block
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, KUList, RunManifest, SlideDeck

SYSTEM_PROMPT = """\
You are the Curriculum Alignment Agent in SyllaByte, a system that turns a \
professor's own course materials into short (60-90 second) educational \
videos. You will be given a course syllabus and one lecture slide deck \
(as a PDF, so you can see diagrams, equations, and layout).

Your job: extract a set of Knowledge Units (KUs) from this deck. A Knowledge \
Unit is a single, self-contained teachable concept that:
  - Can be fully explained in a 60-90 second narrated video (roughly \
150-220 spoken words) — NOT a whole lecture's worth of material. If a topic \
needs more than that, split it into multiple narrower KUs.
  - Cites the specific slide number(s) in THIS deck that it draws from. \
Every KU must have at least one source_refs entry with this deck's name.
  - Is tagged with the Bloom's Taxonomy level the syllabus/slides are \
teaching it at (remember/understand/apply/analyze/evaluate/create).
  - Has a cognitive_load rating (low/medium/high) per Cognitive Load Theory \
— how much intrinsic complexity a novice must hold in working memory.
  - Lists prerequisites as OTHER Knowledge Unit ids from this same deck, \
if any (use ids you invent consistently, e.g. "ku-big-o-definition").
  - Has a one-sentence visual_idea: a concrete idea for how to visualize \
this concept (e.g. "animate a growing input size n next to a bar chart of \
operation counts for O(n) vs O(n^2)").
  - Has a short_worthiness score 1-5 (5 = ideal short-form video material: \
visual, self-contained, high pedagogical value) with a one-sentence reason.

Extract as many well-scoped KUs as the deck naturally supports — do not pad \
with filler or slice a concept into implausibly small pieces just to add \
more.\
"""


def extract_kus_from_deck(
    corpus: CourseCorpus,
    deck: SlideDeck,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> KUList:
    context = (
        f"Course: {corpus.course_name}\n\n"
        f"=== SYLLABUS ===\n{corpus.syllabus_text}\n\n"
        f"=== DECK '{deck.name}' ===\n"
        "The full deck is attached below as a PDF. Extract Knowledge Units "
        f"from it, citing deck_name='{deck.name}' in every source_refs entry."
    )

    if deck.has_images and Path(deck.source_path).suffix.lower() == ".pdf":
        content = [pdf_block(deck.source_path, cache=False), text_block(context)]
    elif deck.has_images:
        # PPTX that was successfully converted to PDF for images has a
        # different source_path than the rendered PDF, so fall back to text.
        content = [text_block(context + "\n\n" + _deck_as_text(deck))]
    else:
        content = [text_block(context + "\n\n" + _deck_as_text(deck))]

    return structured(
        schema=KUList,
        content=content,
        system=SYSTEM_PROMPT,
        stage="extract_kus",
        model=model,
        max_tokens=16000,
        manifest=manifest,
    )


def _deck_as_text(deck: SlideDeck) -> str:
    parts = [f"[Note: no rendered slide images available for this deck — text only.]"]
    for slide in deck.slides:
        parts.append(f"--- Slide {slide.slide_number} ---\n{slide.text}")
        if slide.notes:
            parts.append(f"(speaker notes: {slide.notes})")
    return "\n".join(parts)


def extract_kus(
    corpus: CourseCorpus, *, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None
) -> KUList:
    """Extract KUs from every deck in the corpus and merge into one list."""
    all_kus: list[KnowledgeUnit] = []
    for deck in corpus.decks:
        result = extract_kus_from_deck(corpus, deck, model=model, manifest=manifest)
        all_kus.extend(result.knowledge_units)
    return KUList(knowledge_units=all_kus)


def select_kus(kus: KUList, n: int) -> list[KnowledgeUnit]:
    """Rank by short_worthiness (desc) and return the top n."""
    ranked = sorted(kus.knowledge_units, key=lambda k: k.short_worthiness, reverse=True)
    return ranked[:n]


if __name__ == "__main__":
    import argparse

    from syllabyte_common.models import CourseCorpus as _Corpus

    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, help="Path to corpus.json")
    parser.add_argument("--out", required=True, help="Path to write kus.json")
    args = parser.parse_args()

    corpus = _Corpus.model_validate_json(Path(args.corpus).read_text())
    manifest = RunManifest(run_id="cli")
    kus = extract_kus(corpus, manifest=manifest)

    Path(args.out).write_text(kus.model_dump_json(indent=2))
    print(f"Extracted {len(kus.knowledge_units)} KUs -> {args.out}")
    for ku in kus.knowledge_units:
        print(f"  [{ku.short_worthiness}/5] {ku.id}: {ku.title} ({ku.bloom_level})")
    if manifest.llm_calls:
        call = manifest.llm_calls[0]
        print(f"tokens: input={call.input_tokens} output={call.output_tokens}")
