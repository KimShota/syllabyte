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

MAX_CALLS_PER_BEAT = 6
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


_DOUBLED = re.compile(r"\\\\(?=[A-Za-z])")


def _undouble(value):
    """Strings are read raw, but a model writing calls inside JSON sometimes doubles a backslash ("\\\\Sigma").
    In TeX that is a line break followed by the word "Sigma", and isolating the piece "\\Sigma" in it then
    splits the two backslashes, which LaTeX can't convert (runs/course-test-1, the SVD video). A formula here
    is one line, so a doubled backslash before a letter is always that mistake."""
    if isinstance(value, str):
        return _DOUBLED.sub(r"\\", value)
    if isinstance(value, list):
        return [_undouble(v) for v in value]
    if isinstance(value, dict):
        return {k: _undouble(v) for k, v in value.items()}
    return value


def _kwargs(node: ast.Call, where: str) -> dict:
    if node.args:
        raise CallError(f"{where}: use keyword arguments only (name=value)")
    args = {}
    for kw in node.keywords:
        if kw.arg is None:
            raise CallError(f"{where}: no **kwargs")
        try:
            args[kw.arg] = _undouble(ast.literal_eval(kw.value))
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


@dataclass
class Problem:
    """One thing wrong with a script's calls. `kind` says what (KINDS), so normalize.py can fix the mechanical
    ones without an LLM; `message` names the beat and the call the way a fix prompt does."""

    segment: int
    beat: int  # 1-based, within the segment
    call: int | None  # index of the call within the beat, None for the beat or segment as a whole
    kind: str
    message: str

    def __str__(self) -> str:
        return self.message


# What a problem is about, from its message (the checks in specs.py return plain sentences).
_KINDS = [
    ("hasn't been created", "not_created"), ("fit on screen", "too_long"), ("symbols", "formula_too_long"),
    ("zero vector", "zero_vector"), ("off the grid", "off_grid"), ("sits exactly", "hidden_ghost"),
    ("overlaps", "layout"), ("needs at least half", "layout"), ("objects on screen", "layout"),
    ("calls; at most", "too_many_calls"), ("repeats the line", "echo"), ("only put text", "text_only"),
    ("only Notes", "notes_only"), ("the line says", "count"), ("names none of the", "unmentioned"),
    ("doesn't draw this idea", "wrong_template"),
]


def _kind(message: str) -> str:
    return next((kind for pattern, kind in _KINDS if pattern in message), "other")


@dataclass
class Simulation:
    problems: list[Problem]
    said: list[list[str]]  # per segment, per beat: what the beat's calls show, in words


def check_script(segments: list[list[list[str]] | None], lines: list[list[str]] | None = None,
                 allowed: set[str] | None = None) -> list[Problem]:
    """Problems with a whole script's calls (per segment, per beat), simulated in order. What a segment leaves on
    screen stays on screen into the next one (the renderer replays it), so a later segment can keep acting on it;
    creating a name that is on screen replaces that object. A segment given as None is drawn by LLM code and is
    skipped. With `lines` (each beat's narration), the calls are also checked against the words, as the script
    critic would: every segment shows a diagram, a line that counts cells has that many, notes don't repeat the
    line, and no beat puts only text on screen."""
    return simulate_script(segments, lines, allowed=allowed).problems


def describe_script(segments: list[list[list[str]] | None]) -> list[list[str]]:
    """Per segment, one sentence per beat saying what its calls show, computed from the calls (so it can't promise
    anything they don't draw): the beat's `visual` when it is drawn from templates."""
    return simulate_script(segments, None).said


def check_segment(draws: list[list[str]], lines: list[str] | None = None, carried: list[str] | None = None,
                  ) -> list[str]:
    """check_script for one segment, after `carried` (every call of the segments before it, which the renderer
    replays before beat 1). Problems as messages."""
    segments = [[carried]] if carried else []
    problems = simulate_script([*segments, draws], None if lines is None else [*[[""]] * len(segments), lines],
                               report_from=len(segments)).problems
    return [p.message for p in problems]


def describe_segment(draws: list[list[str]], carried: list[str] | None = None) -> list[str]:
    segments = [[carried]] if carried else []
    return simulate_script([*segments, draws], None).said[-1]


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


def reveal_flags(segments: list[list[list[str]] | None]) -> list[list[list[bool]] | None]:
    """Per segment, per beat, per call: whether the call shows a result (ActionSpec.reveals), judged from what is on
    screen just before it. normalize.hold_reveals moves these out of question and predict lines."""
    out: list[list[list[bool]] | None] = []
    live: dict[str, _Live] = {}
    for draws in segments:
        if draws is None:
            out.append(None)
            continue
        seg = []
        for calls in draws:
            beat = []
            for text in calls:
                flag = False
                try:
                    call = parse_call(text, {n: o.template for n, o in live.items()})
                    if call.action is not None and call.target in live:
                        action = REGISTRY[call.template].all_actions()[call.action]
                        reveals = action.reveals
                        if callable(reveals):
                            reveals = reveals(live[call.target].state, action.args.model_validate(call.args))
                        flag = bool(reveals)
                    _check(call, live)
                except Exception:  # noqa: BLE001 - a broken call reveals nothing; the checker reports it
                    pass
                beat.append(flag)
            seg.append(beat)
        out.append(seg)
    return out


