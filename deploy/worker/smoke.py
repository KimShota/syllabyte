"""Checks a worker machine can do its job, without taking one (deploy/README.md).

    .venv/bin/python deploy/worker/smoke.py            # everything
    .venv/bin/python deploy/worker/smoke.py --offline  # only this machine: voices, rendering, the cast

Online checks: the API answers, it accepts the worker token, and the Anthropic key works (a free model listing). Offline
checks: both cast voices speak (this also downloads the voice model and the English language model the first time),
Manim renders a scene with a formula through LaTeX, and the cast's pictures are there. Secrets are never printed.
Exits 1 if anything failed.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

results: list[tuple[str, bool, str]] = []


def check(name: str):
    def wrap(fn):
        start = time.monotonic()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.monotonic() - start:.1f} s)".strip()))
        except Exception as e:  # report every failure, then carry on to the next check
            results.append((name, False, f"{type(e).__name__}: {e}"))
        return fn

    return wrap


def get(url: str, token: str | None = None) -> int:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def online() -> None:
    server = os.environ.get("SYLLABYTE_SERVER", "").rstrip("/")
    token = os.environ.get("SYLLABYTE_WORKER_TOKEN", "")

    @check("API server answers")
    def _():
        if not server.startswith("https://"):
            raise RuntimeError(f"SYLLABYTE_SERVER should be the production HTTPS address, not {server!r}")
        status = get(f"{server}/api/health")
        if status != 200:
            raise RuntimeError(f"{server}/api/health answered {status}")
        return server

    @check("API accepts the worker token")
    def _():
        if not token:
            raise RuntimeError("SYLLABYTE_WORKER_TOKEN is empty: run deploy/worker/connect.sh")
        # a job id that cannot exist: a good token gets "not found", a bad one (or worker routes switched off) 401
        status = get(f"{server}/api/worker/jobs/smoke-check/file", token)
        if status == 401:
            raise RuntimeError("the API refused the token (or has no SYLLABYTE_WORKER_TOKEN): run deploy/worker/connect.sh")
        return f"answered {status}, not 401"

    @check("Anthropic key works")
    def _():
        name = os.environ.get("ANTHROPIC_KEY_NAME") or "ANTHROPIC_API_KEY"
        key = os.environ.get(name)
        if not key:
            raise RuntimeError(f"{name} is empty: run deploy/worker/set-anthropic-key.sh")
        import anthropic

        anthropic.Anthropic(api_key=key).models.list(limit=1)
        return f"{name} accepted"


def offline() -> None:
    @check("cast pictures and voices are configured")
    def _():
        from syllabyte_common.cast import image_path, load_cast

        cast = load_cast()
        for c in (cast.explainer, cast.peer):
            if not image_path(c).exists():
                raise FileNotFoundError(image_path(c))
        return f"{cast.explainer.name} and {cast.peer.name}"

    @check("both voices speak")
    def _():
        from syllabyte_common.cast import load_cast
        from animation_agent.tts import KokoroBackend

        cast = load_cast()
        out = Path(tempfile.mkdtemp())
        backend = KokoroBackend()
        took = []
        for c in (cast.explainer, cast.peer):
            start = time.monotonic()
            seconds = backend.synthesize(f"Hi, I'm {c.name}. Let's check this machine can talk.", out / f"{c.voice}.wav", c.voice)
            if seconds <= 0.5:
                raise RuntimeError(f"{c.voice} produced {seconds:.2f} s of audio")
            took.append(f"{c.voice} {time.monotonic() - start:.1f} s")
        return ", ".join(took)

    @check("Manim renders text and a formula")
    def _():
        from manim import DOWN, MathTex, Scene, Text, VGroup, Write, tempconfig

        class Smoke(Scene):
            def construct(self):
                self.play(Write(VGroup(Text("SyllaByte"), MathTex(r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}")).arrange(DOWN)))

        media = Path(tempfile.mkdtemp())
        with tempconfig({"media_dir": str(media), "quality": "low_quality", "disable_caching": True, "verbosity": "WARNING", "progress_bar": "none"}):
            Smoke().render()
        videos = list(media.rglob("*.mp4"))
        if not videos:
            raise RuntimeError("no video was written")
        return f"{videos[0].stat().st_size // 1024} KB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="skip the API and Anthropic checks")
    args = ap.parse_args()
    if not args.offline:
        online()
    offline()
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [n for n, ok, _ in results if not ok]
    print("all checks passed" if not failed else f"{len(failed)} check(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
