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


def test_a_stalled_request_gives_up_after_a_minute_not_ten(monkeypatch):
    # runs/h2h: on a flaky connection one request sat 7 minutes, another the SDK's full 10, before its retry
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(llm, "_client", None)
    timeout = llm.get_client().timeout
    assert timeout.read == llm.STALL_SECONDS == 60 and timeout.connect == llm.CONNECT_SECONDS


def test_a_server_that_goes_silent_times_out_and_the_call_is_made_again(monkeypatch, waits):
    """A real socket that accepts the request and never answers: the client gives up after the stall limit (cut to
    half a second here) instead of waiting on it, and the call is made again."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    held = []
    threading.Thread(target=lambda: held.append(server.accept()), daemon=True).start()
    silent = anthropic.Anthropic(api_key="test", base_url=f"http://127.0.0.1:{server.getsockname()[1]}",
                                 max_retries=0, timeout=anthropic.Timeout(0.5, connect=0.5))
    sent: dict = {}
    clients = [silent, _client([], sent)]
    monkeypatch.setattr(llm, "get_client", lambda: clients[0] if len(clients) == 1 else clients.pop(0))
    assert llm.text(content="x", stage="t") == "code"
    assert waits == [llm.OUTAGE_WAITS[0]]
    server.close()


def test_a_stream_that_goes_silent_midway_is_made_again(monkeypatch, waits):
    """The server answers and starts the stream, then goes silent: the SDK's own HTTP package (httpx2) raises the
    timeout while the stream is read, and that is caught as an outage too."""
    import socket
    import threading

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    held = []

    def answer_then_hang():
        conn, _ = server.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\n\r\n"
                     b'event: ping\ndata: {"type": "ping"}\n\n')
        held.append(conn)

    threading.Thread(target=answer_then_hang, daemon=True).start()
    silent = anthropic.Anthropic(api_key="test", base_url=f"http://127.0.0.1:{server.getsockname()[1]}",
                                 max_retries=0, timeout=anthropic.Timeout(0.5, connect=0.5))
    sent: dict = {}
    clients = [silent, _client([], sent)]
    monkeypatch.setattr(llm, "get_client", lambda: clients[0] if len(clients) == 1 else clients.pop(0))
    assert llm.text(content="x", stage="t") == "code"
    assert waits == [llm.OUTAGE_WAITS[0]]
    server.close()
