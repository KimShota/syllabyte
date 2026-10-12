"""The checked-in golden sequences must be what the Python engine produces today."""

import json
import math
from pathlib import Path

import pytest
from assessment_agent.parity import THETA_TOLERANCE, generate_cases

GOLDEN = Path(__file__).resolve().parent.parent / "apps/web/tests/fixtures/cat-parity.json"


def test_golden_file_matches_the_engine():
    if not GOLDEN.exists():
        pytest.fail("run `uv run python scripts/make_cat_parity.py` and commit apps/web/tests/fixtures/cat-parity.json")
    stored = json.loads(GOLDEN.read_text())["cases"]
    fresh = generate_cases()
    assert [c["name"] for c in stored] == [c["name"] for c in fresh]
    for a, b in zip(stored, fresh):
        assert a["items"] == b["items"], a["name"]
        assert len(a["steps"]) == len(b["steps"]), a["name"]
        for k, (x, y) in enumerate(zip(a["steps"], b["steps"])):
            where = f"{a['name']} step {k}"
            assert (x["item_id"], x["outcome"], x["hinted"]) == (y["item_id"], y["outcome"], y["hinted"]), where
            assert math.isclose(x["theta"], y["theta"], abs_tol=THETA_TOLERANCE), where
            if x["se"] is None or y["se"] is None:
                assert x["se"] is y["se"], where
            else:
                assert math.isclose(x["se"], y["se"], abs_tol=THETA_TOLERANCE), where


def test_cases_cover_what_the_port_must_get_right():
    names = {c["name"] for c in generate_cases()}
    for needed in ("all-correct", "all-wrong", "all-not-sure", "symmetric-ties", "pool-smaller-than-length", "2pl-varied-discrimination"):
        assert needed in names
    steps = [s for c in generate_cases() for s in c["steps"]]
    assert any(s["hinted"] for s in steps) and any(s["outcome"] == "not_sure" for s in steps)
