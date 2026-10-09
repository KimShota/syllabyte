"""
Thin Anthropic wrapper shared by every LLM-calling stage of the pipeline
(curriculum_alignment_agent, script_generation_agent, animation_agent).

Responsibilities:
  - Load ANTHROPIC_API_KEY from .env (falls back to the SDK's own credential
    resolution — ANTHROPIC_AUTH_TOKEN / `ant auth login` profile — if unset).
  - Wrap client.messages.parse() for structured (Pydantic) outputs and
    client.messages.create() for plain text (used for Manim code generation,
    which doesn't fit a JSON schema).
  - Build `document` (PDF) and `image` (PNG) content blocks from local paths.
  - Accumulate token usage into a RunManifest so scripts/report.py can print
    a cost/time breakdown per run.

Model default: claude-opus-5 (this project's default per its cost budget
line item — "Anthropic Claude API ... relies on Claude Opus and Claude
Sonnet"). Callers may pass model="claude-sonnet-5" for cheaper/faster calls
(e.g. the critique sub-agent) if desired.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import TypeVar

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from syllabyte_common.models import LLMCallRecord, RunManifest

load_dotenv()

DEFAULT_MODEL = "claude-opus-5"

# Anthropic first-party pricing, $ per million tokens (input, output).
# Used by RunManifest.total_cost_usd() for the Week-1 cost report.
PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # OpenAI prices are not filled in: cost for gpt-* calls reports as $0.
    # Add (input, output) $/Mtok here to include them in the report.
}

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None
_openai_client = None


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_gemini_client = None

# local-* models are served by a vLLM server (OpenAI-compatible API), e.g. the
# lab's DGX Spark reached through `ssh -N -L 8000:localhost:8000 ...`.
# "local-qwen3.8-27b" -> the server's --served-model-name "qwen3.8-27b".
LOCAL_PREFIX = "local-"
_local_client = None


def is_openai_model(model: str) -> bool:
    """Models named gpt-* go to OpenAI, gemini-* to Google (through its
    OpenAI-compatible endpoint) and local-* to a local vLLM server, all via the
    OpenAI SDK; everything else goes to Anthropic. Callers just pass
    model="gpt-5.5" / "gemini-3.8-flash" / "local-qwen3.8-27b"."""
    return model.startswith(("gpt-", "gemini-", LOCAL_PREFIX))


def _openai_request_kwargs(model: str) -> dict:
    """Model name (and extras) to send for an OpenAI-SDK backend. Local Qwen
    runs with thinking off: its reasoning would otherwise land in `content`
    (no reasoning parser is configured) and break JSON / code extraction."""
    if model.startswith(LOCAL_PREFIX):
        return {
            "model": model[len(LOCAL_PREFIX):],
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    return {"model": model}


def get_openai_client(model: str = "gpt-"):
    global _openai_client, _gemini_client, _local_client
    from openai import OpenAI  # imported lazily: only needed for gpt-*/gemini-*/local-* models

    if model.startswith(LOCAL_PREFIX):
        if _local_client is None:
            _local_client = OpenAI(
                api_key=os.environ.get("LOCAL_LLM_API_KEY", "local-secret"),
                base_url=os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:8000/v1"),
                timeout=1800,  # a 27B model on one Spark generates slowly
            )
        return _local_client
    if model.startswith("gemini-"):
        if _gemini_client is None:
            _gemini_client = OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=GEMINI_BASE_URL, max_retries=10)
        return _gemini_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


def _to_openai_messages(content: str | list[dict], system: str | None) -> list[dict]:
    """Translates our Anthropic-style content blocks (text / image) into
    OpenAI chat messages. PDF `document` blocks aren't supported."""
    messages: list[dict] = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    if isinstance(content, str):
        messages.append({"role": "user", "content": content})
        return messages
    parts: list[dict] = []
    for block in content:
        if block["type"] == "text":
            parts.append({"type": "text", "text": block["text"]})
        elif block["type"] == "image":
            src = block["source"]
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"},
            })
        else:
            raise ValueError(f"OpenAI backend doesn't support {block['type']!r} content blocks")
    messages.append({"role": "user", "content": parts})
    return messages


def _record_openai_usage(
    manifest: RunManifest | None, *, stage: str, ku_id: str | None, model: str,
    usage, wall_seconds: float,
) -> None:
    if manifest is None:
        return
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    manifest.llm_calls.append(
        LLMCallRecord(
            stage=stage, ku_id=ku_id, model=model,
            input_tokens=usage.prompt_tokens - cached,
            output_tokens=usage.completion_tokens,
            cache_read_tokens=cached,
            wall_seconds=wall_seconds,
        )
    )


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Segments render concurrently, so expect occasional 429s; the SDK
        # retries them with backoff (its default is 2 retries).
        _client = anthropic.Anthropic(max_retries=6)
    return _client


# --------------------------------------------------------------------------
# Content block builders
# --------------------------------------------------------------------------


