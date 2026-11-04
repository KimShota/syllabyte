"""
Parsing and checking the template calls a script draws its lines with. No Manim import.

A call is one line of Python, from a small subset:
    arr = ArrayBars(values=[1, 3, 4], area="bottom_half")     create a template object
    arr.bisect_check(target=3)                                 act on it
Arguments are keyword-only Python literals (numbers, strings, lists, dicts, True/False/None). Nothing is ever
executed: the call is parsed with `ast` and its arguments read with `ast.literal_eval`, then checked against the
template's spec (specs.py).

Every string in a call is read as a raw string, so TeX like "\\frac" or "\\theta" keeps its backslash (in a
normal Python string "\\f" and "\\t" would turn into control characters).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass

from pydantic import ValidationError

from animation_agent.visuals.specs import AREAS, INIT_CHECKS, REGISTRY, areas_overlap

MAX_CALLS_PER_BEAT = 4
MAX_OBJECTS_ON_SCREEN = 3


class CallError(ValueError):
    pass


@dataclass
class Call:
    target: str  # the object's name
    template: str  # its template's name
    action: str | None  # None: this call creates the object
    args: dict


def _as_raw_strings(text: str) -> str:
    """The call with every unprefixed string literal made raw."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError) as e:
        raise CallError(f"not a single line of Python: {e}") from e
    # (type, string) pairs: untokenize's compatibility mode, which re-spaces the tokens itself, so a string
    # that grew by its prefix doesn't clash with the recorded column positions.
    out = [
        (tok.type, "r" + tok.string if tok.type == tokenize.STRING and tok.string[0] in "\"'" else tok.string)
        for tok in tokens
    ]
    return tokenize.untokenize(out)


def _kwargs(node: ast.Call, where: str) -> dict:
    if node.args:
        raise CallError(f"{where}: use keyword arguments only (name=value)")
    args = {}
    for kw in node.keywords:
        if kw.arg is None:
            raise CallError(f"{where}: no **kwargs")
        try:
            args[kw.arg] = ast.literal_eval(kw.value)
        except (ValueError, SyntaxError) as e:
            raise CallError(f"{where}: {kw.arg}= must be a plain value (number, string, list, dict)") from e
    return args


def parse_call(text: str, templates_of: dict[str, str]) -> Call:
    """One call. `templates_of` maps the names created so far in this segment to their template."""
    try:
        tree = ast.parse(_as_raw_strings(text.strip()))
    except SyntaxError as e:
        raise CallError(f"not valid Python: {e.msg}") from e
    if len(tree.body) != 1:
        raise CallError("one statement per call")
    stmt = tree.body[0]

    if isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            raise CallError("create an object as: name = Template(...)")
        call = stmt.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            raise CallError("create an object as: name = Template(...)")
        template = call.func.id
        if template not in REGISTRY:
            raise CallError(f"unknown template {template}; the templates are {', '.join(REGISTRY)}")
        return Call(stmt.targets[0].id, template, None, _kwargs(call, template))

    if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute) and isinstance(stmt.value.func.value, ast.Name)):
        name, action = stmt.value.func.value.id, stmt.value.func.attr
        if name not in templates_of:
            raise CallError(f"{name} hasn't been created in this segment (each segment starts with an empty screen)")
        template = templates_of[name]
        if action not in REGISTRY[template].all_actions():
            raise CallError(f"{template} has no action {action}; its actions are "
                            f"{', '.join(REGISTRY[template].all_actions())}")
        return Call(name, template, action, _kwargs(stmt.value, f"{name}.{action}"))

    raise CallError("a call is either name = Template(...) or name.action(...)")


def _first_error(e: ValidationError) -> str:
    err = e.errors()[0]
    where = ".".join(str(p) for p in err["loc"])
    return f"{where}: {err['msg']}" if where else err["msg"]


@dataclass
class _Live:
    template: str
    area: str
    state: dict


