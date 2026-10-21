"""
The per-KU item bank (plan/per-ku-profiling-plan.md D4, D5).

Every Knowledge Unit gets three multiple-choice items, one per Bloom tier, written by an LLM from that KU's slides:

    basic     Remember / Understand   restate or recognise the idea
    applied   Apply / Analyze         use it on a small new case, or take a situation apart
    advanced  Evaluate / Create       judge a claim or design, spot the flaw, predict a change

The proposal (§3.2) maps readiness to those tiers, and `readiness_level` reads a KU's level off the difficulties
of its own applied and advanced items. This module is the LLM-free part: how an item's difficulty (beta) is set,
how the three items are put in order, how a generated KU becomes `Item`s, and what a valid bank looks like. The
script scripts/build_item_bank.py does the generation, caching and file output around it.

Difficulty before calibration (D5): the LLM rates the KU once (how hard the concept is for a student meeting it
for the first time), and beta = tier offset + LLM_KU_DIFFICULTY_WEIGHT x that rating. A hard KU shifts all three
of its items up and the tier spreads them one logit apart. The LLM is not asked to score the three items
separately: it already calls a basic item easy, so a per-item score would count the tier twice, and per-item
scores are the noisiest signal available. The three betas are still forced into strictly increasing order, a
guard for when the offsets are tuned. Discrimination stays 1.0 until post-pilot calibration.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel, Field
from syllabyte_common.learner import Item, ItemTier
from syllabyte_common.models import SlideRef

TIERS: tuple[ItemTier, ...] = ("basic", "applied", "advanced")
TIER_BLOOM: dict[ItemTier, str] = {
    "basic": "Remember / Understand",
    "applied": "Apply / Analyze",
    "advanced": "Evaluate / Create",
}

# Design choices, listed in the plan's traceability table; recalibrate from pilot data.
TIER_BETA_OFFSET: dict[ItemTier, float] = {"basic": -1.0, "applied": 0.0, "advanced": 1.0}
LLM_KU_DIFFICULTY_WEIGHT = 0.5  # the LLM rates the KU on -2..2, so it moves its items by at most +-1 logit
LLM_KU_DIFFICULTY_RANGE = (-2.0, 2.0)
MIN_TIER_GAP = 0.2  # beta(applied) >= beta(basic) + gap, and the same for advanced


class BankMCQ(BaseModel):
    """One written question. No difficulty here: it is set per KU and tier, not per item (see the module doc)."""

    stem: str
    options: list[str] = Field(min_length=3, max_length=3)
    correct_index: int = Field(ge=0, le=2)
    explanation: str  # one or two sentences, shown after the answer
    hint: str | None = None  # a nudge that does not give the answer away


class KuBankGen(BaseModel):
    """What the LLM writes for one KU: three items, the slides that ground them, and a difficulty rating."""

    basic: BankMCQ
    applied: BankMCQ
    advanced: BankMCQ
    slides: list[int]
    ku_difficulty: float = Field(ge=-3, le=3)  # -2 (very easy) .. 2 (hard) for a first-time learner; 0 is medium


def tier_beta(tier: ItemTier, ku_difficulty: float) -> float:
    lo, hi = LLM_KU_DIFFICULTY_RANGE
    return TIER_BETA_OFFSET[tier] + LLM_KU_DIFFICULTY_WEIGHT * min(max(ku_difficulty, lo), hi)


def order_tiers(betas: Mapping[ItemTier, float]) -> dict[ItemTier, float]:
    """Force basic < applied < advanced with at least MIN_TIER_GAP between neighbours, moving only upward.

    If the LLM called the advanced item easier than the applied one, the readiness rule (theta >= b) would
    otherwise make "proficient without developing" possible; ordering the tiers closes that.
    """
    out = dict(betas)
    out["applied"] = max(out["applied"], out["basic"] + MIN_TIER_GAP)
    out["advanced"] = max(out["advanced"], out["applied"] + MIN_TIER_GAP)
    return {t: round(out[t], 4) for t in TIERS}


def tier_difficulties(ku_difficulty: float) -> dict[ItemTier, float]:
    """A KU's question difficulty at each tier, ordered: the betas its bank items get, and what an uploaded KU carries
    before any question on it is written (plan/slide-uploads-plan.md V4)."""
    return order_tiers({t: tier_beta(t, ku_difficulty) for t in TIERS})


MAX_STEM_WORDS = 30
# the keyed option is a giveaway when it is this much longer than the longest wrong one
MAX_KEY_LENGTH_RATIO = 1.2
# "the diagram", "this figure", "the house example": material a student who has not had the lecture never saw ("the
# examples" is left alone: it is how a stem refers back to the data it describes)
_UNSEEN_MATERIAL = re.compile(
    r"\b(the|this|that|these)\s+(?:[\w-]+\s+){0,2}?(slides?|diagrams?|figures?|panels?|charts?|plots?|graphs?|tables?|images?|pictures?|illustrations?|example)\b",
    re.IGNORECASE,
)


# specialist notation a general reader cannot follow: Greek letters, maths symbols, subscripts, "Y1 - Y0", and a lone
# letter standing for something ("the experience E", "the mapping f"); "A" and "I" are words, and a letter in quotes
# or after "Plan"/"vitamin" is rare enough in a pre-check to send back anyway
_NOTATION = re.compile(r"[\u0370-\u03ff=^_∑√≤≥≈∈∀∃→←|]|\b[A-Za-z]\d\b|(?<![\w'’-])(?![AaI]\b)[A-Za-z](?![\w'’-])")
# words that mark an option as wrong to a student who knows how tests work, whatever the idea
_ABSOLUTE = re.compile(r"\b(always|never|only|guaranteed?|guarantees|nothing|none|cannot|impossible|entirely|completely)\b", re.IGNORECASE)
# a sentence that ends cleanly: one full stop, question mark or exclamation mark, then at most a closing quote or bracket
_CLEAN_END = re.compile(r"[^.?!][.?!][\"'”’)\]]?$")


def mcq_problems(m: BankMCQ) -> list[str]:
    """What the code can see is wrong with a pre-check question, worded as instructions for the rewrite. The student
    takes the check before the lecture, on a phone, so the question must stand on its own, be short, and not give
    its answer away by its length."""
    out = []
    if not m.stem.strip().endswith("?"):
        # the model likes to end an advanced stem on a claim with no question, so the student has to guess the task
        out.append("the stem must end with a question that tells the student what to do")
    if len(m.stem.split()) > MAX_STEM_WORDS:
        out.append(f"the stem has {len(m.stem.split())} words; keep it to {MAX_STEM_WORDS} or fewer")
    refs = sorted({hit.group(0) for text in (m.stem, *m.options) for hit in _UNSEEN_MATERIAL.finditer(text)})
    if refs:
        out.append(
            f"the question points at material the student has not seen ({', '.join(repr(r) for r in refs)}); "
            "describe the case in the stem instead"
        )
    key = len(m.options[m.correct_index])
    longest_wrong = max(len(o) for i, o in enumerate(m.options) if i != m.correct_index)
    if key > MAX_KEY_LENGTH_RATIO * longest_wrong:
        out.append("the right option is clearly the longest; make the three options about the same length and detail")
    notation = sorted({hit.group(0) for text in (m.stem, *m.options) for hit in _NOTATION.finditer(text)})
    if notation:
        out.append(
            f"the question uses specialist notation ({', '.join(repr(n) for n in notation)}); say it in plain words a "
            "general reader would understand"
        )
    marked = sorted({w.group(0).lower() for i, o in enumerate(m.options) if i != m.correct_index for w in _ABSOLUTE.finditer(o)})
    if marked and not _ABSOLUTE.search(m.options[m.correct_index]):
        out.append(
            f"the wrong options use absolute words ({', '.join(repr(w) for w in marked)}) that the right one avoids; "
            "word all three in the same measured way"
        )
    for name, text in (("explanation", m.explanation), ("hint", m.hint)):
        if text is not None and not _CLEAN_END.search(text.strip()):
            out.append(f"the {name} must be complete sentences ending in one full stop or question mark, with nothing after it")
    return out


def stem_problems(gen: KuBankGen) -> list[str]:
    """`mcq_problems` for each of the KU's three questions, prefixed by its tier."""
    return [f"{t}: {p}" for t in TIERS for p in mcq_problems(getattr(gen, t))]


