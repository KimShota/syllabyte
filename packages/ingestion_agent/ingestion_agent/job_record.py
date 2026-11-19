"""
A record of every video job the worker runs (videos and misconception clips): what it printed, line by line with the
time, how long each phase and pipeline step took, every model call with its tokens and cost, the program attempts and
why each was redrawn, every error with its traceback, and the small files the pipeline left (script, diagnostics,
manifests). The work folder is deleted after a job; its record stays.

    <work-dir>/records/<YYYYmmdd-HHMMSS>_<kind>_<ku>_L<level>_<job>/
        record.json   the summary: phases, steps, calls, cost by stage, errors, the video's facts
        log.txt       every line the job printed, with seconds since it started
        artifacts/    the job's small files (.json .txt .srt .vtt .log .py, up to 2 MB each)
    <work-dir>/records/index.jsonl   one line per job, to compare them (scripts/video_records.py prints them)

Three videos run at once in one worker (threads), and a video's pipeline starts threads of its own (voices, segment
renders, questions). A line is the job's when its thread runs that job's work: install() tees stdout and stderr and
makes ThreadPoolExecutor tasks inherit the job they were submitted from. Output of subprocesses (ffmpeg) goes to the
terminal only.
"""

from __future__ import annotations

import contextvars
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from syllabyte_common.llm import call_cost_usd

_current: contextvars.ContextVar[JobRecorder | None] = contextvars.ContextVar("syllabyte_job_record", default=None)
_patched = False
_install_lock = threading.Lock()


def current() -> JobRecorder | None:
    """The record of the job this thread is working for, if it keeps one."""
    return _current.get()

KEEP_SUFFIXES = {".json", ".txt", ".srt", ".vtt", ".log", ".py"}
KEEP_MAX_BYTES = 2_000_000

_STEP = re.compile(r"\[(\d)/6\] (\w+)")
_SEGMENT = re.compile(r"segment (\d+): tier=(\S+) attempts=(\d+) \(([\d.]+)s\)")
_PROGRAM = re.compile(r"program (\d+): (\d+) lines; snapshots (.*)")
_NOTABLE = re.compile(r"error|failed|traceback|exception|warning|fell back|could not|can't|over the limit|cut off|retry", re.I)


class _Tee:
    """A stream that writes through to the real one and copies each line to the job running in this thread."""

    def __init__(self, stream, name: str):
        self._stream = stream
        self._name = name

    def write(self, text: str) -> int:
        n = self._stream.write(text)
        if (rec := _current.get()) is not None:
            rec._text(self._name, text)
        return n

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, attr):
        return getattr(self._stream, attr)


def install() -> None:
    """Tees stdout/stderr (again whenever something replaced them) and, once per process, makes thread-pool tasks
    belong to the job that submitted them. Run by every recorder as its job starts."""
    global _patched
    with _install_lock:
        if not isinstance(sys.stdout, _Tee):
            sys.stdout = _Tee(sys.stdout, "out")
        if not isinstance(sys.stderr, _Tee):
            sys.stderr = _Tee(sys.stderr, "err")
        if _patched:
            return
        submit = ThreadPoolExecutor.submit

        def submit_in_job(self, fn, /, *args, **kwargs):
            if _current.get() is None:
                return submit(self, fn, *args, **kwargs)
            return submit(self, contextvars.copy_context().run, fn, *args, **kwargs)

        ThreadPoolExecutor.submit = submit_in_job
        _patched = True


