from pathlib import Path

import httpx
import json
import pymupdf
import pytest
from docx import Document
from pptx import Presentation
from ingestion_agent import material_previews
from ingestion_agent.material_previews import render_material
from ingestion_agent.worker import Worker


def pdf(path: Path):
    with pymupdf.open() as doc:
        for text in ("Stacks: LIFO", "Queues: FIFO"):
            page = doc.new_page(width=720, height=405)
            page.insert_text((40, 40), text)
            page.draw_rect(pymupdf.Rect(80, 80, 200, 200), fill=(1, 0, 0))
        doc.save(path)
    return path


def test_renders_each_original_pdf_page_and_preserves_its_text_and_aspect(tmp_path):
    images = []
    result = render_material(pdf(tmp_path / "stacks.pdf"), tmp_path / "out", lambda n, p: images.append((n, p.read_bytes())))
    assert result["unit"] == "page"
    assert [p["text"].strip() for p in result["pages"]] == ["Stacks: LIFO", "Queues: FIFO"]
    assert [n for n, _ in images] == [1, 2]
    for _, image in images:
        pix = pymupdf.Pixmap(image)
        assert pix.width == 1200 and pix.height == 675
        assert image[:2] == b"\xff\xd8" and image[-2:] == b"\xff\xd9"
        # The red shape from the original page is in the preview, not a placeholder image.
        r, g, b = pix.pixel(200, 200)
        assert r > 200 and g < 30 and b < 30


def test_scanned_pdf_pages_still_have_real_images(tmp_path):
    path = tmp_path / "scan.pdf"
    with pymupdf.open() as doc:
        doc.new_page().draw_rect(pymupdf.Rect(50, 50, 100, 100), fill=(0, 0, 0))
        doc.save(path)
    images = []
    result = render_material(path, tmp_path / "out", lambda n, p: images.append(p.read_bytes()))
    assert result["pages"] == [{"n": 1, "text": "", "image": True}]
    assert images


def test_office_fallback_uses_only_the_uploaded_text_and_labels_docx_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(material_previews, "_office_pdf", lambda *a: None)
    deck = Presentation()
    for text in ("Stack API", "Queue API"):
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(0, 0, 1000000, 1000000).text = text
    path = tmp_path / "slides.pptx"
    deck.save(path)
    result = render_material(path, tmp_path / "out", lambda *a: pytest.fail("No image should be invented"))
    assert result == {"unit": "slide", "pages": [{"n": 1, "text": "Stack API", "image": False}, {"n": 2, "text": "Queue API", "image": False}]}
    doc = Document()
    doc.add_paragraph("Algorithms syllabus")
    doc.add_paragraph("Week 1: stacks and queues")
    path = tmp_path / "syllabus.docx"
    doc.save(path)
    result = render_material(path, tmp_path / "word", lambda *a: None)
    assert result["unit"] == "section"
    assert [p["text"] for p in result["pages"]] == ["Algorithms syllabus", "Week 1: stacks and queues"]


def test_preview_worker_uploads_pages_before_publishing_the_manifest(tmp_path):
    source = pdf(tmp_path / "lecture.pdf").read_bytes()
    calls = []
    job = {"id": "preview-1", "kind": "preview", "payload": {"file_id": "file-1"}, "file_name": "lecture.pdf"}

    def server(request):
        calls.append((request.url.path, request.content))
        if request.url.path.endswith("/claim"):
            return httpx.Response(200, json={"job": job})
        if request.url.path.endswith("/file"):
            return httpx.Response(200, content=source)
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(base_url="http://server", transport=httpx.MockTransport(server))
    assert Worker(client, tmp_path / "worker").run_once()
    pages = [c for c in calls if "/pages/" in c[0]]
    assert len(pages) == 2 and all(data.startswith(b"\xff\xd8") for _, data in pages)
    assert calls[-1][0].endswith("/preview")
    assert len(json.loads(calls[-1][1])["result"]["pages"]) == 2
    assert not (tmp_path / "worker" / "preview-1").exists()


def test_unreadable_preview_does_not_make_model_calls(tmp_path):
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a pdf")
    with pytest.raises(Exception):
        render_material(source, tmp_path / "out", lambda *a: None)
