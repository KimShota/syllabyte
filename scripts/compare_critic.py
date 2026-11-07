#!/usr/bin/env python
"""
The script critic's scores per KU in two video stores, side by side, with the change in each and the means.

    uv run python scripts/compare_critic.py runs/dsa-plan runs/dsa-trace

A store is a video_jobs.py --store directory (jobs/*.json, videos/<key>/critique.json). A KU made more than once
in a store counts its latest video. The scores are the critic's last round.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SCORES = ("pedagogical_coherence", "conceptual_accuracy", "learner_appropriateness", "visual_alignment")
SHORT = {"pedagogical_coherence": "PC", "conceptual_accuracy": "CA", "learner_appropriateness": "LA",
         "visual_alignment": "VA"}


def scores(store: Path) -> dict[str, dict[str, int]]:
    """KU id -> the critic's last-round scores, for each ready video in the store."""
    out: dict[str, tuple[str, dict[str, int]]] = {}
    for job_file in (store / "jobs").glob("*.json"):
        job = json.loads(job_file.read_text())
        critique = store / "videos" / job["key"] / "critique.json"
        if not critique.exists():
            continue
        rounds = json.loads(critique.read_text()).get("rounds") or []
        if not rounds:
            continue
        when = job.get("updated_at") or ""
        if job["ku_id"] not in out or when > out[job["ku_id"]][0]:
            out[job["ku_id"]] = (when, {k: rounds[-1][k] for k in SCORES if k in rounds[-1]})
    return {ku: s for ku, (_, s) in out.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    a, b = scores(args.before), scores(args.after)
    both = sorted(set(a) & set(b))
    print(f"{'KU':40} " + "  ".join(f"{SHORT[k]:>9}" for k in SCORES))
    for ku in both:
        cells = [f"{a[ku].get(k, '-')}->{b[ku].get(k, '-')}" for k in SCORES]
        print(f"{ku:40} " + "  ".join(f"{c:>9}" for c in cells))
    if both:
        means = []
        for k in SCORES:
            xs = [(a[ku][k], b[ku][k]) for ku in both if k in a[ku] and k in b[ku]]
            mean = lambda i: sum(x[i] for x in xs) / len(xs)  # noqa: E731
            means.append(f"{mean(0):.2f}->{mean(1):.2f}")
        print(f"{'mean':40} " + "  ".join(f"{m:>9}" for m in means))
        va = [(a[ku]["visual_alignment"], b[ku]["visual_alignment"]) for ku in both]
        up, down = sum(y > x for x, y in va), sum(y < x for x, y in va)
        print(f"visual alignment: {up} up, {down} down, {len(va) - up - down} the same; "
              f"{sum(all(b[ku][k] >= 7 for k in SCORES) for ku in both)} of {len(both)} pass all four at 7")
    for ku in sorted(set(a) ^ set(b)):
        print(f"only in {'before' if ku in a else 'after'}: {ku}")


if __name__ == "__main__":
    main()
