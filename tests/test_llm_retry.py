"""A call that fails on the network is made again after a wait (llm.OUTAGE_WAITS); anything else fails at once."""

import anthropic
import httpx
import pytest

from syllabyte_common import llm
from test_codegen_effort import _Stream


def _client(failures: list[Exception], sent: dict):
    class Client:
        class messages:
            @staticmethod
            def stream(**kw):
                if failures:
                    raise failures.pop(0)
                return _Stream(kw, sent)

    return Client


@pytest.fixture
def waits(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    return slept


def test_a_dropped_connection_is_tried_again(monkeypatch, waits):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    failures = [anthropic.APIConnectionError(request=request),
                httpx.RemoteProtocolError("peer closed connection without sending complete message body")]
    monkeypatch.setattr(llm, "get_client", lambda: _client(failures, {}))
    assert llm.text(content="x", stage="t") == "code"
    assert waits == list(llm.OUTAGE_WAITS[:2])


def test_an_outage_longer_than_the_waits_fails(monkeypatch, waits):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    failures = [anthropic.APIConnectionError(request=request) for _ in range(len(llm.OUTAGE_WAITS) + 1)]
    monkeypatch.setattr(llm, "get_client", lambda: _client(failures, {}))
    with pytest.raises(anthropic.APIConnectionError):
        llm.text(content="x", stage="t")
    assert waits == list(llm.OUTAGE_WAITS)


def test_a_bad_request_is_not_retried(monkeypatch, waits):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(400, request=request)
    failures = [anthropic.BadRequestError("bad", response=response, body=None)]
    monkeypatch.setattr(llm, "get_client", lambda: _client(failures, {}))
    with pytest.raises(anthropic.BadRequestError):
        llm.text(content="x", stage="t")
    assert waits == []
