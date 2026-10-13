"""
Manim code generation + static safety check — Component 4, Week-1 scope.

generate_scene() gets a first attempt from Claude; repair_scene() is Tier 1
of the ScopeRefine-inspired repair ladder (feed the traceback back for a
targeted fix), and repair_layout() is its counterpart for a scene that
renders but fails the legibility check (layout_audit.py);
regenerate_scene() is Tier 3 (start over from the segment
spec, ignoring the broken code). renderer.py orchestrates the full ladder,
falling back to templates.py if every LLM tier still fails to render.

_static_check() is a cheap, local safety net — not a sandbox. It rejects
code that imports/calls things outside the allowed Manim subset before we
ever shell out to `manim render`. This is adequate for solo local
development; it is NOT sufficient isolation for running arbitrary
LLM-generated code in a shared or hosted environment (see the plan's
Risks/notes section).
"""

from __future__ import annotations

import ast
import os
import re

from syllabyte_common.llm import DEFAULT_MODEL, is_openai_model, text
from syllabyte_common.models import RunManifest, Segment

from animation_agent.manim_prompt import (
    build_generation_prompt,
    build_layout_repair_prompt,
    build_repair_prompt,
)

FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "shutil", "socket", "requests", "urllib",
    "open", "eval", "exec", "compile", "__import__", "input", "exit", "quit",
}

CODE_FENCE_RE = re.compile(r"^```(?:python)?\n|\n```$", re.MULTILINE)


def codegen_max_tokens(model: str) -> int:
    """Output budget for a Manim codegen/repair call. On Anthropic models
    thinking counts against max_tokens, and with the legibility rules the
    model can think past 20k before writing any code (text() streams, so a
    large budget is safe). Other backends keep 20k."""
    return 20000 if is_openai_model(model) else 64000


EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_CODEGEN_EFFORT = "low"


def codegen_effort(model: str) -> str | None:
    """Thinking effort for the calls that write Manim code (codegen and its
    repairs): low by default, or CODEGEN_EFFORT. Low made a video in 89 s
    instead of 535 s at the model's default (high) with comparable visuals
    (plan/per-student-video-plan.md, step 4). None for models without an
    effort setting (OpenAI-SDK backends, Haiku 4.5)."""
    if is_openai_model(model) or model.startswith("claude-haiku-4"):
        return None
    effort = os.environ.get("CODEGEN_EFFORT") or DEFAULT_CODEGEN_EFFORT
    if effort not in EFFORTS:
        raise ValueError(f"CODEGEN_EFFORT={effort!r}; expected one of {EFFORTS}")
    return effort


class UnsafeCodeError(Exception):
    pass


def _strip_code_fences(code: str) -> str:
    return CODE_FENCE_RE.sub("", code).strip()


