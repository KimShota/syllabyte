"""
Reading what students upload (plan/slide-uploads-plan.md): a syllabus (its text, the key that decides the shared
course, and its lecture list) and a slide deck (converted to PDF, rendered, and keyed by its content).

Only `read_schedule` calls an LLM. The keys are computed from what was read, never from the file's bytes, so a
re-downloaded or re-exported file with the same content gets the same key.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field
from syllabyte_common.llm import DEFAULT_MODEL, structured, text_block
from syllabyte_common.models import RunManifest, Slide, SlideDeck

from ingestion_agent.slide_parser import parse_slide_deck
from ingestion_agent.syllabus_parser import parse_syllabus


class UploadError(Exception):
    """A file the worker cannot read; the message is shown to the student."""


# --------------------------------------------------------------------------
# syllabus
# --------------------------------------------------------------------------

_PAGE_NUMBER = re.compile(r"(^|\s)(page\s*)?\d+(\s*(of|/)\s*\d+)?$")


def normalize_syllabus(text: str) -> str:
    """The syllabus's text with what differs between copies of the same syllabus taken out (U17): case,
    punctuation and spacing, page-number lines, and short lines that repeat once a trailing page number is ignored
    (page headers and footers: "Course syllabus 3" repeats "Course syllabus 1"). Dropping every such line is
    consistent: a copy without headers loses the same repeated lines as one with them. Other lines keep their numbers."""
    lines = [re.sub(r"\s+", " ", l).strip().lower() for l in text.splitlines()]
    lines = [l for l in lines if l and _PAGE_NUMBER.sub("", l).strip()]
    shape = {l: _PAGE_NUMBER.sub("", l).strip() for l in lines}
    repeats = Counter(shape[l] for l in lines if len(l) <= 80)
    lines = [l for l in lines if len(l) > 80 or repeats[shape[l]] < 2]
    words = re.sub(r"[^\w]+", " ", " ".join(lines))
    return re.sub(r"\s+", " ", words).strip()


def syllabus_key(text: str) -> str:
    return hashlib.sha256(normalize_syllabus(text).encode()).hexdigest()


class ScheduleLecture(BaseModel):
    n: int = Field(ge=1)
    title: str
    week: int | None = None


class SyllabusSchedule(BaseModel):
    course_code: str  # e.g. "CS-UH 2219E"; empty when the syllabus does not give one
    course_name: str
    lectures: list[ScheduleLecture]  # empty when the syllabus has no schedule of lectures


SCHEDULE_SYSTEM = """You read a university course syllabus and return its course code, course name and its schedule of lectures.

