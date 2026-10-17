#!/usr/bin/env python
"""
Write the golden CAT sequences the TypeScript engine is tested against.

    uv run python scripts/make_cat_parity.py

Rerun it after changing assessment_agent/cat.py or upgrading catsim/scipy, then commit the file. The Python test
tests/test_cat_parity.py fails whenever the checked-in file no longer matches the engine.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import catsim
import scipy
from assessment_agent.parity import THETA_TOLERANCE, generate_cases

OUT = REPO / "packages/core/tests/fixtures/cat-parity.json"


def build() -> dict:
    return {
        "description": "Golden CAT sequences from the Python engine (assessment_agent.cat). The TypeScript engine must "
        "pick the same item at every step and match theta and se within the tolerance.",
        "theta_tolerance": THETA_TOLERANCE,
        "generated_with": {"catsim": catsim.__version__, "scipy": scipy.__version__},
        "cases": generate_cases(),
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}")
