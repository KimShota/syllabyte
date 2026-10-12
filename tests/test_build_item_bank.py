"""scripts/build_item_bank.py: cache -> bank assembly, the cost estimate and the prompt. No LLM calls."""

import importlib.util
import json
import struct
import zlib
from pathlib import Path

import pytest

from assessment_agent.bank import TIERS, validate_bank
from syllabyte_common.models import KnowledgeUnit, SlideRef

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_item_bank", REPO / "scripts/build_item_bank.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)


def ku(id_: str, slide: int, prereqs: list[str] | None = None, bloom: str = "understand") -> KnowledgeUnit:
    return KnowledgeUnit(
        id=id_, title=f"Title of {id_}", summary="Summary.", bloom_level=bloom, cognitive_load="medium",
        prerequisites=prereqs or [], source_refs=[SlideRef(deck_name="slides", slide_number=slide)],
        visual_idea="v", short_worthiness=3, short_worthiness_reason="r",
    )


def entry(difficulty: float = 0.0, flags: list[dict] | None = None) -> dict:
    q = lambda t: {"stem": f"{t}?", "options": ["x", "y", "z"], "correct_index": 0, "explanation": "e", "hint": None}  # noqa: E731
    return {
        "gen": {"basic": q("b"), "applied": q("a"), "advanced": q("v"), "slides": [1, 2], "ku_difficulty": difficulty},
        "flags": flags or [],
    }


def write_cache(cache: Path, ku_id: str, e: dict) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    script.cache_path(cache, ku_id).write_text(json.dumps(e))


KUS = [ku("ku-a", 1), ku("ku-b", 5, ["ku-a"]), ku("ku-c", 20, ["ku-b"])]
lecture_of = lambda k: 1 if k.source_refs[0].slide_number < 10 else 2  # noqa: E731


class TestCollectBank:
    def test_assembles_cached_kus_and_reports_the_missing_ones(self, tmp_path):
        write_cache(tmp_path, "ku-a", entry(0.5))
        write_cache(tmp_path, "ku-c", entry(-1.0, flags=[{"id": "as-ku-c-advanced", "issue": "ambiguous"}]))
        items, flags, missing = script.collect_bank(KUS, lecture_of, tmp_path)
        assert [i.id for i in items] == [f"as-{k}-{t}" for k in ("ku-a", "ku-c") for t in TIERS]
        assert missing == ["ku-b"]
        assert flags == {"as-ku-c-advanced": "ambiguous"}
        assert {i.topic_id for i in items} == {"lecture-1", "lecture-2"}
        assert validate_bank(items, ["ku-a", "ku-c"]) == []

    def test_a_ku_is_judged_hard_by_shifting_all_three_of_its_items(self, tmp_path):
        write_cache(tmp_path, "ku-a", entry(2.0))
        items, _, _ = script.collect_bank(KUS, lecture_of, tmp_path)
        assert [i.difficulty_prior for i in items] == [0.0, 1.0, 2.0]

    def test_answers_are_balanced_by_course_position_not_by_what_was_generated(self, tmp_path):
        write_cache(tmp_path, "ku-b", entry())
        only_b, _, _ = script.collect_bank(KUS, lecture_of, tmp_path)
        write_cache(tmp_path, "ku-a", entry())
        write_cache(tmp_path, "ku-c", entry())
        everything, _, _ = script.collect_bank(KUS, lecture_of, tmp_path)
        by_id = {i.id: i.correct_index for i in everything}
        assert all(by_id[i.id] == i.correct_index for i in only_b)

    def test_an_empty_cache_gives_an_empty_bank(self, tmp_path):
        items, flags, missing = script.collect_bank(KUS, lecture_of, tmp_path)
        assert (items, flags, missing) == ([], {}, ["ku-a", "ku-b", "ku-c"])


def png(path: Path, w: int, h: int) -> Path:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")
    )
    return path


class TestEstimate:
    def test_reads_png_dimensions_and_caps_large_images(self, tmp_path):
        assert script.png_size(png(tmp_path / "a.png", 300, 200)) == (300, 200)
        assert script.image_tokens(png(tmp_path / "s.png", 150, 150)) == 30  # 22500 / 750
        assert script.image_tokens(png(tmp_path / "big.png", 4000, 3000)) == script.MAX_IMAGE_TOKENS

    def test_cost_grows_with_the_slide_material_and_scales_with_the_price(self):
        small = script.estimate_ku(1000, (5.0, 25.0))
        large = script.estimate_ku(5000, (5.0, 25.0))
        assert large["usd"] > small["usd"] and large["input_tokens"] > small["input_tokens"]
        assert script.estimate_ku(1000, (0.0, 0.0))["usd"] == 0.0
        assert script.estimate_ku(1000, (10.0, 50.0))["usd"] == pytest.approx(2 * small["usd"])

    def test_includes_the_critic_pass_and_the_rewrite_allowance(self):
        e = script.estimate_ku(2000, (1.0, 0.0))
        gen_in = script.SYSTEM_TOKENS + script.PROMPT_TOKENS + 2000
        crit_in = script.CRITIC_SYSTEM_TOKENS + script.ITEMS_TEXT_TOKENS + 2000
        assert e["input_tokens"] == pytest.approx((gen_in + crit_in) * (1 + script.REGEN_RATE))


class TestPrompt:
    def test_names_all_three_tiers_the_prerequisites_and_asks_for_a_ku_rating(self):
        p = script.bank_prompt(KUS[1], ["Title of ku-a"], "[slide 5]\ntext")
        for needle in ("basic", "applied", "advanced", "Remember / Understand", "Evaluate / Create", "Title of ku-a", "ku_difficulty", "[slide 5]"):
            assert needle in p

    def test_does_not_ask_for_per_item_difficulty(self):
        assert "difficulty_prior" not in script.BANK_SYSTEM
        assert "difficulty_prior" not in script.bank_prompt(KUS[0], [], "x")
        assert "Never use" in script.BANK_SYSTEM  # the rest of the item-writing rules are kept
