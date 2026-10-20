"""
The upload worker's jobs (plan/slide-uploads-plan.md), each a function of what the server sends:

    syllabus    read the syllabus, then (only for a new course) its lecture list
    deck_read   convert, render and key a deck; no LLM, so a deck already in the course costs nothing
    deck        the deck's KUs (with the earlier lectures' KUs as context) and its item bank
    link_pass   links from later lectures' KUs to a lecture that arrived after them (U7)

The results are JSON the server stores as they are: a deck's result is the `DeckResult` of
packages/core/src/logic/assemble.ts.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from assessment_agent.bank import assemble_ku_items, balance_positions, validate_bank
from assessment_agent.bank_writing import write_ku_bank
from assessment_agent.item_writing import slides_material
from curriculum_alignment_agent.deck_kus import EarlierKu, UploadKU, extract_deck_kus, find_links
from syllabyte_common.learner import Item
from syllabyte_common.llm import DEFAULT_MODEL, PRICE_PER_MTOK
from syllabyte_common.models import RunManifest, SlideDeck

from ingestion_agent.uploads import read_deck, read_schedule, read_syllabus

Log = Callable[[str], None]


def run_syllabus_job(path: str | Path, *, is_new: Callable[[str], bool], model: str = DEFAULT_MODEL, manifest: RunManifest | None = None) -> dict:
    """`is_new(key)` asks the server whether this syllabus starts a new course; only then is its lecture list read."""
    read = read_syllabus(path)
    out: dict = {"key": read.key, "text": read.text}
    if is_new(read.key):
        schedule = read_schedule(read.text, model=model, manifest=manifest)
        out["schedule"] = schedule.model_dump()
    return out


def run_deck_read_job(path: str | Path, work_dir: str | Path, deck_name: str) -> dict:
    read, _ = read_deck(path, work_dir, deck_name)
    return read.model_dump()


def deck_bank(
    kus: list[UploadKU], deck: SlideDeck, titles: dict[str, str], *, model: str, critic_model: str, manifest: RunManifest, log: Log = print,
) -> tuple[list[Item], list[dict]]:
    """Three items per KU from its own slides (D4), answers balanced, checked as a bank."""
    by_n = {s.slide_number: s for s in deck.slides}
    items: list[Item] = []
    flags: list[dict] = []
    for ku in kus:
        slides = [by_n[n] for n in sorted({r.slide_number for r in ku.source_refs}) if n in by_n] or deck.slides[:3]
        prereqs = [titles[p] for p in ku.prerequisites if p in titles]
        gen, ku_flags = write_ku_bank(ku, prereqs, slides_material(slides), model=model, critic_model=critic_model, manifest=manifest, log=log)
        items += assemble_ku_items(ku.id, "", gen, deck_name=deck.name)
        flags += ku_flags
    balance_positions(items, [k.id for k in kus])
    problems = validate_bank(items, [k.id for k in kus])
    if problems:
        raise RuntimeError("the item bank is not usable: " + "; ".join(problems))
    return items, flags


def run_deck_job(
    payload: dict, pdf_path: str | Path, work_dir: str | Path, *, model: str = DEFAULT_MODEL, critic_model: str | None = None,
    manifest: RunManifest | None = None, log: Log = print,
) -> dict:
    """payload: deck_id, course_name, syllabus_text, lecture_n, lecture_title, earlier (EarlierKu dicts), taken_ids."""
    manifest = manifest or RunManifest(run_id=f"deck-{payload['deck_id']}")
    _, deck = read_deck(pdf_path, work_dir, payload["deck_id"])
    earlier = [EarlierKu.model_validate(k) for k in payload.get("earlier", [])]
    kus = extract_deck_kus(
        course_name=payload["course_name"], syllabus_text=payload["syllabus_text"], lecture_n=payload["lecture_n"],
        lecture_title=payload["lecture_title"], deck=deck, earlier=earlier, taken_ids=set(payload.get("taken_ids", [])),
        model=model, manifest=manifest,
    )
    if not kus:
        raise RuntimeError("no knowledge units were found in this deck")
    titles = {k.id: k.title for k in earlier} | {k.id: k.short_title for k in kus}
    log(f"deck {payload['deck_id']}: {len(kus)} KUs; writing the item bank")
    items, flags = deck_bank(kus, deck, titles, model=model, critic_model=critic_model or model, manifest=manifest, log=log)
    return {
        "kus": [k.model_dump(mode="json") for k in kus],
        "items": [i.model_dump(mode="json") for i in items],
        "flags": flags,
        "cost_usd": round(manifest.total_cost_usd(PRICE_PER_MTOK), 4),
    }


def run_link_pass_job(payload: dict, *, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None) -> dict:
    """payload: course_name, new_kus and later_kus (EarlierKu dicts)."""
    links = find_links(
        course_name=payload["course_name"],
        new_kus=[EarlierKu.model_validate(k) for k in payload["new_kus"]],
        later_kus=[EarlierKu.model_validate(k) for k in payload["later_kus"]],
        model=model, manifest=manifest,
    )
    return {"links": [l.model_dump() for l in links]}
