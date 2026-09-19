"""
Corpus builder — combines a parsed syllabus (syllabus_parser.py) with one or
more parsed slide decks (slide_parser.py) into a single CourseCorpus, which
is what curriculum_alignment_agent.ku_extractor consumes.
"""

from __future__ import annotations

from pathlib import Path

from ingestion_agent.slide_parser import parse_slide_deck
from ingestion_agent.syllabus_parser import parse_syllabus
from syllabyte_common.models import CourseCorpus


def build_corpus(
    syllabus_path: str | Path,
    slide_paths: list[str | Path],
    image_dir: str | Path,
    course_name: str | None = None,
) -> CourseCorpus:
    syllabus_path = Path(syllabus_path)
    syllabus_doc = parse_syllabus(syllabus_path)

    decks = [parse_slide_deck(p, image_dir=image_dir) for p in slide_paths]

    return CourseCorpus(
        course_name=course_name or syllabus_path.parent.name,
        syllabus_path=str(syllabus_path),
        syllabus_text=syllabus_doc.full_text,
        decks=decks,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--syllabus", required=True)
    parser.add_argument("--slides", nargs="+", required=True)
    parser.add_argument("--out", default="runs/dev")
    args = parser.parse_args()

    out_dir = Path(args.out)
    image_dir = out_dir / "images"
    corpus = build_corpus(args.syllabus, args.slides, image_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corpus.json").write_text(corpus.model_dump_json(indent=2))

    total_slides = sum(len(d.slides) for d in corpus.decks)
    print(
        f"Built corpus for '{corpus.course_name}': "
        f"{len(corpus.syllabus_text)} syllabus chars, "
        f"{len(corpus.decks)} deck(s), {total_slides} slides total."
    )
    print(f"Wrote {out_dir / 'corpus.json'}")