class JobRecorder:
    """One job's record, filled while it runs and written by finish()."""

    def __init__(self, records_dir: Path, kind: str, job_id: str, payload: dict):
        self.records_dir = Path(records_dir)
        self.kind, self.job_id, self.payload = kind, job_id, payload
        self.started = time.time()
        self.lines: list[tuple[float, str, str]] = []  # (unix time, stream, line)
        self.phases: list[dict] = []
        self.errors: list[dict] = []
        self.uploads: list[dict] = []
        self._partial: dict[str, str] = {}
        self._lock = threading.Lock()
        self._token: contextvars.Token | None = None

    # ---- while the job runs

    def __enter__(self) -> JobRecorder:
        install()
        self._token = _current.set(self)
        return self

    def __exit__(self, *exc) -> None:
        if self._token is not None:
            _current.reset(self._token)
            self._token = None

    def _text(self, stream: str, text: str) -> None:
        # print() writes the text and the newline separately, so each thread keeps its own unfinished line: the job's
        # segment renders print at the same time
        key = f"{stream}:{threading.get_ident()}"
        with self._lock:
            buf = self._partial.get(key, "") + text
            *done, rest = buf.split("\n")
            self._partial[key] = rest
            now = time.time()
            self.lines.extend((now, stream, line) for line in done if line.strip())

    @contextmanager
    def phase(self, name: str):
        """Times one phase of the job (downloading its slides, rendering the deck, the pipeline, sending files)."""
        start = time.time()
        entry = {"phase": name, "start_s": round(start - self.started, 2)}
        try:
            yield entry
            entry["ok"] = True
        except BaseException as e:
            entry["ok"] = False
            entry["error"] = repr(e)
            raise
        finally:
            entry["seconds"] = round(time.time() - start, 2)
            with self._lock:
                self.phases.append(entry)

    def upload(self, name: str, file: Path, seconds: float) -> None:
        size = file.stat().st_size if file.exists() else None
        with self._lock:
            self.uploads.append({"file": name, "bytes": size, "seconds": round(seconds, 2)})

    def error(self, where: str, e: BaseException) -> None:
        with self._lock:
            self.errors.append({"where": where, "error": repr(e), "at_s": round(time.time() - self.started, 2),
                                "traceback": "".join(traceback.format_exception(e))})

    # ---- at the end

    def finish(self, *, status: str, manifest, work: Path, total_cost: float | None = None) -> Path | None:
        """Writes the record (record.json, log.txt, artifacts/) and its line in index.jsonl; returns its folder. A
        record that can't be written is reported, never raised: the job's own outcome is what matters."""
        try:
            return self._write(status, manifest, Path(work), total_cost)
        except Exception as e:  # noqa: BLE001
            print(f"[record] {self.kind} {self.job_id}: the record could not be written: {e!r}", file=sys.__stderr__, flush=True)
            return None

    def _write(self, status: str, manifest, work: Path, total_cost: float | None) -> Path:
        ended = time.time()
        with self._lock:
            for stream, rest in self._partial.items():
                if rest.strip():
                    self.lines.append((ended, stream.split(":")[0], rest))
            self._partial.clear()
            lines = sorted(self.lines, key=lambda t: t[0])
        ku = (self.payload.get("ku") or {}).get("id") or self.payload.get("ku_id") or "ku"
        level = self.payload.get("level", "")
        stamp = datetime.fromtimestamp(self.started).strftime("%Y%m%d-%H%M%S")
        folder = self.records_dir / f"{stamp}_{self.kind}_{_safe(ku)}_L{level}_{self.job_id[:8]}"
        folder.mkdir(parents=True, exist_ok=True)

        calls = [self._call(c) for c in getattr(manifest, "llm_calls", [])]
        artifacts = self._keep_artifacts(work, folder / "artifacts") + _move_programs(ku, folder / "artifacts" / "programs")
        facts = self._video_facts(work)
        record = {
            "job_id": self.job_id, "kind": self.kind, "status": status, "ku_id": ku, "level": level,
            "lecture_n": self.payload.get("lecture_n"), "course": self.payload.get("course_name"),
            "started": datetime.fromtimestamp(self.started).isoformat(timespec="seconds"),
            "ended": datetime.fromtimestamp(ended).isoformat(timespec="seconds"),
            "wall_seconds": round(ended - self.started, 2),
            "cost_usd": round(sum(c["cost_usd"] for c in calls), 5),
            "cost_usd_reported": None if total_cost is None else round(total_cost, 5),
            "llm_calls": len(calls),
            "llm_seconds": round(sum(c["wall_seconds"] for c in calls), 2),
            "tokens": {k: sum(c[k] for c in calls) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")},
            "phases": self.phases,
            "steps": _steps(lines, self.started, ended),
            "cost_by_stage": _by_stage(calls),
            "calls": calls,
            "programs": _programs(lines, self.started),
            "segments": _segments(lines),
            "uploads": self.uploads,
            "errors": self.errors,
            "notable_lines": [{"at_s": round(t - self.started, 2), "line": line} for t, _, line in lines if _NOTABLE.search(line)],
            "video": facts,
            "artifacts": artifacts,
            "payload": {k: v for k, v in self.payload.items() if k not in ("ku", "syllabus_text")},
        }
        (folder / "record.json").write_text(json.dumps(record, indent=2, default=str))
        (folder / "log.txt").write_text("".join(f"{t - self.started:9.2f}s {stream} | {line}\n" for t, stream, line in lines))
        summary = {k: record[k] for k in ("started", "kind", "status", "ku_id", "level", "wall_seconds", "cost_usd", "llm_calls", "llm_seconds")}
        summary.update(redraws=max(0, len(record["programs"]["attempts"]) - 1), errors=len(self.errors),
                       video_seconds=facts.get("duration_s"), record=folder.name)
        with self._lock, (self.records_dir / "index.jsonl").open("a") as f:
            f.write(json.dumps(summary) + "\n")
        return folder

    def _call(self, c) -> dict:
        return {
            "stage": c.stage, "model": c.model, "ku_id": c.ku_id,
            "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
            "cache_read_tokens": c.cache_read_tokens, "cache_creation_tokens": c.cache_creation_tokens,
            "wall_seconds": round(c.wall_seconds, 2), "cost_usd": round(call_cost_usd(c), 5),
            "finished_s": round(c.finished_at - self.started, 2) if getattr(c, "finished_at", 0) else None,
        }

    def _keep_artifacts(self, work: Path, into: Path) -> list[str]:
        kept = []
        if not work.exists():
            return kept
        for f in sorted(work.rglob("*")):
            if f.is_file() and f.suffix.lower() in KEEP_SUFFIXES and f.stat().st_size <= KEEP_MAX_BYTES:
                rel = f.relative_to(work)
                (into / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, into / rel)
                kept.append(str(rel))
        return kept

    def _video_facts(self, work: Path) -> dict:
        facts: dict = {}
        finals = sorted(work.rglob("final.mp4")) if work.exists() else []
        if finals:
            facts["bytes"] = finals[0].stat().st_size
            facts["duration_s"] = _duration(finals[0])
        scripts = sorted(work.rglob("script.json")) if work.exists() else []
        if scripts:
            try:
                script = json.loads(scripts[0].read_text())
                segs = script.get("segments", [])
                beats = [b for s in segs for b in s.get("beats", [])]
                facts.update(title=script.get("title"), segments=len(segs), beats=len(beats),
                             words=sum(len(str(b.get("narration", "")).split()) for b in beats),
                             phases=[s.get("phase") for s in segs])
            except (ValueError, OSError):
                pass
        return facts


def _move_programs(ku: str, into: Path) -> list[str]:
    """The picture-program attempts the planner saved for this KU (SYLLABYTE_PLAN_DUMP, set by the worker), moved into
    the record so the next video of the same KU starts with none."""
    dump = os.environ.get("SYLLABYTE_PLAN_DUMP")
    if not dump or not Path(dump).is_dir():
        return []
    moved = []
    for f in sorted(Path(dump).glob(f"{ku}-program*.json")):
        into.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), into / f.name)
        moved.append(f"programs/{f.name}")
    return moved


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text))[:60]