def check_segment(draws: list[list[str]], lines: list[str] | None = None) -> list[str]:
    """Problems with one segment's calls (one list per beat), as messages naming the beat. Simulates the calls:
    every name is created before it's used, arguments match the template, indices stay in range, objects on
    screen at the same time sit in areas that don't overlap. With `lines` (each beat's narration), also checks
    the calls against the words, as the script critic would: the segment shows a diagram, not only notes, and a
    line that counts cells ("eight cells") has a list of that many on screen."""
    return _simulate(draws, lines)[0]


def describe_segment(draws: list[list[str]]) -> list[str]:
    """One sentence per beat saying what its calls show, computed from the calls (so it can't promise anything
    they don't draw): the beat's `visual` when it is drawn from templates. Only for calls check_segment passed."""
    return _simulate(draws, None)[1]


# "eight cells", "a list of 5 numbers": a count the list on screen has to match.
_NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
_COUNTED = re.compile(r"\b(\d+|" + "|".join(_NUMBER_WORDS) + r")\s+(?:sorted\s+|unsorted\s+|blue\s+)?"
                      r"(cells|numbers|items|elements|values|boxes|entries|slots|bars)\b", re.IGNORECASE)


def _counts(line: str) -> list[tuple[int, str]]:
    out = []
    for m in _COUNTED.finditer(line):
        word = m.group(1).lower()
        out.append((int(word) if word.isdigit() else _NUMBER_WORDS[word], m.group(0)))
    return out


