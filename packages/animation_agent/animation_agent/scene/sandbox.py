"""
Runs a picture program (scene/api.py) and returns its snapshots, or the error to send back to the writer.

The program is model-written code, so it is checked and run apart from the pipeline:
  - statically: no imports, no names or attributes starting with "_" (the usual way out of a restricted
    namespace), no more than MAX_SOURCE characters;
  - in a separate Python process (-I: no site packages, no current directory) with only pure builtins, the api's
    functions, a CPU limit, and a wall-clock timeout. It can't open files or the network: open, __import__ and
    the like aren't in its builtins, and import statements are refused before it runs.
It prints the snapshots as JSON; anything else (an exception, a timeout, too much output) is an error.
"""

from __future__ import annotations

import ast
import functools
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

API_FILE = Path(__file__).with_name("api.py")
MAX_SOURCE = 6000
TIMEOUT_SECONDS = 5
MAX_OUTPUT = 2_000_000

SAFE_BUILTINS = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "int", "isinstance", "len",
    "list", "map", "max", "min", "pow", "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    "__build_class__", "object", "True", "False", "None", "ValueError", "IndexError", "KeyError", "Exception", "StopIteration", "print",
)

BOOT = r"""
import importlib.util, json, resource, sys, traceback
resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
spec = importlib.util.spec_from_file_location("picture_api", sys.argv[1])
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
import builtins
safe = {k: getattr(builtins, k) for k in json.loads(sys.argv[2]) if hasattr(builtins, k)}
safe["print"] = lambda *a, **k: None
source = sys.stdin.read()
env = {"__builtins__": safe, "__name__": "picture", **api.EXPORTS}
try:
    exec(compile(source, "<picture>", "exec"), env)
    snaps = api.snapshots()
    if not snaps:
        raise api.PictureError("the program never called snap(), so there is nothing to show")
    sys.stdout.write(json.dumps({"ok": True, "snapshots": snaps}))
except Exception as e:
    tb = traceback.extract_tb(e.__traceback__)
    line = next((f.lineno for f in reversed(tb) if f.filename == "<picture>"), None)
    sys.stdout.write(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "line": line}))
"""


@dataclass
class Result:
    snapshots: list[dict] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def check_source(source: str) -> str | None:
    """Why the program can't run, before running it (None: it may)."""
    if len(source) > MAX_SOURCE:
        return f"the program is {len(source)} characters; keep it under {MAX_SOURCE}"
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"SyntaxError on line {e.lineno}: {e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return f"line {node.lineno}: no imports; everything the program needs is already defined"
        name = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
        if name and name.startswith("_"):
            return f"line {node.lineno}: names starting with _ aren't allowed ({name})"
    return None


def run_program(source: str) -> Result:
    if problem := check_source(source):
        return Result(error=problem)
    try:
        out = subprocess.run(
            [sys.executable, "-I", "-c", BOOT, str(API_FILE), json.dumps(SAFE_BUILTINS)],
            input=source, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return Result(error=f"the program ran longer than {TIMEOUT_SECONDS}s (a loop that never ends?)")
    if len(out.stdout) > MAX_OUTPUT:
        return Result(error="the program recorded too much")
    if out.returncode < 0 and not out.stdout:  # killed by the CPU limit (SIGXCPU) before the wall clock ran out
        return Result(error=f"the program ran longer than {TIMEOUT_SECONDS}s (a loop that never ends?)")
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        tail = (out.stderr or "").strip().splitlines()[-1:] or ["it stopped without saying why"]
        return Result(error=f"the program crashed: {tail[0]}")
    if not data["ok"]:
        where = f" (line {data['line']})" if data.get("line") else ""
        return Result(error=data["error"] + where)
    return Result(snapshots=data["snapshots"])


@functools.lru_cache(maxsize=64)
def run_cached(source: str) -> Result:
    """run_program, once per program per process: the checker, the describer and the renderer all ask for the
    same program's snapshots, and it is deterministic. Callers must not change the result."""
    return run_program(source)
