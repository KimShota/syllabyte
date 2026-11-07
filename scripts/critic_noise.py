#!/usr/bin/env python
"""
How much the script critic's scores move when it scores the same script again: the noise any before/after
comparison of critic scores has to beat.

    # Score every ready video's script in these stores twice more (the score recorded with the video is the first).
    uv run python scripts/critic_noise.py score runs/dsa-plan runs/dsa-trace-2 --times 2 --out runs/critic-noise
    # The spread per script and score, and what it means for a comparison of n KUs.
    uv run python scripts/critic_noise.py report --out runs/critic-noise

Scores land in <out>/<store name>/<ku id>.json as a list of rounds (the recorded one first). Nothing is
rewritten and no video is made: one critic call per extra score.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from compare_critic import SCORES, SHORT  # noqa: E402
from video_jobs import find_ku, load_course  # noqa: E402

from syllabyte_common.llm import PRICE_PER_MTOK  # noqa: E402
from syllabyte_common.models import RunManifest, load_script  # noqa: E402


def _ready(store: Path):
    """(ku id, job, video dir) for each ready video in the store, the latest per KU."""
    latest: dict[str, tuple[str, dict, Path]] = {}
    for job_file in (store / "jobs").glob("*.json"):
        job = json.loads(job_file.read_text())
        video = store / "videos" / job["key"]
        if not (video / "script.json").exists() or not (video / "critique.json").exists():
            continue
        when = job.get("updated_at") or ""
        if job["ku_id"] not in latest or when > latest[job["ku_id"]][0]:
            latest[job["ku_id"]] = (when, job, video)
    return [(ku, job, video) for ku, (_, job, video) in sorted(latest.items())]


def score(stores: list[Path], times: int, out: Path, workers: int) -> None:
    from script_generation_agent.critic import critique_storyboard

    tasks = []
    for store in stores:
        for ku_id, job, video in _ready(store):
            target = out / store.name / f"{ku_id}.json"
            rounds = (json.loads(target.read_text()) if target.exists()
                      else json.loads((video / "critique.json").read_text())["rounds"][-1:])
            tasks.append((store, ku_id, job, video, target, rounds))
    manifest = RunManifest(run_id="critic-noise", course_name="critic noise")

    def one(task):
        store, ku_id, job, video, target, rounds = task
        corpus, kus = load_course(Path(job["course_dir"]))
        ku, _ = find_ku(kus, ku_id)
        script = load_script((video / "script.json").read_text())
        new = []
        for _ in range(times):
            result = critique_storyboard(script, corpus, ku, level=job.get("level") or 2, manifest=manifest)
            new.append(result.rounds[-1].model_dump(mode="json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rounds + new, indent=1))
        print(f"{store.name} {ku_id}: VA " + ", ".join(str(r["visual_alignment"]) for r in rounds + new),
              flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, tasks))
    print(f"cost: ${manifest.total_cost_usd(PRICE_PER_MTOK):.2f} for {len(tasks) * times} critic calls")


def write(course: Path, ku_ids: list[str], out: Path, workers: int, trace: bool) -> None:
    """Each KU's script written once more with today's code and scored, with no voices and no render: the
    writer's noise is the spread between scripts of one KU. The worked example comes from the cache, so it is
    the one the earlier video used."""
    from script_generation_agent.critic import critique_storyboard
    from script_generation_agent.storyboard import write_storyboard

    corpus, kus = load_course(course)
    manifest = RunManifest(run_id="writer-noise", course_name=corpus.course_name)

    def one(ku_id: str):
        ku, prereqs = find_ku(kus, ku_id)
        kwargs = {} if trace else {"example": None}
        script = write_storyboard(ku, corpus, level=2, prereq_titles=prereqs, manifest=manifest, **kwargs)
        result = critique_storyboard(script, corpus, ku, level=2, manifest=manifest)
        folder = out / ku_id
        folder.mkdir(parents=True, exist_ok=True)
        n = len(list(folder.glob("script-*.json"))) + 1
        (folder / f"script-{n}.json").write_text(script.model_dump_json(indent=1))
        (folder / f"critique-{n}.json").write_text(result.model_dump_json(indent=1))
        r = result.rounds[-1]
        print(f"{ku_id}: " + ", ".join(f"{SHORT[k]} {getattr(r, k)}" for k in SCORES), flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, ku_ids))
    print(f"cost: ${manifest.total_cost_usd(PRICE_PER_MTOK):.2f} for {len(ku_ids)} scripts")


def report(out: Path) -> None:
    rows = []  # (store, ku, {score: [values]})
    for f in sorted(out.glob("*/*.json")):
        rounds = json.loads(f.read_text())
        rows.append((f.parent.name, f.stem, {k: [r[k] for r in rounds] for k in SCORES}))
    if not rows:
        raise SystemExit(f"no scores under {out}")
    print(f"{'store / KU':48} " + "  ".join(f"{SHORT[k]:>9}" for k in SCORES) + "   pass")
    for store, ku, s in rows:
        passes = sum(all(s[k][i] >= 7 for k in SCORES) for i in range(len(s[SCORES[0]])))
        print(f"{store + ' / ' + ku:48} " + "  ".join(f"{','.join(map(str, s[k])):>9}" for k in SCORES)
              + f"   {passes}/{len(s[SCORES[0]])}")
    print()
    for k in SCORES:
        sds = [statistics.stdev(s[k]) for _, _, s in rows if len(s[k]) > 1]
        spans = [max(s[k]) - min(s[k]) for _, _, s in rows]
        sd = statistics.mean(sds) if sds else 0.0
        # The score of one KU is one draw: a mean over n KUs (each scored once) differs between two runs of
        # the same scripts by about sqrt(2) * sd / sqrt(n).
        noise = {n: (2 ** 0.5) * sd / n ** 0.5 for n in (5, 7, 12)}
        print(f"{SHORT[k]}: mean within-script SD {sd:.2f}; span 0 on {spans.count(0)}, 1 on {spans.count(1)}, "
              f"2+ on {sum(x >= 2 for x in spans)} of {len(spans)} scripts; a mean over n KUs moves by about "
              + ", ".join(f"±{v:.2f} (n={n})" for n, v in noise.items()) + " (one SD) with no change at all")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("stores", nargs="+", type=Path)
    s.add_argument("--times", type=int, default=2)
    s.add_argument("--out", type=Path, default=Path("runs/critic-noise"))
    s.add_argument("--workers", type=int, default=6)
    w = sub.add_parser("write", help="write and score each KU's script once more, no video")
    w.add_argument("--course", type=Path, required=True)
    w.add_argument("kus", nargs="+")
    w.add_argument("--out", type=Path, default=Path("runs/writer-noise"))
    w.add_argument("--workers", type=int, default=5)
    w.add_argument("--no-trace", action="store_true", help="without the traced worked example")
    r = sub.add_parser("report")
    r.add_argument("--out", type=Path, default=Path("runs/critic-noise"))
    args = parser.parse_args()
    if args.cmd == "score":
        score(args.stores, args.times, args.out, args.workers)
    elif args.cmd == "write":
        write(args.course, args.kus, args.out, args.workers, trace=not args.no_trace)
    else:
        report(args.out)


if __name__ == "__main__":
    main()
