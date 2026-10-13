"""Which Anthropic key the shared client uses: ANTHROPIC_KEY_NAME names the environment variable that holds it."""

import pytest

from syllabyte_common import llm


def test_defaults_to_the_first_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_KEY_NAME", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "first")
    monkeypatch.setenv("ANTHROPIC_API_KEY_2", "second")
    assert llm.anthropic_api_key() == "first"


def test_uses_the_key_named_by_anthropic_key_name(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "first")
    monkeypatch.setenv("ANTHROPIC_API_KEY_2", "second")
    monkeypatch.setenv("ANTHROPIC_KEY_NAME", "ANTHROPIC_API_KEY_2")
    assert llm.anthropic_api_key() == "second"


def test_a_named_key_that_is_missing_is_an_error_not_a_silent_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "first")
    monkeypatch.delenv("ANTHROPIC_API_KEY_2", raising=False)
    monkeypatch.setenv("ANTHROPIC_KEY_NAME", "ANTHROPIC_API_KEY_2")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY_2 is not set"):
        llm.anthropic_api_key()


def test_with_no_key_at_all_the_sdk_resolves_credentials_itself(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_KEY_NAME", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.anthropic_api_key() is None


def test_the_client_is_built_with_the_chosen_key(monkeypatch):
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY_2", "second")
    monkeypatch.setenv("ANTHROPIC_KEY_NAME", "ANTHROPIC_API_KEY_2")
    try:
        assert llm.get_client().api_key == "second"
    finally:
        monkeypatch.setattr(llm, "_client", None)
