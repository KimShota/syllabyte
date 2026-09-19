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
}

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
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
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system is not None:
        kwargs["system"] = system

    start = time.monotonic()
    response = get_client().messages.create(**kwargs)
    wall_seconds = time.monotonic() - start

    if response.stop_reason == "refusal":
        raise RuntimeError(f"[{stage}] request refused by the model (ku={ku_id})")

    _record_usage(
        manifest, stage=stage, ku_id=ku_id, model=model, usage=response.usage,
        wall_seconds=wall_seconds,
    )

    parts = [block.text for block in response.content if block.type == "text"]
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
