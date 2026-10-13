"""Formulas set as plain Text are sent to repair, and one colour key is shared by a video's segments
(plan/per-student-video-plan.md, the defects found in the second low-effort video). No LLM calls, no renders."""

import pytest

from animation_agent import renderer
from animation_agent.manim_codegen import check_text_formulas
from animation_agent.manim_prompt import build_generation_prompt, build_layout_repair_prompt, build_repair_prompt, format_beats
from script_generation_agent.prompts import level_system_prompt
from script_generation_agent.script_writer import validate_script
from syllabyte_common.models import Beat, RenderSegment, Script, Segment, SlideRef, TermColour

REF = [SlideRef(deck_name="slides", slide_number=1)]


def scene(*lines: str) -> str:
    body = "\n".join(f"        {line}" for line in lines)
    return f"""from manim import *
from animation_agent.layout import GridLayoutScene

class Seg0(GridLayoutScene):
    def construct(self):
        self.setup_grid()
{body}
        self.end_beat(1)
"""


class TestTextFormulas:
    @pytest.mark.parametrize("text", ["ȳ_T − ȳ_C", "x^2", "Y_{0}", "E[Y_1 | D=1]", r"\bar{y}", r"\frac{a}{b}"])
    def test_a_formula_typed_into_text_is_flagged(self, text):
        problem = check_text_formulas(scene(f"t = Text({text!r})"))
        assert problem is not None and "line 7" in problem and "ONE MathTex" in problem

    def test_the_split_formula_from_the_second_video_is_flagged(self):
        problem = check_text_formulas(scene(
            'part1 = Text("E[Y₀ | D=1]", font_size=36)',
            'minus = Text("−", font_size=36)',
            'part2 = Text("E[Y₀ | D=0]", font_size=36)',
            "term = VGroup(part1, minus, part2).arrange(DOWN, buff=0.25)",
        ))
        assert problem is not None and "lone operator" in problem and "line 8" in problem

    @pytest.mark.parametrize("text", ["treated", "E[Y₀ | D=1]", "Δmeans = causal + bias", "C = observed control", "4 → 3", "Y₁ − Y₀"])
    def test_labels_and_unicode_subscripts_pass(self, text):
        assert check_text_formulas(scene(f"t = Text({text!r})")) is None

    def test_mathtex_is_never_flagged(self):
        assert check_text_formulas(scene(r'eq = MathTex(r"\bar{y}_T", "-", r"\bar{y}_C")')) is None

    def test_every_offending_line_is_listed(self):
        problem = check_text_formulas(scene('a = Text("y_T")', 'b = Text("=")', 'c = Text("ok")'))
        assert "line 7" in problem and "line 8" in problem and "line 9" not in problem


class TestTryRender:
    def test_a_plain_text_formula_fails_before_rendering(self, tmp_path, monkeypatch):
        monkeypatch.setattr(renderer.subprocess, "run", lambda *a, **k: pytest.fail("should not render"))
        ok, error, mp4, _ = renderer._try_render(tmp_path, scene('t = Text("y_T")'), "Seg0", "low", 1, 1.0)
        assert not ok and mp4 is None and "ONE MathTex" in error

    def test_the_template_fallback_is_not_checked(self, tmp_path, monkeypatch):
        class Rendered(Exception):
            pass

        def run(*a, **k):
            raise Rendered

        monkeypatch.setattr(renderer.subprocess, "run", run)
        with pytest.raises(Rendered):
            renderer._try_render(tmp_path, scene('t = Text("y_T")'), "Seg0", "low", 1, 1.0, check_formulas=False)


class TestLatexPreflight:
    def test_lists_what_is_missing(self, monkeypatch):
        monkeypatch.setattr(renderer.shutil, "which", lambda tool: None if tool == "dvisvgm" else "/bin/" + tool)
        assert renderer.missing_latex_tools() == ["dvisvgm"]

    def test_nothing_missing(self, monkeypatch):
        monkeypatch.setattr(renderer.shutil, "which", lambda tool: "/bin/" + tool)
        assert renderer.missing_latex_tools() == []


KEY = [TermColour(term="treated", colour="GREEN"), TermColour(term="control", colour="BLUE")]
SEG = Segment(phase="deliver", source_refs=REF, beats=[Beat(narration="The treated group.", visual="A green circle")])


class TestColourKey:
    def test_every_animation_prompt_carries_the_key(self):
        seg = RenderSegment(**SEG.model_dump(), colour_key=KEY)
        line = "Colour key for the whole video"
        assert line in format_beats(seg, [1.0])
        assert line in build_generation_prompt(seg, [1.0], "Seg0")[1]
        assert line in build_repair_prompt("code", "err", seg, [1.0], "Seg0")
        assert line in build_layout_repair_prompt("code", "probs", seg, [1.0], "Seg0")
        assert "treated = GREEN; control = BLUE" in format_beats(seg, [1.0])

    def test_a_segment_without_a_key_prompts_as_before(self):
        assert format_beats(SEG, [1.0]) == format_beats(RenderSegment(**SEG.model_dump()), [1.0])
        assert "Colour key" not in format_beats(SEG, [1.0])

    def test_the_key_changes_the_render_cache_input(self):
        with_key = RenderSegment(**SEG.model_dump(), colour_key=KEY).model_dump_json()
        swapped = RenderSegment(**SEG.model_dump(), colour_key=[KEY[0].model_copy(update={"colour": "BLUE"}), KEY[1].model_copy(update={"colour": "GREEN"})]).model_dump_json()
        assert with_key != swapped != SEG.model_dump_json()

    def test_old_scripts_load_with_an_empty_key(self):
        s = Script(ku_id="k", title="t", segments=[SEG])
        assert Script.model_validate_json(s.model_dump_json(exclude={"colour_key"})).colour_key == []

    def test_the_level_prompt_asks_for_the_key(self):
        for level in (1, 2, 3):
            assert "`colour_key`" in level_system_prompt(level) and "each with its own colour" in level_system_prompt(level)

    @pytest.mark.parametrize("key, problem", [
        ([TermColour(term="a", colour="RED"), TermColour(term="b", colour="RED")], "same colour"),
        ([TermColour(term="Treated", colour="RED"), TermColour(term="treated ", colour="BLUE")], "twice"),
        ([TermColour(term=c, colour=c) for c in ("RED", "BLUE", "GREEN", "GOLD", "PINK")], "max 4"),
    ])
    def test_a_clashing_key_is_rejected(self, key, problem):
        s = Script(ku_id="k", title="t", segments=[SEG], colour_key=key)
        assert any(problem in p for p in validate_script(s))

    def test_a_colour_outside_the_palette_is_a_schema_error(self):
        with pytest.raises(ValueError):
            TermColour(term="x", colour="BLUE_E")
