"""Dialogue videos: the script checker, slang, the 70% frame, the caption band and the cache key."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from animation_agent.dialogue_band import band_size, band_timeline, chunk_words, colour_words, draw_band
from animation_agent.frame import DIALOGUE, FULL
from animation_agent.manim_config import write_manim_cfg
from animation_agent.manim_prompt import _build_system_prompt, build_generation_prompt
from animation_agent.tts import _attach_punctuation, estimate_words
from script_generation_agent.prompts import dialogue_critique_system_prompt, dialogue_system_prompt
from script_generation_agent.script_writer import validate_dialogue
from script_generation_agent.slang import find_slang, lexicon_for_prompt, max_slang
from syllabyte_common.cast import CastError, load_cast
from syllabyte_common.models import (
    DialogueScript,
    RenderSegment,
    Script,
    SegmentAudio,
    TermColour,
    WordTiming,
    load_script,
)

REF = [{"deck_name": "d", "slide_number": 1}]


def beat(narration, speaker, step, misconception=False):
    return {"narration": narration, "visual": "a box", "speaker": speaker, "step": step, "misconception": misconception}


def _segments():
    filler = " ".join(["the vector keeps its direction"] * 2)
    return [
        {"phase": "prepare", "source_refs": REF, "beats": [
            beat("Peter, why do some vectors never turn when the matrix hits them?", "peer", "question"),
        ]},
        {"phase": "initiate", "source_refs": REF, "beats": [
            beat("By the end you can say what an eigenvector is and find its eigenvalue.", "explainer", "objective"),
        ]},
        {"phase": "deliver", "source_refs": REF, "beats": [
            beat("Okay so what does the matrix do to a vector, lowkey?", "explainer", "question"),
            beat("Not gonna lie, I think every vector gets rotated by the matrix.", "peer", "answer", True),
            beat(f"Not every one: an eigenvector only gets scaled, because {filler}.", "explainer", "feedback"),
            beat(f"So the eigenvector stays on its own line, and {filler}.", "explainer", "build"),
            beat(f"Pause and guess how much longer it gets, since {filler}.", "peer", "predict"),
            beat(f"It gets longer by the eigenvalue, lambda, which is two here and {filler}.", "explainer", "build"),
        ]},
        {"phase": "deliver", "source_refs": REF, "beats": [
            beat("Wait, for real, why does the second vector turn then?", "peer", "question"),
            beat(f"Because it is not an eigenvector, so the matrix mixes its parts and {filler}.", "explainer", "feedback"),
            beat(f"Look at its new arrow: it points somewhere else entirely and {filler}.", "explainer", "build"),
            beat(f"Okay so the first one is special, it is giving a straight line, {filler}.", "peer", "build"),
        ]},
        {"phase": "end", "source_refs": REF, "beats": [
            beat("So an eigenvector keeps its direction and only gets scaled by the eigenvalue.", "peer", "check"),
            beat("Exactly, its direction stays and its length changes by lambda.", "explainer", "check"),
        ]},
    ]


def make_script(**changes) -> DialogueScript:
    data = {"ku_id": "ku-eigen", "title": "Eigenvectors", "style": "dialogue", "segments": _segments(),
            "colour_key": [{"term": "eigenvector", "colour": "YELLOW"}, {"term": "matrix", "colour": "BLUE"}]}
    data.update(changes)
    return DialogueScript.model_validate(data)


def test_valid_dialogue_passes():
    script = make_script()
    assert 150 <= script.word_count <= 250
    assert validate_dialogue(script) == []


def _with(mutate) -> list[str]:
    segments = copy.deepcopy(_segments())
    mutate(segments)
    return validate_dialogue(make_script(segments=segments))


def test_misconception_must_be_corrected_next():
    def swap(segs):
        d1 = segs[2]["beats"]
        d1[2], d1[3] = d1[3], d1[2]  # the correction no longer follows the wrong answer
    assert any("must be the explainer's feedback" in p and "explainer build -> explainer feedback" in p for p in _with(swap))

    def predict_between(segs):
        d1 = segs[2]["beats"]
        d1.insert(2, d1.pop(4))  # question, wrong answer, predict, feedback, ...
    assert not any("misconception" in p for p in _with(predict_between))


def test_first_deliver_needs_a_misconception():
    def drop(segs):
        segs[2]["beats"][1]["misconception"] = False
    assert any("needs the peer's misconception" in p for p in _with(drop))


def test_only_peer_answers_are_misconceptions():
    def explainer_wrong(segs):
        segs[2]["beats"][1]["speaker"] = "explainer"
    assert any("only the peer's answer" in p for p in _with(explainer_wrong))


def test_exactly_one_predict_line_before_its_answer():
    def none(segs):
        segs[2]["beats"][4]["step"] = "build"
    assert any("exactly one \"predict\"" in p for p in _with(none))

    def last(segs):
        segs[2]["beats"][4]["step"], segs[2]["beats"][5]["step"] = "build", "predict"
    assert any("must come before" in p for p in _with(last))


def test_no_slang_in_check_or_objective_lines():
    def slangy(segs):
        segs[4]["beats"][0]["narration"] = "No cap, an eigenvector keeps its direction and only gets scaled."
    assert any("takes no slang" in p for p in _with(slangy))


def test_too_much_and_too_little_slang():
    def flood(segs):
        for seg in segs[2:4]:
            for b in seg["beats"]:
                b["narration"] = "No cap, bet, lowkey, " + b["narration"]
    assert any("slang phrases for" in p for p in _with(flood))

    def none(segs):
        for seg in segs:
            for b in seg["beats"]:
                for phrase in ("Not gonna lie, ", "lowkey", "for real, ", "it is giving a straight line, "):
                    b["narration"] = b["narration"].replace(phrase, "")
    assert any("slang phrase(s) from the list" in p for p in _with(none))


def test_turns_and_ending():
    def monologue(segs):
        for b in segs[3]["beats"]:
            b["speaker"] = "explainer"
    problems = _with(monologue)
    assert any("both characters must speak in the second deliver" in p for p in problems)
    assert any("more than 3 beats in a row" in p for p in problems)

    def no_restatement(segs):
        segs[4]["beats"][0]["speaker"] = "explainer"
    assert any("the peer restating the idea" in p for p in _with(no_restatement))


def test_find_slang_whole_words_and_apostrophes():
    assert find_slang("Is it between the two?") == []
    assert find_slang("Bet. It’s giving recursion, and it's giving loops.") == ["it's giving", "it's giving", "bet"]
    assert find_slang("NO CAP") == ["no cap"]
    assert max_slang(10) == 4 and max_slang(2) == 2


def test_load_script_picks_the_class():
    dialogue = make_script()
    assert type(load_script(dialogue.model_dump_json())) is DialogueScript
    mono = Script(ku_id="k", title="t", segments=[{"phase": "end", "source_refs": REF, "beats": [{"narration": "a", "visual": "b"}]}])
    assert type(load_script(mono.model_dump_json())) is Script


def test_dialogue_prompts_name_the_characters():
    prompt = dialogue_system_prompt(1, ["Matrices"], explainer="Ada", peer="Bo", lexicon=lexicon_for_prompt())
    assert "Ada (speaker \"explainer\")" in prompt and "Bo (speaker \"peer\")" in prompt
    assert "Ada recaps it" in prompt and "Bo asks how to do the first step" in prompt
    assert "Bo poses ONE \"what if\"" in dialogue_system_prompt(3, [], explainer="Ada", peer="Bo", lexicon="")
    assert "\"the math is mathing\"" in prompt
    assert "molecule" not in prompt  # CS and maths only
    critique = dialogue_critique_system_prompt(1, explainer="Ada", peer="Bo")
    assert "is teaching, not an error" in critique


# -- the 70% frame ------------------------------------------------------------


def test_manim_cfg_for_each_frame(tmp_path):
    write_manim_cfg(tmp_path, "high", "dialogue")
    cfg = (tmp_path / "manim.cfg").read_text()
    assert "pixel_width = 1080" in cfg and "pixel_height = 1344" in cfg and "frame_height = 5.6" in cfg
    write_manim_cfg(tmp_path, "low")
    assert "pixel_height = 960" in (tmp_path / "manim.cfg").read_text()
    for frame in (FULL, DIALOGUE):
        for w, h in frame.pixels.values():
            assert w / h == pytest.approx(frame.width / frame.height)


def test_codegen_prompt_uses_the_segments_frame():
    seg = RenderSegment(phase="deliver", source_refs=REF, beats=[{"narration": "a", "visual": "b"}], frame="dialogue")
    system, _ = build_generation_prompt(seg, [2.0], "Seg0")
    assert "4.5 units wide x 5.6 units tall" in system and "TOP 70%" in system
    assert "8.0 units tall" in _build_system_prompt("Seg0") and "TOP 70%" not in _build_system_prompt("Seg0")


# -- voices, captions and the band ---------------------------------------------


def test_kokoro_punctuation_joins_the_word():
    words = _attach_punctuation([("Peter", 0.1, 0.4), (",", 0.4, 0.45), ("why", None, 0.7), ("?", 0.7, 0.8)])
    assert [(w.word, w.start) for w in words] == [("Peter,", 0.1), ("why?", 0.45)]
    est = estimate_words("ab abcd", 3.0)
    assert est[1].start == pytest.approx(1.0) and est[1].end == pytest.approx(3.0)


def test_chunks_break_at_punctuation_and_length():
    words = [WordTiming(word=w, start=i, end=i + 1) for i, w in enumerate("Peter, why do some vectors never turn?".split())]
    assert [[words[i].word for i in c] for c in chunk_words(words)] == [["Peter,"], ["why", "do", "some"], ["vectors", "never"], ["turn?"]]


def test_caption_colours_follow_the_colour_key():
    key = [TermColour(term="eigenvector", colour="YELLOW"), TermColour(term="column space", colour="BLUE")]
    colours = colour_words(["THE", "EIGENVECTORS,", "column", "space"], key)
    assert colours[0] == (255, 255, 255) and colours[1] != colours[0] and colours[2] == colours[3] != colours[0]
    # Terms written longer than the lines say them still match by their leading words, but not by a short one.
    key = [TermColour(term="eigenvalue λ scaling", colour="ORANGE"), TermColour(term="zero vector / excluded case", colour="RED")]
    colours = colour_words(["the", "eigenvalue", "of", "zero", "vector", "is", "zero"], key)
    white = (255, 255, 255)
    assert colours[1] != white and colours[3] == colours[4] != white and colours[6] == white


def _cast_dir(tmp_path: Path) -> Path:
    for name, size in (("a.png", (40, 80)), ("b.png", (60, 60))):
        Image.new("RGBA", size, (200, 100, 50, 255)).save(tmp_path / name)
    (tmp_path / "cast.json").write_text(json.dumps({
        "explainer": {"name": "Ada", "image": "a.png", "voice": "am_michael", "side": "right"},
        "peer": {"name": "Bo", "image": "b.png", "voice": "bm_george", "side": "left"},
    }))
    return tmp_path


def test_band_timeline_covers_the_narration(tmp_path):
    script = make_script()
    audios, t = [], 0.0
    for i, seg in enumerate(script.segments):
        durations = [2.0] * len(seg.beats)
        words = [estimate_words(b.narration, 1.8) for b in seg.beats]
        audios.append(SegmentAudio(segment_index=i, wav_path="-", duration_seconds=sum(durations), srt_start=t,
                                   srt_end=t + sum(durations), beat_durations=durations, beat_words=words))
        t += sum(durations)
    states = band_timeline(script, audios)
    assert states[0].start == 0 and states[-1].end == pytest.approx(t)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(states, states[1:]))
    spoken = " ".join(b.narration for seg in script.segments for b in seg.beats).upper().split()
    assert [w.text for s in states for w in s.words] == spoken  # captions show exactly what is said

    cast = load_cast(_cast_dir(tmp_path))
    image = draw_band(states[0], cast, *band_size("low"), cast_dir=tmp_path)
    assert image.size == (540, 288)


def test_cast_needs_two_sides(tmp_path):
    d = _cast_dir(tmp_path)
    data = json.loads((d / "cast.json").read_text())
    data["peer"]["side"] = "right"
    (d / "cast.json").write_text(json.dumps(data))
    with pytest.raises(CastError):
        load_cast(d)


def test_dialogue_videos_have_their_own_cache_key(tmp_path, monkeypatch):
    from test_video_jobs import course

    from syllabyte_common.video_jobs import video_key

    cast_dir = tmp_path / "cast"
    cast_dir.mkdir()
    _cast_dir(cast_dir)
    monkeypatch.setenv("SYLLABYTE_CAST_DIR", str(cast_dir))
    corpus, ku = course(tmp_path)
    mono = video_key(corpus, ku, 2, [])
    assert mono == video_key(corpus, ku, 2, [], style="monologue")  # monologue keys are unchanged
    dialogue = video_key(corpus, ku, 2, [], style="dialogue")
    assert dialogue != mono
    Image.new("RGBA", (10, 10)).save(cast_dir / "a.png")  # a new explainer image remakes the video
    assert video_key(corpus, ku, 2, [], style="dialogue") != dialogue
