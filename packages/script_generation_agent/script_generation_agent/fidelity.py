"""
Two checks that the video teaches the slides' own content (runs/picture-p4, the fix check): the volume video drew
z = 2 - x^2 - y^2 where the slide has 1 - x^2 - y^2 (the critic gave accuracy 3), and the Hessian and polar videos
put a step of the working on screen without a line saying it.

1. The slide's example. The planner declares the example it draws (the slide, its functions as expressions, its
   numbers) or that the slides have none that fits. Code then checks the declaration against the plan: every
   declared function is one the Picture program draws (compared by value at a few points), and every declared
   number is on the slides and in the plan. A plan that strays is drawn once more with the reason.
2. Each step of the working is said. A beat that writes a new line of a formula (EquationSteps: made, then,
   rewrite) must have a line that says what the step brings in: its new numbers, powers or functions. A line that
   doesn't is marked for the line-matching call (storyboard.match_lines), which rewrites it to say the step.

Model-written functions are never run here: expressions are read with `ast` and evaluated by a small walker that
knows only arithmetic and the math functions.
"""

from __future__ import annotations

import ast
import math
import random
import re
from types import SimpleNamespace

from pydantic import BaseModel, Field


class SlideExample(BaseModel):
    """What the planner says it draws, checked by code."""

    slide: int | None = Field(description="the number of the slide whose example the picture draws, or null")
    functions: list[str] = Field(default_factory=list, description=(
        "each function of that example as a Python expression in x, y (or the slide's own variables), exactly as "
        "the slide has it, e.g. '1 - x**2 - y**2'; [] if it has none"))
    numbers: list[str] = Field(default_factory=list, description=(
        "the example's numbers as the slide writes them (values, bounds, weights, counts), at most 12"))
    own: bool = Field(description=(
        "true only when the slides have no example that fits the picture and you make one up; the lines must then "
        "say it is an example of your own"))


# ---- a safe evaluator for arithmetic expressions --------------------------------------------------------

_FUNCS = {name: getattr(math, name) for name in ("sin", "cos", "tan", "exp", "log", "sqrt", "atan", "asin", "acos",
                                                 "sinh", "cosh", "tanh", "log10", "log2", "fabs")}
_FUNCS["abs"] = abs
_FUNCS["ln"] = math.log
_CONSTS = {"pi": math.pi, "e": math.e}
_OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b, ast.Mod: lambda a, b: a % b}


class _Unsafe(Exception):
    pass


def _eval(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise _Unsafe(node.id)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Pow) and abs(b) > 50:
            raise _Unsafe("power")
        return _OPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, env)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return float(_FUNCS[node.func.id](*[_eval(a, env) for a in node.args]))
    raise _Unsafe(type(node).__name__)


def _expression(text: str) -> ast.AST | None:
    """A declared function as an expression tree: ^ read as a power, 2x as 2*x, 'z = ...' or 'f(x, y) = ...' to
    its right side."""
    text = text.split("=")[-1].strip().replace("^", "**").replace("−", "-")
    text = re.sub(r"(\d)\s*([A-Za-z(])", r"\1*\2", text)
    try:
        return ast.parse(text, mode="eval")
    except SyntaxError:
        return None


def _variables(tree: ast.AST) -> list[str]:
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - set(_FUNCS) - set(_CONSTS)
    return sorted(names)


def program_functions(program: str) -> list[tuple[list[str], ast.AST]]:
    """The functions a picture program defines: lambdas, and defs that return one expression ((args, body))."""
    try:
        tree = ast.parse(program)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            out.append(([a.arg for a in node.args.args], ast.Expression(node.body)))
        elif isinstance(node, ast.FunctionDef) and len(node.body) == 1 and isinstance(node.body[0], ast.Return):
            if node.body[0].value is not None:
                out.append(([a.arg for a in node.args.args], ast.Expression(node.body[0].value)))
    return out


def same_function(declared: ast.AST, names: list[str], args: list[str], body: ast.AST, tries: int = 6) -> bool:
    """Whether the program's function (args, body) equals the declared one (its variables `names`, matched to the
    args in order) at a few points."""
    if len(args) < len(names):
        return False
    rng = random.Random(7)
    agreed = 0
    for _ in range(tries * 3):
        vals = [rng.uniform(0.2, 1.8) for _ in args]
        try:
            a = _eval(declared, dict(zip(names, vals)))
            b = _eval(body, dict(zip(args, vals)))
        except (_Unsafe, ArithmeticError, ValueError, TypeError):
            continue
        if not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9):
            return False
        agreed += 1
        if agreed >= tries:
            return True
    return False