def _simulate(draws: list[list[str]], lines: list[str] | None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    said: list[str] = []
    if not draws or not draws[0]:
        return ["beat 1 has no calls: the segment's first beat must create what it shows"], said
    live: dict[str, _Live] = {}
    used: set[str] = set()
    for b, calls in enumerate(draws, 1):
        if len(calls) > MAX_CALLS_PER_BEAT:
            problems.append(f"beat {b}: {len(calls)} calls; at most {MAX_CALLS_PER_BEAT} per beat")
        words = []
        for text in calls:
            where = f"beat {b}, `{text}`"
            try:
                call = parse_call(text, {n: o.template for n, o in live.items()})
                problem, what = _check(call, live, used)
            except CallError as e:
                problem, what = str(e), None
            if problem:
                problems.append(f"{where}: {problem}")
            elif what:
                words.append(what)
        sentence = "; ".join(words) + "."
        said.append(sentence[0].upper() + sentence[1:] if words else "The picture stays as it is.")
        if lines is not None and b <= len(lines):
            problems += _count_problems(b, lines[b - 1], live)
            problems += _echo_problems(b, lines[b - 1], calls)
    if lines is not None and used and all(o.template == "Note" for o in _created(draws)):
        problems.append("the segment shows only Notes: every segment shows a diagram (a list, a grid, a formula), "
                        "and a Note is a label or a question beside it")
    return problems, said


def _created(draws: list[list[str]]) -> list[_Live]:
    out = []
    for calls in draws:
        for text in calls:
            try:
                call = parse_call(text, {})
            except CallError:
                continue
            out.append(_Live(call.template, "", {}))
    return out


def _count_problems(b: int, line: str, live: dict[str, _Live]) -> list[str]:
    from animation_agent.visuals.specs import MAX_CELLS

    lists = [len(o.state["values"]) for o in live.values() if o.template == "ArrayBars"]
    out = []
    for n, phrase in _counts(line):
        if lists and n <= MAX_CELLS and n not in lists:
            shown = " and ".join(str(k) for k in lists)
            out.append(f'beat {b}: the line says "{phrase}" but the list on screen has {shown} cells; draw '
                       f"{n} values so the picture matches the words")
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _echo_problems(b: int, line: str, calls: list[str]) -> list[str]:
    """A note that writes out the line's own words (the critic marks these down: the screen should add something
    the voice doesn't say, like a value, a label or a formula)."""
    spoken = set(_words(line))
    out = []
    for text in calls:
        try:
            tree = ast.parse(_as_raw_strings(text.strip()))
            call = tree.body[0].value  # type: ignore[attr-defined]
            name = call.func.id if isinstance(call.func, ast.Name) else call.func.attr
        except (CallError, SyntaxError, AttributeError, IndexError):
            continue
        if name not in ("Note", "say", "note"):
            continue
        written = next((ast.literal_eval(kw.value) for kw in call.keywords if kw.arg == "text"), None)
        words = _words(written) if isinstance(written, str) else []
        if len(words) >= 3 and sum(w in spoken for w in words) / len(words) >= 0.8:
            out.append(f'beat {b}, `{text}`: the note repeats the line\'s own words; show something the voice '
                       "doesn't say (a value, a label, a formula), or highlight the thing itself instead")
    return out


def _check(call: Call, live: dict[str, _Live], used: set[str]) -> tuple[str | None, str | None]:
    """The call's problem, or None and what it shows in words."""
    spec = REGISTRY[call.template]
    if call.action is None:
        if call.target in used:
            return f"the name {call.target} is already used in this segment; pick another", None
        try:
            params = spec.params.model_validate(call.args)
        except ValidationError as e:
            return _first_error(e), None
        if call.template in INIT_CHECKS and (problem := INIT_CHECKS[call.template](params)):
            return problem, None
        if problem := _area_clash(params.area, live, call.target) or _too_small(spec, params.area):
            return problem, None
        if len(live) >= MAX_OBJECTS_ON_SCREEN:
            return f"at most {MAX_OBJECTS_ON_SCREEN} objects on screen; remove one first", None
        state = spec.init_state(params) | {"_noun": spec.noun}
        live[call.target] = _Live(call.template, params.area, state)
        used.add(call.target)
        what = spec.describe(params) if spec.describe else f"a {spec.noun}"
        return None, f"{what} ({AREA_WORDS[params.area]})"

    action = spec.all_actions()[call.action]
    try:
        args = action.args.model_validate(call.args)
    except ValidationError as e:
        return _first_error(e), None
    obj = live[call.target]
    if call.action == "remove":
        del live[call.target]
    elif call.action == "move":
        if problem := _area_clash(args.area, live, call.target) or _too_small(spec, args.area):
            return problem, None
        obj.area = args.area
    elif action.check and (problem := action.check(obj.state, args)):
        return problem, None
    what = action.says(obj.state, args) if action.says else f"the {spec.noun}: {action.doc.split('.')[0].lower()}"
    return None, what


AREA_WORDS = {
    "full": "filling the frame",
    "top_half": "top half",
    "bottom_half": "bottom half",
    "top_third": "top third",
    "middle_third": "middle third",
    "bottom_third": "bottom third",
    "top_two_thirds": "top two thirds",
    "bottom_two_thirds": "bottom two thirds",
}


def _too_small(spec, area: str) -> str | None:
    first, last = AREAS[area]
    if last - first + 1 < spec.min_rows:
        fits = ", ".join(a for a, (f, l) in AREAS.items() if l - f + 1 >= spec.min_rows)
        return f'{spec.name} needs at least half the frame; use one of: {fits}'
    return None


def _area_clash(area: str, live: dict[str, _Live], me: str) -> str | None:
    for name, other in live.items():
        if name != me and areas_overlap(area, other.area):
            return f'area "{area}" overlaps {name} in "{other.area}"; move or remove {name} first'
    return None


def parse_segment(draws: list[list[str]]) -> list[list[Call]]:
    """The calls of a segment that check_segment passed, parsed, one list per beat."""
    templates_of: dict[str, str] = {}
    out = []
    for calls in draws:
        beat = []
        for text in calls:
            call = parse_call(text, templates_of)
            if call.action is None:
                templates_of[call.target] = call.template
            beat.append(call)
        out.append(beat)
    return out


def segment_draws(segment) -> list[list[str]] | None:
    """A segment's calls, one list per beat, or None when it isn't drawn from templates (no beat has calls)."""
    draws = [list(getattr(beat, "draw", None) or []) for beat in segment.beats]
    return draws if any(draws) else None
