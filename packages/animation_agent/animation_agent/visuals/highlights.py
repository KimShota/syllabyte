"""
Highlights that say what they show: code rules for the colours and cells a writer highlights. No Manim import.

The computed steps make the list right, but the highlights around them are the writer's, and in runs/trace-fix-1
and runs/trace-fix-2 they were most of what the critic still marked down in the selection-sort video:
  - an unsorted 5, 2, 8 turned GREEN under the objective (twice), though green is what a sorted or found cell
    looks like, so it showed an unsorted prefix as sorted;
  - a predict line ("which is the minimum of 5, 9 and 8?") highlighting 5, its answer, before the answer;
  - colours outside the video's colour key (yellow, teal);
  - a red "wrong idea" ghost drawn around a peer's correct answer.
So, on a list (ArrayBars):
  - a GREEN highlight may colour only cells that are sorted or found (specs.green_cells); one that colours any
    other cell is dropped (unless the list was changed by hand with swap or set_value: code can't tell then);
  - a question or predict line may not highlight the cell its answer step lands on (the next step
    on that list in the segment: selection's minimum, insertion's place, bisection's middle or discarded half, a
    scan or found that hits, in this segment or a later one): that call is dropped, and the step shows it on the
    line that answers;
  - a highlight of one or two cells whose colour isn't in the colour key takes the colour of the one key term
    its line names, if it names exactly one (never green on cells that aren't sorted or found);
  - a ghost (a wrong idea) outside the wrong-idea line becomes a highlight of the same cells.

The data structures (BinaryTree, Graph, LinkedList) had none of these rules, and in runs/dsa-trace-2 their
question lines lit the answer: a BST search's whole path under "which way first?", the route to the first node
listed under "which node is listed first?", the last node under "which is listed last?"; and a traversal ended with
every node green. So, on their nodes:
  - a question or predict line may not highlight a node the coming operation lands on (the next node down, the
    one found, the parent a value is placed under, the node a search visits or settles, through every step of an
    operation run one step per call). A highlight of more than half the nodes that also lights nodes the operation
    doesn't land on is context (all the leaves, every open node) and stays;
  - GREEN is for found: a highlight of a node no search has found turns TEAL;
  - a ghost outside the wrong-idea line becomes a highlight of the nodes it points at.
"""

from __future__ import annotations

import ast
import copy
import json
import re

from animation_agent.visuals.calls import _check, _Live, parse_call
from animation_agent.visuals.specs import REGISTRY, green_cells

ASKING_STEPS = ("question", "predict")
_STEPS = {"selection_step", "insertion_step", "bisect_check", "bisect_discard", "bisect_step", "scan", "found"}
NEUTRAL = "TEAL"  # a highlight that names no key term: the examples' colour for "look here"


def _indices(call) -> list[int]:
    if "indices" in call.args:
        return list(call.args["indices"])
    if "index" in call.args:
        return [call.args["index"]]
    return []


