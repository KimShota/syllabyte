"""
Golden CAT sequences for the Python <-> TypeScript parity test (plan D3).

`generate_cases()` runs simulated students through `CatSession` on a variety of banks and records every step:
which item was chosen, what the student answered, and the resulting theta and standard error. The TypeScript
engine replays the same answers and must choose the same items and land on the same thetas. The file is written
by scripts/make_cat_parity.py to apps/web/tests/fixtures/cat-parity.json and checked in; tests/test_cat_parity.py
fails if it drifts from what this module produces (for example after a catsim or scipy upgrade).

Everything is seeded, and difficulties/discriminations are rounded to 2 decimals so they survive a JSON round trip
identically in both languages.
"""

from __future__ import annotations

import math
import random
from typing import Any

from assessment_agent.cat import BankItem, CatConfig, CatSession

SEED = 20261013
THETA_TOLERANCE = 1e-6


def _bank(rng: random.Random, n: int, lo: float = -2.5, hi: float = 2.5, a: tuple[float, float] | None = None) -> list[BankItem]:
    return [
        BankItem(f"q{k:02d}", round(rng.uniform(*a), 2) if a else 1.0, round(rng.uniform(lo, hi), 2))
        for k in range(n)
    ]


def _run(
    name: str,
    pool: list[BankItem],
    *,
    length: int,
    rng: random.Random,
    true_theta: float = 0.0,
    start_theta: float = 0.0,
    hint_beta_shift: float = 1.0,
    not_sure_rate: float = 0.0,
    hint_rate: float = 0.0,
    forced: str | None = None,
) -> dict[str, Any]:
    session = CatSession(pool, CatConfig(length=length, start_theta=start_theta, hint_beta_shift=hint_beta_shift))
    steps = []
    while (item := session.next_item()) is not None:
        if rng.random() < not_sure_rate:
            outcome = "not_sure"
        elif forced:
            outcome = forced
        else:
            p = 1 / (1 + math.exp(-item.a * (true_theta - item.b)))
            outcome = "correct" if rng.random() < p else "wrong"
        hinted = outcome != "not_sure" and rng.random() < hint_rate
        theta = session.answer(item.id, outcome, hinted)
        se = session.standard_error
        steps.append(
            {"item_id": item.id, "outcome": outcome, "hinted": hinted, "theta": theta, "se": None if math.isinf(se) else se}
        )
    return {
        "name": name,
        "items": [{"id": it.id, "a": it.a, "b": it.b} for it in pool],
        "length": length,
        "start_theta": start_theta,
        "hint_beta_shift": hint_beta_shift,
        "steps": steps,
    }


def generate_cases() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    cases = [
        _run("rasch-12-items-length-4", _bank(rng, 12), length=4, rng=rng, true_theta=0.8),
        _run("rasch-20-items-length-6", _bank(rng, 20), length=6, rng=rng, true_theta=-0.7),
        _run("rasch-30-items-length-10", _bank(rng, 30), length=10, rng=rng, true_theta=1.4),
        _run("all-correct", _bank(rng, 10), length=4, rng=rng, forced="correct"),
        _run("all-wrong", _bank(rng, 10), length=4, rng=rng, forced="wrong"),
        _run("not-sure-mixed-in", _bank(rng, 14), length=5, rng=rng, true_theta=0.2, not_sure_rate=0.35),
        _run("all-not-sure", _bank(rng, 8), length=4, rng=rng, not_sure_rate=1.0),
        _run("hints-shift-1.0", _bank(rng, 14), length=6, rng=rng, true_theta=-0.3, hint_rate=0.5),
        _run("hints-shift-0.6", _bank(rng, 14), length=6, rng=rng, true_theta=0.5, hint_rate=0.6, hint_beta_shift=0.6),
        _run("2pl-varied-discrimination", _bank(rng, 16, a=(0.6, 2.2)), length=6, rng=rng, true_theta=0.4),
        _run("start-theta-minus-0.5", _bank(rng, 12), length=4, rng=rng, true_theta=-1.0, start_theta=-0.5),
        _run("narrow-pool", _bank(rng, 6, -0.3, 0.3), length=4, rng=rng, true_theta=0.1),
        _run("pool-smaller-than-length", _bank(rng, 3), length=5, rng=rng, true_theta=0.0),
    ]
    # symmetric difficulties: every pick at theta = 0 is a tie that only the pool-order rule resolves
    ties = [BankItem(f"q{k:02d}", 1.0, b) for k, b in enumerate([0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 0.5, -0.5])]
    cases.append(_run("symmetric-ties", ties, length=5, rng=rng, true_theta=0.3))
    for k in range(12):
        cases.append(
            _run(
                f"random-{k:02d}",
                _bank(rng, rng.randint(6, 28), a=(0.7, 2.0) if k % 3 == 0 else None),
                length=rng.randint(3, 8),
                rng=rng,
                true_theta=round(rng.uniform(-2, 2), 2),
                start_theta=round(rng.uniform(-0.6, 0.6), 2),
                not_sure_rate=rng.choice([0.0, 0.0, 0.2]),
                hint_rate=rng.choice([0.0, 0.3]),
            )
        )
    return cases
