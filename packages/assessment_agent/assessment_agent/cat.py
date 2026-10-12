"""
Computerized Adaptive Testing for one topic (= one lecture), on the 2PL model.

This is the engine of record for SyllaByte's assessment (proposal §3.2; plan/per-ku-profiling-plan.md D1-D10).
A TypeScript port (apps/web/lib/logic/cat.ts) runs the static demo and must agree with this module on the
golden sequences in apps/web/tests/fixtures/cat-parity.json.

What comes from catsim, and what is ours:
  * the 2PL response curve, item information and the maximum-likelihood search for theta
    (`NumericalSearchEstimator`, bounded search on [-6, 6]) are catsim's;
  * Dodd's heuristic for an all-correct / all-wrong pattern is catsim's `cat.dodd`, applied over the whole
    session pool's difficulty range;
  * item selection is "most informative unseen item" like catsim's `MaxInfoSelector`, but ties are broken by
    pool order. catsim sorts with `numpy.argsort`, which is not stable, so equally informative items come back
    in arbitrary order; with symmetric difficulties (b = +0.5 and -0.5 at theta = 0) that is the common case,
    and a port could never reproduce it.

Rules from the plan:
  * "Not sure" counts toward the test length but never enters the estimate (plan §2 rule 3);
  * an answer given after a hint is scored as the same item made easier, b - hint_beta_shift (D10);
  * discrimination is whatever the bank says; the bank fixes it at 1.0 until post-pilot calibration (D5).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from catsim import cat as catsim_cat
from catsim import irt
from catsim.estimation import NumericalSearchEstimator
from catsim.item_bank import ItemBank

Outcome = Literal["correct", "wrong", "not_sure"]

# Two items whose information differs by less than this are "tied"; the earlier one in the pool wins.
TIE_TOLERANCE = 1e-9

_ESTIMATOR = NumericalSearchEstimator(method="bounded", dodd=True)


@dataclass(frozen=True)
class BankItem:
    """A 2PL item: discrimination `a`, difficulty `b` (logit scale). No guessing, no upper asymptote."""

    id: str
    a: float
    b: float

    def __post_init__(self) -> None:
        # catsim validates item matrices itself but prints a blank line each time, so we check here and
        # build every ItemBank with validate=False.
        if not (math.isfinite(self.a) and self.a > 0):
            raise ValueError(f"item {self.id}: discrimination must be positive, got {self.a}")
        if not math.isfinite(self.b):
            raise ValueError(f"item {self.id}: difficulty must be finite, got {self.b}")


@dataclass(frozen=True)
class Answer:
    item_id: str
    outcome: Outcome
    hinted: bool = False


@dataclass(frozen=True)
class CatConfig:
    length: int
    start_theta: float = 0.0
    hint_beta_shift: float = 1.0


def _matrix(items: Sequence[BankItem], shifts: Sequence[float] | None = None) -> np.ndarray:
    """catsim's item matrix: columns a, b, c (guessing = 0), d (upper asymptote = 1)."""
    shifts = shifts if shifts is not None else [0.0] * len(items)
    return np.array([[it.a, it.b - s, 0.0, 1.0] for it, s in zip(items, shifts, strict=True)], dtype=float)


def _bank(items: Sequence[BankItem], shifts: Sequence[float] | None = None) -> ItemBank:
    return ItemBank(_matrix(items, shifts), validate=False)


def _by_id(pool: Sequence[BankItem]) -> dict[str, BankItem]:
    out = {it.id: it for it in pool}
    if len(out) != len(pool):
        raise ValueError("duplicate item ids in the pool")
    return out


def _scored(pool: Sequence[BankItem], answers: Sequence[Answer], hint_beta_shift: float):
    """The answers that enter the estimate, as (item, shift, correct)."""
    items = _by_id(pool)
    out = []
    for a in answers:
        if a.outcome == "not_sure":
            continue
        if a.item_id not in items:
            raise ValueError(f"answer for unknown item {a.item_id}")
        out.append((items[a.item_id], hint_beta_shift if a.hinted else 0.0, a.outcome == "correct"))
    return out