def _answer_cells(state: dict, action: str, args: dict) -> set[int]:
    """The cells the step reveals as its result, on a copy of the list's state."""
    spec = REGISTRY["ArrayBars"].all_actions()[action]
    st = copy.deepcopy(state)
    try:
        a = spec.args.model_validate(args)
        if spec.check and spec.check(st, a):
            return set()
    except Exception:  # noqa: BLE001 - a broken step reveals nothing; the checker reports it
        return set()
    if action in ("selection_step", "insertion_step"):
        ev = st["last_sort"][-1]
        if action == "selection_step":
            return {ev["min"]}
        return {ev["to"]} if ev["to"] != ev["from"] else set()  # a value that stays isn't the answer
    if action in ("bisect_check",):
        lo, hi = st["bisect"]["range"]
        return {(lo + hi) // 2}
    if action in ("bisect_discard", "bisect_step"):
        mid, lo, hi, found = st["bisect"]["last"]
        if found:
            return {mid}
        v, t = st["values"], st["bisect"]["target"]
        return set(range(lo, mid + 1)) if v[mid] < t else set(range(mid, hi + 1))
    if action in ("scan", "found"):
        return set(st.get("found", set())) - set(state.get("found", set()))
    return set()


def _next_step(segments: list[list[list[str]] | None], s: int, b: int, name: str, live: dict,
               steps: set[str] | None = None) -> tuple[str, dict] | None:
    """The first step on `name` after beat `b` (0-based) of segment `s`, in it or a later one (the list stays on
    screen): (action, args)."""
    later = [calls for draws in segments[s + 1:] if draws is not None for calls in draws]
    for calls in segments[s][b + 1:] + later:
        for text in calls:
            try:
                call = parse_call(text, {n: o.template for n, o in live.items()})
            except Exception:  # noqa: BLE001
                continue
            if call.target == name and call.action in (_STEPS if steps is None else steps):
                return call.action, call.args
            if call.target == name and call.action is None:
                return None  # created again: what came before is gone
    return None


def _with_colour(text: str, colour: str) -> str:
    """The call with its colour= argument set to `colour`."""
    tree = ast.parse(text.strip())
    call = tree.body[0].value
    call.keywords = [kw for kw in call.keywords if kw.arg != "colour"] + [ast.keyword("colour", ast.Constant(colour))]
    return ast.unparse(tree).replace("'", '"')


def _key_colour(line: str, key: dict[str, str]) -> str | None:
    """The colour of the one key term the line names, if it names exactly one."""
    named = {colour for term, colour in key.items()
             if re.search(r"\b" + re.escape(term.lower()) + r"\b", line.lower())}
    return named.pop() if len(named) == 1 else None


# ---- The data structures ---------------------------------------------------------------------------------------

_NODES_ARG = {"BinaryTree": "values", "Graph": "nodes", "LinkedList": "indices"}
CONTEXT_SHARE = 0.5  # a highlight of more than this share of the nodes is context, not an answer
# A ghost and the nodes it points at, for a ghost on a line that isn't the wrong idea.
_GHOST_NODES = {("BinaryTree", "ghost"): lambda a: [a["parent"]],
                ("BinaryTree", "ghost_turn"): lambda a: [a["at"]],
                ("BinaryTree", "ghost_mark"): lambda a: list(a["values"]),
                ("Graph", "ghost_edge"): lambda a: [a["a"], a["b"]],
                ("Graph", "ghost_mark"): lambda a: list(a["nodes"]),
                ("LinkedList", "ghost"): lambda a: [a["from_index"]]}


def _structure_steps(template: str) -> set[str]:
    from animation_agent.visuals.trace import STEP_ACTIONS

    return STEP_ACTIONS.get(template, set())


def _node_count(template: str, st: dict) -> int:
    if template == "BinaryTree":
        return len(st["heap"]) if st["kind"] != "bst" else len(st["nodes"])
    if template == "Graph":
        return len(st["nodes"])
    return len(st["slots"])


def _landed(template: str, st: dict, action: str) -> list:
    """The nodes the step just run landed on, as a highlight names them (values, node names, positions)."""
    ev = st.get("last") or {}
    if template == "BinaryTree":
        if action in ("insert_step", "search_step"):
            if ev.get("found") or (action == "insert_step" and ev.get("new") is not None):
                return [ev["with"]] if ev.get("with") is not None else []
            return [ev["next"]] if "next" in ev else []
        if action in ("insert", "search"):
            out = [v for v, _ in ev.get("path", [])[1:]]
            if action == "insert" and ev.get("parent") is not None:
                out.append(ev["parent"])
            if action == "search" and ev.get("found"):
                out.append(ev["v"])
            return out
        if action == "push_step" and "placed" in ev:
            return [ev["parent"]] if ev.get("parent") is not None else []
        if action == "traverse_step":
            return [ev["v"]]
        return []
    if template == "Graph":
        pick = {"dfs_step": lambda: [ev.get("visit")], "bfs_level": lambda: list(ev.get("nodes", [])),
                "dijkstra_step": lambda: [ev.get("settled")], "prim_step": lambda: [ev.get("added")],
                "topo_step": lambda: [ev.get("node")]}.get(action)
        return [n for n in (pick() if pick else []) if n is not None]
    if action == "find_step" and ev.get("id") is not None and ev["id"] in st["slots"]:
        if ev["checks"] == 1 and not ev["hit"]:
            return []  # every search starts at the head: lighting it gives nothing away (like a tree's root)
        return [st["slots"].index(ev["id"])]
    return []


def _answer_nodes(template: str, state: dict, action: str, args: dict) -> set:
    """The nodes the coming operation lands on: its next step and, when the operation runs one step per call (a
    tree's _step actions, a list's find_step), each later step of it until it ends. On a copy of the state."""
    spec = REGISTRY[template].all_actions()[action]
    st = copy.deepcopy(state)
    out: set = set()
    for _ in range(MAX_OPERATION_STEPS):
        try:
            a = spec.args.model_validate(args)
            if spec.check and spec.check(st, a):
                break
        except Exception:  # noqa: BLE001 - a broken step reveals nothing; the checker reports it
            break
        out |= set(_landed(template, st, action))
        going = ((template == "BinaryTree" and action.endswith("_step") and action != "traverse_step"
                  and st.get("op") is not None)
                 or (template == "LinkedList" and action == "find_step" and not st["find"]["done"]))
        if not going:
            break
    return out


MAX_OPERATION_STEPS = 25


def _green_ok(template: str, st: dict, nodes: list) -> bool:
    if template == "BinaryTree":
        return set(nodes) <= st.get("found", set())
    if template == "LinkedList":
        f = st.get("find")
        return bool(f and f.get("hit")) and all(0 <= i < len(st["slots"]) and st["slots"][i] == f["at"]
                                                 for i in nodes)
    return True  # a graph's colours name no result


def _fix_structure(text: str, call, live: dict, segments, s: int, b: int, step: str, wrong: bool,
                   ) -> tuple[str | None, str | None]:
    """A data structure's highlight or ghost with the rules above: (the call, or None to drop it; a log line)."""
    template, where = call.template, f"segment {s} beat {b + 1}"
    state = live[call.target].state
    arg = _NODES_ARG[template]
    if (template, call.action) in _GHOST_NODES and not wrong:
        nodes = _GHOST_NODES[(template, call.action)](call.args)
        new = f'{call.target}.highlight({arg}={json.dumps(nodes)}, colour="{NEUTRAL}")'
        return new, f"{where}: `{text}` drew a wrong idea on a line that isn't one; highlighted its nodes instead"
    if call.action != "highlight":
        return text, None
    nodes = list(call.args.get(arg, []))
    if call.args.get("colour") == "GREEN" and not _green_ok(template, state, nodes):
        text = _with_colour(text, NEUTRAL)
        note = f"{where}: green means found, and {nodes} aren't: recoloured {NEUTRAL.lower()}"
    else:
        note = None
    if step in ASKING_STEPS and not wrong and nodes:
        nxt = _next_step(segments, s, b, call.target, live, _structure_steps(template))
        answer = _answer_nodes(template, state, *nxt) if nxt else set()
        context = len(nodes) > CONTEXT_SHARE * _node_count(template, state) and not set(nodes) <= answer
        if set(nodes) & answer and not context:
            return None, (f"{where} ({step}): dropped `{text}`, which lights {sorted(set(nodes) & answer, key=str)}, "
                          "where the coming step lands, before the line that gives it")
    return text, note


def fix_highlights(segments: list[list[list[str]] | None], steps: list[list[tuple[str, bool]]],
                   lines: list[list[str]], key: dict[str, str] | None = None,
                   ) -> tuple[list[list[list[str]] | None], list[str]]:
    """The calls with the rules above applied to every list. `steps` gives each beat's (step, is the wrong idea);
    `key` maps the colour key's terms to their colours. Returns the calls and a log."""
    key = key or {}
    key_colours = set(key.values())
    out: list[list[list[str]] | None] = []
    log: list[str] = []
    live: dict[str, _Live] = {}
    for s, draws in enumerate(segments):
        if draws is None:
            out.append(None)
            continue
        seg: list[list[str]] = []
        for b, calls in enumerate(draws):
            step, wrong = steps[s][b] if s < len(steps) and b < len(steps[s]) else ("", False)
            line = lines[s][b] if s < len(lines) and b < len(lines[s]) else ""
            beat = []
            for text in calls:
                new = text
                try:
                    call = parse_call(text, {n: o.template for n, o in live.items()})
                except Exception:  # noqa: BLE001 - the checker reports it
                    call = None
                if call is not None and call.template in _NODES_ARG and (
                        call.action == "highlight" or (call.template, call.action) in _GHOST_NODES):
                    new, note = _fix_structure(text, call, live, segments, s, b, step, wrong)
                    if note:
                        log.append(note)
                    if new is None:
                        continue
                elif call is not None and call.template == "ArrayBars" and call.action in ("highlight", "ghost",
                                                                                             "point"):
                    state = live[call.target].state
                    cells = _indices(call)
                    where = f"segment {s} beat {b + 1}"
                    if call.action == "ghost" and not wrong:
                        colour = _key_colour(line, key) or NEUTRAL
                        new = f'{call.target}.highlight(indices={cells}, colour="{colour}")'
                        log.append(f"{where}: `{text}` drew a wrong idea on a line that isn't one; "
                                   f"highlighted the cells instead")
                        call = parse_call(new, {n: o.template for n, o in live.items()})
                    if call.action == "highlight":
                        colour = call.args.get("colour", "YELLOW")
                        # A key term names one role (the minimum, the target, the middle), so only a highlight
                        # of a cell or two takes its colour; a wider one is left as it is.
                        legit_green = state.get("edited") or set(cells) <= green_cells(state)
                        if (key_colours and colour not in key_colours and len(cells) <= 2
                                and (better := _key_colour(line, key)) and better != colour
                                and (better != "GREEN" or legit_green)):
                            log.append(f"{where}: `{text}` used {colour}, not in the colour key; recoloured "
                                       f"{better}, the colour of the term the line names")
                            new, colour = _with_colour(new, better), better
                        # A list changed by hand (swap, set_value) may have cells in place that code can't know.
                        if colour == "GREEN" and not legit_green:
                            log.append(f"{where}: dropped `{text}`: green means sorted or found, and "
                                       f"{sorted(set(cells) - green_cells(state))} aren't")
                            continue
                    if step in ASKING_STEPS and not wrong and cells and call.action == "highlight":
                        nxt = _next_step(segments, s, b, call.target, live)
                        answer = _answer_cells(state, *nxt) if nxt else set()
                        if answer and set(cells) <= answer:
                            log.append(f"{where} ({step}): dropped `{text}`, which shows the answer before the "
                                       "line that gives it")
                            continue
                try:
                    _check(parse_call(new, {n: o.template for n, o in live.items()}), live)
                except Exception:  # noqa: BLE001
                    pass
                beat.append(new)
            seg.append(beat)
        out.append(seg)
    return out, log


__all__ = ["fix_highlights"]
