"""Slide images go to the model scaled to a long edge of LLM_IMAGE_LONG_EDGE px; the file on disk is left as it is."""

import base64
from io import BytesIO

from PIL import Image

from syllabyte_common import llm


def _png(path, size):
    Image.new("RGB", size, "white").save(path)
    return path


def _sent_size(block):
    return Image.open(BytesIO(base64.b64decode(block["source"]["data"]))).size


def test_a_large_slide_is_sent_at_the_long_edge_and_keeps_its_shape(tmp_path):
    slide = _png(tmp_path / "slide.png", (4000, 2250))
    assert _sent_size(llm.image_block(slide)) == (llm.LLM_IMAGE_LONG_EDGE, round(2250 * llm.LLM_IMAGE_LONG_EDGE / 4000))
    assert Image.open(slide).size == (4000, 2250)  # the stored render (and the deck hashes made from it) is unchanged


def test_a_portrait_page_is_scaled_by_its_height(tmp_path):
    page = _png(tmp_path / "page.png", (1700, 2200))
    w, h = _sent_size(llm.image_block(page))
    assert h == llm.LLM_IMAGE_LONG_EDGE and w < h


def test_a_small_image_is_sent_byte_for_byte(tmp_path):
    frame = _png(tmp_path / "frame.png", (854, 480))
    assert base64.b64decode(llm.image_block(frame)["source"]["data"]) == frame.read_bytes()


def test_an_edge_of_zero_sends_the_image_as_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "LLM_IMAGE_LONG_EDGE", 0)
    slide = _png(tmp_path / "slide.png", (4000, 2250))
    assert base64.b64decode(llm.image_block(slide)["source"]["data"]) == slide.read_bytes()


def test_a_changed_file_is_scaled_again_not_served_from_the_cache(tmp_path):
    slide = _png(tmp_path / "slide.png", (4000, 2250))
    llm.image_block(slide)
    _png(slide, (3000, 3000))
    assert _sent_size(llm.image_block(slide)) == (llm.LLM_IMAGE_LONG_EDGE, llm.LLM_IMAGE_LONG_EDGE)


def test_a_file_pillow_cant_read_is_sent_as_it_is(tmp_path):
    odd = tmp_path / "odd.png"
    odd.write_bytes(b"not really a png")
    assert base64.b64decode(llm.image_block(odd)["source"]["data"]) == b"not really a png"