def bank_item_id(ku_id: str, tier: ItemTier) -> str:
    return f"as-{ku_id}-{tier}"


def lecture_topic_id(lecture_n: int) -> str:
    """A topic is a lecture (plan D2)."""
    return f"lecture-{lecture_n}"


def assemble_ku_items(ku_id: str, topic_id: str, gen: KuBankGen, deck_name: str = "slides") -> list[Item]:
    """The KU's three bank items, difficulty set and ordered, answers not yet balanced. `deck_name`: the deck the
    slide numbers refer to (the dev course has one, "slides")."""
    betas = tier_difficulties(gen.ku_difficulty)
    refs = [SlideRef(deck_name=deck_name, slide_number=n) for n in gen.slides]
    items = []
    for t in TIERS:
        m: BankMCQ = getattr(gen, t)
        items.append(
            Item(
                id=bank_item_id(ku_id, t), ku_id=ku_id, topic_id=topic_id, context="assessment", stem=m.stem,
                options=list(m.options), correct_index=m.correct_index, allows_not_sure=True, explanation=m.explanation,
                hint=m.hint, difficulty_prior=betas[t], discrimination=1.0, tier=t, source_refs=refs,
            )
        )
    return items


def balance_positions(items: Iterable[Item], ku_order: Sequence[str]) -> None:
    """Spread the keyed answer evenly over A/B/C (the model favours some slots).

    The target slot is (KU position in the whole course + tier position) mod 3, so it does not depend on which
    KUs a run happens to include, and over a full bank each slot is keyed equally often (+-1). Options are swapped
    in place; nothing in an explanation or hint refers to option positions.
    """
    rank = {k: i for i, k in enumerate(sorted(ku_order))}
    for it in items:
        assert it.ku_id is not None and it.tier is not None
        target = (rank[it.ku_id] + TIERS.index(it.tier)) % 3
        c = it.correct_index
        if c != target:
            it.options[c], it.options[target] = it.options[target], it.options[c]
            it.correct_index = target