# ---- 1. the slide's example ------------------------------------------------------------------------------

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def _digits(text: str) -> set[str]:
    return {m.group(0).rstrip("0").rstrip(".") if "." in m.group(0) else m.group(0) for m in _NUMBER.finditer(text)}


def _pictures(segments) -> list[str]:
    """The programs of the plan's Picture calls."""
    from animation_agent.visuals.calls import CallError, parse_call
    from animation_agent.visuals.specs import picture_source

    out = []
    for draws in segments:
        for calls in draws or []:
            for c in calls:
                if "Picture(" not in c:
                    continue
                try:
                    call = parse_call(c, {})
                except CallError:
                    continue
                program = call.args.get("program")
                if isinstance(program, list):
                    out.append(picture_source([line.replace("\\'", "'") for line in program]))
    return out


def example_problem(declared: SlideExample | None, segments, slide_text: str):
    """A problem (as the plan's redraw takes them) when the plan strays from the example it declares, or None."""
    if declared is None or declared.own:
        return None
    programs = _pictures(segments)
    everything = "\n".join(c for draws in segments for calls in (draws or []) for c in calls)
    why = []
    if programs:
        defined = [f for p in programs for f in program_functions(p)]
        for text in declared.functions:
            tree = _expression(text)
            if tree is None:
                continue
            names = _variables(tree)
            if defined and not any(same_function(tree, names, args, body) for args, body in defined):
                why.append(f"the slide's function is {text}, but the program draws none equal to it")
    on_slides = _digits(slide_text)
    used = _digits(everything)
    for n in declared.numbers:
        digits = _digits(n)
        if digits and not digits <= on_slides:
            why.append(f"{n} is not on the slides")
        elif digits and not digits <= used:
            why.append(f"the slide's {n} is not in the picture")
    if not why:
        return None
    where = f" (slide {declared.slide})" if declared.slide else ""
    return SimpleNamespace(segment=0, beat=1, call=None, kind="other", message=(
        f"the plan says it draws the slide's example{where}, but " + "; ".join(why[:4]) + ". Draw the slide's own "
        "example exactly (its functions, numbers and region); only when it can't fit the picture, make one of your "
        "own, set own to true, and let the lines say it is your own example"))


# ---- 2. each step of the working is said ----------------------------------------------------------------

_SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety"}
_DENOM = {2: ["half", "halves"], 3: ["third"], 4: ["quarter", "fourth"], 5: ["fifth"], 6: ["sixth"], 8: ["eighth"],
          10: ["tenth"], 12: ["twelfth"]}
_POWER = {2: ["squared", "square"], 3: ["cubed", "cube", "third power", "to the third"], 4: ["fourth", "to the four"]}
_FUNC_WORDS = {"sin": ["sine", "sin"], "cos": ["cosine", "cos"], "tan": ["tangent", "tan"], "ln": ["log", "ln"],
               "log": ["log"], "exp": ["e to the", "exponential"], "sqrt": ["root"], "frac": [], "int": ["integral"],
               "sum": ["sum"], "nabla": ["gradient", "hessian", "nabla", "del"], "lim": ["limit"],
               "theta": ["theta", "θ"], "pi": ["pi", "π"], "Delta": ["delta", "Δ", "change", "small"]}


def _number_words(n: int) -> list[str]:
    words = [str(n)]
    if 0 <= n <= 20:
        words.append(_SMALL[n])
    elif n < 100 and n - n % 10 in _TENS:
        words.append(_TENS[n - n % 10] + ("" if n % 10 == 0 else "-" + _SMALL[n % 10]))
        words.append(_TENS[n - n % 10] + ("" if n % 10 == 0 else " " + _SMALL[n % 10]))
    return words


