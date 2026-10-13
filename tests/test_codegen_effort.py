"""CODEGEN_EFFORT sets the thinking effort of the Manim code-writing calls (plan/per-student-video-plan.md step 4)."""

import pytest

from animation_agent.manim_codegen import codegen_effort
from syllabyte_common import llm


def test_unset_keeps_the_model_default(monkeypatch):
    monkeypatch.delenv("CODEGEN_EFFORT", raising=False)
    assert codegen_effort() is None


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_a_valid_effort_is_passed_on(monkeypatch, effort):
    monkeypatch.setenv("CODEGEN_EFFORT", effort)
    assert codegen_effort() == effort


def test_a_typo_fails_loudly(monkeypatch):
    monkeypatch.setenv("CODEGEN_EFFORT", "lo")
    with pytest.raises(ValueError, match="CODEGEN_EFFORT"):
        codegen_effort()


class _Stream:
    def __init__(self, kw, sink):
        sink.update(kw)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        class U:
            input_tokens = output_tokens = 1
            cache_read_input_tokens = cache_creation_input_tokens = 0

        class B:
            type, text = "text", "code"

        class M:
            stop_reason, usage, content = "end_turn", U(), [B()]

        return M()


@pytest.mark.parametrize("effort, expected", [(None, None), ("low", {"effort": "low"})])
def test_text_sends_output_config_only_when_an_effort_is_given(monkeypatch, effort, expected):
    sent: dict = {}

    class Client:
        class messages:
            @staticmethod
            def stream(**kw):
                return _Stream(kw, sent)

    monkeypatch.setattr(llm, "get_client", lambda: Client)
    assert llm.text(content="x", stage="t", effort=effort) == "code"
    assert sent.get("output_config") == expected
