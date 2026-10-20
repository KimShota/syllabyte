#!/usr/bin/env python
"""
Build the per-KU item bank (plan/per-ku-profiling-plan.md D4, D5): three multiple-choice items per Knowledge
Unit, one per Bloom tier, written by an LLM from the KU's own slides and checked by the existing critic pass.

    uv run python scripts/build_item_bank.py --estimate                  # what a full run would cost; no API call
    uv run python scripts/build_item_bank.py --lectures 1                # generate one lecture (spends LLM credits)
    uv run python scripts/build_item_bank.py --kus ku-a,ku-b --regen     # redo specific KUs
    uv run python scripts/build_item_bank.py                             # generate everything not cached yet
    uv run python scripts/build_item_bank.py --skip-llm                  # only reassemble bank.json from the cache

Results are cached per KU in <run>/ui_cache/bank-<ku>.json, so a rerun costs nothing and lectures can be built one
at a time. `bank.json` always holds every KU that has a cache entry; `_bank-review.md` lists each question with its
keyed answer, tier, beta and any critic flag: READ IT before using the bank (the plan has you hand-validate a
sample).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import build_ui_fixtures as ui  # noqa: E402  (the dev course's lectures, short titles, critic loop and slide loader)
from assessment_agent.bank import (  # noqa: E402
    KuBankGen,
    assemble_ku_items,
    balance_positions,
    lecture_topic_id,
    validate_bank,
)
from assessment_agent.bank_writing import BANK_SYSTEM, bank_prompt, write_ku_bank  # noqa: E402,F401  (tests read the prompt here)
from syllabyte_common.learner import Item  # noqa: E402
from syllabyte_common.llm import DEFAULT_MODEL, PRICE_PER_MTOK  # noqa: E402
from syllabyte_common.models import CourseCorpus, KnowledgeUnit, KUList, RunManifest  # noqa: E402

# --------------------------------------------------------------------------
# cache <-> items
# --------------------------------------------------------------------------


def cache_path(cache: Path, ku_id: str) -> Path:
    return cache / f"bank-{ku_id}.json"


def collect_bank(
    kus: list[KnowledgeUnit], lecture_of, cache: Path
) -> tuple[list[Item], dict[str, str], list[str]]:
    """Items for every KU that has a cache entry, answers balanced; plus critic flags by item id and the KUs
    still missing."""
    items: list[Item] = []
    flags: dict[str, str] = {}
    missing: list[str] = []
    for ku in kus:
        path = cache_path(cache, ku.id)
        if not path.exists():
            missing.append(ku.id)
            continue
        entry = json.loads(path.read_text())
        ku_items = assemble_ku_items(ku.id, lecture_topic_id(lecture_of(ku)), KuBankGen.model_validate(entry["gen"]))
        items += ku_items
        for f in entry.get("flags", []):
            flags[f["id"]] = f["issue"]
    balance_positions(items, [k.id for k in kus])
    return items, flags, missing


# --------------------------------------------------------------------------
# cost estimate (no API call)
# --------------------------------------------------------------------------

SYSTEM_TOKENS = 450  # BANK_SYSTEM
PROMPT_TOKENS = 700  # the KU header and tier instructions
CRITIC_SYSTEM_TOKENS = 250
OUT_GEN_TOKENS = 800  # three questions with explanations and hints, plus slides and the rating
OUT_CRITIC_TOKENS = 150
ITEMS_TEXT_TOKENS = 700  # the three questions as the critic sees them
REGEN_RATE = 0.25  # share of KUs the critic sends back for one rewrite (the earlier item runs needed about this)
CHARS_PER_TOKEN = 3.6
MAX_IMAGE_TOKENS = 1600


def png_size(path: str | Path) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def image_tokens(path: str | Path) -> int:
    """Anthropic's rule of thumb: width x height / 750 tokens, capped for large images."""
    w, h = png_size(path)
    return min(round(w * h / 750), MAX_IMAGE_TOKENS)


def material_tokens(corpus: CourseCorpus, slide_numbers: list[int]) -> int:
    chars, tokens = 0, 0
    for n in sorted(set(slide_numbers)):
        slide = corpus.slide_by_ref("slides", n) or next((s for d in corpus.decks for s in d.slides if s.slide_number == n), None)
        if slide is None:
            continue
        chars += len(slide.text) + 16
        if slide.image_path and Path(slide.image_path).exists():
            tokens += image_tokens(slide.image_path)
    return tokens + round(chars / CHARS_PER_TOKEN)


def estimate_ku(material: int, price: tuple[float, float]) -> dict[str, float]:
    gen_in = SYSTEM_TOKENS + PROMPT_TOKENS + material
    crit_in = CRITIC_SYSTEM_TOKENS + ITEMS_TEXT_TOKENS + material
    calls_in = (gen_in + crit_in) * (1 + REGEN_RATE)
    calls_out = (OUT_GEN_TOKENS + OUT_CRITIC_TOKENS) * (1 + REGEN_RATE)
    usd = calls_in / 1e6 * price[0] + calls_out / 1e6 * price[1]
    return {"input_tokens": calls_in, "output_tokens": calls_out, "usd": usd}


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------


def generate_ku(ku: KnowledgeUnit, kus: dict[str, KnowledgeUnit], corpus: CourseCorpus, args, manifest: RunManifest) -> dict:
    slides = sorted({r.slide_number for r in ku.source_refs})
    material = ui.slide_material(corpus, slides)
    prereqs = [ui.SHORT_TITLES.get(p, kus[p].title) for p in ku.prerequisites if p in kus]
    ui.log(f"{ku.id}: generating (slides {slides})")
    gen, flags = write_ku_bank(
        ku, prereqs, material, model=args.model, critic_model=args.critic_model or args.model, manifest=manifest, log=ui.log,
    )
    return {"gen": gen.model_dump(), "flags": flags}