def validate_bank(items: Sequence[Item], ku_ids: Iterable[str]) -> list[str]:
    """Problems that would make the bank unusable for CAT; an empty list means it is fine."""
    ku_ids = list(ku_ids)
    problems: list[str] = []
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        problems.append("duplicate item ids")
    by_ku: dict[str, dict[str, Item]] = {}
    for it in items:
        if it.context != "assessment" or it.tier is None or it.ku_id is None:
            problems.append(f"{it.id}: not a bank item (needs context 'assessment', a tier and a KU)")
            continue
        if it.tier in by_ku.setdefault(it.ku_id, {}):
            problems.append(f"{it.ku_id}: two {it.tier} items")
        by_ku[it.ku_id][it.tier] = it
        if len(it.options) != 3:
            problems.append(f"{it.id}: needs exactly 3 options")
        if it.discrimination != 1.0:
            problems.append(f"{it.id}: discrimination must be 1.0 until calibration")
    for ku in ku_ids:
        have = by_ku.get(ku, {})
        missing = [t for t in TIERS if t not in have]
        if missing:
            problems.append(f"{ku}: missing {', '.join(missing)}")
            continue
        b = [have[t].difficulty_prior for t in TIERS]
        if not (b[0] + MIN_TIER_GAP - 1e-9 <= b[1] and b[1] + MIN_TIER_GAP - 1e-9 <= b[2]):
            problems.append(f"{ku}: difficulties not in tier order ({b})")
    unknown = set(by_ku) - set(ku_ids)
    if unknown:
        problems.append(f"items for unknown KUs: {sorted(unknown)}")
    return problems

