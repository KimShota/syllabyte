#!/usr/bin/env python
"""
Render the scene grammar's example programs (animation_agent/scene/examples.py) through the real render path, in
the dialogue frame, one snapshot per beat, and report layout findings (plan/scene-grammar-plan.md, P0).

    uv run python scripts/scene_demo.py --out runs/scene-demo [union_find llrb water_jugs]

With --template, the program is drawn as the storyboard draws it (P1): a Picture call and one p.step() per beat,
through visuals/scene_code.build_spec_scene and SpecRunner, in two segments, the second replaying the first.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from animation_agent.layout import BEATS_FILE  # noqa: E402
from animation_agent.renderer import _try_render  # noqa: E402
from animation_agent.scene.examples import PROGRAMS  # noqa: E402
from animation_agent.scene.sandbox import run_program  # noqa: E402
from animation_agent.visuals.scene_code import build_spec_scene  # noqa: E402

SECONDS_PER_SNAP = 1.6


def scene_code(snaps: list[dict]) -> str:
    beats = "\n".join(f"        run.show({i}, {0.6 * SECONDS_PER_SNAP})\n        self.end_beat({i + 1})"
                      for i in range(len(snaps)))
    return f"""import json
from manim import *

from animation_agent.layout import GridLayoutScene
from animation_agent.scene.draw import PictureRunner

SNAPS = json.loads(r'''{json.dumps(snaps)}''')


class Seg0(GridLayoutScene):
    def construct(self):
        self.setup_grid()
        run = PictureRunner(self, SNAPS)
{beats}
"""


def template_segments(source: str, n: int) -> list[SimpleNamespace]:
    """Two segments: the first creates the Picture and steps half way, the second carries it and steps on."""
    lines = ", ".join(f'"{line}"' for line in source.strip("\n").splitlines())
    calls = [[f"p = Picture(program=[{lines}])"]] + [["p.step()"] for _ in range(n - 1)]
    half = len(calls) // 2
    first = SimpleNamespace(beats=[SimpleNamespace(draw=c) for c in calls[:half]], carried=[], templates=True)
    second = SimpleNamespace(beats=[SimpleNamespace(draw=c) for c in calls[half:]],
                             carried=[c for beat in calls[:half] for c in beat], templates=True)
    return [first, second]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", default=list(PROGRAMS))
    parser.add_argument("--out", default="runs/scene-demo")
    parser.add_argument("--frame", default="dialogue", choices=["dialogue", "full"])
    parser.add_argument("--template", action="store_true", help="draw it as a storyboard's Picture calls")
    args = parser.parse_args()
    out = Path(args.out)
    for name in args.names:
        t0 = time.monotonic()
        result = run_program(PROGRAMS[name])
        ran = time.monotonic() - t0
        if not result.ok:
            print(f"{name}: program error: {result.error}")
            continue
        snaps = result.snapshots
        work = out / name
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        (work / "snapshots.json").write_text(json.dumps(snaps, indent=1))
        if args.template:
            jobs = [(f"Seg{i}", build_spec_scene(seg, f"Seg{i}"), len(seg.beats))
                    for i, seg in enumerate(template_segments(PROGRAMS[name], len(snaps)))]
        else:
            jobs = [("Seg0", scene_code(snaps), len(snaps))]
        for cls, code, beats in jobs:
            if code is None:
                print(f"{name} {cls}: the calls don't pass the checker")
                continue
            seg_work = work / cls
            seg_work.mkdir()
            durations = [SECONDS_PER_SNAP] * beats
            (seg_work / BEATS_FILE).write_text(json.dumps(durations))
            t1 = time.monotonic()
            ok, error, mp4, layout = _try_render(seg_work, code, cls, "low", len(durations), sum(durations),
                                                 check_formulas=False, frame=args.frame)
            rendered = time.monotonic() - t1
            if not ok:
                print(f"{name} {cls}: render failed: {error[-1500:]}")
                continue
            final = out / (f"{name}-{cls}.mp4" if args.template else f"{name}.mp4")
            shutil.copy(mp4, final)
            print(f"{name} {cls}: {beats} beats, program {ran:.2f}s, render {rendered:.1f}s -> {final}")
            for f in layout.findings:
                print(f"   layout: {f}")
        for s in snaps:
            print(f"   - {s['caption']}")


if __name__ == "__main__":
    main()
