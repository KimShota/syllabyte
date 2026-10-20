"""
Which lecture a deck is, from what it teaches (plan/slide-uploads-plan.md V1). File names and covers can't be relied
on (a real course's 23 decks all share one cover; a file may be called slides.pdf), and a syllabus's schedule drifts
from what was taught, so:

    reader     one cheap call per deck: its content pages -> a title and a summary of what it teaches
    placement  one call per batch: the new decks' summaries, the lectures already in the course and the syllabus's
               topics -> the teaching order, and the decks it is not sure about

The first student to upload a deck sees the suggestion on the review screen and confirms or fixes it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from syllabyte_common.llm import image_block, structured, text_block
from syllabyte_common.models import RunManifest, SlideDeck

READER_MODEL = "claude-sonnet-5"
READ_PAGES = 6  # the first pages, after a cover
SPREAD_PAGES = 3  # and a few from the rest, so a long deck's later topics are seen


class DeckSummary(BaseModel):
    title: str = Field(description="what this lecture teaches, under 70 characters, e.g. 'Classification: training, validation and testing'")
    summary: str = Field(description="two or three sentences naming the topics in the order the slides teach them")
    lecture_number: int | None = Field(description="the lecture number only if the slides themselves state it (e.g. 'Lecture 7'); else null")
    is_lecture: bool = Field(description="false if this is not one lecture's slides (a syllabus, a blank file, an unrelated document)")


READER_SYSTEM = """You look at pages from one lecture's slide deck of a university course and say what the lecture teaches.

Rules:
- Ignore a cover page that only names the course, the instructor or the university: many courses use the same cover for every lecture.
- The title names what this lecture teaches, in the slides' own terms, under 70 characters. Do not include the course name or a lecture number.
- The summary is two or three plain sentences naming the topics in the order the slides teach them. Say so when the slides continue a topic from an earlier lecture (a recap, "continued", "last time").
- Set lecture_number only when the slides state it. Never guess it from the topics.
- The file name is a hint only: it may be meaningless or wrong."""


def pages_to_read(n: int) -> list[int]:
    """1-based page numbers: the first READ_PAGES after the cover, then SPREAD_PAGES spread over the rest."""
    first = list(range(1, min(n, READ_PAGES + 1) + 1))
    rest = list(range(first[-1] + 1, n + 1)) if first else []
    if rest:
        step = len(rest) / (SPREAD_PAGES + 1)
        first += sorted({rest[min(len(rest) - 1, int(step * (i + 1)))] for i in range(SPREAD_PAGES)})
    return first


def read_deck_content(deck: SlideDeck, *, file_name: str, course_name: str, model: str = READER_MODEL, manifest: RunManifest | None = None) -> DeckSummary:
    by_n = {s.slide_number: s for s in deck.slides}
    content: list[dict] = [text_block(f"Course: {course_name}\nFile name (a hint only): {file_name}\nThe deck has {len(deck.slides)} pages; these are some of them.")]
    for n in pages_to_read(len(deck.slides)):
        slide = by_n.get(n)
        if slide is None:
            continue
        content.append(text_block(f"[page {n}]\n{slide.text.strip()}"))
        if slide.image_path:
            content.append(image_block(slide.image_path))
    return structured(schema=DeckSummary, content=content, system=READER_SYSTEM, stage="read_deck", model=model, max_tokens=1500, manifest=manifest)


class Placement(BaseModel):
    order: list[str] = Field(description="every id given, lectures and new decks, in the order the course teaches them")
    unsure: list[str] = Field(description="ids of new decks whose place you are not confident about")


PLACEMENT_SYSTEM = """You put a university course's lecture slide decks in the order the course teaches them.

You get the lectures already in the course (in their order, which is fixed), new decks to place, and the topics the syllabus lists. Return every id in teaching order.

Rules:
- Keep the existing lectures in the order given. Place each new deck before, between or after them.
- Decide from what each deck teaches. A deck that continues a topic ("continued", a recap of the previous topic) comes right after the deck it continues. Something foundational comes before what builds on it.
- The syllabus's topic order is a guide, but the course may have drifted from it: decks are what was actually taught. A deck about a topic the syllabus does not list (a review, a guest lecture) still gets a place.
- A lecture number stated on the slides or in a file name is a strong hint; a file name with no number says nothing.
- List in `unsure` the new decks whose place you are not confident about."""


def place_decks(
    *, course_name: str, topics: list[str], lectures: list[dict], new: list[dict], model: str = READER_MODEL, manifest: RunManifest | None = None,
) -> Placement:
    """`lectures`: {id, title, summary} in course order; `new`: {id, file_name, title, summary, lecture_number}.
    The order returned has each id once, existing lectures in their order; an id the model left out goes last and is
    unsure."""
    if not new:
        return Placement(order=[l["id"] for l in lectures], unsure=[])
    if len(new) == 1 and not lectures:
        return Placement(order=[new[0]["id"]], unsure=[])
    def line(d: dict) -> str:
        bits = [f"id={d['id']}", f"title: {d['title']}"]
        if d.get("file_name"):
            bits.append(f"file: {d['file_name']}")
        if d.get("lecture_number"):
            bits.append(f"stated lecture number: {d['lecture_number']}")
        return "- " + "; ".join(bits) + f"\n  {d.get('summary', '')}"

    prompt = (
        f"Course: {course_name}\n\nSyllabus topics, in its order:\n" + ("\n".join(f"- {t}" for t in topics) or "(none listed)")
        + "\n\nLectures already in the course, in order:\n" + ("\n".join(line(l) for l in lectures) or "(none yet)")
        + "\n\nNew decks to place:\n" + "\n".join(line(d) for d in new)
    )
    out = structured(schema=Placement, content=[text_block(prompt)], system=PLACEMENT_SYSTEM, stage="place_decks", model=model, max_tokens=3000, manifest=manifest)
    return clean_placement(out, [l["id"] for l in lectures], [d["id"] for d in new])


def clean_placement(out: Placement, lecture_ids: list[str], new_ids: list[str]) -> Placement:
    """Each id once; the existing lectures in their own order whatever the model did; missing new decks last."""
    known = set(lecture_ids) | set(new_ids)
    order: list[str] = []
    for i in out.order:
        if i in known and i not in order:
            order.append(i)
    missing = [i for i in new_ids if i not in order]
    order += missing
    # existing lectures back in their order, in the slots they took
    slots = [k for k, i in enumerate(order) if i in set(lecture_ids)]
    present = [i for i in lecture_ids if i in order]
    for k, i in zip(slots, present):
        order[k] = i
    order += [i for i in lecture_ids if i not in order]
    unsure = [i for i in new_ids if i in set(out.unsure) or i in missing]
    return Placement(order=order, unsure=unsure)