Rules:
- One entry per lecture (class meeting) in the order they are taught, numbered from 1. Use the syllabus's own topic for each title, shortened to under 60 characters.
- Set week when the syllabus says which week a lecture is in; otherwise null.
- Leave out exams, holidays, reading days and project deadlines: only lectures that teach something.
- If the syllabus lists topics by week rather than by lecture, make one lecture per week.
- If the syllabus has no schedule at all, return an empty list. Never invent lectures."""


def read_schedule(text: str, *, model: str = DEFAULT_MODEL, manifest: RunManifest | None = None) -> SyllabusSchedule:
    """The lecture list read from the syllabus (U2), with lectures renumbered 1..n in order."""
    out = structured(
        schema=SyllabusSchedule, content=[text_block(f"=== SYLLABUS ===\n{text}")], system=SCHEDULE_SYSTEM,
        stage="read_schedule", model=model, max_tokens=4000, manifest=manifest,
    )
    lectures = sorted(out.lectures, key=lambda l: l.n)
    out.lectures = [ScheduleLecture(n=i, title=l.title.strip()[:80], week=l.week) for i, l in enumerate(lectures, start=1)]
    return out


class SyllabusRead(BaseModel):
    text: str
    key: str


def read_syllabus(path: str | Path) -> SyllabusRead:
    try:
        doc = parse_syllabus(path)
    except ValueError as e:
        raise UploadError("A syllabus must be a PDF or Word (.docx) file.") from e
    except Exception as e:  # a damaged file
        raise UploadError("This syllabus file could not be opened.") from e
    if len(normalize_syllabus(doc.full_text)) < 200:
        raise UploadError("No text could be read from this syllabus. If it is a scan, upload a text PDF or a Word file.")
    return SyllabusRead(text=doc.full_text, key=syllabus_key(doc.full_text))


# --------------------------------------------------------------------------
# slide decks
# --------------------------------------------------------------------------


def to_pdf(path: str | Path, out_dir: str | Path) -> Path:
    """The deck as a PDF (U15): a PDF as it is, a PowerPoint converted with LibreOffice."""
    path, out_dir = Path(path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return path
    if suffix == ".key":
        raise UploadError("Keynote files can't be read. In Keynote, choose File > Export To > PDF, then upload the PDF.")
    if suffix != ".pptx":
        raise UploadError("Slides must be a PDF or PowerPoint (.pptx) file.")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise RuntimeError("LibreOffice (soffice) is needed on the worker to convert PowerPoint files")
    with tempfile.TemporaryDirectory() as profile:
        # a private profile, so two conversions at once do not lock each other out
        result = subprocess.run(
            [soffice, f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(path)],
            capture_output=True, timeout=180,
        )
    pdf = out_dir / (path.stem + ".pdf")
    if result.returncode != 0 or not pdf.exists():
        raise UploadError("This PowerPoint file could not be converted. Export it to PDF and upload that instead.")
    return pdf


def page_key(slide: Slide) -> str:
    """One page's text (spacing normalized) and rendered image."""
    h = hashlib.sha256()
    h.update(re.sub(r"\s+", " ", slide.text).strip().encode())
    h.update(b"\0")
    if slide.image_path:
        h.update(hashlib.sha256(Path(slide.image_path).read_bytes()).digest())
    return h.hexdigest()


def deck_content_key(deck: SlideDeck) -> str:
    """Each page's text (spacing normalized) and rendered image (U6): two copies of the same slides match."""
    h = hashlib.sha256()
    for slide in deck.slides:
        h.update(re.sub(r"\s+", " ", slide.text).strip().encode())
        h.update(b"\0")
        if slide.image_path:
            h.update(hashlib.sha256(Path(slide.image_path).read_bytes()).digest())
        h.update(b"\1")
    return h.hexdigest()


def first_title(deck: SlideDeck) -> str:
    """The first page's first line, for suggesting which lecture the deck is."""
    for slide in deck.slides[:2]:
        for line in slide.text.splitlines():
            if line.strip():
                return line.strip()[:120]
    return ""


class DeckRead(BaseModel):
    deck_name: str
    pdf_path: str
    content_key: str
    page_count: int
    first_title: str
    pages: list[str]  # each page's text
    # each page's key: a deck most of whose pages are already in the course is an updated version (V2)
    page_keys: list[str] = []


def read_deck(path: str | Path, work_dir: str | Path, deck_name: str) -> tuple[DeckRead, SlideDeck]:
    """Converts, renders and keys a deck. `deck_name` is how KUs and items cite its slides (the server's deck id)."""
    work_dir = Path(work_dir)
    pdf = to_pdf(path, work_dir / "pdf")
    try:
        parsed = parse_slide_deck(pdf, image_dir=work_dir / "images")
    except Exception as e:
        raise UploadError("This slide file could not be opened.") from e
    if not parsed.slides:
        raise UploadError("This slide file has no pages.")
    deck = SlideDeck(
        name=deck_name, source_path=str(pdf), has_images=parsed.has_images,
        slides=[s.model_copy(update={"deck_name": deck_name}) for s in parsed.slides],
    )
    read = DeckRead(
        deck_name=deck_name, pdf_path=str(pdf), content_key=deck_content_key(deck), page_count=len(deck.slides),
        first_title=first_title(deck), pages=[s.text for s in deck.slides], page_keys=[page_key(s) for s in deck.slides],
    )
    return read, deck