def write_review(out: Path, items: list[Item], flags: dict[str, str], kus_by_id: dict[str, KnowledgeUnit]) -> None:
    lines = ["# Item bank review sheet", "",
             "Generated by `scripts/build_item_bank.py`. **Read every question before using the bank.** "
             "A ⚠ means the critic still objected after one rewrite. beta is the IRT difficulty (logit scale).", ""]
    current = None
    for it in items:
        if it.ku_id != current:
            current = it.ku_id
            ku = kus_by_id[it.ku_id]
            lines += [f"## `{ku.id}` — {ku.title}", f"Bloom level (course analysis): {ku.bloom_level} · topic `{it.topic_id}`", ""]
        flag = f"  ⚠ {flags[it.id]}" if it.id in flags else ""
        lines += [f"### `{it.id}` · {it.tier} · beta {it.difficulty_prior:+.2f}{flag}", f"**{it.stem}**"]
        lines += [f"- {'✅' if i == it.correct_index else '▫️'} {o}" for i, o in enumerate(it.options)]
        lines += [f"_Why:_ {it.explanation}", f"_Hint:_ {it.hint or '—'}", ""]
    (out / "_bank-review.md").write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="runs/dev")
    ap.add_argument("--out", default="packages/core/fixtures")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--critic-model", default=None, help="defaults to --model")
    ap.add_argument("--lectures", default=None, help="comma-separated lecture numbers to generate (default: all)")
    ap.add_argument("--kus", default=None, help="comma-separated KU ids to generate (instead of --lectures)")
    ap.add_argument("--regen", action="store_true", help="ignore the cache for the selected lectures / KUs")
    ap.add_argument("--skip-llm", action="store_true", help="do not call the LLM; only reassemble from the cache")
    ap.add_argument("--estimate", action="store_true", help="print the expected cost and exit; no API call")
    ap.add_argument("--workers", type=int, default=4, help="KUs generated in parallel")
    args = ap.parse_args()

    run, out = Path(args.run), Path(args.out)
    corpus = CourseCorpus.model_validate_json((run / "corpus.json").read_text())
    kus_list = KUList.model_validate_json((run / "kus.json").read_text()).knowledge_units
    kus = {k.id: k for k in kus_list}
    cache = run / "ui_cache"

    def lecture_of(ku: KnowledgeUnit) -> int:
        first = min(r.slide_number for r in ku.source_refs)
        return next(l.n for l in ui.LECTURES if l.slide_start <= first <= l.slide_end)

    ordered = sorted(kus_list, key=lambda k: (lecture_of(k), min(r.slide_number for r in k.source_refs)))
    wanted = {int(n) for n in args.lectures.split(",")} if args.lectures else {l.n for l in ui.LECTURES}
    only = set(args.kus.split(",")) if args.kus else None
    if only and only - set(kus):
        sys.exit(f"unknown KU(s): {sorted(only - set(kus))}")
    todo = [
        k for k in ordered
        if (k.id in only if only else lecture_of(k) in wanted) and (args.regen or not cache_path(cache, k.id).exists())
    ]

    if args.estimate:
        price = PRICE_PER_MTOK.get(args.model, (0.0, 0.0))
        print(f"model {args.model}: ${price[0]:.2f} in / ${price[1]:.2f} out per Mtok (0 means no price on file)")
        total = 0.0
        for n in sorted({lecture_of(k) for k in todo} or wanted):
            rows = [estimate_ku(material_tokens(corpus, [r.slide_number for r in k.source_refs]), price) for k in todo if lecture_of(k) == n]
            usd = sum(r["usd"] for r in rows)
            total += usd
            print(f"lecture {n}: {len(rows)} KUs to generate · ~{sum(r['input_tokens'] for r in rows):,.0f} in / "
                  f"{sum(r['output_tokens'] for r in rows):,.0f} out tokens · ≈ ${usd:.2f}")
        print(f"total ≈ ${total:.2f} for {len(todo)} KUs (includes a critic pass and {REGEN_RATE:.0%} rewrites)")
        return

    manifest = RunManifest(run_id="item-bank", course_name=ui.COURSE_ID)
    if todo and not args.skip_llm:
        ui.log(f"generating {len(todo)} KU(s) with {args.workers} worker(s)")

        def work(ku: KnowledgeUnit) -> None:
            entry = generate_ku(ku, kus, corpus, args, manifest)
            cache_path(cache, ku.id).write_text(json.dumps(entry, indent=2, ensure_ascii=False))

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            list(pool.map(work, todo))
    elif todo:
        ui.log(f"--skip-llm: {len(todo)} KU(s) not generated")

    items, flags, missing = collect_bank(ordered, lecture_of, cache)
    covered = [k.id for k in ordered if k.id not in missing]
    problems = validate_bank(items, covered)
    if problems:
        sys.exit("item bank is not valid:\n  " + "\n  ".join(problems))
    out.mkdir(parents=True, exist_ok=True)
    (out / "bank.json").write_text(json.dumps([i.model_dump() for i in items], indent=2, ensure_ascii=False))
    write_review(out, items, flags, kus)

    ui.log(f"wrote {len(items)} items for {len(covered)}/{len(ordered)} KUs -> {out / 'bank.json'}  "
           f"(LLM cost this run ≈ ${manifest.total_cost_usd(PRICE_PER_MTOK):.2f})")
    if missing:
        ui.log(f"not in the bank yet: {len(missing)} KU(s)")
    if flags:
        ui.log(f"⚠ {len(flags)} item(s) still flagged by the critic — see _bank-review.md: {sorted(flags)}")


if __name__ == "__main__":
    main()
