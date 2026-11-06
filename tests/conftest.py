"""Shared test setup: no test may reach the Anthropic API."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_picture_plan_calls(monkeypatch, tmp_path):
    """The picture plan classifies a KU with an LLM call and caches it under runs/. Tests that need a plan pass
    one (write_storyboard(picture=...)); anything else fails here instead of calling the API."""
    from script_generation_agent import picture_plan

    def refuse(**kw):
        raise AssertionError("a test tried to classify a KU's picture with the API; pass picture= instead")

    monkeypatch.setattr(picture_plan, "structured", refuse)
    monkeypatch.setattr(picture_plan, "CACHE", tmp_path / "picture-plans.json")
