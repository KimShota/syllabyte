"""
What the worker's video records say (ingestion_agent/job_record.py): every video, how long it took and what it cost,
and across them where the time and money went, by pipeline step and by model-call stage.

    uv run python scripts/video_records.py runs/pilot-test-video-work/records          # every video, then the totals
    uv run python scripts/video_records.py runs/pilot-test-video-work/records/<one>    # one video in full
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


def load(folder: Path) -> list[dict]:
    if (folder / "record.json").exists():
        return [json.loads((folder / "record.json").read_text())]
    return [json.loads(f.read_text()) for f in sorted(folder.glob("*/record.json"))]


def table(rows: list[list], head: list[str]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    line = lambda r: "  ".join(str(x).rjust(w) if isinstance(x, (int, float)) else str(x).ljust(w) for x, w in zip(r, widths))
    print(line(head))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(line(r))


def videos(records: list[dict]) -> None:
    rows = [[r["started"][5:16].replace("T", " "), r["ku_id"][:34], r["level"], r["status"], r["wall_seconds"], f"{r['cost_usd']:.3f}",
             r["llm_calls"], max(0, len(r["programs"]["attempts"]) - 1), len(r["errors"]), (r.get("video") or {}).get("duration_s") or ""]
            for r in records]
    table(rows, ["started", "topic", "L", "status", "wall s", "cost $", "calls", "redraws", "errors", "video s"])
    done = [r for r in records if r["status"] == "done"]
    if done:
        cost = sum(r["cost_usd"] for r in done)
        wall = sum(r["wall_seconds"] for r in done)
        print(f"\n{len(done)} of {len(records)} done: ${cost:.2f} (${cost / len(done):.3f} a video), {wall / len(done):.0f} s a video on average")


def stages(records: list[dict]) -> None:
    by: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        for s in r["cost_by_stage"]:
            name = re.sub(r"_l\d$", "", s["stage"])
            for k in ("calls", "cost_usd", "wall_seconds", "input_tokens", "output_tokens", "cache_read_tokens"):
                by[name][k] += s[k]
    total = sum(c["cost_usd"] for c in by.values()) or 1
    rows = [[name, int(c["calls"]), f"{c['cost_usd']:.3f}", f"{c['cost_usd'] / total:.0%}", f"{c['wall_seconds']:.0f}",
             int(c["input_tokens"] / c["calls"]), int(c["output_tokens"] / c["calls"]), int(c["cache_read_tokens"] / c["calls"])]
            for name, c in sorted(by.items(), key=lambda kv: -kv[1]["cost_usd"])]
    print("\nModel calls by stage, all videos:")
    table(rows, ["stage", "calls", "cost $", "share", "model s", "in/call", "out/call", "cache rd/call"])


def steps(records: list[dict]) -> None:
    by: dict[str, list[float]] = defaultdict(list)
    for r in records:
        for s in r["steps"]:
            by[s["step"]].append(s["seconds"])
        for p in r["phases"]:
            by[f"({p['phase']})"].append(p["seconds"])
    rows = [[name, len(v), f"{sum(v) / len(v):.1f}", f"{max(v):.1f}"] for name, v in sorted(by.items())]
    print("\nTime by pipeline step and worker phase:")
    table(rows, ["step", "videos", "mean s", "max s"])


def redraws(records: list[dict]) -> None:
    why = Counter(re.sub(r"'[^']*'|\d+(\.\d+)?", "_", d["why"])[:90] for r in records for d in r["programs"]["redraws"])
    if why:
        print("\nWhy picture programs were redrawn:")
        for text, n in why.most_common(12):
            print(f"  {n:3d}  {text}")


def one(r: dict) -> None:
    print(f"{r['kind']} {r['ku_id']} L{r['level']}  {r['status']}  {r['wall_seconds']} s  ${r['cost_usd']:.4f}  ({r['started']} -> {r['ended']})")
    v = r.get("video") or {}
    if v:
        print(f"video: {v.get('duration_s')} s, {v.get('segments')} segments, {v.get('beats')} lines, {v.get('words')} words, {v.get('bytes')} bytes")
    print("\nPhases:")
    table([[p["phase"], p["start_s"], p["seconds"], "ok" if p.get("ok") else p.get("error", "")] for p in r["phases"]], ["phase", "start s", "seconds", ""])
    print("\nPipeline steps:")
    table([[s["step"], s["start_s"], s["seconds"]] for s in r["steps"]] or [["(none)", "", ""]], ["step", "start s", "seconds"])
    print("\nModel calls, in order:")
    table([[c["stage"], c["finished_s"] if c["finished_s"] is not None else "", c["wall_seconds"], c["input_tokens"], c["output_tokens"],
            c["cache_read_tokens"], c["cache_creation_tokens"], f"{c['cost_usd']:.4f}"] for c in r["calls"]] or [["(none)"] + [""] * 7],
          ["stage", "done at s", "seconds", "in", "out", "cache rd", "cache wr", "cost $"])
    print("\nCost by stage:")
    table([[s["stage"], s["calls"], f"{s['cost_usd']:.4f}", f"{s['share']:.0%}", s["wall_seconds"]] for s in r["cost_by_stage"]] or [["(none)", "", "", "", ""]],
          ["stage", "calls", "cost $", "share", "seconds"])
    if r["programs"]["attempts"]:
        print("\nPicture programs:")
        for a in r["programs"]["attempts"]:
            print(f"  attempt {a['attempt']} at {a['at_s']} s: {a['lines']} lines; {a['snapshots']}")
        for d in r["programs"]["redraws"]:
            print(f"  redrawn at {d['at_s']} s: {d['why']}")
        for k in r["programs"]["built_with_problems"]:
            print(f"  built anyway: {k}")
    if r["segments"]:
        print("\nSegments rendered:")
        table([[s["segment"], s["tier"], s["attempts"], s["seconds"]] for s in r["segments"]], ["segment", "tier", "attempts", "seconds"])
    if r["uploads"]:
        print("\nFiles sent:")
        table([[u["file"], u["bytes"], u["seconds"]] for u in r["uploads"]], ["file", "bytes", "seconds"])
    if r["errors"]:
        print("\nErrors:")
        for e in r["errors"]:
            print(f"  at {e['at_s']} s in {e['where']}: {e['error']}")
    if r["notable_lines"]:
        print("\nLines worth a look:")
        for n in r["notable_lines"][:40]:
            print(f"  {n['at_s']:8.2f}s  {n['line'][:160]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", type=Path, help="a records folder, or one record's folder")
    args = parser.parse_args()
    records = load(args.path)
    if not records:
        raise SystemExit(f"no records in {args.path}")
    if (args.path / "record.json").exists():
        one(records[0])
        return
    videos(records)
    stages(records)
    steps(records)
    redraws(records)


if __name__ == "__main__":
    main()
