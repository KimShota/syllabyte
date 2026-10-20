"""
Knowledge Units for one uploaded deck (plan/slide-uploads-plan.md U3, U7).

A deck is processed once, in lecture order, with the syllabus and the KUs of the earlier lectures, so a KU may build
on an earlier lecture's KU. When an earlier lecture's deck arrives after later ones (U7), `find_links` adds the links
from the later lectures' KUs back to it; it never changes a KU.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from syllabyte_common.llm import DEFAULT_MODEL, pdf_block, structured, text_block
from syllabyte_common.models import KnowledgeUnit, RunManifest, SlideDeck

from curriculum_alignment_agent.ku_extractor import SYSTEM_PROMPT, _deck_as_text


class UploadKU(KnowledgeUnit):
    short_title: str = Field(description="2 to 4 words for a phone screen, e.g. 'Potential outcomes'")


class UploadKUList(BaseModel):
    knowledge_units: list[UploadKU]


class EarlierKu(BaseModel):
    """A KU already in the course, as context for a later deck or the link pass."""

    id: str
    title: str
    summary: str
    lecture_n: int


_SAME_DECK_RULE = """  - Lists prerequisites as OTHER Knowledge Unit ids from this same deck, \
if any (use ids you invent consistently, e.g. "ku-big-o-definition")."""
assert _SAME_DECK_RULE in SYSTEM_PROMPT, "ku_extractor.SYSTEM_PROMPT changed; update the prerequisite rule here"
UPLOAD_SYSTEM = SYSTEM_PROMPT.replace(
    _SAME_DECK_RULE,
    """  - Lists prerequisites: ids of OTHER Knowledge Units it directly builds on, either from this deck (ids you \
invent consistently, e.g. "ku-big-o-definition") or from the earlier lectures' units listed in the request (use \
their ids exactly). Only direct prerequisites a student must know first, not everything related.
  - Has a short_title of 2 to 4 words for a phone screen.""",
)


def _earlier_text(earlier: list[EarlierKu]) -> str:
    if not earlier:
        return "(none: this is the first lecture with slides)"
    return "\n".join(f"- {k.id} (lecture {k.lecture_n}): {k.title}. {k.summary}" for k in earlier)


def extract_deck_kus(
    *,
    course_name: str,
    syllabus_text: str,
    lecture_n: int,
    lecture_title: str,
    deck: SlideDeck,
    earlier: list[EarlierKu],
    taken_ids: set[str],
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> list[UploadKU]:
    """The deck's KUs, with ids unique in the course and prerequisites only to this deck or earlier lectures."""
    context = (
        f"Course: {course_name}\n\n=== SYLLABUS ===\n{syllabus_text}\n\n"
        f"=== KNOWLEDGE UNITS OF EARLIER LECTURES ===\n{_earlier_text(earlier)}\n\n"
        f"=== DECK '{deck.name}': lecture {lecture_n}, {lecture_title} ===\n"
        f"Extract Knowledge Units from this deck, citing deck_name='{deck.name}' in every source_refs entry."
    )
    if deck.has_images and deck.source_path.lower().endswith(".pdf"):
        content = [pdf_block(deck.source_path), text_block(context)]
    else:
        content = [text_block(context + "\n\n" + _deck_as_text(deck))]
    out = structured(
        schema=UploadKUList, content=content, system=UPLOAD_SYSTEM, stage="extract_kus", model=model,
        max_tokens=32000, manifest=manifest,
    )
    return clean_deck_kus(out.knowledge_units, deck, {k.id for k in earlier}, taken_ids)


def clean_deck_kus(kus: list[UploadKU], deck: SlideDeck, earlier_ids: set[str], taken_ids: set[str]) -> list[UploadKU]:
    """Makes the model's output safe to store: ids unique in the course (a clash gets a suffix), prerequisites only to
    this deck's KUs or earlier lectures' (an id of this deck wins over an earlier one with the same name), no
    cycles, and slide references to this deck's pages only."""
    used = set(taken_ids)
    new_ids: list[str] = []
    first: dict[str, str] = {}  # the model's id -> the stored id of the first KU that had it
    for k in kus:
        new, n = k.id, 2
        while new in used:
            new, n = f"{k.id}-{n}", n + 1
        used.add(new)
        new_ids.append(new)
        first.setdefault(k.id, new)
    pages = {s.slide_number for s in deck.slides}

    out: list[UploadKU] = []
    for k, kid in zip(kus, new_ids):
        prereqs: list[str] = []
        for p in k.prerequisites:
            target = first.get(p) or (p if p in earlier_ids else None)
            if target and target != kid and target not in prereqs:
                prereqs.append(target)
        refs = [r.model_copy(update={"deck_name": deck.name}) for r in k.source_refs if r.slide_number in pages]
        short = k.short_title.strip() or k.title[:30]
        out.append(k.model_copy(update={"id": kid, "prerequisites": prereqs, "source_refs": refs, "short_title": short}))
    return _drop_cycles(out)


def _drop_cycles(kus: list[UploadKU]) -> list[UploadKU]:
    """Keeps each prerequisite unless it would close a cycle among this deck's KUs (earlier lectures cannot)."""
    edges: dict[str, list[str]] = {k.id: [] for k in kus}

    def reaches(a: str, b: str) -> bool:
        stack, seen = [a], set()
        while stack:
            x = stack.pop()
            if x == b:
                return True
            if x in seen:
                continue
            seen.add(x)
            stack.extend(edges.get(x, []))
        return False

    out = []
    for k in kus:
        kept = []
        for p in k.prerequisites:
            if p in edges and reaches(p, k.id):
                continue
            kept.append(p)
            if p in edges:
                edges[k.id].append(p)
        out.append(k.model_copy(update={"prerequisites": kept}))
    return out


# --------------------------------------------------------------------------
# the link pass (U7)
# --------------------------------------------------------------------------


class Link(BaseModel):
    ku_id: str  # a later lecture's KU
    prereq_id: str  # the newly processed lecture's KU it builds on


class LinkList(BaseModel):
    links: list[Link]


LINK_SYSTEM = """You connect Knowledge Units of a university course. One lecture's units have just been added; the course's later lectures were added before it.
Return the links where a LATER unit directly builds on a NEW unit: a student must know the new unit first to follow the later one.
Only direct prerequisites, not every related pair. Use the ids exactly as given. Return an empty list when there are none."""


def find_links(
    *,
    course_name: str,
    new_kus: list[EarlierKu],
    later_kus: list[EarlierKu],
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> list[Link]:
    if not new_kus or not later_kus:
        return []
    prompt = (
        f"Course: {course_name}\n\n=== NEW UNITS ===\n{_earlier_text(new_kus)}\n\n"
        f"=== LATER UNITS ===\n{_earlier_text(later_kus)}"
    )
    out = structured(schema=LinkList, content=[text_block(prompt)], system=LINK_SYSTEM, stage="link_pass", model=model, max_tokens=4000, manifest=manifest)
    new_ids, later_ids = {k.id for k in new_kus}, {k.id for k in later_kus}
    seen: set[tuple[str, str]] = set()
    links = []
    for l in out.links:
        key = (l.ku_id, l.prereq_id)
        if l.ku_id in later_ids and l.prereq_id in new_ids and key not in seen:
            seen.add(key)
            links.append(l)
    return links