def _static_check(code: str) -> None:
    """Raises UnsafeCodeError if the code imports or calls anything outside
    the allowed Manim subset. Raises SyntaxError (propagated) if the code
    doesn't even parse — that's a render-time failure, not a safety one, so
    the caller should treat it the same as any other render failure and let
    the repair ladder handle it."""
    tree = ast.parse(code)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root != "manim":
                    raise UnsafeCodeError(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root != "manim" and module != "animation_agent.layout":
                raise UnsafeCodeError(f"forbidden import: {module}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise UnsafeCodeError(f"forbidden name used: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            raise UnsafeCodeError(f"forbidden attribute access: .{node.attr}")


def validate_generated_code(code: str) -> str:
    """Strips markdown code fences and runs the static safety check. Public
    because visual_critic.py's repair path needs the identical validation
    every other codegen path goes through."""
    code = _strip_code_fences(code)
    _static_check(code)
    return code


_validated = validate_generated_code


def check_beat_structure(code: str, n_beats: int) -> str | None:
    """Returns a description of the problem, or None if construct() calls
    self.end_beat(1), ..., self.end_beat(n_beats) exactly once each, in
    order, with literal arguments, and ends on self.end_beat(n_beats).
    A missing beat would silently drop that sentence's visual (and leave
    the clip short of its audio), so this runs before every render."""
    tree = ast.parse(code)

    # The sync lives in layout.GridLayoutScene.end_beat. A scene that
    # defines its own end_beat (or isn't a GridLayoutScene) would pass every
    # other check while bypassing the real audio sync.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "GridLayoutScene" not in bases:
                return "The scene class must subclass GridLayoutScene (not Scene)."
            if any(isinstance(n, ast.FunctionDef) and n.name == "end_beat" for n in node.body):
                return "Do not define end_beat: it is inherited from GridLayoutScene."

    calls = sorted(
        (
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "end_beat"
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    args = [
        node.args[0].value
        if len(node.args) == 1 and isinstance(node.args[0], ast.Constant) else None
        for node in calls
    ]
    expected = list(range(1, n_beats + 1))
    if args != expected:
        return (
            f"The scene must call self.end_beat(N) with a literal N once per beat, "
            f"in order: expected {expected}, found {args}."
        )

    construct = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "construct"),
        None,
    )
    last = construct.body[-1] if construct and construct.body else None
    if not (isinstance(last, ast.Expr) and last.value is calls[-1]):
        return f"self.end_beat({n_beats}) must be the last statement of construct()."
    return None


# `x_T`, `x^2`, `Y_{0}`: a subscript or superscript typed into plain Text shows the `_`/`^` on screen.
_SCRIPT_MARK_RE = re.compile(r"[^\s_^][_^][{A-Za-z0-9(]")
_LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_OPERATORS = {"-", "−", "+", "=", "×", "÷", "·", "/", "<", ">", "≤", "≥", "≠"}


def check_text_formulas(code: str) -> str | None:
    """Returns a description of the problem, or None if no formula is set as
    plain Text. Text can't do subscripts, so a formula typed into it shows
    literal `_`/`^` or LaTeX commands, and one built from separate Text pieces
    (a lone "−" between two halves) falls apart when arranged; one MathTex
    lays it out correctly."""
    problems = []
    for node in ast.walk(ast.parse(code)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Text"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            continue
        value = node.args[0].value
        if _SCRIPT_MARK_RE.search(value) or _LATEX_COMMAND_RE.search(value):
            problems.append(f"line {node.lineno}: Text({value!r}) types a subscript, superscript or LaTeX command")
        elif value.strip() in _OPERATORS:
            problems.append(f"line {node.lineno}: Text({value!r}) is a lone operator, so a formula is built from pieces")
    if not problems:
        return None
    return (
        "Formulas must be ONE MathTex, never Text: "
        + "; ".join(problems)
        + '. Rewrite each formula as a single MathTex (e.g. MathTex(r"\\bar{y}_T", "-", r"\\bar{y}_C"), split into '
        "substrings when parts need their own colour), keeping its position, colours and timing."
    )


def generate_scene(
    segment: Segment,
    beat_durations: list[float],
    class_name: str,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> str:
    system, user = build_generation_prompt(segment, beat_durations, class_name)
    code = text(
        content=user, system=system, stage="manim_codegen", model=model,
        max_tokens=codegen_max_tokens(model), manifest=manifest, effort=codegen_effort(model),
    )
    return _validated(code)


def repair_scene(
    code: str,
    traceback_text: str,
    segment: Segment,
    beat_durations: list[float],
    class_name: str,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> str:
    prompt = build_repair_prompt(code, traceback_text, segment, beat_durations, class_name)
    fixed = text(
        content=prompt, stage="manim_repair", model=model, max_tokens=codegen_max_tokens(model), manifest=manifest, effort=codegen_effort(model),
    )
    return _validated(fixed)


def repair_layout(
    code: str,
    problems: str,
    segment: Segment,
    beat_durations: list[float],
    class_name: str,
    *,
    model: str = DEFAULT_MODEL,
    manifest: RunManifest | None = None,
) -> str:
    """Fixes a scene that renders but fails the layout audit. `problems` is
    LayoutReport.format_for_prompt()."""
    prompt = build_layout_repair_prompt(code, problems, segment, beat_durations, class_name)
    fixed = text(
        content=prompt, stage="manim_layout_repair", model=model, max_tokens=codegen_max_tokens(model), manifest=manifest, effort=codegen_effort(model),
    )
    return _validated(fixed)
