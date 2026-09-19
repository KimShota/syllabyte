"""
Slide Parser — Component 1 (Ingestion Agent), Week-1 scope.

Extracts per-slide text (+ speaker notes, + a rendered PNG when possible)
from a course slide deck, whether it's a PDF or a PowerPoint (.pptx).

  - PDF decks: PyMuPDF gives us text and a rendered PNG per page directly —
    no external tools needed.
  - PPTX decks: python-pptx gives us text (shape text frames) and speaker
    notes with no external tools. Rendered slide *images* require converting
    to PDF first — if LibreOffice (`soffice`) is on PATH, we do that
    automatically; if not, the deck is still fully usable for grounding, just
    without a visual image per slide (`SlideDeck.has_images = False`), and a
    warning is printed suggesting `brew install --cask libreoffice`.

Usage:
    from ingestion_agent.slide_parser import parse_slide_deck
    deck = parse_slide_deck("slides/lecture01.pdf", image_dir="runs/x/images")
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf  # PyMuPDF
from pptx import Presentation

from syllabyte_common.models import Slide, SlideDeck

RENDER_DPI = 150


def _render_pdf_pages_to_png(pdf_path: Path, image_dir: Path, deck_name: str) -> list[Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    zoom = RENDER_DPI / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    with pymupdf.open(pdf_path) as pdf:
        for i, page in enumerate(pdf, start=1):
            pix = page.get_pixmap(matrix=matrix)
            out_path = image_dir / f"{deck_name}_slide{i:03d}.png"
            pix.save(out_path)
            paths.append(out_path)
    return paths


def _parse_pdf_deck(path: Path, image_dir: Path | None, deck_name: str) -> SlideDeck:
    slides: list[Slide] = []
    image_paths: list[Path] = []
    if image_dir is not None:
        image_paths = _render_pdf_pages_to_png(path, image_dir, deck_name)

    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf, start=1):
            text = page.get_text("text")
            image_path = str(image_paths[i - 1]) if image_paths else None
            slides.append(
                Slide(deck_name=deck_name, slide_number=i, text=text, image_path=image_path)
            )

    return SlideDeck(
        name=deck_name, source_path=str(path), slides=slides, has_images=bool(image_paths)
    )


def _extract_pptx_text(shapes) -> str:
    chunks = []
    for shape in shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                chunks.append(text)
        if shape.shape_type == 19 and shape.has_table:  # MSO_SHAPE_TYPE.TABLE
            for row in shape.table.rows:
                chunks.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(chunks)


def _try_convert_pptx_to_pdf(pptx_path: Path, out_dir: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx_path)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[slide_parser] LibreOffice conversion failed for {pptx_path.name}: {e}", file=sys.stderr)
        return None
    pdf_path = out_dir / (pptx_path.stem + ".pdf")
    return pdf_path if pdf_path.exists() else None


def _parse_pptx_deck(path: Path, image_dir: Path | None, deck_name: str) -> SlideDeck:
    # Try to get real slide images by round-tripping through LibreOffice.
    if image_dir is not None:
        with tempfile.TemporaryDirectory() as tmp:
            converted_pdf = _try_convert_pptx_to_pdf(path, Path(tmp))
            if converted_pdf is not None:
                deck = _parse_pdf_deck(converted_pdf, image_dir, deck_name)
                # Prefer python-pptx's own text extraction (cleaner than
                # PyMuPDF's PDF-text-layer extraction) and layer in notes.
                prs = Presentation(str(path))
                for slide_model, pptx_slide in zip(deck.slides, prs.slides):
                    slide_model.text = _extract_pptx_text(pptx_slide.shapes) or slide_model.text
                    if pptx_slide.has_notes_slide:
                        slide_model.notes = pptx_slide.notes_slide.notes_text_frame.text
                deck.source_path = str(path)
                return deck

    print(
        f"[slide_parser] No LibreOffice found — parsing '{path.name}' as text-only "
        "(no slide images). Install with `brew install --cask libreoffice` for "
        "image-grounded script generation.",
        file=sys.stderr,
    )
    prs = Presentation(str(path))
    slides: list[Slide] = []
    for i, pptx_slide in enumerate(prs.slides, start=1):
        notes = ""
        if pptx_slide.has_notes_slide:
            notes = pptx_slide.notes_slide.notes_text_frame.text
        slides.append(
            Slide(
                deck_name=deck_name,
                slide_number=i,
                text=_extract_pptx_text(pptx_slide.shapes),
                notes=notes,
            )
        )
    return SlideDeck(name=deck_name, source_path=str(path), slides=slides, has_images=False)


def parse_slide_deck(path: str | Path, image_dir: str | Path | None = None) -> SlideDeck:
    path = Path(path)
    deck_name = path.stem
    image_dir = Path(image_dir) if image_dir is not None else None
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf_deck(path, image_dir, deck_name)
    elif suffix == ".pptx":
        return _parse_pptx_deck(path, image_dir, deck_name)
    else:
        raise ValueError(f"Unsupported slide deck format: {suffix}. Expected .pdf or .pptx")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m ingestion_agent.slide_parser <deck.pdf|.pptx> [image_out_dir]")
        sys.exit(1)

    img_dir = sys.argv[2] if len(sys.argv) > 2 else None
    deck = parse_slide_deck(sys.argv[1], img_dir)
    print(f"Parsed '{deck.name}': {len(deck.slides)} slides, has_images={deck.has_images}")
    for s in deck.slides[:3]:
        print(f"--- slide {s.slide_number} ---")
        print(s.text[:200], "...")
