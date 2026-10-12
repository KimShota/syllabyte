"""
From a topic's ability (theta) to a Knowledge Unit's readiness level (plan D6).

The proposal (§3.2) maps readiness to Bloom tiers: novice -> Remember/Understand, developing -> Apply/Analyze,
proficient -> Evaluate/Create. Each KU has one item per tier, so the rule reads off the KU's own item
difficulties: theta >= b means the student is more likely than not to answer that item correctly.
"""

from __future__ import annotations

from typing import Literal

Level = Literal[1, 2, 3]  # 1 novice, 2 developing, 3 proficient


def readiness_level(theta: float, b_applied: float, b_advanced: float, n_scored: int) -> Level:
    """Level 3 if theta reaches the KU's advanced item, 2 if it reaches its applied item, else 1.

    `n_scored` is how many answers fed theta. With none (every answer was "Not sure", or the topic was not
    asked), theta is just the starting value and says nothing, so the KU is novice (plan D7).

    The advanced threshold is never taken below the applied one, so a bank whose tiers came out of order
    cannot make a student proficient without being developing.
    """
    if n_scored == 0:
        return 1
    advanced = max(b_advanced, b_applied)
    if theta >= advanced:
        return 3
    if theta >= b_applied:
        return 2
    return 1