# Words that point at cells without naming their values ("the first two", "every cell", "the smaller front").
_POINTING = set("""all every each both whole these those this that rest first last middle front fronts end left
right half halves smallest smaller largest larger biggest bigger minimum maximum min max sorted unsorted target
next pair neighbour neighbor""".split())


def _mentions_values(line: str, values: list) -> bool:
    spoken = set(_words(line))
    if spoken & _POINTING:
        return True
    for v in values:
        tokens = _words(str(v if not isinstance(v, float) or not v.is_integer() else int(v)))
        if tokens and all(t in spoken for t in tokens):
            return True
        if isinstance(v, int | float) and float(v).is_integer() and 0 <= v < len(_SPOKEN_NUMBERS):
            if _SPOKEN_NUMBERS[int(v)] in spoken:
                return True
    return False


_SPOKEN_NUMBERS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                   "sixteen seventeen eighteen nineteen twenty").split()


def _unmentioned(b: int, text: str, call: Call, live: dict[str, _Live], line: str) -> str | None:
    """A highlight on cells the line never names: the course test's critic marked these down as "visuals not tied
    to the line" (an objective line lighting up a cell for no reason)."""
    if call.action != "highlight" or call.template not in ("ArrayBars", "MergeSort") or call.target not in live:
        return None
    state = live[call.target].state
    values = state["values"] if call.template == "ArrayBars" else state["ms"]["values"]
    picked = [values[i] for i in call.args.get("indices", []) if isinstance(i, int) and 0 <= i < len(values)]
    if not picked or _mentions_values(line, picked):
        return None
    shown = ", ".join(str(v) for v in picked)
    return (f"beat {b}, `{text}`: the line names none of the cells it highlights ({shown}); highlight what the "
            "line talks about, or leave the picture as it is")


def simulate_script(segments: list[list[list[str]] | None], lines: list[list[str]] | None = None, *,
                    report_from: int = 0, allowed: set[str] | None = None) -> Simulation:
    """The simulation behind check_script; problems in segments before `report_from` are not reported (they are
    the carried calls of check_segment). With `allowed`, creating a template not in it is a problem (the KU's
    picture plan chose which templates draw it: script_generation_agent.picture_plan)."""
    problems: list[Problem] = []
    said: list[list[str]] = []
    live: dict[str, _Live] = {}
    for s, draws in enumerate(segments):
        if draws is None:
            said.append([])
            continue
        report = s >= report_from
        seg_lines = lines[s] if lines is not None and s < len(lines) else None
        shown = {o.template for o in live.values()}
        seg_said = []

        def flag(beat: int, call: int | None, message: str) -> None:
            if report:
                problems.append(Problem(s, beat, call, _kind(message), message))

        if report and not live and (not draws or not draws[0]):
            flag(1, None, "beat 1 has no calls: the segment's first beat must create what it shows")
        for b, calls in enumerate(draws, 1):
            if report and len(calls) > MAX_CALLS_PER_BEAT:
                flag(b, None, f"beat {b}: {len(calls)} calls; at most {MAX_CALLS_PER_BEAT} per beat")
            words = []
            for c, text in enumerate(calls):
                try:
                    call = parse_call(text, {n: o.template for n, o in live.items()})
                    if allowed is not None and call.action is None and call.template not in allowed:
                        problem, what = (f"{call.template} doesn't draw this idea's picture; use "
                                         f"{', '.join(sorted(allowed))}"), None
                    else:
                        problem, what = _check(call, live)
                    if call.action is None and not problem:
                        shown.add(call.template)
                    if not problem and seg_lines is not None and b <= len(seg_lines) and report:
                        if mention := _unmentioned(b, text, call, live, seg_lines[b - 1]):
                            flag(b, c, mention)
                except CallError as e:
                    problem, what = str(e), None
                if problem:
                    flag(b, c, f"beat {b}, `{text}`: {problem}")
                elif what:
                    words.append(what)
            sentence = "; ".join(words) + "."
            seg_said.append(sentence[0].upper() + sentence[1:] if words else "The picture stays as it is.")
            if seg_lines is not None and b <= len(seg_lines) and report:
                for message, c in (_count_problems(b, seg_lines[b - 1], live)
                                   + _echo_problems(b, seg_lines[b - 1], calls)):
                    flag(b, c, message)
                if calls and all(_only_text(text) for text in calls):
                    flag(b, None, f"beat {b}: its calls only put text on screen (a note, a cleared highlight); the "
                                  "reviewer scores a text-only picture 4 of 10 at most. Show the line in the diagram "
                                  "itself (highlight, point, add, apply, grey out), or leave the beat [] to keep the "
                                  "picture")
        if seg_lines is not None and report and shown and shown <= {"Note"}:
            flag(1, None, "the segment shows only Notes: every segment shows a diagram (a list, a grid, a "
                          "formula), and a Note is a label or a question beside it")
        said.append(seg_said)
    return Simulation(problems, said)