def pdf_block(path: str | Path, *, cache: bool = False) -> dict:
    """A `document` content block from a local PDF file."""
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
    block = {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
    }
    if cache:
        block["cache_control"] = {"type": "ephemeral"}
    return block


def image_block(path: str | Path, *, media_type: str = "image/png") -> dict:
    """An `image` content block from a local image file."""
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


# --------------------------------------------------------------------------
# Usage tracking
# --------------------------------------------------------------------------


def _record_usage(
    manifest: RunManifest | None,
    *,
    stage: str,
    ku_id: str | None,
    model: str,
    usage: anthropic.types.Usage,
    wall_seconds: float,
) -> None:
    if manifest is None:
        return
    manifest.llm_calls.append(
        LLMCallRecord(
            stage=stage,
            ku_id=ku_id,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            wall_seconds=wall_seconds,
        )
    )


# --------------------------------------------------------------------------
# Public call helpers
# --------------------------------------------------------------------------


def structured(
    *,
    schema: type[T],
    content: str | list[dict],
    system: str | None = None,
    stage: str,
    ku_id: str | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16000,
    manifest: RunManifest | None = None,
) -> T:
    """Call the model and validate its response against a Pydantic schema.

    Uses client.messages.parse() (output_config-based structured outputs).
    Raises RuntimeError on a refusal stop reason, and re-raises typed
    Anthropic exceptions (retryable ones are already retried by the SDK's
    default max_retries) so the CLI can log which stage/KU failed.
    """
    if is_openai_model(model):
        start = time.monotonic()
        response = get_openai_client(model).chat.completions.parse(
            **_openai_request_kwargs(model),
            messages=_to_openai_messages(content, system),
            response_format=schema,
            max_completion_tokens=max_tokens,
        )
        message = response.choices[0].message
        if message.refusal:
            raise RuntimeError(f"[{stage}] request refused by the model (ku={ku_id}): {message.refusal}")
        _record_openai_usage(
            manifest, stage=stage, ku_id=ku_id, model=model, usage=response.usage,
            wall_seconds=time.monotonic() - start,
        )
        return message.parsed

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
        "output_format": schema,
    }
    if system is not None:
        kwargs["system"] = system

    start = time.monotonic()
    try:
        response = get_client().messages.parse(**kwargs)
    except anthropic.NotFoundError:
        raise
    except anthropic.RateLimitError:
        raise
    except anthropic.APIStatusError:
        raise
    except anthropic.APIConnectionError:
        raise
    wall_seconds = time.monotonic() - start

    if response.stop_reason == "refusal":
        raise RuntimeError(f"[{stage}] request refused by the model (ku={ku_id})")

    _record_usage(
        manifest, stage=stage, ku_id=ku_id, model=model, usage=response.usage,
        wall_seconds=wall_seconds,
    )
    return response.parsed_output


def text(
    *,
    content: str | list[dict],
    system: str | None = None,
    stage: str,
    ku_id: str | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8000,
    manifest: RunManifest | None = None,
) -> str:
    """Call the model and return its plain text response (used for Manim
    code generation, where the output is Python source, not JSON)."""
    if is_openai_model(model):
        start = time.monotonic()
        response = get_openai_client(model).chat.completions.create(
            **_openai_request_kwargs(model),
            messages=_to_openai_messages(content, system),
            max_completion_tokens=max_tokens,
        )
        _record_openai_usage(
            manifest, stage=stage, ku_id=ku_id, model=model, usage=response.usage,
            wall_seconds=time.monotonic() - start,
        )
        return response.choices[0].message.content or ""

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system is not None:
        kwargs["system"] = system

    # Streamed so callers can give thinking a large max_tokens: the SDK
    # refuses non-streaming requests big enough to risk an HTTP timeout.
    start = time.monotonic()
    with get_client().messages.stream(**kwargs) as stream:
        response = stream.get_final_message()
    wall_seconds = time.monotonic() - start

    if response.stop_reason == "refusal":
        raise RuntimeError(f"[{stage}] request refused by the model (ku={ku_id})")

    _record_usage(
        manifest, stage=stage, ku_id=ku_id, model=model, usage=response.usage,
        wall_seconds=wall_seconds,
    )

    parts = [block.text for block in response.content if block.type == "text"]
    if not parts:
        raise RuntimeError(
            f"[{stage}] model returned no text (stop_reason={response.stop_reason}); "
            "max_tokens was likely used up by thinking — raise it"
        )
    return "\n".join(parts)


if __name__ == "__main__":
    import sys

    if "--ping" in sys.argv:

        class _Ping(BaseModel):
            answer: str

        manifest = RunManifest(run_id="ping")
        result = structured(
            schema=_Ping,
            content="Reply with the single word 'pong' as the answer field.",
            stage="ping",
            manifest=manifest,
        )
        print(f"parsed_output: {result}")
        call = manifest.llm_calls[0]
        print(
            f"tokens: input={call.input_tokens} output={call.output_tokens} "
            f"({call.wall_seconds:.2f}s)"
        )
    else:
        print("Usage: python -m syllabyte_common.llm --ping")
