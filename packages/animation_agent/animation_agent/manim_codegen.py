"""
Manim code generation + static safety check — Component 4, Week-1 scope.

generate_scene() gets a first attempt from Claude; repair_scene() is Tier 1
of the ScopeRefine-inspired repair ladder (feed the traceback back for a
targeted fix); regenerate_scene() is Tier 3 (start over from the segment
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
import re

from syllabyte_common.llm import DEFAULT_MODEL, text
from syllabyte_common.models import RunManifest, Segment

from animation_agent.manim_prompt import build_generation_prompt, build_repair_prompt

FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "shutil", "socket", "requests", "urllib",
    "open", "eval", "exec", "compile", "__import__", "input", "exit", "quit",
}

CODE_FENCE_RE = re.compile(r"^```(?:python)?\n|\n```$", re.MULTILINE)


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
        max_tokens=20000, manifest=manifest,
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
        content=prompt, stage="manim_repair", model=model, max_tokens=20000, manifest=manifest,
    )
    return _validated(fixed)