def _count_problems(b: int, line: str, live: dict[str, _Live]) -> list[tuple[str, int | None]]:
    from animation_agent.visuals.specs import MAX_CELLS

    lists = [len(o.state["values"]) for o in live.values() if o.template == "ArrayBars"]
    out = []
    for n, phrase in _counts(line):
        if lists and n <= MAX_CELLS and n not in lists:
            shown = " and ".join(str(k) for k in lists)
            out.append((f'beat {b}: the line says "{phrase}" but the list on screen has {shown} cells; draw '
                        f"{n} values so the picture matches the words", None))
    return out


# Calls that change only text, or take something away, without drawing the idea.
TEXT_ONLY_ACTIONS = {"note", "say", "clear", "unpoint", "counter", "clear_ghosts"}


def _call_name(text: str) -> tuple[ast.Call | None, str | None]:
    """The call node and its template or action name, without checking anything."""
    try:
        stmt = ast.parse(_as_raw_strings(text.strip())).body[0]
    except (CallError, SyntaxError, IndexError):
        return None, None
    call = getattr(stmt, "value", None)
    if not isinstance(call, ast.Call):
        return None, None
    if isinstance(call.func, ast.Name):
        return call, call.func.id
    if isinstance(call.func, ast.Attribute):
        return call, call.func.attr
    return None, None


def _only_text(text: str) -> bool:
    """A call that only changes text. A formula written as a note (note(tex=...)) is a picture (SHARED_RUBRIC)."""
    call, name = _call_name(text)
    if call is not None and name == "note" and any(kw.arg == "tex" for kw in call.keywords):
        return False
    return name == "Note" or name in TEXT_ONLY_ACTIONS


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _echo_problems(b: int, line: str, calls: list[str]) -> list[tuple[str, int | None]]:
    """A note that writes out the line's own words (the critic marks these down: the screen should add something
    the voice doesn't say, like a value, a label or a formula)."""
    spoken = set(_words(line))
    out = []
    for c, text in enumerate(calls):
        call, name = _call_name(text)
        if call is None or name not in ("Note", "say", "note"):
            continue
        try:
            written = next((ast.literal_eval(kw.value) for kw in call.keywords if kw.arg == "text"), None)
        except ValueError:
            continue
        words = _words(written) if isinstance(written, str) else []
        if len(words) >= 3 and sum(w in spoken for w in words) / len(words) >= 0.8:
            out.append((f'beat {b}, `{text}`: the note repeats the line\'s own words; show something the voice '
                        "doesn't say (a value, a label, a formula), or highlight the thing itself instead", c))
    return out


def _check(call: Call, live: dict[str, _Live]) -> tuple[str | None, str | None]:
    """The call's problem, or None and what it shows in words. Creating a name that is on screen replaces it."""
    spec = REGISTRY[call.template]
    if call.action is None:
        try:
            params = spec.params.model_validate(call.args)
        except ValidationError as e:
            return _first_error(e), None
        if call.template in INIT_CHECKS and (problem := INIT_CHECKS[call.template](params)):
            return problem, None
        others = {n: o for n, o in live.items() if n != call.target}
        if problem := _area_clash(params.area, others, call.target) or _too_small(spec, params.area):
            return problem, None
        if len(others) >= MAX_OBJECTS_ON_SCREEN:
            return f"at most {MAX_OBJECTS_ON_SCREEN} objects on screen; remove one first", None
        replaced = call.target in live
        live.pop(call.target, None)
        state = spec.init_state(params) | {"_noun": spec.noun}
        live[call.target] = _Live(call.template, params.area, state)
        what = spec.describe(params) if spec.describe else f"a {spec.noun}"
        return None, ("it is replaced by " if replaced else "") + f"{what} ({AREA_WORDS[params.area]})"

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


def script_segments(script) -> list[list[list[str]] | None]:
    """A templated script's calls per segment, per beat; None for a segment drawn by LLM code."""
    return [[list(b.draw) for b in seg.beats] if getattr(seg, "drawn_by", "code") == "templates" else None
            for seg in script.segments]


def carried_calls(script, i: int) -> list[str]:
    """Every call of the template segments before segment i, in order: what the renderer replays before beat 1."""
    return [c for draws in script_segments(script)[:i] if draws is not None for beat in draws for c in beat]