def estimate_theta(
    pool: Sequence[BankItem], answers: Sequence[Answer], start_theta: float = 0.0, hint_beta_shift: float = 1.0
) -> float:
    """Ability after `answers`, replaying them in order the way a live CAT would.

    Replaying matters only for Dodd's heuristic, which is defined recursively from the previous estimate: while
    every scored answer so far is correct (or every one is wrong) theta moves halfway toward the pool's hardest
    (easiest) item; once the pattern is mixed the maximum-likelihood estimate takes over and ignores the past.

    Known quirk, inherited from catsim: Dodd's value is a heuristic, not a maximum-likelihood estimate, so with a
    narrow pool "all correct" can land below "all but one correct" (and "all wrong" above "one right"). It is
    always finite and inside the pool's difficulty range. After n uniform answers it sits at (1 - 2^-n) of the way
    from the start to the pool's extreme, which is why the pool needs a wide difficulty range.
    """
    if not pool:
        raise ValueError("empty pool")
    theta = start_theta
    pool_bank = _bank(pool)
    scored = _scored(pool, answers, hint_beta_shift)
    for k in range(1, len(scored) + 1):
        upto = scored[:k]
        outcomes = [c for _, _, c in upto]
        if all(outcomes) or not any(outcomes):
            theta = float(catsim_cat.dodd(theta, pool_bank, outcomes[0]))
        else:
            bank = _bank([it for it, _, _ in upto], [s for _, s, _ in upto])
            theta = float(
                _ESTIMATOR.estimate(
                    item_bank=bank, administered_items=list(range(k)), response_vector=outcomes, est_theta=theta
                )
            )
    return theta


def standard_error(pool: Sequence[BankItem], answers: Sequence[Answer], theta: float, hint_beta_shift: float = 1.0) -> float:
    """1 / sqrt(test information) at `theta` over the scored answers; infinite before any evidence."""
    scored = _scored(pool, answers, hint_beta_shift)
    if not scored:
        return math.inf
    info = irt.test_info(theta, _matrix([it for it, _, _ in scored], [s for _, s, _ in scored]))
    return 1.0 / math.sqrt(info) if info > 0 else math.inf


def select_next(pool: Sequence[BankItem], administered: set[str], theta: float) -> BankItem | None:
    """The most informative item not yet administered, ties to the earlier item; None when none are left."""
    free = [i for i, it in enumerate(pool) if it.id not in administered]
    if not free:
        return None
    info = _bank(pool).information(theta)
    best = max(info[i] for i in free)
    for i in free:
        if info[i] >= best - TIE_TOLERANCE:
            return pool[i]
    raise AssertionError("unreachable")


@dataclass
class CatSession:
    """One adaptive test: `config.length` items from `pool`, each chosen from the answers before it."""

    pool: Sequence[BankItem]
    config: CatConfig
    answers: list[Answer] = field(default_factory=list)
    theta: float = field(init=False)

    def __post_init__(self) -> None:
        _by_id(self.pool)
        self.theta = self.config.start_theta

    @property
    def done(self) -> bool:
        return len(self.answers) >= self.config.length or len(self.answers) >= len(self.pool)

    @property
    def n_scored(self) -> int:
        return sum(1 for a in self.answers if a.outcome != "not_sure")

    def next_item(self) -> BankItem | None:
        if self.done:
            return None
        return select_next(self.pool, {a.item_id for a in self.answers}, self.theta)

    def answer(self, item_id: str, outcome: Outcome, hinted: bool = False) -> float:
        if item_id in {a.item_id for a in self.answers}:
            raise ValueError(f"item {item_id} was already answered")
        if item_id not in _by_id(self.pool):
            raise ValueError(f"unknown item {item_id}")
        self.answers.append(Answer(item_id, outcome, hinted))
        self.theta = estimate_theta(self.pool, self.answers, self.config.start_theta, self.config.hint_beta_shift)
        return self.theta

    @property
    def standard_error(self) -> float:
        return standard_error(self.pool, self.answers, self.theta, self.config.hint_beta_shift)