def step_tokens(tex: str) -> dict[str, list[str]]:
    """What a formula line holds that a line could say, each with the words that say it: numbers, fractions,
    powers, functions."""
    out: dict[str, list[str]] = {}
    tex = re.sub(r"\\([dt]?frac)(\d)(\d)", r"\\\1{\2}{\3}", tex)  # \frac12 is \frac{1}{2}
    for a, b in re.findall(r"\\[dt]?frac\{(\d+)\}\{(\d+)\}", tex):
        out[f"{a}/{b}"] = ([f"{a}/{b}", f"{a} over {b}"] + [w for d in _DENOM.get(int(b), []) for w in (d, d + "s")]
                           + _number_words(int(b))[1:])
    rest = re.sub(r"\\[dt]?frac\{\d+\}\{\d+\}", " ", tex)
    # a denominator under anything else (r^2 over 2): said as "half", "a quarter of", or the number
    for n in re.findall(r"\\[dt]?frac\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\{(\d+)\}", rest):
        out[f"/{n}"] = _number_words(int(n)) + [w for d in _DENOM.get(int(n), []) for w in (d, d + "s")]
    rest = re.sub(r"\\[dt]?frac\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\{\d+\}", lambda m: m.group(0).rsplit("{", 1)[0],
                  rest)
    for p in re.findall(r"\^\{?(\d)\}?", rest):
        out[f"^{p}"] = _POWER.get(int(p), [f"to the {p}"]) + [f"power {p}", f"{_number_words(int(p))[-1]}"]
    rest = re.sub(r"\^\{?\d\}?", " ", rest)
    for n in re.findall(r"(?<![a-zA-Z_])\d+(?:\.\d+)?", rest):
        if n in ("0", "1"):
            continue  # too plain to need saying (bounds, coefficients of one)
        if "." in n:
            whole, frac = n.split(".")
            spoken = " point " + " ".join(_SMALL[int(d)] for d in frac)
            out[n] = [n, n.replace(".", " point "), spoken.strip(), (_number_words(int(whole))[-1] + spoken)]
        else:
            out[n] = _number_words(int(n))
    for name, words in _FUNC_WORDS.items():
        if words and re.search(rf"\\{name}(?![A-Za-z])|(?<![A-Za-z\\]){name}(?![A-Za-z])", tex):
            out[name] = words
    return out


def _formula_steps(segments):
    """(segment, beat 0-based, the new formula line, the line before it) for each beat that writes a formula
    line: an EquationSteps made, or its then() or rewrite()."""
    from animation_agent.visuals.calls import CallError, parse_call

    out = []
    objects: dict[str, str] = {}  # formulas carry over from one segment to the next, like every object
    templates: dict[str, str] = {}
    for s, draws in enumerate(segments):
        for b, calls in enumerate(draws or []):
            for c in calls:
                try:
                    call = parse_call(c, templates)
                except CallError:
                    continue
                if call.action is None:
                    templates[call.target] = call.template
                if templates.get(call.target) != "EquationSteps":
                    continue
                tex = call.args.get("tex")
                if not isinstance(tex, str):
                    continue
                if call.action in (None, "then", "rewrite"):
                    out.append((s, b, tex, objects.get(call.target, "")))
                    objects[call.target] = tex
    return out


# Lines that work through a step: a question, an objective, a check or the peer's wrong idea may point at a formula
# ("how do we integrate this?") without saying its step.
WORKING_STEPS = ("build", "feedback", "predict", "answer")


def unsaid_steps(segments, lines: list[list[str]],
                 roles: list[list[tuple[str, bool]]] | None = None) -> dict[tuple[int, int], str]:
    """{(segment, beat 0-based): why} for each beat that writes a step of the working its line doesn't say:
    none of what the step brings in (its new numbers, fractions, powers, functions) is in the line. `roles` are
    each beat's (tutoring step, is the wrong idea): only working lines are held to it."""
    notes = {}
    for s, b, tex, before in _formula_steps(segments):
        if s >= len(lines) or b >= len(lines[s]):
            continue
        if roles is not None:
            step, wrong = roles[s][b] if s < len(roles) and b < len(roles[s]) else ("", False)
            if wrong or not any(w in step for w in WORKING_STEPS):
                continue
            if "predict" in step and "?" not in tex:
                continue  # a predict line whose formula shows the result: saying it would give the answer away
        new = {k: v for k, v in step_tokens(tex).items() if k not in step_tokens(before)}
        if not new:
            continue  # a rearrangement with nothing new to say aloud
        line = lines[s][b].lower()
        if any(w.lower() in line for words in new.values() for w in words):
            continue
        shown = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", tex)
        shown = re.sub(r"\\[a-zA-Z]+", " ", shown)
        shown = " ".join(re.sub(r"[{}]", "", shown).split())[:60]
        notes[(s, b)] = f"the picture writes the step {shown!r} and the line doesn't say it: say the step"
    return notes
