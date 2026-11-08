"""Small previews of the student's original pages. No model calls or invented content."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from collections.abc import Callable

import pymupdf
from docx import Document
from pptx import Presentation

from ingestion_agent.slide_parser import _extract_pptx_text

MAX_PAGES = 2000
MAX_SIDE = 1200


def _pdf_pages(path: Path, out: Path, send: Callable[[int, Path], None]) -> list[dict]:
    pages = []
    with pymupdf.open(path) as doc:
        if doc.needs_pass or not 0 < len(doc) <= MAX_PAGES:
            raise ValueError("This document cannot be previewed.")
        for n, page in enumerate(doc, 1):
            scale = MAX_SIDE / max(page.rect.width, page.rect.height)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
            image = out / f"{n}.jpg"
            pix.save(image, jpg_quality=80)
            send(n, image)
            pages.append({"n": n, "text": page.get_text()[:2000], "image": True})
    return pages


def _office_pdf(path: Path, out: Path) -> Path | None:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        return None
    # A private profile lets preview conversions run beside the ingestion worker's conversions.
    try:
        subprocess.run([executable, f"-env:UserInstallation={(out / 'office-profile').resolve().as_uri()}",
                        "--headless", "--convert-to", "pdf", "--outdir", str(out), str(path)],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    pdf = out / (path.stem + ".pdf")
    return pdf if pdf.exists() else None


def render_material(path: Path, out: Path, send: Callable[[int, Path], None]) -> dict:
    """Publish every PDF/converted Office page; use labeled extracted text if Office rendering is unavailable."""
    out.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return {"unit": "page", "pages": _pdf_pages(path, out, send)}
    if suffix not in (".pptx", ".docx"):
        raise ValueError("Unsupported preview format.")
    converted = _office_pdf(path, out)
    if converted:
        return {"unit": "slide" if suffix == ".pptx" else "page", "pages": _pdf_pages(converted, out, send)}
    if suffix == ".pptx":
        texts = [_extract_pptx_text(slide.shapes) for slide in Presentation(str(path)).slides]
        unit = "slide"
    else:
        doc = Document(str(path))
        texts = [p.text for p in doc.paragraphs if p.text.strip()]
        texts += ["\n".join(" | ".join(c.text for c in row.cells) for row in t.rows) for t in doc.tables]
        unit = "section"  # DOCX has no fixed pagination without a layout engine.
    if not 0 < len(texts) <= MAX_PAGES:
        raise ValueError("No preview content was found.")
    return {"unit": unit, "pages": [{"n": n, "text": text[:2000], "image": False} for n, text in enumerate(texts, 1)]}