def _duration(path: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=20)
        return round(float(out.stdout.strip()), 2)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _steps(lines: list[tuple[float, str, str]], started: float, ended: float) -> list[dict]:
    """The pipeline's steps ([3/6] script, [4/6] tts, ...) from the lines that start them: each lasts until the next
    begins, the last until the job's final file is written (or the job ends)."""
    marks = [(t, f"{m.group(1)}/6 {m.group(2)}") for t, _, line in lines if (m := _STEP.search(line))]
    done = next((t for t, _, line in lines if "-> " in line and "final.mp4" in line), ended)
    out = []
    for i, (t, name) in enumerate(marks):
        until = marks[i + 1][0] if i + 1 < len(marks) else max(done, t)
        out.append({"step": name, "start_s": round(t - started, 2), "seconds": round(until - t, 2)})
    return out


def _by_stage(calls: list[dict]) -> list[dict]:
    """Calls grouped by stage (the level suffix kept), most expensive first."""
    groups: dict[str, dict] = {}
    for c in calls:
        g = groups.setdefault(c["stage"], {"stage": c["stage"], "calls": 0, "cost_usd": 0.0, "wall_seconds": 0.0,
                                           "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_creation_tokens": 0})
        g["calls"] += 1
        for k in ("cost_usd", "wall_seconds", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"):
            g[k] += c[k]
    total = sum(g["cost_usd"] for g in groups.values()) or 1.0
    for g in groups.values():
        g["cost_usd"] = round(g["cost_usd"], 5)
        g["wall_seconds"] = round(g["wall_seconds"], 2)
        g["share"] = round(g["cost_usd"] / total, 3)
    return sorted(groups.values(), key=lambda g: -g["cost_usd"])


def _programs(lines: list[tuple[float, str, str]], started: float) -> dict:
    """The picture program's attempts and why each one after the first was written again."""
    attempts = [{"at_s": round(t - started, 2), "attempt": int(m.group(1)), "lines": int(m.group(2)), "snapshots": m.group(3)}
                for t, _, line in lines if (m := _PROGRAM.search(line))]
    redraws = [{"at_s": round(t - started, 2), "why": line.split("the program is written again: ", 1)[1]}
               for t, _, line in lines if "the program is written again: " in line]
    kept = [line.split("built with the program as it is: ", 1)[1] for _, _, line in lines if "built with the program as it is: " in line]
    return {"attempts": attempts, "redraws": redraws, "built_with_problems": kept}


def _segments(lines: list[tuple[float, str, str]]) -> list[dict]:
    return [{"segment": int(m.group(1)), "tier": m.group(2), "attempts": int(m.group(3)), "seconds": float(m.group(4))}
            for _, _, line in lines if (m := _SEGMENT.search(line))]
